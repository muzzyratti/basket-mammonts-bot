from datetime import datetime, timedelta

# Словарь для конвертации русских названий в цифры (0 = Понедельник, 6 = Воскресенье)
DAYS_MAP = {
    "понедельник": 0,
    "вторник": 1,
    "среда": 2,
    "четверг": 3,
    "пятница": 4,
    "суббота": 5,
    "воскресенье": 6
}

# Обратный словарь для красивого вывода
DAYS_NAMES = {v: k.capitalize() for k, v in DAYS_MAP.items()}

def get_next_game_date(day_name_ru: str) -> tuple[str, str]:
    """
    Принимает день недели (например, 'суббота').
    Возвращает кортеж: (Название дня, Дата в формате ДД.ММ.ГГГГ).
    Вычисляет ближайший такой день. Если сегодня этот день - возвращает сегодня.
    """
    day_name_clean = day_name_ru.strip().lower()
    target_weekday = DAYS_MAP.get(day_name_clean)
    
    if target_weekday is None:
        # Если в таблице написали дичь, по дефолту берем субботу (5)
        target_weekday = 5 

    today = datetime.now()
    current_weekday = today.weekday()

    # Считаем разницу дней
    days_ahead = target_weekday - current_weekday
    
    # Если день уже прошел на этой неделе (например, сегодня Среда, а мы хотим Вторник),
    # то days_ahead будет отрицательным. Добавляем 7 дней.
    # Если days_ahead == 0, значит игра сегодня.
    if days_ahead < 0:
        days_ahead += 7
        
    next_date = today + timedelta(days=days_ahead)
    
    return DAYS_NAMES[target_weekday], next_date.strftime("%d.%m.%Y")