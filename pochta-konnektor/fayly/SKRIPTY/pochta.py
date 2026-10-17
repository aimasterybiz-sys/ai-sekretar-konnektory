"""Почта: любые ящики, сколько угодно — Gmail, Outlook, iCloud, ukr.net, рабочая почта на своём домене.

  python pochta.py dobavit        страница в браузере: выбрать почту, вписать адрес, подключить (можно несколько)
  python pochta.py --spisok       какие ящики подключены, когда собраны, есть ли ошибки
  python pochta.py                собрать письма всех ящиков с прошлого запуска
  python pochta.py doctor         проверить вход в каждый ящик и где лежит папка секретаря
  python pochta.py udalit <адрес> отключить ящик и стереть его пароль с компьютера
  python pochta.py otpravit --ot <ящик> --komu <адрес> --tema "…" --tekst-fayl 03_RAZBOR/pismo.txt [--otvet-na <id>]
                                  отправить одно письмо (только через skill-publikatsiya после слова «отправляй»)

Читаем только на чтение (EXAMINE + BODY.PEEK): письма не помечаются прочитанными, ничего не удаляется.
Пароли — в хранилище системы, не в файлах. Письма — в 01_ISKHODNIKI/pochta/<дата>.md, как остальные каналы.
"""
import email
import email.policy
import imaplib
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import getaddresses, make_msgid, parseaddr, parsedate_to_datetime, formatdate
from pathlib import Path

from obshchee import ISKHODNIKI, NASTROYKI, ROOT, nachalo_po_umolchaniyu, zapisat, zapomnit
import pochta_dostup as dost
from pochta_dostup import OshibkaPochty

KONTAKTY = NASTROYKI / "pochta-kontakty.json"
ISKLYUCHIT = NASTROYKI / "pochta-isklyuchit.txt"
ZHURNAL_OTPRAVKI = NASTROYKI / "otpravleno.log"
LYUDI = ROOT / "02_ZNANIYA" / "LYUDI.md"
BOLSHOE = 2 * 1024 * 1024          # письма больше 2 МБ — только заголовки
PREDEL_ZA_RAZ = 2000               # писем на папку за один запуск
LIMIT_V_SUTKI = 10                 # писем отправкой за 24 часа
ADRES = re.compile(r"[\w.+'-]+@[\w-]+(?:\.[\w-]+)+")


# ---------- разбор письма ----------

def dekod(s):
    try:
        return str(make_header(decode_header(s or "")))
    except Exception:
        return s or ""


def _chast_v_tekst(part):
    dannye = part.get_payload(decode=True) or b""
    kodirovka = part.get_content_charset() or "utf-8"
    try:
        return dannye.decode(kodirovka, "replace")
    except LookupError:
        return dannye.decode("utf-8", "replace")


def html_v_tekst(h):
    h = re.sub(r"(?is)<(script|style|head).*?</\1>", " ", h)
    h = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</li>|</h\d>", "\n", h)
    h = re.sub(r"(?i)</?(b|i|u|em|strong|span|font|a)(\s[^>]*)?>", "", h)  # выделение внутри строки — без пробела
    h = re.sub(r"<[^>]+>", " ", h)
    for a, b in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'")):
        h = h.replace(a, b)
    return h


def tekst_pisma(msg):
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and not part.get_filename():
                return _chast_v_tekst(part)
        for part in msg.walk():
            if part.get_content_type() == "text/html" and not part.get_filename():
                return html_v_tekst(_chast_v_tekst(part))
        return ""
    t = _chast_v_tekst(msg)
    return html_v_tekst(t) if msg.get_content_type() == "text/html" else t


TSITATA = re.compile(r"\n\s*(?:>|On .{5,200} wrote:|.{3,200} (?:пишет|пише|написав|написала|написал):|"
                     r"-{3,} ?(?:Original Message|Forwarded message|Пересылаемое|Исходное сообщение|Пересланное)|"
                     r"(?:From|От|Від): .{3,200}\n\s*(?:Sent|Date|Отправлено|Дата|Надіслано):)", re.I)


