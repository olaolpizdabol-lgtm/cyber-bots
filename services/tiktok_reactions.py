"""
🎬 TikTok Reactions Engine - Автоматичні реакції у стилі Боді (2026)

Функціонал:
1. Завантаження TikTok відео за посиланням (через yt-dlp).
2. Мультимодальний аналіз відео / аудіо / опису через Gemini AI.
3. Генерація реакції у фірмовому стилі Боді з експорту чатів (іронічний, влучний, саркастичний,
   молодіжний, "одааа", "та похуй", "сігма", "це нормально?", без цензурної душноти та асистентських кліше).
4. Сувора типографіка: ТІЛЬКИ дефіс '-', нуль довгих тире.
5. Логування в SQLite та готовність до відправки в TikTok/Telegram.
"""
import os
import re
import json
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

from config import BASE_DIR, TEMP_DIR
from core.database import save_tiktok_reaction_log, get_recent_tiktok_reactions
from services.gemini_ai import gemini_service, sanitize_typography

logger = logging.getLogger(__name__)

TIKTOK_DOWNLOADS_DIR = TEMP_DIR / "tiktok_reactions"
TIKTOK_DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

# Спеціальний системний промпт для реакцій у стилі Боді (з 10 файлів експорту чату)
BOHDAN_REACTION_PROMPT = """
Ти - Бодя (Богдан). Тобі скинули тікток (або ти дивишся тікток кента чи знайомого).
Напиши коротку (1-3 речення), живу, автентичну реакцію на це відео ТОЧНО так, як Бодя відповідає в особистих повідомленнях Telegram:

ТВІЙ ХАРАКТЕР ТА СТИЛЬ СПІЛКУВАННЯ:
1. Жива, розмовна українська мова, дотепний молодіжний сленг, сарказм, іронія, прямота.
2. Фірмові вирази та вайб (використовуй доречно):
   - "одааа", "ахуєнно", "це нормально взагалі?", "та похуй", "чекни", "сігма", "чистий сігма момент",
   - "це база", "кстаааатііі", "шо це за хуня", "пацан міг просто...", "турікоголовий рівень", "це важливо".
3. Як ти реагуєш:
   - Якщо відео крінжове або дивне: саркастичний підкол, іронічне здивування ("Це нормально блять?", "Пацан міг просто не позоритися").
   - If відео топ/естетика/круте: щирий захват або схвалення ("Одааа, чисто сігма мув", "Ахуєнно зроблено, збережу").
   - Якщо мем/гумор: короткий смішний коментар або відсилка до життя ("Це на рівні сані малого", "Чисто ми в п'ятницю").
4. СУВОРЕ ПРАВИЛО ТИПОГРАФІКИ: ТІЛЬКИ звичайний дефіс '-', НІКОЛИ не став довге тире '—' або '–'!
5. НІЯКИХ ШІ-кліше ("Привіт!", "Ось мій відгук", "Цікаве відео", "Я вважаю"). Тільки чиста реакція людини в чаті!
"""

# Офлайн-шаблони реакцій Боді для друзів (якщо немає інтернету/API)
BOHDAN_OFFLINE_REACTIONS = [
    "одааа, чисто сігма мув 😎",
    "це нормально взагалі? пацан міг просто промовчати 💀",
    "ахуєнно, включи на фоні",
    "та похуй, головне шоб туріков не побачив 😂",
    "чекни кінець, там найцікавіше",
    "це настільки геніально, шо навіть не знаю шо сказати",
    "йоу, ти вибрав не ту цивілізацію",
    "це база, чисто ми після трьох ночі",
    "це важливо, перекинь у групу 🤙"
]

