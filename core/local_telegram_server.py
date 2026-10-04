"""
🚀 Local Telegram Bot API Server Runner
Автоматично запускає офіційний локальний сервер telegram-bot-api у Docker/Railway,
що збільшує ліміт завантаження файлів у чаті з 20 МБ до 2000 МБ (2 Гігабайти)!
"""
import os
import sys
import shutil
import socket
import logging
import asyncio
import subprocess
from pathlib import Path
from typing import Optional, Tuple
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from config import DATA_DIR

logger = logging.getLogger("local_telegram_server")

SERVER_DIR = DATA_DIR / "tg_bot_api"
SERVER_DIR.mkdir(parents=True, exist_ok=True)
SERVER_PORT = 8081


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) == 0


class LocalTelegramServerManager:
    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.api_id = os.getenv("TELEGRAM_API_ID", "").strip()
        self.api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()
        self.binary_path = shutil.which("telegram-bot-api") or "/usr/local/bin/telegram-bot-api"

    def is_configured(self) -> bool:
        return bool(self.api_id and self.api_hash and self.api_id.isdigit())

    def has_binary(self) -> bool:
        p = Path(self.binary_path)
        if p.exists():
            try:
                os.chmod(self.binary_path, 0o755)
            except Exception:
                pass
            return True
        return False

    async def start_server_if_configured(self) -> Optional[AiohttpSession]:
        if not self.is_configured():
            logger.info("ℹ️ TELEGRAM_API_ID або TELEGRAM_API_HASH не налаштовано. Використовуємо стандартний Telegram Cloud API (ліміт 20 МБ).")
            return None

        if not self.has_binary():
            logger.warning(
                f"⚠️ Бінарний файл telegram-bot-api не знайдено за шляхом '{self.binary_path}'. "
                "Сервер працюватиме через стандартний API (20 МБ)."
            )
            return None

        if is_port_in_use(SERVER_PORT):
            logger.info(f"✅ Local Telegram Bot API server уже працює на порті {SERVER_PORT}!")
            return AiohttpSession(
                api=TelegramAPIServer.from_base(f"http://127.0.0.1:{SERVER_PORT}", is_local=True)
            )

        cmd = [
            self.binary_path,
            f"--api-id={self.api_id}",
            f"--api-hash={self.api_hash}",
            "--local",
            f"--http-port={SERVER_PORT}",
            f"--dir={SERVER_DIR}",
            "--max-webhook-connections=100",
            "--verbosity=1"
        ]

        logger.info(f"🚀 Запуск Local Telegram Bot API server (порт {SERVER_PORT}, ліміт 2 ГБ)...")
        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE
            )
            # Чекаємо до 4 секунд готовності порту
            for _ in range(8):
                await asyncio.sleep(0.5)
                if is_port_in_use(SERVER_PORT):
                    logger.info("🎉 Local Telegram Bot API Server успішно запущено! Ліміт файлів: 2000 МБ (2 ГБ)!")
                    return AiohttpSession(
                        api=TelegramAPIServer.from_base(f"http://127.0.0.1:{SERVER_PORT}", is_local=True)
                    )

            logger.warning("Local Telegram Bot API не відкрив порт вчасно. Використовуємо стандартний API.")
        except Exception as e:
            logger.error(f"Помилка запуску Local Telegram Bot API: {e}")

        return None


local_tg_server = LocalTelegramServerManager()
