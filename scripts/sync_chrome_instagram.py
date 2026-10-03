"""
🔄 Автоматична синхронізація сесії Instagram прямо з Chrome Profile "Bohdan"
Витягує зашифровані cookies з локального сховища Chrome без паролів, капч та повторних входів!

Запуск:
    .venv/bin/python scripts/sync_chrome_instagram.py
"""
import os
import sys
import json
import time
import shutil
import sqlite3
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from config import DATA_DIR, CREDENTIALS_DIR

INSTA_STATE_FILE = DATA_DIR / "instagram_state.json"
INSTA_SESSION_FILE = CREDENTIALS_DIR / "instagram_session.json"


def get_chrome_safe_storage_password():
    try:
        cmd = ["security", "find-generic-password", "-s", "Chrome Safe Storage", "-w"]
        res = subprocess.check_output(cmd).strip()
        return res
    except Exception as e:
        print(f"❌ Не вдалося отримати пароль Chrome Safe Storage з Keychain: {e}")
        return None


def sync_instagram_from_chrome(profile_name="Profile 7"):
    print(f"🚀 Синхронізація Instagram сесії з Chrome ({profile_name} / Bohdan)...")
    
    password = get_chrome_safe_storage_password()
    if not password:
        return False

    salt = b"saltysalt"
    kdf = PBKDF2HMAC(algorithm=hashes.SHA1(), length=16, salt=salt, iterations=1003)
    key = kdf.derive(password)

    chrome_dir = Path.home() / "Library/Application Support/Google/Chrome"
    cookie_db = chrome_dir / profile_name / "Cookies"
    if not cookie_db.exists():
        cookie_db = chrome_dir / profile_name / "Network/Cookies"

    if not cookie_db.exists():
        print(f"❌ Базу Cookies не знайдено за шляхом: {cookie_db}")
        return False

    tmp_db = "/tmp/chrome_instagram_cookies.sqlite"
    shutil.copyfile(cookie_db, tmp_db)

    conn = sqlite3.connect(tmp_db)
    cur = conn.cursor()
    cur.execute("""
        SELECT host_key, name, path, is_secure, is_httponly, expires_utc, encrypted_value 
        FROM cookies 
        WHERE host_key LIKE '%instagram%'
    """)

    playwright_cookies = []
    instagrapi_cookies = {}
    session_id = ""
    ds_user_id = ""

    for host, name, path, is_sec, is_http, exp, enc_val in cur.fetchall():
        try:
            raw = enc_val[3:]
            cipher = Cipher(algorithms.AES(key), modes.CBC(b" " * 16))
            dec = cipher.decryptor().update(raw) + cipher.decryptor().finalize()
            pad = dec[-1]
            if 1 <= pad <= 16:
                val = dec[32:-pad].decode("utf-8", errors="ignore")
            else:
                val = dec[32:].decode("utf-8", errors="ignore")

            if name == "sessionid":
                session_id = val
            elif name == "ds_user_id":
                ds_user_id = val

            playwright_cookies.append({
                "name": name,
                "value": val,
                "domain": host,
                "path": path,
                "expires": -1,
                "httpOnly": bool(is_http),
                "secure": bool(is_sec),
                "sameSite": "Lax"
            })
            instagrapi_cookies[name] = val
        except Exception:
            pass

    conn.close()

    if not session_id or not ds_user_id:
        print("⚠️ Не знайдено активних сесійних cookies для Instagram у цьому профілі Chrome.")
        return False

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Зберігаємо для Playwright
    with open(INSTA_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"cookies": playwright_cookies, "origins": []}, f, indent=2)

    # 2. Зберігаємо для Instagrapi
    with open(INSTA_SESSION_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "authorization_data": {
                "ds_user_id": ds_user_id,
                "sessionid": session_id
            },
            "cookies": instagrapi_cookies,
            "last_login": time.time()
        }, f, indent=2)

    print(f"✅ Успішно! Знайдено {len(playwright_cookies)} cookies.")
    print(f"👤 ds_user_id: {ds_user_id}")
    print(f"📁 Збережено Playwright: {INSTA_STATE_FILE}")
    print(f"📁 Збережено Instagrapi: {INSTA_SESSION_FILE}")
    return True


if __name__ == "__main__":
    sync_instagram_from_chrome()
