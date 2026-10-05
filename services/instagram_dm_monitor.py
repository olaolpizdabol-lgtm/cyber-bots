"""
📸 Моніторинг вхідних Instagram Direct повідомлень та Reels від дівчини (@lady_valeriii)
Автоматично пересилає всі нові повідомлення та відео в Telegram бот і НЕ відповідає їй у Direct.
"""
import os
import re
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import requests

from instagrapi import Client
from config import (
    DATA_DIR,
    INSTAGRAM_SESSION_FILE,
    CHANNEL_AUTOMATION_BOT_TOKEN,
    TELEGRAM_BOT_TOKEN,
    ALLOWED_USER_IDS
)
from services.proxy_manager import proxy_manager

logger = logging.getLogger("instagram_dm_monitor")

GF_INSTAGRAM_USERNAME = "lady_valeriii"
GF_TRACKER_FILE = DATA_DIR / "instagram_forwarded_gf_messages.json"


class InstagramDMMonitor:
    def __init__(self):
        self._client: Optional[Client] = None

    def _get_client(self) -> Optional[Client]:
        session_path = Path(INSTAGRAM_SESSION_FILE)
        if not session_path.exists():
            logger.warning(f"Файл сесії Instagram {session_path} не знайдено.")
            return None

        cl = Client()
        # Проксі налаштування
        from config import STRICT_PROXY_CHECK
        proxy_url = proxy_manager.proxy_url
        if proxy_url and not STRICT_PROXY_CHECK and not proxy_manager.is_proxy_alive():
            proxy_url = None

        if proxy_url:
            cl.set_proxy(proxy_url)

        try:
            cl.load_settings(str(session_path))
            return cl
        except Exception as e:
            logger.warning(f"Помилка завантаження сесії Instagram: {e}")
            # Спробуємо без проксі
            if proxy_url:
                try:
                    cl = Client()
                    cl.load_settings(str(session_path))
                    return cl
                except Exception as e2:
                    logger.error(f"Помилка завантаження сесії Instagram без проксі: {e2}")
            return None

    def _notify_telegram(self, html_text: str):
        token = CHANNEL_AUTOMATION_BOT_TOKEN or TELEGRAM_BOT_TOKEN
        if not token or not ALLOWED_USER_IDS:
            return
        for uid in ALLOWED_USER_IDS:
            try:
                requests.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={
                        "chat_id": uid,
                        "text": html_text,
                        "parse_mode": "HTML",
                        "disable_web_page_preview": False
                    },
                    timeout=8
                )
            except Exception as e:
                logger.debug(f"Не вдалося відправити Telegram сповіщення Instagram: {e}")

    def _get_forwarded_ids(self) -> set:
        if GF_TRACKER_FILE.exists():
            try:
                return set(json.loads(GF_TRACKER_FILE.read_text(encoding="utf-8")))
            except Exception:
                return set()
        return set()

    def _save_forwarded_ids(self, ids: set):
        try:
            GF_TRACKER_FILE.write_text(
                json.dumps(list(ids)[-500:], ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            logger.debug(f"Помилка збереження GF_TRACKER_FILE: {e}")

    def check_new_messages(self) -> List[Dict[str, Any]]:
        """
        Перевіряє нові повідомлення в Instagram Direct від @lady_valeriii.
        Пересилає відео та текст у Telegram.
        КАТЕГОРИЧНО НЕ надсилає повідомлень у відповідь.
        """
        cl = self._get_client()
        if not cl:
            return []

        forwarded_ids = self._get_forwarded_ids()
        processed = []

        try:
            threads = cl.direct_threads(amount=10)
        except Exception as e:
            logger.warning(f"Не вдалося отримати direct_threads в Instagram: {e}")
            return []

        target_thread = None
        for t in threads:
            usernames = [u.username.lower() for u in t.users]
            if GF_INSTAGRAM_USERNAME.lower() in usernames:
                target_thread = t
                break

        if not target_thread:
            logger.debug(f"Діалог з @{GF_INSTAGRAM_USERNAME} не знайдено серед останніх {len(threads)} чатів.")
            return []

        # Якщо трекер порожній (перший запуск): додаємо старіші повідомлення окрім сьогоднішніх
        is_first_run = len(forwarded_ids) == 0
        today_date = datetime.now().date()

        for m in reversed(target_thread.messages):
            # Пропускаємо власні повідомлення (відправлені Богданом)
            if getattr(m, "is_sent_by_viewer", False):
                continue

            item_type = getattr(m, "item_type", "")
            if item_type == "action_log":
                continue

            mid = str(getattr(m, "id", ""))
            if not mid:
                continue

            msg_time = getattr(m, "timestamp", None)
            # Якщо перший запуск і повідомлення не сьогоднішнє - позначаємо як прочитане
            if is_first_run and msg_time and hasattr(msg_time, "date") and msg_time.date() < today_date:
                forwarded_ids.add(mid)
                continue

            if mid in forwarded_ids:
                continue

            # 1. Перевірка чи це Reels / Відео
            video_url = None
            if hasattr(m, "xma_share") and m.xma_share:
                video_url = getattr(m.xma_share, "video_url", None)
            elif hasattr(m, "clip") and m.clip:
                code = getattr(m.clip, "code", None)
                if code:
                    video_url = f"https://www.instagram.com/reel/{code}/"
            elif hasattr(m, "media_share") and m.media_share:
                code = getattr(m.media_share, "code", None)
                if code:
                    video_url = f"https://www.instagram.com/p/{code}/"

            # Очищуємо зайві параметри трекінгу з URL
            if video_url:
                clean_url = video_url.split("?")[0]
                text_note = getattr(m, "text", "") or ""
                note_str = f"\n💬 Підпис: <i>«{text_note}»</i>" if text_note else ""

                logger.info(f"💌 Пересилаємо Reels від дівчини (@{GF_INSTAGRAM_USERNAME}) в Telegram: {clean_url}")
                self._notify_telegram(
                    f"🎬 <b>Кохана (@{GF_INSTAGRAM_USERNAME}) надіслала Reels в Instagram:</b>\n\n"
                    f"🔗 <a href='{clean_url}'>{clean_url}</a>{note_str}\n\n"
                    f"💬 <i>(Бот нічого їй не надсилає - переглянь та дай відповідь сам)</i>"
                )
                forwarded_ids.add(mid)
                processed.append({
                    "id": mid,
                    "type": "reel",
                    "url": clean_url
                })
                continue

            # 2. Текстове повідомлення
            raw_text = getattr(m, "text", None)
            if raw_text and raw_text.strip():
                clean_txt = raw_text.strip()
                logger.info(f"💌 Пересилаємо текст від дівчини (@{GF_INSTAGRAM_USERNAME}) в Telegram...")
                self._notify_telegram(
                    f"💌 <b>Нове повідомлення від Коханої (@{GF_INSTAGRAM_USERNAME}) в Instagram:</b>\n\n"
                    f"«{clean_txt}»\n\n"
                    f"💬 <i>(Бот нічого їй не надсилає - напиши відповідь сам)</i>"
                )
                forwarded_ids.add(mid)
                processed.append({
                    "id": mid,
                    "type": "text",
                    "text": clean_txt
                })
                continue

            # Якщо медіа іншого формату
            forwarded_ids.add(mid)

        self._save_forwarded_ids(forwarded_ids)
        return processed


instagram_dm_monitor = InstagramDMMonitor()
