# app/game_manager.py
import json
import os
import random 

LOCATIONS_DB_FILE = 'locations.json'
CARDS_DB_FILE = 'cards.json'
INTRIGUES_DB_FILE = 'intrigues.json'
CONFLICTS_DB_FILE = 'conflicts.json' # <-- NOWOŚĆ
GAME_STATE_FILE = 'game_stat.json'
GAME_STATE_DEFAULT_FILE = 'game_stat.DEFAULT.json' 
AI_PLAYER_NAME = 'Peter' 

def load_json_file(filename):
    """Wczytuje plik JSON i zwraca jego zawartość."""
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
    """Zapisuje dane (słownik) do pliku JSON."""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True 
    except IOError:
        print(f"Error: Could not write to file {filename}")
        return False

def load_game_data():
    """Wczytuje i zwraca kluczowe dane gry."""
    game_state = load_json_file(GAME_STATE_FILE)
    locations_db = load_json_file(LOCATIONS_DB_FILE)
    cards_db = load_json_file(CARDS_DB_FILE)
    intrigues_db = load_json_file(INTRIGUES_DB_FILE)
    conflicts_db = load_json_file(CONFLICTS_DB_FILE) # <-- NOWOŚĆ
    
    # ZAKTUALIZOWANE SPRAWDZENIE
    if not all([game_state, locations_db, cards_db, intrigues_db, conflicts_db]): 
        return None, None, None, None, None # <-- ZAKTUALIZOWANE
    
    if game_state and locations_db:
        if "locations_state" not in game_state or len(game_state["locations_state"]) < len(locations_db) - 4: 
            print("WARNING: locations_state in game_stat.json is missing or incomplete. Rebuilding...")
            game_state["locations_state"] = {}
            for loc_id in locations_db.keys():
                 if not loc_id.endswith("_influence_path"):
                    game_state["locations_state"][loc_id] = {"occupied_by": None}
    
    if game_state and "current_conflict_card" not in game_state:
        game_state["current_conflict_card"] = {
            "name": "N/A",
            "rewards": {},
            "rewards_text": []
        }
    
    if game_state and "conflict_deck" not in game_state:
         game_state["conflict_deck"] = []
    
    if game_state and "players" in game_state:
        for player_name, player_data in game_state["players"].items():
            if "victory_points" not in player_data:
                player_data["victory_points"] = 0
            if "resources" in player_data:
                if "troops" in player_data["resources"] and "troops_garrison" not in player_data["resources"]:
                    player_data["resources"]["troops_garrison"] = player_data["resources"].pop("troops")
                elif "troops_garrison" not in player_data["resources"]:
                    player_data["resources"]["troops_garrison"] = 0
    
    return game_state, locations_db, cards_db, intrigues_db, conflicts_db # <-- ZAKTUALIZOWANE


def get_card_persuasion_cost(card_data):
    """Pobiera koszt perswazji karty z nowej struktury buy_cost."""
    if not card_data:
        return 999
    buy_cost_list = card_data.get("buy_cost", [])
    if not buy_cost_list:
        return 999
    for cost_item in buy_cost_list:
        if cost_item.get("type") == "none":
            return 999 
        if cost_item.get("type") == "pay" and cost_item.get("resource") == "persuasion":
            return cost_item.get("amount", 999)
    return 999 


