"""Точечные исправления кода коннекторов — одинаковые для WhatsApp-Claude и для копий внутри секретаря.

Каждая группа правок: признак «уже исправлено» и список замен «было → стало». Группа применяется целиком
или не применяется вовсе (если какого-то места нет — файл другой версии, его не трогаем и говорим об этом).
Повторный запуск безопасен.
"""
from pathlib import Path

UTF8 = '''# Консоль Windows по умолчанию не печатает кириллицу, «✓» и эмодзи — переключаем вывод на UTF-8
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
'''

VSEGDA_SPRASHIVAT = ('# Отправка всегда ждёт кнопку «Разрешить» от человека — в любом режиме Claude, даже в «Авто»\n'
                     'VSEGDA_SPRASHIVAT = {"anthropic/requiresUserInteraction": True}\n')

PISAT = ("PISAT = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, "
         "openWorldHint=True)\n")

# имя файла → [(признак, [(было, стало), …]), …]
PRAVKI = {
    "wa.py": [
        # даты «0001-01-01» у чатов без сообщений: на Windows перевод такой даты в местное время падает
        ("t.year < 1971", [
            ("        return datetime.fromtimestamp(z)\n",
             "        return datetime.fromtimestamp(z) if z > 0 else None\n"),
            ("    return t.astimezone().replace(tzinfo=None) if t.tzinfo else t\n",
             "    if t.year < 1971:  # «нулевая» дата wacli у чатов без сообщений\n"
             "        return None\n"
             "    try:\n"
             "        return t.astimezone().replace(tzinfo=None) if t.tzinfo else t\n"
             "    except (OverflowError, OSError, ValueError):\n"
             "        return None\n"),
        ]),
        # служба без окна (pythonw) запускает консольную wacli.exe — без флага Windows открывает чёрное окно
        ("BEZ_OKNA = ", [
            ('QR = NASTROYKI / "qr-whatsapp.png"\n',
             'QR = NASTROYKI / "qr-whatsapp.png"\n'
             '# Windows: запускать wacli.exe без чёрного окна консоли\n'
             'BEZ_OKNA = {"creationflags": 0x08000000} if os.name == "nt" else {}\n'),
            ('errors="replace", timeout=timeout)', 'errors="replace", timeout=timeout, **BEZ_OKNA)'),
            ('errors="replace", timeout=600)', 'errors="replace", timeout=600, **BEZ_OKNA)'),
        ]),
    ],
    "mcp_whatsapp.py": [
        ("VSEGDA_SPRASHIVAT", [
            (PISAT, PISAT + VSEGDA_SPRASHIVAT),
            ("@server.tool(annotations=PISAT)\ndef whatsapp_otpravit",
             "@server.tool(annotations=PISAT, meta=VSEGDA_SPRASHIVAT)\ndef whatsapp_otpravit"),
        ]),
    ],
    "mcp_messendzhery.py": [
        ("VSEGDA_SPRASHIVAT", [
            (PISAT, PISAT + VSEGDA_SPRASHIVAT),
            ("@server.tool(annotations=PISAT)\ndef whatsapp_otpravit",
             "@server.tool(annotations=PISAT, meta=VSEGDA_SPRASHIVAT)\ndef whatsapp_otpravit"),
            ("@server.tool(annotations=PISAT)\nasync def telegram_otpravit",
             "@server.tool(annotations=PISAT, meta=VSEGDA_SPRASHIVAT)\nasync def telegram_otpravit"),
        ]),
    ],
    "wa_ustanovka.py": [
        ("_s.reconfigure", [("from pathlib import Path\n", "from pathlib import Path\n\n" + UTF8)]),
    ],
    "mcp_podklyuchit.py": [
        ("_s.reconfigure", [("from pathlib import Path\n", "from pathlib import Path\n\n" + UTF8)]),
    ],
}


def primenit(fayl):
    """Применить правки к файлу. Возвращает список строк-итогов (пустой — менять было нечего)."""
    fayl = Path(fayl)
    gruppy = PRAVKI.get(fayl.name)
    if not gruppy or not fayl.exists():
        return []
    tekst = fayl.read_text(encoding="utf-8")
    novyy, itog = tekst, []
    for priznak, zameny in gruppy:
        if priznak in novyy:
            continue
        if all(novyy.count(bylo) == 1 for bylo, _ in zameny):
            for bylo, stalo in zameny:
                novyy = novyy.replace(bylo, stalo, 1)
            itog.append(f"✓ {fayl.name}: исправлено ({priznak.strip()})")
        else:
            itog.append(f"! {fayl.name}: другая версия файла — исправление «{priznak.strip()}» не применено")
    if novyy != tekst:
        fayl.write_text(novyy, encoding="utf-8")
    return itog
