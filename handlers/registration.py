from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from states import RegistrationStates, ProfileStates
from services.google_sheets import sheets
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

router = Router()

# --- INLINE КЛАВИАТУРЫ ---

# Роли
role_kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="Большой (Центр/Мощь) 💪", callback_data="role_big")],
    [InlineKeyboardButton(text="Снайпер (Темп/Бросок) 🎯", callback_data="role_sniper")],
    [InlineKeyboardButton(text="Нападающий (Универсал) 🏃", callback_data="role_forward")]
])

# Рейтинги
rating_kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="5 (Профи) ⭐️⭐️⭐️⭐️⭐️", callback_data="rate_5")],
    [InlineKeyboardButton(text="4 (Крепкий Мамонт) ⭐️⭐️⭐️⭐️", callback_data="rate_4")],
    [InlineKeyboardButton(text="3 (Стабильный) ⭐️⭐️⭐️", callback_data="rate_3")],
    [InlineKeyboardButton(text="2 (Бегущий) ⭐️⭐️", callback_data="rate_2")],
    [InlineKeyboardButton(text="1 (Новичок) ⭐️", callback_data="rate_1")]
])

# Уведомления
notify_kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="Включить ✅", callback_data="notify_on")],
    [InlineKeyboardButton(text="Выключить 🔕", callback_data="notify_off")]
])

# --- РЕГИСТРАЦИЯ (/start) ---

@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    is_registered = await sheets.check_user_exists(user_id)
    
    if is_registered:
        await message.answer(
            "Привет, Мамонт! 🐘\nТы уже в базе.\n"
            "Добавить телефон: /phone\n"
            "Настройки уведомлений: /notify"
        )
    else:
        await message.answer(
            "Привет! Добро пожаловать в стаю Мамонтов! 🐘🏀\n"
            "Давай заполним твой профиль.\n\n"
            "1. Введи твой <b>Рост</b> (в см, только число, например 185):",
            parse_mode="HTML"
        )
        await state.set_state(RegistrationStates.waiting_for_height)

@router.message(RegistrationStates.waiting_for_height)
async def process_height(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Пожалуйста, введи рост числом (например: 180).")
        return
    await state.update_data(height=message.text)
    await state.set_state(RegistrationStates.waiting_for_weight)
    await message.answer("2. Введи твой <b>Вес</b> (в кг, только число):", parse_mode="HTML")

@router.message(RegistrationStates.waiting_for_weight)
async def process_weight(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Пожалуйста, введи вес числом (например: 85).")
        return
    await state.update_data(weight=message.text)
    await state.set_state(RegistrationStates.waiting_for_role)
    
    await message.answer("3. Выбери свою <b>Роль</b>:", reply_markup=role_kb, parse_mode="HTML")

@router.callback_query(RegistrationStates.waiting_for_role)
async def process_role(callback: types.CallbackQuery, state: FSMContext):
    roles_map = {
        "role_big": "Большой (Центр)",
        "role_sniper": "Снайпер",
        "role_forward": "Нападающий"
    }
    selected_role = roles_map.get(callback.data, "Игрок")
    
    await state.update_data(role=selected_role)
    await callback.answer()
    await callback.message.edit_text(f"3. Роль: <b>{selected_role}</b> ✅", parse_mode="HTML")
    
    await state.set_state(RegistrationStates.waiting_for_rating)
    await callback.message.answer("4. Оцени свой <b>Уровень</b>:", reply_markup=rating_kb, parse_mode="HTML")

@router.callback_query(RegistrationStates.waiting_for_rating)
async def process_rating(callback: types.CallbackQuery, state: FSMContext):
    rating_level = callback.data.split("_")[1]
    
    await callback.answer()
    await callback.message.edit_text(f"4. Уровень: <b>{rating_level}</b> ✅", parse_mode="HTML")
    
    user_data = await state.get_data()
    
    full_user_data = [
        callback.from_user.id,
        callback.from_user.first_name,
        f"@{callback.from_user.username}" if callback.from_user.username else "NoNick",
        user_data['height'],
        user_data['weight'],
        user_data['role'],
        rating_level,
        "Да", 
        ""    
    ]
    
    msg = await callback.message.answer("⏳ Сохраняю профиль...")
    
    try:
        await sheets.register_user(full_user_data)
        await msg.edit_text(
            "✅ <b>Профиль создан!</b>\n\n"
            "Теперь я буду знать, какой ты игрок.\n"
            "Указать телефон для платежей: /phone",
            parse_mode="HTML"
        )
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка сохранения: {e}")
    
    await state.clear()

# --- ДОБАВЛЕНИЕ ТЕЛЕФОНА (/phone) ---

@router.message(Command("phone"))
async def cmd_phone(message: types.Message, state: FSMContext):
    await message.answer(
        "Напиши <b>номер телефона</b> (например: +79991234567), к которому привязан твой банк.",
        parse_mode="HTML"
    )
    await state.set_state(ProfileStates.waiting_for_phone_input)

@router.message(ProfileStates.waiting_for_phone_input)
async def save_phone_number(message: types.Message, state: FSMContext):
    phone = message.text.strip()
    user_id = message.from_user.id
    
    # --- ЗАЩИТА ОТ #ERROR В ГУГЛ ТАБЛИЦАХ ---
    # Если номер начинается с +, добавляем ' в начало
    if phone.startswith("+"):
        phone_to_save = f"'{phone}"
    else:
        phone_to_save = phone
    # ----------------------------------------
    
    success = await sheets.update_phone(user_id, phone_to_save)
    
    if success:
        # Пользователю показываем красивый номер (без апострофа)
        await message.answer(f"✅ Телефон <b>{phone}</b> сохранен!", parse_mode="HTML")
    else:
        await message.answer("❌ Ошибка: Не нашел твой профиль. Нажми /start")
        
    await state.clear()

# --- УВЕДОМЛЕНИЯ (/notify) ---

@router.message(Command("notify"))
async def cmd_toggle_notify(message: types.Message):
    await message.answer("Управление уведомлениями:", reply_markup=notify_kb)

@router.callback_query(F.data == "notify_on")
async def notify_on(callback: types.CallbackQuery):
    await sheets.toggle_notification(callback.from_user.id, "Да")
    await callback.answer("Включено!")
    await callback.message.edit_text("Уведомления: <b>Включены</b> ✅", parse_mode="HTML")

@router.callback_query(F.data == "notify_off")
async def notify_off(callback: types.CallbackQuery):
    await sheets.toggle_notification(callback.from_user.id, "Нет")
    await callback.answer("Выключено!")
    await callback.message.edit_text("Уведомления: <b>Выключены</b> 🔕", parse_mode="HTML")