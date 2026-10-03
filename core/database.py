import sqlite3
import json
from typing import Optional, Dict, Any, List
from config import DB_PATH, DEFAULT_AI_PROMPT
from core.content_type import ContentType


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
    except Exception:
        pass
    return conn


def init_db():
    with get_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content_type TEXT DEFAULT 'video',
                media_paths TEXT,
                video_path TEXT,
                clean_video_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                
                -- YouTube Shorts
                yt_title TEXT,
                yt_desc TEXT,
                yt_video_id TEXT,
                yt_views INTEGER DEFAULT 0,
                yt_likes INTEGER DEFAULT 0,
                
                -- Instagram (Reels / Photo / Carousel)
                ig_caption TEXT,
                ig_media_id TEXT,
                ig_views INTEGER DEFAULT 0,
                ig_likes INTEGER DEFAULT 0,
                
                -- TikTok (Video / Photo Mode)
                tt_caption TEXT,
                tt_video_id TEXT,
                tt_views INTEGER DEFAULT 0,
                tt_likes INTEGER DEFAULT 0,
                
                -- Facebook (Reels / Photos / Posts)
                fb_caption TEXT,
                fb_video_id TEXT,
                fb_views INTEGER DEFAULT 0,
                fb_likes INTEGER DEFAULT 0,
                
                -- Snapchat Spotlight
                snap_title TEXT,
                snap_media_id TEXT,
                snap_views INTEGER DEFAULT 0,
                snap_likes INTEGER DEFAULT 0,
                
                -- X (Twitter Video / Photo / Text)
                tw_post TEXT,
                tw_tweet_id TEXT,
                tw_views INTEGER DEFAULT 0,
                tw_likes INTEGER DEFAULT 0,
                
                -- Threads (Video / Carousel / Text)
                threads_post TEXT,
                threads_media_id TEXT,
                threads_views INTEGER DEFAULT 0,
                threads_likes INTEGER DEFAULT 0,
                
                -- Pinterest (Idea Pins / Video / Image)
                pin_title TEXT,
                pin_desc TEXT,
                pin_id TEXT,
                pin_views INTEGER DEFAULT 0,
                pin_likes INTEGER DEFAULT 0,
                
                -- Bluesky (Video / Image / Text)
                bsky_post TEXT,
                bsky_uri TEXT,
                bsky_views INTEGER DEFAULT 0,
                bsky_likes INTEGER DEFAULT 0,
                
                status TEXT DEFAULT 'draft',
                error_message TEXT
            )
        """)
        
        # Перевіряємо та додаємо нові колонки якщо таблиця створена раніше
        existing_cols = [r[1] for r in cursor.execute("PRAGMA table_info(posts)").fetchall()]
        cols_to_ensure = [
            ("content_type", "TEXT DEFAULT 'video'"),
            ("media_paths", "TEXT"),
            ("fb_caption", "TEXT"), ("fb_video_id", "TEXT"), ("fb_views", "INTEGER DEFAULT 0"), ("fb_likes", "INTEGER DEFAULT 0"),
            ("snap_title", "TEXT"), ("snap_media_id", "TEXT"), ("snap_views", "INTEGER DEFAULT 0"), ("snap_likes", "INTEGER DEFAULT 0"),
            ("tw_post", "TEXT"), ("tw_tweet_id", "TEXT"), ("tw_views", "INTEGER DEFAULT 0"), ("tw_likes", "INTEGER DEFAULT 0"),
            ("threads_post", "TEXT"), ("threads_media_id", "TEXT"), ("threads_views", "INTEGER DEFAULT 0"), ("threads_likes", "INTEGER DEFAULT 0"),
            ("pin_title", "TEXT"), ("pin_desc", "TEXT"), ("pin_id", "TEXT"), ("pin_views", "INTEGER DEFAULT 0"), ("pin_likes", "INTEGER DEFAULT 0"),
            ("bsky_post", "TEXT"), ("bsky_uri", "TEXT"), ("bsky_views", "INTEGER DEFAULT 0"), ("bsky_likes", "INTEGER DEFAULT 0")
        ]
        for col_name, col_def in cols_to_ensure:
            if col_name not in existing_cols:
                try:
                    cursor.execute(f"ALTER TABLE posts ADD COLUMN {col_name} {col_def}")
                except Exception:
                    pass

        # Налаштування
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        
        # Автоматизація #2: TikTok вогники (Streaks) та акаунт дівчини
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tiktok_streak_targets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                nickname TEXT,
                is_girlfriend BOOLEAN DEFAULT 0,
                custom_message TEXT,
                last_sent_at TIMESTAMP,
                streak_count INTEGER DEFAULT 0,
                active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tiktok_streak_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_username TEXT NOT NULL,
                is_girlfriend BOOLEAN DEFAULT 0,
                message_text TEXT NOT NULL,
                status TEXT NOT NULL,
                error TEXT,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Бот "Кібер Рижий" та "Кібер Саня Туріков": історія повідомлень у групі/чатах та пам'ять
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cyber_rizhyi_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                chat_type TEXT,
                user_id INTEGER NOT NULL,
                username TEXT,
                first_name TEXT,
                message_text TEXT,
                has_photo BOOLEAN DEFAULT 0,
                photo_desc TEXT,
                reply_text TEXT,
                bot_persona TEXT DEFAULT 'rizhyi',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cols_msgs = [r[1] for r in cursor.execute("PRAGMA table_info(cyber_rizhyi_messages)").fetchall()]
        if "bot_persona" not in cols_msgs:
            try:
                cursor.execute("ALTER TABLE cyber_rizhyi_messages ADD COLUMN bot_persona TEXT DEFAULT 'rizhyi'")
            except Exception:
                pass
        if "reply_to_user_id" not in cols_msgs:
            try:
                cursor.execute("ALTER TABLE cyber_rizhyi_messages ADD COLUMN reply_to_user_id INTEGER")
            except Exception:
                pass
        if "reply_to_name" not in cols_msgs:
            try:
                cursor.execute("ALTER TABLE cyber_rizhyi_messages ADD COLUMN reply_to_name TEXT")
            except Exception:
                pass
        if "reply_to_msg_text" not in cols_msgs:
            try:
                cursor.execute("ALTER TABLE cyber_rizhyi_messages ADD COLUMN reply_to_msg_text TEXT")
            except Exception:
                pass

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cyber_rizhyi_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, key)
            )
        """)

        # Логи реакцій на TikTok відео у стилі Боді
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tiktok_reactions_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_url TEXT,
                author_username TEXT,
                video_title TEXT,
                summary_content TEXT,
                reaction_text TEXT NOT NULL,
                status TEXT DEFAULT 'success',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Колекція збережених стікерів та GIF для використання ботом
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cyber_collected_media (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                media_type TEXT NOT NULL, -- 'sticker', 'animation', 'video_note'
                file_id TEXT UNIQUE NOT NULL,
                file_unique_id TEXT,
                emoji TEXT,
                set_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Міжботовий міст (Inter-Bot Bridge) для діалогів між Рижим і Туріковим
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cyber_bot_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                from_bot TEXT NOT NULL,         -- 'rizhyi' або 'turikov'
                to_bot TEXT NOT NULL,           -- 'turikov' або 'rizhyi'
                message_id INTEGER,             -- telegram message_id
                text TEXT NOT NULL,             -- текст репліки
                consecutive_count INTEGER DEFAULT 0, -- лічильник обмінів між ботами (анти-луп)
                processed INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cols_ev = [r[1] for r in cursor.execute("PRAGMA table_info(cyber_bot_events)").fetchall()]
        for col_name, col_type in [
            ("sender_user_id", "INTEGER"),
            ("sender_username", "TEXT"),
            ("sender_first_name", "TEXT"),
            ("reply_to_name", "TEXT")
        ]:
            if col_name not in cols_ev:
                try:
                    cursor.execute(f"ALTER TABLE cyber_bot_events ADD COLUMN {col_name} {col_type}")
                except Exception:
                    pass

        # AI-витягнуті факти з чату (LLM memory extraction)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cyber_chat_facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                fact TEXT NOT NULL,
                source_username TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Персональна пам'ять про конкретних юзерів (витягнута AI)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cyber_user_facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT,
                display_name TEXT,
                fact TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("SELECT value FROM settings WHERE key = 'ai_prompt'")
        row = cursor.fetchone()
        if not row:
            cursor.execute("INSERT INTO settings (key, value) VALUES ('ai_prompt', ?)", (DEFAULT_AI_PROMPT,))
        elif "Проаналізуй це коротке вертикальне відео" in row["value"]:
            cursor.execute("UPDATE settings SET value = ? WHERE key = 'ai_prompt'", (DEFAULT_AI_PROMPT,))
            
        conn.commit()


def save_draft_post(
    content_type: ContentType,
    media_paths: List[str],
    metadata: Dict[str, Any]
) -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        primary_video = media_paths[0] if media_paths and content_type == ContentType.VIDEO else ""
        paths_json = json.dumps(media_paths)

        cursor.execute("""
            INSERT INTO posts (
                content_type, media_paths, video_path, clean_video_path,
                yt_title, yt_desc,
                ig_caption, tt_caption, fb_caption,
                snap_title, tw_post, threads_post,
                pin_title, pin_desc, bsky_post,
                status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft')
        """, (
            content_type.value, paths_json, primary_video, primary_video,
            metadata.get("youtube_title"), metadata.get("youtube_desc"),
            metadata.get("ig_caption"), metadata.get("tt_caption"), metadata.get("fb_caption"),
            metadata.get("snapchat_title"), metadata.get("twitter_post"), metadata.get("threads_post"),
            metadata.get("pinterest_title"), metadata.get("pinterest_desc"), metadata.get("bluesky_post")
        ))
        conn.commit()
        return cursor.lastrowid


def update_post_platform_result(
    post_id: int,
    platform: str,
    external_id: Optional[str] = None,
    error: Optional[str] = None
):
    col_map = {
        "youtube": "yt_video_id",
        "instagram": "ig_media_id",
        "tiktok": "tt_video_id",
        "facebook": "fb_video_id",
        "snapchat": "snap_media_id",
        "twitter": "tw_tweet_id",
        "threads": "threads_media_id",
        "pinterest": "pin_id",
        "bluesky": "bsky_uri"
    }
    col = col_map.get(platform)
    if not col:
        return

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE posts SET {col} = ? WHERE id = ?", (external_id, post_id))
        if error:
            cursor.execute("UPDATE posts SET error_message = ? WHERE id = ?", (error, post_id))
        conn.commit()


def update_post_status(post_id: int, status: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE posts SET status = ? WHERE id = ?", (status, post_id))
        conn.commit()


def update_post_platform_stats(post_id: int, platform: str, views: int, likes: int):
    view_col_map = {
        "youtube": ("yt_views", "yt_likes"),
        "instagram": ("ig_views", "ig_likes"),
        "tiktok": ("tt_views", "tt_likes"),
        "facebook": ("fb_views", "fb_likes"),
        "snapchat": ("snap_views", "snap_likes"),
        "twitter": ("tw_views", "tw_likes"),
        "threads": ("threads_views", "threads_likes"),
        "pinterest": ("pin_views", "pin_likes"),
        "bluesky": ("bsky_views", "bsky_likes")
    }
    cols = view_col_map.get(platform)
    if not cols:
        return

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE posts SET {cols[0]} = ?, {cols[1]} = ? WHERE id = ?", (views, likes, post_id))
        conn.commit()


def get_post_by_id(post_id: int) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM posts WHERE id = ?", (post_id,))
        row = cursor.fetchone()
        if not row:
            return None
        res = dict(row)
        if res.get("media_paths"):
            try:
                res["media_paths_list"] = json.loads(res["media_paths"])
            except Exception:
                res["media_paths_list"] = []
        else:
            res["media_paths_list"] = []
        return res


def get_last_published_post() -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM posts 
            WHERE yt_video_id IS NOT NULL OR ig_media_id IS NOT NULL OR tt_video_id IS NOT NULL
               OR fb_video_id IS NOT NULL OR snap_media_id IS NOT NULL OR tw_tweet_id IS NOT NULL
               OR threads_media_id IS NOT NULL OR pin_id IS NOT NULL OR bsky_uri IS NOT NULL
            ORDER BY id DESC LIMIT 1
        """)
        row = cursor.fetchone()
        return dict(row) if row else None


def get_recent_posts(limit: int = 5) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM posts ORDER BY id DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]


def get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row["value"] if row else default


def set_setting(key: str, value: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """, (key, value))
        conn.commit()


def update_post_metadata(post_id: int, metadata: Dict[str, Any]):
    """Оновлює текстові поля метаданих публікації (після скорочення чи редагування)"""
    col_mapping = {
        "youtube_title": "yt_title",
        "youtube_desc": "yt_desc",
        "ig_caption": "ig_caption",
        "tt_caption": "tt_caption",
        "fb_caption": "fb_caption",
        "snapchat_title": "snap_title",
        "twitter_post": "tw_post",
        "threads_post": "threads_post",
        "pinterest_title": "pin_title",
        "pinterest_desc": "pin_desc",
        "bluesky_post": "bsky_post"
    }
    with get_connection() as conn:
        cursor = conn.cursor()
        for meta_key, col_name in col_mapping.items():
            if meta_key in metadata:
                cursor.execute(f"UPDATE posts SET {col_name} = ? WHERE id = ?", (metadata[meta_key], post_id))
            elif col_name in metadata:
                cursor.execute(f"UPDATE posts SET {col_name} = ? WHERE id = ?", (metadata[col_name], post_id))
        conn.commit()


# ==========================================
# АВТОМАТИЗАЦІЯ #2: TIKTOK ВОГНИКИ (STREAKS) ТА АКАУНТ ДІВЧИНИ
# ==========================================

def get_streak_targets(active_only: bool = True) -> List[Dict[str, Any]]:
    """Повертає список контактів для щоденних вогників"""
    with get_connection() as conn:
        cursor = conn.cursor()
        if active_only:
            cursor.execute("SELECT * FROM tiktok_streak_targets WHERE active = 1 ORDER BY is_girlfriend DESC, id ASC")
        else:
            cursor.execute("SELECT * FROM tiktok_streak_targets ORDER BY is_girlfriend DESC, id ASC")
        rows = cursor.fetchall()
        return [dict(r) for r in rows]


def get_streak_target_by_username(username: str) -> Optional[Dict[str, Any]]:
    clean_user = username.strip().lstrip("@")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tiktok_streak_targets WHERE LOWER(username) = LOWER(?)", (clean_user,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_girlfriend_target() -> Optional[Dict[str, Any]]:
    """Повертає збережений акаунт дівчини"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tiktok_streak_targets WHERE is_girlfriend = 1 AND active = 1 LIMIT 1")
        row = cursor.fetchone()
        return dict(row) if row else None


def set_girlfriend_target(username: str, nickname: Optional[str] = "Кохана") -> None:
    """Встановлює або оновлює акаунт дівчини для відправки сердечок"""
    clean_user = username.strip().lstrip("@")
    with get_connection() as conn:
        cursor = conn.cursor()
        # Скидаємо прапорець дівчини з попередніх акаунтів (дівчина тільки одна!)
        cursor.execute("UPDATE tiktok_streak_targets SET is_girlfriend = 0 WHERE is_girlfriend = 1")
        cursor.execute("""
            INSERT INTO tiktok_streak_targets (username, nickname, is_girlfriend, active)
            VALUES (?, ?, 1, 1)
            ON CONFLICT(username) DO UPDATE SET
                is_girlfriend = 1,
                nickname = excluded.nickname,
                active = 1
        """, (clean_user, nickname or "Кохана"))
        conn.commit()


def add_streak_target(username: str, nickname: Optional[str] = None, is_girlfriend: bool = False, custom_message: Optional[str] = None) -> int:
    """Додає друга до щоденних вогників"""
    clean_user = username.strip().lstrip("@")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO tiktok_streak_targets (username, nickname, is_girlfriend, custom_message, active)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(username) DO UPDATE SET
                nickname = COALESCE(excluded.nickname, nickname),
                is_girlfriend = excluded.is_girlfriend,
                custom_message = excluded.custom_message,
                active = 1
        """, (clean_user, nickname, 1 if is_girlfriend else 0, custom_message))
        conn.commit()
        return cursor.lastrowid


