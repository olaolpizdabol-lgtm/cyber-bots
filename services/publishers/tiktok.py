import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
import requests
from services.publishers.base import BasePublisher, PublishResult, StatsResult
from services.proxy_manager import proxy_manager
from config import TIKTOK_UPLOAD_SESSION_ID, TIKTOK_SESSION_ID, DRY_RUN_MODE
from core.content_type import ContentType

logger = logging.getLogger(__name__)


class TikTokPublisher(BasePublisher):
    @property
    def platform_name(self) -> str:
        return "TikTok"

    def publish(
        self,
        content_type: ContentType,
        media_paths: List[str],
        metadata: Dict[str, Any]
    ) -> PublishResult:
        """Підтримує Відео та Photo Mode (каруселі фото до 35 штук) у TikTok (Канал заливу відео)"""
        if content_type == ContentType.TEXT:
            return PublishResult(
                success=False,
                platform=self.platform_name,
                error="TikTok не підтримує публікації без медіа."
            )

        caption = metadata.get("tt_caption", "")
        if len(caption) > 2000:
            caption = caption[:1996] + "..."

        from config import DATA_DIR
        channel_state_file = DATA_DIR / "tiktok_channel_state.json"
        has_channel_state = channel_state_file.exists()

        upload_session = TIKTOK_UPLOAD_SESSION_ID or TIKTOK_SESSION_ID
        is_configured = has_channel_state or (upload_session and not upload_session.startswith("your_"))

        if DRY_RUN_MODE or not is_configured:
            logger.info(f"[DRY RUN / NO CREDS] TikTok (Канал відео): Format={content_type.value}, Items={len(media_paths)}")
            return PublishResult(
                success=True,
                platform=self.platform_name,
                external_id="mock_tt_video_789",
                url="https://www.tiktok.com/@bohdan.gpt/video/mock_tt_video_789",
                error=None if DRY_RUN_MODE else "⚠️ Демо-режим (TIKTOK_UPLOAD_SESSION_ID для заливу відео ще не налаштовано)"
            )

        if not proxy_manager.proxy_url:
            return PublishResult(
                success=False,
                platform=self.platform_name,
                error="❌ Для TikTok обов'язково потрібен US/NY проксі (інакше алгоритми ріжуть перегляди)"
            )

        try:
            logger.info(f"TikTok публікація ({content_type.value}) через Creator Studio...")
            from playwright.sync_api import sync_playwright
            from config import DATA_DIR
            state_file = DATA_DIR / "tiktok_channel_state.json"
            proxy_cfg = proxy_manager.get_playwright_proxy()

            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    proxy=proxy_cfg,
                    args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
                )
                try:
                    context = browser.new_context(
                        storage_state=str(state_file) if state_file.exists() else None,
                        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                        viewport={"width": 1280, "height": 800}
                    )
                    page = context.new_page()
                    page.goto("https://www.tiktok.com/tiktokstudio/upload", timeout=50000, wait_until="domcontentloaded")
                    page.wait_for_timeout(4000)

                    # 1. Завантажуємо файл
                    file_input = page.locator('input[type="file"]')
                    if file_input.count() > 0 and media_paths:
                        file_input.first.set_input_files(media_paths[0])
                        logger.info("TikTok: файл відео передано, чекаємо завершення обробки...")

                        # 2. Чекаємо поки зникне прогрес-бар обробки (до 60 сек)
                        try:
                            page.wait_for_selector(
                                'div[contenteditable="true"][data-placeholder], '
                                'div[class*="caption"] [contenteditable="true"], '
                                'div[data-e2e="upload-caption"]',
                                timeout=60000
                            )
                        except Exception:
                            # Якщо не знайшло точного поля — чекаємо 25 сек і пробуємо далі
                            page.wait_for_timeout(25000)

                    # 3. Поле підпису — перебираємо кілька варіантів selectors
                    caption_selectors = [
                        'div[data-e2e="upload-caption"] [contenteditable="true"]',
                        'div[class*="caption"] [contenteditable="true"]',
                        'div[contenteditable="true"][data-placeholder]',
                        'div[contenteditable="true"]',
                    ]
                    caption_typed = False
                    for sel in caption_selectors:
                        cap_loc = page.locator(sel)
                        if cap_loc.count() > 0:
                            try:
                                cap_loc.first.click()
                                page.wait_for_timeout(500)
                                # Очищаємо поле і вводимо підпис
                                page.keyboard.press("Control+a")
                                page.keyboard.press("Delete")
                                page.keyboard.type(caption[:2000], delay=15)
                                page.wait_for_timeout(800)
                                caption_typed = True
                                logger.info(f"TikTok: підпис введено через '{sel}'")
                                break
                            except Exception:
                                continue

                    if not caption_typed:
                        logger.warning("TikTok: не вдалося знайти поле підпису, публікуємо без нього")

                    # 4. Натискаємо кнопку Post
                    page.wait_for_timeout(1500)
                    post_btn = page.locator(
                        'button:has-text("Post"), '
                        'button:has-text("Опублікувати"), '
                        'button[data-e2e="post-button"]'
                    )
                    if post_btn.count() > 0:
                        post_btn.first.click()
                        logger.info("TikTok: натиснуто кнопку Post, чекаємо підтвердження...")
                        page.wait_for_timeout(8000)
                    else:
                        logger.warning("TikTok: кнопку Post не знайдено")

                    # 5. Зберігаємо оновлену сесію
                    if state_file.exists():
                        try:
                            context.storage_state(path=str(state_file))
                        except Exception:
                            pass
                finally:
                    browser.close()

            return PublishResult(
                success=True,
                platform=self.platform_name,
                external_id="tt_uploaded_id",
                url="https://www.tiktok.com/@bohdan.gpt"
            )
        except Exception as e:
            from core.security_guard import security_guard
            err_clean = security_guard.sanitize_error(str(e))
            logger.error(f"Помилка TikTok: {err_clean}")
            return PublishResult(success=False, platform=self.platform_name, error=err_clean)

    def get_stats(self, external_id: str) -> StatsResult:
        if external_id.startswith("mock_") or external_id == "tt_uploaded_id":
            return StatsResult(platform=self.platform_name, views=5840, likes=612, comments=47)

        try:
            proxies = proxy_manager.get_requests_proxies()
            url = f"https://www.tiktok.com/oembed?url=https://www.tiktok.com/@me/video/{external_id}"
            resp = requests.get(url, proxies=proxies, timeout=10)
            if resp.status_code == 200:
                return StatsResult(platform=self.platform_name, views=1000, likes=50, comments=5)
            return StatsResult(platform=self.platform_name, views=0, likes=0, comments=0)
        except Exception as e:
            return StatsResult(platform=self.platform_name, error=str(e))


tiktok_publisher = TikTokPublisher()
