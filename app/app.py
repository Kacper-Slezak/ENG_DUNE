# app.py
from flask import Flask, render_template, request, redirect, url_for, flash
import json
import os

from game_manager import (
    load_game_data, perform_full_game_reset, save_json_file, is_move_valid, process_move, 
    check_and_advance_phase, process_intrigue,
    calculate_reveal_stats, perform_cleanup_and_new_round, 
    GAME_STATE_FILE,
    process_pass_turn,
    process_buy_card,
    get_card_persuasion_cost,
    add_card_to_market,
    set_player_hand,
    AI_PLAYER_NAME,
    process_conflict_set,
    process_conflict_resolve,
    save_json_file_from_text,
    manual_add_intrigue,
    get_intrigue_requirements,
    get_agent_move_requirements,
    process_commit_troops
)

from build_ai_prompt import generate_ai_prompt

app = Flask(__name__)
app.secret_key = 'your_super_secret_dune_key' 

def get_player_names(game_state):
    """Gets player names."""
    if game_state and "players" in game_state:
        return sorted(list(game_state["players"].keys()))
    return []

def get_available_locations(locations_db, game_state):
    """Returns a list of available (free) locations."""
    available_locations = []
    if "locations_state" not in game_state:
         game_state["locations_state"] = {}
    if not locations_db:
        return []
    for loc_id, loc_data in locations_db.items():
        if loc_id.endswith("_influence_path"):
            continue
        location_state = game_state.get("locations_state", {}).get(loc_id, {})
        if not location_state:
            game_state["locations_state"][loc_id] = {"occupied_by": None}
        if location_state.get("occupied_by") is None:
             available_locations.append({
                "id": loc_id,
                "name": loc_data.get("name", loc_id)
            })
    return sorted(available_locations, key=lambda x: x['name'])

