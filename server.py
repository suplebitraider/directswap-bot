# server.py — Flask 3.x compatible (webhook + commands + web_app_data)
import os, json, logging
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

# ---------- logging ----------
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("directswap")

# ---------- ENV ----------
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or 0)
ADMIN_CHAT_ID = int(os.getenv("ADMIN_TARGET_CHAT_ID", "0") or 0)
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()
WEBHOOK_BASE = os.getenv("WEBHOOK_BASE", "").strip()
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "ds12345").strip()
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "10000"))

if not BOT_TOKEN:
    log.error("Missing BOT_TOKEN")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# ---------- Flask ----------
app = Flask(__name__)
CORS(app)

# ---------- Глобальные переменные ----------
request_counter = 0
user_sessions = {}

# ---------- helpers ----------
def generate_request_id():
    global request_counter
    request_counter += 1
    return f"{request_counter:03d}"

def is_admin(user_id):
    return user_id == ADMIN_ID or user_id == ADMIN_CHAT_ID

# ---------- Flask Routes ----------
@app.get("/")
def root_ok():
    return "DirectSwap backend OK", 200

@app.post("/collect")
@cross_origin()
def collect():
    try:
        data = request.get_json() or {}
        log.info("COLLECT: %s", data)
        
        request_id = generate_request_id()
        request_type = data.get("type", "exchange")
        
        if request_type == "support":
            text = f"🆘 ПОДДЕРЖКА #{request_id}\nКлиент: {data.get('username', '—')}\nТема: {data.get('topic', '—')}\nСообщение: {data.get('message', '—')}"
        else:
            text = f"🎯 ОБМЕН #{request_id}\nСеть: {data.get('network', '—')}\nСумма: {data.get('amount', '—')} USDT\nКарта: {data.get('card_number', '—')}"
        
        keyboard = InlineKeyboardMarkup()
        keyboard.row(
            InlineKeyboardButton("✅ Обработано", callback_data=f"ok_{request_id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"no_{request_id}")
        )
        
        bot.send_message(ADMIN_CHAT_ID, text, reply_markup=keyboard)
        return {"ok": True}
        
    except Exception as e:
        log.error("COLLECT error: %s", e)
        return {"ok": False}, 500

# ---------- ОБРАБОТКА КОМАНД ----------
@bot.message_handler(commands=['start'])
def start_cmd(message):
    log.info("START command from %s", message.chat.id)
    
    text = "🎉 Добро пожаловать в DirectSwap!\n\nНажмите кнопку ниже чтобы начать обмен:"
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🚀 Открыть обменник", web_app=WebAppInfo(url=WEBAPP_URL)))
    
    bot.send_message(message.chat.id, text, reply_markup=keyboard)

@bot.message_handler(commands=['debug'])
def debug_cmd(message):
    bot.send_message(message.chat.id, f"DEBUG: ChatID: {message.chat.id}, UserID: {message.from_user.id}")

# ---------- ОБРАБОТКА WEB APP DATA ----------
@bot.message_handler(content_types=['web_app_data'])
def webapp_data(message):
    try:
        log.info("WEBAPP DATA: %s", message.web_app_data.data)
        data = json.loads(message.web_app_data.data)
        request_id = generate_request_id()
        
        # Сохраняем пользователя
        user_sessions[request_id] = message.chat.id
        
        if data.get('type') == 'support_request':
            text = f"🆘 ПОДДЕРЖКА #{request_id}\nКлиент: {data.get('username', '—')}\nТема: {data.get('topic', '—')}\nСообщение: {data.get('message', '—')}"
            bot.send_message(ADMIN_CHAT_ID, text)
            bot.send_message(message.chat.id, "✅ Сообщение отправлено в поддержку")
        else:
            text = f"🎯 ОБМЕН #{request_id}\nСеть: {data.get('network', '—')}\nСумма: {data.get('amount', '—')} USDT\nКарта: {data.get('card_number', '—')}"
            
            keyboard = InlineKeyboardMarkup()
            keyboard.row(
                InlineKeyboardButton("✅ Обработано", callback_data=f"ok_{request_id}"),
                InlineKeyboardButton("❌ Отклонить", callback_data=f"no_{request_id}")
            )
            
            bot.send_message(ADMIN_CHAT_ID, text, reply_markup=keyboard)
            bot.send_message(message.chat.id, "✅ Заявка отправлена")
            
    except Exception as e:
        log.error("WebApp error: %s", e)
        bot.send_message(message.chat.id, "❌ Ошибка")

# ---------- ОБРАБОТКА CALLBACK ----------
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    try:
        log.info("CALLBACK: %s", call.data)
        
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Нет доступа")
            return
            
        if call.data.startswith("ok_"):
            request_id = call.data.replace("ok_", "")
            user_chat_id = user_sessions.get(request_id)
            
            # Обновляем сообщение
            bot.edit_message_text(
                f"{call.message.text}\n\n✅ ОБРАБОТАНО",
                call.message.chat.id,
                call.message.message_id
            )
            
            # Уведомляем пользователя
            if user_chat_id:
                bot.send_message(user_chat_id, "✅ Ваша заявка обработана!")
                
            bot.answer_callback_query(call.id, "✅ Заявка обработана")
            
        elif call.data.startswith("no_"):
            request_id = call.data.replace("no_", "")
            user_chat_id = user_sessions.get(request_id)
            
            # Обновляем сообщение
            bot.edit_message_text(
                f"{call.message.text}\n\n❌ ОТКЛОНЕНО", 
                call.message.chat.id,
                call.message.message_id
            )
            
            # Уведомляем пользователя
            if user_chat_id:
                bot.send_message(user_chat_id, "❌ Ваша заявка отклонена")
                
            bot.answer_callback_query(call.id, "❌ Заявка отклонена")
            
    except Exception as e:
        log.error("Callback error: %s", e)
        bot.answer_callback_query(call.id, "❌ Ошибка")

# ---------- WEBHOOK ----------
@app.post(f"/webhook/{WEBHOOK_SECRET}")
def webhook():
    try:
        update = request.get_json()
        log.info("WEBHOOK: %s", update)
        
        if update:
            bot.process_new_updates([telebot.types.Update.de_json(update)])
            
        return jsonify(ok=True)
    except Exception as e:
        log.error("Webhook error: %s", e)
        return jsonify(ok=False), 500

# ---------- ЗАПУСК ----------
if __name__ == "__main__":
    log.info("Starting server...")
    try:
        # Настраиваем вебхук
        url = f"{WEBHOOK_BASE}/webhook/{WEBHOOK_SECRET}"
        bot.remove_webhook()
        bot.set_webhook(url=url)
        log.info("Webhook set to: %s", url)
    except Exception as e:
        log.error("Webhook setup error: %s", e)
    
    app.run(host=HOST, port=PORT)
