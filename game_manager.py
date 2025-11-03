import json
import os

# Dodano nowy plik bazy danych
LOCATIONS_DB_FILE = 'locations.json'
CARDS_DB_FILE = 'cards.json'
INTRIGUES_DB_FILE = 'intrigues.json' 
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
    """Wczytuje i zwraca wszystkie kluczowe dane gry."""
    game_state = load_json_file(GAME_STATE_FILE)
    locations_db = load_json_file(LOCATIONS_DB_FILE)
    cards_db = load_json_file(CARDS_DB_FILE)
    intrigues_db = load_json_file(INTRIGUES_DB_FILE)
    
    if not all([game_state, locations_db, cards_db, intrigues_db]):
        return None, None, None, None # Zwraca błąd, jeśli brakuje któregokolwiek pliku
    
    return game_state, locations_db, cards_db, intrigues_db


def is_move_valid(game_state, locations_db, cards_db, player_name, card_id, location_id):
    """Validates a player's move (using card and location IDs)."""
    
    # --- Walidacja 0: Faza Gry ---
    if game_state.get("current_phase") != "AGENT_TURN":
        return False, f"Cannot send an agent. The current game phase is: {game_state.get('current_phase')}"
    
    player_state = game_state.get("players", {}).get(player_name, {})
    
    # --- Walidacja 0.5: Liczba Agentów (NOWOŚĆ) ---
    agents_total = player_state.get("agents_total", 2)
    agents_placed = player_state.get("agents_placed", 0)
    
    if agents_placed >= agents_total:
        return False, f"Player {player_name} has no more agents to place this round ({agents_placed}/{agents_total})."

    # --- Walidacja 1: Lokacja i Karta ---
    if location_id not in locations_db:
        return False, "Invalid location (ID)."
    if card_id not in cards_db:
        return False, "Invalid card (ID)."

    location_data = locations_db[location_id]
    card_data = cards_db[card_id]

    # --- Walidacja 2: Zajętość Lokacji ---
    location_state = game_state.get("locations_state", {}).get(location_id, {})
    if location_state.get("occupied_by") is not None:
        return False, f"Location is already occupied by player {location_state['occupied_by']}."

    # --- Walidacja 3: Posiadanie Karty (na RĘCE) ---
    player_hand = player_state.get("hand", [])
    
    if card_id not in player_hand:
        return False, f"Player {player_name} does not have the card '{card_data['name']}' in their HAND."
            
    # --- Walidacja 4: Symbol Agenta ---
    required_symbol = location_data.get("symbol_required")
    card_symbols = card_data.get("agent_symbols", [])
    
    if required_symbol and required_symbol not in card_symbols:
        return False, f"Card '{card_data['name']}' (symbols: {card_symbols}) does not match location '{location_data['name']}' (required symbol: {required_symbol})."

    # --- Walidacja 5: Koszt Lokacji ---
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
    """Processes a valid move."""
    
    card_name = cards_db.get(card_id, {}).get("name", card_id)
    location_name = locations_db.get(location_id, {}).get("name", location_id)
    location_data = locations_db.get(location_id, {})
    card_data = cards_db.get(card_id, {})
    
    # 1. Zapewnij istnienie klucza locations_state
    if "locations_state" not in game_state:
         game_state["locations_state"] = {}
         
    if location_id not in game_state["locations_state"]:
         game_state["locations_state"][location_id] = {"occupied_by": None} 

    # 2. Zaznacz lokację jako zajętą
    game_state["locations_state"][location_id]["occupied_by"] = player_name
    
    player_state = game_state.get("players", {}).get(player_name, {})
    player_resources = player_state.get("resources", {})
    
    # 3. Przetwórz koszty
    location_cost = location_data.get("cost", [])
    for cost_item in location_cost:
        if cost_item.get("type") == "resource":
            resource_name = cost_item.get("resource")
            resource_amount = cost_item.get("amount", 0)
            current_amount = player_resources.get(resource_name, 0)
            player_resources[resource_name] = current_amount - resource_amount
            
    # 4. Przenieś kartę z ręki do odrzuconych
    if card_id in player_state.get("hand", []):
        player_state["hand"].remove(card_id)
        if "discard_pile" not in player_state:
            player_state["discard_pile"] = []
        player_state["discard_pile"].append(card_id)

    # 5. Przetwórz KORZYŚCI z karty agenta
    agent_gain = card_data.get("agent_effect", {}).get("gain", [])
    for gain_item in agent_gain:
        if gain_item.get("type") == "resource":
            resource_name = gain_item.get("resource")
            resource_amount = gain_item.get("amount", 0)
            current_amount = player_resources.get(resource_name, 0)
            player_resources[resource_name] = current_amount + resource_amount
        # TODO: Dodać logikę "draw_card"

    # 6. Zwiększ licznik agentów (NOWOŚĆ)
    player_state["agents_placed"] = player_state.get("agents_placed", 0) + 1
    
    # 7. Sprawdź efekt lokacji (NOWOŚĆ - SWORDMASTER)
    if location_data.get("effect") == "gain_third_agent":
        player_state["agents_total"] = 3

    # 8. Dodaj do historii
    move_summary = f"{player_name} played '{card_name}' on '{location_name}'."
    if "round_history" not in game_state:
        game_state["round_history"] = []
        
    game_state["round_history"].append({
        "player": player_name,
        "card": card_name,
        "location": location_name,
        "summary": move_summary
    })
    return game_state


