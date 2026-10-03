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
    "zelenskiy404": "Вітос",
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

    if 0 <= hour < 5:
        part_of_day = "глупа ніч"
        vibe = "глупа ніч, нормальні люди сплять або катають нічну в кс. Доречно здивуватися: 'чого не спиш', 'зараз ніч', 'лягай спати'"
    elif 5 <= hour < 9:
        part_of_day = "ранок"
        vibe = "ранок, пора вставати на навчання/в ліцей. Доречно: 'добрий ранок пупсик', 'в ліцей пора', 'ти вже встав?'"
    elif 9 <= hour < 14:
        part_of_day = "день (уроки)"
        vibe = "зараз уроки/пари в ліцеї. Доречно: 'ти на уроці?', 'вчителі не спалили?', 'вчи уроки'"
    elif 14 <= hour < 18:
        part_of_day = "день (після уроків)"
        vibe = "день після занять, час збиратися на площадку біля парку Шевченка, ШоШо, кататися на самокатах"
    elif 18 <= hour < 22:
        part_of_day = "вечір"
        vibe = "вечір, двіж на районі, прогулянки, карти на площадці, 'діма буде в 4-5', 'ти гуляєш?'"
    else:
        part_of_day = "пізній вечір"
        vibe = "пізно вже (після 22:00), час вертатися додому, зависати в телефоні чи чаті"

    is_weekend = now.weekday() in (4, 5, 6)
    weekend_note = "вихідні на носі / вихідний день" if is_weekend else "будній день (завтра на уроки)"

    prompt_line = f"[РЕАЛЬНИЙ ЧАС У ЧЕРНІВЦЯХ: {time_str}, {day_name} ({part_of_day}, {weekend_note}). {vibe}]"

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
        return "Вітос", None
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

    # Якщо повідомлення від бота - ігноруємо прямий тригер (працює окремий міст)
    if message.from_user and (message.from_user.id in (RIZHYI_BOT_ID, TURIKOV_BOT_ID) or (message.from_user.username or "").endswith("bot")):
        return False

    # НА БУДЬ-ЯКЕ ПОВІДОМЛЕННЯ В ЧАТІ ВІДПОВІДАЮТЬ ОБИДВА БОТИ!
    return True
