import asyncio
from typing import Any, Callable, Dict, List, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message


class AlbumMiddleware(BaseMiddleware):
    """
    Middleware для об'єднання медіагруп (альбомів / каруселей) в Telegram.
    Коли користувач надсилає кілька фото/відео як альбом, Telegram надсилає
    окремі повідомлення для кожного елемента з однаковим `media_group_id`.
    Цей middleware збирає їх в один список `album`.
    """

    def __init__(self, latency: float = 0.6):
        self.latency = latency
        self.album_data: Dict[str, List[Message]] = {}

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        if not event.media_group_id:
            return await handler(event, data)

        mg_id = event.media_group_id

        # Якщо група ще не створена — ініціалізуємо
        if mg_id not in self.album_data:
            self.album_data[mg_id] = [event]
            await asyncio.sleep(self.latency)

            # Отримуємо всі зібрані повідомлення групи
            messages = self.album_data.pop(mg_id, [])
            data["album"] = messages
            return await handler(event, data)
        else:
            # Додаємо черговий елемент до альбому
            self.album_data[mg_id].append(event)
            return None
