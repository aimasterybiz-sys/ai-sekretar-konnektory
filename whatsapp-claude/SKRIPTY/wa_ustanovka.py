"""Ставит wacli — программу для WhatsApp — в SKRIPTY/bin. Готовая сборка с GitHub, сверенная по контрольной сумме.

  python wa_ustanovka.py              поставить последнюю версию
  python wa_ustanovka.py 0.21.0       поставить конкретную версию
  python wa_ustanovka.py --proverit   только показать, какая стоит и есть ли новее

Сначала берёт нашу сборку (github.com/aimasterybiz-sys/wacli-sborka): она работает на macOS 12 и новее,
Windows x64 и Windows ARM64. Если её нет — официальную сборку авторов (github.com/openclaw/wacli, macOS 15+).
Ничего не компилирует, Node.js и Go не нужны.
"""
import hashlib
import io
import json
import platform
import ssl
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

# Консоль Windows по умолчанию не печатает кириллицу, «✓» и эмодзи — переключаем вывод на UTF-8
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ISTOCHNIKI = ["aimasterybiz-sys/wacli-sborka", "openclaw/wacli"]
BIN_DIR = Path(__file__).resolve().parent / "bin"
IMYA_BIN = "wacli.exe" if sys.platform == "win32" else "wacli"
TSEL = BIN_DIR / IMYA_BIN


def ssl_kontekst():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def skachat(url):
    req = urllib.request.Request(url, headers={"User-Agent": "sekretar-wa-ustanovka"})
    with urllib.request.urlopen(req, context=ssl_kontekst(), timeout=120) as r:
        return r.read()


def poslednyaya(repo):
    try:
        return json.loads(skachat(f"https://api.github.com/repos/{repo}/releases/latest"))["tag_name"].lstrip("v")
    except Exception:
        return None


def ustanovlennaya():
    if not TSEL.exists():
        return None
    try:
        r = subprocess.run([str(TSEL), "--version"], capture_output=True, text=True, timeout=30)
        return r.stdout.strip().split()[-1].lstrip("v") if r.returncode == 0 else None
    except Exception:
        return None


def sistema():
    """(os, [варианты файлов в порядке предпочтения], понятное название системы)."""
    m = platform.machine().lower()
    if sys.platform == "darwin":
        ver = platform.mac_ver()[0] or "?"
        try:
            glavnaya = int(ver.split(".")[0])
        except ValueError:
            glavnaya = 99
        if glavnaya < 12:
            sys.exit(f"macOS {ver} слишком старая: wacli работает с macOS 12 и новее. "
                     "Для WhatsApp на этом Mac оставьте старый способ (WA_SPOSOB=mac).")
        arch = "arm64" if m in ("arm64", "aarch64") else "amd64"
        return "darwin", ["darwin_universal", f"darwin_{arch}"], f"macOS {ver}"
    if sys.platform == "win32":
        arm = m in ("arm64", "aarch64")
        # Windows на ARM умеет запускать файлы x64 через встроенную эмуляцию — это запасной вариант
        return "windows", (["windows_arm64", "windows_amd64"] if arm else ["windows_amd64"]), \
            f"Windows {platform.release()} {'ARM64' if arm else 'x64'}"
    if sys.platform.startswith("linux"):
        return "linux", ["linux_arm64" if m in ("arm64", "aarch64") else "linux_amd64"], "Linux"
    sys.exit(f"Нет сборки wacli для {sys.platform} {platform.machine()}")


def postavit(versiya=None):
    os_, varianty, nazvanie = sistema()
    print(f"Система: {nazvanie}", flush=True)
    for repo in ISTOCHNIKI:
        v = versiya or poslednyaya(repo)
        if not v:
            continue
        try:
            summy = skachat(f"https://github.com/{repo}/releases/download/v{v}/checksums.txt").decode()
        except Exception:
            continue
        for var in varianty:
            for ext in (".zip", ".tar.gz"):
                arkhiv = f"wacli_{v}_{var}{ext}"
                if arkhiv not in summy:
                    continue
                print(f"Скачиваю {arkhiv} из {repo} …", flush=True)
                dannye = skachat(f"https://github.com/{repo}/releases/download/v{v}/{arkhiv}")
                ozhidaetsya = next((s.split()[0] for s in summy.splitlines() if s.strip().endswith(arkhiv)), None)
                fakt = hashlib.sha256(dannye).hexdigest()
                if ozhidaetsya != fakt:
                    sys.exit(f"Контрольная сумма не сошлась ({arkhiv}): файл не установлен.")
                BIN_DIR.mkdir(parents=True, exist_ok=True)
                vremenny = TSEL.with_suffix(".novyy")
                if ext == ".zip":
                    with zipfile.ZipFile(io.BytesIO(dannye)) as z:
                        vremenny.write_bytes(z.read(next(n for n in z.namelist() if n.endswith(IMYA_BIN))))
                else:
                    with tarfile.open(fileobj=io.BytesIO(dannye), mode="r:gz") as t:
                        chlen = next(x for x in t.getmembers() if x.name.endswith(IMYA_BIN))
                        vremenny.write_bytes(t.extractfile(chlen).read())
                if os_ != "windows":
                    vremenny.chmod(0o755)
                vremenny.replace(TSEL)
                print(f"Готово: wacli {v} ({var}, из {repo}), контрольная сумма сошлась.")
                return v
    sys.exit("Не нашёл подходящую сборку wacli. Проверьте интернет и запустите ещё раз.")


def main():
    a = sys.argv[1:]
    if "--proverit" in a:
        print(f"Стоит: {ustanovlennaya() or 'нет'} · последняя: {poslednyaya(ISTOCHNIKI[0]) or poslednyaya(ISTOCHNIKI[1]) or '?'}")
        return
    v = next((x.lstrip("v") for x in a if not x.startswith("-")), None)
    postavit(v)
    if not v:
        print("Дальше: python SKRIPTY/wa.py vhod")


if __name__ == "__main__":
    main()
