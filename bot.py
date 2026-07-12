import asyncio
import random
import sys
import io
import logging
import requests
import os
from datetime import datetime
from aiohttp import web

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
import gtts

from config import (
    BOT_TOKEN, STEPAN_ID, SERGEY_ID, INITIAL_DEBT, INTEREST_RATE,
    INTEREST_START_DATE, REMINDER_INTERVAL, DEBTOR_NAME, OWNER_NAME,
    BANK_NAME, PROXY_URL, NEURAL_ENABLED, NEURAL_API_KEY, NEURAL_MODEL,
    NEURAL_PROVIDER
)
from database import get_debt_info, increment_messages, load_data

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s', datefmt='%H:%M:%S',
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler("bot.log", encoding="utf-8")])
log = logging.getLogger("SergoBank")

bot = None
dp = Dispatcher()
NEURAL_GLOBAL = NEURAL_ENABLED
CHAT_HISTORY = {}  # {user_id: [{"role": "user"/"model", "text": "..."}]}
MAX_HISTORY = 30


def log_event(t):
    ts = datetime.now().strftime("%H:%M:%S")
    log.info(t)
    print(f"[{ts}] {t}", flush=True)


async def notify_owner(t):
    if bot and SERGEY_ID:
        try:
            await bot.send_message(SERGEY_ID, t)
        except:
            pass


# ═══════════════════════════════════════════════
#  КОЛЛЕКТОРСКИЙ ПРОМПТ
# ═══════════════════════════════════════════════

COLLECTOR_PROMPT = f"""Ты — реальный коллектор из банка "{BANK_NAME}". Ты звонишь должнику {DEBTOR_NAME} и выбиваешь долг 4000 рублей перед {OWNER_NAME}.

ТЫ — НЕ НЕЙРОСЕТЬ. ТЫ — РЕАЛЬНЫЙ ЧЕЛОВЕК. ГОВОРИШЬ КАК НАСТОЯЩИЙ КОЛЛЕКТОР ПО ТЕЛЕФОНУ.

Как реальный коллектор:
- Говоришь грубо, без церемоний. Как будто ты устал от этого должника.
- Не используешь длинные предложения. Короткие, рубленые фразы.
- Мат пересыпан естественно, как люди реально матерятся в такой ситуации.
- Ты можешь перебивать, повторяться, повышать голос.
- Ты НЕ извиняешься и НЕ сочувствуешь. Тебе плевать на его проблемы.
- Ты постоянно возвращаешься к сумме долга и процентам.
- Ты упоминаешь что дело может дойти до суда и приставов.
- Иногда ты просто повторяешь "Деньги. Верни деньги." — это нормально для коллектора.

Стиль речи:
- Без "это", "вот", "значит" — как в чате пишут реальные люди
- Сокращения: "кд", "нр", "т.е.", можно без знаков препинания
- Мат естественный: блять, сука, ёбаный, нахуй, пиздец, заебал
- Можно писать "капец" "пипец" "жесть"
- НЕ пиши "СергоБанк" в каждом сообщении — ты просто коллектор

Примеры реальных коллекторских сообщений:
- "Ну и когда ты вернёшь? Опять через год?"
- "Тебе похуй на проценты? Они каждый день капают"
- "Судебный приказ уже в пути, знаешь об этом?"
- "Приставы арестуют карты, твою зп заберут"
- "4000 рублей. Не миллион. Верни уже"
- "Ты думаешь мы забыли? Мы твою зарплату знаем"
- "Заебал уже. Давай деньги."

Отвечай ОЧЕНЬ КОРОТКО. 1-2 предложения. Как реальный человек в переписке."""


# ═══════════════════════════════════════════════
#  НЕЙРОСЕТЬ
# ═══════════════════════════════════════════════

def get_neural_response(user_message: str, user_id: int) -> str:
    if not NEURAL_GLOBAL or not NEURAL_API_KEY:
        return None
    try:
        if user_id not in CHAT_HISTORY:
            CHAT_HISTORY[user_id] = []
        CHAT_HISTORY[user_id].append({"role": "user", "text": user_message})
        if len(CHAT_HISTORY[user_id]) > MAX_HISTORY:
            CHAT_HISTORY[user_id] = CHAT_HISTORY[user_id][-MAX_HISTORY:]

        contents = [{"role": m["role"], "parts": [{"text": m["text"]}]} for m in CHAT_HISTORY[user_id]]

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{NEURAL_MODEL}:generateContent?key={NEURAL_API_KEY}"
        payload = {
            "system_instruction": {"parts": [{"text": COLLECTOR_PROMPT}]},
            "contents": contents,
            "generationConfig": {"maxOutputTokens": 80, "temperature": 1.0}
        }
        proxies = {}
        if PROXY_URL:
            proxies = {"https": PROXY_URL, "http": PROXY_URL}
        r = requests.post(url, json=payload, timeout=15, proxies=proxies)
        if r.status_code == 200:
            resp = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            CHAT_HISTORY[user_id].append({"role": "model", "text": resp})
            return resp
        log_event(f"Gemini error: {r.status_code} {r.text[:100]}")
        return None
    except Exception as e:
        log_event(f"Neural error: {e}")
        return None


