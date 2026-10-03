import subprocess
import shutil
import json
import logging
from pathlib import Path
from typing import Tuple, Optional, Dict, Any
from config import ANTI_DETECTION_CLEANING

logger = logging.getLogger(__name__)


class VideoProcessor:
    def __init__(self):
        self.ffmpeg_path = shutil.which("ffmpeg") or "ffmpeg"
        self.ffprobe_path = shutil.which("ffprobe") or "ffprobe"

    def get_video_info(self, file_path: str) -> Dict[str, Any]:
        """Отримує інформацію про роздільну здатність, тривалість, кодеки відео"""
        cmd = [
            self.ffprobe_path,
            "-v", "error",
            "-show_entries", "stream=width,height,duration,r_frame_rate,codec_name",
            "-of", "json",
            file_path
        ]
        try:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            data = json.loads(result.stdout)
            streams = data.get("streams", [])
            video_stream = next((s for s in streams if "width" in s and "height" in s), {})
            width = int(video_stream.get("width", 0))
            height = int(video_stream.get("height", 0))
            duration = float(video_stream.get("duration", 0.0))
            return {
                "width": width,
                "height": height,
                "duration": duration,
                "is_vertical": height > width,
                "aspect_ratio": width / height if height else 0
            }
        except Exception as e:
            logger.error(f"Помилка аналізу відео через ffprobe: {e}")
            return {"width": 0, "height": 0, "duration": 0.0, "is_vertical": True, "aspect_ratio": 0.5625}

    def clean_and_prepare_video(self, input_path: str, output_path: Optional[str] = None) -> str:
        """
        Очищає метадані, перекодовує у чистий H.264/AAC, гарантує вертикальний формат
        та робить унікальний цифровий відбиток для уникнення блокувань (0 views jail).
        """
        in_p = Path(input_path)
        if not output_path:
            out_p = in_p.parent / f"clean_{in_p.name}"
        else:
            out_p = Path(output_path)

        if not ANTI_DETECTION_CLEANING:
            logger.info("Anti-detection cleaning вимкнено у налаштуваннях. Використовуємо оригінальний файл.")
            return str(in_p)

        logger.info(f"Обробка відео для обходу алгоритмів: {in_p.name} -> {out_p.name}")

        # Фільтр для тонкої мікро-модифікації (унікальний хеш без помітних оку змін)
        # eq: мікроскопічна зміна гами (1.0001) для зміни кожного байту пікселів
        # volume: мікроскопічна зміна гучності на 0.01 dB
        # scale: якщо не 9:16, масштабує до 1080:1920 із збереженням пропорцій
        vf_filters = [
            "scale=1080:1920:force_original_aspect_ratio=decrease",
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
            "eq=gamma=1.0002"
        ]
        vf_str = ",".join(vf_filters)

        cmd = [
            self.ffmpeg_path,
            "-y",
            "-i", str(in_p),
            "-vf", vf_str,
            "-af", "volume=1.001",
            "-c:v", "libx264",
            "-preset", "fast",
            "-profile:v", "high",
            "-level", "4.2",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "44100",
            "-map_metadata", "-1",         # Повне видалення всіх вихідних метаданих та тегів бота
            "-movflags", "+faststart",     # Оптимізація для веб-стрімінгу та швидкої обробки сервером
            str(out_p)
        ]

        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode != 0:
                logger.warning(f"ffmpeg обробка завершилась із помилкою: {res.stderr}. Залишаємо вихідний файл.")
                return str(in_p)
            logger.info(f"Відео успішно підготовлено та очищено: {out_p}")
            return str(out_p)
        except Exception as e:
            logger.error(f"Помилка запуску ffmpeg: {e}. Використовуємо вихідний файл.")
            return str(in_p)

    def extract_thumbnail(self, video_path: str, thumbnail_path: Optional[str] = None) -> Optional[str]:
        """Витягує перший красивий кадр відео (на 0.5с) як обкладинку"""
        v_p = Path(video_path)
        if not thumbnail_path:
            t_p = v_p.parent / f"thumb_{v_p.stem}.jpg"
        else:
            t_p = Path(thumbnail_path)

        cmd = [
            self.ffmpeg_path,
            "-y",
            "-ss", "00:00:00.500",
            "-i", str(v_p),
            "-vframes", "1",
            "-q:v", "2",
            str(t_p)
        ]
        try:
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            return str(t_p)
        except Exception as e:
            logger.error(f"Помилка створення обкладинки: {e}")
            return None


video_processor = VideoProcessor()
