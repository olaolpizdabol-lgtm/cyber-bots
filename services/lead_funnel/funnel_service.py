"""
🎯 Lead Magnet Funnel Orchestrator
Cross-platform Comment-to-DM Engine with AI Detection & Follower Conversion
"""
import random
import time
import asyncio
import logging
from typing import Dict, Any, List, Optional

from core.database import (
    get_setting,
    set_setting,
    get_lead_funnel_triggers,
    get_lead_comment,
    save_lead_comment,
    get_pending_follow_leads,
    update_lead_status,
    get_lead_funnel_stats
)
from services.lead_funnel.intent_detector import detect_comment_intent
from services.lead_funnel.platforms.instagram import instagram_funnel
from services.lead_funnel.platforms.facebook import facebook_funnel
from services.lead_funnel.platforms.tiktok import tiktok_funnel
from services.lead_funnel.platforms.youtube import youtube_funnel

logger = logging.getLogger("funnel_service")

# Варіанти відповідей у коментарях для підписаних користувачів (Spintax / рандомізація проти спам-фільтрів)
DEFAULT_REPLIES_FOLLOWER = [
    "Check your DM's! ⚡",
    "Sent you the full prompt vault in your DMs! 🚀",
    "Just dropped the link in your inbox! Check your DM's ⚡",
    "Check your DMs! Enjoy 10x-ing your results 🔥",
    "Sent! Let me know what you build with these ⚡"
]

# Варіанти відповідей у коментарях для НЕ підписаних (дружнє, привабливе заохочення підписатися)
DEFAULT_REPLIES_NON_FOLLOWER = [
    "Almost yours! 🎁 Hit Follow on the page, and I'll send the 100+ prompt vault straight to your DMs! ⚡",
    "One quick step! 🚀 Follow the profile and the full prompt database lands in your inbox right now ⚡",
    "Vault is ready! ⚡ Hit Follow so I can open access and send it straight to your DMs!",
    "Just follow the page and check your DMs in 2 seconds — sending it right over! 🚀"
]

# Відповідь якщо у користувача закритий Direct
DEFAULT_REPLY_PRIVATE_DM = "Tried to DM you, but your inbox is private! 📩 Send me a quick DM first so I can drop the link! ⚡"

# Шаблон повідомлення в Direct (DM)
DEFAULT_DM_TEMPLATE = (
    "Hey! 👋 Here is your instant access to the 100+ Best AI Prompts & ChatGPT Vault:\n\n"
    "{link}\n\n"
    "Bookmark it and start 10x-ing your workflow! Let me know if you need any tips. ⚡"
)

DEFAULT_LEAD_LINK = "https://t.me/bohdan_gpt"