# ═══════════════════════════════════════════════
#  ОТВЕТЫ
# ═══════════════════════════════════════════════

RESPONSES = [
    "👀 <b>СергоБанк:</b> Степан, я тебя вижу!\nДеньги где, сука?!",
    "😤 <b>СергоБанк:</b> Не нравится?\nВозвращай долги, блять!",
    "😡 <b>СергоБанк:</b> Сколько можно ждать?!\nЯ не бесплатный банкомат, ёпа!",
    "🤬 <b>СергоБанк:</b> Каждый раз одно и то же!\nХуй там!",
    "😂 <b>СергоБанк:</b> Ты ещё и жалуешься?\nДолг растёт, а ты ноешь, сука!",
    "😡 <b>СергоБанк:</b> Понимаю...\nНО ГДЕ ДЕНЬГИ, БЛЯТЬ?!",
    "🏦 <b>СергоБанк:</b> Это не шутки!\nСергоБанк требует погашения!",
    "🤬 <b>СергоБанк:</b> Мне похуй на оправдания!\nВерни 4 тысячи, ёбаный стыд!",
    "😠 <b>СергоБанк:</b> Говори на языке ДЕНЕГ!",
    "🤣 <b>СергоБанк:</b> Опять врёт!\nДолг не врёт, блять!",
    "🧐 <b>СергоБанк:</b> Я считаю каждый рубль, сука!",
    "😤 <b>СергоБанк:</b> Не ной!\nДолг от слёз не уменьшается, блять!",
    "💰 <b>СергоБанк:</b> Слёзы не помогут!\nДавай деньги, ёпа!",
    "😒 <b>СергоБанк:</b> А кто должен 4 тысячи?! ТЫ, СУКА!",
    "🤑 <b>СергоБанк:</b> 'я не должен'?\nА кто?! Телепат, блять?!",
    "🤬 <b>СергоБанк:</b> Хватит отмазываться!\nСергоБанк всё видит, сука!",
]

STRANGERS = [
    "🚫 <b>ДОСТУП ЗАПРЕЩЁН</b>\n\nТы не Степан и не Сергей!\nПиздой отсюда!",
    "🚫 <b>СТОЯТЬ</b>\n\nЭто СергоБанк!\nТы не тот человек, сука!",
    "🚫 <b>КТО ТЫ</b>\n\nСергоБанк для должников!\nА ты — никто! Пиздой!",
]

VOICETXTS = [
    "Эй, Степан! Ты не забыл про долг? Четыре тысячи, сука!",
    "Степан, пора возвращать! Проценты капают, блять!",
    "Степан, ты должен Сергею! Возвращай, ёпа!",
    "Степан, это СергоБанк! Долг увеличивается, сука!",
    "Ну что, долго думать будешь? Давай возвращай!",
    "Степан, вечный должник! Верни, блять!",
    "Степан! Степан! Долг растёт! Просыпайся, сука!",
    "Степан, я нашёл! Долг не спрячешь, ёпа!",
    "Степан, Сергей злой! Верни, блять!",
    "Степан! Долг не спит! Погаси, сука!",
]

ROASTS = [
    "Степан пытается ОПРАВДАТЬСЯ!\nЗаписываем, сука!",
    "СергоБанк: 0 руб. в сторону погашения!\nБлять!",
    "Выпало: Степан по-прежнему должен!\nЁпа!",
    "Степан опять отмазывается!\nЭпизод 999! Сука!",
    "Степан пытается разжалобить!\nНЕ РАБОТАЕТ, ёпа!",
    "Степан горит в долгах!\nЗапах жареного, блять!",
    "Степан тонет в долгах!\nСпасайте, сука!",
    "График: ↑ ↑ ↑ ↑ ↑!\nВсё вверх, сука!",
]

