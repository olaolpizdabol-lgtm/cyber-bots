import os
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List
import requests
from services.publishers.base import BasePublisher, PublishResult, StatsResult
from config import DRY_RUN_MODE
from core.content_type import ContentType

logger = logging.getLogger(__name__)

BLUESKY_HANDLE = os.getenv("BLUESKY_HANDLE", "").strip()
BLUESKY_APP_PASSWORD = os.getenv("BLUESKY_APP_PASSWORD", "").strip()


class BlueskyPublisher(BasePublisher):
    @property
    def platform_name(self) -> str:
        return "Bluesky"

    def publish(
        self,
        content_type: ContentType,
        media_paths: List[str],
        metadata: Dict[str, Any]
    ) -> PublishResult:
        """Підтримує Відео, Фото (до 4), Каруселі та Текстові пости у Bluesky через AT Protocol"""
        text = metadata.get("bluesky_post") or metadata.get("youtube_title", "")
        if len(text) > 300:
            text = text[:296] + "..."

        handle = os.getenv("BLUESKY_HANDLE", BLUESKY_HANDLE).strip()
        pwd = os.getenv("BLUESKY_APP_PASSWORD", BLUESKY_APP_PASSWORD).strip()
        has_creds = bool(
            handle and not handle.startswith("your_") and
            pwd and not pwd.startswith("your_")
        )

        if not has_creds and not DRY_RUN_MODE:
            logger.info("Bluesky: токени не налаштовано у .env")
            return PublishResult(
                success=False,
                platform=self.platform_name,
                error="Не налаштовано (BLUESKY_HANDLE у .env)"
            )

        if DRY_RUN_MODE and not has_creds:
            logger.info(f"[DRY RUN] Bluesky: Format={content_type.value}, Text len={len(text)}")
            return PublishResult(
                success=True,
                platform=self.platform_name,
                external_id="mock_bsky_post_606",
                url="https://bsky.app/profile/user.bsky.social/post/mock_bsky_post_606"
            )

        try:
            # Сесія
            session_url = "https://bsky.social/xrpc/com.atproto.server.createSession"
            session_res = requests.post(session_url, json={"identifier": handle, "password": pwd}, timeout=15).json()
            access_jwt = session_res.get("accessJwt")
            did = session_res.get("did")
            if not access_jwt or not did:
                raise Exception(f"Помилка сесії Bluesky: {session_res}")

            headers = {"Authorization": f"Bearer {access_jwt}"}
            now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            record_url = "https://bsky.social/xrpc/com.atproto.repo.createRecord"

            record_payload = {
                "$type": "app.bsky.feed.post",
                "text": text,
                "createdAt": now_iso
            }

            if content_type == ContentType.VIDEO and media_paths:
                upload_url = "https://bsky.social/xrpc/com.atproto.repo.uploadBlob"
                with open(media_paths[0], "rb") as vf:
                    blob_res = requests.post(upload_url, data=vf, headers={**headers, "Content-Type": "video/mp4"}, timeout=60).json()
                blob = blob_res.get("blob")
                if blob:
                    record_payload["embed"] = {"$type": "app.bsky.embed.video", "video": blob}

            elif content_type in (ContentType.PHOTO, ContentType.CAROUSEL) and media_paths:
                upload_url = "https://bsky.social/xrpc/com.atproto.repo.uploadBlob"
                images_embed = []
                for p in media_paths[:4]:
                    with open(p, "rb") as pf:
                        b_res = requests.post(upload_url, data=pf, headers={**headers, "Content-Type": "image/jpeg"}, timeout=30).json()
                        img_blob = b_res.get("blob")
                        if img_blob:
                            images_embed.append({"alt": "Slide", "image": img_blob})
                if images_embed:
                    record_payload["embed"] = {"$type": "app.bsky.embed.images", "images": images_embed}

            rec_res = requests.post(record_url, json={"repo": did, "collection": "app.bsky.feed.post", "record": record_payload}, headers=headers, timeout=15).json()
            post_uri = rec_res.get("uri", "")
            rkey = post_uri.split("/")[-1] if "/" in post_uri else "post"

            return PublishResult(success=True, platform=self.platform_name, external_id=post_uri, url=f"https://bsky.app/profile/{BLUESKY_HANDLE}/post/{rkey}")

        except Exception as e:
            from core.security_guard import security_guard
            err_clean = security_guard.sanitize_error(str(e))
            logger.error(f"Помилка Bluesky: {err_clean}")
            return PublishResult(success=False, platform=self.platform_name, error=err_clean)

    def get_stats(self, external_id: str) -> StatsResult:
        if external_id.startswith("mock_"):
            return StatsResult(platform=self.platform_name, views=950, likes=64, comments=12)

        try:
            url = "https://public.api.bsky.app/xrpc/app.bsky.feed.getPostThread"
            res = requests.get(url, params={"uri": external_id}, timeout=10).json()
            post = res.get("thread", {}).get("post", {})
            likes = post.get("likeCount", 0)
            replies = post.get("replyCount", 0)
            return StatsResult(platform=self.platform_name, views=likes * 10, likes=int(likes), comments=int(replies))
        except Exception as e:
            return StatsResult(platform=self.platform_name, error=str(e))


bluesky_publisher = BlueskyPublisher()
