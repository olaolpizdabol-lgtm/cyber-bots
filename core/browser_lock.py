"""
Глобальний лок для браузерних операцій Chromium (Playwright).
Запобігає запуску декількох інстансів Chromium одночасно в низькопам'ятному середовищі (Docker / Railway 512MB RAM).
Включає автоматичний захист від deadlocks та зависань (auto-timeout 180s).
"""
import threading
import time
import logging

logger = logging.getLogger("browser_lock")

# Базові надійні прапорці запуску Chromium для Docker/Railway
CHROME_DOCKER_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--mute-audio",
    "--disable-blink-features=AutomationControlled",
    "--no-first-run",
    "--no-default-browser-check",
    "--renderer-process-limit=1",
    "--disable-software-rasterizer",
    "--disable-accelerated-2d-canvas",
    "--disable-extensions",
    "--disable-component-extensions-with-background-pages",
]


class TimeoutLock:
    def __init__(self, default_timeout: float = 60.0, max_hold_time: float = 180.0):
        self._lock = threading.Lock()
        self._locked_at = 0.0
        self._default_timeout = default_timeout
        self._max_hold_time = max_hold_time

    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        now = time.time()
        # Якщо лок утримується довше ніж max_hold_time — це завислий потік, примусово звільняємо
        if self._lock.locked() and (now - self._locked_at > self._max_hold_time):
            logger.warning(
                f"⚠️ [BROWSER_LOCK] Виявлено завислий лок ({now - self._locked_at:.1f}с > {self._max_hold_time}с)! "
                f"Примусове розблокування для відновлення роботи системи."
            )
            self.release()

        if not blocking:
            ok = self._lock.acquire(blocking=False)
        else:
            to = timeout if timeout >= 0 else self._default_timeout
            ok = self._lock.acquire(blocking=True, timeout=to)

        if ok:
            self._locked_at = time.time()
        return ok

    def release(self):
        self._locked_at = 0.0
        try:
            self._lock.release()
        except RuntimeError:
            pass

    def locked(self) -> bool:
        if self._lock.locked() and (time.time() - self._locked_at > self._max_hold_time):
            self.release()
            return False
        return self._lock.locked()

    def __enter__(self):
        self.acquire(blocking=True, timeout=self._default_timeout)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()


BROWSER_LOCK = TimeoutLock()
