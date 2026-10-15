"""
Глобальний лок для браузерних операцій Chromium (Playwright).
Обмежує одночасні браузери; для контейнера з 512 MB встановіть BROWSER_MAX_CONCURRENCY=1.
Очікування обмежене тайм-аутом; зайнятий лок не забирається у власника.
"""
import os
import threading
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
    def __init__(self, default_timeout: float = 60.0, capacity: int = 1):
        self._lock = threading.BoundedSemaphore(capacity)
        self._capacity = capacity
        self._owners = set()
        self._guard = threading.Lock()
        self._default_timeout = default_timeout

    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        with self._guard:
            if threading.get_ident() in self._owners:
                return False
        if not blocking:
            acquired = self._lock.acquire(blocking=False)
        else:
            acquired = self._lock.acquire(timeout=timeout if timeout >= 0 else self._default_timeout)
        if acquired:
            with self._guard:
                self._owners.add(threading.get_ident())
        return acquired

    def release(self):
        # A timed-out caller must never release another worker's browser.
        with self._guard:
            if threading.get_ident() not in self._owners:
                raise RuntimeError("Browser lock can only be released by its owner")
            self._owners.remove(threading.get_ident())
            self._lock.release()

    def locked(self) -> bool:
        with self._guard:
            return len(self._owners) >= self._capacity

    def __enter__(self):
        if not self.acquire():
            raise TimeoutError("Browser is busy; retry on the next scan")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()


BROWSER_LOCK = TimeoutLock(capacity=max(1, min(4, int(os.getenv("BROWSER_MAX_CONCURRENCY", "1")))))
