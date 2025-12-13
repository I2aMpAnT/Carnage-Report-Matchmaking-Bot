# playlists.py - Multi-Playlist Queue System
# !! REMEMBER TO UPDATE VERSION NUMBER WHEN MAKING CHANGES !!

MODULE_VERSION = "1.3.0"

import discord
from discord.ui import View, Button
from typing import List, Optional, Dict, Tuple
from datetime import datetime, timedelta
import asyncio
import random
import json
import os

# Header image for embeds and DMs
HEADER_IMAGE_URL = "https://raw.githubusercontent.com/I2aMpAnT/H2CarnageReport.com/main/MessagefromCarnageReportHEADERSMALL.png"

# Matchmaking progress images (1-8 players) - using 8-player images temporarily for all queues
MATCHMAKING_IMAGE_BASE = "https://raw.githubusercontent.com/I2aMpAnT/H2CarnageReport.com/main/assets/matchmaking"

# General channel for announcements
GENERAL_CHANNEL_ID = 1403855176460406805

# Ping cooldown in minutes (per playlist)
PING_COOLDOWN_MINUTES = 15

# MLG Map/Gametype combinations (11 total for Team Hardcore)
MLG_MAP_GAMETYPES = [
    ("Midship", "MLG CTF5"),
    ("Midship", "MLG Team Slayer"),
    ("Midship", "MLG Oddball"),
    ("Midship", "MLG Bomb"),
    ("Beaver Creek", "MLG Team Slayer"),
    ("Lockout", "MLG Team Slayer"),
    ("Lockout", "MLG Oddball"),
    ("Warlock", "MLG Team Slayer"),
    ("Warlock", "MLG CTF5"),
    ("Sanctuary", "MLG CTF3"),
    ("Sanctuary", "MLG Team Slayer"),
]

# Head to Head maps (equal chance)
HEAD_TO_HEAD_MAPS = ["Midship", "Lockout", "Sanctuary"]

# Playlist types
class PlaylistType:
    MLG_4V4 = "mlg_4v4"           # Original 4v4 with team selection vote
    TEAM_HARDCORE = "team_hardcore"  # 4v4 auto-balanced, hidden queue
    DOUBLE_TEAM = "double_team"      # 2v2 auto-balanced, hidden queue
    HEAD_TO_HEAD = "head_to_head"    # 1v1 hidden queue


# Playlist configuration
PLAYLIST_CONFIG = {
    PlaylistType.MLG_4V4: {
        "name": "MLG 4v4",
        "channel_id": 1403855421625733151,
        "max_players": 8,
        "team_size": 4,
        "hidden_queue": False,
        "auto_balance": False,  # Uses team selection vote
        "show_map_gametype": False,  # Selected in pregame
        "description": "Classic 4v4 MLG matchmaking with team selection vote",
    },
    PlaylistType.TEAM_HARDCORE: {
        "name": "Team Hardcore",
        "channel_id": 1443783840169721988,
        "max_players": 8,
        "team_size": 4,
        "hidden_queue": True,
        "auto_balance": True,
        "show_map_gametype": True,  # Random MLG map/gametype
        "description": "4v4 auto-balanced teams based on MMR",
    },
    PlaylistType.DOUBLE_TEAM: {
        "name": "Double Team",
        "channel_id": 1443784213135626260,
        "max_players": 4,
        "team_size": 2,
        "hidden_queue": True,
        "auto_balance": True,
        "show_map_gametype": True,  # Random MLG map/gametype
        "description": "2v2 auto-balanced teams based on MMR",
    },
    PlaylistType.HEAD_TO_HEAD: {
        "name": "Head to Head",
        "channel_id": 1443784290230865990,
        "max_players": 2,
        "team_size": 1,
        "hidden_queue": True,
        "auto_balance": False,  # No teams to balance
        "show_map_gametype": True,  # Random 1v1 map
        "description": "1v1 matchmaking",
    },
}

# Match history files - each playlist gets {playlist}_matches.json
PLAYLIST_MATCHES_FILES = {
    "mlg_4v4": "mlg_4v4_matches.json",
    "team_hardcore": "team_hardcore_matches.json",
    "double_team": "double_team_matches.json",
    "head_to_head": "head_to_head_matches.json",
}

# Stats files - each playlist gets {playlist}_stats.json (written by popstats.py or manual matches)
PLAYLIST_STATS_FILES = {
    "mlg_4v4": "mlg_4v4_stats.json",
    "team_hardcore": "team_hardcore_stats.json",
    "double_team": "double_team_stats.json",
    "head_to_head": "head_to_head_stats.json",
}

# Gametype simplification mapping (MLG variant -> simple name)
GAMETYPE_SIMPLE = {
    "MLG CTF5": "CTF",
    "MLG CTF3": "CTF",
    "MLG Team Slayer": "Team Slayer",
    "MLG Oddball": "Oddball",
    "MLG Bomb": "Bomb",
    "1v1 Slayer": "Slayer",
}

def simplify_gametype(gametype: str) -> str:
    """Convert MLG variant name to simple gametype (e.g., 'MLG CTF5' -> 'CTF')"""
    return GAMETYPE_SIMPLE.get(gametype, gametype)

def get_playlist_matches_file(playlist_type: str) -> str:
    """Get the matches file path for a playlist (e.g., mlg_4v4_matches.json)"""
    return PLAYLIST_MATCHES_FILES.get(playlist_type, f"{playlist_type}_matches.json")

def get_playlist_stats_file(playlist_type: str) -> str:
    """Get the stats file path for a playlist (e.g., mlg_4v4_stats.json)"""
    return PLAYLIST_STATS_FILES.get(playlist_type, f"{playlist_type}_stats.json")


def log_action(message: str):
    """Log actions to log.txt (EST timezone)"""
    from datetime import timezone, timedelta
    EST = timezone(timedelta(hours=-5))
    timestamp = datetime.now(EST).strftime('%Y-%m-%d %H:%M:%S EST')
    with open('log.txt', 'a') as f:
        f.write(f"[{timestamp}] {message}\n")
    print(f"[LOG] {message}")


class PlaylistQueueState:
    """Queue state for a single playlist"""
    def __init__(self, playlist_type: str):
        self.playlist_type = playlist_type
        self.config = PLAYLIST_CONFIG[playlist_type]
        self.queue: List[int] = []
        self.queue_join_times: dict = {}  # user_id -> datetime
        self.current_match = None  # Active match in this playlist
        self.paused: bool = False
        self.queue_channel: Optional[discord.TextChannel] = None
        self.queue_message: Optional[discord.Message] = None
        self.inactivity_pending: dict = {}
        self.inactivity_timer_task: Optional[asyncio.Task] = None
        self.match_counter: int = 0
        self.last_ping_time: Optional[datetime] = None  # Last time ping was used
        self.ping_message: Optional[discord.Message] = None  # Ping message in general chat

    @property
    def max_players(self) -> int:
        return self.config["max_players"]

    @property
    def team_size(self) -> int:
        return self.config["team_size"]

    @property
    def name(self) -> str:
        return self.config["name"]

    @property
    def is_hidden(self) -> bool:
        return self.config["hidden_queue"]

    @property
    def auto_balance(self) -> bool:
        return self.config["auto_balance"]