def is_move_valid(game_state, locations_db, cards_db, player_name, card_id, location_id):
    """Waliduje ruch (bez sprawdzania czyja tura)."""
    
    if game_state.get("current_phase") != "AGENT_TURN":
        return False, f"Cannot send an agent. The current game phase is: {game_state.get('current_phase')}"
    
    player_state = game_state.get("players", {}).get(player_name, {})
    if not player_state:
        return False, f"Player {player_name} not found."
    
    if player_state.get("agents_placed", 0) >= player_state.get("agents_total", 2):
        return False, f"Player {player_name} has no more agents to place this round."
        
    if player_state.get("has_passed", False):
        return False, f"Player {player_name} has already passed this round."

    if location_id not in locations_db:
        return False, f"Invalid location (ID: {location_id})."
    if card_id not in cards_db:
        return False, f"Invalid card (ID: {card_id})."

    location_data = locations_db[location_id]
    card_data = cards_db[card_id]

    location_state = game_state.get("locations_state", {}).get(location_id, {})
    if location_state.get("occupied_by") is not None:
        return False, f"Location is already occupied by player {location_state['occupied_by']}."

    if player_name == AI_PLAYER_NAME:
        player_hand = player_state.get("hand", [])
        if card_id not in player_hand:
            return False, f"Player {player_name} (AI) does not have the card '{card_data.get('name', card_id)}' in their strict HAND."
    else:
        player_deck_pool = player_state.get("deck_pool", [])
        if card_id not in player_deck_pool:
            return False, f"Player {player_name} (Human) does not have the card '{card_data.get('name', card_id)}' in their DECK."
            
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
    """Przetwarza ruch ORAZ implementuje proste efekty agenta."""
    
    card_name = cards_db.get(card_id, {}).get("name", card_id)
    location_name = locations_db.get(location_id, {}).get("name", location_id)
    location_data = locations_db.get(location_id, {})
    card_data = cards_db.get(card_id, {})
    
    if location_id not in game_state["locations_state"]:
         game_state["locations_state"][location_id] = {}
         
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
            
    
    move_summary = f"{player_name} played '{card_name}' on '{location_name}'."
    
    location_actions_list = location_data.get("actions", [])
    
    for action_object in location_actions_list:
        for key, data in action_object.items():
            if key.startswith("gain") and isinstance(data, dict):
                gain_data = data
                
                if gain_data.get("type") == "resource":
                    resource_name = gain_data.get("resource")
                    resource_amount = gain_data.get("amount", 0)
                    
                    if resource_name in player_resources:
                        current_amount = player_resources.get(resource_name, 0)
                        player_resources[resource_name] = current_amount + resource_amount
                    
                    elif resource_name == "troops":
                        current_amount = player_resources.get("troops_garrison", 0)
                        player_resources["troops_garrison"] = current_amount + resource_amount
                        move_summary += f" (gained {resource_amount} troops to garrison)"
                        
                    elif resource_name == "intrigue card":
                        if "intrigue_hand" not in player_state:
                            player_state["intrigue_hand"] = []
                        player_state["intrigue_hand"].append(f"Intrigue_Card_{random.randint(100,999)}")
                        move_summary += f" (gained 1 intrigue from location)"
                    
                    elif resource_name == "card from unused pile":
                        move_summary += f" (NEEDS MANUAL ACTION: Draw {resource_amount} card(s))"
                    
                    elif "influence point" in str(resource_name):
                        faction = resource_name.split(" ")[0] 
                        if "influence" not in player_state:
                            player_state["influence"] = {}
                        if faction not in player_state["influence"]:
                            player_state["influence"][faction] = 0
                        
                        player_state["influence"][faction] += resource_amount
                        move_summary += f" (gained {resource_amount} {faction} influence from location)"
                        
                elif gain_data.get("type") == "extra gain":
                    move_summary += f" (NEEDS MANUAL ACTION: {gain_data.get('description')})"
    
    agent_effect = card_data.get("agent_effect", {})
    agent_gain_list = agent_effect.get("actions", [])
    
    is_destroyed = False
    for item in agent_gain_list:
        if item.get("type") == "destroy this card":
            is_destroyed = True
            break
            
    if is_destroyed:
        if card_id in player_state.get("hand", []):
            player_state["hand"].remove(card_id)
        if card_id in player_state.get("deck_pool", []):
            player_state["deck_pool"].remove(card_id)
        if "destroyed_pile" not in game_state:
            game_state["destroyed_pile"] = []
        game_state["destroyed_pile"].append(card_id)
        move_summary += f" (and destroyed the card '{card_name}')"
    else:
        if card_id in player_state.get("hand", []):
            player_state["hand"].remove(card_id)
            if "discard_pile" not in player_state:
                player_state["discard_pile"] = []
            player_state["discard_pile"].append(card_id)
        elif player_name != AI_PLAYER_NAME:
             if "discard_pile" not in player_state:
                player_state["discard_pile"] = []
             player_state["discard_pile"].append(card_id)

    for gain_item in agent_gain_list:
        item_type = gain_item.get("type")
        resource_name = gain_item.get("resource")
        resource_amount = gain_item.get("amount", 0)
        
        if item_type == "gain":
            if resource_name in player_resources:
                current_amount = player_resources.get(resource_name, 0)
                player_resources[resource_name] = current_amount + resource_amount
            
            elif resource_name == "troops":
                current_amount = player_resources.get("troops_garrison", 0)
                player_resources["troops_garrison"] = current_amount + resource_amount
                
            elif resource_name == "intrigue":
                if "intrigue_hand" not in player_state:
                    player_state["intrigue_hand"] = []
                player_state["intrigue_hand"].append(f"Intrigue_Card_{random.randint(100,999)}")
            
            elif "influence" in str(resource_name): 
                if "or" in str(resource_name):
                    move_summary += f" (NEEDS MANUAL ACTION: {gain_item.get('description')})"
                else:
                    faction = resource_name.split(" ")[0] 
                    if "influence" not in player_state:
                        player_state["influence"] = {}
                    if faction not in player_state["influence"]:
                        player_state["influence"][faction] = 0
                    
                    player_state["influence"][faction] += resource_amount
                    move_summary += f" (gained {resource_amount} {faction} influence)"
        
        elif item_type == "pay":
             if resource_name in player_resources:
                current_amount = player_resources.get(resource_name, 0)
                player_resources[resource_name] = max(0, current_amount - resource_amount)
        
        elif item_type == "destroy card":
            move_summary += f" (NEEDS MANUAL ACTION: Destroy {resource_amount} card(s))"

    player_state["agents_placed"] = player_state.get("agents_placed", 0) + 1
    
    if location_id == "mentat": 
        player_state["agents_total"] = 3
    
    if "round_history" not in game_state:
        game_state["round_history"] = []
        
    game_state["round_history"].append({
        "player": player_name,
        "card": card_name,
        "location": location_name,
        "summary": move_summary
    })
    
    game_state["currentPlayer"] = player_name
    
    return game_state