@app.route('/', methods=['GET', 'POST'])
def index():
    game_state, locations_db, cards_db, intrigues_db, conflicts_db, leaders_db = load_game_data() 

    if not all([game_state, locations_db, cards_db, intrigues_db, conflicts_db, leaders_db]): 
        flash("CRITICAL ERROR: Cannot load core game data. Check JSON files.", "error")
        return render_template('error.html'), 500

    current_phase = game_state.get("current_phase", "Unknown Phase") 
    if current_phase == "REVEAL":
        return redirect(url_for('reveal_phase'))

    if request.method == 'POST':
        player_name_input = request.form.get('player_name')
        card_id_input = request.form.get('card_id')
        location_id_input = request.form.get('location_id')
        
        # 1. Podstawowa walidacja ruchu
        is_valid, message = is_move_valid(game_state, locations_db, leaders_db, cards_db, player_name_input, card_id_input, location_id_input) 

        if not is_valid:
            flash(f"Invalid move: {message}", "error")
            return redirect(url_for('index'))

        # 2. (NOWA LOGIKA) Sprawdź, czy ruch wymaga decyzji
        card_data = cards_db.get(card_id_input, {})
        location_data = locations_db.get(location_id_input, {})
        player_state = game_state.get("players", {}).get(player_name_input, {})
        
        requirements = get_agent_move_requirements(card_data, location_data, leaders_db, player_state)

        if requirements["type"] == "simple":
            # --- Ruch jest prosty, wykonaj natychmiast ---
            new_game_state = process_move(game_state, locations_db, cards_db, leaders_db, player_name_input, card_id_input, location_id_input) # kwargs nie są potrzebne
            final_game_state = check_and_advance_phase(new_game_state, cards_db)
            
            if save_json_file(GAME_STATE_FILE, final_game_state):
                 flash(f"Success! Player {player_name_input}'s move has been played.", "success")
            else:
                 flash("CRITICAL ERROR: Cannot save game state to disk.", "error")
        else:
            # --- Ruch jest złożony, wymaga decyzji ---
            # Zapisz stan na wszelki wypadek
            save_json_file(GAME_STATE_FILE, game_state)
            flash(f"Move requires a decision for effect from: {requirements.get('source', 'Unknown')}", "success")
            # Przekieruj do nowego widoku decyzji
            return redirect(url_for('resolve_agent_move', 
                                    player_name=player_name_input, 
                                    card_id=card_id_input,
                                    location_id=location_id_input))
        
        return redirect(url_for('index'))

    current_player = game_state.get("currentPlayer", "Unknown Player")
    current_round = game_state.get("round", 1) 
    round_history = game_state.get("round_history", [])
    player_names = get_player_names(game_state)
    available_locations = get_available_locations(locations_db, game_state)
    
    # Przekaż listę wszystkich intryg do szablonu
    all_intrigues = intrigues_db if intrigues_db else {}
    
    current_conflict = game_state.get("current_conflict_card", {"name": "N/A", "rewards_text": []})
    
    player_card_map = {}
    player_agent_map = {}
    player_intrigue_map = {}
    
    player_states = game_state.get("players", {})
    
    for player_name, player_data in player_states.items():
        card_ids_list = player_data.get("hand", [])
        player_card_list = []
        for card_id in card_ids_list:
            if card_id in cards_db:
                player_card_list.append({
                    "id": card_id,
                    "name": cards_db[card_id].get("name", card_id)
                })
        player_card_map[player_name] = sorted(player_card_list, key=lambda x: x['name'])
    
        player_agent_map[player_name] = {
            "placed": player_data.get("agents_placed", 0),
            "total": player_data.get("agents_total", 2),
            "has_passed": player_data.get("has_passed", False),
            "draw_deck_count": len(player_data.get("draw_deck", []))
        }
        
        intrigue_list = []
        for intrigue_id in player_data.get("intrigue_hand", []):
            intrigue_data = intrigues_db.get(intrigue_id, {})
            intrigue_list.append({
                "id": intrigue_id,
                "name": intrigue_data.get("name", intrigue_id)
            })
        player_intrigue_map[player_name] = sorted(intrigue_list, key=lambda x: x['name'])

        
    return render_template('index.html', 
        current_player=current_player, 
        current_phase=current_phase, 
        current_round=current_round, 
        round_history=round_history,
        player_names=player_names,
        player_card_map=player_card_map,
        player_agent_map=player_agent_map, 
        player_intrigue_map=player_intrigue_map,
        locations=available_locations,
        ai_player_name=AI_PLAYER_NAME,
        current_conflict=current_conflict,
        all_conflicts=conflicts_db,
        all_intrigues=all_intrigues
    )

@app.route('/full_reset')
def full_reset():
    success, message = perform_full_game_reset()
    if success:
        flash(message, "success")
    else:
        flash(message, "error")
    return redirect(url_for('index'))

@app.route('/set_conflict', methods=['POST'])
def set_conflict():
    game_state, _, _, _, conflicts_db, _ = load_game_data()

    if game_state.get("current_phase") != "AGENT_TURN":
        flash("Cannot set conflict: Not in AGENT_TURN phase.", "error")
        return redirect(url_for('index'))

    has_moves = any("player" in entry for entry in game_state.get("round_history", []))
    if has_moves:
        flash("Cannot change conflict: Moves have already been made this round.", "error")
        return redirect(url_for('index'))

    conflict_id = request.form.get('conflict_id')
    
    is_valid, message = process_conflict_set(game_state, conflicts_db, conflict_id)
    
    if is_valid:
        if save_json_file(GAME_STATE_FILE, game_state):
            flash(message, "success")
        else:
            flash("CRITICAL ERROR: Cannot save game state after setting conflict.", "error")
    else:
        flash(f"Failed to set conflict: {message}", "error")
        
    return redirect(url_for('index'))

