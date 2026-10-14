"""
📸 Instagram Lead Funnel Implementation
Account: @bohdan.gpt

Supports:
1. instagrapi session & Graph API
2. Playwright browser fallback
3. Follower verification, Direct Message dispatch, & comment replies
"""
import os
import json
import re
import time
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from services.lead_funnel.platforms.base import BasePlatformFunnel, PlatformComment, PlatformAccessError
from config import INSTAGRAM_USERNAME, INSTAGRAM_SESSION_FILE, DATA_DIR, TEMP_DIR
from services.proxy_manager import proxy_manager

logger = logging.getLogger("instagram_funnel")


class InstagramFunnel(BasePlatformFunnel):
    def __init__(self):
        self._comment_targets = {}
        self._client = None
        self._retry_after = 0.0

    @property
    def platform_name(self) -> str:
        return "instagram"

    def _get_client(self):
        if time.monotonic() < self._retry_after:
            return None
        if self._retry_after:
            self._client = None
            self._retry_after = 0.0
        if self._client:
            return self._client

        proxy_url = proxy_manager.proxy_url
        if proxy_url and not proxy_manager.is_proxy_alive():
            logger.warning("Instagram proxy unavailable; using the same direct connection as browser fallback")
            proxy_url = None

        try:
            from instagrapi import Client
            cl = Client()
            if proxy_url and proxy_manager.is_proxy_alive():
                cl.set_proxy(proxy_url)

            session_path = Path(INSTAGRAM_SESSION_FILE)
            if session_path.exists():
                try:
                    session = json.loads(session_path.read_text())
                    if isinstance(session.get("cookies"), list):
                        session_id = next((c["value"] for c in session["cookies"] if c.get("name") == "sessionid" and c.get("domain", "").lstrip(".") in ("instagram.com", "www.instagram.com")), None)
                        if not session_id or not cl.login_by_sessionid(session_id):
                            return None
                    else:
                        cl.load_settings(str(session_path))
                    self._client = cl
                    return cl
                except Exception as e:
                    logger.warning(f"Не вдалося завантажити instagrapi сесію: {e}")
                    self._retry_after = time.monotonic() + 300
                    return None

            return None
        except Exception as e:
            logger.debug(f"instagrapi unavailable: {e}")
            self._retry_after = time.monotonic() + 300
            return None

    def fetch_recent_unanswered_comments(self, limit_posts: Optional[int] = None) -> List[PlatformComment]:
        """Отримує коментарі під публікаціями (API + Playwright fallback для всіх відео)"""
        comments: List[PlatformComment] = []
        cl = self._get_client()
        if cl:
            try:
                amt = limit_posts if limit_posts is not None else 50
                user_id = os.getenv("INSTAGRAM_USER_ID", "36442665203").strip()
                medias = cl.user_medias(int(user_id) if user_id.isdigit() else user_id, amount=amt)
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
                self._retry_after = time.monotonic() + 300

        # Фолбек на браузерну сесію Playwright якщо через instagrapi повернуто 0
        if not comments:
            comments = self._fetch_comments_via_browser(limit_posts=limit_posts)

        return comments

    def _fetch_comments_via_browser(self, limit_posts: Optional[int] = None) -> List[PlatformComment]:
        """Парсинг коментарів через Playwright браузерну сесію для публікацій"""
        results: List[PlatformComment] = []
        state_file = DATA_DIR / "instagram_state.json"
        if not state_file.exists():
            raise PlatformAccessError("Instagram browser session missing")

        try:
            from playwright.sync_api import sync_playwright
            from core.browser_lock import BROWSER_LOCK, CHROME_DOCKER_ARGS
            with BROWSER_LOCK:
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True, args=CHROME_DOCKER_ARGS)
                    context = browser.new_context(
                        storage_state=str(state_file),
                        viewport={"width": 1280, "height": 800},
                        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                        locale="en-US"
                    )
                    page = context.new_page()
                    try:
                        page.goto(f"https://www.instagram.com/{INSTAGRAM_USERNAME or 'bohdan.gpt'}/", wait_until="domcontentloaded", timeout=18000)
                    except Exception as p_goto_err:
                        logger.debug(f"IG profile goto timeout (proceeding to DOM check): {p_goto_err}")

                    try:
                        page.locator('a[href*="/p/"], a[href*="/reel/"]').first.wait_for(timeout=12000)
                    except Exception:
                        page.wait_for_timeout(3000)

                    # Якщо потрібно просканувати всі пости — скролимо профіль
                    if limit_posts is None or limit_posts > 12:
                        for _ in range(8):
                            page.mouse.wheel(0, 2500)
                            page.wait_for_timeout(700)

                    raw_links = [a.get_attribute("href") for a in page.locator('a[href*="/p/"], a[href*="/reel/"]').all()]
                    unique_links = list(dict.fromkeys([l for l in raw_links if l and ('/p/' in l or '/reel/' in l)]))
                    if not unique_links:
                        raise PlatformAccessError("Instagram posts unavailable; check session and page layout")
                    max_posts = limit_posts if limit_posts is not None else len(unique_links)
                    target_links = unique_links[:max_posts]

                    for href in target_links:
                        if not href:
                            continue
                        shortcode = href.strip("/").split("/")[-1]
                        href = f"/p/{shortcode}/"
                        post_url = f"https://www.instagram.com{href}"
                        try:
                            try:
                                page.goto(post_url, wait_until="domcontentloaded", timeout=18000)
                            except Exception as post_goto_err:
                                logger.debug(f"IG post goto timeout (proceeding to DOM check): {post_goto_err}")

                            try:
                                page.locator('main, article, ul, [role="main"]').first.wait_for(timeout=10000)
                            except Exception:
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

                            # Comment permalinks contain stable IDs, independent of UI language.
                            records = page.locator('a[href*="/c/"]').evaluate_all(r"""links => links.flatMap(link => {
                                const match = link.getAttribute('href').match(/\/c\/(\d+)\/(?:$|\?)/);
                                if (!match) return [];
                                let row = link.parentElement;
                                while (row && (!row.querySelector('h3 a') || !row.querySelector('[role="button"],button'))) row = row.parentElement;
                                if (!row || row === document.body) return [];
                                const author = row.querySelector('h3 a');
                                const username = (author.getAttribute('href') || '').split('/').filter(Boolean)[0];
                                if (!username || row.querySelectorAll('h3').length !== 1) return [];
                                const clone = row.cloneNode(true);
                                clone.querySelectorAll('h3,button,[role="button"],time,a[href*="/c/"]').forEach(el => el.remove());
                                return [{id:match[1], username, text:clone.textContent.trim()}];
                            })""")
                            for record in {r['id']: r for r in records}.values():
                                if not record['text'] or record['username'] == (INSTAGRAM_USERNAME or 'bohdan.gpt'):
                                    continue
                                self._comment_targets[record['id']] = (record['username'], record['text'])
                                results.append(PlatformComment(
                                    comment_id=record['id'], post_id=href, post_url=post_url,
                                    user_id=record['username'], username=record['username'], text=record['text'],
                                    screenshot_path=str(comment_ss_path) if comment_ss_path else None))
                        except Exception as post_err:
                            logger.debug(f"Помилка парсингу поста {post_url}: {post_err}")
                            continue
                    browser.close()
        except Exception as e:
            logger.warning("Instagram browser scan failed: %s", type(e).__name__)
            raise
        return results

    def check_follower_status(self, user_id: str, username: str) -> Tuple[Optional[bool], Optional[str]]:
        client = self._get_client()
        if client:
            try:
                target = str(user_id) if str(user_id).isdigit() else client.user_id_from_username(username)
                relationship = client.user_friendship_v1(target)
                followed_by = getattr(relationship, "followed_by", None)
                if isinstance(followed_by, bool):
                    return followed_by, None
            except Exception as exc:
                logger.warning("Instagram friendship check unavailable: %s", type(exc).__name__)
        state_file = DATA_DIR / "instagram_state.json"
        if state_file.exists() and re.fullmatch(r"[A-Za-z0-9_.]+", username):
            try:
                from playwright.sync_api import sync_playwright
                from core.browser_lock import BROWSER_LOCK, CHROME_DOCKER_ARGS
                with BROWSER_LOCK, sync_playwright() as p:
                    browser = p.chromium.launch(headless=True, args=CHROME_DOCKER_ARGS)
                    try:
                        page = browser.new_page(storage_state=str(state_file), locale="en-US")
                        page.goto(f"https://www.instagram.com/{username}/", wait_until="domcontentloaded", timeout=20000)
                        back = page.get_by_role("button", name=re.compile(r"^(Follow Back|Стежити у відповідь)$", re.I))
                        if back.count() and back.first.is_visible():
                            return True, None
                        page.goto(f"https://www.instagram.com/{INSTAGRAM_USERNAME or 'bohdan.gpt'}/", wait_until="domcontentloaded", timeout=20000)
                        page.get_by_role("link", name=re.compile(r"followers|Читачі", re.I)).click(timeout=10000)
                        dialog = page.get_by_role("dialog")
                        search = dialog.locator('input')
                        if search.count() != 1:
                            return None, None
                        search.fill(username)
                        exact = dialog.locator(f'a[href="/{username}/"]')
                        try:
                            exact.first.wait_for(timeout=8000)
                            return True, None
                        except Exception:
                            # Absence of a result is never positive evidence of a follow.
                            if dialog.get_by_text(re.compile(r"^(No results found\.?|Нічого не знайдено\.?)$", re.I)).count():
                                return False, None
                    finally:
                        browser.close()
            except Exception as exc:
                logger.warning("Instagram browser friendship check unavailable: %s", type(exc).__name__)
        return None, None

    def is_user_following(self, user_id: str, username: str) -> Optional[bool]:
        return self.check_follower_status(user_id, username)[0]

    def fetch_direct_messages(self):
        client = self._get_client()
        if client is None:
            raise PlatformAccessError("Instagram inbox: session unavailable")
        threads = [(t, False) for t in client.direct_threads(amount=20, thread_message_limit=10)]
        threads += [(t, True) for t in client.direct_pending_inbox(amount=20)]
        seen = set()
        for thread, pending in threads:
            if str(thread.id) in seen or len(thread.users) != 1:
                continue
            seen.add(str(thread.id))
            user = thread.users[0]
            for message in thread.messages[:1]:
                if str(message.user_id) == str(user.pk) and message.text:
                    yield PlatformComment(str(message.id), str(thread.id), None, str(user.pk), user.username,
                                          message.text, pending_request=pending)

    def reply_to_direct_message(self, message, text):
        client = self._get_client()
        if client is None:
            return False, "session_unavailable"
        try:
            thread = client.direct_thread(message.post_id, amount=20)
            if len(thread.users) != 1 or str(thread.users[0].pk) != str(message.user_id):
                return False, "recipient_mismatch"
            if any(str(m.user_id) == str(client.user_id) and m.text == text for m in thread.messages):
                return True, None
            if message.pending_request or getattr(thread, "pending", False) is True:
                if client.direct_pending_approve(message.post_id) is not True:
                    return False, "request_not_accepted"
        except Exception as exc:
            return False, type(exc).__name__
        try:
            response = client.direct_send(text, thread_ids=[message.post_id])
            return (True, None) if getattr(response, "id", None) else (False, "delivery_unknown")
        except Exception:
            # A timeout may happen after submission; never fall back and send it twice.
            return False, "delivery_unknown"

    def send_direct_message(self, user_id: str, username: str, text: str, comment_id: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        client = self._get_client()
        if client is None:
            return False, "session_unavailable"
        try:
            target = int(user_id) if str(user_id).isdigit() else client.user_id_from_username(username)
        except Exception as exc:
            return False, type(exc).__name__
        try:
            response = client.direct_send(text, user_ids=[target])
            return (True, None) if getattr(response, "id", None) else (False, "delivery_unknown")
        except Exception:
            return False, "delivery_unknown"

    def reply_to_comment(self, comment_id: str, text: str, post_id: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """Відповідає на коментар у публічній стрічці (API або Playwright браузер)"""
        cl = self._get_client()
        if cl:
            try:
                if post_id and str(comment_id).isdigit():
                    media_id = cl.media_pk_from_url(f"https://www.instagram.com{post_id}") if post_id.startswith("/") else post_id
                    response = cl.media_comment(media_id, text, replied_to_comment_id=int(comment_id))
                    if not getattr(response, "pk", None):
                        return False, "delivery_unknown"
                    logger.info(f"✅ Instagram відповідь на коментар {comment_id} надіслана: '{text}'")
                    return True, None
            except Exception as e:
                logger.warning("Instagram comment receipt unavailable: %s", type(e).__name__)
                self._retry_after = time.monotonic() + 300
                return False, "delivery_unknown"

        # 2. Playwright браузерний фолбек
        submitted = False
        state_file = DATA_DIR / "instagram_state.json"
        if state_file.exists() and post_id:
            try:
                from core.browser_lock import BROWSER_LOCK, CHROME_DOCKER_ARGS
                from playwright.sync_api import sync_playwright
                with BROWSER_LOCK:
                    with sync_playwright() as p:
                        browser = p.chromium.launch(headless=True, args=CHROME_DOCKER_ARGS)
                        ctx = browser.new_context(
                            storage_state=str(state_file),
                            locale="en-US",
                            viewport={"width": 1280, "height": 800}
                        )
                        page = ctx.new_page()
                        target_url = post_id if post_id.startswith("http") else f"https://www.instagram.com{post_id}"
                        try:
                            page.goto(target_url, wait_until="domcontentloaded", timeout=18000)
                        except Exception as rep_goto_err:
                            logger.debug(f"IG reply goto timeout (proceeding): {rep_goto_err}")
                        page.wait_for_timeout(2000)

                        permalink = page.locator(f'a[href*="/c/{comment_id}/"]').first
                        if not permalink.count():
                            browser.close()
                            return False, "comment_target_missing"
                        row = permalink.locator('xpath=ancestor::*[.//h3 and (.//button or .//*[@role="button"])][1]')
                        if row.count() != 1 or row.locator('h3').count() != 1:
                            browser.close()
                            return False, "comment_target_ambiguous"
                        receipt = page.locator(f'a[href*="/c/{comment_id}/r/"]').locator('xpath=ancestor::*[.//h3][1]').filter(
                            has=page.locator(f'h3 a[href="/{INSTAGRAM_USERNAME or "bohdan.gpt"}/"]')).get_by_text(text, exact=False)
                        if receipt.count():
                            browser.close()
                            return True, None
                        reply_btn = row.get_by_text(re.compile(r"^(Reply|Відповісти)$")).first
                        reply_btn.click(timeout=5000)

                        textarea = page.locator('textarea[aria-label*="comment" i], textarea[placeholder*="comment" i], textarea').first
                        if textarea.is_visible():
                            textarea.click()
                            current_val = textarea.input_value()
                            if current_val and not text.startswith("@"):
                                textarea.fill(f"{current_val}{text}")
                            else:
                                textarea.fill(text)
                            page.wait_for_timeout(500)

                            post_btn = page.locator('div[role="button"], button').filter(has_text=re.compile(r"^(Post|Опублікувати)$", re.I)).first
                            submitted = True
                            if post_btn.is_visible():
                                post_btn.click()
                            else:
                                page.keyboard.press("Enter")
                            receipt.last.wait_for(timeout=10000)
                            page.reload(wait_until="domcontentloaded", timeout=20000)
                            receipt.last.wait_for(timeout=10000)
                            browser.close()
                            logger.info(f"✅ [Instagram Playwright Web] Опубліковано відповідь на коментар: '{text}'")
                            return True, None
                        browser.close()
            except Exception as pe:
                logger.warning("Instagram browser reply failed: %s", type(pe).__name__)
                return False, "delivery_unknown" if submitted else "reply_failed"

        logger.warning("Instagram reply delivery failed")
        return False, "reply_failed"

    def like_comment(self, comment_id: str, post_id: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """Ставить лайк на коментар у публічній стрічці Instagram (API або Playwright)"""
        cl = self._get_client()
        # 1. Спроба через instagrapi API якщо comment_id числовий
        if cl:
            try:
                if comment_id and str(comment_id).isdigit():
                    cl.comment_like(int(comment_id))
                    logger.info(f"❤️ [Instagram API] Поставлено лайк на коментар {comment_id}")
                    return True, None
            except Exception as e:
                logger.debug(f"Instagram API comment_like: {e}")
                self._retry_after = time.monotonic() + 300

        # 2. Браузерний Playwright фолбек
        state_file = DATA_DIR / "instagram_state.json"
        if state_file.exists() and post_id:
            try:
                from playwright.sync_api import sync_playwright
                from core.browser_lock import BROWSER_LOCK, CHROME_DOCKER_ARGS
                with BROWSER_LOCK:
                    with sync_playwright() as p:
                        browser = p.chromium.launch(headless=True, args=CHROME_DOCKER_ARGS)
                        ctx = browser.new_context(storage_state=str(state_file), locale="en-US", viewport={"width": 1280, "height": 800})
                        page = ctx.new_page()
                        target_url = post_id if post_id.startswith("http") else f"https://www.instagram.com{post_id}"
                        try:
                            page.goto(target_url, wait_until="domcontentloaded", timeout=18000)
                        except Exception as lk_goto_err:
                            logger.debug(f"IG like goto timeout (proceeding): {lk_goto_err}")
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
