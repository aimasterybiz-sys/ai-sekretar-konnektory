"""Почта: по адресу находим сервер и способ входа — как это делает Thunderbird.

Порядок: своя таблица известных почт → запись MX домена (Google, Microsoft, Zoho, Hostinger…) →
база Mozilla (autoconfig.thunderbird.net) → autoconfig на сайте домена → база Mozilla по домену из MX →
перебор imap./mail.<домен>. Своя таблица нужна потому, что ukr.net, i.ua, meta.ua, Proton и Hostinger
в базе Mozilla нет.

  python pochta_servery.py anna@gmail.com    показать, что нашлось (для проверки)
"""
import json
import re
import socket
import ssl
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

# Приложение «AI-секретарь» в Microsoft Entra (вход в Outlook.com, Hotmail и Microsoft 365).
# Его один раз регистрирует организатор курса — см. ПРОЧТИ-МЕНЯ.md, раздел «Вход через Microsoft».
# Пока строка пустая, Outlook подключить нельзя. Можно задать и в .env: MS_CLIENT_ID=...
MS_CLIENT_ID = ""


def ssl_kontekst(host=""):
    if host in ("127.0.0.1", "localhost"):
        # Proton Bridge работает на этом компьютере со своим сертификатом — проверять его не с чем
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def S(host, port, zashchita):
    """Сервер: zashchita — SSL (сразу защищённое) или STARTTLS (защита после приветствия)."""
    return {"host": host, "port": port, "ssl": zashchita}


# Как получить пароль: шаги для страницы подключения. ссылка — (текст кнопки, адрес).
INSTR = {
    "gmail": [
        ("Откройте страницу паролей приложений Google и войдите в эту почту, если попросит.",
         ("Открыть пароли приложений", "https://myaccount.google.com/apppasswords")),
        ("Google пишет «Настройка недоступна»? Сначала включите двухэтапную проверку, потом вернитесь к первому шагу.",
         ("Включить двухэтапную проверку", "https://myaccount.google.com/signinoptions/twosv")),
        ("В поле «Название приложения» напишите «Секретарь» и нажмите «Создать».", None),
        ("Скопируйте 16 букв из появившегося окна и вставьте ниже.", None),
    ],
    "google_workspace": [
        ("Это рабочая почта на Google. Откройте страницу паролей приложений и войдите в эту почту.",
         ("Открыть пароли приложений", "https://myaccount.google.com/apppasswords")),
        ("Google пишет «Настройка недоступна»? Включите двухэтапную проверку и вернитесь к первому шагу. "
         "Если страницы нет совсем — пароли приложений запретил администратор компании: попросите его разрешить.",
         ("Включить двухэтапную проверку", "https://myaccount.google.com/signinoptions/twosv")),
        ("Название — «Секретарь», «Создать». Скопируйте 16 букв и вставьте ниже.", None),
    ],
    "microsoft": [
        ("Нажмите «Войти через Microsoft». Откроется окно Microsoft: войдите в эту почту и нажмите «Принять». "
         "Пароль сюда вводить не нужно.", None),
    ],
    "microsoft365": [
        ("Это рабочая почта на Microsoft 365. Нажмите «Войти через Microsoft», войдите в эту почту и нажмите «Принять». "
         "Пароль сюда вводить не нужно.", None),
        ("Microsoft пишет «Требуется утверждение администратора»? Администратор вашей компании должен один раз "
         "разрешить приложение «AI-секретарь». Если администратор — вы, войдите своей учётной записью и отметьте "
         "«Согласие от имени организации».", None),
    ],
    "icloud": [
        ("Откройте страницу Apple ID и войдите.", ("Открыть Apple ID", "https://account.apple.com/account/manage")),
        ("«Вход и безопасность» → «Пароли для приложений» → «+». Название — «Секретарь».", None),
        ("Скопируйте пароль вида xxxx-xxxx-xxxx-xxxx и вставьте ниже.", None),
    ],
    "yahoo": [
        ("Откройте безопасность аккаунта Yahoo.", ("Открыть Yahoo", "https://login.yahoo.com/myaccount/security/")),
        ("«Создать пароль приложения» (Generate app password), название — «Секретарь».", None),
        ("Скопируйте пароль и вставьте ниже.", None),
    ],
    "aol": [
        ("Откройте безопасность аккаунта AOL.", ("Открыть AOL", "https://login.aol.com/account/security")),
        ("«Создать пароль приложения» (Generate app password), название — «Секретарь».", None),
        ("Скопируйте пароль и вставьте ниже.", None),
    ],
    "ukrnet": [
        ("Откройте почту ukr.net → Налаштування (шестерёнка) → «Керування IMAP-доступом».",
         ("Открыть ukr.net", "https://mail.ukr.net/")),
        ("«Доступ до зовнішніх програм» → «Створити пароль», назва — «Секретар».", None),
        ("Скопируйте этот пароль и вставьте ниже. Обычный пароль от ukr.net не подойдёт.", None),
    ],
    "zoho": [
        ("В Zoho Mail: Настройки → Почтовые аккаунты → IMAP → включите «Доступ IMAP».",
         ("Открыть Zoho Mail", "https://mail.zoho.com/")),
        ("Включена двухэтапная проверка — создайте пароль приложения и вставьте его ниже. Не включена — обычный пароль.",
         ("Пароли приложений Zoho", "https://accounts.zoho.com/home#security/app_password")),
    ],
    "fastmail": [
        ("Fastmail: Настройки → Конфиденциальность и безопасность → пароли приложений → новый пароль, доступ «Mail (IMAP/SMTP)».",
         ("Открыть Fastmail", "https://app.fastmail.com/settings/security")),
        ("Скопируйте пароль и вставьте ниже.", None),
    ],
    "proton": [
        ("Proton пускает программы к почте только через Proton Mail Bridge (нужен платный тариф). "
         "Установите Bridge и войдите в нём в свою почту.", ("Скачать Proton Bridge", "https://proton.me/mail/bridge")),
        ("В Bridge нажмите на ящик → «Настройки почтового ящика» (Mailbox details) → скопируйте пароль. "
         "Это не пароль от Proton, а пароль, который выдал Bridge.", None),
        ("Вставьте его ниже. Bridge должен быть запущен, пока работает секретарь.", None),
    ],
    "obychnyy": [
        ("Введите пароль от этого ящика — тот, с которым входите в веб-почту.", None),
        ("Если в почте включена двухэтапная проверка — нужен пароль приложения из её настроек.", None),
    ],
}

