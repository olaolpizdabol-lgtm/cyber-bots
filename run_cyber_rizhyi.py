#!/usr/bin/env python3
"""
🤖 Запуск бота «Кібер Рижий» (Cyber Rizhyi Bot Runner)

Використання:
    .venv/bin/python run_cyber_rizhyi.py

Налаштування в .env:
    CYBER_RIZHYI_BOT_TOKEN=...
    GROQ_API_KEY=...
    GEMINI_API_KEY=...
"""
import asyncio
from scripts.run_cyber_rizhyi import main

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
