# app/build_ai_prompt.py
import json
import copy # Needed for deep copy

from game_manager import get_card_persuasion_cost, AI_PLAYER_NAME 

def generate_ai_prompt(game_state_data, cards_db):
    """
    Generates a simplified prompt for the AI, containing only the game state
    and a summary of opponents' public reveal effects.
    
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
    prompt_lines.append(f"You are player {AI_PLAYER_NAME}. Analyze the game state and make your decision.")
    prompt_lines.append(f"Current round: {game_state.get('round', 1)}, Phase: {current_phase}.")

    prompt_lines.append("\n### Current Conflict Rewards ###")
    conflict_card = game_state.get("current_conflict_card", {})
    
    conflict_name = conflict_card.get("name", "N/A")
    conflict_rewards = conflict_card.get("rewards_text", []) # Używamy rewards_text
    
    prompt_lines.append(f"Card: **{conflict_name}**")
    if conflict_rewards:
        for reward in conflict_rewards:
            prompt_lines.append(f"- {reward}")
    else:
        prompt_lines.append("(No conflict rewards set for this round)")

    prompt_lines.append("\n### Move History (This Round) ###")
    history_to_display = game_state.pop("round_history", []) 
    if history_to_display :
        for move in history_to_display:
            prompt_lines.append(f"- {move.get('summary', 'Unknown history item')}")
    else:
        prompt_lines.append("(No moves this round)")
    
    
    if current_phase == "AGENT_TURN":
        prompt_lines.append("\n### Agent Turn Phase ###")
        prompt_lines.append("\n### Opponents' Public Reveal Effects ###")
        prompt_lines.append("(Based on cards they have already played this round)")
        
        if "players" in game_state:
            for player_name, player_data in game_state["players"].items():
                if player_name != AI_PLAYER_NAME:
                    opponent_swords = 0
                    opponent_persuasion = 0
                    
                    for card_id in player_data.get("discard_pile", []):
                        card_data = cards_db.get(card_id)
                        if card_data:
                            reveal_effect = card_data.get("reveal_effect", {})
                            opponent_persuasion += 0 # Zagrane karty nie dają perswazji
                            opponent_swords += reveal_effect.get("swords", 0)
                            
                    agents_left = player_data.get("agents_total", 2) - player_data.get("agents_placed", 0)
                    has_passed = player_data.get("has_passed", False)
                    
                    if has_passed:
                         hand_size_desc = "PASSED"
                    elif agents_left > 0:
                         hand_size_desc = f"({agents_left} agents left to play)"
                    else:
                         hand_size_desc = "(No agents left)"
                    
                    prompt_lines.append(
                        f"- **{player_name}**: "
                        f"PLAYED: {opponent_persuasion} Persuasion, {opponent_swords} Swords. "
                        f"{hand_size_desc}"
                    )
        
        prompt_lines.append(f"\n### Current Game State (Source of Truth) ###")
        prompt_lines.append("Your hand, resources, and intrigues are visible below.")
        prompt_lines.append("Analyze your agent move (card + location) or decide to pass.")

    elif current_phase == "REVEAL":
        prompt_lines.append("\n### Reveal Phase (Buying Cards) ###")
        
        prompt_lines.append("\n### Reveal Stats (All Players) ###")
        prompt_lines.append("This is public information, crucial for making buying decisions.")
        
        all_player_stats = {}
        ai_persuasion = 0
        
        for player_name, player_data in game_state.get("players", {}).items():
            stats = player_data.get("reveal_stats", {})
            persuasion = stats.get("total_persuasion", 0)
            
            base_swords = stats.get("base_swords", 0)
            bonus_swords = player_data.get("active_effects", {}).get("fight_bonus_swords", 0)
            swords = base_swords + bonus_swords 
            all_player_stats[player_name] = f"Persuasion: {persuasion}, Swords: {swords}"
            if player_name == AI_PLAYER_NAME:
                ai_persuasion = persuasion
        
        for player_name, stats_str in sorted(all_player_stats.items()):
            if player_name == AI_PLAYER_NAME:
                prompt_lines.append(f"- **{player_name} (You)**: {stats_str}")
            else:
                prompt_lines.append(f"- {player_name}: {stats_str}")
        
        prompt_lines.append(f"\nYou have: {ai_persuasion} Persuasion (for buying).")

        prompt_lines.append("\n### Available Cards (Imperium Row) ###")
        market_ids = game_state.get("imperium_row", [])
        if market_ids:
            for card_id in market_ids:
                card_data = cards_db.get(card_id, {})
                
                card_cost = get_card_persuasion_cost(card_data)
                cost_display = f"Cost: {card_cost}" if card_cost != 999 else "Cost: N/A"
                
                prompt_lines.append(f"- ID: {card_id}, Name: {card_data.get('name')}, {cost_display}")
        else:
            prompt_lines.append("(Market is empty)")

        prompt_lines.append(f"\n### Current Game State (Source of Truth) ###")
        prompt_lines.append("Analyze which cards to buy with your Persuasion. List the IDs of the cards you want to buy.")


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
    
    # === ZJEDNOCZENIE PROMPTU ===
    # Łączymy instrukcje i JSON z powrotem w jeden ciąg
    final_prompt = "\n".join(prompt_lines)
    final_prompt += f"\n```json\n{game_state_json_string}\n```"
    
    return final_prompt