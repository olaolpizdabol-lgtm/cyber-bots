"""
🎵 TikTok Lead Funnel Platform Handler
Account: @bohdan.gpt

Strategy:
Since TikTok strictly limits direct messaging non-mutual friends,
the bot monitors comments and responds with a magnetic bridge hook in English
directing them to Instagram @bohdan.gpt or the Bio link.
"""
from contextlib import contextmanager
import os
import hashlib
import re
import logging
from typing import Dict, Any, List, Optional, Tuple

from services.lead_funnel.platforms.base import BasePlatformFunnel, PlatformComment, PlatformAccessError
from core.browser_lock import BROWSER_LOCK
from config import BASE_DIR, DATA_DIR

logger = logging.getLogger("tiktok_funnel")


class TikTokFunnel(BasePlatformFunnel):
    def __init__(self):
        self._comment_targets = {}

    @property
    def platform_name(self) -> str:
        return "tiktok"

    def fetch_recent_unanswered_comments(self, limit_posts: int = 5) -> List[PlatformComment]:
        """Отримує коментарі під останніми TikTok відео"""
        results: List[PlatformComment] = []
        state_file = DATA_DIR / "tiktok_channel_state.json"
        if not state_file.exists():
            raise PlatformAccessError("TikTok channel session missing; run scripts/login_tiktok_channel.py")
        try:
            from playwright.sync_api import sync_playwright
            from core.browser_lock import BROWSER_LOCK, CHROME_DOCKER_ARGS
            with BROWSER_LOCK:
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True, args=CHROME_DOCKER_ARGS)
                    page = browser.new_page(
                        storage_state=str(state_file),
                        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                    )
                    page.goto("https://www.tiktok.com/@bohdan.gpt", wait_until="domcontentloaded", timeout=15000)
                    page.wait_for_timeout(3000)

                    # Знаходимо відео профілю
                    if limit_posts is None or limit_posts > 5:
                        for _ in range(4):
                            page.mouse.wheel(0, 2000)
                            page.wait_for_timeout(600)

                    raw_vids = [a.get_attribute("href") for a in page.locator('a[href*="/video/"]').all()]
                    unique_vids = list(dict.fromkeys([l for l in raw_vids if l]))
                    target_vids = unique_vids if limit_posts is None else unique_vids[:limit_posts]

                    for vid_url in target_vids:
                        try:
                            page.goto(vid_url, wait_until="domcontentloaded", timeout=15000)
                            page.wait_for_timeout(2500)
                            comment_elems = page.locator('[data-e2e="comment-level-1"]').all()
                            for c in comment_elems[:15]:
                                try:
                                    text = c.inner_text()
                                    lines = [l.strip() for l in text.split("\n") if l.strip()]
                                    if len(lines) >= 2:
                                        u_name = lines[0]
                                        c_body = lines[1]
                                        if "bohdan" not in u_name.lower():
                                            c_id_gen = "tt_" + hashlib.sha256(f"{vid_url}|{u_name}|{c_body}".encode()).hexdigest()[:24]
                                            self._comment_targets[c_id_gen] = (u_name, c_body)
                                            results.append(PlatformComment(
                                                comment_id=c_id_gen,
                                                post_id=vid_url,
                                                post_url=vid_url,
                                                user_id=c_id_gen,
                                                username=u_name,
                                                text=c_body,
                                                has_author_replied=False
                                            ))
                                except Exception:
                                    continue
                        except Exception as vid_err:
                            logger.debug(f"Помилка парсингу TikTok відео {vid_url}: {vid_err}")
                            continue
                    browser.close()
        except Exception as e:
            logger.warning("TikTok fetch failed: %s", type(e).__name__)
            raise

        return results

    @contextmanager
    def _inbox_page(self):
        from playwright.sync_api import sync_playwright
        from core.browser_lock import CHROME_DOCKER_ARGS
        state_file = DATA_DIR / "tiktok_channel_state.json"
        if not state_file.exists():
            raise PlatformAccessError("TikTok channel session missing")
        with BROWSER_LOCK, sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=CHROME_DOCKER_ARGS)
            try:
                page = browser.new_page(storage_state=str(state_file), locale="en-US")
                page.goto("https://www.tiktok.com/messages", wait_until="domcontentloaded", timeout=25000)
                page.locator('a[href="/@bohdan.gpt"]').first.wait_for(timeout=12000)
                yield page
            finally:
                browser.close()

    def fetch_direct_messages(self):
        messages = []
        with self._inbox_page() as page:
            for pending in (False, True):
                if pending:
                    requests_button = page.get_by_role("button", name=re.compile(r"Message requests|Запити на надсилання повідомлень", re.I))
                    if not requests_button.count():
                        continue
                    requests_button.first.click()
                rows = page.locator('[data-e2e="dm-new-conversation-item"]')
                for index in range(min(rows.count(), 25)):
                    rows.nth(index).click()
                    items = page.locator('[data-e2e="dm-new-chat-item"]')
                    if not items.count():
                        continue
                    record = items.last.evaluate(r"""el => {
                        const avatar = el.querySelector('a[href*="/@"]');
                        const username = avatar?.getAttribute('href')?.match(/\/@([\w.]+)/)?.[1];
                        const id = el.querySelector('[data-e2e="dm-new-more-btn"]')?.id;
                        const text = el.querySelector('[class*="DivTextContainer"]')?.innerText;
                        return {username, id, text};
                    }""")
                    # Positive sender evidence only; missing avatar/id is not an incoming message.
                    if not record.get('id') or not record.get('text') or not record.get('username') or record['username'] == 'bohdan.gpt':
                        continue
                    username = record['username']
                    messages.append(PlatformComment(record['id'], username, None, username, username, record['text'], pending_request=pending))
        return messages

    def is_user_following(self, user_id, username):
        if not re.fullmatch(r"[\w.]+", username):
            return None
        with self._inbox_page() as page:
            page.goto(f"https://www.tiktok.com/@{username}", wait_until="domcontentloaded", timeout=20000)
            # Follow back / Friends proves incoming follow; Follow alone is the opposite direction.
            positive = page.get_by_role("button", name=re.compile(r"^(Follow back|Friends|Стежити у відповідь|Друзі)$", re.I))
            if positive.count() and positive.first.is_visible():
                return True
        return None

    def reply_to_direct_message(self, message, text):
        if not re.fullmatch(r"[\w.]+", message.username):
            return False, "recipient_invalid"
        submitted = False
        try:
            with self._inbox_page() as page:
                page.goto(f"https://www.tiktok.com/@{message.username}", wait_until="domcontentloaded", timeout=20000)
                page.get_by_role("button", name=re.compile(r"^(Message|Повідомлення)$")).click(timeout=10000)
                if not page.locator(f'a[href="/@{message.username}"]').count():
                    return False, "recipient_mismatch"
                accept = page.get_by_role("button", name=re.compile(r"^(Accept|Прийняти)$"))
                if accept.count():
                    accept.click()
                editor = page.locator('[data-e2e="chat-input"] [contenteditable="true"]')
                editor.wait_for(timeout=10000)
                outgoing = page.locator('[data-e2e="dm-new-chat-item"]').filter(
                    has=page.locator('a[href="/@bohdan.gpt"], [data-e2e*="self"], [class*="Self"]')).get_by_text(text, exact=True)
                if outgoing.count():
                    return True, None
                editor.fill(text)
                submitted = True
                editor.press("Enter")
                outgoing.last.wait_for(timeout=10000)
                page.reload(wait_until="domcontentloaded", timeout=20000)
                outgoing.last.wait_for(timeout=10000)
                return True, None
        except Exception as exc:
            return False, "delivery_unknown" if submitted else type(exc).__name__

    def send_direct_message(self, user_id, username, text, comment_id=None):
        return self.reply_to_direct_message(PlatformComment("", username, None, user_id, username, ""), text)

    def reply_to_comment(self, comment_id: str, text: str, post_id: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        state_file = DATA_DIR / "tiktok_channel_state.json"
        target = self._comment_targets.get(comment_id)
        if not state_file.exists() or not target or not post_id:
            return False, "tiktok_session_or_comment_missing"
        try:
            from playwright.sync_api import sync_playwright
            from core.browser_lock import CHROME_DOCKER_ARGS
            with BROWSER_LOCK, sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=CHROME_DOCKER_ARGS)
                try:
                    page = browser.new_page(storage_state=str(state_file), locale="en-US")
                    page.goto(post_id, wait_until="domcontentloaded", timeout=20000)
                    rows = page.locator('[data-e2e="comment-level-1"]').filter(has_text=target[0]).filter(has_text=target[1])
                    rows.first.wait_for(timeout=10000)
                    if rows.count() != 1:
                        return False, "comment_target_ambiguous"
                    row = rows.first
                    if row.get_by_text(text, exact=True).count():
                        return True, None
                    row.get_by_text("Reply", exact=True).click(timeout=5000)
                    editor = page.locator('[contenteditable="true"]').first
                    editor.fill(text)
                    page.get_by_text("Post", exact=True).click(timeout=5000)
                    row.get_by_text(text, exact=True).wait_for(timeout=10000)
                    return True, None
                finally:
                    browser.close()
        except Exception as exc:
            logger.warning("TikTok reply failed: %s", type(exc).__name__)
            return False, "tiktok_reply_failed"

    def like_comment(self, comment_id: str, post_id: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        return False, "not_implemented"


tiktok_funnel = TikTokFunnel()
