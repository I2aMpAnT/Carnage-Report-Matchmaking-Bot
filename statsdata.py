# statsdata.py - Game Data Management and Historical Series Processing
# Handles reading game data, grouping into series, and generating embeds

MODULE_VERSION = "1.1.0"

import discord
import json
import os
from datetime import datetime
from typing import List, Dict, Optional, Tuple

# File paths for different playlists
WEBSITE_DATA_PATH = "/home/carnagereport/CarnageReport.com"
MLG_4V4_HISTORY = "MLG4v4.json"  # Local bot file for MLG 4v4
POSTED_SERIES_FILE = "posted_series.json"  # Track which series have been posted

def log_action(message: str):
    """Log actions"""
    from searchmatchmaking import log_action as queue_log
    queue_log(message)


def get_playlist_data_file(playlist: str) -> str:
    """Get the data file path for a playlist"""
    if playlist == "mlg_4v4":
        return MLG_4V4_HISTORY
    else:
        from playlists import PLAYLIST_MATCHES_FILES
        return PLAYLIST_MATCHES_FILES.get(playlist, f"{WEBSITE_DATA_PATH}/{playlist}_matches.json")


def load_historical_data(playlist: str) -> dict:
    """Load historical game data from JSON file"""
    data_file = get_playlist_data_file(playlist)

    if not os.path.exists(data_file):
        log_action(f"[STATSDATA] Data file not found: {data_file}")
        return {}

    try:
        with open(data_file, 'r') as f:
            return json.load(f)
    except Exception as e:
        log_action(f"[STATSDATA] Failed to load {data_file}: {e}")
        return {}


def load_posted_series() -> dict:
    """Load the set of series that have already been posted to Discord"""
    if not os.path.exists(POSTED_SERIES_FILE):
        return {}
    try:
        with open(POSTED_SERIES_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}


def save_posted_series(posted: dict):
    """Save the set of posted series"""
    try:
        with open(POSTED_SERIES_FILE, 'w') as f:
            json.dump(posted, f, indent=2)
    except Exception as e:
        log_action(f"[STATSDATA] Failed to save posted series: {e}")


def mark_series_posted(playlist: str, series_label: str):
    """Mark a series as posted to avoid duplicates"""
    posted = load_posted_series()
    if playlist not in posted:
        posted[playlist] = []
    if series_label not in posted[playlist]:
        posted[playlist].append(series_label)
        save_posted_series(posted)


def is_series_posted(playlist: str, series_label: str) -> bool:
    """Check if a series has already been posted"""
    posted = load_posted_series()
    return series_label in posted.get(playlist, [])


def get_unposted_series(playlist: str, all_series: List[dict]) -> List[dict]:
    """Filter to only series that haven't been posted yet"""
    posted = load_posted_series()
    posted_labels = posted.get(playlist, [])
    return [s for s in all_series if s.get("series_label") not in posted_labels]


def group_games_into_series(games: List[dict]) -> List[dict]:
    """
    Group individual games into series based on series_label or timing/players.

    Args:
        games: List of game dictionaries

    Returns:
        List of series dictionaries with aggregated game data
    """
    if not games:
        return []

    # Group games by series_label
    series_dict = {}

    for game in games:
        label = game.get("series_label", "Unknown")

        if label not in series_dict:
            series_dict[label] = {
                "series_label": label,
                "match_id": game.get("match_id"),
                "games": [],
                "red_team": set(),
                "blue_team": set(),
                "first_game_time": None,
                "last_game_time": None
            }

        series = series_dict[label]
        series["games"].append(game)

        # Track players from teams_at_game
        teams = game.get("teams_at_game", {})
        for p in teams.get("red", []):
            series["red_team"].add(p)
        for p in teams.get("blue", []):
            series["blue_team"].add(p)

    # Convert to list and calculate metadata
    result = []
    for label, s in series_dict.items():
        # Sort games by game_number
        s["games"].sort(key=lambda g: g.get("game_number", 0))

        # Calculate final score
        red_wins = sum(1 for g in s["games"] if g.get("winner") == "RED")
        blue_wins = sum(1 for g in s["games"] if g.get("winner") == "BLUE")

        s["final_score"] = {"red": red_wins, "blue": blue_wins}
        s["winner"] = "RED" if red_wins > blue_wins else "BLUE" if blue_wins > red_wins else "TIE"
        s["total_games"] = len(s["games"])

        # Convert sets to lists
        s["red_team"] = list(s["red_team"])
        s["blue_team"] = list(s["blue_team"])

        result.append(s)

    # Sort by series number (extract number from "Series X")
    def get_series_num(s):
        label = s.get("series_label", "")
        try:
            # Extract number from "Series 1" or "Test 1"
            parts = label.split()
            if len(parts) >= 2:
                return int(parts[-1])
        except:
            pass
        return 0

    result.sort(key=get_series_num)
    return result


def get_all_series(playlist: str) -> List[dict]:
    """
    Get all series for a playlist from historical data.

    Args:
        playlist: Playlist type (mlg_4v4, team_hardcore, etc.)

    Returns:
        List of series dictionaries
    """
    data = load_historical_data(playlist)

    if not data:
        return []

    # Check if 'matches' array exists (already grouped into series)
    matches = data.get("matches", [])
    if matches:
        return matches

    # Otherwise, reconstruct from 'games' array
    games = data.get("games", [])
    return group_games_into_series(games)


async def get_player_rank_by_name(player_name: str, ranks_data: dict = None) -> int:
    """
    Get a player's rank by their display name.

    Args:
        player_name: Discord display name
        ranks_data: Optional pre-loaded ranks data

    Returns:
        Player's current rank (default 1 if not found)
    """
    if ranks_data is None:
        import STATSRANKS
        ranks_data = await STATSRANKS.async_load_ranks_from_github()

    for uid, data in ranks_data.items():
        if data.get("discord_name", "").lower() == player_name.lower():
            return data.get("rank", 1)

    return 1  # Default rank


