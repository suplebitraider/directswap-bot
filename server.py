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
ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or 0)
ADMIN_CHAT_ID = int(os.getenv("ADMIN_TARGET_CHAT_ID", "0") or 0)
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()
WEBHOOK_BASE = os.getenv("WEBHOOK_BASE", "").strip()
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "ds12345").strip()
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "10000"))

if not BOT_TOKEN or not WEBHOOK_BASE:
    log.error("Missing required ENV (BOT_TOKEN / WEBHOOK_BASE)")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# ---------- Flask ----------
app = Flask(__name__)
CORS(app, origins=[
    "https://sunibaktsalder.github.io",
    "https://telegram.org", 
    "https://web.telegram.org"
])

# ---------- Глобальные переменные ----------
request_counter = 0
user_sessions = {}  # Храним chat_id пользователей

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

def is_admin(user_id):
    return user_id == ADMIN_ID or user_id == ADMIN_CHAT_ID

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

        bot.send_message(
            ADMIN_CHAT_ID, 
            text, 
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        
        log.info("ADMIN DELIVERED (HTTP reserve) - ID: %s", request_id)
        return {"ok": True, "message": "Заявка отправлена"}
    except Exception as e:
        log.error("ADMIN reserve send failed: %r", e)
        return {"ok": False, "error": str(e)}, 500

# --- WEBHOOK ---
@app.post(f"/webhook/{WEBHOOK_SECRET}")
def webhook():
    """Главный обработчик вебхука"""
    upd = request.get_json(silent=True) or {}
    log.info("WEBHOOK JSON[0:300]=%r", str(upd)[:300])
    
    # Передаем обновление боту
    if upd:
        update = telebot.types.Update.de_json(upd)
        bot.process_new_updates([update])
    
    return jsonify(ok=True)

# ---------- КОМАНДЫ БОТА ----------
@bot.message_handler(commands=['start'])
def send_welcome(message):
    """Обработчик команды /start"""
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
    """Обработчик команды /debug"""
    text = (
        f"DEBUG INFO:\n"
        f"User ID: {message.from_user.id}\n"
        f"Admin ID: {ADMIN_ID}\n"
        f"Admin Chat: {ADMIN_CHAT_ID}\n"
        f"Is Admin: {is_admin(message.from_user.id)}"
    )
    bot.send_message(message.chat.id, text)

@bot.message_handler(commands=['admin'])
def admin_panel(message):
    """Админ-панель (только для админов)"""
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "❌ Нет доступа")
        return
        
    text = "🛠 *Панель администратора*\nВыберите действие:"
    keyboard = InlineKeyboardMarkup()
    keyboard.row(
        InlineKeyboardButton("📊 Статистика", callback_data="admin_stats"),
        InlineKeyboardButton("🔄 Обновить", callback_data="admin_refresh")
    )
    
    bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=keyboard)

# ---------- ОБРАБОТКА WEB_APP_DATA ----------
@bot.message_handler(content_types=['web_app_data'])
def handle_web_app_data(message):
    """Обработка данных из мини-приложения"""
    try:
        data = json.loads(message.web_app_data.data)
        user_chat_id = message.chat.id
        request_id = generate_request_id()
        current_time = datetime.now().strftime("%H:%M %d.%m.%Y")
        
        # Сохраняем связь заявки с пользователем
        user_sessions[request_id] = user_chat_id
        log.info("Saved user session: %s -> %s", request_id, user_chat_id)
        
        request_type = data.get('type', 'exchange_request')
        
        if request_type == 'support_request':
            # Обработка заявки в поддержку
            support_topic = data.get("topic", "")
            support_contact = data.get("contact", "")
            support_message = data.get("message", "")
            username = data.get("username", "")
            
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
            
            keyboard = InlineKeyboardMarkup()
            if username and username.startswith('@'):
                keyboard.add(InlineKeyboardButton(
                    "💬 Написать клиенту", 
                    url=f"https://t.me/{username[1:]}"
                ))
            keyboard.add(InlineKeyboardButton("✅ Ответить", callback_data=f"support_{request_id}"))
            
            bot.send_message(ADMIN_CHAT_ID, text, parse_mode="Markdown", reply_markup=keyboard)
            bot.send_message(user_chat_id, "✅ Ваше сообщение отправлено в поддержку. Мы ответим вам в ближайшее время.")
            
        else:
            # Обработка заявки на обмен
            network = data.get('network', 'TRC20')
            amount = data.get('amount', '0')
            card_number = data.get('card_number', '')
            username = data.get('username', '')
            network_icon = get_network_icon(network)
            
            text = (
                f"🎯 *НОВАЯ ЗАЯВКА НА ОБМЕН* #{request_id}\n"
                f"╔══════════════════════\n"
                f"║ 👤 *Клиент:* {username if username else '—'}\n"
                f"║ {network_icon} *Сеть:* {network}\n"
                f"║ 💰 *Сумма:* {amount} USDT\n"
                f"║ 📈 *Курс:* 78.30 ₽\n"
                f"║ 🕒 *Время:* {current_time}\n"
                f"║ ────────────────────\n"
                f"║ 💵 *К выплате:* {float(amount) * 78.30 * 0.97:.2f} ₽\n"
                f"║ 📊 *Комиссия:* {float(amount) * 78.30 * 0.03:.2f} ₽\n"
                f"║ 💳 *Карта:* `{card_number}`\n"
                f"╚══════════════════════"
            )

            keyboard = InlineKeyboardMarkup()
            
            if username and username.startswith('@'):
                keyboard.add(InlineKeyboardButton(
                    "💬 Написать клиенту", 
                    url=f"https://t.me/{username[1:]}"
                ))
            
            keyboard.row(
                InlineKeyboardButton("✅ Обработано", callback_data=f"processed_{request_id}"),
                InlineKeyboardButton("❌ Отклонить", callback_data=f"rejected_{request_id}")
            )

            bot.send_message(ADMIN_CHAT_ID, text, parse_mode="Markdown", reply_markup=keyboard)
            bot.send_message(user_chat_id, "✅ Заявка отправлена. Мы скоро свяжемся с вами.")
            
    except Exception as e:
        log.error("WebApp data error: %r", e)
        bot.send_message(message.chat.id, "❌ Ошибка при отправке заявки")