@app.route('/play_intrigue', methods=['POST'])
def play_intrigue():
    game_state, _, _, intrigues_db, _, _ = load_game_data()

    current_phase = game_state.get("current_phase", "AGENT_TURN")
    redirect_target = 'reveal_phase' if current_phase == "REVEAL" else 'index'

    if current_phase not in ["AGENT_TURN", "REVEAL"]:
        flash(f"Cannot play intrigue: Not in AGENT_TURN or REVEAL phase.", "error")
        return redirect(url_for(redirect_target))

    player_name_input = request.form.get('player_name')
    intrigue_id_input = request.form.get('intrigue_id')
    
    # 1. Sprawdź, czy gracz w ogóle ma tę kartę
    player_state = game_state.get("players", {}).get(player_name_input)
    if not player_state or intrigue_id_input not in player_state.get("intrigue_hand", []):
        flash(f"Invalid play: Player {player_name_input} does not have card {intrigue_id_input}.", "error")
        return redirect(url_for(redirect_target))

    # 2. Sprawdź, czy karta wymaga decyzji
    requirements = get_intrigue_requirements(intrigue_id_input, intrigues_db)
    
    if requirements["type"] == "simple" or requirements["type"] == "not_found":
        # Prosta karta -> wykonaj natychmiast bez dodatkowych decyzji
        is_valid, message = process_intrigue(game_state, intrigues_db, player_name_input, intrigue_id_input)
        
        if is_valid:
            save_json_file(GAME_STATE_FILE, game_state)
            flash(f"Intrigue played: {message}", "success")
        else:
            flash(f"Invalid intrigue play: {message}", "error")
        
        return redirect(url_for(redirect_target))
        
    else:
        # Karta złożona -> Przekieruj do nowego widoku, aby podjąć decyzję
        # Zapisz stan na wszelki wypadek (choć karta nie została jeszcze zagrana)
        save_json_file(GAME_STATE_FILE, game_state)
        return redirect(url_for('resolve_intrigue', 
                                player_name=player_name_input, 
                                intrigue_id=intrigue_id_input))


# DODAJ TĘ NOWĄ TRASĘ (GET)
@app.route('/resolve_intrigue/<string:player_name>/<string:intrigue_id>')
def resolve_intrigue(player_name, intrigue_id):
    """
    Wyświetla stronę, na której gracz może podjąć decyzję 
    dotyczącą złożonej karty intrygi.
    """
    game_state, _, _, intrigues_db, _, _ = load_game_data()
    
    card_data = intrigues_db.get(intrigue_id)
    if not card_data:
        flash(f"Error: Intrigue card {intrigue_id} not found.", "error")
        return redirect(url_for('index'))
        
    player_state = game_state.get("players", {}).get(player_name, {})
    
    # Pobierz wymagania (typ i dane)
    requirements = get_intrigue_requirements(intrigue_id, intrigues_db)

    return render_template('resolve_intrigue.html',
        player_name=player_name,
        player_resources=player_state.get("resources", {}),
        card_id=intrigue_id,
        card_data=card_data,
        requirements=requirements
    )


# DODAJ TĘ NOWĄ TRASĘ (POST)
@app.route('/execute_intrigue', methods=['POST'])
def execute_intrigue():
    """
    Odbiera decyzję gracza z formularza i wywołuje 
    "idealną" funkcję process_intrigue z odpowiednimi kwargs.
    """
    game_state, _, _, intrigues_db, _, _ = load_game_data()
    
    # Odczytaj dane z formularza
    player_name = request.form.get('player_name')
    intrigue_id = request.form.get('intrigue_id')
    
    # Przygotuj słownik kwargs dla decyzji
    kwargs = {}
    if 'pay_cost' in request.form:
        kwargs['pay_cost'] = request.form['pay_cost'] == 'true'
        
    if 'choice_index' in request.form:
        try:
            kwargs['choice_index'] = int(request.form['choice_index'])
        except ValueError:
            flash("Invalid choice index received.", "error")
            return redirect(url_for('index'))

    # Wywołaj "idealny" silnik z zebranymi decyzjami
    is_valid, message = process_intrigue(
        game_state, 
        intrigues_db, 
        player_name, 
        intrigue_id, 
        **kwargs # Rozpakuj decyzje tutaj
    )

    if is_valid:
        save_json_file(GAME_STATE_FILE, game_state)
        flash(f"Intrigue executed: {message}", "success")
    else:
        save_json_file(GAME_STATE_FILE, game_state)
        flash(f"Intrigue failed: {message}", "error")

    current_phase = game_state.get("current_phase", "AGENT_TURN")
    redirect_target = 'reveal_phase' if current_phase == "REVEAL" else 'index'
    
    return redirect(url_for(redirect_target))


