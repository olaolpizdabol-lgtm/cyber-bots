import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from services.publishers.base import BasePublisher, PublishResult, StatsResult
from config import YOUTUBE_CLIENT_SECRETS_FILE, YOUTUBE_TOKEN_FILE, DRY_RUN_MODE
from core.content_type import ContentType

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"]


class YouTubeShortsPublisher(BasePublisher):
    @property
    def platform_name(self) -> str:
        return "YouTube Shorts"

    def _get_authenticated_service(self):
        token_path = Path(YOUTUBE_TOKEN_FILE)
        creds = None
        if token_path.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
            except Exception as e:
                logger.warning(f"Помилка читання токена YouTube: {e}")

        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                with open(token_path, "w") as token_file:
                    token_file.write(creds.to_json())
            except Exception as e:
                logger.error(f"Не вдалося оновити токен YouTube: {e}")
                creds = None

        if not creds or not creds.valid:
            return None

        return build("youtube", "v3", credentials=creds)

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
                error="YouTube Shorts підтримує тільки вертикальне відео."
            )

        video_path = media_paths[0] if media_paths else ""
        title = metadata.get("youtube_title", "Shorts Video #shorts")
        desc = metadata.get("youtube_desc", "")

        if len(title) > 100:
            title = title[:96] + "..."

        if DRY_RUN_MODE or not Path(YOUTUBE_TOKEN_FILE).exists():
            logger.info(f"[DRY RUN / NO CREDS] YouTube Shorts: Title='{title}'")
            return PublishResult(
                success=True,
                platform=self.platform_name,
                external_id="mock_yt_shorts_123",
                url="https://youtube.com/shorts/mock_yt_shorts_123",
                error=None if DRY_RUN_MODE else "⚠️ Демо-режим (YOUTUBE_TOKEN_FILE ще не налаштовано)"
            )

        service = self._get_authenticated_service()
        if not service:
            return PublishResult(
                success=False,
                platform=self.platform_name,
                error="Потрібна авторизація YouTube (запустіть scripts/auth_youtube.py)"
            )

        try:
            body = {
                "snippet": {
                    "title": title,
                    "description": desc,
                    "tags": [t.strip("#") for t in desc.split() if t.startswith("#")][:10],
                    "categoryId": "22"
                },
                "status": {
                    "privacyStatus": "public",
                    "selfDeclaredMadeForKids": False
                }
            }

            media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True)
            request = service.videos().insert(part="snippet,status", body=body, media_body=media)
            response = request.execute()
            video_id = response.get("id")

            return PublishResult(
                success=True,
                platform=self.platform_name,
                external_id=video_id,
                url=f"https://youtube.com/shorts/{video_id}"
            )
        except Exception as e:
            from core.security_guard import security_guard
            err_clean = security_guard.sanitize_error(str(e))
            logger.error(f"Помилка YouTube Shorts: {err_clean}")
            return PublishResult(success=False, platform=self.platform_name, error=err_clean)

    def get_stats(self, external_id: str) -> StatsResult:
        if external_id.startswith("mock_"):
            return StatsResult(platform=self.platform_name, views=1250, likes=89, comments=12)

        service = self._get_authenticated_service()
        if not service:
            return StatsResult(platform=self.platform_name, error="Немає доступу до YouTube API")

        try:
            resp = service.videos().list(part="statistics", id=external_id).execute()
            items = resp.get("items", [])
            if not items:
                return StatsResult(platform=self.platform_name, error="Відео не знайдено")

            stats = items[0].get("statistics", {})
            return StatsResult(
                platform=self.platform_name,
                views=int(stats.get("viewCount", 0)),
                likes=int(stats.get("likeCount", 0)),
                comments=int(stats.get("commentCount", 0))
            )
        except Exception as e:
            return StatsResult(platform=self.platform_name, error=str(e))


youtube_publisher = YouTubeShortsPublisher()
