"""
STATSRANKS.py - Stats and Ranks Management Module
Handles player statistics, XP-based ranks, and game details tracking

Import this module in bot.py with:
    import STATSRANKS

Commands are defined in commands.py and call functions from this module.
"""

MODULE_VERSION = "1.3.0"

import discord
from discord import app_commands
from discord.ext import commands
import json
import os
import asyncio
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import math

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
RANKSTATS_FILE = "rankstats.json"
XP_CONFIG_FILE = "xp_config.json"

# Rank icon URLs (for DMs)
RANK_ICON_BASE = "https://r2-cdn.insignia.live/h2-rank"

def get_rank_icon_url(level: int) -> str:
    """Get the rank icon URL for a given level"""
    return f"{RANK_ICON_BASE}/{level}.png"

def load_json_file(filepath: str) -> dict:
    """Load JSON file, create if doesn't exist"""
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            return json.load(f)
    return {}

def save_json_file(filepath: str, data: dict, skip_github: bool = False):
    """Save data to JSON file and optionally push to GitHub"""
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)
    
    # Push to GitHub unless skipped
    if not skip_github:
        try:
            import github_webhook
            if filepath == RANKSTATS_FILE:
                github_webhook.update_rankstats_on_github()
            elif filepath == GAMESTATS_FILE:
                github_webhook.update_gamestats_on_github()
            elif filepath == XP_CONFIG_FILE:
                github_webhook.update_xp_config_on_github()
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
    """Get player stats from rankstats.json"""
    stats = load_json_file(RANKSTATS_FILE)
    user_key = str(user_id)

    if user_key not in stats:
        stats[user_key] = {
            "xp": 0,
            "wins": 0,
            "losses": 0,
            "series_wins": 0,
            "series_losses": 0,
            "total_games": 0,
            "total_series": 0,
            "mmr": 1500,  # Default MMR
            "rank": 1,
            "highest_rank": 1,
            "playlists": get_default_playlists()
        }
        save_json_file(RANKSTATS_FILE, stats, skip_github=skip_github)
    else:
        # Ensure existing players have playlists and highest_rank
        if "playlists" not in stats[user_key]:
            stats[user_key]["playlists"] = get_default_playlists()
            stats[user_key]["highest_rank"] = 1
            stats[user_key]["rank"] = 1
            save_json_file(RANKSTATS_FILE, stats, skip_github=skip_github)

    return stats[user_key]

def get_existing_player_stats(user_id: int) -> dict:
    """Get player stats ONLY if they already exist (don't create new entry)"""
    stats = load_json_file(RANKSTATS_FILE)
    user_key = str(user_id)
    
    if user_key in stats:
        return stats[user_key]
    return None

def update_player_stats(user_id: int, stats_update: dict):
    """Update player stats - XP never goes below 0
    Note: highest_rank is calculated by the website, not the bot"""
    stats = load_json_file(RANKSTATS_FILE)
    user_key = str(user_id)

    if user_key not in stats:
        stats[user_key] = {
            "xp": 0,
            "wins": 0,
            "losses": 0,
            "series_wins": 0,
            "series_losses": 0,
            "total_games": 0,
            "total_series": 0,
            "mmr": 1500,
            "rank": 1,
            "highest_rank": 1,
            "playlists": get_default_playlists()
        }
    elif "playlists" not in stats[user_key]:
        stats[user_key]["playlists"] = get_default_playlists()
        stats[user_key]["highest_rank"] = 1
        stats[user_key]["rank"] = 1

    for key, value in stats_update.items():
        if key in stats[user_key]:
            stats[user_key][key] += value
        else:
            stats[user_key][key] = value

    # Ensure XP never goes below 0
    stats[user_key]["xp"] = max(0, stats[user_key]["xp"])

    # Note: highest_rank is calculated by the website from playlist current ranks
    # Bot does not recalculate it

    save_json_file(RANKSTATS_FILE, stats)


