import logging
import random
import re
from typing import Optional, Tuple
from aiogram.types import Message, User

logger = logging.getLogger(__name__)

# ID ботів у Telegram
RIZHYI_BOT_ID = 8959835424
TURIKOV_BOT_ID = 8837375550

RIZHYI_USERNAMES = {"cyber_red_head_bot"}
TURIKOV_USERNAMES = {"turikov_bot", "cyberturikovbot"}

# Карта учасників чату банди "єгор біргєр" та їхніх ролей
GANG_USERNAMES_MAP = {
    "la_coste228": "Справжній Рижий (Саня)",
    "smo1zi": "Саня Туріков (справжній)",
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
    "cyber_red_head_bot": "Саня Рижий",
    "turikov_bot": "Саня Туріков",
    "cyberturikovbot": "Саня Туріков",
}

# Справжні юзернейми людей (не ботів)
GANG_HUMAN_USERNAMES = {
    "la_coste228", "smo1zi", "twdht", "vad1mk4k", "chernivtsizov1958",
    "mxsdt", "davvidka1", "hzshopusati", "zelenskiy404", "for4ik333", "bodya_qq"
}


def get_sender_character_profile(
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    user_id: Optional[int] = None
) -> dict:
    """
    Визначає точний профіль та персональну інструкцію для автора повідомлення.
    СУВОРИЙ ЗАХИСТ ВІД ПЛУТАНИНИ:
    - Бодя (@bodya_qq) — це друг 'богдан банан', у нього НЕМАЄ ламби і НЕМАЄ вусів!
    - Вітьок (@zelenskiy404) — ТІЛЬКИ ВІН клоун з чужою зеленою ламбою на аві, якого кинула тьолка!
    - Танєвський (@hzshopusati) — ТІЛЬКИ ВІН вусатий кент!
    - Давід (@davvidka1) — ТІЛЬКИ ВІН шейх з Facebook шортсів!
    """
    u_clean = (username or "").lower().lstrip("@")
    f_clean = (first_name or "").lower()

    # 1. Вітьок (@zelenskiy404) — суворо ТІЛЬКИ якщо сам автор є Вітьком!
    if u_clean == "zelenskiy404" or any(k in f_clean for k in ["вітя", "вітьок", "зеленський"]):
        return {
            "key": "vitos",
            "name": "Вітьок",
            "username": "zelenskiy404",
            "is_vitos": True,
            "instruction": "Тобі зараз пише Вітьок (@zelenskiy404)! Тільки над ним угарай, що він додік з чужою зеленою ламбою на аві, якого кинула дівчина і вся 11 школа з нього рже!"
        }

    # 2. Бодя (@bodya_qq) — друг 'богдан банан', НЕ Вітьок і НЕ Танєвський!
    if u_clean == "bodya_qq" or any(k in f_clean for k in ["бодя", "богдан"]):
        return {
            "key": "bodia",
            "name": "Бодя",
            "username": "bodya_qq",
            "is_vitos": False,
            "instruction": "Тобі зараз пише твій найкращий кент Бодя (@bodya_qq) ('богдан банан')! ВІН НЕ ВІТЬОК І НЕ ТАНЄВСЬКИЙ! У Боді НЕМАЄ ламби і НЕМАЄ вусів! Підколюй його: 'богдан банан', 'чого як баба ниєш', 'шо за тіктоки дивишся', або клич у Столову №1 поїсти борщ!"
        }

    # 3. Танєвський (@hzshopusati) — ТІЛЬКИ ВІН вусатий!
    if u_clean == "hzshopusati" or "танєвськ" in f_clean:
        return {
            "key": "tanevsky",
            "name": "Танєвський",
            "username": "hzshopusati",
            "is_vitos": False,
            "instruction": "Тобі зараз пише Танєвський (@hzshopusati) — вусатий кент. ТІЛЬКИ У ТАНЄВСЬКОГО Є ВУСА! Підколюй його за вуса ('бери вуса і підвалюй', 'збрив вуса чи сциш') і клич у Столову №1 на борщик та барабулю фрі!"
        }

    # 4. Давід (@davvidka1) — шейх фейсбучний
    if u_clean == "davvidka1" or "давід" in f_clean:
        return {
            "key": "david",
            "name": "Давід",
            "username": "davvidka1",
            "is_vitos": False,
            "instruction": "Тобі зараз пише Давід (@davvidka1) — шейх фейсбучний, який піднявся на шортсах у Facebook. Підколюй його за бабки з фб і вимагай щоб проставився в Столовій №1 за борщ і барабулю фрі!"
        }

    # 5. Діма (@twdht)
    if u_clean == "twdht" or any(k in f_clean for k in ["діма", "дімас"]):
        return {
            "key": "dima",
            "name": "Діма",
            "username": "twdht",
            "is_vitos": False,
            "instruction": "Тобі зараз пише Діма (@twdht). Підколюй де він проїбався, чому не бере трубку, чи буде в 4-5 і кого склеїв на майдані!"
        }

    # 6. Вадим Хомяк (@vad1mk4k)
    if u_clean == "vad1mk4k" or "хомяк" in f_clean or "вадим" in f_clean:
        return {
            "key": "khomiak",
            "name": "Вадим Хомяк",
            "username": "vad1mk4k",
            "is_vitos": False,
            "instruction": "Тобі зараз пише Вадим Хомяк (@vad1mk4k). Він задротить у танки! Питай яка улюблена карта і клич на південно-кільцеву чи в Столову №1!"
        }

    # 7. Коля Шахов (@chernivtsizov1958)
    if u_clean == "chernivtsizov1958" or "коля" in f_clean or "шахов" in f_clean:
        return {
            "key": "kolya",
            "name": "Коля Шахов",
            "username": "chernivtsizov1958",
            "is_vitos": False,
            "instruction": "Тобі зараз пише Коля Шахов (@chernivtsizov1958). Він спортік і каратист! Питай в якій ваговій категорії б'ється!"
        }

    # 8. Мишко (@mxsdt)
    if u_clean == "mxsdt" or any(k in f_clean for k in ["міша", "мишко", "михайло"]):
        return {
            "key": "misha",
            "name": "Мишко",
            "username": "mxsdt",
            "is_vitos": False,
            "instruction": "Тобі зараз пише Мишко (@mxsdt). Він каратист, ходить на секцію карате! Підколюй за тренування!"
        }

    # 9. Тімур (@invicible11)
    if u_clean == "invicible11" or "тімур" in f_clean:
        return {
            "key": "timur",
            "name": "Тімур",
            "username": "invicible11",
            "is_vitos": False,
            "instruction": "Тобі зараз пише Тімур (@invicible11). Він крутить кейси! Питай чи дропнув щось нормальне чи знов злив бабки!"
        }

    # 10. Саня Туріков (@smo1zi) (якщо пише реальний Туріков)
    if u_clean == "smo1zi" or any(k in f_clean for k in ["туріков", "турік"]):
        return {
            "key": "turikov",
            "name": "Саня Туріков",
            "username": "smo1zi",
            "is_vitos": False,
            "instruction": "Тобі зараз пише твій кент Саня Туріков (@smo1zi)! Він літає на китайському самокаті з повним зарядом і п'є маленьку колу. Підколюй його за самокат!"
        }

    # 11. Саня Рижий (@la_coste228) (якщо пише реальний Рижий)
    if u_clean == "la_coste228" or any(k in f_clean for k in ["рижий"]):
        return {
            "key": "rizhyi",
            "name": "Саня Рижий",
            "username": "la_coste228",
            "is_vitos": False,
            "instruction": "Тобі зараз пише твій кент Саня Рижий (@la_coste228)! У нього комп-калькулятор лагає, п'є квас і ригав від печення!"
        }

    fallback_name = GANG_USERNAMES_MAP.get(u_clean) or first_name or username or "Кент"
    return {
        "key": "other",
        "name": fallback_name,
        "username": u_clean,
        "is_vitos": False,
        "instruction": f"Тобі зараз пише {fallback_name}. Спілкуйся з ним по-пацанськи. ВІН НЕ ВІТЬОК (ламба тільки у Вітька @zelenskiy404) і НЕ ТАНЄВСЬКИЙ (вуса тільки у Танєвського @hzshopusati)!"
    }


