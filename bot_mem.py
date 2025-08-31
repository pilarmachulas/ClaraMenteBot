import os
import json
import logging
import requests
import telebot
from telebot import types
import openai
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
import time
import traceback

# ============ LOGGING ============
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s: %(message)s")
telebot.logger.setLevel(logging.WARNING)

# ============ ENV VARS ============
try:
    TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
    OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
    openai.api_key = OPENAI_API_KEY
except KeyError as e:
    logging.error(f"Falta variable de entorno: {e}. Revísalas en tu panel (Ereku/Heroku).")
    raise


SYSTEM_PROMPT_BASE = os.environ.get(
    "SYSTEM_PROMPT",
    "Eres ClaraMente, guía emocional cálida, directa y breve. Entregas calma, claridad y autoestima con tips simples. Nunca das párrafos largos."
)

# --- ENLACES DE RECURSOS (pon tus URLs reales) ---
GUIDE_ES_URL = os.environ.get("GUIDE_ES_URL", "https://TU-LINK-ES.pdf")
GUIDE_PT_URL = os.environ.get("GUIDE_PT_URL", "https://TU-LINK-PT.pdf")
# Opcional: links de Hotmart
HOTMART_ES = os.environ.get("HOTMART_ES", "https://TU-CHECKOUT-ES")
HOTMART_PT = os.environ.get("HOTMART_PT", "https://TU-CHECKOUT-PT")

# Webhook de Make/Zapier que crea/actualiza contacto en MailerLite
MAILER_WEBHOOK_URL = os.environ.get("MAILER_WEBHOOK_URL")  # ejemplo: https://hook.eu1.make.com/xxxx

# ============ CLIENTES ============
bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode="Markdown")

# ============ PERSISTENCIA ============
DB_PATH = os.environ.get("USERS_DB_PATH", "usuarios.json")
user_data = {}  # {str(chat_id): {...}}

def load_db():
    global user_data
    try:
        with open(DB_PATH, "r", encoding="utf-8") as f:
            user_data = json.load(f)
            user_data = {str(k): v for k, v in user_data.items()}
            logging.info(f"DB cargada: {len(user_data)} usuarias")
    except FileNotFoundError:
        user_data = {}
    except Exception:
        logging.exception("No pude cargar DB, inicio vacía")
        user_data = {}

def save_db():
    try:
        with open(DB_PATH, "w", encoding="utf-8") as f:
            json.dump(user_data, f, ensure_ascii=False, indent=2)
    except Exception:
        logging.exception("Error guardando DB")

def get_ud(chat_id: int):
    cid = str(chat_id)
    if cid not in user_data:
        user_data[cid] = {
            "idioma": None,      # "ES" | "PT"
            "stage": "lang",     # lang -> name -> age -> role -> topic -> email -> ready
            "nombre": None,
            "edad": None,        # "18–25" | "26–35" | "36–45" | "46+"
            "pais": None,
            "rol": None,         # madre/profesional/estudiante/otro | mãe/profissional/estudante/outro
            "tema": None,        # ansiedad/autoestima/calma | ansiedade/autoestima/calma
            "email": None,
            "etapa": "dia0",     # dia1..dia4
            "compras": []
        }
    return user_data[cid]

# ============ KEYBOARDS ============
def kb_lang():
    mk = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    mk.row("Español 🇪🇸", "Português 🇧🇷")
    return mk

def kb_age(_lang):
    mk = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    mk.row("18–25", "26–35")
    mk.row("36–45", "46+")
    return mk

def kb_role(lang):
    mk = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    if lang == "PT":
        mk.row("👩‍👧 Mãe/cuidadora", "👩‍💻 Profissional")
        mk.row("🎓 Estudante", "🌱 Outro")
    else:
        mk.row("👩‍👧 Madre/cuidadora", "👩‍💻 Profesional")
        mk.row("🎓 Estudiante", "🌱 Otro")
    return mk

def kb_topic(lang):
    mk = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    if lang == "PT":
        mk.row("😰 Ansiedade", "💔 Autoestima", "🧘 Calma rápida")
    else:
        mk.row("😰 Ansiedad", "💔 Autoestima", "🧘 Calma rápida")
    return mk

def rmv():
    return types.ReplyKeyboardRemove()

