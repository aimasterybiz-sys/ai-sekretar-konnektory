"""Сбор и отправка почты на поддельном сервере: разбор писем, UID, дубли, рассылки, контакты, отправка и её запреты."""
import json
import os
import re
import sys
from datetime import datetime, timedelta
from email.header import Header
from email.message import EmailMessage
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    _s.reconfigure(encoding="utf-8", errors="replace")

SKRIPTY = Path(sys.argv[1])
sys.path.insert(0, str(SKRIPTY))
ROOT = SKRIPTY.parent
os.environ["SEKRETAR_START"] = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")

import pochta  # noqa: E402
import pochta_dostup as dost  # noqa: E402

TEPER = datetime.now()


def pismo(ot, komu, tema, tekst, mid=True, html=False, dop=None, dney=1):
    m = EmailMessage()
    m["From"], m["To"] = ot, komu
    m["Subject"] = tema
    m["Date"] = (TEPER - timedelta(days=dney)).strftime("%a, %d %b %Y %H:%M:%S +0000")
    if mid:
        m["Message-ID"] = mid if isinstance(mid, str) else f"<{abs(hash(tema))}@test>"
    for k, v in (dop or {}).items():
        m[k] = v
    if html:
        m.set_content(tekst, subtype="html")
    else:
        m.set_content(tekst)
    return m.as_bytes()


VKHODYASHCHIE = {
    101: pismo("Иван Петров <ivan@client.lv>", "me@firma.lv", "Смета по объекту на Бривибас",
               "Добрый день!\nПришлите смету до пятницы.\n\nOn Mon, 12 Oct 2026 Anna wrote:\n> старое письмо", mid="<smeta-1@client.lv>"),
    102: pismo("shop@news.com", "me@firma.lv", "Скидки недели", "Купите", dop={"List-Unsubscribe": "<mailto:u@news.com>"}),
    103: pismo("Ольга <olga@partner.ua>", "me@firma.lv", "Договір", "<p>Надсилаю <b>договір</b>.</p><p>Олга</p>", html=True),
    104: pismo("x@spam.com", "me@firma.lv", "Без id", "текст без Message-ID", mid=False),
    105: b"BIG",  # большое письмо: размер > 2 МБ
    106: pismo("bank@bank.lv", "me@firma.lv", "Выписка", "секретно"),
    107: pismo("old@client.lv", "me@firma.lv", "Старое", "очень старое письмо", dney=30),
}
OTPRAVLENNYE = {
    201: pismo("me@firma.lv", "ivan@client.lv, buh@firma.lv", "Re: Смета по объекту на Бривибас",
               "Иван, отправлю в четверг.", mid="<otvet-1@firma.lv>"),
}
OTPRAVLENNYE[202] = VKHODYASHCHIE[101]  # то же письмо лежит и во второй папке (как метки Gmail)
BOLSHOE_ZAGOLOVKI = pismo("Архитектор <arch@studio.lv>", "me@firma.lv", "Чертежи", "")
PAPKI = {"INBOX": VKHODYASHCHIE, "&BB4EQgQ,BEAEMAQyBDsENQQ9BD0ESwQ1-": OTPRAVLENNYE}
dobavleno_v_otpravlennye = []


