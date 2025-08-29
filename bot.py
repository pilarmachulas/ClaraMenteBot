import os
import logging
import telebot
from openai import OpenAI

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
SYSTEM_PROMPT = os.environ.get("SYSTEM_PROMPT", "Eres ClaraMente, una guía empática…")

bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode="Markdown")
client = OpenAI(api_key=OPENAI_API_KEY)

@bot.message_handler(commands=["start", "ayuda"])
def on_start(m):
    bot.reply_to(m, "Hola, soy *ClaraMente* 🧠. Cuéntame, ¿en qué te puedo ayudar hoy?")

@bot.message_handler(func=lambda m: True, content_types=["text"])
def on_text(m):
    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": m.text}
            ],
            temperature=0.6,
            max_tokens=400
        )
        answer = completion.choices[0].message.content.strip()
    except Exception as e:
        logging.exception("OpenAI error")
        answer = "Recibí tu mensaje pero tuve un problema al pensar 🤯. Probemos otra vez."

    bot.reply_to(m, answer)

if __name__ == "__main__":
    bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)

