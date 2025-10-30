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

# ---------- helpers ----------
def generate_request_id():
    return f"{int(time.time())}"

def get_network_icon(network):
    icons = {
        "TRC20": "⏩",
        "ERC20": "Ⓜ️", 
        "TON": "💎"
    }
    return icons.get(network, "🌐")

def admin_send(text, **kw):
    try:
        admin_bot.send_message(ADMIN_TARGET_CHAT_ID or ADMIN_ID, text, **kw)
        log.info("admin_bot: delivered to %s", ADMIN_TARGET_CHAT_ID or ADMIN_ID)
    except Exception as e:
        log.exception("admin_bot send failed: %r", e)

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

@app.get("/botinfo")
def botinfo():
    try:
        me = bot.get_me()
        return {
            "ok": True,
            "username": me.username,
            "id": me.id,
            "webhook": f"{WEBHOOK_BASE}/webhook/{WEBHOOK_SECRET}"
        }, 200
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500

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
    
    # Определяем тип заявки
    request_type = p.get("type", "exchange_request")
    request_id = generate_request_id()
    current_time = datetime.now().strftime("%H:%M %d.%m.%Y")
    
    if request_type == "support_request":
        # Обработка заявки поддержки
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
        # Обработка заявки обмена
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
        # СОЗДАЕМ КЛАВИАТУРУ ТОЛЬКО С КНОПКОЙ "НАПИСАТЬ КЛИЕНТУ" (если есть username)
        keyboard = None
        
        # Если есть username, добавляем кнопку "Написать клиенту"
        username = p.get('username', '')
        if username and username.startswith('@'):
            keyboard = InlineKeyboardMarkup()
            keyboard.add(InlineKeyboardButton(
                "💬 Написать клиенту", 
                url=f"https://t.me/{username[1:]}"
            ))

        # ОТПРАВЛЯЕМ СООБЩЕНИЕ БЕЗ КНОПКИ "ОТВЕТИТЬ"
        admin_bot.send_message(
            ADMIN_TARGET_CHAT_ID, 
            text, 
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        log.info("ADMIN DELIVERED (HTTP reserve) without reply button - ID: %s", request_id)
        return {"ok": True, "message": "Заявка отправлена"}
    except Exception as e:
        log.error("ADMIN reserve send failed: %r", e)
        return {"ok": False, "error": str(e)}, 500

# --- WEBHOOK ---
@app.post(f"/webhook/{WEBHOOK_SECRET}")
def webhook():
    upd = request.get_json(silent=True) or {}
    log.info("WEBHOOK JSON[0:300]=%r", str(upd)[:300])

    # Обработка callback query для админ-бота
    callback_query = upd.get("callback_query")
    if callback_query:
        # Передаем callback в админ-бота для обработки
        admin_bot.process_new_updates([telebot.types.Update.de_json(upd)])
        return jsonify(ok=True)

    msg = upd.get("message") or upd.get("edited_message")
    if not msg:
        return jsonify(ok=True)

    chat_id = msg.get("chat", {}).get("id")
    text = (msg.get("text") or "").strip()

    # 1) Данные из мини-аппа
    wad = msg.get("web_app_data")
    if wad and isinstance(wad, dict):
        raw = wad.get("data") or ""
        log.info("WEBAPP RAW=%s", raw)
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {"raw": raw}

        # Определяем тип заявки
        request_type = payload.get("type", "exchange_request") if isinstance(payload, dict) else "exchange_request"
        request_id = generate_request_id()
        current_time = datetime.now().strftime("%H:%M %d.%m.%Y")
        
        if request_type == "support_request" and isinstance(payload, dict):
            # Обработка заявки поддержки
            support_topic = payload.get("topic", "")
            support_contact = payload.get("contact", "")
            support_message = payload.get("message", "")
            username = payload.get("username", "")
            
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
            
            keyboard = None
            if username and username.startswith('@'):
                keyboard = InlineKeyboardMarkup()
                keyboard.add(InlineKeyboardButton(
                    "💬 Написать клиенту", 
                    url=f"https://t.me/{username[1:]}"
                ))
            
            admin_bot.send_message(
                ADMIN_TARGET_CHAT_ID,
                text,
                parse_mode="Markdown",
                reply_markup=keyboard
            )
            
            bot.send_message(chat_id, "✅ Ваше сообщение отправлено в поддержку. Мы ответим вам в ближайшее время.")
            
        else:
            # Обработка заявки обмена
            p = payload if isinstance(payload, dict) else {"raw": str(payload)}
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

            client = uname if uname else f"id:{msg.get('from', {}).get('id', '?')}"
            
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

            keyboard = None
            if uname and uname.startswith('@'):
                keyboard = InlineKeyboardMarkup()
                keyboard.add(InlineKeyboardButton(
                    "💬 Написать клиенту", 
                    url=f"https://t.me/{uname[1:]}"
                ))

            admin_bot.send_message(
                ADMIN_TARGET_CHAT_ID,
                text,
                parse_mode="Markdown",
                reply_markup=keyboard
            )
            
            bot.send_message(chat_id, "✅ Заявка отправлена. Мы скоро свяжемся с вами.")

        return jsonify(ok=True)

    # 2) Обычные команды (/start)
    if text in ("/start", "/init"):
        welcome_text = (
            "🎉 *Добро пожаловать в DirectSwap!*\n\n"
            "💱 *Обменяйте криптовалюту по выгодному курсу:*\n"
            "• USDT → RUB\n" 
            "• Быстро и безопасно\n"
            "• Поддержка 24/7\n\n"
            "🚀 *Начните обмен - нажмите кнопку ниже!*"
        )
        
        bot.send_message(
            chat_id,
            welcome_text,
            parse_mode="Markdown",
            reply_markup=make_open_webapp_kb()
        )
        return jsonify(ok=True)

    # прочее — просто лог
    log.info("MSG: chat_id=%s text=%r", chat_id, text)
    return jsonify(ok=True)

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
