"""
🎯 Lead Magnet Funnel Orchestrator
Cross-platform Comment-to-DM Engine with AI Detection & Follower Conversion
"""
import os
import re
import html
import threading
import random
import time
import logging
from typing import Dict, Any, List, Optional

from core.database import (
    get_setting,
    get_lead_funnel_triggers,
    get_lead_comment,
    save_lead_comment,
    get_pending_follow_leads,
    update_lead_status,
    has_user_received_lead
)
from services.lead_funnel.intent_detector import detect_comment_intent, CommentIntentResult
from services.lead_funnel.platforms.instagram import instagram_funnel
from services.lead_funnel.platforms.facebook import facebook_funnel
from services.lead_funnel.platforms.tiktok import tiktok_funnel
from services.lead_funnel.platforms.youtube import youtube_funnel
import requests
from config import (
    CHANNEL_AUTOMATION_BOT_TOKEN,
    TELEGRAM_BOT_TOKEN,
    CYBER_RIZHYI_BOT_TOKEN,
    ALLOWED_USER_IDS
)

logger = logging.getLogger("funnel_service")

import json
from pathlib import Path


def notify_telegram_lead(html_text: str, photo_paths: Optional[List[str]] = None):
    """Надсилає Telegram сповіщення власнику бота разом зі скріншотами коментаря та перевірки підписки"""
    candidate_tokens = []
    for tok in [CHANNEL_AUTOMATION_BOT_TOKEN, TELEGRAM_BOT_TOKEN, CYBER_RIZHYI_BOT_TOKEN]:
        if tok and not tok.startswith("123456789:") and tok not in candidate_tokens:
            candidate_tokens.append(tok)

    if not candidate_tokens:
        logger.warning("⚠️ Не налаштовано жодного валідного Telegram токена для сповіщень!")
        return

    target_uids = [uid for uid in ALLOWED_USER_IDS if uid] or [1929970467]
    valid_photos = [p for p in (photo_paths or []) if p and Path(p).exists()]

    for uid in target_uids:
        delivered = False
        for token in candidate_tokens:
            if delivered:
                break

            # 1. Спроба відправити фото
            if valid_photos:
                try:
                    if len(valid_photos) == 1:
                        caption = html_text[:1020]
                        with open(valid_photos[0], "rb") as f:
                            r = requests.post(
                                f"https://api.telegram.org/bot{token}/sendPhoto",
                                data={"chat_id": uid, "caption": caption, "parse_mode": "HTML"},
                                files={"photo": f},
                                timeout=12
                            )
                            if r.status_code == 200:
                                delivered = True
                                logger.info(f"✅ [Telegram Lead Notify] Фото-звіт доставлено до {uid} через налаштований бот")
                                break
                            else:
                                logger.debug("sendPhoto HTTP %s", r.status_code)
                    else:
                        files = {}
                        media = []
                        for idx, p_path in enumerate(valid_photos[:5]):
                            files[f"photo{idx}"] = open(p_path, "rb")
                            m_item = {"type": "photo", "media": f"attach://photo{idx}"}
                            if idx == 0:
                                m_item["caption"] = html_text[:1020]
                                m_item["parse_mode"] = "HTML"
                            media.append(m_item)
                        try:
                            r = requests.post(
                                f"https://api.telegram.org/bot{token}/sendMediaGroup",
                                data={"chat_id": uid, "media": json.dumps(media)},
                                files=files,
                                timeout=15
                            )
                            if r.status_code == 200:
                                delivered = True
                                logger.info(f"✅ [Telegram Lead Notify] Медіагрупу доставлено до {uid} через налаштований бот")
                                break
                            else:
                                logger.debug("sendMediaGroup HTTP %s", r.status_code)
                        finally:
                            for f in files.values():
                                f.close()
                except Exception as photo_err:
                    logger.debug("Telegram photo failed: %s", type(photo_err).__name__)

            # 2. Спроба текстового повідомлення (HTML)
            if not delivered:
                try:
                    r = requests.post(
                        f"https://api.telegram.org/bot{token}/sendMessage",
                        json={
                            "chat_id": uid,
                            "text": html_text,
                            "parse_mode": "HTML",
                            "disable_web_page_preview": True
                        },
                        timeout=8
                    )
                    if r.status_code == 200:
                        delivered = True
                        logger.info(f"✅ [Telegram Lead Notify] Повідомлення доставлено до {uid} через налаштований бот")
                        break
                    else:
                        logger.debug("sendMessage HTTP %s", r.status_code)
                        # Фолбек на чистий текст (якщо в html_text був невалідний тег)
                        clean_plain = re.sub(r"<[^>]+>", "", html_text)
                        r2 = requests.post(
                            f"https://api.telegram.org/bot{token}/sendMessage",
                            json={
                                "chat_id": uid,
                                "text": clean_plain,
                                "disable_web_page_preview": True
                            },
                            timeout=8
                        )
                        if r2.status_code == 200:
                            delivered = True
                            logger.info(f"✅ [Telegram Lead Notify] Plain-text повідомлення доставлено до {uid}")
                            break
                except Exception as e:
                    logger.debug("Telegram message failed: %s", type(e).__name__)

        if not delivered:
            logger.warning(f"⚠️ [Telegram Lead Notify] Не вдалося доставити сповіщення користувачу {uid} через жоден бот.")


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
    "Please follow @bohdan.gpt first. I haven't sent the vault yet; I'll send it after your follow is verified."
]
DEFAULT_REPLY_UNVERIFIED = "I couldn't verify your follow yet. I haven't sent the vault. I'll check again and send it once confirmed."

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
        self._platform_locks = {name: threading.Lock() for name in ("instagram", "facebook", "tiktok", "youtube")}
        self.last_scan = {}
        self.last_scan_at = {}
        self.last_error = {}
        self.active_scans = set()
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
            base_link = env_url if env_url else "https://bohdan-gpt.vercel.app/vault/"

        clean_base = base_link.split("?")[0].rstrip("/")
        if not clean_base.endswith("/vault"):
            clean_base += "/vault/"
        else:
            clean_base += "/"

        platform_clean = (platform or "instagram").lower().strip()
        return f"{clean_base}?from={platform_clean}"

    def get_facebook_reply(self):
        return "Here is the full 100+ AI Prompt Vault: " + self.get_lead_link("facebook") + " — enjoy! ⚡"

    def get_formatted_dm_text(self, platform: str = "instagram") -> str:
        tpl = self.get_dm_template()
        link = self.get_lead_link(platform=platform)
        return tpl.replace("{link}", link)

    def process_platform_comments(self, platform_name: str, limit_posts: Optional[int] = 5, max_replies_batch: int = 25) -> Dict[str, int]:
        stats = {"processed": 0, "leads": 0, "dms_sent": 0, "pending_follow": 0, "replies": 0, "errors": 0}
        handler = self.platforms.get(platform_name)
        if not handler:
            return stats
        lock = self._platform_locks[platform_name]
        if not lock.acquire(blocking=False):
            return dict(stats, busy=1)
        self.last_error.pop(platform_name, None)
        self.active_scans.add(platform_name)
        try:
            comments = handler.fetch_recent_unanswered_comments(limit_posts=limit_posts)
            triggers = get_lead_funnel_triggers(only_active=True)
            for comm in comments:
                if stats["processed"] >= max_replies_batch:
                    break
                try:
                    self._process_comment(platform_name, handler, comm, triggers, stats)
                except Exception as exc:
                    stats["errors"] += 1
                    logger.warning("[%s] Comment processing failed: %s", platform_name, type(exc).__name__)
            return stats
        except Exception as exc:
            stats["errors"] += 1
            self.last_error[platform_name] = type(exc).__name__
            logger.warning("[%s] Scan failed: %s", platform_name, type(exc).__name__)
            return stats
        finally:
            self.last_scan[platform_name] = dict(stats)
            self.last_scan_at[platform_name] = time.time()
            self.active_scans.discard(platform_name)
            lock.release()

    def _process_comment(self, platform, handler, comm, triggers, stats):
        existing = get_lead_comment(platform, comm.comment_id)
        retry_statuses = ("reply_failed", "sent_dm_reply_pending")
        if platform == "facebook":
            retry_statuses += ("pending_follow", "pending_verification", "dm_failed", "dm_failed_private")
        if existing and existing["status"] not in retry_statuses:
            return
        if comm.has_author_replied:
            return
        intent = (CommentIntentResult("lead_magnet") if platform == "facebook"
                  else detect_comment_intent(comm.text, custom_triggers=triggers))
        if intent.intent == "spam":
            return
        stats["processed"] += 1
        following = False
        dm_sent = bool(existing and existing.get("dm_delivery_verified") and existing.get("dm_sent_at"))
        proof = None

        def save(status):
            save_lead_comment(
                platform=platform, comment_id=comm.comment_id, post_id=comm.post_id,
                post_url=comm.post_url, user_id=comm.user_id, username=comm.username,
                comment_text=comm.text, detected_intent=intent.intent,
                matched_trigger=intent.matched_trigger, is_following=following,
                status=status, dm_sent=dm_sent,
            )

        if platform == "facebook":
            reply = self.get_facebook_reply()
            status = "replied_public_only"
        elif intent.is_lead_magnet():
            stats["leads"] += 1
            if platform in ("tiktok", "youtube"):
                reply = random.choice(DEFAULT_REPLIES_TIKTOK_BRIDGE if platform == "tiktok" else DEFAULT_REPLIES_YOUTUBE_BRIDGE)
                status = "replied_public_only"
            elif dm_sent or has_user_received_lead(platform, comm.username):
                following = True
                reply = "The vault is already in our DM conversation. Check your inbox and message requests! ⚡"
                status = "sent_dm" if dm_sent else "already_sent_earlier"
            else:
                if comm.is_following is None:
                    following, proof = handler.check_follower_status(comm.user_id, comm.username)
                else:
                    following = comm.is_following
                if following is True:
                    dm_sent, error = handler.send_direct_message(
                        comm.user_id, comm.username, self.get_formatted_dm_text(platform), comment_id=comm.comment_id)
                    if dm_sent:
                        # Persist delivery before the separate public reply to avoid duplicate DMs.
                        save("sent_dm_reply_pending")
                        stats["dms_sent"] += 1
                        reply = random.choice(DEFAULT_REPLIES_FOLLOWER)
                        status = "sent_dm"
                    else:
                        reply = "I couldn't confirm the DM was sent. Please message me directly so I can help."
                        status = "delivery_unknown" if error == "delivery_unknown" else "dm_failed"
                else:
                    reply = DEFAULT_REPLIES_NON_FOLLOWER[0] if following is False else DEFAULT_REPLY_UNVERIFIED
                    status = "pending_follow" if following is False else "pending_verification"
        elif intent.ai_reply_text:
            reply = intent.ai_reply_text
            status = "replied_public_only"
        else:
            return

        try:
            ok, error = handler.reply_to_comment(comm.comment_id, reply, post_id=comm.post_id)
        except Exception:
            save("sent_dm_reply_pending" if dm_sent else "reply_failed")
            raise
        if not ok:
            save("reply_delivery_unknown" if error == "delivery_unknown" else "sent_dm_reply_pending" if dm_sent else "reply_failed")
            stats["errors"] += 1
            logger.warning("[%s] Reply was not confirmed; retained for retry", platform)
            return
        save(status)
        stats["replies"] += 1
        if status in ("pending_follow", "pending_verification"):
            stats["pending_follow"] += 1
        time.sleep(1.0 if platform == "facebook" else random.uniform(2.0, 4.0))

    def process_instagram_messages(self):
        return self.process_direct_messages("instagram")

    def process_direct_messages(self, platform_name):
        stats = {"processed": 0, "dms_sent": 0, "replies": 0, "pending_follow": 0, "errors": 0}
        lock = self._platform_locks[platform_name]
        if not lock.acquire(blocking=False):
            return dict(stats, busy=1)
        key = platform_name + "_dm"
        self.last_error.pop(key, None)
        self.active_scans.add(key)
        try:
            handler = self.platforms[platform_name]
            for message in handler.fetch_direct_messages():
                if stats["processed"] >= 25:
                    break
                message_key = "dm_" + message.comment_id
                if get_lead_comment(platform_name, message_key):
                    continue
                try:
                    intent = CommentIntentResult("lead_magnet") if platform_name == "facebook" else detect_comment_intent(message.text)
                    if intent.intent == "spam":
                        continue
                    stats["processed"] += 1
                    following = None
                    if platform_name == "facebook":
                        text = self.get_facebook_reply()
                        status = "sent_dm"
                    else:
                        following, _ = handler.check_follower_status(message.user_id, message.username)
                        if following is True:
                            text = self.get_formatted_dm_text(platform_name)
                            status = "sent_dm"
                        else:
                            text = DEFAULT_REPLIES_NON_FOLLOWER[0] if following is False else DEFAULT_REPLY_UNVERIFIED
                            status = "pending_follow" if following is False else "pending_verification"
                    ok, error = handler.reply_to_direct_message(message, text)
                    if not ok:
                        stats["errors"] += 1
                        self.last_error[key] = error or "delivery_failed"
                        if error != "delivery_unknown":
                            continue
                        status = "delivery_unknown"
                    delivered = ok and (platform_name == "facebook" or following is True)
                    save_lead_comment(
                        platform=platform_name, comment_id=message_key, post_id=message.post_id,
                        user_id=message.user_id, username=message.username, comment_text=message.text,
                        detected_intent=intent.intent, matched_trigger=intent.matched_trigger,
                        is_following=following, status=status, dm_sent=delivered)
                    stats["replies"] += int(ok)
                    stats["dms_sent"] += int(delivered)
                    stats["pending_follow"] += int(status in ("pending_follow", "pending_verification"))
                    time.sleep(random.uniform(2.0, 5.0))
                except Exception as exc:
                    stats["errors"] += 1
                    self.last_error[key] = type(exc).__name__
            return stats
        except Exception as exc:
            stats["errors"] += 1
            self.last_error[key] = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
            return stats
        finally:
            self.last_scan[key] = dict(stats)
            self.last_scan_at[key] = time.time()
            self.active_scans.discard(key)
            lock.release()

    def recheck_pending_leads(self, platform_name=None) -> int:
        converted = 0
        for platform in ([platform_name] if platform_name else list(self.platforms)):
            lock = self._platform_locks[platform]
            if not lock.acquire(blocking=False):
                continue
            try:
                converted += self._recheck_pending_leads(platform)
            finally:
                lock.release()
        return converted

    def _recheck_pending_leads(self, platform_name) -> int:
        if platform_name == "facebook":
            return 0
        pending = get_pending_follow_leads(platform=platform_name, limit=25)
        converted = 0
        logger.info(f"Перевірка підписок для {len(pending)} очікуючих лідів...")

        for lead in pending:
            try:
                platform = lead["platform"]
                handler = self.platforms.get(platform)
                if not handler:
                    continue

                u_id = lead["user_id"]
                u_name = lead["username"]

                if has_user_received_lead(platform, u_name):
                    update_lead_status(lead["id"], status="already_converted")
                    continue

                following = handler.is_user_following(u_id, u_name)
                if following is True:
                    # Користувач підписався! 🎉
                    logger.info(f"🎉 Користувач @{u_name} ({platform}) щойно підписався! Надсилаємо DM...")
                    dm_text = self.get_formatted_dm_text(platform=platform)
                    if lead["comment_id"].startswith("dm_"):
                        from services.lead_funnel.platforms.base import PlatformComment
                        message = PlatformComment(lead["comment_id"][3:], lead["post_id"], None, u_id, u_name, lead["comment_text"])
                        ok, err = handler.reply_to_direct_message(message, dm_text)
                    else:
                        ok, err = handler.send_direct_message(u_id, u_name, dm_text, comment_id=lead["comment_id"])
                    if ok:
                        update_lead_status(lead["id"], status="converted", is_following=True, dm_sent=True)
                        converted += 1
                        notify_telegram_lead(
                            f"🎉 <b>New Follower Converted!</b>\n"
                            f"• Платформа: <b>{platform.upper()}</b>\n"
                            f"• Користувач: <code>@{html.escape(u_name)}</code>\n"
                            f"• Щойно підписався на профіль після нагадування! 🚀\n"
                            f"• 📩 <b>Надіслано в Direct:</b>\n<code>{html.escape(dm_text)}</code>"
                        )
                    else:
                        update_lead_status(lead["id"], status="delivery_unknown" if err == "delivery_unknown" else "dm_failed", is_following=True)
                else:
                    # Ще не підписався, оновлюємо лічильник перевірок
                    update_lead_status(lead["id"], status="pending_follow" if following is False else "pending_verification", is_following=following)

                time.sleep(random.uniform(2.0, 5.0))
            except Exception as exc:
                logger.warning("Pending lead check failed: %s", type(exc).__name__)
                update_lead_status(lead["id"], status=lead["status"])

        return converted


lead_funnel_service = LeadFunnelService()
