"""Общее для всех сборщиков секретаря: пути, ключи, окно по времени, запись сообщений.

Формат строки в 01_ISKHODNIKI/<канал>/<ГГГГ-ММ-ДД>.md (одна строка = одно сообщение):
[id] ГГГГ-ММ-ДД ЧЧ:ММ · Чат · Автор: текст
id — уникальный ключ источника (tg:<чат>:<сообщение>, wa:<чат>:<сообщение>, mail:<id>).
По нему агенты ловят дубли, поэтому id не меняется никогда.
"""
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ISKHODNIKI = ROOT / "01_ISKHODNIKI"
GOLOS = ISKHODNIKI / "golosovye"
NASTROYKI = ROOT / "NASTROYKI"
SOSTOYANIE = NASTROYKI / "sostoyanie.json"

# Windows-консоль по умолчанию не печатает кириллицу и эмодзи
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def env():
    """Ключи из .env (строки КЛЮЧ=значение). Переменные окружения важнее файла."""
    znach = {}
    f = ROOT / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            znach[k.strip()] = v.strip().strip('"').strip("'")
    for k, v in os.environ.items():
        if k in znach or k.startswith(("TG_", "GROQ_", "MAIL_", "WA_", "SEKRETAR_")):
            znach[k] = v
    return znach


def nachalo_po_umolchaniyu():
    """Старт мониторинга: SEKRETAR_START из .env (ГГГГ-ММ-ДД), иначе понедельник этой недели."""
    s = env().get("SEKRETAR_START")
    if s:
        return datetime.strptime(s, "%Y-%m-%d")
    segodnya = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return segodnya - timedelta(days=segodnya.weekday())


def _sostoyanie():
    if SOSTOYANIE.exists():
        return json.loads(SOSTOYANIE.read_text(encoding="utf-8"))
    return {}


def okno(kanal):
    """С какого момента собирать канал: явная дата этого запуска (SEKRETAR_S, ставит sbor.py --s),
    иначе с прошлого запуска (минус час запаса), иначе со старта."""
    yavno = os.environ.get("SEKRETAR_S")
    if yavno:
        return datetime.strptime(yavno, "%Y-%m-%d")
    st = _sostoyanie().get(kanal)
    if st:
        return datetime.fromisoformat(st) - timedelta(hours=1)
    return nachalo_po_umolchaniyu()


def zapomnit(kanal, moment=None):
    NASTROYKI.mkdir(parents=True, exist_ok=True)
    st = _sostoyanie()
    st[kanal] = (moment or datetime.now()).isoformat(timespec="seconds")
    SOSTOYANIE.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")


def spisok_chatov(fayl):
    """Чаты из NASTROYKI/<fayl>: по одному названию в строке, # — комментарий."""
    p = NASTROYKI / fayl
    if not p.exists():
        return []
    return [s.strip() for s in p.read_text(encoding="utf-8").splitlines()
            if s.strip() and not s.strip().startswith("#")]


_STROKA = re.compile(r"^\[(?P<id>[^\]]+)\] (?P<vremya>\d{4}-\d{2}-\d{2} \d{2}:\d{2}) · ")


def _odna_stroka(t):
    return re.sub(r"\s*\n\s*", " ⏎ ", (t or "").strip())


def zapisat(kanal, soobshcheniya):
    """soobshcheniya: список словарей id, vremya (datetime), chat, avtor, tekst.
    Раскладывает по дням, объединяет с уже записанным по id. Возвращает число новых."""
    papka = ISKHODNIKI / kanal
    papka.mkdir(parents=True, exist_ok=True)
    po_dnyam = {}
    for s in soobshcheniya:
        po_dnyam.setdefault(s["vremya"].strftime("%Y-%m-%d"), []).append(s)
    novykh = 0
    for den, spisok in po_dnyam.items():
        f = papka / f"{den}.md"
        stroki = {}
        if f.exists():
            for line in f.read_text(encoding="utf-8").splitlines():
                m = _STROKA.match(line)
                if m:
                    stroki[m["id"]] = line
        for s in spisok:
            line = (f"[{s['id']}] {s['vremya'].strftime('%Y-%m-%d %H:%M')} · "
                    f"{_odna_stroka(s['chat'])} · {_odna_stroka(s['avtor'])}: {_odna_stroka(s['tekst'])}")
            if s["id"] not in stroki:
                novykh += 1
            stroki[s["id"]] = line
        upor = sorted(stroki.values(), key=lambda l: _STROKA.match(l)["vremya"])
        f.write_text(f"# {kanal} · {den}\n\n" + "\n".join(upor) + "\n", encoding="utf-8")
    return novykh


def bezopasnoe_imya(s):
    return re.sub(r"[^\w.-]+", "_", s)[:150]
