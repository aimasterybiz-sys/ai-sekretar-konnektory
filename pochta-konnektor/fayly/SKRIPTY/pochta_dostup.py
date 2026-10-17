"""Почта: список ящиков, пароли, вход через Microsoft, подключение к серверам.

Список ящиков — NASTROYKI/pochta.json, без паролей.
Пароли — в хранилище системы: «Связка ключей» на Mac, «Диспетчер учётных данных» на Windows.
Вход Microsoft — зашифрованный кэш NASTROYKI/ms-token.bin (ключ шифрования тоже у системы).
Ни одна функция здесь не печатает пароль или токен — даже частично.
"""
import base64
import imaplib
import json
import re
import smtplib
from datetime import datetime
from pathlib import Path

from obshchee import NASTROYKI, ROOT, env
import pochta_servery as srv

YASHCHIKI = NASTROYKI / "pochta.json"
MS_KESH = NASTROYKI / "ms-token.bin"
SLUZHBA = "AI-sekretar-pochta"
MS_SCOPES = ["https://outlook.office.com/IMAP.AccessAsUser.All", "https://outlook.office.com/SMTP.Send"]
TAYMAUT = 30


class OshibkaPochty(Exception):
    """Ошибка, которую можно показать человеку как есть."""


# ---------- список ящиков ----------

def zagruzit():
    if YASHCHIKI.exists():
        return json.loads(YASHCHIKI.read_text(encoding="utf-8"))
    return {"yashchiki": []}


def sokhranit(dannye):
    NASTROYKI.mkdir(parents=True, exist_ok=True)
    vremennyy = YASHCHIKI.with_suffix(".tmp")
    vremennyy.write_text(json.dumps(dannye, ensure_ascii=False, indent=2), encoding="utf-8")
    vremennyy.replace(YASHCHIKI)


def yashchik(adres, dannye=None):
    adres = adres.strip().lower()
    for y in (dannye or zagruzit())["yashchiki"]:
        if y["adres"] == adres:
            return y
    return None


def zapisat_yashchik(nastroyki, adres):
    """Добавить или обновить ящик (состояние сбора старого ящика сохраняется)."""
    d = zagruzit()
    staryy = yashchik(adres, d)
    novyy = {"adres": adres, "provayder": nastroyki["provayder"], "imya": nastroyki["imya"],
             "vkhod": nastroyki["vkhod"], "imap": nastroyki["imap"], "smtp": nastroyki.get("smtp"),
             "otpravka": nastroyki.get("otpravka", True), "otpravlennye": nastroyki.get("otpravlennye"),
             "papki": (staryy or {}).get("papki", {}), "dobavlen": (staryy or {}).get("dobavlen")
             or datetime.now().isoformat(timespec="seconds"), "oshibka": None}
    d["yashchiki"] = [y for y in d["yashchiki"] if y["adres"] != adres] + [novyy]
    sokhranit(d)
    return novyy


# ---------- пароли ----------

def _keyring():
    try:
        import keyring
        return keyring
    except ImportError:
        raise OshibkaPochty("Не установлена библиотека keyring. Запустите: python -m pip install -r SKRIPTY/requirements.txt")


def parol_sokhranit(adres, parol):
    _keyring().set_password(SLUZHBA, adres, parol)


def parol(adres):
    p = _keyring().get_password(SLUZHBA, adres)
    if not p:
        raise OshibkaPochty(f"Нет сохранённого пароля для {adres}. Подключите ящик заново: python pochta.py dobavit")
    return p


def parol_udalit(adres):
    try:
        _keyring().delete_password(SLUZHBA, adres)
    except Exception:
        pass


# ---------- Microsoft ----------

def ms_client_id():
    return env().get("MS_CLIENT_ID") or srv.MS_CLIENT_ID


