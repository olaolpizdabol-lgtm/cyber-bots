import subprocess
import shutil
import json
import logging
from pathlib import Path
from typing import Tuple, Optional, Dict, Any, List
from PIL import Image, ImageOps
from config import ANTI_DETECTION_CLEANING

logger = logging.getLogger(__name__)


class MediaProcessor:
    def __init__(self):
        self.ffmpeg_path = shutil.which("ffmpeg") or "ffmpeg"
        self.ffprobe_path = shutil.which("ffprobe") or "ffprobe"

    # ==========================================
    # ВІДЕО ОБРОБКА (FFmpeg Anti-Detection)
    # ==========================================

    def get_video_info(self, file_path: str) -> Dict[str, Any]:
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
        Очищає метадані відео, нормалізує у 1080x1920 (9:16),
        перекодовує в еталонний H.264/AAC і генерує унікальний цифровий хеш.
        """
        in_p = Path(input_path)
        if not output_path:
            out_p = in_p.parent / f"clean_{in_p.name}"
        else:
            out_p = Path(output_path)

        if not ANTI_DETECTION_CLEANING:
            return str(in_p)

        info = self.get_video_info(str(in_p))
        duration = info.get("duration", 0.0)
        loop_args = []
        if 0 < duration < 3.0:
            loops = int(4.0 / duration) + 1
            loop_args = ["-stream_loop", str(loops)]
            logger.info(f"Відео коротке ({duration:.1f}с < 3с). Зациклюємо {loops} разів для Reels.")

        vf_filters = [
            "scale=1080:1920:force_original_aspect_ratio=decrease",
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
            "eq=gamma=1.0002"
        ]
        vf_str = ",".join(vf_filters)

        cmd = [
            self.ffmpeg_path,
            "-y",
            *loop_args,
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
            "-map_metadata", "-1",
            "-movflags", "+faststart",
            str(out_p)
        ]

        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode != 0:
                logger.warning(f"ffmpeg обробка завершилась із помилкою: {res.stderr}")
                return str(in_p)
            return str(out_p)
        except Exception as e:
            logger.error(f"Помилка запуску ffmpeg: {e}")
            return str(in_p)

    def extract_thumbnail(self, video_path: str, thumbnail_path: Optional[str] = None) -> Optional[str]:
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

    # ==========================================
    # ФОТО ТА КАРУСЕЛЬ ОБРОБКА З РОЗРАХУНКОМ ПРОПОРЦІЙ
    # ==========================================

    def clean_and_prepare_image(self, input_path: str, target_platform: Optional[str] = None) -> str:
        """
        Очищає EXIF, адаптує пропорції під платформу:
        - Pinterest: 1000x1500 (2:3)
        - Instagram / Threads: 1080x1350 (4:5)
        - X (Twitter): 1200x675 (16:9)
        - TikTok Photo Mode: 1080x1920 (9:16)
        - Facebook: 1200x630
        та робить унікальний цифровий хеш пікселів.
        """
        in_p = Path(input_path)
        prefix = f"{target_platform}_" if target_platform else ""
        out_p = in_p.parent / f"{prefix}clean_{in_p.name}"

        try:
            with Image.open(in_p) as img:
                img = ImageOps.exif_transpose(img)
                img = img.convert("RGB")

                # Розрахунок пропорцій під платформу якщо задано
                target_size = None
                if target_platform == "pinterest":
                    target_size = (1000, 1500) # 2:3
                elif target_platform in ("instagram", "threads"):
                    target_size = (1080, 1350) # 4:5
                elif target_platform == "twitter":
                    target_size = (1200, 675)  # 16:9
                elif target_platform == "tiktok":
                    target_size = (1080, 1920) # 9:16
                elif target_platform == "facebook":
                    target_size = (1200, 630)  # Landscape 1.91:1

                if target_size:
                    # Робимо акуратне масштабування з паддінгом (без обрізання країв)
                    img = ImageOps.pad(img, target_size, color=(0, 0, 0))

                # Унікальний хеш пікселів
                pixels = img.load()
                r, g, b = pixels[0, 0]
                pixels[0, 0] = ((r + 1) % 256, g, b)

                img.save(out_p, format="JPEG", quality=95, optimize=True)
                return str(out_p)
        except Exception as e:
            logger.error(f"Помилка обробки фото {input_path}: {e}")
            return str(input_path)

    def clean_carousel_images(self, image_paths: List[str], target_platform: Optional[str] = None) -> List[str]:
        cleaned = []
        for p in image_paths:
            cleaned.append(self.clean_and_prepare_image(p, target_platform))
        return cleaned


media_processor = MediaProcessor()
video_processor = media_processor
