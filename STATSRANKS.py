"""
STATSRANKS.py - Stats and Ranks Management Module
Handles player statistics, XP-based ranks, and game details tracking

Import this module in bot.py with:
    import STATSRANKS
    await bot.load_extension('STATSRANKS')
"""

MODULE_VERSION = "1.4.1"

import discord
from discord import app_commands
from discord.ext import commands
import json
import os
import asyncio
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import math

# Import GitHub functions for pulling ranks.json and emblems.json
try:
    from github_webhook import async_pull_ranks_from_github, async_pull_emblems_from_github
    GITHUB_AVAILABLE = True
except ImportError:
    GITHUB_AVAILABLE = False
    async_pull_ranks_from_github = None
    async_pull_emblems_from_github = None

# Map and Gametype Configuration
MAP_GAMETYPES = {
    "Midship": ["MLG CTF5", "MLG Team Slayer", "MLG Oddball", "MLG Bomb"],
    "Beaver Creek": ["MLG Team Slayer"],
    "Lockout": ["MLG Team Slayer", "MLG Oddball"],
    "Warlock": ["MLG Team Slayer", "MLG CTF5"],
    "Sanctuary": ["MLG CTF3", "MLG Team Slayer"]
}

ALL_MAPS = list(MAP_GAMETYPES.keys())
ALL_GAMETYPES = ["MLG CTF5", "MLG CTF3", "MLG Team Slayer", "MLG Oddball", "MLG Bomb"]

# Admin roles
ADMIN_ROLES = ["Overlord", "Staff", "Server Support"]

# Channel ID for populate_stats.py refresh trigger
REFRESH_TRIGGER_CHANNEL_ID = 1427929973125156924

# Playlist types for per-playlist ranking (display names as used by website)
PLAYLIST_TYPES = ["MLG 4v4", "Team Hardcore", "Double Team", "Head to Head"]

# Default playlists structure (matches website format)
def get_default_playlists() -> dict:
    """Get default playlists structure for a new player"""
    return {
        ptype: {"rank": 1, "highest_rank": 1, "xp": 0, "wins": 0, "losses": 0}
        for ptype in PLAYLIST_TYPES
    }

# File paths
GAMESTATS_FILE = "gamestats.json"
RANKS_FILE = "ranks.json"  # Website source of truth (discord_id -> rank data)
XP_CONFIG_FILE = "xp_config.json"
MMR_FILE = "MMR.json"  # Contains MMR values for team balancing (simple format for easy editing)

# Rank icon URLs (for DMs)
RANK_ICON_BASE = "https://r2-cdn.insignia.live/h2-rank"

# Emblem VPS server for rendering emblem PNGs
EMBLEM_VPS_BASE = "http://104.207.143.249:3001"

def get_rank_icon_url(level: int) -> str:
    """Get the rank icon URL for a given level"""
    return f"{RANK_ICON_BASE}/{level}.png"

def get_emblem_png_url(emblem_url: str) -> str:
    """Convert emblem HTML URL to VPS PNG URL.

    Converts: https://carnagereport.com/emblem.html?P=1&S=0&EP=1&ES=0&EF=2&EB=25&ET=0
    To: http://104.207.143.249:3001/P1-S0-EP1-ES0-EF2-EB25-ET0.png
    """
    if not emblem_url:
        return None

    try:
        # Parse URL parameters
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(emblem_url)
        params = parse_qs(parsed.query)

        # Extract values (default to 0 if missing)
        p = params.get('P', ['0'])[0]
        s = params.get('S', ['0'])[0]
        ep = params.get('EP', ['0'])[0]
        es = params.get('ES', ['0'])[0]
        ef = params.get('EF', ['0'])[0]
        eb = params.get('EB', ['0'])[0]
        et = params.get('ET', ['0'])[0]

        # Build VPS URL
        return f"{EMBLEM_VPS_BASE}/P{p}-S{s}-EP{ep}-ES{es}-EF{ef}-EB{eb}-ET{et}.png"
    except Exception as e:
        print(f"[EMBLEM] Failed to parse emblem URL: {e}")
        return None

def load_json_file(filepath: str) -> dict:
    """Load JSON file, create if doesn't exist"""
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            return json.load(f)
    return {}


def get_player_rank_from_ranks_file(user_id: int, playlist: str = None) -> int:
    """Get player rank from ranks.json (website source of truth)

    Args:
        user_id: Discord user ID
        playlist: Optional playlist name (e.g., "MLG 4v4"). If None, returns highest_rank.

    Returns:
        Rank level (1-50), defaults to 1 if not found
    """
    ranks = load_json_file(RANKS_FILE)
    user_key = str(user_id)

    if user_key not in ranks:
        return 1

    player_data = ranks[user_key]

    if playlist:
        # Get rank for specific playlist
        playlists = player_data.get("playlists", {})
        if playlist in playlists:
            return playlists[playlist].get("rank", 1)
        return 1
    else:
        # Get overall highest rank
        return player_data.get("highest_rank", 1)


def get_all_players_from_ranks_file() -> dict:
    """Get all players from ranks.json with their rank data"""
    return load_json_file(RANKS_FILE)


async def async_load_ranks_from_github() -> dict:
    """Load ranks.json from GitHub (website source of truth)

    Falls back to local file if GitHub pull fails.
    """
    if GITHUB_AVAILABLE and async_pull_ranks_from_github:
        try:
            ranks = await async_pull_ranks_from_github()
            if ranks:
                print(f"[RANKS] Loaded {len(ranks)} players from GitHub ranks.json")
                return ranks
        except Exception as e:
            print(f"[RANKS] GitHub pull failed, using local: {e}")

    # Fallback to local file
    return load_json_file(RANKS_FILE)


def save_json_file(filepath: str, data: dict, skip_github: bool = False):
    """Save data to JSON file and optionally push to GitHub

    Note: ranks.json is managed by the website - bot only reads it.
    Bot can still push gamestats.json and xp_config.json.
    """
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)

    # Push to GitHub unless skipped
    if not skip_github:
        try:
            import github_webhook
            if filepath == GAMESTATS_FILE:
                github_webhook.update_gamestats_on_github()
            elif filepath == XP_CONFIG_FILE:
                github_webhook.update_xp_config_on_github()
            # Note: ranks.json is managed by the website, not the bot
        except Exception as e:
            print(f"GitHub push failed for {filepath}: {e}")