def _ms_prilozhenie():
    try:
        import msal
        from msal_extensions import PersistedTokenCache, build_encrypted_persistence
    except ImportError:
        raise OshibkaPochty("Не установлены библиотеки msal и msal-extensions. "
                            "Запустите: python -m pip install -r SKRIPTY/requirements.txt")
    if not ms_client_id():
        raise OshibkaPochty("Вход через Microsoft ещё не включён организатором курса (нет MS_CLIENT_ID).")
    NASTROYKI.mkdir(parents=True, exist_ok=True)
    kesh = PersistedTokenCache(build_encrypted_persistence(str(MS_KESH)))
    return msal.PublicClientApplication(ms_client_id(), authority="https://login.microsoftonline.com/common",
                                        token_cache=kesh)


def ms_voyti(adres):
    """Окно входа Microsoft в браузере. Возвращает адрес, под которым человек вошёл."""
    app = _ms_prilozhenie()
    r = app.acquire_token_interactive(MS_SCOPES, login_hint=adres, prompt="select_account", timeout=600)
    if "access_token" not in r:
        opisanie = r.get("error_description") or r.get("error") or "вход не завершён"
        if "AADSTS65001" in opisanie or "AADSTS90094" in opisanie or "admin" in opisanie.lower():
            raise OshibkaPochty("Microsoft просит согласие администратора вашей компании на приложение «AI-секретарь».")
        raise OshibkaPochty("Вход через Microsoft не получился: " + opisanie.split("\r\n")[0][:200])
    voshel = (r.get("id_token_claims") or {}).get("preferred_username", "").lower()
    return voshel


def ms_token(adres):
    app = _ms_prilozhenie()
    akkaunty = [a for a in app.get_accounts() if a.get("username", "").lower() == adres]
    r = app.acquire_token_silent(MS_SCOPES, account=akkaunty[0]) if akkaunty else None
    if not r or "access_token" not in r:
        raise OshibkaPochty(f"Вход Microsoft для {adres} истёк. Подключите ящик заново: python pochta.py dobavit")
    return r["access_token"]


def ms_zabyt(adres):
    try:
        app = _ms_prilozhenie()
        for a in app.get_accounts():
            if a.get("username", "").lower() == adres:
                app.remove_account(a)
    except Exception:
        pass


def _xoauth2(login, token):
    return f"user={login}\x01auth=Bearer {token}\x01\x01"


# ---------- подключение ----------

def _sekret(y, parol_yavno=None):
    if y["vkhod"] == "microsoft":
        return ms_token(y["adres"])
    p = parol_yavno if parol_yavno is not None else parol(y["adres"])
    return p


def imap_vkhod(y, parol_yavno=None):
    s = y["imap"]
    ctx = srv.ssl_kontekst(s["host"])
    try:
        if s["ssl"] == "SSL":
            im = imaplib.IMAP4_SSL(s["host"], s["port"], ssl_context=ctx, timeout=TAYMAUT)
        else:
            im = imaplib.IMAP4(s["host"], s["port"], timeout=TAYMAUT)
            im.starttls(ssl_context=ctx)
    except Exception as e:
        raise OshibkaPochty(oshibka_svyazi(e, s["host"], y))
    sekret = _sekret(y, parol_yavno)
    try:
        if y["vkhod"] == "microsoft":
            im.authenticate("XOAUTH2", lambda _: _xoauth2(s.get("login", y["adres"]), sekret).encode())
        else:
            im._encoding = "utf-8"  # пароль с буквами не латиницей
            im.login(s.get("login", y["adres"]), sekret)
    except imaplib.IMAP4.error as e:
        raise OshibkaPochty(oshibka_vkhoda(str(e), y))
    return im


def smtp_vkhod(y, parol_yavno=None):
    s = y.get("smtp")
    if not s:
        raise OshibkaPochty("Для этой почты не найден сервер отправки (SMTP).")
    ctx = srv.ssl_kontekst(s["host"])
    try:
        if s["ssl"] == "SSL":
            sm = smtplib.SMTP_SSL(s["host"], s["port"], context=ctx, timeout=TAYMAUT)
        else:
            sm = smtplib.SMTP(s["host"], s["port"], timeout=TAYMAUT)
            sm.ehlo()
            sm.starttls(context=ctx)
            sm.ehlo()
    except Exception as e:
        raise OshibkaPochty(oshibka_svyazi(e, s["host"], y))
    sekret = _sekret(y, parol_yavno)
    try:
        if y["vkhod"] == "microsoft":
            stroka = _xoauth2(s.get("login", y["adres"]), sekret)
            sm.auth("XOAUTH2", lambda challenge=None: stroka, initial_response_ok=True)
        else:
            sm.login(s.get("login", y["adres"]), sekret)
    except smtplib.SMTPException as e:
        raise OshibkaPochty("Отправка: " + oshibka_vkhoda(str(e), y))
    return sm


