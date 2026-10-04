import os
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
import requests
from requests_oauthlib import OAuth1
from services.publishers.base import BasePublisher, PublishResult, StatsResult
from config import DRY_RUN_MODE
from core.content_type import ContentType

logger = logging.getLogger(__name__)

TWITTER_API_KEY = os.getenv("TWITTER_API_KEY", "").strip()
TWITTER_API_SECRET = os.getenv("TWITTER_API_SECRET", "").strip()
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN", "").strip()
TWITTER_ACCESS_TOKEN_SECRET = os.getenv("TWITTER_ACCESS_TOKEN_SECRET", "").strip()


class TwitterPublisher(BasePublisher):
    @property
    def platform_name(self) -> str:
        return "X (Twitter)"

    def _get_auth(self) -> Optional[OAuth1]:
        if not (TWITTER_API_KEY and TWITTER_API_SECRET and TWITTER_ACCESS_TOKEN and TWITTER_ACCESS_TOKEN_SECRET):
            return None
        if TWITTER_API_KEY.startswith("your_"):
            return None
        return OAuth1(TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET)

    def publish(
        self,
        content_type: ContentType,
        media_paths: List[str],
        metadata: Dict[str, Any]
    ) -> PublishResult:
        """Підтримує Відео, Фото, Каруселі (до 4 фото) та Текстові твіти у X (Twitter)"""
        post_text = metadata.get("twitter_post") or metadata.get("youtube_title", "")
        if len(post_text) > 280:
            post_text = post_text[:276] + "..."

        auth = self._get_auth()
        if not auth and not DRY_RUN_MODE:
            logger.info("X (Twitter): ключі не налаштовано у .env")
            return PublishResult(
                success=False,
                platform=self.platform_name,
                error="Не налаштовано (TWITTER ключі у .env)"
            )

        if DRY_RUN_MODE and not auth:
            logger.info(f"[DRY RUN] X: Format={content_type.value}, Text len={len(post_text)}")
            return PublishResult(
                success=True,
                platform=self.platform_name,
                external_id="mock_tweet_303",
                url="https://x.com/user/status/mock_tweet_303"
            )

        upload_url = "https://upload.twitter.com/1.1/media/upload.json"
        tweet_url = "https://api.twitter.com/2/tweets"

        try:
            media_ids = []

            if content_type == ContentType.VIDEO and media_paths:
                # Відео через Chunked Upload
                v_path = Path(media_paths[0])
                total_bytes = v_path.stat().st_size
                init_data = {"command": "INIT", "media_type": "video/mp4", "total_bytes": str(total_bytes), "media_category": "tweet_video"}
                init_res = requests.post(upload_url, data=init_data, auth=auth, timeout=15).json()
                media_id = init_res.get("media_id_string")

                segment_id = 0
                with open(v_path, "rb") as f:
                    while True:
                        chunk = f.read(4 * 1024 * 1024)
                        if not chunk:
                            break
                        requests.post(upload_url, data={"command": "APPEND", "media_id": media_id, "segment_index": str(segment_id)}, files={"media": chunk}, auth=auth, timeout=30)
                        segment_id += 1

                fin_res = requests.post(upload_url, data={"command": "FINALIZE", "media_id": media_id}, auth=auth, timeout=15).json()
                processing = fin_res.get("processing_info")
                while processing and processing.get("state") in ("pending", "in_progress"):
                    time.sleep(processing.get("check_after_secs", 2))
                    status_res = requests.get(upload_url, params={"command": "STATUS", "media_id": media_id}, auth=auth, timeout=10).json()
                    processing = status_res.get("processing_info")
                media_ids.append(media_id)

            elif content_type in (ContentType.PHOTO, ContentType.CAROUSEL) and media_paths:
                # До 4 фото у твіті
                for img_p in media_paths[:4]:
                    with open(img_p, "rb") as f:
                        res = requests.post(upload_url, files={"media": f}, auth=auth, timeout=15).json()
                        mid = res.get("media_id_string")
                        if mid:
                            media_ids.append(mid)

            tweet_payload = {"text": post_text}
            if media_ids:
                tweet_payload["media"] = {"media_ids": media_ids}

            tweet_res = requests.post(tweet_url, json=tweet_payload, auth=auth, timeout=15).json()
            tweet_id = tweet_res.get("data", {}).get("id")
            if not tweet_id:
                raise Exception(f"Помилка створення твіту: {tweet_res}")

            return PublishResult(success=True, platform=self.platform_name, external_id=tweet_id, url=f"https://x.com/i/status/{tweet_id}")

        except Exception as e:
            from core.security_guard import security_guard
            err_clean = security_guard.sanitize_error(str(e))
            logger.error(f"Помилка X (Twitter): {err_clean}")
            return PublishResult(success=False, platform=self.platform_name, error=err_clean)

    def get_stats(self, external_id: str) -> StatsResult:
        if external_id.startswith("mock_"):
            return StatsResult(platform=self.platform_name, views=1890, likes=132, comments=14)

        auth = self._get_auth()
        if not auth:
            return StatsResult(platform=self.platform_name, error="Немає ключів X")

        try:
            url = f"https://api.twitter.com/2/tweets/{external_id}"
            params = {"tweet.fields": "public_metrics"}
            res = requests.get(url, params=params, auth=auth, timeout=10).json()
            metrics = res.get("data", {}).get("public_metrics", {})
            return StatsResult(
                platform=self.platform_name,
                views=int(metrics.get("impression_count", 0)),
                likes=int(metrics.get("like_count", 0)),
                comments=int(metrics.get("reply_count", 0))
            )
        except Exception as e:
            return StatsResult(platform=self.platform_name, error=str(e))


twitter_publisher = TwitterPublisher()
