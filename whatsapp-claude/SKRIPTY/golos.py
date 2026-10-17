"""Расшифровка голосовых через Groq (Whisper). Только стандартная библиотека.

Правила (из Темы 2):
1. Не удалось — не теряем молча: возвращаем «[голосовое, расшифровать не удалось: причина]».
2. Уже расшифрованное второй раз не отправляем: рядом с аудио лежит .txt.
3. Упёрлись в лимит — ждём и повторяем, в конце сборщик говорит, сколько осталось.

Запуск вручную для проверки:  python golos.py путь/к/файлу.ogg
"""
import json
import ssl
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from obshchee import GOLOS, env

URL = "https://api.groq.com/openai/v1/audio/transcriptions"
MAX_BAYT = 25 * 1024 * 1024
NE_RASSHIFROVANO = []  # сборщики читают это в конце, чтобы сказать «осталось N»


def _ssl():
    # Python с python.org на Mac не видит системные сертификаты — берём их из certifi
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _zapros(put, klyuch, model, yazyk):
    granitsa = uuid.uuid4().hex
    chasti = []

    def pole(imya, znach):
        chasti.append(f'--{granitsa}\r\nContent-Disposition: form-data; name="{imya}"\r\n\r\n{znach}\r\n'.encode())

    pole("model", model)
    pole("response_format", "json")
    if yazyk:
        pole("language", yazyk)
    # Голосовые WhatsApp и Telegram — это Opus в контейнере Ogg; Groq принимает их как .ogg
    chasti.append(
        f'--{granitsa}\r\nContent-Disposition: form-data; name="file"; filename="voice.ogg"\r\n'
        f"Content-Type: audio/ogg\r\n\r\n".encode()
        + Path(put).read_bytes() + b"\r\n")
    chasti.append(f"--{granitsa}--\r\n".encode())
    req = urllib.request.Request(URL, data=b"".join(chasti), method="POST", headers={
        "Authorization": f"Bearer {klyuch}",
        "Content-Type": f"multipart/form-data; boundary={granitsa}",
        "User-Agent": "Mozilla/5.0 sekretar",
    })
    with urllib.request.urlopen(req, timeout=120, context=_ssl()) as r:
        return json.loads(r.read().decode("utf-8")).get("text", "").strip()


def rasshifrovat(put, dlitelnost=None):
    """Текст голосового. put — файл аудио. dlitelnost — секунды, для подписи."""
    put = Path(put)
    podpis = f"голосовое{', ' + str(int(dlitelnost)) + ' с' if dlitelnost else ''}"
    kesh = put.with_suffix(".txt")
    if kesh.exists():
        return f"[{podpis}] {kesh.read_text(encoding='utf-8').strip()}"
    if not put.exists():
        NE_RASSHIFROVANO.append(str(put))
        return f"[{podpis}, расшифровать не удалось: файла нет на диске]"
    if put.stat().st_size > MAX_BAYT:
        NE_RASSHIFROVANO.append(str(put))
        return f"[{podpis}, расшифровать не удалось: файл больше 25 МБ]"
    e = env()
    klyuch = e.get("GROQ_API_KEY")
    if not klyuch:
        NE_RASSHIFROVANO.append(str(put))
        return f"[{podpis}, расшифровать не удалось: нет GROQ_API_KEY в .env]"
    model = e.get("GROQ_MODEL", "whisper-large-v3-turbo")
    for popytka in range(4):
        try:
            tekst = _zapros(put, klyuch, model, e.get("GROQ_LANG"))
            kesh.write_text(tekst, encoding="utf-8")
            return f"[{podpis}] {tekst}"
        except urllib.error.HTTPError as err:
            if err.code in (429, 503) and popytka < 3:
                zhdat = int(err.headers.get("retry-after") or 20 * (popytka + 1))
                print(f"  Groq просит подождать {zhdat} с…", file=sys.stderr)
                time.sleep(min(zhdat, 120))
                continue
            prichina = f"Groq ответил {err.code}"
        except Exception as err:  # сеть, таймаут
            prichina = f"{type(err).__name__}"
            if popytka < 3:
                time.sleep(5)
                continue
        NE_RASSHIFROVANO.append(str(put))
        return f"[{podpis}, расшифровать не удалось: {prichina}]"


if __name__ == "__main__":
    GOLOS.mkdir(parents=True, exist_ok=True)
    print(rasshifrovat(sys.argv[1]))
