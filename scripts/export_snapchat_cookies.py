import os
import shutil
import sqlite3
import hashlib
import json
import subprocess
from pathlib import Path
from Cryptodome.Cipher import AES

def decrypt_chrome_cookie(encrypted_value: bytes, key: bytes) -> str:
    if not encrypted_value:
        return ""
    if encrypted_value[:3] == b"v10":
        encrypted_value = encrypted_value[3:]
        iv = b" " * 16
        cipher = AES.new(key, AES.MODE_CBC, iv)
        decrypted = cipher.decrypt(encrypted_value)
        # Strip PKCS7 padding
        pad_len = decrypted[-1]
        if isinstance(pad_len, int) and 1 <= pad_len <= 16:
            raw_val = decrypted[32:-pad_len]
        else:
            raw_val = decrypted[32:]
        try:
            return raw_val.decode("utf-8")
        except UnicodeDecodeError:
            return raw_val.decode("latin1", errors="ignore")
    return ""

def export_snapchat_cookies():
    # 1. Get Chrome password from Keychain
    res = subprocess.run(
        ["security", "find-generic-password", "-w", "-s", "Chrome Safe Storage"],
        capture_output=True,
        text=True
    )
    pwd = res.stdout.strip()
    if not pwd:
        raise RuntimeError("Could not retrieve Chrome Safe Storage key from keychain")

    key = hashlib.pbkdf2_hmac("sha1", pwd.encode("utf-8"), b"saltysalt", 1003, dklen=16)

    # 2. Path to Profile 4 Cookies
    cookie_db = os.path.expanduser("~/Library/Application Support/Google/Chrome/Profile 4/Cookies")
    tmp_db = "/tmp/chrome_snapchat_cookies_export.db"
    shutil.copy2(cookie_db, tmp_db)

    conn = sqlite3.connect(tmp_db)
    cur = conn.cursor()
    cur.execute("""
        SELECT name, value, host_key, path, expires_utc, is_secure, is_httponly, samesite, encrypted_value
        FROM cookies
        WHERE host_key LIKE '%snapchat%' OR host_key LIKE '%snap.com%'
    """)

    playwright_cookies = []
    for row in cur.fetchall():
        name, value, host_key, path, expires_utc, is_secure, is_httponly, samesite, encrypted_value = row
        val = value
        if not val and encrypted_value:
            val = decrypt_chrome_cookie(encrypted_value, key)

        if not val:
            continue

        samesite_map = {-1: "None", 0: "None", 1: "Lax", 2: "Strict"}
        same_site_str = samesite_map.get(samesite, "None")

        # In Chromium, sameSite=None cookies MUST have secure=True
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

        playwright_cookies.append(cookie_dict)

    conn.close()
    if os.path.exists(tmp_db):
        os.remove(tmp_db)

    print(f"Decrypted {len(playwright_cookies)} valid Snapchat cookies from Chrome Profile 4!")
    
    out_file = Path("/Users/bohdan/Downloads/Telegram Desktop/Channel Automations/data/snapchat_state.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    
    storage_state = {
        "cookies": playwright_cookies,
        "origins": []
    }
    with open(out_file, "w") as f:
        json.dump(storage_state, f, indent=2)

    print(f"Saved Playwright storage_state to {out_file}")

if __name__ == "__main__":
    export_snapchat_cookies()
