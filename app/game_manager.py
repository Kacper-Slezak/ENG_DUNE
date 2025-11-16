# app/game_manager.py
import json
import os
import random 

APP_DIR = os.path.dirname(os.path.abspath(__file__))

LOCATIONS_DB_FILE = os.path.join(APP_DIR, 'locations.json')
CARDS_DB_FILE = os.path.join(APP_DIR, 'cards.json')
INTRIGUES_DB_FILE = os.path.join(APP_DIR, 'intrigues.json')
CONFLICTS_DB_FILE = os.path.join(APP_DIR, 'conflicts.json') 
LEADERS_DB_FILE = os.path.join(APP_DIR, 'leaders.json')
GAME_STATE_FILE = os.path.join(APP_DIR, 'game_stat.json')
GAME_STATE_DEFAULT_FILE = os.path.join(APP_DIR, 'game_stat.DEFAULT.json')

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
    conflicts_db = load_json_file(CONFLICTS_DB_FILE)
    leaders_db = load_json_file(LEADERS_DB_FILE) # <-- NOWA LINIA
    if not all([game_state, locations_db, cards_db, intrigues_db, conflicts_db, leaders_db]): # <--
        return None, None, None, None, None, None 
    
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
    
    return game_state, locations_db, cards_db, intrigues_db, conflicts_db, leaders_db

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


def is_move_valid(game_state, locations_db, leaders_db, cards_db, player_name, card_id, location_id):
    """Waliduje ruch (bez sprawdzania czyja tura)."""
    
    if game_state.get("current_phase") != "AGENT_TURN":
        return False, f"Cannot send an agent. The current game phase is: {game_state.get('current_phase')}"
    
    player_state = game_state.get("players", {}).get(player_name, {})
    if not player_state:
        return False, f"Player {player_name} not found."
    
    player_leader_id = player_state.get("leader")
    leader_data = leaders_db.get(player_leader_id, {})
    passive_ability_name = leader_data.get("ability_passive", {}).get("name")
    
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
        # Sprawdź zdolność Heleny
        if passive_ability_name == "Knows Everything":
            location_symbol = location_data.get("symbol_required")
            if location_symbol in ["populated areas", "Landsraad"]:
                pass # Zdolność Heleny pozwala zignorować zajęte pole
            else:
                return False, f"Location is already occupied. (Helena's ability only works on 'populated areas' and 'Landsraad' spaces)."
        else:
            return False, f"Location is already occupied by player {location_state['occupied_by']}."

    player_hand = player_state.get("hand", [])
    if card_id not in player_hand:
        card_name = card_data.get('name', card_id)
        return False, f"Player {player_name} does not have the card '{card_name}' in their hand."
            
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
            
            effective_required_amount = required_amount
            if passive_ability_name == "Popularity in Landsraad" and resource_name == "solari":
                location_symbol = location_data.get("symbol_required")
                if location_symbol == "Landsraad":
                    effective_required_amount = max(0, required_amount - 1)
            
            if player_has < effective_required_amount:
                return False, f"Player {player_name} does not have enough resources. Required: {effective_required_amount} {resource_name} (Original: {required_amount}), Has: {player_has}."

    extra_req = location_data.get("extra_requirement")
    
    if extra_req and extra_req != "none":
        
        
        if extra_req == "2 fremen influence points":
            player_fremen_influence = player_state.get("influence", {}).get("fremen", 0)
            if player_fremen_influence < 2:
                return False, f"Wymaganie lokacji: '{extra_req}'. Gracz {player_name} ma tylko {player_fremen_influence}."
        
    return True, "Move is valid."


# --- NOWA FUNKCJA POMOCNICZA: DOBIERANIE KART ---
def draw_cards(player_state, amount_to_draw):
    """
    Automatycznie dobiera karty dla gracza, tasując odrzucone karty, jeśli to konieczne.
    """
    draw_deck = player_state.get("draw_deck", [])
    discard_pile = player_state.get("discard_pile", [])
    hand = player_state.get("hand", [])
    
    cards_drawn_names = []

    for _ in range(amount_to_draw):
        if not draw_deck:
            if not discard_pile:
                # Nie ma więcej kart do dobrania
                break
            
            # Przetasuj discard_pile aby stał się nowym draw_deck
            random.shuffle(discard_pile)
            draw_deck = discard_pile
            discard_pile = []
            
        # Dobierz kartę
        card_id = draw_deck.pop(0)
        hand.append(card_id)
        cards_drawn_names.append(card_id) # Można zamienić na nazwę karty dla lepszego logu

    player_state["draw_deck"] = draw_deck
    player_state["discard_pile"] = discard_pile
    player_state["hand"] = hand
    
    return f"drew {len(cards_drawn_names)} card(s)"