def check_and_advance_phase(game_state):
    """
    Sprawdza, czy wszyscy gracze zakończyli turę agentów. 
    Jeśli tak, przełącza fazę gry na "REVEAL".
    """
    if game_state.get("current_phase") != "AGENT_TURN":
        return game_state # Nic nie rób, jeśli nie jest faza agentów

    all_agents_placed = True
    for player_name, player_data in game_state.get("players", {}).items():
        if player_data.get("agents_placed", 0) < player_data.get("agents_total", 2):
            all_agents_placed = False
            break # Wystarczy jeden gracz, który nie skończył

    if all_agents_placed:
        game_state["current_phase"] = "REVEAL"
        # TODO: Ustawić "currentPlayer" na pierwszego gracza do fazy ujawnienia?
        # Na razie resetujemy, żeby nikt nie mógł wykonać ruchu agenta
        game_state["currentPlayer"] = "SYSTEM" 
        
    return game_state


def process_intrigue(game_state, intrigues_db, player_name, intrigue_id):
    """Przetwarza zagranie karty intrygi."""
    
    player_state = game_state.get("players", {}).get(player_name, {})
    intrigue_hand = player_state.get("intrigue_hand", [])
    
    if intrigue_id not in intrigue_hand:
        return False, "Player does not have this intrigue card."
        
    intrigue_data = intrigues_db.get(intrigue_id)
    if not intrigue_data:
        return False, "Intrigue card definition not found."
        
    # Sprawdź, czy można zagrać tę kartę teraz
    if intrigue_data.get("type") != "agent_turn":
        return False, f"This card cannot be played during the AGENT_TURN (Type: {intrigue_data.get('type')})."

    # --- Zastosuj efekt (TODO: Rozbudować logikę) ---
    # Na razie po prostu usuwamy kartę i zwracamy opis
    player_state["intrigue_hand"].remove(intrigue_id)
    # TODO: Dodać "intrigue_discard_pile"
    
    # Przykładowa prosta logika efektu
    if intrigue_id == "plot_twist":
         player_state.get("resources", {})["solari"] = player_state.get("resources", {}).get("solari", 0) + 1
         player_state.get("resources", {})["spice"] = player_state.get("resources", {}).get("spice", 0) + 1
         
    # TODO: Efekt "diplomacy" wymagałby ustawienia flagi, np.
    # player_state["bonus_flags"]["can_use_occupied"] = True
    # którą `is_move_valid` musiałoby sprawdzać.

    summary = f"Player {player_name} played intrigue: '{intrigue_data['name']}'."
    
    return True, summary