class PlaylistMatch:
    """Represents an active match in a playlist"""
    def __init__(self, playlist_state: PlaylistQueueState, players: List[int],
                 team1: List[int] = None, team2: List[int] = None):
        self.playlist_state = playlist_state
        self.playlist_type = playlist_state.playlist_type
        self.players = players
        self.team1 = team1 or []  # "Red" team or Player 1
        self.team2 = team2 or []  # "Blue" team or Player 2

        playlist_state.match_counter += 1
        self.match_number = playlist_state.match_counter

        self.games: List[str] = []  # 'TEAM1' or 'TEAM2' - populated from parsed stats
        self.game_stats: Dict[int, dict] = {}  # game_number -> {"map": str, "gametype": str, "parsed_stats": dict}
        self.current_game = 1

        # Selected map/gametype for auto-queue playlists
        self.map_name: Optional[str] = None
        self.gametype: Optional[str] = None

        # Voice channel IDs
        self.team1_vc_id: Optional[int] = None
        self.team2_vc_id: Optional[int] = None
        self.shared_vc_id: Optional[int] = None  # For Head to Head
        self.pregame_vc_id: Optional[int] = None  # Pregame lobby

        # Message references
        self.match_message: Optional[discord.Message] = None
        self.general_message: Optional[discord.Message] = None
        self.pregame_message: Optional[discord.Message] = None

        # Time window for stats matching
        self.start_time = datetime.now()
        self.end_time: Optional[datetime] = None

        # Results message for updating after stats parse
        self.results_message: Optional[discord.Message] = None
        self.results_channel_id: Optional[int] = None

        self.end_series_votes: set = set()  # User IDs who voted to end

    def get_match_label(self) -> str:
        """Get display label for this match"""
        return f"{self.playlist_state.name} #{self.match_number}"

    @classmethod
    def restore_from_json(cls, playlist_state: 'PlaylistQueueState', match_data: dict) -> 'PlaylistMatch':
        """Restore a match from JSON data (used on bot restart)"""
        team1 = match_data.get("team1", {}).get("player_ids", [])
        team2 = match_data.get("team2", {}).get("player_ids", [])
        players = team1 + team2

        # Create match but don't increment counter (we'll set it manually)
        playlist_state.match_counter -= 1  # Will be incremented back in __init__
        match = cls(playlist_state, players, team1, team2)

        # Override the match number from JSON
        match.match_number = match_data.get("match_number", match.match_number)

        # Ensure match_counter is at least as high as this match
        if playlist_state.match_counter < match.match_number:
            playlist_state.match_counter = match.match_number

        # Restore timestamps
        start_time_str = match_data.get("start_time")
        if start_time_str:
            try:
                match.start_time = datetime.fromisoformat(start_time_str)
            except:
                pass

        # Restore games
        for game in match_data.get("games", []):
            winner = game.get("winner")
            if winner:
                match.games.append(winner)
                game_num = game.get("game_number", len(match.games))
                match.game_stats[game_num] = {
                    "map": game.get("map", ""),
                    "gametype": game.get("gametype", ""),
                    "score": game.get("score", "")
                }

        return match


# Global playlist states
playlist_states: Dict[str, PlaylistQueueState] = {}


def get_playlist_state(playlist_type: str) -> PlaylistQueueState:
    """Get or create playlist state"""
    if playlist_type not in playlist_states:
        playlist_states[playlist_type] = PlaylistQueueState(playlist_type)
    return playlist_states[playlist_type]


def get_playlist_by_channel(channel_id: int) -> Optional[PlaylistQueueState]:
    """Get playlist state by channel ID"""
    for ptype, config in PLAYLIST_CONFIG.items():
        if config["channel_id"] == channel_id:
            return get_playlist_state(ptype)
    return None


def get_all_playlists() -> List[PlaylistQueueState]:
    """Get all playlist states"""
    return [get_playlist_state(ptype) for ptype in PLAYLIST_CONFIG.keys()]


async def get_player_mmr(user_id: int) -> int:
    """Get player MMR from STATSRANKS"""
    import STATSRANKS
    stats = STATSRANKS.get_existing_player_stats(user_id)
    if stats and 'mmr' in stats:
        return stats['mmr']
    return 1500


def select_random_map_gametype(playlist_type: str) -> Tuple[str, str]:
    """Select random map/gametype for playlist"""
    if playlist_type == PlaylistType.HEAD_TO_HEAD:
        map_name = random.choice(HEAD_TO_HEAD_MAPS)
        return (map_name, "1v1 Slayer")
    elif playlist_type in [PlaylistType.TEAM_HARDCORE, PlaylistType.DOUBLE_TEAM]:
        return random.choice(MLG_MAP_GAMETYPES)
    return ("", "")


def get_queue_progress_image(player_count: int, max_players: int = 8) -> str:
    """Get the queue progress image URL for current player count."""
    if player_count < 1:
        return None  # No image for empty queue

    # Use actual images for each queue size
    if max_players == 2:
        # Head to Head 1v1 - use 1outof2.png and 2outof2.png
        if player_count > 2:
            player_count = 2
        return f"{MATCHMAKING_IMAGE_BASE}/{player_count}outof2.png"
    elif max_players == 4:
        # Double Team 2v2 - use 1outof4.png through 4outof4.png
        if player_count > 4:
            player_count = 4
        return f"{MATCHMAKING_IMAGE_BASE}/{player_count}outof4.png"
    else:
        # MLG 4v4 and Team Hardcore - use 8-player images
        if player_count > 8:
            player_count = 8
        return f"{MATCHMAKING_IMAGE_BASE}/{player_count}outof8.png"


def get_end_series_votes_needed(playlist_type: str) -> int:
    """Get number of votes needed to end series for a playlist type"""
    if playlist_type == PlaylistType.HEAD_TO_HEAD:
        return 1  # 1v1: either player can end
    elif playlist_type == PlaylistType.DOUBLE_TEAM:
        return 3  # 2v2: 3 of 4 players
    elif playlist_type == PlaylistType.TEAM_HARDCORE:
        return 5  # 4v4: 5 of 8 players
    return 5  # Default


async def balance_teams_by_mmr(players: List[int], team_size: int) -> Tuple[List[int], List[int]]:
    """Balance players into two teams based on MMR using exhaustive search"""
    from itertools import combinations

    # Get all player MMRs
    player_mmrs = {}
    for uid in players:
        player_mmrs[uid] = await get_player_mmr(uid)

    total_mmr = sum(player_mmrs.values())
    target_mmr = total_mmr / 2  # Ideal team MMR is half the total

    best_team1 = None
    best_team2 = None
    best_diff = float('inf')

    # Try all possible team combinations and find the one closest to balanced
    # For 8 players choosing 4, there are only 70 combinations
    # For 4 players choosing 2, there are only 6 combinations
    for team1_combo in combinations(players, team_size):
        team1 = list(team1_combo)
        team2 = [p for p in players if p not in team1]

        team1_mmr = sum(player_mmrs[uid] for uid in team1)
        team2_mmr = sum(player_mmrs[uid] for uid in team2)
        diff = abs(team1_mmr - team2_mmr)

        if diff < best_diff:
            best_diff = diff
            best_team1 = team1[:]
            best_team2 = team2[:]

            # Perfect balance found, stop searching
            if diff == 0:
                break

    # Sort teams by average MMR (higher avg team first for consistency)
    team1_avg = sum(player_mmrs[uid] for uid in best_team1) / len(best_team1)
    team2_avg = sum(player_mmrs[uid] for uid in best_team2) / len(best_team2)

    if team2_avg > team1_avg:
        best_team1, best_team2 = best_team2, best_team1

    log_action(f"Balanced teams - MMR diff: {best_diff} (checked all {len(list(combinations(players, team_size)))} combinations)")
    return best_team1, best_team2


async def get_player_names(guild, player_ids: List[int]) -> Dict[int, str]:
    """Get display names for a list of player IDs"""
    names = {}
    for uid in player_ids:
        member = guild.get_member(uid) if guild else None
        if member:
            names[uid] = member.display_name
        else:
            names[uid] = f"Unknown ({uid})"
    return names