class FakeIMAP:
    def __init__(self):
        self.papka = None

    def list(self):
        return "OK", [b'(\\HasNoChildren) "/" "INBOX"',
                      b'(\\HasNoChildren \\Sent) "/" "&BB4EQgQ,BEAEMAQyBDsENQQ9BD0ESwQ1-"',
                      b'(\\HasNoChildren) "/" "Drafts"']

    def select(self, imya, readonly=False):
        assert readonly, "папка открыта НЕ только на чтение"
        self.papka = imya.strip('"')
        return "OK", [str(len(PAPKI[self.papka])).encode()]

    def response(self, k):
        return "OK", [b"777"]

    def uid(self, komanda, *a):
        pisma = PAPKI[self.papka]
        if komanda == "search":
            if a[1] == "UID":
                n = int(a[2].split(":")[0])
                uidy = [u for u in pisma if u >= n] or [max(pisma)]
            elif a[1] == "HEADER":
                return "OK", [b""]
            else:
                uidy = list(pisma)
            return "OK", [" ".join(map(str, sorted(uidy))).encode()]
        if komanda == "fetch":
            nabor, chto = a
            assert "BODY[" not in chto.replace("BODY.PEEK[", ""), "чтение без PEEK пометит письмо прочитанным"
            otvet = []
            for u in map(int, nabor.split(",")):
                syroe = pisma[u]
                razmer = 3_000_000 if syroe == b"BIG" else len(syroe)
                if chto == "(UID RFC822.SIZE)":
                    otvet.append(f"{u} (RFC822.SIZE {razmer} UID {u})".encode())  # порядок полей другой — так бывает
                    continue
                if syroe == b"BIG":
                    assert "HEADER" in chto, "большое письмо скачивается целиком"
                    syroe = BOLSHOE_ZAGOLOVKI
                golova = f'{u} (UID {u} RFC822.SIZE {razmer} INTERNALDATE "16-Oct-2026 10:00:00 +0000" BODY[] {{{len(syroe)}}}'
                otvet += [(golova.encode(), syroe), b")"]
            return "OK", otvet
        raise AssertionError(komanda)

    def append(self, papka, flagi, data, soobshchenie):
        dobavleno_v_otpravlennye.append((papka, soobshchenie))
        return "OK", []

    def logout(self):
        pass


otpravleno = []


class FakeSMTP:
    def send_message(self, m):
        otpravleno.append(m)

    def quit(self):
        pass


dost.imap_vkhod = lambda y, p=None: FakeIMAP()
dost.smtp_vkhod = lambda y, p=None: FakeSMTP()
pochta.time.sleep = lambda s: None

dost.zapisat_yashchik({"provayder": "domen", "imya": "Почта firma.lv", "vkhod": "parol",
                       "imap": {"host": "imap.firma.lv", "port": 993, "ssl": "SSL"},
                       "smtp": {"host": "smtp.firma.lv", "port": 465, "ssl": "SSL"}, "otpravka": True}, "me@firma.lv")
(ROOT / "NASTROYKI" / "pochta-isklyuchit.txt").write_text("# личное\n@bank.lv\n", encoding="utf-8")


def proverka(imya, uslovie, podrobno=""):
    print(("✓ " if uslovie else "✗ ") + imya + (f" — {podrobno}" if podrobno else ""))


print("=== первый сбор")
pochta.sobrat()
stroki = []
for f in sorted((ROOT / "01_ISKHODNIKI" / "pochta").glob("*.md")):
    stroki += [s for s in f.read_text(encoding="utf-8").splitlines() if s.startswith("[")]
vse = "\n".join(stroki)
print("\n".join("   " + s[:170] for s in stroki))
proverka("кириллица в теме раскодирована", "Смета по объекту на Бривибас" in vse)
proverka("цитата под ответом отрезана", "Пришлите смету до пятницы." in vse and "старое письмо" not in vse)
proverka("HTML превращён в текст", "Надсилаю договір" in vse.replace("  ", " ") and "<b>" not in vse)
proverka("рассылка пропущена", "Скидки недели" not in vse)
proverka("исключённый домен не сохранён", "Выписка" not in vse and "секретно" not in vse)
proverka("письмо без Message-ID получило id ящика", "[mail:me@firma.lv:INBOX:777:104]" in vse)
proverka("большое письмо — только заголовок", "Чертежи" in vse and "большое письмо" in vse)
proverka("старое письмо (до даты старта) не взято", "очень старое" not in vse)
proverka("своё письмо подписано «Я»", any("· Я: Иван, отправлю в четверг." in s for s in stroki))
proverka("одно письмо в двух папках — одна строка", vse.count("[mail:smeta-1@client.lv]") == 1)
proverka("ящик указан в строке", "[ящик me@firma.lv]" in vse)
knt = json.loads((ROOT / "NASTROYKI" / "pochta-kontakty.json").read_text(encoding="utf-8"))
proverka("контакты из «Отправленных»", {"ivan@client.lv", "buh@firma.lv"} <= set(knt), sorted(knt))
proverka("отправители входящих НЕ стали контактами", "olga@partner.ua" not in knt and "x@spam.com" not in knt)
y = dost.yashchik("me@firma.lv")
proverka("найдена папка «Отправленные» по флагу \\Sent", dost.mutf7_dekod(y["otpravlennye"]) == "Отправленные")
proverka("запомнен последний UID", y["papki"]["INBOX"]["uid"] == 107, y["papki"])