def get_xp_config() -> dict:
    """Get XP reward configuration and rank thresholds"""
    config = load_json_file(XP_CONFIG_FILE)
    if not config:
        # Default XP values and rank thresholds
        config = {
            "game_win": 50,
            "game_loss": 10,
            "rank_thresholds": {
                "1": [0, 88],
                "2": [89, 188],
                "3": [189, 288],
                "4": [289, 388],
                "5": [389, 488],
                "6": [489, 588],
                "7": [589, 688],
                "8": [689, 788],
                "9": [789, 888],
                "10": [889, 988],
                "11": [989, 1088],
                "12": [1089, 1188],
                "13": [1189, 1388],
                "14": [1389, 1588],
                "15": [1589, 1788],
                "16": [1789, 1988],
                "17": [1989, 2238],
                "18": [2239, 2488],
                "19": [2489, 2738],
                "20": [2739, 2988],
                "21": [2989, 3238],
                "22": [3239, 3488],
                "23": [3489, 3738],
                "24": [3739, 3988],
                "25": [3989, 4238],
                "26": [4239, 4488],
                "27": [4489, 4738],
                "28": [4739, 4988],
                "29": [4989, 5238],
                "30": [5239, 5488],
                "31": [5489, 5738],
                "32": [5739, 5988],
                "33": [5989, 6238],
                "34": [6239, 6488],
                "35": [6489, 6738],
                "36": [6739, 6988],
                "37": [6989, 7238],
                "38": [7239, 7488],
                "39": [7489, 7738],
                "40": [7739, 7988],
                "41": [7989, 8238],
                "42": [8239, 8488],
                "43": [8489, 8738],
                "44": [8739, 8988],
                "45": [8989, 9238],
                "46": [9239, 9488],
                "47": [9489, 9738],
                "48": [9739, 9988],
                "49": [9989, 10238],
                "50": [10239, 1000000000]
            }
        }
        save_json_file(XP_CONFIG_FILE, config)
    return config

def get_rank_thresholds() -> dict:
    """Get rank thresholds from config"""
    config = get_xp_config()
    thresholds = config.get("rank_thresholds", {})
    # Convert string keys to integers and lists to tuples
    return {int(k): tuple(v) for k, v in thresholds.items()}

def get_player_stats(user_id: int, skip_github: bool = False) -> dict:
    """Get player stats from ranks.json (website source of truth)

    Note: This now reads from ranks.json instead of rankstats.json.
    The website calculates and stores all stats in ranks.json.
    MMR is read from rankstats.json for team balancing.
    """
    ranks = load_json_file(RANKS_FILE)
    mmr_data = load_json_file(MMR_FILE)
    user_key = str(user_id)

    # Get MMR from MMR.json (if exists)
    mmr = None
    if user_key in mmr_data:
        mmr = mmr_data[user_key].get("mmr")

    if user_key not in ranks:
        # Return default stats if player not found in ranks.json
        # But still include MMR if they have it in rankstats.json
        stats = {
            "xp": 0,
            "wins": 0,
            "losses": 0,
            "kills": 0,
            "deaths": 0,
            "series_wins": 0,
            "series_losses": 0,
            "total_games": 0,
            "total_series": 0,
            "rank": 1,
            "highest_rank": 1,
            "playlists": get_default_playlists()
        }
        if mmr is not None:
            stats["mmr"] = mmr
        return stats

    # Convert ranks.json format to expected format
    player_data = ranks[user_key]
    wins = player_data.get("wins", 0)
    losses = player_data.get("losses", 0)
    series_wins = player_data.get("series_wins", 0)
    series_losses = player_data.get("series_losses", 0)

    stats = {
        "xp": 0,  # XP not tracked in ranks.json
        "wins": wins,
        "losses": losses,
        "kills": player_data.get("kills", 0),
        "deaths": player_data.get("deaths", 0),
        "series_wins": series_wins,
        "series_losses": series_losses,
        "total_games": wins + losses,
        "total_series": series_wins + series_losses,
        "rank": player_data.get("rank", 1),
        "highest_rank": player_data.get("highest_rank", 1),
        "playlists": player_data.get("playlists", get_default_playlists())
    }
    if mmr is not None:
        stats["mmr"] = mmr
    return stats

def get_existing_player_stats(user_id: int) -> dict:
    """Get player stats ONLY if they already exist (don't create new entry)

    Now reads from ranks.json (website source of truth).
    MMR is read from rankstats.json for team balancing.
    Returns stats if player exists in either ranks.json OR has MMR in rankstats.json.
    """
    ranks = load_json_file(RANKS_FILE)
    mmr_data = load_json_file(MMR_FILE)
    user_key = str(user_id)

    # Get MMR from MMR.json (if exists)
    mmr = None
    if user_key in mmr_data:
        mmr = mmr_data[user_key].get("mmr")

    if user_key in ranks:
        player_data = ranks[user_key]
        wins = player_data.get("wins", 0)
        losses = player_data.get("losses", 0)
        series_wins = player_data.get("series_wins", 0)
        series_losses = player_data.get("series_losses", 0)

        stats = {
            "xp": 0,
            "wins": wins,
            "losses": losses,
            "kills": player_data.get("kills", 0),
            "deaths": player_data.get("deaths", 0),
            "series_wins": series_wins,
            "series_losses": series_losses,
            "total_games": wins + losses,
            "total_series": series_wins + series_losses,
            "rank": player_data.get("rank", 1),
            "highest_rank": player_data.get("highest_rank", 1),
            "playlists": player_data.get("playlists", {})
        }
        if mmr is not None:
            stats["mmr"] = mmr
        return stats

    # If not in ranks.json but has MMR in rankstats.json, return stats with MMR
    if mmr is not None:
        return {
            "xp": 0,
            "wins": 0,
            "losses": 0,
            "kills": 0,
            "deaths": 0,
            "series_wins": 0,
            "series_losses": 0,
            "total_games": 0,
            "total_series": 0,
            "rank": 1,
            "highest_rank": 1,
            "playlists": {},
            "mmr": mmr
        }
    return None

def update_player_stats(user_id: int, stats_update: dict):
    """DEPRECATED: Stats are now managed by the website via ranks.json.

    This function is kept for backwards compatibility but does nothing.
    The website (populate_stats.py) calculates stats from xlsx files
    and updates ranks.json directly.
    """
    # Stats are handled by the website - this is now a no-op
    print(f"[STATS] update_player_stats called for {user_id} - stats managed by website")


def update_playlist_stats(user_id: int, playlist_type: str, stats_update: dict):
    """DEPRECATED: Stats are now managed by the website via ranks.json.

    This function is kept for backwards compatibility but does nothing.
    The website (populate_stats.py) calculates stats from xlsx files
    and updates ranks.json directly.
    """
    # Stats are handled by the website - this is now a no-op
    print(f"[STATS] update_playlist_stats called for {user_id} ({playlist_type}) - stats managed by website")
    return get_player_stats(user_id)  # Return current stats from ranks.json


