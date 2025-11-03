# app.py
from flask import Flask, render_template, request, redirect, url_for, flash
import json
import os

from game_manager import (
    load_game_data, save_json_file, is_move_valid, process_move, 
    check_and_advance_phase, process_intrigue,
    calculate_reveal_stats, perform_cleanup_and_new_round, 
    GAME_STATE_FILE,
    process_pass_turn 
)

from build_ai_prompt import generate_ai_prompt, AI_PLAYER_NAME

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
    
    for loc_id, loc_data in locations_db.items():
        location_state = game_state.get("locations_state", {}).get(loc_id, {})
        if location_state.get("occupied_by") is None:
             available_locations.append({
                "id": loc_id,
                "name": loc_data["name"]
            })
    return available_locations

@app.route('/', methods=['GET', 'POST'])
def index():
    # Intrigues_db już nie jest potrzebne
    game_state, locations_db, cards_db, _ = load_game_data()

    if game_state is None or locations_db is None or cards_db is None:
        flash("CRITICAL ERROR: Cannot load core game data. Check JSON files.", "error")
        return render_template('error.html'), 500

    current_phase = game_state.get("current_phase", "Unknown Phase") 
    if current_phase == "REVEAL":
        return redirect(url_for('reveal_phase'))

    if request.method == 'POST':
        # Logika ruchu agenta
        player_name_input = request.form.get('player_name')
        card_id_input = request.form.get('card_id')
        location_id_input = request.form.get('location_id')

        # --- USUNIĘTO WALIDACJĘ 'currentPlayer' ---
        
        is_valid, message = is_move_valid(game_state, locations_db, cards_db, player_name_input, card_id_input, location_id_input)

        if is_valid:
            new_game_state = process_move(game_state, locations_db, cards_db, player_name_input, card_id_input, location_id_input)
            final_game_state = check_and_advance_phase(new_game_state)
            
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
    
    player_card_map = {}
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
    
    player_agent_map = {}
    # --- USUNIĘTO 'player_intrigue_map' ---
    
    for player_name, player_data in player_states.items():
        player_agent_map[player_name] = {
            "placed": player_data.get("agents_placed", 0),
            "total": player_data.get("agents_total", 2),
            "has_passed": player_data.get("has_passed", False) 
        }
        
    return render_template('index.html', 
        current_player=current_player, # Zostawiamy dla spójności UI (wybrany gracz)
        current_phase=current_phase, 
        current_round=current_round, 
        round_history=round_history,
        player_names=player_names,
        player_card_map=player_card_map,
        player_agent_map=player_agent_map, 
        # Usunięto player_intrigue_map
        locations=available_locations,
        ai_player_name=AI_PLAYER_NAME
    )

# --- CAŁKOWICIE NOWA LOGIKA INTRYG ---
@app.route('/play_intrigue', methods=['POST'])
def play_intrigue():
    """Obsługa ręcznie wpisanej intrygi."""
    game_state, _, _, _ = load_game_data()

    if game_state.get("current_phase") != "AGENT_TURN":
        flash("Cannot play intrigue: Not in AGENT_TURN phase.", "error")
        return redirect(url_for('index'))

    # Pobierz gracza i tekst z formularza
    player_name_input = request.form.get('player_name')
    intrigue_text_input = request.form.get('intrigue_text')
    
    # --- USUNIĘTO WALIDACJĘ 'currentPlayer' ---
        
    # Użyj nowej funkcji z game_manager
    is_valid, message = process_intrigue(game_state, player_name_input, intrigue_text_input)
    
    if is_valid:
        if save_json_file(GAME_STATE_FILE, game_state):
            flash(f"Intrigue played: {message}", "success")
        else:
            flash("CRITICAL ERROR: Cannot save game state after playing intrigue.", "error")
    else:
        flash(f"Invalid intrigue play: {message}", "error")
        
    return redirect(url_for('index'))


@app.route('/pass_turn', methods=['POST'])
def pass_turn():
    """Przetwarza spasowanie tury przez gracza."""
    game_state, _, _, _ = load_game_data()
    
    if game_state.get("current_phase") != "AGENT_TURN":
        flash("Cannot pass: Not in AGENT_TURN phase.", "error")
        return redirect(url_for('index'))

    player_name_input = request.form.get('player_name')
    if not player_name_input:
         flash("Invalid pass: Player name was missing.", "error")
         return redirect(url_for('index'))
         
    # --- USUNIĘTO WALIDACJĘ 'currentPlayer' ---
    
    game_state, is_valid, message = process_pass_turn(game_state, player_name_input)
    
    if is_valid:
        flash(message, "success")
        final_game_state = check_and_advance_phase(game_state)
        save_json_file(GAME_STATE_FILE, final_game_state)
    else:
        flash(f"Invalid pass: {message}", "error")

    return redirect(url_for('index'))


@app.route('/reveal')
def reveal_phase():
    """Wyświetla stronę Fazy Odkrycia (Reveal Phase)."""
    game_state, _, cards_db, _ = load_game_data()
    
    current_phase = game_state.get("current_phase", "Unknown Phase")
    if current_phase != "REVEAL":
        return redirect(url_for('index'))
        
    all_player_stats = []
    player_states = game_state.get("players", {})
    
    for player_name, player_data in player_states.items():
        stats = calculate_reveal_stats(player_data, cards_db)
        stats["name"] = player_name
        all_player_stats.append(stats)

    return render_template('reveal.html',
        current_round=game_state.get("round", 1),
        all_player_stats=all_player_stats
    )


@app.route('/ai_prompt')
def ai_prompt():
    game_state, _, _, _ = load_game_data()
    
    if game_state is None:
        flash("CRITICAL ERROR: Cannot load game data.", "error")
        return render_template('error.html'), 500
        
    prompt_text = generate_ai_prompt(game_state) 
    
    return render_template('ai_prompt.html', 
        prompt_text=prompt_text,
        ai_player_name=AI_PLAYER_NAME
    )
    
@app.route('/reset_board')
def reset_board():
    """Resetuje planszę na kolejną rundę."""
    game_state, _, _, _ = load_game_data()
    if game_state:
        new_game_state = perform_cleanup_and_new_round(game_state)

        if save_json_file(GAME_STATE_FILE, new_game_state):
            flash("Board has been reset, new round started! Cards shuffled and drawn.", "success")
        else:
            flash("ERROR: Failed to save game state changes.", "error")
    
    return redirect(url_for('index'))


if __name__ == '__main__':
    print("Starting server at http://0.0.0.0:5000")
    print("To access from other computers, use your computer's IP address, e.g., http://192.168.1.10:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)