def save_match_to_history(match: PlaylistMatch, result: str, guild=None):
    """Save match to playlist-specific history file

    Structure:
    - active_matches: Currently in-progress matches
    - matches: Completed match history with player names, maps, gametypes
    - total_matches: Count of completed matches

    Match entry structure:
    - match_number: int
    - playlist: str (e.g., "mlg_4v4")
    - start_time: ISO format (when series opened)
    - start_time_display: Human readable start time
    - end_time: ISO format (when series closed) - null for active matches
    - end_time_display: Human readable end time - null for active matches
    - result: "TEAM1_WIN" | "TEAM2_WIN" | "TIE" | "STARTED"
    - team1/team2: {player_ids: [], player_names: [], color: "Red"/"Blue" or null for 1v1}
    - games: [{winner: "TEAM1"|"TEAM2", map: str, gametype: str (simplified)}]
    """
    # Get the matches file for this playlist
    matches_file = get_playlist_matches_file(match.playlist_type)

    # Load existing history or create new
    history = {"total_matches": 0, "matches": [], "active_matches": []}
    if os.path.exists(matches_file):
        try:
            with open(matches_file, 'r') as f:
                history = json.load(f)
                if "active_matches" not in history:
                    history["active_matches"] = []
        except:
            history = {"total_matches": 0, "matches": [], "active_matches": []}

    # Get player names from guild if available
    team1_names = []
    team2_names = []
    if guild:
        for uid in match.team1:
            member = guild.get_member(uid)
            team1_names.append(member.display_name if member else f"Unknown")
        for uid in match.team2:
            member = guild.get_member(uid)
            team2_names.append(member.display_name if member else f"Unknown")
    else:
        team1_names = [str(uid) for uid in match.team1]
        team2_names = [str(uid) for uid in match.team2]

    # Build games array with simplified gametypes
    games_data = []
    for i, winner in enumerate(match.games, 1):
        stats = match.game_stats.get(i, {})
        games_data.append({
            "game_number": i,
            "winner": winner,
            "map": stats.get("map", match.map_name or ""),
            "gametype": simplify_gametype(stats.get("gametype", match.gametype or ""))
        })

    # Determine team structure based on playlist type
    is_1v1 = match.playlist_state.playlist_type == PlaylistType.HEAD_TO_HEAD

    match_data = {
        "match_number": match.match_number,
        "playlist": match.playlist_type,
        "playlist_name": match.playlist_state.name,
        "start_time": match.start_time.isoformat(),
        "start_time_display": match.start_time.strftime('%Y-%m-%d %H:%M:%S'),
        "end_time": match.end_time.isoformat() if match.end_time else None,
        "end_time_display": match.end_time.strftime('%Y-%m-%d %H:%M:%S') if match.end_time else None,
        "result": result,
        "team1": {
            "player_ids": match.team1,
            "player_names": team1_names,
            "color": None if is_1v1 else "Red",
            "games_won": match.games.count('TEAM1')
        },
        "team2": {
            "player_ids": match.team2,
            "player_names": team2_names,
            "color": None if is_1v1 else "Blue",
            "games_won": match.games.count('TEAM2')
        },
        "games": games_data,
    }

    if result == "STARTED":
        # Add to active_matches
        history["active_matches"].append(match_data)
        log_action(f"Added {match.get_match_label()} to active_matches in {matches_file}")
    else:
        # Remove from active_matches if present
        history["active_matches"] = [
            m for m in history["active_matches"]
            if m.get("match_number") != match.match_number
        ]
        # Add to completed matches
        history["matches"].append(match_data)
        history["total_matches"] = len(history["matches"])
        log_action(f"Completed {match.get_match_label()} in {matches_file}")

    with open(matches_file, 'w') as f:
        json.dump(history, f, indent=2)

    # Sync to GitHub
    try:
        import github_webhook
        github_webhook.push_file_to_github(matches_file, matches_file)
    except Exception as e:
        log_action(f"Failed to sync {matches_file} to GitHub: {e}")


def update_active_match_in_history(match: PlaylistMatch):
    """Update an active match's data in the history file (e.g., game results)"""
    matches_file = get_playlist_matches_file(match.playlist_type)

    history = {"total_matches": 0, "matches": [], "active_matches": []}
    if os.path.exists(matches_file):
        try:
            with open(matches_file, 'r') as f:
                history = json.load(f)
                if "active_matches" not in history:
                    history["active_matches"] = []
        except:
            return

    # Build games array with simplified gametypes
    games_data = []
    for i, winner in enumerate(match.games, 1):
        stats = match.game_stats.get(i, {})
        games_data.append({
            "game_number": i,
            "winner": winner,
            "map": stats.get("map", match.map_name or ""),
            "gametype": simplify_gametype(stats.get("gametype", match.gametype or ""))
        })

    # Update the active match with current game data
    for i, m in enumerate(history["active_matches"]):
        if m.get("match_number") == match.match_number:
            history["active_matches"][i]["games"] = games_data
            history["active_matches"][i]["team1"]["games_won"] = match.games.count('TEAM1')
            history["active_matches"][i]["team2"]["games_won"] = match.games.count('TEAM2')
            break

    with open(matches_file, 'w') as f:
        json.dump(history, f, indent=2)

    # Sync to GitHub
    try:
        import github_webhook
        github_webhook.push_file_to_github(matches_file, matches_file)
    except Exception as e:
        log_action(f"Failed to sync {matches_file} to GitHub: {e}")


