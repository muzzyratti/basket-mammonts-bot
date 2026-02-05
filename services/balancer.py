import random
import itertools
from datetime import datetime
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from services.google_sheets import sheets
# Импортируй свои настройки бота (token и т.д.)
# from config import BOT_TOKEN 

# --- КЛАСС ИГРОКА ---
class Player:
    def __init__(self, name, nick="", rating=3.0, role="Универсал", height=180, weight=80, raw_time=""):
        self.name = name
        self.nick = nick
        self.raw_time = raw_time 
        
        try:
            self.rating = float(str(rating).split(" ")[0])
        except:
            self.rating = 3.0
            
        self.role = role
        self.height = int(height) if height and str(height).isdigit() else 180
        self.weight = int(weight) if weight and str(weight).isdigit() else 80

        r_lower = role.lower()
        if "большой" in r_lower or "центр" in r_lower:
            self.simple_role = "big"
        elif "снайпер" in r_lower or "разыгрывающий" in r_lower:
            self.simple_role = "sniper"
        else:
            self.simple_role = "other"

    def __repr__(self):
        return f"{self.name} ({self.rating})"

# --- ПАРСИНГ ВРЕМЕНИ ---
def parse_signup_time(time_str):
    if not time_str:
        return datetime.max 
    
    # Жесткая чистка
    clean_str = str(time_str).replace("\xa0", " ").strip()
    
    formats = [
        "%d.%m.%Y %H:%M:%S", 
        "%d.%m.%Y %H:%M",
        "%Y-%m-%d %H:%M:%S", 
        "%Y-%m-%d %H:%M",
        "%d/%m/%Y %H:%M:%S", 
        "%d/%m/%Y %H:%M",
        "%H:%M:%S",
        "%d.%m.%Y"
    ]
    for fmt in formats:
        try:
            return datetime.strptime(clean_str, fmt)
        except ValueError:
            continue
            
    # Не спамим в лог, просто возвращаем макс
    return datetime.max 

# --- УМНЫЙ ПОИСК ЗНАЧЕНИЯ ПО СИНОНИМАМ ---
def get_val_smart(data, keys_list, default=None):
    """
    Ищет значение в словаре data, перебирая ключи из keys_list.
    Игнорирует регистр ключей.
    """
    data_keys_lower = {str(k).lower().strip(): k for k in data.keys()}
    
    for key_variant in keys_list:
        kv_lower = key_variant.lower().strip()
        if kv_lower in data_keys_lower:
            real_key = data_keys_lower[kv_lower]
            val = data[real_key]
            if val: return val
            
    return default

