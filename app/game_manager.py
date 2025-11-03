import json
import os
import random 

LOCATIONS_DB_FILE = 'locations.json'
CARDS_DB_FILE = 'cards.json'
# INTRIGUES_DB_FILE został usunięty
GAME_STATE_FILE = 'game_stat.json'

def load_json_file(filename):
    """Loads a JSON file and returns its content."""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: File not found {filename}")
        return None
    except json.JSONDecodeError:
        print(f"Error: JSON decode error in {filename}")
        return None

def save_json_file(filename, data):
    """Saves data (dictionary) to a JSON file."""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True 
    except IOError:
        print(f"Error: Could not write to file {filename}")
        return False

def load_game_data():
    """Wczytuje i zwraca kluczowe dane gry (bez intryg)."""
    game_state = load_json_file(GAME_STATE_FILE)
    locations_db = load_json_file(LOCATIONS_DB_FILE)
    cards_db = load_json_file(CARDS_DB_FILE)
    # Usunięto ładowanie intrigues_db
    
    if not all([game_state, locations_db, cards_db]):
        return None, None, None, None 
    
    return game_state, locations_db, cards_db, None # Zwracamy None dla intryg


def is_move_valid(game_state, locations_db, cards_db, player_name, card_id, location_id):
    """Waliduje ruch (bez sprawdzania czyja tura)."""
    
    if game_state.get("current_phase") != "AGENT_TURN":
        return False, f"Cannot send an agent. The current game phase is: {game_state.get('current_phase')}"
    
    player_state = game_state.get("players", {}).get(player_name, {})
    if not player_state:
        return False, f"Player {player_name} not found."
    
    agents_total = player_state.get("agents_total", 2)
    agents_placed = player_state.get("agents_placed", 0)
    
    if agents_placed >= agents_total:
        return False, f"Player {player_name} has no more agents to place this round ({agents_placed}/{agents_total})."
        
    if player_state.get("has_passed", False):
        return False, f"Player {player_name} has already passed this round."

    if location_id not in locations_db:
        return False, "Invalid location (ID)."
    if card_id not in cards_db:
        return False, "Invalid card (ID)."

    location_data = locations_db[location_id]
    card_data = cards_db[card_id]

    location_state = game_state.get("locations_state", {}).get(location_id, {})
    if location_state.get("occupied_by") is not None:
        return False, f"Location is already occupied by player {location_state['occupied_by']}."

    player_hand = player_state.get("hand", [])
    
    if card_id not in player_hand:
        return False, f"Player {player_name} does not have the card '{card_data['name']}' in their HAND."
            
    required_symbol = location_data.get("symbol_required")
    card_symbols = card_data.get("agent_symbols", [])
    
    if required_symbol and required_symbol not in card_symbols:
        return False, f"Card '{card_data['name']}' (symbols: {card_symbols}) does not match location '{location_data['name']}' (required symbol: {required_symbol})."

    location_cost = location_data.get("cost", [])
    player_resources = player_state.get("resources", {})

    for cost_item in location_cost:
        if cost_item.get("type") == "resource":
            resource_name = cost_item.get("resource")
            required_amount = cost_item.get("amount", 0)
            player_has = player_resources.get(resource_name, 0)
            
            if player_has < required_amount:
                return False, f"Player {player_name} does not have enough resources. Required: {required_amount} {resource_name}, Has: {player_has}."

    return True, "Move is valid."


def process_move(game_state, locations_db, cards_db, player_name, card_id, location_id):
    """Przetwarza ruch (bez ustawiania następnego gracza)."""
    
    card_name = cards_db.get(card_id, {}).get("name", card_id)
    location_name = locations_db.get(location_id, {}).get("name", location_id)
    location_data = locations_db.get(location_id, {})
    card_data = cards_db.get(card_id, {})
    
    if "locations_state" not in game_state:
         game_state["locations_state"] = {}
    if location_id not in game_state["locations_state"]:
         game_state["locations_state"][location_id] = {"occupied_by": None} 

    game_state["locations_state"][location_id]["occupied_by"] = player_name
    
    player_state = game_state.get("players", {}).get(player_name, {})
    player_resources = player_state.get("resources", {})
    
    location_cost = location_data.get("cost", [])
    for cost_item in location_cost:
        if cost_item.get("type") == "resource":
            resource_name = cost_item.get("resource")
            resource_amount = cost_item.get("amount", 0)
            current_amount = player_resources.get(resource_name, 0)
            player_resources[resource_name] = current_amount - resource_amount
            
    if card_id in player_state.get("hand", []):
        player_state["hand"].remove(card_id)
        if "discard_pile" not in player_state:
            player_state["discard_pile"] = []
        player_state["discard_pile"].append(card_id)

    agent_gain = card_data.get("agent_effect", {}).get("gain", [])
    for gain_item in agent_gain:
        if gain_item.get("type") == "resource":
            resource_name = gain_item.get("resource")
            resource_amount = gain_item.get("amount", 0)
            current_amount = player_resources.get(resource_name, 0)
            player_resources[resource_name] = current_amount + resource_amount

    player_state["agents_placed"] = player_state.get("agents_placed", 0) + 1
    
    if location_data.get("effect") == "gain_third_agent":
        player_state["agents_total"] = 3
        
    # --- USUNIĘTO LOGIKĘ USTAWIANIA NASTĘPNEGO GRACZA ---
    
    move_summary = f"{player_name} played '{card_name}' on '{location_name}'."
    if "round_history" not in game_state:
        game_state["round_history"] = []
        
    game_state["round_history"].append({
        "player": player_name,
        "card": card_name,
        "location": location_name,
        "summary": move_summary
    })
    
    # Ustawiamy 'currentPlayer' na tego, kto wykonał ruch (dla spójności UI)
    game_state["currentPlayer"] = player_name
    
    return game_state


