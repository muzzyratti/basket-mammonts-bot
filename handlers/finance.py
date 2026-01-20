from aiogram import Router, types, F
from aiogram.filters import Command, CommandObject
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from services.google_sheets import sheets
from services.date_tools import get_next_game_date
import math

router = Router()

@router.message(Command("pay"))
async def cmd_pay(message: types.Message, command: CommandObject):
    """
    Примеры:
    /pay 5000      -> делит на кол-во записанных в боте
    /pay 5000 18   -> делит на 18 человек (принудительно)
    """
    if not command.args:
        await message.answer("💸 Использование: `/pay 5000` или `/pay 5000 10`", parse_mode="Markdown")
        return

    args = command.args.split()
    try:
        amount = int(args[0])
        # Если есть второй аргумент - это ручное количество людей
        manual_count = int(args[1]) if len(args) > 1 else None
    except ValueError:
        await message.answer("❌ Сумма и количество должны быть числами.")
        return

    status = await message.answer("💰 Считаю дебет с кредитом...")

    try:
        # 1. Дата игры
        settings = await sheets.get_settings()
        game_day = settings.get("день_игры", "суббота")
        _, game_date = get_next_game_date(game_day)
        
        # 2. Ищем записанных "Воинов"
        votes = await sheets.get_votes_for_date(game_date)
        ws_m = await sheets._get_ws("Мамонты")
        all_mammoths = await ws_m.get_all_records()
        
        debtors_ids = []
        debtors_names = []
        payer_id = message.from_user.id
        
        # Сопоставляем голоса с базой, чтобы найти ID
        for v in votes:
            v_nick = v['nick'].replace("@", "").lower() if v['nick'] else ""
            v_name = v['name']
            
            found_id = None
            for m in all_mammoths:
                m_nick = str(m.get("Ник", "")).replace("@", "").lower()
                m_name = m.get("Имя", "")
                
                if (v_nick and v_nick == m_nick) or (v_name == m_name):
                    found_id = m.get("ID Telegram")
                    break
            
            # Добавляем в должники всех, кроме плательщика
            if found_id:
                if str(found_id) != str(payer_id):
                    debtors_ids.append(found_id)
                    debtors_names.append(v_name)
            else:
                debtors_names.append(f"{v_name} (без ID)")

        # 3. МАТЕМАТИКА (Важный момент!)
        found_count = len(votes)
        
        # Если указали руками, используем ручное число. Иначе - то, что нашли в базе.
        final_count = manual_count if manual_count else found_count
        
        if final_count == 0:
            await status.edit_text("❌ Игроков 0. Делить на ноль нельзя.")
            return

        cost_exact = amount / final_count
        cost_rounded = math.ceil(cost_exact / 10) * 10
        
        # 4. Плательщик
        payer_name = message.from_user.first_name
        payer_phone = await sheets.get_user_phone(payer_id)
        phone_text = f"<code>{payer_phone}</code>" if payer_phone else "<i>(нет в базе, спросите в лс)</i>"

        # 5. Запись
        await sheets.add_payment(
            game_date, payer_name, amount, final_count, cost_rounded, debtors_ids, debtors_names
        )

        # 6. Кнопка
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💸 Я перевел!", callback_data="payment_done")]
        ])

        # 7. Отчет
        # Добавляем пояснение, если реальных записей меньше, чем указано руками
        warning_text = ""
        if manual_count and manual_count > found_count:
            warning_text = f"\n⚠️ <i>Расчет на {manual_count} чел, но в боте записано только {found_count}.</i>"

        report = (
            f"💸 <b>СБОР ДЕНЕГ ({game_date})</b>\n\n"
            f"Всего: {amount} ₽ | Игроков: {final_count}{warning_text}\n\n"
            f"💎 <b>Скидываем по: {cost_rounded} ₽</b>\n\n"
            f"💳 Куда: {phone_text} ({payer_name})\n\n\n"
            f"👇 <i>Нажми кнопку, когда переведешь!</i>"
        )
        
        await status.delete()
        await message.answer(report, parse_mode="HTML", reply_markup=kb)

    except Exception as e:
        import traceback
        traceback.print_exc()
        await status.edit_text(f"❌ Ошибка: {e}")

@router.message(Command("pay"))
async def cmd_pay(message: types.Message, command: CommandObject):
    print(f"DEBUG: Поймал команду /pay от {message.from_user.first_name}")

@router.callback_query(F.data == "payment_done")
async def payment_done_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user_name = callback.from_user.first_name
    
    remaining_count, _ = await sheets.remove_debtor(user_id, user_name)
    
    if remaining_count is None:
        await callback.answer("Ты не найден в списке должников (или сбор закрыт).", show_alert=True)
        return
    
    await callback.answer("Оплата отмечена! ✅")
    
    if remaining_count == 0:
        # Убираем кнопку, если все оплатили
        await callback.message.edit_text(
            callback.message.text + "\n\n✅ <b>ВСЕ ОПЛАТИЛИ! СБОР ЗАКРЫТ.</b>", 
            parse_mode="HTML", 
            reply_markup=None
        )