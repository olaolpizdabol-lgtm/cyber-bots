#!/usr/bin/env python3
"""
🚀 Запуск сервісу автоматичних відповідей на ліди (Lead Funnel):
1. «Канал Автоматизація (Lead Funnel)» — відповіді на коментарі та DM у соціальних мережах

Використання:
    python run_all_bots.py
"""
import asyncio
import logging
import sys

from config import (
    CHANNEL_AUTOMATION_BOT_TOKEN,
    TELEGRAM_BOT_TOKEN
)
import main as channel_main_module

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("bot_runner")


async def run_supervised(name: str, coroutine_func):
    """Супервізор: перезапускає бота при збоях"""
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
    ch_valid = bool(ch_token and not ch_token.startswith("123456789:"))

    if not ch_valid:
        logger.error(
            "❌ Не вказано валідний CHANNEL_AUTOMATION_BOT_TOKEN або TELEGRAM_BOT_TOKEN у .env!\n"
            "Вкажіть токен для бота відповідей."
        )
        return

    logger.info("✅ Запуск бота автоматичних відповідей на коментарі та DM...")
    await run_supervised("«Канал Автоматизація (Lead Funnel)»", channel_main_module.main)


if __name__ == "__main__":
    try:
        asyncio.run(run_both())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот зупинений.")

