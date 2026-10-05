"""
Скрипт для перевірки та збереження токена Threads API.
"""
import sys
import os
import requests
from pathlib import Path

ENV_PATH = Path(".env")

def test_and_save_threads_token(token: str, app_secret: str = None):
    token = token.strip()
    print(f"Перевіряємо токен Threads: {token[:15]}...")
    
    # 1. Запит інформації про користувача
    url = f"https://graph.threads.net/v1.0/me?fields=id,username,name,threads_profile_picture_url&access_token={token}"
    resp = requests.get(url, timeout=10)
    
    if resp.status_code != 200:
        print(f"Помилка перевірки токена: {resp.status_code}")
        print(resp.text)
        return False
        
    data = resp.json()
    user_id = data.get("id")
    username = data.get("username")
    print(f"Успішно підключено! Користувач: @{username} (ID: {user_id})")
    
    final_token = token
    # 2. Якщо є App Secret - обмінюємо на довгоживучий 60-денний токен
    if app_secret:
        print("Обмінюємо на довгоживучий 60-денний токен...")
        exchange_url = (
            f"https://graph.threads.net/access_token?"
            f"grant_type=th_exchange_token&client_secret={app_secret}&access_token={token}"
        )
        ex_resp = requests.get(exchange_url, timeout=10)
        if ex_resp.status_code == 200:
            ex_data = ex_resp.json()
            final_token = ex_data.get("access_token", token)
            expires_in = ex_data.get("expires_in", 5184000)
            print(f"Отримано довгоживучий токен (дійсний {expires_in // 86400} днів)!")
        else:
            print(f"Попередження: обмін токена не вдався ({ex_resp.text}), використовуємо початковий.")

    # 3. Зберігаємо у .env
    lines = []
    if ENV_PATH.exists():
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
        
    updated_token = False
    updated_user = False
    new_lines = []
    for line in lines:
        if line.startswith("THREADS_ACCESS_TOKEN="):
            new_lines.append(f"THREADS_ACCESS_TOKEN={final_token}")
            updated_token = True
        elif line.startswith("THREADS_USER_ID="):
            new_lines.append(f"THREADS_USER_ID={user_id}")
            updated_user = True
        else:
            new_lines.append(line)
            
    if not updated_token:
        new_lines.append(f"THREADS_ACCESS_TOKEN={final_token}")
    if not updated_user:
        new_lines.append(f"THREADS_USER_ID={user_id}")
        
    ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    print("Успішно збережено THREADS_ACCESS_TOKEN та THREADS_USER_ID у .env!")
    return True

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Використання: python scripts/setup_threads_token.py <THREADS_ACCESS_TOKEN> [APP_SECRET]")
        sys.exit(1)
    tok = sys.argv[1]
    sec = sys.argv[2] if len(sys.argv) > 2 else None
    test_and_save_threads_token(tok, sec)
