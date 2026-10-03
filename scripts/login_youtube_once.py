"""
🎥 1-Клік Авторизація YouTube Shorts (Google OAuth 2.0)
Зберігає токени у credentials/youtube_token.json

Запуск:
    .venv/bin/python scripts/login_youtube_once.py
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from config import YOUTUBE_CLIENT_SECRETS_FILE, YOUTUBE_TOKEN_FILE, CREDENTIALS_DIR

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly"
]


def setup_youtube():
    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
    secrets_path = Path(YOUTUBE_CLIENT_SECRETS_FILE)
    token_path = Path(YOUTUBE_TOKEN_FILE)

    print("🚀 Авторизація YouTube Shorts (Google Data API v3)...")

    # Якщо файлу secrets ще немає — пропонуємо швидке створення
    if not secrets_path.exists():
        # Перевіримо, чи випадково користувач не поклав client_secret*.json у корінь або credentials
        found = list(CREDENTIALS_DIR.glob("client_secret*.json")) or list(Path(".").glob("client_secret*.json"))
        if found:
            secrets_path = found[0]
            print(f"📁 Знайдено файл ключів: {secrets_path}")
        else:
            print("\n" + "="*60)
            print("⚠️ ДЛЯ YOUTUBE ПОТРІБЕН GOOGLE OAUTH CLIENT ID:")
            print("1. Зайди на: https://console.cloud.google.com/apis/credentials")
            print("2. Створи або обери проект, увімкни 'YouTube Data API v3'")
            print("3. Натисни 'Створити облікові дані' -> 'Ідентифікатор клієнта OAuth' -> 'ПК / Desktop app'")
            print("4. Завантаж JSON-файл і збережи як:")
            print(f"   {YOUTUBE_CLIENT_SECRETS_FILE}")
            print("="*60 + "\n")

            client_id = input("Або введи Client ID прямо сюди (Enter щоб скасувати): ").strip()
            if not client_id:
                print("❌ Скасовано.")
                return

            client_secret = input("Введи Client Secret: ").strip()
            if not client_secret:
                print("❌ Скасовано.")
                return

            secrets_data = {
                "installed": {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                    "redirect_uris": ["http://localhost:8080/"]
                }
            }
            with open(secrets_path, "w", encoding="utf-8") as f:
                json.dump(secrets_data, f, indent=2)
            print(f"✅ Файл конфігурації створено: {secrets_path}")

    # Запуск OAuth flow
    flow = InstalledAppFlow.from_client_secrets_file(str(secrets_path), SCOPES)
    print("\n🌐 Відкриваємо сторінку авторизації Google у браузері...")
    print("👉 Обери свій Google акаунт з YouTube-каналом та надай доступ.")

    try:
        creds = flow.run_local_server(port=8080, prompt="consent", access_type="offline")
    except Exception as e:
        print(f"⚠️ Локальний сервер не відкрився ({e}), перемикаємось на консольний код:")
        creds = flow.run_console()

    # Зберігаємо токен
    with open(token_path, "w", encoding="utf-8") as token_file:
        token_file.write(creds.to_json())

    print(f"\n🎉 YouTube Shorts успішно авторизовано! Токен збережено у: {token_path}")
    print("✨ Тепер бот може публікувати Shorts повністю автономно!")


if __name__ == "__main__":
    setup_youtube()
