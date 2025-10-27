# server.py — Flask 3.x compatible (webhook + commands + web_app_data)
import os, json, logging, time
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS, cross_origin
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

# ---------- logging ----------
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("directswap")

# ---------- ENV ----------
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or 0)
ADMIN_TARGET_CHAT_ID = int(os.getenv("ADMIN_TARGET_CHAT_ID", "0") or 0)
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()
WEBHOOK_BASE = os.getenv("WEBHOOK_BASE", "").strip()
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "ds12345").strip()
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "10000"))

if not BOT_TOKEN or not ADMIN_BOT_TOKEN or not WEBHOOK_BASE:
    log.error("Missing required ENV (BOT_TOKEN / ADMIN_BOT_TOKEN / WEBHOOK_BASE)")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
admin_bot = telebot.TeleBot(ADMIN_BOT_TOKEN, parse_mode="HTML")

# ---------- Flask ----------
app = Flask(__name__)
CORS(app, origins=[
    "https://sunibaktsalder.github.io",
    "https://telegram.org", 
    "https://web.telegram.org"
])

# ---------- Глобальные переменные ----------
request_counter = 0
user_sessions = {}

# ---------- helpers ----------
def generate_request_id():
    global request_counter
    request_counter += 1
    return f"{request_counter:03d}"

def get_network_icon(network):
    icons = {
        "TRC20": "⏩",
        "ERC20": "Ⓜ️", 
        "TON": "💎"
    }
    return icons.get(network, "🌐")

def make_open_webapp_kb():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🚀 Открыть DirectSwap", web_app=WebAppInfo(url=WEBAPP_URL)))
    return kb

# ---------- Flask Routes ----------
@app.get("/")
def root_ok():
    return "DirectSwap backend OK", 200

@app.get("/healthz")
def healthz():
    return "ok", 200

@app.post("/collect")
@cross_origin()
def collect():
    """Резерв: приём заявки обычным HTTP из браузера."""
    try:
        p = request.get_json(force=True) or {}
        log.info("COLLECT received: %s", p)
    except Exception as e:
        log.error("COLLECT error: %r", e)
        p = {}

    if not isinstance(p, dict):
        p = {"raw": str(p)}
    
    request_type = p.get("type", "exchange_request")
    request_id = generate_request_id()
    current_time = datetime.now().strftime("%H:%M %d.%m.%Y")
    
    if request_type == "support_request":
        support_topic = p.get("topic", "")
        support_contact = p.get("contact", "")
        support_message = p.get("message", "")
        username = p.get("username", "")
        
        text = (
            f"🆘 *ЗАПРОС ПОДДЕРЖКИ* #{request_id}\n"
            f"╔══════════════════════\n"
            f"║ 👤 *Клиент:* {username if username else '—'}\n"
            f"║ 📞 *Контакт:* {support_contact if support_contact else '—'}\n"
            f"║ 🕒 *Время:* {current_time}\n"
            f"║ ────────────────────\n"
            f"║ 📝 *Тема:* {support_topic}\n"
            f"║ 💬 *Сообщение:*\n"
            f"║ {support_message}\n"
            f"╚══════════════════════"
        )
        
    else:
        calc = p.get("calc") or {}
        network = p.get("network", "?")
        network_icon = get_network_icon(network)
        
        text = (
            f"🎯 *НОВАЯ ЗАЯВКА НА ОБМЕН* #{request_id}\n"
            f"╔══════════════════════\n"
            f"║ 👤 *Клиент:* {p.get('username', '—')}\n"
            f"║ {network_icon} *Сеть:* {network}\n"
            f"║ 💰 *Сумма:* {p.get('amount','?')} USDT\n"
            f"║ 📈 *Курс:* {p.get('usd_rub','?')} ₽\n"
            f"║ 🕒 *Время:* {current_time}\n"
            f"║ ────────────────────\n"
            f"║ 💵 *К выплате:* {calc.get('result_rub','?')} ₽\n"
            f"║ 📊 *Комиссия:* {calc.get('commission_rub','?')} ₽\n"
            f"║ 💳 *Карта:* `{p.get('card_number','?')}`\n"
            f"╚══════════════════════"
        )

    try:
        keyboard = InlineKeyboardMarkup()
        
        username = p.get('username', '')
        if username and username.startswith('@'):
            keyboard.add(InlineKeyboardButton(
                "💬 Написать клиенту", 
                url=f"https://t.me/{username[1:]}"
            ))
        
        if request_type == "exchange_request":
            keyboard.row(
                InlineKeyboardButton("✅ Обработано", callback_data=f"processed_{request_id}"),
                InlineKeyboardButton("❌ Отклонить", callback_data=f"rejected_{request_id}")
            )

        admin_bot.send_message(
            ADMIN_TARGET_CHAT_ID, 
            text, 
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        
        log.info("ADMIN DELIVERED (HTTP reserve) - ID: %s", request_id)
        return {"ok": True, "message": "Заявка отправлена"}
    except Exception as e:
        log.error("ADMIN reserve send failed: %r", e)
        return {"ok": False, "error": str(e)}, 500

# --- Обработка команд основного бота ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    welcome_text = (
        "🎉 *Добро пожаловать в DirectSwap!*\n\n"
        "💱 *Обменяйте криптовалюту по выгодному курсу:*\n"
        "• USDT → RUB\n" 
        "• Быстро и безопасно\n"
        "• Поддержка 24/7\n\n"
        "🚀 *Начните обмен - нажмите кнопку ниже!*"
    )
    
    bot.send_message(
        message.chat.id,
        welcome_text,
        parse_mode="Markdown",
        reply_markup=make_open_webapp_kb()
    )

