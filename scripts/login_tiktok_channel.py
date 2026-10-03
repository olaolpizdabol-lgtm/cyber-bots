"""
🔑 Авторизація TikTok для КАНАЛЬНОГО акаунту (постинг відео/контенту)
Зберігає сесію у data/tiktok_channel_state.json — окремо від стріків!

Запуск:
    .venv/bin/python scripts/login_tiktok_channel.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.sync_api import sync_playwright
from config import DATA_DIR
from services.proxy_manager import proxy_manager

STATE_FILE = DATA_DIR / "tiktok_channel_state.json"


def login_once():
    proxy_cfg = proxy_manager.get_playwright_proxy()
    print("🚀 Запуск браузера для авторизації TikTok КАНАЛЬНОГО акаунту...")
    print("📌 Це ОКРЕМИЙ акаунт від стріків — для постингу відео!")
    if proxy_cfg:
        print(f"🌐 Проксі: {proxy_cfg.get('server')}")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            proxy=proxy_cfg,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled"
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="uk-UA"
        )
        page = context.new_page()
        page.goto("https://www.tiktok.com/login", timeout=30000)

        print("\n" + "="*50)
        print("✋ ДІЙ ЗАРАЗ:")
        print("   1. Увійди в КАНАЛЬНИЙ TikTok акаунт (не той що для стріків!)")
        print("   2. Після входу зачекай 3 секунди")
        print("   3. Скрипт автоматично збереже сесію")
        print("="*50 + "\n")

        # Чекаємо поки з'явиться головна сторінка (ознака успішного входу)
        print("⏳ Очікуємо входу в акаунт...")
        try:
            page.wait_for_url("https://www.tiktok.com/foryou*", timeout=180000)
        except Exception:
            try:
                page.wait_for_url("https://www.tiktok.com/*", timeout=60000)
            except Exception:
                pass

        time.sleep(3)

        # Зберігаємо повний storage_state
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        context.storage_state(path=str(STATE_FILE))
        print(f"\n✅ Сесія канального акаунту збережена: {STATE_FILE}")
        print("🎉 Тепер бот може постити відео у TikTok автономно!")

        browser.close()


if __name__ == "__main__":
    login_once()
