import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from instagrapi import Client
from services.publishers.base import BasePublisher, PublishResult, StatsResult
from services.proxy_manager import proxy_manager
from config import (
    INSTAGRAM_USERNAME,
    INSTAGRAM_PASSWORD,
    INSTAGRAM_SESSION_FILE,
    DRY_RUN_MODE
)
from core.content_type import ContentType

logger = logging.getLogger(__name__)


class InstagramPublisher(BasePublisher):
    def __init__(self):
        self._client: Optional[Client] = None

    @property
    def platform_name(self) -> str:
        return "Instagram"

    def _get_client(self) -> Optional[Client]:
        if self._client:
            return self._client

        session_path = Path(INSTAGRAM_SESSION_FILE)
        has_session = session_path.exists()
        has_creds = bool(INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD and not INSTAGRAM_USERNAME.startswith("your_"))

        if not has_session and not has_creds:
            return None

        cl = Client()
        if proxy_manager.proxy_url:
            cl.set_proxy(proxy_manager.proxy_url)

        logged_in = False
        if has_session:
            try:
                cl.load_settings(str(session_path))
                if has_creds:
                    cl.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
                logged_in = True
                logger.info("Сесію Instagram успішно завантажено з файлу сесії")
            except Exception as e:
                logger.warning(f"Помилка відновлення сесії Instagram: {e}")

        if not logged_in and has_creds:
            try:
                cl.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
                cl.dump_settings(str(session_path))
                logged_in = True
            except Exception as e:
                logger.error(f"Помилка входу в Instagram: {e}")
                return None

        if logged_in:
            self._client = cl
            return cl
        return None

    def publish(
        self,
        content_type: ContentType,
        media_paths: List[str],
        metadata: Dict[str, Any]
    ) -> PublishResult:
        """Підтримує Reels (Відео), Фото та Каруселі (Альбоми) в Instagram"""
        if content_type == ContentType.TEXT:
            return PublishResult(
                success=False,
                platform=self.platform_name,
                error="Instagram не підтримує текстові пости без медіа (використовуйте Threads)."
            )

        caption = metadata.get("ig_caption", "")
        if len(caption) > 2000:
            caption = caption[:1996] + "..."

        session_path = Path(INSTAGRAM_SESSION_FILE)
        has_session = session_path.exists()
        has_creds = bool(INSTAGRAM_USERNAME and not INSTAGRAM_USERNAME.startswith("your_"))

        if DRY_RUN_MODE or not (has_session or (has_creds and INSTAGRAM_PASSWORD and not INSTAGRAM_PASSWORD.startswith("your_"))):
            logger.info(f"[DRY RUN / NO CREDS] Instagram: Format={content_type.value}, Items={len(media_paths)}")
            return PublishResult(
                success=True,
                platform=self.platform_name,
                external_id="mock_ig_media_456",
                url="https://instagram.com/p/mock_ig_media_456",
                error=None if DRY_RUN_MODE else "⚠️ Демо-режим (INSTAGRAM credentials не задано)"
            )

        client = self._get_client()
        if not client:
            return PublishResult(success=False, platform=self.platform_name, error="Instagram клієнт не авторизований")

        from core.security_guard import security_guard
        import time

        max_retries = 2
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                if content_type == ContentType.VIDEO:
                    # Відео публікується у Reels з авто-поширенням на прив'язаний Facebook
                    from core.media_processor import media_processor
                    video_p = Path(media_paths[0])
                    thumb_p = None
                    extracted_thumb = media_processor.extract_thumbnail(str(video_p))
                    if extracted_thumb and Path(extracted_thumb).exists():
                        thumb_p = Path(extracted_thumb)

                    try:
                        media = client.clip_upload(path=video_p, caption=caption, thumbnail=thumb_p, share_to_facebook=True)
                    except Exception as fb_err:
                        logger.warning(f"Спроба з share_to_facebook не вдалася ({fb_err}), публікуємо звичайний Reels...")
                        media = client.clip_upload(path=video_p, caption=caption, thumbnail=thumb_p)
                elif content_type in (ContentType.CAROUSEL, ContentType.MIXED_CAROUSEL):
                    # Карусель з кількох фото/відео (до 20 слайдів)
                    media = client.album_upload(paths=[Path(p) for p in media_paths], caption=caption)
                elif content_type == ContentType.PHOTO:
                    # Одне фото
                    media = client.photo_upload(path=media_paths[0], caption=caption)
                else:
                    raise Exception(f"Невідомий формат для Instagram: {content_type.value}")

                media_id = str(media.pk)
                code = media.code
                url = f"https://instagram.com/p/{code}"

                return PublishResult(success=True, platform=self.platform_name, external_id=media_id, url=url)
            except Exception as e:
                last_error = e
                logger.warning(f"Спроба {attempt + 1}/{max_retries + 1} публікації в Instagram не вдалася: {e}")
                err_str = str(e).lower()
                if "proxy" in err_str or "transport" in err_str or "429" in err_str:
                    logger.info("Instagram: помилка проксі (429/ProxyError), перемикаємось на пряме з'єднання...")
                    try:
                        client.set_proxy("")
                    except Exception:
                        pass
                if attempt < max_retries:
                    time.sleep(2.0 * (attempt + 1))

        err_clean = security_guard.sanitize_error(str(last_error))
        logger.error(f"Помилка публікації в Instagram після ретраїв: {err_clean}")
        return PublishResult(success=False, platform=self.platform_name, error=err_clean)

    def get_stats(self, external_id: str) -> StatsResult:
        if external_id.startswith("mock_"):
            return StatsResult(platform=self.platform_name, views=3420, likes=245, comments=19)

        client = self._get_client()
        if not client:
            return StatsResult(platform=self.platform_name, error="Instagram клієнт не авторизований")

        try:
            media_info = client.media_info(external_id)
            views = getattr(media_info, "play_count", 0) or getattr(media_info, "view_count", 0) or 0
            likes = getattr(media_info, "like_count", 0) or 0
            comments = getattr(media_info, "comment_count", 0) or 0
            return StatsResult(
                platform=self.platform_name,
                views=int(views),
                likes=int(likes),
                comments=int(comments)
            )
        except Exception as e:
            return StatsResult(platform=self.platform_name, error=str(e))


instagram_publisher = InstagramPublisher()
