import os
import sys
import asyncio
import logging
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

    # Запускаємо Web Uploader для завантаження великих файлів якщо задано PORT (Railway)
    web_port = int(os.getenv("PORT", 0) or 0)
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

    logger.info("Запуск Telegram бота (polling) з підтримкою ВСІХ форматів контенту та TikTok вогників...")
    
    # Запускаємо фоновий планувальник вогників
    from datetime import datetime, timezone, timedelta
    from core.database import get_setting, set_setting
    from services.automations.automation_2 import tiktok_streak_service
    from config import ALLOWED_USER_IDS, DATA_DIR, TIKTOK_STREAK_SCHEDULE_TIME

    async def streak_scheduler_background_task():
        logger.info("Фоновий планувальник TikTok вогників та вхідних відео активний.")
        last_dispatched_date = None
        last_react_check_minute = None
        streak_file = DATA_DIR / "last_streak_dispatch_date.txt"

        while True:
            try:
                await asyncio.sleep(45)
                try:
                    from zoneinfo import ZoneInfo
                    kyiv_tz = ZoneInfo("Europe/Kyiv")
                    now_kyiv = datetime.now(kyiv_tz)
                except Exception:
                    kyiv_tz = timezone(timedelta(hours=3))
                    now_kyiv = datetime.now(kyiv_tz)

                today_str = now_kyiv.strftime("%Y-%m-%d")
                current_hm = now_kyiv.strftime("%H:%M")
                sched_time = get_setting("tiktok_streak_schedule_time") or TIKTOK_STREAK_SCHEDULE_TIME or "10:00"
                last_db_date = get_setting("last_streak_dispatch_date", "")

                last_file_date = ""
                if streak_file.exists():
                    try:
                        last_file_date = streak_file.read_text(encoding="utf-8").strip()
                    except Exception:
                        pass

                # Запускаємо якщо настав час розкладу і сьогодні ще не відправляли
                should_run = False
                if last_dispatched_date != today_str and last_db_date != today_str and last_file_date != today_str:
                    if current_hm >= sched_time and now_kyiv.hour < 23:
                        should_run = True

                if should_run:
                    logger.info(f"⏰ Настав час розкладу ({sched_time}, зараз {current_hm} Київ): запуск щоденної відправки вогників...")
                    last_dispatched_date = today_str
                    set_setting("last_streak_dispatch_date", today_str)
                    try:
                        streak_file.write_text(today_str, encoding="utf-8")
                    except Exception:
                        pass
                    res = await tiktok_streak_service.run_streaks_dispatch()
                    if ALLOWED_USER_IDS and res.get("sent_count", 0) > 0:
                        for uid in ALLOWED_USER_IDS:
                            try:
                                await bot.send_message(
                                    uid,
                                    f"🔥 <b>Щоденний звіт TikTok вогників!</b>\n"
                                    f"Час: {current_hm} (Київ)\n"
                                    f"Успішно опрацьовано: {res['sent_count']} контактів.",
                                    parse_mode="HTML"
                                )
                            except Exception:
                                pass

                # Періодична перевірка вхідних TikTok відео кожні 15 хвилин
                if now_kyiv.minute % 15 == 0 and last_react_check_minute != now_kyiv.minute:
                    last_react_check_minute = now_kyiv.minute
                    try:
                        logger.info("🔍 Фонова перевірка скинутих TikTok відео у чатах...")
                        await tiktok_streak_service.check_and_react_to_shared_videos()
                    except Exception as react_err:
                        logger.error(f"Помилка фонової перевірки TikTok відео: {react_err}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Помилка фонового планувальника вогників: {e}")

    async def post_scheduler_background_task():
        logger.info("Фоновий планувальник публікацій контенту активний (перевірка кожні 20 сек).")
        from core.database import get_due_scheduled_posts, update_post_status
        from services.automations.auto_poster import auto_poster
        from core.security_guard import security_guard
        from bot.keyboards import get_publish_result_keyboard
        import html

        icons = {
            "tiktok": "⚫️", "instagram": "🟣", "youtube": "🔴",
            "facebook": "🔵", "snapchat": "🟡", "twitter": "𝕏",
            "threads": "🧵", "pinterest": "📌", "bluesky": "🦋",
            "telegram": "💬"
        }

        while True:
            try:
                await asyncio.sleep(20)
                due_posts = get_due_scheduled_posts()
                if not due_posts:
                    continue

                for post in due_posts:
                    post_id = post["id"]
                    logger.info(f"⏰ Настав час публікації запланованого поста #{post_id}!")
                    update_post_status(post_id, "publishing")

                    target_platforms = post.get("target_platforms_list")
                    chat_id = post.get("scheduled_by_chat_id")

                    results = await asyncio.to_thread(auto_poster.publish_post, post_id, target_platforms)

                    has_failures = any(not res.success for res in results.values()) if results else False
                    report_text = f"⏰ <b>Запланований пост #{post_id} опубліковано!</b>\n\n"
                    for plat, res in results.items():
                        icon = icons.get(plat, "🌐")
                        if res.success:
                            link = f"<a href='{res.url}'>Переглянути</a>" if res.url else "Опубліковано"
                            report_text += f"{icon} <b>{res.platform}:</b> ✅ Успішно! ({link})\n"
                        else:
                            err_msg = security_guard.sanitize_error(str(res.error or "Помилка"))
                            if len(err_msg) > 160:
                                err_msg = err_msg[:157] + "..."
                            report_text += f"{icon} <b>{res.platform}:</b> ❌ <i>{html.escape(err_msg)}</i>\n"

                    recipients = [chat_id] if chat_id else ALLOWED_USER_IDS
                    for uid in recipients:
                        if not uid:
                            continue
                        try:
                            await bot.send_message(
                                uid,
                                report_text,
                                reply_markup=get_publish_result_keyboard(post_id, has_failures=has_failures),
                                parse_mode="HTML",
                                disable_web_page_preview=True
                            )
                        except Exception as send_err:
                            logger.warning(f"Не вдалося надіслати звіт публікації користувачу {uid}: {send_err}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Помилка фонового планувальника публікацій: {e}")

    post_scheduler_task = asyncio.create_task(post_scheduler_background_task())
    scheduler_task = asyncio.create_task(streak_scheduler_background_task())

    try:
        await bot.delete_webhook(drop_pending_updates=False)
        await dp.start_polling(bot)
    finally:
        scheduler_task.cancel()
        post_scheduler_task.cancel()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот зупинений.")
