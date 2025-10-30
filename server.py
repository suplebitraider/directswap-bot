import os
import json
from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

BOT_TOKEN = '7551518552:AAGvaJ87gP84CtgOQyDpjUzjcy_STYvRsGw'
WEBAPP_URL = 'https://suplabiltraidor.github.io/directswap-mob/index.html'

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

@bot.message_handler(commands=['start'])
def start_cmd(message):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("✔ открыть обменник", web_app=WebAppInfo(url=WEBAPP_URL)))
    bot.send_message(message.chat.id, "Добро пожаловать!\nНажмите кнопку ниже:", reply_markup=keyboard)

@bot.message_handler(content_types=['web_app_data'])
def webapp_data(message):
    try:
        data = json.loads(message.web_app_data.data)
        bot.send_message(message.chat.id, "✅ Заявка принята!")
    except:
        bot.send_message(message.chat.id, "❌ Ошибка данных")

@app.route('/webhook/ds12345', methods=['POST'])
def webhook():
    update = telebot.types.Update.de_json(request.get_json())
    bot.process_new_updates([update])
    return ''

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