def process_pass_turn(game_state, player_name):
    """Oznacza gracza jako pasującego."""
    player_state = game_state.get("players", {}).get(player_name)
    if not player_state:
        return game_state, False, f"Player {player_name} not found."
    if player_state.get("agents_placed", 0) >= player_state.get("agents_total", 2):
        return game_state, False, f"Player {player_name} has already placed all agents."
    if player_state.get("has_passed", False):
        return game_state, False, f"Player {player_name} has already passed."

    player_state["has_passed"] = True
    summary = f"Player {player_name} passed their agent turn."
    
    if "round_history" not in game_state:
        game_state["round_history"] = []
    game_state["round_history"].append({"summary": summary})
    game_state["currentPlayer"] = player_name
    
    return game_state, True, summary


def check_and_advance_phase(game_state, cards_db):
    """Sprawdza, czy faza agentów się skończyła i przechodzi do Fazy Odkrycia."""
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
        game_state = calculate_and_store_reveal_stats(game_state, cards_db)
        game_state["current_phase"] = "REVEAL"
        game_state["currentPlayer"] = "SYSTEM"
        
    return game_state

# --- ZAKTUALIZOWANA FUNKCJA INTRYGI ---
def process_intrigue(game_state, intrigues_db, player_name, intrigue_id):
    """Przetwarza zagranie intrygi z ręki i automatyzuje proste efekty."""
    player_state = game_state.get("players", {}).get(player_name)
    if not player_state:
        return False, "Player not found."
        
    if not intrigue_id:
        return False, "No intrigue card selected."
        
    if intrigue_id not in player_state.get("intrigue_hand", []):
        return False, "Player does not have this intrigue card in hand."
        
    intrigue_data = intrigues_db.get(intrigue_id)
    if not intrigue_data:
        intrigue_data = {"name": intrigue_id, "description": "No description found."}

    # Usuń intrygę z ręki
    player_state["intrigue_hand"].remove(intrigue_id)
    
    summary = f"Player {player_name} played intrigue: '{intrigue_data.get('name')}'."
    
    # --- AUTOMATYZACJA EFEKTÓW ---
    if intrigue_id == 'plot_twist':
        player_resources = player_state.get("resources", {})
        player_resources["solari"] = player_resources.get("solari", 0) + 1
        player_resources["Spice"] = player_resources.get("Spice", 0) + 1
        summary += " (Auto-gained 1 Solari and 1 Spice)"
    elif intrigue_id == 'diplomacy':
        summary += " (EFFECT: Can place agent on occupied space) - APPLY MANUALLY."
    elif intrigue_id == 'ambush':
        summary += " (EFFECT: +5 Strength in combat) - APPLY MANUALLY IN CONFLICT."
    else:
        summary += f" (EFFECT: {intrigue_data.get('description')}) - APPLY MANUALLY."

    
    if "round_history" not in game_state:
        game_state["round_history"] = []
    game_state["round_history"].append({"summary": summary})
    
    return True, summary


