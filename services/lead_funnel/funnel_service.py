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
import requests
from config import CHANNEL_AUTOMATION_BOT_TOKEN, TELEGRAM_BOT_TOKEN, ALLOWED_USER_IDS

logger = logging.getLogger("funnel_service")


def notify_telegram_lead(html_text: str):
    """Надсилає миттєве Telegram сповіщення власнику бота про нових лідів"""
    token = CHANNEL_AUTOMATION_BOT_TOKEN or TELEGRAM_BOT_TOKEN
    if not token or not ALLOWED_USER_IDS:
        return
    for uid in ALLOWED_USER_IDS:
        try:
            requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={
                    "chat_id": uid,
                    "text": html_text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True
                },
                timeout=5
            )
        except Exception:
            pass


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
DEFAULT_REPLY_PRIVATE_DM = "Tried to DM you, but your inbox is private! 📩 Check the link in my bio or message me first! ⚡"

# Варіанти відповідей для TikTok (без зовнішніх посилань, щоб не зловити тіньовий бан / спам-фільтр)
DEFAULT_REPLIES_TIKTOK_BRIDGE = [
    "Grab the 100+ Prompt Vault via the link in my IG bio @bohdan.gpt! ⚡",
    "Link to the full database is in my Instagram bio @bohdan.gpt (or drop me 'GPT' in DMs there)! 🚀",
    "All prompts & codes are linked directly in my IG bio @bohdan.gpt! 🔥",
    "Head over to my Instagram @bohdan.gpt — the vault link is right in my bio! ⚡",
    "Instant access is linked in my IG bio @bohdan.gpt! Enjoy 🚀"
]

