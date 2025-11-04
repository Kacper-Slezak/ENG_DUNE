# app/game_manager.py
import json
import os
import random 

LOCATIONS_DB_FILE = 'locations.json'
CARDS_DB_FILE = 'cards.json'
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
    
    if not all([game_state, locations_db, cards_db]):
        return None, None, None, None 
    
    if game_state and locations_db:
        if "locations_state" not in game_state or len(game_state["locations_state"]) < len(locations_db) - 4: 
            print("WARNING: locations_state in game_stat.json is missing or incomplete. Rebuilding...")
            game_state["locations_state"] = {}
            for loc_id in locations_db.keys():
                 if not loc_id.endswith("_influence_path"):
                    game_state["locations_state"][loc_id] = {"occupied_by": None}
    
    # --- NOWOŚĆ: Upewnij się, że pole konfliktu istnieje ---
    if game_state and "current_conflict_card" not in game_state:
        game_state["current_conflict_card"] = {
            "name": "N/A",
            "rewards": []
        }
    
    return game_state, locations_db, cards_db, None 


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
                        current_amount = player_resources.get("troops", 0)
                        player_resources["troops"] = current_amount + resource_amount
                        
                    elif resource_name == "intrigue card":
                        if "intrigue_hand" not in player_state:
                            player_state["intrigue_hand"] = []
                        player_state["intrigue_hand"].append(f"Intrigue_Card_{random.randint(100,999)}")
                        move_summary += f" (gained 1 intrigue from location)"
                    
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
                current_amount = player_resources.get("troops", 0)
                player_resources["troops"] = current_amount + resource_amount
                
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


def process_intrigue(game_state, player_name, intrigue_text):
    """Po prostu zapisuje ręcznie wpisany tekst intrygi do historii."""
    player_state = game_state.get("players", {}).get(player_name)
    if not player_state:
        return False, "Player not found."
    if not intrigue_text:
        return False, "Intrigue text cannot be empty."
    
    summary = f"Player {player_name} played intrigue: '{intrigue_text}'."
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
    
    
    has_emperor_token = player_state.get("influence", {}).get("emperor", 0) > 0
    
    has_fremen_card_in_play = False
    for card_id in player_state.get("discard_pile", []):
        card_data = cards_db.get(card_id)
        if card_data and "fremen" in card_data.get("agent_symbols", []):
            has_fremen_card_in_play = True
            break

    for card_id in cards_to_reveal_ids:
        card_data = cards_db.get(card_id)
        if not card_data:
            continue
            
        reveal_effect = card_data.get("reveal_effect", {})
        possible_actions = reveal_effect.get("possible actions", {})
        description = possible_actions.get("description", "")
        
        if "if you have emperor token you gain 4 persuasion" in description:
            if has_emperor_token:
                total_persuasion += 4
                
        elif "if you already have a fremen card in play, you gain 3 persuasion and 1 spice" in description:
            if has_fremen_card_in_play:
                total_persuasion += 3
    
    return {
        "total_persuasion": total_persuasion,
        "total_swords": total_swords,
        "cards_in_hand": cards_in_hand_details,
        "cards_played": cards_played_details
    }


def process_buy_card(game_state, player_name, card_id, cards_db):
    """
    Przetwarza zakup karty ORAZ implementuje proste efekty zakupu.
    """
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
        return False, f"Card '{card_data.get('name')}' is not a buyable card (it's a starting card or has no cost)."

    if "imperium_row" not in game_state:
        game_state["imperium_row"] = []
        
    game_state["imperium_row"].append(card_id)
    
    return True, f"Card '{card_data.get('name')}' has been added to the Imperium Row."


def perform_full_game_reset():
    """
    Kasuje game_stat.json i zastępuje go zawartością z game_stat.DEFAULT.json.
    """
    default_state = load_json_file(GAME_STATE_DEFAULT_FILE)
    
    if default_state is None:
        print(f"CRITICAL: Could not load default state from {GAME_STATE_DEFAULT_FILE}")
        return False, f"Error: Default state file '{GAME_STATE_DEFAULT_FILE}' not found. Please create this file."
        
    if save_json_file(GAME_STATE_FILE, default_state):
        return True, "Success! The game has been fully reset to Round 1."
    else:
        print(f"CRITICAL: Could not save default state to {GAME_STATE_FILE}")
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
        
        # --- NOWOŚĆ: Resetuj kartę konfliktu ---
        game_state["current_conflict_card"] = { "name": "N/A", "rewards": [] }
        
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
    """
    Ręcznie ustawia rękę gracza (np. AI), przenosząc resztę kart do draw_deck.
    """
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
            draw_deck_list.remove(card) # Usuwa pierwsze wystąpienie (dobre dla duplikatów)
            
    player_state["draw_deck"] = draw_deck_list
    
    player_state["discard_pile"] = []
    
    return True, f"Success! Set 5 cards for {player_name}. All other cards moved to draw deck."

# --- NOWE FUNKCJE KONFLIKTU ---

def process_conflict_set(game_state, conflict_name, reward1, reward2, reward3):
    """Ustawia nową kartę konfliktu na tę rundę."""
    
    if not conflict_name:
        conflict_name = "N/A"
        
    rewards_list = []
    if reward1: rewards_list.append(f"1st: {reward1}")
    if reward2: rewards_list.append(f"2nd: {reward2}")
    if reward3: rewards_list.append(f"3rd: {reward3}")
    
    game_state["current_conflict_card"] = {
        "name": conflict_name,
        "rewards": rewards_list
    }
    
    summary = f"Conflict set: {conflict_name} | Rewards: {', '.join(rewards_list)}"
    
    if "round_history" not in game_state:
        game_state["round_history"] = []
    game_state["round_history"].append({"summary": summary})
    
    return True, f"Conflict set: {conflict_name}"

def process_conflict_resolve(game_state, first_place, second_place, third_place):
    """Zapisuje wyniki konfliktu do historii."""
    
    conflict_name = game_state.get("current_conflict_card", {}).get("name", "Conflict")
    
    summaries = []
    if first_place: summaries.append(f"1st Place: {first_place}")
    if second_place: summaries.append(f"2nd Place: {second_place}")
    if third_place: summaries.append(f"3rd Place: {third_place}")
    
    if not summaries:
        return False, "No winners entered."
        
    full_summary = f"Conflict Resolved ({conflict_name}): {', '.join(summaries)}"

    if "round_history" not in game_state:
        game_state["round_history"] = []
    game_state["round_history"].append({"summary": full_summary})

    return True, "Conflict results saved to history."