def oshibka_svyazi(e, host, y):
    t = f"{type(e).__name__}: {e}"
    if y.get("provayder") == "proton":
        return "Не могу связаться с Proton Bridge. Запустите программу Proton Mail Bridge и повторите."
    if "gaierror" in t or "Name or service not known" in t or "nodename nor servname" in t:
        return f"Не нашёл сервер {host}. Проверьте адрес почты или имя сервера."
    if "CERTIFICATE" in t.upper() or "SSL" in t.upper():
        return f"Не удалось установить защищённое соединение с {host}. Сервер указан верно?"
    return f"Сервер {host} не отвечает. Проверьте интернет и повторите через минуту."


def oshibka_vkhoda(t, y):
    p = y.get("provayder")
    nizh = t.lower()
    if "application-specific password" in nizh or "app password" in nizh or p in ("gmail", "google_workspace") \
            and ("invalid credentials" in nizh or "username and password not accepted" in nizh):
        return ("Google не принял пароль. Нужен пароль приложения (16 букв), а не обычный пароль от Gmail. "
                "Создайте его по шагам на странице и вставьте заново.")
    if "imap" in nizh and ("disabled" in nizh or "not enabled" in nizh):
        return "В настройках почты выключен доступ по IMAP. Включите его по шагам на странице."
    if y.get("vkhod") == "microsoft":
        return "Microsoft не пустил по входу. Подключите ящик заново кнопкой «Войти через Microsoft»."
    podskazka = {
        "icloud": "Нужен пароль для приложений Apple (вида xxxx-xxxx-xxxx-xxxx), а не пароль Apple ID.",
        "yahoo": "Нужен пароль приложения Yahoo, а не обычный пароль.",
        "aol": "Нужен пароль приложения AOL, а не обычный пароль.",
        "ukrnet": "Нужен пароль IMAP-доступа из настроек ukr.net, а не обычный пароль.",
        "proton": "Нужен пароль, который показывает Proton Bridge, а не пароль от Proton.",
    }.get(p, "Проверьте пароль. Если в почте включена двухэтапная проверка — нужен пароль приложения.")
    return "Почта не приняла пароль. " + podskazka


# ---------- папки ----------

def mutf7_dekod(s):
    """Названия папок IMAP приходят в modified UTF-7: «&BB4EQgQ,BEAEMAQyBDsENQQ9BD0ESwQ1-» → «Отправленные»."""
    def zamena(m):
        kusok = m.group(1)
        if not kusok:
            return "&"
        b = kusok.replace(",", "/")
        b += "=" * (-len(b) % 4)
        return base64.b64decode(b).decode("utf-16-be", "replace")
    return re.sub(r"&([^-]*)-", zamena, s)


_LIST = re.compile(r'^\((?P<flagi>[^)]*)\) (?:"[^"]*"|NIL) (?P<imya>.+)$')
IMENA_OTPRAVLENNYKH = ("sent", "sent items", "sent messages", "sent mail", "inbox.sent", "отправленные",
                       "надіслані", "відправлені", "gesendet", "gesendete elemente", "enviados")


def papki(im):
    """[(сырое имя для SELECT, имя для человека, флаги)]"""
    _, spisok = im.list()
    rez = []
    for el in spisok or []:
        if isinstance(el, tuple):  # имя пришло литералом
            m = _LIST.match(el[0].decode("utf-8", "replace").rsplit("{", 1)[0].strip() + " X")
            imya = el[1].decode("utf-8", "replace")
            flagi = m.group("flagi") if m else ""
        else:
            m = _LIST.match((el or b"").decode("utf-8", "replace"))
            if not m:
                continue
            imya, flagi = m.group("imya"), m.group("flagi")
            if imya.startswith('"') and imya.endswith('"'):
                imya = imya[1:-1].replace('\\"', '"').replace("\\\\", "\\")
        rez.append((imya, mutf7_dekod(imya), flagi.lower()))
    return rez