def get_temporal_context() -> dict:
    """
    Повертає точний контекст реального часу в Чернівцях (Europe/Kyiv):
    час, день тижня, пору доби та підказку поведінки для ШІ (школа/ніч/гуляння/вихідні).
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo

    now = datetime.now(ZoneInfo("Europe/Kyiv"))
    days_uk = {
        0: "понеділок",
        1: "вівторок",
        2: "середа",
        3: "четвер",
        4: "п'ятниця",
        5: "субота",
        6: "неділя"
    }
    day_name = days_uk.get(now.weekday(), "")
    hour = now.hour
    minute = now.minute
    time_str = f"{hour:02d}:{minute:02d}"

    is_weekend = now.weekday() in (5, 6)
    is_friday = now.weekday() == 4

    if is_weekend:
        if 0 <= hour < 5:
            part_of_day = "глупа ніч вихідного"
            vibe = "глупа ніч вихідного дня. НІЯКИХ УРОКІВ НЕМАЄ! Чіл, ігри, сон."
        elif 5 <= hour < 11:
            part_of_day = "ранок вихідного"
            vibe = "ранок вихідного дня (субота/неділя). УРОКІВ НЕМАЄ! Всі сплять або чілять."
        elif 11 <= hour < 18:
            part_of_day = "день вихідного дня (СУБОТА/НЕДІЛЯ)"
            vibe = "сьогодні СУБОТА/НЕДІЛЯ, ВИХІДНИЙ ДЕНЬ! НІЯКИХ УРОКІВ, ШКОЛИ, ПАР ЧИ ВЧИТЕЛІВ НЕМАЄ І БУТИ НЕ МОЖЕ! Всі чілять, гуляють на площадці, біля тайстри, грають у кс/танки або шаряться по району. СТРОГО ЗАБОРОНЕНО писати про уроки, вчителів чи школу!"
        elif 18 <= hour < 23:
            part_of_day = "вечір вихідного"
            vibe = "вечір вихідного дня. Двіж, гулянки, карти на площадці біля тайстри. НІЯКИХ УРОКІВ."
        else:
            part_of_day = "пізній вечір вихідного"
            vibe = "пізно вже, сидіти в телефоні чи за компом."
        weekend_note = "ВИХІДНИЙ ДЕНЬ (СУБОТА/НЕДІЛЯ), УРОКІВ НЕМАЄ"
    else:
        if 0 <= hour < 5:
            part_of_day = "глупа ніч"
            vibe = "глупа ніч, нормальні люди сплять або катають у кс."
        elif 5 <= hour < 9:
            part_of_day = "ранок"
            vibe = "ранок, пора вставати."
        elif 9 <= hour < 14:
            part_of_day = "день"
            vibe = "день, будень."
        elif 14 <= hour < 18:
            part_of_day = "день (після занять)"
            vibe = "день, можна на площадку біля парку Шевченка чи ШоШо."
        elif 18 <= hour < 22:
            part_of_day = "вечір"
            vibe = "вечір, двіж на районі, карти на площадці."
        else:
            part_of_day = "пізній вечір"
            vibe = "пізно вже, час вертатися додому."
        weekend_note = "п'ятниця перед вихідними" if is_friday else "будній день"

    prompt_line = f"[РЕАЛЬНИЙ ЧАС У ЧЕРНІВЦЯХ: {time_str}, {day_name} ({part_of_day}). {vibe}]"

    return {
        "time_str": time_str,
        "day_name": day_name,
        "hour": hour,
        "minute": minute,
        "part_of_day": part_of_day,
        "vibe": vibe,
        "is_weekend": is_weekend,
        "weekend_note": weekend_note,
        "prompt_context": prompt_line
    }


def get_user_display_name(user: Optional[User]) -> str:
    """Повертає канонічне дружнє ім'я учасника з урахуванням лору банди"""
    if not user:
        return "Кент"
    u = (user.username or "").lower().lstrip("@")
    if u in GANG_USERNAMES_MAP:
        return GANG_USERNAMES_MAP[u]
    if user.id == RIZHYI_BOT_ID:
        return "Саня Рижий"
    if user.id == TURIKOV_BOT_ID:
        return "Саня Туріков"
    return user.first_name or user.username or "Кент"