# ============ TEXTOS ============
def t(lang, key, **kwargs):
    es = {
        "hello": "🌸 Hola, soy Clara. ¿Prefieres conversar en Español 🇪🇸 o Português 🇧🇷?",
        "ask_name": "Encantada de acompañarte 💌. ¿Cómo te llamas?",
        "ask_age": "Para personalizar tu experiencia, ¿cuál es tu rango de edad?",
        "ask_role": "¿Con cuál de estos roles te identificas más hoy?",
        "ask_topic": "¿Qué sientes que necesitas más ahora mismo?",
        "thanks_name": "Gracias, {n} 🌸",
        "ask_email": "📥 Te regalo mi *Guía SOS*. ¿Quieres que también te la envíe a tu correo? Escríbelo aquí.",
        "done": "¡Listo, {n}! Desde ahora te acompaño con tips breves sobre *{tema}*. Cuando quieras, pregúntame lo que necesites.",
        "invalid_email": "Ese correo no parece válido. ¿Puedes escribirlo de nuevo?"
    }
    pt = {
        "hello": "🌸 Olá, sou a Clara. Você prefere conversar em Español 🇪🇸 ou Português 🇧🇷?",
        "ask_name": "É um prazer te acompanhar 💌. Como você se chama?",
        "ask_age": "Para personalizar sua experiência, qual é a sua faixa etária?",
        "ask_role": "Com qual desses papéis você mais se identifica hoje?",
        "ask_topic": "O que você sente que mais precisa agora?",
        "thanks_name": "Obrigada, {n} 🌸",
        "ask_email": "📥 Eu te presenteio com meu *Guia SOS*. Quer que eu também envie para seu e-mail? Escreva aqui.",
        "done": "Pronto, {n}! A partir de agora vou te acompanhar com dicas rápidas sobre *{tema}*. Quando quiser, pergunte o que precisar.",
        "invalid_email": "Esse e-mail não parece válido. Pode escrever novamente?"
    }
    tbl = pt if lang == "PT" else es
    return (tbl[key].format(**kwargs) if kwargs else tbl[key])

def guess_lang_from_btn(txt):
    lt = txt.lower()
    if "portugu" in lt or "🇧🇷" in lt: return "PT"
    if "español" in lt or "🇪🇸" in lt: return "ES"
    return None

def normalize_role(lang, txt):
    lt = txt.lower()
    if lang == "PT":
        if "mãe" in lt or "cuidad" in lt: return "mãe"
        if "profiss" in lt: return "profissional"
        if "estud" in lt: return "estudante"
        return "outro"
    else:
        if "madre" in lt or "cuidad" in lt: return "madre"
        if "profes" in lt: return "profesional"
        if "estud" in lt: return "estudiante"
        return "otro"

def normalize_topic(lang, txt):
    lt = txt.lower()
    if lang == "PT":
        if "ansied" in lt: return "ansiedade"
        if "autoest" in lt: return "autoestima"
        return "calma"
    else:
        if "ansied" in lt: return "ansiedad"
        if "autoest" in lt: return "autoestima"
        return "calma"

def is_email(s):
    return "@" in s and "." in s and " " not in s

# ============ RECURSOS & MAILER ============
def send_guide(chat_id, lang):
    link = GUIDE_PT_URL if lang == "PT" else GUIDE_ES_URL
    try:
        bot.send_message(chat_id, f"📥 *Guía SOS* lista:\n{link}", parse_mode="Markdown")
    except Exception:
        logging.exception("No pude enviar la guía")

def send_to_mailer(ud, chat_id):
    if not MAILER_WEBHOOK_URL:
        return
    payload = {
        "chat_id": chat_id,
        "nombre": ud.get("nombre"),
        "email": ud.get("email"),
        "edad": ud.get("edad"),
        "rol": ud.get("rol"),
        "tema": ud.get("tema"),
        "idioma": ud.get("idioma"),
        "etapa": ud.get("etapa"),
        "fuente": "telegram"
    }
    try:
        requests.post(MAILER_WEBHOOK_URL, json=payload, timeout=8)
    except Exception:
        logging.exception("Error enviando datos a MailerLite/Make")