def remove_streak_target(username: str) -> bool:
    """Видаляє акаунт зі списку вогників"""
    clean_user = username.strip().lstrip("@")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tiktok_streak_targets WHERE LOWER(username) = LOWER(?)", (clean_user,))
        deleted = cursor.rowcount > 0
        conn.commit()
        return deleted


def update_streak_target_sent(username: str, streak_count: Optional[int] = None) -> None:
    """Оновлює час відправки та збільшує лічильник серії (streak count)"""
    clean_user = username.strip().lstrip("@")
    with get_connection() as conn:
        cursor = conn.cursor()
        if streak_count is not None:
            cursor.execute("""
                UPDATE tiktok_streak_targets
                SET last_sent_at = CURRENT_TIMESTAMP, streak_count = ?
                WHERE LOWER(username) = LOWER(?)
            """, (streak_count, clean_user))
        else:
            cursor.execute("""
                UPDATE tiktok_streak_targets
                SET last_sent_at = CURRENT_TIMESTAMP, streak_count = streak_count + 1
                WHERE LOWER(username) = LOWER(?)
            """, (clean_user,))
        conn.commit()


def save_streak_log(target_username: str, is_girlfriend: bool, message_text: str, status: str, error: Optional[str] = None) -> int:
    """Зберігає запис у лог відправок вогників"""
    clean_user = target_username.strip().lstrip("@")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO tiktok_streak_logs (target_username, is_girlfriend, message_text, status, error)
            VALUES (?, ?, ?, ?, ?)
        """, (clean_user, 1 if is_girlfriend else 0, message_text, status, error))
        conn.commit()
        return cursor.lastrowid


def get_recent_streak_logs(limit: int = 10) -> List[Dict[str, Any]]:
    """Повертає останні логи відправки вогників"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tiktok_streak_logs ORDER BY id DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]


