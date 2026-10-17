"""Собрать все подключённые каналы одной командой: python sbor.py
За определённый период: python sbor.py --s 2026-10-01 (с этой даты, не трогая обычный порядок)

Сам решает, что запускать:
- Telegram — если есть сессия (NASTROYKI/secretary.session) и выбраны чаты;
- WhatsApp — через программу wacli (wa.py), если она установлена: одинаково на Mac и Windows, умеет отправлять.
  Запасные пути, только если указать в .env: WA_SPOSOB=mac (база приложения WhatsApp на Mac)
  или WA_SPOSOB=chrome (расширение «Секретарь-WA»). Без wacli: Mac — приложение, Windows — расширение;
- почта по IMAP — если в .env есть MAIL_HOST.
Gmail и Outlook собирает сам агент через коннектор (это не скрипт).
"""
import os
import subprocess
import sys
from pathlib import Path

from obshchee import NASTROYKI, env, spisok_chatov

ZDES = Path(__file__).resolve().parent


def zapustit(skript, *args):
    print(f"\n=== {skript} ===", flush=True)
    r = subprocess.run([sys.executable, str(ZDES / skript), *args], cwd=ZDES)
    return r.returncode == 0


def main():
    if "--s" in sys.argv:
        os.environ["SEKRETAR_S"] = sys.argv[sys.argv.index("--s") + 1]
    e = env()
    itog = {}
    if (NASTROYKI / "secretary.session").exists() and spisok_chatov("chaty-telegram.txt"):
        itog["Telegram"] = zapustit("tg_sbor.py")
    else:
        print("Telegram: не подключён (нет входа или не выбраны чаты) — пропускаю")
    if spisok_chatov("chaty-whatsapp.txt"):
        sposob = e.get("WA_SPOSOB", "").lower()
        est_wacli = (ZDES / "bin" / ("wacli.exe" if os.name == "nt" else "wacli")).exists()
        # wacli — основной путь везде, где он установлен; mac и chrome — запасные, только если указаны явно
        if sposob == "wacli" or (est_wacli and sposob not in ("mac", "chrome")):
            itog["WhatsApp"] = zapustit("wa.py")
        else:
            cherez_chrome = sys.platform != "darwin" or sposob == "chrome"
            itog["WhatsApp"] = zapustit("wa_web.py" if cherez_chrome else "wa_mac.py")
    else:
        print("WhatsApp: не выбраны чаты — пропускаю")
    if e.get("MAIL_HOST"):
        itog["Почта IMAP"] = zapustit("pochta_imap.py")
    print("\nИТОГ: " + (", ".join(f"{k} {'✓' if v else '✗'}" for k, v in itog.items()) or "ничего не подключено"))


if __name__ == "__main__":
    main()
