# app/build_ai_prompt.py
import json
import copy # Needed for deep copy

# NOWY IMPORT:
from game_manager import get_card_persuasion_cost 

AI_PLAYER_NAME = 'Peter'


def generate_ai_prompt(game_state_data, cards_db):
    """
    Generuje uproszczony prompt dla AI, zawierający tylko stan gry
    oraz podsumowanie publicznych efektów 'reveal' przeciwników.
    
    Args:
        game_state_data (dict): The current state of the game.
        cards_db (dict): The database of all cards.
        
    Returns:
        str: The final prompt text.
    """
    if not game_state_data:
        return "CRITICAL ERROR: Cannot load game state."
        
    if not cards_db:
        return "CRITICAL ERROR: Cards DB was not provided."

    game_state = copy.deepcopy(game_state_data)
    current_phase = game_state.get('current_phase', 'Unknown')
    
    prompt_lines = []
    prompt_lines.append(f"Jesteś graczem {AI_PLAYER_NAME}. Przeanalizuj stan gry i podejmij decyzję.")
    prompt_lines.append(f"Obecna runda: {game_state.get('round', 1)}, Faza: {current_phase}.")

    prompt_lines.append("\n### Historia Ruchów (ta runda) ###")
    history_to_display = game_state.pop("round_history", []) 
    if history_to_display :
        for move in history_to_display:
            prompt_lines.append(f"- {move.get('summary', 'Unknown history item')}")
    else:
        prompt_lines.append("(Brak ruchów)")
    
    
    if current_phase == "AGENT_TURN":
        prompt_lines.append("\n### Faza Akcji Agentów ###")
        prompt_lines.append("\n### Publiczne Efekty Odkrycia Przeciwników ###")
        prompt_lines.append("(Oparte na kartach, które już zagrali w tej rundzie)")
        
        if "players" in game_state:
            for player_name, player_data in game_state["players"].items():
                if player_name != AI_PLAYER_NAME:
                    opponent_swords = 0
                    opponent_persuasion = 0
                    
                    for card_id in player_data.get("discard_pile", []):
                        card_data = cards_db.get(card_id)
                        if card_data:
                            reveal_effect = card_data.get("reveal_effect", {})
                            opponent_persuasion += reveal_effect.get("persuasion", 0)
                            opponent_swords += reveal_effect.get("swords", 0)

                    hand_size = len(player_data.get("hand", [])) 
                    
                    prompt_lines.append(
                        f"- **{player_name}**: "
                        f"ZAGRAŁ: {opponent_persuasion} Perswazji, {opponent_swords} Siły. "
                        f"(Ma jeszcze {hand_size} kart na ręce)."
                    )
        
        prompt_lines.append(f"\n### Aktualny Stan Gry (Source of Truth) ###")
        prompt_lines.append("Twoja ręka, zasoby i intrygi są widoczne poniżej.")
        prompt_lines.append("Przeanalizuj swój ruch agenta (karta + lokacja) lub spasowanie.")

    elif current_phase == "REVEAL":
        prompt_lines.append("\n### Faza Odkrycia (Kupowanie Kart) ###")
        
        ai_player_data = game_state.get("players", {}).get(AI_PLAYER_NAME, {})
        ai_stats = ai_player_data.get("reveal_stats", {})
        my_persuasion = ai_stats.get("total_persuasion", 0)
        my_swords = ai_stats.get("total_swords", 0)
        
        prompt_lines.append(f"Posiadasz: {my_persuasion} Perswazji (do kupowania).")
        prompt_lines.append(f"Posiadasz: {my_swords} Siły (do walki).")

        prompt_lines.append("\n### Dostępne Karty (Imperium Row) ###")
        market_ids = game_state.get("imperium_row", [])
        if market_ids:
            for card_id in market_ids:
                card_data = cards_db.get(card_id, {})
                
                # --- ZMIANA: Użyj nowej funkcji do pobrania kosztu ---
                card_cost = get_card_persuasion_cost(card_data)
                cost_display = f"Koszt: {card_cost}" if card_cost != 999 else "Koszt: N/A"
                
                prompt_lines.append(f"- ID: {card_id}, Nazwa: {card_data.get('name')}, {cost_display}")
        else:
            prompt_lines.append("(Rynek jest pusty)")

        prompt_lines.append(f"\n### Aktualny Stan Gry (Source of Truth) ###")
        prompt_lines.append("Przeanalizuj, które karty kupić za posiadaną Perswazję. Wymień ID kart, które chcesz kupić.")


    if "players" in game_state:
        for player_name, player_data in game_state["players"].items():
            if player_name == AI_PLAYER_NAME:
                player_data.pop("draw_deck", None)
            else:
                player_data.pop("hand", None)
                player_data.pop("deck_pool", None)
                player_data.pop("draw_deck", None)
                player_data.pop("intrigue_hand", None)
                
    game_state_json_string = json.dumps(game_state, indent=2, ensure_ascii=False)
    
    final_prompt = "\n".join(prompt_lines)
    final_prompt += f"\n```json\n{game_state_json_string}\n```"
    
    return final_prompt 