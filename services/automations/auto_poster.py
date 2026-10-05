import logging
import random
import time
import threading
from typing import Dict, Any, Optional, List

from core.browser_lock import BROWSER_LOCK
from core.media_processor import media_processor
from core.security_guard import security_guard
from core.content_type import (
    ContentType,
    FORMAT_SUPPORTED_PLATFORMS,
    PLATFORM_CONSTRAINTS
)
from core.database import (
    save_draft_post,
    update_post_platform_result,
    update_post_status,
    update_post_platform_stats,
    update_post_metadata,
    get_last_published_post,
    get_post_by_id
)
from services.gemini_ai import (
    gemini_service,
    sanitize_typography,
    truncate_at_word_boundary
)
from services.proxy_manager import (
    proxy_manager,
    IP_DEPENDENT_PLATFORMS,
    DIRECT_PLATFORMS
)
from services.publishers.base import PublishResult
from services.publishers.youtube import youtube_publisher
from services.publishers.instagram import instagram_publisher
from services.publishers.tiktok import tiktok_publisher
from services.publishers.facebook import facebook_publisher
from services.publishers.snapchat import snapchat_publisher
from services.publishers.twitter import twitter_publisher
from services.publishers.threads import threads_publisher
from services.publishers.pinterest import pinterest_publisher
from services.publishers.bluesky import bluesky_publisher
from services.publishers.telegram_channel import telegram_channel_publisher

logger = logging.getLogger(__name__)

TIER_1_PLATFORMS = ["tiktok", "instagram", "youtube", "facebook", "snapchat"]
TIER_2_PLATFORMS = ["twitter", "threads", "pinterest", "bluesky", "telegram"]
ALL_PLATFORMS = TIER_1_PLATFORMS + TIER_2_PLATFORMS

PUBLISHERS = {
    "youtube": youtube_publisher,
    "instagram": instagram_publisher,
    "tiktok": tiktok_publisher,
    "facebook": facebook_publisher,
    "snapchat": snapchat_publisher,
    "twitter": twitter_publisher,
    "threads": threads_publisher,
    "pinterest": pinterest_publisher,
    "bluesky": bluesky_publisher,
    "telegram": telegram_channel_publisher
}


