from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import config
from services.google_sheets import sheets
from services.poll_message import start_poll_routine
from datetime import datetime

router = Router()

class ManualPollStates(StatesGroup):
    waiting_for_date = State()

# Словарь для обратного перевода (0 -> понедельник)
WEEKDAYS_RU = {
    0: "понедельник",
    1: "вторник",
    2: "среда",
    3: "четверг",
    4: "пятница",
    5: "суббота",
    6: "воскресенье"
}

@router.message(Command("poll"))
async def cmd_manual_poll(message: types.Message, state: FSMContext):
    if message.from_user.id not in config.admin_ids_list:
        return

    if message.chat.type != 'private':
        try: await message.delete()
        except: pass

    await message.answer(
        "📅 **Ручной запуск опроса**\n\n"
        "Введи дату игры (ДД.ММ.ГГГГ), например: `24.01.2026`\n"
        "Я вычислю день недели, обновлю настройку `день_игры` и запущу опрос.",
        parse_mode="Markdown"
    )
    await state.set_state(ManualPollStates.waiting_for_date)

@router.message(ManualPollStates.waiting_for_date)
async def process_poll_date(message: types.Message, state: FSMContext):
    date_str = message.text.strip()
    
    try:
        # Парсим дату
        dt = datetime.strptime(date_str, "%d.%m.%Y")
        
        # Определяем день недели (0-6) -> (понедельник...)
        day_name = WEEKDAYS_RU[dt.weekday()]
        
        status = await message.answer(f"⏳ Это <b>{day_name}</b>. Обновляю настройки и запускаю...", parse_mode="HTML")
        
        # 1. Обновляем ТОЛЬКО день игры (как ты просил изначально)
        await sheets.update_setting("день_игры", day_name)
        
        # 2. Запускаем опрос
        result_text = await start_poll_routine(message.bot)
        
        await status.edit_text(f"✅ Готово! Установлен день игры: <b>{day_name}</b>.\n{result_text}", parse_mode="HTML")
        
    except ValueError:
        await message.answer("❌ Неверный формат даты. Нужно ДД.ММ.ГГГГ. Попробуй еще раз.")
        return
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
    
    await state.clear()