def process_move(game_state, locations_db, cards_db, leaders_db, player_name, card_id, location_id, **kwargs):    
    """
    Przetwarza ruch ORAZ implementuje efekty agenta, lokacji i sygnetu.
    """
    
    card_name = cards_db.get(card_id, {}).get("name", card_id)
    location_name = locations_db.get(location_id, {}).get("name", location_id)
    location_data = locations_db.get(location_id, {})
    card_data = cards_db.get(card_id, {})
    
    player_state = game_state.get("players", {}).get(player_name, {})
    player_resources = player_state.get("resources", {})

    player_leader_id = player_state.get("leader")
    leader_data = leaders_db.get(player_leader_id, {})
    passive_ability_name = leader_data.get("ability_passive", {}).get("name")

    # --- 1. Ustawienie lokacji ---
    if location_id not in game_state["locations_state"]:
         game_state["locations_state"][location_id] = {}
    game_state["locations_state"][location_id]["occupied_by"] = player_name
    
    move_summary = f"{player_name} played '{card_name}' on '{location_name}'."

    # --- 2. Zapłać koszt lokacji ---
    location_cost = location_data.get("cost", [])
    for cost_item in location_cost:
        if cost_item.get("type") == "resource":
            resource_name = cost_item.get("resource")
            resource_amount = cost_item.get("amount", 0)
            
            # Oblicz efektywny koszt (Zdolność Leto)
            effective_resource_amount = resource_amount
            if passive_ability_name == "Popularity in Landsraad" and resource_name == "solari":
                location_symbol = location_data.get("symbol_required")
                if location_symbol == "Landsraad":
                    effective_resource_amount = max(0, resource_amount - 1)
            
            # Zapłać koszt
            current_amount = player_resources.get(resource_name, 0)
            player_resources[resource_name] = current_amount - effective_resource_amount
            move_summary += f" (Paid {effective_resource_amount} {resource_name})"
            
            # Sprawdź zdolność Ilbana
            if passive_ability_name == "Ruthless Negotiator" and resource_name == "solari" and effective_resource_amount > 0:
                draw_summary = draw_cards(player_state, 1) # Użyj istniejącej funkcji pomocniczej
                move_summary += f" | Ilban's Ability: {draw_summary}"
            
    # --- 3. Zastosuj efekty lokacji ---
    location_actions_list = location_data.get("actions", [])
    loc_summary_parts = [] # Lista na podsumowanie efektów lokacji
    
    # Wywołujemy "mądrą" funkcję, przekazując jej game_state
    _process_action_list(player_state, location_actions_list, loc_summary_parts, game_state, **kwargs)    
    if loc_summary_parts:
        move_summary += f" | Location: {', '.join(loc_summary_parts)}"
    else:
        move_summary += " | Location: (No effect)"

    # --- POCZĄTEK NOWEJ LOGIKI (EARL) ---
    # Sprawdź zdolność Earla po zajęciu High Council
    if passive_ability_name == "Connections" and location_id == "high_council":
        # Ręcznie stwórz akcję "gain intrigue" i przetwórz ją
        intrigue_action = [{"gain": {"type": "resource", "resource": "intrigue", "amount": 1}}] # Lekko zmieniona struktura, aby pasowała do _process_action_list
        intrigue_summary_parts = []
        
        # Używamy "mądrej" funkcji, przekazując kwargs na wypadek przyszłych zmian
        _process_action_list(player_state, intrigue_action, intrigue_summary_parts, game_state, **kwargs) 
        
        if intrigue_summary_parts:
            move_summary += f" | Earl's Ability: {', '.join(intrigue_summary_parts)}"
    # --- KONIEC NOWEJ LOGIKI ---
    
    # --- 4. Zastosuj efekty karty (Agent lub Signet) ---
    is_destroyed = False
    
    # === OBSŁUGA SIGNET RING ===
    if card_id == 'signet_ring':
        player_leader_id = player_state.get("leader") # To już mamy
        if player_leader_id and player_leader_id in leaders_db:
            leader_data_signet = leaders_db[player_leader_id] # Użyj innej zmiennej
            signet_ability = leader_data_signet.get("ability_signet", {})
            signet_actions = signet_ability.get("action", [])
            
            # Przekaż dane lidera również tutaj (na wypadek, gdyby sygnet dawał przyprawę Arianie)
            signet_summary_parts = []
            _process_action_list(player_state, signet_actions, signet_summary_parts, game_state, **kwargs)
            if signet_summary_parts:
                move_summary += f" | Signet ({signet_ability.get('name', 'Ability')}): {', '.join(signet_summary_parts)}"
            else:
                move_summary += f" | Signet ({signet_ability.get('name', 'Ability')}): (No effect)"
        else:
            move_summary += " | (ERROR: Player leader not found for Signet Ring)"
    
    # === OBSŁUGA STANDARDOWEGO EFEKTU AGENTA ===
    else:
        agent_effect = card_data.get("agent_effect", {})
        agent_actions_list = agent_effect.get("actions", [])
        
        card_summary_parts = [] # Lista na podsumowanie efektów karty
        _process_action_list(player_state, agent_actions_list, card_summary_parts, game_state, **kwargs)
        
        if card_summary_parts:
            move_summary += f" | Card: {', '.join(card_summary_parts)}"
        else:
            move_summary += " | Card: (No effect)"
        
        # Sprawdź, czy karta ma być zniszczona
        for item in agent_actions_list:
            if item.get("type") == "destroy this card":
                is_destroyed = True
                break
            
    # --- 5. Przenieś kartę (do odrzuconych lub zniszczonych) ---
    if is_destroyed:
        if card_id in player_state.get("hand", []):
            player_state["hand"].remove(card_id)
        if card_id in player_state.get("deck_pool", []):
            player_state["deck_pool"].remove(card_id)
        if "destroyed_pile" not in game_state:
            game_state["destroyed_pile"] = []
        game_state["destroyed_pile"].append(card_id)
        move_summary += " (Card Destroyed)"
    else:
        # Przenieś z ręki (AI) lub z puli (Człowiek) na stos odrzuconych
        if card_id in player_state.get("hand", []):
            player_state["hand"].remove(card_id)
            if "discard_pile" not in player_state:
                player_state["discard_pile"] = []
            player_state["discard_pile"].append(card_id)
        elif player_name != AI_PLAYER_NAME:
             if "discard_pile" not in player_state:
                player_state["discard_pile"] = []
             player_state["discard_pile"].append(card_id)

    # --- 6. Zaktualizuj stan agentów gracza ---
    player_state["agents_placed"] = player_state.get("agents_placed", 0) + 1
    
    # Lokacja MENTAT: Daje +1 agenta TYLKO w tej rundzie
    # Osiągamy to przez cofnięcie licznika zużytych agentów o 1
    if location_id == "mentat": 
        if player_state.get("agents_placed", 0) > 0:
            player_state["agents_placed"] -= 1
            move_summary += " (Gained 1 temporary agent)"

    # Lokacja SWORDMASTER: Daje +1 agenta NA STAŁE
    if location_id == "swordmaster":
        if player_state.get("agents_total", 2) < 3: # Zapobiega wielokrotnemu dodawaniu
            player_state["agents_total"] = 3
            move_summary += " (Gained 1 permanent agent)"
    
    if "round_history" not in game_state:
        game_state["round_history"] = []
        
    game_state["round_history"].append({
        "player": player_name,
        "card": card_name,
        "location": location_name,
        "summary": move_summary
    })
        
    return game_state


def get_intrigue_requirements(intrigue_id, intrigues_db):
    """
    Sprawdza, czy karta intrygi wymaga interakcji z graczem (wyboru lub opłaty).
    Zwraca słownik opisujący wymaganą decyzję.
    """
    card_data = intrigues_db.get(intrigue_id)
    if not card_data:
        return {"type": "not_found"}

    actions = card_data.get("actions", {})
    
    # Proste karty, które nie wymagają decyzji (tylko 'gain' lub 'set_flag')
    if "gain" in actions or "set_flag" in actions:
        return {"type": "simple"} #

    if "action" in actions:
        action_list = actions["action"]
        if not action_list or not isinstance(action_list, list):
            return {"type": "simple"} # Karta ma pustą akcję lub jest tylko opisem

        first_op = action_list[0]
        
        if "choice" in first_op:
            # Karta wymaga wyboru (np. "master_tactitian", "bypass_protocol")
            #
            return {
                "type": "choice",
                "data": first_op["choice"] # Przekaż listę opcji do app.py
            }
            
        if "exchange" in first_op:
            # Karta wymaga wymiany (np. "bribery", "personal_army")
            #
            return {
                "type": "exchange",
                "data": first_op["exchange"] # Przekaż dane wymiany do app.py
            }
            
        if "pay" in first_op:
            # Karta wymaga opcjonalnej opłaty (np. "calculated_recruitment")
            #
            return {
                "type": "conditional_pay",
                "data": first_op["pay"] # Przekaż dane opłaty do app.py
            }

    # Domyślnie, jeśli struktura jest nieznana lub to tylko opis (np. "infiltration")
    #
    return {"type": "simple"}


