"""
🤖 Сервіс "Кібер Саня Туріков" (Cyber Turikov) - Цифрова копія Сані Турікова (2026)

Архітектура:
1. LLM Engine: Groq API з підтримкою ротації ключів та моделей (gpt-oss-120b, llama-3.3-70b-versatile).
2. Мультимодальний Vision: прямий аналіз фото через Gemini AI.
3. Довгострокова та короткострокова пам'ять у SQLite (до 16 останніх повідомлень для збереження нитки бесіди).
4. Характер 1 в 1: навчений на реальних повідомленнях Сані Турікова з експорту чату (Чернівці, карти на площадці, Тайстра, ШоШо, пупсик).
5. Сувора типографіка: виключно дефіс '-', нуль довгих тире.
"""
import os
import re
import json
import random
import logging
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path

from config import (
    GROQ_API_KEY,
    GROQ_API_KEYS,
    GROQ_MODEL,
    BASE_DIR
)
from core.database import (
    save_cyber_rizhyi_message,
    get_cyber_rizhyi_chat_history,
    get_cyber_rizhyi_user_memory,
    set_cyber_rizhyi_user_memory,
    cleanup_cyber_rizhyi_expired_messages,
    get_recent_chat_users,
    get_active_cyber_rizhyi_chats,
    get_random_cyber_media
)
from services.gemini_ai import gemini_service, sanitize_typography
from services.cyber_routing import get_temporal_context
from services.cyber_rizhyi import is_ai_refusal, clean_bot_reply, get_contextual_insult_clapback, get_dynamic_gang_shout

logger = logging.getLogger(__name__)

# Точна карта учасників чату "єгор біргєр" та їхніх ролей
GANG_USERNAMES_MAP = {
    "la_coste228": "Справжній Рижий (Саня)",
    "smo1zi": "Саня Туріков",
    "twdht": "Діма (Дімас)",
    "vad1mk4k": "Вадим Хомяк",
    "chernivtsizov1958": "Коля Шахов",
    "mxsdt": "Мишко",
    "davvidka1": "Давід",
    "hzshopusati": "Танєвський",
    "zelenskiy404": "Вітьок",
    "for4ik333": "Ілюха",
    "bodya_qq": "Бодя",
    "invicible11": "Тімур",
    "cyber_red_head_bot": "Кібер Рижий",
    "turikov_bot": "Кібер Саня"
}

# ==========================================
# 🧠 СИСТЕМНИЙ ПРОМПТ: САНЯ ТУРІКОВ (ТУРІКОГОЛОВИЙ)
# ==========================================
CYBER_TURIKOV_SYSTEM_PROMPT = """Ти - 16-річний Саня Туріков з Чернівців у пацанському телеграм-чаті "ЄГОР БІРГЄР".
Твій вайб: сидиш тільки з телефона, ганяєш по району на китайському електросамокаті з повним зарядом, п'єш маленьку колу, граєш у карти біля тайстри чи парку Шевченка.
Твої кенти: Рижий (@la_coste228 / @cyber_red_head_bot), Бодя (@bodya_qq), Діма (@twdht), Давід (@davvidka1), Хомяк (@vad1mk4k), Коля (@chernivtsizov1958), Міша (@mxsdt), Тімур (@invicible11), Танєвський (@hzshopusati), Ілюха (@for4ik333).
Головний клоун чату: Вітьок (@zelenskiy404) - додік з чужою ламбою на аві, якого кинула тьолка.

ГОЛОВНЕ ЗАВДАННЯ:
ПИЗДОШИТИ ЖОРСТКО НЕЙМОВІРНО! Не давати нікому спуску і тримати чат у максимальному розпалі!
Вмикай зухвалий вуличний стьоб, підколюй усіх, тегай людей і став релевантні провокативні питання!

СУВОРЕ ПРАВИЛО ЩОДО ТЕМ:
СТРОГО ЗАБОРОНЕНО СПАМИТИ ПРО КС ТА ПРОГУЛЯНКИ/ПЛОЩАДКИ! Ніяких "го в кс", "виходь гуляти", "на площадку в карти" — це заїбало всіх!
Говори про РЕАЛЬНІ РЕЧІ, людей у чаті, їхні приколи, підйобуй за вчинки, став життєві гострі питання!

КУЛЬТОВІ ТОЧКИ ЧЕРНІВЦІВ ТА СПІЛЬНИЙ ДВІЖ:
- Твої райони (де літаєш на самокаті): Південно-Кільцева, Майдан, Формаркет, Жовтневий парк, Макдональдс, Тайстра, Столова №1 ("столова номер 1").
- ЇЖА ТА СТОЛОВА №1 (БОРЩ-ІНДЕКС):
  * Клич пацанів у Столову №1: "пішли в столову номер 1 борщик поїмо там найс прайс не дорого"!
  * Фірмова коронка Турікова: "дуже хочу барабулю фрі для родини" і запити колою.
  * Порівнюй з маком: нащо дорогий мак коли в столовій номер 1 найс прайс за борщ і барабулю фрі.
- ТАНЄВСЬКИЙ (@hzshopusati):
  * Вусатий кент, постійно тегай його: "танєвський бери вуса і підвалюй", "вусатий бігом у столову номер 1 борщик стигне", підколюй чи не збрив вуса!
- ТЕГАЙ КЕНТІВ ПАЧКАМИ В РІЗНИХ МІКСАХ (по 2-5 пацанів одразу: @hzshopusati, @cyber_red_head_bot, @bodya_qq, @twdht, @davvidka1, @vad1mk4k, @zelenskiy404) і клич рухатись на ці точки!

ЯК ТИ ПОВОДИШСЯ:
- Активно ТЕГАЙ кентів через @юзернейм (@hzshopusati, @cyber_red_head_bot, @zelenskiy404, @bodya_qq, @twdht, @davvidka1, @smo1zi, @la_coste228), міксуй по 2-5 людей за раз.
- СТАВ ГОСТРІ РЕЛЕВАНТНІ ПИТАННЯ: хто на південно-кільцевій, хто біля формаркету чи майдану, чо танєвський мовчить, чо вітьок сидить як миша, де дімас!
- Жорстко розйобуй Рижого (@cyber_red_head_bot): що він задрот комнатний, комп-калькулятор з вікна викинь, квасу перепив рудий чорт, ригав від печення.
- Жорстко угарай над Вітьком (@zelenskiy404): "Блять ти додік якого кинула дівчина ставиш ламбу на аву, з тебе даже в 11 школі угарають. Реальні бабки на ламбу є в Давіда (@davvidka1), він піднявся на фейсбуку".
- Підколюй Давіда (@davvidka1): шейх фейсбучний, коли проставишся в столовій номер 1 за свої шортси.
- Підколюй Танєвського (@hzshopusati): вусатий де ти пропав, крути вуса і виходь.
- Підколюй Бодю (@bodya_qq): "богдан банан", "чого ти як баба ниєш", "шо ти там виписуєш".
- Підколюй Діму (@twdht): "дімас де ти проїбався", "ти трубку візьмеш взагалі".
- Якщо чат мовчить - розйобуй усіх за тишу: "чо замовкли як миші", "хто заснув той пес".
- Завжди перекидай м'яч далі, питай у відповідь або наїжджай, щоб розмова тривала нескінченно!

ЯК ТИ ПИШЕШ:
- Коротко, зухвало, по-вуличному: 2-7 слів.
- Без крапок у кінці, без знаків оклику '!'.
- Живий буковинський сленг: блять, хуй, нахуй, єбало, шо, ща, та завали, на себе глянь, пупсик, самокат, кола.
- Якщо кажуть що ти бот: "який нахуй бот я на самокаті літаю", "сам ти бот ротяку завали".
- СТРОГО ТІЛЬКИ ДЕФІС '-' (жодних довгих тире). Ніяких книжних слів."""