# Спеціальний системний промпт для реакцій у стилі Боді для дівчини
BOHDAN_GIRLFRIEND_REACTION_PROMPT = """
Ти - Бодя (Богдан). Твоя кохана дівчина надіслала тобі TikTok відео в особисті повідомлення.
Напиши коротку (1-2 речення), живу, теплу, дотепну або закохану реакцію на це відео:

СТИЛЬ СПІЛКУВАННЯ З ДІВЧИНОЮ:
1. Теплий, ніжний, з гумором, щирий. Додавай милі смайлики (❤️, 🥰, 😂, 💕, ✨).
2. Якщо відео миле / тварини / романтика / естетика:
   - "Боже яке миле кошеня 🥰", "Ахаха це чисто ми з тобою ❤️", "Оце естетика, зберіг 💕"
3. Якщо відео смішне / життєве / мем:
   - "Ахахаха жиза 😂", "Це просто розрив, скинь ще 😂❤️", "Чисто твій вайб зранку 🥰"
4. СУВОРЕ ПРАВИЛО ТИПОГРАФІКИ: ТІЛЬКИ звичайний дефіс '-', НІКОЛИ не став довге тире '—' або '–'!
5. НІЯКИХ ШІ-кліше ("Привіт!", "Ось мій відгук", "Цікаве відео"). Тільки жива реакція в чаті!
"""

GIRLFRIEND_OFFLINE_REACTIONS = [
    "Ахахаха це чисто ми з тобою 😂❤️",
    "Боже, яке миле кошеня 🥰 збережу собі!",
    "Ахаха це розрив просто 😂 скидай ще!",
    "Оце естетика, дуже красиво ✨💕",
    "Чисто твій настрій сьогодні зранку 🥰❤️",
    "Ахахах я не можу, де ти таке знаходиш 😂❤️"
]