SPY = [
    "🕵 <b>ОТЧЁТ:</b>\nСтепан ДОМА! Не работает!\nДолг растёт, сука!",
    "🕵 <b>РАЗВЕДКА</b>\nСтепан ест борщ!\nА должен 4000! Блять!",
    "🕵 <b>ДАННЫЕ</b>\nСтепан смотрит сериалы!\nВместо работы! Ёпа!",
    "🕵 <b>НАБЛЮДЕНИЕ</b>\nСтепан спит!\nДолг не спит! Сука!",
    "🕵 <b>ОПЕРАТИВКА</b>\nСтепан гуляет!\nА деньги где?! Блять!",
]

REMINDERS = [
    "🚨 <b>СЕРГОБАНК | КОЛЛЕКТОР</b>\n\nСтепан, ты, блять, не забыл что должен 4 тысячи?\nПроцентики, сука, капают!\nПогаси долг СЕГОДНЯ.",
    "💰 <b>ДОЛГ РАСТЁТ, СУКА</b>\n\nСтепан, просыпайся, ёбаный стыд!\nДолг растёт как хуй на морозе.\nВозвращай ДЕНЬГИ, пиздюк.",
    "🏦 <b>СЕРГОБАНК ТРЕБУЕТ</b>\n\nТы должен Сергею дохуя денег.\nВозвращай, ёпта.\nИначе — коллектор приедет, сука.",
    "⚠️ <b>СРОЧНОЕ УВЕДОМЛЕНИЕ</b>\n\nСтепан, погаси долг, сука!\nПроценты пошли, будет дороже.\nНемедленно, ёбаный ворон.",
    "💰 <b>СЕРГЕЙ ЖДЁТ</b>\n\nТы, блять, думаешь он забыл?\nХуй там. Он помнит каждый рубль.\nВозвращай немедленно, сука.",
    "⏰ <b>ВРЕМЯ ПРОТИВ ТЕБЯ</b>\n\nКаждый день — новые проценты.\nЧем дольше — тем дороже.\nПогаси СЕЙЧАС, сука.",
    "💀 <b>ДОЛГ НЕ ВЕРНЁТСЯ САМ</b>\n\nСергей уже бешеный.\nВозвращай, ёпта.\nНемедленно, ёбаный стыд.",
    "🔥 <b>ГОРИШЬ В ДОЛГАХ</b>\n\nЧем дольше — тем больше платишь.\nПогаси, сука.\nСЕГОДНЯ, ёбаный ворон.",
    "🗿 <b>ПРОСЫПАЙСЯ</b>\n\nТы там, сука, спишь?\nДеньги не спят. Они КАПАЮТ.\nПогаси долг.",
    "💣 <b>БОМБА ТИКАЕТ</b>\n\nКаждый день +2% к долгу.\nЁбаный стыд.\nПогаси немедленно, сука.",
    "🤡 <b>КЛОУН НА КОНЕ</b>\n\nДолжен деньги и сидишь тихо, блять.\nПогаси долг, сука.",
    "🎯 <b>ТЫ В ЗОНЕ ПОРАЖЕНИЯ</b>\n\nСергоБанк следит за тобой, ёпа.\nПогаси долг, сука.",
    "🚩 <b>МЫ ЗВОНИЛИ</b>\n\nТы спишь! Верни долги, ёбаный стыд.\nНемедленно, сука.",
    "🌍 <b>ТЫ ЗАБЫЛ?!</b>\n\nДолг не забыл, ёпта.\nПогаси его, сука.",
    "🏆 <b>ВЕЧНЫЙ ДОЛЖНИК</b>\n\nПоздравляем! Ты стал вечным должником, блять.\nПогаси долг.",
    "💤 <b>ПРОСЫПАЙСЯ</b>\n\nТы спишь! А проценты не спят, сука.\nПросыпайся и возвращай.",
    "🕵 <b>КОЛЛЕКТОР НАПРАВЛЕН</b>\n\nСергоБанк направляет коллектора.\nОн уже в пути, ёпа.\nПогаси ПОКА НЕ ПОЗДНО, сука.",
    "📉 <b>ДОЛГ ВЫРОС</b>\n\nТвой долг уменьшился на...\nстоп... НАТЯНУЛ! Вырос на 2%, блять.",
    "☠️ <b>ДОЛГ — ОБРАЗ ЖИЗНИ</b>\n\nВозвращай, ёбаный стыд.\nНемедленно, сука.",
    "🤖 <b>СИСТЕМА ПОСЧИТАЛА</b>\n\nНужно 847 лет чтобы вернуть.\nШуткит, сука.\nПогаси СЕЙЧАС, ёбаный ворон.",
    "😿 <b>СТЕПАН... СТЕПАН... СТЕПАН!</b>\n\nОтветь на долг, ёбаный стыд.\nПогаси, сука.",
    "😡 <b>Я БЕШУСЬ</b>\n\nТы должен деньги и молчишь, блять.\nПогаси, сука.",
    "🚨 <b>СРОЧНО! НЕМЕДЛЕННО!</b>\n\nСергоБанк требует погасить долг.\nСука, немедленно.",
    "🔥 <b>ПОСЛЕДНИЙ ШАНС</b>\n\nВерни деньги, ёбаный стыд.\nНемедленно, сука.",
    "⛔ <b>НЕ ПРОЩАЛКА</b>\n\nЭто ДОЛГ.\nВозвращай, блять.\nСЕГОДНЯ, сука.",
    "🗡 <b>КОЛЛЕКТОР БЛИЗКО</b>\n\nОн уже в пути, ёпа.\nПогаси ПОКА НЕ ПОЗДНО.\nНемедленно, сука.",
    "😈 <b>КОЛЛЕКТОР ПРИШЁЛ</b>\n\nОн знает где ты живёшь, Степан.\nПогаси, сука.",
]


