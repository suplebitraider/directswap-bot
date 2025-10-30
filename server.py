import os
import logging
from flask import Flask, request, jsonify
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
bot = telebot.TeleBot('7551518552:AAGvaJ87gP84CtgOQyDpjUzjcy_STYvRsGw')

@bot.message_handler(commands=['start'])
def start(message):
    try:
        logger.info(f"START command from {message.chat.id}")
        
        keyboard = InlineKeyboardMarkup()
        button = InlineKeyboardButton(
            "✔ открыть обменник", 
            web_app=WebAppInfo(url="https://suplabiltraidor.github.io/directswap-mob/index.html")
        )
        keyboard.add(button)
        
        logger.info("Keyboard created")
        bot.send_message(message.chat.id, "Тестовое сообщение!", reply_markup=keyboard)
        logger.info("Message sent successfully")
        
    except Exception as e:
        logger.error(f"Error in start: {e}")

@app.route('/webhook/ds12345', methods=['POST'])
def webhook():
    try:
        logger.info("Webhook called")
        json_data = request.get_json()
        logger.info(f"Received update: {json_data}")
        
        update = telebot.types.Update.de_json(json_data)
        bot.process_new_updates([update])
        
        logger.info("Update processed")
        return jsonify({"status": "ok"})
        
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    logger.info("Starting server...")
    app.run(host='0.0.0.0', port=10000)