def update_playlist_stats(user_id: int, playlist_type: str, stats_update: dict):
    """Update player stats for a specific playlist - XP never goes below 0
    Note: Ranks are calculated by the website, not the bot"""
    stats = load_json_file(RANKSTATS_FILE)
    user_key = str(user_id)

    # Initialize player if doesn't exist
    if user_key not in stats:
        stats[user_key] = {
            "xp": 0,
            "wins": 0,
            "losses": 0,
            "series_wins": 0,
            "series_losses": 0,
            "total_games": 0,
            "total_series": 0,
            "mmr": 1500,
            "rank": 1,
            "highest_rank": 1,
            "playlists": get_default_playlists()
        }
    elif "playlists" not in stats[user_key]:
        stats[user_key]["playlists"] = get_default_playlists()
        stats[user_key]["highest_rank"] = 1
        stats[user_key]["rank"] = 1

    # Ensure playlist exists in player's playlists
    if playlist_type not in stats[user_key]["playlists"]:
        stats[user_key]["playlists"][playlist_type] = {
            "rank": 1, "highest_rank": 1, "xp": 0, "wins": 0, "losses": 0
        }

    playlist_data = stats[user_key]["playlists"][playlist_type]

    # Update playlist-specific stats
    for key, value in stats_update.items():
        if key in playlist_data:
            playlist_data[key] += value
        else:
            playlist_data[key] = value

    # Ensure XP never goes below 0
    playlist_data["xp"] = max(0, playlist_data["xp"])

    # Also update global stats for backwards compatibility
    for key in ["xp", "wins", "losses", "series_wins", "series_losses"]:
        if key in stats_update:
            if key in stats[user_key]:
                stats[user_key][key] += stats_update[key]
            else:
                stats[user_key][key] = stats_update[key]
    stats[user_key]["xp"] = max(0, stats[user_key]["xp"])

    # Increment global counters
    if "wins" in stats_update or "losses" in stats_update:
        stats[user_key]["total_games"] = stats[user_key].get("total_games", 0) + stats_update.get("wins", 0) + stats_update.get("losses", 0)
    if "series_wins" in stats_update or "series_losses" in stats_update:
        stats[user_key]["total_series"] = stats[user_key].get("total_series", 0) + stats_update.get("series_wins", 0) + stats_update.get("series_losses", 0)

    # Note: highest_rank is calculated by the website from playlist current ranks
    # Bot does not recalculate it

    save_json_file(RANKSTATS_FILE, stats)
    return stats[user_key]


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

# Rank icon URLs (for DMs)
RANK_ICON_BASE = "https://r2-cdn.insignia.live/h2-rank"

def get_rank_icon_url(level: int) -> str:
    """Get the rank icon URL for a given level"""
    return f"{RANK_ICON_BASE}/{level}.png"

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
                embed = discord.Embed(color=discord.Color.blue())

                # Add header image
                embed.set_image(url="https://raw.githubusercontent.com/I2aMpAnT/H2CarnageReport.com/main/MessagefromCarnageReportHEADER.png")

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
    """Refresh rank roles for all players in a match - always recalculates highest_rank"""
    from searchmatchmaking import queue_state

    # Load stats once
    stats = load_json_file(RANKSTATS_FILE)
    updated = False

    for user_id in player_ids:
        if user_id in queue_state.guests:
            continue  # Skip guests

        user_key = str(user_id)
        player_stats = stats.get(user_key)

        if not player_stats:
            continue  # Skip if no stats

        # Always recalculate highest rank to ensure accuracy
        highest = calculate_highest_rank(player_stats)

        # Update stored highest_rank
        if stats[user_key].get("highest_rank") != highest:
            stats[user_key]["highest_rank"] = highest
            updated = True

        await update_player_rank_role(guild, user_id, highest, send_dm=send_dm)

    # Save once at the end if anything changed
    if updated:
        save_json_file(RANKSTATS_FILE, stats, skip_github=True)


async def refresh_playlist_ranks(guild: discord.Guild, player_ids: List[int], playlist_type: str, send_dm: bool = True):
    """Refresh rank roles for players after a playlist match - recalculates and saves highest_rank"""
    # Load stats once
    stats = load_json_file(RANKSTATS_FILE)
    updated = False

    for user_id in player_ids:
        user_key = str(user_id)
        player_stats = stats.get(user_key)

        if not player_stats:
            continue  # Skip if no stats

        # Recalculate highest rank
        highest = calculate_highest_rank(player_stats)

        # Update stored highest_rank
        if stats[user_key].get("highest_rank") != highest:
            stats[user_key]["highest_rank"] = highest
            updated = True

        await update_player_rank_role(guild, user_id, highest, send_dm=send_dm)

    # Save once at the end if anything changed
    if updated:
        save_json_file(RANKSTATS_FILE, stats, skip_github=True)

def get_all_players_sorted(sort_by: str = "rank") -> List[Tuple[str, dict]]:
    """Get all players sorted by specified criteria"""
    stats = load_json_file(RANKSTATS_FILE)
    
    players = []
    for user_id, player_stats in stats.items():
        player_stats["rank"] = calculate_rank(player_stats["xp"])
        players.append((user_id, player_stats))
    
    # Sort based on criteria
    if sort_by == "rank":
        players.sort(key=lambda x: (x[1]["rank"], x[1]["xp"]), reverse=True)
    elif sort_by == "wins":
        players.sort(key=lambda x: x[1]["wins"], reverse=True)
    elif sort_by == "series_wins":
        players.sort(key=lambda x: x[1]["series_wins"], reverse=True)
    elif sort_by == "mmr":
        players.sort(key=lambda x: x[1].get("mmr", 1500), reverse=True)
    
    return players