def calculate_and_store_reveal_stats(game_state, cards_db):
    """Oblicza i zapisuje statystyki Odkrycia dla wszystkich graczy."""
    for player_name, player_data in game_state.get("players", {}).items():
        stats = calculate_reveal_stats(player_data, cards_db)
        player_data["reveal_stats"] = stats
    return game_state


# --- CAŁKOWICIE PRZEBUDOWANA FUNKCJA (REQ 1) ---
def calculate_reveal_stats(player_state, cards_db):
    """
    Oblicza sumę Perswazji i Siły dla gracza.
    Perswazja = tylko karty z ręki.
    Siła = karty z ręki + karty zagrane + wojska z garnizonu.
    """
    total_persuasion = 0
    total_swords = 0
    
    cards_in_hand_ids = player_state.get("hand", [])
    cards_played_ids = player_state.get("discard_pile", [])
    
    cards_in_hand_details = []
    cards_played_details = [] 

    # Krok 1: Przetwórz karty W RĘCE (dają Perswazję i Siłę)
    for card_id in cards_in_hand_ids:
        card_data = cards_db.get(card_id)
        if card_data:
            reveal_effect = card_data.get("reveal_effect", {})
            persuasion = reveal_effect.get("persuasion", 0)
            swords = reveal_effect.get("swords", 0)
            
            total_persuasion += persuasion
            total_swords += swords
            
            cards_in_hand_details.append({
                "name": card_data.get("name", card_id),
                "persuasion": persuasion,
                "swords": swords
            })

    # Krok 2: Przetwórz karty ZAGRANE (dają TYLKO Siłę)
    for card_id in cards_played_ids:
        card_data = cards_db.get(card_id)
        if card_data:
            reveal_effect = card_data.get("reveal_effect", {})
            # Perswazja z zagranych kart się nie liczy
            swords = reveal_effect.get("swords", 0)
            
            total_swords += swords
            
            cards_played_details.append({
                "name": card_data.get("name", card_id),
                "persuasion": 0, # Nie liczy się
                "swords": swords
            })
    
    # Krok 3: Efekty specjalne (na razie uproszczone, bazują na wszystkich kartach)
    # TODO: Ta logika powinna być bardziej złożona (np. "if you have emperor token" wpływa na perswazję z ręki)
    all_revealed_cards = cards_in_hand_ids + cards_played_ids
    has_emperor_token = player_state.get("influence", {}).get("emperor", 0) > 0
    has_fremen_card_in_play = False # Uproszczenie: czy zagrano kartę fremen
    for card_id in cards_played_ids:
        card_data = cards_db.get(card_id)
        if card_data and "fremen" in card_data.get("agent_symbols", []):
            has_fremen_card_in_play = True
            break

    for card_id in cards_in_hand_ids: # Sprawdzamy tylko karty w ręce pod kątem bonusów
        card_data = cards_db.get(card_id)
        if not card_data: continue
            
        reveal_effect = card_data.get("reveal_effect", {})
        description = reveal_effect.get("possible actions", {}).get("description", "")
        
        if "if you have emperor token you gain 4 persuasion" in description:
            if has_emperor_token:
                total_persuasion += 4
                
        elif "if you already have a fremen card in play, you gain 3 persuasion and 1 spice" in description:
            if has_fremen_card_in_play:
                total_persuasion += 3
    
    # Krok 4: Dodaj wojska z garnizonu do Siły
    garrison_troops = player_state.get("resources", {}).get("troops_garrison", 0)
    total_swords += garrison_troops
    
    return {
        "total_persuasion": total_persuasion,
        "total_swords": total_swords,
        "cards_in_hand": cards_in_hand_details,
        "cards_played": cards_played_details
    }


