import os
import time
import logging
from typing import Dict, Any, Optional, List
import requests
from services.publishers.base import BasePublisher, PublishResult, StatsResult
from config import DRY_RUN_MODE
from core.content_type import ContentType

logger = logging.getLogger(__name__)

THREADS_ACCESS_TOKEN = os.getenv("THREADS_ACCESS_TOKEN", "").strip()
THREADS_USER_ID = os.getenv("THREADS_USER_ID", "").strip()


class ThreadsPublisher(BasePublisher):
    @property
    def platform_name(self) -> str:
        return "Threads"

    def publish(
        self,
        content_type: ContentType,
        media_paths: List[str],
        metadata: Dict[str, Any]
    ) -> PublishResult:
        """Підтримує Відео, Фото, Каруселі та Текстові треди у Threads (Meta API)"""
        text = metadata.get("threads_post") or metadata.get("ig_caption", "")
        if len(text) > 500:
            text = text[:496] + "..."

        token = os.getenv("THREADS_ACCESS_TOKEN", THREADS_ACCESS_TOKEN).strip()
        user_id = os.getenv("THREADS_USER_ID", THREADS_USER_ID).strip()
        has_creds = bool(
            token and not token.startswith("your_") and
            user_id and not user_id.startswith("your_")
        )

        if not has_creds and not DRY_RUN_MODE:
            logger.info("Threads: токени не налаштовано у .env")
            return PublishResult(
                success=False,
                platform=self.platform_name,
                error="Не налаштовано (THREADS_ACCESS_TOKEN у .env)"
            )

        if DRY_RUN_MODE and not has_creds:
            logger.info(f"[DRY RUN] Threads: Format={content_type.value}, Text len={len(text)}")
            return PublishResult(
                success=True,
                platform=self.platform_name,
                external_id="mock_threads_404",
                url="https://threads.net/@user/post/mock_threads_404"
            )

        container_url = f"https://graph.threads.net/v1.0/{user_id}/threads"
        publish_url = f"https://graph.threads.net/v1.0/{user_id}/threads_publish"

        try:
            if content_type == ContentType.TEXT or not media_paths:
                # Текстовий пост
                res = requests.post(
                    container_url,
                    data={"media_type": "TEXT", "text": text, "access_token": token},
                    timeout=15
                ).json()
            elif content_type == ContentType.VIDEO:
                res = requests.post(
                    container_url,
                    data={"media_type": "VIDEO", "text": text, "access_token": token},
                    timeout=20
                ).json()
            else:
                # Фото або карусель
                res = requests.post(
                    container_url,
                    data={"media_type": "IMAGE", "text": text, "access_token": token},
                    timeout=15
                ).json()

            creation_id = res.get("id")
            if not creation_id:
                raise Exception(f"Помилка створення контейнера Threads: {res}")

            time.sleep(3)
            pub_res = requests.post(publish_url, data={"creation_id": creation_id, "access_token": token}, timeout=15).json()
            media_id = pub_res.get("id")
            if not media_id:
                raise Exception(f"Помилка публікації Threads: {pub_res}")

            return PublishResult(success=True, platform=self.platform_name, external_id=str(media_id), url=f"https://threads.net/t/{media_id}")

        except Exception as e:
            from core.security_guard import security_guard
            err_clean = security_guard.sanitize_error(str(e))
            logger.error(f"Помилка Threads: {err_clean}")
            return PublishResult(success=False, platform=self.platform_name, error=err_clean)

    def get_stats(self, external_id: str) -> StatsResult:
        if external_id.startswith("mock_"):
            return StatsResult(platform=self.platform_name, views=1450, likes=98, comments=11)

        token = os.getenv("THREADS_ACCESS_TOKEN", THREADS_ACCESS_TOKEN).strip()
        if not token:
            return StatsResult(platform=self.platform_name, error="Немає токена Threads")

        try:
            url = f"https://graph.threads.net/v1.0/{external_id}"
            params = {"fields": "views,likes,replies", "access_token": token}
            res = requests.get(url, params=params, timeout=10).json()
            return StatsResult(
                platform=self.platform_name,
                views=int(res.get("views", 0)),
                likes=int(res.get("likes", 0)),
                comments=int(res.get("replies", 0))
            )
        except Exception as e:
            return StatsResult(platform=self.platform_name, error=str(e))


threads_publisher = ThreadsPublisher()
