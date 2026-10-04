#!/usr/bin/env python3
"""
🚀 Одночасний запуск обох ботів:
1. «Канал Автоматизація» (Channel Automation Bot)
2. «Кібер Рижий» (Cyber Rizhyi Bot)

Використання:
    .venv/bin/python run_all_bots.py
"""
import asyncio
import logging
import sys

from config import (
    CHANNEL_AUTOMATION_BOT_TOKEN,
    TELEGRAM_BOT_TOKEN,
    CYBER_RIZHYI_BOT_TOKEN,
    CYBER_TURIKOV_BOT_TOKEN
)
import main as channel_main_module
import scripts.run_cyber_rizhyi as rizhyi_main_module
import scripts.run_cyber_turikov as turikov_main_module

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("multi_bot_runner")


async def run_supervised(name: str, coroutine_func):
    """Супервізор: перезапускає бота при збоях, не даючи впасти іншим ботам"""
    while True:
        try:
            logger.info(f"▶️ Запуск {name}...")
            await coroutine_func()
            logger.info(f"ℹ️ {name} завершив роботу коректно.")
            break
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"❌ Збій у {name}: {e}. Перезапуск через 5 сек...", exc_info=True)
            await asyncio.sleep(5)


async def run_both():
    from core.railway_sync import restore_sessions_from_env
    restore_sessions_from_env()

    ch_token = CHANNEL_AUTOMATION_BOT_TOKEN or TELEGRAM_BOT_TOKEN
    rz_token = CYBER_RIZHYI_BOT_TOKEN
    tk_token = CYBER_TURIKOV_BOT_TOKEN

    ch_valid = bool(ch_token and not ch_token.startswith("123456789:"))
    rz_valid = bool(rz_token and not rz_token.startswith("987654321:") and not rz_token.startswith("123456789:"))
    tk_valid = bool(tk_token and not tk_token.startswith("123456789:"))

    tasks = []

    if ch_valid:
        logger.info("✅ Запуск Бота 1: «Канал Автоматизація» (TikTok Вогники, автопостинг)...")
        tasks.append(asyncio.create_task(run_supervised("«Канал Автоматизація»", channel_main_module.main)))
    else:
        logger.warning("⚠️ Бот 1 («Канал Автоматизація»): Токен не вказано або є тестовим. Пропускаємо.")

    if rz_valid:
        logger.info("✅ Запуск Бота 2: «Кібер Рижий»...")
        tasks.append(asyncio.create_task(run_supervised("«Кібер Рижий»", rizhyi_main_module.main)))
    else:
        logger.warning("⚠️ Бот 2 («Кібер Рижий»): CYBER_RIZHYI_BOT_TOKEN не вказано або є тестовим. Пропускаємо.")

    if tk_valid:
        logger.info("✅ Запуск Бота 3: «Кібер Саня Туріков»...")
        tasks.append(asyncio.create_task(run_supervised("«Кібер Саня Туріков»", turikov_main_module.main)))
    else:
        logger.warning("⚠️ Бот 3 («Кібер Саня Туріков»): CYBER_TURIKOV_BOT_TOKEN не вказано. Пропускаємо.")

    if not tasks:
        logger.error(
            "❌ Жоден із ботів не має валідного токена у .env!\n"
            "• Вкажіть CHANNEL_AUTOMATION_BOT_TOKEN для бота каналу/вогників\n"
            "• Вкажіть CYBER_RIZHYI_BOT_TOKEN для Кібер Рижого\n"
            "• Вкажіть CYBER_TURIKOV_BOT_TOKEN для Кібер Турікова\n"
            "Після цього повторіть запуск."
        )
        return

    logger.info(f"🚀 Запущено {len(tasks)} автоматизацій паралельно.")
    await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    try:
        asyncio.run(run_both())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Усі боти зупинені.")