def get_streak_stats() -> Dict[str, Any]:
    """Зведена статистика по вогниках"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as total FROM tiktok_streak_targets WHERE active = 1")
        total_targets = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) as gf_count FROM tiktok_streak_targets WHERE is_girlfriend = 1 AND active = 1")
        has_gf = cursor.fetchone()["gf_count"] > 0

        cursor.execute("SELECT COUNT(*) as sent_today FROM tiktok_streak_logs WHERE DATE(sent_at) = DATE('now') AND status IN ('sent', 'dry_run')")
        sent_today = cursor.fetchone()["sent_today"]

        cursor.execute("SELECT MAX(streak_count) as max_streak FROM tiktok_streak_targets")
        max_streak_row = cursor.fetchone()
        max_streak = max_streak_row["max_streak"] if max_streak_row and max_streak_row["max_streak"] else 0

        return {
            "total_targets": total_targets,
            "has_girlfriend": has_gf,
            "sent_today": sent_today,
            "max_streak": max_streak
        }


# ---------------------------------------------------------
# БОТ "КІБЕР РИЖИЙ": МЕТОДИ ПАМ'ЯТІ ТА КОНТЕКСТУ
# ---------------------------------------------------------

def save_cyber_rizhyi_message(
    chat_id: int,
    chat_type: str,
    user_id: int,
    username: Optional[str],
    first_name: Optional[str],
    message_text: str,
    has_photo: bool = False,
    photo_desc: Optional[str] = None,
    reply_text: Optional[str] = None,
    bot_persona: str = "rizhyi",
    reply_to_user_id: Optional[int] = None,
    reply_to_name: Optional[str] = None,
    reply_to_msg_text: Optional[str] = None
) -> int:
    """Зберігає повідомлення у чаті/групі для пам'яті Кібер Рижого або Сані Турікова"""
    with get_connection() as conn:
        cursor = conn.cursor()
        # Захист від подвійного збереження того самого вхідного повідомлення без відповіді
        if not reply_text and message_text:
            cursor.execute("""
                SELECT id FROM cyber_rizhyi_messages
                WHERE chat_id = ? AND user_id = ? AND message_text = ? AND reply_text IS NULL
                ORDER BY id DESC LIMIT 1
            """, (chat_id, user_id, message_text))
            if cursor.fetchone():
                return 0

        cursor.execute("""
            INSERT INTO cyber_rizhyi_messages (
                chat_id, chat_type, user_id, username, first_name,
                message_text, has_photo, photo_desc, reply_text, bot_persona,
                reply_to_user_id, reply_to_name, reply_to_msg_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            chat_id, chat_type, user_id, username, first_name,
            message_text, 1 if has_photo else 0, photo_desc, reply_text, bot_persona,
            reply_to_user_id, reply_to_name, reply_to_msg_text
        ))
        conn.commit()
        return cursor.lastrowid


def cleanup_cyber_rizhyi_expired_messages(hours: float = 72.0, keep_last: int = 60) -> int:
    """
    Видаляє застарілі повідомлення з пам'яті (TTL за замовчуванням 72 години),
    АЛЕ гарантовано зберігає останні keep_last повідомлень для кожного чату!
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM cyber_rizhyi_messages
            WHERE created_at < datetime('now', '-' || ? || ' hours')
              AND id NOT IN (
                  SELECT id FROM cyber_rizhyi_messages m2
                  WHERE m2.chat_id = cyber_rizhyi_messages.chat_id
                  ORDER BY m2.id DESC LIMIT ?
              )
        """, (hours, keep_last))
        deleted_count = cursor.rowcount
        conn.commit()
        return deleted_count


def get_cyber_rizhyi_chat_history(chat_id: int, limit: int = 20, max_age_hours: float = 72.0) -> List[Dict[str, Any]]:
    """
    Повертає останні повідомлення чату/групи для контексту Рижого/Турікова (до 20 повідомлень).
    Автоматично очищає старіші за max_age_hours, зберігаючи мінімум 60 останніх реплік.
    """
    cleanup_cyber_rizhyi_expired_messages(max_age_hours, keep_last=60)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM cyber_rizhyi_messages
            WHERE chat_id = ?
            ORDER BY id DESC LIMIT ?
        """, (chat_id, limit))
        rows = cursor.fetchall()
        # Повертаємо в хронологічному порядку
        return [dict(r) for r in reversed(rows)]


