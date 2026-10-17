"""Архивы для выпуска: правильное содержимое, и обновление работает прямо из скачанного архива."""
import json
import zipfile

from conftest import KOREN, sekretar, zapustit


def test_arkhivy_i_obnovlenie_iz_arkhiva(tmp_path, dom):
    dist = tmp_path / "dist"
    kod, vyvod = zapustit(KOREN / "sborka.py", dist, home=tmp_path, cwd=KOREN)
    assert kod == 0, vyvod
    k = zipfile.ZipFile(dist / "konnektory.zip").namelist()
    for nuzhno in ("konnektory/obnovit.py", "konnektory/pravki.py", "konnektory/proverka.py", "konnektory/VERSIYA",
                   "konnektory/whatsapp-claude/SKRIPTY/wa.py", "konnektory/pochta-konnektor/ustanovit.py",
                   "konnektory/pochta-konnektor/fayly/SKRIPTY/pochta.py"):
        assert nuzhno in k
    assert not any("__pycache__" in n for n in k)
    w = zipfile.ZipFile(dist / "WhatsApp-Claude.zip")
    assert "t.year < 1971" in w.read("WhatsApp-Claude/SKRIPTY/wa.py").decode("utf-8")
    assert "WhatsApp-Claude/USTANOVKA.md" in w.namelist()
    assert "pochta-konnektor/ustanovit.py" in zipfile.ZipFile(dist / "pochta-konnektor.zip").namelist()
    # как у ученика: распаковать во временную папку и запустить obnovit.py оттуда
    zipfile.ZipFile(dist / "konnektory.zip").extractall(tmp_path / "skachano")
    kod, vyvod = zapustit(tmp_path / "skachano" / "konnektory" / "obnovit.py", home=dom, cwd=sekretar(dom))
    assert kod == 0, vyvod
    assert (sekretar(dom) / "SKRIPTY" / "pochta.py").exists()
    assert json.loads((dom / ".claude" / "settings.json").read_text(encoding="utf-8"))["permissions"]["ask"]