def bez_tsitat(t):
    """Обрезаем историю переписки под ответом — она уже есть в прошлых письмах."""
    t = TSITATA.split("\n" + (t or ""), maxsplit=1)[0]
    return re.sub(r"\s+", " ", t).strip()[:3000]


def vlozheniya(msg):
    return [dekod(p.get_filename()) for p in msg.walk() if p.get_filename()]


def adresa(msg, *polya):
    return [a.lower() for _, a in getaddresses([dekod(msg.get(p, "")) for p in polya]) if "@" in a]


def rassylka(msg):
    if msg.get("List-Unsubscribe") or msg.get("List-Id"):
        return True
    if (msg.get("Precedence") or "").lower() in ("bulk", "list", "junk"):
        return True
    avto = (msg.get("Auto-Submitted") or "no").lower()
    return avto != "no"


def isklyucheniya():
    if not ISKLYUCHIT.exists():
        return set()
    return {s.strip().lower() for s in ISKLYUCHIT.read_text(encoding="utf-8").splitlines()
            if s.strip() and not s.strip().startswith("#")}


def isklyuchen(spisok_adresov, isk):
    for a in spisok_adresov:
        if a in isk or "@" + a.split("@")[-1] in isk or a.split("@")[-1] in isk:
            return True
    return False


# ---------- контакты: кому владелец сам писал ----------

def kontakty():
    if KONTAKTY.exists():
        return json.loads(KONTAKTY.read_text(encoding="utf-8"))
    return {}


def kontakty_dobavit(knt, spisok, kogda):
    for a in spisok:
        z = knt.setdefault(a, {"pisem": 0, "poslednee": ""})
        z["pisem"] += 1
        z["poslednee"] = max(z["poslednee"], kogda)


