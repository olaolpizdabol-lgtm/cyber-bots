"""
🎯 Base platform contract for Lead Funnel
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class PlatformComment:
    comment_id: str
    post_id: str
    post_url: Optional[str]
    user_id: str
    username: str
    text: str
    has_author_replied: bool = False
    created_time: Optional[str] = None
    screenshot_path: Optional[str] = None


class BasePlatformFunnel(ABC):
    @property
    @abstractmethod
    def platform_name(self) -> str:
        pass

    @abstractmethod
    def fetch_recent_unanswered_comments(self, limit_posts: int = 5) -> List[PlatformComment]:
        """Отримує свіжі коментарі, на які автор ще не відповів"""
        pass

    @abstractmethod
    def is_user_following(self, user_id: str, username: str) -> bool:
        """Перевіряє, чи підписаний користувач на наш акаунт/сторінку"""
        pass

    def check_follower_status(self, user_id: str, username: str) -> Tuple[bool, Optional[str]]:
        """
        Перевіряє статус підписки та повертає (is_following, proof_screenshot_path).
        За замовчуванням викликає is_user_following.
        """
        return self.is_user_following(user_id, username), None

    @abstractmethod
    def send_direct_message(self, user_id: str, username: str, text: str, comment_id: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """
        Надсилає повідомлення в Direct / Messenger.
        Повертає (успіх, помилка).
        Якщо помилка 'private_dm', викликач знає про закритий профіль.
        """
        pass

    @abstractmethod
    def reply_to_comment(self, comment_id: str, text: str, post_id: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """Публікує відповідь на коментар під відео/дописом"""
        pass
