"""Одно обновление «Обнови коннекторы секретаря» — как у ученика на Windows и Mac."""
import json
from pathlib import Path

import pytest
import py_compile

from conftest import KOREN, sekretar, zapustit

OBNOVIT = KOREN / "obnovlenie" / "obnovit.py"
PRAVILA = {"mcp__whatsapp__whatsapp_otpravit", "mcp__messendzhery__whatsapp_otpravit",
           "mcp__messendzhery__telegram_otpravit", "Bash(*otpravit*)", "PowerShell(*otpravit*)"}


def tekst(f):
    return f.read_text(encoding="utf-8")


def test_obnovlyaet_vse(dom):
    sek, wa = sekretar(dom), dom / "WhatsApp-Claude"
    kod, vyvod = zapustit(OBNOVIT, home=dom, cwd=sek)
    assert kod == 0, vyvod
    assert "ОБНОВЛЕНИЕ КОННЕКТОРОВ" in vyvod and "ГОТОВО" in vyvod and "Полностью закройте Claude" in vyvod
    assert "ПРОВЕРКА КОННЕКТОРОВ" in vyvod  # в конце сразу показана проверка
    # исправления Windows — и в секретаре, и в «WhatsApp в Claude»
    for f in (sek / "SKRIPTY" / "wa.py", wa / "SKRIPTY" / "wa.py"):
        assert "t.year < 1971" in tekst(f) and tekst(f).count("**BEZ_OKNA") == 2 and "CHUZHOY_VKHOD" in tekst(f)
        assert "\r\n" not in f.read_bytes().decode("utf-8")  # переводы строк как в Unix и на Windows
    # отправка всегда с вопросом «Разрешить?»
    assert tekst(sek / "SKRIPTY" / "mcp_messendzhery.py").count("meta=VSEGDA_SPRASHIVAT") == 2
    assert tekst(wa / "SKRIPTY" / "mcp_whatsapp.py").count("meta=VSEGDA_SPRASHIVAT") == 1
    nastr = json.loads(tekst(dom / ".claude" / "settings.json"))
    assert PRAVILA <= set(nastr["permissions"]["ask"])
    # почта
    assert (sek / "SKRIPTY" / "pochta.py").exists() and not (sek / "SKRIPTY" / "pochta_imap.py").exists()
    assert 'zapustit("pochta.py")' in tekst(sek / "SKRIPTY" / "sbor.py")
    assert "pochta.py otpravit" in tekst(sek / ".claude" / "skills" / "skill-publikatsiya" / "SKILL.md")
    assert "keyring" in tekst(sek / "SKRIPTY" / "requirements.txt")
    # «Проверь коннекторы» и версия
    assert (sek / "SKRIPTY" / "proverka.py").exists() and "proverka.py" in tekst(sek / "CLAUDE.md")
    assert tekst(sek / "NASTROYKI" / "versiya-konnektorov.txt").strip() == tekst(KOREN / "VERSIYA").strip()
    # прежние версии сохранены
    assert list(sek.glob("_do-obnovleniya-*")) and list(sek.glob("_do-pochty-*")) and list(wa.glob("_do-obnovleniya-*"))
    for f in list((sek / "SKRIPTY").glob("*.py")) + list((wa / "SKRIPTY").glob("*.py")):
        py_compile.compile(str(f), doraise=True)


def test_povtornyy_zapusk_nichego_ne_lomaet(dom):
    sek = sekretar(dom)
    zapustit(OBNOVIT, home=dom, cwd=sek)
    snimok = {f: f.read_bytes() for f in sek.rglob("*") if f.is_file() and "_do-" not in str(f)
              and "versiya" not in f.name and "obnovlenie-" not in f.name and "__pycache__" not in str(f)}
    kod, vyvod = zapustit(OBNOVIT, home=dom, cwd=sek)
    assert kod == 0, vyvod
    assert "Полностью закройте Claude" not in vyvod and "Откройте новый чат" in vyvod
    for f, bayty in snimok.items():
        assert f.read_bytes() == bayty, f"второй запуск изменил {f}"
    assert tekst(sek / "CLAUDE.md").count("proverka.py") == 1


def test_nakhodit_sekretarya_sam(dom):
    """Claude открыт не в папке секретаря — обновление само находит её в домашней папке."""
    kod, vyvod = zapustit(OBNOVIT, home=dom, cwd=dom)
    assert kod == 0, vyvod
    assert "AI SYSTEM" in vyvod and (sekretar(dom) / "SKRIPTY" / "pochta.py").exists()


