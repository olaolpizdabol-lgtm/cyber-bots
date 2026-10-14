"""
📘 Facebook Page Lead Funnel Implementation
Target: Page 'Bohdan GPT' (ID: 1383757231485870)

Supports:
1. Meta Graph API (Private Replies / Comments)
2. Playwright Headless Browser fallback (for visual interaction, follower badge check, & Messenger replies)
"""
import os
import re
import time
import json
import logging
import hashlib
from urllib.parse import urlsplit, parse_qs
from typing import Dict, Any, List, Optional, Tuple
import requests

from core.browser_lock import BROWSER_LOCK, CHROME_DOCKER_ARGS
from services.proxy_manager import proxy_manager
from services.lead_funnel.platforms.base import BasePlatformFunnel, PlatformComment, PlatformAccessError
from config import BASE_DIR, DATA_DIR, TEMP_DIR

logger = logging.getLogger("facebook_funnel")

FACEBOOK_PAGE_ID = os.getenv("FACEBOOK_PAGE_ID", "1383757231485870").strip()
# Facebook's public profile ID differs from its Business Suite / Graph asset ID.
if FACEBOOK_PAGE_ID == "61594989335713":
    FACEBOOK_PAGE_ID = "1383757231485870"
FACEBOOK_PROFILE_ID = os.getenv("FACEBOOK_PROFILE_ID", "61594989335713").strip()
GRAPH_VERSION = os.getenv("META_GRAPH_VERSION", "v22.0")
FACEBOOK_PAGE_TOKEN = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN", "").strip()
FACEBOOK_STATE_FILE = DATA_DIR / "facebook_state.json"


