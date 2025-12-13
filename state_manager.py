"""
state_manager.py - Matchmaking State Persistence
Saves and restores queue/match state across bot restarts
"""

MODULE_VERSION = "1.2.0"

import json
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

STATE_FILE = 'matchmakingstate.json'

# EST timezone
EST = timezone(timedelta(hours=-5))

def log_state(message: str):
    """Log state manager actions (EST timezone)"""
    timestamp = datetime.now(EST).strftime('%Y-%m-%d %H:%M:%S EST')
    print(f"[STATE] [{timestamp}] {message}")

def save_state():
    """Save current matchmaking state to JSON"""
    from searchmatchmaking import queue_state
    
    state = {
        "saved_at": datetime.now().isoformat(),
        "queue": queue_state.queue,
        "queue_join_times": {
            str(uid): time.isoformat() 
            for uid, time in queue_state.queue_join_times.items()
        },
        "test_mode": queue_state.test_mode,
        "test_team": queue_state.test_team,
        "current_series": None
    }
    
    # Save series state if active
    if queue_state.current_series:
        series = queue_state.current_series
        state["current_series"] = {
            "red_team": series.red_team,
            "blue_team": series.blue_team,
            "games": series.games,
            "current_game": series.current_game,
            "test_mode": series.test_mode,
            "match_number": series.match_number,
            "series_number": series.series_number,
            "red_vc_id": series.red_vc_id,
            "blue_vc_id": series.blue_vc_id,
            "text_channel_id": getattr(series, 'text_channel_id', None),
            "swap_history": getattr(series, 'swap_history', []),
            "series_message_id": series.series_message.id if series.series_message else None,
            "series_message_channel_id": series.series_message.channel.id if series.series_message else None,
            "general_message_id": series.general_message.id if hasattr(series, 'general_message') and series.general_message else None
        }
        
        # Save counters
        from ingame import Series
        state["match_counter"] = Series.match_counter
        state["test_counter"] = Series.test_counter
    
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)
        log_state(f"State saved - Queue: {len(queue_state.queue)}, Series: {'Active' if queue_state.current_series else 'None'}")
    except Exception as e:
        log_state(f"Failed to save state: {e}")

def load_state() -> Optional[dict]:
    """Load saved state from JSON"""
    if not os.path.exists(STATE_FILE):
        log_state("No saved state found")
        return None
    
    try:
        with open(STATE_FILE, 'r') as f:
            state = json.load(f)
        log_state(f"State loaded from {state.get('saved_at', 'unknown')}")
        return state
    except Exception as e:
        log_state(f"Failed to load state: {e}")
        return None

async def restore_state(bot) -> bool:
    """Restore matchmaking state after bot restart"""
    from searchmatchmaking import queue_state
    from ingame import Series, SeriesView, update_general_chat_embed, GENERAL_CHANNEL_ID
    
    state = load_state()
    if not state:
        return False
    
    try:
        # Restore queue
        queue_state.queue = state.get("queue", [])
        queue_state.test_mode = state.get("test_mode", False)
        queue_state.test_team = state.get("test_team")
        
        # Restore join times
        queue_join_times = state.get("queue_join_times", {})
        for uid_str, time_str in queue_join_times.items():
            queue_state.queue_join_times[int(uid_str)] = datetime.fromisoformat(time_str)
        
        log_state(f"Restored queue: {len(queue_state.queue)} players")
        
        # Restore series if active
        series_data = state.get("current_series")
        if series_data:
            # Restore counters first
            Series.match_counter = state.get("match_counter", 0)
            Series.test_counter = state.get("test_counter", 0)
            
            # Create series without incrementing counter
            series = Series.__new__(Series)
            series.red_team = series_data["red_team"]
            series.blue_team = series_data["blue_team"]
            series.games = series_data["games"]
            series.current_game = series_data["current_game"]
            series.test_mode = series_data["test_mode"]
            series.match_number = series_data["match_number"]
            series.series_number = series_data["series_number"]
            series.red_vc_id = series_data["red_vc_id"]
            series.blue_vc_id = series_data["blue_vc_id"]
            series.text_channel_id = series_data.get("text_channel_id")
            series.swap_history = series_data.get("swap_history", [])
            series.votes = {}
            series.end_series_votes = set()
            series.series_message = None
            series.general_message = None
            
            queue_state.current_series = series
            
            log_state(f"Restored series: {series.series_number} - Game {series.current_game}")
            
            # Try to recover message references
            guild = bot.guilds[0] if bot.guilds else None
            if guild:
                # Recover series message
                msg_channel_id = series_data.get("series_message_channel_id")
                msg_id = series_data.get("series_message_id")
                if msg_channel_id and msg_id:
                    try:
                        channel = guild.get_channel(msg_channel_id)
                        if channel:
                            series.series_message = await channel.fetch_message(msg_id)
                            log_state("Recovered series message reference")
                    except:
                        log_state("Could not recover series message - will create new one")
                
                # Update general chat embed
                try:
                    await update_general_chat_embed(guild, series)
                    log_state("Updated general chat embed")
                except Exception as e:
                    log_state(f"Failed to update general chat: {e}")
        
        log_state("State restoration complete")
        return True
    
    except Exception as e:
        log_state(f"Failed to restore state: {e}")
        return False

def clear_state():
    """Clear saved state file"""
    if os.path.exists(STATE_FILE):
        try:
            os.remove(STATE_FILE)
            log_state("State file cleared")
        except Exception as e:
            log_state(f"Failed to clear state: {e}")

def has_saved_state() -> bool:
    """Check if there's a saved state"""
    return os.path.exists(STATE_FILE)