def process_buy_card(game_state, player_name, card_id, cards_db):
    """Przetwarza zakup karty ORAZ implementuje proste efekty zakupu."""
    player_state = game_state.get("players", {}).get(player_name)
    if not player_state:
        return False, f"Player {player_name} not found."
        
    card_data = cards_db.get(card_id)
    if not card_data:
        return False, "Card ID not found in database."

    market = game_state.get("imperium_row", [])
    if card_id not in market:
        return False, "Card is not available in the Imperium Row."
        
    card_cost = get_card_persuasion_cost(card_data)
    if card_cost == 999:
        return False, f"Card '{card_data.get('name')}' is not buyable."
    
    player_persuasion = player_state.get("reveal_stats", {}).get("total_persuasion", 0)
    
    if player_persuasion < card_cost:
        return False, f"Player {player_name} does not have enough persuasion. Required: {card_cost}, Has: {player_persuasion}."

    player_state["reveal_stats"]["total_persuasion"] -= card_cost
    
    if "discard_pile" not in player_state:
        player_state["discard_pile"] = []
    player_state["discard_pile"].append(card_id)
    
    if "deck_pool" not in player_state:
        player_state["deck_pool"] = []
    player_state["deck_pool"].append(card_id)
    
    game_state["imperium_row"].remove(card_id)
    
    summary = f"Player {player_name} bought '{card_data.get('name')}' for {card_cost} persuasion."
    
    buy_effect_list = card_data.get("buy_effect", {}).get("gain", [])
    for item in buy_effect_list:
        if item.get("type") == "gain":
            resource = item.get("resource")
            amount = item.get("amount", 0)
            
            if "influence" in str(resource):
                faction = resource.split(" ")[0] 
                if "influence" not in player_state:
                     player_state["influence"] = {}
                if faction not in player_state["influence"]:
                     player_state["influence"][faction] = 0
                player_state["influence"][faction] += amount
                summary += f" (and gained {amount} {faction} influence)"
            
            if resource == "victory point":
                if "victory_points" not in player_state:
                    player_state["victory_points"] = 0
                player_state["victory_points"] += amount
                summary += f" (and gained {amount} VICTORY POINT!)"
    
    if "round_history" not in game_state:
        game_state["round_history"] = []
    game_state["round_history"].append({"summary": summary})
    
    return True, summary


def add_card_to_market(game_state, card_id, cards_db):
    """Ręcznie dodaje kartę do rynku (Imperium Row)."""
    if card_id not in cards_db:
        return False, f"Card ID '{card_id}' not found in database."
    card_data = cards_db[card_id]
    cost = get_card_persuasion_cost(card_data)
    if cost == 999:
        return False, f"Card '{card_data.get('name')}' is not a buyable card."
    if "imperium_row" not in game_state:
        game_state["imperium_row"] = []
    game_state["imperium_row"].append(card_id)
    return True, f"Card '{card_data.get('name')}' has been added to the Imperium Row."


def perform_full_game_reset():
    """Kasuje game_stat.json i zastępuje go zawartością z game_stat.DEFAULT.json."""
    default_state = load_json_file(GAME_STATE_DEFAULT_FILE)
    if default_state is None:
        return False, f"Error: Default state file '{GAME_STATE_DEFAULT_FILE}' not found."
    if save_json_file(GAME_STATE_FILE, default_state):
        return True, "Success! The game has been fully reset to Round 1."
    else:
        return False, "Error: Could not write to game_stat.json."


