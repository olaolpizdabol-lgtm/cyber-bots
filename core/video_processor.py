import subprocess
import shutil
import json
import logging
from pathlib import Path
from typing import Tuple, Optional, Dict, Any, List
from config import ANTI_DETECTION_CLEANING

logger = logging.getLogger(__name__)


class VideoProcessor:
    def __init__(self):
        self.ffmpeg_path = shutil.which("ffmpeg") or "ffmpeg"
        self.ffprobe_path = shutil.which("ffprobe") or "ffprobe"

    def get_video_info(self, file_path: str) -> Dict[str, Any]:
        """Отримує детальну інформацію про відео"""
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

            return {
                "width": width,
                "height": height,
                "duration": duration,
                "is_vertical": height > width if (height and width) else True,
                "aspect_ratio": round(width / height, 4) if height else 0.5625,
                "codec_name": codec_name,
                "has_audio": bool(audio_stream),
                "file_size": file_size,
                "file_size_mb": file_size_mb
            }
        except Exception as e:
            logger.error(f"Помилка аналізу відео через ffprobe: {e}")
            return {
                "width": 0, "height": 0, "duration": 0.0,
                "is_vertical": True, "aspect_ratio": 0.5625,
                "codec_name": "unknown", "has_audio": True,
                "file_size": file_size, "file_size_mb": file_size_mb
            }

    def check_video_issues(self, file_path: str) -> Dict[str, Any]:
        """Аналізує відео на проблеми з платформами"""
        info = self.get_video_info(file_path)
        issues: List[str] = []

        duration = info.get("duration", 0.0)
        width = info.get("width", 0)
        height = info.get("height", 0)
        aspect_ratio = info.get("aspect_ratio", 0.5625)
        codec_name = info.get("codec_name", "")
        file_size_mb = info.get("file_size_mb", 0.0)

        if 0 < duration < 3.0:
            issues.append(f"⏱ <b>Відео закоротке ({duration:.1f}с):</b> Instagram Reels та TikTok вимагають щонайменше 3 секунди.")
        elif duration > 60.0:
            issues.append(f"⏱ <b>Відео довше 60 секунд ({int(duration // 60)}хв {int(duration % 60)}с):</b> YouTube опублікує як звичайне відео, а не Shorts.")

        if width > 0 and height > 0:
            if width > height:
                issues.append(f"📐 <b>Горизонтальне відео ({width}x{height}):</b> Shorts, Reels та TikTok розраховані на 9:16.")
            elif width == height:
                issues.append(f"📐 <b>Квадратне відео ({width}x{height}):</b> не є стандартом 9:16.")
            elif aspect_ratio > 0.65:
                issues.append(f"📐 <b>Нестандартні пропорції ({width}x{height}):</b> відхиляються від 9:16.")

        if codec_name and codec_name not in ("h264", "avc1", "unknown"):
            issues.append(f"🎞 <b>Відеокодек {codec_name}:</b> платформи очікують H.264 (AVC).")

        if file_size_mb > 100:
            issues.append(f"📦 <b>Великий розмір ({file_size_mb:.1f} МБ):</b> завантаження триватиме довше.")

        return {
            "issues": issues,
            "has_issues": len(issues) > 0,
            "info": info
        }

    def clean_and_prepare_video(
        self,
        input_path: str,
        output_path: Optional[str] = None,
        force_optimize: bool = False
    ) -> str:
        """
        За замовчуванням повертає оригінальний файл як є!
        Якщо force_optimize=True, масштабує до 1080x1920 (9:16) H.264.
        """
        in_p = Path(input_path)
        if not in_p.exists():
            return str(in_p)

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


video_processor = VideoProcessor()
