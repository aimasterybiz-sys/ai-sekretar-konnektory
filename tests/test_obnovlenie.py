"""Одно обновление «Обнови коннекторы секретаря» — как у ученика на Windows и Mac."""
import json
import py_compile

from conftest import KOREN, sekretar, zapustit

OBNOVIT = KOREN / "obnovlenie" / "obnovit.py"
PRAVILA = {"mcp__whatsapp__whatsapp_otpravit", "mcp__messendzhery__whatsapp_otpravit",
           "mcp__messendzhery__telegram_otpravit"} | {
    f"{sh}(*{sk} otpravit*)" if sk != "tg_otpravit.py" else f"{sh}(*tg_otpravit.py*)"
    for sh in ("Bash", "PowerShell") for sk in ("pochta.py", "wa.py", "tg_otpravit.py")}


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


def test_chuzhaya_versiya_wa_py_ne_vydaetsya_za_ispravlennuyu(dom):
    sek = sekretar(dom)
    f = sek / "SKRIPTY" / "wa.py"
    f.write_text(tekst(f).replace('QR = NASTROYKI / "qr-whatsapp.png"\n', 'QR = NASTROYKI / "qr.png"\n'), encoding="utf-8")
    kod, vyvod = zapustit(OBNOVIT, home=dom, cwd=sek)
    assert kod == 0, vyvod
    assert "! WhatsApp: часть исправлений не применена" in vyvod
    assert "чёрное окно" not in vyvod
    assert "BEZ_OKNA" not in tekst(f) and "t.year < 1971" in tekst(f)  # что можно — исправлено, остальное честно нет


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
