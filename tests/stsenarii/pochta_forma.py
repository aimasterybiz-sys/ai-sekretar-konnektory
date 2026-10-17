"""Проверка страницы подключения почты в песочнице: доступ, определение, ошибки входа, закрытие."""
import json
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser

for _s in (sys.stdout, sys.stderr):
    _s.reconfigure(encoding="utf-8", errors="replace")

SKRIPTY = sys.argv[1]
sys.path.insert(0, SKRIPTY)
import pochta_forma as pf  # noqa: E402
import pochta_dostup as dost  # noqa: E402


def _ne_pustil(y, p=None):  # без настоящего входа в чужую почту: ответ сервера Google при неверном пароле
    raise dost.OshibkaPochty(dost.oshibka_vkhoda("[AUTHENTICATIONFAILED] Invalid credentials (Failure)", y))


dost.imap_vkhod = _ne_pustil

pf.PROSTOY = 60
otkryto = []
webbrowser.open = lambda url: otkryto.append(url) or True
potok = threading.Thread(target=pf.zapustit, daemon=True)
potok.start()
for _ in range(50):
    if otkryto:
        break
    time.sleep(0.1)
url = otkryto[0]
baza, token = url.split("/?t=")
port = baza.rsplit(":", 1)[1]


def zapros(put, telo=None, token_=token, host=None):
    zag = {"X-Token": token_} if token_ else {}
    if host:
        zag["Host"] = host
    dannye = None
    if telo is not None:
        dannye = json.dumps(telo).encode()
        zag["Content-Type"] = "application/json"
    req = urllib.request.Request(baza + put, data=dannye, headers=zag)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def proverka(imya, uslovie, podrobno=""):
    print(("✓ " if uslovie else "✗ ") + imya + (f" — {podrobno}" if podrobno else ""))


kod, _ = zapros("/", token_=None)
proverka("без ключа → 403", kod == 403, kod)
kod, _ = zapros("/", token_="nevernyy")
proverka("неверный ключ → 403", kod == 403, kod)
kod, _ = zapros("/", host=f"evil.com:{port}")
proverka("чужой Host (DNS rebinding) → 403", kod == 403, kod)
kod, html = zapros("/")
proverka("страница с ключом → 200", kod == 200 and "Подключение почты" in html and token in html, kod)

for adres, zhdu in [("anna@gmail.com", "Gmail"), ("x@protuz.com", "Hostinger"), ("y@microsoft.com", "Microsoft 365"),
                    ("w@icloud.com", "iCloud"), ("v@ukr.net", "ukr.net")]:
    _, t = zapros("/api/opredelit?adres=" + adres)
    d = json.loads(t)
    proverka(f"определение {adres}", zhdu in d.get("imya", ""), f"{d.get('imya')} · вход {d.get('vkhod')} · шагов {len(d['shagi'])} · «{d.get('nadpis_parolya')}»")
_, t = zapros("/api/opredelit?adres=z@i.ua")
proverka("i.ua — понятный отказ", "IMAP" in json.loads(t).get("oshibka", ""))
_, t = zapros("/api/opredelit?adres=q@nonexistent-domain-xyz123.com")
d = json.loads(t)
proverka("неизвестный домен — просим сервер вручную", d.get("vruchnuyu") is True and len(d["shagi"]) > 0)

t0 = time.time()
_, t = zapros("/api/podklyuchit", {"adres": "sekretar.test.nonexistent.7q2x@gmail.com", "parol": "abcd efgh ijkl mnop"})
d = json.loads(t)
proverka("неверный пароль Gmail — человеческая ошибка", d.get("ok") is False and "пароль" in d.get("oshibka", "").lower(),
         f"{time.time() - t0:.1f} с: {d.get('oshibka')}")
_, t = zapros("/api/podklyuchit", {"adres": "anna@nonexistent-domain-xyz123.com", "parol": "x",
                                   "imap": "mail.nonexistent-domain-xyz123.com"})
d = json.loads(t)
proverka("сервер вручную, которого нет — понятная ошибка", d.get("ok") is False, d.get("oshibka"))
_, t = zapros("/api/podklyuchit", {"adres": "y@microsoft.com", "parol": "x"})
proverka("Microsoft по паролю — отказ с подсказкой", "Microsoft" in json.loads(t).get("oshibka", ""), json.loads(t).get("oshibka"))
_, t = zapros("/api/spisok")
proverka("ничего лишнего не сохранено", json.loads(t)["yashchiki"] == [], t)

kod, _ = zapros("/api/gotovo", {})
potok.join(15)
proverka("«Готово» закрывает страницу", not potok.is_alive())
