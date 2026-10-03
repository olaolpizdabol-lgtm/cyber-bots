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
    CYBER_RIZHYI_BOT_TOKEN
)
import main as channel_main_module
import scripts.run_cyber_rizhyi as rizhyi_main_module

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("multi_bot_runner")


async def run_both():
    ch_token = CHANNEL_AUTOMATION_BOT_TOKEN or TELEGRAM_BOT_TOKEN
    rz_token = CYBER_RIZHYI_BOT_TOKEN

    ch_valid = bool(ch_token and not ch_token.startswith("123456789:"))
    rz_valid = bool(rz_token and not rz_token.startswith("987654321:") and not rz_token.startswith("123456789:"))

    tasks = []

    if ch_valid:
        logger.info("✅ Запуск Бота 1: «Канал Автоматизація»...")
        tasks.append(asyncio.create_task(channel_main_module.main()))
    else:
        logger.warning("⚠️ Бот 1 («Канал Автоматизація»): Токен не вказано або є тестовим. Пропускаємо.")

    if rz_valid:
        logger.info("✅ Запуск Бота 2: «Кібер Рижий»...")
        tasks.append(asyncio.create_task(rizhyi_main_module.main()))
    else:
        logger.warning("⚠️ Бот 2 («Кібер Рижий»): CYBER_RIZHYI_BOT_TOKEN не вказано або є тестовим. Пропускаємо.")

    if not tasks:
        logger.error(
            "❌ Жоден із ботів не має валідного токена у .env!\n"
            "• Вкажіть CHANNEL_AUTOMATION_BOT_TOKEN для бота каналу\n"
            "• Вкажіть CYBER_RIZHYI_BOT_TOKEN для Кібер Рижого\n"
            "Після цього повторіть запуск."
        )
        return

    logger.info(f"🚀 Запущено {len(tasks)} бот(ів) паралельно.")
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    try:
        asyncio.run(run_both())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Усі боти зупинені.")
