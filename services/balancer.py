import random
import itertools
from services.google_sheets import sheets

class Player:
    # Добавил аргумент nick в __init__
    def __init__(self, name, nick="", rating=3.0, role="Универсал", height=180, weight=80):
        self.name = name
        self.nick = nick  # Сохраняем ник
        # Парсим рейтинг
        try:
            self.rating = float(str(rating).split(" ")[0])
        except:
            self.rating = 3.0
            
        self.role = role
        # Парсим физику (защита от пустых полей)
        self.height = int(height) if height and str(height).isdigit() else 180
        self.weight = int(weight) if weight and str(weight).isdigit() else 80

        # Упрощаем роль для алгоритма (Нормализация)
        r_lower = role.lower()
        if "большой" in r_lower or "центр" in r_lower:
            self.simple_role = "big"
        elif "снайпер" in r_lower or "разыгрывающий" in r_lower:
            self.simple_role = "sniper"
        else:
            self.simple_role = "other"

    def __repr__(self):
        return f"{self.name} ({self.rating})"

async def form_teams(game_date: str):
    # 1. Голоса
    votes = await sheets.get_votes_for_date(game_date)
    if not votes:
        return None, "❌ Никто не записался."

    # 2. Статистика
    stats_db = await sheets.get_players_stats()

    active_players = []
    for v in votes:
        # Достаем ник из голосов
        current_nick = v.get('nick', '')
        
        key = v['nick'] if v['nick'] in stats_db else v['name']
        if key in stats_db:
            p_data = stats_db[key]
            player = Player(
                name=v['name'],
                nick=current_nick,  # Передаем ник
                rating=p_data['rating'], 
                role=p_data['role'], 
                height=p_data['height'], 
                weight=p_data['weight']
            )
        else:
            player = Player(name=v['name'], nick=current_nick, rating=3.0, role="Новичок")
        active_players.append(player)

    count = len(active_players)
    if count < 4:
         return None, f"⚠ Мало игроков: {count}."

    # --- АНАЛИЗ ИСТОРИИ ---
    print("⏳ Анализируем историю игр...")
    past_games = await sheets.get_last_games_teams(limit=2, exclude_date=game_date)
    forbidden_pairs = set()
    
    if len(past_games) >= 2:
        game1_teams = past_games[0]
        game2_teams = past_games[1]
        
        pairs_g1 = set()
        for team_set in game1_teams:
            for pair in itertools.combinations(sorted(list(team_set)), 2):
                pairs_g1.add(pair)
        
        pairs_g2 = set()
        for team_set in game2_teams:
            for pair in itertools.combinations(sorted(list(team_set)), 2):
                pairs_g2.add(pair)
        
        forbidden_pairs = pairs_g1.intersection(pairs_g2)
        print(f"🚫 Найдено нежелательных пар: {len(forbidden_pairs)}")

    # --- КОЛИЧЕСТВО КОМАНД ---
    num_teams = 2
    if count >= 18:
        num_teams = 3
    elif 15 <= count < 18:
        num_teams = 3
    elif count == 9:
        num_teams = 3
    
    reserve_pool = []
    if num_teams == 3 and count > 18:
        random.shuffle(active_players)
        reserve_pool = active_players[18:]
        active_players = active_players[:18]

    # --- БАЛАНСИРОВКА 2.0 (Спортивная) ---
    best_teams = []
    min_total_penalty = 100000 
    
    iterations = 10000 
    
    for _ in range(iterations): 
        random.shuffle(active_players)
        current_teams = [active_players[i::num_teams] for i in range(num_teams)]
        if any(len(t) == 0 for t in current_teams): continue

        # --- СБОР МЕТРИК ---
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

        # --- РАСЧЕТ ШТРАФОВ ---
        diff_rating = max(ratings) - min(ratings)
        penalty_history = history_violations * 2.0
        
        diff_bigs = max(bigs_counts) - min(bigs_counts)
        penalty_bigs = 0
        if diff_bigs > 1:
            penalty_bigs = 1.5 
            
        diff_snipers = max(snipers_counts) - min(snipers_counts)
        penalty_snipers = 0
        if diff_snipers > 1:
            penalty_snipers = 0.8
            
        diff_height = max(heights) - min(heights)
        penalty_height = diff_height / 15.0 
        
        diff_weight = max(weights) - min(weights)
        penalty_weight = diff_weight / 20.0

        total_penalty = (
            diff_rating + 
            penalty_history + 
            penalty_bigs + 
            penalty_snipers + 
            penalty_height + 
            penalty_weight
        )
        
        if total_penalty < min_total_penalty:
            min_total_penalty = total_penalty
            best_teams = current_teams
            
            if total_penalty < 0.15:
                break

    # --- ФОРМИРОВАНИЕ ОТЧЕТА ---
    all_names = ["White eggs ⚪️", "Black hole ⚫", "Red Tits 🔴"]
    team_names = all_names[:num_teams]
    
    report_html = f"🏀 <b>Составы на {game_date}</b>\n"
    report_html += f"Всего в заявке: {count}\n\n"
    
    teams_data_for_sheet = []

    for i, team in enumerate(best_teams):
        t_name = team_names[i]
        
        avg_r = sum(p.rating for p in team) / len(team)
        avg_h = sum(p.height for p in team) / len(team)
        avg_w = sum(p.weight for p in team) / len(team)
        
        # --- ИЗМЕНЕНИЕ ЗДЕСЬ: Добавляем никнейм в список ---
        players_list_html = []
        for p in team:
            # Если ник есть, добавляем пробел перед ним, иначе пустота
            nick_display = f" {p.nick}" if p.nick else ""
            players_list_html.append(f"- {p.name}{nick_display} (<i>{p.role}, {p.rating}</i>)")
            
        players_list_str = "\n".join(players_list_html)
        # ----------------------------------------------------
        
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
        report_html += f"📓 <b>Резерв:</b> {res_list}\n"
        teams_data_for_sheet.append({
            "date": game_date,
            "team_name": "Резерв",
            "roster": "\n".join([p.name for p in reserve_pool]),
            "rating": "-"
        })
        
    await sheets.save_teams_batch(teams_data_for_sheet)
    
    return best_teams, report_html