def perform_cleanup_and_new_round(game_state):
    """Resetuje planszę na kolejną rundę. (Automatyczne dobieranie)"""
    if game_state:
        if "locations_state" in game_state:
            for loc_id in game_state["locations_state"]:
                game_state["locations_state"][loc_id]["occupied_by"] = None
        
        game_state["round_history"] = []
        game_state["current_phase"] = "AGENT_TURN" 
        game_state["round"] = game_state.get("round", 0) + 1
        
        # Resetuj kartę konfliktu (zostanie ustawiona ręcznie)
        game_state["current_conflict_card"] = { "name": "N/A", "rewards": {}, "rewards_text": [] }
        
        player_names = sorted(list(game_state.get("players", {}).keys()))
        game_state["currentPlayer"] = player_names[0] 

        for player_name, player_data in game_state.get("players", {}).items():
            player_data["agents_placed"] = 0
            player_data["has_passed"] = False 
            player_data["reveal_stats"] = {"total_persuasion": 0, "total_swords": 0}
            
            if player_data.get("agents_total", 2) != 3:
                player_data["agents_total"] = 2 
            
            player_data["draw_deck"] = player_data.get("draw_deck", []) + \
                                     player_data.get("hand", []) + \
                                     player_data.get("discard_pile", [])
            player_data["hand"] = []
            player_data["discard_pile"] = []
            
            player_data["draw_deck"] = list(player_data.get("deck_pool", []))
            
            random.shuffle(player_data["draw_deck"])
            
            for _ in range(5):
                if len(player_data["draw_deck"]) > 0:
                    card = player_data["draw_deck"].pop(0)
                    player_data["hand"].append(card)
            
    return game_state


def set_player_hand(game_state, player_name, card_ids_list, cards_db):
    """Ręcznie ustawia rękę gracza (np. AI)."""
    if not player_name:
        return False, "Player name not provided."
    player_state = game_state.get("players", {}).get(player_name)
    if not player_state:
        return False, f"Player {player_name} not found."
    if len(card_ids_list) != 5:
        return False, f"Invalid selection. You must select exactly 5 cards. You selected {len(card_ids_list)}."
    deck_pool = player_state.get("deck_pool", [])
    for card_id in card_ids_list:
        if card_id not in cards_db:
            return False, f"Invalid Card ID: {card_id} not found in database."
        if card_id not in deck_pool:
            card_name = cards_db.get(card_id, {}).get("name", card_id)
            return False, f"Invalid card: '{card_name}' is not in player {player_name}'s deck pool."
    player_state["hand"] = list(card_ids_list)
    draw_deck_list = list(deck_pool) 
    for card in card_ids_list:
        if card in draw_deck_list:
            draw_deck_list.remove(card)
    player_state["draw_deck"] = draw_deck_list
    player_state["discard_pile"] = []
    return True, f"Success! Set 5 cards for {player_name}. All other cards moved to draw deck."


# --- ZAKTUALIZOWANA FUNKCJA (REQ 3) ---
def process_conflict_set(game_state, conflicts_db, conflict_id):
    """Ustawia nową kartę konfliktu na tę rundę z bazy danych."""
    
    if not conflict_id:
        return False, "No conflict ID provided."
        
    if conflict_id not in conflicts_db:
        return False, f"Conflict ID '{conflict_id}' not found in database."
        
    conflict_data = conflicts_db[conflict_id]
    
    # Buduj tekstowe nagrody dla UI
    rewards_text_list = []
    rewards_map = conflict_data.get("rewards", {})
    for place in ["1", "2", "3"]:
        if place in rewards_map and rewards_map[place]:
            reward_str_parts = []
            for reward in rewards_map[place]:
                if reward["type"] == "vp":
                    reward_str_parts.append(f"{reward['amount']} VP")
                elif reward["type"] == "resource":
                    reward_str_parts.append(f"{reward['amount']} {reward['resource']}")
                elif reward["type"] == "intrigue":
                    reward_str_parts.append(f"{reward['amount']} Intrigue Card")
            rewards_text_list.append(f"{place}st: {', '.join(reward_str_parts)}")

    
    game_state["current_conflict_card"] = {
        "name": conflict_data.get("name", "Unknown Conflict"),
        "rewards": conflict_data.get("rewards", {}),
        "rewards_text": rewards_text_list # Przechowuj tekst dla UI
    }
    
    summary = f"Conflict set: {conflict_data.get('name')}"
    
    if "round_history" not in game_state:
        game_state["round_history"] = []
    game_state["round_history"].append({"summary": summary})
    
    return True, f"Conflict set: {conflict_data.get('name')}"


