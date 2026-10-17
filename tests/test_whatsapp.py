"""WhatsApp: даты «0001-01-01» не роняют список чатов, чёрного окна нет, отправка всегда с вопросом."""
import shutil
import sys

import pytest

from conftest import KOREN, OBRAZTSY, kod_python

WA = KOREN / "whatsapp-claude" / "SKRIPTY"

CHATY = r'''
import json, wa
wa.wacli = lambda *a, **k: [
    {"jid": "1@s.whatsapp.net", "name": "Без сообщений", "last_message_ts": "0001-01-01T00:00:00Z"},
    {"jid": "2@g.us", "name": "Группа", "last_message_ts": "2026-10-16T17:00:00Z"},
    {"jid": "3@s.whatsapp.net", "name": "Числом", "last_message_ts": 1792160000},
    {"jid": "4@s.whatsapp.net", "name": "Ноль", "last_message_ts": 0},
]
ch = wa.chaty_zhivye()
print(json.dumps([[c["imya"], c["t"] is None] for c in ch], ensure_ascii=False))
print("ZERO", wa.vremya_iz("0001-01-01T00:00:00Z"), wa.vremya_iz(-5), wa.vremya_iz("2026-10-16T17:00:00Z") is not None)
print("OKNO", wa.BEZ_OKNA)
'''


def test_nulevye_daty_ne_valyat_spisok_chatov():
    kod, vyvod = kod_python(CHATY, WA)
    assert kod == 0, vyvod
    assert '["Без сообщений", true]' in vyvod and '["Группа", false]' in vyvod and '["Ноль", true]' in vyvod
    assert "ZERO None None True" in vyvod


def test_na_windows_wacli_zapuskaetsya_bez_okna():
    kod, vyvod = kod_python(CHATY, WA)
    assert kod == 0, vyvod
    if sys.platform == "win32":
        assert "OKNO {'creationflags': 134217728}" in vyvod
    else:
        assert "OKNO {}" in vyvod


@pytest.mark.skipif(sys.platform != "win32", reason="ошибка бывает только на Windows")
@pytest.mark.xfail(strict=False, reason="показывает исходную ошибку: старый код падает на Windows")
def test_staryy_kod_padal_na_windows(tmp_path):
    shutil.copytree(OBRAZTSY / "WhatsApp-Claude" / "SKRIPTY", tmp_path / "S")
    kod, vyvod = kod_python(CHATY, tmp_path / "S")
    assert kod != 0 and ("OSError" in vyvod or "OverflowError" in vyvod)


METKI = r'''
import asyncio, json, sys
sys.path.insert(0, ".")
import {modul} as m
async def go():
    for t in await m.server.list_tools():
        d = t.model_dump(by_alias=True, exclude_none=True)
        print(t.name, json.dumps(d.get("_meta")))
asyncio.run(go())
'''


def test_otpravka_whatsapp_vsegda_sprashivaet():
    kod, vyvod = kod_python(METKI.replace("{modul}", "mcp_whatsapp"), WA)
    assert kod == 0, vyvod
    stroki = dict(s.split(" ", 1) for s in vyvod.strip().splitlines())
    assert stroki["whatsapp_otpravit"] == '{"anthropic/requiresUserInteraction": true}'
    assert all(v == "null" for k, v in stroki.items() if k != "whatsapp_otpravit")


def test_messendzhery_sekretarya_posle_pravok(tmp_path):
    sys.path.insert(0, str(KOREN / "obnovlenie"))
    import pravki
    shutil.copytree(OBRAZTSY / "02_sekretar" / "SKRIPTY", tmp_path / "S")
    for f in (tmp_path / "S").glob("*.py"):
        pravki.primenit(f)
    kod, vyvod = kod_python(METKI.replace("{modul}", "mcp_messendzhery"), tmp_path / "S")
    assert kod == 0, vyvod
    stroki = dict(s.split(" ", 1) for s in vyvod.strip().splitlines())
    for t in ("whatsapp_otpravit", "telegram_otpravit"):
        assert stroki[t] == '{"anthropic/requiresUserInteraction": true}'
    assert sum(v != "null" for v in stroki.values()) == 2
