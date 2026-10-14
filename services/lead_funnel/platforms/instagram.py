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
        self._client = None
        self._retry_after = 0.0

    @property
    def platform_name(self) -> str:
        return "instagram"

    def _pause_rejected_session(self, exc):
        status = getattr(exc, "code", None) or getattr(getattr(exc, "response", None), "status_code", None)
        if status in (401, 403):
            self._client = None
            self._retry_after = time.monotonic() + 300
            return f"Instagram API authorization rejected (HTTP {status}); paused for 5 minutes"
        return None

    def _get_client(self):
        if time.monotonic() < self._retry_after:
            return None
        if self._retry_after:
            self._client = None
            self._retry_after = 0.0
        if self._client:
            return self._client

        session_path = Path(INSTAGRAM_SESSION_FILE)
        if session_path.exists():
            try:
                if isinstance(json.loads(session_path.read_text()).get("cookies"), list):
                    return None
            except (OSError, ValueError):
                return None

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
                        # Chrome cookies belong to the web client; a mobile login can invalidate them.
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
        from .instagram_web import instagram_web
        results = {}
        with instagram_web() as web:
            for post in web.posts(limit_posts or 50):
                if str((post.get("user") or {}).get("pk")) != web.owner_id:
                    continue
                comments = web.comments(post["pk"])
                for comment in comments:
                    user = comment.get("user") or {}
                    if str(user.get("pk")) == web.owner_id or not user.get("username") or not comment.get("text"):
                        continue
                    replies = comment.get("preview_child_comments") or []
                    replied = any(str((c.get("user") or {}).get("pk")) == web.owner_id for c in replies)
                    if not replied and comment.get("child_comment_count", 0) > len(replies):
                        replies = web.child_comments(post["pk"], comment["pk"])
                        replied = any(str((c.get("user") or {}).get("pk")) == web.owner_id for c in replies)
                    cid = str(comment["pk"])
                    results[cid] = PlatformComment(cid, str(post["pk"]),
                        f"https://www.instagram.com/p/{post['code']}/", str(user["pk"]), user["username"],
                        comment["text"], has_author_replied=replied, created_time=str(comment.get("created_at", "")))
        logger.info("Instagram web scan: %s comments", len(results))
        return list(results.values())

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
                self._pause_rejected_session(exc)
                logger.warning("Instagram friendship check unavailable: %s", type(exc).__name__)
        from .instagram_web import instagram_web
        try:
            if not (DATA_DIR / "instagram_state.json").exists():
                return None, None
            with instagram_web() as web:
                return web.following(user_id, username), None
        except Exception as exc:
            logger.warning("Instagram web friendship check unavailable: %s", type(exc).__name__)
            return None, None

    def is_user_following(self, user_id: str, username: str) -> Optional[bool]:
        return self.check_follower_status(user_id, username)[0]

    def fetch_direct_messages(self):
        client = self._get_client()
        if client is None:
            yield from self._fetch_web_messages()
            return
        try:
            threads = [(t, False) for t in client.direct_threads(amount=20, thread_message_limit=10)]
            threads += [(t, True) for t in client.direct_pending_inbox(amount=20)]
        except Exception as exc:
            reason = self._pause_rejected_session(exc)
            if reason:
                raise PlatformAccessError(reason) from None
            raise
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

    def _fetch_web_messages(self):
        from .instagram_web import instagram_web
        messages = []
        with instagram_web() as web:
            for preview in web.inbox():
                if preview.get("is_group") or len(preview.get("usersWithoutViewer", [])) != 1:
                    continue
                latest = web.messages(preview)[:1]
                viewer = preview.get("viewer") or {}
                if not latest or latest[0].get("sender_fbid") == viewer.get("interop_messaging_user_fbid"):
                    continue
                thread = web.thread(preview["thread_key"])
                users = thread.get("users") or []
                if len(users) != 1:
                    continue
                user = users[0]
                latest = web.messages(thread)[:1]
                if not latest or web.is_own_message(latest[0]) or not latest[0].get("text_body"):
                    continue
                sender = ((latest[0].get("sender") or {}).get("user_dict") or {})
                if sender.get("username") != user.get("username"):
                    continue
                message = latest[0]
                messages.append(PlatformComment(str(message.get("message_id") or message["id"]),
                    thread["thread_key"], None, str(user["pk"]), user["username"], message["text_body"],
                    pending_request=thread.get("system_folder") == "PENDING"))
        logger.info("Instagram web inbox: %s incoming messages", len(messages))
        return messages

    def _send_web_message(self, text, user_id, username, thread_key=None):
        from .instagram_web import instagram_web
        if time.monotonic() < self._retry_after:
            return False, "authorization_paused"
        submitted = False
        try:
            with instagram_web() as web:
                if not str(user_id).isdigit():
                    user_id = web.follower_id(username)
                    if not user_id:
                        return False, "recipient_unresolved"
                if thread_key and len(str(thread_key)) >= 30:
                    preview = next((t for t in web.inbox() if t.get("thread_id") == str(thread_key)), None)
                    if not preview:
                        return False, "thread_unresolved"
                    thread_key = preview["thread_key"]
                thread = web.thread(thread_key) if thread_key else None
                if thread is None:
                    preview = next((t for t in web.inbox()
                        if not t.get("is_group") and len(t.get("usersWithoutViewer", [])) == 1
                        and str(t["usersWithoutViewer"][0].get("id")) == str(user_id)), None)
                    if preview:
                        thread = web.thread(preview["thread_key"])
                if thread:
                    users = thread.get("users") or []
                    if len(users) != 1 or str(users[0].get("pk")) != str(user_id) or users[0].get("username") != username:
                        return False, "recipient_mismatch"
                    if any(web.is_own_message(m) and m.get("text_body") == text for m in web.messages(thread)):
                        return True, None
                    if thread.get("system_folder") == "PENDING":
                        if not web.accept_request(thread):
                            return False, "request_not_accepted"
                elif not str(user_id).isdigit():
                    return False, "recipient_unresolved"
                submitted = True
                receipt = web.send_text(text, thread=thread, recipient=None if thread else user_id)
                if not receipt:
                    return False, "delivery_unknown"
                if not thread:
                    preview = next((t for t in web.inbox()
                        if not t.get("is_group") and len(t.get("usersWithoutViewer", [])) == 1
                        and str(t["usersWithoutViewer"][0].get("id")) == str(user_id)), None)
                    if not preview:
                        return False, "delivery_unknown"
                    thread = web.thread(preview["thread_key"])
                verified = web.thread(thread["thread_key"])
                users = verified.get("users") or []
                if len(users) != 1 or str(users[0].get("pk")) != str(user_id):
                    return False, "delivery_unknown"
                if not any((m.get("message_id") or m.get("id")) == receipt and web.is_own_message(m)
                           and m.get("text_body") == text for m in web.messages(verified)):
                    return False, "delivery_unknown"
                logger.info("Instagram web DM verified: recipient=%s message=%s", user_id, receipt)
                return True, None
        except Exception as exc:
            logger.warning("Instagram web DM failed: %s", type(exc).__name__)
            return False, "delivery_unknown" if submitted else str(exc) if isinstance(exc, PlatformAccessError) else "session_unavailable"

    def reply_to_direct_message(self, message, text):
        client = self._get_client()
        if client is None:
            return self._send_web_message(text, message.user_id, message.username, message.post_id)
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
        except Exception as exc:
            reason = self._pause_rejected_session(exc)
            if reason:
                return False, reason
            # A timeout may happen after submission; never fall back and send it twice.
            return False, "delivery_unknown"

    def send_direct_message(self, user_id: str, username: str, text: str, comment_id: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        client = self._get_client()
        if client is None:
            return self._send_web_message(text, user_id, username)
        try:
            target = int(user_id) if str(user_id).isdigit() else client.user_id_from_username(username)
        except Exception as exc:
            return False, type(exc).__name__
        try:
            response = client.direct_send(text, user_ids=[target])
            return (True, None) if getattr(response, "id", None) else (False, "delivery_unknown")
        except Exception as exc:
            reason = self._pause_rejected_session(exc)
            if reason:
                return False, reason
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

        return self._reply_web_comment(comment_id, text, post_id)

    def _reply_web_comment(self, comment_id, text, post_id):
        from .instagram_web import instagram_web
        submitted = False
        try:
            if not str(comment_id).isdigit() or not str(post_id).isdigit():
                return False, "comment_target_missing"
            with instagram_web() as web:
                info = web.api(f"media/{post_id}/info/").get("items", [])
                if len(info) != 1 or str((info[0].get("user") or {}).get("pk")) != web.owner_id:
                    return False, "post_owner_mismatch"
                parent = next((c for c in web.comments(post_id) if str(c["pk"]) == str(comment_id)), None)
                if not parent or str((parent.get("user") or {}).get("pk")) == web.owner_id:
                    return False, "comment_target_missing"
                def receipt(comment):
                    prefix = "@" + parent["user"]["username"] + " "
                    return (str((comment.get("user") or {}).get("pk")) == web.owner_id
                        and comment.get("text") in (text, prefix + text)
                        and str(comment.get("parent_comment_id")) == str(comment_id))
                if any(receipt(c) for c in web.child_comments(post_id, comment_id)):
                    return True, None
                submitted = True
                response = web.create_comment(post_id, comment_id, text)
                if not response or not response.get("pk") or str((response.get("user") or {}).get("pk")) != web.owner_id:
                    return False, "delivery_unknown"
                if not any(str(c["pk"]) == str(response["pk"]) and receipt(c) for c in web.child_comments(post_id, comment_id)):
                    return False, "delivery_unknown"
                logger.info("Instagram web reply verified: parent=%s reply=%s", comment_id, response["pk"])
                return True, None
        except Exception as exc:
            logger.warning("Instagram web comment failed: %s", type(exc).__name__)
            return False, "delivery_unknown" if submitted else "reply_failed"

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
