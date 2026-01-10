"""
twitch.py - Twitch Integration Module
Manages player Twitch links, multi-stream URLs, and live stream notifications via EventSub WebSocket
"""

MODULE_VERSION = "1.4.0"

import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.ui import View, Button
import json
import os
import re
import logging
import aiohttp
import asyncio
import websockets
from typing import Optional, List, Dict, Tuple
from datetime import datetime, timedelta

# Twitch API Credentials
TWITCH_CLIENT_ID = "r21afgjrogl0ed9wmliqyuv8oxo1zf"
TWITCH_CLIENT_SECRET = "ox1va8o8933jir3148qfuh8ikp28wn"

# Twitch API endpoints
TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
TWITCH_EVENTSUB_URL = "wss://eventsub.wss.twitch.tv/ws"
TWITCH_API_BASE = "https://api.twitch.tv/helix"

# Channel to post live notifications (will be set from bot.py)
LIVE_NOTIFICATION_CHANNEL_ID = None

# Store for active live streams and subscriptions
_live_streams: Dict[str, dict] = {}  # twitch_user_id -> stream info
_eventsub_session_id: Optional[str] = None
_app_access_token: Optional[str] = None
_token_expires_at: Optional[datetime] = None
_websocket_task: Optional[asyncio.Task] = None
_bot_instance = None

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
    """Get player as a clickable Twitch link (Discord name displayed) or just Discord name if no Twitch.
    Shows 🔴 LIVE indicator if the player is currently streaming."""
    players = load_players()
    player_data = players.get(str(user_id))

    # Get Discord display name
    member = guild.get_member(user_id)
    discord_name = member.display_name if member else str(user_id)

    if player_data and 'twitch_url' in player_data:
        # Check if user is live
        twitch_name = player_data.get("twitch_name", "").lower()
        is_live = is_user_live(twitch_name) if twitch_name else False

        # Use Discord name but link to Twitch
        url = player_data["twitch_url"]
        if is_live:
            return f"[{discord_name}]({url}) - 🔴 LIVE"
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
    def __init__(self, red_names: List[str], blue_names: List[str],
                 red_label: str = None, blue_label: str = None):
        super().__init__(timeout=None)

        all_names = red_names + blue_names

        # Use custom labels if provided, otherwise default to "Red Team Streams" / "Blue Team Streams"
        red_label = red_label or "Red Team Streams"
        blue_label = blue_label or "Blue Team Streams"

        # Note: Discord link buttons are always grey - we use emoji in labels for color indication
        # Red Team button
        if red_names:
            red_url = make_multitwitch(red_names)
            red_emoji = f"<:redteam:{RED_TEAM_EMOJI_ID}>" if RED_TEAM_EMOJI_ID else "🔴"
            self.add_item(Button(
                label=f"{red_label} ({len(red_names)})",
                emoji=discord.PartialEmoji.from_str(f"redteam:{RED_TEAM_EMOJI_ID}") if RED_TEAM_EMOJI_ID else None,
                url=red_url,
                style=discord.ButtonStyle.link
            ))

        # Blue Team button
        if blue_names:
            blue_url = make_multitwitch(blue_names)
            self.add_item(Button(
                label=f"{blue_label} ({len(blue_names)})",
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


# =============================================================================
# TWITCH EVENTSUB WEBSOCKET - LIVE STREAM DETECTION
# =============================================================================

async def get_app_access_token() -> Optional[str]:
    """Get or refresh Twitch App Access Token using Client Credentials flow"""
    global _app_access_token, _token_expires_at

    # Return cached token if still valid
    if _app_access_token and _token_expires_at and datetime.now() < _token_expires_at:
        return _app_access_token

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                TWITCH_TOKEN_URL,
                data={
                    "client_id": TWITCH_CLIENT_ID,
                    "client_secret": TWITCH_CLIENT_SECRET,
                    "grant_type": "client_credentials"
                }
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    _app_access_token = data["access_token"]
                    # Token expires in 'expires_in' seconds, refresh 5 min early
                    expires_in = data.get("expires_in", 3600)
                    _token_expires_at = datetime.now() + timedelta(seconds=expires_in - 300)
                    logger.info("Obtained Twitch App Access Token")
                    return _app_access_token
                else:
                    error = await resp.text()
                    logger.error(f"Failed to get Twitch token: {resp.status} - {error}")
                    return None
    except Exception as e:
        logger.exception(f"Error getting Twitch token: {e}")
        return None


async def get_twitch_user_id(twitch_name: str) -> Optional[str]:
    """Convert Twitch username to user ID"""
    token = await get_app_access_token()
    if not token:
        return None

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{TWITCH_API_BASE}/users",
                params={"login": twitch_name},
                headers={
                    "Client-ID": TWITCH_CLIENT_ID,
                    "Authorization": f"Bearer {token}"
                }
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    users = data.get("data", [])
                    if users:
                        return users[0]["id"]
                return None
    except Exception as e:
        logger.exception(f"Error getting Twitch user ID for {twitch_name}: {e}")
        return None


async def get_stream_info(twitch_user_id: str) -> Optional[dict]:
    """Get current stream info for a Twitch user"""
    token = await get_app_access_token()
    if not token:
        return None

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{TWITCH_API_BASE}/streams",
                params={"user_id": twitch_user_id},
                headers={
                    "Client-ID": TWITCH_CLIENT_ID,
                    "Authorization": f"Bearer {token}"
                }
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    streams = data.get("data", [])
                    if streams:
                        return streams[0]
                return None
    except Exception as e:
        logger.exception(f"Error getting stream info: {e}")
        return None


async def get_user_info(twitch_user_id: str) -> Optional[dict]:
    """Get Twitch user info including profile image"""
    token = await get_app_access_token()
    if not token:
        return None

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{TWITCH_API_BASE}/users",
                params={"id": twitch_user_id},
                headers={
                    "Client-ID": TWITCH_CLIENT_ID,
                    "Authorization": f"Bearer {token}"
                }
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    users = data.get("data", [])
                    if users:
                        return users[0]
                return None
    except Exception as e:
        logger.exception(f"Error getting user info: {e}")
        return None


def get_discord_user_for_twitch(twitch_user_id: str) -> Optional[int]:
    """Find Discord user ID that has this Twitch account linked"""
    players = load_players()

    for discord_id, player_data in players.items():
        if player_data.get("twitch_user_id") == twitch_user_id:
            return int(discord_id)
        # Also check by twitch_name if user_id not stored yet
        twitch_name = player_data.get("twitch_name", "").lower()
        if twitch_name:
            # We'd need to look up - for now just return None and handle later
            pass

    return None


async def create_live_embed(twitch_user_id: str, stream_data: dict) -> discord.Embed:
    """Create embed for live stream notification"""
    user_info = await get_user_info(twitch_user_id)

    user_name = stream_data.get("user_name", "Unknown")
    title = stream_data.get("title", "No title")
    game_name = stream_data.get("game_name", "Unknown Game")
    viewer_count = stream_data.get("viewer_count", 0)
    thumbnail_url = stream_data.get("thumbnail_url", "").replace("{width}", "440").replace("{height}", "248")

    embed = discord.Embed(
        title=f"🔴 {user_name} is LIVE!",
        description=f"**{title}**",
        url=f"https://twitch.tv/{stream_data.get('user_login', user_name)}",
        color=discord.Color.purple()
    )

    embed.add_field(name="Playing", value=game_name, inline=True)
    embed.add_field(name="Viewers", value=f"{viewer_count:,}", inline=True)

    if thumbnail_url:
        embed.set_image(url=thumbnail_url)

    if user_info and user_info.get("profile_image_url"):
        embed.set_thumbnail(url=user_info["profile_image_url"])

    embed.set_footer(text="Twitch • Live Now")
    embed.timestamp = datetime.now()

    return embed


async def subscribe_to_stream_events(session_id: str, twitch_user_id: str) -> bool:
    """Subscribe to stream.online and stream.offline events for a user"""
    token = await get_app_access_token()
    if not token:
        return False

    try:
        async with aiohttp.ClientSession() as session:
            # Subscribe to stream.online
            for event_type in ["stream.online", "stream.offline"]:
                async with session.post(
                    f"{TWITCH_API_BASE}/eventsub/subscriptions",
                    json={
                        "type": event_type,
                        "version": "1",
                        "condition": {"broadcaster_user_id": twitch_user_id},
                        "transport": {
                            "method": "websocket",
                            "session_id": session_id
                        }
                    },
                    headers={
                        "Client-ID": TWITCH_CLIENT_ID,
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json"
                    }
                ) as resp:
                    if resp.status in [200, 202]:
                        logger.info(f"Subscribed to {event_type} for user {twitch_user_id}")
                    else:
                        error = await resp.text()
                        logger.warning(f"Failed to subscribe to {event_type}: {resp.status} - {error}")
        return True
    except Exception as e:
        logger.exception(f"Error subscribing to stream events: {e}")
        return False


async def handle_stream_online(event_data: dict):
    """Handle stream.online event - player went live"""
    global _live_streams

    broadcaster_user_id = event_data.get("broadcaster_user_id")
    broadcaster_user_name = event_data.get("broadcaster_user_name")

    logger.info(f"Stream online: {broadcaster_user_name} ({broadcaster_user_id})")

    # Get stream details
    stream_info = await get_stream_info(broadcaster_user_id)
    if not stream_info:
        logger.warning(f"Could not get stream info for {broadcaster_user_name}")
        return

    # Store live stream info
    _live_streams[broadcaster_user_id] = {
        "stream_info": stream_info,
        "started_at": datetime.now(),
        "message_id": None
    }

    # Post to Discord if channel is configured
    if _bot_instance and LIVE_NOTIFICATION_CHANNEL_ID:
        try:
            channel = _bot_instance.get_channel(LIVE_NOTIFICATION_CHANNEL_ID)
            if channel:
                embed = await create_live_embed(broadcaster_user_id, stream_info)

                # Create watch button
                view = View(timeout=None)
                view.add_item(Button(
                    label=f"Watch {broadcaster_user_name}",
                    url=f"https://twitch.tv/{stream_info.get('user_login', broadcaster_user_name)}",
                    style=discord.ButtonStyle.link,
                    emoji="📺"
                ))

                msg = await channel.send(embed=embed, view=view)
                _live_streams[broadcaster_user_id]["message_id"] = msg.id
                logger.info(f"Posted live notification for {broadcaster_user_name}")
        except Exception as e:
            logger.exception(f"Error posting live notification: {e}")

    # Immediately update active match embeds to show live status
    await update_active_match_embeds()


async def handle_stream_offline(event_data: dict):
    """Handle stream.offline event - player went offline"""
    global _live_streams

    broadcaster_user_id = event_data.get("broadcaster_user_id")
    broadcaster_user_name = event_data.get("broadcaster_user_name")

    logger.info(f"Stream offline: {broadcaster_user_name} ({broadcaster_user_id})")

    # Get stored info
    stream_data = _live_streams.pop(broadcaster_user_id, None)

    # Update or delete the notification message
    if stream_data and stream_data.get("message_id") and _bot_instance and LIVE_NOTIFICATION_CHANNEL_ID:
        try:
            channel = _bot_instance.get_channel(LIVE_NOTIFICATION_CHANNEL_ID)
            if channel:
                try:
                    msg = await channel.fetch_message(stream_data["message_id"])
                    # Edit to show stream ended
                    embed = msg.embeds[0] if msg.embeds else discord.Embed()
                    embed.title = f"⚫ {broadcaster_user_name} was live"
                    embed.color = discord.Color.dark_grey()
                    embed.set_footer(text="Stream ended")
                    await msg.edit(embed=embed, view=None)
                except discord.NotFound:
                    pass
        except Exception as e:
            logger.exception(f"Error updating offline notification: {e}")

    # Immediately update active match embeds to remove live status
    await update_active_match_embeds()


async def eventsub_websocket_loop():
    """Main EventSub WebSocket connection loop"""
    global _eventsub_session_id, _live_streams

    while True:
        try:
            logger.info("Connecting to Twitch EventSub WebSocket...")

            async with websockets.connect(TWITCH_EVENTSUB_URL) as websocket:
                # Wait for welcome message
                welcome_msg = await asyncio.wait_for(websocket.recv(), timeout=30)
                welcome_data = json.loads(welcome_msg)

                if welcome_data.get("metadata", {}).get("message_type") == "session_welcome":
                    session_data = welcome_data.get("payload", {}).get("session", {})
                    _eventsub_session_id = session_data.get("id")
                    keepalive_timeout = session_data.get("keepalive_timeout_seconds", 10)

                    logger.info(f"EventSub connected! Session ID: {_eventsub_session_id}")

                    # Subscribe to all linked Twitch users
                    await subscribe_all_linked_users()

                    # Main message loop
                    while True:
                        try:
                            msg = await asyncio.wait_for(
                                websocket.recv(),
                                timeout=keepalive_timeout + 10
                            )
                            data = json.loads(msg)
                            msg_type = data.get("metadata", {}).get("message_type")

                            if msg_type == "session_keepalive":
                                # Keepalive received, connection is healthy
                                pass

                            elif msg_type == "notification":
                                # Handle event notification
                                sub_type = data.get("metadata", {}).get("subscription_type")
                                event = data.get("payload", {}).get("event", {})

                                if sub_type == "stream.online":
                                    await handle_stream_online(event)
                                elif sub_type == "stream.offline":
                                    await handle_stream_offline(event)

                            elif msg_type == "session_reconnect":
                                # Need to reconnect to new URL
                                new_url = data.get("payload", {}).get("session", {}).get("reconnect_url")
                                logger.info(f"Reconnecting to: {new_url}")
                                break

                        except asyncio.TimeoutError:
                            logger.warning("EventSub keepalive timeout, reconnecting...")
                            break
                else:
                    logger.error(f"Unexpected welcome message: {welcome_data}")

        except websockets.exceptions.ConnectionClosed as e:
            logger.warning(f"EventSub WebSocket closed: {e}")
        except Exception as e:
            logger.exception(f"EventSub WebSocket error: {e}")

        # Wait before reconnecting
        logger.info("Reconnecting in 5 seconds...")
        await asyncio.sleep(5)


async def subscribe_all_linked_users():
    """Subscribe to stream events for all users with linked Twitch accounts"""
    if not _eventsub_session_id:
        logger.warning("No EventSub session ID, cannot subscribe")
        return

    players = load_players()
    subscribed = 0

    for discord_id, player_data in players.items():
        twitch_name = player_data.get("twitch_name")
        if not twitch_name:
            continue

        # Get or store Twitch user ID
        twitch_user_id = player_data.get("twitch_user_id")
        if not twitch_user_id:
            twitch_user_id = await get_twitch_user_id(twitch_name)
            if twitch_user_id:
                # Store for future use
                player_data["twitch_user_id"] = twitch_user_id
                save_players(players)

        if twitch_user_id:
            await subscribe_to_stream_events(_eventsub_session_id, twitch_user_id)
            subscribed += 1
            # Small delay to avoid rate limits
            await asyncio.sleep(0.1)

    logger.info(f"Subscribed to {subscribed} Twitch users for stream events")


def start_eventsub(bot):
    """Start the EventSub WebSocket connection and live polling (call from bot.py on_ready)"""
    global _bot_instance, _websocket_task

    _bot_instance = bot

    if _websocket_task and not _websocket_task.done():
        logger.info("EventSub already running")
        return

    _websocket_task = asyncio.create_task(eventsub_websocket_loop())
    logger.info("Started EventSub WebSocket task")

    # Start the 5-minute polling task for live status
    start_live_polling()

    # Do an immediate poll to populate live status on startup
    asyncio.create_task(poll_all_linked_users())


def stop_eventsub():
    """Stop the EventSub WebSocket connection"""
    global _websocket_task

    if _websocket_task:
        _websocket_task.cancel()
        _websocket_task = None
        logger.info("Stopped EventSub WebSocket task")


def get_live_streams() -> Dict[str, dict]:
    """Get currently live streams"""
    return _live_streams.copy()


def is_user_live(twitch_name: str) -> bool:
    """Check if a Twitch user is currently live"""
    for stream_data in _live_streams.values():
        if stream_data.get("stream_info", {}).get("user_login", "").lower() == twitch_name.lower():
            return True
    return False


def is_discord_user_live(user_id: int) -> bool:
    """Check if a Discord user (by their linked Twitch) is currently live"""
    players = load_players()
    player_data = players.get(str(user_id))
    if not player_data:
        return False

    twitch_name = player_data.get("twitch_name", "").lower()
    if not twitch_name:
        return False

    return is_user_live(twitch_name)


async def refresh_live_status_for_players(player_ids: List[int]):
    """
    Refresh live status for specific Discord users (e.g., players in a match).
    Updates the _live_streams cache with current status.
    """
    global _live_streams

    players = load_players()
    twitch_names = []

    # Get Twitch names for the specified players
    for uid in player_ids:
        player_data = players.get(str(uid))
        if player_data:
            twitch_name = player_data.get("twitch_name")
            if twitch_name:
                twitch_names.append(twitch_name.lower())

    if not twitch_names:
        return

    # Check who is live
    live_users = await batch_check_live_streams(twitch_names)

    # Update _live_streams cache
    for twitch_name, stream_info in live_users.items():
        user_id = stream_info.get("user_id")
        if user_id:
            _live_streams[user_id] = {
                "stream_info": stream_info,
                "started_at": datetime.now(),
                "message_id": None
            }
            logger.info(f"Refreshed live status: {twitch_name} is LIVE")


async def batch_check_live_streams(twitch_names: List[str]) -> Dict[str, dict]:
    """
    Batch check which Twitch users are currently live.
    Returns dict of {twitch_name: stream_info} for users that are live.
    """
    token = await get_app_access_token()
    if not token:
        return {}

    live_users = {}

    # Twitch API allows up to 100 user_logins per request
    for i in range(0, len(twitch_names), 100):
        batch = twitch_names[i:i+100]
        try:
            async with aiohttp.ClientSession() as session:
                params = [("user_login", name) for name in batch]
                async with session.get(
                    f"{TWITCH_API_BASE}/streams",
                    params=params,
                    headers={
                        "Client-ID": TWITCH_CLIENT_ID,
                        "Authorization": f"Bearer {token}"
                    }
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for stream in data.get("data", []):
                            user_login = stream.get("user_login", "").lower()
                            live_users[user_login] = stream
        except Exception as e:
            logger.exception(f"Error batch checking live streams: {e}")

    return live_users


async def poll_all_linked_users():
    """Poll all linked Twitch users to check who is currently live"""
    global _live_streams

    players = load_players()
    twitch_names = []

    # Collect all linked Twitch names
    for discord_id, player_data in players.items():
        twitch_name = player_data.get("twitch_name")
        if twitch_name:
            twitch_names.append(twitch_name.lower())

    if not twitch_names:
        return

    logger.info(f"Polling {len(twitch_names)} linked Twitch users for live status...")

    # Batch check who is live
    live_users = await batch_check_live_streams(twitch_names)

    # Update _live_streams with current live status
    # First, mark any users who are no longer live
    offline_users = []
    for user_id in list(_live_streams.keys()):
        stream_info = _live_streams[user_id].get("stream_info", {})
        user_login = stream_info.get("user_login", "").lower()
        if user_login not in live_users:
            offline_users.append(user_id)

    for user_id in offline_users:
        _live_streams.pop(user_id, None)

    # Add newly live users
    newly_live = []
    for twitch_name, stream_info in live_users.items():
        user_id = stream_info.get("user_id")
        if user_id and user_id not in _live_streams:
            _live_streams[user_id] = {
                "stream_info": stream_info,
                "started_at": datetime.now(),
                "message_id": None
            }
            newly_live.append(stream_info.get("user_name", twitch_name))

    if newly_live:
        logger.info(f"Found {len(newly_live)} live users: {', '.join(newly_live)}")
    else:
        logger.info(f"Currently live: {len(_live_streams)} users")

    # Update active match embeds if any users are in a match
    await update_active_match_embeds()


async def update_active_match_embeds():
    """Update all active match embeds to reflect current live status"""
    if not _bot_instance:
        return

    try:
        from searchmatchmaking import queue_state, queue_state_2

        for qs in [queue_state, queue_state_2]:
            if qs.current_series:
                series = qs.current_series
                guild = None

                # Get guild from series channel
                if series.text_channel_id:
                    channel = _bot_instance.get_channel(series.text_channel_id)
                    if channel:
                        guild = channel.guild

                if not guild and hasattr(series, 'general_message') and series.general_message:
                    guild = series.general_message.guild

                if guild:
                    # Update general chat embed
                    from ingame import update_general_chat_embed
                    await update_general_chat_embed(guild, series)
                    logger.info(f"Updated match embed with live status for {series.series_number}")
    except Exception as e:
        logger.exception(f"Error updating active match embeds: {e}")


_poll_task: Optional[asyncio.Task] = None


async def live_status_poll_loop():
    """Background loop that polls live status every 5 minutes"""
    while True:
        try:
            await poll_all_linked_users()
        except Exception as e:
            logger.exception(f"Error in live status poll: {e}")

        # Wait 5 minutes
        await asyncio.sleep(300)


def start_live_polling():
    """Start the live status polling task"""
    global _poll_task

    if _poll_task and not _poll_task.done():
        logger.info("Live polling already running")
        return

    _poll_task = asyncio.create_task(live_status_poll_loop())
    logger.info("Started live status polling task (every 5 minutes)")