def _find_decision_in_actions(actions_list):
    """
    (NOWY POMOCNIK) Skanuje listę akcji i zwraca pierwszy znaleziony wymóg decyzji.
    """
    if not isinstance(actions_list, list):
        return {"type": "simple"}

    for item in actions_list:
        if not item: continue
        
        # Klucz operacji to zazwyczaj pierwszy klucz w słowniku
        operation_key = list(item.keys())[0]

        if operation_key == "choice":
            return {
                "type": "choice",
                "data": item["choice"]
            }
        
        if operation_key == "exchange":
            return {
                "type": "exchange",
                "data": item["exchange"]
            }

        if operation_key == "pay":
             # Zakładamy, że "pay" na tym poziomie to opcjonalna opłata
            return {
                "type": "conditional_pay",
                "data": item["pay"]
            }
    
    return {"type": "simple"}

def get_agent_move_requirements(card_data, location_data, leaders_db, player_state):
    """
    (NOWA FUNKCJA) Sprawdza, czy ruch agenta (karta + lokacja + sygnet) wymaga interakcji.
    """
    
    # 1. Sprawdź efekty Karty Agenta
    if card_data.get("name") == "Signet Ring":
        # === Specjalny przypadek: Sygnet ===
        player_leader_id = player_state.get("leader")
        if player_leader_id and player_leader_id in leaders_db:
            leader_data_signet = leaders_db[player_leader_id]
            signet_ability = leader_data_signet.get("ability_signet", {})
            signet_actions = signet_ability.get("action", [])
            
            sygnet_decision = _find_decision_in_actions(signet_actions)
            if sygnet_decision["type"] != "simple":
                sygnet_decision["source"] = leader_data_signet.get("ability_signet", {}).get("name", "Signet Ring")
                return sygnet_decision
    else:
        # === Standardowa Karta Agenta ===
        agent_actions = card_data.get("agent_effect", {}).get("actions", [])
        card_decision = _find_decision_in_actions(agent_actions)
        if card_decision["type"] != "simple":
            card_decision["source"] = card_data.get("name", "Card")
            return card_decision

    # 2. Sprawdź efekty Lokacji
    location_actions = location_data.get("actions", [])
    loc_decision = _find_decision_in_actions(location_actions)
    if loc_decision["type"] != "simple":
        loc_decision["source"] = location_data.get("name", "Location")
        return loc_decision
        
    # 3. Jeśli nigdzie nie znaleziono decyzji
    return {"type": "simple"}


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
        game_state["current_phase"] = "REVEAL"
        
    return game_state



def _check_requirement(player_state, requirement_list, game_state):
    """(Helper) Sprawdza, czy gracz spełnia wymagania."""
    log_summary = []
    all_met = True
    
    if not isinstance(requirement_list, list):
        requirement_list = [requirement_list]

    for req in requirement_list:
        req_type = req.get("type")
        
        if req_type == "action" and "win the conflict" in req.get("description", ""):
            # Wymagałoby to flagi ustawionej po rozwiązaniu konfliktu
            if not player_state.get("active_effects", {}).get("won_conflict", False):
                log_summary.append("Wymaganie 'wygrania konfliktu' niespełnione.")
                all_met = False
        
        elif req_type == "resource" and req.get("resource") == "The Spice Must Flow":
            # Dla "market_manopoly"
            count = player_state.get("deck_pool", []).count("the_spice_must_flow")
            min_amount = req.get("amount", 2) # Domyślnie 2 z opisu
            if count < min_amount:
                log_summary.append(f"Wymaganie 'min. {min_amount} The Spice Must Flow' niespełnione (Ma: {count}).")
                all_met = False
        
        elif req_type == "influence":
             # Dla "plans_within_plans"
            influence = player_state.get("influence", {})
            min_level = 3 # Z opisu
            count = sum(1 for v in influence.values() if v >= min_level)
            
            if "3 influence on 3 faction tracks" in req.get("description", ""):
                if count < 3:
                    log_summary.append("Wymaganie 'min. 3 wpływu na 3 ścieżkach' niespełnione.")
                    all_met = False
            elif "3 influence on 4 faction tracks" in req.get("description", ""):
                if count < 4:
                    log_summary.append("Wymaganie 'min. 3 wpływu na 4 ścieżkach' niespełnione.")
                    all_met = False
                    
        elif req_type == "action" and "place in high council" in req.get("description", ""):
            # Dla "agreement_from_high_council"
            # Zakładamy, że lokacja "high_council" jest zajęta przez gracza
            if game_state.get("locations_state", {}).get("high_council", {}).get("occupied_by") != player_state.get("name", ""):
                 log_summary.append("Wymaganie 'miejsce w High Council' niespełnione.")
                 all_met = False

        else:
            log_summary.append(f"Wymaganie '{req.get('description', 'nieznane')}' sprawdzane manualnie (założono TRUE).")
            
    return all_met, " ".join(log_summary)

def _apply_cost(player_state, pay_data, log_summary):
    """(Helper) Próbuje pobrać koszt od gracza. Zwraca True/False."""
    if not isinstance(pay_data, list):
        pay_data = [pay_data]
        
    player_resources = player_state.get("resources", {})
    
    # Krok 1: Sprawdź, czy gracza stać
    for cost in pay_data:
        resource = cost.get("resource")
        amount = cost.get("amount", 0)
        
        # Specjalna obsługa dla "feigned_incident"
        if resource == "troops in conflict":
            # To musiałoby być obsługiwane przez stan konfliktu, tu symulujemy
            if player_state.get("troops_in_conflict", 0) < amount:
                 log_summary.append(f"Niepowodzenie: brak {amount} wojsk w konflikcie.")
                 return False
        elif player_resources.get(resource, 0) < amount:
            log_summary.append(f"Niepowodzenie: brak {amount} {resource}.")
            return False
            
    # Krok 2: Pobierz zasoby
    for cost in pay_data:
        resource = cost.get("resource")
        amount = cost.get("amount", 0)
        
        if resource == "troops in conflict":
            player_state["troops_in_conflict"] = player_state.get("troops_in_conflict", 0) - amount
            log_summary.append(f"Usunięto {amount} wojsk z konfliktu.")
        else:
            player_resources[resource] -= amount
            log_summary.append(f"Zapłacono {amount} {resource}.")
        
    return True

