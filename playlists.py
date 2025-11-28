# playlists.py - Multi-Playlist Queue System

MODULE_VERSION = "1.0.0"

import discord
from discord.ui import View, Button
from typing import List, Optional, Dict, Tuple
from datetime import datetime, timedelta
import asyncio
import random
import json
import os

# Header image for embeds
HEADER_IMAGE_URL = "https://raw.githubusercontent.com/I2aMpAnT/H2CarnageReport.com/main/MessagefromCarnageReportHEADER.png"

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

# Match history file
MATCH_HISTORY_FILE = "match_history.json"


def log_action(message: str):
    """Log actions to log.txt"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
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

        self.games: List[str] = []  # 'TEAM1' or 'TEAM2'
        self.game_stats: Dict[int, dict] = {}
        self.current_game = 1

        # Selected map/gametype for auto-queue playlists
        self.map_name: Optional[str] = None
        self.gametype: Optional[str] = None

        # Voice channel IDs
        self.team1_vc_id: Optional[int] = None
        self.team2_vc_id: Optional[int] = None
        self.shared_vc_id: Optional[int] = None  # For Head to Head

        # Message references
        self.match_message: Optional[discord.Message] = None
        self.general_message: Optional[discord.Message] = None

        self.start_time = datetime.now()
        self.end_series_votes: set = set()  # User IDs who voted to end

    def get_match_label(self) -> str:
        """Get display label for this match"""
        return f"{self.playlist_state.name} #{self.match_number}"


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
    """Get the queue progress image URL for current player count.
    Temporarily using 8-player images for all queues - scales smaller queues to 8."""
    # Scale to 8-player images temporarily
    if max_players == 8:
        scaled_count = player_count
    elif max_players == 4:
        # 2v2: 1->2, 2->4, 3->6, 4->8
        scaled_count = player_count * 2
    elif max_players == 2:
        # 1v1: 1->4, 2->8
        scaled_count = player_count * 4
    else:
        scaled_count = player_count

    if scaled_count < 1:
        return f"{MATCHMAKING_IMAGE_BASE}/1outof8.png"
    if scaled_count > 8:
        scaled_count = 8
    return f"{MATCHMAKING_IMAGE_BASE}/{scaled_count}outof8.png"


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
    """Balance players into two teams based on MMR"""
    # Get all player MMRs
    player_mmrs = {}
    for uid in players:
        player_mmrs[uid] = await get_player_mmr(uid)

    # Sort by MMR (highest first)
    sorted_players = sorted(players, key=lambda x: player_mmrs[x], reverse=True)

    # Snake draft for balance
    team1 = []
    team2 = []

    for i, player in enumerate(sorted_players):
        if i % 2 == 0:
            if len(team1) < team_size:
                team1.append(player)
            else:
                team2.append(player)
        else:
            if len(team2) < team_size:
                team2.append(player)
            else:
                team1.append(player)

    # Try swapping to optimize
    best_diff = abs(sum(player_mmrs[u] for u in team1) - sum(player_mmrs[u] for u in team2))
    best_team1 = team1[:]
    best_team2 = team2[:]

    for t1_player in team1:
        for t2_player in team2:
            test_team1 = [p if p != t1_player else t2_player for p in team1]
            test_team2 = [p if p != t2_player else t1_player for p in team2]

            diff = abs(sum(player_mmrs[u] for u in test_team1) - sum(player_mmrs[u] for u in test_team2))
            if diff < best_diff:
                best_diff = diff
                best_team1 = test_team1[:]
                best_team2 = test_team2[:]

    log_action(f"Balanced teams - MMR diff: {best_diff}")
    return best_team1, best_team2


def save_match_to_history(match: PlaylistMatch, result: str):
    """Save match to history file"""
    history = {}
    if os.path.exists(MATCH_HISTORY_FILE):
        try:
            with open(MATCH_HISTORY_FILE, 'r') as f:
                history = json.load(f)
        except:
            history = {}

    playlist_key = match.playlist_type
    if playlist_key not in history:
        history[playlist_key] = []

    match_data = {
        "match_number": match.match_number,
        "timestamp": match.start_time.isoformat(),
        "players": match.players,
        "team1": match.team1,
        "team2": match.team2,
        "map": match.map_name,
        "gametype": match.gametype,
        "games": match.games,
        "result": result,
    }

    history[playlist_key].append(match_data)

    with open(MATCH_HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=2)

    log_action(f"Saved {match.get_match_label()} to history")


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

        if len(ps.queue) >= ps.max_players:
            await interaction.response.send_message("Queue is full!", ephemeral=True)
            return

        if ps.current_match:
            await interaction.response.send_message("Match in progress!", ephemeral=True)
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

        # Create ping embed
        current_count = len(ps.queue)
        needed = ps.max_players - current_count

        embed = discord.Embed(
            title=f"{ps.name} - Players Needed!",
            description=f"We have **{current_count}/{ps.max_players}** players searching.\nNeed **{needed}** more to start!",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=HEADER_IMAGE_URL)

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

        if len(ps.queue) >= ps.max_players:
            await interaction.response.send_message("Queue is full!", ephemeral=True)
            return

        if ps.current_match:
            await interaction.response.send_message("Match in progress!", ephemeral=True)
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

    # Update the message
    needed = ps.max_players - current_count

    embed = discord.Embed(
        title=f"{ps.name} - Players Needed!",
        description=f"We have **{current_count}/{ps.max_players}** players searching.\nNeed **{needed}** more to start!",
        color=discord.Color.green()
    )
    embed.set_thumbnail(url=HEADER_IMAGE_URL)

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
    """Start a match when queue is full"""
    ps = playlist_state
    players = ps.queue[:]

    log_action(f"Starting {ps.name} match with {len(players)} players")

    # Clear queue
    ps.queue.clear()
    ps.queue_join_times.clear()

    # Select map/gametype for auto-queue playlists
    map_name, gametype = ("", "")
    if ps.config["show_map_gametype"]:
        map_name, gametype = select_random_map_gametype(ps.playlist_type)

    # Balance teams or assign players
    if ps.playlist_type == PlaylistType.HEAD_TO_HEAD:
        # 1v1 - no teams, just two players
        team1 = [players[0]]
        team2 = [players[1]]
    elif ps.auto_balance:
        # Auto-balance by MMR
        team1, team2 = await balance_teams_by_mmr(players, ps.team_size)
    else:
        # MLG 4v4 - will use team selection (handled separately in pregame)
        # For now, just create the match and proceed to pregame
        team1 = []
        team2 = []

    # Create match object
    match = PlaylistMatch(ps, players, team1, team2)
    match.map_name = map_name
    match.gametype = gametype
    ps.current_match = match

    # For MLG 4v4, go to team selection (use existing pregame system)
    if ps.playlist_type == PlaylistType.MLG_4V4:
        # Use existing pregame system
        from pregame import start_pregame
        from searchmatchmaking import queue_state
        queue_state.queue = players
        await start_pregame(channel)
        return

    # For other playlists, create voice channels and show match embed
    guild = channel.guild
    voice_category_id = 1403916181554860112
    category = guild.get_channel(voice_category_id)

    if ps.playlist_type == PlaylistType.HEAD_TO_HEAD:
        # Create shared voice channel for 1v1
        player1 = guild.get_member(team1[0])
        player2 = guild.get_member(team2[0])
        p1_name = player1.display_name if player1 else "Player 1"
        p2_name = player2.display_name if player2 else "Player 2"

        vc = await guild.create_voice_channel(
            name=f"{p1_name} vs {p2_name}",
            category=category,
            user_limit=4
        )
        match.shared_vc_id = vc.id

        # Move players
        for uid in players:
            member = guild.get_member(uid)
            if member and member.voice:
                try:
                    await member.move_to(vc)
                except:
                    pass
    else:
        # Create team voice channels for 2v2 or 4v4
        team1_mmrs = [await get_player_mmr(uid) for uid in team1]
        team2_mmrs = [await get_player_mmr(uid) for uid in team2]
        team1_avg = int(sum(team1_mmrs) / len(team1_mmrs)) if team1_mmrs else 1500
        team2_avg = int(sum(team2_mmrs) / len(team2_mmrs)) if team2_mmrs else 1500

        match_label = match.get_match_label()

        team1_vc = await guild.create_voice_channel(
            name=f"Red {match_label} - {team1_avg} MMR",
            category=category,
            user_limit=ps.team_size + 2
        )
        team2_vc = await guild.create_voice_channel(
            name=f"Blue {match_label} - {team2_avg} MMR",
            category=category,
            user_limit=ps.team_size + 2
        )

        match.team1_vc_id = team1_vc.id
        match.team2_vc_id = team2_vc.id

        # Move players
        for uid in team1:
            member = guild.get_member(uid)
            if member and member.voice:
                try:
                    await member.move_to(team1_vc)
                except:
                    pass

        for uid in team2:
            member = guild.get_member(uid)
            if member and member.voice:
                try:
                    await member.move_to(team2_vc)
                except:
                    pass

    # Show match embed
    await show_playlist_match_embed(channel, match)

    # Update queue embed to show "match in progress"
    await update_playlist_embed(channel, ps)

    # Save to history
    save_match_to_history(match, "STARTED")


async def show_playlist_match_embed(channel: discord.TextChannel, match: PlaylistMatch):
    """Show match embed for playlist match"""
    ps = match.playlist_state
    guild = channel.guild

    embed = discord.Embed(
        title=f"{match.get_match_label()} - In Progress",
        description=f"**{ps.name}**",
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
        # Team format
        team1_mentions = "\n".join([f"<@{uid}>" for uid in match.team1])
        team2_mentions = "\n".join([f"<@{uid}>" for uid in match.team2])

        team1_wins = match.games.count('TEAM1')
        team2_wins = match.games.count('TEAM2')

        embed.add_field(
            name=f"Red Team - {team1_wins}",
            value=team1_mentions or "TBD",
            inline=True
        )
        embed.add_field(
            name=f"Blue Team - {team2_wins}",
            value=team2_mentions or "TBD",
            inline=True
        )

    # Show completed games
    if match.games:
        games_text = ""
        for i, winner in enumerate(match.games, 1):
            stats = match.game_stats.get(i, {})
            map_name = stats.get("map", "")
            if ps.playlist_type == PlaylistType.HEAD_TO_HEAD:
                winner_label = "P1" if winner == "TEAM1" else "P2"
            else:
                winner_label = "🔴" if winner == "TEAM1" else "🔵"
            if map_name:
                games_text += f"Game {i}: {winner_label} - {map_name}\n"
            else:
                games_text += f"Game {i}: {winner_label}\n"
        embed.add_field(
            name="Completed Games",
            value=games_text.strip(),
            inline=False
        )

    # Show next map/gametype
    if match.map_name and match.gametype:
        embed.add_field(
            name=f"Game {match.current_game} - Next Map",
            value=f"**{match.map_name}** - {match.gametype}",
            inline=False
        )

    # Show end series votes
    votes_needed = get_end_series_votes_needed(ps.playlist_type)
    current_votes = len(match.end_series_votes)
    total_players = len(match.team1) + len(match.team2)

    embed.add_field(
        name=f"End Series Votes ({current_votes}/{votes_needed})",
        value=f"{current_votes} vote{'s' if current_votes != 1 else ''} to end",
        inline=False
    )

    view = PlaylistMatchView(match)

    # Find and update existing match message
    if match.match_message:
        try:
            await match.match_message.edit(embed=embed, view=view)
            return
        except:
            pass

    match.match_message = await channel.send(embed=embed, view=view)


class PlaylistMatchView(View):
    """View for active playlist match with voting buttons"""
    def __init__(self, match: PlaylistMatch):
        super().__init__(timeout=None)
        self.match = match

        # Customize based on playlist type
        if match.playlist_state.playlist_type == PlaylistType.HEAD_TO_HEAD:
            self.team1_btn.label = "Player 1 Wins"
            self.team2_btn.label = "Player 2 Wins"
        else:
            self.team1_btn.label = f"Red Team Wins Game {match.current_game}"
            self.team2_btn.label = f"Blue Team Wins Game {match.current_game}"

        # Set unique custom IDs
        ptype = match.playlist_state.playlist_type
        self.team1_btn.custom_id = f"vote_team1_{ptype}_{match.match_number}"
        self.team2_btn.custom_id = f"vote_team2_{ptype}_{match.match_number}"
        self.end_btn.custom_id = f"end_match_{ptype}_{match.match_number}"

    @discord.ui.button(label="Red Team Wins", style=discord.ButtonStyle.danger, row=0)
    async def team1_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_vote(interaction, 'TEAM1')

    @discord.ui.button(label="Blue Team Wins", style=discord.ButtonStyle.primary, row=1)
    async def team2_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_vote(interaction, 'TEAM2')

    @discord.ui.button(label="End Match", style=discord.ButtonStyle.secondary, row=2)
    async def end_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.end_match(interaction)

    async def process_vote(self, interaction: discord.Interaction, winner: str):
        """Process game winner vote"""
        # Check if user is a player or staff
        all_players = self.match.team1 + self.match.team2
        user_roles = [role.name for role in interaction.user.roles]
        is_staff = any(role in ["Overlord", "Staff", "Server Tech Support"] for role in user_roles)

        if not is_staff and interaction.user.id not in all_players:
            await interaction.response.send_message("Only players or staff can vote!", ephemeral=True)
            return

        # Record game winner with current map/gametype
        self.match.games.append(winner)
        self.match.game_stats[len(self.match.games)] = {
            "map": self.match.map_name,
            "gametype": self.match.gametype
        }
        self.match.current_game += 1

        log_action(f"{self.match.get_match_label()} - Game {len(self.match.games)} won by {winner} on {self.match.map_name}")

        await interaction.response.defer()

        # Select NEW random map/gametype for next game
        new_map, new_gametype = select_random_map_gametype(self.match.playlist_state.playlist_type)
        self.match.map_name = new_map
        self.match.gametype = new_gametype

        # Update buttons
        if self.match.playlist_state.playlist_type == PlaylistType.HEAD_TO_HEAD:
            self.team1_btn.label = "Player 1 Wins"
            self.team2_btn.label = "Player 2 Wins"
        else:
            self.team1_btn.label = f"Red Team Wins Game {self.match.current_game}"
            self.team2_btn.label = f"Blue Team Wins Game {self.match.current_game}"

        await show_playlist_match_embed(interaction.channel, self.match)

    async def end_match(self, interaction: discord.Interaction):
        """Vote to end the series"""
        # Check permissions
        user_roles = [role.name for role in interaction.user.roles]
        is_staff = any(role in ["Overlord", "Staff", "Server Tech Support"] for role in user_roles)
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
                if any(role in ["Overlord", "Staff", "Server Tech Support"] for role in member_roles):
                    staff_votes += 1

        if current_votes >= votes_needed or staff_votes >= 2:
            await end_playlist_match(interaction.channel, self.match)
        else:
            await show_playlist_match_embed(interaction.channel, self.match)


async def end_playlist_match(channel: discord.TextChannel, match: PlaylistMatch):
    """End a playlist match"""
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

    # Save to history
    save_match_to_history(match, result)

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
    """Initialize all playlist embeds"""
    for ptype, config in PLAYLIST_CONFIG.items():
        channel = bot.get_channel(config["channel_id"])
        if channel:
            ps = get_playlist_state(ptype)
            await create_playlist_embed(channel, ps)
            log_action(f"Initialized {ps.name} in #{channel.name}")
        else:
            log_action(f"Could not find channel {config['channel_id']} for {config['name']}")


# Export
__all__ = [
    'PlaylistType',
    'PLAYLIST_CONFIG',
    'PlaylistQueueView',
    'PlaylistPingJoinView',
    'PlaylistMatchView',
    'get_playlist_state',
    'get_playlist_by_channel',
    'get_all_playlists',
    'create_playlist_embed',
    'update_playlist_embed',
    'start_playlist_match',
    'end_playlist_match',
    'pause_playlist',
    'resume_playlist',
    'clear_playlist_queue',
    'set_playlist_hidden',
    'initialize_all_playlists',
]