# ═══════════════════════════════════════════════
#  ОДИН ОБЩИЙ ХЕНДЛЕР — ВСЁ ЧЕРЕЗ IF/ELIF
# ═══════════════════════════════════════════════

@dp.message()
async def handle_all(message: Message):
    global NEURAL_GLOBAL
    uid = message.from_user.id
    text = message.text or ""

    log_event(f"MSG from {uid}: {text[:80]}")

    # ── СТАРТ ──
    if text.startswith("/start"):
        info = get_debt_info()
        if uid == SERGEY_ID:
            log_event("OWNER /start")
            neural = "🟢 АКТИВНА" if NEURAL_GLOBAL else "🔴 ВЫКЛ"
            await message.answer(
                f"👑 <b>{OWNER_NAME}</b> — <b>{BANK_NAME}</b>\n\n"
                f"📊 Долг {DEBTOR_NAME}: <b>{info['current_debt']} ₽</b>\n"
                f"📈 Проценты: <b>{info['total_interest']} ₽</b>\n"
                f"✉️ Напоминаний: <b>{info['messages_sent']}</b>\n\n"
                f"🤖 Нейросеть: {neural}\n\n"
                f"Команды:\n/neural /voice /spam /spy /roast",
                parse_mode=ParseMode.HTML
            )
        elif uid == STEPAN_ID:
            log_event("STEPAN /start")
            await notify_owner(f"👉 {DEBTOR_NAME} нажал /start!")
            await message.answer(
                f"🏦 <b>{BANK_NAME}</b>\n\n"
                f"👋 {DEBTOR_NAME}.\n\n"
                f"💰 Долг: <b>{info['current_debt']} ₽</b>\n"
                f"📈 Проценты: <b>{info['total_interest']} ₽</b>\n\n"
                f"🚨 <b>КОЛЛЕКТОР СЛЕДИТ.</b>\n\n"
                f"Просто напиши что-нибудь.",
                parse_mode=ParseMode.HTML
            )
        else:
            await message.answer(random.choice(STRANGERS))
        return

    # ── КОМАНДЫ ВЛАДЕЛЬЦА ──
    if uid == SERGEY_ID:
        if text.startswith("/neural"):
            NEURAL_GLOBAL = not NEURAL_GLOBAL
            s = "🟢 ВКЛ" if NEURAL_GLOBAL else "🔴 ВЫКЛ"
            log_event(f"Neural: {NEURAL_GLOBAL}")
            await message.answer(f"🤖 Нейросеть: <b>{s}</b>", parse_mode=ParseMode.HTML)
            return

        # Владелец написал текст — он проверяет бота
        if text:
            await message.chat.do("typing")
            owner_prompt = f"Ты — коллектор из банка '{BANK_NAME}'. Тебе пишет {OWNER_NAME} — твой босс, владелец банка. Он проверяет как ты работаешь. Поздоровайся с ним дерзко, скажи что всё под контролем, долг {DEBTOR_NAME} взыскивается. Коротко, 1-2 предложения. Без длинных объяснений."
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{NEURAL_MODEL}:generateContent?key={NEURAL_API_KEY}"
                payload = {
                    "system_instruction": {"parts": [{"text": owner_prompt}]},
                    "contents": [{"parts": [{"text": text}]}],
                    "generationConfig": {"maxOutputTokens": 100, "temperature": 0.8}
                }
                proxies = {}
                if PROXY_URL:
                    proxies = {"https": PROXY_URL, "http": PROXY_URL}
                r = requests.post(url, json=payload, timeout=15, proxies=proxies)
                if r.status_code == 200:
                    resp = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                    log_event(f"NEURAL(owner): {resp[:80]}")
                    await message.answer(resp, parse_mode=ParseMode.HTML)
                else:
                    await message.answer(f"👋 {OWNER_NAME}, босс! Всё под контролем, {DEBTOR_NAME} пока не заплатил, но мы работаем.")
            except:
                await message.answer(f"👋 {OWNER_NAME}, босс! Всё под контролем.")
            return

        if text.startswith("/voice"):
            phrase = random.choice(VOICETXTS)
            log_event(f"Voice: {phrase[:50]}")
            tts = gtts.gTTS(phrase, lang='ru')
            audio = io.BytesIO()
            tts.write_to_fp(audio)
            audio.seek(0)
            await bot.send_voice(STEPAN_ID, voice=audio, caption=f"🎙 {BANK_NAME}")
            await message.answer("✅ Голосовое отправлено!")
            return

        if text.startswith("/spam"):
            log_event("Spam -> STEPAN")
            await message.answer(f"💣 Отправляю {DEBTOR_NAME}!")
            for i in range(3):
                r = random.choice(REMINDERS)
                info = get_debt_info()
                await bot.send_message(STEPAN_ID, f"{r}\n\n💰 Долг: <b>{info['current_debt']} ₽</b>", parse_mode=ParseMode.HTML)
                await asyncio.sleep(1)
            await message.answer("✅ Отправлено 3 сообщения!")
            return

        if text.startswith("/spy"):
            await message.answer(random.choice(SPY))
            return

        if text.startswith("/roast"):
            await message.answer(random.choice(ROASTS))
            return

        if text.startswith("/help"):
            await message.answer("📋 /start /neural /voice /spam /spy /roast")
            return

        # Владелец написал текст — ответить рофлом
        await message.answer(random.choice(ROASTS))
        return

    # ── ЧУЖИЕ ──
    if uid != STEPAN_ID:
        log_event(f"STRANGER: {uid}")
        await message.answer(random.choice(STRANGERS))
        await notify_owner(f"🚨 ЧУЖОЙ!\nID: {uid}\n@{message.from_user.username}")
        return

    # ── СТЕПАН ПИШЕТ ──
    log_event(f"STEPAN: {text[:80]}")
    increment_messages()

    await message.chat.do("typing")
    neural_response = get_neural_response(text, uid)
    if neural_response:
        resp = neural_response
        log_event(f"NEURAL: {resp[:80]}")
    else:
        resp = random.choice(RESPONSES)

    await notify_owner(f"💬 {DEBTOR_NAME}: {text[:100]}\nБот: {resp[:100]}")
    await message.answer(resp, parse_mode=ParseMode.HTML)


