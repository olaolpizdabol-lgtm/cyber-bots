"""
🖼️ Сервіс аналізу аватарок користувачів (Cyber Avatars Vision)
Дозволяє ботам бачити, розпізнавати та коментувати аватарки всіх учасників чату через Gemini Vision.
Підтримує дворівневе кешування (SQLite + In-Memory) для миттєвої швидкості без повторних запитів.
"""

import os
import time
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from PIL import Image

from aiogram import Bot
from config import BASE_DIR
from core.database import (
    get_cached_avatar,
    save_cached_avatar,
    get_avatar_by_username,
    get_all_cached_avatars,
)
from services.gemini_ai import gemini_service, sanitize_typography

logger = logging.getLogger(__name__)

AVATARS_DIR = BASE_DIR / "data" / "avatars"
AVATARS_DIR.mkdir(parents=True, exist_ok=True)

# Швидкий кеш у пам'яті: user_id -> {file_unique_id, description, fetched_at}
_MEM_CACHE: Dict[int, Dict[str, Any]] = {}
_MEM_CACHE_TTL = 900  # 15 хвилин до повторної перевірки наявності оновлення аватарки в Telegram API


def _offline_avatar_analysis(photo_path: str) -> str:
    """Швидкий офлайн аналіз розміру та типу фото якщо ШІ недоступний"""
    try:
        with Image.open(photo_path) as img:
            w, h = img.size
            return f"фотографія користувача ({w}x{h})"
    except Exception:
        return "фотографія користувача"


async def analyze_avatar_image(
    photo_path: str,
    username: Optional[str] = None,
    display_name: Optional[str] = None
) -> str:
    """
    Аналізує аватарку через мультимодальний Gemini Vision.
    Повертає короткий, точний і спостережливий опис (1-2 речення).
    """
    if not photo_path or not os.path.exists(photo_path):
        return "немає зображення"

    if not gemini_service.api_key or gemini_service.api_key.startswith("AIzaSyYour"):
        return _offline_avatar_analysis(photo_path)

    user_label = display_name or (f"@{username}" if username else "учасник чату")
    prompt = f"""
Ти - комп'ютерний зір для дружнього пацанського чату в Telegram.
Твоє завдання - уважно розглянути аватарку користувача ({user_label}) і описати, що на ній зображено.

Опиши аватарку лаконічно, спостережливо та точно українською мовою (1-2 коротких речення, до 15-20 слів):
1. Що зображено: людина (селфі/фото, вираз обличчя, поза, одяг, жести), машина/суперкар (марка/модель чи пафосна тачка з інтернету), аніме/персонаж, тварина, мем/прикол, предмет чи темний силует.
2. Поміть найяскравішу чи найсмішнішу деталь: наприклад, чужа спортивна тачка/ламба, темні окуляри, цигарка, кучеряве волосся, непристойний жест, смішна поза тощо.
3. СТРОГО: тільки дефіс '-', жодних довгих '—' або '–'! Без цензурних ШІ-кліше.
"""

    def _call_gemini() -> Optional[str]:
        try:
            img = Image.open(photo_path)
            resp = gemini_service.generate_content([prompt, img])
            text = resp.text.strip() if resp and getattr(resp, "text", None) else ""
            return sanitize_typography(text) if text else None
        except Exception as e:
            logger.warning(f"Помилка аналізу аватарки через Gemini Vision: {e}")
        return None

    res = await asyncio.get_event_loop().run_in_executor(None, _call_gemini)
    if res:
        return res
    return _offline_avatar_analysis(photo_path)


