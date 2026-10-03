"""
🚀 Unified Runner for Both Cyber Bots (Кібер Рижий & Кібер Саня Туріков)
Runs both bots concurrently in a single process, sharing the same SQLite database and event bridge.
Perfect for deployment to Railway, Render, Fly.io, or VPS on free tier!
"""
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.run_cyber_rizhyi import main as main_rizhyi
from scripts.run_cyber_turikov import main as main_turikov

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("cyber_all")


async def run_both():
    logger.info("Запуск обох ботів (Кібер Рижий + Кібер Туріков) в одному процесі...")
    await asyncio.gather(
        main_rizhyi(),
        main_turikov()
    )


if __name__ == "__main__":
    try:
        asyncio.run(run_both())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Обидва боти зупинені.")