@app.route('/pass_turn', methods=['POST'])
def pass_turn():
    game_state, _, cards_db, _, _, _ = load_game_data()
    
    if game_state.get("current_phase") != "AGENT_TURN":
        flash("Cannot pass: Not in AGENT_TURN phase.", "error")
        return redirect(url_for('index'))

    player_name_input = request.form.get('player_name')
    if not player_name_input:
         flash("Invalid pass: Player name was missing.", "error")
         return redirect(url_for('index'))
         
    game_state, is_valid, message = process_pass_turn(game_state, player_name_input)
    
    if is_valid:
        flash(message, "success")
        final_game_state = check_and_advance_phase(game_state, cards_db)
        save_json_file(GAME_STATE_FILE, final_game_state)
    else:
        flash(f"Invalid pass: {message}", "error")

    return redirect(url_for('index'))


@app.route('/reveal')
def reveal_phase():
    game_state, _, cards_db, intrigues_db, _, _ = load_game_data()
    
    current_phase = game_state.get("current_phase", "Unknown Phase")
    if current_phase != "REVEAL":
        return redirect(url_for('index'))
        
    all_player_stats = []
    player_states = game_state.get("players", {})
    player_intrigue_map = {}
    for player_name, player_data in player_states.items():
        intrigue_list = []
        for intrigue_id in player_data.get("intrigue_hand", []):
            intrigue_data = intrigues_db.get(intrigue_id, {})
            # Filtrujemy - pokazujemy tylko intrygi bitewne
            if intrigue_data.get("type") == "fight":
                intrigue_list.append({
                    "id": intrigue_id,
                    "name": intrigue_data.get("name", intrigue_id)
                })
    player_intrigue_map[player_name] = sorted(intrigue_list, key=lambda x: x['name'])
    for player_name, player_data in player_states.items():
        stats = player_data.get("reveal_stats", {}) 
        stats["name"] = player_name
        stats["influence"] = player_data.get("influence", {}) 
        stats["vp"] = player_data.get("victory_points", 0)
        stats["base_swords"] = stats.get("base_swords", 0) 
        stats["bonus_swords"] = player_data.get("active_effects", {}).get("fight_bonus_swords", 0)
        stats["troops_garrison"] = player_data.get("resources", {}).get("troops_garrison", 0)
        stats["troops_in_conflict"] = player_data.get("resources", {}).get("troops_in_conflict", 0)

        all_player_stats.append(stats)

    market_cards_details = []
    market_ids = game_state.get("imperium_row", [])
    for card_id in market_ids:
        card_data = cards_db.get(card_id, {})
        card_cost = get_card_persuasion_cost(card_data)
        cost_display = str(card_cost) if card_cost != 999 else "N/A"
        
        market_cards_details.append({
            "id": card_id, 
            "name": card_data.get("name", card_id), 
            "cost": cost_display
        })
        
    all_buyable_cards = []
    for card_id, card_data in cards_db.items():
        if get_card_persuasion_cost(card_data) != 999:
            all_buyable_cards.append({
                "id": card_id,
                "name": card_data.get("name", card_id)
            })
            
    current_conflict = game_state.get("current_conflict_card", {"name": "N/A", "rewards_text": []})

    return render_template('reveal.html',
        current_round=game_state.get("round", 1),
        all_player_stats=all_player_stats,
        market_cards=market_cards_details,
        player_names=get_player_names(game_state),
        ai_player_name=AI_PLAYER_NAME,
        round_history=game_state.get("round_history", []),
        all_buyable_cards=all_buyable_cards,
        player_intrigue_map=player_intrigue_map,
        current_conflict=current_conflict
    )

