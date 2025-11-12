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
    save_json_file_from_text
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
        
        is_valid, message = is_move_valid(game_state, locations_db, cards_db, player_name_input, card_id_input, location_id_input) 

        if is_valid:
            new_game_state = process_move(game_state, locations_db, cards_db, leaders_db, player_name_input, card_id_input, location_id_input)
            final_game_state = check_and_advance_phase(new_game_state, cards_db)
            
            if save_json_file(GAME_STATE_FILE, final_game_state):
                 flash(f"Success! Player {player_name_input}'s move has been played.", "success")
            else:
                 flash("CRITICAL ERROR: Cannot save game state to disk.", "error")
        else:
            flash(f"Invalid move: {message}", "error")
        
        return redirect(url_for('index'))

    # --- Logika GET ---
    current_player = game_state.get("currentPlayer", "Unknown Player")
    current_round = game_state.get("round", 1) 
    round_history = game_state.get("round_history", [])
    player_names = get_player_names(game_state)
    available_locations = get_available_locations(locations_db, game_state)
    
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
        all_conflicts=conflicts_db
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

    if game_state.get("current_phase") not in ["AGENT_TURN", "REVEAL"]:
        flash(f"Cannot play intrigue: Not in AGENT_TURN or REVEAL phase.", "error")
        
        if game_state.get("current_phase") == "REVEAL":
            return redirect(url_for('reveal_phase'))
        return redirect(url_for('index'))

    player_name_input = request.form.get('player_name')
    intrigue_id_input = request.form.get('intrigue_id')
    
    is_valid, message = process_intrigue(game_state, intrigues_db, player_name_input, intrigue_id_input)
    
    if is_valid:
        if save_json_file(GAME_STATE_FILE, game_state):
            flash(f"Intrigue played: {message}", "success")
        else:
            flash("CRITICAL ERROR: Cannot save game state after playing intrigue.", "error")
    else:
        flash(f"Invalid intrigue play: {message}", "error")
        
    if game_state.get("current_phase") == "REVEAL":
        return redirect(url_for('reveal_phase'))
    else:
        return redirect(url_for('index'))


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
    game_state, _, cards_db, _, _, _ = load_game_data()
    
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

    # --- NOWA LOGIKA: SUMOWANIE SIŁY I OBSŁUGA REMISÓW ---
    
    # 1. Zbierz statystyki graczy i OBLICZ FINALNĄ SIŁĘ
    player_stats = []
    for player_name, player_data in game_state.get("players", {}).items():
        stats = player_data.get("reveal_stats", {})
        
        # Pobierz siłę bazową (z kart i wojsk)
        base_swords = stats.get("base_swords", 0)
        
        # Pobierz siłę bonusową (z intryg)
        bonus_swords = player_data.get("active_effects", {}).get("fight_bonus_swords", 0)
        
        final_swords = base_swords + bonus_swords
        
        player_stats.append({
            "name": player_name,
            "swords": final_swords # Użyj finalnej siły
        })
    
    # 2. Posortuj graczy malejąco wg siły
    player_stats.sort(key=lambda x: x['swords'], reverse=True)
    
    # 3. Odfiltruj graczy z 0 siły
    contenders = [p for p in player_stats if p['swords'] > 0]
    c_len = len(contenders)

    if c_len == 0:
        flash("Conflict resolved automatically: No one had any swords.", "success")
        process_conflict_resolve(game_state, None, None, None)
        save_json_file(GAME_STATE_FILE, game_state)
        return redirect(url_for('reveal_phase'))

    # 4. Zainicjuj zwycięzców
    first_place = None
    second_place = None
    third_place = None

    # 5. Sprawdź 1. miejsce
    if c_len == 1:
        first_place = contenders[0]['name']
    
    elif contenders[0]['swords'] > contenders[1]['swords']:
        # Brak remisu o 1. miejsce
        first_place = contenders[0]['name']
        
        # 6. Sprawdź 2. miejsce
        if c_len == 2:
            second_place = contenders[1]['name']
        elif contenders[1]['swords'] > contenders[2]['swords']:
            # Brak remisu o 2. miejsce
            second_place = contenders[1]['name']
            
            # 7. Sprawdź 3. miejsce
            if c_len == 3:
                third_place = contenders[2]['name']
            elif c_len > 3 and contenders[2]['swords'] > contenders[3]['swords']:
                # Brak remisu o 3. miejsce
                third_place = contenders[2]['name']
            # else: Remis o 3. miejsce, third_place=None
        
        else:
            # Remis o 2. miejsce
            second_place = None
            second_place_score = contenders[1]['swords']
            third_place_candidate = None
            for p in contenders:
                if p['swords'] < second_place_score:
                    third_place_candidate = p
                    break
            
            if third_place_candidate:
                third_place_score = third_place_candidate['swords']
                num_at_third_score = len([p for p in contenders if p['swords'] == third_place_score])
                if num_at_third_score == 1:
                    third_place = third_place_candidate['name']

    else:
        # Remis o 1. miejsce
        first_place = None
        second_place = None
        first_place_score = contenders[0]['swords']
        third_place_candidate = None
        for p in contenders:
            if p['swords'] < first_place_score:
                third_place_candidate = p
                break
        
        if third_place_candidate:
            third_place_score = third_place_candidate['swords']
            num_at_third_score = len([p for p in contenders if p['swords'] == third_place_score])
            if num_at_third_score == 1:
                third_place = third_place_candidate['name']
    

    is_valid, message = process_conflict_resolve(game_state, first_place, second_place, third_place)
    
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


# --- ZAKTUALIZOWANA TRASA /ai_prompt ---
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

@app.route('/manage_ai_hand', methods=['GET', 'POST'])
def manage_ai_hand():
    game_state, _, cards_db, _, _, _ = load_game_data()
    if game_state is None or cards_db is None:
        flash("CRITICAL ERROR: Cannot load core game data. Check JSON files.", "error")
        return render_template('error.html'), 500
    if request.method == 'POST':
        player_name = AI_PLAYER_NAME
        card_ids = request.form.getlist('card_ids')
        is_valid, message = set_player_hand(game_state, player_name, card_ids, cards_db)
        if is_valid:
            if save_json_file(GAME_STATE_FILE, game_state):
                flash(message, "success")
            else:
                flash("CRITICAL ERROR: Cannot save game state after setting hand.", "error")
        else:
            flash(f"Invalid hand: {message}", "error")
        return redirect(url_for('manage_ai_hand'))
    player_data = game_state.get("players", {}).get(AI_PLAYER_NAME, {})
    deck_pool_ids = player_data.get("deck_pool", [])
    current_hand_ids = player_data.get("hand", [])
    deck_pool_details = []
    for card_id in deck_pool_ids:
        card_data = cards_db.get(card_id, {})
        deck_pool_details.append({
            "id": card_id,
            "name": card_data.get("name", card_id)
        })
    return render_template('manage_ai_hand.html',
        ai_player_name=AI_PLAYER_NAME,
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


if __name__ == '__main__':
    print("Starting server at http://0.0.0.0:5000")
    print("To access from other computers, use your computer's IP address, e.g., http://192.168.1.10:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)