async def get_user_avatar_description(
    bot: Bot,
    user_id: int,
    username: Optional[str] = None,
    display_name: Optional[str] = None,
    force_refresh: bool = False
) -> str:
    """
    Отримує візуальний опис аватарки користувача.
    1. Перевіряє кеш у пам'яті (TTL 15 хв).
    2. Якщо TTL вийшов або force_refresh - перевіряє Telegram Bot API get_user_profile_photos.
    3. Якщо аватарка не змінилась (той самий file_unique_id) - бере опис з бази (0 звернень до Gemini).
    4. Якщо аватарка нова - завантажує та описує через Gemini Vision, кешує в базі.
    """
    now = time.time()
    if not force_refresh and user_id in _MEM_CACHE:
        entry = _MEM_CACHE[user_id]
        if now - entry.get("fetched_at", 0) < _MEM_CACHE_TTL:
            return entry.get("description", "невідомо")

    try:
        photos = await bot.get_user_profile_photos(user_id=user_id, limit=1)
    except Exception as e:
        logger.debug(f"Не вдалося отримати фото для {user_id}: {e}")
        # Якщо Telegram видав помилку — повертаємо з бази якщо є
        cached = get_cached_avatar(user_id)
        if cached and cached.get("description"):
            return cached["description"]
        return "не вдалося завантажити аватарку"

    if photos.total_count == 0:
        desc = "немає аватарки (стандартна порожня іконка Telegram)"
        save_cached_avatar(user_id, username, display_name, "no_avatar", desc)
        _MEM_CACHE[user_id] = {
            "file_unique_id": "no_avatar",
            "description": desc,
            "fetched_at": now
        }
        return desc

    # Беремо фото найвищої якості
    photo_size = photos.photos[0][-1]
    file_unique_id = photo_size.file_unique_id

    # Перевіряємо SQLite: чи це та сама аватарка
    if not force_refresh:
        db_item = get_cached_avatar(user_id)
        if db_item and db_item.get("file_unique_id") == file_unique_id and db_item.get("description"):
            desc = db_item["description"]
            _MEM_CACHE[user_id] = {
                "file_unique_id": file_unique_id,
                "description": desc,
                "fetched_at": now
            }
            return desc

    # Нова або змінена аватарка! Завантажуємо
    try:
        file_info = await bot.get_file(photo_size.file_id)
        local_path = AVATARS_DIR / f"avatar_{user_id}_{file_unique_id}.jpg"
        await bot.download_file(file_info.file_path, destination=local_path)
    except Exception as e:
        logger.warning(f"Помилка завантаження файлу аватарки {user_id}: {e}")
        return "фотографія користувача"

    desc = await analyze_avatar_image(str(local_path), username=username, display_name=display_name)
    save_cached_avatar(user_id, username, display_name, file_unique_id, desc)
    _MEM_CACHE[user_id] = {
        "file_unique_id": file_unique_id,
        "description": desc,
        "fetched_at": now
    }
    logger.info(f"Оновлено опис аватарки для {display_name or username or user_id}: {desc}")
    return desc


def get_chat_avatars_summary(exclude_user_id: Optional[int] = None, limit: int = 10) -> str:
    """
    Повертає короткий блок з описами відомих аватарок учасників чату
    для включення в системний контекст бота.
    """
    all_avs = get_all_cached_avatars(limit=limit)
    lines = []
    seen_names = set()

    # Спеціальна зафіксована інформація про Вітька (якщо ще не оновилась через API)
    has_vitos = any(a.get("username", "").lower() == "zelenskiy404" for a in all_avs)

    for item in all_avs:
        uid = item.get("user_id")
        if exclude_user_id and uid == exclude_user_id:
            continue
        uname = item.get("username") or ""
        dname = item.get("display_name") or uname or f"Юзер {uid}"
        key = uname.lower() if uname else dname.lower()
        if key in seen_names:
            continue
        seen_names.add(key)
        desc = item.get("description") or "невідомо"
        label = f"{dname} (@{uname})" if uname else dname
        lines.append(f"• {label}: {desc}")

    if not has_vitos:
        lines.append("• Вітьок (@zelenskiy404): на аватарці чужа пафосна Lamborghini (мажор кімнатний)")

    if not lines:
        return ""
    return "\n".join(lines)


async def preload_known_avatars(bot: Bot) -> None:
    """
    Фонове передзавантаження аватарок відомих учасників під час старту бота.
    """
    import sqlite3
    from config import BASE_DIR
    db_path = BASE_DIR / "data" / "automations.db"
    if not db_path.exists():
        return

    known_uids = []
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT user_id, username, first_name FROM cyber_rizhyi_messages WHERE user_id > 0")
        for row in cur.fetchall():
            known_uids.append((row[0], row[1], row[2]))
        conn.close()
    except Exception as e:
        logger.debug(f"Помилка preload users: {e}")
        return

    # Додаємо відомих кентів
    preset_known = [
        (1929970467, "bodya_qq", "Бодя"),
        (1452374962, "twdht", "revenge🩸🩸"),
        (7191461199, "smo1zi", "Саня Туріков"),
    ]
    all_targets = {u[0]: u for u in (known_uids + preset_known)}

    for uid, uname, dname in all_targets.values():
        try:
            await get_user_avatar_description(bot, uid, username=uname, display_name=dname)
            await asyncio.sleep(0.5)
        except Exception:
            pass