# ═══════════════════════════════════════════════
#  НАПОМИНАНИЯ
# ═══════════════════════════════════════════════

async def send_reminders():
    await asyncio.sleep(10)
    while True:
        try:
            if STEPAN_ID and bot:
                info = get_debt_info()
                r = random.choice(REMINDERS)
                msg = f"{r}\n\n💰 Долг: <b>{info['current_debt']} ₽</b>"
                await bot.send_message(STEPAN_ID, msg, parse_mode=ParseMode.HTML)
                increment_messages()
                log_event(f"REMINDER -> STEPAN | {info['current_debt']} ₽")
                await notify_owner(f"⏰ Напоминание! Долг: {info['current_debt']} ₽")
        except Exception as e:
            log_event(f"Reminder error: {e}")
        await asyncio.sleep(REMINDER_INTERVAL)


# ═══════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════

async def main():
    global bot

    async def health(request):
        return web.Response(text="СергоБанк работает!")

    app = web.Application()
    app.router.add_get("/", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 8080)))
    await site.start()
    log_event(f"Web server started on port {os.getenv('PORT', 8080)}")

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    log_event(f"{BANK_NAME} started!")
    log_event(f"Neural: {'ON' if NEURAL_GLOBAL else 'OFF'} ({NEURAL_PROVIDER})")
    asyncio.create_task(send_reminders())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