def get_rank_emoji(guild: discord.Guild, level: int) -> str:
    """Get the custom rank emoji for a level"""
    if guild:
        emoji_name = str(level)
        emoji = discord.utils.get(guild.emojis, name=emoji_name)
        if emoji:
            return str(emoji)
        # Try underscore version for single digits
        if level <= 9:
            emoji = discord.utils.get(guild.emojis, name=f"{level}_")
            if emoji:
                return str(emoji)
    return f"Lv{level}"


async def build_series_embed(
    series: dict,
    guild: discord.Guild,
    playlist: str,
    red_emoji_id: int = None,
    blue_emoji_id: int = None,
    ranks_data: dict = None
) -> discord.Embed:
    """
    Build a Discord embed for a series.

    Args:
        series: Series dictionary with games, teams, etc.
        guild: Discord guild for emoji lookup
        playlist: Playlist name for footer
        red_emoji_id: Custom red team emoji ID
        blue_emoji_id: Custom blue team emoji ID
        ranks_data: Optional pre-loaded ranks data

    Returns:
        Discord Embed object
    """
    if ranks_data is None:
        import STATSRANKS
        ranks_data = await STATSRANKS.async_load_ranks_from_github()

    label = series.get("series_label", "Unknown")
    games = series.get("games", [])
    final_score = series.get("final_score", {"red": 0, "blue": 0})
    winner = series.get("winner", "UNKNOWN")

    # Get teams
    teams_final = series.get("teams_final", {})
    red_players = teams_final.get("red", {}).get("players", series.get("red_team", []))
    blue_players = teams_final.get("blue", {}).get("players", series.get("blue_team", []))

    # Team emojis
    red_emoji = f"<:redteam:{red_emoji_id}>" if red_emoji_id else "🔴"
    blue_emoji = f"<:blueteam:{blue_emoji_id}>" if blue_emoji_id else "🔵"

    # Build embed
    if winner == "RED":
        color = discord.Color.red()
        winner_text = f"{red_emoji} **RED TEAM WINS**"
    elif winner == "BLUE":
        color = discord.Color.blue()
        winner_text = f"{blue_emoji} **BLUE TEAM WINS**"
    else:
        color = discord.Color.gold()
        winner_text = "**TIE**"

    embed = discord.Embed(
        title=f"📜 {label} - Historical Record",
        description=f"{winner_text}\n**Final Score: {final_score['red']} - {final_score['blue']}**",
        color=color
    )

    # Red team with rank emojis
    red_team_text = ""
    for player in red_players:
        rank = await get_player_rank_by_name(player, ranks_data)
        rank_emoji = get_rank_emoji(guild, rank)
        red_team_text += f"{rank_emoji} {player}\n"
    embed.add_field(
        name=f"{red_emoji} Red Team",
        value=red_team_text.strip() or "No players",
        inline=True
    )

    # Blue team with rank emojis
    blue_team_text = ""
    for player in blue_players:
        rank = await get_player_rank_by_name(player, ranks_data)
        rank_emoji = get_rank_emoji(guild, rank)
        blue_team_text += f"{rank_emoji} {player}\n"
    embed.add_field(
        name=f"{blue_emoji} Blue Team",
        value=blue_team_text.strip() or "No players",
        inline=True
    )

    # Games breakdown
    games_text = ""
    for game in games:
        game_num = game.get("game_number", "?")
        game_winner = game.get("winner", "?")
        map_name = game.get("map", "Unknown")
        gametype = game.get("gametype", "Unknown")
        score = game.get("score", "")

        winner_emoji_game = red_emoji if game_winner == "RED" else blue_emoji
        games_text += f"{winner_emoji_game} Game {game_num}: **{gametype}** on **{map_name}**"
        if score:
            games_text += f" ({score})"
        games_text += "\n"

    if games_text:
        embed.add_field(
            name=f"Games Played ({len(games)})",
            value=games_text.strip(),
            inline=False
        )

    # Timestamp
    timestamp = series.get("timestamp_display") or series.get("timestamp", "Unknown")
    embed.set_footer(text=f"Played: {timestamp} | {playlist.replace('_', ' ').title()}")

    return embed


async def generate_all_series_embeds(
    playlist: str,
    guild: discord.Guild,
    red_emoji_id: int = None,
    blue_emoji_id: int = None,
    series_number: int = None
) -> List[discord.Embed]:
    """
    Generate embeds for all series in a playlist.

    Args:
        playlist: Playlist type
        guild: Discord guild
        red_emoji_id: Custom red team emoji ID
        blue_emoji_id: Custom blue team emoji ID
        series_number: Optional - filter to specific series

    Returns:
        List of Discord Embed objects
    """
    series_list = get_all_series(playlist)

    if not series_list:
        return []

    # Filter to specific series if requested
    if series_number:
        series_list = [s for s in series_list if str(series_number) in s.get("series_label", "")]

    # Pre-load ranks data once
    import STATSRANKS
    ranks_data = await STATSRANKS.async_load_ranks_from_github()

    embeds = []
    for series in series_list:
        embed = await build_series_embed(
            series, guild, playlist,
            red_emoji_id, blue_emoji_id, ranks_data
        )
        embeds.append(embed)

    return embeds


# Export for commands
__all__ = [
    'load_historical_data',
    'group_games_into_series',
    'get_all_series',
    'get_player_rank_by_name',
    'get_rank_emoji',
    'build_series_embed',
    'generate_all_series_embeds',
    'get_playlist_data_file',
]
