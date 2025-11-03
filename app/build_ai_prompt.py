# app/build_ai_prompt.py
import json
import copy # Needed for deep copy

AI_PLAYER_NAME = 'Peter'


def generate_ai_prompt(game_state_data):
    """
    Generates the AI prompt text from the game state dictionary.
    
    Args:
        game_state_data (dict): The current state of the game.
        
    Returns:
        str: The final prompt text.
    """
    if not game_state_data:
        return "CRITICAL ERROR: Cannot load game state."

    # Create a DEEP copy to safely delete keys
    game_state = copy.deepcopy(game_state_data)
    
    prompt_lines = []
    prompt_lines.append(f"Attention, it's your turn, {AI_PLAYER_NAME}! You are a player in a board game. Your task is to make the best possible move based on the current game state.\n")
    prompt_lines.append("The game state is as follows:\n")

    # Collecting moves from history (logic unchanged)
    players_moves = {}
    history_to_display = game_state.pop("round_history", []) # Use pop to get history and remove it from the JSON state

    if history_to_display :
        for move in history_to_display:
            player = move["player"]
            summary = move["summary"]
            if player not in players_moves:
                players_moves[player] = []
            players_moves[player].append(move["summary"])
    
    for player, moves in players_moves.items():
        prompt_lines.append(f"Player {player}'s moves:\n")
        for i, move_summary in enumerate(moves, 1):
            prompt_lines.append(f"    {i}. {move_summary}")
    
    
    # --- NOWA, POPRAWIONA LOGIKA UKRYWANIA DANYCH ---
    # Ukryj prywatne dane innych graczy przed serializacją JSON
    if "players" in game_state:
        for player_name, player_data in game_state["players"].items():
            
            if player_name == AI_PLAYER_NAME:
                # To jest gracz AI
                # Widzi swoją rękę (hand), stos odrzuconych (discard_pile) i kolekcję (deck_pool)
                # Ukrywamy tylko talię dobierania (draw_deck)
                player_data.pop("draw_deck", None)
            else:
                # To jest inny gracz
                # AI nie powinno widzieć żadnych jego prywatnych pól kart
                player_data.pop("hand", None)
                player_data.pop("discard_pile", None)
                player_data.pop("deck_pool", None)
                player_data.pop("draw_deck", None)
                
    # --- KONIEC NOWEJ LOGIKI ---

    prompt_lines.append(f"\nNow it's your move ({AI_PLAYER_NAME}).")
    prompt_lines.append(f"Current phase: {game_state.get('current_phase', 'Unknown')}.")
    prompt_lines.append("Analyze the JSON state below. Your hand, discard pile, and card pool are visible only to you.")
    prompt_lines.append("\n### GAME STATE (Source of Truth) ###")
        
    # Format JSON
    game_state_json_string = json.dumps(game_state, indent=2, ensure_ascii=False)
    
    # --- Combine everything ---
    final_prompt = "\n".join(prompt_lines)
    final_prompt += f"\n```json\n{game_state_json_string}\n```"

    return final_prompt