# Провайдеры: имя для человека, способ входа, серверы, подсказка.
PROVAYDERY = {
    "gmail": {"imya": "Gmail", "vkhod": "parol", "imap": S("imap.gmail.com", 993, "SSL"),
              "smtp": S("smtp.gmail.com", 465, "SSL"), "instr": "gmail", "probely": True},
    "google_workspace": {"imya": "Рабочая почта Google", "vkhod": "parol", "imap": S("imap.gmail.com", 993, "SSL"),
                         "smtp": S("smtp.gmail.com", 465, "SSL"), "instr": "google_workspace", "probely": True},
    "outlook": {"imya": "Outlook / Hotmail", "vkhod": "microsoft", "imap": S("outlook.office365.com", 993, "SSL"),
                "smtp": S("smtp-mail.outlook.com", 587, "STARTTLS"), "instr": "microsoft"},
    "microsoft365": {"imya": "Рабочая почта Microsoft 365", "vkhod": "microsoft",
                     "imap": S("outlook.office365.com", 993, "SSL"), "smtp": S("smtp.office365.com", 587, "STARTTLS"),
                     "instr": "microsoft365"},
    "icloud": {"imya": "iCloud", "vkhod": "parol", "imap": S("imap.mail.me.com", 993, "SSL"),
               "smtp": S("smtp.mail.me.com", 587, "STARTTLS"), "instr": "icloud"},
    "yahoo": {"imya": "Yahoo", "vkhod": "parol", "imap": S("imap.mail.yahoo.com", 993, "SSL"),
              "smtp": S("smtp.mail.yahoo.com", 465, "SSL"), "instr": "yahoo", "probely": True},
    "aol": {"imya": "AOL", "vkhod": "parol", "imap": S("imap.aol.com", 993, "SSL"),
            "smtp": S("smtp.aol.com", 465, "SSL"), "instr": "aol", "probely": True},
    "ukrnet": {"imya": "ukr.net", "vkhod": "parol", "imap": S("imap.ukr.net", 993, "SSL"),
               "smtp": S("smtp.ukr.net", 465, "SSL"), "instr": "ukrnet"},
    "zoho": {"imya": "Zoho", "vkhod": "parol", "imap": S("imap.zoho.com", 993, "SSL"),
             "smtp": S("smtp.zoho.com", 465, "SSL"), "instr": "zoho"},
    "zoho_eu": {"imya": "Zoho (EU)", "vkhod": "parol", "imap": S("imap.zoho.eu", 993, "SSL"),
                "smtp": S("smtp.zoho.eu", 465, "SSL"), "instr": "zoho"},
    "zoho_pro": {"imya": "Почта на Zoho", "vkhod": "parol", "imap": S("imappro.zoho.com", 993, "SSL"),
                 "smtp": S("smtppro.zoho.com", 465, "SSL"), "instr": "zoho"},
    "zoho_pro_eu": {"imya": "Почта на Zoho (EU)", "vkhod": "parol", "imap": S("imappro.zoho.eu", 993, "SSL"),
                    "smtp": S("smtppro.zoho.eu", 465, "SSL"), "instr": "zoho"},
    "fastmail": {"imya": "Fastmail", "vkhod": "parol", "imap": S("imap.fastmail.com", 993, "SSL"),
                 "smtp": S("smtp.fastmail.com", 465, "SSL"), "instr": "fastmail"},
    "proton": {"imya": "Proton (через Bridge)", "vkhod": "parol", "imap": S("127.0.0.1", 1143, "STARTTLS"),
               "smtp": S("127.0.0.1", 1025, "STARTTLS"), "instr": "proton"},
    "hostinger": {"imya": "Почта на Hostinger", "vkhod": "parol", "imap": S("imap.hostinger.com", 993, "SSL"),
                  "smtp": S("smtp.hostinger.com", 465, "SSL"), "instr": "obychnyy"},
}

