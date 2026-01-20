from config import config
from services.google_sheets import sheets
from services.date_tools import get_next_game_date

OPTIONS = [
    "Я воин мяча! 🔥",
    "Я воин подушки!💤"
]

async def start_poll_routine(bot):
    """
    Основная функция: формирует и отправляет опрос в чат.
    Возвращает текст статуса для логов/админа.
    """
    try:
        # 1. Читаем настройки
        settings = await sheets.get_settings()
        game_day = settings.get("день_игры", "суббота")
        
        # 2. Считаем дату
        day_str, date_str = get_next_game_date(game_day)
        question = f"{day_str}, {date_str}. Ты в Игре? 🏀"

        # 3. Отправляем в группу
        await bot.send_poll(
            chat_id=config.GROUP_CHAT_ID,
            question=question,
            options=OPTIONS,
            is_anonymous=False,
            allows_multiple_answers=False
        )

        # 4. Пишем в таблицу новую дату (для истории)
        await sheets.update_setting("дата_текущей_игры", date_str)
        
        return f"✅ Опрос успешно отправлен. Дата: {date_str}"

    except Exception as e:
        return f"❌ Ошибка при отправке опроса: {e}"