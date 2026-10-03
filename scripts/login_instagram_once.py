"""
📸 1-Клік Авторизація Instagram через реальний Браузер (на VPN або прямому з'єднанні)
Зберігає сесію у credentials/instagram_session.json та data/instagram_state.json

Запуск:
    .venv/bin/python scripts/login_instagram_once.py
"""
import sys
import time
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.sync_api import sync_playwright
from config import DATA_DIR, CREDENTIALS_DIR

INSTA_STATE_FILE = DATA_DIR / "instagram_state.json"
INSTA_SESSION_FILE = CREDENTIALS_DIR / "instagram_session.json"


def login_instagram():
    print("🚀 Запуск браузера Chrome для авторизації в Instagram...")
    print("🌐 Режим: пряме з'єднання / системний VPN (без додаткового SOCKS5 проксі)")
    
    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
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
        page.goto("https://www.instagram.com/accounts/login/", timeout=40000)

        print("\n" + "="*55)
        print("✋ ДІЙ ЗАРАЗ У ВІКНІ БРАУЗЕРА:")
        print("   1. Увійди у свій Instagram акаунт")
        print("   2. Якщо потрібно — введи код 2FA або підтверди вхід")
        print("   3. Зачекай відкриття головної сторінки Instagram")
        print("="*55 + "\n")

        print("⏳ Очікуємо успішного входу в акаунт...")
        logged_in = False
        start_time = time.time()
        
        while time.time() - start_time < 240:
            time.sleep(2)
            cookies = context.cookies()
            c_dict = {c["name"]: c["value"] for c in cookies}
            
            # Ознака авторизації в Instagram: наявність sessionid та ds_user_id
            if "sessionid" in c_dict and "ds_user_id" in c_dict:
                print("\n🎉 Авторизаційні токени Instagram успішно перехоплено!")
                logged_in = True
                break

        if not logged_in:
            print("❌ Час очікування вийшов або вхід не виконано.")
            browser.close()
            return

        time.sleep(3)
        
        # 1. Зберігаємо повний storage_state для Playwright
        context.storage_state(path=str(INSTA_STATE_FILE))
        print(f"✅ Збережено Playwright стан: {INSTA_STATE_FILE}")

        # 2. Формуємо та зберігаємо сесію для instagrapi
        cookies = context.cookies()
        c_dict = {c["name"]: c["value"] for c in cookies}
        user_id = c_dict.get("ds_user_id", "")
        
        instagrapi_session = {
            "authorization_data": {
                "ds_user_id": user_id,
                "sessionid": c_dict.get("sessionid", "")
            },
            "cookies": {c["name"]: c["value"] for c in cookies if "instagram.com" in c.get("domain", "")},
            "last_login": time.time()
        }
        
        with open(INSTA_SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(instagrapi_session, f, indent=2)
        print(f"✅ Збережено сесію Instagrapi: {INSTA_SESSION_FILE}")

        # Оновлюємо .env якщо потрібно
        env_file = Path(".env")
        if env_file.exists():
            content = env_file.read_text(encoding="utf-8")
            if "INSTAGRAM_SESSION_FILE=" in content:
                print("🔑 .env готовий до роботи з новою сесією Instagram!")

        print("\n✨ Instagram успішно підключено без жодних блокувань чи капч!")
        browser.close()


if __name__ == "__main__":
    login_instagram()