# Почты без IMAP: читать их программой нельзя — честно говорим и предлагаем выход.
BEZ_IMAP = {
    "i.ua": "i.ua не даёт программам читать почту по IMAP, поэтому секретарь не может её подключить. "
            "Если в настройках i.ua есть пересылка писем — перешлите их на почту, которая подключена здесь.",
    "meta.ua": "meta.ua не даёт программам читать почту по IMAP, поэтому секретарь не может её подключить. "
               "Если в настройках meta.ua есть пересылка писем — перешлите их на почту, которая подключена здесь.",
}

DOMENY = {
    "gmail.com": "gmail", "googlemail.com": "gmail",
    "outlook.com": "outlook", "hotmail.com": "outlook", "live.com": "outlook", "msn.com": "outlook",
    "icloud.com": "icloud", "me.com": "icloud", "mac.com": "icloud",
    "yahoo.com": "yahoo", "ymail.com": "yahoo", "rocketmail.com": "yahoo",
    "aol.com": "aol",
    "ukr.net": "ukrnet",
    "zoho.com": "zoho", "zohomail.com": "zoho", "zoho.eu": "zoho_eu", "zohomail.eu": "zoho_eu",
    "fastmail.com": "fastmail", "fastmail.fm": "fastmail",
    "proton.me": "proton", "protonmail.com": "proton", "protonmail.ch": "proton", "pm.me": "proton",
}
# hotmail.de, outlook.fr, yahoo.co.uk, live.lv …
SHABLONY_DOMENOV = [(r"^(hotmail|outlook|live)\.[a-z.]+$", "outlook"), (r"^yahoo\.[a-z.]+$", "yahoo")]

