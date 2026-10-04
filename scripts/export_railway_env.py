"""
📦 Експорт усіх налаштувань та сесій для Railway у компактний файл
Очищає зайвий кеш TikTok з 1.3 МБ до 9 КБ!
Зберігає результат у файл `railway_env_ready.txt` і копіює в буфер обміну Mac (pbcopy).

Запуск:
    .venv/bin/python scripts/export_railway_env.py
"""
import os
import sys
import json
import base64
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import BASE_DIR

OUTPUT_FILE = BASE_DIR / "railway_env_ready.txt"


def get_compact_tiktok_state(path: Path) -> bytes:
    """Видаляє 1.3 МБ зайвого localStorage, залишаючи лише сесійні cookies (~7 КБ)"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        compact = {
            "cookies": data.get("cookies", []),
            "origins": []
        }
        return json.dumps(compact).encode("utf-8")
    except Exception:
        return path.read_bytes()


def main():
    print("🚀 Генерація компактного пакету змінних для Railway...")
    lines = []

    # 1. Читаємо актуальний .env (без дублікатів і коментарів)
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line_str = line.strip()
                if line_str and not line_str.startswith("#") and "=" in line_str:
                    lines.append(line_str)

    # 2. Додаємо закодовані сесії
    session_files = [
        ("credentials/youtube_token.json", "YOUTUBE_TOKEN_B64", False),
        ("credentials/youtube_client_secrets.json", "YOUTUBE_SECRETS_B64", False),
        ("credentials/instagram_session.json", "INSTAGRAM_SESSION_B64", False),
        ("data/tiktok_channel_state.json", "TIKTOK_CHANNEL_STATE_B64", True),
        ("data/tiktok_state.json", "TIKTOK_STATE_B64", True),
        ("data/snapchat_state.json", "SNAPCHAT_STATE_B64", False),
    ]

    print("\n📦 Стиснення та кодування сесій:")
    for rel_path, env_name, is_tiktok in session_files:
        full_path = BASE_DIR / rel_path
        if full_path.exists():
            if is_tiktok:
                raw_bytes = get_compact_tiktok_state(full_path)
            else:
                raw_bytes = full_path.read_bytes()

            b64_str = base64.b64encode(raw_bytes).decode("utf-8")
            size_kb = len(b64_str) / 1024
            print(f"  • {env_name:<26} -> {size_kb:.1f} КБ (готово)")
            lines.append(f"{env_name}={b64_str}")
        else:
            print(f"  • ⚠️ {rel_path} не знайдено локально")

    # 3. Записуємо у файл
    content = "\n".join(lines) + "\n"
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(content)

    # 4. Копіюємо в буфер обміну macOS через pbcopy
    copied_to_clipboard = False
    try:
        proc = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
        proc.communicate(content.encode("utf-8"))
        if proc.returncode == 0:
            copied_to_clipboard = True
    except Exception:
        pass

    print("\n" + "=" * 65)
    print("🎉 УСПІШНО! ПАКЕТ ДЛЯ RAILWAY СТВОРЕНО")
    print("=" * 65)
    print(f"📁 Збережено у файл: {OUTPUT_FILE}")
    if copied_to_clipboard:
        print("📋 ВМІСТ АВТОМАТИЧНО СКОПІЙОВАНО В БУФЕР ОБМІНУ (Cmd+V)!")
    print("\n👉 Як додати у Railway за 5 секунд:")
    print("1. Відкрий свій проект у https://railway.app/")
    print("2. Перейди у вкладку 'Variables'")
    print("3. Натисни кнопку 'RAW Editor' (угорі праворуч)")
    print("4. Натисни Cmd+V (Вставити) і збережи!")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    main()
