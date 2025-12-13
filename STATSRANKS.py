"""
STATSRANKS.py - Stats and Ranks Management Module
Handles player statistics, XP-based ranks, and game details tracking

Import this module in bot.py with:
    import STATSRANKS

Commands are defined in commands.py and call functions from this module.
"""

MODULE_VERSION = "1.4.2"

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
RANKS_FILE = "/home/carnagereport/CarnageReport.com/ranks.json"  # Website source of truth (discord_id -> rank data)
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
    """Get the highest CURRENT rank across all playlists for a player.

    This returns the current rank of your highest ranking playlist,
    NOT the peak rank ever achieved.

    Used for Discord role assignment."""
    # Find max of current playlist ranks (use "rank" field, not "highest_rank")
    highest = 1
    playlists = player_stats.get("playlists", {})

    for ptype, pdata in playlists.items():
        # "rank" is the CURRENT rank, "highest_rank" is peak achieved - use current
        playlist_rank = pdata.get("rank", 1)
        if playlist_rank > highest:
            highest = playlist_rank

    # If no playlists found but top-level highest_rank exists, use that as fallback
    if highest == 1 and "highest_rank" in player_stats:
        highest = player_stats.get("highest_rank", 1)

    return highest


def get_playlist_rank(user_id: int, playlist_type: str) -> int:
    """Get a player's CURRENT rank for a specific playlist (read from website data)"""
    player_stats = get_player_stats(user_id)
    playlists = player_stats.get("playlists", {})

    if playlist_type in playlists:
        # Use "rank" field - this is the CURRENT rank (not peak/highest_rank)
        return playlists[playlist_type].get("rank", 1)

    return 1


def get_all_playlist_ranks(user_id: int) -> dict:
    """Get all playlist CURRENT ranks for a player (read from website data)"""
    player_stats = get_player_stats(user_id)
    playlists = player_stats.get("playlists", {})

    ranks = {}
    for ptype in PLAYLIST_TYPES:
        if ptype in playlists:
            # Use "rank" field - this is the CURRENT rank (not peak/highest_rank)
            ranks[ptype] = playlists[ptype].get("rank", 1)
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

async def send_playlist_rank_dm(guild: discord.Guild, member: discord.Member, old_level: int, new_level: int, playlist_name: str):
    """Send a DM notification for a playlist rank change"""
    try:
        # Get rank emoji from guild
        rank_emoji = None
        emoji_name = str(new_level)
        emoji = discord.utils.get(guild.emojis, name=emoji_name)
        if emoji:
            rank_emoji = str(emoji)
        elif new_level <= 9:
            # Single-digit levels use underscore suffix (e.g., "6_")
            emoji = discord.utils.get(guild.emojis, name=f"{new_level}_")
            if emoji:
                rank_emoji = str(emoji)
        if not rank_emoji:
            rank_emoji = f"**Level {new_level}**"  # Fallback

        # Send banner at top as header
        await member.send("https://raw.githubusercontent.com/I2aMpAnT/H2CarnageReport.com/main/MessagefromCarnageReportHEADERSMALL.png")

        # Then send the rank message embed
        embed = discord.Embed(color=discord.Color.from_rgb(255, 255, 255))

        if new_level > old_level:
            embed.description = f"Congratulations, you have ranked up to {rank_emoji} in **{playlist_name}**!"
        elif new_level < old_level:
            embed.description = f"Sorry, you have been deranked to {rank_emoji} in **{playlist_name}**."

        await member.send(embed=embed)
        print(f"Sent {playlist_name} rank DM to {member.name}: {old_level} -> {new_level}")
        return True
    except discord.Forbidden:
        print(f"Could not DM {member.name} - DMs disabled")
        return False
    except Exception as e:
        print(f"Error sending DM to {member.name}: {e}")
        return False


async def update_player_rank_role(guild: discord.Guild, user_id: int, new_level: int, send_dm: bool = True, playlist_name: str = None):
    """Update player's rank role (Discord role only, DMs handled separately)"""
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
        print(f"Updated {member.name}'s Discord role to {new_role_name}")
    else:
        print(f"Role '{new_role_name}' not found in guild")

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

    # Get playlist name for DM
    playlist_name = None
    try:
        from playlists import PLAYLIST_CONFIG
        if playlist_type in PLAYLIST_CONFIG:
            playlist_name = PLAYLIST_CONFIG[playlist_type]["name"]
    except:
        pass

    for user_id in player_ids:
        user_key = str(user_id)

        # Get highest_rank from ranks.json, default to 1
        if user_key in ranks:
            highest = ranks[user_key].get("highest_rank", 1)
        else:
            highest = 1

        await update_player_rank_role(guild, user_id, highest, send_dm=send_dm, playlist_name=playlist_name)

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
    'update_player_rank_role',
    'get_playlist_rank',
    'get_all_playlist_ranks',
    'get_xp_config',
    'load_json_file',
    'save_json_file',
    'async_load_ranks_from_github',
    'get_rank_icon_url',
    'get_emblem_png_url',
    'RANKS_FILE',
    'MMR_FILE',
    'PLAYLIST_TYPES',
    'MAP_GAMETYPES',
    'add_game_stats',
    'LeaderboardView'
]