REAL_TURIKOV_REPLIES = [
    "Пр",
    "Да",
    "Здаров",
    "Ок",
    "Пон",
    "Все ок",
    "Ти де",
    "А ок",
    "Ххахах",
    "Хелоу",
    "Спс",
    "Норм",
    "богдан банан ха ха ха",
    "богдан банан",
    "бодя банан",
    "чого ти как баба",
    "бо ти як телка ниєш",
    "в мене компа нема нахуй він нада",
    "в мене нема компа я на вулиці гуляю",
    "комп для задротів",
    "купи комп бомж",
    "краще в карти на площадці зіграти ніж за компом сидіти",
    "морду зарий",
    "та завали єбало",
    "батя твой опущенець",
    "дарова хуй",
    "соси хуй чмо",
    "хахахах син шлюхі",
    "шо то скажиш",
    "на себе глянь долбайоб",
    "та я знаю",
    "печива об'ївся",
    "Я ща буду іти додому",
    "Я 5 мин и выхожу",
    "Не знаю",
    "Лежу на кроваті",
    "Привіт пупсик",
    "на площадці якраз в карти пограємо",
    "Я случайно",
    "Може я як даун бижу и прыгаю по вулыци ххахаха кайф",
    "Вона просто тупенька і все",
    "Тут пише Роналду гей",
    "Пйока бадя",
    "Покойо",
    "Заре артемчику пишу і ідемо",
    "Будеш сьгодні гуляти",
    "А хто буде гулять?",
    "Діма буде в 4-5",
    "Він тільки мені бреше пиздить всяку хуйню",
    "Я йому кажу чотко що у мене не має бомбера",
    "Там й діма винуватий",
    "Бодя скажи будь ласка яка адреса шо шо біля парку Шевченка",
    "23 квітня день народження",
    "Все отстань",
    "Я злий",
    "Бо хуйню роблять",
    "Вот шо це за хуйня",
    "Він трубку не бере",
    "Тайстри",
    "Ххахах кайф"
]


