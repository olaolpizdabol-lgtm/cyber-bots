import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
import requests
from services.publishers.base import BasePublisher, PublishResult, StatsResult
from services.proxy_manager import proxy_manager
from config import DATA_DIR, DRY_RUN_MODE, STRICT_PROXY_CHECK
from core.content_type import ContentType

logger = logging.getLogger(__name__)

SNAPCHAT_STATE_FILE = DATA_DIR / "snapchat_state.json"
SNAPCHAT_UPLOADER_URL = (
    "https://profile.snapchat.com/c2443976-9439-4927-8ae2-0bcaf23c2860/profiles/da45adf0-1cf8-489f-9836-173241bb8020/web-uploader"
)
SNAPCHAT_FALLBACK_URL = "https://my.snapchat.com"

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
        """Публікація вертикального відео в Snapchat Spotlight через Playwright (як TikTok)"""
        if content_type != ContentType.VIDEO:
            return PublishResult(
                success=False,
                platform=self.platform_name,
                error="Snapchat Spotlight підтримує тільки вертикальне відео."
            )

        video_path = media_paths[0] if media_paths else ""
        if not video_path or not Path(video_path).exists():
            return PublishResult(
                success=False,
                platform=self.platform_name,
                error="Файл відео не знайдено."
            )

        title = metadata.get("snapchat_title") or metadata.get("youtube_title") or metadata.get("title", "")
        if len(title) > 160:
            title = title[:156] + "..."

        headline = metadata.get("headline") or metadata.get("short_title") or ""
        if not headline and title:
            headline = title.split("#")[0].strip()[:36]

        has_state = False
        if SNAPCHAT_STATE_FILE.exists():
            try:
                import json
                with open(SNAPCHAT_STATE_FILE, "r", encoding="utf-8") as sf:
                    s_data = json.load(sf)
                cookie_names = {c.get("name") for c in s_data.get("cookies", [])}
                # Snapchat може використовувати різні ключові куки залежно від типу сесії
                session_indicators = [
                    "sc-a-nonce", "sc-a-session", "xs", "sessionid",
                    "_sc-sid", "blizzard_web_session_id", "sc-a-csrf",
                ]
                if any(k in cookie_names for k in session_indicators):
                    has_state = True
            except Exception:
                has_state = False

        has_api_token = (
            bool(SNAPCHAT_ACCESS_TOKEN) and
            not SNAPCHAT_ACCESS_TOKEN.startswith("your_") and
            bool(SNAPCHAT_ACCOUNT_ID) and
            not SNAPCHAT_ACCOUNT_ID.startswith("your_")
        )
        is_configured = has_state or has_api_token

        if not is_configured and not DRY_RUN_MODE:
            logger.info("Snapchat Spotlight: сесія не налаштована у data/snapchat_state.json")
            return PublishResult(
                success=False,
                platform=self.platform_name,
                error="Не налаштовано (увійдіть у Snapchat у Chrome та експортуйте cookies)"
            )

        if DRY_RUN_MODE and not is_configured:
            logger.info(f"[DRY RUN] Snapchat Spotlight: Title='{title}'")
            return PublishResult(
                success=True,
                platform=self.platform_name,
                external_id="mock_snap_spotlight_202",
                url="https://snapchat.com/spotlight/mock_snap_spotlight_202"
            )

        # 1. Основний і найнадійніший режим: Playwright веб-автоматизація Profile Manager
        if has_state:
            return self._publish_via_playwright(video_path, title, headline)

        # 2. Запасний режим: Marketing API (якщо є токен)
        return self._publish_via_api(video_path, title)

    def _publish_via_playwright(self, video_path: str, caption: str, headline: str = "") -> PublishResult:
        from playwright.sync_api import sync_playwright

        proxy_cfg = proxy_manager.get_playwright_proxy()

        # Проксі: завжди використовуємо якщо є URL (Snapchat Spotlight потребує US IP)
        # Fallback на пряме з'єднання якщо проксі недоступний.
        proxy_modes = [True, False] if proxy_cfg else [False]
        last_err = None

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
        ]
        # На Linux (Docker/Railway) додаткові флаги для зниження пам'яті
        import sys as _sys
        if _sys.platform.startswith("linux"):
            _base_args += ["--no-zygote"]

        for use_proxy in proxy_modes:
            launch_kwargs = {
                "headless": True,
                "args": _base_args,
            }
            if use_proxy and proxy_cfg:
                launch_kwargs["proxy"] = proxy_cfg

            try:
                proxy_label = "через проксі" if use_proxy else "пряме зєднання"
                logger.info(f"Snapchat: запуск браузера ({proxy_label})...")
                with sync_playwright() as p:
                    browser = p.chromium.launch(**launch_kwargs)
                    try:
                        context = browser.new_context(
                            storage_state=str(SNAPCHAT_STATE_FILE),
                            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                            viewport={"width": 1280, "height": 900},
                            locale="en-US"
                        )

                        # Очищаємо тимчасові DBSC кукі з 30-хвилинним лімітом, щоб Snapchat використовував майстер-сесію
                        try:
                            all_c = context.cookies()
                            clean_c = [c for c in all_c if "dbsc" not in c["name"].lower()]
                            if len(clean_c) != len(all_c):
                                context.clear_cookies()
                                context.add_cookies(clean_c)
                        except Exception:
                            pass

                        page = context.new_page()

                        try:
                            from playwright_stealth import stealth_sync
                            stealth_sync(page)
                        except Exception:
                            pass

                        goto_timeout = 25000 if use_proxy else 40000
                        logger.info(f"Snapchat Spotlight: відкриваємо веб-завантажувач Profile Manager (proxy={use_proxy}, timeout={goto_timeout}ms)...")
                        page.goto(SNAPCHAT_UPLOADER_URL, timeout=goto_timeout, wait_until="domcontentloaded")
                        page.wait_for_timeout(3000)
                        logger.info(f"Snapchat Spotlight: сторінку завантажено (URL: {page.url})")

                        if "login" in page.url:
                            logger.info("Snapchat Spotlight: перевіряємо перехід через fallback %s...", SNAPCHAT_FALLBACK_URL)
                            page.goto(SNAPCHAT_FALLBACK_URL, timeout=goto_timeout, wait_until="domcontentloaded")
                            page.wait_for_timeout(4000)

                        if "captcha" in page.url:
                            return PublishResult(
                                success=False,
                                platform=self.platform_name,
                                error="⚠️ Snapchat вимагає проходження капчі (антифрод-захист). Оновіть SNAPCHAT_STATE_B64."
                            )

                        if "login" in page.url:
                            return PublishResult(
                                success=False,
                                platform=self.platform_name,
                                error="⚠️ Сесія Snapchat застаріла. Оновіть її: .venv/bin/python scripts/export_snapchat_cookies.py"
                            )

                        # Чекаємо поки закінчиться спіннер завантаження і з'явиться input файлу
                        logger.info("Snapchat Spotlight: шукаємо поле input[type='file']...")
                        try:
                            page.wait_for_selector('input[type="file"]', state="attached", timeout=25000)
                        except Exception:
                            pass

                        target_scope = page
                        file_input = page.locator('input[type="file"]')
                        if file_input.count() == 0:
                            for frame in page.frames:
                                try:
                                    f_inp = frame.locator('input[type="file"]')
                                    if f_inp.count() > 0:
                                        file_input = f_inp
                                        target_scope = frame
                                        logger.info("Snapchat Spotlight: поле input[type='file'] знайдено всередині iframe")
                                        break
                                except Exception:
                                    pass

                        if file_input.count() == 0:
                            debug_shot = DATA_DIR / "snapchat_no_input_debug.png"
                            try:
                                page.screenshot(path=str(debug_shot))
                            except Exception:
                                pass
                            return PublishResult(
                                success=False,
                                platform=self.platform_name,
                                error=f"Не знайдено поле завантаження відео на сторінці (знімок: {debug_shot.name})"
                            )

                        logger.info(f"Snapchat Spotlight: передаємо файл {video_path} в input...")
                        file_input.first.set_input_files(video_path)
                        logger.info("Snapchat Spotlight: файл відео передано, чекаємо генерацію прев'ю та готовність форми...")
                        page.wait_for_timeout(5000)

                        # 2. Вибір призначення: Post to Spotlight
                        try:
                            spotlight_cb = target_scope.locator('input[type="checkbox"]').first
                            if spotlight_cb.count() > 0:
                                if not spotlight_cb.is_checked():
                                    spotlight_cb.check(force=True)
                                    logger.info("Snapchat: відмічено чекбокс 'Post to Spotlight'")
                                else:
                                    logger.info("Snapchat: чекбокс 'Post to Spotlight' вже активний за замовчуванням")
                            else:
                                logger.info("Snapchat: чекбоксів не знайдено, переходимо далі")
                        except Exception as cbe:
                            logger.warning(f"Snapchat: перевірка чекбокса Spotlight: {cbe}")

                        # 3. Заповнення опису (Description)
                        desc_box = target_scope.locator('textarea[placeholder*="description" i], textarea').first
                        if desc_box.count() > 0 and desc_box.is_visible():
                            try:
                                desc_box.scroll_into_view_if_needed()
                                desc_box.click(force=True)
                                desc_box.fill(caption[:160])
                                logger.info("Snapchat: опис відео заповнено")
                            except Exception as de:
                                logger.warning(f"Snapchat: помилка заповнення опису: {de}")
                            page.wait_for_timeout(500)

                        # 4. Заповнення заголовка мініатюри (Headline)
                        h_text = headline or (caption[:36] if caption else "Spotlight")
                        headline_candidates = [
                            target_scope.locator('input[placeholder*="thumbnail" i]'),
                            target_scope.locator('input[placeholder*="headline" i]'),
                            target_scope.locator('input[aria-label*="headline" i]'),
                            target_scope.locator('input[name*="headline" i]'),
                            target_scope.locator('input[type="text"]').last
                        ]
                        headline_filled = False
                        for h_cand in headline_candidates:
                            if h_cand.count() > 0:
                                try:
                                    h_cand.first.scroll_into_view_if_needed()
                                    h_cand.first.click(force=True)
                                    h_cand.first.fill(h_text[:40])
                                    logger.info(f"Snapchat: заголовок мініатюри заповнено: «{h_text[:40]}»")
                                    headline_filled = True
                                    break
                                except Exception:
                                    pass
                        if not headline_filled:
                            logger.info("Snapchat: поле заголовка не вимагається або не знайдене")
                        page.wait_for_timeout(500)

                        # 5. Кнопка публікації Post (очікуємо готовність кнопки до 45с)
                        logger.info("Snapchat: очікуємо готовність кнопки 'Post' (обробка відео)...")
                        try:
                            page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
                        except Exception:
                            pass
                        page.wait_for_timeout(1000)

                        post_btn = None
                        for btn_sel in [
                            'button[type="submit"]:has-text("Post")',
                            'button:has-text("Post to Spotlight")',
                            'button:has-text("Post")'
                        ]:
                            loc = target_scope.locator(btn_sel)
                            if loc.count() > 0:
                                post_btn = loc.last
                                break

                        if not post_btn or post_btn.count() == 0:
                            post_btn = target_scope.locator('button').last

                        for wait_iter in range(45):
                            try:
                                is_dis = post_btn.is_disabled()
                                is_vis = post_btn.is_visible()
                                if is_vis and not is_dis:
                                    logger.info(f"Snapchat: кнопка 'Post' готова на {wait_iter}с!")
                                    break
                            except Exception:
                                pass
                            page.wait_for_timeout(1000)

                        if post_btn.is_disabled():
                            debug_shot = DATA_DIR / "snapchat_post_disabled_debug.png"
                            try:
                                page.screenshot(path=str(debug_shot), full_page=True)
                            except Exception:
                                pass
                            return PublishResult(
                                success=False,
                                platform=self.platform_name,
                                error=f"Кнопка Post недоступна після 45с очікування (знімок: {debug_shot.name})"
                            )

                        post_btn.scroll_into_view_if_needed()
                        page.wait_for_timeout(500)
                        post_btn.click(force=True)
                        logger.info("Snapchat: успішно натиснуто кнопку публікації 'Post'!")
                        page.wait_for_timeout(12000)

                        try:
                            context.storage_state(path=str(SNAPCHAT_STATE_FILE))
                        except Exception:
                            pass

                        success_shot = DATA_DIR / "snapchat_post_success.png"
                        page.screenshot(path=str(success_shot))

                        return PublishResult(
                            success=True,
                            platform=self.platform_name,
                            external_id="snap_spotlight_playwright",
                            url="https://www.snapchat.com/@bohdan.gpt"
                        )
                    finally:
                        browser.close()

            except Exception as e:
                from core.security_guard import security_guard
                last_err = security_guard.sanitize_error(str(e))
                logger.warning(f"Snapchat Playwright спроба (proxy={use_proxy}) завершилась: {last_err}")
                continue

        return PublishResult(
            success=False,
            platform=self.platform_name,
            error=last_err or "Помилка Playwright під час завантаження в Snapchat Spotlight"
        )

    def _publish_via_api(self, video_path: str, title: str) -> PublishResult:
        proxies = proxy_manager.get_requests_proxies()
        try:
            url = f"https://adsapi.snapchat.com/v1/media/{SNAPCHAT_ACCOUNT_ID}/spotlight"
            headers = {"Authorization": f"Bearer {SNAPCHAT_ACCESS_TOKEN}"}

            with open(video_path, "rb") as vf:
                files = {"file": (Path(video_path).name, vf, "video/mp4")}
                data = {"caption": title}
                resp = requests.post(url, headers=headers, files=files, data=data, proxies=proxies, timeout=60)

            if resp.status_code not in (200, 201):
                raise Exception(f"Помилка Snapchat API (HTTP {resp.status_code}): {resp.text[:150]}")

            res = resp.json()
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
            logger.error(f"Помилка Snapchat Spotlight API: {err_clean}")
            return PublishResult(success=False, platform=self.platform_name, error=err_clean)

    def get_stats(self, external_id: str) -> StatsResult:
        return StatsResult(platform=self.platform_name, views=0, likes=0, comments=0)


snapchat_publisher = SnapchatSpotlightPublisher()
