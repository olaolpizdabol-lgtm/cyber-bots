import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
import requests
from services.publishers.base import BasePublisher, PublishResult, StatsResult
from services.proxy_manager import proxy_manager
from config import DRY_RUN_MODE
from core.content_type import ContentType

logger = logging.getLogger(__name__)

SNAPCHAT_ACCESS_TOKEN = os.getenv("SNAPCHAT_ACCESS_TOKEN", "").strip()
SNAPCHAT_ACCOUNT_ID = os.getenv("SNAPCHAT_ACCOUNT_ID", "").strip()


class SnapchatSpotlightPublisher(BasePublisher):
    @property
    def platform_name(self) -> str:
        return "Snapchat Spotlight"

    def publish(
        self,
        content_type: ContentType,
        media_paths: List[str],
        metadata: Dict[str, Any]
    ) -> PublishResult:
        if content_type != ContentType.VIDEO:
            return PublishResult(
                success=False,
                platform=self.platform_name,
                error="Snapchat Spotlight підтримує тільки вертикальне відео."
            )

        video_path = media_paths[0] if media_paths else ""
        title = metadata.get("snapchat_title") or metadata.get("youtube_title", "")
        if len(title) > 100:
            title = title[:96] + "..."

        if DRY_RUN_MODE or not SNAPCHAT_ACCESS_TOKEN:
            logger.info(f"[DRY RUN / NO CREDS] Snapchat Spotlight: Title='{title}'")
            return PublishResult(
                success=True,
                platform=self.platform_name,
                external_id="mock_snap_spotlight_202",
                url="https://snapchat.com/spotlight/mock_snap_spotlight_202",
                error=None if DRY_RUN_MODE else "⚠️ Демо-режим (SNAPCHAT токени не налаштовано)"
            )

        proxies = proxy_manager.get_requests_proxies()
        try:
            url = f"https://adsapi.snapchat.com/v1/media/{SNAPCHAT_ACCOUNT_ID}/spotlight"
            headers = {"Authorization": f"Bearer {SNAPCHAT_ACCESS_TOKEN}"}
            
            with open(video_path, "rb") as vf:
                files = {"file": (Path(video_path).name, vf, "video/mp4")}
                data = {"caption": title}
                res = requests.post(url, headers=headers, files=files, data=data, proxies=proxies, timeout=60).json()

            media_id = res.get("media", {}).get("id") or res.get("id")
            if not media_id:
                raise Exception(f"Помилка публікації в Spotlight: {res}")

            return PublishResult(
                success=True,
                platform=self.platform_name,
                external_id=str(media_id),
                url=f"https://snapchat.com/spotlight/{media_id}"
            )
        except Exception as e:
            from core.security_guard import security_guard
            err_clean = security_guard.sanitize_error(str(e))
            logger.error(f"Помилка Snapchat Spotlight: {err_clean}")
            return PublishResult(success=False, platform=self.platform_name, error=err_clean)

    def get_stats(self, external_id: str) -> StatsResult:
        if external_id.startswith("mock_"):
            return StatsResult(platform=self.platform_name, views=4200, likes=310, comments=24)

        if not SNAPCHAT_ACCESS_TOKEN:
            return StatsResult(platform=self.platform_name, error="Немає токена Snapchat")

        proxies = proxy_manager.get_requests_proxies()
        try:
            url = f"https://adsapi.snapchat.com/v1/media/{external_id}/stats"
            headers = {"Authorization": f"Bearer {SNAPCHAT_ACCESS_TOKEN}"}
            res = requests.get(url, headers=headers, proxies=proxies, timeout=10).json()
            views = res.get("stats", {}).get("views", 0)
            likes = res.get("stats", {}).get("favorites", 0)
            return StatsResult(
                platform=self.platform_name,
                views=int(views),
                likes=int(likes),
                comments=0
            )
        except Exception as e:
            return StatsResult(platform=self.platform_name, error=str(e))


snapchat_publisher = SnapchatSpotlightPublisher()
