
# 🏆 NAIZA Tournament Bot

Telegram-ға арналған FC Mobile турнир боты.

## 1. BotFather
@BotFather-дан бот жасап, жаңа token алыңыз. Ескі жарияланған token-ді міндетті түрде `/revoke` арқылы жойыңыз.

## 2. Telegram ID
Ботты іске қосқаннан кейін `/id` командасын жіберіп, өз Telegram ID-іңізді алыңыз.

## 3. Орнату
Python 3.11+ керек.

```bash
pip install -r requirements.txt
```

## 4. Environment variables

```text
BOT_TOKEN=ЖАҢА_TOKEN
ADMIN_ID=СІЗДІҢ_TELEGRAM_ID
```

## 5. Іске қосу

```bash
python bot.py
```

## Командалар

- `/new 16` — 16 ойыншыға жаңа NAIZA League
- `/add nz•Zevrix` — ойыншы қосу
- `/players` — ойыншылар
- `/draw` — жеребе
- `/bracket` — сетка
- `/result 3 2-1` — №3 матч нәтижесі
- `/status` — статус
- `/cancel` — турнирді жабу
- `/id` — Telegram ID

Қолдайтын өлшемдер: 4, 8, 16, 32 ойыншы.

Ескерту: `/result` тең есеп қабылдамайды. FC Mobile матчында жеңімпаз анықталғаннан кейін ғана нәтиже енгізіледі.
