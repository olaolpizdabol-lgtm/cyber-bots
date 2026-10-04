"""
🔑 Авторизація Snapchat для публікації Spotlight відео через Playwright
Зберігає сесію у data/snapchat_state.json

Запуск:
    .venv/bin/python scripts/login_snapchat.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.sync_api import sync_playwright
from config import DATA_DIR
from services.proxy_manager import proxy_manager

STATE_FILE = DATA_DIR / "snapchat_state.json"


def login_snapchat():
    proxy_cfg = proxy_manager.get_playwright_proxy()
    use_proxy = False
    if proxy_cfg:
        try:
            import requests
            req_p = proxy_manager.get_requests_proxies()
            r = requests.get("https://my.snapchat.com", proxies=req_p, timeout=5)
            if r.status_code in (200, 301, 302, 303):
                use_proxy = True
        except Exception:
            pass

    if use_proxy and proxy_cfg:
        print(f"🌐 Проксі активний: {proxy_cfg.get('server')}")
        actual_proxy = proxy_cfg
    else:
        print("🌐 Пряме підключення (швидко та надійно)")
        actual_proxy = None

    print("🚀 Запуск браузера для авторизації Snapchat...")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            proxy=actual_proxy,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage"
            ]
        )
        
        context_kwargs = {
            "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "viewport": {"width": 1280, "height": 900},
            "locale": "en-US"
        }

        context = browser.new_context(**context_kwargs)
        page = context.new_page()

        try:
            from playwright_stealth import stealth_sync
            stealth_sync(page)
        except Exception:
            pass

        target_url = "https://my.snapchat.com"
        print(f"🔗 Відкриваємо {target_url}...")
        page.goto(target_url, timeout=45000, wait_until="domcontentloaded")

        print("\n" + "=" * 55)
        print("✋ ДІЇ В БРАУЗЕРІ:")
        print("   1. Увійдіть у свій акаунт Snapchat (@bohdan.gpt)")
        print("   2. Дочекайтеся переходу (або відкриття кабінету)")
        print("   3. Скрипт автоматично зафіксує вхід і збереже сесію!")
        print("=" * 55 + "\n")

        print("⏳ Очікуємо завершення входу...")
        page.wait_for_timeout(3000)

        logged_in = False
        start_time = time.time()
        max_wait = 300  # 5 хвилин

        while time.time() - start_time < max_wait:
            curr_url = page.url

            # Ознака входу: сторінка перестала бути формою логіну
            is_login_form = (
                "/login" in curr_url or
                page.locator('input[type="password"]').count() > 0 or
                page.locator('text="Log in to Snapchat"').count() > 0
            )

            if not is_login_form:
                print(f"\n🎉 Форма логіну пройдена! Поточна адреса: {curr_url}")
                # Переконуємось, що ми на цільовій сторінці завантаження
                if "snap-posting-web" not in curr_url:
                    print("🔗 Переходимо на сторінку публікації Snapchat Profile Manager...")
                    try:
                        page.goto("https://profile.snapchat.com/snap-posting-web", timeout=20000, wait_until="domcontentloaded")
                        time.sleep(3)
                    except Exception as ge:
                        print(f"Помилка переходу: {ge}")

                # Перевіряємо ще раз, чи сесія активна на сторінці постінгу
                if "/login" not in page.url:
                    logged_in = True
                    break

            time.sleep(2)

        if logged_in:
            print(f"📍 Фінальна URL: {page.url}")
            time.sleep(5)  # Чекаємо збереження всіх сесійних кукі

            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            context.storage_state(path=str(STATE_FILE))
            print(f"✅ Сесія Snapchat успішно збережена у: {STATE_FILE}")

            screenshot_path = DATA_DIR / "snapchat_logged_in_page.png"
            page.screenshot(path=str(screenshot_path))
            print(f"📸 Знімок сторінки збережено: {screenshot_path}")
            print("🎉 Вітаємо! Snapchat Spotlight тепер повністю підключено!")
        else:
            print("\n⚠️ Час очікування вичерпано. Зберігаємо поточний стан...")
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            context.storage_state(path=str(STATE_FILE))

        browser.close()


if __name__ == "__main__":
    login_snapchat()