class PlaylistQueueView(View):
    """View for playlist queue with join/leave/ping buttons"""
    def __init__(self, playlist_state: PlaylistQueueState):
        super().__init__(timeout=None)
        self.playlist_state = playlist_state
        # Custom IDs must be unique per playlist
        self.join_btn.custom_id = f"join_{playlist_state.playlist_type}"
        self.leave_btn.custom_id = f"leave_{playlist_state.playlist_type}"
        self.ping_btn.custom_id = f"ping_{playlist_state.playlist_type}"

    @discord.ui.button(label="Join Queue", style=discord.ButtonStyle.success)
    async def join_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_join(interaction)

    @discord.ui.button(label="Leave Queue", style=discord.ButtonStyle.danger)
    async def leave_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_leave(interaction)

    @discord.ui.button(label="Ping", style=discord.ButtonStyle.secondary)
    async def ping_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_ping(interaction)

    async def handle_join(self, interaction: discord.Interaction):
        """Handle player joining queue"""
        user_id = interaction.user.id
        ps = self.playlist_state

        if ps.paused:
            await interaction.response.send_message(
                f"**{ps.name}** is currently paused.",
                ephemeral=True
            )
            return

        # Check if player has MMR
        import STATSRANKS
        player_stats = STATSRANKS.get_existing_player_stats(user_id)
        if not player_stats or 'mmr' not in player_stats:
            await interaction.response.send_message(
                "You don't have an MMR rating yet!\n"
                "A staff member needs to set your MMR with `/setmmr`.",
                ephemeral=True
            )
            return

        if user_id in ps.queue:
            await interaction.response.send_message("You're already in this queue!", ephemeral=True)
            return

        # Check if in another queue (Head to Head is exempt from this rule)
        if ps.playlist_type != PlaylistType.HEAD_TO_HEAD:
            # Check MLG 4v4 queue
            try:
                from searchmatchmaking import queue_state as mlg_queue
                if user_id in mlg_queue.queue:
                    await interaction.response.send_message(
                        "You're already in the **MLG 4v4** queue!\n"
                        f"Leave that queue first before joining {ps.name}.",
                        ephemeral=True
                    )
                    return
            except:
                pass

            # Check other playlist queues (except Head to Head)
            for other_ps in get_all_playlists():
                if other_ps == ps:
                    continue  # Skip self
                if other_ps.playlist_type == PlaylistType.HEAD_TO_HEAD:
                    continue  # Head to Head exempt
                if user_id in other_ps.queue:
                    await interaction.response.send_message(
                        f"You're already in the **{other_ps.name}** queue!\n"
                        f"Leave that queue first before joining {ps.name}.",
                        ephemeral=True
                    )
                    return

        if len(ps.queue) >= ps.max_players:
            await interaction.response.send_message("Queue is full!", ephemeral=True)
            return

        # Check if player is in the current match (can't queue while playing)
        if ps.current_match:
            if user_id in ps.current_match.team1 or user_id in ps.current_match.team2:
                await interaction.response.send_message("You're in the current match! Finish it first.", ephemeral=True)
                return

        # Add to queue
        ps.queue.append(user_id)
        ps.queue_join_times[user_id] = datetime.now()

        log_action(f"{interaction.user.display_name} joined {ps.name} ({len(ps.queue)}/{ps.max_players})")

        await interaction.response.defer()
        await update_playlist_embed(interaction.channel, ps)

        # Check if queue is full
        if len(ps.queue) >= ps.max_players:
            await start_playlist_match(interaction.channel, ps)

    async def handle_leave(self, interaction: discord.Interaction):
        """Handle player leaving queue"""
        user_id = interaction.user.id
        ps = self.playlist_state

        if user_id not in ps.queue:
            await interaction.response.send_message("You're not in this queue!", ephemeral=True)
            return

        ps.queue.remove(user_id)
        if user_id in ps.queue_join_times:
            del ps.queue_join_times[user_id]

        log_action(f"{interaction.user.display_name} left {ps.name} ({len(ps.queue)}/{ps.max_players})")

        await interaction.response.defer()
        await update_playlist_embed(interaction.channel, ps)

    async def handle_ping(self, interaction: discord.Interaction):
        """Handle ping button - send message to general chat"""
        ps = self.playlist_state

        # Check if queue is empty
        if len(ps.queue) == 0:
            await interaction.response.send_message("Queue is empty! Join first before pinging.", ephemeral=True)
            return

        # Check if queue is full
        if len(ps.queue) >= ps.max_players:
            await interaction.response.send_message("Queue is already full!", ephemeral=True)
            return

        # Check cooldown
        if ps.last_ping_time:
            elapsed = datetime.now() - ps.last_ping_time
            remaining = timedelta(minutes=PING_COOLDOWN_MINUTES) - elapsed

            if remaining.total_seconds() > 0:
                mins = int(remaining.total_seconds() // 60)
                secs = int(remaining.total_seconds() % 60)
                await interaction.response.send_message(
                    f"Ping is on cooldown! Try again in **{mins}m {secs}s**",
                    ephemeral=True
                )
                return

        await interaction.response.defer()

        guild = interaction.guild
        general_channel = guild.get_channel(GENERAL_CHANNEL_ID)

        if not general_channel:
            return

        # Update cooldown
        ps.last_ping_time = datetime.now()

        # Delete old ping message if exists
        if ps.ping_message:
            try:
                await ps.ping_message.delete()
            except:
                pass

        # Create ping embed - just the progress image, no redundant text
        current_count = len(ps.queue)

        embed = discord.Embed(color=discord.Color.green())
        embed.set_image(url=get_queue_progress_image(current_count, ps.max_players))

        # Create view with join button
        view = PlaylistPingJoinView(ps)

        # Send @here ping then delete it
        here_msg = await general_channel.send("@here")
        await asyncio.sleep(0.1)
        try:
            await here_msg.delete()
        except:
            pass

        # Send the embed
        ps.ping_message = await general_channel.send(embed=embed, view=view)

        log_action(f"{interaction.user.display_name} pinged for {ps.name} ({current_count}/{ps.max_players})")


class PlaylistPingJoinView(View):
    """View for playlist ping message with join button"""
    def __init__(self, playlist_state: PlaylistQueueState):
        super().__init__(timeout=None)
        self.playlist_state = playlist_state
        self.join_btn.custom_id = f"ping_join_{playlist_state.playlist_type}"

    @discord.ui.button(label="Join Queue", style=discord.ButtonStyle.success)
    async def join_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Join queue from ping message"""
        user_id = interaction.user.id
        ps = self.playlist_state

        if ps.paused:
            await interaction.response.send_message(f"**{ps.name}** is currently paused.", ephemeral=True)
            return

        # Check if player has MMR
        import STATSRANKS
        player_stats = STATSRANKS.get_existing_player_stats(user_id)
        if not player_stats or 'mmr' not in player_stats:
            await interaction.response.send_message(
                "You don't have an MMR rating yet!\nA staff member needs to set your MMR.",
                ephemeral=True
            )
            return

        if user_id in ps.queue:
            await interaction.response.send_message("You're already in this queue!", ephemeral=True)
            return

        # Check if in another queue (Head to Head is exempt from this rule)
        if ps.playlist_type != PlaylistType.HEAD_TO_HEAD:
            # Check MLG 4v4 queue
            try:
                from searchmatchmaking import queue_state as mlg_queue
                if user_id in mlg_queue.queue:
                    await interaction.response.send_message(
                        "You're already in the **MLG 4v4** queue!\n"
                        f"Leave that queue first before joining {ps.name}.",
                        ephemeral=True
                    )
                    return
            except:
                pass

            # Check other playlist queues (except Head to Head)
            for other_ps in get_all_playlists():
                if other_ps == ps:
                    continue  # Skip self
                if other_ps.playlist_type == PlaylistType.HEAD_TO_HEAD:
                    continue  # Head to Head exempt
                if user_id in other_ps.queue:
                    await interaction.response.send_message(
                        f"You're already in the **{other_ps.name}** queue!\n"
                        f"Leave that queue first before joining {ps.name}.",
                        ephemeral=True
                    )
                    return

        if len(ps.queue) >= ps.max_players:
            await interaction.response.send_message("Queue is full!", ephemeral=True)
            return

        # Check if player is in the current match (can't queue while playing)
        if ps.current_match:
            if user_id in ps.current_match.team1 or user_id in ps.current_match.team2:
                await interaction.response.send_message("You're in the current match! Finish it first.", ephemeral=True)
                return

        # Add to queue
        ps.queue.append(user_id)
        ps.queue_join_times[user_id] = datetime.now()

        log_action(f"{interaction.user.display_name} joined {ps.name} from ping ({len(ps.queue)}/{ps.max_players})")

        await interaction.response.defer()

        # Update queue embed
        if ps.queue_channel:
            await update_playlist_embed(ps.queue_channel, ps)

        # Update or delete ping message
        await update_playlist_ping_message(interaction.guild, ps)

        # Check if queue is full
        if len(ps.queue) >= ps.max_players:
            if ps.queue_channel:
                await start_playlist_match(ps.queue_channel, ps)


async def update_playlist_ping_message(guild: discord.Guild, ps: PlaylistQueueState):
    """Update or delete the ping message based on queue state"""
    if not ps.ping_message:
        return

    current_count = len(ps.queue)

    # Delete if queue is full or empty
    if current_count >= ps.max_players or current_count == 0:
        try:
            await ps.ping_message.delete()
            ps.ping_message = None
            log_action(f"Deleted {ps.name} ping message - queue {'full' if current_count >= ps.max_players else 'empty'}")
        except:
            pass
        return

    # Update the message with just the progress image
    embed = discord.Embed(color=discord.Color.green())
    embed.set_image(url=get_queue_progress_image(current_count, ps.max_players))

    try:
        await ps.ping_message.edit(embed=embed)
    except:
        pass


async def create_playlist_embed(channel: discord.TextChannel, playlist_state: PlaylistQueueState):
    """Create or update playlist queue embed"""
    ps = playlist_state
    ps.queue_channel = channel

    embed = discord.Embed(
        title=f"{ps.name} Matchmaking",
        description=ps.config["description"],
        color=discord.Color.blue()
    )

    if ps.is_hidden and ps.queue:
        # Hidden queue - don't show who's in it
        player_list = f"**{len(ps.queue)}** player{'s' if len(ps.queue) != 1 else ''} searching..."
    elif ps.queue:
        # Show players
        lines = []
        now = datetime.now()
        for uid in ps.queue:
            join_time = ps.queue_join_times.get(uid)
            if join_time:
                elapsed = now - join_time
                total_minutes = int(elapsed.total_seconds() / 60)
                if total_minutes >= 60:
                    hours = total_minutes // 60
                    mins = total_minutes % 60
                    time_str = f"{hours}h {mins}m"
                elif total_minutes > 0:
                    time_str = f"{total_minutes}m"
                else:
                    time_str = f"{int(elapsed.total_seconds())}s"
                lines.append(f"<@{uid}> - {time_str}")
            else:
                lines.append(f"<@{uid}>")
        player_list = "\n".join(lines)
    else:
        player_list = "*No players yet*"

    embed.add_field(
        name=f"Queue ({len(ps.queue)}/{ps.max_players})",
        value=player_list,
        inline=False
    )

    if ps.paused:
        embed.add_field(name="Status", value="**PAUSED**", inline=False)
        embed.color = discord.Color.orange()

    # Add queue progress image (temporarily using 8-player images scaled for all queues)
    player_count = len(ps.queue)
    if player_count > 0:
        embed.set_image(url=get_queue_progress_image(player_count, ps.max_players))

    view = PlaylistQueueView(ps)

    # Find and update existing message
    async for message in channel.history(limit=50):
        if message.author.bot and message.embeds:
            title = message.embeds[0].title or ""
            if ps.name in title and "Matchmaking" in title:
                try:
                    await message.edit(embed=embed, view=view)
                    ps.queue_message = message
                    return
                except:
                    pass

    # Create new message
    ps.queue_message = await channel.send(embed=embed, view=view)


async def update_playlist_embed(channel: discord.TextChannel, playlist_state: PlaylistQueueState):
    """Update existing playlist embed"""
    await create_playlist_embed(channel, playlist_state)


async def start_playlist_match(channel: discord.TextChannel, playlist_state: PlaylistQueueState):
    """Start a match when queue is full - routes ALL playlists through pregame.py"""
    ps = playlist_state
    players = ps.queue[:]

    # Reset ping cooldown so players can ping again for new matches
    ps.last_ping_time = None
    log_action(f"Reset ping cooldown for {ps.name}")

    log_action(f"Starting {ps.name} match with {len(players)} players")

    # Clear queue
    ps.queue.clear()
    ps.queue_join_times.clear()

    # ALL playlists now route through pregame.py
    from pregame import start_pregame

    if ps.playlist_type == PlaylistType.MLG_4V4:
        # MLG 4v4: Use existing pregame system with team selection voting
        from searchmatchmaking import queue_state
        queue_state.queue = players
        await start_pregame(channel)
    else:
        # Team Hardcore, Double Team, Head to Head: Route through pregame with playlist params
        # pregame.py will handle auto-balance or 1v1 based on playlist config
        await start_pregame(channel, playlist_state=ps, playlist_players=players)


async def wait_for_pregame_join(guild: discord.Guild, pregame_vc: discord.VoiceChannel,
                                 players: List[int], pregame_msg: discord.Message,
                                 match, channel: discord.TextChannel) -> bool:
    """Wait for all players to join pregame VC. Returns True if all joined, False if timeout."""
    import asyncio

    timeout_seconds = 300  # 5 minutes
    check_interval = 5  # Check every 5 seconds
    elapsed = 0

    while elapsed < timeout_seconds:
        # Check who's in the pregame VC
        try:
            vc = guild.get_channel(pregame_vc.id)
            if not vc:
                return False  # VC was deleted

            members_in_vc = [m.id for m in vc.members]
            players_in_vc = [uid for uid in players if uid in members_in_vc]
            players_not_in_vc = [uid for uid in players if uid not in members_in_vc]

            # All players joined!
            if len(players_in_vc) == len(players):
                return True

            # Update embed with status
            time_remaining = timeout_seconds - elapsed
            minutes = time_remaining // 60
            seconds = time_remaining % 60

            embed = discord.Embed(
                title=f"{match.get_match_label()} - Waiting for Players",
                description=f"**{match.playlist_state.name}**\n\n⏳ Time remaining: **{minutes}:{seconds:02d}**",
                color=discord.Color.orange()
            )

            # Show who's in and who's not
            in_vc_names = []
            not_in_vc_names = []
            for uid in players:
                member = guild.get_member(uid)
                name = member.display_name if member else f"<@{uid}>"
                if uid in players_in_vc:
                    in_vc_names.append(f"✅ {name}")
                else:
                    not_in_vc_names.append(f"❌ {name}")

            all_names = in_vc_names + not_in_vc_names
            embed.add_field(
                name=f"Players ({len(players_in_vc)}/{len(players)})",
                value="\n".join(all_names),
                inline=False
            )

            embed.add_field(
                name="🔊 Join Voice Channel",
                value=f"<#{pregame_vc.id}>",
                inline=False
            )

            if match.map_name and match.gametype:
                embed.add_field(
                    name="Map & Gametype",
                    value=f"{match.map_name} - {match.gametype}",
                    inline=False
                )

            try:
                await pregame_msg.edit(embed=embed)
            except:
                pass

        except Exception as e:
            log_action(f"Error checking pregame VC: {e}")

        await asyncio.sleep(check_interval)
        elapsed += check_interval

    return False  # Timeout


async def show_playlist_match_embed(channel: discord.TextChannel, match: PlaylistMatch):
    """Show match embed for playlist match"""
    ps = match.playlist_state
    guild = channel.guild

    embed = discord.Embed(
        title=f"{match.get_match_label()} - In Progress",
        description=f"**{ps.name}**\n*Game winners will be determined from parsed stats*",
        color=discord.Color.green()
    )

    if ps.playlist_type == PlaylistType.HEAD_TO_HEAD:
        # 1v1 format
        player1 = guild.get_member(match.team1[0])
        player2 = guild.get_member(match.team2[0])
        p1_name = player1.display_name if player1 else "Player 1"
        p2_name = player2.display_name if player2 else "Player 2"

        p1_wins = match.games.count('TEAM1')
        p2_wins = match.games.count('TEAM2')

        embed.add_field(
            name="Match",
            value=f"**{p1_name}** ({p1_wins}) vs **{p2_name}** ({p2_wins})",
            inline=False
        )
    else:
        # Team format with red/blue emojis
        team1_mentions = "\n".join([f"<@{uid}>" for uid in match.team1])
        team2_mentions = "\n".join([f"<@{uid}>" for uid in match.team2])

        team1_wins = match.games.count('TEAM1')
        team2_wins = match.games.count('TEAM2')

        embed.add_field(
            name=f"🔴 Red Team - {team1_wins}",
            value=team1_mentions or "TBD",
            inline=True
        )
        embed.add_field(
            name=f"🔵 Blue Team - {team2_wins}",
            value=team2_mentions or "TBD",
            inline=True
        )

    # Show completed games (populated from parsed stats)
    if match.games:
        games_text = ""
        for i, winner in enumerate(match.games, 1):
            stats = match.game_stats.get(i, {})
            map_name = stats.get("map", "")
            gametype = stats.get("gametype", "")
            if ps.playlist_type == PlaylistType.HEAD_TO_HEAD:
                winner_label = "P1" if winner == "TEAM1" else "P2"
            else:
                winner_label = "🔴" if winner == "TEAM1" else "🔵"
            if map_name and gametype:
                games_text += f"Game {i}: {winner_label} - {map_name} - {gametype}\n"
            elif map_name:
                games_text += f"Game {i}: {winner_label} - {map_name}\n"
            else:
                games_text += f"Game {i}: {winner_label}\n"
        embed.add_field(
            name="Completed Games",
            value=games_text.strip(),
            inline=False
        )

    # Show end series votes
    votes_needed = get_end_series_votes_needed(ps.playlist_type)
    current_votes = len(match.end_series_votes)

    embed.add_field(
        name=f"End Series Votes ({current_votes}/{votes_needed})",
        value=f"{current_votes} vote{'s' if current_votes != 1 else ''} - Click End Match when your games are done",
        inline=False
    )

    view = PlaylistMatchView(match)

    # Delete old message and repost (keeps it at bottom of channel)
    if match.match_message:
        try:
            await match.match_message.delete()
        except:
            pass

    match.match_message = await channel.send(embed=embed, view=view)


class PlaylistMatchView(View):
    """View for active playlist match - only END SERIES button"""
    def __init__(self, match: PlaylistMatch):
        super().__init__(timeout=None)
        self.match = match

        # Set unique custom ID for end button
        ptype = match.playlist_state.playlist_type
        self.end_btn.custom_id = f"end_match_{ptype}_{match.match_number}"

    @discord.ui.button(label="End Match", style=discord.ButtonStyle.secondary, row=0)
    async def end_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.end_match(interaction)

    async def end_match(self, interaction: discord.Interaction):
        """Vote to end the series"""
        # Check permissions
        user_roles = [role.name for role in interaction.user.roles]
        is_staff = any(role in ["Overlord", "Staff", "Server Support"] for role in user_roles)
        all_players = self.match.team1 + self.match.team2

        if not is_staff and interaction.user.id not in all_players:
            await interaction.response.send_message("Only players or staff can vote to end!", ephemeral=True)
            return

        # Toggle vote
        user_id = interaction.user.id
        if user_id in self.match.end_series_votes:
            self.match.end_series_votes.remove(user_id)
            await interaction.response.defer()
            await show_playlist_match_embed(interaction.channel, self.match)
            return
        else:
            self.match.end_series_votes.add(user_id)

        await interaction.response.defer()

        # Check if enough votes to end
        votes_needed = get_end_series_votes_needed(self.match.playlist_state.playlist_type)
        current_votes = len(self.match.end_series_votes)

        # Staff can force end with 2 votes
        staff_votes = 0
        for uid in self.match.end_series_votes:
            member = interaction.guild.get_member(uid)
            if member:
                member_roles = [role.name for role in member.roles]
                if any(role in ["Overlord", "Staff", "Server Support"] for role in member_roles):
                    staff_votes += 1

        if current_votes >= votes_needed or staff_votes >= 2:
            await end_playlist_match(interaction.channel, self.match)
        else:
            await show_playlist_match_embed(interaction.channel, self.match)


async def end_playlist_match(channel: discord.TextChannel, match: PlaylistMatch, admin_ended: bool = False):
    """End a playlist match (can be called from vote or admin command)"""
    ps = match.playlist_state
    guild = channel.guild

    # Determine winner
    team1_wins = match.games.count('TEAM1')
    team2_wins = match.games.count('TEAM2')

    if team1_wins > team2_wins:
        result = "TEAM1_WIN"
    elif team2_wins > team1_wins:
        result = "TEAM2_WIN"
    else:
        result = "TIE"

    log_action(f"{match.get_match_label()} ended: {result} ({team1_wins}-{team2_wins})")

    # Set end time for the match
    match.end_time = datetime.now()

    # Save to history (with guild for player names)
    save_match_to_history(match, result, guild)

    # Move players to postgame voice channel before deleting VCs
    POSTGAME_VC_ID = 1424845826362048643
    postgame_vc = guild.get_channel(POSTGAME_VC_ID)
    if postgame_vc:
        all_players = match.team1 + match.team2
        for uid in all_players:
            member = guild.get_member(uid)
            if member and member.voice:
                try:
                    await member.move_to(postgame_vc)
                except:
                    pass

    # Delete voice channels
    if match.shared_vc_id:
        vc = guild.get_channel(match.shared_vc_id)
        if vc:
            try:
                await vc.delete()
            except:
                pass

    if match.team1_vc_id:
        vc = guild.get_channel(match.team1_vc_id)
        if vc:
            try:
                await vc.delete()
            except:
                pass

    if match.team2_vc_id:
        vc = guild.get_channel(match.team2_vc_id)
        if vc:
            try:
                await vc.delete()
            except:
                pass

    # Delete match message
    if match.match_message:
        try:
            await match.match_message.delete()
        except:
            pass

    # Delete general chat message if exists
    if match.general_message:
        try:
            await match.general_message.delete()
        except:
            pass

    # Delete ping message if exists
    if ps.ping_message:
        try:
            await ps.ping_message.delete()
            ps.ping_message = None
        except:
            pass

    # Clear current match
    ps.current_match = None

    # Update queue embed
    await update_playlist_embed(channel, ps)

    # Send summary
    embed = discord.Embed(
        title=f"{match.get_match_label()} - Complete",
        color=discord.Color.gold()
    )

    if ps.playlist_type == PlaylistType.HEAD_TO_HEAD:
        player1 = guild.get_member(match.team1[0])
        player2 = guild.get_member(match.team2[0])
        p1_name = player1.display_name if player1 else "Player 1"
        p2_name = player2.display_name if player2 else "Player 2"

        if result == "TEAM1_WIN":
            embed.description = f"**{p1_name}** defeats **{p2_name}**"
        elif result == "TEAM2_WIN":
            embed.description = f"**{p2_name}** defeats **{p1_name}**"
        else:
            embed.description = f"**{p1_name}** ties **{p2_name}**"
    else:
        if result == "TEAM1_WIN":
            embed.description = f"**Red Team** wins! ({team1_wins}-{team2_wins})"
        elif result == "TEAM2_WIN":
            embed.description = f"**Blue Team** wins! ({team1_wins}-{team2_wins})"
        else:
            embed.description = f"Match tied ({team1_wins}-{team2_wins})"

    await channel.send(embed=embed)

    # Record playlist-specific stats for all players
    await record_playlist_match_stats(match, guild)


async def record_playlist_match_stats(match: PlaylistMatch, guild: discord.Guild):
    """Record playlist-specific stats for all players in a match"""
    import STATSRANKS

    playlist_type = match.playlist_state.playlist_type
    xp_config = STATSRANKS.get_xp_config()

    # Count wins per team
    team1_game_wins = match.games.count('TEAM1')
    team2_game_wins = match.games.count('TEAM2')

    # Determine series winner
    if team1_game_wins > team2_game_wins:
        series_winner = "TEAM1"
    elif team2_game_wins > team1_game_wins:
        series_winner = "TEAM2"
    else:
        series_winner = "TIE"

    # Update Team 1 players
    for user_id in match.team1:
        update = {
            "wins": team1_game_wins,
            "losses": team2_game_wins,
            "xp": (team1_game_wins * xp_config["game_win"]) + (team2_game_wins * xp_config["game_loss"])
        }

        if series_winner == "TEAM1":
            update["series_wins"] = 1
        elif series_winner == "TEAM2":
            update["series_losses"] = 1

        STATSRANKS.update_playlist_stats(user_id, playlist_type, update)

    # Update Team 2 players
    for user_id in match.team2:
        update = {
            "wins": team2_game_wins,
            "losses": team1_game_wins,
            "xp": (team2_game_wins * xp_config["game_win"]) + (team1_game_wins * xp_config["game_loss"])
        }

        if series_winner == "TEAM2":
            update["series_wins"] = 1
        elif series_winner == "TEAM1":
            update["series_losses"] = 1

        STATSRANKS.update_playlist_stats(user_id, playlist_type, update)

    # Refresh ranks for all players (uses highest_rank)
    all_players = match.team1 + match.team2
    await STATSRANKS.refresh_playlist_ranks(guild, all_players, playlist_type, send_dm=True)

    log_action(f"Recorded stats for {match.get_match_label()}: {len(all_players)} players")

    # Also save to playlist-specific stats file
    save_playlist_stats(match, guild)


def save_playlist_stats(match: PlaylistMatch, guild=None):
    """Save player stats to playlist-specific stats file ({playlist}_stats.json)

    Structure per player:
    {
        "discord_id": {
            "discord_name": "PlayerName",
            "wins": 10,
            "losses": 5,
            "games_played": 15,
            "xp": 500,
            "rank": 5
        }
    }
    """
    stats_file = get_playlist_stats_file(match.playlist_type)

    # Load existing stats
    stats = {}
    if os.path.exists(stats_file):
        try:
            with open(stats_file, 'r') as f:
                stats = json.load(f)
        except:
            stats = {}

    # Count wins/losses for each player
    team1_wins = match.games.count('TEAM1')
    team2_wins = match.games.count('TEAM2')

    # Update Team 1 players
    for uid in match.team1:
        uid_str = str(uid)
        member = guild.get_member(uid) if guild else None
        name = member.display_name if member else f"Unknown ({uid})"

        if uid_str not in stats:
            stats[uid_str] = {
                "discord_name": name,
                "wins": 0,
                "losses": 0,
                "games_played": 0,
                "xp": 0,
                "rank": 1
            }

        stats[uid_str]["discord_name"] = name  # Update name in case it changed
        stats[uid_str]["wins"] += team1_wins
        stats[uid_str]["losses"] += team2_wins
        stats[uid_str]["games_played"] += team1_wins + team2_wins

    # Update Team 2 players
    for uid in match.team2:
        uid_str = str(uid)
        member = guild.get_member(uid) if guild else None
        name = member.display_name if member else f"Unknown ({uid})"

        if uid_str not in stats:
            stats[uid_str] = {
                "discord_name": name,
                "wins": 0,
                "losses": 0,
                "games_played": 0,
                "xp": 0,
                "rank": 1
            }

        stats[uid_str]["discord_name"] = name
        stats[uid_str]["wins"] += team2_wins
        stats[uid_str]["losses"] += team1_wins
        stats[uid_str]["games_played"] += team1_wins + team2_wins

    # Save stats file
    with open(stats_file, 'w') as f:
        json.dump(stats, f, indent=2)

    # Sync to GitHub
    try:
        import github_webhook
        github_webhook.push_file_to_github(stats_file, stats_file)
    except Exception as e:
        log_action(f"Failed to sync {stats_file} to GitHub: {e}")

    log_action(f"Saved stats to {stats_file}")


# Command helper functions
def pause_playlist(playlist_type: str) -> bool:
    """Pause a playlist"""
    ps = get_playlist_state(playlist_type)
    ps.paused = True
    log_action(f"Paused {ps.name}")
    return True


def resume_playlist(playlist_type: str) -> bool:
    """Resume a playlist"""
    ps = get_playlist_state(playlist_type)
    ps.paused = False
    log_action(f"Resumed {ps.name}")
    return True


def clear_playlist_queue(playlist_type: str) -> int:
    """Clear a playlist queue, returns number of players removed"""
    ps = get_playlist_state(playlist_type)
    count = len(ps.queue)
    ps.queue.clear()
    ps.queue_join_times.clear()
    log_action(f"Cleared {ps.name} queue ({count} players)")
    return count


def set_playlist_hidden(playlist_type: str, hidden: bool) -> bool:
    """Set whether a playlist queue is hidden"""
    ps = get_playlist_state(playlist_type)
    PLAYLIST_CONFIG[playlist_type]["hidden_queue"] = hidden
    log_action(f"Set {ps.name} hidden={hidden}")
    return True


async def initialize_all_playlists(bot):
    """Initialize all playlist embeds, restoring active matches from JSON if any"""
    for ptype, config in PLAYLIST_CONFIG.items():
        channel = bot.get_channel(config["channel_id"])
        if channel:
            ps = get_playlist_state(ptype)

            # Check for active matches in JSON file to restore after restart
            matches_file = get_playlist_matches_file(ptype)
            restored_match = None
            if os.path.exists(matches_file):
                try:
                    with open(matches_file, 'r') as f:
                        file_data = json.load(f)
                    active_matches = file_data.get("active_matches", [])
                    if active_matches:
                        # Restore the most recent active match
                        match_data = active_matches[-1]
                        restored_match = PlaylistMatch.restore_from_json(ps, match_data)
                        ps.current_match = restored_match
                        log_action(f"Restored {restored_match.get_match_label()} from JSON after restart")
                except Exception as e:
                    log_action(f"Failed to restore active match for {ps.name}: {e}")

            if ps.current_match:
                # Show match embed for restored active match
                await show_playlist_match_embed(channel, ps.current_match)
                log_action(f"Initialized {ps.name} with active match #{ps.current_match.match_number} in #{channel.name}")
            else:
                # Normal queue embed
                await create_playlist_embed(channel, ps)
                log_action(f"Initialized {ps.name} in #{channel.name}")
        else:
            log_action(f"Could not find channel {config['channel_id']} for {config['name']}")


async def sync_game_results_from_files(bot) -> dict:
    """
    Sync game results from playlist JSON files (updated by populate_stats.py).
    Updates in-memory match objects and refreshes embeds.

    Returns dict with counts of updates made.
    """
    results = {
        "games_added": 0,
        "matches_completed": 0,
        "embeds_updated": 0,
        "errors": []
    }

    for ptype in PLAYLIST_CONFIG.keys():
        try:
            matches_file = get_playlist_matches_file(ptype)
            if not os.path.exists(matches_file):
                continue

            with open(matches_file, 'r') as f:
                file_data = json.load(f)

            ps = get_playlist_state(ptype)

            # Check if there's an active match in memory
            if not ps.current_match:
                continue

            match = ps.current_match

            # Find this match in the file's active_matches
            active_matches = file_data.get("active_matches", [])
            file_match = None
            for am in active_matches:
                if am.get("match_number") == match.match_number:
                    file_match = am
                    break

            if not file_match:
                # Match might have been moved to completed - check matches array
                completed_matches = file_data.get("matches", [])
                for cm in completed_matches:
                    if cm.get("match_number") == match.match_number:
                        # Match was completed by populate_stats.py
                        # Update in-memory match with final results
                        games = cm.get("games", [])
                        for game in games:
                            game_num = game.get("game_number", len(match.games) + 1)
                            winner = game.get("winner")

                            # Skip ties - game will be replayed
                            if winner == "TIE" or winner == "TIED" or not winner:
                                continue

                            # Skip resets (games under 2 minutes) - game will be replayed
                            duration_seconds = game.get("duration_seconds", 9999)
                            if duration_seconds < 120:
                                continue

                            if len(match.games) < game_num:
                                match.games.append(winner)
                                match.game_stats[game_num] = {
                                    "map": game.get("map", ""),
                                    "gametype": game.get("gametype", "")
                                }
                                results["games_added"] += 1

                        # End the match
                        channel = bot.get_channel(PLAYLIST_CONFIG[ptype]["channel_id"])
                        if channel:
                            await complete_match_from_stats(channel, match, cm)
                            results["matches_completed"] += 1
                        break
                continue

            # Sync games from file to in-memory match
            file_games = file_match.get("games", [])
            games_before = len(match.games)

            for game in file_games:
                game_num = game.get("game_number", len(match.games) + 1)
                winner = game.get("winner")

                # Skip ties - game will be replayed
                if winner == "TIE" or winner == "TIED" or not winner:
                    log_action(f"Skipping tied game {game_num} in {ps.name} - will be replayed")
                    continue

                # Skip resets (games under 2 minutes) - game will be replayed
                duration_seconds = game.get("duration_seconds", 9999)
                if duration_seconds < 120:  # 2 minutes
                    log_action(f"Skipping reset game {game_num} in {ps.name} ({duration_seconds}s) - will be replayed")
                    continue

                # Only add if we don't have this game yet
                if game_num > len(match.games) and winner:
                    match.games.append(winner)
                    match.game_stats[game_num] = {
                        "map": game.get("map", ""),
                        "gametype": game.get("gametype", ""),
                        "score": game.get("score", "")
                    }
                    results["games_added"] += 1

            # Update embed if games were added
            if len(match.games) > games_before:
                channel = bot.get_channel(PLAYLIST_CONFIG[ptype]["channel_id"])
                if channel:
                    await show_playlist_match_embed(channel, match)
                    results["embeds_updated"] += 1
                    log_action(f"Updated {ps.name} match embed with {len(match.games) - games_before} new game(s)")

                # Also update the active match in file with new data
                update_active_match_in_history(match)

        except Exception as e:
            results["errors"].append(f"{ptype}: {str(e)}")
            log_action(f"Error syncing {ptype} game results: {e}")

    return results


async def complete_match_from_stats(channel: discord.TextChannel, match: PlaylistMatch, completed_data: dict):
    """
    Complete a match that was finished by populate_stats.py.
    Posts final results to channel and cleans up.
    """
    ps = match.playlist_state
    guild = channel.guild

    # Set end time from file data
    end_time_str = completed_data.get("end_time")
    if end_time_str:
        match.end_time = datetime.fromisoformat(end_time_str)
    else:
        match.end_time = datetime.now()

    # Determine winner
    team1_wins = match.games.count('TEAM1')
    team2_wins = match.games.count('TEAM2')

    result = completed_data.get("result", "TIE")

    log_action(f"{match.get_match_label()} completed from stats: {result} ({team1_wins}-{team2_wins})")

    # Post final results embed
    await post_match_results(channel, match, result)

    # Move players to postgame if they're still in match VCs
    POSTGAME_VC_ID = 1424845826362048643
    postgame_vc = guild.get_channel(POSTGAME_VC_ID)
    if postgame_vc:
        all_players = match.team1 + match.team2
        for uid in all_players:
            member = guild.get_member(uid)
            if member and member.voice:
                # Check if they're in one of the match VCs
                if member.voice.channel and member.voice.channel.id in [match.team1_vc_id, match.team2_vc_id, match.shared_vc_id]:
                    try:
                        await member.move_to(postgame_vc)
                    except:
                        pass

    # Delete match VCs
    for vc_id in [match.shared_vc_id, match.team1_vc_id, match.team2_vc_id]:
        if vc_id:
            vc = guild.get_channel(vc_id)
            if vc:
                try:
                    await vc.delete()
                except:
                    pass

    # Delete match embed
    if match.match_message:
        try:
            await match.match_message.delete()
        except:
            pass

    # Clear current match
    ps.current_match = None

    # Update queue embed
    await update_playlist_embed(channel, ps)

    # Refresh ranks for all players (with DMs)
    import STATSRANKS
    all_players = match.team1 + match.team2
    await STATSRANKS.refresh_playlist_ranks(guild, all_players, ps.playlist_type, send_dm=True)

    log_action(f"Completed {match.get_match_label()} from populate_stats.py")


async def post_match_results(channel: discord.TextChannel, match: PlaylistMatch, result: str):
    """
    Post final match results to the playlist channel.
    Format for teams: {winning team logo} {color} Team won {gametype} on {map} - {score}
    Format for 1v1: {winner_name} won {gametype} on {map}! (with winner's emblem as thumbnail)
    """
    ps = match.playlist_state
    guild = channel.guild

    # Team emoji IDs
    RED_TEAM_EMOJI_ID = 1442675426886418522
    BLUE_TEAM_EMOJI_ID = 1442675472428433438
    red_logo = f"<:redteam:{RED_TEAM_EMOJI_ID}>"
    blue_logo = f"<:blueteam:{BLUE_TEAM_EMOJI_ID}>"

    team1_wins = match.games.count('TEAM1')
    team2_wins = match.games.count('TEAM2')

    # Determine embed color based on winner
    if result == "TEAM1_WIN":
        color = discord.Color.red()
    elif result == "TEAM2_WIN":
        color = discord.Color.blue()
    else:
        color = discord.Color.gold()

    embed = discord.Embed(
        title=f"{match.get_match_label()} - Complete",
        color=color
    )

    # Winner announcement
    if ps.playlist_type == PlaylistType.HEAD_TO_HEAD:
        player1 = guild.get_member(match.team1[0])
        player2 = guild.get_member(match.team2[0])
        p1_name = player1.display_name if player1 else "Player 1"
        p2_name = player2.display_name if player2 else "Player 2"

        if result == "TEAM1_WIN":
            embed.description = f"**{p1_name}** defeats **{p2_name}** ({team1_wins}-{team2_wins})"
            winner_id = match.team1[0]
        elif result == "TEAM2_WIN":
            embed.description = f"**{p2_name}** defeats **{p1_name}** ({team2_wins}-{team1_wins})"
            winner_id = match.team2[0]
        else:
            embed.description = f"**{p1_name}** ties **{p2_name}** ({team1_wins}-{team2_wins})"
            winner_id = None

        # Set winner's emblem as thumbnail for Head to Head
        if winner_id:
            try:
                import STATSRANKS
                from github_webhook import async_pull_emblems_from_github
                emblems = await async_pull_emblems_from_github() or {}
                user_key = str(winner_id)
                if user_key in emblems:
                    emblem_url = emblems[user_key].get("emblem_url") if isinstance(emblems[user_key], dict) else emblems[user_key]
                    if emblem_url:
                        emblem_png = STATSRANKS.get_emblem_png_url(emblem_url)
                        if emblem_png:
                            embed.set_thumbnail(url=emblem_png)
            except Exception as e:
                log_action(f"Failed to load winner emblem: {e}")
    else:
        if result == "TEAM1_WIN":
            embed.description = f"{red_logo} **Red Team** wins! ({team1_wins}-{team2_wins})"
        elif result == "TEAM2_WIN":
            embed.description = f"{blue_logo} **Blue Team** wins! ({team1_wins}-{team2_wins})"
        else:
            embed.description = f"Match tied ({team1_wins}-{team2_wins})"

    # Game-by-game results
    if match.games:
        games_text = ""
        for i, winner in enumerate(match.games, 1):
            stats = match.game_stats.get(i, {})
            map_name = stats.get("map", "Unknown")
            gametype = stats.get("gametype", "")
            score = stats.get("score", "")

            if ps.playlist_type == PlaylistType.HEAD_TO_HEAD:
                # Format: {winner_name} won {gametype} on {map}!
                player1 = guild.get_member(match.team1[0])
                player2 = guild.get_member(match.team2[0])
                p1_name = player1.display_name if player1 else "Player 1"
                p2_name = player2.display_name if player2 else "Player 2"

                winner_name = p1_name if winner == "TEAM1" else p2_name
                if gametype:
                    games_text += f"**{winner_name}** won {gametype} on {map_name}!\n"
                else:
                    games_text += f"**{winner_name}** won on {map_name}!\n"
            else:
                # Format: {logo} {Color} Team won {gametype} on {map} - {score}
                if winner == "TEAM1":
                    logo = red_logo
                    team_color = "Red"
                else:
                    logo = blue_logo
                    team_color = "Blue"

                if gametype and score:
                    games_text += f"{logo} **{team_color} Team** won {gametype} on {map_name} - {score}\n"
                elif gametype:
                    games_text += f"{logo} **{team_color} Team** won {gametype} on {map_name}\n"
                else:
                    games_text += f"{logo} **{team_color} Team** won on {map_name}\n"

        embed.add_field(
            name="Game Results",
            value=games_text.strip(),
            inline=False
        )

    await channel.send(embed=embed)
    log_action(f"Posted final results for {match.get_match_label()}")


# Export
__all__ = [
    'PlaylistType',
    'PLAYLIST_CONFIG',
    'PLAYLIST_MATCHES_FILES',
    'PLAYLIST_STATS_FILES',
    'GAMETYPE_SIMPLE',
    'PlaylistQueueView',
    'PlaylistPingJoinView',
    'PlaylistMatchView',
    'get_playlist_state',
    'get_playlist_by_channel',
    'get_all_playlists',
    'get_playlist_matches_file',
    'get_playlist_stats_file',
    'simplify_gametype',
    'create_playlist_embed',
    'update_playlist_embed',
    'start_playlist_match',
    'end_playlist_match',
    'save_match_to_history',
    'update_active_match_in_history',
    'save_playlist_stats',
    'pause_playlist',
    'resume_playlist',
    'clear_playlist_queue',
    'set_playlist_hidden',
    'initialize_all_playlists',
    'sync_game_results_from_files',
    'complete_match_from_stats',
    'post_match_results',
]
