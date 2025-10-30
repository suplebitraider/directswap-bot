import os
import json
import logging
from flask import Flask, request, jsonify
from flask_cors import CORS
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

# Настройка логирования
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = os.getenv('BOT_TOKEN')
WEBAPP_URL = os.getenv('WEBAPP_URL', 'https://your-webapp-url.com')

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
    log.info("START command from %s", message.chat.id)

    text = "Добро пожаловать в DirectSwap!\n\nНажмите кнопку ниже чтобы начать обмен:"
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("✔ открыть обменник", web_app=WebAppInfo(url=WEBAPP_URL)))

    bot.send_message(message.chat.id, text, reply_markup=keyboard)

@bot.message_handler(commands=['debug'])
def debug_cmd(message):
    bot.send_message(message.chat.id, f"DEBUG: ChatID: {message.chat.id}, UserID: {message.from_user.id}")

# --- ОБРАБОТКА WEB APP DATA ---
@bot.message_handler(content_types=['web_app_data'])
def webapp_data(message):
    try:
        log.info("WEBAPP DATA: %s", message.web_app_data.data)
        data = json.loads(message.web_app_data.data)
        request_id = generate_request_id()

        # Сохраняем пользователя
        user_sessions[request_id] = message.chat.id

        # Обработка данных от webapp
        # TODO: Добавьте вашу логику обработки обмена

        bot.send_message(message.chat.id, "✅ Заявка принята в обработку!")

    except Exception as e:
        log.error("Webapp data error: %s", e)
        bot.send_message(message.chat.id, "❌ Ошибка обработки данных")

# --- WEBHOOK ENDPOINTS ---
@app.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return ''
    else:
        return 'Invalid content type', 400

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "ok", "message": "Server is running"})

# --- MAIN ---
if __name__ == '__main__':
    # Удаляем вебхук (на всякий случай)
    bot.remove_webhook()
    
    # Устанавливаем вебхук
    webhook_url = os.getenv('WEBHOOK_URL')
    if webhook_url:
        bot.set_webhook(url=f"{webhook_url}/webhook")
        log.info("Webhook set to: %s", webhook_url)
    
    # Запускаем Flask app
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
