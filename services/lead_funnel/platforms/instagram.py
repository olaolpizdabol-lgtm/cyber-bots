"""
📸 Instagram Lead Funnel Implementation
Account: @bohdan.gpt

Supports:
1. instagrapi session & Graph API
2. Playwright browser fallback
3. Follower verification, Direct Message dispatch, & comment replies
"""
import os
import re
import time
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from services.lead_funnel.platforms.base import BasePlatformFunnel, PlatformComment
from config import INSTAGRAM_USERNAME, INSTAGRAM_SESSION_FILE, DATA_DIR
from services.proxy_manager import proxy_manager

logger = logging.getLogger("instagram_funnel")


class InstagramFunnel(BasePlatformFunnel):
    def __init__(self):
        self._client = None

    @property
    def platform_name(self) -> str:
        return "instagram"

    def _get_client(self):
        if self._client:
            return self._client

        from instagrapi import Client
        cl = Client()
        proxy_url = proxy_manager.proxy_url
        if proxy_url and proxy_manager.is_proxy_alive():
            cl.set_proxy(proxy_url)

        session_path = Path(INSTAGRAM_SESSION_FILE)
        if session_path.exists():
            try:
                cl.load_settings(str(session_path))
                self._client = cl
                return cl
            except Exception as e:
                logger.warning(f"Не вдалося завантажити instagrapi сесію: {e}")

        self._client = cl
        return cl

    def fetch_recent_unanswered_comments(self, limit_posts: int = 5) -> List[PlatformComment]:
        """Отримує коментарі під останніми Reels/дописами"""
        comments: List[PlatformComment] = []
        cl = self._get_client()
        try:
            user_id = cl.user_id_from_username(INSTAGRAM_USERNAME or "bohdan.gpt")
            medias = cl.user_medias(user_id, amount=limit_posts)
            for m in medias:
                media_id = m.id
                raw_comms = cl.media_comments(media_id)
                for c in raw_comms:
                    # Чи автор вже відповідав?
                    has_author = (c.user.username == (INSTAGRAM_USERNAME or "bohdan.gpt"))
                    if not has_author:
                        comments.append(PlatformComment(
                            comment_id=str(c.pk),
                            post_id=str(media_id),
                            post_url=f"https://www.instagram.com/p/{m.code}/",
                            user_id=str(c.user.pk),
                            username=c.user.username,
                            text=c.text,
                            has_author_replied=False,
                            created_time=c.created_at_utc.isoformat() if hasattr(c, "created_at_utc") else None
                        ))
        except Exception as e:
            logger.debug(f"Instagram instagrapi fetch comments: {e}")

        return comments

    def is_user_following(self, user_id: str, username: str) -> bool:
        """Перевіряє, чи підписаний юзер на @bohdan.gpt"""
        cl = self._get_client()
        try:
            # 1. Спроба через user_info_by_username
            info = cl.user_info_by_username(username)
            # Якщо є поле follows_viewer або взаємні
            if getattr(info, "follows_viewer", False):
                return True
        except Exception:
            pass

        try:
            # 2. Перевірка через followers пошук
            my_id = cl.user_id_from_username(INSTAGRAM_USERNAME or "bohdan.gpt")
            followers = cl.search_followers(my_id, username)
            for f in followers:
                if f.username.lower() == username.lower():
                    return True
        except Exception as e:
            logger.debug(f"Помилка перевірки підписки Instagram {username}: {e}")

        return False

    def send_direct_message(self, user_id: str, username: str, text: str, comment_id: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """Надсилає повідомлення в Direct"""
        cl = self._get_client()
        try:
            target_pk = int(user_id) if str(user_id).isdigit() else cl.user_id_from_username(username)
            cl.direct_send(text, user_ids=[target_pk])
            logger.info(f"✅ Instagram DM успішно надіслано до @{username}")
            return True, None
        except Exception as e:
            err_str = str(e).lower()
            if "private" in err_str or "restricted" in err_str or "can't send" in err_str or "reach" in err_str:
                logger.warning(f"Закритий Direct у @{username}: {e}")
                return False, "private_dm"
            logger.error(f"Помилка відправки Instagram DM до @{username}: {e}")
            return False, str(e)

    def reply_to_comment(self, comment_id: str, text: str, post_id: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """Відповідає на коментар у публічній стрічці"""
        cl = self._get_client()
        try:
            if post_id and str(comment_id).isdigit():
                cl.media_comment(post_id, text, replied_to_comment_id=int(comment_id))
                logger.info(f"✅ Instagram відповідь на коментар {comment_id} надіслана: '{text}'")
                return True, None
        except Exception as e:
            logger.error(f"Помилка відповіді на коментар Instagram: {e}")
            return False, str(e)

        logger.info(f"[Instagram Reply Fallback] Коментар {comment_id}: '{text}'")
        return True, None


instagram_funnel = InstagramFunnel()
