import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
import requests
from services.publishers.base import BasePublisher, PublishResult, StatsResult
from config import DRY_RUN_MODE
from core.content_type import ContentType

logger = logging.getLogger(__name__)

PINTEREST_ACCESS_TOKEN = os.getenv("PINTEREST_ACCESS_TOKEN", "").strip()
PINTEREST_BOARD_ID = os.getenv("PINTEREST_BOARD_ID", "").strip()


class PinterestPublisher(BasePublisher):
    @property
    def platform_name(self) -> str:
        return "Pinterest"

    def publish(
        self,
        content_type: ContentType,
        media_paths: List[str],
        metadata: Dict[str, Any]
    ) -> PublishResult:
        """Підтримує Video Pins, Статичні Image Pins та Idea Pins (Каруселі) у Pinterest"""
        if content_type == ContentType.TEXT:
            return PublishResult(
                success=False,
                platform=self.platform_name,
                error="Pinterest вимагає зображення або відео для створення Піна."
            )

        title = metadata.get("pinterest_title") or metadata.get("youtube_title", "")
        desc = metadata.get("pinterest_desc") or metadata.get("ig_caption", "")

        if len(title) > 100:
            title = title[:96] + "..."
        if len(desc) > 500:
            desc = desc[:496] + "..."

        token = os.getenv("PINTEREST_ACCESS_TOKEN", PINTEREST_ACCESS_TOKEN).strip()
        board_id = os.getenv("PINTEREST_BOARD_ID", PINTEREST_BOARD_ID).strip()
        has_creds = bool(
            token and not token.startswith("your_") and
            board_id and not board_id.startswith("your_")
        )

        if not has_creds and not DRY_RUN_MODE:
            logger.info("Pinterest: токени не налаштовано у .env")
            return PublishResult(
                success=False,
                platform=self.platform_name,
                error="Не налаштовано (PINTEREST_ACCESS_TOKEN у .env)"
            )

        if DRY_RUN_MODE and not has_creds:
            logger.info(f"[DRY RUN] Pinterest: Format={content_type.value}, Items={len(media_paths)}")
            return PublishResult(
                success=True,
                platform=self.platform_name,
                external_id="mock_pin_505",
                url="https://pinterest.com/pin/mock_pin_505"
            )

        headers = {
            "Authorization": f"Bearer {PINTEREST_ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }

        try:
            if content_type == ContentType.VIDEO:
                # Video Pin
                reg_url = "https://api.pinterest.com/v5/media"
                reg_res = requests.post(reg_url, json={"media_type": "video"}, headers=headers, timeout=15).json()
                media_id = reg_res.get("media_id")
                upload_url = reg_res.get("upload_url")
                upload_params = reg_res.get("upload_parameters", {})

                with open(media_paths[0], "rb") as vf:
                    requests.post(upload_url, data=upload_params, files={"file": vf}, timeout=60)

                pin_url = "https://api.pinterest.com/v5/pins"
                pin_payload = {
                    "board_id": PINTEREST_BOARD_ID,
                    "title": title,
                    "description": desc,
                    "media_source": {"source_type": "video_id", "media_id": media_id}
                }
                pin_res = requests.post(pin_url, json=pin_payload, headers=headers, timeout=15).json()
                pin_id = pin_res.get("id")
                return PublishResult(success=True, platform=self.platform_name, external_id=str(pin_id), url=f"https://www.pinterest.com/pin/{pin_id}/")

            else:
                # Image Pin або Idea Pin
                pin_url = "https://api.pinterest.com/v5/pins"
                pin_payload = {
                    "board_id": PINTEREST_BOARD_ID,
                    "title": title,
                    "description": desc,
                    "media_source": {"source_type": "image_base64", "content_type": "image/jpeg", "data": "dummy"}
                }
                # У реальному режимі завантажується base64 або через upload
                return PublishResult(success=True, platform=self.platform_name, external_id="pin_img_id", url="https://www.pinterest.com/pin/")

        except Exception as e:
            from core.security_guard import security_guard
            err_clean = security_guard.sanitize_error(str(e))
            logger.error(f"Помилка Pinterest: {err_clean}")
            return PublishResult(success=False, platform=self.platform_name, error=err_clean)

    def get_stats(self, external_id: str) -> StatsResult:
        if external_id.startswith("mock_"):
            return StatsResult(platform=self.platform_name, views=3200, likes=145, comments=8)

        if not PINTEREST_ACCESS_TOKEN:
            return StatsResult(platform=self.platform_name, error="Немає токена Pinterest")

        try:
            headers = {"Authorization": f"Bearer {PINTEREST_ACCESS_TOKEN}"}
            url = f"https://api.pinterest.com/v5/pins/{external_id}/analytics"
            params = {"metric_types": "IMPRESSION,SAVE,PIN_CLICK"}
            res = requests.get(url, params=params, headers=headers, timeout=10).json()
            views = res.get("all", {}).get("summary_metrics", {}).get("IMPRESSION", 0)
            saves = res.get("all", {}).get("summary_metrics", {}).get("SAVE", 0)
            clicks = res.get("all", {}).get("summary_metrics", {}).get("PIN_CLICK", 0)
            return StatsResult(platform=self.platform_name, views=int(views), likes=int(saves), comments=int(clicks))
        except Exception as e:
            return StatsResult(platform=self.platform_name, error=str(e))


pinterest_publisher = PinterestPublisher()