# Варіанти відповідей для YouTube (чисті коментарі без посилань, що направляють в IG bio)
DEFAULT_REPLIES_YOUTUBE_BRIDGE = [
    "Link to the full 100+ Prompt Vault is right in my Instagram bio @bohdan.gpt! ⚡",
    "Grab the complete database via the link in my IG bio @bohdan.gpt (or DM me 'GPT' there)! 🚀",
    "All visual codes and prompt synthesizer are linked in my Instagram bio @bohdan.gpt! 🔥",
    "Check the link in my IG bio @bohdan.gpt for instant vault access! ⚡"
]

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

    def get_lead_link(self, platform: str = "instagram") -> str:
        """
        Повертає цільове посилання на Vault із динамічним параметром джерела:
        ?from=instagram / ?from=tiktok / ?from=youtube / ?from=facebook
        """
        base_link = get_setting("lead_funnel_link")
        if not base_link or "t.me/" in base_link:
            env_url = os.getenv("VAULT_BASE_URL", "").strip()
            base_link = env_url if env_url else "https://cyber-bots.up.railway.app/vault/"

        clean_base = base_link.split("?")[0].rstrip("/")
        if not clean_base.endswith("/vault"):
            clean_base += "/vault/"
        else:
            clean_base += "/"

        platform_clean = (platform or "instagram").lower().strip()
        return f"{clean_base}?from={platform_clean}"

    def get_formatted_dm_text(self, platform: str = "instagram") -> str:
        tpl = self.get_dm_template()
        link = self.get_lead_link(platform=platform)
        return tpl.format(link=link)

    def process_platform_comments(self, platform_name: str, limit_posts: Optional[int] = 5, max_replies_batch: int = 25) -> Dict[str, int]:
        """
        Перевіряє та обробляє всі свіжі або всі історичні коментарі для обраної платформи.
        limit_posts=None означає глибокий скан УСІХ доступних відео.
        max_replies_batch обмежує кількість активних відповідей за 1 раз для захисту від блокувань Meta.
        """
        handler = self.platforms.get(platform_name)
        if not handler:
            return {"processed": 0, "leads": 0}

        stats = {"processed": 0, "leads": 0, "dms_sent": 0, "pending_follow": 0}
        comments = handler.fetch_recent_unanswered_comments(limit_posts=limit_posts)
        logger.info(f"[{platform_name.upper()}] Отримано {len(comments)} коментарів для перевірки (limit_posts={limit_posts})")

        triggers = get_lead_funnel_triggers(only_active=True)

        for comm in comments:
            # 1. Захист від перевищення годинного ліміту платформи (Meta anti-ban)
            if stats["leads"] >= max_replies_batch:
                logger.info(
                    f"[{platform_name.upper()}] 🛡 Досягнуто безпечний ліміт пачки ({max_replies_batch} відповідей). "
                    f"Залишок коментарів буде опрацьовано у наступних циклах для уникнення блокувань."
                )
                break

            # 2. Перевіряємо, чи цей коментар уже є в базі
            existing = get_lead_comment(platform_name, comm.comment_id)
            if existing:
                continue

            # 3. Якщо автор ВЖЕ відповів (перевірено через DOM сторінки/відео)
            if comm.has_author_replied:
                save_lead_comment(
                    platform=platform_name,
                    comment_id=comm.comment_id,
                    post_id=comm.post_id,
                    post_url=comm.post_url,
                    user_id=comm.user_id,
                    username=comm.username,
                    comment_text=comm.text,
                    detected_intent="already_replied",
                    matched_trigger=None,
                    is_following=False,
                    status="already_replied_manual",
                    dm_sent=False
                )
                continue

            stats["processed"] += 1
            # 4. Розпізнавання наміру
            intent_res = detect_comment_intent(comm.text, custom_triggers=triggers)
            logger.info(f"[{platform_name}] Comment from {comm.username}: '{comm.text[:40]}' -> Intent: {intent_res.intent}")

            if intent_res.is_lead_magnet():
                stats["leads"] += 1
                # 2. Перевірка підписки
                is_following = handler.is_user_following(comm.user_id, comm.username)

                if platform_name in ("tiktok", "youtube"):
                    # Для TikTok / YouTube: відповідаємо коментарем без посилань (направляємо в Instagram @bohdan.gpt bio)
                    if platform_name == "tiktok":
                        reply_txt = random.choice(DEFAULT_REPLIES_TIKTOK_BRIDGE)
                    else:
                        reply_txt = random.choice(DEFAULT_REPLIES_YOUTUBE_BRIDGE)

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
                    dm_text = self.get_formatted_dm_text(platform=platform_name)
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
                        notify_telegram_lead(
                            f"⚡️ <b>Lead Magnet DM Delivered!</b>\n"
                            f"• Платформа: <b>{platform_name.upper()}</b>\n"
                            f"• Користувач: <code>@{comm.username}</code> (Підписаний ✅)\n"
                            f"• Коментар: <i>\"{comm.text[:70]}\"</i>\n"
                            f"• Тригер: <code>{intent_res.matched_trigger}</code>\n"
                            f"🚀 Надіслано 100+ Prompt Vault у Direct!"
                        )
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
                        notify_telegram_lead(
                            f"⚠️ <b>Закритий Direct у користувача:</b>\n"
                            f"• Платформа: <b>{platform_name.upper()}</b>\n"
                            f"• Користувач: <code>@{comm.username}</code>\n"
                            f"💬 Бот відповів у коментарі з проханням відкрити чат."
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

                # Анти-бан пауза між активними діями/відповідями (8-16 секунд)
                time.sleep(random.uniform(8.0, 16.0))

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
                time.sleep(random.uniform(8.0, 16.0))

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
                dm_text = self.get_formatted_dm_text(platform=platform)
                ok, err = handler.send_direct_message(u_id, u_name, dm_text, comment_id=lead["comment_id"])
                if ok:
                    update_lead_status(lead["id"], status="converted", is_following=True, dm_sent=True)
                    converted += 1
                    notify_telegram_lead(
                        f"🎉 <b>New Follower Converted!</b>\n"
                        f"• Платформа: <b>{platform.upper()}</b>\n"
                        f"• Користувач: <code>@{u_name}</code>\n"
                        f"• Щойно підписався на профіль після нагадування! 🚀\n"
                        f"⚡️ 100+ Prompt Vault автоматично відправлено в Direct!"
                    )
                elif err == "private_dm":
                    update_lead_status(lead["id"], status="dm_failed_private", is_following=True)
            else:
                # Ще не підписався, оновлюємо лічильник перевірок
                update_lead_status(lead["id"], status="pending_follow", is_following=False)

            time.sleep(random.uniform(2.0, 5.0))

        return converted


lead_funnel_service = LeadFunnelService()
