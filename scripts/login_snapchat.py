"""
🔑 Авторизація Snapchat для публікації Spotlight відео через Playwright
Зберігає робочу сесію у data/snapchat_state.json та оновлює data/snapchat_b64.txt для Railway.

Запуск:
    .venv/bin/python scripts/login_snapchat.py
"""
import sys
import os
import time
import json
import base64
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.sync_api import sync_playwright
from config import DATA_DIR
from services.proxy_manager import proxy_manager

STATE_FILE = DATA_DIR / "snapchat_state.json"
B64_FILE = DATA_DIR / "snapchat_b64.txt"
SNAPCHAT_UPLOADER_URL = (
    "https://profile.snapchat.com/c2443976-9439-4927-8ae2-0bcaf23c2860/profiles/da45adf0-1cf8-489f-9836-173241bb8020/web-uploader"
)


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

        # Якщо є попередній файл сесії, спробуємо завантажити його для збереження cookies
        if STATE_FILE.exists():
            try:
                context = browser.new_context(storage_state=str(STATE_FILE), **context_kwargs)
            except Exception:
                context = browser.new_context(**context_kwargs)
        else:
            context = browser.new_context(**context_kwargs)

        page = context.new_page()

        try:
            from playwright_stealth import stealth_sync
            stealth_sync(page)
        except Exception:
            pass

        target_url = "https://my.snapchat.com"
        print(f"🔗 Відкриваємо {target_url}...")
        try:
            page.goto(target_url, timeout=45000, wait_until="domcontentloaded")
        except Exception as e:
            print(f"Попередження при завантаженні: {e}")

        print("\n" + "=" * 60)
        print("✋ ДІЇ В БРАУЗЕРІ:")
        print("   1. Увійдіть у свій акаунт Snapchat (@bohdan.gpt)")
        print("   2. Дочекайтеся появи особистого кабінету my.snapchat.com")
        print("   3. Скрипт автоматично перейде на сторінку Spotlight,")
        print("      перевірить права та збереже токен для Railway!")
        print("=" * 60 + "\n")

        print("⏳ Очікуємо завершення входу в браузері...")
        page.wait_for_timeout(3000)

        logged_in = False
        start_time = time.time()
        max_wait = 300  # 5 хвилин

        while time.time() - start_time < max_wait:
            curr_url = page.url

            # Ознака проходження логіну:
            is_login_page = (
                "/login" in curr_url or
                page.locator('input[type="password"]').count() > 0 or
                page.locator('text="Log in to Snapchat"').count() > 0
            )

            # Перевіряємо наявність майстер-сесійних cookies
            cookies = context.cookies()
            has_auth_cookie = any(
                ("auth-session" in c["name"].lower() or "xsrf_token" in c["name"].lower())
                for c in cookies
            )

            if not is_login_page and (has_auth_cookie or "my.snapchat.com" in curr_url):
                print(f"\n🎉 Вхід зафіксовано! (URL: {curr_url})")
                print("🔗 Перевіряємо доступ до веб-завантажувача Spotlight...")
                try:
                    page.goto(SNAPCHAT_UPLOADER_URL, timeout=30000, wait_until="domcontentloaded")
                    page.wait_for_timeout(4000)
                except Exception as ge:
                    print(f"Помилка відкриття uploader: {ge}")

                if "/login" not in page.url:
                    logged_in = True
                    break
                else:
                    print("⏳ Виконується SSO перехід на Profile Manager, зачекайте кілька секунд...")
                    page.wait_for_timeout(3000)
                    if "/login" not in page.url:
                        logged_in = True
                        break

            time.sleep(2)

        if logged_in:
            print(f"📍 Фінальна цільова сторінка: {page.url}")
            time.sleep(3)

            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            context.storage_state(path=str(STATE_FILE))

            # Очищаємо DBSC кукі з короткочасним TTL 30 хвилин для довготривалої роботи
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as sf:
                    state_data = json.load(sf)
                all_c = state_data.get("cookies", [])
                clean_c = [c for c in all_c if "dbsc" not in c.get("name", "").lower()]
                state_data["cookies"] = clean_c
                with open(STATE_FILE, "w", encoding="utf-8") as sf:
                    json.dump(state_data, sf, indent=2)
            except Exception:
                pass

            screenshot_path = DATA_DIR / "snapchat_logged_in_page.png"
            try:
                page.screenshot(path=str(screenshot_path))
                print(f"📸 Знімок сторінки збережено: {screenshot_path}")
            except Exception:
                pass

            # Генеруємо Base64 для Railway
            with open(STATE_FILE, "r", encoding="utf-8") as sf:
                raw_json = sf.read().strip()
            b64_val = base64.b64encode(raw_json.encode("utf-8")).decode("utf-8")

            with open(B64_FILE, "w", encoding="utf-8") as bf:
                bf.write(f"SNAPCHAT_STATE_B64={b64_val}\n")

            print("\n" + "=" * 65)
            print("🎉 УСПІХ! СЕСІЯ SNAPCHAT SPOTLIGHT ЗБЕРЕЖЕНА ТА ОНОВЛЕНА!")
            print("=" * 65)
            print(f"📁 Файл сесії: {STATE_FILE}")
            print(f"📦 Base64 збережено у: {B64_FILE}")
            print("\n📋 Скопіюйте оновлену змінну для Railway (Variables -> Raw Editor):")
            print(f"\nSNAPCHAT_STATE_B64={b64_val}\n")
            print("=" * 65 + "\n")
        else:
            print("\n❌ Час очікування вичерпано або вікно закрито без входу.")
            print("⚠️ Файл сесії data/snapchat_state.json залишено без змін, щоб не пошкодити дані.")

        browser.close()


if __name__ == "__main__":
    login_snapchat()
