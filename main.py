import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from config import config

# ИМПОРТЫ ХЕНДЛЕРОВ
from handlers import admin
from handlers import registration
from handlers import manual_poll
from handlers import vote_handler
from handlers import finance  # <--- 1. ПРОВЕРЬ ЭТОТ ИМПОРТ
from services.poll_scheduler import start_scheduler

logging.basicConfig(level=logging.INFO)

async def setup_bot_commands(bot: Bot):
    commands = [
        BotCommand(command="/start", description="🏁 Создать профиль"),
        BotCommand(command="/phone", description="📱 Телефон для оплат"),
        BotCommand(command="/pay", description="💸 Оплата аренды"),
        BotCommand(command="/notify", description="🔔 Уведомления"),
        BotCommand(command="/make_teams", description="⚖️ Собрать составы (Админ)"),
    ]
    await bot.set_my_commands(commands)

async def main():
    bot = Bot(token=config.BOT_TOKEN.get_secret_value())
    dp = Dispatcher()

    # ПОДКЛЮЧЕНИЕ РОУТЕРОВ (ПОРЯДОК ВАЖЕН)
    # Admin ловит свои команды первым
    dp.include_router(admin.router)
    # Finance ловит /pay
    dp.include_router(finance.router) # <--- 2. ПРОВЕРЬ, ЧТО ЭТА СТРОКА ЕСТЬ И НЕ ЗАКОММЕНТИРОВАНА
    # Остальные
    dp.include_router(registration.router)
    dp.include_router(manual_poll.router)
    dp.include_router(vote_handler.router)

    await setup_bot_commands(bot)
    
    # Запуск планировщика (с проверкой на двойной старт внутри)
    start_scheduler(bot)

    await bot.delete_webhook(drop_pending_updates=True)
    # Выводим список админов (ADMIN_IDS) или вообще убираем вывод ID
    print(f"🐘 Бот Мамонтов запущен! Админы: {config.ADMIN_IDS}")
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())