"""
▶️ YouTube Lead Funnel Platform Handler
Channel: Bohdan AI (@bohdan_gpt)

Strategy:
YouTube has no DMs. The bot monitors incoming comments, recognizes requests,
and replies with direct link / access instructions in English.
"""
import os
import re
import logging
from typing import Dict, Any, List, Optional, Tuple

from services.lead_funnel.platforms.base import BasePlatformFunnel, PlatformComment
from config import BASE_DIR, DATA_DIR, YOUTUBE_TOKEN_FILE

logger = logging.getLogger("youtube_funnel")


class YouTubeFunnel(BasePlatformFunnel):
    @property
    def platform_name(self) -> str:
        return "youtube"

    def fetch_recent_unanswered_comments(self, limit_posts: int = 5) -> List[PlatformComment]:
        """Отримує коментарі під останніми YouTube Shorts/відео через API або браузер"""
        results: List[PlatformComment] = []
        # Якщо підключено YouTube Data API
        try:
            from services.publishers.youtube import youtube_publisher
            service = youtube_publisher._get_authenticated_service()
            if service:
                # Отримуємо останні коментарі каналу
                req = service.commentThreads().list(
                    part="snippet",
                    allThreadsRelatedToChannelId=None,
                    maxResults=20
                )
                resp = req.execute()
                for item in resp.get("items", []):
                    top = item["snippet"]["topLevelComment"]["snippet"]
                    author_name = top["authorDisplayName"]
                    text = top["textDisplay"]
                    cid = item["id"]
                    vid_id = item["snippet"].get("videoId", "")
                    if "bohdan" not in author_name.lower():
                        results.append(PlatformComment(
                            comment_id=cid,
                            post_id=vid_id,
                            post_url=f"https://www.youtube.com/watch?v={vid_id}" if vid_id else None,
                            user_id=top.get("authorChannelId", {}).get("value", cid),
                            username=author_name,
                            text=text,
                            has_author_replied=False
                        ))
        except Exception as e:
            logger.debug(f"YouTube comment fetch: {e}")

        return results

    def is_user_following(self, user_id: str, username: str) -> bool:
        # YouTube API не надає статус підписки окремих коментаторів без їхнього OAuth
        return False

    def send_direct_message(self, user_id: str, username: str, text: str, comment_id: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        # У YouTube немає Direct Messages
        return False, "youtube_no_dm"

    def reply_to_comment(self, comment_id: str, text: str, post_id: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """Відповідає на коментар у YouTube"""
        try:
            from services.publishers.youtube import youtube_publisher
            service = youtube_publisher._get_authenticated_service()
            if service:
                service.comments().insert(
                    part="snippet",
                    body={
                        "snippet": {
                            "parentId": comment_id,
                            "textOriginal": text
                        }
                    }
                ).execute()
                logger.info(f"✅ YouTube відповідь надіслана на {comment_id}: '{text}'")
                return True, None
        except Exception as e:
            logger.debug(f"YouTube reply err: {e}")

        logger.info(f"[YouTube Public Reply Fallback] На коментар {comment_id}: '{text}'")
        return True, None


youtube_funnel = YouTubeFunnel()
