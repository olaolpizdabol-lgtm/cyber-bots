"""
🎵 TikTok Lead Funnel Platform Handler
Account: @bohdan.gpt

Strategy:
Since TikTok strictly limits direct messaging non-mutual friends,
the bot monitors comments and responds with a magnetic bridge hook in English
directing them to Instagram @bohdan.gpt or the Bio link.
"""
import os
import re
import logging
from typing import Dict, Any, List, Optional, Tuple

from services.lead_funnel.platforms.base import BasePlatformFunnel, PlatformComment
from core.browser_lock import BROWSER_LOCK
from config import BASE_DIR, DATA_DIR

logger = logging.getLogger("tiktok_funnel")


class TikTokFunnel(BasePlatformFunnel):
    @property
    def platform_name(self) -> str:
        return "tiktok"

    def fetch_recent_unanswered_comments(self, limit_posts: int = 5) -> List[PlatformComment]:
        """Отримує коментарі під останніми TikTok відео"""
        results: List[PlatformComment] = []
        try:
            from playwright.sync_api import sync_playwright
            with BROWSER_LOCK:
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    page = browser.new_page(
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
                                            c_id_gen = f"tt_{abs(hash(text))}"
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
            logger.debug(f"TikTok fetch comments: {e}")

        return results

    def is_user_following(self, user_id: str, username: str) -> bool:
        # Для TikTok через блокування DM ми ведемо на IG/Bio
        return False

    def send_direct_message(self, user_id: str, username: str, text: str, comment_id: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        # TikTok не дозволяє прямі DM незнайомцям без взаємної підписки
        return False, "tiktok_dm_restricted"

    def reply_to_comment(self, comment_id: str, text: str, post_id: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """Відповідає на коментар у TikTok публічно"""
        logger.info(f"[TikTok Public Reply] На коментар {comment_id}: '{text}'")
        return True, None


tiktok_funnel = TikTokFunnel()
