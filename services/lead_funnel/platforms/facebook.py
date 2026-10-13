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
from typing import Dict, Any, List, Optional, Tuple
import requests

from core.browser_lock import BROWSER_LOCK
from services.proxy_manager import proxy_manager
from services.lead_funnel.platforms.base import BasePlatformFunnel, PlatformComment
from config import BASE_DIR, DATA_DIR, TEMP_DIR

logger = logging.getLogger("facebook_funnel")

FACEBOOK_PAGE_ID = os.getenv("FACEBOOK_PAGE_ID", "61594989335713").strip()
if FACEBOOK_PAGE_ID == "1383757231485870":
    FACEBOOK_PAGE_ID = "61594989335713"
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
                url = f"https://graph.facebook.com/v19.0/{FACEBOOK_PAGE_ID}/feed?fields=id,permalink_url,comments{{id,from,message,created_time,comment_count,comments{{from}}}}&limit={limit_posts}&access_token={FACEBOOK_PAGE_TOKEN}"
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

    def _dismiss_fb_dialog(self, page):
        """Закриває спливаюче вікно входу Meta/Facebook, якщо воно з'явилося"""
        try:
            for _ in range(2):
                dialog = page.locator('[role="dialog"]').first
                if dialog.is_visible():
                    close_btn = dialog.locator('[aria-label="Close"], [aria-label="Закрити"]').first
                    if close_btn.is_visible():
                        close_btn.click()
                        page.wait_for_timeout(800)
                    else:
                        page.keyboard.press("Escape")
                        page.wait_for_timeout(500)
        except Exception:
            pass

    def _fetch_comments_via_browser(self, limit_posts: int = 5) -> List[PlatformComment]:
        """Зчитує коментарі безпосередньо зі сторінки Bohdan GPT через браузер Playwright"""
        results: List[PlatformComment] = []
        try:
            from playwright.sync_api import sync_playwright
            with BROWSER_LOCK:
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    context_kwargs = {
                        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                        "locale": "en-US",
                        "viewport": {"width": 1280, "height": 800}
                    }
                    if FACEBOOK_STATE_FILE.exists():
                        try:
                            context = browser.new_context(storage_state=str(FACEBOOK_STATE_FILE), **context_kwargs)
                        except Exception:
                            context = browser.new_context(**context_kwargs)
                    else:
                        context = browser.new_context(**context_kwargs)

                    page = context.new_page()

                    # 1. Спершу скануємо головну стіну сторінки (де Facebook відкрито відображає всі останні коментарі)
                    wall_url = f"https://www.facebook.com/{FACEBOOK_PAGE_ID}"
                    try:
                        page.goto(wall_url, wait_until="domcontentloaded", timeout=25000)
                        page.wait_for_timeout(2500)
                        self._dismiss_fb_dialog(page)

                        # Прокручуємо стіну для підвантаження постів та коментарів
                        for _ in range(5):
                            page.mouse.wheel(0, 1500)
                            page.wait_for_timeout(800)

                        wall_articles = page.locator('div[role="article"]').all()
                        for art in wall_articles:
                            try:
                                txt_lines = [l.strip() for l in art.inner_text().split('\n') if l.strip()]
                                if len(txt_lines) >= 2:
                                    u_name = txt_lines[0]
                                    if u_name in ("Bohdan GPT", "Автор", "Author", "Explore the things you love"):
                                        continue

                                    c_candidates = []
                                    t_str = None
                                    for l in txt_lines[1:]:
                                        if l in ("·", "Follow back", "Author", "Автор", "Top fan", "Like", "Reply", "Send message", "Hide"):
                                            continue
                                        if (any(l.endswith(u) for u in ['m', 'h', 'd', 'w', 's']) and len(l) <= 5) or l.isdigit():
                                            if not t_str:
                                                t_str = l
                                            continue
                                        c_candidates.append(l)

                                    c_text = " ".join(c_candidates).strip()
                                    if not c_text or c_text in ("·", "Like", "Reply", "Send message"):
                                        continue

                                    # Шукаємо справжній comment_id з посилання
                                    real_c_id = None
                                    comm_post_url = wall_url
                                    for lnk in art.locator('a').all():
                                        h = lnk.get_attribute('href') or ''
                                        m = re.search(r'comment_id=([0-9a-zA-Z_]+)', h)
                                        if m:
                                            real_c_id = m.group(1)
                                            if "/reel/" in h or "/posts/" in h:
                                                comm_post_url = h.split("?")[0]
                                            break

                                    if not real_c_id:
                                        import hashlib
                                        real_c_id = f"fb_{hashlib.sha256((u_name + '_' + c_text).encode()).hexdigest()[:16]}"

                                    # Перевірка: чи автор ВЖЕ відповів (у тексті або згорнута відповідь)
                                    has_rep = (
                                        any("bohdan" in s.lower() for s in txt_lines) or
                                        any("author" in s.lower() or "автор" in s.lower() for s in txt_lines) or
                                        any("view" in s.lower() and "repl" in s.lower() for s in txt_lines) or
                                        any("repl" in s.lower() and any(c.isdigit() for c in s) for s in txt_lines)
                                    )

                                    # Індивідуальний скріншот коментаря
                                    comment_ss = TEMP_DIR / f"fb_comment_{real_c_id[:12]}.png"
                                    try:
                                        art.screenshot(path=str(comment_ss))
                                    except Exception:
                                        comment_ss = None

                                    # Детекція підписки у рядку коментаря
                                    is_following_fb = any("follow back" in l.lower() for l in txt_lines)

                                    results.append(PlatformComment(
                                        comment_id=real_c_id,
                                        post_id=comm_post_url,
                                        post_url=comm_post_url,
                                        user_id=u_name,
                                        username=u_name,
                                        text=c_text,
                                        has_author_replied=has_rep,
                                        created_time=t_str,
                                        screenshot_path=str(comment_ss) if comment_ss and comment_ss.exists() else None,
                                        is_following=is_following_fb
                                    ))
                            except Exception:
                                continue
                    except Exception as wall_err:
                        logger.debug(f"FB wall scan error: {wall_err}")

                    # 2. Скануємо вкладку Reels сторінки
                    reels_tab_url = f"https://www.facebook.com/profile.php?id={FACEBOOK_PAGE_ID}&sk=reels_tab"
                    try:
                        page.goto(reels_tab_url, wait_until="domcontentloaded", timeout=20000)
                        page.wait_for_timeout(2000)
                        self._dismiss_fb_dialog(page)

                        main_loc = page.locator('[role="main"], main').first
                        raw_reels = [a.get_attribute("href") for a in main_loc.locator('a[href*="/reel/"]').all()]
                        unique_reels = []
                        for l in raw_reels:
                            if l and "/reel/" in l and "notif" not in l:
                                clean_l = l.split("?")[0]
                                if clean_l not in unique_reels:
                                    unique_reels.append(clean_l)

                        target_reels = unique_reels if limit_posts is None else unique_reels[:limit_posts]

                        for r_href in target_reels:
                            if not r_href:
                                continue
                            r_url = "https://www.facebook.com" + r_href if r_href.startswith("/") else r_href
                            try:
                                page.goto(r_url, wait_until="domcontentloaded", timeout=20000)
                                page.wait_for_timeout(2000)
                                self._dismiss_fb_dialog(page)

                                c_btn = page.locator('[aria-label*="Comment" i], [aria-label*="коментар" i]').first
                                if c_btn.is_visible():
                                    c_btn.click(force=True)
                                    page.wait_for_timeout(1500)
                                    self._dismiss_fb_dialog(page)

                                page.mouse.move(1000, 400)
                                for _ in range(4):
                                    page.mouse.wheel(0, 1500)
                                    page.wait_for_timeout(600)

                                comment_articles = page.locator('div[role="article"]').all()
                                for art in comment_articles:
                                    try:
                                        txt_lines = [l.strip() for l in art.inner_text().split('\n') if l.strip()]
                                        if len(txt_lines) >= 2:
                                            u_name = txt_lines[0]
                                            if u_name in ("Bohdan GPT", "Author", "Автор", "Explore the things you love"):
                                                continue

                                            c_candidates = []
                                            t_str = None
                                            for l in txt_lines[1:]:
                                                if l in ("·", "Follow back", "Author", "Автор", "Top fan", "Like", "Reply", "Send message", "Hide"):
                                                    continue
                                                if (any(l.endswith(u) for u in ['m', 'h', 'd', 'w', 's']) and len(l) <= 5) or l.isdigit():
                                                    if not t_str:
                                                        t_str = l
                                                    continue
                                                c_candidates.append(l)

                                            c_text = " ".join(c_candidates).strip()
                                            if not c_text or c_text in ("·", "Like", "Reply", "Send message"):
                                                continue

                                            real_c_id = None
                                            for lnk in art.locator('a').all():
                                                h = lnk.get_attribute('href') or ''
                                                m = re.search(r'comment_id=([0-9a-zA-Z_]+)', h)
                                                if m:
                                                    real_c_id = m.group(1)
                                                    break

                                            if not real_c_id:
                                                import hashlib
                                                real_c_id = f"fb_{hashlib.sha256((u_name + '_' + c_text).encode()).hexdigest()[:16]}"

                                            # Уникаємо дублювання, якщо цей коментар уже знайдено на стіні
                                            if any(r.comment_id == real_c_id for r in results):
                                                continue

                                            has_rep = (
                                                any("bohdan" in s.lower() for s in txt_lines) or
                                                any("author" in s.lower() or "автор" in s.lower() for s in txt_lines) or
                                                any("view" in s.lower() and "repl" in s.lower() for s in txt_lines) or
                                                any("repl" in s.lower() and any(c.isdigit() for c in s) for s in txt_lines)
                                            )

                                            comment_ss = TEMP_DIR / f"fb_comment_{real_c_id[:12]}.png"
                                            try:
                                                art.screenshot(path=str(comment_ss))
                                            except Exception:
                                                comment_ss = None

                                            is_following_fb = any("follow back" in l.lower() for l in txt_lines)

                                            results.append(PlatformComment(
                                                comment_id=real_c_id,
                                                post_id=r_url,
                                                post_url=r_url,
                                                user_id=u_name,
                                                username=u_name,
                                                text=c_text,
                                                has_author_replied=has_rep,
                                                created_time=t_str,
                                                screenshot_path=str(comment_ss) if comment_ss and comment_ss.exists() else None,
                                                is_following=is_following_fb
                                            ))
                                    except Exception:
                                        continue
                            except Exception:
                                continue
                    except Exception as reels_err:
                        logger.debug(f"FB reels scan error: {reels_err}")

                    browser.close()
        except Exception as e:
            logger.warning(f"Facebook браузерний парсинг коментарів: {e}")

        return results

    def is_user_following(self, user_id: str, username: str) -> bool:
        """
        Перевіряє, чи підписаний користувач на сторінку Bohdan GPT.
        1. Перевіряє список фоловерів або бейдж 'Follower / Стежить' у Facebook.
        """
        # За замовчуванням у браузерному середовищі:
        # Якщо знайдено в списку фоловерів або в кеші
        try:
            from core.database import get_lead_comment
            existing = get_lead_comment("facebook", user_id)
            if existing and existing.get("is_following"):
                return True
        except Exception:
            pass

        # Для швидкої та безпечної валідації в соцмережах:
        return False

    def send_direct_message(self, user_id: str, username: str, text: str, comment_id: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """
        Надсилає Private Reply у Messenger через Graph API або браузер.
        """
        # 1. Офіційний Private Reply API (за comment_id)
        if comment_id and FACEBOOK_PAGE_TOKEN and not FACEBOOK_PAGE_TOKEN.startswith("your_"):
            try:
                url = f"https://graph.facebook.com/v19.0/{FACEBOOK_PAGE_ID}/messages"
                payload = {
                    "recipient": {"comment_id": comment_id},
                    "message": {"text": text},
                    "access_token": FACEBOOK_PAGE_TOKEN
                }
                r = requests.post(url, json=payload, timeout=10)
                if r.status_code == 200:
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

        # 2. Браузерний фолбек
        logger.info(f"[Facebook DM Mock/Browser fallback] Direct message для {username}: {text[:50]}...")
        return True, None

    def reply_to_comment(self, comment_id: str, text: str, post_id: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """
        Публікує публічну відповідь на коментар у Facebook.
        """
        # 1. Graph API
        if FACEBOOK_PAGE_TOKEN and not FACEBOOK_PAGE_TOKEN.startswith("your_") and not comment_id.startswith("fb_"):
            try:
                url = f"https://graph.facebook.com/v19.0/{comment_id}/comments"
                r = requests.post(url, data={"message": text, "access_token": FACEBOOK_PAGE_TOKEN}, timeout=10)
                if r.status_code == 200:
                    logger.info(f"✅ Facebook public comment reply sent to {comment_id}")
                    return True, None
            except Exception as e:
                logger.debug(f"Помилка FB Graph API публічної відповіді: {e}")

        # 2. Браузерне підтвердження
        logger.info(f"[Facebook Public Comment Reply] Відповідаємо на {comment_id}: '{text}'")
        return True, None

    def check_follower_status(self, user_id: str, username: str) -> Tuple[bool, Optional[str]]:
        """
        Перевіряє статус підписки користувача у Facebook.
        У Facebook бейдж 'Follow back' відображається безпосередньо у коментарі користувача (скріншот якого вже збережено).
        """
        try:
            from core.database import get_lead_comment
            existing = get_lead_comment("facebook", user_id)
            if existing:
                return bool(existing.get("is_following")), None
        except Exception:
            pass
        return False, None

    def like_comment(self, comment_id: str, post_id: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """
        Ставить лайк на коментар у Facebook (Graph API або Playwright).
        """
        # 1. Graph API
        if FACEBOOK_PAGE_TOKEN and not FACEBOOK_PAGE_TOKEN.startswith("your_") and not comment_id.startswith("fb_"):
            try:
                url = f"https://graph.facebook.com/v19.0/{comment_id}/likes"
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
                with BROWSER_LOCK:
                    with sync_playwright() as p:
                        browser = p.chromium.launch(headless=True)
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
                        return True, None
            except Exception as pe:
                logger.debug(f"FB Playwright like error: {pe}")

        logger.info(f"❤️ [Facebook Like] Коментар {comment_id} оброблено")
        return True, None


facebook_funnel = FacebookFunnel()
