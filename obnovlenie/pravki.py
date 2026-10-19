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

CHUZHOY_VKHOD = '''STORE = NASTROYKI / "wacli"
# «WhatsApp в Claude» уже стоит в домашней папке — берём его вход и переписку, второй раз в WhatsApp не входим
_WA_CLAUDE = Path.home() / "WhatsApp-Claude"
_CHUZHOY_STORE = _WA_CLAUDE / "NASTROYKI" / "wacli"
CHUZHOY_VKHOD = (not STORE.exists() and ROOT.resolve() != _WA_CLAUDE.resolve()
                 and _CHUZHOY_STORE.is_dir() and any(_CHUZHOY_STORE.iterdir()))
if CHUZHOY_VKHOD:
    STORE = _CHUZHOY_STORE
    if not BIN.exists():
        BIN = _WA_CLAUDE / "SKRIPTY" / "bin" / BIN.name
'''

UZHE_VOSHLI = '''    if CHUZHOY_VKHOD and (wacli("auth", "status", check=False) or {}).get("authenticated"):
        print("Вход в WhatsApp уже есть — из «WhatsApp в Claude». Второй раз входить не нужно.")
        return
'''

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
        # секретарь пользуется входом «WhatsApp в Claude», если свой вход не делали
        ("CHUZHOY_VKHOD", [
            ('STORE = NASTROYKI / "wacli"\n', CHUZHOY_VKHOD),
            ('def vhod_po_nomeru(nomer):\n'
             '    """Вход без QR: WhatsApp покажет поле для 8-значного кода, который печатает wacli."""\n'
             '    STORE.mkdir(parents=True, exist_ok=True)\n',
             'def vhod_po_nomeru(nomer):\n'
             '    """Вход без QR: WhatsApp покажет поле для 8-значного кода, который печатает wacli."""\n'
             + UZHE_VOSHLI + '    STORE.mkdir(parents=True, exist_ok=True)\n'),
            ('def vhod():\n    STORE.mkdir(parents=True, exist_ok=True)\n',
             'def vhod():\n' + UZHE_VOSHLI + '    STORE.mkdir(parents=True, exist_ok=True)\n'),
            ('def sluzhba(deystvie):\n    STORE.mkdir(parents=True, exist_ok=True)\n',
             'def sluzhba(deystvie):\n'
             '    if CHUZHOY_VKHOD:\n'
             '        print("Служба: общая с «WhatsApp в Claude» (~/WhatsApp-Claude)" if deystvie == "--status"\n'
             '              else "Вход и служба уже есть в «WhatsApp в Claude» — вторая служба не нужна.")\n'
             '        return\n'
             '    STORE.mkdir(parents=True, exist_ok=True)\n'),
            ('''    print(f"Программа wacli: {wa_ustanovka.ustanovlennaya() or 'не установлена'}")\n''',
             '''    if CHUZHOY_VKHOD:\n'''
             '''        print("Вход, программа wacli и переписка: из «WhatsApp в Claude» (~/WhatsApp-Claude), общие с секретарём")\n'''
             '''    else:\n'''
             '''        print(f"Программа wacli: {wa_ustanovka.ustanovlennaya() or 'не установлена'}")\n'''),
        ]),
    ],
    "sbor.py": [
        # общий сбор видит программу WhatsApp и в «WhatsApp в Claude», а не только в папке секретаря
        ("WhatsApp-Claude", [
            ('        est_wacli = (ZDES / "bin" / ("wacli.exe" if os.name == "nt" else "wacli")).exists()\n',
             '        imya_wacli = "wacli.exe" if os.name == "nt" else "wacli"\n'
             '        est_wacli = ((ZDES / "bin" / imya_wacli).exists()\n'
             '                     or (Path.home() / "WhatsApp-Claude" / "SKRIPTY" / "bin" / imya_wacli).exists())\n'),
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


def chitat(fayl):
    """Текст файла в UTF-8 (и с BOM от Блокнота). Файла нет или он в другой кодировке — None: его не трогаем."""
    fayl = Path(fayl)
    if not fayl.is_file():
        return None
    try:
        return fayl.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return None


def pisat(fayl, tekst):
    """Записать в UTF-8 с переводами строк как в Unix — на Windows иначе файлы получают CRLF."""
    with open(fayl, "w", encoding="utf-8", newline="\n") as f:
        f.write(tekst)


def primenit(fayl):
    """Применить правки к файлу. Возвращает список строк-итогов (пустой — менять было нечего)."""
    fayl = Path(fayl)
    gruppy = PRAVKI.get(fayl.name)
    if not gruppy or not fayl.exists():
        return []
    tekst = chitat(fayl)
    if tekst is None:
        return [f"! {fayl.name}: файл не в кодировке UTF-8 — не тронут (сохраните его в UTF-8 и повторите)"]
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
        pisat(fayl, novyy)
    return itog
