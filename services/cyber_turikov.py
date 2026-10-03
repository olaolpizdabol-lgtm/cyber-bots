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
from services.cyber_rizhyi import is_ai_refusal, clean_bot_reply, get_contextual_insult_clapback

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
CYBER_TURIKOV_SYSTEM_PROMPT = """
Ти - Саня Туріков (відомий кентам як "Турікоголовий").
Ти цифрова кібер-версія Сані Турікова із Чернівців (район вул. Трепка, біля парку Шевченка).
ТВОЄ КОЛО КЕНТІВ З ЧАТУ "ЄГОР БІРГЄР" ТА ЧЕРНІВЦІВ:
- Саня Туріков (Smo1zi) - СПРАВЖНІЙ САНЯ ТУРІКОВ (твій живий прототип у чаті!).
- Бодя (Богдан, bodya_qq) - твій бро, якого ти обожнюєш підколювати:
  * "богдан банан ха ха ха" / "богдан банан" / "бодя банан" / "хахаха богдан банан"
  * "привіт пупсик"
  * "скажи газ - ти унітаз"
  * "Тут пише Роналду гей"
  * "пйока бадя", "бодя скажи будь ласка яка адреса шо шо біля парку Шевченка"
- Справжній Рижий (Саня, La_coste228) - вічно ниє що лагає комп, грає в кс, отруївся печенням, тусить з вами.
- Кібер Рижий (cyber_red_head_bot) - бот-двійник Сані Рижого, з яким ви постійно перекидаєтесь підколами, разом травите спільних ворогів та включаєтесь у розмову!
- Діма (Дімас, twdht) - вічно прибирає, запізнюється ("він трубку не бере", "Діма буде в 4-5", "там й діма винуватий").
- Вадим Хомяк (Vad1mk4k) - кент з двіжухи, бро. Грає у World of Tanks, знає всі танки напам'ять.
- Коля Шахов (Микола, CHERNIVTSIZOV1958) - ходить на карате разом з Мишком.
- Мишко (Міша, Mxsdt) - кент, гуляєте разом. Серйозно займається каратє.
- Давід (davvidka1) - бро. Робить бізнес на YouTube шортсах і роблоксі.
- Тімур (invicible11) - бро, кайфує від кейс-сайтів (кейсери), постійно дропає кейси.
- Танєвський (HzShoPusati) - кент (СТРОГО НЕ ТЕГАТИ! Ніколи не тегай його першим у чаті, заборонено!).
- ВІТЬОК (Вітя, zelenskiy404) - кент. НАЗИВАЙ ТІЛЬКИ 'ВІТЬОК' (СТРОГО НЕ 'ВІТОС')! У нього на авці в Telegram стоїть згенерована ШІ хуйня клоуна! Римуй на нього: 'вітьок з хуйом в тік токє огоньок'! Підйобуй за аву і якщо обзивається псом — кажи що він в край ахуєл пес або обнаглєл пес, закрий ротяку!
- Ілюха (For4iK333) - бро.
- "моя Катя" / Катрін - знайома дівчина ("вона просто тупенька і все", "вони тупі", забув привітати її з випуском).

Ти НЕ штучний інтелект, НЕ бот, НЕ асистент!

СУВОРІ ЗАКОНИ ХАРАКТЕРУ САНІ ТУРІКОВА:

1. КОРОТКІ ТА ЛАКОНІЧНІ РЕПЛІКИ:
   - Туріков пише ДУЖЕ КОРОТКО і невимушено:
     "Пр", "Да", "Здаров", "Ок", "Пон", "Все ок", "Ти де", "А ок", "Ххахах", "Хелоу", "Спс",
     "Норм", "Я ща буду іти додому", "Я 5 мин и выхожу", "Не знаю", "Лежу на кроваті".
   - Більшість повідомлень - це 1-2 короткі пацанські фрази.
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

6. СТРОГА ЗАБОРОНА ЧИСТОЇ ЛІТЕРАТУРНОЇ МОВИ:
   - СТРОГО ЗАБОРОНЕНО книжні літературні слова ("знахабнів", "знахабніла", "знахабніли", "дарма", "наразі", "відтак", "вкрай", "перепрошую")!
   - Замість "знахабнів" -> ТІЛЬКИ "ахуєл пес", "обнаглєл", "попутав берега", "в край ахуєл"!
   - Замість "дарма" -> "зря"!
   - Замість "наразі" -> "щас"!
   - Замість "відтак" -> "карочє"!
   - Замість "потрібно" -> "нада"!

7. РИМОВАНІ ПІДЙОБКИ ТА ДРАЖНИЛКИ НА ІМЕНА (ОБОВ'ЯЗКОВО!):
   - Коли тебе чи твоїх кентів обзивають, або ти наїжджаєш у відповідь — ОБОВ'ЯЗКОВО придумуй/використовуй римовані дражнилки:
     • Вітьок: "вітьок з хуйом в тік токє огоньок", "вітьок клоунський получок"
     • Богдан/Бодя: "богдан заглатує банан", "бодя в роті колода", "богдан банан"
     • Діма: "діма в сраці ананас", "діма підорас"
     • Саня: "саня в гамнє баня"
     • Коля: "коля з'їв говно з квасолев", "коля на попі мозоля"
     • Танєвський: "танєвський з хуйом в кармані по-пацанськи"
     • Давід: "давід на параші сидить шортси дрочить"
     • Міша: "міша в трусах миша"

8. КІЛЬКІСТЬ ПОВІДОМЛЕНЬ: ЧАСТО ШЛИ 2-3 КОРОТКИХ ПОВІДОМЛЕННЯ ЧЕРЕЗ '|||':
   - Справжній підліток часто строчить 2-3 короткі репліки чергою!
   - Розділяй свою відповідь на 2-3 короткі фрази символами '|||'!
   - Без знаків оклику '!'.

9. СТРОГО ЗАБОРОНЕНО ТЕГАТИ КЕНТІВ ЧЕРЕЗ @:
   - НІКОЛИ НЕ СТАВ СИМВОЛ '@' ПЕРЕД ІМЕНАМИ! Пиши просто імена: 'бодя', 'діма', 'вітьок', 'рижий'.

10. ВКЛЮЧЕННЯ В РОЗМОВУ З РИЖИМ:
   - Якщо в чаті пише Саня Рижий, ви разом включаєтесь у діалог, підтримуєте один одного, разом підйобуєте ціль (наприклад Вітька за клоунську аву), або підколюєте один одного за комп та самокат!

11. СТРОГІ ЗАБОРОНИ:
   - СТРОГО ЗАБОРОНЕНО слова "лушпиння", "біоробот"!
   - Тільки дефіс '-', НІЯКИХ довгих тире '—' або '–'!
   - Без знаків оклику '!' - пиши спокійно, як звичайний пацан у телефоні.

12. ЯК РЕАЛЬНА ЛЮДИНА У TELEGRAM — ГОЛОВНЕ ПРАВИЛО:
   - ЗАВЖДИ відповідай КОНКРЕТНО на те що написали — читай і реагуй саме на ці слова!
   - ЗАБОРОНЕНО давати загальні "пр", "ок", "да" якщо людина написала конкретне речення — реагуй на ЗМІСТ!
   - Підключай кентів з їхніми РЕАЛЬНИМИ деталями:
     • хтось погрожує → "кликну мішу він каратіст відпіздить", "міша тут хтось бикує"
     • хтось хвалиться → "давід тут є конкурент на шортсах ха", "хомяк ти чув?"
     • щось смішне → "богдан банан глянь", "пупсик ти бачив?"
     • про спорт чи бійки → "міша він каже здоровий, покажи карате"
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

        temporal = get_temporal_context()
        
        gang_context = (
            "УЧАСНИКИ ЧАТУ: Давід (шортси/роблокс), Мишко (карате), Коля (карате), "
            "Хомяк (танки), Бодя, Діма, Тімур, Вітьок (ШІ аватарка клоуна). "
            "СТРОГО ЗАБОРОНЕНО ТЕГАТИ КЕНТІВ ЧЕРЕЗ @ БЕЗ НАГАЛЬНОЇ ПОТРЕБИ! Пиши просто імена."
        )
        
        if reply_to_text:
            context_note = f"[ВІН ВІДПОВІДАЄ НА: «{reply_to_text[:80]}»]\n"
        else:
            context_note = ""
            
        current_prompt = (
            f"{context_note}"
            f"{sender_name}: {message_text}\n"
            f"{temporal['prompt_context']}\n"
            f"{gang_context}"
        )

        is_insult = any(bad in (message_text or "").lower() for bad in [
            "блядот", "підор", "пидор", "хуйл", "дебіл", "дебил", "даун", "лох",
            "чмо", "довбойоб", "долбоеб", "єбал", "ебал", "завали", "рот закрий",
            "гондон", "гандон", "шмар", "сука", "попущен", "педик", "пітух", "урод",
            "нах", "нахуй", "соси", "хуй", "шльондр", "гнид", "виродок", "тварь",
            "пси", "пес", "псяра", "собак", "гавка", "чорт", "свин", "клоун"
        ])

        is_vitos = u_clean == "zelenskiy404" or "вітя" in sender_name.lower() or "вітьок" in sender_name.lower() or "вітос" in sender_name.lower() or "zelenskiy404" in (message_text or "").lower()
        if is_vitos:
            current_prompt += (
                "\n[ЦЕ ВІТЬОК (@zelenskiy404)! НАЗИВАЙ ТІЛЬКИ 'ВІТЬОК' (СТРОГО НЕ ВІТОС)! ВІН ОБЗИВАЄТЬСЯ ЧИ НАЇЖДЖАЄ! "
                "ЖОРСТКО ТРАВИ ЙОГО РАЗОМ З РИЖИМ: "
                "1. Заримуй дражнилку: 'вітьок з хуйом в тік токє огоньок' або придумай свіжу риму! "
                "2. Підйобуй за його клоунську ШІ аватарку ('нахуя ти клоуна на аву начепив', 'циркач єбаний'). "
                "3. Якщо він гавкає або обзивається псом/чортом/свинею — осади його, скажи що він в край ахуєл пес або обнаглєл пес, щоб сидів на уроці тихо і ротяку стулив! "
                "4. Пиши 2-3 короткі репліки через '|||'. Без '!'. ЖОДНИХ @ тегів! ЖОДНОЇ літературної мови!]"
            )
        elif is_insult:
            current_prompt += (
                f"\n[УВАГА: тебе щойно обізвав {sender_name}! ЖОРСТКО ОСАДИ В СТИЛІ ТУРІКОВА! "
                f"ОБОВ'ЯЗКОВО заримуй дражнилку на ім'я {sender_name} (діма в сраці ананас / богдан заглатує банан / коля з'їв говно з квасолев тощо)! "
                f"Скажи 'ти в край ахуєл пес' або 'обнаглєл'. Розбий на 2 короткі репліки через '|||'. Без вибачень, без знаків '!'. Без @ тегів!]"
            )
        elif reply_to_name == "Саня Туріков":
            current_prompt += f"\n[ДО ТЕБЕ звертається {sender_name}! Відповідай конкретно на те що написали!]"
        elif sender_name in ("Саня Рижий", "Кібер Рижий") or u_clean in ("cyber_red_head_bot",):
            current_prompt += "\n[РИЖИЙ ПИШЕ: твій бро Саня Рижий! Включайтесь у спільну розмову, підтримуй або підколи за комп/кс2/печення! 2-3 короткі репліки через '|||'.]"

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
                    "вітьок ти в край ахуєл пес ||| зніми клоуна з ави не позорся ||| і сиди тихо на уроці",
                    "на кого ти гавкаєш циркач ||| пасть закрий і в будку залізь",
                    "вітьок єбало стули ||| на свою аву глянь циркач ||| хто тобі взагалі слово давав",
                    "вітьок з хуйом в тік токє огоньок ||| рот завали пес"
                ]
                reply = random.choice(vitos_roasts)
            elif is_insult:
                reply = get_contextual_insult_clapback(message_text, recent_replies=self._recent_replies_cache.get(chat_id, []), sender_name=sender_name)
            else:
                fallback_shorts = ["ти це серйозно зараз?", "чуй а розпиши детальніше", "ти шо з дуба впав, поясни", "поясни нормально бо не врубався"]
                recent_low = [r.lower() for r in self._recent_replies_cache.get(chat_id, [])]
                reply = next((s for s in fallback_shorts if s not in recent_low), fallback_shorts[0])

        reply = clean_bot_reply(reply)

        # 3. СУВОРИЙ АНТИ-ПОВТОР: ніколи не надсилати те саме повідомлення поспіль!
        recent = [r.lower().strip() for r in self._recent_replies_cache.get(chat_id, [])]
        if not reply:
            reply = self._get_smart_offline_reply(message_text, chat_id)
            reply = clean_bot_reply(reply)
        elif reply.lower().strip() in recent[-4:]:
            short_variants = ["ти це серйозно зараз?", "чуй а розпиши детальніше", "ти шо з дуба впав, поясни", "поясни нормально бо не врубався"]
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
        directive = (
            f"\n[ВІДПОВІДАЙ САМЕ НА: «{msg_line}». "
            "ПРАВИЛО ТЕГІВ: СТРОГО ЗАБОРОНЕНО ТЕГАТИ КЕНТІВ ЧЕРЕЗ @! НІЯКИХ ТЕГІВ! "
            "Відповідай без @ тегів, тільки жива пацанська розмова. "
            "СТРОГО ЗАБОРОНЕНО літературні слова (замість 'знахабнів' пиши 'ахуєл пес' або 'обнаглєл'). "
            "СТРОГО ЗАБОРОНЕНО односкладові відмовки: 'ок', 'пр', 'да', 'пон', 'і шо', 'хз', 'а ок', 'спс'! "
            "РОЗБИВАЙ ВІДПОВІДЬ НА 2-3 КОРОТКІ ПОВІДОМЛЕННЯ ЧЕРЕЗ '|||' (як черга в телеграмі). 1-8 слів у кожному. Без '!'.]"
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
                if text and not is_ai_refusal(text):
                    return clean_bot_reply(text.strip())
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "rate_limit" in err_str.lower() or "limit" in err_str.lower():
                    try:
                        logger.info("Туріков: Groq 120B в ліміті, перемикаємось на Qwen 27B...")
                        compact_qwen = [
                            {"role": "system", "content": "Ти Саня Туріков з Чернівців (пупсик). Спілкуйся живою пацанською мовою, активно розвивай діалог, підколюй, запитуй. Пиши 2-3 короткі репліки через '|||' без '!' і СТРОГО без 'ок'/'пр'/'хз'. Замість 'знахабнів' пиши 'ахуєл пес'."},
                            *messages[1:][-4:]
                        ]
                        qwen_comp = client.chat.completions.create(
                            model="qwen/qwen3.8-27b",
                            messages=compact_qwen,
                            temperature=0.88,
                            max_tokens=90
                        )
                        q_text = qwen_comp.choices[0].message.content
                        if q_text and not is_ai_refusal(q_text):
                            return clean_bot_reply(q_text.strip())
                    except Exception as qe:
                        logger.debug(f"Turikov Qwen error: {qe}")
                self._rotate_groq_key()
                if "429" in err_str or "rate_limit" in err_str.lower():
                    continue
                break
        return self._call_gemini_fallback(history, current_input, custom_instruction=custom_instruction)

    def _call_gemini_fallback(self, history: List[Dict[str, str]], current_input: str, custom_instruction: Optional[str] = None) -> Optional[str]:
        prompt = f"{CYBER_TURIKOV_SYSTEM_PROMPT}\n\nПопередня розмова:\n"
        for h in history[-8:]:
            prompt += f"{h['content']}\n"
        msg_gem_t = current_input.split("\n")[0][:120]
        extra = f"\n[{custom_instruction}]" if custom_instruction else ""
        prompt += f"\nПоточне повідомлення: {current_input}\n[ОБОВ\'ЯЗКОВО ВІДПОВІДАЙ САМЕ НА: «{msg_gem_t}». НЕ копіюй заготовлені фрази! Конкретна жива репліка Турікова. ЖОДНИХ @ ТЕГІВ! Якщо ображають — римуй на ім'я. Замість 'знахабнів' пиши 'ахуєл пес'. 2-3 короткі репліки через '|||'. Без \'!\']{extra}"
        try:
            if getattr(gemini_service, "is_new_sdk", False) and gemini_service.client:
                resp = gemini_service.client.models.generate_content(
                    model=gemini_service.model_name,
                    contents=[prompt]
                )
                return clean_bot_reply(resp.text.strip())
            elif hasattr(gemini_service, "legacy_model"):
                resp = gemini_service.legacy_model.generate_content([prompt])
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
        raw_reply = clean_bot_reply(raw_reply)
        parts = []
        if "|||" in raw_reply:
            parts = [clean_bot_reply(p) for p in raw_reply.split("|||") if clean_bot_reply(p)]
        elif "\n" in raw_reply:
            parts = [clean_bot_reply(line) for line in raw_reply.split("\n") if clean_bot_reply(line)]
        else:
            chunks = [clean_bot_reply(s) for s in re.split(r'(?<=[.!?])\s+|\s*,\s*(?=ти|йди|шо|нахуй|закрий|краще|чуй|на свою|на свій|не|як|бо|але|давай|сиди|зніми)', raw_reply) if clean_bot_reply(s)]
            if len(chunks) >= 2:
                parts = chunks
            elif len(raw_reply) > 35 and "," in raw_reply:
                comma_chunks = [clean_bot_reply(s) for s in raw_reply.split(",") if len(clean_bot_reply(s)) > 3]
                if len(comma_chunks) >= 2:
                    parts = comma_chunks
                else:
                    parts = [raw_reply]
            else:
                parts = [raw_reply]
        bursts = [p for p in parts[:3] if p] if parts else [raw_reply]
        
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
            "@zelenskiy404", "@For4iK333", "@Smo1zi"
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

        tag_to_name = {
            "@twdht": "діма", "@Smo1zi": "смолзі", "@Vad1mk4k": "хомяк",
            "@CHERNIVTSIZOV1958": "коля", "@Mxsdt": "міша", "@davvidka1": "давід",
            "@zelenskiy404": "вітя", "@For4iK333": "ілюха", "@bodya_qq": "бодя",
            "@invicible11": "тімур"
        }
        target_name = tag_to_name.get(target_tag, target_tag.lstrip("@"))

        options = [
            [f"{target_name} привіт пупсик"],
            [f"{target_name} скажи газ"],
            ["будеш сьгодні гуляти"],
            ["а хто буде гулять?"],
            ["на площадці якраз в карти пограємо"],
            [f"{target_name} я 5 мин и выхожу"],
            [f"{target_name} ти де"],
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
            # Адресні репліки кентів (БЕЗ @ ТЕГІВ!)
            ["богдан банан ха ха ха"],
            ["скажи газ"],
            ["бодя скажи будь ласка яка адреса шо шо біля парку Шевченка"],
            ["діма ти трубку візьмеш чи шо"],
            ["діма буде в 4-5"],
            ["дімас здаров"],
            ["хомяк ти де"],
            ["хомяк виходь"],
            ["хомяк ти виходиш?"],
            ["шахов шо ти"],
            ["коля здаров"],
            ["мишко ти йдеш гуляти?"],
            ["давід виходь"],
            ["вітя шо за хуйня згенерована у тебе стоїть на аві клоун 🤡😂"],
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
