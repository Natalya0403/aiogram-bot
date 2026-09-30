from aiogram import BaseMiddleware
import time

class RateLimitMiddleware(BaseMiddleware):
    def __init__(self, limit_seconds: float = 3.0):
        self.limit_seconds = limit_seconds
        self.user_timestamps = {}

    async def __call__(self, handler, event, data):
        user_id = event.from_user.id
        current_time = time.time()

        last_time = self.user_timestamps.get(user_id, 0)

        if current_time - last_time < self.limit_seconds:
            await event.answer(f"Подождите немного, так как отправка сообщений доступна раз на {self.limit_seconds} секунды")
            return
        
        self.user_timestamps[user_id] = current_time

        return await handler(event, data)

