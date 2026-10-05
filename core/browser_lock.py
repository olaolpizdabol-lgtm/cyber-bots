"""
Глобальний лок для браузерних операцій Chromium (Playwright).
Запобігає запуску декількох інстансів Chromium одночасно в низькопам'ятному середовищі (Docker / Railway 512MB RAM).
"""
import threading

BROWSER_LOCK = threading.Lock()
