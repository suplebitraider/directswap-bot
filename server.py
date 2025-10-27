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
user_sessions = {}  # Храним chat_id пользователей
admin_messages = {}  # Храним message_id админ-сообщений

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

def fmt_money(v):
    try:
        return f"{float(v):,.2f}".replace(",", " ")
    except Exception:
        return str(v)

# ---------- Flask Routes ----------
@app.get("/")
def root_ok():
    return "DirectSwap backend OK", 200

@app.get("/healthz")
def healthz():
    return "ok", 200

@app.get("/init")
def init():
    """Ручная установка вебхука."""
    try:
        url = f"{WEBHOOK_BASE}/webhook/{WEBHOOK_SECRET}"
        bot.remove_webhook()
        bot.set_webhook(url=url)
        me = bot.get_me()
        log.info("Webhook (manual) set to %s for @%s", url, me.username)
        return f"Webhook set to {url} for @{me.username}", 200
    except Exception as e:
        log.exception("init/set_webhook failed: %r", e)
        return f"error: {e}", 500

# ---------- Резервный эндпоинт для заявок ----------
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
        else:
            keyboard.add(InlineKeyboardButton("✅ Ответить", callback_data=f"support_{request_id}"))

        # Отправляем через админ-бота
        sent_message = admin_bot.send_message(
            ADMIN_TARGET_CHAT_ID, 
            text, 
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        
        # Сохраняем ID сообщения для callback
        admin_messages[request_id] = sent_message.message_id
        
        log.info("ADMIN DELIVERED (HTTP reserve) - ID: %s", request_id)
        return {"ok": True, "message": "Заявка отправлена"}
    except Exception as e:
        log.error("ADMIN reserve send failed: %r", e)
        return {"ok": False, "error": str(e)}, 500

# --- WEBHOOK ---
@app.post(f"/webhook/{WEBHOOK_SECRET}")
def webhook():
    upd = request.get_json(silent=True) or {}
    log.info("WEBHOOK JSON[0:300]=%r", str(upd)[:300])

    # Обрабатываем через основного бота (включая callback)
    bot.process_new_updates([telebot.types.Update.de_json(upd)])
    return jsonify(ok=True)

# ---------- Обработка callback query ----------
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    """Обработка нажатий на кнопки."""
    try:
        data = call.data
        user_chat_id = call.from_user.id
        
        # Проверяем, что это админ (по ID)
        if user_chat_id != ADMIN_ID and user_chat_id != ADMIN_TARGET_CHAT_ID:
            bot.answer_callback_query(call.id, text="❌ Нет доступа")
            return
        
        log.info("Callback received: %s from user: %s", data, user_chat_id)
        
        if data.startswith("rejected_"):
            request_id = data.replace("rejected_", "")
            client_chat_id = user_sessions.get(request_id)
            
            # Обновляем сообщение в админ-чате
            try:
                original_text = call.message.text
                new_text = original_text + f"\n\n❌ *ОТКЛОНЕНО* администратором"
                
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=new_text,
                    parse_mode="Markdown",
                    reply_markup=None
                )
                log.info("Заявка %s отмечена как отклоненная", request_id)
            except Exception as e:
                log.error("Ошибка при обновлении сообщения: %r", e)
            
            # Отправляем уведомление клиенту
            if client_chat_id:
                try:
                    rejection_text = (
                        "❌ *Ваша заявка не была обработана*\n\n"
                        "К сожалению, мы не смогли выполнить ваш запрос. "
                        "Пожалуйста, обратитесь в поддержку или создайте новую заявку.\n\n"
                        "💬 *По вопросам:* @directswap_support"
                    )
                    bot.send_message(client_chat_id, rejection_text, parse_mode="Markdown")
                    log.info("Уведомление об отклонении отправлено пользователю %s", client_chat_id)
                except Exception as e:
                    log.error("Ошибка при отправке уведомления клиенту: %r", e)
            
            bot.answer_callback_query(call.id, text="✅ Заявка отклонена")
            
        elif data.startswith("processed_"):
            request_id = data.replace("processed_", "")
            client_chat_id = user_sessions.get(request_id)
            
            # Обновляем сообщение в админ-чате
            try:
                original_text = call.message.text
                new_text = original_text + f"\n\n✅ *ОБРАБОТАНО* администратором"
                
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=new_text,
                    parse_mode="Markdown",
                    reply_markup=None
                )
                log.info("Заявка %s отмечена как обработанная", request_id)
            except Exception as e:
                log.error("Ошибка при обновлении сообщения: %r", e)
            
            # Отправляем уведомление клиенту
            if client_chat_id:
                try:
                    processed_text = (
                        "✅ *Ваша заявка успешно обработана!*\n\n"
                        "Средства будут зачислены в ближайшее время.\n"
                        "Спасибо, что выбрали наш сервис! 🎉\n\n"
                        "💬 *По вопросам:* @directswap_support"
                    )
                    bot.send_message(client_chat_id, processed_text, parse_mode="Markdown")
                    log.info("Уведомление об обработке отправлено пользователю %s", client_chat_id)
                except Exception as e:
                    log.error("Ошибка при отправке уведомления клиенту: %r", e)
            
            bot.answer_callback_query(call.id, text="✅ Заявка обработана")
                
        elif data.startswith("support_"):
            request_id = data.replace("support_", "")
            bot.answer_callback_query(
                call.id,
                text=f"Ответьте на заявку поддержки #{request_id}",
                show_alert=False
            )
            
    except Exception as e:
        log.exception("Callback failed: %r", e)
        try:
            bot.answer_callback_query(call.id, text="❌ Ошибка обработки")
        except:
            pass

