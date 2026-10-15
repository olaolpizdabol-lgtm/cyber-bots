import os
import sys
import json
import html
import asyncio
import logging
from pathlib import Path
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import (
    CHANNEL_AUTOMATION_BOT_TOKEN,
    TELEGRAM_BOT_TOKEN,
    CYBER_RIZHYI_BOT_TOKEN
)
from bot.handlers import router as bot_router
from bot.album_middleware import AlbumMiddleware
from core.database import init_db

# Налаштування логування
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] channel_bot: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


from aiogram import BaseMiddleware
from aiogram.types import Update


class UpdateLoggingMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: Update, data):
        if event.message:
            m = event.message
            u_id = m.from_user.id if m.from_user else "unknown"
            u_name = m.from_user.username if m.from_user else ""
            c_type = m.content_type
            txt = (m.text or m.caption or "")[:80]
            logger.info(f"📩 Вхідне Message від {u_id} (@{u_name}): {c_type}, txt={txt!r}, video={bool(m.video)}, photo={bool(m.photo)}, doc={bool(m.document)}")
        elif event.callback_query:
            cq = event.callback_query
            u_id = cq.from_user.id if cq.from_user else "unknown"
            logger.info(f"🔘 Вхідний Callback від {u_id}: data={cq.data!r}")
        return await handler(event, data)