# ---------- ОБРАБОТКА CALLBACK (КНОПОК) ----------
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    """Обработка нажатий на кнопки"""
    try:
        data = call.data
        user_id = call.from_user.id
        
        # Проверяем права админа
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "❌ Нет доступа")
            return
            
        log.info("Callback received: %s from admin: %s", data, user_id)
        
        if data.startswith("rejected_"):
            request_id = data.replace("rejected_", "")
            client_chat_id = user_sessions.get(request_id)
            
            # Обновляем сообщение
            original_text = call.message.text
            new_text = original_text + f"\n\n❌ *ОТКЛОНЕНО* администратором"
            
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=new_text,
                parse_mode="Markdown",
                reply_markup=None
            )
            
            # Уведомляем клиента
            if client_chat_id:
                rejection_text = (
                    "❌ *Ваша заявка не была обработана*\n\n"
                    "К сожалению, мы не смогли выполнить ваш запрос. "
                    "Пожалуйста, обратитесь в поддержку или создайте новую заявку.\n\n"
                    "💬 *По вопросам:* @directswap_support"
                )
                bot.send_message(client_chat_id, rejection_text, parse_mode="Markdown")
            
            bot.answer_callback_query(call.id, "✅ Заявка отклонена")
            
        elif data.startswith("processed_"):
            request_id = data.replace("processed_", "")
            client_chat_id = user_sessions.get(request_id)
            
            # Обновляем сообщение
            original_text = call.message.text
            new_text = original_text + f"\n\n✅ *ОБРАБОТАНО* администратором"
            
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=new_text,
                parse_mode="Markdown",
                reply_markup=None
            )
            
            # Уведомляем клиента
            if client_chat_id:
                processed_text = (
                    "✅ *Ваша заявка успешно обработана!*\n\n"
                    "Средства будут зачислены в ближайшее время.\n"
                    "Спасибо, что выбрали наш сервис! 🎉\n\n"
                    "💬 *По вопросам:* @directswap_support"
                )
                bot.send_message(client_chat_id, processed_text, parse_mode="Markdown")
            
            bot.answer_callback_query(call.id, "✅ Заявка обработана")
            
        elif data.startswith("support_"):
            request_id = data.replace("support_", "")
            bot.answer_callback_query(call.id, f"Ответьте на заявку поддержки #{request_id}")
            
        elif data == "admin_stats":
            stats_text = f"📊 *Статистика*\nВсего заявок: {request_counter}"
            bot.answer_callback_query(call.id)
            bot.send_message(call.message.chat.id, stats_text, parse_mode="Markdown")
            
        elif data == "admin_refresh":
            bot.answer_callback_query(call.id, "✅ Обновлено")
            
    except Exception as e:
        log.error("Callback error: %r", e)
        bot.answer_callback_query(call.id, "❌ Ошибка обработки")

# ---------- НАСТРОЙКА ВЕБХУКА ----------
def setup_webhook():
    """Настройка вебхука при запуске"""
    try:
        url = f"{WEBHOOK_BASE}/webhook/{WEBHOOK_SECRET}"
        bot.remove_webhook()
        bot.set_webhook(url=url)
        me = bot.get_me()
        log.info("✅ Webhook set to %s for @%s", url, me.username)
    except Exception as e:
        log.error("❌ Webhook setup failed: %r", e)

# Запускаем настройку вебхука
setup_webhook()

if __name__ == "__main__":
    app.run(host=HOST, port=PORT)
