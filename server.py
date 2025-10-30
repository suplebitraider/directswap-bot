import os
import json
import logging
from flask import Flask, request, jsonify
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = os.getenv('BOT_TOKEN', '7551518552:AAGvaJ87gP84CtgOQyDpjUzjcy_STYvRsGw')
WEBAPP_URL = os.getenv('WEBAPP_URL', 'https://suplabiltraidor.github.io/directswap-mob/index.html')
WEBHOOK_SECRET = os.getenv('WEBHOOK_SECRET', 'ds12345')

log.info(f"Bot token: {BOT_TOKEN[:10]}...")
log.info(f"Webhook secret: {WEBHOOK_SECRET}")

# Инициализация
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# Простой обработчик команд
@bot.message_handler(commands=['start', 'test'])
def handle_commands(message):
    log.info(f"Command {message.text} from {message.chat.id}")
    
    if message.text == '/start':
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("✔ открыть обменник", web_app=WebAppInfo(url=WEBAPP_URL)))
        bot.send_message(message.chat.id, "Добро пожаловать! Нажмите кнопку ниже:", reply_markup=keyboard)
    else:
        bot.send_message(message.chat.id, "✅ Бот работает!")

# Обработчик всех текстовых сообщений
@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    log.info(f"Message from {message.chat.id}: {message.text}")
    bot.send_message(message.chat.id, f"Вы написали: {message.text}")

# Webhook endpoint
@app.route(f'/webhook/{WEBHOOK_SECRET}', methods=['POST'])
def webhook():
    try:
        log.info("Webhook called")
        json_data = request.get_json()
        log.info(f"Update received: {json_data}")
        
        update = telebot.types.Update.de_json(json_data)
        bot.process_new_updates([update])
        
        return jsonify({"status": "ok"})
    except Exception as e:
        log.error(f"Webhook error: {e}")
        return jsonify({"error": str(e)}), 500

# Health check
@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "bot": "running"})

# Установка webhook
@app.route('/set_webhook', methods=['GET'])
def set_webhook():
    try:
        webhook_url = f'https://directswap-bot.onrender.com/webhook/{WEBHOOK_SECRET}'
        result = bot.set_webhook(url=webhook_url)
        return jsonify({"status": "ok", "url": webhook_url, "result": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 10000))
    log.info(f"Starting server on port {port}")
    
    # Устанавливаем webhook при запуске
    try:
        webhook_url = f'https://directswap-bot.onrender.com/webhook/{WEBHOOK_SECRET}'
        bot.remove_webhook()
        bot.set_webhook(url=webhook_url)
        log.info(f"Webhook set to: {webhook_url}")
    except Exception as e:
        log.error(f"Failed to set webhook: {e}")
    
    app.run(host='0.0.0.0', port=port)