async def main():
    from core.railway_sync import restore_sessions_from_env
    restore_sessions_from_env()

    logger.info("Ініціалізація бази даних та модулів для Бота Канал Автоматизація...")
    init_db()

    # Скидаємо пости, що застрягли у 'publishing' після аварійного перезапуску
    try:
        from core.database import reset_stuck_publishing_posts
        reset_stuck_publishing_posts()
    except Exception as rs_err:
        logger.warning(f"Не вдалося скинути stuck-пости: {rs_err}")

    # Прибирання старих тимчасових файлів (downloads/temp/скріншоти)
    try:
        from core.mem_guard import cleanup_temp_dirs
        cleanup_temp_dirs()
    except Exception as cl_err:
        logger.warning(f"Не вдалося прибрати тимчасові файли: {cl_err}")

    token = CHANNEL_AUTOMATION_BOT_TOKEN or TELEGRAM_BOT_TOKEN
    if not token or token.startswith("123456789:"):
        logger.warning(
            "⚠️ CHANNEL_AUTOMATION_BOT_TOKEN (або TELEGRAM_BOT_TOKEN) не задано або містить приклад з .env! "
            "Вкажіть токен у файлі .env, отриманий від @BotFather."
        )

    if CYBER_RIZHYI_BOT_TOKEN and not CYBER_RIZHYI_BOT_TOKEN.startswith("987654321:"):
        logger.info(
            "💡 Виявлено налаштований CYBER_RIZHYI_BOT_TOKEN! "
            "Ви можете запустити бота «Кібер Рижий» окремо через 'python run_cyber_rizhyi.py' "
            "або обидва боти разом через 'python run_all_bots.py'."
        )

    # Надійне офіційне підключення до Telegram Cloud API (100% доставка повідомлень)
    bot = Bot(token=token if token else "000000000:dummy")
    dp = Dispatcher(storage=MemoryStorage())

    # Логуємо всі вхідні оновлення для прозорої діагностики
    dp.update.outer_middleware(UpdateLoggingMiddleware())

    # Реєструємо AlbumMiddleware для коректної обробки медіагруп (каруселей/альбомів)
    dp.message.middleware(AlbumMiddleware(latency=0.6))

    # Реєструємо хендлери
    dp.include_router(bot_router)

    if not token or token.startswith("123456789:"):
        logger.info(
            "Бот готовий до роботи. Для запуску Telegram опитування додайте валідний токен у .env."
        )
        return

    # Запускаємо Web Uploader та PROMPT VAULT сервер
    web_port = int(os.getenv("PORT", 0) or os.getenv("WEB_PORT", 8080))
    if web_port > 0:
        try:
            import aiohttp.web
            from core.web_uploader import create_web_uploader_app
            uploader_app = create_web_uploader_app(bot=bot)
            runner = aiohttp.web.AppRunner(uploader_app)
            await runner.setup()
            site = aiohttp.web.TCPSite(runner, "0.0.0.0", web_port)
            await site.start()
            logger.info(f"🌐 Web App Uploader успішно запущено на порті {web_port}")
        except Exception as we:
            logger.warning(f"Не вдалося запустити Web Uploader: {we}")

    logger.info("Запуск Telegram бота (polling) та авто-відповідей (Lead Funnel)...")


    async def lead_funnel_background_task():
        from services.lead_funnel import lead_funnel_service
        async def platform_worker(platform, cycle=1):
            try:
                if platform in ("instagram", "tiktok"):
                    await asyncio.to_thread(lead_funnel_service.process_direct_messages, platform)
                await asyncio.to_thread(
                    lead_funnel_service.process_platform_comments,
                    platform,
                    None if cycle % 12 == 0 else 6
                )
                await asyncio.to_thread(lead_funnel_service.recheck_pending_leads, platform)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Lead worker %s failed: %s", platform, type(exc).__name__)

        logger.info("Lead funnel background monitor active (sequential mode)")
        try:
            await asyncio.sleep(10)
            cycle = 0
            while True:
                cycle += 1
                for platform in ("facebook", "instagram", "tiktok", "youtube"):
                    await platform_worker(platform, cycle)
                    await asyncio.sleep(3)
                await asyncio.sleep(120)
        except asyncio.CancelledError:
            logger.info("Lead funnel background monitor stopped.")

    async def lead_report_background_task():
        from services.lead_funnel import lead_funnel_service
        first_report = True
        logger.info("Lead reporter started: interval=600s recipients=%d", len(ALLOWED_USER_IDS))
        while True:
            try:
                import time
                rows = ["✅ <b>Бот запущений. Моніторинг активний.</b>" if first_report else "📊 <b>Звіт бота за останнім скануванням</b>"]
                for platform in ("instagram", "instagram_dm", "facebook", "tiktok", "tiktok_dm", "youtube"):
                    stats = lead_funnel_service.last_scan.get(platform)
                    if stats is None:
                        rows.append(f"• {platform}: сканування ще не завершене")
                    else:
                        rows.append(
                            f"• {platform}: перевірено {stats.get('checked', stats.get('processed', 0))}, "
                            f"нових {stats.get('processed', 0)}, "
                            f"відповідей {stats.get('replies', 0)}, DM {stats.get('dms_sent', 0)}, "
                            f"помилок {stats.get('errors', 0)} "
                            f"(оновлено {int((time.time() - lead_funnel_service.last_scan_at.get(platform, time.time())) / 60)} хв тому)")
                    if platform in lead_funnel_service.last_error:
                        rows.append(f"  Причина: {html.escape(lead_funnel_service.last_error[platform])}")
                if lead_funnel_service.active_scans:
                    rows.append("Зараз виконується: " + ", ".join(sorted(lead_funnel_service.active_scans.copy())))
                from core.database import get_lead_funnel_stats
                delivery_stats = await asyncio.to_thread(get_lead_funnel_stats)
                rows.append(f"Непідтверджені надсилання, потрібна перевірка: {delivery_stats['unconfirmed_delivery']}")
                rows.append("Наступний звіт через 10 хвилин. Непідтверджені надсилання не повторюються автоматично.")
            except Exception as exc:
                logger.warning("Lead report build failed: %s", type(exc).__name__)
                rows = ["⚠️ Бот працює, але статистику зібрати не вдалося. Наступна спроба через 10 хвилин."]
            for recipient_index, uid in enumerate(ALLOWED_USER_IDS):
                try:
                    sent = await bot.send_message(uid, "\n".join(rows), parse_mode="HTML")
                    logger.info("Lead report sent: recipient_index=%d message_id=%s", recipient_index, sent.message_id)
                except Exception as exc:
                    logger.warning("Lead report delivery failed: recipient_index=%d error=%s", recipient_index, type(exc).__name__)
            first_report = False
            await asyncio.sleep(600)

    funnel_task = asyncio.create_task(lead_funnel_background_task())
    report_task = asyncio.create_task(lead_report_background_task())

    try:
        await bot.delete_webhook(drop_pending_updates=False)
        await dp.start_polling(bot)
    finally:
        funnel_task.cancel()
        report_task.cancel()
        await asyncio.gather(funnel_task, report_task, return_exceptions=True)
        if "runner" in locals():
            await runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот зупинений.")