def calculate_playlist_rank(xp: int) -> int:
    """Calculate rank level (1-50) based on XP from config"""
    thresholds = get_rank_thresholds()
    for level in range(50, 0, -1):
        min_xp, max_xp = thresholds[level]
        if xp >= min_xp:
            return level
    return 1


def calculate_highest_rank(player_stats: dict) -> int:
    """Get the highest current rank across all playlists for a player.

    The website calculates this as: max(all playlist current ranks)
    This is used for Discord role assignment.

    Returns highest_rank from data if set, otherwise finds max of playlist ranks."""
    # First, check if highest_rank is already set by the website
    if "highest_rank" in player_stats and player_stats["highest_rank"] is not None:
        return player_stats["highest_rank"]

    # Fallback: find max of current playlist ranks
    highest = 1
    playlists = player_stats.get("playlists", {})

    for ptype, pdata in playlists.items():
        # highest_rank in each playlist is the current rank for that playlist
        playlist_rank = pdata.get("highest_rank", 1)
        if playlist_rank > highest:
            highest = playlist_rank

    return highest


def get_playlist_rank(user_id: int, playlist_type: str) -> int:
    """Get a player's current rank for a specific playlist (read from website data)"""
    player_stats = get_player_stats(user_id)
    playlists = player_stats.get("playlists", {})

    if playlist_type in playlists:
        # Read highest_rank - this is the current rank in this playlist
        return playlists[playlist_type].get("highest_rank", 1)

    return 1


def get_all_playlist_ranks(user_id: int) -> dict:
    """Get all playlist current ranks for a player (read from website data)"""
    player_stats = get_player_stats(user_id)
    playlists = player_stats.get("playlists", {})

    ranks = {}
    for ptype in PLAYLIST_TYPES:
        if ptype in playlists:
            # Read highest_rank - this is the current rank in this playlist
            ranks[ptype] = playlists[ptype].get("highest_rank", 1)
        else:
            ranks[ptype] = 1

    return ranks

def calculate_rank(xp: int) -> int:
    """Calculate rank level based on XP from config"""
    thresholds = get_rank_thresholds()
    for level in range(50, 0, -1):
        min_xp, max_xp = thresholds[level]
        if xp >= min_xp:
            return level
    return 1

def get_rank_progress(xp: int) -> Tuple[int, int, int]:
    """Get current rank, XP in rank, and XP needed for next rank"""
    rank = calculate_rank(xp)
    if rank == 50:
        return rank, xp, 0  # Max rank
    
    thresholds = get_rank_thresholds()
    current_min, current_max = thresholds[rank]
    next_min, next_max = thresholds[rank + 1]
    
    xp_in_rank = xp - current_min
    xp_for_next = next_min - xp
    
    return rank, xp_in_rank, xp_for_next

def get_rank_role_name(level: int) -> str:
    """Get the role name for a rank level"""
    return f"Level {level}"

async def update_player_rank_role(guild: discord.Guild, user_id: int, new_level: int, send_dm: bool = True):
    """Update player's rank role with DM notification on rank change"""
    member = guild.get_member(user_id)
    if not member:
        return

    # Check current level before making changes
    old_level = None
    for role in member.roles:
        if role.name.startswith("Level "):
            try:
                old_level = int(role.name.replace("Level ", ""))
                break
            except ValueError:
                pass

    # Skip if player already has the correct rank - no changes needed
    if old_level == new_level:
        return

    # Remove all level roles (1-50)
    roles_to_remove = []
    for role in member.roles:
        if role.name.startswith("Level "):
            roles_to_remove.append(role)

    if roles_to_remove:
        await member.remove_roles(*roles_to_remove, reason="Rank update")

    # Add new level role
    new_role_name = get_rank_role_name(new_level)
    new_role = discord.utils.get(guild.roles, name=new_role_name)
    
    if new_role:
        await member.add_roles(new_role, reason=f"Reached {new_role_name}")

        # Send DM notification if rank changed and send_dm is enabled
        if send_dm and old_level is not None and old_level != new_level:
            try:
                # Send banner image first (appears at top)
                await member.send("https://raw.githubusercontent.com/I2aMpAnT/H2CarnageReport.com/main/MessagefromCarnageReportHEADER.png")

                # Then send the rank change embed
                embed = discord.Embed(color=discord.Color.blue())

                if new_level > old_level:
                    # Level up
                    embed.set_thumbnail(url=get_rank_icon_url(new_level))
                    embed.description = f"Congratulations, you have ranked up to **Level {new_level}**!"
                    embed.color = discord.Color.green()
                elif new_level < old_level:
                    # Derank
                    embed.set_thumbnail(url=get_rank_icon_url(new_level))
                    embed.description = f"Sorry, you have deranked to **Level {new_level}**."
                    embed.color = discord.Color.red()

                await member.send(embed=embed)
                print(f"Sent rank change DM to {member.name}: {old_level} -> {new_level}")
            except discord.Forbidden:
                print(f"Could not DM {member.name} - DMs disabled")
            except Exception as e:
                print(f"Error sending DM to {member.name}: {e}")
    else:
        print(f"⚠️ Role '{new_role_name}' not found in guild")

def add_game_stats(match_number: int, game_number: int, map_name: str, gametype: str) -> bool:
    """Add game stats to gamestats.json with timestamp"""
    # Validate map and gametype combination
    if map_name not in MAP_GAMETYPES:
        return False
    
    if gametype not in MAP_GAMETYPES[map_name]:
        return False
    
    # Load existing stats
    stats = load_json_file(GAMESTATS_FILE)
    
    # Create match key
    match_key = f"match_{match_number}"
    if match_key not in stats:
        stats[match_key] = {}
    
    # Add game data with date timestamp
    game_key = f"game_{game_number}"
    stats[match_key][game_key] = {
        "map": map_name,
        "gametype": gametype,
        "timestamp": datetime.now().isoformat(),
        "date": datetime.now().strftime("%Y-%m-%d")  # For rank resets
    }
    
    # Save
    save_json_file(GAMESTATS_FILE, stats)
    return True

def record_match_results(winners: List[int], losers: List[int], is_series_end: bool = False):
    """Record match results - stats are handled by populate_stats.py

    This function no longer writes stats directly. Stats are calculated
    from xlsx game files by populate_stats.py, which is the authoritative source.
    The bot only tracks active_matches for playlist tagging.
    """
    # Stats are handled by populate_stats.py from xlsx files
    # This function now just logs for debugging
    print(f"  Match recorded: {len(winners)} winners, {len(losers)} losers (stats via populate_stats.py)")