def save_cyber_media(
    chat_id: int,
    media_type: str,
    file_id: str,
    file_unique_id: Optional[str] = None,
    emoji: Optional[str] = None,
    set_name: Optional[str] = None
) -> int:
    """Зберігає стікер або GIF, надісланий у чат, для подальшого використання ботами"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO cyber_collected_media (chat_id, media_type, file_id, file_unique_id, emoji, set_name)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(file_id) DO UPDATE SET
                emoji = COALESCE(excluded.emoji, emoji),
                set_name = COALESCE(excluded.set_name, set_name)
        """, (chat_id, media_type, file_id, file_unique_id, emoji, set_name))
        conn.commit()
        return cursor.lastrowid


def get_random_cyber_media(media_type: Optional[str] = None, emoji: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Отримує випадковий стікер чи GIF з бази для відповіді"""
    with get_connection() as conn:
        cursor = conn.cursor()
        if media_type and emoji:
            cursor.execute("""
                SELECT * FROM cyber_collected_media 
                WHERE media_type = ? AND emoji = ? 
                ORDER BY RANDOM() LIMIT 1
            """, (media_type, emoji))
            row = cursor.fetchone()
            if row:
                return dict(row)
        if media_type:
            cursor.execute("""
                SELECT * FROM cyber_collected_media 
                WHERE media_type = ? 
                ORDER BY RANDOM() LIMIT 1
            """, (media_type,))
            row = cursor.fetchone()
            if row:
                return dict(row)
        cursor.execute("SELECT * FROM cyber_collected_media ORDER BY RANDOM() LIMIT 1")
        row = cursor.fetchone()
        return dict(row) if row else None


def get_all_cyber_media(limit: int = 100) -> List[Dict[str, Any]]:
    """Повертає список збережених стікерів та анімацій"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM cyber_collected_media ORDER BY id DESC LIMIT ?", (limit,))
        return [dict(r) for r in cursor.fetchall()]


