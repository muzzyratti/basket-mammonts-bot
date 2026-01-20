import gspread_asyncio
from google.oauth2.service_account import Credentials
from config import config

def get_creds():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_file(config.SERVICE_ACCOUNT_FILE)
    return creds.with_scopes(scopes)

agcm = gspread_asyncio.AsyncioGspreadClientManager(get_creds)

class GoogleSheetsService:
    def __init__(self):
        self.agcm = agcm
        self.spreadsheet_id = config.SPREADSHEET_ID

    async def _get_ws(self, name):
        client = await self.agcm.authorize()
        ss = await client.open_by_key(self.spreadsheet_id)
        return await ss.worksheet(name)

    # --- SETTINGS ---
    async def get_settings(self) -> dict:
        ws = await self._get_ws("Настройки бота")
        records = await ws.get_all_records()
        return {row['key']: row['value'] for row in records if row.get('key')}

    async def update_setting(self, key: str, value: str):
        ws = await self._get_ws("Настройки бота")
        try:
            cell = await ws.find(key)
            if cell:
                await ws.update_cell(cell.row, cell.col + 1, value)
            else:
                await ws.append_row([key, value])
        except Exception as e:
            print(f"Error updating setting: {e}")

    # --- USERS ---
    async def check_user_exists(self, user_id: int) -> bool:
        ws = await self._get_ws("Мамонты")
        try:
            cell = await ws.find(str(user_id), in_column=1)
            return cell is not None
        except:
            return False

    async def register_user(self, user_data: list):
        ws = await self._get_ws("Мамонты")
        await ws.insert_row(user_data, index=2)

    async def update_phone(self, user_id: int, phone: str) -> bool:
        ws = await self._get_ws("Мамонты")
        try:
            cell = await ws.find(str(user_id), in_column=1)
            if cell:
                await ws.update_cell(cell.row, 9, phone)
                return True
            return False
        except:
            return False
    
    async def toggle_notification(self, user_id: int, status: str):
        ws = await self._get_ws("Мамонты")
        try:
            cell = await ws.find(str(user_id), in_column=1)
            if cell:
                await ws.update_cell(cell.row, 8, status)
        except:
            pass

    # --- VOTES & TEAMS (НОВОЕ) ---
    async def log_vote(self, user_data: dict, vote_result: str, game_date: str):
        ws = await self._get_ws("Голосования")
        from datetime import datetime
        vote_time = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        row_data = [game_date, user_data.get("first_name", ""), user_data.get("username", "NoNick"), vote_result, vote_time]
        await ws.insert_row(row_data, index=2)

    async def get_players_stats(self):
        """Возвращает словарь: {Ник: stats, Имя: stats}"""
        ws = await self._get_ws("Мамонты")
        records = await ws.get_all_records()
        
        players = {}
        for row in records:
            # Сохраняем и по Нику (если есть), и по Имени
            # Это двойная страховка
            
            p_stats = {
                'height': row.get('Рост'),
                'weight': row.get('Вес'),
                'role': row.get('Роль'),
                'rating': row.get('Рейтинг')
            }
            
            # 1. Если есть Ник - сохраняем по нику (с @ и без)
            nick = row.get('Ник')
            if nick and nick != "NoNick":
                players[nick] = p_stats
                # Если записан как "@vasya", сохраним и "vasya"
                if nick.startswith("@"):
                    players[nick[1:]] = p_stats
            
            # 2. Сохраняем по Имени (Вася, Петя)
            name = row.get('Имя')
            if name:
                players[name] = p_stats
                
        return players

    async def get_votes_for_date(self, date_str: str):
        """
        Получает список тех, кто идет, на конкретную дату.
        Возвращает список словарей: [{'name': 'Alexander', 'nick': '@alex'}]
        """
        ws = await self._get_ws("Голосования")
        records = await ws.get_all_records()
        
        players_in = []
        for row in records:
            # Сравниваем дату и ищем ключевую фразу "воин мяча"
            # (Учитываем, что ответ может быть с огоньком или без, главное суть)
            if row.get('Дата игры') == date_str and "Я воин мяча" in row.get('Голос'):
                player_info = {
                    'name': row.get('Имя'),
                    'nick': row.get('Ник')
                }
                players_in.append(player_info)
        return players_in

    async def save_teams_batch(self, teams_data: list):
        """
        Сохраняет составы. Принимает список словарей:
        [{"date": "...", "team_name": "...", "roster": "...", "rating": "..."}]
        Каждую команду пишет в отдельную строку.
        """
        try:
            ws = await self._get_ws("Составы")
            # Данные для вставки (список списков)
            rows_to_insert = []
            
            # Идем в обратном порядке, чтобы при вставке "сверху" (index=2) 
            # первая команда оказалась выше второй
            for team in reversed(teams_data):
                row = [
                    team['date'],       # Col A: Дата
                    team['team_name'],  # Col B: Название
                    team['roster'],     # Col C: Состав
                    team['rating']      # Col D: Рейтинг
                ]
                rows_to_insert.append(row)
            
            # Вставляем пачкой или по одному
            for row in rows_to_insert:
                await ws.insert_row(row, index=2)
                
        except Exception as e:
            print(f"Ошибка записи составов: {e}")

    async def get_last_games_teams(self, limit=2, exclude_date=None):
        """
        Возвращает составы последних игр, ИСКЛЮЧАЯ указанную дату.
        """
        ws = await self._get_ws("Составы")
        records = await ws.get_all_records()
        
        if not records:
            print("DEBUG HISTORY: Лист 'Составы' пуст.")
            return []

        games_map = {}
        
        print(f"DEBUG HISTORY: Начинаю анализ. Исключаю дату: {exclude_date}")

        for row in records:
            # Поддержка разных названий колонок
            date = str(row.get("Дата игры") or row.get("date") or row.get("Дата трени")).strip()
            roster_str = row.get("Состав команды") or row.get("roster") or row.get("Состав команды")
            
            # Игнорируем текущую дату (чтобы не сравнивать с только что созданной записью)
            if date == exclude_date:
                continue
                
            if not date or not roster_str:
                continue
                
            if date not in games_map:
                games_map[date] = []
            
            # Парсинг имен
            player_names = set()
            # Разбиваем по переносу строки
            lines = roster_str.split('\n')
            
            for line in lines:
                # Очистка от ролей: "Вася (Снайпер)" -> "Вася"
                clean_name = line.split(' (')[0].strip()
                # Удаляем возможные HTML теги если попали
                clean_name = clean_name.replace("<b>", "").replace("</b>", "")
                
                if clean_name:
                    player_names.add(clean_name)
            
            games_map[date].append(player_names)

        # Сортировка дат
        from datetime import datetime
        def parse_date(d):
            try: return datetime.strptime(d, "%d.%m.%Y")
            except: return datetime.min

        sorted_dates = sorted(games_map.keys(), key=parse_date, reverse=True)
        
        # Вывод найденных дат для отладки
        print(f"DEBUG HISTORY: Нашел даты в истории (после фильтра): {sorted_dates}")
        
        # Берем последние N
        last_dates = sorted_dates[:limit]
        
        history = []
        for d in last_dates:
            teams = games_map[d]
            history.append(teams)
            # Покажем кого распарсили
            print(f"DEBUG HISTORY: Дата {d}, Команды: {teams}")
            
        return history

    async def get_users_for_notification(self):
        """Возвращает список ID пользователей, у которых включены уведомления"""
        ws = await self._get_ws("Мамонты")
        records = await ws.get_all_records()
        
        user_ids = []
        for row in records:
            # Проверяем колонку "Отправлять уведомления" (или как она у тебя названа)
            # В твоей таблице это столбец H
            notify = str(row.get("Отправлять уведомления", "")).lower()
            if notify == "да":
                user_ids.append(row.get("ID Telegram"))
        return user_ids

    async def get_all_voters_nicks(self, game_date: str) -> set:
        """
        Возвращает множество (set) ников всех, кто хоть как-то проголосовал за эту дату.
        Нужно для того, чтобы не слать напоминания тем, кто уже нажал кнопку.
        """
        ws = await self._get_ws("Голосования")
        records = await ws.get_all_records()
        
        voted_nicks = set()
        for row in records:
            if row.get('Дата игры') == game_date:
                # Берем Ник. Если его нет, берем Имя (хотя по Имени сложнее матчить)
                # Надежнее всего работать с Никами, как мы решили ранее.
                nick = row.get('Ник')
                if nick:
                    # Убираем @ если есть, приводим к нижнему регистру для надежности
                    clean_nick = nick.replace("@", "").strip().lower()
                    if clean_nick:
                        voted_nicks.add(clean_nick)
        return voted_nicks

    async def get_user_phone(self, user_id: int):
        """Ищет телефон пользователя по ID в листе Мамонты"""
        ws = await self._get_ws("Мамонты")
        try:
            cell = await ws.find(str(user_id), in_column=1)
            if cell:
                # Телефон в 9-й колонке (I)
                return (await ws.cell(cell.row, 9)).value
        except:
            return None
        return None

    async def add_payment(self, game_date, payer_name, amount, count, cost, debtors_ids: list, debtors_names: list):
        """Создает запись о платеже"""
        ws = await self._get_ws("Финансы")
        
        # Превращаем списки в строки для хранения
        ids_str = ",".join(map(str, debtors_ids)) # "12345,67890"
        names_str = ", ".join(debtors_names)      # "Вася, Петя"
        
        row = [
            game_date,
            payer_name,
            amount,
            count,
            cost,
            ids_str,
            names_str,
            "Открыт"
        ]
        await ws.insert_row(row, index=2)

    async def remove_debtor(self, user_id: int, user_name: str):
        """
        Удаляет ID из списка должников.
        Возвращает: (остаток_долга, список_имен_кто_остался)
        """
        ws = await self._get_ws("Финансы")
        # Ищем строку, где есть этот ID в столбце F (6)
        # Это не идеально (find ищет полное совпадение или часть), 
        # но для MVP списка через запятую сойдет.
        # Лучше перебрать последние 10 строк, чтобы найти актуальный долг.
        
        records = await ws.get_all_records()
        # Идем сверху вниз (index=2 в таблице = index 0 в records)
        # Нам нужна самая свежая запись со статусом "Открыт"
        
        target_row_idx = None
        target_row_data = None
        
        for i, row in enumerate(records):
            if str(user_id) in str(row.get("ID должников", "")) and row.get("Статус") == "Открыт":
                # Нашли! (i - это индекс в списке records. В таблице это i + 2)
                target_row_idx = i + 2
                target_row_data = row
                break
        
        if not target_row_idx:
            return None, None # Не нашли долг

        # Парсим текущие списки
        current_ids = str(target_row_data.get("ID должников", "")).split(",")
        current_names = str(target_row_data.get("Имена должников", "")).split(", ")
        
        # Удаляем плательщика
        new_ids = [x for x in current_ids if x.strip() != str(user_id)]
        
        # Имена удалять сложнее (нет четкой связи), поэтому просто удаляем по значению
        # или оставляем как есть, обновляя только ID. 
        # Но для красоты попробуем удалить имя.
        new_names = [n for n in current_names if n.strip() not in user_name and user_name not in n] 
        # (Это упрощение, в идеале хранить dict {id: name})

        # Обновляем ячейки
        await ws.update_cell(target_row_idx, 6, ",".join(new_ids))
        # await ws.update_cell(target_row_idx, 7, ", ".join(new_names)) # Имена можно не трогать, чтобы видеть историю, или трогать.
        
        # Если список ID пуст - закрываем долг
        if not new_ids or new_ids == ['']:
            await ws.update_cell(target_row_idx, 8, "Закрыт") # Статус
            return 0, []
            
        return len(new_ids), new_names

    async def get_pending_payments(self):
        """Возвращает список активных сборов для напоминаний"""
        ws = await self._get_ws("Финансы")
        records = await ws.get_all_records()
        
        pending = []
        for row in records:
            if row.get("Статус") == "Открыт" and row.get("ID должников"):
                pending.append({
                    "date": row.get("Дата игры"),
                    "cost": row.get("С человека"),
                    "payer": row.get("Плательщик"),
                    "debtors_ids": str(row.get("ID должников")).split(",")
                })
        return pending

sheets = GoogleSheetsService()