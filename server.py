import os
import json
import logging
from flask import Flask, request, jsonify
from flask_cors import CORS
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = os.getenv('BOT_TOKEN')
WEBAPP_URL = os.getenv('WEBAPP_URL', 'https://suplabiltraidor.github.io/directswap-mob/index.html')
RENDER_URL = os.getenv('WEBHOOK_BASE', 'https://directswap-bot.onrender.com')
WEBHOOK_SECRET = os.getenv('WEBHOOK_SECRET', 'ds12345')

if not BOT_TOKEN:
    log.error("BOT_TOKEN not set!")
    raise ValueError("BOT_TOKEN environment variable is required")

log.info(f"Initializing bot with token: {BOT_TOKEN[:10]}...")
log.info(f"Webhook URL: {RENDER_URL}")
log.info(f"Webhook secret: {WEBHOOK_SECRET}")

# Инициализация бота и приложения
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
CORS(app)

# Глобальные переменные
user_sessions = {}
exchange_requests = {}

def generate_request_id():
    return str(hash(str(os.urandom(16))))

# --- ОБРАБОТКА КОМАНД ---
@bot.message_handler(commands=['start'])
def start_cmd(message):
    log.info(f"START command from {message.chat.id}")
    
    try:
        text = "Добро пожаловать в DirectSwap!\n\nНажмите кнопку ниже чтобы начать обмен:"
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("✔ открыть обменник", web_app=WebAppInfo(url=WEBAPP_URL)))
        
        bot.send_message(message.chat.id, text, reply_markup=keyboard)
        log.info(f"Start message sent to {message.chat.id}")
        
    except Exception as e:
        log.error(f"Error in start_cmd: {e}")

@bot.message_handler(commands=['debug'])
def debug_cmd(message):
    try:
        response = f"DEBUG: ChatID: {message.chat.id}, UserID: {message.from_user.id}"
        bot.send_message(message.chat.id, response)
        log.info(f"Debug info sent to {message.chat.id}")
    except Exception as e:
        log.error(f"Error in debug_cmd: {e}")

@bot.message_handler(commands=['test'])
def test_cmd(message):
    try:
        bot.send_message(message.chat.id, "✅ Бот работает!")
        log.info(f"Test message sent to {message.chat.id}")
    except Exception as e:
        log.error(f"Error in test_cmd: {e}")

# --- ОБРАБОТКА WEB APP DATA ---
@bot.message_handler(content_types=['web_app_data'])
def webapp_data(message):
    try:
        log.info(f"WEBAPP DATA from {message.chat.id}: {message.web_app_data.data}")
        data = json.loads(message.web_app_data.data)
        request_id = generate_request_id()

        # Сохраняем пользователя
        user_sessions[request_id] = message.chat.id
        log.info(f"User session saved: {request_id} -> {message.chat.id}")

        # TODO: Добавьте вашу логику обработки обмена

        bot.send_message(message.chat.id, "✅ Заявка принята в обработку!")
        log.info(f"Confirmation sent to {message.chat.id}")

    except Exception as e:
        log.error(f"Webapp data error: {e}")
        try:
            bot.send_message(message.chat.id, "❌ Ошибка обработки данных")
        except:
            pass

# --- WEBHOOK ENDPOINTS ---
@app.route(f'/webhook/{WEBHOOK_SECRET}', methods=['POST'])
def webhook():
    try:
        if request.headers.get('content-type') == 'application/json':
            json_string = request.get_data().decode('utf-8')
            update = telebot.types.Update.de_json(json_string)
            bot.process_new_updates([update])
            log.info("Webhook processed successfully")
            return jsonify({"status": "ok"})
        else:
            log.warning("Invalid content type in webhook")
            return 'Invalid content type', 400
    except Exception as e:
        log.error(f"Webhook error: {e}")
        return 'Error', 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "ok", 
        "message": "Server is running",
        "bot_initialized": BOT_TOKEN is not None,
        "webhook_secret": WEBHOOK_SECRET
    })

@app.route('/set_webhook', methods=['GET'])
def set_webhook():
    try:
        webhook_url = f"{RENDER_URL}/webhook/{WEBHOOK_SECRET}"
        result = bot.set_webhook(url=webhook_url)
        log.info(f"Webhook set to: {webhook_url}, result: {result}")
        return jsonify({"status": "ok", "webhook_url": webhook_url, "result": result})
    except Exception as e:
        log.error(f"Error setting webhook: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route('/delete_webhook', methods=['GET'])
def delete_webhook():
    try:
        result = bot.remove_webhook()
        log.info(f"Webhook deleted, result: {result}")
        return jsonify({"status": "ok", "result": result})
    except Exception as e:
        log.error(f"Error deleting webhook: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

# --- MAIN ---
if __name__ == '__main__':
    # Устанавливаем вебхук при запуске
    try:
        webhook_url = f"{RENDER_URL}/webhook/{WEBHOOK_SECRET}"
        bot.remove_webhook()
        bot.set_webhook(url=webhook_url)
        log.info(f"Webhook set to: {webhook_url}")
    except Exception as e:
        log.error(f"Error setting webhook on startup: {e}")
    
    # Запускаем Flask app
    port = int(os.getenv('PORT', 10000))
    log.info(f"Starting server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