def process_pass_turn(game_state, player_name):
    """Oznacza gracza jako pasującego (bez ustawiania następnego gracza)."""
    
    player_state = game_state.get("players", {}).get(player_name)
    if not player_state:
        return game_state, False, f"Player {player_name} not found."

    if player_state.get("agents_placed", 0) >= player_state.get("agents_total", 2):
        return game_state, False, f"Player {player_name} has already placed all agents."
        
    if player_state.get("has_passed", False):
        return game_state, False, f"Player {player_name} has already passed."

    player_state["has_passed"] = True
    
    # --- USUNIĘTO LOGIKĘ USTAWIANIA NASTĘPNEGO GRACZA ---
    
    summary = f"Player {player_name} passed their agent turn."
    if "round_history" not in game_state:
        game_state["round_history"] = []
    game_state["round_history"].append({"summary": summary})
    
    # Ustawiamy 'currentPlayer' na tego, kto spasował
    game_state["currentPlayer"] = player_name
    
    return game_state, True, summary


def check_and_advance_phase(game_state):
    """
    Sprawdza, czy wszyscy gracze zakończyli (zagrali agentów LUB spasowali).
    """
    if game_state.get("current_phase") != "AGENT_TURN":
        return game_state 

    all_players_finished = True
    player_names = sorted(list(game_state.get("players", {}).keys()))
    
    for player_name in player_names:
        player_data = game_state["players"][player_name]
        
        agents_done = player_data.get("agents_placed", 0) >= player_data.get("agents_total", 2)
        has_passed = player_data.get("has_passed", False)
        
        if not agents_done and not has_passed:
            all_players_finished = False
            break 

    if all_players_finished:
        game_state["current_phase"] = "REVEAL"
        # Ustawiamy na "SYSTEM" lub pierwszego gracza, bez znaczenia
        game_state["currentPlayer"] = "SYSTEM"
        
    return game_state


# --- ZUPEŁNIE NOWA LOGIKA INTRYG ---
def process_intrigue(game_state, player_name, intrigue_text):
    """Po prostu zapisuje ręcznie wpisany tekst intrygi do historii."""
    
    player_state = game_state.get("players", {}).get(player_name)
    if not player_state:
        return False, "Player not found."
        
    if not intrigue_text:
        return False, "Intrigue text cannot be empty."

    # Nie musimy już sprawdzać 'intrigue_hand' ani bazy danych
    
    summary = f"Player {player_name} played intrigue: '{intrigue_text}'."
    
    # Dodaj do historii
    if "round_history" not in game_state:
        game_state["round_history"] = []
    game_state["round_history"].append({"summary": summary})
    
    # TODO: W przyszłości możesz dodać logikę, która parsuje 'intrigue_text'
    # i modyfikuje stan gry, jeśli wpiszesz np. "plot_twist"
    
    return True, summary

# --- Reszta funkcji (calculate_reveal_stats, perform_cleanup_and_new_round) ---
# --- Pozostaje bez zmian ---

def calculate_reveal_stats(player_state, cards_db):
    """
    Oblicza sumę Perswazji i Siły dla gracza.
    """
    total_persuasion = 0
    total_swords = 0
    
    cards_to_reveal_ids = player_state.get("hand", []) + player_state.get("discard_pile", [])
    
    cards_in_hand_details = []
    cards_played_details = []

    for card_id in cards_to_reveal_ids:
        card_data = cards_db.get(card_id)
        if card_data:
            reveal_effect = card_data.get("reveal_effect", {})
            persuasion = reveal_effect.get("persuasion", 0)
            swords = reveal_effect.get("swords", 0)
            
            total_persuasion += persuasion
            total_swords += swords
            
            card_detail = {
                "name": card_data.get("name", card_id),
                "persuasion": persuasion,
                "swords": swords
            }
            
            if card_id in player_state.get("hand", []):
                cards_in_hand_details.append(card_detail)
            else:
                cards_played_details.append(card_detail)

    return {
        "total_persuasion": total_persuasion,
        "total_swords": total_swords,
        "cards_in_hand": cards_in_hand_details,
        "cards_played": cards_played_details
    }


def perform_cleanup_and_new_round(game_state):
    """
    Resetuje planszę, czyści stan graczy, tasuje talie i dobiera 5 kart.
    """
    if game_state:
        if "locations_state" in game_state:
            for loc_id in game_state["locations_state"]:
                game_state["locations_state"][loc_id]["occupied_by"] = None
        
        game_state["round_history"] = []
        game_state["current_phase"] = "AGENT_TURN" 
        game_state["round"] = game_state.get("round", 0) + 1
        
        player_names = sorted(list(game_state.get("players", {}).keys()))
        game_state["currentPlayer"] = player_names[0] 

        for player_name, player_data in game_state.get("players", {}).items():
            player_data["agents_placed"] = 0
            player_data["has_passed"] = False 
            
            if player_data.get("agents_total", 2) != 3:
                player_data["agents_total"] = 2 
            
            player_data["draw_deck"] = player_data.get("draw_deck", []) + \
                                     player_data.get("hand", []) + \
                                     player_data.get("discard_pile", [])
            player_data["hand"] = []
            player_data["discard_pile"] = []
            
            random.shuffle(player_data["draw_deck"])
            
            for _ in range(5):
                if len(player_data["draw_deck"]) > 0:
                    card = player_data["draw_deck"].pop(0)
                    player_data["hand"].append(card)
                else:
                    pass 
            
            player_data["deck_pool"] = player_data["hand"] + player_data["draw_deck"]
            
    return game_state