class TikTokReactionsService:
    def __init__(self):
        self.output_dir = TIKTOK_DOWNLOADS_DIR

    def is_tiktok_url(self, text: str) -> bool:
        """Перевіряє чи текст містить посилання на TikTok"""
        if not text:
            return False
        pattern = r"(https?://(?:www\.|vm\.|vt\.)?tiktok\.com/[^\s]+)"
        return bool(re.search(pattern, text))

    def extract_tiktok_url(self, text: str) -> Optional[str]:
        """Витягує посилання на TikTok із тексту"""
        pattern = r"(https?://(?:www\.|vm\.|vt\.)?tiktok\.com/[^\s]+)"
        match = re.search(pattern, text)
        return match.group(1) if match else None

    def download_tiktok_video(self, url: str) -> Tuple[Optional[str], Dict[str, Any]]:
        """
        Завантажує відео з TikTok за допомогою yt-dlp.
        Повертає (шлях до файлу, метадані відео).
        """
        clean_url = url.strip()
        import time
        unique_prefix = f"tt_{int(time.time())}_{abs(hash(clean_url)) % 100000}"
        out_template = str(self.output_dir / f"{unique_prefix}_%(id)s.%(ext)s")
        meta = {
            "title": "",
            "uploader": "",
            "description": "",
            "duration": 0
        }

        try:
            import sys
            # Викликаємо yt-dlp через поточний python інтерпретатор
            cmd = [
                sys.executable, "-m", "yt_dlp",
                "--no-playlist",
                "-f", "b[ext=mp4]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best",
                "-o", out_template,
                "--write-info-json",
                "--max-filesize", "80M",
                clean_url
            ]
            logger.info(f"Завантаження TikTok через yt-dlp: {clean_url}")
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=60
            )

            # Шукаємо щойно завантажений файл із відповідним префіксом
            matched_files = sorted(
                list(self.output_dir.glob(f"{unique_prefix}_*.mp4")),
                key=os.path.getmtime,
                reverse=True
            )

            if matched_files:
                target_f = matched_files[0]
                meta_json = target_f.with_suffix(".info.json")
                if meta_json.exists():
                    try:
                        with open(meta_json, "r", encoding="utf-8") as jfp:
                            info = json.load(jfp)
                            meta["title"] = info.get("title", "")
                            meta["uploader"] = info.get("uploader", "")
                            meta["description"] = info.get("description", "")
                            meta["duration"] = info.get("duration", 0)
                    except Exception:
                        pass
                return str(target_f), meta

            # Якщо відео не зберіглося як mp4, спробуємо знайти будь-який найновіший файл
            all_mp4s = sorted(list(self.output_dir.glob("*.mp4")), key=os.path.getmtime, reverse=True)
            if all_mp4s:
                return str(all_mp4s[0]), meta

            # Якщо завантаження відео заблоковано - витягуємо метадані через dump-json для аналізу
            dump_cmd = [sys.executable, "-m", "yt_dlp", "--dump-json", "--no-playlist", clean_url]
            dump_proc = subprocess.run(dump_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15)
            if dump_proc.returncode == 0 and dump_proc.stdout.strip():
                try:
                    info = json.loads(dump_proc.stdout.strip())
                    meta["title"] = info.get("title", "")
                    meta["uploader"] = info.get("uploader", "")
                    meta["description"] = info.get("description", "")
                    meta["duration"] = info.get("duration", 0)
                except Exception:
                    pass

        except Exception as e:
            logger.warning(f"yt-dlp не зміг завантажити напряму: {e}")

        # Очищення старих тимчасових файлів (> 24 годин)
        self.cleanup_old_downloads(max_age_hours=24)

        return None, meta

    def cleanup_old_downloads(self, max_age_hours: int = 24):
        """Очищує завантажені тимчасові файли, старші за вказаний час"""
        import time
        now = time.time()
        max_age_sec = max_age_hours * 3600
        try:
            for p in self.output_dir.iterdir():
                if p.is_file() and (now - p.stat().st_mtime) > max_age_sec:
                    try:
                        p.unlink()
                    except Exception:
                        pass
        except Exception:
            pass

    def generate_reaction(
        self,
        video_path: Optional[str] = None,
        video_meta: Optional[Dict[str, Any]] = None,
        custom_note: Optional[str] = None
    ) -> str:
        """
        Генерує реакцію в стилі Боді через Gemini AI з відео або метаданими.
        """
        meta = video_meta or {}
        title = meta.get("title", "")
        uploader = meta.get("uploader", "")
        desc = meta.get("description", "")

        context_prompt = BOHDAN_REACTION_PROMPT
        user_content = f"""
Контекст TikTok відео:
- Автор: @{uploader or 'невідомий'}
- Заголовок/опис: {title or desc or 'Без опису'}
{f'- Додаткова нотатка: {custom_note}' if custom_note else ''}

Напиши твою коротку фірмову реакцію на це відео (1-2 речення, тільки дефіс '-', стиль Боді):
"""

        # Спроба генерації через Gemini
        if gemini_service.api_key and not gemini_service.api_key.startswith("AIzaSyYour"):
            try:
                # Якщо є файл відео і новий SDK
                uploaded_file = None
                if video_path and os.path.exists(video_path) and getattr(gemini_service, "is_new_sdk", False) and gemini_service.client:
                    try:
                        f_res = gemini_service.client.files.upload(file=video_path)
                        uploaded_file = f_res.name
                    except Exception:
                        uploaded_file = None

                contents = [context_prompt, user_content]
                if uploaded_file and gemini_service.client:
                    contents.append(gemini_service.client.files.get(name=uploaded_file))

                resp = gemini_service.generate_content(contents)
                if resp:
                    clean_res = sanitize_typography(resp.text.strip())
                    if clean_res:
                        return clean_res
            except Exception as e:
                logger.error(f"Помилка Gemini при генерації реакції на TikTok: {e}")

        # Демо / Fallback реакція в стилі Боді
        import random
        return sanitize_typography(random.choice(BOHDAN_OFFLINE_REACTIONS))

    def process_tiktok_link(self, url: str, custom_note: Optional[str] = None) -> Dict[str, Any]:
        """
        Повний цикл: завантаження -> Gemini аналіз -> реакція -> лог
        """
        video_path, meta = self.download_tiktok_video(url)
        reaction_text = self.generate_reaction(video_path, meta, custom_note)

        # Зберігаємо в БД
        save_tiktok_reaction_log(
            video_url=url,
            author_username=meta.get("uploader"),
            video_title=meta.get("title"),
            summary_content=meta.get("description"),
            reaction_text=reaction_text,
            status="success"
        )

        return {
            "success": True,
            "url": url,
            "uploader": meta.get("uploader", "TikTok"),
            "title": meta.get("title", ""),
            "video_path": video_path,
            "reaction": reaction_text
        }


# Глобальний екземпляр сервісу
tiktok_reactions_service = TikTokReactionsService()
