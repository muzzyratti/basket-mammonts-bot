from aiogram import Router, types
from services.google_sheets import sheets
from services.date_tools import get_next_game_date

router = Router()

OPTIONS = [
    "Я воин мяча! 🔥",
    "Я воин подушки!💤"
]

@router.poll_answer()
async def handle_poll_answer(poll_answer: types.PollAnswer):
    user = poll_answer.user
    option_ids = poll_answer.option_ids
    
    if not option_ids:
        vote_result = "Голос отозван ❌"
    else:
        selected_index = option_ids[0]
        if selected_index < len(OPTIONS):
            vote_result = OPTIONS[selected_index]
        else:
            vote_result = "Неизвестный вариант"

    # --- ЛОГИКА ДАТЫ (СТРОГО ПО ТЗ) ---
    # 1. Читаем настройки
    settings = await sheets.get_settings()
    
    # 2. Берем день недели (по дефолту суббота)
    game_day = settings.get("день_игры", "суббота")
    
    # 3. Вычисляем дату через date_tools
    _, calculated_date = get_next_game_date(game_day)
    game_date = calculated_date
    # ----------------------------------

    user_data = {
        "first_name": user.first_name,
        "username": f"@{user.username}" if user.username else "NoNick"
    }

    try:
        await sheets.log_vote(user_data, vote_result, game_date)
    except Exception as e:
        print(f"❌ Ошибка записи голоса: {e}")