@app.route('/resolve_conflict_auto', methods=['POST'])
def resolve_conflict_auto():
    game_state, _, _, _, _, _ = load_game_data()

    if game_state.get("current_phase") != "REVEAL":
        flash("Cannot resolve conflict: Not in REVEAL phase.", "error")
        return redirect(url_for('reveal_phase'))

    player_stats = []
    for player_name, player_data in game_state.get("players", {}).items():
        stats = player_data.get("reveal_stats", {})
        base_swords = stats.get("base_swords", 0)
        bonus_swords = player_data.get("active_effects", {}).get("fight_bonus_swords", 0)
        final_swords = base_swords + bonus_swords
        
        player_stats.append({
            "name": player_name,
            "swords": final_swords
        })
    
    # 1.5 Pobierz całkowitą liczbę graczy w grze
    num_players = len(game_state.get("players", {}))

    # 2. Pogrupuj graczy walczących (siła > 0) według ich wyników
    contenders = [p for p in player_stats if p['swords'] > 0]
    if not contenders:
        flash("Conflict resolved automatically: No one had any swords.", "success")
        is_valid, message = process_conflict_resolve(game_state, [], [], [])
        save_json_file(GAME_STATE_FILE, game_state)
        return redirect(url_for('reveal_phase'))

    scores_to_players = {}
    for p in contenders:
        score = p['swords']
        if score not in scores_to_players:
            scores_to_players[score] = []
        scores_to_players[score].append(p['name'])

    # 3. Pobierz posortowaną listę unikalnych wyników
    unique_scores = sorted(scores_to_players.keys(), reverse=True)

    # 4. Zainicjuj listy nagród
    first_place_list = []
    second_place_list = []
    third_place_list = []

    # 5. Przypisz grupy graczy do wyników
    players_score1 = scores_to_players[unique_scores[0]]
    players_score2 = scores_to_players[unique_scores[1]] if len(unique_scores) > 1 else []
    players_score3 = scores_to_players[unique_scores[2]] if len(unique_scores) > 2 else []

    # 6. Zastosuj oficjalne zasady przyznawania nagród
    if len(players_score1) == 1:
        # --- Przypadek A: Czysty zwycięzca 1. miejsca ---
        first_place_list = players_score1
        
        if len(players_score2) == 1:
            # A1: Czysty zwycięzca 2. miejsca
            second_place_list = players_score2
            
            # Sprawdź 3. miejsce
            if len(players_score3) == 1:
                # A1a: Czysty zwycięzca 3. miejsca
                third_place_list = players_score3
            # else (remis o 3. miejsce): nikt nie dostaje 3. nagrody
        
        elif len(players_score2) > 1:
            # A2: Remis o 2. miejsce
            # Nikt nie dostaje 2. nagrody. Zremisowani dostają 3. nagrodę.
            third_place_list = players_score2
    
    elif len(players_score1) > 1:
        # --- Przypadek B: Remis o 1. miejsce ---
        # Nikt nie dostaje 1. nagrody. Zremisowani dostają 2. nagrodę.
        second_place_list = players_score1
        
        # Sprawdź 3. miejsce
        # Następna grupa (players_score2) dostaje 3. nagrodę
        if len(players_score2) == 1:
            # B1: Czysty "następny" gracz
            third_place_list = players_score2
        # else (remis o "następne" miejsce): nikt nie dostaje 3. nagrody

    # --- KONIEC NOWEJ LOGIKI ---
    
    # Przekaż finalne listy do funkcji przetwarzającej nagrody
    is_valid, message = process_conflict_resolve(game_state, first_place_list, second_place_list, third_place_list)
    
    if is_valid:
        if save_json_file(GAME_STATE_FILE, game_state):
            flash(f"Conflict Resolved Automatically! {message}", "success")
        else:
            flash("CRITICAL ERROR: Cannot save game state after resolving conflict.", "error")
    else:
        flash(f"Failed to auto-resolve conflict: {message}", "error")
        
    return redirect(url_for('reveal_phase'))

