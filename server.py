# server.py — Flask 3.x compatible (webhook + commands + web_app_data)
from flask import Flask, request, jsonify   # ← jsonify добавили здесь
import json                                 # ← чтобы json.loads работал
import time
import logging
import os

import telebot


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
    """Ручная установка вебхука (дерни из браузера после деплоя)."""
    try:
        url = f"{WEBHOOK_BASE}/webhook/{WEBHOOK_SECRET}"
        bot.remove_webhook()
        bot.set_webhook(url=url)  # без allowed_updates — Telegram пришлёт ВСЁ (и /start, и web_app_data)
        me = bot.get_me()
        log.info("Webhook (manual) set to %s for @%s", url, me.username)
        return f"Webhook set to {url} for @{me.username}", 200
    except Exception as e:
        log.exception("init/set_webhook failed: %r", e)
        return f"error: {e}", 500

@app.post(f"/webhook/{WEBHOOK_SECRET}")
def webhook():
    upd = request.get_json(silent=True) or {}
    log.info("WEBHOOK JSON[0:300]=%r", str(upd)[:300])

    msg = upd.get("message") or upd.get("edited_message")
    if not msg:
        return jsonify(ok=True)

    chat_id = msg.get("chat", {}).get("id")
    text = (msg.get("text") or "").strip()

    # === 1) ДАННЫЕ ИЗ МИНИ-ПРИЛОЖЕНИЯ ===
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
            f"Telegram: *{p.get('username','—')}*",
        ]
        admin_text = "\n".join(lines)

        # отправка в админ-бот с ретраями
        try:
            for i in range(3):
                try:
                    admin_bot.send_message(ADMIN_TARGET_CHAT_ID, admin_text, parse_mode="Markdown")
                    log.info("ADMIN DELIVERED")
                    break
                except Exception as e:
                    log.warning("ADMIN send fail try=%s: %r", i+1, e)
                    time.sleep(0.8)
        except Exception as e:
            log.error("ADMIN final fail: %r", e)

        return jsonify(ok=True)

    # === 2) Команды ===
    if text in ("/start", "/init"):
        bot.send_message(chat_id, "Готово. Нажмите *Начать обмен* в меню.", parse_mode="Markdown")
        return jsonify(ok=True)

    if text in ("/debug", "/testadmin"):
        dbg = (
            "DEBUG\n"
            f"admin_bot: {'ON' if ADMIN_BOT_TOKEN else 'OFF'}\n"
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
        bot.set_webhook(url=url)  # без allowed_updates
        me = bot.get_me()
        log.info("Webhook (import) set to %s for @%s", url, me.username)
    except Exception as e:
        log.exception("import set_webhook failed: %r", e)

_ensure_webhook_on_import()

# ---------- локальный запуск (для dev; на Render не нужно) ----------
if __name__ == "__main__":
    try:
        url = f"{WEBHOOK_BASE}/webhook/{WEBHOOK_SECRET}"
        bot.remove_webhook()
        bot.set_webhook(url=url)  # без allowed_updates
        me = bot.get_me()
        log.info("Webhook (main) set to %s for @%s", url, me.username)
    except Exception as e:
        log.exception("main set_webhook failed: %r", e)

    app.run(host=HOST, port=PORT)