def test_tolko_whatsapp_bez_sekretarya(dom, tmp_path):
    import shutil
    shutil.rmtree(dom / "AI SYSTEM")
    kod, vyvod = zapustit(OBNOVIT, home=dom, cwd=dom)
    assert kod == 0, vyvod
    assert "t.year < 1971" in tekst(dom / "WhatsApp-Claude" / "SKRIPTY" / "wa.py")
    assert PRAVILA <= set(json.loads(tekst(dom / ".claude" / "settings.json"))["permissions"]["ask"])


def test_svoi_nastroyki_cheloveka_sokhranyayutsya(dom):
    (dom / ".claude").mkdir()
    (dom / ".claude" / "settings.json").write_text(json.dumps(
        {"theme": "dark", "permissions": {"allow": ["Bash(ls)"], "ask": ["Bash(rm *)"]}}), encoding="utf-8")
    kod, vyvod = zapustit(OBNOVIT, home=dom, cwd=sekretar(dom))
    assert kod == 0, vyvod
    nastr = json.loads(tekst(dom / ".claude" / "settings.json"))
    assert nastr["theme"] == "dark" and nastr["permissions"]["allow"] == ["Bash(ls)"]
    assert "Bash(rm *)" in nastr["permissions"]["ask"] and PRAVILA <= set(nastr["permissions"]["ask"])
    assert list((dom / ".claude").glob("settings.do-obnovleniya-*.json"))


def test_slomannyy_settings_ne_valit_obnovlenie(dom):
    (dom / ".claude").mkdir()
    (dom / ".claude" / "settings.json").write_text("{ это не json", encoding="utf-8")
    kod, vyvod = zapustit(OBNOVIT, home=dom, cwd=sekretar(dom))
    assert kod == 0, vyvod
    assert "не читается" in vyvod
    assert tekst(dom / ".claude" / "settings.json") == "{ это не json"


def test_ustanovshchik_pochty_otdelno_v_kodirovke_windows(dom):
    kod, vyvod = zapustit(KOREN / "pochta-konnektor" / "ustanovit.py", sekretar(dom), home=dom, cwd=dom)
    assert kod == 0, vyvod
    assert "Коннектор почты установлен" in vyvod and "✓" in vyvod


def test_fayl_ne_v_utf8_ne_lomaet_obnovlenie(dom):
    """CLAUDE.md сохранён старым Блокнотом в cp1251 — обновление доводится до конца, файл не тронут."""
    sek = sekretar(dom)
    bayty = tekst(sek / "CLAUDE.md").encode("cp1251")
    (sek / "CLAUDE.md").write_bytes(bayty)
    kod, vyvod = zapustit(OBNOVIT, home=dom, cwd=sek)
    assert kod == 0, vyvod
    assert "ГОТОВО" in vyvod and "! CLAUDE.md не в кодировке UTF-8" in vyvod
    assert (sek / "CLAUDE.md").read_bytes() == bayty
    assert (sek / "SKRIPTY" / "pochta.py").exists() and "t.year < 1971" in tekst(sek / "SKRIPTY" / "wa.py")
    assert PRAVILA <= set(json.loads(tekst(dom / ".claude" / "settings.json"))["permissions"]["ask"])


def test_ruchnaya_pravka_wa_py_zamenyaetsya_svezhim(dom):
    """Как у Насти: wa.py правили руками не байт в байт — обновление ставит свежий файл целиком, без круга."""
    sek = sekretar(dom)
    f = sek / "SKRIPTY" / "wa.py"
    f.write_text(tekst(f).replace('QR = NASTROYKI / "qr-whatsapp.png"\n', 'QR = NASTROYKI / "qr.png"  # моя правка\n'),
                 encoding="utf-8")
    kod, vyvod = zapustit(OBNOVIT, home=dom, cwd=sek)
    assert kod == 0, vyvod
    assert "часть исправлений не применена" not in vyvod and "исправлены ошибки Windows" in vyvod
    t = tekst(f)
    assert "BEZ_OKNA" in t and "CHUZHOY_VKHOD" in t and '"com.sekretar.wacli"' in t and '"SekretarWA"' in t
    assert "моя правка" in (next(sek.glob("_do-obnovleniya-*")) / "wa.py").read_text(encoding="utf-8")
    kod, vyvod = zapustit(OBNOVIT, home=dom, cwd=sek)
    assert "Всё уже свежее" in vyvod or "Откройте новый чат" in vyvod