# По MX: почта на своём домене, которую обслуживает известный провайдер
MX_PROVAYDERY = [
    (r"\.mail\.protection\.outlook\.com$", "microsoft365"),
    (r"(^|\.)(google|googlemail)\.com$", "google_workspace"),
    (r"(^|\.)mx\.zoho\.eu$", "zoho_pro_eu"), (r"(^|\.)zoho\.eu$", "zoho_pro_eu"),
    (r"(^|\.)zoho\.com$", "zoho_pro"),
    (r"(^|\.)messagingengine\.com$", "fastmail"),
    (r"(^|\.)hostinger\.(com|io)$", "hostinger"),
    (r"(^|\.)mail\.icloud\.com$", "icloud"),
    (r"(^|\.)protonmail\.ch$", "proton"),
]


def zapros(url, timeout=8, zagolovki=None):
    req = urllib.request.Request(url, headers={"User-Agent": "AI-sekretar", **(zagolovki or {})})
    with urllib.request.urlopen(req, context=ssl_kontekst(), timeout=timeout) as r:
        return r.read()


def mx_zapisi(domen):
    """MX домена через DNS по HTTPS (Cloudflare, запасной — Google): без лишних библиотек."""
    for url, zag in ((f"https://cloudflare-dns.com/dns-query?name={domen}&type=MX", {"Accept": "application/dns-json"}),
                     (f"https://dns.google/resolve?name={domen}&type=MX", None)):
        try:
            otvet = json.loads(zapros(url, 6, zag))
            zapisi = [a["data"].split()[-1].rstrip(".").lower() for a in otvet.get("Answer", []) if a.get("type") == 15]
            return zapisi
        except Exception:
            continue
    return []


def iz_xml(dannye, adres):
    """Разбор autoconfig-файла (формат Mozilla): первый IMAP и первый SMTP."""
    lokal, domen = adres.split("@", 1)
    root = ET.fromstring(dannye)

    def server(tag, tip):
        for el in root.iter(tag):
            if el.get("type") != tip:
                continue
            zashch = (el.findtext("socketType") or "").upper()
            if zashch not in ("SSL", "STARTTLS"):
                continue  # без шифрования не подключаемся
            login = (el.findtext("username") or "%EMAILADDRESS%")
            login = login.replace("%EMAILADDRESS%", adres).replace("%EMAILLOCALPART%", lokal).replace("%EMAILDOMAIN%", domen)
            auth = [a.text or "" for a in el.findall("authentication")]
            return {"host": el.findtext("hostname"), "port": int(el.findtext("port")), "ssl": zashch,
                    "login": login, "oauth_tolko": auth and all(a == "OAuth2" for a in auth)}
        return None

    imap, smtp = server("incomingServer", "imap"), server("outgoingServer", "smtp")
    if not imap:
        return None
    return {"imap": imap, "smtp": smtp}


def ispdb(domen, adres):
    try:
        return iz_xml(zapros(f"https://autoconfig.thunderbird.net/v1.1/{domen}"), adres)
    except Exception:
        return None


def autoconfig_domena(domen, adres):
    q = urllib.parse.quote(adres)
    for url in (f"https://autoconfig.{domen}/mail/config-v1.1.xml?emailaddress={q}",
                f"https://{domen}/.well-known/autoconfig/mail/config-v1.1.xml?emailaddress={q}"):
        try:
            r = iz_xml(zapros(url, 6), adres)
            if r:
                return r
        except Exception:
            continue
    return None


def otkryt_li(host, port, timeout=4):
    try:
        with socket.create_connection((host, port), timeout=timeout) as s:
            if port in (993, 465):
                with ssl_kontekst().wrap_socket(s, server_hostname=host):
                    return True
            return True
    except Exception:
        return False


def perebor(domen):
    imap = next((S(h, 993, "SSL") for h in (f"imap.{domen}", f"mail.{domen}") if otkryt_li(h, 993)), None)
    if not imap:
        return None
    smtp = None
    for h in (f"smtp.{domen}", f"mail.{domen}", imap["host"]):
        if otkryt_li(h, 465):
            smtp = S(h, 465, "SSL")
            break
        if otkryt_li(h, 587):
            smtp = S(h, 587, "STARTTLS")
            break
    return {"imap": imap, "smtp": smtp}