class LeaderboardView(discord.ui.View):
    """Leaderboard with tabs for Overall and each playlist"""

    # View options: Overall + each playlist
    VIEWS = ["Overall", "MLG 4v4", "Team Hardcore", "Double Team", "Head to Head"]

    def __init__(self, bot):
        super().__init__(timeout=300)
        self.bot = bot
        self.current_view = "Overall"  # Default view
        self.current_page = 1
        self.total_pages = 1
        self.per_page = 10

    def get_position_display(self, position: int) -> str:
        """Get medal emoji or position number"""
        if position == 1:
            return "🥇"
        elif position == 2:
            return "🥈"
        elif position == 3:
            return "🥉"
        else:
            return f"`{position}.`"

    def get_rank_display(self, level: int) -> str:
        """Get rank icon display - shows level with icon"""
        # Use rank icon URL format for reference, but display as text with visual
        if level >= 45:
            return f"<:rank{level}:> **{level}**" if level <= 50 else f"⭐ **{level}**"
        elif level >= 35:
            return f"🔷 **{level}**"
        elif level >= 25:
            return f"🔶 **{level}**"
        elif level >= 15:
            return f"⬜ **{level}**"
        else:
            return f"⬛ **{level}**"

    async def get_players_for_view(self) -> list:
        """Get sorted players based on current view"""
        stats = load_json_file(RANKSTATS_FILE)

        if self.current_view == "Overall":
            # Sort by highest_rank (highest first)
            players = []
            for user_id, data in stats.items():
                highest = calculate_highest_rank(data)
                wins = data.get("wins", 0)
                losses = data.get("losses", 0)
                players.append((user_id, highest, wins, losses, data))
            # Sort by rank descending, then wins descending
            players.sort(key=lambda x: (x[1], x[2]), reverse=True)
            return players
        else:
            # Playlist-specific view
            playlist_name = self.current_view
            players = []
            for user_id, data in stats.items():
                playlists = data.get("playlists", {})
                if playlist_name in playlists:
                    pdata = playlists[playlist_name]
                    rank = pdata.get("highest_rank", 1)
                    wins = pdata.get("wins", 0)
                    losses = pdata.get("losses", 0)
                    # Only include players who have played this playlist
                    if wins > 0 or losses > 0:
                        players.append((user_id, rank, wins, losses, data))
            # Sort by rank descending, then wins descending
            players.sort(key=lambda x: (x[1], x[2]), reverse=True)
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
            desc = "Ranked by highest level across all playlists"
        else:
            title = f"🏆 {self.current_view} Leaderboard"
            desc = f"Ranked by level in {self.current_view}"

        embed = discord.Embed(
            title=title,
            description=desc,
            color=discord.Color.from_rgb(0, 112, 192)
        )

        if not page_players:
            embed.add_field(name="No Players", value="No players have stats for this view yet!", inline=False)
        else:
            # Build leaderboard text
            leaderboard_lines = []
            for i, (user_id, rank, wins, losses, _) in enumerate(page_players, start=start_idx + 1):
                try:
                    user = await self.bot.fetch_user(int(user_id))
                    name = user.display_name
                except:
                    name = f"User {user_id[:8]}..."

                position = self.get_position_display(i)
                rank_display = self.get_rank_display(rank)

                # Format: position | rank icon | name | W/L
                leaderboard_lines.append(f"{position} {rank_display} **{name}** • {wins}W/{losses}L")

            embed.add_field(name="\u200b", value="\n".join(leaderboard_lines), inline=False)

        # Footer with pagination and view info
        embed.set_footer(text=f"Page {self.current_page}/{self.total_pages} • {len(players)} players • View: {self.current_view}")

        # Set thumbnail to rank 50 icon for flair
        embed.set_thumbnail(url=get_rank_icon_url(50))

        # Update button states
        self.update_buttons()

        return embed

    def update_buttons(self):
        """Update button disabled states"""
        # Navigation buttons
        for item in self.children:
            if hasattr(item, 'custom_id'):
                if item.custom_id == "lb_prev":
                    item.disabled = self.current_page <= 1
                elif item.custom_id == "lb_next":
                    item.disabled = self.current_page >= self.total_pages

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary, custom_id="lb_prev", row=0)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = max(1, self.current_page - 1)
        embed = await self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary, custom_id="lb_next", row=0)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = min(self.total_pages, self.current_page + 1)
        embed = await self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Overall", style=discord.ButtonStyle.primary, custom_id="lb_overall", row=1)
    async def view_overall(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_view = "Overall"
        self.current_page = 1
        embed = await self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="MLG 4v4", style=discord.ButtonStyle.secondary, custom_id="lb_mlg", row=1)
    async def view_mlg(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_view = "MLG 4v4"
        self.current_page = 1
        embed = await self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Hardcore", style=discord.ButtonStyle.secondary, custom_id="lb_hardcore", row=1)
    async def view_hardcore(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_view = "Team Hardcore"
        self.current_page = 1
        embed = await self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Doubles", style=discord.ButtonStyle.secondary, custom_id="lb_doubles", row=2)
    async def view_doubles(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_view = "Double Team"
        self.current_page = 1
        embed = await self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="1v1", style=discord.ButtonStyle.secondary, custom_id="lb_1v1", row=2)
    async def view_1v1(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_view = "Head to Head"
        self.current_page = 1
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
    'RANKSTATS_FILE',
    'PLAYLIST_TYPES',
    'MAP_GAMETYPES',
    'add_game_stats',
    'LeaderboardView'
]