class AutoPosterService:
    """
    Автоматизація #1 (Ідеальна точність розрахунків по форматах 2026):
    - Враховує точні слайд-ліміти кожної платформи (X: max 4, Bluesky: max 4, TikTok: max 35 фото, IG/Threads: max 10 мікс).
    - Автоматично обрізає або розділяє медіа під конкретні вимоги платформи.
    - Підтримує Mixed Media (фото + відео).
    - Маршрутизує тільки на 100% сумісні соцмережі.
    - Захищає від тіньового бану (Humanized Jitter, New York IP перевірка, очищення метаданих).
    - Забезпечує строгу типографіку (ТІЛЬКИ '-', ніяких '—' чи '–').
    """

    def detect_content_type(self, media_paths: List[str]) -> ContentType:
        """Визначає точний тип контенту на основі списку файлів"""
        if not media_paths:
            return ContentType.TEXT

        has_video = any(p.lower().endswith((".mp4", ".mov", ".mkv", ".avi", ".webm")) for p in media_paths)
        has_photo = any(p.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".heic")) for p in media_paths)

        if len(media_paths) == 1:
            return ContentType.VIDEO if has_video else ContentType.PHOTO

        if has_video and has_photo:
            return ContentType.MIXED_CAROUSEL

        if has_video and not has_photo:
            return ContentType.VIDEO

        return ContentType.CAROUSEL

    def process_incoming_content(
        self,
        content_type: Optional[ContentType] = None,
        media_paths: Optional[List[str]] = None,
        raw_text: Optional[str] = None,
        prompt_override: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Обробка вхідного контенту з повним розрахунком специфіки форматів
        """
        paths = media_paths or []
        if not content_type:
            content_type = self.detect_content_type(paths)

        cleaned_paths = []
        thumb_path = None

        if content_type == ContentType.VIDEO and paths:
            clean_v = media_processor.clean_and_prepare_video(paths[0])
            cleaned_paths.append(clean_v)
            thumb_path = media_processor.extract_thumbnail(clean_v)
        elif content_type in (ContentType.PHOTO, ContentType.CAROUSEL, ContentType.MIXED_CAROUSEL) and paths:
            for p in paths:
                if p.lower().endswith((".mp4", ".mov", ".mkv")):
                    cleaned_paths.append(media_processor.clean_and_prepare_video(p))
                else:
                    cleaned_paths.append(media_processor.clean_and_prepare_image(p))
            thumb_path = cleaned_paths[0] if cleaned_paths else None
        else:
            cleaned_paths = []

        # Генерація метаданих через Gemini з розрахунком лімітів та типографіки
        ai_data = gemini_service.generate_metadata(
            content_type=content_type,
            media_paths=cleaned_paths if cleaned_paths else None,
            raw_text=raw_text,
            prompt_override=prompt_override
        )

        post_id = save_draft_post(
            content_type=content_type,
            media_paths=cleaned_paths,
            metadata=ai_data
        )

        compatible_platforms = FORMAT_SUPPORTED_PLATFORMS.get(content_type, ALL_PLATFORMS)

        return {
            "post_id": post_id,
            "content_type": content_type,
            "media_paths": cleaned_paths,
            "thumb_path": thumb_path,
            "compatible_platforms": compatible_platforms,
            **ai_data
        }

    def process_incoming_video(self, raw_video_path: str, prompt_override: Optional[str] = None) -> Dict[str, Any]:
        return self.process_incoming_content(
            content_type=ContentType.VIDEO,
            media_paths=[raw_video_path],
            prompt_override=prompt_override
        )

    def prepare_media_for_platform(self, plat_key: str, content_type: ContentType, media_files: List[str]) -> List[str]:
        """
        Розраховує та адаптує медіа-файли під індивідуальні ліміти платформи:
        - X (Twitter) та Bluesky: рівно до 4 елементів.
        - TikTok: тільки фото у Photo Mode (без відео) до 35 штук.
        - Instagram/Threads/FB: до 10 елементів.
        """
        constraints = PLATFORM_CONSTRAINTS.get(plat_key, {})
        max_slides = constraints.get("max_slides", len(media_files))

        if not media_files:
            return []

        # Для відео - завжди перше відео
        if content_type == ContentType.VIDEO:
            videos = [p for p in media_files if p.lower().endswith((".mp4", ".mov", ".mkv"))]
            return [videos[0]] if videos else [media_files[0]]

        # Для TikTok Photo Mode: приймаються тільки фото!
        if plat_key == "tiktok":
            photos = [p for p in media_files if not p.lower().endswith((".mp4", ".mov", ".mkv"))]
            return photos[:max_slides]

        # Для X (Twitter) при каруселях: беремо тільки фото до 4 штук
        if plat_key == "twitter" and content_type in (ContentType.CAROUSEL, ContentType.MIXED_CAROUSEL):
            photos = [p for p in media_files if not p.lower().endswith((".mp4", ".mov", ".mkv"))]
            if photos:
                return photos[:4]
            return media_files[:1]

        # Для Bluesky: строго до 4 фото
        if plat_key == "bluesky" and content_type in (ContentType.CAROUSEL, ContentType.MIXED_CAROUSEL):
            photos = [p for p in media_files if not p.lower().endswith((".mp4", ".mov", ".mkv"))]
            return photos[:4]

        # Для решти платформ (Instagram, Threads, FB, Telegram):
        return media_files[:max_slides] if max_slides > 0 else media_files

    def condense_post_texts(
        self,
        post_id: int,
        target_platform: Optional[str] = None,
        max_chars: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Інтелектуальне скорочення тексту для збереженого поста.
        Якщо target_platform та max_chars задані - скорочує для конкретної платформи.
        Якщо ні - пакетно скорочує для всіх мікроблогів (X, Threads, Bluesky).
        """
        post = get_post_by_id(post_id)
        if not post:
            return {"error": f"Публікацію #{post_id} не знайдено"}

        source_text = post.get("ig_caption") or post.get("yt_desc") or post.get("tw_post") or ""
        media_paths = post.get("media_paths_list") or ([post["clean_video_path"]] if post.get("clean_video_path") else None)

        if target_platform and max_chars:
            condensed = gemini_service.condense_text(
                text=source_text,
                target_platform=target_platform,
                max_chars=max_chars,
                media_paths=media_paths
            )
            plat_field_map = {
                "twitter": "twitter_post",
                "threads": "threads_post",
                "bluesky": "bluesky_post",
                "youtube": "youtube_title",
                "snapchat": "snapchat_title",
                "pinterest": "pinterest_desc"
            }
            field_name = plat_field_map.get(target_platform.lower(), "twitter_post")
            update_post_metadata(post_id, {field_name: condensed})
        else:
            batch_updates = gemini_service.condense_all_for_post(raw_text=source_text, media_paths=media_paths)
            update_post_metadata(post_id, batch_updates)

        return get_post_by_id(post_id) or {}

    def publish_post(self, post_id: int, platforms: Optional[List[str]] = None) -> Dict[str, Any]:
        post = get_post_by_id(post_id)
        if not post:
            return {"error": f"Публікацію з ID {post_id} не знайдено"}

        c_type_str = post.get("content_type", "video")
        try:
            content_type = ContentType(c_type_str)
        except Exception:
            content_type = ContentType.VIDEO

        supported_by_format = FORMAT_SUPPORTED_PLATFORMS.get(content_type, ALL_PLATFORMS)
        chosen_platforms = platforms or supported_by_format
        valid_platforms = [p for p in chosen_platforms if p in supported_by_format]

        all_media_files = post.get("media_paths_list") or []
        if not all_media_files and post.get("clean_video_path"):
            all_media_files = [post["clean_video_path"]]

        results = {}
        raw_metadata = {
            "youtube_title": post.get("yt_title", ""),
            "youtube_desc": post.get("yt_desc", ""),
            "ig_caption": post.get("ig_caption", ""),
            "tt_caption": post.get("tt_caption", ""),
            "fb_caption": post.get("fb_caption", ""),
            "snapchat_title": post.get("snap_title", ""),
            "twitter_post": post.get("tw_post", ""),
            "threads_post": post.get("threads_post", ""),
            "pinterest_title": post.get("pin_title", ""),
            "pinterest_desc": post.get("pin_desc", ""),
            "bluesky_post": post.get("bsky_post", "")
        }

        # 100% суворе дотримання типографіки (дефіс '-' замість '—')
        metadata = {k: sanitize_typography(v) for k, v in raw_metadata.items()}

        for plat_key in valid_platforms:
            publisher = PUBLISHERS.get(plat_key)
            if not publisher:
                continue

            # Невелика пауза між викликами API різних мереж
            if results:
                jitter = random.uniform(0.5, 1.0)
                logger.info(f"Пауза {jitter:.2f} сек перед публікацією на {plat_key}...")
                time.sleep(jitter)

            # 2. Pre-flight перевірка безпеки та IP (US/NY для чутливих мереж)
            is_safe, safety_msg = proxy_manager.verify_platform_safety(plat_key)
            if not is_safe:
                logger.warning(f"⛔️ Безпековий захист: публікацію на {plat_key} заблоковано: {safety_msg}")
                err_clean = security_guard.sanitize_error(safety_msg)
                res = PublishResult(
                    success=False,
                    platform=plat_key,
                    error=err_clean
                )
                results[plat_key] = res
                update_post_platform_result(
                    post_id=post_id,
                    platform=plat_key,
                    error=err_clean
                )
                continue

            # 3. Точний розрахунок медіа під ліміти платформи
            platform_media = self.prepare_media_for_platform(plat_key, content_type, all_media_files)

            logger.info(f"Публікація #{post_id} ({content_type.value}) на {publisher.platform_name} (файлів: {len(platform_media)})...")
            if plat_key in ("tiktok", "snapchat"):
                logger.info(f"Очікуємо захоплення браузерного локу для {publisher.platform_name}...")
                with BROWSER_LOCK:
                    logger.info(f"Браузерний лок захоплено для {publisher.platform_name}, починаємо публікацію...")
                    try:
                        res = publisher.publish(
                            content_type=content_type,
                            media_paths=platform_media,
                            metadata=metadata
                        )
                    finally:
                        logger.info(f"Браузерний лок для {publisher.platform_name} успішно звільнено.")
            else:
                res = publisher.publish(
                    content_type=content_type,
                    media_paths=platform_media,
                    metadata=metadata
                )

            # Маскування будь-яких випадкових чутливих даних у тексті помилки
            if res.error:
                res.error = security_guard.sanitize_error(res.error)

            results[plat_key] = res
            update_post_platform_result(
                post_id=post_id,
                platform=plat_key,
                external_id=res.external_id,
                error=res.error
            )

        all_success = all(r.success for r in results.values()) if results else False
        update_post_status(post_id, "published" if all_success else "partial")

        return results

    def retry_failed_platforms(self, post_id: int, platforms: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Перезапуск публікації тільки для тих платформ, де стався збій або помилка.
        """
        from core.database import get_failed_platforms_for_post
        failed = platforms or get_failed_platforms_for_post(post_id)
        if not failed:
            return {"message": "Усі сумісні платформи вже успішно опубліковані!", "results": {}}

        logger.info(f"🔄 Перезапуск публікації поста #{post_id} для платформ: {failed}...")
        results = self.publish_post(post_id, platforms=failed)
        return {
            "post_id": post_id,
            "retried_platforms": failed,
            "results": results
        }

    def get_post_analytics_summary(self, post_id: int) -> Dict[str, Any]:
        """
        Агрегована статистика публікації по всіх 10 платформах
        з підрахунком сумарних переглядів, лайків та визначенням топ-мережі.
        """
        post = get_post_by_id(post_id)
        if not post:
            return {"error": f"Пост #{post_id} не знайдено"}

        col_id_map = {
            "youtube": "yt_video_id",
            "instagram": "ig_media_id",
            "tiktok": "tt_video_id",
            "facebook": "fb_video_id",
            "snapchat": "snap_media_id",
            "twitter": "tw_tweet_id",
            "threads": "threads_media_id",
            "pinterest": "pin_id",
            "bluesky": "bsky_uri",
            "telegram": "error_message"
        }

        total_views = 0
        total_likes = 0
        total_comments = 0
        platform_stats = {}
        top_platform = None
        max_views = -1

        for plat_key, pub in PUBLISHERS.items():
            ext_id = post.get(col_id_map.get(plat_key, ""))
            if ext_id:
                stat = pub.get_stats(ext_id)
                platform_stats[plat_key] = stat
                if not stat.error:
                    update_post_platform_stats(post_id, plat_key, stat.views, stat.likes)
                    total_views += stat.views
                    total_likes += stat.likes
                    total_comments += stat.comments
                    if stat.views > max_views:
                        max_views = stat.views
                        top_platform = pub.platform_name

        return {
            "post_id": post_id,
            "total_views": total_views,
            "total_likes": total_likes,
            "total_comments": total_comments,
            "top_platform": top_platform or "Не визначено",
            "platforms": platform_stats
        }

    def get_latest_video_stats(self) -> Dict[str, Any]:
        last_post = get_last_published_post()
        if not last_post:
            return {"error": "Ще не було жодної публікації."}

        post_id = last_post["id"]
        stats_summary = {
            "post_id": post_id,
            "created_at": last_post["created_at"],
            "title": last_post.get("yt_title") or last_post.get("snap_title") or last_post.get("tw_post") or "Публікація",
            "platforms": {}
        }

        col_id_map = {
            "youtube": "yt_video_id",
            "instagram": "ig_media_id",
            "tiktok": "tt_video_id",
            "facebook": "fb_video_id",
            "snapchat": "snap_media_id",
            "twitter": "tw_tweet_id",
            "threads": "threads_media_id",
            "pinterest": "pin_id",
            "bluesky": "bsky_uri",
            "telegram": "error_message"
        }

        for plat_key, pub in PUBLISHERS.items():
            ext_id = last_post.get(col_id_map.get(plat_key, ""))
            if ext_id:
                stat = pub.get_stats(ext_id)
                stats_summary["platforms"][plat_key] = stat
                if not stat.error:
                    update_post_platform_stats(post_id, plat_key, stat.views, stat.likes)

        return stats_summary


auto_poster = AutoPosterService()
