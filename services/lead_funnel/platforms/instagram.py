"""
📸 Instagram Lead Funnel Implementation
Account: @bohdan.gpt

Supports:
1. instagrapi session & Graph API
2. Playwright browser fallback
3. Follower verification, Direct Message dispatch, & comment replies
"""
import os
import re
import time
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from services.lead_funnel.platforms.base import BasePlatformFunnel, PlatformComment
from config import INSTAGRAM_USERNAME, INSTAGRAM_SESSION_FILE, DATA_DIR, TEMP_DIR
from services.proxy_manager import proxy_manager

logger = logging.getLogger("instagram_funnel")


class InstagramFunnel(BasePlatformFunnel):
    def __init__(self):
        self._client = None

    @property
    def platform_name(self) -> str:
        return "instagram"

    def _get_client(self):
        if self._client:
            return self._client

        try:
            from instagrapi import Client
            cl = Client()
            proxy_url = proxy_manager.proxy_url
            if proxy_url and proxy_manager.is_proxy_alive():
                cl.set_proxy(proxy_url)

            session_path = Path(INSTAGRAM_SESSION_FILE)
            if session_path.exists():
                try:
                    cl.load_settings(str(session_path))
                    self._client = cl
                    return cl
                except Exception as e:
                    logger.warning(f"Не вдалося завантажити instagrapi сесію: {e}")

            self._client = cl
            return cl
        except Exception as e:
            logger.debug(f"instagrapi unavailable: {e}")
            return None

    def fetch_recent_unanswered_comments(self, limit_posts: Optional[int] = None) -> List[PlatformComment]:
        """Отримує коментарі під публікаціями (API + Playwright fallback для всіх відео)"""
        comments: List[PlatformComment] = []
        cl = self._get_client()
        if cl:
            try:
                amt = limit_posts if limit_posts is not None else 50
                user_id = cl.user_id_from_username(INSTAGRAM_USERNAME or "bohdan.gpt")
                medias = cl.user_medias(user_id, amount=amt)
                for m in medias:
                    media_id = m.id
                    raw_comms = cl.media_comments(media_id)
                    for c in raw_comms:
                        has_author = (c.user.username == (INSTAGRAM_USERNAME or "bohdan.gpt"))
                        if not has_author:
                            comments.append(PlatformComment(
                                comment_id=str(c.pk),
                                post_id=str(media_id),
                                post_url=f"https://www.instagram.com/p/{m.code}/",
                                user_id=str(c.user.pk),
                                username=c.user.username,
                                text=c.text,
                                has_author_replied=False,
                                created_time=c.created_at_utc.isoformat() if hasattr(c, "created_at_utc") else None
                            ))
            except Exception as e:
                logger.debug(f"Instagram instagrapi fetch comments: {e}")

        # Фолбек на браузерну сесію Playwright якщо через instagrapi повернуто 0
        if not comments:
            comments = self._fetch_comments_via_browser(limit_posts=limit_posts)

        return comments

    def _fetch_comments_via_browser(self, limit_posts: Optional[int] = None) -> List[PlatformComment]:
        """Парсинг коментарів через Playwright браузерну сесію для ВСІХ публікацій"""
        results: List[PlatformComment] = []
        state_file = DATA_DIR / "instagram_state.json"
        if not state_file.exists():
            return results

        try:
            from playwright.sync_api import sync_playwright
            from core.browser_lock import BROWSER_LOCK
            with BROWSER_LOCK:
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    context = browser.new_context(storage_state=str(state_file), viewport={"width": 1280, "height": 800})
                    page = context.new_page()
                    page.goto(f"https://www.instagram.com/{INSTAGRAM_USERNAME or 'bohdan.gpt'}/", wait_until="domcontentloaded", timeout=20000)
                    page.wait_for_timeout(2500)

                    # Якщо потрібно просканувати всі пости — скролимо профіль
                    if limit_posts is None or limit_posts > 12:
                        for _ in range(8):
                            page.mouse.wheel(0, 2500)
                            page.wait_for_timeout(700)

                    raw_links = [a.get_attribute("href") for a in page.locator('a[href*="/p/"], a[href*="/reel/"]').all()]
                    unique_links = list(dict.fromkeys([l for l in raw_links if l]))
                    target_links = unique_links if limit_posts is None else unique_links[:limit_posts]

                    for href in target_links:
                        if not href:
                            continue
                        post_url = f"https://www.instagram.com{href}"
                        try:
                            page.goto(post_url, wait_until="domcontentloaded", timeout=20000)
                            page.wait_for_timeout(2000)

                            # 1. Розгортаємо приховані коментарі та пагінацію (lazy-load)
                            try:
                                # Прокручуємо контейнер коментарів вниз, щоб підвантажити сховані
                                for _ in range(4):
                                    page.mouse.wheel(0, 1200)
                                    page.wait_for_timeout(800)

                                # Клікаємо кнопку 'View hidden comments' якщо Meta приховала коментарі
                                hidden_btn = page.locator('text="View hidden comments", [aria-label*="hidden comments"]').first
                                if hidden_btn.is_visible():
                                    hidden_btn.click()
                                    page.wait_for_timeout(1000)
                            except Exception:
                                pass

                            # Робимо скріншот поста з коментарями для звіту
                            post_shortcode = href.strip("/").split("/")[-1]
                            comment_ss_path = TEMP_DIR / f"comment_ss_{post_shortcode}.png"
                            try:
                                page.screenshot(path=str(comment_ss_path), clip={'x': 0, 'y': 0, 'width': 1280, 'height': 800})
                            except Exception:
                                comment_ss_path = None

                            full_text = page.locator('article, [role="dialog"], main').first.inner_text()
                            lines = [l.strip() for l in full_text.split('\n') if l.strip()]

                            for idx, line in enumerate(lines):
                                if line.lower() == 'reply' and idx >= 2:
                                    comment_text = lines[idx-1]
                                    username = None
                                    time_ago = None
                                    for back in range(2, 6):
                                        if idx - back >= 0:
                                            candidate = lines[idx - back]
                                            if any(unit in candidate for unit in ['m', 'h', 'd', 'w', 'Edited']) and len(candidate) <= 15:
                                                time_ago = candidate
                                                if idx - back - 1 >= 0:
                                                    username = lines[idx - back - 1]
                                                break
                                    if username and username != (INSTAGRAM_USERNAME or 'bohdan.gpt') and 'tag a' not in username.lower() and 'drop an' not in username.lower():
                                        c_content = comment_text
                                        if any(w in c_content.lower() for w in ['like', 'likes', 'view all']):
                                            c_content = lines[idx-2]

                                        # 2. Перевірка: чи автор ВЖЕ відповів у цьому ланцюжку (включно зі словами автора та згорнутими відповідями)
                                        has_replied = False
                                        sub_window = lines[idx:min(len(lines), idx+6)]
                                        for sub in sub_window:
                                            sub_lower = sub.lower()
                                            if (INSTAGRAM_USERNAME or 'bohdan.gpt').lower() in sub_lower or any(w in sub_lower for w in ['dm', 'sent', 'check', 'message', 'author', 'автор']):
                                                has_replied = True
                                                break
                                            if 'view' in sub_lower and 'repl' in sub_lower:
                                                has_replied = True
                                                break
                                            if 'replies' in sub_lower or ('reply' in sub_lower and any(c.isdigit() for c in sub)):
                                                has_replied = True
                                                break

                                        import hashlib
                                        c_id = f"ig_{hashlib.sha256((username.lower() + '_' + c_content.strip() + '_' + href).encode()).hexdigest()[:16]}"

                                        # Індивідуальний скріншот рядка коментаря
                                        c_ss = TEMP_DIR / f"ig_comment_{c_id[3:]}.png"
                                        try:
                                            c_elem = page.locator('h3, a').filter(has_text=username).first
                                            if c_elem.is_visible():
                                                c_row = c_elem.locator('xpath=../../../../../..')
                                                if c_row.is_visible() and len(c_row.inner_text()) < 300:
                                                    c_row.screenshot(path=str(c_ss))
                                                else:
                                                    c_elem.screenshot(path=str(c_ss))
                                        except Exception:
                                            c_ss = comment_ss_path

                                        results.append(PlatformComment(
                                            comment_id=c_id,
                                            post_id=href,
                                            post_url=post_url,
                                            user_id=username,
                                            username=username,
                                            text=c_content,
                                            has_author_replied=has_replied,
                                            created_time=time_ago,
                                            screenshot_path=str(c_ss) if c_ss and c_ss.exists() else None
                                        ))
                        except Exception as post_err:
                            logger.debug(f"Помилка парсингу поста {post_url}: {post_err}")
                            continue
                    browser.close()
        except Exception as e:
            logger.debug(f"Instagram Playwright fetch comments: {e}")
        return results

    def check_follower_status(self, user_id: str, username: str) -> Tuple[bool, Optional[str]]:
        """
        Перевіряє, чи підписаний користувач на @bohdan.gpt з фото-доказом (скріншотом шапки профілю з кнопками).
        """
        state_file = DATA_DIR / "instagram_state.json"
        proof_path = TEMP_DIR / f"follower_proof_{username}.png"

        # 1. Браузерна перевірка через Playwright (найточніша)
        if state_file.exists():
            try:
                from playwright.sync_api import sync_playwright
                from core.browser_lock import BROWSER_LOCK
                with BROWSER_LOCK:
                    with sync_playwright() as p:
                        browser = p.chromium.launch(headless=True)
                        ctx = browser.new_context(
                            storage_state=str(state_file),
                            locale="en-US",
                            viewport={"width": 1280, "height": 800}
                        )
                        page = ctx.new_page()
                        page.goto(f"https://www.instagram.com/{username}/", wait_until="domcontentloaded", timeout=15000)
                        page.wait_for_timeout(2000)

                        buttons = [b.inner_text().strip() for b in page.locator('header button, header a').all() if b.inner_text().strip()]
                        
                        # Робимо скріншот САМЕ ЦЬОГО користувача (шапки профілю з кнопкою Follow / Follow Back)
                        header = page.locator('header').first
                        try:
                            if header.is_visible():
                                header.screenshot(path=str(proof_path))
                            else:
                                page.screenshot(path=str(proof_path), clip={"x": 0, "y": 0, "width": 1280, "height": 450})
                        except Exception:
                            proof_path = None

                        # Якщо кнопка 'Follow Back' — користувач точно підписаний на нас!
                        is_following = any("follow back" in b.lower() for b in buttons)

                        # Якщо кнопки 'Follow Back' немає, але є 'Message'/'Following' — шукаємо в списку підписників
                        if not is_following and any(b.lower() in ["following", "message"] for b in buttons):
                            page.goto(f"https://www.instagram.com/{INSTAGRAM_USERNAME or 'bohdan.gpt'}/", wait_until="domcontentloaded", timeout=15000)
                            page.wait_for_timeout(2000)
                            f_link = page.locator('a:has-text("followers")').first
                            if f_link.is_visible():
                                f_link.click()
                                page.wait_for_timeout(1500)
                                dialog = page.locator('[role="dialog"]').first
                                search_input = dialog.locator('input[placeholder*="Search"]').first
                                if search_input.is_visible():
                                    search_input.fill(username)
                                    page.wait_for_timeout(1200)
                                    no_results = dialog.locator('text="No results found."').is_visible()
                                    is_following = not no_results

                        browser.close()
                        return is_following, (str(proof_path) if proof_path and proof_path.exists() else None)

                        browser.close()
                        return is_following, (str(proof_path) if proof_path and proof_path.exists() else None)
            except Exception as e:
                logger.debug(f"Playwright check_follower_status error for {username}: {e}")

        return False, None

    def is_user_following(self, user_id: str, username: str) -> bool:
        """Перевіряє, чи підписаний юзер на @bohdan.gpt"""
        is_f, _ = self.check_follower_status(user_id, username)
        return is_f

    def send_direct_message(self, user_id: str, username: str, text: str, comment_id: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """Надсилає повідомлення в Direct (instagrapi з фолбеком на браузерний Playwright)"""
        cl = self._get_client()
        if cl:
            try:
                target_pk = int(user_id) if str(user_id).isdigit() else cl.user_id_from_username(username)
                cl.direct_send(text, user_ids=[target_pk])
                logger.info(f"✅ Instagram DM успішно надіслано до @{username}")
                return True, None
            except Exception as e:
                err_str = str(e).lower()
                if "private" in err_str or "restricted" in err_str or "can't send" in err_str or "reach" in err_str:
                    logger.warning(f"Закритий Direct у @{username}: {e}")
                    return False, "private_dm"
                logger.debug(f"Instagrapi DM не спрацював ({e}), спробуємо через Playwright...")

        # Playwright browser fallback
        state_file = DATA_DIR / "instagram_state.json"
        if state_file.exists():
            try:
                from core.browser_lock import BROWSER_LOCK
                from playwright.sync_api import sync_playwright
                with BROWSER_LOCK:
                    with sync_playwright() as p:
                        browser = p.chromium.launch(headless=True)
                        ctx = browser.new_context(storage_state=str(state_file), viewport={"width": 1280, "height": 800})
                        page = ctx.new_page()
                        page.goto("https://www.instagram.com/direct/new/", wait_until="domcontentloaded", timeout=20000)
                        page.wait_for_timeout(2000)
                        search_inp = page.locator('input[placeholder*="Search" i], input[name*="query" i]').first
                        if search_inp.is_visible():
                            search_inp.fill(username)
                            page.wait_for_timeout(1500)
                            user_btn = page.locator('div[role="button"], span').filter(has_text=username).first
                            if user_btn.is_visible():
                                user_btn.click()
                                page.wait_for_timeout(1000)
                                chat_btn = page.locator('button, div[role="button"]').filter(has_text="Chat").first
                                if chat_btn.is_visible():
                                    chat_btn.click()
                                    page.wait_for_timeout(2000)
                                msg_box = page.locator('div[role="textbox"][aria-label*="Message" i], textarea').first
                                if msg_box.is_visible():
                                    msg_box.fill(text)
                                    page.wait_for_timeout(500)
                                    page.keyboard.press("Enter")
                                    page.wait_for_timeout(1500)
                                    browser.close()
                                    logger.info(f"✅ Instagram Playwright DM надіслано до @{username}")
                                    return True, None
                        browser.close()
            except Exception as b_err:
                logger.warning(f"Instagram Playwright DM error: {b_err}")

        return False, "dm_failed"

    def reply_to_comment(self, comment_id: str, text: str, post_id: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """Відповідає на коментар у публічній стрічці"""
        cl = self._get_client()
        try:
            if post_id and str(comment_id).isdigit():
                cl.media_comment(post_id, text, replied_to_comment_id=int(comment_id))
                logger.info(f"✅ Instagram відповідь на коментар {comment_id} надіслана: '{text}'")
                return True, None
        except Exception as e:
            logger.error(f"Помилка відповіді на коментар Instagram: {e}")
            return False, str(e)

        logger.info(f"[Instagram Reply Fallback] Коментар {comment_id}: '{text}'")
        return True, None

    def like_comment(self, comment_id: str, post_id: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """Ставить лайк на коментар у публічній стрічці Instagram (API або Playwright)"""
        cl = self._get_client()
        # 1. Спроба через instagrapi API якщо comment_id числовий
        try:
            if comment_id and str(comment_id).isdigit():
                cl.comment_like(int(comment_id))
                logger.info(f"❤️ [Instagram API] Поставлено лайк на коментар {comment_id}")
                return True, None
        except Exception as e:
            logger.debug(f"Instagram API comment_like: {e}")

        # 2. Браузерний Playwright фолбек
        state_file = DATA_DIR / "instagram_state.json"
        if state_file.exists() and post_id:
            try:
                from playwright.sync_api import sync_playwright
                from core.browser_lock import BROWSER_LOCK
                with BROWSER_LOCK:
                    with sync_playwright() as p:
                        browser = p.chromium.launch(headless=True)
                        ctx = browser.new_context(storage_state=str(state_file), locale="en-US", viewport={"width": 1280, "height": 800})
                        page = ctx.new_page()
                        target_url = post_id if post_id.startswith("http") else f"https://www.instagram.com{post_id}"
                        page.goto(target_url, wait_until="domcontentloaded", timeout=15000)
                        page.wait_for_timeout(2500)
                        like_elems = page.locator('span:has(svg[aria-label="Like"]), [aria-label="Like"]').all()
                        for el in like_elems:
                            if el.is_visible():
                                el.click()
                                page.wait_for_timeout(500)
                                logger.info(f"❤️ [Instagram Web] Поставлено лайк на коментар у {target_url}")
                                break
                        browser.close()
                        return True, None
            except Exception as pe:
                logger.debug(f"Instagram Playwright comment like: {pe}")

        logger.info(f"❤️ [Instagram Like] Коментар {comment_id} оброблено")
        return True, None


instagram_funnel = InstagramFunnel()
