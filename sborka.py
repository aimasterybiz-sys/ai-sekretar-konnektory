"""Собрать архивы для выпуска на GitHub: konnektory.zip, WhatsApp-Claude.zip, pochta-konnektor.zip.

  python sborka.py [папка для архивов, по умолчанию dist]

konnektory.zip — одно обновление для ученика: внутри obnovit.py, исправления, проверка и оба коннектора.
"""
import sys
import zipfile
from pathlib import Path

KOREN = Path(__file__).resolve().parent
for _s in (sys.stdout, sys.stderr):
    _s.reconfigure(encoding="utf-8", errors="replace")
LISHNEE = ("__pycache__", ".DS_Store", ".pyc")


def fayly(papka):
    return sorted(f for f in papka.rglob("*") if f.is_file() and not any(x in str(f) for x in LISHNEE))


def upakovat(arkhiv, chasti):
    """chasti: [(путь на диске, путь внутри архива)] — папки раскрываются целиком."""
    with zipfile.ZipFile(arkhiv, "w", zipfile.ZIP_DEFLATED) as z:
        for istochnik, vnutri in chasti:
            if istochnik.is_dir():
                for f in fayly(istochnik):
                    z.write(f, f"{vnutri}/{f.relative_to(istochnik).as_posix()}")
            else:
                z.write(istochnik, vnutri)
    return arkhiv


def main():
    dist = Path(sys.argv[1]) if len(sys.argv) > 1 else KOREN / "dist"
    dist.mkdir(parents=True, exist_ok=True)
    o = KOREN / "obnovlenie"
    gotovo = [
        upakovat(dist / "konnektory.zip", [
            (o / "obnovit.py", "konnektory/obnovit.py"), (o / "pravki.py", "konnektory/pravki.py"),
            (o / "proverka.py", "konnektory/proverka.py"), (KOREN / "VERSIYA", "konnektory/VERSIYA"),
            (KOREN / "whatsapp-claude", "konnektory/whatsapp-claude"),
            (KOREN / "pochta-konnektor", "konnektory/pochta-konnektor"),
        ]),
        upakovat(dist / "WhatsApp-Claude.zip", [(KOREN / "whatsapp-claude", "WhatsApp-Claude")]),
        upakovat(dist / "pochta-konnektor.zip", [(KOREN / "pochta-konnektor", "pochta-konnektor")]),
    ]
    for a in gotovo:
        print(f"{a.name}: {a.stat().st_size // 1024} КБ")


if __name__ == "__main__":
    main()