async def record_manual_match(red_team: List[int], blue_team: List[int], games: List[dict],
                               series_winner: str, guild: discord.Guild, match_number: int = None):
    """Record a manually entered match - stats handled by populate_stats.py

    Args:
        red_team: List of red team player IDs
        blue_team: List of blue team player IDs
        games: List of game dicts with 'winner', 'map', 'gametype'
        series_winner: 'RED', 'BLUE', or 'TIE'
        guild: Discord guild for rank updates
        match_number: Optional match number for logging

    Note: Player stats (wins/losses/XP) are NOT written here.
    Stats are calculated from xlsx files by populate_stats.py.
    This only records game stats (map/gametype) and refreshes Discord roles.
    """
    # Count wins for each team (for logging only)
    red_game_wins = sum(1 for g in games if g["winner"] == "RED")
    blue_game_wins = sum(1 for g in games if g["winner"] == "BLUE")

    # Record game stats (map/gametype tracking) - this is still useful
    for i, game in enumerate(games, 1):
        record_game_stat(game["map"], game["gametype"], game["winner"])

    # Refresh ranks for all players from rankstats.json (populated by populate_stats.py)
    all_players = red_team + blue_team
    await refresh_all_ranks(guild, all_players, send_dm=True)

    match_label = f"#{match_number}" if match_number else ""
    print(f"✅ Manual match {match_label} logged: {series_winner} wins ({red_game_wins}-{blue_game_wins}) - stats via populate_stats.py")

async def refresh_all_ranks(guild: discord.Guild, player_ids: List[int], send_dm: bool = True):
    """Refresh rank roles for all players - reads from ranks.json (website source of truth)"""
    from searchmatchmaking import queue_state

    # Load ranks.json from GitHub (website source of truth)
    ranks = await async_load_ranks_from_github()

    for user_id in player_ids:
        if user_id in queue_state.guests:
            continue  # Skip guests

        user_key = str(user_id)

        # Get highest_rank from ranks.json, default to 1
        if user_key in ranks:
            highest = ranks[user_key].get("highest_rank", 1)
        else:
            highest = 1

        await update_player_rank_role(guild, user_id, highest, send_dm=send_dm)


async def refresh_playlist_ranks(guild: discord.Guild, player_ids: List[int], playlist_type: str, send_dm: bool = True):
    """Refresh rank roles for players after a playlist match - reads from ranks.json"""
    # Load ranks.json from GitHub (website source of truth)
    ranks = await async_load_ranks_from_github()

    for user_id in player_ids:
        user_key = str(user_id)

        # Get highest_rank from ranks.json, default to 1
        if user_key in ranks:
            highest = ranks[user_key].get("highest_rank", 1)
        else:
            highest = 1

        await update_player_rank_role(guild, user_id, highest, send_dm=send_dm)

def get_all_players_sorted(sort_by: str = "rank") -> List[Tuple[str, dict]]:
    """Get all players sorted by specified criteria - reads from local ranks.json"""
    ranks = load_json_file(RANKS_FILE)

    players = []
    for user_id, player_data in ranks.items():
        # Create a stats dict compatible with old format
        stats = {
            "rank": player_data.get("highest_rank", 1),
            "wins": player_data.get("wins", 0),
            "losses": player_data.get("losses", 0),
            "kills": player_data.get("kills", 0),
            "deaths": player_data.get("deaths", 0),
            "series_wins": player_data.get("series_wins", 0),
            "series_losses": player_data.get("series_losses", 0)
        }
        players.append((user_id, stats))

    # Sort based on criteria
    if sort_by == "rank":
        players.sort(key=lambda x: (x[1]["rank"], x[1]["wins"]), reverse=True)
    elif sort_by == "wins":
        players.sort(key=lambda x: x[1]["wins"], reverse=True)
    elif sort_by == "series_wins":
        players.sort(key=lambda x: x[1]["series_wins"], reverse=True)
    elif sort_by == "kd":
        players.sort(key=lambda x: (x[1]["kills"] / x[1]["deaths"]) if x[1]["deaths"] > 0 else x[1]["kills"], reverse=True)

    return players

class StatsCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        """Listen for refresh trigger from populate_stats.py"""
        # Ignore bot messages (but allow webhooks)
        if message.author.bot and not message.webhook_id:
            return

        # Only listen in the trigger channel
        if message.channel.id != REFRESH_TRIGGER_CHANNEL_ID:
            return

        # Check for trigger message
        if message.content == "!refresh_ranks_trigger":
            print("Received rank refresh trigger from populate_stats.py")
            try:
                guild = message.guild

                # STEP 1: Sync game results from JSON files and update active match embeds
                try:
                    import playlists
                    sync_results = await playlists.sync_game_results_from_files(self.bot)
                    print(f"Game sync: {sync_results['games_added']} games added, {sync_results['matches_completed']} matches completed, {sync_results['embeds_updated']} embeds updated")
                    if sync_results['errors']:
                        print(f"  Sync errors: {sync_results['errors']}")
                except Exception as e:
                    print(f"Error syncing game results: {e}")

                # STEP 2: Refresh Discord ranks for all players
                # Get all players from GitHub ranks.json (website source of truth)
                ranks = await async_load_ranks_from_github()

                updated_count = 0
                skipped_count = 0
                error_count = 0
                level1_count = 0
                dm_count = 0

                # Process ALL guild members (like /silentverify does)
                for member in guild.members:
                    if member.bot:
                        continue

                    try:
                        user_id_str = str(member.id)

                        # Get current Discord rank
                        current_rank = None
                        for role in member.roles:
                            if role.name.startswith("Level "):
                                try:
                                    current_rank = int(role.name.replace("Level ", ""))
                                    break
                                except:
                                    pass

                        # Get rank from ranks.json
                        if user_id_str in ranks:
                            highest = ranks[user_id_str].get("highest_rank", 1)
                        else:
                            # Not in ranks.json - only assign Level 1 if they have NO Level role
                            # Don't downgrade players who already have a Level role
                            if current_rank is not None:
                                skipped_count += 1
                                continue
                            highest = 1  # New player, give Level 1

                        # Skip if already correct
                        if current_rank == highest:
                            skipped_count += 1
                            continue

                        if highest == 1 and current_rank is None:
                            level1_count += 1

                        # Send DMs for rank changes (except new Level 1s)
                        should_dm = current_rank is not None and current_rank != highest
                        await update_player_rank_role(guild, member.id, highest, send_dm=should_dm)
                        updated_count += 1
                        if should_dm:
                            dm_count += 1

                        # Small delay to avoid rate limits
                        await asyncio.sleep(0.2)

                    except Exception as e:
                        print(f"❌ Error updating {member.display_name}: {e}")
                        error_count += 1

                # Delete the trigger message
                await message.delete()
                print(f"Rank refresh completed: {updated_count} updated (new L1: {level1_count}, DMs sent: {dm_count}), {skipped_count} skipped, {error_count} errors")
            except Exception as e:
                print(f"Error during rank refresh: {e}")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Automatically assign Level 1 role to new members"""
        if member.bot:
            return

        # Check if member already has a Level role
        for role in member.roles:
            if role.name.startswith("Level "):
                return  # Already has a level role

        # Get rank from GitHub ranks.json, default to Level 1
        ranks = await async_load_ranks_from_github()
        user_id_str = str(member.id)

        if user_id_str in ranks:
            highest = ranks[user_id_str].get("highest_rank", 1)
        else:
            highest = 1  # Default: give Level 1 to all new members

        # Assign the role
        role_name = get_rank_role_name(highest)
        role = discord.utils.get(member.guild.roles, name=role_name)

        if role:
            try:
                await member.add_roles(role, reason=f"New member - auto-assigned {role_name}")
                print(f"[AUTO] Assigned {role_name} to new member {member.display_name}")
            except Exception as e:
                print(f"❌ Failed to assign {role_name} to {member.display_name}: {e}")
        else:
            print(f"⚠️ Role '{role_name}' not found in guild")

    def has_admin_role():
        """Check if user has admin role"""
        async def predicate(interaction: discord.Interaction):
            user_roles = [role.name for role in interaction.user.roles]
            if any(role in ADMIN_ROLES for role in user_roles):
                return True
            await interaction.response.send_message("❌ You need Overlord, Staff, or Server Support role!", ephemeral=True)
            return False
        return app_commands.check(predicate)
    
    @app_commands.command(name="addgamestats", description="[ADMIN] Add game statistics")
    @has_admin_role()
    @app_commands.describe(
        match_number="Match number",
        game_number="Game number within the match",
        map_name="Map that was played",
        gametype="Gametype that was played"
    )
    @app_commands.choices(
        map_name=[
            app_commands.Choice(name="Midship", value="Midship"),
            app_commands.Choice(name="Beaver Creek", value="Beaver Creek"),
            app_commands.Choice(name="Lockout", value="Lockout"),
            app_commands.Choice(name="Warlock", value="Warlock"),
            app_commands.Choice(name="Sanctuary", value="Sanctuary"),
        ],
        gametype=[
            app_commands.Choice(name="MLG CTF5", value="MLG CTF5"),
            app_commands.Choice(name="MLG CTF3", value="MLG CTF3"),
            app_commands.Choice(name="MLG Team Slayer", value="MLG Team Slayer"),
            app_commands.Choice(name="MLG Oddball", value="MLG Oddball"),
            app_commands.Choice(name="MLG Bomb", value="MLG Bomb"),
        ]
    )
    async def addgamestats(
        self,
        interaction: discord.Interaction,
        match_number: int,
        game_number: int,
        map_name: str,
        gametype: str
    ):
        """Add game statistics"""
        # Validate combination
        if gametype not in MAP_GAMETYPES.get(map_name, []):
            await interaction.response.send_message(
                f"❌ Sorry, **{gametype}** is not played on **{map_name}**\n\n"
                f"Valid gametypes for {map_name}: {', '.join(MAP_GAMETYPES[map_name])}",
                ephemeral=True
            )
            return
        
        # Add to stats
        success = add_game_stats(match_number, game_number, map_name, gametype)
        
        if success:
            await interaction.response.send_message(
                f"✅ Game stats added!\n"
                f"**Match #{match_number}** - Game {game_number}\n"
                f"**Map:** {map_name}\n"
                f"**Gametype:** {gametype}",
                ephemeral=True
            )
            print(f"[STATS] Game stats added: Match {match_number}, Game {game_number}, {map_name}, {gametype}")
        else:
            await interaction.response.send_message(
                "❌ Failed to add game stats!",
                ephemeral=True
            )
    
    @app_commands.command(name="playerstats", description="View player matchmaking statistics")
    @app_commands.describe(user="User to view stats for (optional)")
    async def playerstats(self, interaction: discord.Interaction, user: discord.User = None):
        """Show player stats with placement ranking - reads from ranks.json"""
        await interaction.response.defer()

        target_user = user or interaction.user

        # Get stats from GitHub ranks.json (website source of truth)
        ranks = await async_load_ranks_from_github()
        user_key = str(target_user.id)

        # Load emblems from GitHub
        emblems = {}
        if GITHUB_AVAILABLE and async_pull_emblems_from_github:
            try:
                emblems = await async_pull_emblems_from_github() or {}
            except Exception as e:
                print(f"[EMBLEMS] Failed to load emblems: {e}")

        if user_key not in ranks:
            await interaction.followup.send(
                f"{target_user.display_name} hasn't played any ranked games yet!",
                ephemeral=True
            )
            return

        player_data = ranks[user_key]

        # Get data from ranks.json
        highest_rank = player_data.get("highest_rank", 1)
        wins = player_data.get("wins", 0)
        losses = player_data.get("losses", 0)
        kills = player_data.get("kills", 0)
        deaths = player_data.get("deaths", 0)
        series_wins = player_data.get("series_wins", 0)
        series_losses = player_data.get("series_losses", 0)
        total_games = wins + losses

        # Calculate win rate and K/D
        win_rate = (wins / total_games * 100) if total_games > 0 else 0
        kd_ratio = (kills / deaths) if deaths > 0 else kills

        # Calculate placement among all players (sorted by highest_rank)
        all_players = []
        for uid, data in ranks.items():
            p_rank = data.get("highest_rank", 1)
            p_wins = data.get("wins", 0)
            all_players.append((uid, p_rank, p_wins))

        # Sort by rank desc, then wins desc
        all_players.sort(key=lambda x: (x[1], x[2]), reverse=True)
        total_players = len(all_players)

        # Find this player's placement
        placement = 1
        for i, (uid, _, _) in enumerate(all_players, 1):
            if uid == user_key:
                placement = i
                break

        # Calculate percentiles
        placement_pct = (placement / total_players * 100) if total_players > 0 else 0
        placement_label = "TOP" if placement_pct <= 50 else "BOTTOM"
        placement_pct_display = placement_pct if placement_pct <= 50 else (100 - placement_pct)

        # Wins percentile (higher is better)
        wins_sorted = sorted([d.get("wins", 0) for d in ranks.values()], reverse=True)
        wins_rank = 1
        for i, w in enumerate(wins_sorted, 1):
            if w <= wins:
                wins_rank = i
                break
        wins_pct = (wins_rank / total_players * 100) if total_players > 0 else 0

        # Games percentile
        games_sorted = sorted([d.get("wins", 0) + d.get("losses", 0) for d in ranks.values()], reverse=True)
        games_rank = 1
        for i, g in enumerate(games_sorted, 1):
            if g <= total_games:
                games_rank = i
                break
        games_pct = (games_rank / total_players * 100) if total_players > 0 else 0

        # Create embed
        embed = discord.Embed(
            title=f"{target_user.display_name}'s Stats",
            color=discord.Color.from_rgb(0, 112, 192)
        )

        # Row 1: RANK | WINRATE | K/D
        embed.add_field(
            name="RANK",
            value=f"**#{placement}**\n{placement_label} {placement_pct_display:.0f}%",
            inline=True
        )

        embed.add_field(
            name="WINRATE",
            value=f"**{win_rate:.0f}%**",
            inline=True
        )

        embed.add_field(
            name="K/D",
            value=f"**{kd_ratio:.2f}**\n{kills}K / {deaths}D",
            inline=True
        )

        # Row 3: WINS | LOSSES | SERIES
        embed.add_field(
            name="WINS",
            value=f"**{wins}**\nTOP {wins_pct:.0f}%",
            inline=True
        )

        embed.add_field(
            name="LOSSES",
            value=f"**{losses}**",
            inline=True
        )

        embed.add_field(
            name="SERIES",
            value=f"**{series_wins}W - {series_losses}L**",
            inline=True
        )

        # Set thumbnail to rank icon PNG
        embed.set_thumbnail(url=get_rank_icon_url(highest_rank))

        # Set emblem as main image if available (from emblems.json)
        if user_key in emblems:
            emblem_url = emblems[user_key].get("emblem_url") if isinstance(emblems[user_key], dict) else emblems[user_key]
            if emblem_url:
                emblem_png = get_emblem_png_url(emblem_url)
                if emblem_png:
                    embed.set_image(url=emblem_png)

        embed.set_footer(text=f"#{placement} of {total_players} players • {total_games} games")

        # Add website link button
        view = discord.ui.View()
        view.add_item(discord.ui.Button(
            label="See more at CarnageReport.com",
            url="https://www.carnagereport.com",
            style=discord.ButtonStyle.link
        ))

        await interaction.followup.send(embed=embed, view=view)
    
    @app_commands.command(name="verifystats", description="Update your rank role based on your current stats")
    async def verifystats(self, interaction: discord.Interaction):
        """Verify and update your own rank - reads from ranks.json (website source of truth)"""
        await interaction.response.defer(ephemeral=True)

        # Read from GitHub ranks.json (website source of truth)
        ranks = await async_load_ranks_from_github()
        user_id_str = str(interaction.user.id)

        if not ranks or user_id_str not in ranks:
            await interaction.followup.send(
                "❌ Could not find your stats in ranks.json. You may not have played any ranked games yet.",
                ephemeral=True
            )
            return

        player_data = ranks[user_id_str]

        # Use highest_rank from ranks.json
        highest = player_data.get("highest_rank", 1)

        # Update role based on highest rank (with DM notification)
        await update_player_rank_role(interaction.guild, interaction.user.id, highest, send_dm=True)

        # Get per-playlist ranks for display
        playlists = player_data.get("playlists", {})
        ranks_display = "\n".join([
            f"• **{ptype}**: Level {pdata.get('rank', 1)}"
            for ptype, pdata in playlists.items()
            if pdata.get('rank', 0) > 0
        ]) or "No playlist stats yet"

        await interaction.followup.send(
            f"✅ Your rank has been verified!\n"
            f"**Highest Rank: Level {highest}**\n\n"
            f"Per-playlist ranks:\n{ranks_display}",
            ephemeral=True
        )
        print(f"[VERIFY] {interaction.user.name} verified rank: Level {highest}")
    
    @app_commands.command(name="verifystatsall", description="[ADMIN] Refresh all players' rank roles")
    @has_admin_role()
    async def verifystatsall(self, interaction: discord.Interaction):
        """Refresh all ranks (Admin only) - reads from GitHub ranks.json, gives Level 1 to members without rank"""
        await interaction.response.send_message(
            "🔄 Syncing ranks from GitHub ranks.json... This may take a while.",
            ephemeral=True
        )

        guild = interaction.guild

        # Read from GitHub ranks.json (website source of truth)
        ranks = await async_load_ranks_from_github()

        updated_count = 0
        skipped_count = 0
        error_count = 0
        level1_count = 0

        # Process ALL guild members
        for member in guild.members:
            if member.bot:
                continue

            try:
                user_id_str = str(member.id)

                # Get current Discord rank
                current_rank = None
                for role in member.roles:
                    if role.name.startswith("Level "):
                        try:
                            current_rank = int(role.name.replace("Level ", ""))
                            break
                        except:
                            pass

                # Get rank from ranks.json
                if user_id_str in ranks:
                    highest = ranks[user_id_str].get("highest_rank", 1)
                else:
                    # Not in ranks.json - only assign Level 1 if they have NO Level role
                    # Don't downgrade players who already have a Level role
                    if current_rank is not None:
                        skipped_count += 1
                        continue
                    highest = 1  # New player, give Level 1

                # Skip if already correct
                if current_rank == highest:
                    skipped_count += 1
                    continue

                if highest == 1 and current_rank is None:
                    level1_count += 1
                    print(f"  [NEW] {member.display_name}: Assigning Level 1")
                else:
                    print(f"  [SYNC] {member.display_name}: Discord={current_rank}, ranks.json={highest}")

                await update_player_rank_role(guild, member.id, highest, send_dm=False)
                updated_count += 1

                # Small delay to avoid rate limits
                await asyncio.sleep(0.2)

            except Exception as e:
                print(f"❌ Error updating {member.display_name}: {e}")
                error_count += 1

        # Summary
        await interaction.followup.send(
            f"✅ Rank sync complete!\n"
            f"**Updated:** {updated_count}\n"
            f"**New Level 1:** {level1_count}\n"
            f"**Already correct:** {skipped_count}\n"
            f"**Errors:** {error_count}",
            ephemeral=True
        )
        print(f"[VERIFY ALL] Updated {updated_count} ranks (new L1: {level1_count}), skipped {skipped_count}, {error_count} errors")

    @app_commands.command(name="silentverify", description="[ADMIN] Sync all ranks silently (no DMs)")
    @has_admin_role()
    async def silentverify(self, interaction: discord.Interaction):
        """Refresh all ranks silently (Admin only) - reads from GitHub ranks.json, gives Level 1 to all"""
        await interaction.response.send_message(
            "🔄 Silently syncing ranks from GitHub ranks.json... (no DMs will be sent)",
            ephemeral=True
        )

        guild = interaction.guild

        # Read from GitHub ranks.json (website source of truth)
        ranks = await async_load_ranks_from_github()

        updated_count = 0
        skipped_count = 0
        error_count = 0
        level1_count = 0

        # Process ALL guild members
        for member in guild.members:
            if member.bot:
                continue

            try:
                user_id_str = str(member.id)

                # Get current Discord rank
                current_rank = None
                for role in member.roles:
                    if role.name.startswith("Level "):
                        try:
                            current_rank = int(role.name.replace("Level ", ""))
                            break
                        except:
                            pass

                # Get rank from ranks.json
                if user_id_str in ranks:
                    highest = ranks[user_id_str].get("highest_rank", 1)
                else:
                    # Not in ranks.json - only assign Level 1 if they have NO Level role
                    # Don't downgrade players who already have a Level role
                    if current_rank is not None:
                        skipped_count += 1
                        continue
                    highest = 1  # New player, give Level 1

                # Skip if already correct
                if current_rank == highest:
                    skipped_count += 1
                    continue

                if highest == 1 and current_rank is None:
                    level1_count += 1

                await update_player_rank_role(guild, member.id, highest, send_dm=False)
                updated_count += 1

                # Small delay to avoid rate limits
                await asyncio.sleep(0.2)

            except Exception as e:
                print(f"❌ Error updating {member.display_name}: {e}")
                error_count += 1

        # Summary
        await interaction.followup.send(
            f"✅ Silent rank sync complete!\n"
            f"**Updated:** {updated_count}\n"
            f"**New Level 1:** {level1_count}\n"
            f"**Already correct:** {skipped_count}\n"
            f"**Errors:** {error_count}",
            ephemeral=True
        )
        print(f"[SILENT VERIFY] Synced {updated_count} ranks (new L1: {level1_count}), skipped {skipped_count}, {error_count} errors")

    @app_commands.command(name="setmmr", description="[ADMIN] Set a player's MMR for team balancing")
    @has_admin_role()
    @app_commands.describe(
        player="Player to set MMR for",
        value="MMR value (e.g., 1500)"
    )
    async def set_mmr(self, interaction: discord.Interaction, player: discord.User, value: int):
        """Set a player's MMR value for team balancing (Admin only)"""
        # Validate MMR range
        if value < 0 or value > 3000:
            await interaction.response.send_message(
                "MMR value must be between 0 and 3000.",
                ephemeral=True
            )
            return

        # Load MMR.json
        mmr_data = load_json_file(MMR_FILE)
        user_key = str(player.id)

        # Create or update player entry (simple format: mmr + discord_name)
        mmr_data[user_key] = {
            "mmr": value,
            "discord_name": player.display_name
        }

        # Save to file
        with open(MMR_FILE, 'w') as f:
            json.dump(mmr_data, f, indent=2)

        # Push to GitHub
        try:
            import github_webhook
            github_webhook.push_file_to_github(MMR_FILE, MMR_FILE)
        except Exception as e:
            print(f"Failed to push MMR.json to GitHub: {e}")

        await interaction.response.send_message(
            f"✅ Set **{player.display_name}**'s MMR to **{value}**",
            ephemeral=True
        )
        print(f"[MMR] {interaction.user.display_name} set {player.display_name}'s MMR to {value}")
    
    @app_commands.command(name="leaderboard", description="View the matchmaking leaderboard")
    async def leaderboard(self, interaction: discord.Interaction):
        """Show leaderboard - starts with Overall view, use buttons to switch"""
        view = LeaderboardView(self.bot, interaction.guild)
        embed = await view.build_embed()
        await interaction.response.send_message(embed=embed, view=view)

