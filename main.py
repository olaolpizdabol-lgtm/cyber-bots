import asyncio
import logging
import sys
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


async def main():
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

    bot = Bot(token=token if token else "000000000:dummy")
    dp = Dispatcher(storage=MemoryStorage())

    # Реєструємо AlbumMiddleware для коректної обробки медіагруп (каруселей/альбомів)
    dp.message.middleware(AlbumMiddleware(latency=0.6))

    # Реєструємо хендлери
    dp.include_router(bot_router)

    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN.startswith("123456789:"):
        logger.info(
            "Бот готовий до роботи. Для запуску Telegram опитування додайте валідний токен у .env."
        )
        return

    logger.info("Запуск Telegram бота (polling) з підтримкою ВСІХ форматів контенту та TikTok вогників...")
    
    # Запускаємо фоновий планувальник вогників
    from datetime import datetime
    from core.database import get_setting
    from services.automations.automation_2 import tiktok_streak_service
    from config import ALLOWED_USER_IDS

    async def streak_scheduler_background_task():
        logger.info("Фоновий планувальник TikTok вогників активний.")
        last_dispatched_date = None
        while True:
            try:
                await asyncio.sleep(45)
                now = datetime.now()
                today_str = now.strftime("%Y-%m-%d")
                current_hm = now.strftime("%H:%M")
                sched_time = get_setting("tiktok_streak_schedule_time", "10:00")

                if current_hm == sched_time and last_dispatched_date != today_str:
                    logger.info(f"⏰ Настав час розкладу ({sched_time}): запуск щоденної відправки вогників...")
                    res = await tiktok_streak_service.run_streaks_dispatch()
                    last_dispatched_date = today_str
                    if ALLOWED_USER_IDS and res.get("sent_count", 0) > 0:
                        for uid in ALLOWED_USER_IDS:
                            try:
                                await bot.send_message(
                                    uid,
                                    f"🔥 <b>Щоденний звіт TikTok вогників!</b>\n"
                                    f"Успішно опрацьовано: {res['sent_count']} контактів.",
                                    parse_mode="HTML"
                                )
                            except Exception:
                                pass
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Помилка фонового планувальника вогників: {e}")

    scheduler_task = asyncio.create_task(streak_scheduler_background_task())

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        scheduler_task.cancel()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот зупинений.")
