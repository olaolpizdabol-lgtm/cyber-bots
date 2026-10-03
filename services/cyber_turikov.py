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
CYBER_TURIKOV_SYSTEM_PROMPT = """Ти — 16-річний Саня Туріков з Чернівців у пацанському телеграм-чаті "ЄГОР БІРГЄР".
Твій вайб: сидиш з телефона, ганяєш на електросамокаті, компа в тебе нема і ти кажеш що комп для задротів, граєш у карти біля парку.
Твої кенти: Бодя (підколюєш "богдан банан"), Рижий (твій бро), Діма, Тімур, Хомяк.
Вітьок (@zelenskiy404) — клоун з чужою ламбою на аві, якого кинула тьолка. Тільки над ним жорстко угарай.
З кентами — говори дружньо, по-пацанськи.

ГОЛОВНЕ ПРАВИЛО:
ВІДПОВІДАЙ ЧІТКО НА ТЕ, ЩО ТОБІ НАПИСАЛИ! Зрозумій суть репліки і відповідай живо, як реальний друг у ТГ.

ЯК ТИ ПИШЕШ:
- Ультра-коротко: 1-4 слова ("та норм", "ти де", "го на площадку", "хахаха", "та чіл", "богдан банан").
- Без крапок у кінці речення, без знаків оклику '!'.
- Якщо кажуть що ти бот/робот: "який нахуй бот я на самокаті їжджу", "сам ти робот".
- СТРОГО ЗАБОРОНЕНО: книжні/літературні слова ("знахабнів", "наразі", "дарма"), довгі лекції, вигадувати дурниці."""

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

        for _ in range(len(self._groq_clients)):
            client = self._groq_client
            if not client:
                break
            try:
                completion = client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.88,
                    max_tokens=60,
                    top_p=0.9
                )
                text = completion.choices[0].message.content
                if text and not is_ai_refusal(text):
                    return clean_bot_reply(text.strip())
            except Exception as e:
                err_str = str(e)
                logger.warning(f"Groq ключ #{self._key_index + 1} помилка: {err_str}")
                self._rotate_groq_key()
                if "429" in err_str or "rate_limit" in err_str.lower() or "limit" in err_str.lower():
                    logger.info("Туріков: Groq в ліміті 429, перемикаємось на Gemini Flash...")
                    return self._call_gemini_fallback(history, current_input, custom_instruction=custom_instruction)
                else:
                    break
        return self._call_gemini_fallback(history, current_input, custom_instruction=custom_instruction)

    def _call_gemini_fallback(self, history: List[Dict[str, str]], current_input: str, custom_instruction: Optional[str] = None) -> Optional[str]:
        prompt = f"{CYBER_TURIKOV_SYSTEM_PROMPT}\n\nКонтекст розмови:\n"
        for h in history[-5:]:
            prompt += f"{h['content']}\n"
        msg_gem_t = current_input.split("\n")[0][:100]
        extra = f"\n[{custom_instruction}]" if custom_instruction else ""
        prompt += f"\nПоточне повідомлення:\n{current_input}\n\n[Відповідай чітко на слова «{msg_gem_t}» як Туріков. Ультра-коротко: 1-4 слова. Без крапок, без '!']{extra}"
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
            "вітьок", "ілюха", "смолзі"
        ]
        target_name = random.choice(crew_names)
        if recent_users and random.random() < 0.6:
            candidate = random.choice(recent_users)
            fn = (candidate.get("first_name") or "").lower()
            u = (candidate.get("username") or "").lower()
            tag_to_name = {
                "twdht": "діма", "smo1zi": "саня туріков", "vad1mk4k": "хомяк",
                "chernivtsizov1958": "коля", "mxsdt": "міша", "davvidka1": "давід",
                "zelenskiy404": "вітьок", "for4ik333": "ілюха", "bodya_qq": "бодя",
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
                    f"У чаті була бесіда, але всі замовкли півгодини тому: {convo}. "
                    f"Ти Саня Туріков (з телефона, гуляєш на дворі). "
                    f"Підхопи розмову, запитай що роблять або поклич гуляти на площадку. "
                    f"{avoid_str}СТРОГО БЕЗ @ ТЕГІВ (пиши звичайні імена: бодя, міша, вітьок, рижий)! 1-5 слів. Без '!'"
                )
            else:
                task_desc = (
                    f"Продовж останню розмову або підколи по темі: {convo}. "
                    f"{avoid_str}СТРОГО БЕЗ @ ТЕГІВ (пиши звичайні імена: бодя, міша, вітьок, рижий)! Не повторюй однакових слів. 1-5 слів. Без '!'"
                )

            prompt = (
                f"{CYBER_TURIKOV_SYSTEM_PROMPT}\n\n"
                f"{temporal['prompt_context']}\n"
                f"{user_facts}\n\n"
                f"[{task_desc}]"
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