class LeaderboardView(discord.ui.View):
    """Leaderboard with tabs for Overall and each playlist, plus sort options"""

    # View options: Overall + each playlist
    VIEWS = ["Overall", "MLG 4v4", "Team Hardcore", "Double Team", "Head to Head"]
    # Sort options (K/D replaces MMR since ranks.json has kills/deaths)
    SORTS = ["Level", "Wins", "K/D"]

    def __init__(self, bot, guild: discord.Guild = None):
        super().__init__(timeout=300)
        self.bot = bot
        self.guild = guild
        self.current_view = "Overall"  # Default view
        self.current_sort = "Level"    # Default sort
        self.current_page = 1
        self.total_pages = 1
        self.per_page = 10

        # Add website link button (row 2)
        self.add_item(discord.ui.Button(
            label="See more at CarnageReport.com",
            url="https://www.carnagereport.com",
            style=discord.ButtonStyle.link,
            row=2
        ))

    def get_rank_emoji(self, level: int) -> str:
        """Get the custom rank emoji for a level (e.g., :15: or :6_:)"""
        if self.guild:
            # Look for emoji with name matching the level number
            emoji_name = str(level)
            emoji = discord.utils.get(self.guild.emojis, name=emoji_name)
            if emoji:
                return str(emoji)
            # For single-digit levels (1-9), also try with underscore suffix (e.g., "6_")
            # Discord doesn't allow single-character emoji names
            if level <= 9:
                emoji_name_underscore = f"{level}_"
                emoji = discord.utils.get(self.guild.emojis, name=emoji_name_underscore)
                if emoji:
                    return str(emoji)
                print(f"[EMOJI] Could not find :{emoji_name}: or :{emoji_name_underscore}: in guild {self.guild.name}")
            else:
                # Debug: print available emojis if not found
                print(f"[EMOJI] Could not find :{emoji_name}: in guild {self.guild.name} - Total emojis: {len(self.guild.emojis)}")
        else:
            print(f"[EMOJI] No guild available for emoji lookup")
        # Fallback to text display
        return f"Lv{level}"

    async def get_players_for_view(self) -> list:
        """Get sorted players based on current view and sort.

        Reads from GitHub ranks.json (website source of truth):
        - ranks.json[discord_id].highest_rank - overall highest rank
        - ranks.json[discord_id].playlists["MLG 4v4"].rank - rank per playlist
        - ranks.json[discord_id].kills/deaths - for K/D ratio
        """
        ranks = await async_load_ranks_from_github()

        if self.current_view == "Overall":
            players = []
            for user_id, data in ranks.items():
                highest = data.get("highest_rank", 1)
                # Get overall wins/losses from top-level data
                total_wins = data.get("wins", 0)
                total_losses = data.get("losses", 0)
                kills = data.get("kills", 0)
                deaths = data.get("deaths", 0)
                games = total_wins + total_losses
                wl_pct = (total_wins / games * 100) if games > 0 else 0
                kd_ratio = (kills / deaths) if deaths > 0 else kills
                players.append({
                    "user_id": user_id,
                    "discord_name": data.get("discord_name", "Unknown"),
                    "level": highest,
                    "wins": total_wins,
                    "losses": total_losses,
                    "games": games,
                    "wl_pct": wl_pct,
                    "kills": kills,
                    "deaths": deaths,
                    "kd": kd_ratio
                })
        else:
            # Playlist-specific view
            playlist_name = self.current_view
            players = []
            for user_id, data in ranks.items():
                playlists = data.get("playlists", {})
                if playlist_name in playlists:
                    pdata = playlists[playlist_name]
                    level = pdata.get("rank", 1)
                    wins = pdata.get("wins", 0)
                    losses = pdata.get("losses", 0)
                    games = wins + losses
                    # Only include players who have played this playlist
                    if games > 0:
                        wl_pct = (wins / games * 100) if games > 0 else 0
                        # Use overall K/D for now (playlist-specific K/D not in ranks.json)
                        kills = data.get("kills", 0)
                        deaths = data.get("deaths", 0)
                        kd_ratio = (kills / deaths) if deaths > 0 else kills
                        players.append({
                            "user_id": user_id,
                            "discord_name": data.get("discord_name", "Unknown"),
                            "level": level,
                            "wins": wins,
                            "losses": losses,
                            "games": games,
                            "wl_pct": wl_pct,
                            "kills": kills,
                            "deaths": deaths,
                            "kd": kd_ratio
                        })

        # Sort based on current_sort
        if self.current_sort == "Level":
            players.sort(key=lambda x: (x["level"], x["wins"]), reverse=True)
        elif self.current_sort == "Wins":
            players.sort(key=lambda x: (x["wins"], x["level"]), reverse=True)
        elif self.current_sort == "K/D":
            players.sort(key=lambda x: (x["kd"], x["level"]), reverse=True)

        return players

    async def build_embed(self) -> discord.Embed:
        """Build the leaderboard embed for current view"""
        players = await self.get_players_for_view()

        # Calculate pagination
        self.total_pages = max(1, math.ceil(len(players) / self.per_page))
        self.current_page = max(1, min(self.current_page, self.total_pages))

        start_idx = (self.current_page - 1) * self.per_page
        end_idx = start_idx + self.per_page
        page_players = players[start_idx:end_idx]

        # Create embed with view-specific title
        if self.current_view == "Overall":
            title = "🏆 Overall Leaderboard"
        else:
            title = f"🏆 {self.current_view} Leaderboard"

        embed = discord.Embed(
            title=title,
            color=discord.Color.from_rgb(0, 112, 192)
        )

        if not page_players:
            embed.add_field(name="No Players", value="No players have stats for this view yet!", inline=False)
        else:
            # Build leaderboard text
            leaderboard_lines = []
            for i, p in enumerate(page_players, start=start_idx + 1):
                # Use discord_name from ranks.json (fallback if API fails)
                name = p.get("discord_name", "Unknown")
                try:
                    user = await self.bot.fetch_user(int(p["user_id"]))
                    name = user.display_name
                except:
                    pass  # Keep name from ranks.json

                rank_emoji = self.get_rank_emoji(p["level"])

                # Format: position. name + rank emoji on right
                if self.current_sort == "Level":
                    line = f"{i}. {name} {rank_emoji}"
                elif self.current_sort == "Wins":
                    line = f"{i}. {name} • **{p['wins']}W** {rank_emoji}"
                elif self.current_sort == "K/D":
                    line = f"{i}. {name} • **{p['kd']:.2f}** {rank_emoji}"
                else:
                    line = f"{i}. {name} {rank_emoji}"

                leaderboard_lines.append(line)

            embed.add_field(name="\u200b", value="\n".join(leaderboard_lines), inline=False)

        # Footer with pagination and view info
        embed.set_footer(text=f"Page {self.current_page}/{self.total_pages} • {len(players)} players • {self.current_view}")

        # Update button states
        self.update_buttons()

        return embed

    def update_buttons(self):
        """Update button disabled states"""
        for item in self.children:
            if hasattr(item, 'custom_id'):
                if item.custom_id == "lb_prev":
                    item.disabled = self.current_page <= 1
                elif item.custom_id == "lb_next":
                    item.disabled = self.current_page >= self.total_pages

    # Row 0: Playlist tabs
    @discord.ui.button(label="Overall", style=discord.ButtonStyle.primary, custom_id="lb_overall", row=0)
    async def view_overall(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_view = "Overall"
        self.current_page = 1
        embed = await self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="MLG 4v4", style=discord.ButtonStyle.secondary, custom_id="lb_mlg", row=0)
    async def view_mlg(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_view = "MLG 4v4"
        self.current_page = 1
        embed = await self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Team Hardcore", style=discord.ButtonStyle.secondary, custom_id="lb_hardcore", row=0)
    async def view_hardcore(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_view = "Team Hardcore"
        self.current_page = 1
        embed = await self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Double Team", style=discord.ButtonStyle.secondary, custom_id="lb_doubles", row=0)
    async def view_doubles(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_view = "Double Team"
        self.current_page = 1
        embed = await self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Head to Head", style=discord.ButtonStyle.secondary, custom_id="lb_1v1", row=0)
    async def view_1v1(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_view = "Head to Head"
        self.current_page = 1
        embed = await self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    # Row 1: Sort options
    @discord.ui.button(label="Level", style=discord.ButtonStyle.primary, custom_id="lb_sort_level", row=1)
    async def sort_level(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_sort = "Level"
        self.current_page = 1
        embed = await self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Wins", style=discord.ButtonStyle.secondary, custom_id="lb_sort_wins", row=1)
    async def sort_wins(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_sort = "Wins"
        self.current_page = 1
        embed = await self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="K/D", style=discord.ButtonStyle.secondary, custom_id="lb_sort_kd", row=1)
    async def sort_kd(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_sort = "K/D"
        self.current_page = 1
        embed = await self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary, custom_id="lb_prev", row=1)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = max(1, self.current_page - 1)
        embed = await self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary, custom_id="lb_next", row=1)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = min(self.total_pages, self.current_page + 1)
        embed = await self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

async def setup(bot):
    """Setup function to add cog to bot"""
    await bot.add_cog(StatsCommands(bot))

# Export functions for use in main bot
__all__ = [
    'record_match_results',
    'refresh_all_ranks',
    'refresh_playlist_ranks',
    'get_player_stats',
    'get_existing_player_stats',
    'calculate_rank',
    'calculate_playlist_rank',
    'calculate_highest_rank',
    'update_playlist_stats',
    'get_playlist_rank',
    'get_all_playlist_ranks',
    'get_xp_config',
    'PLAYLIST_TYPES',
    'setup'
]
