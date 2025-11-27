# postgame.py - Postgame Processing, Stats Recording, and Cleanup

import discord
from discord.ui import View, Button
from typing import List
from datetime import datetime

# Will be imported from bot.py
POSTGAME_LOBBY_ID = None
QUEUE_CHANNEL_ID = None
RED_TEAM_EMOJI_ID = None
BLUE_TEAM_EMOJI_ID = None

def log_action(message: str):
    """Log actions"""
    from searchmatchmaking import log_action as queue_log
    queue_log(message)

def save_match_history(series, winner: str):
    """Save match results to matchhistory.json with comprehensive data"""
    import json
    import os
    from datetime import datetime
    
    timestamp = datetime.now().isoformat()
    timestamp_display = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    match_type = "TEST" if series.test_mode else "RANKED"
    
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
    
    # Create match entry
    match_entry = {
        "type": "SERIES",
        "match_type": match_type,
        "series_label": series.series_number,
        "match_id": series.match_number,
        "timestamp": timestamp,
        "timestamp_display": timestamp_display,
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
        history_file = 'matchhistory.json'
    else:
        history_file = 'testmatchhistory.json'
    
    # Load existing history or create new
    if os.path.exists(history_file):
        try:
            with open(history_file, 'r') as f:
                history = json.load(f)
        except:
            if match_type == "RANKED":
                history = {"total_ranked_matches": 0, "matches": []}
            else:
                history = {"total_test_matches": 0, "matches": []}
    else:
        if match_type == "RANKED":
            history = {"total_ranked_matches": 0, "matches": []}
        else:
            history = {"total_test_matches": 0, "matches": []}
    
    # Update counters
    if match_type == "RANKED":
        history["total_ranked_matches"] = history.get("total_ranked_matches", 0) + 1
    else:
        history["total_test_matches"] = history.get("total_test_matches", 0) + 1
    
    # Add new match
    history["matches"].append(match_entry)
    
    # Save back to file
    with open(history_file, 'w') as f:
        json.dump(history, f, indent=2)
    
    log_action(f"Saved {match_type} match {series.series_number} to {history_file}")

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
        history_file = 'testmatchhistory.json'
        key = 'total_test_matches'
    else:
        history_file = 'matchhistory.json'
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

async def end_series(series_view, channel: discord.TextChannel):
    """End series, record stats, cleanup VCs, move players"""
    series = series_view.series
    
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
        winner = 'TIE'
        series_winners = []
        series_losers = []
    
    log_action(f"Series ended - Winner: {winner} ({red_wins}-{blue_wins}) in Match #{series.match_number}")
    save_match_history(series, winner)
    
    # Push to GitHub - ONLY for real matches, not test matches
    if not series.test_mode:
        try:
            import github_webhook
            github_webhook.update_matchhistory_on_github()
        except Exception as e:
            log_action(f"Failed to push to GitHub: {e}")
    
    # Record series results if not test mode
    if not series.test_mode and winner != 'TIE':
        import STATSRANKS
        
        STATSRANKS.record_match_results(series_winners, series_losers, is_series_end=True)
        
        # Refresh ranks for all players
        all_players = series.red_team + series.blue_team
        await STATSRANKS.refresh_all_ranks(channel.guild, all_players)
        print(f"✅ Refreshed ranks for {len(all_players)} players")
    
    # Create final results embed - color based on winning team
    if winner == 'RED':
        embed_color = discord.Color.red()
    elif winner == 'BLUE':
        embed_color = discord.Color.blue()
    else:
        embed_color = discord.Color.greyple()
    
    embed = discord.Embed(
        title=f"Match #{series.match_number} Results - {winner} WINS!",
        color=embed_color
    )
    
    red_mentions = "\n".join([f"<@{uid}>" for uid in series.red_team])
    blue_mentions = "\n".join([f"<@{uid}>" for uid in series.blue_team])
    
    # Team fields with win counts (same as ingame)
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
    
    # Show game results with map/gametype stats
    from ingame import format_game_result
    results_text = ""
    for i, game_winner in enumerate(series.games, 1):
        results_text += format_game_result(i, game_winner, series.game_stats)
    
    embed.add_field(name="Game Results", value=results_text, inline=False)
    
    # Post to queue channel (no buttons)
    queue_channel = channel.guild.get_channel(QUEUE_CHANNEL_ID)
    if queue_channel:
        await queue_channel.send(embed=embed)
    
    # Delete the series voting embed
    if series_view.series.series_message:
        try:
            await series_view.series.series_message.delete()
            log_action("Deleted series voting embed")
        except:
            pass
    
    # Delete general chat match-in-progress embed
    try:
        from ingame import delete_general_chat_embed
        await delete_general_chat_embed(channel.guild, series)
        log_action("Deleted general chat match-in-progress embed")
    except Exception as e:
        log_action(f"Failed to delete general chat embed: {e}")
    
    # Move to postgame and delete VCs
    await cleanup_after_series(series, channel.guild)
    
    # Clear state
    from searchmatchmaking import queue_state, update_queue_embed
    queue_state.current_series = None
    queue_state.queue.clear()
    queue_state.test_mode = False
    queue_state.test_team = None
    queue_state.testers = []  # Clear testers list
    
    await update_queue_embed(queue_channel if queue_channel else channel)

async def cleanup_after_series(series, guild: discord.Guild):
    """Move players to postgame and delete team VCs"""
    # Move to Postgame Carnage Report (ID: 1424845826362048643) FIRST before deleting VCs
    POSTGAME_CARNAGE_REPORT_ID = 1424845826362048643
    postgame_vc = guild.get_channel(POSTGAME_CARNAGE_REPORT_ID)
    if postgame_vc:
        all_players = series.red_team + series.blue_team
        for user_id in all_players:
            member = guild.get_member(user_id)
            if member and member.voice:
                try:
                    await member.move_to(postgame_vc)
                    log_action(f"Moved {member.name} to Postgame Carnage Report")
                except:
                    pass
    else:
        log_action(f"Warning: Postgame Carnage Report channel {POSTGAME_CARNAGE_REPORT_ID} not found")
    
    # Delete the created voice channels AFTER moving players
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
    
    # Clear saved state since series ended
    try:
        import state_manager
        state_manager.clear_state()
    except:
        pass
