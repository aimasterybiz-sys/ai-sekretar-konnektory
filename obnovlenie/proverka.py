"""Проверка коннекторов секретаря: Telegram, WhatsApp, почта и защита отправки — одним отчётом.

  python SKRIPTY/proverka.py

Ничего не меняет и ничего не отправляет. Ученик пересылает организатору снимок этого отчёта.
"""
import json
import platform
import subprocess
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ZDES = Path(__file__).resolve().parent
SEK = ZDES.parent if (ZDES.parent / "CLAUDE.md").exists() else None
WA_CLAUDE = Path.home() / "WhatsApp-Claude"
PRAVILA_SPRASHIVAT = ["mcp__whatsapp__whatsapp_otpravit", "mcp__messendzhery__whatsapp_otpravit",
                      "mcp__messendzhery__telegram_otpravit"] + [
    f"{shell}(*{skript} otpravit*)" if skript != "tg_otpravit.py" else f"{shell}(*tg_otpravit.py*)"
    for shell in ("Bash", "PowerShell") for skript in ("pochta.py", "wa.py", "tg_otpravit.py")]
BEZ_OKNA = {"creationflags": 0x08000000} if sys.platform == "win32" else {}


def zapustit(skript, *args, timeout=180):
    """Запустить скрипт коннектора и вернуть его вывод (только чтение)."""
    try:
        r = subprocess.run([sys.executable, str(skript), *args], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout, cwd=str(Path(skript).parent), **BEZ_OKNA)
        return (r.stdout + r.stderr).strip() or "(пусто)"
    except subprocess.TimeoutExpired:
        return "не ответил за 3 минуты"


def otstup(t):
    return "\n".join("     " + s for s in t.splitlines()[-12:])


def razdel(imya):
    print(f"\n— {imya} —")


def main():
    print("ПРОВЕРКА КОННЕКТОРОВ СЕКРЕТАРЯ")
    print(f"Компьютер: {platform.system()} {platform.release()} · Python {platform.python_version()}")
    if sys.version_info < (3, 10):
        print("✗ Python старый (нужен 3.10 или новее). Скажите Claude: «Поставь свежий Python».")
    versiya = (SEK / "NASTROYKI" / "versiya-konnektorov.txt") if SEK else None
    print("Версия коннекторов: " + (versiya.read_text(encoding="utf-8").strip()
                                    if versiya and versiya.exists() else "не обновлялись"))

    nedostayet = []
    for modul, chto in (("telethon", "Telegram"), ("keyring", "почта"), ("msal", "почта Outlook"), ("mcp", "коннекторы в чатах")):
        try:
            __import__(modul)
        except ImportError:
            nedostayet.append(f"{modul} ({chto})")
    if nedostayet:
        print("✗ Не хватает библиотек: " + ", ".join(nedostayet)
              + ". Скажите Claude: «Поставь библиотеки из SKRIPTY/requirements.txt».")

    razdel("Telegram")
    if SEK and (SEK / "NASTROYKI" / "secretary.session").exists():
        print("✓ Вход в Telegram есть")
    else:
        print("· Telegram не подключён (подключается в /skill-nastroyka, шаг 5)")

    razdel("WhatsApp")
    nashel = False
    est_wa_claude = (WA_CLAUDE / "NASTROYKI" / "wacli").exists()
    for imya, papka in (("в секретаре", SEK), ("WhatsApp в Claude", WA_CLAUDE)):
        if not papka or not (papka / "SKRIPTY" / "wa.py").exists():
            continue
        # у секретаря вход может быть свой, а может быть общий с «WhatsApp в Claude»
        if (papka / "NASTROYKI" / "wacli").exists() or (papka == SEK and est_wa_claude):
            nashel = True
            print(f"{imya}:\n" + otstup(zapustit(papka / "SKRIPTY" / "wa.py", "doctor")))
    if not nashel:
        print("· WhatsApp не подключён")

    razdel("Почта")
    if SEK and (SEK / "SKRIPTY" / "pochta.py").exists():
        if (SEK / "NASTROYKI" / "pochta.json").exists():
            print(otstup(zapustit(SEK / "SKRIPTY" / "pochta.py", "doctor")))
        else:
            print("· Коннектор почты стоит, ящики не подключены. Скажите Claude: «Подключи почту».")
    else:
        print("· Коннектор почты не установлен")

    razdel("Защита отправки")
    nastroyki = Path.home() / ".claude" / "settings.json"
    try:
        ask = json.loads(nastroyki.read_text(encoding="utf-8")).get("permissions", {}).get("ask", [])
    except Exception:
        ask = []
    net = [p for p in PRAVILA_SPRASHIVAT if p not in ask]
    print("✓ Перед каждой отправкой Claude спрашивает «Разрешить?»" if not net else
          "✗ Не везде Claude спрашивает перед отправкой. Скажите Claude: «Обнови коннекторы секретаря».")
    for papka in (SEK, WA_CLAUDE):
        for f, priznaki in (("mcp_messendzhery.py", ("VSEGDA_SPRASHIVAT",)), ("mcp_whatsapp.py", ("VSEGDA_SPRASHIVAT",)),
                            ("wa.py", ("t.year < 1971", "BEZ_OKNA", "CHUZHOY_VKHOD"))):
            p = papka / "SKRIPTY" / f if papka else None
            if not p or not p.exists():
                continue
            t = p.read_text(encoding="utf-8", errors="replace")
            if not all(x in t for x in priznaki):
                print(f"✗ {f} старой версии ({papka.name}). Скажите Claude: «Обнови коннекторы секретаря».")
    print("\nЕсли где-то ✗ — пришлите снимок этого отчёта организатору.")


if __name__ == "__main__":
    main()
