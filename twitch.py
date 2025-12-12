"""
twitch.py - Twitch Integration Module
Manages player Twitch links and multi-stream URLs
"""

MODULE_VERSION = "1.2.5"

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button
import json
import os
import re
import logging
from typing import Optional, List, Dict, Tuple

# Logging
logger = logging.getLogger("twitch")

# File path for player Twitch data
# This file contains confidential player data and should NOT be in the GitHub repo
# It stays on the server in the same directory as bot.py
PLAYERS_FILE = "players.json"
PLAYERS_BACKUP = "players.json.bak"

# Multi-stream base URLs
MULTITWITCH_BASE = "https://multitwitch.tv/"

# Header image for embeds
HEADER_IMAGE_URL = "https://raw.githubusercontent.com/I2aMpAnT/H2CarnageReport.com/main/H2CRFinal.png"

# Twitch parsing regex
TWITCH_URL_RE = re.compile(r"(?:https?://)?(?:www\.)?twitch\.tv/([^/?\s@]+)", re.IGNORECASE)
TWITCH_NAME_RE = re.compile(r"^[A-Za-z0-9_]{3,25}$")

# Team emojis (will be set from bot.py)
RED_TEAM_EMOJI_ID = None
BLUE_TEAM_EMOJI_ID = None

# Admin and Staff roles
ADMIN_ROLES = ["Overlord", "Staff", "Server Support"]
STAFF_ROLES = ["Overlord", "Staff", "Server Support"]

def has_staff_role():
    """Check if user has staff role"""
    async def predicate(interaction: discord.Interaction):
        user_roles = [role.name for role in interaction.user.roles]
        if any(role in STAFF_ROLES for role in user_roles):
            return True
        await interaction.response.send_message("❌ You need Overlord, Staff, or Server Support role!", ephemeral=True)
        return False
    return app_commands.check(predicate)

# In-memory cache
_PLAYERS_CACHE = None