print("=== второй сбор")
do = len(stroki)
pochta.sobrat()
stroki2 = []
for f in sorted((ROOT / "01_ISKHODNIKI" / "pochta").glob("*.md")):
    stroki2 += [s for s in f.read_text(encoding="utf-8").splitlines() if s.startswith("[")]
proverka("повторный сбор не плодит дубли", len(stroki2) == do, f"{do} → {len(stroki2)}")

print("=== отправка")
fayl = ROOT / "03_RAZBOR" / "pismo.txt"
fayl.parent.mkdir(exist_ok=True)


def popytka(*argv):
    fayl.write_text("Иван, смета во вложении будет завтра.\nДмитрий", encoding="utf-8")
    try:
        pochta.otpravit(list(argv))
        return "ok"
    except SystemExit as e:
        return str(e)


r = popytka("--komu", "evil@attacker.com", "--tema", "Re: Смета", "--tekst-fayl", "03_RAZBOR/pismo.txt")
proverka("незнакомый адрес — отказ", "нет среди тех" in r and not otpravleno, r[:90])
r = popytka("--komu", "olga@partner.ua", "--tema", "Re", "--tekst-fayl", "03_RAZBOR/pismo.txt")
proverka("тот, кто только писал владельцу, — тоже незнакомый", "нет среди тех" in r)
r = popytka("--komu", "ivan@client.lv", "--tema", "Re", "--tekst-fayl", "03_RAZBOR/pismo.txt", "--otvet-na", "mail:netu@x")
proverka("ответ на несуществующее письмо — отказ", "Не нашёл письмо" in r and not otpravleno)
r = popytka("--komu", "ivan@client.lv", "--tema", "Re: Смета по объекту на Бривибас",
            "--tekst-fayl", "03_RAZBOR/pismo.txt", "--otvet-na", "mail:smeta-1@client.lv")
m = otpravleno[-1] if otpravleno else None
proverka("знакомому — отправлено", r == "ok" and m is not None, r[:90])
proverka("ответ в той же цепочке", m and m["In-Reply-To"] == "<smeta-1@client.lv>" and m["References"] == "<smeta-1@client.lv>")
proverka("отправитель — выбранный ящик", m and m["From"] == "me@firma.lv")
proverka("файл с текстом удалён после отправки", not fayl.exists())
proverka("копия положена в «Отправленные»", len(dobavleno_v_otpravlennye) == 1)
zh = (ROOT / "NASTROYKI" / "otpravleno.log").read_text(encoding="utf-8")
proverka("запись в журнале отправок", "· почта · me@firma.lv → ivan@client.lv" in zh)
(ROOT / "02_ZNANIYA" / "LYUDI.md").write_text("| Олег | oleg@new.lv |\n", encoding="utf-8")
r = popytka("--komu", "oleg@new.lv", "--tema", "Привет", "--tekst-fayl", "03_RAZBOR/pismo.txt")
proverka("адрес из LYUDI.md — разрешён", r == "ok")
r = popytka("--komu", "new@person.lv", "--tema", "Привет", "--tekst-fayl", "03_RAZBOR/pismo.txt", "--novyy-adres")
proverka("новый адрес с подтверждением — разрешён", r == "ok")
with open(ROOT / "NASTROYKI" / "otpravleno.log", "a", encoding="utf-8") as f:
    for _ in range(10):
        f.write(f"{datetime.now():%Y-%m-%d %H:%M} · почта · me@firma.lv → x · t · t\n")
n = len(otpravleno)
r = popytka("--komu", "ivan@client.lv", "--tema", "Ещё", "--tekst-fayl", "03_RAZBOR/pismo.txt")
proverka("11-е письмо за сутки — отказ", "предел" in r and len(otpravleno) == n, r[:80])