@app.route('/buy_card', methods=['POST'])
def buy_card():
    game_state, _, cards_db, _, _, _ = load_game_data()
    if game_state.get("current_phase") != "REVEAL":
        flash("Cannot buy cards: Not in REVEAL phase.", "error")
        return redirect(url_for('reveal_phase'))
    player_name = request.form.get('player_name')
    card_id = request.form.get('card_id')
    if not player_name or not card_id:
        flash("Invalid purchase: Player or Card missing.", "error")
        return redirect(url_for('reveal_phase'))
    is_valid, message = process_buy_card(game_state, player_name, card_id, cards_db)
    if is_valid:
        if save_json_file(GAME_STATE_FILE, game_state):
            flash(message, "success")
        else:
            flash("CRITICAL ERROR: Cannot save game state after buying card.", "error")
    else:
        flash(f"Invalid purchase: {message}", "error")
    return redirect(url_for('reveal_phase'))

@app.route('/add_to_market', methods=['POST'])
def add_to_market():
    game_state, _, cards_db, _, _, _ = load_game_data()
    if game_state.get("current_phase") != "REVEAL":
        flash("Cannot modify market: Not in REVEAL phase.", "error")
        return redirect(url_for('reveal_phase'))
    card_id_input = request.form.get('card_id_typed') 
    if not card_id_input:
        flash("Invalid input: No card ID or name provided.", "error")
        return redirect(url_for('reveal_phase'))
    card_id_to_add = None
    if card_id_input in cards_db:
        card_id_to_add = card_id_input
    else:
        for c_id, c_data in cards_db.items():
            if c_data.get("name", "").lower() == card_id_input.lower():
                card_id_to_add = c_id
                break
    if not card_id_to_add:
        flash(f"Invalid card: '{card_id_input}' not found as ID or Name.", "error")
        return redirect(url_for('reveal_phase'))
    is_valid, message = add_card_to_market(game_state, card_id_to_add, cards_db)
    if is_valid:
        if save_json_file(GAME_STATE_FILE, game_state):
            flash(message, "success")
        else:
            flash("CRITICAL ERROR: Cannot save game state after modifying market.", "error")
    else:
        flash(f"Failed to add card: {message}", "error")
    return redirect(url_for('reveal_phase'))


@app.route('/commit_troops', methods=['POST'])
def commit_troops():
    game_state, _, _, _, _, _ = load_game_data()
    if game_state.get("current_phase") != "REVEAL":
        flash("Cannot commit troops: Not in REVEAL phase.", "error")
        return redirect(url_for('reveal_phase'))

    player_name = request.form.get('player_name')
    troop_amount = request.form.get('troop_amount')

    is_valid, message = process_commit_troops(game_state, player_name, troop_amount)

    if is_valid:
        if save_json_file(GAME_STATE_FILE, game_state):
            flash(message, "success")
        else:
            flash("CRITICAL ERROR: Cannot save game state after committing troops.", "error")
    else:
        flash(f"Failed to commit troops: {message}", "error")

    return redirect(url_for('reveal_phase'))


