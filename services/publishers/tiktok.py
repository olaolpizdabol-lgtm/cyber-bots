import os
import re
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
import requests
from services.publishers.base import BasePublisher, PublishResult, StatsResult
from services.proxy_manager import proxy_manager
from config import TIKTOK_UPLOAD_SESSION_ID, TIKTOK_SESSION_ID, DRY_RUN_MODE
from core.content_type import ContentType

logger = logging.getLogger(__name__)

_SUCCESS_TEXTS = [
    "your video has been uploaded",
    "video posted",
    "upload complete",
    "your post has been published",
    "відео завантажено",
    "опубліковано",
]
_FAIL_TEXTS = [
    "your video failed to upload",
    "upload failed",
    "something went wrong",
    "помилка завантаження",
]


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

            # Проксі: завжди використовуємо якщо є URL (незалежно від STRICT_PROXY_CHECK)
            # щоб TikTok бачив US IP і давав охоплення в США.
            # Якщо проксі недоступний - fallback на пряме з'єднання.
            proxy_modes = [True, False] if proxy_cfg else [False]
            last_loop_err = None

            # Базові Chrome flags для headless + стабільності на Railway
            _base_args = [
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--mute-audio",
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
                # Memory-reducing flags
                "--renderer-process-limit=1",
                "--disable-software-rasterizer",
                "--disable-accelerated-2d-canvas",
                "--disable-extensions",
                "--disable-component-extensions-with-background-pages",
                "--disk-cache-size=1",
                "--media-cache-size=1",
                "--js-flags=--max-old-space-size=256",
            ]

            for use_proxy in proxy_modes:
                launch_kwargs = {
                    "headless": True,
                    "args": _base_args,
                }
                if use_proxy and proxy_cfg:
                    launch_kwargs["proxy"] = proxy_cfg

                try:
                    proxy_label = "через проксі" if use_proxy else "пряме зєднання"
                    from core.mem_guard import ensure_memory_for_browser
                    if not ensure_memory_for_browser("TikTok"):
                        raise RuntimeError("Недостатньо вільної RAM для запуску Chromium (TikTok). Спробуйте пізніше.")
                    logger.info(f"TikTok: запуск браузера ({proxy_label})...")
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

                            # Зменшуємо пікове навантаження на пам'ять при розборі відео
                            try:
                                page.add_init_script("""
                                    window.Worker = class { constructor() { throw new Error('Worker disabled'); } };
                                    window.SharedWorker = class { constructor() { throw new Error('Worker disabled'); } };
                                    window.createImageBitmap = undefined;
                                """)
                            except Exception:
                                pass

                            try:
                                from playwright_stealth import stealth_sync
                                stealth_sync(page)
                            except Exception:
                                pass

                            goto_timeout = 25000 if use_proxy else 45000
                            logger.info(f"TikTok Studio: завантажуємо сторінку upload (proxy={use_proxy}, timeout={goto_timeout}ms)...")
                            page.goto("https://www.tiktok.com/tiktokstudio/upload", timeout=goto_timeout, wait_until="domcontentloaded")
                            page.wait_for_timeout(3000)
                            logger.info(f"TikTok Studio: сторінку завантажено (URL: {page.url})")

                            if "login" in page.url:
                                logger.warning(f"TikTok Studio: редірект на логін ({page.url})")
                                raise RuntimeError("TikTok Studio перенаправив на сторінку логіну. Потрібно оновити TIKTOK_CHANNEL_STATE_B64.")

                            # 1. Завантажуємо файл (перевіряємо головну сторінку та iframe)
                            logger.info("TikTok Studio: шукаємо поле input[type='file']...")
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
                                                logger.info("TikTok Studio: поле input[type='file'] знайдено в iframe")
                                                break
                                        except Exception:
                                            pass
                            except Exception:
                                pass

                            if file_input.count() == 0:
                                debug_shot = DATA_DIR / "tiktok_no_input_debug.png"
                                try:
                                    page.screenshot(path=str(debug_shot))
                                except Exception:
                                    pass
                                raise RuntimeError(f"Не знайдено поле input[type='file'] в TikTok Studio (знімок: {debug_shot.name})")

                            if media_paths:
                                existing = [p for p in media_paths if Path(p).exists()]
                                if len(existing) != len(media_paths):
                                    missing = [p for p in media_paths if not Path(p).exists()]
                                    raise RuntimeError(f"TikTok: медіафайли відсутні: {missing}")
                                if not existing:
                                    raise RuntimeError("TikTok: не передано жодного медіафайлу")
                                logger.info(f"TikTok Studio: передаємо {len(existing)} файл(ів) в input (перший: {existing[0]})...")
                                file_input.first.set_input_files(existing if len(existing) > 1 else existing[0])
                                logger.info("TikTok Studio: файли передано, очікуємо завантаження форми редагування...")
                                page.wait_for_timeout(4000)

                                # Верифікуємо, що TikTok прийняв САМЕ наші файли (не залишковий з попередньої сесії)
                                try:
                                    body_text = page.inner_text("body", timeout=5000)
                                except Exception:
                                    body_text = ""
                                for fail_marker in ("Failed to upload", "Unsupported file", "File too large", "Помилка завантаження"):
                                    if fail_marker.lower() in body_text.lower():
                                        raise RuntimeError(f"TikTok відхилив медіафайл: {fail_marker}")

                                # Закриваємо модальні діалоги ("Turn on automatic checks?", "Got it", "Cancel" тощо)
                                for _ in range(4):
                                    try:
                                        page.keyboard.press("Escape")
                                    except Exception:
                                        pass
                                    for btn_name in ["Cancel", "Скасувати", "Got it", "Зрозуміло", "Turn on", "Увімкнути", "Close", "Закрити", "Skip"]:
                                        btns = page.locator(f'button:has-text("{btn_name}")')
                                        for i in range(btns.count()):
                                            try:
                                                b = btns.nth(i)
                                                if b.is_visible():
                                                    logger.info(f"TikTok Studio: закриваємо модалку '{btn_name}'")
                                                    b.click(force=True)
                                                    page.wait_for_timeout(400)
                                            except Exception:
                                                pass

                                    try:
                                        page.evaluate('''() => {
                                            document.querySelectorAll('[role="dialog"], .TUXModal-overlay, [class*="modal-overlay"], #react-joyride-portal, [data-test-id="overlay"]').forEach(el => el.remove());
                                        }''')
                                    except Exception:
                                        pass
                                    page.wait_for_timeout(500)

                            # 3. Поле підпису (Caption)
                            logger.info("TikTok Studio: заповнюємо поле опису...")
                            cap_loc = None
                            for c_sel in [
                                'div[role="combobox"][contenteditable="true"]',
                                'div[class*="caption"] [contenteditable="true"]',
                                'div[data-e2e="upload-caption"] [contenteditable="true"]',
                                'div[contenteditable="true"]'
                            ]:
                                loc = page.locator(c_sel)
                                if loc.count() > 0 and loc.first.is_visible():
                                    cap_loc = loc.first
                                    break

                            if cap_loc:
                                try:
                                    cap_loc.scroll_into_view_if_needed()
                                    cap_loc.click(force=True)
                                    page.wait_for_timeout(300)
                                    # Очищаємо авто-підставлене ім'я файлу
                                    page.keyboard.press("Meta+a")
                                    page.keyboard.press("Control+a")
                                    page.keyboard.press("Backspace")
                                    page.wait_for_timeout(200)
                                    page.keyboard.type(caption[:2000], delay=10)
                                    page.wait_for_timeout(400)
                                    page.keyboard.press("Escape")
                                    logger.info("TikTok Studio: опис успішно заповнено")
                                except Exception as ce:
                                    logger.warning(f"TikTok Studio: помилка заповнення опису: {ce}")
                            else:
                                logger.warning("TikTok Studio: поле опису не знайдено, переходимо до кнопки публікації")

                            # 4. Кнопка публікації Post
                            logger.info("TikTok Studio: шукаємо кнопку Post...")
                            try:
                                page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
                            except Exception:
                                pass
                            page.wait_for_timeout(1000)

                            post_btn = None
                            for btn_sel in [
                                'button[data-e2e="post-button"]',
                                'button:has-text("Post")',
                                'button:has-text("Опублікувати")'
                            ]:
                                loc = page.locator(btn_sel)
                                for i in range(loc.count()):
                                    b = loc.nth(i)
                                    if b.is_visible() and b.inner_text().strip() in ["Post", "Опублікувати"]:
                                        post_btn = b
                                        break
                                if post_btn:
                                    break

                            if not post_btn:
                                all_b = page.locator('button')
                                for i in range(all_b.count()):
                                    b = all_b.nth(i)
                                    if b.is_visible() and b.inner_text().strip() in ["Post", "Опублікувати"]:
                                        post_btn = b
                                        break

                            if not post_btn:
                                debug_shot = DATA_DIR / "tiktok_no_post_debug.png"
                                try:
                                    page.screenshot(path=str(debug_shot))
                                except Exception:
                                    pass
                                raise RuntimeError(f"Не знайдено кнопку Post у TikTok Studio (знімок: {debug_shot.name})")

                            # Чекаємо готовність кнопки Post (до 30 сек)
                            for wait_i in range(30):
                                try:
                                    if not post_btn.is_disabled():
                                        logger.info(f"TikTok Studio: кнопка Post готова на {wait_i}с!")
                                        break
                                except Exception:
                                    pass
                                page.wait_for_timeout(1000)

                            post_btn.scroll_into_view_if_needed()
                            page.wait_for_timeout(500)
                            post_btn.click(force=True)
                            logger.info("TikTok: натиснуто Post, очікуємо підтвердження публікації...")

                            published_url, verify_err = self._wait_for_publication(page, timeout_s=90)
                            if not published_url and verify_err:
                                debug_shot = DATA_DIR / "tiktok_publish_verify_failed.png"
                                try:
                                    page.screenshot(path=str(debug_shot))
                                except Exception:
                                    pass
                                return PublishResult(
                                    success=False,
                                    platform=self.platform_name,
                                    error=f"TikTok не підтвердив публікацію: {verify_err} (знімок: {debug_shot.name})"
                                )
                            if not published_url:
                                debug_shot = DATA_DIR / "tiktok_publish_unverified.png"
                                try:
                                    page.screenshot(path=str(debug_shot))
                                except Exception:
                                    pass
                                return PublishResult(
                                    success=False,
                                    platform=self.platform_name,
                                    error=f"TikTok не підтвердив публікацію за 90с (знімок: {debug_shot.name})"
                                )

                            if state_file.exists():
                                try:
                                    context.storage_state(path=str(state_file))
                                except Exception:
                                    pass

                            return PublishResult(
                                success=True,
                                platform=self.platform_name,
                                external_id=self._extract_video_id(published_url),
                                url=published_url
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
            return _do_upload()
        except Exception as e:
            from core.security_guard import security_guard
            err_clean = security_guard.sanitize_error(str(e))
            logger.error(f"Помилка TikTok: {err_clean}")
            return PublishResult(success=False, platform=self.platform_name, error=err_clean)

    def _extract_video_id(self, url: str) -> Optional[str]:
        if not url:
            return None
        m = re.search(r"/video/(\d{6,})", url)
        if m:
            return m.group(1)
        m = re.search(r"item_id=(\d{6,})", url)
        if m:
            return m.group(1)
        return None

    def _wait_for_publication(self, page, timeout_s: int = 90) -> tuple:
        """Чекає реального підтвердження публікації. Повертає (published_url, error)."""
        deadline = time.time() + timeout_s
        last_body = ""
        while time.time() < deadline:
            # 1. Редірект на сторінку відео/контенту = успіх
            cur = page.url or ""
            if re.search(r"/@[^/]+/video/\d{6,}", cur) or ("/content/" in cur and "upload" not in cur):
                return cur, None
            try:
                last_body = page.inner_text("body", timeout=3000) or ""
            except Exception:
                last_body = ""
            low = last_body.lower()
            # 2. Текстові індикатори успіху
            for t in _SUCCESS_TEXTS:
                if t.lower() in low:
                    # намагаємось дістати реальне посилання
                    try:
                        link = page.evaluate(
                            """() => {
                                const a = Array.from(document.querySelectorAll('a'))
                                    .find(a => /\\/video\\/\\d{6,}/.test(a.href || ''));
                                return a ? a.href : null;
                            }"""
                        )
                        if link:
                            return link, None
                    except Exception:
                        pass
                    return cur, None
            # 3. Виразні помилки
            for t in _FAIL_TEXTS:
                if t.lower() in low:
                    return None, f"отримано помилку в UI: '{t}'"
            # 4. Кнопка Post зникла після кліку = форму відправлено
            # (помилки ми вже перевірили вище, тож це ознака успіху)
            try:
                post_btns = page.locator('button:has-text("Post")')
                visible = False
                for i in range(post_btns.count()):
                    try:
                        if post_btns.nth(i).is_visible():
                            visible = True
                            break
                    except Exception:
                        continue
                if not visible:
                    return page.url, None
            except Exception:
                pass
            page.wait_for_timeout(2000)
        return None, "підтвердження не отримано (таймаут)"

    def get_stats(self, external_id: str) -> StatsResult:
        if not external_id or external_id.startswith("mock_") or external_id == "tt_uploaded_id":
            return StatsResult(platform=self.platform_name, error="ID публікації не підтверджено")

        try:
            proxies = proxy_manager.get_requests_proxies()
            url = f"https://www.tiktok.com/oembed?url=https://www.tiktok.com/@me/video/{external_id}"
            resp = requests.get(url, proxies=proxies, timeout=10)
            if resp.status_code == 200:
                try:
                    data = resp.json() or {}
                    title = data.get("title", "")
                except Exception:
                    title = ""
                return StatsResult(platform=self.platform_name, views=0, likes=0, comments=0,
                                   error=None if title else "TikTok не підтвердив відео (oembed порожній)")
            return StatsResult(platform=self.platform_name, views=0, likes=0, comments=0,
                               error=f"oembed HTTP {resp.status_code}")
        except Exception as e:
            return StatsResult(platform=self.platform_name, error=str(e))


tiktok_publisher = TikTokPublisher()
