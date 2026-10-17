"""WhatsApp через wacli — одна программа на Mac и Windows: читает переписку и умеет отправлять.

wacli (github.com/openclaw/wacli, MIT) входит в WhatsApp как ещё одно связанное устройство — как Telegram
у нас входит через Telethon. Переписка копируется в локальную базу NASTROYKI/wacli/, оттуда её берёт секретарь.
Файл SKRIPTY/bin/wacli ставит скрипт wa_ustanovka.py (готовая сборка с GitHub, сверенная по контрольной сумме).

  python wa.py vhod              вход по QR (телефон: WhatsApp → Связанные устройства → Привязка устройства)
  python wa.py vhod --telefon +371XXXXXXXX   вход без QR: код из 8 знаков вводится на телефоне
  python wa.py sluzhba           включить фоновую службу: каждые 10 минут забирает новое, вычищает личные чаты
  python wa.py vychistit         сразу удалить с компьютера чаты из NASTROYKI/chaty-isklyuchit.txt
  python wa.py doctor            всё ли в порядке: вход, служба, последняя синхронизация, версия
  python wa.py sluzhba --stop    выключить службу          python wa.py sluzhba --status    состояние
  python wa.py --spisok          чаты по свежести → NASTROYKI/whatsapp-vse-chaty.md
  python wa.py                   собрать выбранные чаты (NASTROYKI/chaty-whatsapp.txt) с прошлого запуска
  python wa.py otpravit --komu "Название чата" --tekst "..."        отправить текст
  python wa.py otpravit --komu "Название чата" --golos файл.m4a     отправить голосовое (нужен ffmpeg)

Чтение — всегда в режиме «только чтение» (--read-only): ничего не помечается прочитанным, синих галочек нет.
Отправляет только команда otpravit, её вызывает скилл skill-publikatsiya после слова владельца «отправляй».
"""
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from obshchee import GOLOS, NASTROYKI, ROOT, bezopasnoe_imya, env, okno, spisok_chatov, zapisat, zapomnit
import golos

BIN = ROOT / "SKRIPTY" / "bin" / ("wacli.exe" if os.name == "nt" else "wacli")
STORE = NASTROYKI / "wacli"
KARTA = NASTROYKI / "whatsapp-chaty.json"      # название чата → адрес (JID)
ISKLYUCHIT = NASTROYKI / "chaty-isklyuchit.txt"  # личные чаты: не хранить на компьютере совсем
INTERVAL_MIN = 10                               # как часто служба подтягивает переписку
ZHURNAL_OTPRAVKI = NASTROYKI / "otpravleno.log"
SLUZHBA = "com.sekretar.wacli"
QR = NASTROYKI / "qr-whatsapp.png"


# ---------- вызов wacli ----------
def wacli(*args, read_only=True, json_out=True, timeout=300, check=True):
    if not BIN.exists():
        sys.exit("Нет SKRIPTY/bin/wacli. Сначала: python SKRIPTY/wa_ustanovka.py")
    cmd = [str(BIN), "--store", str(STORE)]
    if json_out:
        cmd.append("--json")
    if read_only:
        cmd.append("--read-only")
    else:
        cmd += ["--lock-wait", "90s"]
    cmd += [str(a) for a in args]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    if check and r.returncode != 0:
        raise RuntimeError((r.stderr.strip() or r.stdout.strip())[-1200:] or f"wacli вернул код {r.returncode}")
    if not json_out:
        return r.stdout
    text = r.stdout.strip()
    if not text:
        return None
    try:
        otvet = json.loads(text)
    except json.JSONDecodeError:
        # NDJSON — по объекту на строку
        return [json.loads(s) for s in text.splitlines() if s.strip().startswith("{")]
    # wacli заворачивает ответ: {"success": true, "data": …, "error": null}
    if isinstance(otvet, dict) and "success" in otvet and "data" in otvet:
        if not otvet["success"] and check:
            raise RuntimeError(str(otvet.get("error"))[:800])
        return otvet["data"]
    return otvet