# ============ SECUENCIA DÍA 1–4 ============
def seq_text(lang, day, ud):
    nombre = ud.get("nombre") or ("amiga" if lang == "ES" else "amiga")
    tema = ud.get("tema") or ("ansiedad" if lang == "ES" else "ansiedade")
    if lang == "PT":
        textos = {
            1: f"🌸 {nombre}, como combinamos: respire 3x com pausa de 4s. Isso te aterra em 1 minuto.",
            2: f"💡 Dica express para {tema}: nomeie a emoção em voz alta. Isso reduz o pico em 30–60s.",
            3: "✨ História real: uma mulher como você começou com o Guia SOS e retomou o sono em 7 dias.",
            4: f"🌸 Se sente que é sua hora, o *Programa Clara Mente 21 dias* te acompanha passo a passo 👉 {HOTMART_PT}"
        }
    else:
        textos = {
            1: f"🌸 {nombre}, como quedamos: respira 3 veces con pausa de 4s. Te aterriza en 1 minuto.",
            2: f"💡 Tip express para {tema}: nombra la emoción en voz alta. Baja el pico en 30–60s.",
            3: "✨ Historia real: una mujer como tú empezó con la Guía SOS y recuperó el sueño en 7 días.",
            4: f"🌸 Si sientes que es tu momento, el *Programa Clara Mente 21 días* te acompaña paso a paso 👉 {HOTMART_ES}"
        }
    return textos.get(day)

scheduler = BackgroundScheduler(timezone="UTC")

def schedule_followups(chat_id, start_in_hours=23):
    """Programa Día1–Día4 aprox diario sin clavar 24h exactas."""
    cid = str(chat_id)
    offsets = [start_in_hours, start_in_hours+24, start_in_hours+48, start_in_hours+72]
    for i, off in enumerate(offsets, start=1):
        run_dt = datetime.utcnow() + timedelta(hours=off)
        scheduler.add_job(send_followup, "date", run_date=run_dt, args=[cid, i],
                          id=f"{cid}-d{i}", replace_existing=True)

def send_followup(cid, day):
    ud = user_data.get(str(cid))
    if not ud or ud.get("stage") != "ready":
        return
    lang = ud.get("idioma") or "ES"
    txt = seq_text(lang, day, ud)
    if not txt:
        return
    try:
        bot.send_message(int(cid), txt, parse_mode="Markdown")
        ud["etapa"] = f"dia{day}"
        save_db()
    except Exception:
        logging.exception("No pude enviar followup")

# ============ COMANDOS ============
@bot.message_handler(commands=["start", "ayuda", "ping", "reset", "datos"])
def on_start(m):
    ud = get_ud(m.chat.id)
    cmd = m.text.split()[0].lower()
    if cmd == "/reset":
        user_data[str(m.chat.id)] = {
            "idioma": None, "stage": "lang", "nombre": None, "edad": None,
            "pais": None, "rol": None, "tema": None, "email": None,
            "etapa": "dia0", "compras": []
        }
        save_db()
        bot.reply_to(m, "🔄 Reinicié tu experiencia. Vamos de nuevo.", reply_markup=kb_lang())
        return
    if cmd == "/datos":
        bot.reply_to(m, f"```json\n{json.dumps(ud, ensure_ascii=False, indent=2)}\n```", parse_mode=None)
        return

    # /start /ayuda /ping → saludo / idioma
    if not ud["idioma"]:
        bot.reply_to(m, t("ES", "hello"), reply_markup=kb_lang())
    else:
        lang = ud["idioma"]
        bot.reply_to(m, t(lang, "thanks_name", n=ud["nombre"] or "🌸"))
        if ud["stage"] != "ready":
            advance_onboarding(m, ud)
        else:
            bot.reply_to(m, "Escríbeme cuando quieras 💌" if lang == "ES" else "Escreva quando quiser 💌", reply_markup=rmv())

# ============ MENSAJES ============
@bot.message_handler(func=lambda m: True, content_types=["text"])
def on_text(m):
    ud = get_ud(m.chat.id)
    txt = m.text.strip()

    # 1) Fijar idioma si no está
    if ud["stage"] == "lang":
        lang_guess = guess_lang_from_btn(txt)
        if lang_guess:
            ud["idioma"] = lang_guess
            ud["stage"] = "name"
            save_db()
            bot.reply_to(m, t(lang_guess, "ask_name"), reply_markup=rmv())
            return
        bot.reply_to(m, t("ES", "hello"), reply_markup=kb_lang())
        return

    lang = ud["idioma"] or "ES"

    # 2) Onboarding secuencial
    if ud["stage"] == "name":
        ud["nombre"] = txt.split()[0][:30]
        ud["stage"] = "age"
        save_db()
        bot.reply_to(m, t(lang, "ask_age"), reply_markup=kb_age(lang))
        return

    if ud["stage"] == "age":
        ud["edad"] = txt if any(k in txt for k in ["18", "26", "36", "46"]) else None
        ud["stage"] = "role"
        save_db()
        bot.reply_to(m, t(lang, "ask_role"), reply_markup=kb_role(lang))
        return

    if ud["stage"] == "role":
        ud["rol"] = normalize_role(lang, txt)
        ud["stage"] = "topic"
        save_db()
        bot.reply_to(m, t(lang, "ask_topic"), reply_markup=kb_topic(lang))
        return

    if ud["stage"] == "topic":
        ud["tema"] = normalize_topic(lang, txt)
        ud["stage"] = "email"
        save_db()
        bot.reply_to(m, t(lang, "ask_email"), reply_markup=rmv())
        return

    if ud["stage"] == "email":
        if is_email(txt):
            ud["email"] = txt
            ud["stage"] = "ready"
            ud["etapa"] = "dia1"
            save_db()

            # Envío de Guía + Envío a Mailer
            send_guide(m.chat.id, lang)
            send_to_mailer(ud, m.chat.id)

            tema_show = ud["tema"] or ("ansiedad" if lang == "ES" else "ansiedade")
            name_show = ud["nombre"] or ("amiga" if lang == "ES" else "amiga")
            bot.reply_to(m, t(lang, "done", n=name_show, tema=tema_show))
            # Programa secuencia D1–D4
            schedule_followups(m.chat.id)
            return
        else:
            bot.reply_to(m, t(lang, "invalid_email"))
            return

    # 3) Modo conversacional GPT con contexto
