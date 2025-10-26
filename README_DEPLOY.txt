DirectSwap — Telegram webhook bot (Render/Railway/Fly/VPS)
==============================================================
Netlify — только для фронта. Ботам нужен сервер с HTTPS и публичным URL.

Вариант A: Render (просто)
--------------------------
1) Создай новый Blueprint → загрузить файл render.yaml или подключи репозиторий с этими файлами.
2) После создания сервиса открой Settings → Environment → добавь переменные:
   BOT_TOKEN, ADMIN_BOT_TOKEN, ADMIN_ID, ADMIN_TARGET_CHAT_ID, WEBAPP_URL, WEBHOOK_BASE (скопируй домен Render).
   (WEBHOOK_SECRET можно оставить сгенерированным / или задать вручную)
3) Перезапусти сервис. Логи покажут: "Webhook set to https://.../webhook/<secret>"
4) В Telegram в основном боте: /start → "Открыть DirectSwap 💱" → оформи заявку → проверь админ-чат.

Вариант B: Railway
------------------
1) Создай новый проект → Deploy from GitHub/Zip → добавь эти файлы.
2) Добавь переменные окружения из .env.example (PORT Railway задаёт сам).
3) Запусти деплой. После старта выстави WEBHOOK_BASE на публичный Railway URL и перезапусти.

Локально (для теста через ngrok)
---------------------------------
1) Скопируй .env.example → .env и заполни.
2) Запусти:  Windows: start_local.bat  |  macOS/Linux: bash start_local.sh
3) Подними ngrok:  ngrok http 8080
4) Поставь WEBHOOK_BASE=https://<ngrok-subdomain>.ngrok.io  → перезапусти сервер.py

Важно
-----
- WEBAPP_URL должен указывать на https://.../index.html на Netlify.
- Запускать мини-приложение надо из кнопки бота, а не напрямую в браузере.
- Если хочешь принимать в группу: ADMIN_TARGET_CHAT_ID = числовой ID группы (-100xxxx...), бот должен быть добавлен и иметь право писать.