# ---------- Обработка web_app_data ----------
@bot.message_handler(content_types=["web_app_data"])
def handle_web_app_data(message):
    """Обработка заявок из мини-приложения."""
    try:
        raw = message.web_app_data.data
        log.info("WEBAPP RAW=%s", raw)
        try:
            data = json.loads(raw)
        except Exception:
            data = {"raw": raw}

        # Сохраняем chat_id пользователя
        user_chat_id = message.chat.id
        request_type = data.get("type", "exchange_request") if isinstance(data, dict) else "exchange_request"
        request_id = generate_request_id()
        current_time = datetime.now().strftime("%H:%M %d.%m.%Y")
        
        user_sessions[request_id] = user_chat_id
        log.info("Saved user session: %s -> %s", request_id, user_chat_id)
        
        if request_type == "support_request" and isinstance(data, dict):
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
            
            admin_bot.send_message(
                ADMIN_TARGET_CHAT_ID,
                text,
                parse_mode="Markdown",
                reply_markup=keyboard
            )
            
            bot.send_message(user_chat_id, "✅ Ваше сообщение отправлено в поддержку. Мы ответим вам в ближайшее время.")
            
        else:
            p = data if isinstance(data, dict) else {"raw": str(data)}
            calc = p.get("calc") or {}
            network = p.get("network", "-")
            network_icon = get_network_icon(network)
            
            amt = p.get("amount", "-")
            rate = p.get("usd_rub", "-")
            res_rub = fmt_money(calc.get("result_rub", "-"))
            fee_rub = fmt_money(calc.get("commission_rub", "-"))
            card = p.get("card_number", "—")
            uname = p.get("username", "") or ""
            if uname and not uname.startswith("@"):
                uname = "@" + uname

            client = uname if uname else f"id:{message.from_user.id}"
            
            text = (
                f"🎯 *НОВАЯ ЗАЯВКА НА ОБМЕН* #{request_id}\n"
                f"╔══════════════════════\n"
                f"║ 👤 *Клиент:* {client}\n"
                f"║ {network_icon} *Сеть:* {network}\n"
                f"║ 💰 *Сумма:* {amt} USDT\n"
                f"║ 📈 *Курс:* {rate} ₽\n"
                f"║ 🕒 *Время:* {current_time}\n"
                f"║ ────────────────────\n"
                f"║ 💵 *К выплате:* {res_rub} ₽\n"
                f"║ 📊 *Комиссия:* {fee_rub} ₽\n"
                f"║ 💳 *Карта:* `{card}`\n"
                f"╚══════════════════════"
            )

            keyboard = InlineKeyboardMarkup()
            
            if uname and uname.startswith('@'):
                keyboard.add(InlineKeyboardButton(
                    "💬 Написать клиенту", 
                    url=f"https://t.me/{uname[1:]}"
                ))
            
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
            
            bot.send_message(user_chat_id, "✅ Заявка отправлена. Мы скоро свяжемся с вами.")
            
    except Exception as e:
        log.exception("handle_web_app_data failed: %r", e)

# ---------- commands ----------
@bot.message_handler(commands=["start"])
def cmd_start(m):
    welcome_text = (
        "🎉 *Добро пожаловать в DirectSwap!*\n\n"
        "💱 *Обменяйте криптовалюту по выгодному курсу:*\n"
        "• USDT → RUB\n" 
        "• Быстро и безопасно\n"
        "• Поддержка 24/7\n\n"
        "🚀 *Начните обмен - нажмите кнопку ниже!*"
    )
    
    bot.send_message(
        m.chat.id,
        welcome_text,
        parse_mode="Markdown",
        reply_markup=make_open_webapp_kb()
    )

@bot.message_handler(commands=["debug"])
def cmd_debug(m):
    text = (
        "DEBUG\n"
        f"BOT_ID: {m.chat.id}\n"
        f"ADMIN_TARGET_CHAT_ID: {ADMIN_TARGET_CHAT_ID}\n"
        f"ADMIN_ID: {ADMIN_ID}\n"
        f"WEBAPP_URL: {WEBAPP_URL}\n"
    )
    bot.send_message(m.chat.id, text)

# ---------- webhook setup ----------
def _ensure_webhook_on_import():
    try:
        url = f"{WEBHOOK_BASE}/webhook/{WEBHOOK_SECRET}"
        bot.remove_webhook()
        bot.set_webhook(url=url)
        me = bot.get_me()
        log.info("Webhook (import) set to %s for @%s", url, me.username)
    except Exception as e:
        log.exception("import set_webhook failed: %r", e)

_ensure_webhook_on_import()

if __name__ == "__main__":
    app.run(host=HOST, port=PORT)
