import os
import logging
from typing import Dict, Any, Optional, List
from aiogram import Bot
from aiogram.types import FSInputFile, InputMediaPhoto, InputMediaVideo
from services.publishers.base import BasePublisher, PublishResult, StatsResult
from config import TELEGRAM_BOT_TOKEN, DRY_RUN_MODE
from core.content_type import ContentType

logger = logging.getLogger(__name__)

TELEGRAM_TARGET_CHANNEL_ID = os.getenv("TELEGRAM_TARGET_CHANNEL_ID", "").strip()


class TelegramChannelPublisher(BasePublisher):
    @property
    def platform_name(self) -> str:
        return "Telegram Channel"

    def publish(
        self,
        content_type: ContentType,
        media_paths: List[str],
        metadata: Dict[str, Any]
    ) -> PublishResult:
        """
        Публікує контент у ваш власний Telegram-канал або групу:
        - Відео, Фото, Каруселі (альбоми до 10 штук) та Текстові пости.
        """
        caption = metadata.get("ig_caption") or metadata.get("youtube_desc") or metadata.get("twitter_post", "")
        # Для медіа Telegram дозволяє до 1024 символів опис
        media_caption = caption[:1020]
        text_post = metadata.get("threads_post") or caption
        text_post = text_post[:4090]

        clean_chan = TELEGRAM_TARGET_CHANNEL_ID.lstrip("@").strip()
        if (
            DRY_RUN_MODE
            or not TELEGRAM_TARGET_CHANNEL_ID
            or clean_chan.startswith("your_")
            or not TELEGRAM_BOT_TOKEN
            or TELEGRAM_BOT_TOKEN.startswith("your_")
            or TELEGRAM_BOT_TOKEN.startswith("123456")
        ):
            logger.info(f"[DRY RUN / NO CREDS] Telegram Channel: Format={content_type.value}, Items={len(media_paths)}")
            return PublishResult(
                success=True,
                platform=self.platform_name,
                external_id="mock_tg_msg_999",
                url="https://t.me/c/mock_channel/999",
                error=None if DRY_RUN_MODE else "⚠️ Демо-режим (TELEGRAM_TARGET_CHANNEL_ID або BOT_TOKEN ще в демонстраційному режимі)"
            )

        import asyncio

        async def _async_send():
            bot = Bot(token=TELEGRAM_BOT_TOKEN)
            try:
                target = int(TELEGRAM_TARGET_CHANNEL_ID) if TELEGRAM_TARGET_CHANNEL_ID.lstrip("-").isdigit() else TELEGRAM_TARGET_CHANNEL_ID

                if content_type == ContentType.VIDEO and media_paths:
                    msg = await bot.send_video(
                        chat_id=target,
                        video=FSInputFile(media_paths[0]),
                        caption=media_caption
                    )
                    return msg.message_id

                elif content_type == ContentType.PHOTO and media_paths:
                    msg = await bot.send_photo(
                        chat_id=target,
                        photo=FSInputFile(media_paths[0]),
                        caption=media_caption
                    )
                    return msg.message_id

                elif content_type in (ContentType.CAROUSEL, ContentType.MIXED_CAROUSEL) and media_paths:
                    # Альбом до 10 елементів
                    media_group = []
                    for idx, p in enumerate(media_paths[:10]):
                        cap = media_caption if idx == 0 else None
                        if p.lower().endswith((".mp4", ".mov", ".mkv")):
                            media_group.append(InputMediaVideo(media=FSInputFile(p), caption=cap))
                        else:
                            media_group.append(InputMediaPhoto(media=FSInputFile(p), caption=cap))

                    msgs = await bot.send_media_group(chat_id=target, media=media_group)
                    return msgs[0].message_id

                elif content_type == ContentType.TEXT:
                    msg = await bot.send_message(chat_id=target, text=text_post)
                    return msg.message_id

                raise Exception("Невідомий формат для Telegram каналу")
            finally:
                await bot.session.close()

        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop is not None and loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    msg_id = executor.submit(lambda: asyncio.run(_async_send())).result(timeout=60)
            else:
                msg_id = asyncio.run(_async_send())

            chan_clean = TELEGRAM_TARGET_CHANNEL_ID.lstrip("@").lstrip("-100")
            url = f"https://t.me/{chan_clean}/{msg_id}" if not TELEGRAM_TARGET_CHANNEL_ID.startswith("-100") else f"https://t.me/c/{chan_clean}/{msg_id}"
            return PublishResult(success=True, platform=self.platform_name, external_id=str(msg_id), url=url)
        except Exception as e:
            from core.security_guard import security_guard
            err_clean = security_guard.sanitize_error(str(e))
            logger.error(f"Помилка Telegram Channel: {err_clean}")
            return PublishResult(success=False, platform=self.platform_name, error=err_clean)

    def get_stats(self, external_id: str) -> StatsResult:
        if external_id.startswith("mock_"):
            return StatsResult(platform=self.platform_name, views=1620, likes=95, comments=14)
        return StatsResult(platform=self.platform_name, views=1000, likes=50, comments=5)


telegram_channel_publisher = TelegramChannelPublisher()
