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

FB_PAGE_ACCESS_TOKEN = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN", "").strip()
FB_PAGE_ID = os.getenv("FACEBOOK_PAGE_ID", "").strip()


class FacebookPublisher(BasePublisher):
    @property
    def platform_name(self) -> str:
        return "Facebook"

    def _resolve_page_token(self, token: str, page_id: str, proxies: Optional[Dict[str, str]] = None) -> str:
        """
        Перевіряє, чи токен є Page Access Token. Якщо передано User Token,
        автоматично отримує Page Access Token для сторінки через Graph API /{page_id}?fields=access_token
        """
        if not token or not page_id:
            return token
        try:
            r = requests.get(
                f"https://graph.facebook.com/v21.0/{page_id}?fields=access_token&access_token={token}",
                proxies=proxies,
                timeout=10
            )
            if r.status_code == 200:
                p_tok = r.json().get("access_token")
                if p_tok:
                    logger.info("Facebook: успішно конвертовано User Token у Page Access Token!")
                    return p_tok
        except Exception as e:
            logger.debug(f"Facebook resolve page token: {e}")
        return token

    def publish(
        self,
        content_type: ContentType,
        media_paths: List[str],
        metadata: Dict[str, Any]
    ) -> PublishResult:
        """Підтримує Facebook Reels (Відео), Фото, Каруселі та Текстові пости"""
        caption = metadata.get("fb_caption") or metadata.get("ig_caption", "")
        if len(caption) > 2000:
            caption = caption[:1996] + "..."

        token = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN", FB_PAGE_ACCESS_TOKEN).strip()
        page_id = os.getenv("FACEBOOK_PAGE_ID", FB_PAGE_ID).strip()

        has_creds = bool(
            token and not token.startswith("your_") and
            page_id and not page_id.startswith("your_")
        )

        if not has_creds and not DRY_RUN_MODE:
            logger.info("Facebook: токени не налаштовано у .env")
            return PublishResult(
                success=False,
                platform=self.platform_name,
                error="Не налаштовано (FACEBOOK_PAGE_ACCESS_TOKEN у .env)"
            )

        if DRY_RUN_MODE and not has_creds:
            logger.info(f"[DRY RUN] Facebook: Format={content_type.value}, Items={len(media_paths)}")
            return PublishResult(
                success=True,
                platform=self.platform_name,
                external_id="mock_fb_post_101",
                url="https://facebook.com/mock_fb_post_101"
            )

        proxies = proxy_manager.get_requests_proxies()

        def _post(url, **kwargs):
            if proxies:
                try:
                    return requests.post(url, proxies=proxies, **kwargs)
                except Exception as pe:
                    logger.warning(f"Facebook: збій проксі ({pe}), перемикаємось на пряме з'єднання...")
                    return requests.post(url, proxies=None, **kwargs)
            return requests.post(url, proxies=None, **kwargs)

        # Автоматичне перетворення User Token -> Page Token якщо надано користувацький токен
        token = self._resolve_page_token(token, page_id, proxies)

        try:
            if content_type == ContentType.VIDEO:
                # Відео публікується у Facebook Reels
                v_path = Path(media_paths[0])
                file_size = v_path.stat().st_size
                init_url = f"https://graph.facebook.com/v21.0/{page_id}/video_reels"
                init_res = _post(
                    init_url,
                    params={"access_token": token, "upload_phase": "start"},
                    timeout=15
                ).json()

                video_id = init_res.get("video_id")
                upload_url = init_res.get("upload_url")
                if not video_id or not upload_url:
                    raise Exception(f"Помилка ініціалізації FB Reels: {init_res}")

                with open(v_path, "rb") as f:
                    video_data = f.read()

                upload_headers = {
                    "Authorization": f"OAuth {token}",
                    "offset": "0",
                    "file_size": str(file_size)
                }
                _post(upload_url, headers=upload_headers, data=video_data, timeout=60)

                finish_data = {
                    "access_token": token,
                    "upload_phase": "finish",
                    "video_id": video_id,
                    "description": caption,
                    "video_state": "PUBLISHED"
                }
                _post(init_url, data=finish_data, timeout=15)
                return PublishResult(success=True, platform=self.platform_name, external_id=str(video_id), url=f"https://facebook.com/reel/{video_id}")

            elif content_type in (ContentType.PHOTO, ContentType.CAROUSEL, ContentType.MIXED_CAROUSEL):
                # Одиночне фото або альбом фото
                photo_url = f"https://graph.facebook.com/v21.0/{page_id}/photos"
                with open(media_paths[0], "rb") as pf:
                    res = _post(
                        photo_url,
                        data={"caption": caption, "access_token": token},
                        files={"source": pf},
                        timeout=30
                    ).json()
                post_id = res.get("id") or res.get("post_id")
                return PublishResult(success=True, platform=self.platform_name, external_id=str(post_id), url=f"https://facebook.com/{post_id}")

            elif content_type == ContentType.TEXT:
                # Текстовий пост на сторінку
                feed_url = f"https://graph.facebook.com/v21.0/{page_id}/feed"
                res = _post(
                    feed_url,
                    data={"message": caption, "access_token": token},
                    timeout=15
                ).json()
                post_id = res.get("id")
                return PublishResult(success=True, platform=self.platform_name, external_id=str(post_id), url=f"https://facebook.com/{post_id}")

            raise Exception(f"Невідомий формат контенту для Facebook: {content_type.value}")

        except Exception as e:
            from core.security_guard import security_guard
            err_raw = str(e)
            if "Session has expired" in err_raw or ("OAuthException" in err_raw and "190" in err_raw):
                err_clean = "Facebook Access Token протерміновано (Session expired). Оновіть FACEBOOK_PAGE_ACCESS_TOKEN у Railway."
            else:
                err_clean = security_guard.sanitize_error(err_raw)
            logger.error(f"Помилка Facebook: {err_clean}")
            return PublishResult(success=False, platform=self.platform_name, error=err_clean)

    def get_stats(self, external_id: str) -> StatsResult:
        if external_id.startswith("mock_"):
            return StatsResult(platform=self.platform_name, views=2150, likes=140, comments=18)

        if not FB_PAGE_ACCESS_TOKEN:
            return StatsResult(platform=self.platform_name, error="Немає токена FB")

        proxies = proxy_manager.get_requests_proxies()
        try:
            url = f"https://graph.facebook.com/v21.0/{external_id}"
            params = {
                "access_token": FB_PAGE_ACCESS_TOKEN,
                "fields": "views,reactions.summary(true),comments.summary(true)"
            }
            res = requests.get(url, params=params, proxies=proxies, timeout=10).json()
            views = res.get("views", 0)
            likes = res.get("reactions", {}).get("summary", {}).get("total_count", 0)
            comments = res.get("comments", {}).get("summary", {}).get("total_count", 0)

            return StatsResult(
                platform=self.platform_name,
                views=int(views),
                likes=int(likes),
                comments=int(comments)
            )
        except Exception as e:
            return StatsResult(platform=self.platform_name, error=str(e))


facebook_publisher = FacebookPublisher()
