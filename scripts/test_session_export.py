"""Synthetic fixtures only: never access live browser profiles or Keychain."""
import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from export_social_cookies import AES, decrypt_chrome_cookie, select_profile, private_write, read_cookies


class ExportTests(unittest.TestCase):
    def test_selects_exact_profile_and_rejects_ambiguity(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            profiles = {'Default': {'name': 'Bohdan Work'}, 'Profile 2': {'name': 'Bohdan'}}
            (root / 'Local State').write_text(json.dumps({'profile': {'info_cache': profiles}}))
            self.assertEqual(select_profile(root, 'Bohdan'), root / 'Profile 2')
            with self.assertRaises(RuntimeError):
                select_profile(root, 'Bogdan')
            profiles['Profile 3'] = {'name': 'Bohdan'}
            (root / 'Local State').write_text(json.dumps({'profile': {'info_cache': profiles}}))
            with self.assertRaises(RuntimeError):
                select_profile(root, 'Bohdan')

    def test_cookie_host_digest_is_validated(self):
        key, host = b'0' * 16, '.example.test'
        raw = hashlib.sha256(host.encode()).digest() + b'fixture-not-a-real-session'
        pad = 16 - len(raw) % 16
        encrypted = b'v10' + AES.new(key, AES.MODE_CBC, b' ' * 16).encrypt(raw + bytes([pad]) * pad)
        self.assertEqual(decrypt_chrome_cookie(encrypted, key, host, 24), 'fixture-not-a-real-session')
        with self.assertRaises(RuntimeError):
            decrypt_chrome_cookie(encrypted, key, '.other.test', 24)

    def test_output_is_private_even_when_replacing_existing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'export.env'
            path.write_text('old'); path.chmod(0o644)
            private_write(path, 'synthetic')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.read_text(), 'synthetic')

    def test_cookie_export_excludes_expired_and_unrelated_domains(self):
        with tempfile.TemporaryDirectory() as folder:
            profile = Path(folder)
            with sqlite3.connect(profile / 'Cookies') as connection:
                connection.execute('CREATE TABLE meta (key TEXT, value TEXT)')
                connection.execute("INSERT INTO meta VALUES ('version', '24')")
                connection.execute('CREATE TABLE cookies (name,value,host_key,path,expires_utc,is_secure,is_httponly,samesite,encrypted_value)')
                connection.executemany('INSERT INTO cookies VALUES (?,?,?,?,?,?,?,?,?)', [
                    ('sessionid', 'fixture', '.example.test', '/', 0, 1, 1, 1, b''),
                    ('old', 'fixture', '.example.test', '/', 11644473600000001, 1, 1, 1, b''),
                    ('other', 'fixture', '.notexample.test', '/', 0, 1, 1, 1, b''),
                ])
            cookies = read_cookies(profile, 'example.test', b'0' * 16)
            self.assertEqual([cookie['name'] for cookie in cookies], ['sessionid'])


if __name__ == '__main__':
    unittest.main()
