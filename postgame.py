# postgame.py - Postgame Processing, Stats Recording, and Cleanup

MODULE_VERSION = "1.4.0"

import discord
from discord.ui import View, Button
from typing import List
from datetime import datetime, timezone, timedelta
import json
import os

# Will be imported from bot.py
POSTGAME_LOBBY_ID = None
QUEUE_CHANNEL_ID = None
RED_TEAM_EMOJI_ID = None
BLUE_TEAM_EMOJI_ID = None

# Active match file
ACTIVE_MATCH_FILE = 'activematch.json'

# Timezone for consistent logging (EST = UTC-5)
EST = timezone(timedelta(hours=-5))
TIMEZONE = EST
TIMEZONE_NAME = "EST"


def get_est_now():
    """Get current time in EST"""
    return datetime.now(TIMEZONE)


# Alias for backwards compatibility
get_utc_now = get_est_now


def format_timestamp(dt: datetime) -> dict:
    """Format a datetime with timezone info for JSON storage"""
    if dt is None:
        return {"iso": None, "display": None, "timezone": TIMEZONE_NAME}

    # Ensure timezone aware
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TIMEZONE)

    return {
        "iso": dt.isoformat(),
        "display": dt.strftime('%Y-%m-%d %H:%M:%S'),
        "timezone": TIMEZONE_NAME
    }


