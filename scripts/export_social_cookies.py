"""
🍪 Automatic Facebook & Instagram Cookie Exporter for Playwright & Instagrapi
Extracts live authenticated sessions from Chrome Profile 4 on macOS
"""
import os
import shutil
import sqlite3
import hashlib
import json
import base64
import subprocess
from pathlib import Path
from Cryptodome.Cipher import AES

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CREDENTIALS_DIR = BASE_DIR / "credentials"


def get_chrome_safe_storage_key() -> bytes:
    res = subprocess.run(
        ["security", "find-generic-password", "-w", "-s", "Chrome Safe Storage"],
        capture_output=True,
        text=True
    )
    pwd = res.stdout.strip()
    if not pwd:
        raise RuntimeError("Could not retrieve Chrome Safe Storage key from keychain")
    return hashlib.pbkdf2_hmac("sha1", pwd.encode("utf-8"), b"saltysalt", 1003, dklen=16)


def decrypt_chrome_cookie(encrypted_value: bytes, key: bytes) -> str:
    if not encrypted_value or encrypted_value[:3] != b"v10":
        return ""
    cipher = AES.new(key, AES.MODE_CBC, b" " * 16)
    dec = cipher.decrypt(encrypted_value[3:])
    pad = dec[-1]
    if isinstance(pad, int) and 1 <= pad <= 16:
        raw = dec[32:-pad]
    else:
        raw = dec[32:]
    try:
        return raw.decode("utf-8")
    except Exception:
        return raw.decode("latin1", errors="ignore")


def export_cookies_for_platform(platform_name: str, host_filter: str, out_json_path: Path):
    key = get_chrome_safe_storage_key()
    chrome_profiles = [
        os.path.expanduser("~/Library/Application Support/Google/Chrome/Profile 4"),
        os.path.expanduser("~/Library/Application Support/Google/Chrome/Profile 1"),
        os.path.expanduser("~/Library/Application Support/Google/Chrome/Profile 7"),
        os.path.expanduser("~/Library/Application Support/Google/Chrome/Default"),
    ]

    best_cookies = []

    for prof in chrome_profiles:
        cookie_db = os.path.join(prof, "Cookies")
        if not os.path.exists(cookie_db):
            continue

        tmp_db = f"/tmp/chrome_{platform_name}_cookies_export.db"
        try:
            shutil.copy2(cookie_db, tmp_db)
            conn = sqlite3.connect(tmp_db)
            cur = conn.cursor()
            cur.execute(f"""
                SELECT name, value, host_key, path, expires_utc, is_secure, is_httponly, samesite, encrypted_value
                FROM cookies
                WHERE host_key LIKE '%{host_filter}%'
            """)

            cookies = []
            for row in cur.fetchall():
                name, value, host_key, path, expires_utc, is_secure, is_httponly, samesite, encrypted_value = row
                val = value
                if not val and encrypted_value:
                    val = decrypt_chrome_cookie(encrypted_value, key)
                if not val:
                    continue

                samesite_map = {-1: "None", 0: "None", 1: "Lax", 2: "Strict"}
                same_site_str = samesite_map.get(samesite, "None")
                is_sec = bool(is_secure)
                if same_site_str == "None" and not is_sec:
                    same_site_str = "Lax"

                cookie_dict = {
                    "name": name,
                    "value": val,
                    "domain": host_key,
                    "path": path or "/",
                    "httpOnly": bool(is_httponly),
                    "secure": is_sec,
                    "sameSite": same_site_str
                }
                if expires_utc and int(expires_utc) > 0:
                    exp_unix = (float(expires_utc) / 1000000.0) - 11644473600.0
                    if exp_unix > 0:
                        cookie_dict["expires"] = exp_unix

                cookies.append(cookie_dict)

            conn.close()
            if os.path.exists(tmp_db):
                os.remove(tmp_db)

            # Перевіряємо чи є сесійні куки (c_user/sessionid)
            has_auth = any(c["name"] in ("c_user", "sessionid") for c in cookies)
            if has_auth and len(cookies) > len(best_cookies):
                best_cookies = cookies
                print(f"[{platform_name}] Знайдено авторизовану сесію в {os.path.basename(prof)} ({len(cookies)} кукісів)")
        except Exception as e:
            if os.path.exists(tmp_db):
                os.remove(tmp_db)

    if not best_cookies:
        print(f"⚠️ Не знайдено авторизованих кукісів для {platform_name}")
        return False

    out_json_path.parent.mkdir(parents=True, exist_ok=True)
    storage_state = {
        "cookies": best_cookies,
        "origins": []
    }
    with open(out_json_path, "w") as f:
        json.dump(storage_state, f, indent=2)

    print(f"✅ Збережено Playwright session state: {out_json_path}")
    return True