def get_chat_persona(chat_id: int, default: str = "rizhyi") -> str:
    """Повертає поточну активну персону в чаті: 'rizhyi' або 'turikov'"""
    val = get_setting(f"chat_persona_{chat_id}", default)
    return val if val in ("rizhyi", "turikov") else default


def set_chat_persona(chat_id: int, persona: str) -> None:
    """Встановлює активну персону в чаті: 'rizhyi' або 'turikov'"""
    if persona in ("rizhyi", "turikov"):
        set_setting(f"chat_persona_{chat_id}", persona)


def get_recent_chat_users(chat_id: int, limit: int = 10, exclude_bots: bool = True) -> List[Dict[str, Any]]:
    """Повертає живих користувачів, які нещодавно писали в чаті (виключаючи самих ботів)"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT user_id, username, first_name
            FROM cyber_rizhyi_messages
            WHERE chat_id = ? 
              AND (username IS NOT NULL OR first_name IS NOT NULL)
              AND (message_text IS NOT NULL AND message_text != '')
            ORDER BY id DESC LIMIT ?
        """, (chat_id, limit * 3))
        rows = [dict(r) for r in cursor.fetchall()]

    if exclude_bots:
        bot_names = {
            "cyber_red_head_bot", "turikov_bot", "cyber_bot", "cyber_turikov_bot",
            "bednihryak_bot", "pipisabot", "eeoneaibot", "truemafiabot"
        }
        filtered = []
        for r in rows:
            u = (r.get("username") or "").lower()
            fn = (r.get("first_name") or "").lower()
            if u in bot_names or u.endswith("bot") or "кібер" in fn or "саня туріков" in fn:
                continue
            filtered.append(r)
        return filtered[:limit]
    return rows[:limit]


