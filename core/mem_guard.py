"""
Охорона пам'яті для 1 ГБ Railway:
- перевіряє вільну RAM перед запуском Chromium;
- прибирає старі файли з downloads/temp, щоб не переповнювати диск.
"""
import os
import gc
import time
import shutil
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Скільки вільної RAM має бути перед запуском Chromium (МБ)
MIN_FREE_MB_FOR_BROWSER = 280
# Вік життя тимчасових файлів (секунди)
TEMP_FILE_MAX_AGE_S = 24 * 3600


def get_free_memory_mb() -> Optional[int]:
    """Вільна RAM у МБ (Linux /proc/meminfo). None якщо невідомо (macOS)."""
    try:
        meminfo = Path("/proc/meminfo")
        if meminfo.exists():
            for line in meminfo.read_text().splitlines():
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
    except Exception:
        pass
    return None


def ensure_memory_for_browser(platform_label: str = "browser") -> bool:
    """
    Повертає True якщо можна запускати Chromium.
    При нестачі пам'яті — збирає сміття і повертає False (запуск потрібно пропустити).
    """
    gc.collect()
    free_mb = get_free_memory_mb()
    if free_mb is None:
        return True
    if free_mb < MIN_FREE_MB_FOR_BROWSER:
        gc.collect()
        free_mb = get_free_memory_mb()
        if free_mb is not None and free_mb < MIN_FREE_MB_FOR_BROWSER:
            logger.warning(
                f"🚫 Недостатньо пам'яті для запуску Chromium ({platform_label}): "
                f"{free_mb} МБ вільно, потрібно >= {MIN_FREE_MB_FOR_BROWSER} МБ. Пропускаємо."
            )
            return False
    logger.info(f"🧠 Пам'ять OK для {platform_label}: {free_mb} МБ вільно.")
    return True


def cleanup_old_files(directory, max_age_s: int = TEMP_FILE_MAX_AGE_S, keep_recent: int = 5) -> int:
    """Видаляє файли старіші за max_age_s у directory. Повертає кількість видалених."""
    d = Path(directory)
    if not d.exists():
        return 0
    now = time.time()
    removed = 0
    try:
        files = sorted(
            [p for p in d.iterdir() if p.is_file()],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except Exception:
        return 0
    for i, p in enumerate(files):
        try:
            if i < keep_recent:
                continue
            if now - p.stat().st_mtime > max_age_s:
                p.unlink(missing_ok=True)
                removed += 1
        except Exception:
            continue
    if removed:
        logger.info(f"🧹 Прибрано {removed} старих файлів з {d}")
    return removed


def cleanup_temp_dirs() -> int:
    """Прибирання старого вмісту downloads/, temp/ та діагностичних скріншотів."""
    from config import BASE_DIR
    total = 0
    total += cleanup_old_files(BASE_DIR / "downloads", keep_recent=3)
    total += cleanup_old_files(BASE_DIR / "temp", keep_recent=3)
    # Скріншоти діагностики (data/*.png) — тільки зображення, НІКОЛИ не чіпаємо .json/.db
    data_dir = BASE_DIR / "data"
    if data_dir.exists():
        now = time.time()
        for p in data_dir.glob("*.png"):
            try:
                if now - p.stat().st_mtime > 3 * 24 * 3600:
                    p.unlink(missing_ok=True)
                    total += 1
            except Exception:
                continue
    if total:
        logger.info(f"🧹 Прибрано {total} старих тимчасових файлів")
    return total