@app.route('/ai_prompt')
def ai_prompt():
    game_state, _, cards_db, _, _, _ = load_game_data()
    
    if game_state is None or cards_db is None:
        flash("CRITICAL ERROR: Cannot load game data or cards data.", "error")
        return render_template('error.html'), 500
        
    # ZMIANA: Odbierz tylko jedną wartość
    prompt_text = generate_ai_prompt(game_state, cards_db) 
    
    # ZMIANA: Przekaż tylko jedną wartość
    return render_template('ai_prompt.html', 
        prompt_text=prompt_text,
        ai_player_name=AI_PLAYER_NAME
    )
    
@app.route('/reset_board')
def reset_board():
    game_state, _, _, _, _, _ = load_game_data()
    if game_state:
        new_game_state = perform_cleanup_and_new_round(game_state)
        if save_json_file(GAME_STATE_FILE, new_game_state):
            flash("Board has been reset, new round started! Cards shuffled and drawn.", "success")
        else:
            flash("ERROR: Failed to save game state changes.", "error")
    return redirect(url_for('index'))

@app.route('/manage_hand/<string:player_name>', methods=['GET', 'POST'])
def manage_hand(player_name):
    """
    Dynamiczna strona do zarządzania ręką DOWOLNEGO gracza.
    """
    game_state, _, cards_db, _, _, _ = load_game_data()
    if game_state is None or cards_db is None:
        flash("CRITICAL ERROR: Cannot load core game data. Check JSON files.", "error")
        return render_template('error.html'), 500

    if request.method == 'POST':
        # player_name jest teraz brany z URL, a nie hardkodowany
        card_ids = request.form.getlist('card_ids')
        is_valid, message = set_player_hand(game_state, player_name, card_ids, cards_db)
        
        if is_valid:
            if save_json_file(GAME_STATE_FILE, game_state):
                flash(message, "success")
            else:
                flash("CRITICAL ERROR: Cannot save game state after setting hand.", "error")
        else:
            flash(f"Invalid hand: {message}", "error")
        
        # Przekieruj z powrotem do tej samej strony
        return redirect(url_for('manage_hand', player_name=player_name))

    # Logika GET
    player_data = game_state.get("players", {}).get(player_name, {})
    if not player_data:
        flash(f"Player {player_name} not found!", "error")
        return redirect(url_for('index'))
        
    deck_pool_ids = player_data.get("deck_pool", [])
    current_hand_ids = player_data.get("hand", [])
    deck_pool_details = []
    
    for card_id in deck_pool_ids:
        card_data = cards_db.get(card_id, {})
        deck_pool_details.append({
            "id": card_id,
            "name": card_data.get("name", card_id)
        })
        
    return render_template('manage_hand.html', # Użyjemy nowego szablonu
        player_name=player_name,
        deck_cards=sorted(deck_pool_details, key=lambda x: x['name']),
        current_hand=current_hand_ids
    )

@app.route('/debug_json')
def debug_json():
    game_state, _, _, _, _, _ = load_game_data()
    if game_state is None:
        flash("CRITICAL ERROR: Cannot load game_stat.json.", "error")
        return render_template('error.html'), 500
    json_text = json.dumps(game_state, indent=2, ensure_ascii=False)
    return render_template('debug_json.html', json_text=json_text)


@app.route('/save_debug_json', methods=['POST'])
def save_debug_json():
    """
    Zapisuje stan gry z edytora debugowania JSON.
    """
    text_data = request.form.get('json_text')
    if not text_data:
        flash("Błąd: Nie otrzymano żadnych danych do zapisu.", "error")
        return redirect(url_for('debug_json'))

    # Użyj funkcji z game_manager do walidacji i zapisu
    is_valid, message = save_json_file_from_text(text_data)
    
    if is_valid:
        flash(message, "success")
    else:
        # Błąd parsowania JSON lub zapisu jest już w 'message'
        flash(f"Błąd zapisu: {message}", "error")
        
    return redirect(url_for('debug_json'))


