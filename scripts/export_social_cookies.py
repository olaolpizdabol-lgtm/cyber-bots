"""Export explicitly selected Chrome profile sessions to a private Railway env file."""
import argparse
import base64
import hashlib
import json
import os
import sqlite3
import subprocess
import tempfile
import time
from pathlib import Path

try:
    from Cryptodome.Cipher import AES
except ImportError:
    from Crypto.Cipher import AES

BASE_DIR = Path(__file__).resolve().parent.parent
PLATFORMS = {
    'facebook': ('facebook.com', {'c_user', 'xs'}, 'FACEBOOK_STATE_B64'),
    'instagram': ('instagram.com', {'sessionid', 'ds_user_id'}, 'INSTAGRAM_STATE_B64'),
    'tiktok': ('tiktok.com', {'sessionid'}, 'TIKTOK_CHANNEL_STATE_B64'),
}


def select_profile(root, name):
    profiles = json.loads((root / 'Local State').read_text())['profile']['info_cache']
    matches = [root / directory for directory, info in profiles.items() if info.get('name') == name]
    if len(matches) != 1:
        raise RuntimeError('Profile name must match exactly one Chrome profile')
    return matches[0]


def get_chrome_safe_storage_key():
    result = subprocess.run(['security', 'find-generic-password', '-w', '-s', 'Chrome Safe Storage'], capture_output=True, check=True)
    return hashlib.pbkdf2_hmac('sha1', result.stdout.strip(), b'saltysalt', 1003, dklen=16)


def decrypt_chrome_cookie(encrypted, key, host, version):
    if not encrypted.startswith(b'v10'):
        raise RuntimeError('Unsupported cookie encryption; export stopped')
    raw = AES.new(key, AES.MODE_CBC, b' ' * 16).decrypt(encrypted[3:])
    padding = raw[-1]
    if not 1 <= padding <= 16 or raw[-padding:] != bytes([padding]) * padding:
        raise RuntimeError('Cookie decryption failed')
    raw = raw[:-padding]
    if version >= 24:
        if raw[:32] != hashlib.sha256(host.encode()).digest():
            raise RuntimeError('Cookie host validation failed')
        raw = raw[32:]
    return raw.decode('utf-8')


def read_cookies(profile, domain, key):
    source = profile / 'Cookies'
    if not source.exists():
        source = profile / 'Network' / 'Cookies'
    with tempfile.TemporaryDirectory(prefix='social-session-') as folder:
        snapshot = Path(folder) / 'cookies.db'
        with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as src, sqlite3.connect(snapshot) as dst:
            src.backup(dst)
            version = int(dst.execute("SELECT value FROM meta WHERE key='version'").fetchone()[0])
            rows = dst.execute('SELECT name,value,host_key,path,expires_utc,is_secure,is_httponly,samesite,encrypted_value FROM cookies WHERE host_key = ? OR host_key LIKE ?', (domain, '%.' + domain)).fetchall()
    cookies = []
    for name, value, host, path, expires, secure, http_only, same_site, encrypted in rows:
        expiry = expires / 1_000_000 - 11644473600 if expires else -1
        if expiry != -1 and expiry <= time.time():
            continue
        value = value or decrypt_chrome_cookie(encrypted, key, host, version)
        if not value:
            continue
        same_site = {1: 'Lax', 2: 'Strict'}.get(same_site, 'None' if secure else 'Lax')
        cookies.append(dict(name=name, value=value, domain=host, path=path or '/', expires=expiry, secure=bool(secure), httpOnly=bool(http_only), sameSite=same_site))
    return cookies


def private_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', required=True, help='Exact Chrome display name, e.g. Bohdan')
    parser.add_argument('--platform', nargs='+', choices=PLATFORMS, required=True)
    parser.add_argument('--output', type=Path, required=True, help='Private .env import file; never commit it')
    args = parser.parse_args()
    profile = select_profile(Path.home() / 'Library/Application Support/Google/Chrome', args.profile)
    key = get_chrome_safe_storage_key()
    exports = []
    for platform in dict.fromkeys(args.platform):
        domain, required, env_name = PLATFORMS[platform]
        cookies = read_cookies(profile, domain, key)
        if not required <= {cookie['name'] for cookie in cookies}:
            raise RuntimeError(f'{platform}: active authentication cookies missing in selected profile')
        state = json.dumps({'cookies': cookies, 'origins': []})
        exports.append((env_name, state))
        if platform == 'instagram':
            # The adapter validates browser cookies through login_by_sessionid.
            exports.append(('INSTAGRAM_SESSION_B64', state))
    private_write(args.output, ''.join(f'{name}={base64.b64encode(state.encode()).decode()}\n' for name, state in exports))
    print(f'Prepared {len(exports)} session variables in {args.output}; not uploaded or verified by platforms.')


if __name__ == '__main__':
    main()