def get_active_cyber_rizhyi_chats() -> List[int]:
    """Повертає список active group chat_id для спонтанних повідомлень Рижого"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT chat_id FROM cyber_rizhyi_messages WHERE chat_type IN ('group', 'supergroup')")
        return [r["chat_id"] for r in cursor.fetchall()]


def get_cyber_rizhyi_user_memory(user_id: int) -> Dict[str, str]:
    """Повертає всі збережені факти/спогади про користувача"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM cyber_rizhyi_memory WHERE user_id = ?", (user_id,))
        rows = cursor.fetchall()
        return {r["key"]: r["value"] for r in rows}


def set_cyber_rizhyi_user_memory(user_id: int, key: str, value: str) -> None:
    """Оновлює або записує факт у довгострокову пам'ять про людину"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO cyber_rizhyi_memory (user_id, key, value, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
        """, (user_id, key, value))
        conn.commit()


def save_cyber_chat_fact(chat_id: int, fact: str, source_username: str = None) -> None:
    """Зберігає AI-витягнутий факт з переписки чату"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO cyber_chat_facts (chat_id, fact, source_username)
            VALUES (?, ?, ?)
        """, (chat_id, fact[:500], source_username))
        conn.commit()


def get_cyber_chat_facts(chat_id: int, limit: int = 15) -> List[str]:
    """Повертає останні AI-витягнуті факти з чату"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT fact, source_username FROM cyber_chat_facts
            WHERE chat_id = ?
            ORDER BY created_at DESC LIMIT ?
        """, (chat_id, limit))
        rows = cursor.fetchall()
        result = []
        for r in rows:
            fact = r["fact"]
            if r["source_username"]:
                fact = f"@{r['source_username']}: {fact}"
            result.append(fact)
        return result


