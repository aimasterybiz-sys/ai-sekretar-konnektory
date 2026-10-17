"""Обновить коннекторы AI-секретаря: WhatsApp, Telegram, почта — одной командой. Mac и Windows.

  python obnovit.py [папка секретаря 02_sekretar]

Что делает:
1. Находит папку секретаря (указанную, текущую или в домашней папке) и коннектор «WhatsApp в Claude» (~/WhatsApp-Claude).
2. Ставит исправления для Windows, коннектор почты, проверку «Проверь коннекторы».
3. Включает правило: перед каждой отправкой сообщения или письма Claude спрашивает «Разрешить?».
4. Ставит недостающие библиотеки и показывает проверку всех коннекторов.
Прежние версии изменённых файлов сохраняются рядом (папки _do-obnovleniya-<дата>). Повторный запуск безопасен.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ZDES = Path(__file__).resolve().parent
# в скачанном архиве коннекторы лежат рядом с obnovit.py, в репозитории — уровнем выше
BAZA = ZDES if (ZDES / "pochta-konnektor").exists() else ZDES.parent
sys.path.insert(0, str(ZDES))
import pravki  # noqa: E402

VERSIYA = (BAZA / "VERSIYA").read_text(encoding="utf-8").strip() if (BAZA / "VERSIYA").exists() else "?"
METKA = datetime.now().strftime("%Y-%m-%d-%H%M%S")
# На Windows Claude Code работает в PowerShell, и правила для Bash его не касаются — поэтому оба набора
PRAVILA_SPRASHIVAT = ["mcp__whatsapp__whatsapp_otpravit", "mcp__messendzhery__whatsapp_otpravit",
                      "mcp__messendzhery__telegram_otpravit"] + [
    f"{shell}(*{skript} otpravit*)" if skript != "tg_otpravit.py" else f"{shell}(*tg_otpravit.py*)"
    for shell in ("Bash", "PowerShell") for skript in ("pochta.py", "wa.py", "tg_otpravit.py")]
STROKA_PROVERKI = ("- «Проверь коннекторы» — запусти `python SKRIPTY/proverka.py` (на Mac `python3`) и покажи отчёт "
                   "как есть, ничего не сокращая.")
BEZ_OKNA = {"creationflags": 0x08000000} if sys.platform == "win32" else {}
PROPUSK = {"Library", "AppData", "node_modules", "$Recycle.Bin", "Windows"}  # системные папки — не искать


def eto_sekretar(p):
    return (p / "CLAUDE.md").exists() and (p / "SKRIPTY" / "obshchee.py").exists()


def nayti_sekretarya(yavno):
    if yavno:
        p = Path(yavno).expanduser().resolve()
        return p if eto_sekretar(p) else None
    if eto_sekretar(Path.cwd()):
        return Path.cwd()
    kandidaty = []
    doma = Path.home()
    for koren, papki, _ in os.walk(doma):
        chasti = Path(koren).relative_to(doma).parts
        if len(chasti) >= 4:
            papki[:] = []
            continue
        papki[:] = [p for p in papki if p not in PROPUSK and not p.startswith((".", "_архив", "_do-"))]
        for imya in papki:
            if imya == "02_sekretar" and eto_sekretar(Path(koren) / imya):
                kandidaty.append(Path(koren) / imya)
    if not kandidaty:
        return None
    # рабочая папка — та, где уже есть вход в Telegram или подключённые ящики
    kandidaty.sort(key=lambda p: ((p / "NASTROYKI" / "secretary.session").exists(),
                                  (p / "NASTROYKI").stat().st_mtime if (p / "NASTROYKI").exists() else 0), reverse=True)
    if len(kandidaty) > 1:
        print("Нашёл несколько папок 02_sekretar, обновляю рабочую. Остальные: "
              + "; ".join(str(p) for p in kandidaty[1:]) + " — если нужна другая, откройте Claude в ней.", flush=True)
    return kandidaty[0]


def kopiya(fayl, rezerv):
    if fayl.exists():
        rezerv.mkdir(parents=True, exist_ok=True)
        tsel = rezerv / fayl.name
        if not tsel.exists():
            shutil.copy2(fayl, tsel)


def ispravit(papka, itog, rezerv):
    """Точечные исправления в SKRIPTY (копия файла — перед правкой). Возвращает True, если что-то поменялось."""
    pomenyal = False
    for f in sorted((papka / "SKRIPTY").glob("*.py")):
        if f.name not in pravki.PRAVKI:
            continue
        do = f.read_bytes()
        stroki = pravki.primenit(f)
        if f.read_bytes() != do:
            pomenyal = True
            rezerv.mkdir(parents=True, exist_ok=True)
            if not (rezerv / f.name).exists():
                (rezerv / f.name).write_bytes(do)
        itog += stroki
    return pomenyal


def obnovit_sekretarya(sek, itog):
    rezerv = sek / f"_do-obnovleniya-{METKA}"
    # почта (свой установщик: файлы, скиллы, правила)
    spec = importlib.util.spec_from_file_location("ustanovit_pochty", BAZA / "pochta-konnektor" / "ustanovit.py")
    ust = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ust)
    stroki, _ = ust.ustanovit(sek)
    itog += [s.replace("✓ ", "✓ почта: ", 1) if s.startswith("✓ ") else s for s in stroki]
    # исправления Windows и подтверждение отправки
    mcp_izmenen = ispravit(sek, itog, rezerv)
    # «Проверь коннекторы»
    istochnik, tsel = ZDES / "proverka.py", sek / "SKRIPTY" / "proverka.py"
    if pravki.chitat(tsel) != pravki.chitat(istochnik) if tsel.exists() else True:
        kopiya(tsel, rezerv)
        pravki.pisat(tsel, pravki.chitat(istochnik))
        itog.append("✓ проверка «Проверь коннекторы» поставлена")
    cl = sek / "CLAUDE.md"
    t = pravki.chitat(cl)
    if t is None:
        itog.append("! CLAUDE.md не в кодировке UTF-8 — фраза «Проверь коннекторы» в него не добавлена "
                    "(сохраните файл в UTF-8 и повторите обновление)")
    elif "proverka.py" not in t:
        kopiya(cl, rezerv)
        t = t.replace("## Команды\n", "## Команды\n" + STROKA_PROVERKI + "\n", 1) if "## Команды\n" in t \
            else t.rstrip("\n") + "\n\n## Команды\n" + STROKA_PROVERKI + "\n"
        pravki.pisat(cl, t)
        itog.append("✓ CLAUDE.md: фраза «Проверь коннекторы»")
    (sek / "NASTROYKI").mkdir(exist_ok=True)
    pravki.pisat(sek / "NASTROYKI" / "versiya-konnektorov.txt", VERSIYA + "\n")
    return mcp_izmenen


def obnovit_wa_claude(papka, itog):
    """Коннектор «WhatsApp в Claude»: заменить программы свежими, переписку и вход не трогать."""
    rezerv = papka / f"_do-obnovleniya-{METKA}"
    istochnik = BAZA / "whatsapp-claude"
    pomenyal = False
    for f in sorted((istochnik / "SKRIPTY").iterdir()):
        if f.is_dir():
            continue
        tsel = papka / "SKRIPTY" / f.name
        # текстовые файлы — через чтение/запись: переводы строк всегда как в Unix, откуда бы ни взялся источник
        tekstovyy = f.suffix in (".py", ".md", ".txt")
        novoe = pravki.chitat(f) if tekstovyy else None
        if tekstovyy and novoe is not None:
            if pravki.chitat(tsel) == novoe:
                continue
            kopiya(tsel, rezerv)
            pravki.pisat(tsel, novoe)
        else:
            if tsel.exists() and tsel.read_bytes() == f.read_bytes():
                continue
            kopiya(tsel, rezerv)
            shutil.copy2(f, tsel)
        pomenyal = True
    for f in ("USTANOVKA.md",):
        if (istochnik / f).exists():
            shutil.copy2(istochnik / f, papka / f)
    itog.append("✓ WhatsApp в Claude: обновлён" if pomenyal else "· WhatsApp в Claude: уже свежий")
    return pomenyal


def pravila_sprashivat(itog):
    """Общие настройки Claude этого пользователя: перед каждой отправкой — вопрос «Разрешить?»."""
    f = Path.home() / ".claude" / "settings.json"
    try:
        nastr = json.loads(f.read_text(encoding="utf-8-sig")) if f.exists() else {}
    except (ValueError, UnicodeDecodeError):
        itog.append(f"! {f} не читается — правило «спрашивать перед отправкой» не добавлено")
        return False
    ask = nastr.setdefault("permissions", {}).setdefault("ask", [])
    novye = [p for p in PRAVILA_SPRASHIVAT if p not in ask]
    if not novye:
        return False
    if f.exists():
        shutil.copy2(f, f.with_name(f"settings.do-obnovleniya-{METKA}.json"))
    ask += novye
    f.parent.mkdir(parents=True, exist_ok=True)
    pravki.pisat(f, json.dumps(nastr, ensure_ascii=False, indent=2) + "\n")
    itog.append("✓ Claude спрашивает «Разрешить?» перед каждой отправкой (WhatsApp, Telegram, почта) — в любом режиме")
    return True


def biblioteki(papka, itog):
    req = papka / "SKRIPTY" / "requirements.txt"
    if not req.exists() or os.environ.get("OBNOVIT_BEZ_PIP"):  # OBNOVIT_BEZ_PIP — для автотестов
        return
    print(f"  Ставлю библиотеки для {papka.name} (до нескольких минут)…", flush=True)
    komanda = [sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check", "-r", str(req)]
    r = subprocess.run(komanda, capture_output=True, text=True, encoding="utf-8", errors="replace", **BEZ_OKNA)
    if r.returncode != 0 and "externally-managed" in (r.stderr + r.stdout):
        r = subprocess.run(komanda + ["--user"], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", **BEZ_OKNA)
    if r.returncode != 0:
        itog.append(f"! библиотеки для {papka.name} не поставились: {(r.stderr or r.stdout).strip()[-300:]}")


def svodka(itog):
    """Итог для человека: что изменилось — простыми словами, без имён файлов."""
    est = lambda *nachala: any(s.startswith(nachala) for s in itog)  # noqa: E731
    stroki = []
    if est("✓ почта:"):
        stroki.append("✓ Почта: установлена — подключайте любые ящики фразой «Подключи почту»")
    if est("! wa.py"):
        stroki.append("! WhatsApp: часть исправлений не применена — файл wa.py другой версии (подробности в журнале)")
    elif est("✓ wa.py", "✓ mcp_", "✓ wa_ustanovka"):
        stroki.append("✓ WhatsApp и Telegram: исправлены ошибки Windows (список чатов, чёрное окно)")
    if est("✓ WhatsApp в Claude: обновлён"):
        stroki.append("✓ «WhatsApp в Claude»: обновлён")
    if est("✓ Claude спрашивает", "✓ почта: .claude/settings.json") or est("✓ mcp_messendzhery", "✓ mcp_whatsapp"):
        stroki.append("✓ Отправка: Claude всегда спрашивает «Разрешить?» — в любом режиме, и в «Авто» тоже")
    if est("✓ проверка", "✓ CLAUDE.md: фраза"):
        stroki.append("✓ Новая фраза «Проверь коннекторы» — один отчёт по всем каналам")
    stroki += [s for s in itog if s.startswith("!") and not s.startswith("! wa.py")]
    return stroki or ["· Всё уже свежее — менять нечего"]


def main():
    yavno = sys.argv[1] if len(sys.argv) > 1 else None
    sek = nayti_sekretarya(yavno)
    wa = Path.home() / "WhatsApp-Claude"
    wa = wa if (wa / "SKRIPTY" / "wa.py").exists() else None
    if yavno and not sek:
        sys.exit(f"В папке {yavno} нет AI-секретаря. Откройте Claude в папке 02_sekretar и повторите.")
    if not sek and not wa:
        sys.exit("Не нашёл ни папку секретаря 02_sekretar, ни коннектор «WhatsApp в Claude». "
                 "Откройте Claude в папке секретаря и повторите.")
    print(f"ОБНОВЛЕНИЕ КОННЕКТОРОВ · версия {VERSIYA}", flush=True)
    print("Секретарь: " + (str(sek) if sek else "не найден") + " · WhatsApp в Claude: " + (str(wa) if wa else "не установлен"))
    itog, perezapusk = [], False
    if sek:
        perezapusk |= obnovit_sekretarya(sek, itog)
    if wa:
        perezapusk |= obnovit_wa_claude(wa, itog)
    perezapusk |= pravila_sprashivat(itog)
    print("\n".join("  " + s for s in svodka(itog)), flush=True)
    for p in (sek, wa):
        if p:
            biblioteki(p, itog)
    # подробный список — в журнал для организатора, человеку — короткий итог простыми словами
    zhurnal = (sek / "NASTROYKI" if sek else wa) / f"obnovlenie-{METKA}.log"
    pravki.pisat(zhurnal, "\n".join(itog) + "\n")
    for s in itog:
        if s.startswith("! библиотеки"):
            print("  " + s, flush=True)
    print(f"  (подробно для организатора: {zhurnal})", flush=True)
    if sek:
        print(flush=True)
        subprocess.run([sys.executable, str(sek / "SKRIPTY" / "proverka.py")])
    print("\nГОТОВО. " + ("Полностью закройте Claude и откройте снова — тогда обновление заработает "
                          "(Windows: правой кнопкой по значку Claude возле часов → «Выйти»; Mac: Cmd + Q)."
                          if perezapusk else "Откройте новый чат — в нём обновление уже работает."))


if __name__ == "__main__":
    main()