# --- NOWA FUNKCJA POMOCNICZA (REQ 4) ---
def apply_rewards(game_state, player_name, rewards_list):
    """Stosuje listę nagród dla danego gracza."""
    player_state = game_state.get("players", {}).get(player_name)
    if not player_state:
        return f"(Player {player_name} not found)"
        
    player_resources = player_state.get("resources", {})
    summary_parts = []
    
    for reward in rewards_list:
        try:
            r_type = reward.get("type")
            r_amount = reward.get("amount", 0)
            
            if r_type == "vp":
                player_state["victory_points"] = player_state.get("victory_points", 0) + r_amount
                summary_parts.append(f"gained {r_amount} VP")
                
            elif r_type == "resource":
                r_resource = reward.get("resource")
                if r_resource in player_resources:
                     player_resources[r_resource] = player_resources.get(r_resource, 0) + r_amount
                     summary_parts.append(f"gained {r_amount} {r_resource}")
                elif r_resource == "troops_garrison": # Na wszelki wypadek
                     player_resources["troops_garrison"] = player_resources.get("troops_garrison", 0) + r_amount
                     summary_parts.append(f"gained {r_amount} troops")
                
            elif r_type == "intrigue":
                if "intrigue_hand" not in player_state:
                    player_state["intrigue_hand"] = []
                for _ in range(r_amount):
                    player_state["intrigue_hand"].append(f"Intrigue_Card_{random.randint(100,999)}")
                summary_parts.append(f"gained {r_amount} Intrigue Card(s)")
                
        except Exception as e:
            print(f"Error applying reward: {e}")
            summary_parts.append(f"(Error applying reward: {reward})")
            
    return ", ".join(summary_parts)


# --- ZAKTUALIZOWANA FUNKCJA (REQ 4) ---
def process_conflict_resolve(game_state, first_place, second_place, third_place):
    """Zapisuje wyniki konfliktu i AUTOMATYCZNIE przyznaje nagrody."""
    
    conflict_card = game_state.get("current_conflict_card", {})
    conflict_name = conflict_card.get("name", "Conflict")
    rewards_map = conflict_card.get("rewards", {})
    
    summaries = []
    
    if first_place and "1" in rewards_map:
        reward_details = apply_rewards(game_state, first_place, rewards_map["1"])
        summaries.append(f"1st: {first_place} ({reward_details})")
        
    if second_place and "2" in rewards_map:
        reward_details = apply_rewards(game_state, second_place, rewards_map["2"])
        summaries.append(f"2nd: {second_place} ({reward_details})")

    if third_place and "3" in rewards_map:
        reward_details = apply_rewards(game_state, third_place, rewards_map["3"])
        summaries.append(f"3rd: {third_place} ({reward_details})")
    
    if not summaries:
        if not any([first_place, second_place, third_place]):
            return False, "No winners entered."
        # Ktoś wygrał, ale nie było nagród
        summaries = [f"1st: {first_place}", f"2nd: {second_place}", f"3rd: {third_place}"]
        
    full_summary = f"Conflict Resolved ({conflict_name}): {', '.join(summaries)}"

    if "round_history" not in game_state:
        game_state["round_history"] = []
    game_state["round_history"].append({"summary": full_summary})

    return True, "Conflict results saved and rewards applied."

def save_json_file_from_text(text_data):
    """
    Paruje tekst na JSON i zapisuje go do GAME_STATE_FILE.
    Zwraca (True, "Success") lub (False, "Error Message").
    """
    try:
        # Krok 1: Spróbuj sparsować tekst, aby sprawdzić, czy jest poprawnym JSONem
        data = json.loads(text_data)
        
        # Krok 2: Jeśli się udało, użyj istniejącej funkcji do zapisu
        if save_json_file(GAME_STATE_FILE, data):
            return True, "Zapisano pomyślnie."
        else:
            return False, "Wystąpił błąd wejścia/wyjścia (I/O) podczas zapisu pliku."
            
    except json.JSONDecodeError as e:
        # Krok 3: Jeśli parsowanie się nie powiodło, zwróć błąd
        print(f"JSON DECODE ERROR: {e}")
        return False, f"Błąd parsowania JSON. Sprawdź składnię. (Błąd: {e})"
    except Exception as e:
        print(f"UNKNOWN SAVE ERROR: {e}")
        return False, f"Wystąpił nieznany błąd: {e}"