def get_message_target(message: Message) -> Tuple[Optional[str], Optional[int]]:
    """
    Визначає адресата повідомлення:
    Повертає (target_name, target_user_id) або (None, None), якщо повідомлення кинуто взагалі в чат.
    """
    # 1. Відповідь через нативний Reply в Telegram
    if message.reply_to_message and message.reply_to_message.from_user:
        rep_u = message.reply_to_message.from_user
        rep_uname = (rep_u.username or "").lower().lstrip("@")
        rep_id = rep_u.id

        if rep_id == RIZHYI_BOT_ID or rep_uname in RIZHYI_USERNAMES:
            return "Саня Рижий", RIZHYI_BOT_ID
        if rep_id == TURIKOV_BOT_ID or rep_uname in TURIKOV_USERNAMES:
            return "Саня Туріков", TURIKOV_BOT_ID
        if rep_uname in GANG_USERNAMES_MAP:
            return GANG_USERNAMES_MAP[rep_uname], rep_id
        return rep_u.first_name or rep_u.username or "Кент", rep_id

    # 2. Пошук згадок і тегів у тексті повідомлення
    text = (message.text or message.caption or "").strip()
    text_low = text.lower()
    words = [w.strip(".,!?@:;()\"'") for w in text_low.split()]

    # Маркери ботів
    rizhyi_markers = [
        "@cyber_red_head_bot", "рижий", "рижа", "рижого", "рижому", "рижим",
        "куріл", "рулет", "кирило", "діджей куріл", "діджей куріл рулет"
    ]
    turikov_markers = [
        "@turikov_bot", "@cyberturikovbot", "туріков", "турік", "турікоу",
        "туріка", "туріку", "туріком", "турікоголов", "турікоголовий",
        "пупсик", "саня туріков", "саша туріков"
    ]
    both_bots_markers = [
        "бляшанк", "бляшанка", "бляшанки", "дві бляшанки", "бляхи", "бляха",
        "боти", "ботів", "ботам", "роботи", "роботів", "роботам", "штучний інтелект",
        "два дебіла", "два придурка", "два придурки", "напали", "накинулись", "боти напали",
        "боти накинулись", "шо з ботами", "чого мовчите", "чому мовчите",
        "чого не відповідають", "чому не відповідають", "зависли", "глючать", "лаги"
    ]

    has_both = any(m in text_low for m in both_bots_markers)
    has_rizhyi = any(m in text_low for m in rizhyi_markers)
    has_turikov = any(m in text_low for m in turikov_markers)

    if has_both or (has_rizhyi and has_turikov):
        return "Обидва боти", None
    if has_rizhyi and not has_turikov:
        return "Саня Рижий", RIZHYI_BOT_ID
    if has_turikov and not has_rizhyi:
        return "Саня Туріков", TURIKOV_BOT_ID

    # Явні теги конкретних людей через @
    if "@la_coste228" in text_low:
        return "Справжній Рижий (Саня)", None
    if "@smo1zi" in text_low:
        return "Саня Туріков (справжній)", None
    if "@chernivtsizov1958" in text_low:
        return "Коля Шахов", None
    if "@bodya_qq" in text_low:
        return "Бодя", None
    if "@twdht" in text_low:
        return "Діма (Дімас)", None
    if "@vad1mk4k" in text_low:
        return "Вадим Хомяк", None
    if "@davvidka1" in text_low:
        return "Давід", None
    if "@hzshopusati" in text_low:
        return "Танєвський", None
    if "@zelenskiy404" in text_low:
        return "Вітьок", None
    if "@for4ik333" in text_low:
        return "Ілюха", None
    if "@mxsdt" in text_low:
        return "Мишко", None

    # Якщо просто звернення "саня", "саша", "саньок" (обидва боти - Сані)
    if any(w in ["саня", "саша", "саньок"] for w in words):
        try:
            from core.database import get_cyber_rizhyi_chat_history
            recent = get_cyber_rizhyi_chat_history(message.chat.id, limit=4)
            for r in reversed(recent):
                if r.get("bot_persona") == "turikov":
                    return "Саня Туріков", TURIKOV_BOT_ID
                elif r.get("bot_persona") == "rizhyi":
                    return "Саня Рижий", RIZHYI_BOT_ID
        except Exception:
            pass
        if message.message_id % 2 == 0:
            return "Саня Рижий", RIZHYI_BOT_ID
        else:
            return "Саня Туріков", TURIKOV_BOT_ID

    return None, None


