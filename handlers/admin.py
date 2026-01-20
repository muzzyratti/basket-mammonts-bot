from aiogram import Router, types
from aiogram.filters import Command
from config import config
from services.google_sheets import sheets
from services.balancer import form_teams
from services.date_tools import get_next_game_date

router = Router()

@router.message(Command("make_teams"))
async def cmd_make_teams(message: types.Message):
    if message.from_user.id not in config.admin_ids_list:
        return

    status = await message.answer("⏳ Считаю составы...")
    try:
        settings = await sheets.get_settings()
        game_day = settings.get("день_игры", "суббота")
        _, game_date = get_next_game_date(game_day)

        # Вызываем новый балансировщик
        teams, report = await form_teams(game_date)
        
        await status.delete()

        if not teams:
            await message.answer(report)
        else:
            # Отправляем с HTML (теперь там нет конфликтующих **)
            await message.answer(report, parse_mode="HTML")
            
            if message.chat.id != config.GROUP_CHAT_ID:
                try:
                    await message.bot.send_message(
                        chat_id=config.GROUP_CHAT_ID,
                        text=report,
                        parse_mode="HTML"
                    )
                    await message.answer("✅ Отправлено в общий чат.")
                except Exception as e:
                    pass
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        await message.answer(f"❌ Ошибка: {e}")

@router.message(Command("pause"))
async def cmd_pause(message: types.Message):
    if message.from_user.id not in config.admin_ids_list:
        return
    
    await sheets.update_setting("бот_активен", "Нет")
    await message.answer("😴 **Бот уснул.**\nОпросы, напоминалки и составы отключены.")

@router.message(Command("resume"))
async def cmd_resume(message: types.Message):
    if message.from_user.id not in config.admin_ids_list:
        return
    
    await sheets.update_setting("бот_активен", "Да")
    await message.answer("🚀 **Бот проснулся!**\nРаботаем по расписанию.")