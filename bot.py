import telebot

# 👉 Reemplaza este TOKEN con el que te dio BotFather
import telebot

# 👉 Usa el token nuevo que te dio BotFather
TOKEN = "7818612520:AAEBcI4MJfwvsjY8HD-0MQuzuFYDlAJlc8k"

bot = telebot.TeleBot(TOKEN)

# Cuando alguien escriba /start
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "💜 Hola, soy Clara Mente. Estoy aquí para ayudarte a recuperar tu calma en minutos 💜")

# Cuando alguien escriba cualquier mensaje
@bot.message_handler(func=lambda message: True)
def echo_all(message):
    bot.reply_to(message, "✨ Recibí tu mensaje: " + message.text)

print("🤖 Bot en marcha...")

bot.infinity_polling()