class FacebookFunnel(BasePlatformFunnel):
    @property
    def platform_name(self) -> str:
        return "facebook"

    def fetch_recent_unanswered_comments(self, limit_posts: int = 5) -> List[PlatformComment]:
        """
        Зчитує свіжі коментарі з останніх постів або Reels сторінки Bohdan GPT.
        Спробує через Graph API; якщо токен обмежений — використовує Playwright.
        """
        comments: List[PlatformComment] = []

        # 1. Спроба через Graph API
        if FACEBOOK_PAGE_TOKEN and not FACEBOOK_PAGE_TOKEN.startswith("your_"):
            try:
                url = f"https://graph.facebook.com/{GRAPH_VERSION}/{FACEBOOK_PAGE_ID}/feed?fields=id,permalink_url,comments{{id,from,message,created_time,comment_count,comments{{from}}}}&limit={limit_posts or 50}&access_token={FACEBOOK_PAGE_TOKEN}"
                res = requests.get(url, timeout=10)
                if res.status_code == 200:
                    data = res.json().get("data", [])
                    for post in data:
                        p_id = post.get("id")
                        p_url = post.get("permalink_url")
                        comms_data = post.get("comments", {}).get("data", [])
                        for c in comms_data:
                            c_id = c.get("id")
                            from_user = c.get("from", {})
                            u_id = from_user.get("id")
                            u_name = from_user.get("name", "")
                            msg = c.get("message", "")

                            # Перевіряємо чи автор вже відповідав у вкладених коментарях
                            sub_comments = c.get("comments", {}).get("data", [])
                            has_author = any(sub.get("from", {}).get("id") == FACEBOOK_PAGE_ID for sub in sub_comments)

                            if u_id != FACEBOOK_PAGE_ID and msg:
                                comments.append(PlatformComment(
                                    comment_id=str(c_id),
                                    post_id=str(p_id),
                                    post_url=p_url,
                                    user_id=str(u_id),
                                    username=u_name,
                                    text=msg,
                                    has_author_replied=has_author,
                                    created_time=c.get("created_time")
                                ))
                    if comments:
                        return comments
            except Exception as e:
                logger.debug(f"Graph API fetch comments не спрацював: {e}")

        # 2. Браузерний збір через Playwright
        comments.extend(self._fetch_comments_via_browser(limit_posts=limit_posts))
        return comments

    @staticmethod
    def _check_restrictions(page):
        if page.get_by_text("Confirm your identity to send messages", exact=True).count():
            raise PlatformAccessError("Facebook requires identity confirmation before sending messages")
        if "login" in page.url or page.locator('input[name="email"]').count():
            raise PlatformAccessError("Facebook browser session expired")

    def _fetch_comments_via_browser(self, limit_posts=5):
        if not FACEBOOK_STATE_FILE.exists():
            raise PlatformAccessError("Facebook browser session missing")
        from playwright.sync_api import sync_playwright
        results = {}
        with BROWSER_LOCK, sync_playwright() as p:
            browser = p.chromium.launch(channel="chromium", headless=True, args=CHROME_DOCKER_ARGS)
            try:
                page = browser.new_page(storage_state=str(FACEBOOK_STATE_FILE), locale="en-US")
                page.route("**/*", lambda route: route.abort() if route.request.resource_type in ("image", "media", "font") else route.continue_())
                page.goto(f"https://business.facebook.com/latest/inbox/facebook?asset_id={FACEBOOK_PAGE_ID}", wait_until="domcontentloaded", timeout=30000)
                self._check_restrictions(page)
                page.get_by_role("link", name="Facebook comments", exact=True).wait_for(timeout=15000)
                # Business Suite lists both posts and reels in this one inbox.
                previews = self._read_post_previews(page)
                for index, preview in enumerate(previews[:limit_posts or 50]):
                    old_link = page.locator('[role="article"] a[href*="comment_id="]').first
                    previous_href = old_link.get_attribute("href") if old_link.count() else None
                    page.get_by_text(preview, exact=True).first.click(timeout=5000)
                    if index and previous_href:
                        page.wait_for_function("old => document.querySelector('[role=article] a[href*=comment_id]')?.getAttribute('href') !== old", arg=previous_href, timeout=10000)
                    page.locator('[role="article"][aria-label^="Comment by"]').first.wait_for(timeout=10000)
                    for _ in range(5):
                        more = page.get_by_role("button", name=re.compile(r"^View \d+ more comments$"))
                        if not more.count():
                            break
                        more.first.click()
                        page.wait_for_timeout(500)
                    for record in self._read_comment_rows(page):
                        results[record['id']] = PlatformComment(record['id'], page.url, record['url'],
                            record['user_id'], record['username'], record['text'], has_author_replied=record['replied'])
                return list(results.values())
            except Exception as exc:
                if 'Page crashed' in str(exc):
                    from core.mem_guard import get_free_memory_mb, get_oom_kill_count
                    raise PlatformAccessError(f"Facebook page crashed; container OOM kills={get_oom_kill_count()}, free memory={get_free_memory_mb()} MB") from None
                raise
            finally:
                try:
                    browser.close()
                except Exception:
                    pass  # Preserve the original scan failure if Chromium has already exited.

    @staticmethod
    def _read_post_previews(page):
        # The navigation renders before the asynchronous post list.
        previews = page.locator('div._at42 > div._4ik4._4ik5')
        try:
            previews.first.wait_for(state="visible", timeout=20000)
        except Exception:
            raise PlatformAccessError("Facebook comment inbox list did not load; check page layout and account access") from None
        return list(dict.fromkeys(text.strip() for text in previews.all_text_contents() if text.strip()))

    @staticmethod
    def _read_comment_rows(page):
        return page.locator('[role="article"][aria-label^="Comment by"]').evaluate_all(r"""rows => rows.flatMap(row => {
            const link = row.querySelector('a[href*="comment_id="]');
            if (!link) return [];
            const url = new URL(link.href);
            const id = url.searchParams.get('comment_id');
            if (!id) return [];
            const buttons = [...row.querySelectorAll('[role="button"]')];
            const author = buttons.find(el => el.textContent.trim() && !el.getAttribute('aria-label'));
            const username = author?.textContent.trim();
            if (!username || username === 'Bohdan GPT') return [];
            const clone = row.cloneNode(true);
            clone.querySelectorAll('[role="button"], a, [role="article"], [role="textbox"]').forEach(el => el.remove());
            const text = clone.textContent.replace(/^[\s·]+/, '').trim();
            if (!text) return [];
            const replied = [...row.parentElement.querySelectorAll('[role="article"]')].some(el => (el.getAttribute('aria-label') || '').startsWith('Comment by Bohdan GPT '));
            return [{id, url:url.origin + url.pathname + '?comment_id=' + id, user_id:username, username, text, replied}];
        })""")

    def is_user_following(self, user_id, username):
        return None

    def check_follower_status(self, user_id, username):
        return None, None

    def fetch_direct_messages(self):
        if not FACEBOOK_PAGE_TOKEN or FACEBOOK_PAGE_TOKEN.startswith("your_"):
            raise PlatformAccessError("Messenger requires a Page token with pages_messaging; check Business Suite identity restriction")
        from datetime import datetime, timezone
        response = requests.get(f"https://graph.facebook.com/{GRAPH_VERSION}/{FACEBOOK_PAGE_ID}/conversations",
            params={"access_token": FACEBOOK_PAGE_TOKEN, "platform": "messenger", "fields": "id,messages.limit(1){id,message,from,created_time}", "limit": 25}, timeout=20)
        if response.status_code != 200:
            raise PlatformAccessError(f"Messenger inbox unavailable (HTTP {response.status_code})")
        for thread in response.json().get("data", []):
            for message in thread.get("messages", {}).get("data", []):
                sender = message.get("from", {})
                if not sender.get("id") or sender["id"] == FACEBOOK_PAGE_ID or not message.get("message"):
                    continue
                timestamp = datetime.fromisoformat(message["created_time"].replace("Z", "+00:00"))
                if (datetime.now(timezone.utc) - timestamp).total_seconds() >= 86400:
                    continue
                yield PlatformComment(message["id"], thread["id"], None, sender["id"], sender.get("name", sender["id"]), message["message"])

    def reply_to_direct_message(self, message, text):
        if not FACEBOOK_PAGE_TOKEN:
            return False, "page_token_missing"
        try:
            response = requests.post(f"https://graph.facebook.com/{GRAPH_VERSION}/{FACEBOOK_PAGE_ID}/messages",
                json={"recipient": {"id": message.user_id}, "messaging_type": "RESPONSE", "message": {"text": text},
                      "access_token": FACEBOOK_PAGE_TOKEN}, timeout=20)
            if response.status_code == 200 and response.json().get("message_id"):
                return True, None
            if response.status_code == 200 or response.status_code >= 500:
                return False, "delivery_unknown"
            return False, f"messenger_http_{response.status_code}"
        except requests.RequestException:
            return False, "delivery_unknown"

    def send_direct_message(self, user_id: str, username: str, text: str, comment_id: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """
        Надсилає Private Reply у Messenger через Graph API або браузер.
        """
        # 1. Офіційний Private Reply API (за comment_id)
        if comment_id and FACEBOOK_PAGE_TOKEN and not FACEBOOK_PAGE_TOKEN.startswith("your_"):
            try:
                url = f"https://graph.facebook.com/{GRAPH_VERSION}/{FACEBOOK_PAGE_ID}/messages"
                payload = {
                    "recipient": {"comment_id": comment_id},
                    "message": {"text": text},
                    "access_token": FACEBOOK_PAGE_TOKEN
                }
                r = requests.post(url, json=payload, timeout=10)
                if r.status_code == 200 and r.json().get("message_id"):
                    logger.info(f"✅ Facebook Private Reply успішно надіслано на comment_id={comment_id}")
                    return True, None
                else:
                    err_data = r.json()
                    err_msg = err_data.get("error", {}).get("message", "")
                    if "cannot call" in err_msg.lower() or "permission" in err_msg.lower():
                        logger.debug(f"Facebook API token limitations: {err_msg}")
                    elif "private" in err_msg.lower() or "closed" in err_msg.lower():
                        return False, "private_dm"
            except Exception as e:
                logger.debug(f"Помилка відправки FB Graph API: {e}")

        # 2. Браузерний фолбек: якщо Graph API недоступний (Dev mode), повертаємо restricted_dm для публічної відповіді
        logger.info(f"[Facebook DM] Прямий Direct до @{username} обмежено платформою Meta, перемикаємо на публічну відповідь...")
        return False, "restricted_dm"

    def reply_to_comment(self, comment_id: str, text: str, post_id: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """
        Публікує публічну відповідь на коментар у Facebook (Graph API або Playwright).
        """
        # 1. Graph API
        if FACEBOOK_PAGE_TOKEN and not FACEBOOK_PAGE_TOKEN.startswith("your_") and not comment_id.startswith("fb_"):
            try:
                url = f"https://graph.facebook.com/{GRAPH_VERSION}/{comment_id}/comments"
                r = requests.post(url, data={"message": text, "access_token": FACEBOOK_PAGE_TOKEN}, timeout=10)
                if r.status_code == 200 and r.json().get("id"):
                    logger.info(f"✅ Facebook public comment reply sent to {comment_id}")
                    return True, None
                if r.status_code >= 500 or r.status_code == 200:
                    return False, "delivery_unknown"
            except requests.RequestException:
                return False, "delivery_unknown"

        # 2. Браузерна публікація через Playwright
        submitted = False
        if FACEBOOK_STATE_FILE.exists():
            try:
                from core.browser_lock import BROWSER_LOCK, CHROME_DOCKER_ARGS
                from playwright.sync_api import sync_playwright
                with BROWSER_LOCK:
                    with sync_playwright() as p:
                        browser = p.chromium.launch(channel="chromium", headless=True, args=CHROME_DOCKER_ARGS)
                        ctx = browser.new_context(
                            storage_state=str(FACEBOOK_STATE_FILE),
                            locale="en-US",
                            viewport={"width": 1280, "height": 800}
                        )
                        page = ctx.new_page()
                        try:
                            page.route("**/*", lambda route: route.abort() if route.request.resource_type in ("image", "media", "font") else route.continue_())
                        except Exception:
                            pass
                        target_url = post_id if post_id and str(post_id).startswith("https://") else f"https://www.facebook.com/{FACEBOOK_PROFILE_ID}?comment_id={comment_id}"
                        page.goto(target_url, wait_until="domcontentloaded", timeout=25000)
                        self._check_restrictions(page)
                        page.locator(f'a[href*="comment_id={comment_id}"]').first.wait_for(timeout=15000)

                        if comment_id.startswith("fb_"):
                            browser.close()
                            return False, "comment_target_missing"
                        links = [link for link in page.locator('a[href*="comment_id="]').all()
                                 if parse_qs(urlsplit(link.get_attribute("href") or "").query).get("comment_id") == [comment_id]]
                        if not links:
                            browser.close()
                            return False, "comment_target_missing"
                        row = links[0].locator('xpath=ancestor::div[@role="article"][1]')
                        thread = row.locator('xpath=..')
                        receipt = thread.locator('[role="article"][aria-label^="Comment by Bohdan GPT "]').get_by_text(text, exact=True)
                        if receipt.count():
                            browser.close()
                            return True, None
                        row.get_by_text(re.compile(r"^(Reply|Відповісти)$")).first.click(timeout=5000)

                        # 3. Знаходимо активне поле вводу Lexical / Draft.js / textarea
                        textbox = thread.get_by_role("textbox", name=re.compile(r"^Reply as|^Відповісти як")).first
                        if textbox.is_visible():
                            textbox.scroll_into_view_if_needed()
                            textbox.click(force=True)
                            page.wait_for_timeout(300)
                            try:
                                textbox.fill(text)
                            except Exception:
                                page.keyboard.type(text, delay=20)
                            page.wait_for_timeout(500)
                            submitted = True
                            textbox.press("Enter")
                            receipt.last.wait_for(timeout=10000)
                            page.reload(wait_until="domcontentloaded", timeout=20000)
                            receipt.last.wait_for(timeout=10000)
                            browser.close()
                            logger.info(f"✅ [Facebook Playwright] Опубліковано відповідь на {comment_id}: '{text}'")
                            return True, None
                        browser.close()
            except Exception as pe:
                logger.warning("Facebook reply failed: %s", type(pe).__name__)
                return False, "delivery_unknown" if submitted else "reply_failed"

        logger.warning("Facebook reply delivery failed")
        return False, "reply_failed"

    def like_comment(self, comment_id: str, post_id: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """
        Ставить лайк на коментар у Facebook (Graph API або Playwright).
        """
        # 1. Graph API
        if FACEBOOK_PAGE_TOKEN and not FACEBOOK_PAGE_TOKEN.startswith("your_") and not comment_id.startswith("fb_"):
            try:
                url = f"https://graph.facebook.com/{GRAPH_VERSION}/{comment_id}/likes"
                r = requests.post(url, data={"access_token": FACEBOOK_PAGE_TOKEN}, timeout=10)
                if r.status_code == 200:
                    logger.info(f"❤️ [Facebook Graph API] Лайк надіслано на comment_id={comment_id}")
                    return True, None
            except Exception as e:
                logger.debug(f"FB Graph API like error: {e}")

        # 2. Playwright browser mode
        if post_id and FACEBOOK_STATE_FILE.exists():
            try:
                from playwright.sync_api import sync_playwright
                from core.browser_lock import BROWSER_LOCK, CHROME_DOCKER_ARGS
                with BROWSER_LOCK:
                    with sync_playwright() as p:
                        browser = p.chromium.launch(channel="chromium", headless=True, args=CHROME_DOCKER_ARGS)
                        ctx = browser.new_context(storage_state=str(FACEBOOK_STATE_FILE), locale="en-US", viewport={"width": 1280, "height": 800})
                        page = ctx.new_page()
                        target_url = post_id if post_id.startswith("http") else f"https://www.facebook.com{post_id}"
                        page.goto(target_url, wait_until="domcontentloaded", timeout=15000)
                        page.wait_for_timeout(2000)
                        c_btn = page.locator('[aria-label*="Comment"], [aria-label*="comment"]').first
                        if c_btn.is_visible():
                            c_btn.click()
                            page.wait_for_timeout(1500)
                        like_btn = page.locator('[aria-label="Like"]').first
                        if like_btn.is_visible():
                            like_btn.click()
                            page.wait_for_timeout(400)
                            logger.info(f"❤️ [Facebook Playwright] Лайк поставлено у {target_url}")
                        browser.close()
                        return False, "like_not_verified"
            except Exception as pe:
                logger.debug("Facebook like failed: %s", type(pe).__name__)
        return False, "like_not_verified"


facebook_funnel = FacebookFunnel()