# --- ОСНОВНАЯ ФУНКЦИЯ ---
async def form_teams(game_date: str):
    print(f"\n🐛 --- НАЧАЛО СБОРА ({game_date}) ---")
    
    votes = await sheets.get_votes_for_date(game_date)
    if not votes:
        return None, "❌ Никто не записался."

    stats_db = await sheets.get_players_stats()
    # stats_db - это словарь { 'ID': { 'Имя': ..., 'Рейтинг': ... } }
    
    print(f"📚 База игроков: {len(stats_db)} записей.")

    # --- 1. СОЗДАЕМ ИНДЕКСЫ ДЛЯ ПОИСКА ---
    players_by_nick = {}
    players_by_id = {}

    for p_id, p_data in stats_db.items():
        clean_id = str(p_id).strip()
        players_by_id[clean_id] = p_data

        # Ищем ник (пробуем разные варианты названия колонки)
        p_nick = get_val_smart(p_data, ['ник', 'nick', 'nickname'])
        
        if p_nick:
            clean_nick = str(p_nick).replace("@", "").strip().lower()
            if clean_nick:
                players_by_nick[clean_nick] = p_data

    active_players = []
    
    # --- 2. МАТЧИНГ ---
    for v in votes:
        # Извлекаем данные из голоса (тоже через синонимы)
        raw_vote_nick = get_val_smart(v, ['ник', 'nick', 'username'], "")
        vote_name = get_val_smart(v, ['имя', 'name'], "Неизвестный")
        signup_time_str = get_val_smart(v, ['время записи', 'время', 'time', 'timestamp'], "")
        vote_id = str(get_val_smart(v, ['id', 'user_id', 'id telegram'], "")).strip()

        vote_nick_clean = str(raw_vote_nick).replace("@", "").strip().lower()
        vote_name = str(vote_name).strip()
        
        # Ищем в базе
        found_data = None
        
        if vote_id and vote_id in players_by_id:
             found_data = players_by_id[vote_id]
        elif vote_nick_clean and vote_nick_clean in players_by_nick:
            found_data = players_by_nick[vote_nick_clean]
        
        # Применяем данные
        final_name = vote_name
        rating = 3.0
        role = "Новичок"
        height = 180
        weight = 80
        
        if found_data:
            # ВОТ ТУТ БЫЛА ОШИБКА. Теперь ищем и по-русски, и по-английски
            rating = get_val_smart(found_data, ['рейтинг', 'rating'], 3.0)
            role = get_val_smart(found_data, ['роль', 'role'], 'Универсал')
            height = get_val_smart(found_data, ['рост', 'height'], 180)
            weight = get_val_smart(found_data, ['вес', 'weight'], 80)
            
            db_name = get_val_smart(found_data, ['имя', 'name'], None)
            if db_name:
                final_name = str(db_name).strip()
        else:
            # Для отладки: кого не нашли
            print(f"⚠️ Не найден в базе: {vote_name} (@{vote_nick_clean})")

        player = Player(
            name=final_name,    
            nick=raw_vote_nick, 
            rating=rating, 
            role=role, 
            height=height, 
            weight=weight,
            raw_time=signup_time_str
        )
        active_players.append(player)

    # --- 3. СОРТИРОВКА ---
    active_players.sort(key=lambda x: parse_signup_time(x.raw_time))

    count = len(active_players)
    if count < 4:
         return None, f"⚠ Мало игроков: {count}."

    # --- 4. РЕЗЕРВ ---
    reserve_pool = []
    LIMIT = 18
    if count > LIMIT:
        reserve_pool = active_players[LIMIT:] 
        active_players = active_players[:LIMIT]

    # --- 5. БАЛАНСИРОВКА (СТАНДАРТНАЯ) ---
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

    num_teams = 2
    if len(active_players) >= 15:
        num_teams = 3
    
    best_teams = []
    min_total_penalty = 100000 
    iterations = 10000 
    players_pool = list(active_players)

    for _ in range(iterations): 
        random.shuffle(players_pool)
        current_teams = [players_pool[i::num_teams] for i in range(num_teams)]
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
            if total_penalty < 0.15: break

    # --- ОТЧЕТ ---
    all_names = ["White eggs ⚪️", "Black hole ⚫", "Red Tits 🔴"]
    team_names = all_names[:num_teams]
    
    report_html = f"🏀 <b>Составы на {game_date}</b>\n"
    report_html += f"Игроков в основе: {len(active_players)}\n"
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
            nick_display = f" {p.nick}" if p.nick else ""
            players_list_html.append(f"- {p.name}{nick_display} (<i>{p.role}, {p.rating}</i>)")
            
        block_html = f"<b>{t_name}</b>\n📊 <i>Ср. рейтинг: {avg_r:.2f} | Ср. рост: {avg_h:.0f}см | Ср. вес: {avg_w:.0f}кг</i>\n" + "\n".join(players_list_html) + "\n\n"
        report_html += block_html
        
        players_clean = "\n".join([f"{p.name} ({p.role})" for p in team])
        teams_data_for_sheet.append({
            "date": game_date, "team_name": t_name, "roster": players_clean, "rating": f"{avg_r:.2f}"
        })

    if reserve_pool:
        # ВОТ ЗДЕСЬ ИЗМЕНЕНИЕ: Добавляем ник к имени
        res_list = ", ".join([f"{p.name} {p.nick}" if p.nick else p.name for p in reserve_pool])
        
        report_html += f"📓 <b>Резерв ({len(reserve_pool)}):</b> {res_list}\n"
        
        teams_data_for_sheet.append({
            "date": game_date, "team_name": "Резерв", "roster": "\n".join([p.name for p in reserve_pool]), "rating": "-"
        })
        
    await sheets.save_teams_batch(teams_data_for_sheet)
    return best_teams, report_html