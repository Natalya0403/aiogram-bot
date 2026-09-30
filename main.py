import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramAPIError
from middleware.admin_only import AdminOnlyMiddleware
from middleware.rate_limit import RateLimitMiddleware
from dotenv import load_dotenv
import os

from handlers import routes

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
# ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

logging.basicConfig(level=logging.INFO)


async def main() -> None:
    bot = Bot(
        token=TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    dp = Dispatcher(storage=MemoryStorage())

    # dp.message.middleware(AdminOnlyMiddleware())
    dp.message.middleware(RateLimitMiddleware(limit_seconds=1.0))

    dp.include_router(routes.router)

    await bot.set_my_commands([])

    try:
        await dp.start_polling(bot)
    except TelegramAPIError as e:
        logging.error(f"Ошибка при запуске TelegramAPIError: {e}")
    finally:
        await bot.session.close()

if __name__ == '__main__':
    asyncio.run(main())