def _apply_gain(player_state, gain_data, log_summary, game_state, **kwargs):
    """(Helper) Stosuje zysk dla gracza."""
    if not isinstance(gain_data, list):
        gain_data = [gain_data]

    player_resources = player_state.get("resources", {})

    for gain in gain_data:
        gain_type = gain.get("type")
        
        if gain_type == "resource":
            resource = gain.get("resource")
            amount = gain.get("amount", 0)
            
            if "influence point" in resource:
                faction = resource.split(" ")[0]
                if "influence" not in player_state: player_state["influence"] = {}
                player_state["influence"][faction] = player_state["influence"].get(faction, 0) + amount
                log_summary.append(f"Zyskano {amount} wpływu {faction}.")

                # Pobierz nowy stan wpływów
                new_influence = player_state["influence"][faction]

                # --- START NOWY KOD (Bonus 1 VP za 2 pkt) ---
                if "faction_vp_claimed_2pts" not in player_state:
                    player_state["faction_vp_claimed_2pts"] = {"emperor": False, "guild": False, "fremen": False, "bene_gesserit": False}

                if new_influence >= 2 and not player_state["faction_vp_claimed_2pts"].get(faction, False):
                    player_state["faction_vp_claimed_2pts"][faction] = True
                    player_state["victory_points"] = player_state.get("victory_points", 0) + 1
                    log_summary.append(f"Osiągnięto 2 pkt. wpływu w {faction}! Zyskano 1 VP (nowa mechanika).")
                # --- KONIEC NOWEGO KODU ---


                # --- START KOD (BONUS ZA 4 PKT) ---
                if "faction_bonus_claimed" not in player_state:
                    player_state["faction_bonus_claimed"] = {"emperor": False, "guild": False, "fremen": False, "bene_gesserit": False}
                
                # Sprawdź jednorazowy bonus za 4 punkty
                if new_influence >= 4 and not player_state["faction_bonus_claimed"].get(faction, False):
                    player_state["faction_bonus_claimed"][faction] = True
                    log_summary.append(f"Osiągnięto 4 pkt. wpływu! Odbieranie jednorazowej nagrody...")
                    
                    bonus_reward = []
                    if faction == "emperor":
                        # Uwaga: Aplikacja nie wspiera "deploy". Dajemy wojsko do garnizonu.
                        bonus_reward = [{"type": "resource", "resource": "troops_garrison", "amount": 2}]
                    elif faction == "guild":
                        bonus_reward = [{"type": "resource", "resource": "solari", "amount": 3}]
                    elif faction == "fremen":
                        bonus_reward = [{"type": "resource", "resource": "water", "amount": 1}]
                    elif faction == "bene_gesserit":
                        bonus_reward = [{"type": "resource", "resource": "intrigue", "amount": 1}]
                    
                    if bonus_reward:
                        _apply_gain(player_state, bonus_reward, log_summary, game_state, **kwargs) 

                check_and_update_alliances(player_state, game_state, faction, log_summary)

            elif resource == "vp":
                player_state["victory_points"] = player_state.get("victory_points", 0) + amount
                log_summary.append(f"Zyskano {amount} VP!")
            elif resource == "fight points":
                # Dla "master_tactitian", "personal_army"
                if "active_effects" not in player_state: player_state["active_effects"] = {}
                current = player_state["active_effects"].get("fight_bonus_swords", 0)
                player_state["active_effects"]["fight_bonus_swords"] = current + amount
                log_summary.append(f"Zyskano {amount} punktów walki (miecza).")
            elif resource == "persuasion":
                 # Dla "charisma"
                if "reveal_stats" not in player_state: player_state["reveal_stats"] = {}
                current = player_state["reveal_stats"].get("total_persuasion", 0)
                player_state["reveal_stats"]["total_persuasion"] = current + amount
                log_summary.append(f"Zyskano {amount} perswazji (do Fazy Odkrycia).")
            elif resource in player_resources:
                player_resources[resource] = player_resources.get(resource, 0) + amount
                log_summary.append(f"Zyskano {amount} {resource}.")
            # --- START POPRAWKI (TROOPS & INTRIGUE) ---
            elif resource == "troops":
                # Naprawia błąd (np. z Kartaginy), przekierowując wojsko do garnizonu
                player_resources["troops_garrison"] = player_resources.get("troops_garrison", 0) + amount
                log_summary.append(f"Zyskano {amount} troops (do garnizonu).")
            
            elif resource == "intrigue":
                # Naprawia błąd (np. z Kartaginy, B.G.)
                if "intrigue_hand" not in player_state:
                    player_state["intrigue_hand"] = []
                for _ in range(amount): # Użyj pętli, jeśli amount > 1
                    player_state["intrigue_hand"].append(f"Intrigue_Card_{random.randint(100,999)}")
                log_summary.append(f"Zyskano {amount} kartę Intrygi (placeholder).")
            # --- KONIEC POPRAWKI ---
            else:
                log_summary.append(f"Nieznany zasób: {resource}.")
        
        elif gain_type == "action":
            # Dla kart "trick", "concentration", "infiltration" itp.
            # Te nadal wymagają ręcznej obsługi LUB dalszej rozbudowy logiki
            log_summary.append(f"Efekt manualny: {gain.get('description')}")
        
        else:
            log_summary.append(f"Manualny zysk: {gain.get('description', 'nieznany')}")


