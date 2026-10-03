"""
🔑 1-Клік Авторизація TikTok для Вогників (TikTok Streaks Login Helper)

Запуск:
    .venv/bin/python scripts/login_tiktok_once.py

Що робить:
1. Відкриває реальне вікно браузера Chrome з вашим проксі.
2. Ви входите в акаунт (найшвидше — 3 секунди скануванням QR-коду з мобільного додатку TikTok).
3. Скрипт автоматично перехоплює ВСІ токени, cookies (ttwid, sessionid, sid_guard) та зберігає їх у data/tiktok_state.json.
4. Після цього бот працює повністю автономно без капч та вікон входу!
"""
import sys
import time
from pathlib import Path

# Додаємо корінь проекту в PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.sync_api import sync_playwright
from config import DATA_DIR
from services.proxy_manager import proxy_manager

STATE_FILE = DATA_DIR / "tiktok_state.json"


def login_once():
    proxy_cfg = proxy_manager.get_playwright_proxy()
    print("🚀 Запуск браузера для авторизації TikTok...")
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
            viewport={"width": 1280, "height": 850},
            locale="uk-UA"
        )
        page = context.new_page()

        print("📱 Відкриваємо сторінку входу TikTok...")
        page.goto("https://www.tiktok.com/login", timeout=60000)

        print("\n" + "="*60)
        print("👉 БУДЬ ЛАСКА, УВІЙДІТЬ У СВІЙ АКАУНТ У ВІДКРИТОМУ ВІКНІ")
        print("💡 Найзручніше: відкрийте TikTok на телефоні -> Профіль -> Меню (три рисочки) -> Мій QR-код -> Сканувати")
        print("="*60 + "\n")

        print("⏳ Очікую підтвердження авторизації (максимум 3 хвилини)...")
        logged_in = False
        start_time = time.time()

        while time.time() - start_time < 180:
            time.sleep(2)
            try:
                cookies = context.cookies()
                cookie_names = {c["name"]: c["value"] for c in cookies}
                has_session = "sessionid" in cookie_names and len(cookie_names["sessionid"]) > 15
                has_uid = "uid_tt" in cookie_names or "sid_guard" in cookie_names

                # Перевіряємо чи зникла сторінка логіну або з'явився профіль
                is_on_home_or_feed = "/login" not in page.url and (has_session or has_uid)

                if has_session and (has_uid or is_on_home_or_feed):
                    logged_in = True
                    sess_val = cookie_names["sessionid"]
                    print(f"✅ Успішно виявлено активну сесію! (sessionid={sess_val[:10]}...)")
                    break
            except Exception:
                pass

        if logged_in:
            page.wait_for_timeout(3000)
            context.storage_state(path=str(STATE_FILE))
            print(f"\n🎉 ПЕРЕМОГА! Повний стан сесії та cookies успішно збережено у:")
            print(f"📁 {STATE_FILE}")
            print("🚀 Тепер бот може відправляти TikTok вогники 100% автономно!\n")
        else:
            print("❌ Час очікування авторизації вичерпано. Спробуйте ще раз.")

        browser.close()


if __name__ == "__main__":
    login_once()