def spisok_iz(otvet, *klyuchi):
    """Ответ wacli может быть списком или словарём с полем-списком — достаём список."""
    if otvet is None:
        return []
    if isinstance(otvet, list):
        return otvet
    for k in klyuchi:
        if isinstance(otvet.get(k), list):
            return otvet[k]
    for v in otvet.values():
        if isinstance(v, list):
            return v
    return []


def pole(d, *imena, default=None):
    for i in imena:
        if i in d and d[i] not in (None, ""):
            return d[i]
    return default


def vremya_iz(z):
    if z is None:
        return None
    if isinstance(z, (int, float)):
        if z > 1e12:
            z /= 1000
        return datetime.fromtimestamp(z)
    s = str(z).replace("Z", "+00:00")
    try:
        t = datetime.fromisoformat(s)
    except ValueError:
        return None
    return t.astimezone().replace(tzinfo=None) if t.tzinfo else t


# ---------- вход ----------
def vhod_po_nomeru(nomer):
    """Вход без QR: WhatsApp покажет поле для 8-значного кода, который печатает wacli."""
    STORE.mkdir(parents=True, exist_ok=True)
    nomer = re.sub(r"[^\d]", "", nomer)
    print("На телефоне: WhatsApp → Настройки → Связанные устройства → Привязка устройства →")
    print("внизу «Привязать по номеру телефона». Сейчас здесь появится код — введите его на телефоне.", flush=True)
    cmd = [str(BIN), "--store", str(STORE), "auth", "--phone", nomer, "--history-days", "14", "--idle-exit", "45s"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    for line in p.stdout:
        line = line.rstrip()
        if line and not line.startswith("{"):
            print("  " + line[:200], flush=True)
    p.wait()
    st = wacli("auth", "status", check=False) or {}
    if st.get("authenticated"):
        print("Готово: WhatsApp подключён. Дальше: python wa.py sluzhba, потом python wa.py --spisok")
    else:
        sys.exit("Вход не подтверждён. Запустите ещё раз и введите код на телефоне в течение минуты.")


def vhod():
    STORE.mkdir(parents=True, exist_ok=True)
    print("Возьмите телефон: WhatsApp → Настройки → Связанные устройства → Привязка устройства.")
    print("Сейчас откроется картинка с QR — наведите камеру. Код обновляется сам.", flush=True)
    import qrcode
    cmd = [str(BIN), "--store", str(STORE), "auth", "--qr-format", "text", "--history-days", "14", "--idle-exit", "45s"]
    start = time.time()
    pokazan = 0
    st = {}
    while time.time() - start < 600 and not st.get("authenticated"):
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        for line in p.stdout:
            line = line.rstrip()
            # wacli выдаёт ссылку https://wa.me/settings/linked_devices#2@… — кодируем её целиком
            kod = re.search(r"(https://wa\.me/settings/linked_devices#\S+|\b\d@[A-Za-z0-9+/=,_\-]{60,})", line)
            if kod:
                qrcode.make(kod.group(1)).save(QR)
                pokazan += 1
                # картинку открываем каждый раз: просмотрщик не всегда замечает, что файл сменился
                subprocess.run(["open", str(QR)]) if sys.platform == "darwin" else os.startfile(QR)  # noqa
                print(("QR открыт" if pokazan == 1 else f"QR обновлён ({pokazan})") + " — наведите камеру", flush=True)
                continue
            if line and not line.startswith("{") and "timed out" not in line:
                print("  " + line[:160], flush=True)
            if time.time() - start > 600:
                p.kill()
                break
        p.wait()
        st = wacli("auth", "status", check=False) or {}
        if not st.get("authenticated") and time.time() - start < 600:
            print("Код устарел — запрашиваю новый…", flush=True)
    if QR.exists():
        QR.unlink()
    if st.get("authenticated"):
        print("Готово: WhatsApp подключён. Первая копия переписки уже загружена.")
        print("Дальше: python wa.py sluzhba — чтобы переписка подтягивалась постоянно, потом python wa.py --spisok")
    else:
        sys.exit("Вход не подтверждён. Проверьте на телефоне список связанных устройств и запустите ещё раз.")


# ---------- личные чаты, которые не храним ----------
def isklyuchennye():
    """JID чатов из NASTROYKI/chaty-isklyuchit.txt: номер телефона, JID или название чата."""
    if not ISKLYUCHIT.exists():
        return []
    karta = json.loads(KARTA.read_text(encoding="utf-8")) if KARTA.exists() else {}
    jids = []
    for s in spisok_chatov(ISKLYUCHIT.name):
        j = jid_po_imeni(s, karta)
        if j:
            jids.append(j)
    return jids


def vychistit():
    """Удаляет исключённые чаты из локальной базы и затирает освободившееся место."""
    jids = isklyuchennye()
    if not jids:
        return 0
    for j in jids:
        wacli("chats", "cleanup", "--jid", j, "--confirm", read_only=False, check=False, timeout=120)
    # SQLite при удалении только помечает место свободным — пересобираем файл, чтобы текста не осталось на диске
    import sqlite3
    try:
        con = sqlite3.connect(STORE / "wacli.db", timeout=30)
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        con.execute("VACUUM")
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        con.close()
    except sqlite3.Error as e:
        print(f"  ! не удалось пересобрать базу: {e}")
    karta = json.loads(KARTA.read_text(encoding="utf-8")) if KARTA.exists() else {}
    imena = {k for k, v in karta.items() if v in jids}
    if KARTA.exists():
        KARTA.write_text(json.dumps({k: v for k, v in karta.items() if v not in jids}, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    vse = NASTROYKI / "whatsapp-vse-chaty.md"
    if vse.exists():
        stroki = [s for s in vse.read_text(encoding="utf-8").splitlines()
                  if not any(j in s for j in jids) and not any(f"| {i} |" in s for i in imena)]
        vse.write_text("\n".join(stroki) + "\n", encoding="utf-8")
    return len(jids)


def v_zhurnal_sluzhby(stroka):
    with open(STORE / "sluzhba.log", "a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M} · {stroka}\n")


def obnovit_wacli(prichina):
    """Ставит последнюю сборку wacli и пишет об этом в журнал службы и в _ZHURNAL.md секретаря."""
    import wa_ustanovka
    try:
        v = wa_ustanovka.postavit()
    except SystemExit as e:
        v_zhurnal_sluzhby(f"обновление wacli не удалось ({prichina}): {e}")
        return
    v_zhurnal_sluzhby(f"wacli обновлён до {v} ({prichina})")
    with open(ROOT / "_ZHURNAL.md", "a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M} · WhatsApp: программа wacli обновлена до {v} ({prichina})\n")


def proverit_obnovlenie():
    """Раз в сутки: есть ли новее сборка — тогда обновиться (WhatsApp со временем отключает старые версии)."""
    metka = STORE / "obnovlenie.txt"
    if metka.exists() and time.time() - metka.stat().st_mtime < 86400:
        return
    metka.write_text(datetime.now().isoformat(timespec="seconds"), encoding="utf-8")
    import wa_ustanovka
    stoit, novaya = wa_ustanovka.ustanovlennaya(), wa_ustanovka.poslednyaya(wa_ustanovka.ISTOCHNIKI[0])
    if stoit and novaya and stoit != novaya:
        obnovit_wacli(f"вышла версия {novaya}, стояла {stoit}")


def cikl():
    """Один такт службы: забрать новое из WhatsApp, сразу вычистить личные чаты, при необходимости обновиться."""
    STORE.mkdir(parents=True, exist_ok=True)
    try:
        r = subprocess.run([str(BIN), "--store", str(STORE), "sync", "--once", "--idle-exit", "20s",
                            "--presence-mode", "quiet", "--max-db-size", "1GB"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
        vyvod = (r.stdout + r.stderr).lower()
        novykh = re.search(r"messages stored:\s*(\d+)", vyvod)
        v_zhurnal_sluzhby(f"синхронизация: {'ок' if r.returncode == 0 else 'ошибка ' + str(r.returncode)}"
                          + (f", новых {novykh.group(1)}" if novykh else ""))
        if "client outdated" in vyvod or "405" in vyvod:
            obnovit_wacli("WhatsApp сообщил, что версия устарела")
        elif "logged out" in vyvod or "session revoked" in vyvod:
            v_zhurnal_sluzhby("WhatsApp отвязал это устройство — нужен вход: python wa.py vhod")
    except subprocess.TimeoutExpired:
        v_zhurnal_sluzhby("синхронизация не уложилась в 10 минут")
    vychistit()
    try:
        proverit_obnovlenie()
    except Exception as e:  # обновление не должно ломать сбор
        v_zhurnal_sluzhby(f"проверка обновления: {e}")


def zdorove():
    """Понятный отчёт: вход, служба, свежесть, версия, исключённые чаты."""
    import wa_ustanovka
    d = wacli("doctor", check=False) or {}
    st = d.get("store") or {}
    print(f"Программа wacli: {wa_ustanovka.ustanovlennaya() or 'не установлена'}")
    if d.get("session_revoked"):
        print("Вход в WhatsApp: ОТВЯЗАН (телефон был офлайн ~14 дней или устройство удалили). Нужно: python wa.py vhod")
    else:
        print(f"Вход в WhatsApp: {'есть' if d.get('authenticated') else 'нет — python wa.py vhod'}")
    sledy = [f.stat().st_mtime for f in (STORE / "sluzhba.log", STORE / "wacli.db") if f.exists()]
    if sledy:
        posl = datetime.fromtimestamp(max(sledy))
        minut = int((datetime.now() - posl).total_seconds() // 60)
        print(f"Последняя синхронизация: {posl:%d.%m %H:%M} ({minut} мин назад)"
              + ("" if minut <= 3 * INTERVAL_MIN else " — служба не работает? python wa.py sluzhba"))
    print(f"В базе: сообщений {st.get('messages', '?')}, чатов {st.get('chats', '?')}")
    print(f"Личных чатов в исключениях: {len(isklyuchennye())}")
    sluzhba("--status")


# ---------- фоновая служба ----------
def sluzhba_komanda():
    python = sys.executable
    if os.name == "nt":
        # pythonw — тот же Python без чёрного окна: иначе раз в 10 минут мигала бы консоль
        bez_okna = Path(python).with_name("pythonw.exe")
        if bez_okna.exists():
            python = str(bez_okna)
    return [python, str(Path(__file__).resolve()), "cikl"]


def sluzhba(deystvie):
    STORE.mkdir(parents=True, exist_ok=True)
    log = STORE / "sluzhba.log"
    if sys.platform == "darwin":
        plist = Path.home() / "Library" / "LaunchAgents" / f"{SLUZHBA}.plist"
        uid = os.getuid()
        if deystvie == "--status":
            r = subprocess.run(["launchctl", "print", f"gui/{uid}/{SLUZHBA}"], capture_output=True, text=True)
            print("Служба: " + (f"включена, запускается каждые {INTERVAL_MIN} минут" if r.returncode == 0
                                else "выключена — включить: python wa.py sluzhba"))
            return
        subprocess.run(["launchctl", "bootout", f"gui/{uid}", str(plist)], capture_output=True)
        if deystvie == "--stop":
            plist.unlink(missing_ok=True)
            print("Служба выключена.")
            return
        else:
            plist.parent.mkdir(parents=True, exist_ok=True)
            with open(plist, "wb") as f:
                plistlib.dump({"Label": SLUZHBA, "ProgramArguments": sluzhba_komanda(), "RunAtLoad": True,
                               "StartInterval": INTERVAL_MIN * 60, "StandardOutPath": str(log),
                               "StandardErrorPath": str(log), "WorkingDirectory": str(ROOT / "SKRIPTY")}, f)
            r = subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", str(plist)], capture_output=True, text=True)
            if r.returncode != 0:
                sys.exit("Не удалось запустить службу: " + (r.stderr or r.stdout))
            print(f"Служба включена: каждые {INTERVAL_MIN} минут забирает новое из WhatsApp и вычищает личные чаты "
                  "из NASTROYKI/chaty-isklyuchit.txt. Работает и после перезагрузки.")
    elif os.name == "nt":
        imya = "SekretarWA"
        if deystvie == "--stop":
            subprocess.run(["schtasks", "/End", "/TN", imya], capture_output=True)
            subprocess.run(["schtasks", "/Delete", "/TN", imya, "/F"], capture_output=True)
            print("Служба выключена.")
            return
        if deystvie == "--status":
            r = subprocess.run(["schtasks", "/Query", "/TN", imya], capture_output=True, text=True)
            print("Служба: " + (f"включена, запускается каждые {INTERVAL_MIN} минут" if r.returncode == 0
                                else "выключена — включить: python wa.py sluzhba"))
            return
        else:
            tr = subprocess.list2cmdline(sluzhba_komanda())
            r = subprocess.run(["schtasks", "/Create", "/TN", imya, "/SC", "MINUTE", "/MO", str(INTERVAL_MIN),
                                "/RL", "LIMITED", "/TR", tr, "/F"], capture_output=True, text=True)
            if r.returncode != 0:
                sys.exit("Не удалось создать задачу: " + (r.stderr or r.stdout))
            subprocess.run(["schtasks", "/Run", "/TN", imya], capture_output=True)
            print(f"Служба включена: задача SekretarWA каждые {INTERVAL_MIN} минут забирает новое и вычищает личные чаты.")
    else:
        sys.exit("Для этой системы службу настройте вручную: " + " ".join(sluzhba_komanda()))
    time.sleep(3)
    d = wacli("doctor", check=False) or {}
    print(f"Вход в WhatsApp: {'есть' if d.get('authenticated') else 'нет'}, "
          f"сообщений в базе: {(d.get('store') or {}).get('messages', '?')}")


# ---------- чаты ----------
def chaty_zhivye(limit=80):
    otvet = wacli("chats", "list", "--limit", limit, "--no-archived")
    skryt = set(isklyuchennye()) if ISKLYUCHIT.exists() and KARTA.exists() else set()
    chaty = []
    for c in spisok_iz(otvet, "chats", "items", "results"):
        jid = pole(c, "jid", "chat_jid", "id", default="")
        if not jid or jid.endswith(("@status", "@broadcast", "@newsletter")) or jid in skryt:
            continue
        imya = pole(c, "name", "title", "display_name", "subject", default=jid.split("@")[0])
        chaty.append({"jid": jid, "imya": imya, "gruppa": jid.endswith("@g.us"),
                      "t": vremya_iz(pole(c, "last_message_at", "last_message_ts", "last_activity", "updated_at", "timestamp")),
                      "neprochitano": pole(c, "unread_count", default=0)})
    return chaty


def spisok():
    chaty = chaty_zhivye()
    KARTA.write_text(json.dumps({c["imya"]: c["jid"] for c in chaty}, ensure_ascii=False, indent=2), encoding="utf-8")
    stroki = ["# WhatsApp — чаты по свежести", "",
              "Скопируйте нужные названия в NASTROYKI/chaty-whatsapp.txt (по одному в строке, символ в символ).", "",
              "| № | Чат | Тип | Последнее |", "|---|---|---|---|"]
    for i, c in enumerate(chaty, 1):
        t = c["t"].strftime("%Y-%m-%d %H:%M") if c["t"] else "—"
        stroki.append(f"| {i} | {c['imya']} | {'группа' if c['gruppa'] else 'личный'} | {t} |")
    NASTROYKI.mkdir(parents=True, exist_ok=True)
    (NASTROYKI / "whatsapp-vse-chaty.md").write_text("\n".join(stroki) + "\n", encoding="utf-8")
    print("\n".join(stroki))


def chisto(s):
    """Без невидимых знаков направления текста (WhatsApp ставит их вокруг номеров) и лишних пробелов."""
    return re.sub(r"[‎‏‪-‮⁦-⁩]", "", s).strip().casefold()


def jid_po_imeni(imya, karta):
    if imya in karta:
        return karta[imya]
    if "@" in imya:
        return imya
    for k, v in karta.items():
        if chisto(k) == chisto(imya):
            return v
    tsifry = re.sub(r"\D", "", imya)
    if len(tsifry) >= 8 and re.fullmatch(r"[\d\s+()\-]+", chisto(imya)):
        for v in karta.values():
            if v.split("@")[0] == tsifry:
                return v
        return f"{tsifry}@s.whatsapp.net"
    return None


# ---------- сбор ----------
def sobrat(syroy=False):
    vybrano = spisok_chatov("chaty-whatsapp.txt")
    if not vybrano:
        sys.exit("NASTROYKI/chaty-whatsapp.txt пуст. Сначала: python wa.py --spisok и выберите чаты.")
    d = wacli("doctor", check=False) or {}
    if d.get("session_revoked"):
        sys.exit("WhatsApp отвязал это устройство (телефон был офлайн около 14 дней или устройство удалили "
                 "в «Связанных устройствах»). Войдите заново: python wa.py vhod")
    if not d.get("authenticated"):
        sys.exit("WhatsApp не подключён. Сначала: python wa.py vhod")
    # свежесть: когда служба последний раз отработала (её журнал пишется каждый такт)
    sledy = [f.stat().st_mtime for f in (STORE / "sluzhba.log", STORE / "HEARTBEAT", STORE / "wacli.db") if f.exists()]
    posledniy = datetime.fromtimestamp(max(sledy)) if sledy else None
    if posledniy and (datetime.now() - posledniy).total_seconds() > 3600:
        print(f"  ! WhatsApp последний раз синхронизировался {posledniy:%d.%m %H:%M}: служба выключена? "
              "Беру то, что уже в базе. Включить: python wa.py sluzhba")
    karta = json.loads(KARTA.read_text(encoding="utf-8")) if KARTA.exists() else {}
    if not karta:
        karta = {c["imya"]: c["jid"] for c in chaty_zhivye()}
        KARTA.write_text(json.dumps(karta, ensure_ascii=False, indent=2), encoding="utf-8")
    s_momenta = okno("whatsapp")
    posle = s_momenta.astimezone().isoformat(timespec="seconds")
    GOLOS.mkdir(parents=True, exist_ok=True)
    soobshcheniya, ne_naydeno = [], []
    for imya in vybrano:
        jid = jid_po_imeni(imya, karta)
        if not jid:
            ne_naydeno.append(imya)
            continue
        otvet = wacli("messages", "list", "--chat", jid, "--after", posle, "--limit", 5000, "--asc")
        msgs = spisok_iz(otvet, "messages", "items", "results")
        if syroy and msgs:
            print(json.dumps(msgs[0], ensure_ascii=False, indent=2))
        gruppa = jid.endswith("@g.us")
        for m in msgs:
            if m.get("Revoked") or m.get("ReactionEmoji"):
                continue
            mid = pole(m, "MsgID", "id", "msg_id", "message_id")
            t = vremya_iz(pole(m, "Timestamp", "timestamp", "ts"))
            if not mid or not t or t < s_momenta:
                continue
            ot_menya = bool(pole(m, "FromMe", "from_me", default=False))
            tip = str(pole(m, "MediaType", "media_type", "type", default="text") or "text").lower()
            tekst = pole(m, "DisplayText", "Text", "text", "body", default="") or ""
            podpis = pole(m, "MediaCaption", "media_caption", "caption", default="") or ""
            if tip in ("audio", "ptt", "voice"):
                fayl = GOLOS / f"wa_{bezopasnoe_imya(mid)}.ogg"
                if not fayl.exists() and not fayl.with_suffix(".txt").exists():
                    try:
                        wacli("media", "download", "--chat", jid, "--id", mid, "--output", fayl, timeout=120)
                    except RuntimeError as e:
                        golos.NE_RASSHIFROVANO.append(mid)
                        tekst = f"[голосовое, расшифровать не удалось: {str(e)[:80]}]"
                if fayl.exists() or fayl.with_suffix(".txt").exists():
                    tekst = golos.rasshifrovat(fayl, None)
            elif tip not in ("text", "chat", "", "none"):
                nazv = {"image": "фото", "video": "видео", "document": "файл", "sticker": "стикер",
                        "location": "геопозиция", "contact": "контакт", "vcard": "контакт"}.get(tip, tip)
                imya_f = pole(m, "Filename", "filename")
                tekst = f"[{nazv}{': ' + imya_f if imya_f else ''}] {podpis or tekst}".strip()
            if not tekst:
                continue
            if ot_menya:
                avtor = "Я"
            elif gruppa:
                avtor = pole(m, "SenderName", "SenderJID", "sender_name", default="?")
                avtor = str(avtor).split("@")[0]
            else:
                avtor = imya
            soobshcheniya.append({"id": f"wa:{jid}:{mid}", "vremya": t, "chat": imya, "avtor": avtor, "tekst": tekst})
    novykh = zapisat("whatsapp", soobshcheniya)
    zapomnit("whatsapp")
    print(f"WhatsApp (wacli): с {s_momenta:%d.%m %H:%M}, сообщений {len(soobshcheniya)}, новых {novykh}.")
    for imya in ne_naydeno:
        print(f"  ! чат «{imya}» не найден — запустите python wa.py --spisok и проверьте название")
    if golos.NE_RASSHIFROVANO:
        print(f"  ! не расшифровано голосовых: {len(golos.NE_RASSHIFROVANO)}")


# ---------- отправка ----------
class OshibkaOtpravki(Exception):
    pass


def otpravit_v_chat(komu, tekst=None, golos_f=None):
    """Отправляет одно сообщение в известный чат. Возвращает строку-отчёт или бросает OshibkaOtpravki.
    Незнакомым номерам и личным чатам из chaty-isklyuchit.txt не пишет."""
    if not komu or not (tekst or golos_f):
        raise OshibkaOtpravki("Нужно название чата и текст (или файл голосового)")
    karta = json.loads(KARTA.read_text(encoding="utf-8")) if KARTA.exists() else {}
    jid = jid_po_imeni(komu, karta)
    if not jid or jid not in karta.values():
        # нет в сохранённой карте — смотрим все чаты, где уже была переписка
        karta = {c["imya"]: c["jid"] for c in chaty_zhivye(500)}
        jid = jid_po_imeni(komu, karta)
    if not jid or jid not in karta.values():
        raise OshibkaOtpravki(f"Чат «{komu}» не найден среди ваших чатов WhatsApp. Незнакомым не отправляем.")
    if jid in isklyuchennye():
        raise OshibkaOtpravki(f"Чат «{komu}» в списке личных (chaty-isklyuchit.txt) — секретарь с ним не работает.")
    if golos_f:
        src = Path(golos_f)
        if not src.exists():
            raise OshibkaOtpravki(f"Нет файла {src}")
        if src.suffix.lower() != ".ogg":
            if not shutil.which("ffmpeg"):
                raise OshibkaOtpravki("Для голосового нужен ffmpeg. Отправьте текстом.")
            ogg = STORE / "otpravka.ogg"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-vn", "-c:a", "libopus",
                            "-b:a", "32k", "-ac", "1", "-ar", "48000", str(ogg)], check=True)
            src = ogg
        wacli("send", "voice", "--to", jid, "--file", src, read_only=False, timeout=180)
        chto = f"голосовое {golos_f}"
    else:
        wacli("send", "text", "--to", jid, "--message", tekst, read_only=False, timeout=120)
        chto = tekst
    with open(ZHURNAL_OTPRAVKI, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M} · WhatsApp · {komu} · {chto[:200]}\n")
    return f"Отправлено в WhatsApp «{komu}»"


def otpravit(argv):
    def arg(k):
        return argv[argv.index(k) + 1] if k in argv and argv.index(k) + 1 < len(argv) else None
    try:
        print(otpravit_v_chat(arg("--komu"), arg("--tekst"), arg("--golos")))
    except (OshibkaOtpravki, RuntimeError) as e:
        sys.exit(str(e))


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        sobrat()
    elif a[0] == "vhod" and "--telefon" in a and a.index("--telefon") + 1 < len(a):
        vhod_po_nomeru(a[a.index("--telefon") + 1])
    elif a[0] == "vhod":
        vhod()
    elif a[0] == "sluzhba":
        sluzhba(a[1] if len(a) > 1 else "")
    elif a[0] == "--spisok":
        spisok()
    elif a[0] == "cikl":
        cikl()
    elif a[0] == "doctor":
        zdorove()
    elif a[0] == "vychistit":
        print(f"Вычищено чатов: {vychistit()}")
    elif a[0] == "--syroy":
        sobrat(syroy=True)
    elif a[0] == "otpravit":
        otpravit(a[1:])
    else:
        sys.exit(__doc__)