def check_and_update_alliances(player_state, game_state, faction, log_summary):
    """
    Sprawdza i aktualizuje stan sojuszy dla danej frakcji po zdobyciu wpływów.
    Przyznaje 1 VP nowemu sojusznikowi i odbiera 1 VP staremu sojusznikowi.
    """
    player_name = player_state.get("name", "Unknown Player") # Upewnij się, że player_state ma "name" lub pobierz go inaczej
    if player_name == "Unknown Player" and "leader" in player_state: # Hack, aby znaleźć nazwę gracza
        for name, p_data in game_state.get("players", {}).items():
            if p_data.get("leader") == player_state.get("leader"):
                player_name = name
                player_state["name"] = name # Zapisz na przyszłość
                break

    player_influence = player_state.get("influence", {}).get(faction, 0)

    # --- START POPRAWKI (PRZYWRÓCENIE POPRAWNEGO PROGU) ---
    # Gracz musi mieć co najmniej 4 wpływy, aby kwalifikować się do sojuszu
    if player_influence < 4:
        return # Gracz nie ma wystarczająco wpływów
    # --- KONIEC POPRAWKI ---

    if "alliances" not in game_state:
        game_state["alliances"] = {"emperor": None, "guild": None, "fremen": None, "bene_gesserit": None}

    current_ally_name = game_state["alliances"].get(faction)

    # Jeśli gracz już ma ten sojusz, nic się nie zmienia
    if current_ally_name == player_name:
        return

    # Sprawdź, czy gracz ma więcej wpływów niż obecny sojusznik
    if current_ally_name:
        current_ally_state = game_state.get("players", {}).get(current_ally_name)
        if current_ally_state:
            current_ally_influence = current_ally_state.get("influence", {}).get(faction, 0)
            # Gracz musi mieć ŚCIŚLE WIĘCEJ wpływów, aby przejąć sojusz
            if player_influence <= current_ally_influence:
                return # Nie udało się przejąć sojuszu

            # Odbierz VP staremu sojusznikowi
            current_ally_state["victory_points"] = current_ally_state.get("victory_points", 1) - 1
            log_summary.append(f"Gracz {current_ally_name} stracił sojusz z {faction} (i 1 VP).")

    # Przyznaj sojusz i VP nowemu graczowi
    game_state["alliances"][faction] = player_name
    player_state["victory_points"] = player_state.get("victory_points", 0) + 1
    log_summary.append(f"Gracz {player_name} zdobył sojusz z {faction} i zyskał 1 VP!")
    

def _process_action_list(player_state, action_list, log_summary, game_state, **kwargs):
    """(Helper) Przetwarza złożoną listę akcji, wymagań, wyborów i wymian."""
    
    all_reqs_met = True
    
    for item in action_list:
        if not all_reqs_met:
            log_summary.append("Akcja przerwana z powodu niespełnienia wymagań.")
            break
        
        if not item: continue
        # Znajdź kluczowy typ operacji (np. "type", "exchange", "choice", "gain", "pay")
        operation_key = list(item.keys())[0]

        if operation_key == "type":
            if item["type"] == "requirement":
                all_reqs_met, req_log = _check_requirement(player_state, item["requirement"], game_state)
                if req_log: log_summary.append(req_log)
            elif item["type"] == "action":
                _apply_gain(player_state, item, log_summary, game_state, **kwargs)
            else:
                log_summary.append(f"Nieznany typ operacji: {item['type']}")

        elif operation_key == "gain":
            _apply_gain(player_state, item["gain"], log_summary, game_state, **kwargs)

        elif operation_key == "pay":
            # Dla "calculated_recruitment"
            if kwargs.get("pay_cost", False): # Wymaga jawnej zgody
                if not _apply_cost(player_state, item["pay"], log_summary):
                    all_reqs_met = False # Nie udało się zapłacić, zatrzymaj dalsze akcje
            else:
                log_summary.append("Gracz odrzucił opcjonalny koszt.")
                all_reqs_met = False # Odrzucenie kosztu zatrzymuje łańcuch

        elif operation_key == "exchange":
            # Dla "bribery", "personal_army", "trick", "sleeping_must_wake_up", "khoam_shares"
            exchange_data = item["exchange"]
            pay_data = next((d for d in exchange_data if "pay" in d), {}).get("pay")
            gain_data_list = [d for d in exchange_data if "pay" not in d] 
            
            if not pay_data or not gain_data_list:
                log_summary.append("Błąd struktury wymiany.")
                continue

            if kwargs.get("pay_cost", False): # Wymaga jawnej zgody na wymianę
                if _apply_cost(player_state, pay_data, log_summary):
                    for gain_item in gain_data_list:
                        if "gain" in gain_item:
                             _apply_gain(player_state, gain_item["gain"], log_summary, game_state, **kwargs)
                        elif "type" in gain_item and gain_item["type"] == "action":
                             _apply_gain(player_state, gain_item, log_summary, game_state, **kwargs)
                else:
                    log_summary.append("Wymiana nieudana (brak środków).")
            else:
                log_summary.append("Gracz odrzucił opcjonalną wymianę.")
                
        elif operation_key == "choice":
            # Dla "master_tactitian", "bypass_protocol", "demand_for_a_respect"
            choice_index = kwargs.get("choice_index", -1)
            choices = item["choice"]
            
            if choice_index < 0 or choice_index >= len(choices):
                log_summary.append(f"Wymagany wybór (0-{len(choices)-1}), ale nie podano lub jest błędny. Karta odrzucona bez efektu.")
                all_reqs_met = False
            else:
                log_summary.append(f"Wybrano opcję {choice_index + 1}.")
                # Wybrana opcja to lista akcji (np. [{ "gain": ... }] lub [{ "pay": ... }, { "type": "action" ... }])
                chosen_action_key = list(choices[choice_index].keys())[0] # np. "action1"
                chosen_action_list = choices[choice_index][chosen_action_key]
                _process_action_list(player_state, chosen_action_list, log_summary, game_state, **kwargs)
        
        else:
             log_summary.append(f"Nieobsługiwany klucz operacji: {operation_key}")

    return all_reqs_met

# --- KONIEC SEKCJI POMOCNICZEJ ---


