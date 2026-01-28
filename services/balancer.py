import random
import itertools
from datetime import datetime
from services.google_sheets import sheets

class Player:
    def __init__(self, name, nick="", rating=3.0, role="Универсал", height=180, weight=80, raw_time=""):
        self.name = name
        self.nick = nick
        self.raw_time = raw_time # Строка времени для сортировки
        
        # Парсим рейтинг
        try:
            self.rating = float(str(rating).split(" ")[0])
        except:
            self.rating = 3.0
            
        self.role = role
        # Парсим физику
        self.height = int(height) if height and str(height).isdigit() else 180
        self.weight = int(weight) if weight and str(weight).isdigit() else 80

        # Упрощаем роль для алгоритма
        r_lower = role.lower()
        if "большой" in r_lower or "центр" in r_lower:
            self.simple_role = "big"
        elif "снайпер" in r_lower or "разыгрывающий" in r_lower:
            self.simple_role = "sniper"
        else:
            self.simple_role = "other"

    def __repr__(self):
        return f"{self.name} ({self.rating})"

def parse_signup_time(time_str):
    """
    Превращает строку времени из Гугла в объект datetime для сортировки.
    """
    if not time_str:
        return datetime.max 
    
    clean_str = str(time_str).strip()
    formats = [
        "%d.%m.%Y %H:%M:%S",
        "%d.%m.%Y %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%H:%M:%S"
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(clean_str, fmt)
        except ValueError:
            continue
            
    return datetime.max 

async def form_teams(game_date: str):
    print(f"📥 Начинаем сбор команд на {game_date}")
    
    # 1. Голоса
    votes = await sheets.get_votes_for_date(game_date)
    if not votes:
        return None, "❌ Никто не записался."

    # 2. Статистика (Лист "Мамонты")
    stats_db = await sheets.get_players_stats()

    active_players = []
    
    # --- СБОР ДАННЫХ И МАТЧИНГ ---
    for v in votes:
        # Данные из голосования (Telegram)
        vote_nick = v.get('nick', '').strip().replace("@", "").lower() # Чистим ник
        vote_name = v['name'].strip()
        
        # Ищем время
        signup_time_str = ""
        for k, val in v.items():
            if "время" in k.lower() or "time" in k.lower():
                signup_time_str = val
                break
        
        # Данные по умолчанию
        final_name = vote_name # По дефолту имя из ТГ
        rating = 3.0
        role = "Новичок"
        height = 180
        weight = 80
        
        # Поиск игрока в базе (stats_db)
        # Ключи в stats_db у тебя хранятся и как ники (без @), и как имена
        
        p_data = None
        
        # Попытка 1: По нику
        if vote_nick and vote_nick in stats_db:
             p_data = stats_db[vote_nick]
        # Попытка 2: По имени (если нет ника или не нашлось)
        elif vote_name in stats_db:
             p_data = stats_db[vote_name]
             
        # Если нашли профиль в Мамонтах
        if p_data:
            rating = p_data.get('rating', 3.0)
            role = p_data.get('role', 'Универсал')
            height = p_data.get('height', 180)
            weight = p_data.get('weight', 80)
            
            # --- ГЛАВНОЕ: БЕРЕМ ИМЯ ИЗ ТАБЛИЦЫ ---
            # Ищем поле 'Имя' или 'name' в данных профиля
            db_name = p_data.get('Имя') or p_data.get('name')
            if db_name:
                final_name = str(db_name).strip()
            # -------------------------------------

        player = Player(
            name=final_name,    # Теперь здесь строго имя из базы (если нашли)
            nick=v.get('nick', ''), # Сохраняем оригинальный ник для дисплея
            rating=rating, 
            role=role, 
            height=height, 
            weight=weight,
            raw_time=signup_time_str
        )
        active_players.append(player)

    # --- СОРТИРОВКА ПО ВРЕМЕНИ ---
    # Важно: Сортируем ДО отсечения резерва
    active_players.sort(key=lambda x: parse_signup_time(x.raw_time))

    count = len(active_players)
    if count < 4:
         return None, f"⚠ Мало игроков: {count}."

    # --- НАРЕЗКА РЕЗЕРВА (СТРОГО 18) ---
    reserve_pool = []
    LIMIT = 18
    
    if count > LIMIT:
        # Все кто после 18-го — в резерв
        reserve_pool = active_players[LIMIT:] 
        active_players = active_players[:LIMIT]
        print(f"✂️ Отрезали {len(reserve_pool)} чел. в резерв.")

    # Обновляем кол-во активных после среза
    active_count = len(active_players)

    # --- АНАЛИЗ ИСТОРИИ ---
    print("⏳ Анализируем историю игр...")
    past_games = await sheets.get_last_games_teams(limit=2, exclude_date=game_date)
    forbidden_pairs = set()
    if len(past_games) >= 2:
        for i in range(2):
            team_set_list = past_games[i]
            current_pairs = set()
            for t_s in team_set_list:
                for pair in itertools.combinations(sorted(list(t_s)), 2):
                    current_pairs.add(pair)
            if i == 0:
                forbidden_pairs = current_pairs
            else:
                forbidden_pairs = forbidden_pairs.intersection(current_pairs)

    # --- КОЛИЧЕСТВО КОМАНД ---
    # Логика простая: если нас 18 (после среза) или около того -> 3 команды
    # Если меньше 15 -> 2 команды
    num_teams = 2
    if active_count >= 15:
        num_teams = 3
    
    # --- БАЛАНСИРОВКА ---
    best_teams = []
    min_total_penalty = 100000 
    iterations = 10000 
    
    players_pool = list(active_players)

    for _ in range(iterations): 
        random.shuffle(players_pool)
        
        current_teams = [players_pool[i::num_teams] for i in range(num_teams)]
        # Проверка на пустые команды (на всякий случай)
        if any(len(t) == 0 for t in current_teams): continue

        ratings = []
        heights = []
        weights = []
        bigs_counts = []
        snipers_counts = []
        history_violations = 0

        for team in current_teams:
            ratings.append(sum(p.rating for p in team) / len(team))
            heights.append(sum(p.height for p in team) / len(team))
            weights.append(sum(p.weight for p in team) / len(team))
            
            bigs_counts.append(sum(1 for p in team if p.simple_role == 'big'))
            snipers_counts.append(sum(1 for p in team if p.simple_role == 'sniper'))
            
            team_names = sorted([p.name for p in team])
            for pair in itertools.combinations(team_names, 2):
                if pair in forbidden_pairs:
                    history_violations += 1

        diff_rating = max(ratings) - min(ratings)
        penalty_history = history_violations * 2.0
        
        diff_bigs = max(bigs_counts) - min(bigs_counts)
        penalty_bigs = 0 if diff_bigs <= 1 else 1.5
        diff_snipers = max(snipers_counts) - min(snipers_counts)
        penalty_snipers = 0 if diff_snipers <= 1 else 0.8
        penalty_height = (max(heights) - min(heights)) / 15.0 
        penalty_weight = (max(weights) - min(weights)) / 20.0

        total_penalty = (diff_rating + penalty_history + penalty_bigs + 
                         penalty_snipers + penalty_height + penalty_weight)
        
        if total_penalty < min_total_penalty:
            min_total_penalty = total_penalty
            best_teams = [list(t) for t in current_teams]
            
            if total_penalty < 0.15:
                break

    # --- ОТЧЕТ ---
    all_names = ["White eggs ⚪️", "Black hole ⚫", "Red Tits 🔴"]
    team_names = all_names[:num_teams]
    
    report_html = f"🏀 <b>Составы на {game_date}</b>\n"
    report_html += f"Игроков в основе: {active_count}\n"
    if reserve_pool:
        report_html += f"В резерве: {len(reserve_pool)}\n"
    report_html += "\n"
    
    teams_data_for_sheet = []

    for i, team in enumerate(best_teams):
        t_name = team_names[i]
        
        avg_r = sum(p.rating for p in team) / len(team)
        avg_h = sum(p.height for p in team) / len(team)
        avg_w = sum(p.weight for p in team) / len(team)
        
        players_list_html = []
        for p in team:
            # Имя теперь берется из self.name (которое мы взяли из базы)
            # Ник добавляем для справки, если он есть
            nick_display = f" {p.nick}" if p.nick else ""
            players_list_html.append(f"- {p.name}{nick_display} (<i>{p.role}, {p.rating}</i>)")
            
        players_list_str = "\n".join(players_list_html)
        
        stats_line = f"Ср. рейтинг: {avg_r:.2f} | Ср. рост: {avg_h:.0f}см | Ср. вес: {avg_w:.0f}кг\n"
        
        block_html = f"<b>{t_name}</b>\n📊 <i>{stats_line}</i>\n{players_list_str}\n\n"
        report_html += block_html
        
        players_clean = "\n".join([f"{p.name} ({p.role})" for p in team])
        
        teams_data_for_sheet.append({
            "date": game_date,
            "team_name": t_name,
            "roster": players_clean,
            "rating": f"{avg_r:.2f}"
        })

    if reserve_pool:
        res_list = ", ".join([p.name for p in reserve_pool])
        report_html += f"📓 <b>Резерв ({len(reserve_pool)}):</b> {res_list}\n"
        teams_data_for_sheet.append({
            "date": game_date,
            "team_name": "Резерв",
            "roster": "\n".join([p.name for p in reserve_pool]),
            "rating": "-"
        })
        
    await sheets.save_teams_batch(teams_data_for_sheet)
    
    return best_teams, report_html