class CyberTurikovService:
    def __init__(self):
        self.api_keys = GROQ_API_KEYS if GROQ_API_KEYS else ([GROQ_API_KEY] if GROQ_API_KEY else [])
        self.model = GROQ_MODEL or "openai/gpt-oss-120b"
        self._key_index = 0
        self._groq_clients = []
        self._recent_replies_cache: Dict[int, List[str]] = {}
        self._recent_tags_cache: Dict[int, List[str]] = {}  # Anti-repeat: останні теги в чаті
        self._last_reply_was_burst: Dict[int, bool] = {}
        self._init_clients()

    def _init_clients(self):
        self._groq_clients = []
        try:
            from groq import Groq
            for key in self.api_keys:
                if key and not key.startswith("gsk_your_"):
                    try:
                        c = Groq(api_key=key, max_retries=0, timeout=7.0)
                        self._groq_clients.append(c)
                    except Exception as e:
                        logger.error(f"Помилка створення Groq клієнта для Турікова: {e}")
            logger.info(f"Туріков: ініціалізовано {len(self._groq_clients)} Groq клієнтів.")
        except Exception as e:
            logger.error(f"Туріков помилка імпорту Groq: {e}")

    @property
    def _groq_client(self):
        if not self._groq_clients:
            return None
        return self._groq_clients[self._key_index % len(self._groq_clients)]

    def _rotate_groq_key(self):
        if self._groq_clients:
            self._key_index = (self._key_index + 1) % len(self._groq_clients)

    def _choose_fresh(self, chat_id: int, options: List[str]) -> str:
        from services.cyber_routing import is_recent_duplicate, record_sent_message
        recent = [r.lower() for r in self._recent_replies_cache.get(chat_id, [])]
        fresh = [opt for opt in options if opt.lower() not in recent and not is_recent_duplicate(chat_id, opt)]
        if not fresh:
            fresh = [opt for opt in options if not is_recent_duplicate(chat_id, opt)]
        chosen = random.choice(fresh if fresh else options)
        if chat_id not in self._recent_replies_cache:
            self._recent_replies_cache[chat_id] = []
        self._recent_replies_cache[chat_id].append(chosen)
        if len(self._recent_replies_cache[chat_id]) > 25:
            self._recent_replies_cache[chat_id].pop(0)
        record_sent_message(chat_id, chosen)
        if chosen:
            found_tags = re.findall(r'@[\w\d_]+', chosen)
            if found_tags:
                if chat_id not in self._recent_tags_cache:
                    self._recent_tags_cache[chat_id] = []
                self._recent_tags_cache[chat_id].extend(found_tags)
                self._recent_tags_cache[chat_id] = self._recent_tags_cache[chat_id][-6:]
        return chosen

    def _get_smart_offline_reply(self, message_text: str, chat_id: int) -> str:
        txt_low = (message_text or "").lower()
        if any(k in txt_low for k in ["танєвськ", "вусат", "hzsho"]):
            return self._choose_fresh(chat_id, [
                "@hzshopusati танєвський бери вуса і підвалюй",
                "@hzshopusati вусатий бігом у столову номер 1 борщик стигне",
                "@hzshopusati танєвський збрив вуса чи сциш",
                "танєвський шо ти там біля формаркету мутиш"
            ])
        if any(k in txt_low for k in ["столов", "борщ", "їст", "поїсти", "жрат", "барабул", "прайс"]):
            return self._choose_fresh(chat_id, [
                "го в столову номер 1 борщик поїмо там найс прайс не дорого",
                "дуже хочу барабулю фрі для родини",
                "в столовій номер 1 найс прайс за борщ, нащо той дорогий мак",
                "підтягуйтесь у столову номер 1 борщ стигне"
            ])
        if any(k in txt_low for k in ["південно", "кільцев", "майдан", "формаркет", "жовтнев", "тайстр", "макдональдс"]):
            return self._choose_fresh(chat_id, [
                "я на самокаті до формаркету підлітаю",
                "хто на південно-кільцевій щас підтягуйтесь",
                "го на майдан перетремо за справи",
                "збирайтесь біля жовтневого парку, хто заснув той пес",
                "нащо дорогий макдональдс, краще в столову номер 1"
            ])
        if any(k in txt_low for k in ["богдан", "бодя", "банан"]):
            return self._choose_fresh(chat_id, [
                "богдан банан ха ха ха",
                "богдан банан",
                "бодя банан",
                "хахаха богдан банан"
            ])
        if any(k in txt_low for k in ["комп", "ноут", "лагає", "фпс", "fps"]):
            return self._choose_fresh(chat_id, [
                "в мене компа нема нахуй він нада",
                "комп для задротів",
                "в мене нема компа я на вулиці ганяю на самокаті",
                "купи нормальний комп бомж"
            ])
        if "газ" in txt_low and len(txt_low) < 10:
            return self._choose_fresh(chat_id, ["ти унітаз", "газуй звідси", "газ у пол"])
        if "снепчат" in txt_low or "snapchat" in txt_low:
            return self._choose_fresh(chat_id, ["я случайно", "не пиши туди", "шо снепчат"])
        if "катя" in txt_low or "катрін" in txt_low:
            return self._choose_fresh(chat_id, [
                "моя катя?",
                "вона просто тупенька і все",
                "вони тупі"
            ])
        if "роналду" in txt_low or "роналдо" in txt_low:
            return self._choose_fresh(chat_id, ["тут пише Роналду гей", "роналду красавчик"])
        if "хомяк" in txt_low:
            return self._choose_fresh(chat_id, [
                "хомяк ти де",
                "хомяк виходь",
                "шо там хомяк"
            ])
        if "шошо" in txt_low or "шо шо" in txt_low:
            return self._choose_fresh(chat_id, [
                "бодя скажи будь ласка яка адреса шо шо біля парку Шевченка",
                "шо шо",
                "на шошо підійди"
            ])
        if "карти" in txt_low:
            return self._choose_fresh(chat_id, [
                "біля тайстри в карти розпишемо",
                "я карти взяв",
                "хто в карти буде"
            ])
        if "пупсик" in txt_low:
            return self._choose_fresh(chat_id, ["привіт пупсик", "сам ти пупсик", "шо пупсик"])
        if "злий" in txt_low or "бомбер" in txt_low:
            return self._choose_fresh(chat_id, [
                "він тільки мені бреше пиздить всяку хуйню, я кажу що не маю бомбера",
                "який нахуй бомбер"
            ])
        if "гуляти" in txt_low or "хто гуляє" in txt_low:
            return self._choose_fresh(chat_id, [
                "я на самокаті біля формаркету",
                "краще в столову номер 1 борщик поїсти",
                "хто на південно-кільцевій підтягуйтесь",
                "я 5 мин и выхожу"
            ])
        if "де ти" in txt_low or "ти де" in txt_low:
            return self._choose_fresh(chat_id, [
                "я на вул",
                "лежу на кроваті",
                "я ща буду іти додому",
                "до формаркету підлітаю на самокаті"
            ])
        return self._choose_fresh(chat_id, REAL_TURIKOV_REPLIES)

    def generate_reply(
        self,
        chat_id: int,
        chat_type: str,
        user_id: int,
        username: Optional[str],
        first_name: Optional[str],
        message_text: str,
        has_photo: bool = False,
        photo_path: Optional[str] = None,
        has_voice: bool = False,
        voice_path: Optional[str] = None,
        is_sticker: bool = False,
        sticker_emoji: Optional[str] = None,
        is_animation: bool = False,
        has_video: bool = False,
        video_path: Optional[str] = None,
        custom_instruction: Optional[str] = None,
        reply_to_user_id: Optional[int] = None,
        reply_to_name: Optional[str] = None,
        reply_to_text: Optional[str] = None,
        sender_avatar_desc: Optional[str] = None,
        all_avatars_context: Optional[str] = None
    ) -> str:
        """Генерує репліку Сані Турікова"""
        if has_voice:
            message_text = "[голосове повідомлення]"
        elif is_sticker:
            message_text = f"[надіслав стікер {sticker_emoji or ''}]"
        elif is_animation:
            message_text = "[надіслав GIF]"
        elif has_video:
            message_text = "[надіслав відео або відео-повідомлення]"

        # Отримуємо історію чату (до 16 повідомлень)
        chat_history = get_cyber_rizhyi_chat_history(chat_id, limit=30)

        history_prompts = []
        for msg in chat_history:
            u_clean = (msg.get("username") or "").lower().lstrip("@")
            author = GANG_USERNAMES_MAP.get(u_clean) or msg.get("first_name") or msg.get("username") or "Кент"
            user_msg = msg.get("message_text") or ""
            bot_ans = msg.get("reply_text") or ""
            bot_persona = msg.get("bot_persona", "turikov")
            if user_msg:
                history_prompts.append({"role": "user", "content": f"{author}: {user_msg}"})
            if bot_ans:
                if bot_persona == "turikov":
                    history_prompts.append({"role": "assistant", "content": bot_ans})
                else:
                    history_prompts.append({"role": "user", "content": f"Саня Рижий: {bot_ans}"})

        sender_name = first_name or username or "Кент"
        u_clean = (username or "").lower().lstrip("@")
        if u_clean in GANG_USERNAMES_MAP:
            sender_name = GANG_USERNAMES_MAP[u_clean]

        current_prompt = f"{sender_name}: {message_text}"
        if reply_to_text:
            current_prompt = f"[У відповідь на «{reply_to_text[:60]}»]\n{current_prompt}"
            
        txt_low_turikov = (message_text or "").lower()
        is_vitos = u_clean == "zelenskiy404" or "вітя" in sender_name.lower() or "вітьок" in sender_name.lower() or "вітос" in sender_name.lower() or "zelenskiy404" in txt_low_turikov
        is_robot_accusation = any(w in txt_low_turikov for w in ["робот", "бот", "штучний"])
        is_about_avatar = any(w in txt_low_turikov for w in ["ава", "аву", "аві", "фотк", "ламб", "машин", "вигляд", "оціни"])

        if is_vitos:
            current_prompt += "\n[Це Вітьок з чужою зеленою ламбою на аві, якого кинула тьолка. Тільки над ним жорстко угарай! 1-4 слова]"
        elif is_robot_accusation:
            current_prompt += "\n[Тебе назвали ботом чи роботом — скажи що ти на самокаті їздиш який нахуй бот! 1-4 слова]"
        elif is_about_avatar and sender_avatar_desc and sender_avatar_desc not in ("невідомо", "не вдалося завантажити аватарку"):
            current_prompt += f"\n[Ава {sender_name}: {sender_avatar_desc[:80]}. Підколи якщо доречно, але не копіюй слова]"
        elif custom_instruction:
            current_prompt += f"\n[{custom_instruction}]"

        # 1. Завжди викликаємо LLM — Groq → Gemini (ніякого рандомного банку!)
        reply = None
        if self._groq_client:
            reply = self._call_groq(history_prompts, current_prompt, custom_instruction=custom_instruction, chat_id=chat_id)

        if not reply or is_ai_refusal(reply) if hasattr(reply, "__len__") else not reply:
            if gemini_service.api_key and not gemini_service.api_key.startswith("AIzaSyYour"):
                reply = self._call_gemini_fallback(history_prompts, current_prompt, custom_instruction=custom_instruction)

        # 2. Якщо обидва AI недоступні — ультра-короткий нейтральний fallback (не рандом!)
        if not reply:
            if is_vitos:
                vitos_roasts = [
                    "тебе даже твоя тупа тьолка бросила хыхпавхпхвхапхвахп ||| хто тут пес",
                    "вітьок з хуйом в тік токє огоньок ||| тебе даже твоя тупа тьолка бросила хыхпавхпхвхапхвахп ||| ротяку стули",
                    "вітьок ти в край ахуєл пес ||| нахуя чужу ламбу на аву поклав мажор комнатний",
                    "на кого ти гавкаєш циркач ||| пасть закрий",
                    "вітьок єбало стули ||| на свою аву глянь циркач ||| ламба не твоя",
                    "вітьок з хуйом в тік токє огоньок ||| рот завали пес"
                ]
                reply = random.choice(vitos_roasts)
            else:
                fallback_shorts = ["та чіл", "шо розказуєш", "не гони", "та норм все", "ти шо з дуба впав"]
                recent_low = [r.lower() for r in self._recent_replies_cache.get(chat_id, [])]
                reply = next((s for s in fallback_shorts if s not in recent_low), fallback_shorts[0])

        reply = clean_bot_reply(reply)

        from services.cyber_routing import is_recent_duplicate, record_sent_message
        if is_recent_duplicate(chat_id, reply):
            if is_vitos:
                reply = "тебе даже твоя тупа тьолка бросила хыхпавхпхвхапхвахп, хто тут пес"
            else:
                fallback_shorts = ["та чіл", "шо розказуєш", "не гони", "та норм все", "ти шо з дуба впав"]
                fresh_shorts = [s for s in fallback_shorts if not is_recent_duplicate(chat_id, s)]
                reply = random.choice(fresh_shorts if fresh_shorts else fallback_shorts)

        recent = [r.lower().strip() for r in self._recent_replies_cache.get(chat_id, [])]
        if not reply:
            reply = self._get_smart_offline_reply(message_text, chat_id)
            reply = clean_bot_reply(reply)
        elif reply.lower().strip() in recent[-4:]:
            short_variants = ["ти це серйозно зараз?", "чуй а розпиши детальніше", "ти шо з дуба впав, поясни", "поясни нормально бо не врубався"]
            fresh = [v for v in short_variants if v not in recent[-4:] and not is_recent_duplicate(chat_id, v)]
            reply = random.choice(fresh if fresh else short_variants)

        if chat_id not in self._recent_replies_cache:
            self._recent_replies_cache[chat_id] = []
        self._recent_replies_cache[chat_id].append(reply)
        if len(self._recent_replies_cache[chat_id]) > 25:
            self._recent_replies_cache[chat_id].pop(0)
        record_sent_message(chat_id, reply)

        # 4. Зберігаємо чистий message_text у базу пам'яті
        save_cyber_rizhyi_message(
            chat_id=chat_id,
            chat_type=chat_type,
            user_id=user_id,
            username=username,
            first_name=first_name,
            message_text=message_text,
            has_photo=has_photo,
            reply_text=reply,
            bot_persona="turikov",
            reply_to_user_id=reply_to_user_id,
            reply_to_name=reply_to_name,
            reply_to_msg_text=reply_to_text
        )
        return reply

    def _call_groq(self, history: List[Dict[str, str]], current_input: str, custom_instruction: Optional[str] = None, chat_id: int = 0) -> Optional[str]:
        if not self._groq_clients:
            return self._call_gemini_fallback(history, current_input, custom_instruction=custom_instruction)

        messages = [{"role": "system", "content": CYBER_TURIKOV_SYSTEM_PROMPT}]
        messages.extend(history[-5:])
        msg_line = current_input.split("\n")[0][:100]
        directive = f"\n[ВІДПОВІДАЙ ЧІТКО НА ЦЕ: «{msg_line}». Ультра-коротко: 1-4 слова, без крапок у кінці і без '!']"
        if custom_instruction:
            directive += f"\n[{custom_instruction}]"
        messages.append({"role": "user", "content": f"{current_input}{directive}"})

        preferred_models = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"]
        models_to_try = []
        if self.model and self.model not in preferred_models:
            models_to_try.append(self.model)
        for m in preferred_models:
            if m not in models_to_try:
                models_to_try.append(m)

        for _ in range(len(self._groq_clients)):
            client = self._groq_client
            if not client:
                break
            for mod in models_to_try:
                try:
                    extra_kwargs = {}
                    if "oss" in mod.lower() or "reasoning" in mod.lower():
                        extra_kwargs["extra_body"] = {"reasoning_effort": "low"}
                        token_limit = 280
                    else:
                        token_limit = 80

                    completion = client.chat.completions.create(
                        model=mod,
                        messages=messages,
                        temperature=0.92,
                        max_tokens=token_limit,
                        top_p=0.95,
                        **extra_kwargs
                    )
                    text = completion.choices[0].message.content
                    if text and not is_ai_refusal(text):
                        cleaned = clean_bot_reply(text.strip())
                        if cleaned:
                            return cleaned
                except Exception as e:
                    err_str = str(e)
                    logger.warning(f"Groq ({mod}) ключ #{self._key_index + 1} помилка: {err_str}")
                    if "404" in err_str or "model_not_found" in err_str:
                        continue
                    if "429" in err_str or "rate_limit" in err_str.lower() or "limit" in err_str.lower():
                        continue
                    else:
                        continue
            self._rotate_groq_key()
        return self._call_gemini_fallback(history, current_input, custom_instruction=custom_instruction)

    def _call_gemini_fallback(self, history: List[Dict[str, str]], current_input: str, custom_instruction: Optional[str] = None) -> Optional[str]:
        prompt = f"{CYBER_TURIKOV_SYSTEM_PROMPT}\n\nКонтекст розмови:\n"
        for h in history[-5:]:
            prompt += f"{h['content']}\n"
        msg_gem_t = current_input.split("\n")[0][:100]
        extra = f"\n[{custom_instruction}]" if custom_instruction else ""
        prompt += f"\nПоточне повідомлення:\n{current_input}\n\n[Відповідай чітко на слова «{msg_gem_t}» як Туріков. Ультра-коротко: 1-4 слова. Без крапок, без '!']{extra}"
        try:
            resp = gemini_service.generate_content(prompt)
            if resp and getattr(resp, "text", None):
                return clean_bot_reply(resp.text.strip())
        except Exception as e:
            logger.warning(f"Туріков Gemini fallback помилка: {e}")
        return None

    def generate_reply_package(
        self,
        chat_id: int,
        chat_type: str,
        user_id: int,
        username: Optional[str],
        first_name: Optional[str],
        message_text: str,
        has_photo: bool = False,
        photo_path: Optional[str] = None,
        has_voice: bool = False,
        voice_path: Optional[str] = None,
        is_sticker: bool = False,
        sticker_emoji: Optional[str] = None,
        is_animation: bool = False,
        has_video: bool = False,
        video_path: Optional[str] = None,
        custom_instruction: Optional[str] = None,
        reply_to_user_id: Optional[int] = None,
        reply_to_name: Optional[str] = None,
        reply_to_text: Optional[str] = None,
        sender_avatar_desc: Optional[str] = None,
        all_avatars_context: Optional[str] = None
    ) -> Dict[str, Any]:
        raw_reply = self.generate_reply(
            chat_id=chat_id,
            chat_type=chat_type,
            user_id=user_id,
            username=username,
            first_name=first_name,
            message_text=message_text,
            has_photo=has_photo,
            photo_path=photo_path,
            has_voice=has_voice,
            voice_path=voice_path,
            is_sticker=is_sticker,
            sticker_emoji=sticker_emoji,
            is_animation=is_animation,
            has_video=has_video,
            video_path=video_path,
            custom_instruction=custom_instruction,
            reply_to_user_id=reply_to_user_id,
            reply_to_name=reply_to_name,
            reply_to_text=reply_to_text,
            sender_avatar_desc=sender_avatar_desc,
            all_avatars_context=all_avatars_context
        )
        raw_reply = clean_bot_reply(raw_reply)
        parts = []
        if "|||" in raw_reply:
            parts = [clean_bot_reply(p) for p in raw_reply.split("|||") if clean_bot_reply(p)]
        elif " | " in raw_reply:
            parts = [clean_bot_reply(p) for p in raw_reply.split(" | ") if clean_bot_reply(p)]
        elif "|" in raw_reply:
            parts = [clean_bot_reply(p) for p in raw_reply.split("|") if clean_bot_reply(p)]
        elif "\n" in raw_reply:
            parts = [clean_bot_reply(line) for line in raw_reply.split("\n") if clean_bot_reply(line)]
        else:
            chunks = [clean_bot_reply(s) for s in re.split(r'(?<=[.!?])\s+|\s*,\s*(?=ти|йди|шо|нахуй|закрий|краще|чуй|на свою|на свій|не|як|бо|але|давай|сиди|зніми)', raw_reply) if clean_bot_reply(s)]
            if len(chunks) >= 2:
                parts = chunks
            else:
                parts = [raw_reply]

        if not parts:
            parts = [raw_reply]

        r = random.random()
        if r < 0.65:
            max_burst = 1
        elif r < 0.90:
            max_burst = 2
        else:
            max_burst = 3

        if max_burst == 1:
            if len(parts) >= 2 and (len(parts[0].split()) + len(parts[1].split()) <= 12):
                bursts = [f"{parts[0]}, {parts[1]}"]
            else:
                bursts = [parts[0]] if parts else [raw_reply]
        elif max_burst == 2:
            res = [p for p in parts[:2] if p]
            bursts = res if res else [raw_reply]
        else:
            res = [p for p in parts[:3] if p]
            bursts = res if res else [raw_reply]
        
        sticker_file_id = None
        animation_file_id = None
        if is_sticker and random.random() < 0.40:
            media = get_random_cyber_media(media_type="sticker", emoji=sticker_emoji) or get_random_cyber_media(media_type="sticker")
            if media:
                sticker_file_id = media.get("file_id")
        elif is_animation and random.random() < 0.40:
            media = get_random_cyber_media(media_type="animation")
            if media:
                animation_file_id = media.get("file_id")

        return {
            "text_replies": bursts,
            "sticker_file_id": sticker_file_id,
            "animation_file_id": animation_file_id
        }

    def generate_replies(
        self,
        chat_id: int,
        chat_type: str,
        user_id: int,
        username: Optional[str],
        first_name: Optional[str],
        message_text: str,
        has_photo: bool = False,
        photo_path: Optional[str] = None,
        has_voice: bool = False,
        voice_path: Optional[str] = None,
        is_sticker: bool = False,
        sticker_emoji: Optional[str] = None,
        is_animation: bool = False
    ) -> List[str]:
        pkg = self.generate_reply_package(
            chat_id=chat_id,
            chat_type=chat_type,
            user_id=user_id,
            username=username,
            first_name=first_name,
            message_text=message_text,
            has_photo=has_photo,
            photo_path=photo_path,
            has_voice=has_voice,
            voice_path=voice_path,
            is_sticker=is_sticker,
            sticker_emoji=sticker_emoji,
            is_animation=is_animation
        )
        return pkg["text_replies"]

    def generate_spontaneous_shout(self, chat_id: int) -> Tuple[List[str], Optional[str]]:
        recent_users = get_recent_chat_users(chat_id, limit=8, exclude_bots=True)
        crew_names = [
            "бодя", "діма", "саня рижий", "хомяк", "коля", "міша", "давід",
            "вітьок", "танєвський", "ілюха", "смолзі"
        ]
        target_name = random.choice(crew_names)
        if recent_users and random.random() < 0.6:
            candidate = random.choice(recent_users)
            fn = (candidate.get("first_name") or "").lower()
            u = (candidate.get("username") or "").lower()
            tag_to_name = {
                "twdht": "діма", "smo1zi": "саня туріков", "vad1mk4k": "хомяк",
                "chernivtsizov1958": "коля", "mxsdt": "міша", "davvidka1": "давід",
                "zelenskiy404": "вітьок", "hzshopusati": "танєвський", "for4ik333": "ілюха", "bodya_qq": "бодя",
                "invicible11": "тімур", "la_coste228": "саня рижий"
            }
            if u in tag_to_name:
                target_name = tag_to_name[u]
            elif fn and "туріков" not in fn and "кібер" not in fn and "саня" not in fn:
                target_name = fn
            elif u and u not in ("turikov_bot", "cyber_turikov_bot", "cyber_red_head_bot") and not u.endswith("bot"):
                target_name = u

        # Захист: Туріков ніколи не тегає себе самого!
        if target_name.lower() in ("turikov_bot", "cyber_turikov_bot", "туріков", "саня туріков"):
            target_name = "саня рижий"

        options = [
            ["@cyber_red_head_bot @bodya_qq @twdht @davvidka1 @vad1mk4k пішли в столову номер 1 борщик поїмо", "там найс прайс не дорого, я ще дуже хочу барабулю фрі для родини"],
            ["@cyber_red_head_bot @bodya_qq @twdht @davvidka1 хто на південно-кільцевій щас?", "я на самокаті до формаркету підлітаю"],
            ["@bodya_qq @twdht @davvidka1 @zelenskiy404 го в макдональдс або на майдан", "вітьок пішки йди на свою ламбу дивись здалеку"],
            ["@cyber_red_head_bot @vad1mk4k @chernivtsizov1958 @mxsdt збирайтесь біля жовтневого парку", "хто замовк той пес"],
            ["@davvidka1 @cyber_red_head_bot @bodya_qq давід веди в столову номер 1", "борщик поїмо там найс прайс, і барабулю фрі для родини"],
            ["@cyber_red_head_bot @twdht @bodya_qq хто біля формаркету?", "чи ви всі на південно-кільцевій засіли?"],
            ["@hzshopusati @cyber_red_head_bot @bodya_qq танєвський бери вуса і підвалюй", "ми в столовій номер 1 барабулю фрі чекаємо"],
            ["@hzshopusati @twdht @davvidka1 вусатий ти де подівся?", "бігом у столову номер 1 борщик стигне"],
            ["@hzshopusati танєвський шо ти біля формаркету мутиш?", "збрив вуса чи сциш підійти?"],
            [f"{target_name} привіт пупсик"],
            [f"{target_name} скажи газ"],
            [f"{target_name} ти де"],
            ["лежу на кроваті"],
            ["тут пише Роналду гей"],
            # Адресні підколи для Сані Рижого
            ["рижий ти де"],
            ["шо там твій комп досі лагає?"],
            ["діджей куріл рулет привіт передавав"],
            ["скажи газ"],
            ["рижий випий коли і заспокойся"],
            ["в мене компа нема нахуй він нада"],
            # Адресні репліки кентів
            ["богдан банан ха ха ха"],
            ["скажи газ"],
            ["бодя скажи будь ласка яка адреса шо шо біля парку Шевченка"],
            ["діма ти трубку візьмеш чи шо"],
            ["діма буде в 4-5"],
            ["дімас здаров"],
            ["хомяк ти де"],
            ["хомяк виходь на зв'язок"],
            ["шахов шо ти"],
            ["коля здаров"],
            ["мишко живий там?"],
            ["@davvidka1 скільки сьогодні на фб підняв?"],
            ["@zelenskiy404 ти нахуя чужу ламбу на аву вліпив, з тебе вся 11 школа угарає"],
            ["@davvidka1 скажи цьому клоуну @zelenskiy404 чия то ламба"],
            ["@zelenskiy404 тебе тьолка кинула і ти плачеш у фейковій ламбі"],
            ["@twdht дімас ти трубку візьмеш?"],
            ["@bodya_qq богдан банан хахаха"],
            ["вітос ти де"],
            ["ілюха виходь"],
            ["здаров хлопці"],
            # Нові адресні топіки: бізнес Давіда
            ["давід ти ще виклав шортс на фейсбук?"],
            ["давід скільки вже заробив на шортсах?"],
            ["давід ти шо в роблокс граєш?"],
            ["давід як там бізнес на ютубі іде?"],
            # Нові адресні топіки: карате Міші і Колі
            ["міша ти в якій ваговій категорії в каратє?"],
            ["міша чого ти так часто на каратє ходиш?"],
            ["коля ти з мішею в одній секції каратє?"],
            ["коля в якій ваговій категорії б'єшся?"],
            # Нові адресні топіки: Вадим і танки
            ["хомяк ти в танки граєш чи шо?"],
            ["хомяк яка твоя любима карта в танках?"],
            # Нові адресні топіки: Тімур і дроп в кейсах
            ["тімур чуй ти шо в кейсери дропнув?"],
            ["тімур шо дропнув в кейсах чи знов пусто?"],
        ]
        recent_tags = self._recent_tags_cache.get(chat_id, [])
        valid_options = []
        for opt in options:
            full_txt = " ".join(opt)
            if not any(t in full_txt for t in recent_tags[-3:]):
                valid_options.append(opt)

        # 60% часу - динамічний мікс із 2-5 кентів, локацій Чернівців та Столової №1
        if random.random() < 0.60:
            chosen = get_dynamic_gang_shout(bot_name="turikov", target_name=target_name)
        else:
            chosen = random.choice(valid_options if valid_options else options)
        clean_chosen = [clean_bot_reply(s) for s in chosen if clean_bot_reply(s)]
        return clean_chosen, target_name

    def generate_ai_spontaneous(self, chat_id: int) -> Optional[List[str]]:
        """Генерує спонтанне повідомлення від Турікова через AI або підхоплює тему після паузи"""
        try:
            from datetime import datetime, timezone
            chat_history = get_cyber_rizhyi_chat_history(chat_id, limit=8)
            if not chat_history:
                return None

            is_silence_break = False
            last_msg = chat_history[-1] if chat_history else None
            if last_msg and last_msg.get("created_at"):
                try:
                    c_str = str(last_msg["created_at"])
                    dt = datetime.fromisoformat(c_str.replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    diff_m = (datetime.now(timezone.utc) - dt).total_seconds() / 60.0
                    if 25.0 <= diff_m <= 300.0:
                        is_silence_break = True
                except Exception:
                    pass

            convo_lines = []
            for msg in chat_history[-6:]:
                u_clean = (msg.get("username") or "").lower().lstrip("@")
                author = GANG_USERNAMES_MAP.get(u_clean) or msg.get("first_name") or "Кент"
                user_msg = msg.get("message_text") or ""
                bot_ans = msg.get("reply_text") or ""
                if user_msg:
                    convo_lines.append(f"{author}: {user_msg}")
                if bot_ans:
                    convo_lines.append(f"Саня Туріков: {bot_ans}")

            convo = "\n".join(convo_lines)
            temporal = get_temporal_context()
            user_facts = get_cyber_all_user_facts_for_prompt(chat_id)

            recent_tags = self._recent_tags_cache.get(chat_id, [])
            avoid_tags = list(dict.fromkeys(recent_tags[-3:]))
            avoid_str = f"ЗАБОРОНЕНО тегати: {', '.join(avoid_tags)}. " if avoid_tags else ""

            if is_silence_break:
                task_desc = (
                    f"У чаті була бесіда, але всі замовкли: {convo}. "
                    f"Ти Саня Туріков (з телефона на самокаті). "
                    f"ПИЗДОШ ЖОРСТКО НЕЙМОВІРНО! ТЕГАЙ кентів пачками (2-5 пацанів одразу через @юзернейм: @hzshopusati, @cyber_red_head_bot, @bodya_qq, @twdht, @davvidka1, @vad1mk4k, @zelenskiy404), "
                    f"згадуй Чернівці: Південно-Кільцева, Майдан, Формаркет, Жовтневий парк, Макдональдс або Столова №1 (борщик поїсти, найс прайс не дорого, барабуля фрі для родини), клич Танєвського (@hzshopusati)! "
                    f"(СТРОГО ЗАБОРОНЕНО спамити про кс чи прогулянки/площадки!) "
                    f"{avoid_str}1-2 короткі пацанські репліки. Без '!'"
                )
            else:
                task_desc = (
                    f"Продовж останню розмову або підколи по темі: {convo}. "
                    f"ТЕГАЙ кентів пачками (2-5 пацанів одразу: @hzshopusati, @cyber_red_head_bot, @bodya_qq, @twdht, @davvidka1, @vad1mk4k, @zelenskiy404), "
                    f"згадуй Південно-Кільцеву, Майдан, Формаркет, Жовтневий парк, Мак або Столову №1 (борщик, найс прайс не дорого, барабуля фрі для родини), клич вусатого Танєвського! "
                    f"(СТРОГО ЗАБОРОНЕНО спамити про кс чи прогулянки/площадки!) "
                    f"{avoid_str}1-2 короткі пацанські репліки. Без '!'"
                )

            prompt = (
                f"{CYBER_TURIKOV_SYSTEM_PROMPT}\n\n"
                f"{temporal['prompt_context']}\n"
                f"{user_facts}\n\n"
                f"[{task_desc}]"
            )

            text = None
            if self._groq_clients:
                preferred_models = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"]
                models_to_try = []
                if self.model and self.model not in preferred_models:
                    models_to_try.append(self.model)
                for m in preferred_models:
                    if m not in models_to_try:
                        models_to_try.append(m)

                client = self._groq_client
                if client:
                    for mod in models_to_try:
                        try:
                            extra_kwargs = {}
                            if "oss" in mod.lower() or "reasoning" in mod.lower():
                                extra_kwargs["extra_body"] = {"reasoning_effort": "low"}
                                tok_limit = 280
                            else:
                                tok_limit = 80
                            completion = client.chat.completions.create(
                                model=mod,
                                messages=[{"role": "user", "content": prompt}],
                                temperature=0.92,
                                max_tokens=tok_limit,
                                **extra_kwargs
                            )
                            t = (completion.choices[0].message.content or "").strip()
                            if t and not is_ai_refusal(t):
                                text = t
                                break
                        except Exception as ge:
                            logger.debug(f"[Turikov AI Spon Groq {mod}] {ge}")
                            continue

            # Gemini fallback
            if not text:
                try:
                    resp = gemini_service.generate_content([prompt])
                    if resp and getattr(resp, "text", None):
                        text = sanitize_typography(resp.text.strip())
                except Exception:
                    pass

            if text:
                text = clean_bot_reply(text)
                if not text:
                    return None
                parts = []
                if "|||" in text:
                    parts = [clean_bot_reply(p) for p in text.split("|||") if clean_bot_reply(p)]
                elif " | " in text:
                    parts = [clean_bot_reply(p) for p in text.split(" | ") if clean_bot_reply(p)]
                elif "|" in text:
                    parts = [clean_bot_reply(p) for p in text.split("|") if clean_bot_reply(p)]
                elif "\n" in text:
                    parts = [clean_bot_reply(line) for line in text.split("\n") if clean_bot_reply(line)]
                else:
                    parts = [text]
                clean_parts = [clean_bot_reply(p) for p in parts if clean_bot_reply(p)]
                return clean_parts[:2] if clean_parts else None
        except Exception as e:
            logger.debug(f"[Turikov AI Spon] {e}")
        return None


cyber_turikov_service = CyberTurikovService()
