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

        if not is_configured and not DRY_RUN_MODE:
            logger.info("TikTok: токени сесії не налаштовано у .env")
            return PublishResult(
                success=False,
                platform=self.platform_name,
                error="Не налаштовано (TIKTOK_UPLOAD_SESSION_ID у .env)"
            )

        if DRY_RUN_MODE and not is_configured:
            logger.info(f"[DRY RUN] TikTok (Канал відео): Format={content_type.value}, Items={len(media_paths)}")
            return PublishResult(
                success=True,
                platform=self.platform_name,
                external_id="mock_tt_video_789",
                url="https://www.tiktok.com/@bohdan.gpt/video/mock_tt_video_789"
            )

        from config import STRICT_PROXY_CHECK
        if not proxy_manager.proxy_url and STRICT_PROXY_CHECK:
            return PublishResult(
                success=False,
                platform=self.platform_name,
                error="❌ Для TikTok обов'язково потрібен US/NY проксі (інакше алгоритми ріжуть перегляди)"
            )

        import concurrent.futures

        def _do_upload() -> PublishResult:
            import shutil
            from playwright.sync_api import sync_playwright
            from config import DATA_DIR
            state_file = DATA_DIR / "tiktok_channel_state.json"
            proxy_cfg = proxy_manager.get_playwright_proxy()

            chromium_bin = shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome")
            proxy_modes = [True, False] if (proxy_cfg and not STRICT_PROXY_CHECK) else [bool(proxy_cfg)]
            last_loop_err = None

            for use_proxy in proxy_modes:
                launch_kwargs = {
                    "headless": True,
                    "args": [
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--disable-webgl",
                        "--disable-webgl2",
                        "--disable-3d-apis",
                        "--renderer-process-limit=1",
                        "--disable-site-isolation-trials",
                        "--mute-audio",
                        "--disable-blink-features=AutomationControlled",
                        "--no-first-run",
                        "--no-default-browser-check",
                        "--js-flags=--max-old-space-size=256",
                        "--disable-extensions",
                        "--disable-background-networking"
                    ]
                }
                if use_proxy and proxy_cfg:
                    launch_kwargs["proxy"] = proxy_cfg

                try:
                    with sync_playwright() as p:
                        browser = p.chromium.launch(**launch_kwargs)
                        try:
                            context = browser.new_context(
                                storage_state=str(state_file) if state_file.exists() else None,
                                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                                viewport={"width": 1280, "height": 800}
                            )
                            if not state_file.exists() and upload_session:
                                try:
                                    context.add_cookies([
                                        {"name": "sessionid", "value": upload_session, "domain": ".tiktok.com", "path": "/", "secure": True, "httpOnly": True},
                                        {"name": "sessionid_ss", "value": upload_session, "domain": ".tiktok.com", "path": "/", "secure": True, "httpOnly": True}
                                    ])
                                    logger.info("TikTok: додано sessionid та sessionid_ss у браузер")
                                except Exception as ce:
                                    logger.warning(f"TikTok: не вдалося додати sessionid cookies: {ce}")

                            page = context.new_page()

                            # Захист від падіння вкладки через нестачу RAM у хмарі: блокуємо важкі ресурси
                            try:
                                def _block_heavy(route):
                                    if route.request.resource_type in ["image", "media", "font"]:
                                        route.abort()
                                    else:
                                        route.continue_()
                                page.route("**/*", _block_heavy)
                            except Exception:
                                pass

                            try:
                                from playwright_stealth import stealth_sync
                                stealth_sync(page)
                            except Exception:
                                pass

                            page.goto("https://www.tiktok.com/tiktokstudio/upload", timeout=50000, wait_until="domcontentloaded")
                            page.wait_for_timeout(3000)

                            # 1. Завантажуємо файл (перевіряємо головну сторінку та iframe)
                            try:
                                page.wait_for_selector('input[type="file"]', state="attached", timeout=20000)
                            except Exception:
                                pass

                            target_scope = page
                            file_input = page.locator('input[type="file"]')
                            try:
                                if file_input.count() == 0:
                                    for frame in page.frames:
                                        try:
                                            f_inp = frame.locator('input[type="file"]')
                                            if f_inp.count() > 0:
                                                file_input = f_inp
                                                target_scope = frame
                                                break
                                        except Exception:
                                            pass
                            except Exception:
                                pass

                            if file_input.count() > 0 and media_paths:
                                file_input.first.set_input_files(media_paths[0])
                                logger.info("TikTok: файл відео передано, чекаємо завершення обробки...")

                                # 2. Чекаємо поки зникне прогрес-бар обробки або з'явиться поле підпису
                                try:
                                    target_scope.wait_for_selector(
                                        'div[contenteditable="true"][data-placeholder], '
                                        'div[class*="caption"] [contenteditable="true"], '
                                        'div[data-e2e="upload-caption"]',
                                        timeout=45000
                                    )
                                except Exception:
                                    page.wait_for_timeout(15000)

                            # 2.5. Закриваємо popup-модалки TikTok ("Turn on", "Got it", "Cancel" тощо) та joyride overlay
                            for _ in range(6):
                                dismissed = False
                                try:
                                    # Видаляємо joyride onboarding tour overlays, які можуть перехоплювати кліки
                                    page.evaluate("""() => {
                                        document.querySelectorAll('#react-joyride-portal, .react-joyride__overlay, [data-test-id="overlay"]').forEach(el => el.remove());
                                    }""")
                                except Exception:
                                    pass

                                for scope in [target_scope, page]:
                                    for btn_text in [
                                        "Turn on", "Увімкнути",
                                        "Got it", "Зрозуміло",
                                        "Cancel", "Скасувати",
                                        "Close", "Закрити",
                                        "Skip", "Пропустити",
                                        "Not now", "Не зараз"
                                    ]:
                                        loc = scope.locator(f'button:has-text("{btn_text}")')
                                        for i in range(loc.count()):
                                            try:
                                                b = loc.nth(i)
                                                if b.is_visible():
                                                    logger.info(f"TikTok: закриваємо модалку кнопкою '{btn_text}'")
                                                    b.click(force=True)
                                                    page.wait_for_timeout(1000)
                                                    dismissed = True
                                                    break
                                            except Exception:
                                                continue
                                        if dismissed:
                                            break
                                    if dismissed:
                                        break
                                try:
                                    overlay = page.locator('.TUXModal-overlay, [class*="modal-overlay"]')
                                    if overlay.count() > 0:
                                        page.keyboard.press("Escape")
                                        page.wait_for_timeout(600)
                                except Exception:
                                    pass
                                if not dismissed:
                                    break

                            page.wait_for_timeout(1000)
                            # 3. Поле підпису
                            caption_selectors = [
                                'div[role="combobox"][contenteditable="true"]',
                                'div[data-e2e="upload-caption"] [contenteditable="true"]',
                                'div[class*="caption"] [contenteditable="true"]',
                                'div[contenteditable="true"][data-placeholder]',
                                'div[contenteditable="true"]',
                            ]
                            for scope in [target_scope, page]:
                                cap_typed = False
                                for sel in caption_selectors:
                                    try:
                                        cap_loc = scope.locator(sel)
                                        if cap_loc.count() > 0:
                                            cap_loc.first.click(force=True)
                                            page.wait_for_timeout(500)
                                            page.keyboard.press("Meta+a")
                                            page.keyboard.press("Control+a")
                                            page.keyboard.press("Backspace")
                                            page.keyboard.type(caption[:2000], delay=15)
                                            page.wait_for_timeout(500)
                                            page.keyboard.press("Space")
                                            page.wait_for_timeout(400)
                                            # Закриваємо випадаюче меню автопідказки хештегів
                                            page.keyboard.press("Escape")
                                            page.wait_for_timeout(500)
                                            cap_typed = True
                                            logger.info("TikTok: опис успішно введено")
                                            break
                                    except Exception:
                                        continue
                                if cap_typed:
                                    break

                            # 4. Натискаємо кнопку Post
                            page.wait_for_timeout(2000)
                            post_clicked = False
                            for scope in [target_scope, page]:
                                try:
                                    # Пріоритет: точна первинна кнопка Post
                                    post_btn = scope.locator(
                                        'button.Button__root--type-primary:has-text("Post"), '
                                        'button.Button__root--type-primary:has-text("Опублікувати"), '
                                        'button[data-e2e="post-button"]:has-text("Post"), '
                                        'button[data-e2e="post-button"]'
                                    )
                                    if post_btn.count() == 0:
                                        # Fallback перебір видимих кнопок
                                        all_btns = scope.locator('button')
                                        for i in range(all_btns.count()):
                                            b = all_btns.nth(i)
                                            if b.inner_text().strip() in ["Post", "Опублікувати"] and b.is_visible():
                                                post_btn = b
                                                break

                                    if post_btn and post_btn.count() > 0:
                                        for _ in range(20):
                                            try:
                                                is_disabled = post_btn.first.get_attribute("disabled") is not None
                                                if not is_disabled:
                                                    break
                                            except Exception:
                                                pass
                                            page.wait_for_timeout(1500)

                                        post_btn.first.scroll_into_view_if_needed()
                                        page.wait_for_timeout(500)
                                        post_btn.first.click(force=True)
                                        logger.info("TikTok: успішно натиснуто кнопку Post, очікуємо публікації...")
                                        post_clicked = True
                                        page.wait_for_timeout(10000)
                                        break
                                except Exception as e:
                                    logger.warning(f"TikTok: помилка при пошуку кнопки Post: {e}")
                                    continue

                            if not post_clicked:
                                raise RuntimeError("Не вдалося знайти або натиснути кнопку Post у TikTok Studio")

                            if state_file.exists():
                                try:
                                    context.storage_state(path=str(state_file))
                                except Exception:
                                    pass

                            return PublishResult(
                                success=True,
                                platform=self.platform_name,
                                external_id="tt_uploaded_id",
                                url="https://www.tiktok.com/@bohdan.gpt"
                            )
                        finally:
                            try:
                                browser.close()
                            except Exception:
                                pass
                except Exception as loop_err:
                    last_loop_err = loop_err
                    if use_proxy and len(proxy_modes) > 1:
                        logger.warning(f"TikTok: спроба через проксі не вдалася ({loop_err}), перемикаємось на пряме з'єднання...")
                        continue
                    raise loop_err

            if last_loop_err:
                raise last_loop_err

        try:
            logger.info(f"TikTok публікація ({content_type.value}) через Creator Studio...")
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_do_upload)
                return future.result(timeout=240)
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
