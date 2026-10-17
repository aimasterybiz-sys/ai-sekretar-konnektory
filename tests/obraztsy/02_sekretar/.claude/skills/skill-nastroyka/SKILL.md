# Первая настройка (образец)
- Почта не Google и не Microsoft: запусти `python SKRIPTY/klyuchi.py pochta` с таймаутом 15 минут.
Проверь коннекторы. Почта не Google и не Microsoft — значит IMAP: проверь `MAIL_HOST`, `MAIL_USER`, `MAIL_PASS` в `.env`; если `MAIL_HOST` пуст — найди IMAP-сервер по домену адреса и предложи вписать.
