"""Страница «Подключение почты»: выбрать почту, вписать адрес, вставить пароль — секретарь сам найдёт сервер,
проверит вход и отправку и сохранит пароль в хранилище системы. Можно подключить сколько угодно ящиков подряд.

Страница открывается только на этом компьютере (127.0.0.1), с одноразовым ключом в адресе.
Закрывается по кнопке «Готово» или через 15 минут без действий. Пароль не печатается и в чат не попадает.
"""
import json
import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pochta_dostup as dost
import pochta_servery as srv
from pochta_dostup import OshibkaPochty

PROSTOY = 15 * 60

PLITKI = [
    ("gmail", "Gmail", "gmail.com"), ("outlook", "Outlook / Hotmail", ""), ("icloud", "iCloud", "icloud.com"),
    ("yahoo", "Yahoo", "yahoo.com"), ("ukrnet", "ukr.net", "ukr.net"),
    ("rabochaya", "Рабочая почта (Google или Microsoft)", ""), ("proton", "Proton", "proton.me"),
    ("drugaya", "Другая / на своём домене", ""),
]

STRANITSA = r"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Подключение почты</title>
<style>
body{font-family:-apple-system,"Segoe UI",system-ui,sans-serif;background:#f5f5f7;margin:0;padding:32px 16px;color:#1d1d1f}
.card{max-width:680px;margin:0 auto 16px;background:#fff;border-radius:16px;padding:28px 32px;box-shadow:0 6px 24px rgba(0,0,0,.08)}
h1{font-size:26px;margin:0 0 6px} h2{font-size:19px;margin:0 0 14px}
.sub{color:#6e6e73;margin:0;font-size:16px;line-height:1.5}
.plitki{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:10px}
.plitka{font-size:16px;font-weight:600;padding:16px 12px;border:2px solid #d2d2d7;border-radius:12px;background:#fff;cursor:pointer;text-align:left;color:#1d1d1f}
.plitka:hover{border-color:#0a84ff} .plitka.vybrana{border-color:#0a84ff;background:#eef6ff}
.plitka small{display:block;font-weight:400;color:#6e6e73;font-size:13px;margin-top:4px}
label{display:block;font-weight:600;font-size:17px;margin:20px 0 6px}
input{width:100%;box-sizing:border-box;font-size:18px;padding:14px;border:2px solid #d2d2d7;border-radius:10px}
input:focus{outline:none;border-color:#0a84ff}
.opr{margin-top:10px;font-size:15px;color:#1a7f37;min-height:20px} .opr.ploho{color:#d70015}
ol{padding-left:22px;margin:14px 0 0} li{font-size:16px;line-height:1.5;margin:0 0 12px}
a.knopka{display:inline-block;margin-top:6px;padding:8px 14px;border-radius:9px;background:#eef6ff;color:#0a64d0;text-decoration:none;font-weight:600;font-size:15px}
button.glavnaya{margin-top:24px;width:100%;font-size:19px;font-weight:600;padding:16px;border:0;border-radius:12px;background:#0a84ff;color:#fff;cursor:pointer}
button.glavnaya:disabled{background:#a1c9f5;cursor:wait}
button.vtorostep{margin-top:12px;width:100%;font-size:17px;font-weight:600;padding:14px;border:2px solid #d2d2d7;border-radius:12px;background:#fff;cursor:pointer;color:#1d1d1f}
.pokaz{font-size:14px;color:#0a64d0;background:none;border:0;cursor:pointer;padding:6px 0}
.itog{font-size:17px;line-height:1.55;border-radius:12px;padding:16px 18px;margin-top:18px}
.itog.ok{background:#eaf7ee;color:#14532d} .itog.ploho{background:#fdecee;color:#8a0b1a}
.podkl{font-size:16px;line-height:1.8;margin:0;padding-left:20px}
.skryto{display:none} .tikho{color:#6e6e73;font-size:14px;margin-top:8px}
</style></head><body>
<div class="card"><h1>📬 Подключение почты</h1>
<p class="sub">Можно подключить сколько угодно ящиков. Пароль сохраняется в защищённом хранилище вашего компьютера
и не попадает ни в чат, ни в файлы. Секретарь читает письма, не отмечая их прочитанными.</p></div>

<div class="card skryto" id="uzhe"><h2>Уже подключены</h2><ul class="podkl" id="uzhe_spisok"></ul></div>

<div class="card" id="shag1"><h2>1. Какую почту подключаем?</h2><div class="plitki" id="plitki"></div></div>

<div class="card skryto" id="shag2"><h2>2. Адрес и вход</h2>
<label for="adres">Адрес почты</label>
<input id="adres" type="email" autocomplete="off" spellcheck="false" placeholder="anna@firma.com">
<div class="opr" id="opr"></div>
<div id="servery" class="skryto">
  <label for="imap">Сервер входящей почты (IMAP)</label><input id="imap" placeholder="mail.firma.com">
  <label for="smtp">Сервер отправки (SMTP) — можно пусто, если тот же</label><input id="smtp" placeholder="mail.firma.com">
</div>
<ol id="shagi"></ol>
<div id="blok_parol" class="skryto">
  <label for="parol" id="parol_nadpis">Пароль</label>
  <input id="parol" type="password" autocomplete="new-password" spellcheck="false">
  <button class="pokaz" type="button" id="pokaz">Показать пароль</button>
  <button class="glavnaya" id="podkl">Подключить</button>
</div>
<div id="blok_ms" class="skryto"><button class="glavnaya" id="ms">Войти через Microsoft</button>
  <div class="tikho">Откроется окно Microsoft в браузере. После входа вернитесь на эту вкладку.</div></div>
<div id="itog"></div>
</div>

<div class="card skryto" id="dalshe">
<button class="glavnaya" id="eshche">➕ Подключить ещё одну почту</button>
<button class="vtorostep" id="gotovo">Готово — вернуться в Claude</button></div>

<div class="card skryto" id="konets"><h2>✅ Готово</h2><p class="sub">Эту вкладку можно закрыть и вернуться в Claude.</p></div>

<script>
const T = "__TOKEN__", PLITKI = __PLITKI__, MS_EST = __MS__;
const $ = id => document.getElementById(id);
let vybor = null, nastr = null, tayMer = null;

function api(put, telo) {
  const o = telo ? {method: "POST", headers: {"Content-Type": "application/json", "X-Token": T}, body: JSON.stringify(telo)}
                 : {headers: {"X-Token": T}};
  return fetch(put, o).then(r => r.json());
}
function tekst(el, t) { el.textContent = t; return el; }

function uzhe() {
  api("/api/spisok").then(d => {
    const ul = $("uzhe_spisok"); ul.innerHTML = "";
    d.yashchiki.forEach(y => ul.appendChild(tekst(document.createElement("li"), y)));
    $("uzhe").classList.toggle("skryto", !d.yashchiki.length);
  });
}

PLITKI.forEach(([k, imya, domen]) => {
  const b = document.createElement("button"); b.className = "plitka"; b.textContent = imya;
  if (k === "outlook" && !MS_EST) { const s = document.createElement("small"); s.textContent = "пока не включено"; b.appendChild(s); }
  b.onclick = () => {
    document.querySelectorAll(".plitka").forEach(x => x.classList.remove("vybrana")); b.classList.add("vybrana");
    vybor = {k, domen}; $("shag2").classList.remove("skryto"); $("itog").innerHTML = "";
    $("adres").placeholder = domen ? "anna@" + domen : (k === "outlook" ? "anna@outlook.com" : "anna@firma.com");
    if (k === "outlook" && !MS_EST) {
      pokazatOshibku("Вход через Microsoft ещё не включён организатором курса. Остальные почты подключаются уже сейчас.");
    } else if ($("adres").value) { opredelit(); }
    $("adres").focus(); $("shag2").scrollIntoView({behavior: "smooth"});
  };
  $("plitki").appendChild(b);
});

function polnyyAdres() {
  let a = $("adres").value.trim();
  if (a && !a.includes("@") && vybor && vybor.domen) { a = a + "@" + vybor.domen; }
  return a;
}
function pokazatOshibku(t) { const o = $("opr"); o.className = "opr ploho"; o.textContent = t; }

function opredelit() {
  const a = polnyyAdres(); if (!a.includes("@")) return;
  $("opr").className = "opr"; $("opr").textContent = "Ищу настройки этой почты…";
  ["blok_parol", "blok_ms", "servery"].forEach(id => $(id).classList.add("skryto")); $("shagi").innerHTML = "";
  api("/api/opredelit?adres=" + encodeURIComponent(a)).then(d => {
    nastr = d;
    if (d.oshibka) {
      pokazatOshibku(d.oshibka);
      if (d.vruchnuyu) { $("servery").classList.remove("skryto"); pokazatShagi(d.shagi || []); $("blok_parol").classList.remove("skryto"); }
      return;
    }
    $("opr").textContent = "✓ " + d.imya + (d.uzhe ? " — уже подключена, можно подключить заново" : "");
    pokazatShagi(d.shagi);
    if (d.vkhod === "microsoft") {
      if (!MS_EST) { pokazatOshibku("Это почта Microsoft, а вход через Microsoft ещё не включён организатором курса."); return; }
      $("blok_ms").classList.remove("skryto");
    } else {
      $("parol_nadpis").textContent = d.nadpis_parolya; $("blok_parol").classList.remove("skryto");
    }
  });
}
function pokazatShagi(shagi) {
  const ol = $("shagi"); ol.innerHTML = "";
  shagi.forEach(([t, ssylka]) => {
    const li = tekst(document.createElement("li"), t);
    if (ssylka) { const a = document.createElement("a"); a.className = "knopka"; a.target = "_blank"; a.rel = "noopener";
      a.href = ssylka[1]; a.textContent = ssylka[0] + " ↗"; li.appendChild(document.createElement("br")); li.appendChild(a); }
    ol.appendChild(li);
  });
}
$("adres").addEventListener("input", () => { clearTimeout(tayMer); tayMer = setTimeout(opredelit, 700); });
$("adres").addEventListener("blur", () => { clearTimeout(tayMer); opredelit(); });
$("pokaz").onclick = () => { const p = $("parol"); p.type = p.type === "password" ? "text" : "password";
  $("pokaz").textContent = p.type === "password" ? "Показать пароль" : "Скрыть пароль"; };

function itog(d) {
  const div = document.createElement("div");
  if (d.ok) {
    div.className = "itog ok";
    let t = "✅ " + d.adres + " подключена.";
    if (d.vkhodyashchikh !== null && d.vkhodyashchikh !== undefined) t += " Во входящих писем: " + d.vkhodyashchikh + ".";
    t += d.otpravlennye ? " Нашёл папку «" + d.otpravlennye + "»." : " Папку «Отправленные» не нашёл — секретарь будет видеть только входящие.";
    t += d.otpravka ? " Отправка работает." : " Отправка не работает: " + d.pochemu_net_otpravki + " Читать письма секретарь будет.";
    div.textContent = t;
    ["blok_parol", "blok_ms", "servery"].forEach(id => $(id).classList.add("skryto")); $("shagi").innerHTML = "";
    $("parol").value = ""; $("dalshe").classList.remove("skryto"); uzhe();
    $("dalshe").scrollIntoView({behavior: "smooth"});
  } else { div.className = "itog ploho"; div.textContent = "✗ " + d.oshibka; }
  $("itog").innerHTML = ""; $("itog").appendChild(div);
}

$("podkl").onclick = () => {
  const a = polnyyAdres(), p = $("parol").value;
  if (!a.includes("@")) { pokazatOshibku("Впишите адрес почты."); return; }
  if (!p) { pokazatOshibku("Вставьте пароль."); return; }
  const b = $("podkl"); b.disabled = true; b.textContent = "Проверяю вход и отправку… 5–20 секунд";
  api("/api/podklyuchit", {adres: a, parol: p, imap: $("imap").value.trim(), smtp: $("smtp").value.trim()})
    .then(itog).catch(() => itog({ok: false, oshibka: "Страница потеряла связь с секретарём. Попросите его открыть её заново."}))
    .finally(() => { b.disabled = false; b.textContent = "Подключить"; });
};

$("ms").onclick = () => {
  const a = polnyyAdres(), b = $("ms"); b.disabled = true; b.textContent = "Жду входа в окне Microsoft…";
  api("/api/microsoft", {adres: a}).then(() => {
    const opros = setInterval(() => api("/api/microsoft").then(d => {
      if (d.sostoyanie === "zhdu") return;
      clearInterval(opros); b.disabled = false; b.textContent = "Войти через Microsoft"; itog(d);
    }), 2000);
  });
};

$("eshche").onclick = () => {
  $("dalshe").classList.add("skryto"); $("shag2").classList.add("skryto"); $("adres").value = ""; $("opr").textContent = "";
  $("itog").innerHTML = ""; document.querySelectorAll(".plitka").forEach(x => x.classList.remove("vybrana"));
  window.scrollTo({top: 0, behavior: "smooth"});
};
$("gotovo").onclick = () => {
  api("/api/gotovo", {}).finally(() => {
    ["shag1", "shag2", "dalshe", "uzhe"].forEach(id => $(id).classList.add("skryto")); $("konets").classList.remove("skryto");
  });
};
uzhe();
</script></body></html>"""


def shagi_dlya(nastr):
    return [[t, list(s) if s else None] for t, s in srv.INSTR.get(nastr.get("instr", "obychnyy"), [])]


NADPIS = {"gmail": "Пароль приложения Google (16 букв)", "google_workspace": "Пароль приложения Google (16 букв)",
          "icloud": "Пароль для приложений Apple", "yahoo": "Пароль приложения Yahoo", "aol": "Пароль приложения AOL",
          "ukrnet": "Пароль IMAP-доступа ukr.net", "proton": "Пароль из Proton Bridge"}


class Server:
    def __init__(self):
        self.token = secrets.token_urlsafe(18)
        self.poslednee = time.time()
        self.konets = threading.Event()
        self.podklyucheny = []
        self.ms = {"sostoyanie": "net"}
        self.kesh = {}

    def opredelit(self, adres):
        adres = adres.strip().lower()
        if adres not in self.kesh:
            self.kesh[adres] = srv.opredelit(adres)
        return adres, self.kesh[adres]

    def ms_vkhod(self, adres):
        try:
            _, nastr = self.opredelit(adres)
            if "oshibka" in nastr or nastr["vkhod"] != "microsoft":
                raise OshibkaPochty("Это не почта Microsoft.")
            voshel = dost.ms_voyti(adres)
            if voshel and voshel != adres:
                dost.ms_zabyt(voshel)
                raise OshibkaPochty(f"В окне Microsoft вы вошли как {voshel}, а подключаем {adres}. "
                                    "Нажмите кнопку ещё раз и выберите нужную почту.")
            rez = dost.proverit_i_sokhranit(adres, nastr)
            self.podklyucheny.append(adres)
            self.ms = dict(rez, ok=True, sostoyanie="gotovo")
        except OshibkaPochty as e:
            self.ms = {"ok": False, "oshibka": str(e), "sostoyanie": "gotovo"}
        except Exception as e:
            self.ms = {"ok": False, "oshibka": f"Вход через Microsoft не получился ({type(e).__name__}).",
                       "sostoyanie": "gotovo"}


def obrabotchik(s, port):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _svoy(self):
            host_ok = self.headers.get("Host") in (f"127.0.0.1:{port}", f"localhost:{port}")
            t = self.headers.get("X-Token") or parse_qs(urlparse(self.path).query).get("t", [""])[0]
            return host_ok and secrets.compare_digest(t, s.token)

        def _otvet(self, kod, telo, tip="application/json; charset=utf-8"):
            dannye = telo if isinstance(telo, bytes) else json.dumps(telo, ensure_ascii=False).encode("utf-8")
            self.send_response(kod)
            self.send_header("Content-Type", tip)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()
            self.wfile.write(dannye)

        def do_GET(self):
            if not self._svoy():
                return self._otvet(403, {"oshibka": "нет доступа"})
            s.poslednee = time.time()
            u = urlparse(self.path)
            if u.path == "/":
                html = (STRANITSA.replace("__TOKEN__", s.token)
                        .replace("__PLITKI__", json.dumps(PLITKI, ensure_ascii=False))
                        .replace("__MS__", "true" if dost.ms_client_id() else "false"))
                return self._otvet(200, html.encode("utf-8"), "text/html; charset=utf-8")
            if u.path == "/api/spisok":
                return self._otvet(200, {"yashchiki": [f"{y['adres']} · {y['imya']}"
                                                       for y in dost.zagruzit()["yashchiki"]]})
            if u.path == "/api/opredelit":
                adres, nastr = s.opredelit(parse_qs(u.query).get("adres", [""])[0])
                otvet = {k: nastr[k] for k in ("oshibka", "vruchnuyu", "imya", "vkhod") if k in nastr}
                otvet["shagi"] = shagi_dlya(nastr if "oshibka" not in nastr else {"instr": "obychnyy"})
                otvet["nadpis_parolya"] = NADPIS.get(nastr.get("provayder"), "Пароль от этой почты")
                otvet["uzhe"] = bool(dost.yashchik(adres)) if "@" in adres else False
                return self._otvet(200, otvet)
            if u.path == "/api/microsoft":
                return self._otvet(200, s.ms)
            return self._otvet(404, {"oshibka": "нет такой страницы"})

        def do_POST(self):
            if not self._svoy():
                return self._otvet(403, {"oshibka": "нет доступа"})
            s.poslednee = time.time()
            try:
                telo = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length") or 0), 20000)) or b"{}")
            except ValueError:
                return self._otvet(400, {"oshibka": "непонятный запрос"})
            put = urlparse(self.path).path
            if put == "/api/podklyuchit":
                adres, nastr = s.opredelit(telo.get("adres", ""))
                try:
                    if telo.get("imap"):
                        nastr = srv.vruchnuyu(adres, telo["imap"], telo.get("smtp") or None)
                    if "oshibka" in nastr:
                        raise OshibkaPochty(nastr["oshibka"])
                    if nastr["vkhod"] != "parol":
                        raise OshibkaPochty("Эту почту подключают кнопкой «Войти через Microsoft».")
                    rez = dost.proverit_i_sokhranit(adres, nastr, telo.get("parol", ""))
                    s.podklyucheny.append(adres)
                    return self._otvet(200, dict(rez, ok=True))
                except OshibkaPochty as e:
                    return self._otvet(200, {"ok": False, "oshibka": str(e)})
                except Exception as e:
                    return self._otvet(200, {"ok": False, "oshibka": f"Не получилось подключить ({type(e).__name__}). "
                                                                      "Проверьте адрес и пароль и повторите."})
            if put == "/api/microsoft":
                if s.ms.get("sostoyanie") != "zhdu":
                    s.ms = {"sostoyanie": "zhdu"}
                    threading.Thread(target=s.ms_vkhod, args=(telo.get("adres", "").strip().lower(),), daemon=True).start()
                return self._otvet(200, {"ok": True})
            if put == "/api/gotovo":
                s.konets.set()
                return self._otvet(200, {"ok": True})
            return self._otvet(404, {"oshibka": "нет такой страницы"})
    return H


def zapustit():
    s = Server()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), None)
    port = httpd.server_address[1]
    httpd.RequestHandlerClass = obrabotchik(s, port)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{port}/?t={s.token}"
    print("Открываю страницу «Подключение почты» в браузере.", flush=True)
    print(f"Если она не открылась — откройте этот адрес: {url}", flush=True)
    webbrowser.open(url)
    while not s.konets.wait(5):
        if time.time() - s.poslednee > PROSTOY and s.ms.get("sostoyanie") != "zhdu":
            print("Страница закрыта: 15 минут без действий.")
            break
    time.sleep(1)
    httpd.shutdown()
    if s.podklyucheny:
        print("Подключено за этот раз: " + ", ".join(dict.fromkeys(s.podklyucheny)))
    else:
        print("За этот раз новых ящиков не подключено.")
    vse = [y["adres"] for y in dost.zagruzit()["yashchiki"]]
    print("Всего подключено: " + (", ".join(vse) if vse else "ни одного"))


if __name__ == "__main__":
    zapustit()