def save_cyber_user_fact(chat_id: int, user_id: int, username: str, display_name: str, fact: str) -> None:
    """Зберігає AI-витягнутий факт про конкретного юзера"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO cyber_user_facts (chat_id, user_id, username, display_name, fact)
            VALUES (?, ?, ?, ?, ?)
        """, (chat_id, user_id, username, display_name, fact[:300]))
        conn.commit()


def get_cyber_user_facts(chat_id: int, user_id: int = None, limit: int = 5) -> List[Dict]:
    """Повертає факти про юзера або всіх юзерів чату"""
    with get_connection() as conn:
        cursor = conn.cursor()
        if user_id:
            cursor.execute("""
                SELECT display_name, username, fact FROM cyber_user_facts
                WHERE chat_id = ? AND user_id = ?
                ORDER BY created_at DESC LIMIT ?
            """, (chat_id, user_id, limit))
        else:
            cursor.execute("""
                SELECT display_name, username, fact FROM cyber_user_facts
                WHERE chat_id = ?
                ORDER BY created_at DESC LIMIT ?
            """, (chat_id, limit))
        return [dict(r) for r in cursor.fetchall()]


def get_cyber_all_user_facts_for_prompt(chat_id: int) -> str:
    """Повертає всі факти про юзерів у форматі для системного промпту"""
    facts = get_cyber_user_facts(chat_id, limit=20)
    if not facts:
        return ""
    lines = []
    for f in facts:
        name = f.get("display_name") or f.get("username") or "Кент"
        uname = f"@{f['username']}" if f.get("username") else ""
        lines.append(f"- {name} {uname}: {f['fact']}")
    return "ЩО ВІДОМО ПРО КЕНТІВ З ЧАТУ:\n" + "\n".join(lines)


# ---------------------------------------------------------
# МІЖБОТОВИЙ МІСТ (INTER-BOT BRIDGE) ДЛЯ ДІАЛОГІВ У ГРУПАХ
# ---------------------------------------------------------

def enqueue_cyber_bot_event(
    chat_id: int,
    from_bot: str,
    to_bot: str,
    message_id: Optional[int],
    text: str,
    consecutive_count: int = 0,
    sender_user_id: Optional[int] = None,
    sender_username: Optional[str] = None,
    sender_first_name: Optional[str] = None,
    reply_to_name: Optional[str] = None
) -> int:
    """Ставить репліку одного бота в чергу для реакції іншого бота в спільній групі"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO cyber_bot_events (
                chat_id, from_bot, to_bot, message_id, text, consecutive_count, processed,
                sender_user_id, sender_username, sender_first_name, reply_to_name
            )
            VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
        """, (
            chat_id, from_bot, to_bot, message_id, text, consecutive_count,
            sender_user_id, sender_username, sender_first_name, reply_to_name
        ))
        conn.commit()
        return cursor.lastrowid


