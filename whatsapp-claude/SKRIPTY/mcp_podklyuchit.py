"""Подключает коннектор WhatsApp ко всем чатам Claude на этом компьютере.

  python mcp_podklyuchit.py           подключить (или переподключить после переноса папки)
  python mcp_podklyuchit.py --ubrat   отключить

После подключения Claude нужно полностью закрыть и открыть снова.
"""
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Консоль Windows по умолчанию не печатает кириллицу, «✓» и эмодзи — переключаем вывод на UTF-8
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

IMYA = "whatsapp"
SERVER = Path(__file__).resolve().parent / "mcp_whatsapp.py"


def zapis(put, dannye):
    if put.exists():
        shutil.copy2(put, put.with_name(f"{put.name}.kopiya-{datetime.now():%Y%m%d-%H%M%S}"))
    put.parent.mkdir(parents=True, exist_ok=True)
    put.write_text(json.dumps(dannye, ensure_ascii=False, indent=2), encoding="utf-8")


def v_konfig(put, ubrat, s_tipom):
    """Добавляет или убирает коннектор в файле настроек Claude, сохранив копию файла."""
    dannye = json.loads(put.read_text(encoding="utf-8")) if put.exists() else {}
    servery = dannye.setdefault("mcpServers", {})
    if ubrat:
        if IMYA not in servery:
            return
        servery.pop(IMYA)
    else:
        zapis_servera = {"command": sys.executable, "args": [str(SERVER)]}
        if s_tipom:
            zapis_servera = {"type": "stdio", **zapis_servera, "env": {}}
        if servery.get(IMYA) == zapis_servera:
            return
        servery[IMYA] = zapis_servera
    zapis(put, dannye)


def main():
    ubrat = "--ubrat" in sys.argv
    if not ubrat:
        try:
            import mcp  # noqa: F401
        except ImportError:
            sys.exit("Нет библиотеки mcp. Сначала: python -m pip install -r SKRIPTY/requirements.txt")

    # 1. Вкладка Code (Claude Code): через команду claude, если она есть, иначе — файл ~/.claude.json
    claude = shutil.which("claude")
    if claude:
        subprocess.run([claude, "mcp", "remove", "-s", "user", IMYA], capture_output=True, text=True)
        if not ubrat:
            subprocess.run([claude, "mcp", "add", "-s", "user", IMYA, "--", sys.executable, str(SERVER)],
                           capture_output=True, text=True)
    else:
        v_konfig(Path.home() / ".claude.json", ubrat, s_tipom=True)

    # 2. Вкладка Chat приложения Claude: claude_desktop_config.json
    if sys.platform == "darwin":
        papka = Path.home() / "Library" / "Application Support" / "Claude"
    elif sys.platform == "win32":
        papka = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "Claude"
    else:
        papka = Path.home() / ".config" / "Claude"
    if papka.exists():
        v_konfig(papka / "claude_desktop_config.json", ubrat, s_tipom=False)

    if ubrat:
        print("Коннектор WhatsApp отключён.")
    else:
        print("Коннектор WhatsApp подключён. Полностью закройте Claude и откройте снова — "
              "WhatsApp появится в любом чате.")


if __name__ == "__main__":
    main()
