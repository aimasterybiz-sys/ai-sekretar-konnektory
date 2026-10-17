import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

KOREN = Path(__file__).resolve().parents[1]
OBRAZTSY = Path(__file__).parent / "obraztsy"


@pytest.fixture
def dom(tmp_path):
    """Домашняя папка ученика: секретарь в «AI SYSTEM» (как у Насти) и старый «WhatsApp в Claude»."""
    home = tmp_path / "home"
    shutil.copytree(OBRAZTSY / "02_sekretar", home / "AI SYSTEM" / "02_sekretar")
    shutil.copytree(OBRAZTSY / "WhatsApp-Claude", home / "WhatsApp-Claude")
    return home


def sekretar(home):
    return home / "AI SYSTEM" / "02_sekretar"


def zapustit(skript, *args, home, cwd, kodirovka="cp1252", timeout=300):
    """Запуск как у ученика на Windows: консоль не в UTF-8 (cp1252), домашняя папка — подставная."""
    env = dict(os.environ, HOME=str(home), USERPROFILE=str(home), PYTHONIOENCODING=kodirovka, OBNOVIT_BEZ_PIP="1")
    env.pop("PYTHONUTF8", None)
    r = subprocess.run([sys.executable, str(skript), *map(str, args)], cwd=str(cwd), env=env,
                       capture_output=True, timeout=timeout)
    return r.returncode, r.stdout.decode("utf-8", "replace") + r.stderr.decode("utf-8", "replace")


def kod_python(kod, cwd, timeout=120, home=None):
    """Выполнить кусок Python в отдельном процессе (модули wa/obshchee из разных папок не смешиваются)."""
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    if home:
        env.update(HOME=str(home), USERPROFILE=str(home))
    r = subprocess.run([sys.executable, "-c", kod], cwd=str(cwd), capture_output=True, timeout=timeout, env=env)
    return r.returncode, r.stdout.decode("utf-8", "replace") + r.stderr.decode("utf-8", "replace")
