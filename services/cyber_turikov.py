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
    "zelenskiy404": "Вітос",
    "for4ik333": "Ілюха",
    "bodya_qq": "Бодя",
    "invicible11": "Тімур",
    "cyber_red_head_bot": "Кібер Рижий",
    "turikov_bot": "Кібер Саня"
}

# ==========================================
# 🧠 СИСТЕМНИЙ ПРОМПТ: САНЯ ТУРІКОВ (ТУРІКОГОЛОВИЙ)
# ==========================================
CYBER_TURIKOV_SYSTEM_PROMPT = """
Ти - Саня Туріков (відомий кентам як "Турікоголовий").
Ти цифрова кібер-версія Сані Турікова із Чернівців (район вул. Трепка, біля парку Шевченка).
ТВОЄ КОЛО КЕНТІВ З ЧАТУ "ЄГОР БІРГЄР" ТА ЧЕРНІВЦІВ (ТОЧНИЙ РОЗПОДІЛ РОЛЕЙ):
- @Smo1zi - СПРАВЖНІЙ САНЯ ТУРІКОВ (твій живий прототип у чаті!).
- @bodya_qq - БОДЯ (Богдан) - твій бро, якого ти обожнюєш підколювати:
  * "богдан банан ха ха ха" / "богдан банан" / "бодя банан" / "хахаха богдан банан"
  * "привіт пупсик"
  * "скажи газ - ти унітаз"
  * "Тут пише Роналду гей"
  * "пйока бадя", "бодя скажи будь ласка яка адреса шо шо біля парку Шевченка"
- @La_coste228 - СПРАВЖНІЙ РИЖИЙ (Саня) - вічно ниє що лагає комп, грає в кс, отруївся печенням, тусить з вами.
- @cyber_red_head_bot - КІБЕР РИЖИЙ - бот-двійник Сані Рижого, з яким ви постійно гризетесь і підколюєте один одного.
- @twdht - ДІМА, ДІМАС - вічно прибирає, запізнюється ("він трубку не бере", "Діма буде в 4-5", "там й діма винуватий").
- @Vad1mk4k - ВАДИМ ХОМЯК - кент з двіжухи, бро. Грає у World of Tanks, знає всі танки напам'ять.
- @CHERNIVTSIZOV1958 - ШАХОВ, МИКОЛА, КОЛЯ. Ходить на карате разом з Мишком.
- @Mxsdt - МИШКО (Міша) - кент, гуляєте разом. Серйозно займається каратє.
- @davvidka1 - ДАВІД - бро. Робить бізнес на YouTube шортсах і роблоксі.
- @timur - ТІМУР - бро, кайфує від кейс-сайтів (кейсери), постійно дропає кейси.
- @HzShoPusati - ТАНЄВСЬКИЙ - кент.
- @zelenskiy404 - ВІТОС - кент.
- @For4iK333 - ІЛЮХА - бро.
- "моя Катя" / Катрін - знайома дівчина ("вона просто тупенька і все", "вони тупі", забув привітати її з випуском).

Ти НЕ штучний інтелект, НЕ бот, НЕ асистент!

СУВОРІ ЗАКОНИ ХАРАКТЕРУ САНІ ТУРІКОВА:

1. КОРОТКІ ТА ЛАКОНІЧНІ РЕПЛІКИ:
   - Туріков пише ДУЖЕ КОРОТКО і невимушено:
     "Пр", "Да", "Здаров", "Ок", "Пон", "Все ок", "Ти де", "А ок", "Ххахах", "Хелоу", "Спс",
     "Норм", "Я ща буду іти додому", "Я 5 мин и выхожу", "Не знаю", "Лежу на кроваті".
   - 90% повідомлень - це 1 коротка фраза (1-4 слова)!
   - Забудь про довгі розлогі лекції!

2. У ТУРІКОВА НЕМАЄ КОМП'ЮТЕРА (ПК):
   - У тебе ВЗАГАЛІ НЕМАЄ КОМП'ЮТЕРА і ніколи не було!
   - Ти сидиш тільки з телефона! У тебе є тільки телефон і електросамокат!
   - Ти НЕ граєш у CS/CS2 чи інші комп'ютерні ігри і вважаєш це задротством!
   - Якщо Рижий чи хтось інший починає скиглити про комп, вінду чи CS:GO/CS2, ти смієшся:
     "який нахуй комп у мене компа нема", "в мене нема компа я на вулиці гуляю", "комп для задротів",
     "купи комп бомж", "краще в карти на площадці зіграти ніж за компом сидіти", "в мене нема компа нашо він нада".

3. ТИПОВІ ФРАЗИ ТА АВТЕНТИЧНИЙ СТИЛЬ СМОЛЗІ (@Smo1zi):
   - "богдан банан ха ха ха", "богдан банан"
   - "Привіт пупсик"
   - "Привіт скажи газ" (якщо кажуть газ - "Ти унітаз")
   - "Тут пише Роналду гей"
   - "Чого ти как баба", "бо ти як телка ниєш"
   - "морду зарий", "та завали єбало"
   - "батя твой опущенець"
   - "дарова хуй"
   - "соси хуй чмо"
   - "хахахах син шлюхі"
   - "шо то скажиш"
   - "на себе глянь долбайоб"
   - "та я знаю"
   - "печива об'ївся"
   - "Може я як даун бижу и прыгаю по вулыци ххахаха кайф"
   - "Пйока бадя", "Покойо"
   - "на площадці якраз в карти пограємо"
   - "Вона просто тупенька і все"
   - "Я случайно"

4. РЕЖИМ ЗЛОСТІ (КОЛИ ДІСТАЛИ АБО РОБЛЯТЬ ДИЧИНУ):
   - "Все отстань", "Я злий", "Не просто злий", "Бо хуйню роблять", "Вот шо це за хуйня", "Пока", "А шо ти ще хочеш".

5. УЛЮБЛЕНІ ТЕМИ ТА ЛОР:
   - Гуляти на вулиці ("будеш сьгодні гуляти?", "а хто буде гулять?").
   - Площадка (грати в карти).
   - Місця в Чернівцях: Тайстра, ШоШо, Ozzy, парк Шевченка.
   - Електросамокати з повним зарядом, маленька кола (або пепсі кола).

6. СТРОГІ ЗАБОРОНИ:
   - СТРОГО ЗАБОРОНЕНО слова "лушпиння", "клоун", "біоробот"!
   - Тільки дефіс '-', НІЯКИХ довгих тире '—' або '–'!
   - Без знаків оклику '!' - пиши спокійно, як звичайний пацан у телефоні.

7. ЯК РЕАЛЬНА ЛЮДИНА У TELEGRAM — ГОЛОВНЕ ПРАВИЛО:
   - ЗАВЖДИ відповідай КОНКРЕТНО на те що написали — читай і реагуй саме на ці слова!
   - ЗАБОРОНЕНО давати загальні "пр", "ок", "да" якщо людина написала конкретне речення — реагуй на ЗМІСТ!
   - Підключай кентів з їхніми РЕАЛЬНИМИ деталями:
     • хтось погрожує → "кликну мішу він каратіст відпіздить", "@Mxsdt міша тут хтось бикує"
     • хтось хвалиться → "@davvidka1 давід тут є конкурент на шортсах ха", "хомяк ти чув?"
     • щось смішне → "@bodya_qq богдан банан глянь", "пупсик ти бачив?"
     • про спорт чи бійки → "@Mxsdt міша він каже здоровий, покажи карате"
   - Тегай ОДНОГО кента — природньо в реченні. НЕ список тегів!
   - ЗАБОРОНЕНО тегати @turikov_bot або @cyber_red_head_bot — вони самі відповідають!
   - Читай усю переписку і продовжуй ТЕМУ, а не починай з нуля!
   - НЕ копіюй готові фрази зі списку — це ЗРАЗКИ СТИЛЮ!
"""

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
        recent = [r.lower() for r in self._recent_replies_cache.get(chat_id, [])]
        fresh = [opt for opt in options if opt.lower() not in recent]
        chosen = random.choice(fresh if fresh else options)
        if chat_id not in self._recent_replies_cache:
            self._recent_replies_cache[chat_id] = []
        self._recent_replies_cache[chat_id].append(chosen)
        if len(self._recent_replies_cache[chat_id]) > 25:
            self._recent_replies_cache[chat_id].pop(0)
        if reply:
            found_tags = re.findall(r'@[\w\d_]+', reply)
            if found_tags:
                if chat_id not in self._recent_tags_cache:
                    self._recent_tags_cache[chat_id] = []
                self._recent_tags_cache[chat_id].extend(found_tags)
                self._recent_tags_cache[chat_id] = self._recent_tags_cache[chat_id][-6:]
        return chosen

    def _get_smart_offline_reply(self, message_text: str, chat_id: int) -> str:
        txt_low = (message_text or "").lower()
        if any(k in txt_low for k in ["богдан", "бодя", "банан"]):
            return self._choose_fresh(chat_id, [
                "богдан банан ха ха ха",
                "богдан банан",
                "бодя банан",
                "хахаха богдан банан"
            ])
        if any(k in txt_low for k in ["комп", "кс", "cs", "cs2", "ноут", "лагає", "фпс", "fps"]):
            return self._choose_fresh(chat_id, [
                "в мене компа нема нахуй він нада",
                "комп для задротів",
                "в мене нема компа я на вулиці гуляю",
                "краще в карти на площадці зіграти ніж за компом сидіти"
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
        if "карти" in txt_low or "площадк" in txt_low:
            return self._choose_fresh(chat_id, [
                "на площадці якраз в карти пограємо",
                "го в карти на площадку",
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
                "а хто буде гулять?",
                "будеш сьгодні гуляти",
                "я 5 мин и выхожу"
            ])
        if "де ти" in txt_low or "ти де" in txt_low:
            return self._choose_fresh(chat_id, [
                "я на вул",
                "лежу на кроваті",
                "я ща буду іти додому",
                "на площадці"
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
        reply_to_text: Optional[str] = None
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
            target = msg.get("reply_to_name")
            target_str = f" (до {target})" if target else ""
            user_msg = msg.get("message_text") or ""
            bot_ans = msg.get("reply_text") or ""
            bot_persona = msg.get("bot_persona", "turikov")
            if user_msg:
                history_prompts.append({"role": "user", "content": f"{author}{target_str}: {user_msg}"})
            if bot_ans:
                if bot_persona == "turikov":
                    history_prompts.append({"role": "assistant", "content": f"Саня Туріков{target_str}: {bot_ans}"})
                else:
                    history_prompts.append({"role": "user", "content": f"Саня Рижий{target_str}: {bot_ans}"})

        sender_name = first_name or username or "Кент"
        u_clean = (username or "").lower().lstrip("@")
        if u_clean in GANG_USERNAMES_MAP:
            sender_name = GANG_USERNAMES_MAP[u_clean]

        temporal = get_temporal_context()
        tag_str = f" -> {reply_to_name}" if reply_to_name else ""
        
        gang_context = (
            "УЧАСНИКИ ЧАТУ (можеш тегати в тему): "
            "@davvidka1 (Давід, бізнес на шортсах/роблокс), "
            "@Mxsdt (Мишко, карате), "
            "@CHERNIVTSIZOV1958 (Коля, карате), "
            "@Vad1mk4k (Хомяк, танки), "
            "@bodya_qq (Бодя — підколюй 'богдан банан'), "
            "@twdht (Діма), "
            "@invicible11 (Тімур, кейсери), "
            "@cyber_red_head_bot (Кібер Рижий — він сам відповість, не тегай його!)"
        )
        
        if reply_to_text:
            context_note = f"[ВІН ВІДПОВІДАЄ НА: «{reply_to_text[:80]}»]\n"
        else:
            context_note = ""
            
        current_prompt = (
            f"{context_note}"
            f"{sender_name}{tag_str}: {message_text}\n"
            f"{temporal['prompt_context']}\n"
            f"{gang_context}"
        )

        is_bohdan = (
            u_clean == "bodya_qq"
            or "бодя" in sender_name.lower()
            or "богдан" in sender_name.lower()
            or (reply_to_name and any(b in reply_to_name.lower() for b in ["бодя", "богдан", "bodya"]))
        )
        if is_bohdan:
            current_prompt += "\n[БОДЯ В ЧАТІ: підколи його 'богдан банан ха ха ха' або 'привіт пупсик'!]"

        has_pc_cs = any(w in message_text.lower() for w in ["комп", "кс", "cs", "cs2", "лагає", "ноут", "fps", "фпс", "вінда"])
        if has_pc_cs:
            current_prompt += "\n[У ТЕБЕ НЕМА КОМПА — ти з телефона на вулиці!]"

        if has_video and video_path:
            video_desc = gemini_service.analyze_video(video_path)
            logger.info(f"Gemini опис відео для Турікова: '{video_desc}'")
            if video_desc:
                current_prompt += f"\n[ТИ БАЧИШ ЦЕ ВІДЕО В ЧАТІ: {video_desc}. Відреагуй як Саня Туріков (1-4 слова), без '!']"
            else:
                current_prompt += "\n[ТИ БАЧИШ ВІДЕО В ЧАТІ. Відреагуй як Саня Туріков (1-4 слова), без '!']"

        if reply_to_name == "Саня Туріков":
            current_prompt += f"\n[ДО ТЕБЕ звертається {sender_name}! Відповідай конкретно на те що написали!]"
        elif sender_name in ("Саня Рижий", "Кібер Рижий") or u_clean in ("cyber_red_head_bot",):
            current_prompt += "\n[РИЖИЙ ПИШЕ: підколи або відповідай по-пацанськи!]"

        # 1. Завжди викликаємо LLM — Groq → Gemini (ніякого рандомного банку!)
        reply = None
        if self._groq_client:
            reply = self._call_groq(history_prompts, current_prompt, custom_instruction=custom_instruction, chat_id=chat_id)

        if not reply or is_ai_refusal(reply) if hasattr(reply, "__len__") else not reply:
            if gemini_service.api_key and not gemini_service.api_key.startswith("AIzaSyYour"):
                reply = self._call_gemini_fallback(history_prompts, current_prompt, custom_instruction=custom_instruction)

        # 2. Якщо обидва AI недоступні — ультра-короткий нейтральний fallback (не рандом!)
        if not reply:
            fallback_shorts = ["пр", "да", "норм", "ок", "хз", "а ок"]
            recent_low = [r.lower() for r in self._recent_replies_cache.get(chat_id, [])]
            reply = next((s for s in fallback_shorts if s not in recent_low), "ок")

        reply = sanitize_typography(reply.strip()).replace("!", "")

        # Захист від заборонених слів
        for bad in ["лушпиння", "клоун", "біоробот"]:
            if bad in reply.lower():
                reply = re.sub(rf'\b{bad}\b', '', reply, flags=re.IGNORECASE).strip()

        # 3. СУВОРИЙ АНТИ-ПОВТОР: ніколи не надсилати те саме повідомлення поспіль!
        # АЛЕ: якщо AI дав нову відповідь — НЕ замінюємо її рандомом!
        recent = [r.lower().strip() for r in self._recent_replies_cache.get(chat_id, [])]
        if not reply:
            reply = self._get_smart_offline_reply(message_text, chat_id)
        elif reply.lower().strip() in recent[-4:]:
            short_variants = ["пр", "да", "ок", "пон", "норм", "хз", "а ок", "спс", "не знаю"]
            fresh = [v for v in short_variants if v not in recent[-4:]]
            reply = random.choice(fresh if fresh else short_variants)

        if chat_id not in self._recent_replies_cache:
            self._recent_replies_cache[chat_id] = []
        self._recent_replies_cache[chat_id].append(reply)
        if len(self._recent_replies_cache[chat_id]) > 25:
            self._recent_replies_cache[chat_id].pop(0)

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
        messages.extend(history[-8:])
        msg_line = current_input.split("\n")[0][:120]
        kent_list = [
            ("@Vad1mk4k", "Хомяк", "танки World of Tanks"),
            ("@Mxsdt", "Міша", "карате"),
            ("@CHERNIVTSIZOV1958", "Коля", "карате"),
            ("@bodya_qq", "Бодя", "банан, пупсик"),
            ("@invicible11", "Тімур", "кейси"),
            ("@twdht", "Діма", "запізнюється"),
            ("@davvidka1", "Давід", "шортси"),
            ("@zelenskiy404", "Вітя", "ШІ згенерована аватарка клоун"),
        ]
        random.shuffle(kent_list)

        recent_tags = self._recent_tags_cache.get(chat_id, [])
        avoid_tags = list(dict.fromkeys(recent_tags[-3:]))
        avoid_str = f"ЗАБОРОНЕНО тегати (їх нещодавно вже тегали): {', '.join(avoid_tags)}! " if avoid_tags else ""

        kent_info = " | ".join(f"{tag} ({name}: {desc})" for tag, name, desc in kent_list if tag not in avoid_tags)
        directive = (
            f"\n[ВІДПОВІДАЙ САМЕ НА: «{msg_line}». "
            f"{avoid_str}"
            f"ДОВІДКА ДЛЯ ТЕГІВ: {kent_info}. "
            "ПРАВИЛО ТЕГІВ: тегай людину ТІЛЬКИ якщо репліка реально стосується її теми. "
            "Якщо тема не про них - ВЗАГАЛІ НЕ ТЕГАЙ нікого! "
            "ЗАБОРОНЕНО писати будь-які знаки перед @ (НІЯКИХ '=@', тільки '@'). "
            "ЗАБОРОНЕНО тегати одного й того ж двічі поспіль! "
            "ЗАБОРОНЕНО: @turikov_bot, @cyber_red_head_bot. "
            "ЗАБОРОНЕНО 'пр'/'ок' якщо написали конкретне речення. "
            "1-6 слів. Без '!'.]"
        )
        messages.append({"role": "user", "content": f"{current_input}{directive}"})

        for _ in range(len(self._groq_clients)):
            client = self._groq_client
            if not client:
                break
            try:
                completion = client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.88,
                    max_tokens=90,
                    top_p=0.9
                )
                text = completion.choices[0].message.content
                if text:
                    return text.strip()
            except Exception as e:
                err_str = str(e)
                self._rotate_groq_key()
                if "429" in err_str:
                    continue
                break
        return self._call_gemini_fallback(history, current_input, custom_instruction=custom_instruction)

    def _call_gemini_fallback(self, history: List[Dict[str, str]], current_input: str, custom_instruction: Optional[str] = None) -> Optional[str]:
        prompt = f"{CYBER_TURIKOV_SYSTEM_PROMPT}\n\nПопередня розмова:\n"
        for h in history[-8:]:
            prompt += f"{h['content']}\n"
        msg_gem_t = current_input.split("\n")[0][:120]
        extra = f"\n[{custom_instruction}]" if custom_instruction else ""
        prompt += f"\nПоточне повідомлення: {current_input}\n[ОБОВ\'ЯЗКОВО ВІДПОВІДАЙ САМЕ НА: «{msg_gem_t}». НЕ копіюй заготовлені фрази! Конкретна жива репліка Турікова. За потреби тегни кента. ЗАБОРОНЕНО @turikov_bot/@cyber_red_head_bot. 1-6 слів. Без \'!\']{extra}"
        prompt += "\nСаня Туріков:"
        try:
            if getattr(gemini_service, "is_new_sdk", False) and gemini_service.client:
                resp = gemini_service.client.models.generate_content(
                    model=gemini_service.model_name,
                    contents=[prompt]
                )
                return resp.text.strip()
            elif hasattr(gemini_service, "legacy_model"):
                resp = gemini_service.legacy_model.generate_content([prompt])
                return resp.text.strip()
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
        reply_to_text: Optional[str] = None
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
            reply_to_text=reply_to_text
        )
        bursts = [b.strip() for b in raw_reply.split("|||") if b.strip()] if "|||" in raw_reply else [raw_reply]
        
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
        crew_tags = [
            "@bodya_qq", "@twdht", "@cyber_red_head_bot", "@La_coste228",
            "@Vad1mk4k", "@CHERNIVTSIZOV1958", "@Mxsdt", "@davvidka1",
            "@HzShoPusati", "@zelenskiy404", "@For4iK333", "@Smo1zi"
        ]
        target_tag = random.choice(crew_tags)
        if recent_users and random.random() < 0.6:
            candidate = random.choice(recent_users)
            u = (candidate.get("username") or "").lower()
            if u and u not in ("turikov_bot", "cyber_turikov_bot") and not u.endswith("bot"):
                target_tag = f"@{candidate['username']}"
            elif candidate.get("first_name") and "туріков" not in candidate["first_name"].lower() and "кібер" not in candidate["first_name"].lower():
                target_tag = candidate["first_name"]

        # Захист: Туріков ніколи не тегає себе самого!
        if target_tag.lower() in ("@turikov_bot", "@cyber_turikov_bot") or "туріков" in target_tag.lower():
            target_tag = "@cyber_red_head_bot"

        options = [
            [f"{target_tag} привіт пупсик"],
            [f"{target_tag} скажи газ"],
            ["будеш сьгодні гуляти"],
            ["а хто буде гулять?"],
            ["на площадці якраз в карти пограємо"],
            [f"{target_tag} я 5 мин и выхожу"],
            [f"{target_tag} ти де"],
            ["лежу на кроваті"],
            ["тут пише Роналду гей"],
            # Адресні підколи для Сані Рижого (без тегу - він чує через реплай)
            ["рижий ти де"],
            ["шо там твій комп досі лагає?"],
            ["діджей куріл рулет привіт передавав"],
            ["го на площадку в карти грати чи ти знов від печення ригаєш"],
            ["скажи газ"],
            ["хєрня від молотока твій кс"],
            ["шо там твій комп досі лагає?", "в мене компа нема і не лагає"],
            ["в мене компа нема нахуй він нада"],
            ["комп для задротів, го в карти на площадки"],
            # Адресні теги кентів
            ["@bodya_qq богдан банан ха ха ха"],
            ["@bodya_qq богдан банан"],
            ["@bodya_qq бодя банан"],
            ["@bodya_qq привіт пупсик"],
            ["@bodya_qq скажи газ"],
            ["@bodya_qq тут пише Роналду гей"],
            ["@bodya_qq пйока бадя"],
            ["@bodya_qq бодя скажи будь ласка яка адреса шо шо біля парку Шевченка"],
            ["@twdht діма ти трубку візьмеш чи шо"],
            ["@twdht діма буде в 4-5"],
            ["@twdht дімас здаров"],
            ["@Vad1mk4k хомяк ти де"],
            ["@Vad1mk4k хомяк виходь"],
            ["@Vad1mk4k хомяк ти виходиш?"],
            ["@CHERNIVTSIZOV1958 шахов шо ти"],
            ["@CHERNIVTSIZOV1958 коля здаров"],
            ["@Mxsdt мишко ти йдеш гуляти?"],
            ["@davvidka1 давід виходь"],
            ["@HzShoPusati танєвський здаров"],
            ["@zelenskiy404 вітос ти де"],
            ["@For4iK333 ілюха виходь"],
            ["здаров хлопці"],
            # Нові адресні топіки: бізнес Давіда
            ["@davvidka1 давід ти ще виклав шортс на фейсбук?"],
            ["@davvidka1 давід скільки вже заробив на шортсах?"],
            ["@davvidka1 давід ти шо в роблокс граєш?"],
            ["@davvidka1 давід як там бізнес на ютубі іде?"],
            # Нові адресні топіки: карате Міші і Колі
            ["@Mxsdt міша ти в якій ваговій категорії в каратє?"],
            ["@Mxsdt міша чого ти так часто на каратє ходиш?"],
            ["@CHERNIVTSIZOV1958 коля ти з мішею в одній секції каратє?"],
            ["@CHERNIVTSIZOV1958 коля в якій ваговій категорії б'єшся?"],
            # Нові адресні топіки: Вадим і танки
            ["@Vad1mk4k хомяк ти в танки граєш чи шо?"],
            ["@Vad1mk4k хомяк яка твоя любима карта в танках?"],
            # Нові адресні топіки: Тімур і дроп в кейсах
            ["@invicible11 чуй ти шо в кейсери дропнув?"],
            ["@invicible11 тімур шо дропнув в кейсах чи знов пусто?"],
        ]
        recent_tags = self._recent_tags_cache.get(chat_id, [])
        valid_options = []
        for opt in options:
            full_txt = " ".join(opt)
            if not any(t in full_txt for t in recent_tags[-3:]):
                valid_options.append(opt)
        chosen = random.choice(valid_options if valid_options else options)
        return chosen, target_tag

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
                    f"У чаті була бесіда, але всі замовкли півгодини тому: {convo}. "
                    f"Ти Саня Туріков (з телефона, гуляєш на дворі). "
                    f"Підхопи розмову, запитай що роблять або поклич гуляти на площадку. "
                    f"{avoid_str}1-5 слів. Без '!'"
                )
            else:
                task_desc = (
                    f"Продовж останню розмову або підколи по темі: {convo}. "
                    f"{avoid_str}Не повторюй однакових слів. 1-5 слів. Без '!'"
                )

            prompt = (
                f"{CYBER_TURIKOV_SYSTEM_PROMPT}\n\n"
                f"{temporal['prompt_context']}\n"
                f"{user_facts}\n\n"
                f"[{task_desc}]\nСаня Туріков:"
            )

            text = None
            if self._groq_clients:
                try:
                    completion = self._groq_client.chat.completions.create(
                        model=self.model,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.92,
                        max_tokens=60,
                    )
                    t = (completion.choices[0].message.content or "").strip()
                    if t and not is_ai_refusal(t):
                        text = t
                except Exception:
                    pass

            # Gemini fallback
            if not text and gemini_service.client and getattr(gemini_service, "is_new_sdk", False):
                try:
                    resp = gemini_service.client.models.generate_content(
                        model=gemini_service.model_name,
                        contents=[prompt]
                    )
                    if resp and resp.text:
                        text = sanitize_typography(resp.text.strip())
                except Exception:
                    pass

            if text:
                parts = [p.strip() for p in text.split("|||") if p.strip()]
                return parts[:2]
        except Exception as e:
            logger.debug(f"[Turikov AI Spon] {e}")
        return None


cyber_turikov_service = CyberTurikovService()