def process_intrigue(game_state, intrigues_db, player_name, intrigue_id, **kwargs):
    """
    Przetwarza zagranie intrygi z ręki i automatyzuje wszystkie efekty
    na podstawie struktury JSON i dodatkowych argumentów (decyzji gracza).
    
    Argumenty **kwargs:
    - pay_cost (bool): True, jeśli gracz zgadza się na opcjonalny koszt/wymianę.
    - choice_index (int): Indeks (0, 1, ...) wyboru dokonanego przez gracza.
    """
    player_state = game_state.get("players", {}).get(player_name)
    if not player_state:
        return False, "Nie znaleziono gracza."
        
    if not intrigue_id:
        return False, "Nie wybrano karty intrygi."
        
    if intrigue_id not in player_state.get("intrigue_hand", []):
        return False, "Gracz nie ma tej karty intrygi w ręce."
        
    intrigue_data = intrigues_db.get(intrigue_id)
    if not intrigue_data:
        intrigue_data = {"name": intrigue_id, "description": "Nie znaleziono opisu.", "actions": {}}

    # Usuń intrygę z ręki NATYCHMIAST
    player_state["intrigue_hand"].remove(intrigue_id)
    
    log_summary = [f"Gracz {player_name} zagrał intrygę: '{intrigue_data.get('name')}'."]
    
    actions_object = intrigue_data.get("actions", {})
    card_type = intrigue_data.get("type", "conspiracy")

    # --- NOWA, SOLIDNA OBSŁUGA ---
    
    if "gain" in actions_object:
        # 1. Prosty GAIN (np. "occasion", "learn_their_path")
        _apply_gain(player_state, actions_object["gain"], log_summary, game_state, **kwargs)
        
    elif "set_flag" in actions_object:
        # 2. Ustawienie FLAGI (np. "ambush")
        flag_data = actions_object["set_flag"]
        flag_name = flag_data.get("name")
        
        if "active_effects" not in player_state:
            player_state["active_effects"] = {}
        
        if "value_add" in flag_data:
            current_value = player_state["active_effects"].get(flag_name, 0)
            added_value = flag_data.get("value_add", 0)
            player_state["active_effects"][flag_name] = current_value + added_value
            log_summary.append(f"Efekt: Zyskano bonus +{added_value} {flag_name}.")
        else:
             value_to_set = flag_data.get("value", True) 
             player_state["active_effects"][flag_name] = value_to_set
             log_summary.append(f"Efekt: Zyskano tymczasową zdolność '{flag_name}'.")

    elif "action" in actions_object:
        # 3. Złożona lista AKCJI (np. "bribery", "master_tactitian", "plans_within_plans")
        # Przekazujemy player_state, listę akcji, log, cały stan gry (dla _check_requirement) i decyzje
        _process_action_list(player_state, actions_object["action"], log_summary, game_state, **kwargs)
    
    elif "action1" in actions_object:
         # 4. Specjalny przypadek dla "market_manopoly"
         # Ta karta ma dwie oddzielne, niezależne akcje
        log_summary.append("Sprawdzanie efektów 'Market Manopoly':")
        _process_action_list(player_state, [actions_object["action1"]], log_summary, game_state, **kwargs)
        _process_action_list(player_state, [actions_object["action2"]], log_summary, game_state, **kwargs)

    else:
        # 5. Fallback dla nieznanych struktur lub kart tylko z opisem
        log_summary.append(f"Efekt manualny: {intrigue_data.get('description')}")

    
    final_summary = " | ".join(log_summary)

    if "round_history" not in game_state:
        game_state["round_history"] = []
    game_state["round_history"].append({"summary": final_summary})
    
    return True, final_summary


def calculate_and_store_reveal_stats(game_state, cards_db):
    """Oblicza i zapisuje statystyki Odkrycia dla wszystkich graczy."""
    for player_name, player_data in game_state.get("players", {}).items():
        stats = calculate_reveal_stats(player_data, cards_db)
        player_data["reveal_stats"] = stats
    return game_state