@bot.message_handler(commands=['debug'])
def debug_info(message):
    text = f"DEBUG\nChat ID: {message.chat.id}\nADMIN_ID: {ADMIN_ID}"
    bot.send_message(message.chat.id, text)

# --- Обработка web_app_data ---
@bot.message_handler(content_types=['web_app_data'])
def handle_web_app_data(message):
    try:
        data = json.loads(message.web_app_data.data)
        request_id = generate_request_id()
        user_sessions[request_id] = message.chat.id
        
        log.info(f"WebApp data: {data}")
        
        if data.get('type') == 'support_request':
            # Обработка поддержки
            support_text = (
                f"🆘 *ЗАПРОС ПОДДЕРЖКИ* #{request_id}\n"
                f"От: {data.get('username', '—')}\n"
                f"Тема: {data.get('topic', '—')}\n"
                f"Сообщение: {data.get('message', '—')}"
            )
            admin_bot.send_message(ADMIN_TARGET_CHAT_ID, support_text, parse_mode="Markdown")
            bot.send_message(message.chat.id, "✅ Сообщение отправлено в поддержку")
            
        else:
            # Обработка обмена
            exchange_text = (
                f"🎯 *НОВАЯ ЗАЯВКА* #{request_id}\n"
                f"Сеть: {data.get('network', '—')}\n"
                f"Сумма: {data.get('amount', '—')} USDT\n"
                f"Карта: {data.get('card_number', '—')}"
            )
            
            keyboard = InlineKeyboardMarkup()
            keyboard.row(
                InlineKeyboardButton("✅ Обработано", callback_data=f"processed_{request_id}"),
                InlineKeyboardButton("❌ Отклонить", callback_data=f"rejected_{request_id}")
            )
            
            admin_bot.send_message(
                ADMIN_TARGET_CHAT_ID, 
                exchange_text, 
                parse_mode="Markdown",
                reply_markup=keyboard
            )
            bot.send_message(message.chat.id, "✅ Заявка отправлена")
            
    except Exception as e:
        log.error(f"WebApp error: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка отправки")

# --- Обработка callback для админ-бота ---
@admin_bot.callback_query_handler(func=lambda call: True)
def handle_admin_callback(call):
    try:
        data = call.data
        request_id = data.split('_')[1] if '_' in data else ''
        client_chat_id = user_sessions.get(request_id)
        
        if 'rejected' in data:
            # Обновляем сообщение
            admin_bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=call.message.text + "\n\n❌ ОТКЛОНЕНО",
                parse_mode="Markdown"
            )
            # Уведомляем клиента
            if client_chat_id:
                bot.send_message(client_chat_id, "❌ Ваша заявка отклонена")
            admin_bot.answer_callback_query(call.id, "Заявка отклонена")
            
        elif 'processed' in data:
            # Обновляем сообщение
            admin_bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=call.message.text + "\n\n✅ ОБРАБОТАНО", 
                parse_mode="Markdown"
            )
            # Уведомляем клиента
            if client_chat_id:
                bot.send_message(client_chat_id, "✅ Ваша заявка обработана!")
            admin_bot.answer_callback_query(call.id, "Заявка обработана")
            
    except Exception as e:
        log.error(f"Callback error: {e}")
        admin_bot.answer_callback_query(call.id, "Ошибка")

# --- WEBHOOK обработка ---
@app.post(f"/webhook/{WEBHOOK_SECRET}")
def webhook():
    """Обработка вебхука от Telegram"""
    if request.content_type != 'application/json':
        return jsonify({'ok': False}), 400
        
    json_data = request.get_json()
    log.info(f"Webhook received: {json_data}")
    
    # Пробуем обработать через основного бота
    try:
        update = telebot.types.Update.de_json(json_data)
        bot.process_new_updates([update])
    except Exception as e:
        log.error(f"Main bot processing error: {e}")
    
    # Пробуем обработать через админ-бота  
    try:
        update = telebot.types.Update.de_json(json_data)
        admin_bot.process_new_updates([update])
    except Exception as e:
        log.error(f"Admin bot processing error: {e}")
    
    return jsonify({'ok': True})

# --- Настройка вебхука при старте ---
@app.before_request
def setup_webhook():
    url = f"{WEBHOOK_BASE}/webhook/{WEBHOOK_SECRET}"
    bot.remove_webhook()
    bot.set_webhook(url=url)

if __name__ == "__main__":
    app.run(host=HOST, port=PORT)
