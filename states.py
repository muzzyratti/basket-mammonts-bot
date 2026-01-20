from aiogram.fsm.state import State, StatesGroup

class RegistrationStates(StatesGroup):
    waiting_for_height = State()
    waiting_for_weight = State()
    waiting_for_role = State()
    waiting_for_rating = State()

class ProfileStates(StatesGroup):
    waiting_for_phone_input = State() # Отдельное состояние для ввода телефона