#!/usr/bin/env python3
"""
Скрипт для первинної авторизації YouTube каналу.
Запустіть цей скрипт один раз на комп'ютері, щоб створити youtube_token.json.
Після цього токен буде оновлюватися автоматично (refresh_token) і на сервері.
"""
import os
import sys
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow

# Додаємо корінь проекту в sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import YOUTUBE_CLIENT_SECRETS_FILE, YOUTUBE_TOKEN_FILE

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly"
]


def main():
    secrets_path = Path(YOUTUBE_CLIENT_SECRETS_FILE)
    token_path = Path(YOUTUBE_TOKEN_FILE)

    if not secrets_path.exists():
        print(f"❌ Файл {secrets_path} не знайдено!")
        print("1. Перейдіть у Google Cloud Console (https://console.cloud.google.com/)")
        print("2. Створіть проект, увімкніть 'YouTube Data API v3'")
        print("3. Створіть 'OAuth 2.0 Client IDs' (Desktop Application)")
        print(f"4. Завантажте JSON файл і збережіть як: {secrets_path.resolve()}")
        return

    print("🚀 Запуск OAuth2 авторизації YouTube каналу...")
    flow = InstalledAppFlow.from_client_secrets_file(str(secrets_path), SCOPES)
    creds = flow.run_local_server(port=0)

    token_path.parent.mkdir(parents=True, exist_ok=True)
    with open(token_path, "w") as token_file:
        token_file.write(creds.to_json())

    print(f"✅ Авторизація успішна! Токен збережено у: {token_path.resolve()}")
    print("Тепер бот може публікувати Shorts та зчитувати перегляди без додаткових підтверджень!")


if __name__ == "__main__":
    main()
