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
    # ВІДЕО АНАЛІЗ ТА ПЕРЕВІРКА ПРОБЛЕМ
    # ==========================================

    def get_video_info(self, file_path: str) -> Dict[str, Any]:
        """
        Отримує повну технічну інформацію про відео:
        роздільна здатність, тривалість, кодек відео, аудіо та розмір файлу.
        """
        p = Path(file_path)
        file_size = p.stat().st_size if p.exists() else 0
        file_size_mb = round(file_size / (1024 * 1024), 2)

        cmd = [
            self.ffprobe_path,
            "-v", "error",
            "-show_entries", "stream=width,height,duration,r_frame_rate,codec_name,codec_type",
            "-show_entries", "format=duration,size",
            "-of", "json",
            str(file_path)
        ]
        try:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            data = json.loads(result.stdout)
            streams = data.get("streams", [])
            video_stream = next((s for s in streams if s.get("codec_type") == "video" or ("width" in s and "height" in s)), {})
            audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), {})
            fmt = data.get("format", {})

            width = int(video_stream.get("width", 0))
            height = int(video_stream.get("height", 0))
            raw_dur = video_stream.get("duration") or fmt.get("duration") or 0.0
            duration = round(float(raw_dur), 2)
            codec_name = (video_stream.get("codec_name") or "").lower()
            audio_codec = (audio_stream.get("codec_name") or "").lower()
            has_audio = bool(audio_stream)

            return {
                "width": width,
                "height": height,
                "duration": duration,
                "is_vertical": height > width if (height and width) else True,
                "aspect_ratio": round(width / height, 4) if height else 0.5625,
                "codec_name": codec_name,
                "audio_codec": audio_codec,
                "has_audio": has_audio,
                "file_size": file_size,
                "file_size_mb": file_size_mb
            }
        except Exception as e:
            logger.error(f"Помилка аналізу відео через ffprobe: {e}")
            return {
                "width": 0,
                "height": 0,
                "duration": 0.0,
                "is_vertical": True,
                "aspect_ratio": 0.5625,
                "codec_name": "unknown",
                "audio_codec": "",
                "has_audio": True,
                "file_size": file_size,
                "file_size_mb": file_size_mb
            }

    def check_video_issues(self, file_path: str) -> Dict[str, Any]:
        """
        Аналізує відео на потенційні проблеми з платформами (Shorts, Reels, TikTok):
        - Тривалість (< 3с або > 60с)
        - Співвідношення сторін (горизонтальне, квадратне, не 9:16)
        - Кодек (не H.264)
        - Розмір файлу (> 100 МБ)
        Повертає список проблем для попередження користувача.
        """
        info = self.get_video_info(file_path)
        issues: List[str] = []

        duration = info.get("duration", 0.0)
        width = info.get("width", 0)
        height = info.get("height", 0)
        aspect_ratio = info.get("aspect_ratio", 0.5625)
        codec_name = info.get("codec_name", "")
        file_size_mb = info.get("file_size_mb", 0.0)

        # 1. Перевірка тривалості
        if 0 < duration < 3.0:
            issues.append(f"⏱ <b>Відео закоротке ({duration:.1f}с):</b> Instagram Reels та TikTok вимагають щонайменше 3 секунди і відхилять ролик.")
        elif duration > 60.0:
            issues.append(f"⏱ <b>Відео довше 60 секунд ({int(duration // 60)}хв {int(duration % 60)}с):</b> YouTube класифікує його як звичайне відео, а не як Shorts.")

        # 2. Перевірка пропорцій / орієнтації
        if width > 0 and height > 0:
            if width > height:
                issues.append(f"📐 <b>Горизонтальне відео ({width}x{height}):</b> Shorts, Reels та TikTok розраховані на вертикальний формат 9:16. Відео відображатиметься з чорними смугами.")
            elif width == height:
                issues.append(f"📐 <b>Квадратне відео ({width}x{height}):</b> не є вертикальним стандартом 9:16.")
            elif aspect_ratio > 0.65:
                issues.append(f"📐 <b>Нестандартні пропорції ({width}x{height}):</b> відхиляються від вертикального 9:16.")

        # 3. Перевірка кодеку
        if codec_name and codec_name not in ("h264", "avc1", "unknown"):
            issues.append(f"🎞 <b>Відеокодек {codec_name}:</b> платформи (особливо Instagram) вимагають H.264 (AVC). З іншими кодеками завантаження може провалитися.")

        # 4. Перевірка розміру
        if file_size_mb > 100:
            issues.append(f"📦 <b>Великий розмір файлу ({file_size_mb:.1f} МБ):</b> завантаження може тривати довше.")

        return {
            "issues": issues,
            "has_issues": len(issues) > 0,
            "info": info
        }

    # ==========================================
    # ПІДГОТОВКА ВІДЕО ТА ОБКЛАДИНКИ
    # ==========================================

    def clean_and_prepare_video(
        self,
        input_path: str,
        output_path: Optional[str] = None,
        force_optimize: bool = False
    ) -> str:
        """
        Підготовка відео.
        За замовчуванням (force_optimize=False) повертає ОРИГІНАЛЬНИЙ файл без змін!
        Якщо force_optimize=True (користувач підтвердив оптимізацію):
        масштабує до 1080x1920 (9:16) та кодує у чистий H.264/AAC.
        """
        in_p = Path(input_path)
        if not in_p.exists():
            return str(in_p)

        # Якщо примусова оптимізація не вказана і anti-detection вимкнено — зберігаємо оригінал!
        if not force_optimize and not ANTI_DETECTION_CLEANING:
            return str(in_p)

        if not output_path:
            out_p = in_p.parent / f"opt_{in_p.name}"
        else:
            out_p = Path(output_path)

        info = self.get_video_info(str(in_p))
        duration = info.get("duration", 0.0)
        loop_args = []
        if 0 < duration < 3.0:
            loops = int(4.0 / duration) + 1
            loop_args = ["-stream_loop", str(loops)]
            logger.info(f"Відео коротке ({duration:.1f}с < 3с). Зациклюємо {loops} разів для сумісності з Reels/TikTok.")

        # Чистий scale + pad до 1080x1920 (без штучних спотворень гами та звуку!)
        vf_filters = [
            "scale=1080:1920:force_original_aspect_ratio=decrease",
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2"
        ]
        vf_str = ",".join(vf_filters)

        cmd = [
            self.ffmpeg_path,
            "-y",
            *loop_args,
            "-i", str(in_p),
            "-vf", vf_str,
            "-c:v", "libx264",
            "-crf", "18",
            "-preset", "fast",
            "-profile:v", "high",
            "-level", "4.2",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "44100",
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
    # ФОТО ТА КАРУСЕЛЬ ОБРОБКА
    # ==========================================

    def clean_and_prepare_image(
        self,
        input_path: str,
        target_platform: Optional[str] = None,
        force_optimize: bool = False
    ) -> str:
        """
        За замовчуванням повертає оригінальне фото як є!
        Якщо force_optimize=True, адаптує розміри під конкретну соцмережу.
        """
        in_p = Path(input_path)
        if not in_p.exists():
            return str(in_p)

        if not force_optimize and not ANTI_DETECTION_CLEANING:
            return str(in_p)

        prefix = f"{target_platform}_" if target_platform else ""
        out_p = in_p.parent / f"{prefix}clean_{in_p.name}"

        try:
            with Image.open(in_p) as img:
                img = ImageOps.exif_transpose(img)
                img = img.convert("RGB")

                target_size = None
                if target_platform == "pinterest":
                    target_size = (1000, 1500)
                elif target_platform in ("instagram", "threads"):
                    target_size = (1080, 1350)
                elif target_platform == "twitter":
                    target_size = (1200, 675)
                elif target_platform == "tiktok":
                    target_size = (1080, 1920)
                elif target_platform == "facebook":
                    target_size = (1200, 630)

                if target_size:
                    img = ImageOps.pad(img, target_size, color=(0, 0, 0))

                img.save(out_p, format="JPEG", quality=95, optimize=True)
                return str(out_p)
        except Exception as e:
            logger.error(f"Помилка обробки фото {input_path}: {e}")
            return str(input_path)

    def clean_carousel_images(self, image_paths: List[str], target_platform: Optional[str] = None, force_optimize: bool = False) -> List[str]:
        cleaned = []
        for p in image_paths:
            cleaned.append(self.clean_and_prepare_image(p, target_platform, force_optimize=force_optimize))
        return cleaned


media_processor = MediaProcessor()
video_processor = media_processor