def test_slomannyy_wa_py_tozhe_zamenyaetsya(dom):
    sek = sekretar(dom)
    f = sek / "SKRIPTY" / "wa.py"
    f.write_text(tekst(f).replace("def vremya_iz(z):\n", "def vremya_iz(z):\n  x = 1\n", 1), encoding="utf-8")
    kod, vyvod = zapustit(OBNOVIT, home=dom, cwd=sek)
    assert kod == 0, vyvod
    compile(tekst(f), str(f), "exec")
    assert "t.year < 1971" in tekst(f)


def test_proverka_vidit_staruyu_versiyu_i_novuyu(dom):
    import shutil
    sek = sekretar(dom)
    shutil.copy2(KOREN / "obnovlenie" / "proverka.py", sek / "SKRIPTY" / "proverka.py")
    kod, vyvod = zapustit(sek / "SKRIPTY" / "proverka.py", home=dom, cwd=sek)
    assert kod == 0, vyvod
    assert "✗ wa.py старой версии" in vyvod and "✗ Не везде Claude спрашивает" in vyvod
    zapustit(OBNOVIT, home=dom, cwd=sek)
    kod, vyvod = zapustit(sek / "SKRIPTY" / "proverka.py", home=dom, cwd=sek)
    assert kod == 0, vyvod
    assert "старой версии" not in vyvod and "✓ Перед каждой отправкой Claude спрашивает" in vyvod


def test_novyy_fayl_v_whatsapp_claude_ne_valit_obnovlenie(dom):
    """У ученика нет файла, который есть в свежем «WhatsApp в Claude» (так будет при следующем выпуске)."""
    (dom / "WhatsApp-Claude" / "SKRIPTY" / "golos.py").unlink()
    kod, vyvod = zapustit(OBNOVIT, home=dom, cwd=sekretar(dom))
    assert kod == 0, vyvod
    assert (dom / "WhatsApp-Claude" / "SKRIPTY" / "golos.py").exists() and "ГОТОВО" in vyvod


def test_strannye_nastroyki_claude_ne_valyat_obnovlenie(dom):
    (dom / ".claude").mkdir()
    (dom / ".claude" / "settings.json").write_text('{"permissions": {"ask": "Bash(rm *)"}}', encoding="utf-8")
    kod, vyvod = zapustit(OBNOVIT, home=dom, cwd=sekretar(dom))
    assert kod == 0, vyvod
    assert "устроен неожиданно" in vyvod and "ГОТОВО" in vyvod
    assert tekst(dom / ".claude" / "settings.json") == '{"permissions": {"ask": "Bash(rm *)"}}'


def test_sbor_vidit_whatsapp_iz_whatsapp_claude(dom):
    zapustit(OBNOVIT, home=dom, cwd=sekretar(dom))
    s = tekst(sekretar(dom) / "SKRIPTY" / "sbor.py")
    assert '"WhatsApp-Claude"' in s and 'zapustit("pochta.py")' in s
    compile(s, "sbor.py", "exec")


def test_iz_vremennoy_papki_s_putem(dom, tmp_path):
    """Claude запускает обновление из временной папки и передаёт путь к секретарю — всё находится."""
    vremennaya = tmp_path / "temp"
    vremennaya.mkdir()
    kod, vyvod = zapustit(OBNOVIT, sekretar(dom), home=dom, cwd=vremennaya)
    assert kod == 0, vyvod
    assert (sekretar(dom) / "SKRIPTY" / "pochta.py").exists()


def test_sekretar_ne_nayden_no_whatsapp_est_chestno_skazano(dom, tmp_path):
    import shutil
    glubzhe = dom / "OneDrive" / "Документы" / "Курс" / "AI SYSTEM"
    glubzhe.mkdir(parents=True)
    shutil.move(str(sekretar(dom)), str(glubzhe / "02_sekretar"))
    vremennaya = tmp_path / "temp"
    vremennaya.mkdir()
    kod, vyvod = zapustit(OBNOVIT, home=dom, cwd=vremennaya)
    assert kod == 0, vyvod
    assert "Папку секретаря не нашёл" in vyvod and "python obnovit.py" in vyvod


def test_staryy_python_ponyatnoe_soobshchenie():
    import shutil, subprocess
    staryy = shutil.which("python3.9") or ("/usr/bin/python3" if Path("/usr/bin/python3").exists() else None)
    if not staryy:
        pytest.skip("нет Python 3.9 на этой машине")
    v = subprocess.run([staryy, "-c", "import sys; print(sys.version_info[:2] < (3, 10))"], capture_output=True, text=True)
    if v.stdout.strip() != "True":
        pytest.skip("системный python3 не старый")
    r = subprocess.run([staryy, str(OBNOVIT)], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode != 0 and "слишком старый" in r.stderr and "Traceback" not in r.stderr