def iz_provaydera(kluch, adres, istochnik):
    p = PROVAYDERY[kluch]
    login = adres
    return {"provayder": kluch, "imya": p["imya"], "vkhod": p["vkhod"], "instr": p["instr"],
            "imap": dict(p["imap"], login=login), "smtp": dict(p["smtp"], login=login),
            "probely": p.get("probely", False), "istochnik": istochnik}


def opredelit(adres):
    """Что за почта и как к ней подключаться. Возвращает словарь; при неудаче — ключ 'oshibka'."""
    adres = (adres or "").strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[a-z0-9-]{2,}$", adres):
        return {"oshibka": "Это не похоже на адрес почты. Пример: anna@firma.com"}
    domen = adres.split("@", 1)[1]
    if domen in BEZ_IMAP:
        return {"oshibka": BEZ_IMAP[domen], "bez_imap": True}
    kluch = DOMENY.get(domen) or next((k for r, k in SHABLONY_DOMENOV if re.match(r, domen)), None)
    if kluch:
        return iz_provaydera(kluch, adres, "таблица")

    mx = mx_zapisi(domen)
    for zapis in mx:
        for r, k in MX_PROVAYDERY:
            if re.search(r, zapis):
                return iz_provaydera(k, adres, f"MX {zapis}")

    naydeno = ispdb(domen, adres) or autoconfig_domena(domen, adres)
    istochnik = "база Mozilla / autoconfig"
    if not naydeno and mx:
        # почта на хостинге: mx1.provider.tld → ищем provider.tld в базе Mozilla
        chasti = mx[0].split(".")
        if len(chasti) >= 2:
            naydeno = ispdb(".".join(chasti[-2:]), adres)
            istochnik = f"база Mozilla по MX {mx[0]}"
    if not naydeno:
        naydeno = perebor(domen)
        istochnik = "перебор серверов"
    if not naydeno:
        return {"oshibka": "Не нашёл почтовый сервер для этого адреса. Узнайте у того, кто настраивал почту, "
                           "адрес сервера IMAP (например mail.firma.com) и впишите его вручную.", "vruchnuyu": True}
    imap, smtp = naydeno["imap"], naydeno.get("smtp")
    imap.setdefault("login", adres)
    if smtp:
        smtp.setdefault("login", imap["login"])
    if imap.pop("oauth_tolko", False):
        return {"oshibka": "Эта почта пускает программы только через вход провайдера (OAuth), "
                           "а его секретарь пока не умеет для этого провайдера.", "vruchnuyu": False}
    if smtp:
        smtp.pop("oauth_tolko", None)
    return {"provayder": "domen", "imya": f"Почта {domen}", "vkhod": "parol", "instr": "obychnyy",
            "imap": imap, "smtp": smtp, "probely": False, "istochnik": istochnik}


def vruchnuyu(adres, imap_host, smtp_host=None):
    """Сервер вписан руками: IMAP 993 SSL, SMTP — 465 SSL или 587 STARTTLS, что откроется."""
    smtp_host = smtp_host or imap_host
    smtp = S(smtp_host, 465, "SSL") if otkryt_li(smtp_host, 465) else S(smtp_host, 587, "STARTTLS")
    return {"provayder": "domen", "imya": f"Почта {adres.split('@')[-1]}", "vkhod": "parol", "instr": "obychnyy",
            "imap": dict(S(imap_host, 993, "SSL"), login=adres), "smtp": dict(smtp, login=adres),
            "probely": False, "istochnik": "вручную"}


if __name__ == "__main__":
    for a in sys.argv[1:]:
        r = opredelit(a)
        if "oshibka" in r:
            print(f"{a}: ✗ {r['oshibka']}")
        else:
            smtp = r["smtp"] or {}
            print(f"{a}: {r['imya']} · вход {r['vkhod']} · IMAP {r['imap']['host']}:{r['imap']['port']} "
                  f"· SMTP {smtp.get('host')}:{smtp.get('port')} {smtp.get('ssl')} · {r['istochnik']}")
