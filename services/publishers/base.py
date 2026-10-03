from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from core.content_type import ContentType


@dataclass
class PublishResult:
    success: bool
    platform: str
    external_id: Optional[str] = None
    url: Optional[str] = None
    error: Optional[str] = None


@dataclass
class StatsResult:
    platform: str
    views: int = 0
    likes: int = 0
    comments: int = 0
    error: Optional[str] = None


class BasePublisher(ABC):
    @property
    @abstractmethod
    def platform_name(self) -> str:
        pass

    @abstractmethod
    def publish(
        self,
        content_type: ContentType,
        media_paths: List[str],
        metadata: Dict[str, Any]
    ) -> PublishResult:
        pass

    @abstractmethod
    def get_stats(self, external_id: str) -> StatsResult:
        pass
