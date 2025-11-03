# app.py
from flask import Flask, render_template, request, redirect, url_for, flash
import json
import os

# Zaktualizowano importy z game_manager
from game_manager import load_game_data, save_json_file, is_move_valid, process_move, check_and_advance_phase, process_intrigue
from build_ai_prompt import generate_ai_prompt, AI_PLAYER_NAME

# Użyjemy stałych z game_manager.py
from game_manager import GAME_STATE_FILE, INTRIGUES_DB_FILE

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

# --- FUNKCJA draw_cards_for_ai() ZOSTAŁA USUNIĘTA ---

@app.route('/', methods=['GET', 'POST'])
def index():
    # Używamy nowej, zbiorczej funkcji
    game_state, locations_db, cards_db, intrigues_db = load_game_data()

    if game_state is None or locations_db is None or cards_db is None or intrigues_db is None:
        flash("CRITICAL ERROR: Cannot load core game data. Check JSON files.", "error")
        return render_template('error.html'), 500

    if request.method == 'POST':
        # Walidacja ruchu AGENTA
        player_name_input = request.form.get('player_name')
        card_id_input = request.form.get('card_id')
        location_id_input = request.form.get('location_id')

        is_valid, message = is_move_valid(game_state, locations_db, cards_db, player_name_input, card_id_input, location_id_input)

        if is_valid:
            new_game_state = process_move(game_state, locations_db, cards_db, player_name_input, card_id_input, location_id_input)
            
            # NOWOŚĆ: Po każdym ruchu sprawdź, czy kończy się faza agentów
            final_game_state = check_and_advance_phase(new_game_state)
            
            if save_json_file(GAME_STATE_FILE, final_game_state):
                 flash(f"Success! Player {player_name_input}'s move has been played.", "success")
            else:
                 flash("CRITICAL ERROR: Cannot save game state to disk.", "error")
        else:
            flash(f"Invalid move: {message}", "error")
        
        return redirect(url_for('index'))

    # --- Logika GET (wyświetlanie strony) ---
    current_player = game_state.get("currentPlayer", "Unknown Player")
    current_phase = game_state.get("current_phase", "Unknown Phase") 
    current_round = game_state.get("round", 1) 
    round_history = game_state.get("round_history", [])
    player_names = get_player_names(game_state)
    available_locations = get_available_locations(locations_db, game_state)
    
    # --- ZMODYFIKOWANA LOGIKA MAPY KART (z 'hand') ---
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
    
    # --- NOWA LOGIKA: Przygotowanie danych o intrygach i agentach ---
    player_agent_map = {}
    player_intrigue_map = {}
    
    for player_name, player_data in player_states.items():
        # Mapa Agentów
        player_agent_map[player_name] = {
            "placed": player_data.get("agents_placed", 0),
            "total": player_data.get("agents_total", 2)
        }
        
        # Mapa Intryg (lista obiektów)
        intrigue_ids_list = player_data.get("intrigue_hand", [])
        player_intrigue_list = []
        for intrigue_id in intrigue_ids_list:
            if intrigue_id in intrigues_db:
                intrigue_data = intrigues_db[intrigue_id]
                # Pokaż tylko karty, które można zagrać teraz
                if intrigue_data.get("type") == "agent_turn":
                    player_intrigue_list.append({
                        "id": intrigue_id,
                        "name": intrigue_data.get("name", intrigue_id),
                        "description": intrigue_data.get("description", "No description.")
                    })
        player_intrigue_map[player_name] = player_intrigue_list


    return render_template('index.html', 
        current_player=current_player,
        current_phase=current_phase, 
        current_round=current_round, 
        round_history=round_history,
        player_names=player_names,
        player_card_map=player_card_map,
        player_agent_map=player_agent_map, # Nowe
        player_intrigue_map=player_intrigue_map, # Nowe
        locations=available_locations,
        ai_player_name=AI_PLAYER_NAME
    )

@app.route('/play_intrigue', methods=['POST'])
def play_intrigue():
    """Nowa ścieżka do obsługi zagrywania kart intryg."""
    game_state, _, _, intrigues_db = load_game_data()

    if game_state.get("current_phase") != "AGENT_TURN":
        flash("Cannot play intrigue: Not in AGENT_TURN phase.", "error")
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
        
    return redirect(url_for('index'))


@app.route('/ai_prompt')
def ai_prompt():
    game_state, _, _, _ = load_game_data() # Używamy nowej funkcji
    
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
    """
    Resetuje planszę na kolejną rundę.
    TERAZ musi też resetować agentów i dobierać karty.
    """
    game_state, _, _, _ = load_game_data()
    if game_state:
        # 1. Reset lokacji
        if "locations_state" in game_state:
            for loc_id in game_state["locations_state"]:
                game_state["locations_state"][loc_id]["occupied_by"] = None
        
        # 2. Reset fazy i historii
        game_state["round_history"] = []
        game_state["current_phase"] = "AGENT_TURN" 
        game_state["round"] = game_state.get("round", 0) + 1

        # 3. Reset agentów i dobieranie kart dla wszystkich graczy (NOWA LOGIKA)
        for player_name, player_data in game_state.get("players", {}).items():
            # Reset agentów (zachowaj 3, jeśli zdobył)
            player_data["agents_placed"] = 0
            # Bazowa liczba to 2, chyba że już mają 3
            if player_data.get("agents_total", 2) != 3:
                player_data["agents_total"] = 2 
            
            # TODO: Dodać pełną logikę tasowania i dobierania 5 kart
            # Na razie: przenieś wszystko z discard_pile do hand
            player_data["hand"] = player_data.get("hand", []) + player_data.get("discard_pile", [])
            player_data["discard_pile"] = []


        if save_json_file(GAME_STATE_FILE, game_state):
            flash("Board has been reset, new round started! (Cards shuffled - simplified)", "success")
        else:
            flash("ERROR: Failed to save game state changes.", "error")
    
    return redirect(url_for('index'))


if __name__ == '__main__':
    print("Starting server at http://0.0.0.0:5000")
    print("To access from other computers, use your computer's IP address, e.g., http://192.168.1.10:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)