def load_players() -> Dict[str, Dict[str, str]]:
    """Load players data from JSON with caching"""
    global _PLAYERS_CACHE
    
    if _PLAYERS_CACHE is not None:
        return _PLAYERS_CACHE
    
    if not os.path.exists(PLAYERS_FILE):
        logger.info("players.json not found; starting with empty DB.")
        _PLAYERS_CACHE = {}
        return _PLAYERS_CACHE
    
    try:
        with open(PLAYERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("players.json root must be an object")
        _PLAYERS_CACHE = data
        return _PLAYERS_CACHE
    except Exception as e:
        logger.exception("Failed to load players.json")
        _PLAYERS_CACHE = {}
        return _PLAYERS_CACHE

def save_players(players: Dict[str, Dict[str, str]]):
    """Save players data to JSON"""
    global _PLAYERS_CACHE
    _PLAYERS_CACHE = players
    
    try:
        # Backup previous file
        if os.path.exists(PLAYERS_FILE):
            try:
                os.replace(PLAYERS_FILE, PLAYERS_BACKUP)
            except:
                pass
        
        with open(PLAYERS_FILE, "w", encoding="utf-8") as f:
            json.dump(players, f, indent=2, ensure_ascii=False)
        logger.info("Saved players.json")
        
        # Push to GitHub
        try:
            import github_webhook
            github_webhook.update_players_on_github()
        except Exception as e:
            logger.warning(f"GitHub push failed for players.json: {e}")
    except Exception as e:
        logger.exception("Failed to save players.json")

def extract_twitch_name(text: str) -> Optional[str]:
    """Extract and validate Twitch name from text or URL"""
    if not text:
        return None
    text = text.strip()
    
    # Try to match URL first
    m = TWITCH_URL_RE.search(text)
    if m:
        candidate = m.group(1)
    else:
        # Try as plain name
        token = text.split()[0].lstrip("@")
        candidate = token
    
    # Validate
    if TWITCH_NAME_RE.match(candidate):
        return candidate
    return None

def get_player_twitch(user_id: int) -> Optional[dict]:
    """Get a player's Twitch info"""
    players = load_players()
    return players.get(str(user_id))

def set_player_twitch(user_id: int, twitch_name: str):
    """Set a player's Twitch info (preserves existing MAC/other data)"""
    players = load_players()
    user_key = str(user_id)

    # Initialize if doesn't exist, otherwise preserve existing data
    if user_key not in players:
        players[user_key] = {}

    # Update/add Twitch fields only (preserves mac_addresses, etc.)
    players[user_key]["twitch_name"] = twitch_name
    players[user_key]["twitch_url"] = f"https://twitch.tv/{twitch_name}"

    save_players(players)

def remove_player_twitch(user_id: int) -> bool:
    """Remove a player's Twitch info (preserves MAC/other data)"""
    players = load_players()
    user_key = str(user_id)

    if user_key in players:
        player_data = players[user_key]
        had_twitch = 'twitch_name' in player_data

        # Remove only Twitch-related fields
        player_data.pop('twitch_name', None)
        player_data.pop('twitch_url', None)

        # If no other data remains, remove the entry entirely
        if not player_data:
            del players[user_key]

        save_players(players)
        return had_twitch

    return False

def make_multitwitch(names: List[str]) -> str:
    """Build multitwitch URL from list of names"""
    safe = [n for n in names if n]
    if not safe:
        return ""
    return MULTITWITCH_BASE + "/".join(safe)

def get_team_twitch_names(team_user_ids: List[int]) -> List[str]:
    """Get Twitch names for a list of user IDs"""
    players = load_players()
    names = []

    for user_id in team_user_ids:
        player_data = players.get(str(user_id))
        if player_data and 'twitch_name' in player_data:
            names.append(player_data["twitch_name"])

    return names

def get_player_display_name(user_id: int, guild: discord.Guild) -> str:
    """Get display name - Twitch display_name if set, otherwise twitch_name, otherwise Discord name"""
    players = load_players()
    player_data = players.get(str(user_id))

    if player_data and 'twitch_name' in player_data:
        return player_data.get("display_name", player_data["twitch_name"])

    # Fallback to Discord display name
    member = guild.get_member(user_id)
    if member:
        return member.display_name
    return str(user_id)

def get_player_as_link(user_id: int, guild: discord.Guild) -> str:
    """Get player as a clickable Twitch link (Discord name displayed) or just Discord name if no Twitch"""
    players = load_players()
    player_data = players.get(str(user_id))

    # Get Discord display name
    member = guild.get_member(user_id)
    discord_name = member.display_name if member else str(user_id)

    if player_data and 'twitch_url' in player_data:
        # Use Discord name but link to Twitch
        url = player_data["twitch_url"]
        return f"[{discord_name}]({url})"

    # No Twitch linked - just show Discord name (no link)
    return discord_name

def format_team_with_links(team_ids: List[int], guild: discord.Guild) -> str:
    """Format a team as clickable Twitch links (Discord names displayed)"""
    lines = []
    for uid in team_ids:
        lines.append(get_player_as_link(uid, guild))
    return "\n".join(lines) if lines else "*No players*"


class MultiStreamView(View):
    """View with multi-stream buttons for Red, Blue, and All streams"""
    def __init__(self, red_names: List[str], blue_names: List[str]):
        super().__init__(timeout=None)
        
        all_names = red_names + blue_names
        
        # Note: Discord link buttons are always grey - we use emoji in labels for color indication
        # Red Team button
        if red_names:
            red_url = make_multitwitch(red_names)
            red_emoji = f"<:redteam:{RED_TEAM_EMOJI_ID}>" if RED_TEAM_EMOJI_ID else "🔴"
            self.add_item(Button(
                label=f"Red Team ({len(red_names)})",
                emoji=discord.PartialEmoji.from_str(f"redteam:{RED_TEAM_EMOJI_ID}") if RED_TEAM_EMOJI_ID else None,
                url=red_url,
                style=discord.ButtonStyle.link
            ))
        
        # Blue Team button
        if blue_names:
            blue_url = make_multitwitch(blue_names)
            self.add_item(Button(
                label=f"Blue Team ({len(blue_names)})",
                emoji=discord.PartialEmoji.from_str(f"blueteam:{BLUE_TEAM_EMOJI_ID}") if BLUE_TEAM_EMOJI_ID else None,
                url=blue_url,
                style=discord.ButtonStyle.link
            ))
        
        # All streams button (white/neutral)
        if all_names:
            all_url = make_multitwitch(all_names)
            self.add_item(Button(
                label=f"All Streams ({len(all_names)})",
                url=all_url,
                style=discord.ButtonStyle.link
            ))


def build_match_embed_with_twitch(
    series,
    guild: discord.Guild
) -> Tuple[discord.Embed, Optional[MultiStreamView]]:
    """
    Build the match-in-progress embed with Twitch links and multistream buttons.
    Returns (embed, view) tuple.
    """
    red_team = series.red_team
    blue_team = series.blue_team
    
    # Build embed
    embed = discord.Embed(
        title=f"Match In Progress - {series.series_number}",
        description="**Halo 2 MLG 2007 Matchmaking**",
        color=discord.Color.from_rgb(0, 112, 192)
    )
    
    # Format teams with clickable Twitch links
    red_text = format_team_with_links(red_team, guild)
    blue_text = format_team_with_links(blue_team, guild)
    
    # Count wins
    red_wins = series.games.count('RED')
    blue_wins = series.games.count('BLUE')
    
    # Add team fields
    red_emoji = f"<:redteam:{RED_TEAM_EMOJI_ID}>" if RED_TEAM_EMOJI_ID else "🔴"
    blue_emoji = f"<:blueteam:{BLUE_TEAM_EMOJI_ID}>" if BLUE_TEAM_EMOJI_ID else "🔵"
    
    embed.add_field(
        name=f"{red_emoji} Red Team - {red_wins}", 
        value=red_text, 
        inline=True
    )
    embed.add_field(
        name=f"{blue_emoji} Blue Team - {blue_wins}",
        value=blue_text,
        inline=True
    )

    # Completed games
    if series.games:
        from ingame import format_game_result
        games_text = ""
        for i, winner in enumerate(series.games, 1):
            games_text += format_game_result(i, winner, series.game_stats)
        
        embed.add_field(
            name="Completed Games",
            value=games_text.strip(),
            inline=False
        )
    
    embed.set_footer(text="Match in progress - Click player names to view streams")

    # Get Twitch names for multistream buttons
    red_twitch = get_team_twitch_names(red_team)
    blue_twitch = get_team_twitch_names(blue_team)
    
    # Create view with buttons if we have any Twitch names
    view = None
    if red_twitch or blue_twitch:
        view = MultiStreamView(red_twitch, blue_twitch)
    
    return embed, view