def load_active_matches() -> dict:
    """Load active matches from activematch.json"""
    if os.path.exists(ACTIVE_MATCH_FILE):
        try:
            with open(ACTIVE_MATCH_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {"timezone": TIMEZONE_NAME, "active_matches": []}


def save_active_matches(data: dict):
    """Save active matches to activematch.json"""
    with open(ACTIVE_MATCH_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def add_to_active_matches(series):
    """Add a series to activematch.json when it starts"""
    match_type = "TEST" if series.test_mode else "RANKED"
    start_time = get_utc_now()

    # Update series start_time to use UTC
    series.start_time = start_time

    active_entry = {
        "type": "SERIES",
        "match_type": match_type,
        "series_label": series.series_number,
        "match_id": series.match_number,
        "start_time": format_timestamp(start_time),
        "end_time": format_timestamp(None),
        "result": "IN_PROGRESS",
        "teams": {
            "red": {
                "players": series.red_team[:],
                "voice_channel_id": getattr(series, 'red_vc_id', None)
            },
            "blue": {
                "players": series.blue_team[:],
                "voice_channel_id": getattr(series, 'blue_vc_id', None)
            }
        },
        "text_channel_id": getattr(series, 'text_channel_id', None),
        "games": []
    }

    data = load_active_matches()
    data["active_matches"].append(active_entry)
    save_active_matches(data)

    log_action(f"Added {match_type} match {series.series_number} to {ACTIVE_MATCH_FILE}")


def update_active_match_games(series):
    """Update the games list for an active match"""
    data = load_active_matches()

    for match in data["active_matches"]:
        if match.get("match_id") == series.match_number:
            match["games"] = series.games[:]
            break

    save_active_matches(data)


def remove_from_active_matches(series) -> dict:
    """Remove a series from activematch.json and return its data"""
    data = load_active_matches()

    removed_match = None
    new_active = []

    for match in data["active_matches"]:
        if match.get("match_id") == series.match_number:
            removed_match = match
        else:
            new_active.append(match)

    data["active_matches"] = new_active
    save_active_matches(data)

    if removed_match:
        log_action(f"Removed match {series.series_number} from {ACTIVE_MATCH_FILE}")

    return removed_match

def log_action(message: str):
    """Log actions"""
    from searchmatchmaking import log_action as queue_log
    queue_log(message)

def save_match_history(series, winner: str):
    """Save match results to MLG4v4.json with comprehensive data"""
    match_type = "TEST" if series.test_mode else "RANKED"

    # Set end time with UTC
    end_time = get_utc_now()
    series.end_time = end_time

    # Remove from activematch.json
    remove_from_active_matches(series)

    # Calculate final scores
    red_wins = series.games.count('RED')
    blue_wins = series.games.count('BLUE')

    # Build game-by-game breakdown with map/gametype data if available
    game_breakdown = []
    gamestats = load_gamestats()
    match_key = f"match_{series.match_number}"

    for i, game_winner in enumerate(series.games, 1):
        game_data = {
            "game_number": i,
            "winner": game_winner,
            "loser": "BLUE" if game_winner == "RED" else "RED"
        }

        # Add map/gametype if available from gamestats
        if match_key in gamestats:
            game_key = f"game_{i}"
            if game_key in gamestats[match_key]:
                game_data["map"] = gamestats[match_key][game_key].get("map")
                game_data["gametype"] = gamestats[match_key][game_key].get("gametype")

        game_breakdown.append(game_data)

    # Create match entry with start_time and end_time (UTC timezone)
    match_entry = {
        "type": "SERIES",
        "match_type": match_type,
        "series_label": series.series_number,
        "match_id": series.match_number,
        "start_time": format_timestamp(series.start_time),
        "end_time": format_timestamp(end_time),
        "timezone": TIMEZONE_NAME,
        "winner": winner,
        "final_score": {
            "red": red_wins,
            "blue": blue_wins
        },
        "teams_final": {
            "red": {
                "players": series.red_team[:],  # Final team composition
                "voice_channel_id": getattr(series, 'red_vc_id', None)
            },
            "blue": {
                "players": series.blue_team[:],  # Final team composition
                "voice_channel_id": getattr(series, 'blue_vc_id', None)
            }
        },
        "games": game_breakdown,
        "total_games_played": len(series.games),
        "stats_recorded": not series.test_mode,
        "swap_history": getattr(series, 'swap_history', [])
    }

    # Save to different files based on match type
    if match_type == "RANKED":
        history_file = 'MLG4v4.json'
    else:
        history_file = 'testMLG4v4.json'

    # Load existing history or create new
    if os.path.exists(history_file):
        try:
            with open(history_file, 'r') as f:
                history = json.load(f)
        except:
            if match_type == "RANKED":
                history = {"total_ranked_matches": 0, "matches": [], "timezone": TIMEZONE_NAME}
            else:
                history = {"total_test_matches": 0, "matches": [], "timezone": TIMEZONE_NAME}
    else:
        if match_type == "RANKED":
            history = {"total_ranked_matches": 0, "matches": [], "timezone": TIMEZONE_NAME}
        else:
            history = {"total_test_matches": 0, "matches": [], "timezone": TIMEZONE_NAME}

    # Ensure timezone is set
    history["timezone"] = TIMEZONE_NAME

    # Update counters
    if match_type == "RANKED":
        history["total_ranked_matches"] = history.get("total_ranked_matches", 0) + 1
    else:
        history["total_test_matches"] = history.get("total_test_matches", 0) + 1

    # Add new match to completed matches
    history["matches"].append(match_entry)

    # Save back to file
    with open(history_file, 'w') as f:
        json.dump(history, f, indent=2)

    log_action(f"Saved {match_type} match {series.series_number} to {history_file} (UTC)")


def save_active_match(series):
    """Save match to activematch.json when series starts"""
    add_to_active_matches(series)


def load_gamestats():
    """Load gamestats.json if available"""
    import json
    import os
    
    gamestats_file = "gamestats.json"
    if os.path.exists(gamestats_file):
        try:
            with open(gamestats_file, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

async def record_game_winner(series_view, winner: str, channel: discord.TextChannel):
    """Record game winner and update series"""
    series = series_view.series
    
    series.games.append(winner)
    series.votes.clear()
    series_view.game_voters.clear()
    series.current_game += 1
    
    game_number = len(series.games)
    log_action(f"Game {game_number} won by {winner} in Match #{series.match_number}")

    # Log individual game result immediately
    log_individual_game(series, game_number, winner)

    # Update activematch.json with game results
    update_active_match_games(series)

    # Save state
    try:
        import state_manager
        state_manager.save_state()
    except:
        pass
    
    # Record stats if not test mode
    if not series.test_mode:
        import STATSRANKS
        
        # Determine winners and losers
        if winner == 'RED':
            game_winners = series.red_team
            game_losers = series.blue_team
        else:
            game_winners = series.blue_team
            game_losers = series.red_team
        
        # Record game results (not series end)
        STATSRANKS.record_match_results(game_winners, game_losers, is_series_end=False)
        
        # Refresh ranks for all players after each game
        all_players = series.red_team + series.blue_team
        await STATSRANKS.refresh_all_ranks(channel.guild, all_players)
        log_action(f"✅ Stats recorded and ranks refreshed for game {game_number}")
    
    # Update buttons and embed
    series_view.update_buttons()
    await series_view.update_series_embed(channel)
    
    # Check for series end (best of 7, first to 4) - ONLY for real matches
    # Test mode continues until testers vote to end (2 votes required)
    if not series.test_mode:
        red_wins = series.games.count('RED')
        blue_wins = series.games.count('BLUE')
        
        if red_wins >= 4 or blue_wins >= 4:
            await end_series(series_view, channel)

def log_individual_game(series, game_number: int, winner: str):
    """Log individual game result to JSON immediately"""
    import json
    import os
    from datetime import datetime
    
    timestamp = datetime.now().isoformat()
    match_type = "TEST" if series.test_mode else "RANKED"
    
    # Determine file
    if series.test_mode:
        history_file = 'testMLG4v4.json'
        key = 'total_test_matches'
    else:
        history_file = 'MLG4v4.json'
        key = 'total_ranked_matches'
    
    game_entry = {
        "type": "GAME",
        "match_type": match_type,
        "series_label": series.series_number,
        "match_id": series.match_number,
        "game_number": game_number,
        "winner": winner,
        "loser": "BLUE" if winner == "RED" else "RED",
        "timestamp": timestamp,
        "teams_at_game": {
            "red": series.red_team[:],
            "blue": series.blue_team[:]
        }
    }
    
    # Load or create file
    if os.path.exists(history_file):
        try:
            with open(history_file, 'r') as f:
                history = json.load(f)
        except:
            history = {key: 0, "games": [], "matches": []}
    else:
        history = {key: 0, "games": [], "matches": []}
    
    # Ensure games array exists
    if "games" not in history:
        history["games"] = []
    
    history["games"].append(game_entry)
    
    with open(history_file, 'w') as f:
        json.dump(history, f, indent=2)
    
    log_action(f"Logged individual game {game_number} to {history_file}")
    
    # Push to GitHub - ONLY for real matches, not test matches
    if not series.test_mode:
        try:
            import github_webhook
            github_webhook.update_matchhistory_on_github()
        except Exception as e:
            log_action(f"Failed to push game to GitHub: {e}")

async def end_series(series_view_or_channel, channel: discord.TextChannel = None, series=None, admin_ended=False):
    """End series - closes the stats matching window and posts results embed

    Can be called two ways:
    1. end_series(series_view, channel) - from vote button
    2. end_series(channel, series=series, admin_ended=True) - from admin command
    """
    from datetime import datetime

    # Handle both call signatures
    if series is not None:
        # Called with series directly (admin command)
        if channel is None:
            channel = series_view_or_channel
    else:
        # Called with series_view (vote button)
        series = series_view_or_channel.series

    # Record end time for stats matching window
    series.end_time = datetime.now()
    log_action(f"Series #{series.match_number} ended - Stats window: {series.start_time} to {series.end_time}")

    # Get current game counts (may be updated later when stats are parsed)
    red_wins = series.games.count('RED')
    blue_wins = series.games.count('BLUE')

    if red_wins > blue_wins:
        winner = 'RED'
        series_winners = series.red_team
        series_losers = series.blue_team
    elif blue_wins > red_wins:
        winner = 'BLUE'
        series_winners = series.blue_team
        series_losers = series.red_team
    else:
        winner = 'PENDING'  # Will be updated when stats are parsed
        series_winners = []
        series_losers = []

    log_action(f"Series ended - Current Winner: {winner} ({red_wins}-{blue_wins}) in Match #{series.match_number}")

    # Create results embed - will be updated later when stats are parsed
    if winner == 'RED':
        embed_color = discord.Color.red()
        title = f"Match #{series.match_number} Results - RED WINS!"
    elif winner == 'BLUE':
        embed_color = discord.Color.blue()
        title = f"Match #{series.match_number} Results - BLUE WINS!"
    else:
        embed_color = discord.Color.gold()
        title = f"Match #{series.match_number} Results - Awaiting Stats"

    embed = discord.Embed(
        title=title,
        description="*Results will update automatically when game stats are parsed*",
        color=embed_color
    )

    red_mentions = "\n".join([f"<@{uid}>" for uid in series.red_team])
    blue_mentions = "\n".join([f"<@{uid}>" for uid in series.blue_team])

    # Team fields with win counts
    embed.add_field(
        name=f"<:redteam:{RED_TEAM_EMOJI_ID}> Red Team - {red_wins}",
        value=red_mentions,
        inline=True
    )
    embed.add_field(
        name=f"<:blueteam:{BLUE_TEAM_EMOJI_ID}> Blue Team - {blue_wins}",
        value=blue_mentions,
        inline=True
    )

    embed.add_field(name="Final Score", value=f"Red **{red_wins}** - **{blue_wins}** Blue", inline=False)

    # Show game results with map/gametype stats (if any parsed yet)
    if series.games:
        from ingame import format_game_result
        results_text = ""
        for i, game_winner in enumerate(series.games, 1):
            results_text += format_game_result(i, game_winner, series.game_stats)
        embed.add_field(name="Game Results", value=results_text.strip(), inline=False)
    else:
        embed.add_field(name="Game Results", value="*No games recorded yet - will update from parsed stats*", inline=False)

    # Add stats matching info (convert to EST if needed)
    start_est = series.start_time.astimezone(EST) if series.start_time.tzinfo else series.start_time
    end_est = series.end_time.astimezone(EST) if series.end_time.tzinfo else series.end_time
    embed.set_footer(text=f"Stats window: {start_est.strftime('%H:%M')} - {end_est.strftime('%H:%M')} EST")

    # Post to queue channel and store reference for later updates
    queue_channel = channel.guild.get_channel(QUEUE_CHANNEL_ID)
    if queue_channel:
        results_message = await queue_channel.send(embed=embed)
        series.results_message = results_message
        series.results_channel_id = queue_channel.id

    # Save series data for stats matching
    save_series_for_stats_matching(series)

    # Only record stats now if we have actual game results
    if not series.test_mode and winner != 'PENDING' and series.games:
        save_match_history(series, winner)

        # Push to GitHub
        try:
            import github_webhook
            github_webhook.update_matchhistory_on_github()
        except Exception as e:
            log_action(f"Failed to push to GitHub: {e}")

        # Record series results
        import STATSRANKS
        STATSRANKS.record_match_results(series_winners, series_losers, is_series_end=True)

        # Refresh ranks for all players
        all_players = series.red_team + series.blue_team
        await STATSRANKS.refresh_all_ranks(channel.guild, all_players)
        print(f"✅ Refreshed ranks for {len(all_players)} players")

    # Delete the series embed
    if series.series_message:
        try:
            await series.series_message.delete()
            log_action("Deleted series embed")
        except:
            pass

    # Delete general chat match-in-progress embed
    try:
        from ingame import delete_general_chat_embed
        await delete_general_chat_embed(channel.guild, series)
        log_action("Deleted general chat match-in-progress embed")
    except Exception as e:
        log_action(f"Failed to delete general chat embed: {e}")

    # Remove active matchmaking roles from all players
    if not series.test_mode:
        try:
            from searchmatchmaking import remove_active_match_roles
            all_match_players = series.red_team + series.blue_team
            playlist_name = getattr(series, 'playlist_name', 'MLG4v4')
            await remove_active_match_roles(channel.guild, all_match_players, playlist_name, series.match_number)
        except Exception as e:
            log_action(f"Failed to remove active match roles: {e}")

    # Move to postgame and delete VCs
    await cleanup_after_series(series, channel.guild)

    # Clear state (but NOT the queue - players waiting should stay in queue)
    from searchmatchmaking import queue_state, queue_state_2, update_queue_embed

    # Determine which queue this series belonged to and clear the correct one
    if queue_state_2.current_series and queue_state_2.current_series == series:
        queue_state_2.current_series = None
        queue_state_2.test_mode = False
        queue_state_2.test_team = None
        queue_state_2.testers = []
        queue_state_2.locked = False
        queue_state_2.locked_players = []
        log_action("Cleared queue_state_2 after series end")
    else:
        queue_state.current_series = None
        queue_state.test_mode = False
        queue_state.test_team = None
        queue_state.testers = []
        queue_state.locked = False
        queue_state.locked_players = []
        log_action("Cleared queue_state after series end")

    await update_queue_embed(queue_channel if queue_channel else channel)


def save_series_for_stats_matching(series):
    """Save series data for later stats matching"""
    import json
    import os

    pending_file = 'pending_series.json'

    # Load existing pending series
    pending = []
    if os.path.exists(pending_file):
        try:
            with open(pending_file, 'r') as f:
                pending = json.load(f)
        except:
            pending = []

    # Add this series
    series_data = {
        "match_number": series.match_number,
        "series_number": series.series_number,
        "test_mode": series.test_mode,
        "red_team": series.red_team,
        "blue_team": series.blue_team,
        "start_time": series.start_time.isoformat(),
        "end_time": series.end_time.isoformat() if series.end_time else None,
        "results_channel_id": series.results_channel_id,
        "results_message_id": series.results_message.id if series.results_message else None,
        "games": series.games,
        "game_stats": {str(k): v for k, v in series.game_stats.items()},
    }

    pending.append(series_data)

    # Save back
    with open(pending_file, 'w') as f:
        json.dump(pending, f, indent=2)

    log_action(f"Saved series #{series.match_number} for stats matching")

async def cleanup_after_series(series, guild: discord.Guild):
    """Move ALL users (not just players) to postgame and delete team VCs"""
    # Move to Postgame Carnage Report (ID: 1424845826362048643) FIRST before deleting VCs
    POSTGAME_CARNAGE_REPORT_ID = 1424845826362048643
    postgame_vc = guild.get_channel(POSTGAME_CARNAGE_REPORT_ID)

    # Move ALL users from team VCs to postgame (not just players - includes spectators/staff)
    if postgame_vc:
        # Move everyone from Red VC
        if series.red_vc_id:
            red_vc = guild.get_channel(series.red_vc_id)
            if red_vc and red_vc.members:
                for member in list(red_vc.members):  # Use list() to avoid modification during iteration
                    try:
                        await member.move_to(postgame_vc)
                        log_action(f"Moved {member.name} to Postgame Carnage Report")
                    except:
                        pass

        # Move everyone from Blue VC
        if series.blue_vc_id:
            blue_vc = guild.get_channel(series.blue_vc_id)
            if blue_vc and blue_vc.members:
                for member in list(blue_vc.members):  # Use list() to avoid modification during iteration
                    try:
                        await member.move_to(postgame_vc)
                        log_action(f"Moved {member.name} to Postgame Carnage Report")
                    except:
                        pass
    else:
        log_action(f"Warning: Postgame Carnage Report channel {POSTGAME_CARNAGE_REPORT_ID} not found")

    # Delete the created voice channels AFTER moving all users
    if series.red_vc_id:
        red_vc = guild.get_channel(series.red_vc_id)
        if red_vc:
            try:
                await red_vc.delete(reason="Series ended")
                log_action(f"Deleted Red Team voice channel")
            except Exception as e:
                log_action(f"Failed to delete red VC: {e}")

    if series.blue_vc_id:
        blue_vc = guild.get_channel(series.blue_vc_id)
        if blue_vc:
            try:
                await blue_vc.delete(reason="Series ended")
                log_action(f"Deleted Blue Team voice channel")
            except Exception as e:
                log_action(f"Failed to delete blue VC: {e}")

    # Delete the series text channel (results already posted to queue channel)
    if hasattr(series, 'text_channel_id') and series.text_channel_id:
        text_channel = guild.get_channel(series.text_channel_id)
        if text_channel:
            try:
                await text_channel.delete(reason="Series ended - results saved to queue channel")
                log_action(f"Deleted series text channel: {text_channel.name}")
            except Exception as e:
                log_action(f"Failed to delete series text channel: {e}")

    # Clear saved state since series ended
    try:
        import state_manager
        state_manager.clear_state()
    except:
        pass