try:
    nombre = ud["nombre"] or ("amiga" if lang == "ES" else "amiga")
    tema = ud["tema"] or ("ansiedad" if lang == "ES" else "ansiedade")
    rol = ud["rol"] or ("madre" if lang == "ES" else "mãe")

    system_prompt = SYSTEM_PROMPT_BASE + (
        "\nResponde **en español**, breve (2–4 frases), tono cálido y claro. Personaliza usando el nombre cuando corresponda."
        if lang == "ES" else
        "\nResponda **em português**, curto (2–4 frases), tom caloroso e claro. Personalize usando o nome quando fizer sentido."
    )

    persona_context = (
        f"Contexto de usuaria: nombre={nombre}, edad={ud['edad']}, rol={rol}, "
        f"tema_principal={tema}, etapa={ud['etapa']}, email={'sí' if ud['email'] else 'no'}."
    )

except Exception as e:
    logging.error(f"Error preparando contexto GPT: {e}")
    persona_context = "Contexto vacío por error."

# 2) Texto del usuario, limpio y con límite
user_text = (m.text or "").strip()
if len(user_text) > 1000:
    user_text = user_text[:1000] + "…"

    # 3) Mensajes para el modelo
messages = [
    {"role": "system", "content": system_prompt},
    {"role": "system", "content": persona_context},
    {"role": "user", "content": user_text},
]

last_err = None
for attempt in range(3):  # hasta 3 intentos con backoff
    try:
        completion = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.6,
            max_tokens=400,
            timeout=20,  # evita que quede colgado mucho tiempo
        )
        answer = completion.choices[0].message.content.strip()
        bot.reply_to(m, answer)
        break

    except Exception as e:
        last_err = e
        logging.error(f"[GPT ERROR][try {attempt+1}/3] {repr(e)}\n{traceback.format_exc()}")
        time.sleep(1.5 * (attempt + 1))  # backoff progresivo

else:
    # <- este else ya está alineado con el for, no con el try
    lang = (get_ud(m.chat.id).get("idioma") or "ES")
    if lang == "ES":
        bot.reply_to(m, "Tuve un problemita al pensar 🤯. Probemos de nuevo en un momento.")
    else:
        bot.reply_to(m, "Tive um probleminha para pensar 🤯. Vamos tentar novamente em instantes.")
    return

def advance_onboarding(m, ud):
    lang = ud["idioma"] or "ES"
    stage = ud["stage"]
    if stage == "name":
        bot.reply_to(m, t(lang, "ask_name"), reply_markup=rmv())
    elif stage == "age":
        bot.reply_to(m, t(lang, "ask_age"), reply_markup=kb_age(lang))
    elif stage == "role":
        bot.reply_to(m, t(lang, "ask_role"), reply_markup=kb_role(lang))
    elif stage == "topic":
        bot.reply_to(m, t(lang, "ask_topic"), reply_markup=kb_topic(lang))
    elif stage == "email":
        bot.reply_to(m, t(lang, "ask_email"), reply_markup=rmv())
    else:
        bot.reply_to(m, "Seguimos 💌" if lang == "ES" else "Seguimos 💌")

if __name__ == "__main__":
    load_db()
    logging.info("✅ Bot multilingüe con memoria iniciado")
    scheduler.start()
    try:
        bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)
    finally:
        save_db()
        scheduler.shutdown(wait=False)