def kontakty_sokhranit(knt):
    NASTROYKI.mkdir(parents=True, exist_ok=True)
    KONTAKTY.write_text(json.dumps(knt, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")


def kontakty_iz_otpravlennykh(im, papka, moi, knt, dney=365):
    """При первом сборе ящика: адреса из «Отправленных» за год — по заголовкам, без текста писем."""
    data = (datetime.now() - timedelta(days=dney)).strftime("%d-%b-%Y")
    _, d = im.uid("search", None, "SINCE", data)
    uidy = (d[0] or b"").split()[-3000:]
    for i in range(0, len(uidy), 200):
        _, otvet = im.uid("fetch", b",".join(uidy[i:i + 200]).decode(),
                          "(BODY.PEEK[HEADER.FIELDS (TO CC BCC DATE)])")
        for el in otvet or []:
            if isinstance(el, tuple):
                m = email.message_from_bytes(el[1])
                kontakty_dobavit(knt, [a for a in adresa(m, "To", "Cc", "Bcc") if a not in moi],
                                 _data_pisma(m, None).strftime("%Y-%m-%d"))


# ---------- сбор ----------

def _data_pisma(msg, vnutr):
    try:
        return parsedate_to_datetime(msg["Date"]).astimezone().replace(tzinfo=None)
    except Exception:
        pass
    if vnutr:
        t = imaplib.Internaldate2tuple(vnutr)
        if t:
            return datetime.fromtimestamp(time.mktime(t))
    return datetime.now()


def _razobrat_fetch(otvet):
    """Ответ FETCH → [(uid, размер, INTERNALDATE-строка, байты)]"""
    rez = []
    for el in otvet or []:
        if not isinstance(el, tuple):
            continue
        golova = el[0]
        uid = re.search(rb"UID (\d+)", golova)
        razmer = re.search(rb"RFC822\.SIZE (\d+)", golova)
        vnutr = re.search(rb'INTERNALDATE "[^"]+"', golova)
        rez.append((int(uid.group(1)) if uid else 0, int(razmer.group(1)) if razmer else 0,
                    vnutr.group(0) if vnutr else None, el[1]))
    return rez


def sobrat_papku(im, y, papka, otpravlennye, moi, knt, isk, s_daty, schet):
    status, d = im.select(dost.v_kavychkakh(papka), readonly=True)
    if status != "OK":
        print(f"  ! папка {dost.mutf7_dekod(papka)} не открылась")
        return []
    uv = int((im.response("UIDVALIDITY")[1] or [b"0"])[0] or 0)
    st = y["papki"].get(papka)
    if st and st.get("uidvalidity") == uv and not os.environ.get("SEKRETAR_S"):
        _, d = im.uid("search", None, "UID", f"{st['uid'] + 1}:*")
        uidy = [u for u in (d[0] or b"").split() if int(u) > st["uid"]]
    else:
        if otpravlennye and not st:
            kontakty_iz_otpravlennykh(im, papka, moi, knt)
            im.select(dost.v_kavychkakh(papka), readonly=True)
        _, d = im.uid("search", None, "SINCE", (s_daty - timedelta(days=1)).strftime("%d-%b-%Y"))
        uidy = (d[0] or b"").split()
    if len(uidy) > PREDEL_ZA_RAZ:
        print(f"  ! в папке {dost.mutf7_dekod(papka)} {len(uidy)} новых писем — беру последние {PREDEL_ZA_RAZ}")
        uidy = uidy[-PREDEL_ZA_RAZ:]
    max_uid = (st or {}).get("uid", 0) if (st or {}).get("uidvalidity") == uv else 0
    soobshcheniya = []
    for i in range(0, len(uidy), 50):
        pachka = b",".join(uidy[i:i + 50]).decode()
        _, razmery = im.uid("fetch", pachka, "(UID RFC822.SIZE)")
        bolshie = set()
        for r in razmery or []:
            golova = r if isinstance(r, bytes) else r[0]
            u, s = re.search(rb"UID (\d+)", golova or b""), re.search(rb"RFC822\.SIZE (\d+)", golova or b"")
            if u and s and int(s.group(1)) > BOLSHOE:
                bolshie.add(int(u.group(1)))
        malye = [u.decode() for u in uidy[i:i + 50] if int(u) not in bolshie]
        polucheno = []
        if malye:
            _, otvet = im.uid("fetch", ",".join(malye), "(UID RFC822.SIZE INTERNALDATE BODY.PEEK[])")
            polucheno += _razobrat_fetch(otvet)
        if bolshie:
            _, otvet = im.uid("fetch", ",".join(map(str, bolshie)), "(UID RFC822.SIZE INTERNALDATE BODY.PEEK[HEADER])")
            polucheno += _razobrat_fetch(otvet)
        for uid, razmer, vnutr, syroe in polucheno:
            max_uid = max(max_uid, uid)
            msg = email.message_from_bytes(syroe)
            kogda = _data_pisma(msg, vnutr)
            ot_imya, ot_adres = parseaddr(dekod(msg.get("From")))
            ot_adres = ot_adres.lower()
            komu = adresa(msg, "To", "Cc")
            ya_avtor = ot_adres in moi
            if ya_avtor:
                kontakty_dobavit(knt, [a for a in komu + adresa(msg, "Bcc") if a not in moi], kogda.strftime("%Y-%m-%d"))
            if (not st or os.environ.get("SEKRETAR_S")) and kogda < s_daty:
                continue
            if isklyuchen([ot_adres] + komu, isk):
                schet["isklyucheno"] += 1
                continue
            if not ya_avtor and rassylka(msg):
                schet["rassylki"] += 1
                continue
            tema = dekod(msg.get("Subject")) or "(без темы)"
            if razmer > BOLSHOE:
                tekst = f"[большое письмо, {razmer / 1048576:.1f} МБ — текст не загружен, откройте в почте]"
            else:
                tekst = bez_tsitat(tekst_pisma(msg))
            fayly = vlozheniya(msg)
            if fayly:
                tekst += " [вложения: " + ", ".join(fayly)[:300] + "]"
            mid = (msg.get("Message-ID") or "").strip().strip("<>").strip()
            soobshcheniya.append({
                "id": "mail:" + (mid or f"{y['adres']}:{papka}:{uv}:{uid}"),
                "vremya": kogda,
                "chat": f"{tema} (кому: {', '.join(komu)[:80]}) [ящик {y['adres']}]",
                "avtor": "Я" if ya_avtor else f"{dekod(ot_imya) or ot_adres} <{ot_adres}>",
                "tekst": tekst,
            })
    y["papki"][papka] = {"uidvalidity": uv, "uid": max_uid}
    return soobshcheniya


def sobrat():
    pereneseno = dost.perenesti_iz_env()
    if pereneseno:
        print(f"Перенёс ящик {pereneseno} из .env в хранилище паролей системы.")
    dannye = dost.zagruzit()
    if not dannye["yashchiki"]:
        sys.exit("Почта не подключена. Скажите секретарю «подключи почту» или запустите: python pochta.py dobavit")
    yavno = os.environ.get("SEKRETAR_S")
    s_daty = datetime.strptime(yavno, "%Y-%m-%d") if yavno else nachalo_po_umolchaniyu()
    moi = {y["adres"] for y in dannye["yashchiki"]}
    knt, isk = kontakty(), isklyucheniya()
    start = datetime.now()
    vse, itogi, oshibki = [], [], 0
    for y in dannye["yashchiki"]:
        schet = {"rassylki": 0, "isklyucheno": 0}
        try:
            im = dost.imap_vkhod(y)
        except OshibkaPochty as e:
            y["oshibka"] = str(e)
            itogi.append(f"  ✗ {y['adres']}: {e}")
            oshibki += 1
            continue
        try:
            if not y.get("otpravlennye"):
                y["otpravlennye"] = dost.papka_otpravlennykh(dost.papki(im))
            sobrano = sobrat_papku(im, y, "INBOX", False, moi, knt, isk, s_daty, schet)
            if y.get("otpravlennye"):
                sobrano += sobrat_papku(im, y, y["otpravlennye"], True, moi, knt, isk, s_daty, schet)
            vse += sobrano
            y["oshibka"], y["sobrano"] = None, start.isoformat(timespec="seconds")
            dop = ", ".join(f"{k} {v}" for k, v in (("рассылок пропущено", schet["rassylki"]),
                                                     ("исключено", schet["isklyucheno"])) if v)
            itogi.append(f"  ✓ {y['adres']}: писем {len(sobrano)}" + (f" ({dop})" if dop else ""))
        except (imaplib.IMAP4.error, OSError) as e:
            y["oshibka"] = f"сбор прервался: {type(e).__name__}"
            itogi.append(f"  ✗ {y['adres']}: сбор прервался ({type(e).__name__}), повторю в следующий раз")
            oshibki += 1
        finally:
            try:
                im.logout()
            except Exception:
                pass
    novykh = zapisat("pochta", vse) if vse else 0
    dost.sokhranit(dannye)
    kontakty_sokhranit(knt)
    zapomnit("pochta", start)
    print(f"Почта: с {s_daty:%d.%m} (или с прошлого сбора), писем {len(vse)}, новых {novykh}.")
    print("\n".join(itogi))
    if oshibki == len(dannye["yashchiki"]):
        sys.exit(1)


# ---------- список, проверка, удаление ----------

def spisok():
    dannye = dost.zagruzit()
    if not dannye["yashchiki"]:
        print("Почта не подключена. Подключить: python pochta.py dobavit")
        return
    for y in dannye["yashchiki"]:
        sobrano = (y.get("sobrano") or "ещё не собирали").replace("T", " ")
        otpr = "отправка есть" if y.get("otpravka") else "только чтение"
        print(f"{y['adres']} · {y['imya']} · {otpr} · собрано: {sobrano}"
              + (f" · ОШИБКА: {y['oshibka']}" if y.get("oshibka") else ""))


OBLAKA = ("Mobile Documents", "iCloud", "OneDrive", "Dropbox", "Google Drive", "GoogleDrive", "CloudStorage")


def doctor():
    put = str(ROOT)
    if any(o.lower() in put.lower() for o in OBLAKA):
        print(f"⚠ Папка секретаря лежит в облачной папке ({put}). Письма и настройки уезжают в облако — "
              "перенесите папку в обычное место, например в Документы без синхронизации.")
    else:
        print(f"✓ Папка секретаря не в облаке: {put}")
    try:
        import keyring
        print(f"✓ Хранилище паролей: {type(keyring.get_keyring()).__name__}")
    except ImportError:
        print("✗ Нет библиотеки keyring: python -m pip install -r SKRIPTY/requirements.txt")
    print("✓ Вход через Microsoft включён" if dost.ms_client_id()
          else "· Вход через Microsoft не включён (Outlook подключить нельзя, остальные почты — можно)")
    for y in dost.zagruzit()["yashchiki"]:
        try:
            im = dost.imap_vkhod(y)
            im.logout()
            stroka = f"✓ {y['adres']}: чтение работает"
        except OshibkaPochty as e:
            print(f"✗ {y['adres']}: {e}")
            continue
        if y.get("otpravka"):
            try:
                dost.smtp_vkhod(y).quit()
                stroka += ", отправка работает"
            except OshibkaPochty as e:
                stroka += f", отправка НЕ работает: {e}"
        print(stroka)


def udalit(adres):
    if dost.udalit(adres):
        print(f"Ящик {adres} отключён, пароль стёрт с компьютера. Уже собранные письма остались в 01_ISKHODNIKI/pochta.")
    else:
        print(f"Ящика {adres} нет среди подключённых.")


# ---------- отправка ----------

def izvestnye_adresa():
    """Кому можно писать: тем, кому владелец сам писал (из «Отправленных»), и адресам из 02_ZNANIYA/LYUDI.md."""
    izv = set(kontakty())
    if LYUDI.exists():
        izv |= {a.lower() for a in ADRES.findall(LYUDI.read_text(encoding="utf-8"))}
    return izv


def otpravok_za_sutki():
    if not ZHURNAL_OTPRAVKI.exists():
        return 0
    granitsa = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
    return sum(1 for s in ZHURNAL_OTPRAVKI.read_text(encoding="utf-8").splitlines()
               if s[:16] >= granitsa and " · почта · " in s)


def nayti_pismo(mid):
    """Строка письма в 01_ISKHODNIKI/pochta по id — для темы ответа и проверки, что письмо было."""
    kluch = f"[mail:{mid}]"
    for f in sorted((ISKHODNIKI / "pochta").glob("*.md"), reverse=True):
        for s in f.read_text(encoding="utf-8").splitlines():
            if s.startswith(kluch):
                return s
    return None


def otpravit(argv):
    def arg(k):
        return argv[argv.index(k) + 1] if k in argv and argv.index(k) + 1 < len(argv) else None

    ot, komu, tema = (arg("--ot") or "").lower().strip(), (arg("--komu") or "").lower().strip(), arg("--tema")
    tekst, fayl, otvet_na = arg("--tekst"), arg("--tekst-fayl"), arg("--otvet-na")
    if fayl:
        p = Path(fayl) if Path(fayl).is_absolute() else ROOT / fayl
        if not p.exists():
            sys.exit(f"Нет файла с текстом: {fayl}")
        tekst = p.read_text(encoding="utf-8")
    dannye = dost.zagruzit()
    if not ot and len(dannye["yashchiki"]) == 1:
        ot = dannye["yashchiki"][0]["adres"]
    y = dost.yashchik(ot, dannye) if ot else None
    if not y:
        sys.exit("Укажите, с какого ящика отправлять: --ot <адрес>. Подключённые: "
                 + ", ".join(x["adres"] for x in dannye["yashchiki"]))
    if not y.get("otpravka"):
        sys.exit(f"С ящика {ot} отправка не настроена (при подключении сервер не принял вход для отправки). "
                 "Проверьте: python pochta.py doctor")
    if not ADRES.fullmatch(komu or ""):
        sys.exit("Нужен один адрес получателя: --komu anna@firma.com")
    if not tema or not (tekst or "").strip():
        sys.exit('Нужны тема и текст: --tema "…" --tekst-fayl 03_RAZBOR/pismo.txt')
    if len(tekst) > 20000:
        sys.exit("Текст длиннее 20 000 знаков — так секретарь не отправляет.")
    if komu not in izvestnye_adresa() and "--novyy-adres" not in argv:
        sys.exit(f"Адреса {komu} нет среди тех, кому вы уже писали, и в 02_ZNANIYA/LYUDI.md. "
                 "Новому адресу секретарь пишет только если владелец в чате сам подтвердил именно этот адрес "
                 "(тогда команда с ключом --novyy-adres).")
    if otpravok_za_sutki() >= LIMIT_V_SUTKI:
        sys.exit(f"За сутки уже отправлено {LIMIT_V_SUTKI} писем — это предел секретаря. Остальное — завтра или из почты.")

    msg = EmailMessage()
    msg["From"] = y["adres"]
    msg["To"] = komu
    msg["Subject"] = tema
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=y["adres"].split("@")[1])
    if otvet_na:
        mid = otvet_na.replace("mail:", "", 1).strip().strip("<>")
        if not nayti_pismo(mid):
            sys.exit(f"Не нашёл письмо {otvet_na} в 01_ISKHODNIKI/pochta — не на что отвечать.")
        msg["In-Reply-To"] = f"<{mid}>"
        msg["References"] = f"<{mid}>"
    msg.set_content(tekst.strip() + "\n")

    sm = dost.smtp_vkhod(y)
    try:
        sm.send_message(msg)
    finally:
        try:
            sm.quit()
        except Exception:
            pass
    kratko = re.sub(r"\s+", " ", tekst)[:150]
    with open(ZHURNAL_OTPRAVKI, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M} · почта · {y['adres']} → {komu} · {tema[:100]} · {kratko}\n")
    if fayl:
        try:
            p.unlink()  # чтобы этот же текст случайно не ушёл второй раз
        except Exception:
            pass
    kopiya = polozhit_v_otpravlennye(y, msg)
    print(f"Отправлено: {y['adres']} → {komu} · «{tema}». {kopiya}")


def polozhit_v_otpravlennye(y, msg):
    """Gmail и Microsoft кладут копию в «Отправленные» сами; остальные — нет. Ждём до 6 секунд, нет копии — кладём."""
    if not y.get("otpravlennye"):
        return "Папку «Отправленные» не нашёл — копии в ящике нет."
    try:
        im = dost.imap_vkhod(y)
    except OshibkaPochty:
        return "Копию в «Отправленные» положить не удалось."
    try:
        mid = msg["Message-ID"]
        for _ in range(3):
            im.select(dost.v_kavychkakh(y["otpravlennye"]), readonly=True)
            _, d = im.uid("search", None, "HEADER", "Message-ID", mid)
            if d and d[0]:
                return "Копия есть в «Отправленных»."
            time.sleep(2)
        im.append(dost.v_kavychkakh(y["otpravlennye"]), "(\\Seen)", imaplib.Time2Internaldate(time.time()),
                  msg.as_bytes(policy=email.policy.SMTP))
        return "Копию положил в «Отправленные»."
    except Exception:
        return "Копию в «Отправленные» положить не удалось."
    finally:
        try:
            im.logout()
        except Exception:
            pass


if __name__ == "__main__":
    a = sys.argv[1:]
    try:
        if not a:
            sobrat()
        elif a[0] == "dobavit":
            import pochta_forma
            pochta_forma.zapustit()
        elif a[0] == "--spisok":
            spisok()
        elif a[0] == "doctor":
            doctor()
        elif a[0] == "udalit" and len(a) > 1:
            udalit(a[1])
        elif a[0] == "otpravit":
            otpravit(a[1:])
        else:
            print(__doc__)
    except OshibkaPochty as e:
        sys.exit(str(e))
