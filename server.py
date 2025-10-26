# server.py — Flask 3.x compatible
import os, json, logging
from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

# ---------- logging ----------
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("directswap")

# ---------- ENV ----------
BOT_TOKEN             = os.getenv("BOT_TOKEN", "").strip()
ADMIN_BOT_TOKEN       = os.getenv("ADMIN_BOT_TOKEN", "").strip()
ADMIN_ID              = int(os.getenv("ADMIN_ID", "0") or 0)
ADMIN_TARGET_CHAT_ID  = int(os.getenv("ADMIN_TARGET_CHAT_ID", "0") or 0)
WEBAPP_URL            = os.getenv("WEBAPP_URL", "").strip()
WEBHOOK_BASE          = os.getenv("WEBHOOK_BASE", "").strip()          # https://<service>.onrender.com
WEBHOOK_SECRET        = os.getenv("WEBHOOK_SECRET", "ds12345").strip() # ds12345
HOST                  = os.getenv("HOST", "0.0.0.0")
PORT                  = int(os.getenv("PORT", "10000"))

if not BOT_TOKEN or not ADMIN_BOT_TOKEN or not WEBHOOK_BASE:
    log.error("Missing required ENV (BOT_TOKEN / ADMIN_BOT_TOKEN / WEBHOOK_BASE)")

bot       = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
admin_bot = telebot.TeleBot(ADMIN_BOT_TOKEN, parse_mode="HTML")

# ---------- Flask ----------
app = Flask(__name__)

@app.get("/")
def root_ok():
    return "DirectSwap backend OK", 200

@app.get("/healthz")
def healthz():
    return "ok", 200

@app.get("/init")
def init():
    """Ручная установка вебхука (можно дернуть из браузера после деплоя)."""
    try:
        url = f"{WEBHOOK_BASE}/webhook/{WEBHOOK_SECRET}"
        bot.remove_webhook()
        # для web_app_data достаточно "message"
        bot.set_webhook(url=url, allowed_updates=["message"])
        log.info("Webhook (manual) set to %s", url)
        return f"Webhook set to {url}", 200
    except Exception as e:
        log.exception("init/set_webhook failed: %r", e)
        return f"error: {e}", 500

@app.post(f"/webhook/{WEBHOOK_SECRET}")
def webhook():
    ct = request.headers.get("content-type", "")
    body = request.get_data().decode("utf-8", errors="ignore")
    log.info("WEBHOOK HIT ct=%s body[0:200]=%s", ct, body[:200])
    try:
        update = telebot.types.Update.de_json(body)
        bot.process_new_updates([update])
    except Exception as e:
        log.exception("process_new_updates failed: %r", e)
    return "", 200

# ---------- helpers ----------
def admin_send(text, **kw):
    """Отправка в админ-чат/бот."""
    try:
        admin_bot.send_message(ADMIN_TARGET_CHAT_ID or ADMIN_ID, text, **kw)
        log.info("admin_bot: delivered to %s", ADMIN_TARGET_CHAT_ID or ADMIN_ID)
    except Exception as e:
        log.exception("admin_bot send failed: %r", e)

def make_open_webapp_kb():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("Открыть DirectSwap 💱", web_app=WebAppInfo(url=WEBAPP_URL)))
    return kb

def fmt_money(v):
    try:
        return f"{float(v):,.2f}".replace(",", " ")
    except Exception:
        return str(v)

# ---------- commands ----------
@bot.message_handler(commands=["start"])
def cmd_start(m):
    bot.send_message(
        m.chat.id,
        "Добро пожаловать в DirectSwap!\nНажмите кнопку ниже, чтобы открыть мини-приложение.",
        reply_markup=make_open_webapp_kb()
    )

