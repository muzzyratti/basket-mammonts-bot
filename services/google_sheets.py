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
        """Возвращает словарь: {Ник: stats, Имя: stats, ID: stats}"""
        ws = await self._get_ws("Мамонты")
        records = await ws.get_all_records()
        
        players = {}
        for row in records:
            # Игнорируем пустые строки (если вдруг)
            if not row.get('Имя'): continue

            # СОХРАНЯЕМ ВСЕ ПОЛЯ ВНУТРЬ СЛОВАРЯ
            p_stats = {
                'name': row.get('Имя'),        # ВАЖНО: Добавил имя внутрь
                'nick': row.get('Ник'),        # ВАЖНО: Добавил ник внутрь
                'id': str(row.get('ID Telegram')), # ВАЖНО: Добавил ID
                'height': row.get('Рост'),
                'weight': row.get('Вес'),
                'role': row.get('Роль'),
                'rating': row.get('Рейтинг')
            }
            
            # 1. Сохраняем по ID (самый надежный ключ)
            tg_id = str(row.get('ID Telegram'))
            if tg_id:
                players[tg_id] = p_stats

            # 2. Сохраняем по Нику (с @ и без)
            nick = row.get('Ник')
            if nick and nick != "NoNick":
                players[nick] = p_stats
                if nick.startswith("@"):
                    players[nick[1:]] = p_stats
            
            # 3. Сохраняем по Имени (как фоллбэк)
            name = row.get('Имя')
            if name:
                players[name] = p_stats
                
        return players

    async def get_votes_for_date(self, date_str: str):
        """
        Получает список тех, кто АКТУАЛЬНО записан на игру.
        Разделяет людей с NoNick по именам.
        """
        ws = await self._get_ws("Голосования")
        records = await ws.get_all_records()
        
        final_status = {}
        
        from datetime import datetime
        def parse_vote_time(t_str):
            try: return datetime.strptime(str(t_str).strip(), "%d.%m.%Y %H:%M:%S")
            except: return datetime.min

        day_records = [r for r in records if r.get('Дата игры') == date_str]
        # Сортируем от старых к новым
        day_records.sort(key=lambda x: parse_vote_time(x.get('Время записи')))

        for row in day_records:
            nick = str(row.get('Ник', '')).strip()
            name = str(row.get('Имя', '')).strip()
            
            # ОПРЕДЕЛЕНИЕ КЛЮЧА
            # Считаем ник валидным, только если это не пустая строка и не "nonick"
            is_valid_nick = nick and nick.lower() != 'nonick'
            
            if is_valid_nick:
                user_key = nick.lower()
            else:
                # Если ника нет или он NoNick -> ключом становится ИМЯ
                # Это разделит "Николая" и "First Name"
                user_key = name.lower()
            
            if not user_key: continue
            
            vote_text = row.get('Голос', '')
            
            if "Я воин мяча" in vote_text:
                if user_key in final_status and final_status[user_key]['status'] == 'active':
                    continue 
                final_status[user_key] = { 'status': 'active', 'data': row }
            else:
                final_status[user_key] = { 'status': 'cancelled', 'data': row }

        players_in = []
        for info in final_status.values():
            if info['status'] == 'active':
                row = info['data']
                row['name'] = row.get('Имя')
                row['nick'] = row.get('Ник')
                row['time'] = row.get('Время записи')
                players_in.append(row)
                
        return players_in

    async def save_teams_batch(self, teams_data: list):
        """
        Сохраняет составы.
        """
        try:
            ws = await self._get_ws("Составы")
            rows_to_insert = []
            
            for team in reversed(teams_data):
                row = [
                    team['date'],       
                    team['team_name'],  
                    team['roster'],     
                    team['rating']      
                ]
                rows_to_insert.append(row)
            
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
            date = str(row.get("Дата игры") or row.get("date") or row.get("Дата трени")).strip()
            roster_str = row.get("Состав команды") or row.get("roster") or row.get("Состав команды")
            
            if date == exclude_date:
                continue
                
            if not date or not roster_str:
                continue
                
            if date not in games_map:
                games_map[date] = []
            
            player_names = set()
            lines = roster_str.split('\n')
            
            for line in lines:
                clean_name = line.split(' (')[0].strip()
                clean_name = clean_name.replace("<b>", "").replace("</b>", "")
                
                if clean_name:
                    player_names.add(clean_name)
            
            games_map[date].append(player_names)

        from datetime import datetime
        def parse_date(d):
            try: return datetime.strptime(d, "%d.%m.%Y")
            except: return datetime.min

        sorted_dates = sorted(games_map.keys(), key=parse_date, reverse=True)
        
        print(f"DEBUG HISTORY: Нашел даты в истории (после фильтра): {sorted_dates}")
        
        last_dates = sorted_dates[:limit]
        
        history = []
        for d in last_dates:
            teams = games_map[d]
            history.append(teams)
            print(f"DEBUG HISTORY: Дата {d}, Команды: {teams}")
            
        return history

    async def get_users_for_notification(self):
        ws = await self._get_ws("Мамонты")
        records = await ws.get_all_records()
        
        user_ids = []
        for row in records:
            notify = str(row.get("Отправлять уведомления", "")).lower()
            if notify == "да":
                user_ids.append(row.get("ID Telegram"))
        return user_ids

    async def get_all_voters_nicks(self, game_date: str) -> set:
        ws = await self._get_ws("Голосования")
        records = await ws.get_all_records()
        
        voted_nicks = set()
        for row in records:
            if row.get('Дата игры') == game_date:
                nick = row.get('Ник')
                if nick:
                    clean_nick = nick.replace("@", "").strip().lower()
                    if clean_nick:
                        voted_nicks.add(clean_nick)
        return voted_nicks

    async def get_user_phone(self, user_id: int):
        ws = await self._get_ws("Мамонты")
        try:
            cell = await ws.find(str(user_id), in_column=1)
            if cell:
                return (await ws.cell(cell.row, 9)).value
        except:
            return None
        return None

    async def add_payment(self, game_date, payer_name, amount, count, cost, debtors_ids: list, debtors_names: list):
        ws = await self._get_ws("Финансы")
        ids_str = ",".join(map(str, debtors_ids)) 
        names_str = ", ".join(debtors_names)      
        row = [game_date, payer_name, amount, count, cost, ids_str, names_str, "Открыт"]
        await ws.insert_row(row, index=2)

    async def remove_debtor(self, user_id: int, user_name: str):
        ws = await self._get_ws("Финансы")
        records = await ws.get_all_records()
        
        target_row_idx = None
        target_row_data = None
        
        for i, row in enumerate(records):
            if str(user_id) in str(row.get("ID должников", "")) and row.get("Статус") == "Открыт":
                target_row_idx = i + 2
                target_row_data = row
                break
        
        if not target_row_idx:
            return None, None

        current_ids = str(target_row_data.get("ID должников", "")).split(",")
        current_names = str(target_row_data.get("Имена должников", "")).split(", ")
        
        new_ids = [x for x in current_ids if x.strip() != str(user_id)]
        new_names = [n for n in current_names if n.strip() not in user_name and user_name not in n] 

        await ws.update_cell(target_row_idx, 6, ",".join(new_ids))
        
        if not new_ids or new_ids == ['']:
            await ws.update_cell(target_row_idx, 8, "Закрыт") 
            return 0, []
            
        return len(new_ids), new_names

    async def get_pending_payments(self):
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