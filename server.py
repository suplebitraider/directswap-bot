# server.py — DirectSwap webhook server (main + admin via webhook)
import os, json, logging
from flask import Flask, request, abort
from dotenv import load_dotenv
import telebot
from telebot.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN","").strip()
WEBAPP_URL = os.getenv("WEBAPP_URL","").strip()        # https://.../index.html
ADMIN_ID = int(os.getenv("ADMIN_ID","0") or 0)
ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN","").strip()
ADMIN_TARGET_CHAT_ID = int(os.getenv("ADMIN_TARGET_CHAT_ID","0") or 0)

PORT = int(os.getenv("PORT","8080"))
HOST = os.getenv("HOST","0.0.0.0")

WEBHOOK_BASE = os.getenv("WEBHOOK_BASE","").strip()    # e.g. https://your-app.onrender.com
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET","secret")  # anything hard to guess

assert BOT_TOKEN, "BOT_TOKEN is required"
assert WEBAPP_URL.startswith("https://") and WEBAPP_URL.endswith("index.html"), "WEBAPP_URL must be https and end with index.html"
assert WEBHOOK_BASE.startswith("https://"), "WEBHOOK_BASE must be https public url"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("directswap-webhook")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
admin_bot = telebot.TeleBot(ADMIN_BOT_TOKEN, parse_mode="HTML") if ADMIN_BOT_TOKEN else None

def admin_send(text, reply_markup=None):
    sent=False
    if admin_bot and ADMIN_TARGET_CHAT_ID:
        try:
            admin_bot.send_message(ADMIN_TARGET_CHAT_ID, text, reply_markup=reply_markup, disable_web_page_preview=True)
            sent=True
        except Exception as e:
            log.error("admin_bot send failed: %r", e)
    if not sent and ADMIN_ID:
        try:
            bot.send_message(ADMIN_ID, "⚠️ <b>Admin bot could not deliver.</b>\n\n"+text, reply_markup=reply_markup, disable_web_page_preview=True)
            sent=True
        except Exception as e2:
            log.error("fallback send failed: %r", e2)
    return sent

app = Flask(__name__)

@app.route("/", methods=["GET"])
def root():
    return "DirectSwap webhook OK", 200

@app.route(f"/webhook/{WEBHOOK_SECRET}", methods=["POST"])
def webhook():
    if request.headers.get("content-type") == "application/json":
        json_str = request.get_data().decode("utf-8")
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
        return "", 200
    else:
        abort(403)

@bot.message_handler(commands=["start"])
def start(message):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("Открыть DirectSwap 💱", web_app=WebAppInfo(url=WEBAPP_URL)))
    bot.send_message(message.chat.id, "Добро пожаловать в DirectSwap!\n\nКоманды: /debug /testadmin", reply_markup=kb)

@bot.message_handler(commands=["debug"])
def debug(message):
    info = (f"<b>DEBUG</b>\n"
            f"admin_bot: {'ON' if admin_bot else 'OFF'}\n"
            f"ADMIN_TARGET_CHAT_ID: {ADMIN_TARGET_CHAT_ID}\n"
            f"ADMIN_ID: {ADMIN_ID}\n"
            f"WEBAPP_URL: {WEBAPP_URL}\n"
            f"WEBHOOK_BASE: {WEBHOOK_BASE}\n")
    bot.send_message(message.chat.id, info)

@bot.message_handler(commands=["testadmin"])
def testadmin(message):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("💬 Открыть чат (тест)", url=f"tg://user?id={message.from_user.id}"))
    ok = admin_send("🧪 TEST: Проверка доставки в админ-чат/бота", reply_markup=kb)
    bot.send_message(message.chat.id, "✅ testadmin: отправлено" if ok else "❌ testadmin: не удалось (проверьте ADMIN_TARGET_CHAT_ID/права)")

@bot.message_handler(content_types=["web_app_data"])
def web_app_data(message):
    try:
        data = json.loads(message.web_app_data.data)
    except Exception:
        data = {"type":"unknown","raw": message.web_app_data.data}
    user = message.from_user
    user_tag = f"@{user.username}" if user.username else f"id:{user.id}"
    deep_profile = f"tg://user?id={user.id}"
    dtype = data.get("type")

    if dtype == "exchange_request":
        calc = data.get("calc", {}) or {}
        handle = data.get("username")
        bot.send_message(message.chat.id, ("✅ Заявка на обмен принята\n"
                                           f"Сеть: <b>{data.get('network')}</b>\n"
                                           f"Сумма: <b>{data.get('amount')}</b>\n"
                                           f"Итог к выплате: <b>{calc.get('result_rub')} ₽</b>"))
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("💬 Открыть чат с клиентом", url=deep_profile))
        if handle and handle.startswith('@'):
            kb.add(InlineKeyboardButton("👤 Профиль (из WebApp)", url=f"https://t.me/{handle[1:]}"))
        elif user.username:
            kb.add(InlineKeyboardButton("👤 Профиль", url=f"https://t.me/{user.username}"))
        text_admin = ("🆕 <b>Заявка DirectSwap</b>\n"
                      f"От: {user_tag}\n"
                      f"Handle (из WebApp): {handle}\n"
                      f"User ID: <code>{user.id}</code>\n"
                      f"Имя: {user.first_name or ''} {user.last_name or ''}\n"
                      f"Сеть: {data.get('network')}\n"
                      f"Сумма: {data.get('amount')}\n"
                      f"Курс USD→RUB: {data.get('usd_rub')}\n"
                      f"Итог: <b>{calc.get('result_rub')} ₽</b>\n"
                      f"Комиссия сервиса: {calc.get('commission_rub')} ₽\n"
                      f"Номер карты: <code>{data.get('card_number')}</code>\n")
        admin_send(text_admin, reply_markup=kb)

    elif dtype == "support_request":
        handle = data.get("username")
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("💬 Открыть чат с клиентом", url=deep_profile))
        if handle and handle.startswith('@'):
            kb.add(InlineKeyboardButton("👤 Профиль (из WebApp)", url=f"https://t.me/{handle[1:]}"))
        elif user.username:
            kb.add(InlineKeyboardButton("👤 Профиль", url=f"https://t.me/{user.username}"))
        text_admin = ("🆘 <b>Обращение в поддержку</b>\n"
                      f"От: {user_tag}\n"
                      f"Handle (из WebApp): {handle}\n"
                      f"Тема: {data.get('topic')}\n"
                      f"Контакт: {data.get('contact')}\n"
                      f"Сообщение: {data.get('message')}")
        bot.send_message(message.chat.id, "✅ Сообщение в поддержку доставлено.")
        admin_send(text_admin, reply_markup=kb)

# --- webhook set/unset helpers ---
def set_webhook():
    url = f"{WEBHOOK_BASE}/webhook/{WEBHOOK_SECRET}"
    bot.remove_webhook()
    bot.set_webhook(url=url, allowed_updates=["message", "web_app_data"])
    log.info("Webhook set to %s", url)

if __name__ == "__main__":
    set_webhook()
    app.run(host=HOST, port=PORT)