def papka_otpravlennykh(spisok):
    for imya, chel, flagi in spisok:
        if "\\sent" in flagi:
            return imya
    for imya, chel, flagi in spisok:
        if chel.lower().split("/")[-1].split(".")[-1] in IMENA_OTPRAVLENNYKH or chel.lower() in IMENA_OTPRAVLENNYKH:
            return imya
    return None


def v_kavychkakh(imya):
    return '"' + imya.replace("\\", "\\\\").replace('"', '\\"') + '"'


# ---------- проверка при подключении ----------

def proverit_i_sokhranit(adres, nastroyki, parol_yavno=None):
    """Входим, находим папки, проверяем отправку; при успехе сохраняем ящик и пароль.
    Возвращает словарь для показа человеку."""
    y = dict(nastroyki, adres=adres)
    if y.get("probely") and parol_yavno:
        parol_yavno = re.sub(r"\s+", "", parol_yavno)  # пароли приложений Google/Yahoo копируются с пробелами
    elif parol_yavno:
        parol_yavno = parol_yavno.strip()
    im = imap_vkhod(y, parol_yavno)
    try:
        spisok = papki(im)
        otpr = papka_otpravlennykh(spisok)
        _, d = im.select("INBOX", readonly=True)
        vo_vkhodyashchikh = int(d[0]) if d and d[0] and d[0].isdigit() else None
    finally:
        try:
            im.logout()
        except Exception:
            pass
    otpravka, pochemu = True, ""
    try:
        sm = smtp_vkhod(y, parol_yavno)
        sm.quit()
    except OshibkaPochty as e:
        otpravka, pochemu = False, str(e)
    if y["vkhod"] == "parol":
        parol_sokhranit(adres, parol_yavno)
    y["otpravlennye"], y["otpravka"] = otpr, otpravka
    zapisat_yashchik(y, adres)
    return {"adres": adres, "imya": y["imya"], "vkhodyashchikh": vo_vkhodyashchikh,
            "otpravlennye": mutf7_dekod(otpr) if otpr else None, "otpravka": otpravka, "pochemu_net_otpravki": pochemu}


def udalit(adres):
    adres = adres.strip().lower()
    d = zagruzit()
    y = yashchik(adres, d)
    if not y:
        return False
    d["yashchiki"] = [x for x in d["yashchiki"] if x["adres"] != adres]
    sokhranit(d)
    parol_udalit(adres)
    if y["vkhod"] == "microsoft":
        ms_zabyt(adres)
    return True


def perenesti_iz_env():
    """Ящик из старой настройки (.env: MAIL_HOST, MAIL_USER, MAIL_PASS) → pochta.json и хранилище паролей.
    Строки MAIL_* из .env удаляются только после того, как пароль сохранён."""
    e = env()
    adres, p = (e.get("MAIL_USER") or "").strip().lower(), e.get("MAIL_PASS")
    if not adres or not p or yashchik(adres):
        return None
    nastroyki = srv.opredelit(adres)
    if "oshibka" in nastroyki or (e.get("MAIL_HOST") and nastroyki.get("imap", {}).get("host") != e["MAIL_HOST"]):
        if not e.get("MAIL_HOST"):
            return None
        nastroyki = srv.vruchnuyu(adres, e["MAIL_HOST"])
        if e.get("MAIL_PORT"):
            nastroyki["imap"]["port"] = int(e["MAIL_PORT"])
    if nastroyki["vkhod"] != "parol":
        return None
    parol_sokhranit(adres, p)
    zapisat_yashchik(nastroyki, adres)
    f = ROOT / ".env"
    if f.exists():
        stroki = [s for s in f.read_text(encoding="utf-8").splitlines()
                  if not re.match(r"^\s*MAIL_(HOST|USER|PASS|PORT|FOLDERS)\s*=", s)]
        f.write_text("\n".join(stroki) + "\n", encoding="utf-8")
    return adres