@bot.message_handler(commands=["debug"])
def cmd_debug(m):
    text = (
        "DEBUG\n"
        f"admin_bot: ON\n"
        f"ADMIN_TARGET_CHAT_ID: {ADMIN_TARGET_CHAT_ID}\n"
        f"ADMIN_ID: {ADMIN_ID}\n"
        f"WEBAPP_URL: {WEBAPP_URL}\n"
        f"WEBHOOK_BASE: {WEBHOOK_BASE}\n"
        f"WEBHOOK_SECRET: {WEBHOOK_SECRET}\n"
    )
    bot.send_message(m.chat.id, text)

@bot.message_handler(commands=["testadmin"])
def cmd_testadmin(m):
    try:
        admin_send("🧪 TEST: Проверка доставки в админ-чат/бота")
        bot.send_message(m.chat.id, "Ок, тест отправлен в админ-бот.")
    except Exception as e:
        bot.send_message(m.chat.id, "⚠️ Admin bot failed. Mirror copy:\n\n🧪 TEST: Проверка доставки в админ-чат/бота")
        log.exception("testadmin failed: %r", e)

# ---------- заявки из WebApp ----------
@bot.message_handler(content_types=["web_app_data"])
def handle_web_app_data(message: telebot.types.Message):
    """Главный обработчик заявок из мини-приложения (Telegram.WebApp.sendData)."""
    try:
        raw = message.web_app_data.data
        log.info("web_app_data RAW: %s", raw)
        try:
            data = json.loads(raw)
        except Exception:
            data = {"raw": raw}

        typ   = data.get("type", "exchange_request")
        net   = data.get("network", "-")
        amt   = data.get("amount", "-")
        rate  = data.get("usd_rub", "-")
        calc  = data.get("calc", {}) or {}
        res_rub = fmt_money(calc.get("result_rub", "-"))
        fee_rub = fmt_money(calc.get("commission_rub", "-"))
        card  = data.get("card_number", "—")
        uname = data.get("username", "") or ""
        if uname and not uname.startswith("@"):
            uname = "@" + uname

        client = uname if uname else f"id:{message.from_user.id}"
        title = "🟢 Новая заявка" if typ == "exchange_request" else "🟦 Обращение в поддержку"

        text = (
            f"{title}\n"
            f"— Клиент: {client}\n"
            f"— Сеть: {net}\n"
            f"— Сумма: {amt} USDT\n"
            f"— Курс: {rate} ₽\n"
            f"— Итог (к выплате): {res_rub} ₽\n"
            f"— Комиссия сервиса: {fee_rub} ₽\n"
            f"— Карта: <code>{card}</code>\n"
        )
        admin_send(text)
        bot.send_message(message.chat.id, "✅ Заявка отправлена. Мы скоро свяжемся с вами.")

    except Exception as e:
        log.exception("handle_web_app_data failed: %r", e)
        try:
            admin_send(f"⚠️ Ошибка при приёме web_app_data: <code>{e}</code>")
        except Exception:
            pass

# ---------- webhook setup on import (Flask 3.x safe) ----------
def _ensure_webhook_on_import():
    """Вызывается при импорте модуля (когда gunicorn загрузил server:app)."""
    try:
        url = f"{WEBHOOK_BASE}/webhook/{WEBHOOK_SECRET}"
        bot.remove_webhook()
        bot.set_webhook(url=url, allowed_updates=["message"])
        log.info("Webhook (import) set to %s", url)
    except Exception as e:
        log.exception("import set_webhook failed: %r", e)

# выставляем вебхук при загрузке модуля
_ensure_webhook_on_import()

# ---------- локальный запуск (для dev, не нужен на Render) ----------
if __name__ == "__main__":
    # Дополнительно ставим вебхук при локальном запуске
    try:
        url = f"{WEBHOOK_BASE}/webhook/{WEBHOOK_SECRET}"
        bot.remove_webhook()
        bot.set_webhook(url=url, allowed_updates=["message"])
        log.info("Webhook (main) set to %s", url)
    except Exception as e:
        log.exception("main set_webhook failed: %r", e)

    app.run(host=HOST, port=PORT)
