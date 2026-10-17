"""Почта: поиск серверов, сбор и отправка на поддельном сервере, страница подключения."""
import shutil
import sys

from conftest import KOREN, OBRAZTSY, kod_python, zapustit

POCHTA = KOREN / "pochta-konnektor" / "fayly" / "SKRIPTY"
STSENARII = KOREN / "tests" / "stsenarii"


def sekretar_s_pochtoy(tmp_path):
    sek = tmp_path / "02_sekretar"
    shutil.copytree(OBRAZTSY / "02_sekretar", sek)
    for f in POCHTA.glob("*.py"):
        shutil.copy2(f, sek / "SKRIPTY" / f.name)
    (sek / "02_ZNANIYA").mkdir()
    return sek


def test_servery_bez_interneta():
    kod, vyvod = kod_python(r'''
import pochta_servery as s
for a in ["anna@gmail.com", "x@hotmail.de", "z@icloud.com", "a@yahoo.co.uk", "b@ukr.net", "e@proton.me", "g@zoho.eu"]:
    r = s.opredelit(a); print(a, r["provayder"], r["imap"]["host"], r["vkhod"])
print("iua", s.opredelit("c@i.ua").get("bez_imap"))
print("plokho", "oshibka" in s.opredelit("bad-address"))
xml = b"""<clientConfig><emailProvider id="x"><incomingServer type="imap"><hostname>imap.x.lv</hostname><port>993</port>
<socketType>SSL</socketType><username>%EMAILLOCALPART%</username><authentication>password-cleartext</authentication></incomingServer>
<outgoingServer type="smtp"><hostname>smtp.x.lv</hostname><port>587</port><socketType>STARTTLS</socketType>
<username>%EMAILADDRESS%</username></outgoingServer></emailProvider></clientConfig>"""
r = s.iz_xml(xml, "anna@x.lv"); print("xml", r["imap"]["host"], r["imap"]["login"], r["smtp"]["port"], r["smtp"]["login"])
''', POCHTA)
    assert kod == 0, vyvod
    for ozhidayu in ("anna@gmail.com gmail imap.gmail.com parol", "x@hotmail.de outlook outlook.office365.com microsoft",
                     "b@ukr.net ukrnet imap.ukr.net parol", "e@proton.me proton 127.0.0.1 parol",
                     "iua True", "plokho True", "xml imap.x.lv anna 587 anna@x.lv"):
        assert ozhidayu in vyvod, vyvod


def test_sbor_i_otpravka_na_poddelnom_servere(tmp_path):
    sek = sekretar_s_pochtoy(tmp_path)
    kod, vyvod = zapustit(STSENARII / "pochta_sbor.py", sek / "SKRIPTY", home=tmp_path, cwd=tmp_path)
    assert kod == 0, vyvod
    assert "✗" not in vyvod, vyvod
    assert vyvod.count("✓") >= 28, vyvod


def test_stranitsa_podklyucheniya(tmp_path):
    sek = sekretar_s_pochtoy(tmp_path)
    kod, vyvod = zapustit(STSENARII / "pochta_forma.py", sek / "SKRIPTY", home=tmp_path, cwd=tmp_path)
    assert kod == 0, vyvod
    assert "✗" not in vyvod, vyvod
    assert vyvod.count("✓") >= 15, vyvod


def test_spisok_i_doctor_v_kodirovke_windows(tmp_path):
    sek = sekretar_s_pochtoy(tmp_path)
    kod, vyvod = zapustit(sek / "SKRIPTY" / "pochta.py", "--spisok", home=tmp_path, cwd=sek / "SKRIPTY")
    assert kod == 0 and "Почта не подключена" in vyvod, vyvod
    kod, vyvod = zapustit(sek / "SKRIPTY" / "pochta.py", "doctor", home=tmp_path, cwd=sek / "SKRIPTY")
    assert kod == 0 and "Папка секретаря" in vyvod, vyvod
    assert sys.platform != "win32" or "Traceback" not in vyvod