@app.route('/add_intrigue', methods=['POST'])
def add_intrigue():
    game_state, _, _, intrigues_db, _, _ = load_game_data()

    player_name_input = request.form.get('player_name')
    intrigue_id_input = request.form.get('intrigue_id')
    
    if not player_name_input or not intrigue_id_input:
        flash("Invalid input: Player or Intrigue card missing.", "error")
        return redirect(url_for('index'))

    is_valid, message = manual_add_intrigue(game_state, player_name_input, intrigue_id_input, intrigues_db)
    
    if is_valid:
        if save_json_file(GAME_STATE_FILE, game_state):
            flash(message, "success")
        else:
            flash("CRITICAL ERROR: Cannot save game state after adding intrigue.", "error")
    else:
        flash(f"Failed to add intrigue: {message}", "error")
        
    return redirect(url_for('index'))


# === NOWE TRASY DLA ZŁOŻONYCH RUCHÓW AGENTA ===

@app.route('/resolve_agent_move/<string:player_name>/<string:card_id>/<string:location_id>')
def resolve_agent_move(player_name, card_id, location_id):
    """
    (NOWA TRASA) Wyświetla stronę, na której gracz podejmuje decyzję
    dotyczącą złożonego ruchu agenta (karty lub lokacji).
    """
    game_state, locations_db, cards_db, intrigues_db, conflicts_db, leaders_db = load_game_data()
    
    card_data = cards_db.get(card_id)
    location_data = locations_db.get(location_id)
    player_state = game_state.get("players", {}).get(player_name, {})
    
    if not card_data or not location_data:
        flash("Error: Card or Location data not found for decision.", "error")
        return redirect(url_for('index'))
        
    # Ponownie sprawdzamy wymagania, aby uzyskać dane do wyświetlenia
    requirements = get_agent_move_requirements(card_data, location_data, leaders_db, player_state)
    
    # Używamy tego samego szablonu co intrygi, ale przekazujemy dodatkowe dane
    return render_template('resolve_intrigue.html',
        player_name=player_name,
        player_resources=player_state.get("resources", {}),
        card_id=card_id,
        card_data={"name": f"{card_data.get('name')} on {location_data.get('name')}", "description": f"Effect from {requirements.get('source', 'Unknown')}"},
        requirements=requirements,
        # Dodatkowe pola dla formularza
        location_id=location_id 
    )

@app.route('/execute_agent_move', methods=['POST'])
def execute_agent_move():
    """
    (NOWA TRASA) Odbiera decyzję gracza z formularza
    i wywołuje process_move z odpowiednimi kwargs.
    """
    game_state, locations_db, cards_db, _, _, leaders_db = load_game_data()
    
    # Odczytaj wszystkie dane ruchu z formularza
    player_name = request.form.get('player_name')
    card_id = request.form.get('card_id')
    location_id = request.form.get('location_id')
    
    # Przygotuj słownik kwargs dla decyzji
    kwargs = {}
    if 'pay_cost' in request.form:
        kwargs['pay_cost'] = request.form['pay_cost'] == 'true'
        
    if 'choice_index' in request.form:
        try:
            kwargs['choice_index'] = int(request.form['choice_index'])
        except ValueError:
            flash("Invalid choice index received.", "error")
            return redirect(url_for('index'))

    # Wywołaj silnik ruchu agenta, przekazując zebrane decyzje
    new_game_state = process_move(
        game_state, locations_db, cards_db, leaders_db, 
        player_name, card_id, location_id, 
        **kwargs # Rozpakuj decyzje tutaj
    )
    
    final_game_state = check_and_advance_phase(new_game_state, cards_db)
    
    if save_json_file(GAME_STATE_FILE, final_game_state):
         flash(f"Success! Player {player_name}'s complex move has been executed.", "success")
    else:
         flash("CRITICAL ERROR: Cannot save game state after complex move.", "error")

    return redirect(url_for('index'))


if __name__ == '__main__':
    print("Starting server at http://0.0.0.0:5000")
    print("To access from other computers, use your computer's IP address, e.g., http://192.168.1.10:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)