def calculate_reveal_stats(player_state, cards_db):
    """
    Oblicza sumę Perswazji i BAZOWEJ Siły dla gracza.
    TERAZ OBSŁUGUJE KLUCZOWE EFEKTY WARUNKOWE.
    """
    total_persuasion = 0
    base_swords = 0  
    
    cards_in_hand_ids = player_state.get("hand", [])
    cards_played_ids = player_state.get("discard_pile", [])
    
    cards_in_hand_details = []
    cards_played_details = [] 

    # --- Krok 0: Przygotuj dane do warunków ---
    
    # Zbuduj listę ID kart fremenów zagranych w tej rundzie (w discard_pile)
    played_fremen_card_ids = []
    for card_id in cards_played_ids:
        card_data = cards_db.get(card_id, {})
        # Sprawdzamy tagi "agent_symbols" LUB "type" (na wszelki wypadek)
        if "fremen" in card_data.get("agent_symbols", []):
            played_fremen_card_ids.append(card_id)
    
    # Sprawdź sojusz z Cesarzem (Uproszczenie: 4+ wpływu = sojusz. Pełna logika sojuszy to Krok 7)
    player_influence = player_state.get("influence", {})
    has_emperor_alliance = player_influence.get("emperor", 0) >= 4

    # --- Krok 1: Przetwórz karty W RĘCE (dają Perswazję i Siłę) ---
    for card_id in cards_in_hand_ids:
        card_data = cards_db.get(card_id)
        if not card_data: continue
            
        reveal_effect = card_data.get("reveal_effect", {})
        
        # --- Logika bazowa + warunkowa ---
        persuasion = reveal_effect.get("persuasion", 0)
        swords = reveal_effect.get("swords", 0)
        description = reveal_effect.get("possible actions", {}).get("description", "No effect.")
        
        # === POCZĄTEK NOWEJ LOGIKI WARUNKOWEJ ===
        
        # "Sietch Reverend Mother" (sietch_reverend_mother)
        if card_id == "sietch_reverend_mother":
            if len(played_fremen_card_ids) > 0:
                persuasion += 3
                # Bonus +1 Spice jest obsługiwany manualnie, tu liczymy tylko P/S
                description = f"BONUS AKTYWOWANY: +3 Perswazji (za zagraną kartę Fremenów)."

        # "Fedaykin Death Commando" (fedaykin_death_commando)
        elif card_id == "fedaykin_death_commando":
            if len(played_fremen_card_ids) > 0:
                swords += 3
                description = f"BONUS AKTYWOWANY: +3 Miecza (za zagraną kartę Fremenów)."

        # "Firm Grip" (firm_grip)
        elif card_id == "firm_grip":
            if has_emperor_alliance:
                persuasion += 4
                description = f"BONUS AKTYWOWANY: +4 Perswazji (za sojusz z Cesarzem)."

        # "Liet Kynes" (liet_kynes)
        elif card_id == "liet_kynes":
            # Ten efekt liczy karty Fremenów "w grze" (w ręce i zagrane)
            # 1. Liczymy zagrane (z Kroku 0)
            fremen_count = len(played_fremen_card_ids)
            # 2. Liczymy te w ręce (ale nie liczymy samej Liet Kynes)
            for hand_card_id in cards_in_hand_ids:
                if hand_card_id == "liet_kynes": continue
                hand_card_data = cards_db.get(hand_card_id, {})
                if "fremen" in hand_card_data.get("agent_symbols", []):
                    fremen_count += 1
            
            bonus_persuasion = fremen_count * 2
            if bonus_persuasion > 0:
                persuasion += bonus_persuasion
                description = f"BONUS AKTYWOWANY: +{bonus_persuasion} Perswazji (2 za każdą z {fremen_count} kart Fremenów)."
        
        # "Control the Spice" (control_the_spice) - Fremen Bond
        elif card_id == "control_the_spice":
            if len(played_fremen_card_ids) > 0:
                 # Bonus +1 Spice jest manualny
                 description = f"BONUS (MANUALNY): Zyskaj 1 Przyprawę (za zagraną kartę Fremenów)."
        
        # "Spice Hunter" (spice_hunter) - Fremen Bond
        elif card_id == "spice_hunter":
            if len(played_fremen_card_ids) > 0:
                 # Bonus +1 Spice jest manualny
                 description = f"BONUS (MANUALNY): Zyskaj 1 Przyprawę (za zagraną kartę Fremenów)."

        # Oznacz karty z manualną opcją (np. Gurney Halleck "You may pay...")
        elif "You may pay" in description or " or " in description.lower():
             description = f"[MANUAL ACTION NEEDED] {description}"
        
        # === KONIEC NOWEJ LOGIKI WARUNKOWEJ ===

        total_persuasion += persuasion
        base_swords += swords
        
        cards_in_hand_details.append({
            "id": card_id,
            "name": card_data.get("name", card_id),
            "persuasion": persuasion,
            "swords": swords,
            "description": description # Zaktualizowany opis
        })
    
    committed_troops = player_state.get("resources", {}).get("troops_in_conflict", 0)
    base_swords += (committed_troops * 2)
    
    return {
        "total_persuasion": total_persuasion,
        "base_swords": base_swords,
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
    
    # === NOWA POPRAWKA: Oblicz perswazję na żywo ===
    # Użyj funkcji, którą już mamy, aby pobrać Prawdziwą wartość
    live_stats = calculate_reveal_stats(player_state, cards_db)
    player_persuasion = live_stats.get("total_persuasion", 0)
    # === KONIEC POPRAWKI ===
    
    if player_persuasion < card_cost:
        return False, f"Player {player_name} does not have enough persuasion. Required: {card_cost}, Has: {player_persuasion}."

    # === POPRAWKA 2: Zapisz zaktualizowaną wartość z powrotem do JSON ===
    # Najpierw odejmij od prawdziwej wartości
    new_persuasion_total = player_persuasion - card_cost
    # A teraz zapisz tę nową, poprawną wartość w 'reveal_stats'
    if "reveal_stats" not in player_state:
        player_state["reveal_stats"] = {}
    player_state["reveal_stats"]["total_persuasion"] = new_persuasion_total
    # === KONIEC POPRAWKI ===
    
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

                temp_log_summary = []
                check_and_update_alliances(player_state, game_state, faction, temp_log_summary)
                if temp_log_summary:
                    if "round_history" not in game_state: game_state["round_history"] = []
                    game_state["round_history"].append({"summary": f"Alliance change for {player_name}: {', '.join(temp_log_summary)}"})
                # <<< KONIEC NOWEGO KODU >>>

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


def process_commit_troops(game_state, player_name, amount_to_commit_str):
    """
    Ustawia, ile wojsk gracz wysyła do konfliktu w Fazie Odkrycia.
    Pozwala graczowi zmienić zdanie i dostosować liczbę w dowolnym momencie.
    """
    player_state = game_state.get("players", {}).get(player_name)
    if not player_state:
        return False, f"Player {player_name} not found."
        
    try:
        amount_to_commit = int(amount_to_commit_str)
    except (ValueError, TypeError):
        return False, f"Invalid input: '{amount_to_commit_str}' is not a valid number."
        
    if amount_to_commit < 0:
        return False, "Cannot commit a negative number of troops."
        
    player_resources = player_state.get("resources", {})
    
    # Pobierz bieżące wojska
    current_garrison = player_resources.get("troops_garrison", 0)
    current_in_conflict = player_resources.get("troops_in_conflict", 0)
    
    # Oblicz sumę wszystkich wojsk gracza
    total_available_troops = current_garrison + current_in_conflict
    
    if amount_to_commit > total_available_troops:
        return False, f"Invalid amount: Player only has {total_available_troops} troops in total (garrison + conflict). Cannot commit {amount_to_commit}."
        
    # Ustaw nowe wartości
    player_resources["troops_in_conflict"] = amount_to_commit
    player_resources["troops_garrison"] = total_available_troops - amount_to_commit
    
    summary = f"Player {player_name} committed {amount_to_commit} troops to the conflict. (Garrison: {player_resources['troops_garrison']})"
    
    # Zapiszmy to też w historii
    if "round_history" not in game_state:
        game_state["round_history"] = []
    game_state["round_history"].append({"summary": summary})

    return True, summary


def perform_full_game_reset():
    """Kasuje game_stat.json i zastępuje go zawartością z game_stat.DEFAULT.json."""
    default_state = load_json_file(GAME_STATE_DEFAULT_FILE)
    if default_state is None:
        return False, f"Error: Default state file '{GAME_STATE_DEFAULT_FILE}' not found."
    
    leaders_db = load_json_file(LEADERS_DB_FILE)
    if leaders_db and "players" in default_state:
        print("Applying passive leader start bonuses...")
        for player_name, player_data in default_state["players"].items():
            leader_id = player_data.get("leader")
            if not leader_id:
                continue
                
            leader_data = leaders_db.get(leader_id, {})
            passive_ability = leader_data.get("ability_passive", {})
            
            # Specjalna obsługa dla "Fief of Arrakis" Rabbana
            if passive_ability.get("name") == "Fief of Arrakis":
                start_bonus = passive_ability.get("gain", [])
                player_resources = player_data.get("resources", {})
                
                for item in start_bonus:
                    resource = item.get("resource")
                    amount = item.get("amount", 0)
                    if resource in player_resources:
                        player_resources[resource] = player_resources.get(resource, 0) + amount
                        print(f"Applied start bonus to {player_name}: +{amount} {resource}")

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

            if "resources" in player_data:
                player_data["resources"]["troops_in_conflict"] = 0
            
            
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
    Ręcznie ustawia rękę gracza (np. AI).
    NIE MA LIMITU KART - pozwala to na dodawanie kart w trakcie tury (np. z efektu).
    """
    if not player_name:
        return False, "Player name not provided."
    player_state = game_state.get("players", {}).get(player_name)
    if not player_state:
        return False, f"Player {player_name} not found."
    
    # USUNIĘTO WALIDACJĘ 5 KART
    # if len(card_ids_list) != 5:
    #     return False, f"Invalid selection. You must select exactly 5 cards. You selected {len(card_ids_list)}."
        
    deck_pool = player_state.get("deck_pool", [])
    
    # Sprawdzamy, czy wszystkie podane karty istnieją w ogólnej puli gracza
    for card_id in card_ids_list:
        if card_id not in cards_db:
            return False, f"Invalid Card ID: {card_id} not found in database."
        if card_id not in deck_pool:
            card_name = cards_db.get(card_id, {}).get("name", card_id)
            return False, f"Invalid card: '{card_name}' is not in player {player_name}'s deck pool."
            
    player_state["hand"] = list(card_ids_list)
    
    # Logika pomocnicza: ustawia resztę kart jako 'draw_deck' dla jasności
    draw_deck_list = list(deck_pool) 
    for card in card_ids_list:
        if card in draw_deck_list:
            draw_deck_list.remove(card)
            
    player_state["draw_deck"] = draw_deck_list
    player_state["discard_pile"] = [] # Czyścimy też discard dla porządku
    
    # Zmieniona wiadomość sukcesu
    return True, f"Success! Set {len(card_ids_list)} card(s) for {player_name}."


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

            # <<< START NOWEGO KODU >>>
            elif r_type == "control":
                location_name = reward.get("control")
                if "control" not in player_state: # Dodaj listę, jeśli nie istnieje
                    player_state["control"] = []
                if location_name and location_name not in player_state["control"]:
                    player_state["control"].append(location_name)
                    summary_parts.append(f"gained control of {location_name}")
                
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
def process_conflict_resolve(game_state, first_place_list, second_place_list, third_place_list):
    """Zapisuje wyniki konfliktu i AUTOMATYCZNIE przyznaje nagrody.
    Akceptuje listy graczy dla każdego miejsca."""
    
    conflict_card = game_state.get("current_conflict_card", {})
    conflict_name = conflict_card.get("name", "Conflict")
    rewards_map = conflict_card.get("rewards", {})
    
    summaries = []
    
    # Ważne: Sprawdzamy czy lista zwycięzców nie jest pusta ORAZ czy nagroda dla tego miejsca istnieje
    if first_place_list and "1" in rewards_map:
        for player_name in first_place_list:
            reward_details = apply_rewards(game_state, player_name, rewards_map["1"])
            summaries.append(f"1st: {player_name} ({reward_details})")
        
    if second_place_list and "2" in rewards_map:
        for player_name in second_place_list:
            reward_details = apply_rewards(game_state, player_name, rewards_map["2"])
            summaries.append(f"2nd: {player_name} ({reward_details})")

    if third_place_list and "3" in rewards_map:
        for player_name in third_place_list:
            reward_details = apply_rewards(game_state, player_name, rewards_map["3"])
            summaries.append(f"3rd: {player_name} ({reward_details})")
    
    if not summaries:
        if not any([first_place_list, second_place_list, third_place_list]):
            full_summary = f"Conflict Resolved ({conflict_name}): No winners."
        else:
            # Ktoś wygrał, ale nie było nagród dla przyznanych miejsc
            f_winners = ', '.join(first_place_list) if first_place_list else 'None'
            s_winners = ', '.join(second_place_list) if second_place_list else 'None'
            t_winners = ', '.join(third_place_list) if third_place_list else 'None'
            full_summary = f"Conflict Resolved ({conflict_name}): 1st: {f_winners}, 2nd: {s_winners}, 3rd: {t_winners} (No applicable rewards found for these tiers)."
    else:
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
    
def manual_add_intrigue(game_state, player_name, intrigue_id, intrigues_db):
    """Ręcznie dodaje konkretną kartę intrygi do ręki gracza."""
    player_state = game_state.get("players", {}).get(player_name)
    if not player_state:
        return False, f"Player {player_name} not found."
        
    if not intrigue_id or intrigue_id not in intrigues_db:
        return False, f"Intrigue ID '{intrigue_id}' not found in database."
        
    if "intrigue_hand" not in player_state:
        player_state["intrigue_hand"] = []
        
    player_state["intrigue_hand"].append(intrigue_id)
    card_name = intrigues_db[intrigue_id].get("name", intrigue_id)
    
    summary = f"Player {player_name} manually added intrigue: '{card_name}'."
    if "round_history" not in game_state:
        game_state["round_history"] = []
    game_state["round_history"].append({"summary": summary})
    
    return True, summary


def _safe_add_resource(player_dict, key, value_str):
    """
    Bezpiecznie próbuje dodać wartość (dodatnią lub ujemną) do klucza w słowniku.
    Zwraca opis zmiany lub None jeśli błąd.
    """
    if not value_str: # Jeśli pole jest puste
        return None
    
    try:
        value = int(value_str)
        if value == 0:
            return None
            
        current_value = player_dict.get(key, 0)
        # Zapobiegaj ujemnym zasobom (ale pozwól na ujemne wpływy, jeśli trzeba)
        if (current_value + value) < 0 and key not in ["emperor", "guild", "fremen", "bene_gesserit"]:
             player_dict[key] = 0 # Zeruj zamiast zejść poniżej 0
             change_desc = f"zmieniono {key} o {value} (wynik {current_value + value}, ustawiono na 0)"
        else:
            player_dict[key] = current_value + value
            change_desc = f"zmieniono {key} o {value} (nowa wartość: {player_dict[key]})"
        
        return change_desc
        
    except ValueError:
        return f"błędna wartość dla {key} ('{value_str}')"
    except Exception as e:
        return f"błąd przy {key}: {e}"


def process_manual_override(game_state, player_name, form_data):
    """
    Przetwarza ręczną korektę stanu gry dla wybranego gracza.
    """
    player_state = game_state.get("players", {}).get(player_name)
    if not player_state:
        return False, f"Nie znaleziono gracza {player_name}."

    if "resources" not in player_state:
        player_state["resources"] = {}
    if "influence" not in player_state:
        player_state["influence"] = {}
        
    player_res = player_state["resources"]
    player_inf = player_state["influence"]
    
    changes_log = []

    # 1. Zmiana Zasobów
    res_keys = ["solari", "Spice", "water", "troops_garrison", "troops_in_conflict"]
    for key in res_keys:
        log = _safe_add_resource(player_res, key, form_data.get(key))
        if log:
            changes_log.append(log)

    # 2. Zmiana Wpływów
    inf_keys = {"faction_emperor": "emperor", "faction_guild": "guild", "faction_fremen": "fremen", "faction_bene_gesserit": "bene_gesserit"}
    for form_key, state_key in inf_keys.items():
        log = _safe_add_resource(player_inf, state_key, form_data.get(form_key))
        if log:
            changes_log.append(log)

    if not changes_log:
        return True, "Nie wprowadzono żadnych zmian."

    summary = ", ".join(changes_log)
    
    # Zapisz również w historii głównej
    if "round_history" not in game_state:
        game_state["round_history"] = []
    game_state["round_history"].append({"summary": f"[KOREKTA] {player_name}: {summary}"})

    return True, summary