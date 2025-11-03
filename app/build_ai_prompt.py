# app/build_ai_prompt.py
import json
import copy # Needed for deep copy

# Wczytujemy TYLKO definicje kart, aby móc policzyć efekty 'reveal'
from game_manager import load_json_file, CARDS_DB_FILE 

# Stała przeniesiona z game_manager, aby ten plik był bardziej samodzielny
AI_PLAYER_NAME = 'Peter'


def generate_ai_prompt(game_state_data):
    """
    Generuje uproszczony prompt dla AI, zawierający tylko stan gry
    oraz podsumowanie publicznych efektów 'reveal' przeciwników.
    
    Args:
        game_state_data (dict): The current state of the game.
        
    Returns:
        str: The final prompt text.
    """
    if not game_state_data:
        return "CRITICAL ERROR: Cannot load game state."
        
    # Wczytaj bazę kart - jest potrzebna TYLKO do policzenia statystyk 'reveal'
    cards_db = load_json_file(CARDS_DB_FILE)
    if not cards_db:
        return "CRITICAL ERROR: Cannot load cards_db for reveal calculation."

    # Create a DEEP copy to safely delete keys
    game_state = copy.deepcopy(game_state_data)
    
    prompt_lines = []
    prompt_lines.append(f"Jesteś graczem {AI_PLAYER_NAME}. Przeanalizuj stan gry i podejmij decyzję.")
    prompt_lines.append(f"Obecna runda: {game_state.get('round', 1)}, Faza: {game_state.get('current_phase', 'Unknown')}.")

    # --- Historia Ruchów ---
    prompt_lines.append("\n### Historia Ruchów (ta runda) ###")
    history_to_display = game_state.pop("round_history", []) 
    if history_to_display :
        for move in history_to_display:
            prompt_lines.append(f"- {move['summary']}")
    else:
        prompt_lines.append("(Brak ruchów)")
    
    
    # --- NOWA SEKCJA: Efekty Odkrycia Przeciwników ---
    # To jest kluczowe dla AI: widzi, co przeciwnicy JUŻ zagrali
    prompt_lines.append("\n### Publiczne Efekty Odkrycia Przeciwników ###")
    prompt_lines.append("(Oparte na kartach, które już zagrali w tej rundzie)")
    
    if "players" in game_state:
        for player_name, player_data in game_state["players"].items():
            if player_name != AI_PLAYER_NAME:
                
                opponent_swords = 0
                opponent_persuasion = 0
                
                # Przelicz 'reveal' tylko z kart ZAGRANYCH (discard_pile)
                for card_id in player_data.get("discard_pile", []):
                    card_data = cards_db.get(card_id)
                    if card_data:
                        reveal_effect = card_data.get("reveal_effect", {})
                        opponent_persuasion += reveal_effect.get("persuasion", 0)
                        opponent_swords += reveal_effect.get("swords", 0)

                # AI widzi, ile kart przeciwnik ma jeszcze na ręce
                hand_size = len(player_data.get("hand", [])) 
                
                prompt_lines.append(
                    f"- **{player_name}**: "
                    f"ZAGRAŁ: {opponent_persuasion} Perswazji, {opponent_swords} Siły. "
                    f"(Ma jeszcze {hand_size} kart na ręce)."
                )

    # --- Ukrywanie danych (tak jak było) ---
    if "players" in game_state:
        for player_name, player_data in game_state["players"].items():
            
            if player_name == AI_PLAYER_NAME:
                # Gracz AI widzi swoją rękę i discard
                player_data.pop("draw_deck", None)
            else:
                # Inny gracz - ukryj wszystko, czego AI nie powinno widzieć
                player_data.pop("hand", None)
                player_data.pop("discard_pile", None)
                player_data.pop("deck_pool", None)
                player_data.pop("draw_deck", None)
                player_data.pop("intrigue_hand", None)
                
    # --- Stan Gry (JSON) ---
    prompt_lines.append(f"\n### Aktualny Stan Gry (Source of Truth) ###")
    prompt_lines.append("Twoja ręka, zasoby i intrygi są widoczne poniżej.")
        
    game_state_json_string = json.dumps(game_state, indent=2, ensure_ascii=False)
    
    final_prompt = "\n".join(prompt_lines)
    final_prompt += f"\n```json\n{game_state_json_string}\n```"
    
    final_prompt += "\nPrzeanalizuj swój ruch."

    return final_prompt