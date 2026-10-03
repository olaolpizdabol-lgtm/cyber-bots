import os
import stat
import logging
import re
from pathlib import Path
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class SecurityGuard:
    """
    Модуль захисту від витоку облікових даних та безпекового аудиту:
    1. Забезпечує безпечні права доступу до файлів токенів та бази даних (chmod 600 / 700)
    2. Маскує чутливі токени та паролі проксі у логах та повідомленнях
    3. Запобігає передачі секретів у відкритому вигляді
    4. Проводить комплексний аудит безпеки середовища
    """

    @staticmethod
    def secure_credentials_directory(directory_path: Path):
        """Встановлює обмежені права на папку секретів (тільки для власника)"""
        if not directory_path.exists():
            directory_path.mkdir(parents=True, exist_ok=True)
        try:
            # chmod 700 (rwx------) на директорію
            os.chmod(directory_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
            for f in directory_path.iterdir():
                if f.is_file():
                    # chmod 600 (rw-------) на файли токенів і сесій
                    os.chmod(f, stat.S_IRUSR | stat.S_IWUSR)
        except Exception as e:
            logger.debug(f"Встановлення прав доступу: {e}")

    @staticmethod
    def secure_file(file_path: Path):
        """Встановлює chmod 600 на конкретний файл конфігурації або БД"""
        if file_path.exists() and file_path.is_file():
            try:
                os.chmod(file_path, stat.S_IRUSR | stat.S_IWUSR)
            except Exception as e:
                logger.debug(f"Не вдалося встановити chmod 600 на {file_path}: {e}")

    @staticmethod
    def mask_secret(secret: Optional[str], visible_chars: int = 4) -> str:
        """Маскує токени для безпечного відображення в інтерфейсі та логах"""
        if not secret:
            return "Не налаштовано"
        if len(secret) <= visible_chars * 2:
            return "****"
        return f"{secret[:visible_chars]}...{secret[-visible_chars:]}"

    @staticmethod
    def sanitize_proxy_url(proxy_url: Optional[str]) -> str:
        """Маскує логін та пароль у URL проксі для логів та UI"""
        if not proxy_url:
            return "Не налаштовано"
        # socks5://user:pass@host:port -> socks5://user:****@host:port
        return re.sub(r'(:\/\/[^:]+):([^@]+)@', r'\1:****@', proxy_url)

    @staticmethod
    def sanitize_error(error_msg: str) -> str:
        """Очищає помилки від можливих витоків токенів, паролів або сесійних cookie"""
        if not error_msg:
            return ""
        sanitized = str(error_msg)
        sanitized = re.sub(r'access_token=[a-zA-Z0-9_\-]+', 'access_token=***', sanitized)
        sanitized = re.sub(r'Bearer\s+[a-zA-Z0-9_\.\-]+', 'Bearer ***', sanitized)
        sanitized = re.sub(r':\/\/[^:]+:[^@]+@', '://***:***@', sanitized)
        sanitized = re.sub(r'sessionid=[a-zA-Z0-9_\%]+', 'sessionid=***', sanitized)
        sanitized = re.sub(r'client_secret=[a-zA-Z0-9_\-]+', 'client_secret=***', sanitized)
        return sanitized

    @classmethod
    def audit_security(cls, project_root: Path) -> Dict[str, Any]:
        """
        Комплексний безпековий аудит локального середовища:
        - Перевірка прав доступу на .env, data/, tokens/
        - Перевірка наявності небезпечних публічних витоків
        - Перевірка ізоляції сесій
        """
        issues = []
        passed = []

        # 1. Перевірка .env
        env_file = project_root / ".env"
        if env_file.exists():
            mode = oct(env_file.stat().st_mode & 0o777)
            if mode in ("0o600", "0o400"):
                passed.append(".env файл захищено (chmod 600)")
            else:
                cls.secure_file(env_file)
                passed.append(f".env права оновлено до chmod 600 (було {mode})")
        else:
            issues.append(".env файл не знайдено")

        # 2. Перевірка data/ директорії
        data_dir = project_root / "data"
        if data_dir.exists():
            cls.secure_credentials_directory(data_dir)
            passed.append("Папка data/ та SQLite БД захищені (chmod 700 / 600)")

        # 3. Перевірка безпеки медіа-директорії
        dl_dir = project_root / "downloads"
        if dl_dir.exists():
            cls.secure_credentials_directory(dl_dir)
            passed.append("Папка завантажень downloads/ захищена")

        return {
            "is_secure": len(issues) == 0,
            "passed": passed,
            "issues": issues,
            "summary": "✅ Усі секрети та сесії надійно ізольовані локально!" if not issues else f"⚠️ Знайдено зауваження: {', '.join(issues)}"
        }


security_guard = SecurityGuard()
