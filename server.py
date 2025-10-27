# server.py — Flask 3.x compatible (webhook + commands + web_app_data)
import os, json, logging, time
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
    calc = p.get("calc") or {}

    lines = [
        "💠 *Новая заявка* (HTTP резерв)",
        f"Сеть: *{p.get('network','?')}*",
        f"Сумма: *{p.get('amount','?')} USDT*", 
        f"Курс: *{p.get('usd_rub','?')} ₽*",
        f"Итог (RUB): *{calc.get('result_rub','?')}*",
        f"Комиссия сервиса: *{calc.get('commission_rub','?')}*",
        f"Карта: *{p.get('card_number','?')}*",
        f"Telegram: *{p.get('username','—')}*",
    ]
    admin_text = "\n".join(lines)

    try:
        admin_bot.send_message(ADMIN_TARGET_CHAT_ID, admin_text, parse_mode="Markdown")
        log.info("ADMIN DELIVERED (HTTP reserve)")
        return {"ok": True, "message": "Заявка отправлена"}
    except Exception as e:
        log.error("ADMIN reserve send failed: %r", e)
        return {"ok": False, "error": str(e)}, 500

# --- WEBHOOK ---
@app.post(f"/webhook/{WEBHOOK_SECRET}")
def webhook():
    upd = request.get_json(silent=True) or {}
    log.info("WEBHOOK JSON[0:300]=%r", str(upd)[:300])

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

        p = payload if isinstance(payload, dict) else {"raw": str(payload)}
        calc = p.get("calc") or {}
        lines = [
            "💠 *Новая заявка*",
            f"Сеть: *{p.get('network','?')}*",
            f"Сумма: *{p.get('amount','?')} USDT*",
            f"Курс: *{p.get('usd_rub','?')} ₽*",
            f"Итог (RUB): *{calc.get('result_rub','?')}*", 
            f"Комиссия сервиса: *{calc.get('commission_rub','?')}*",
            f"Карта: *{p.get('card_number','?')}*",
            f"Telegram: *{p.get('username','—')}*"
        ]
        admin_text = "\n".join(lines)

        try:
            for i in range(3):
                try:
                    admin_bot.send_message(
                        ADMIN_TARGET_CHAT_ID,
                        admin_text, 
                        parse_mode="Markdown"
                    )
                    log.info("ADMIN DELIVERED")
                    break
                except Exception as e:
                    log.warning("ADMIN send fail try=%s: %r", i+1, e)
                    time.sleep(0.8)
        except Exception as e:
            log.error("ADMIN final fail: %r", e)

        return jsonify(ok=True)

    # 2) Обычные команды
    if text in ("/start", "/init"):
        bot.send_message(chat_id, "Готово. Нажмите *Начать обмен* в меню.", parse_mode="Markdown")
        return jsonify(ok=True)

    if text in ("/debug", "/testadmin"):
        admin_ok = "ON" if ADMIN_BOT_TOKEN else "OFF"
        dbg = (
            "DEBUG\n"
            f"admin_bot: {admin_ok}\n"
            f"ADMIN_TARGET_CHAT_ID: {ADMIN_TARGET_CHAT_ID}\n"
            f"WEBAPP_URL: {WEBAPP_URL}\n"
            f"WEBHOOK_BASE: {WEBHOOK_BASE}\n"
        )
        bot.send_message(chat_id, dbg)
        try:
            admin_bot.send_message(ADMIN_TARGET_CHAT_ID, "🧪 TEST: Проверка доставки в админ-чат/бота")
        except Exception as e:
            log.error("Admin test send failed: %r", e)
        return jsonify(ok=True)

    log.info("MSG: chat_id=%s text=%r", chat_id, text)
    return jsonify(ok=True)

# ---------- helpers ----------
def admin_send(text, **kw):
    try:
        admin_bot.send_message(ADMIN_TARGET_CHAT_ID or ADMIN_ID, text, **kw)
        log.info("admin_bot: delivered to %s", ADMIN_TARGET_CHAT_ID or ADMIN_ID)
    except Exception as e:
        log.exception("admin_bot send failed: %r", e)

def make_open_webapp_kb():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("Открыть DirectSwap 💱", web_app=WebAppInfo(url=WEBAPP_URL)))
    return kb

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