class LeadFunnelService:
    def __init__(self):
        self.platforms = {
            "instagram": instagram_funnel,
            "facebook": facebook_funnel,
            "tiktok": tiktok_funnel,
            "youtube": youtube_funnel
        }

    def get_dm_template(self) -> str:
        tpl = get_setting("lead_funnel_dm_template")
        return tpl if tpl else DEFAULT_DM_TEMPLATE

    def get_lead_link(self) -> str:
        link = get_setting("lead_funnel_link")
        return link if link else DEFAULT_LEAD_LINK

    def get_formatted_dm_text(self) -> str:
        tpl = self.get_dm_template()
        link = self.get_lead_link()
        return tpl.format(link=link)

    def process_platform_comments(self, platform_name: str, limit_posts: int = 5) -> Dict[str, int]:
        """
        Перевіряє та обробляє всі свіжі коментарі для обраної платформи.
        """
        handler = self.platforms.get(platform_name)
        if not handler:
            return {"processed": 0, "leads": 0}

        stats = {"processed": 0, "leads": 0, "dms_sent": 0, "pending_follow": 0}
        comments = handler.fetch_recent_unanswered_comments(limit_posts=limit_posts)
        logger.info(f"[{platform_name.upper()}] Отримано {len(comments)} коментарів для перевірки")

        triggers = get_lead_funnel_triggers(only_active=True)

        for comm in comments:
            # Перевіряємо, чи цей коментар уже є в базі
            existing = get_lead_comment(platform_name, comm.comment_id)
            if existing:
                continue

            stats["processed"] += 1
            # 1. Розпізнавання наміру
            intent_res = detect_comment_intent(comm.text, custom_triggers=triggers)
            logger.info(f"[{platform_name}] Comment from {comm.username}: '{comm.text[:40]}' -> Intent: {intent_res.intent}")

            if intent_res.is_lead_magnet():
                stats["leads"] += 1
                # 2. Перевірка підписки
                is_following = handler.is_user_following(comm.user_id, comm.username)

                if platform_name in ("tiktok", "youtube"):
                    # Для TikTok / YouTube: відповідаємо коментарем-мостом
                    if platform_name == "tiktok":
                        reply_txt = f"TikTok restricts direct DMs here — drop '{intent_res.matched_trigger or 'GPT'}' on my IG @bohdan.gpt (or tap bio link) and I'll send you the 100+ prompt vault immediately! ⚡"
                    else:
                        reply_txt = f"The prompt vault link is in the channel description & bio, or DM me '{intent_res.matched_trigger or 'GPT'}' on IG @bohdan.gpt for instant access! ⚡"

                    handler.reply_to_comment(comm.comment_id, reply_txt, post_id=comm.post_id)
                    save_lead_comment(
                        platform=platform_name,
                        comment_id=comm.comment_id,
                        post_id=comm.post_id,
                        post_url=comm.post_url,
                        user_id=comm.user_id,
                        username=comm.username,
                        comment_text=comm.text,
                        detected_intent="lead_magnet",
                        matched_trigger=intent_res.matched_trigger,
                        is_following=False,
                        status="replied_public_only",
                        dm_sent=False
                    )
                    continue

                if is_following:
                    # Сценарій А: Людина підписана -> відправляємо DM + коментар
                    dm_text = self.get_formatted_dm_text()
                    dm_ok, dm_err = handler.send_direct_message(
                        user_id=comm.user_id,
                        username=comm.username,
                        text=dm_text,
                        comment_id=comm.comment_id
                    )

                    if dm_ok:
                        reply_comment = random.choice(DEFAULT_REPLIES_FOLLOWER)
                        handler.reply_to_comment(comm.comment_id, reply_comment, post_id=comm.post_id)
                        save_lead_comment(
                            platform=platform_name,
                            comment_id=comm.comment_id,
                            post_id=comm.post_id,
                            post_url=comm.post_url,
                            user_id=comm.user_id,
                            username=comm.username,
                            comment_text=comm.text,
                            detected_intent="lead_magnet",
                            matched_trigger=intent_res.matched_trigger,
                            is_following=True,
                            status="sent_dm",
                            dm_sent=True
                        )
                        stats["dms_sent"] += 1
                    elif dm_err == "private_dm":
                        # Закритий direct
                        handler.reply_to_comment(comm.comment_id, DEFAULT_REPLY_PRIVATE_DM, post_id=comm.post_id)
                        save_lead_comment(
                            platform=platform_name,
                            comment_id=comm.comment_id,
                            post_id=comm.post_id,
                            post_url=comm.post_url,
                            user_id=comm.user_id,
                            username=comm.username,
                            comment_text=comm.text,
                            detected_intent="lead_magnet",
                            matched_trigger=intent_res.matched_trigger,
                            is_following=True,
                            status="dm_failed_private",
                            dm_sent=False
                        )
                else:
                    # Сценарій Б: Людина НЕ підписана -> просимо підписатися та додаємо в чергу
                    reply_comment = random.choice(DEFAULT_REPLIES_NON_FOLLOWER)
                    handler.reply_to_comment(comm.comment_id, reply_comment, post_id=comm.post_id)
                    save_lead_comment(
                        platform=platform_name,
                        comment_id=comm.comment_id,
                        post_id=comm.post_id,
                        post_url=comm.post_url,
                        user_id=comm.user_id,
                        username=comm.username,
                        comment_text=comm.text,
                        detected_intent="lead_magnet",
                        matched_trigger=intent_res.matched_trigger,
                        is_following=False,
                        status="pending_follow",
                        dm_sent=False
                    )
                    stats["pending_follow"] += 1

            elif intent_res.intent == "question_chat" and intent_res.ai_reply_text:
                # Відповідаємо розумно згенерованим текстом
                handler.reply_to_comment(comm.comment_id, intent_res.ai_reply_text, post_id=comm.post_id)
                save_lead_comment(
                    platform=platform_name,
                    comment_id=comm.comment_id,
                    post_id=comm.post_id,
                    post_url=comm.post_url,
                    user_id=comm.user_id,
                    username=comm.username,
                    comment_text=comm.text,
                    detected_intent="question_chat",
                    matched_trigger=None,
                    is_following=False,
                    status="replied_public_only",
                    dm_sent=False
                )

            # Анти-бан пауза між відповідями (5-15 секунд)
            time.sleep(random.uniform(5.0, 15.0))

        return stats

    def recheck_pending_leads(self) -> int:
        """
        Фонова перевірка: чи підписалися користувачі після нашого прохання.
        Як тільки підписався — миттєво відправляємо лід-магніт у Direct!
        """
        pending = get_pending_follow_leads(limit=25)
        converted = 0
        logger.info(f"Перевірка підписок для {len(pending)} очікуючих лідів...")

        for lead in pending:
            platform = lead["platform"]
            handler = self.platforms.get(platform)
            if not handler:
                continue

            u_id = lead["user_id"]
            u_name = lead["username"]

            if handler.is_user_following(u_id, u_name):
                # Користувач підписався! 🎉
                logger.info(f"🎉 Користувач @{u_name} ({platform}) щойно підписався! Надсилаємо DM...")
                dm_text = self.get_formatted_dm_text()
                ok, err = handler.send_direct_message(u_id, u_name, dm_text, comment_id=lead["comment_id"])
                if ok:
                    update_lead_status(lead["id"], status="converted", is_following=True, dm_sent=True)
                    converted += 1
                elif err == "private_dm":
                    update_lead_status(lead["id"], status="dm_failed_private", is_following=True)
            else:
                # Ще не підписався, оновлюємо лічильник перевірок
                update_lead_status(lead["id"], status="pending_follow", is_following=False)

            time.sleep(random.uniform(2.0, 5.0))

        return converted


lead_funnel_service = LeadFunnelService()
