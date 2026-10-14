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
                channels = service.channels().list(part="id", mine=True).execute().get("items", [])
                if not channels:
                    raise RuntimeError("YouTube channel unavailable")
                channel_id = channels[0]["id"]
                page_token = None
                while True:
                    resp = service.commentThreads().list(
                        part="snippet,replies", allThreadsRelatedToChannelId=channel_id,
                        maxResults=100, order="time", textFormat="plainText", pageToken=page_token,
                    ).execute()
                    for item in resp.get("items", []):
                        top_comment = item["snippet"]["topLevelComment"]
                        top = top_comment["snippet"]
                        author_id = top.get("authorChannelId", {}).get("value", "")
                        if author_id == channel_id:
                            continue
                        cid = top_comment["id"]
                        replies = item.get("replies", {}).get("comments", [])
                        if item["snippet"].get("totalReplyCount", 0) > len(replies):
                            reply_page = None
                            replies = []
                            while True:
                                reply_resp = service.comments().list(part="snippet", parentId=cid,
                                    maxResults=100, pageToken=reply_page).execute()
                                replies.extend(reply_resp.get("items", []))
                                reply_page = reply_resp.get("nextPageToken")
                                if not reply_page:
                                    break
                        vid = item["snippet"].get("videoId", "")
                        results.append(PlatformComment(
                            comment_id=cid, post_id=vid, post_url=f"https://www.youtube.com/watch?v={vid}",
                            user_id=author_id, username=top["authorDisplayName"], text=top.get("textOriginal", top["textDisplay"]),
                            has_author_replied=any(r["snippet"].get("authorChannelId", {}).get("value") == channel_id for r in replies)))
                    page_token = resp.get("nextPageToken")
                    if limit_posts is not None or not page_token:
                        break
            else:
                raise RuntimeError("YouTube authorization required")
        except Exception as e:
            logger.warning("YouTube comment fetch failed: %s", type(e).__name__)
            raise

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
                response = service.comments().insert(
                    part="snippet",
                    body={
                        "snippet": {
                            "parentId": comment_id,
                            "textOriginal": text
                        }
                    }
                ).execute()
                if not response.get("id"):
                    return False, "delivery_unknown"
                logger.info(f"✅ YouTube відповідь надіслана на {comment_id}: '{text}'")
                return True, None
        except Exception as e:
            logger.debug(f"YouTube reply err: {e}")

        logger.warning("YouTube reply failed; check OAuth youtube.force-ssl permission")
        return False, "youtube_reply_failed"

    def like_comment(self, comment_id: str, post_id: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """Лайкає коментар у YouTube"""
        return False, "unsupported_by_youtube_api"


youtube_funnel = YouTubeFunnel()