def export_all():
    print("🚀 Експорт соціальних сесій з Google Chrome...")
    # 1. Facebook
    fb_path = DATA_DIR / "facebook_state.json"
    fb_ok = export_cookies_for_platform("facebook", "facebook.com", fb_path)

    # 2. Instagram
    ig_path = DATA_DIR / "instagram_state.json"
    ig_ok = export_cookies_for_platform("instagram", "instagram.com", ig_path)

    # Також створюємо instagrapi session format для Instagram
    if ig_ok and ig_path.exists():
        try:
            with open(ig_path) as f:
                state_data = json.load(f)
            cookies_list = state_data.get("cookies", [])
            ig_cookies = {c["name"]: c["value"] for c in cookies_list if "instagram.com" in c.get("domain", "")}
            user_id = ig_cookies.get("ds_user_id", "")
            
            instagrapi_session = {
                "uuids": {
                    "phone_id": "912b4bfa-4c4d-4b82-8c01-7fa1e5a5933f",
                    "uuid": "4c4d912b-4bfa-4b82-8c01-7fa1e5a5933f",
                    "client_session_id": "8c01912b-4bfa-4c4d-4b82-7fa1e5a5933f",
                    "device_id": f"android-{user_id}"
                },
                "mid": ig_cookies.get("mid", ""),
                "ig_u_rur": None,
                "ig_www_claim": None,
                "authorization_data": {
                    "ds_user_id": user_id,
                    "sessionid": ig_cookies.get("sessionid", "")
                },
                "cookies": ig_cookies,
                "last_login": 1791880000.0,
                "device_settings": {
                    "app_version": "269.0.0.18.75",
                    "android_version": 30,
                    "android_release": "11.0",
                    "dpi": "480dpi",
                    "resolution": "1080x2400",
                    "manufacturer": "Samsung",
                    "device": "SM-G998B",
                    "model": "Galaxy S21 Ultra",
                    "cpu": "exynos2100",
                    "version_code": "314665256"
                },
                "user_agent": "Instagram 269.0.0.18.75 Android (30/11.0; 480dpi; 1080x2400; samsung; SM-G998B; p3s; exynos2100; en_US; 314665256)"
            }
            CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
            session_file = CREDENTIALS_DIR / "instagram_session.json"
            with open(session_file, "w") as f:
                json.dump(instagrapi_session, f, indent=2)
            print(f"✅ Згенеровано instagrapi session: {session_file} (user_id={user_id})")
        except Exception as e:
            print(f"Помилка створення instagrapi_session: {e}")

    # 3. Синхронізація у .env для хмарного деплою (Railway)
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        try:
            with open(env_file) as f:
                env_text = f.read()

            if fb_ok and fb_path.exists():
                fb_b64 = base64.b64encode(fb_path.read_bytes()).decode("utf-8")
                if "FACEBOOK_STATE_B64=" in env_text:
                    env_text = re.sub(r"FACEBOOK_STATE_B64=.*", f"FACEBOOK_STATE_B64={fb_b64}", env_text)
                else:
                    env_text += f"\nFACEBOOK_STATE_B64={fb_b64}\n"
                print("✅ Оновлено FACEBOOK_STATE_B64 у .env")

            ig_sess_file = CREDENTIALS_DIR / "instagram_session.json"
            if ig_sess_file.exists():
                ig_b64 = base64.b64encode(ig_sess_file.read_bytes()).decode("utf-8")
                if "INSTAGRAM_SESSION_B64=" in env_text:
                    env_text = re.sub(r"INSTAGRAM_SESSION_B64=.*", f"INSTAGRAM_SESSION_B64={ig_b64}", env_text)
                else:
                    env_text += f"\nINSTAGRAM_SESSION_B64={ig_b64}\n"
                print("✅ Оновлено INSTAGRAM_SESSION_B64 у .env")

            with open(env_file, "w") as f:
                f.write(env_text)
        except Exception as e:
            print(f"Помилка оновлення .env: {e}")

    print("🎉 Всі соціальні сесії готові до автономної роботи!")


if __name__ == "__main__":
    import re
    export_all()