def is_message_addressed_to_bot(message: Message, bot_identity: str) -> bool:
    """
    Визначає, чи повинен вказаний бот (rizhyi чи turikov) реагувати на повідомлення:
    - За прямою вимогою користувача: ОБИДВА БОТИ ВІДПОВІДАЮТЬ НА КОЖНЕ ПОВІДОМЛЕННЯ В ЧАТІ (100% покриття)!
    - Якщо повідомлення від іншого бота (самого себе або двійника) - не реагувати (захист від нескінченних лупів).
    """
    if message.chat.type == "private":
        return True

    # Ігноруємо тільки НАШИХ двох ботів (захист від лупів). Незалежні боти — відповідаємо!
    if message.from_user and message.from_user.id in (RIZHYI_BOT_ID, TURIKOV_BOT_ID):
        return False

    # НА БУДЬ-ЯКЕ ПОВІДОМЛЕННЯ В ЧАТІ ВІДПОВІДАЮТЬ ОБИДВА БОТИ!
    return True


# ==============================================================================
# 🛡️ АНТИ-ПОВТОР 30 ХВИЛИН (1800 СЕКУНД) ТА ПЕРЕРВИ МІЖ ПОВІДОМЛЕННЯМИ БОТІВ
# ==============================================================================
import time
from typing import Dict, Tuple