def get_unprocessed_cyber_bot_events(for_bot: str, max_age_seconds: int = 120) -> List[Dict[str, Any]]:
    """Повертає непрочитані репліки, призначені для вказаного бота"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM cyber_bot_events
            WHERE to_bot = ? AND processed = 0
              AND created_at >= datetime('now', '-' || ? || ' seconds')
            ORDER BY id ASC
        """, (for_bot, max_age_seconds))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]


def mark_cyber_bot_event_processed(event_id: int) -> None:
    """Позначає міжботову подію як оброблену"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE cyber_bot_events SET processed = 1 WHERE id = ?", (event_id,))
        conn.commit()




def save_tiktok_reaction_log(
    video_url: str,
    author_username: Optional[str],
    video_title: Optional[str],
    summary_content: Optional[str],
    reaction_text: str,
    status: str = "success"
) -> int:
    """Зберігає згенеровану реакцію на TikTok відео"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO tiktok_reactions_log (
                video_url, author_username, video_title, summary_content, reaction_text, status
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (video_url, author_username, video_title, summary_content, reaction_text, status))
        conn.commit()
        return cursor.lastrowid


def get_recent_tiktok_reactions(limit: int = 10) -> List[Dict[str, Any]]:
    """Повертає історію реакцій на TikTok"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tiktok_reactions_log ORDER BY id DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]


def get_failed_platforms_for_post(post_id: int) -> List[str]:
    """Визначає список платформ, для яких публікація не вдалася або має помилку"""
    post = get_post_by_id(post_id)
    if not post:
        return []

    c_type_str = post.get("content_type", "video")
    try:
        from core.content_type import ContentType, FORMAT_SUPPORTED_PLATFORMS
        c_type = ContentType(c_type_str)
        supported = FORMAT_SUPPORTED_PLATFORMS.get(c_type, [])
    except Exception:
        supported = ["youtube", "instagram", "tiktok", "facebook", "snapchat", "twitter", "threads", "pinterest", "bluesky", "telegram"]

    plat_id_fields = {
        "youtube": "yt_video_id",
        "instagram": "ig_media_id",
        "tiktok": "tt_video_id",
        "facebook": "fb_video_id",
        "snapchat": "snap_media_id",
        "twitter": "tw_tweet_id",
        "threads": "threads_media_id",
        "pinterest": "pin_id",
        "bluesky": "bsky_uri",
        "telegram": "error_message"
    }

    failed = []
    for plat in supported:
        field = plat_id_fields.get(plat)
        val = post.get(field)
        if not val:
            failed.append(plat)
    return failed


def get_expiring_streaks(threshold_hours: float = 20.0) -> List[Dict[str, Any]]:
    """
    Знаходить контакти, у яких вогник під загрозою згасання:
    якщо з моменту останньої відправки минуло більше threshold_hours або сьогодні ще не відправляли.
    """
    from datetime import datetime
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tiktok_streak_targets WHERE active = 1")
        rows = cursor.fetchall()

    expiring = []
    now = datetime.now()

    for r in rows:
        item = dict(r)
        last_sent = item.get("last_sent_at")
        if not last_sent:
            item["hours_elapsed"] = 999.0
            item["urgency"] = "critical"
            expiring.append(item)
            continue

        try:
            dt = datetime.strptime(last_sent[:19], "%Y-%m-%d %H:%M:%S")
            diff_hours = (now - dt).total_seconds() / 3600.0
            item["hours_elapsed"] = round(diff_hours, 1)
            if diff_hours >= threshold_hours:
                item["urgency"] = "warning" if diff_hours < 24.0 else "critical"
                expiring.append(item)
        except Exception:
            item["hours_elapsed"] = 999.0
            item["urgency"] = "unknown"
            expiring.append(item)

    return expiring


def get_aggregate_stats() -> Dict[str, Any]:
    """Агрегує сумарні перегляди та взаємодії за всіма публікаціями в системі"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                COUNT(*) as total_posts,
                COALESCE(SUM(yt_views + ig_views + tt_views + fb_views + snap_views + tw_views + threads_views + pin_views + bsky_views), 0) as total_views,
                COALESCE(SUM(yt_likes + ig_likes + tt_likes + fb_likes + snap_likes + tw_likes + threads_likes + pin_likes + bsky_likes), 0) as total_likes
            FROM posts
        """)
        row = cursor.fetchone()
        return {
            "total_posts": row["total_posts"] if row else 0,
            "total_views": row["total_views"] if row else 0,
            "total_likes": row["total_likes"] if row else 0
        }


init_db()
