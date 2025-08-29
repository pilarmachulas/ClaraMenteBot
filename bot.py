import os
import logging
import telebot
from openai import OpenAI

# Logging claro
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s: %(message)s")
telebot.logger.setLevel(logging.WARNING)  # sube a DEBUG si quieres más ruido

# Variables de entorno
try:
    TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
    OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
except KeyError as e:
    logging.error(f"Falta variable de entorno: {e}. Revisa Config Vars en Heroku.")
    raise

SYSTEM_PROMPT = os.environ.get(
    "SYSTEM_PROMPT",
    "Eres ClaraMente, una guía emocional empática y cercana. Responde en español, breve y con claridad."
)

# Inicializa clientes
bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode="Markdown")
client = OpenAI(api_key=OPENAI_API_KEY)

@bot.message_handler(commands=["start", "ayuda", "ping"])
def on_start(m):
    logging.info(f"/start o /ping de {m.chat.id}")
    bot.reply_to(m, "Estoy viva 🧠✨ ¿En qué te acompaño hoy?")

@bot.message_handler(func=lambda m: True, content_types=["text"])
def on_text(m):
    user_text = m.text.strip()
    logging.info(f"Mensaje recibido de {m.chat.id}: {user_text!r}")
    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ],
            temperature=0.6,
            max_tokens=400
        )
        answer = completion.choices[0].message.content.strip()
        logging.info(f"Respuesta generada: {answer[:100]}...")
        bot.reply_to(m, answer)
    except Exception as e:
        logging.exception("Error generando respuesta con OpenAI")
        bot.reply_to(m, "Recibí tu mensaje, pero tuve un problemita al pensar 🤯. Probemos de nuevo en un momento.")

if __name__ == "__main__":
    logging.info("✅ Bot iniciado: entrando en infinity_polling()")
    # Si vuelve a aparecer 409, hay otra instancia ejecutándose.
    bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)