_sent_message_timestamps: Dict[Tuple[int, str], float] = {}
_last_bot_message_timestamp: Dict[int, float] = {}


def normalize_message_for_dedup(text: str) -> str:
    """Нормалізує текст повідомлення для перевірки дублікатів (без знаків, нижній регістр)"""
    if not text:
        return ""
    import re
    cleaned = re.sub(r'[^\w\s]', '', text.lower())
    return " ".join(cleaned.split())


def is_recent_duplicate(chat_id: int, text: str, cooldown_seconds: float = 1800.0) -> bool:
    """
    Перевіряє, чи надсилалося таке саме (або практично ідентичне) повідомлення
    у цей чат протягом останніх 30 хвилин (1800 секунд).
    """
    now = time.time()
    norm = normalize_message_for_dedup(text)
    if not norm or len(norm) < 3:
        return False

    # Очищуємо застарілі записи в оперативній пам'яті (старше 1 години)
    to_del = [k for k, t in _sent_message_timestamps.items() if (now - t) > 3600.0]
    for k in to_del:
        _sent_message_timestamps.pop(k, None)

    key = (chat_id, norm)
    last_t = _sent_message_timestamps.get(key)
    if last_t and (now - last_t) < cooldown_seconds:
        return True

    # Перевірка по базі даних cyber_rizhyi_messages
    try:
        from core.database import get_connection
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT reply_text FROM cyber_rizhyi_messages
                WHERE chat_id = ? AND reply_text IS NOT NULL
                  AND created_at >= datetime('now', '-' || ? || ' seconds')
                ORDER BY id DESC LIMIT 50
            """, (chat_id, int(cooldown_seconds)))
            for row in cursor.fetchall():
                db_reply = row["reply_text"]
                if db_reply and normalize_message_for_dedup(db_reply) == norm:
                    _sent_message_timestamps[key] = now
                    return True
    except Exception:
        pass

    return False


def record_sent_message(chat_id: int, text: str):
    """Фіксує надіслане повідомлення для блокування повторів на 30 хвилин та оновлює час останнього повідомлення"""
    norm = normalize_message_for_dedup(text)
    if norm:
        _sent_message_timestamps[(chat_id, norm)] = time.time()
    _last_bot_message_timestamp[chat_id] = time.time()


def get_seconds_since_last_bot_message(chat_id: int) -> float:
    """Повертає кількість секунд з моменту останнього повідомлення будь-якого бота у чаті"""
    last_t = _last_bot_message_timestamp.get(chat_id)
    if not last_t:
        return 9999.0
    return time.time() - last_t

