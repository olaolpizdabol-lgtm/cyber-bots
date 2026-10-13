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
from config import INSTAGRAM_USERNAME, INSTAGRAM_SESSION_FILE, DATA_DIR
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

    def fetch_recent_unanswered_comments(self, limit_posts: Optional[int] = None) -> List[PlatformComment]:
        """Отримує коментарі під публікаціями (API + Playwright fallback для всіх відео)"""
        comments: List[PlatformComment] = []
        cl = self._get_client()
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

                                        # 2. Перевірка: чи автор ВЖЕ відповів у цьому ланцюжку (включно зі словами автора)
                                        has_replied = False
                                        sub_window = lines[idx:min(len(lines), idx+6)]
                                        for sub in sub_window:
                                            if (INSTAGRAM_USERNAME or 'bohdan.gpt').lower() in sub.lower() or any(w in sub.lower() for w in ['dm', 'sent', 'check', 'message', 'author', 'автор']):
                                                has_replied = True
                                                break

                                        c_id = f"ig_{abs(hash(username + c_content + href))}"
                                        results.append(PlatformComment(
                                            comment_id=c_id,
                                            post_id=href,
                                            post_url=post_url,
                                            user_id=username,
                                            username=username,
                                            text=c_content,
                                            has_author_replied=has_replied,
                                            created_time=time_ago,
                                            screenshot_path=str(comment_ss_path) if comment_ss_path and comment_ss_path.exists() else None
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

                        # Робимо скріншот профілю з кнопками дій
                        try:
                            page.screenshot(path=str(proof_path), clip={"x": 0, "y": 0, "width": 1280, "height": 450})
                        except Exception:
                            proof_path = None

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
        """Надсилає повідомлення в Direct"""
        cl = self._get_client()
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
            logger.error(f"Помилка відправки Instagram DM до @{username}: {e}")
            return False, str(e)

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


instagram_funnel = InstagramFunnel()
