# searchmatchmaking.py - MLG 4v4 Queue Management System
# !! REMEMBER TO UPDATE VERSION NUMBER WHEN MAKING CHANGES !!

MODULE_VERSION = "1.7.0"

import discord
from discord.ui import View, Button
from typing import List, Optional
from datetime import datetime, timedelta
import asyncio

# Header image for embeds and DMs
HEADER_IMAGE_URL = "https://raw.githubusercontent.com/I2aMpAnT/H2CarnageReport.com/main/MessagefromCarnageReportHEADERSMALL.png"

# Matchmaking progress images (1-8 players)
MATCHMAKING_IMAGE_BASE = "https://raw.githubusercontent.com/I2aMpAnT/H2CarnageReport.com/main/assets/matchmaking"

# Queue channel IDs (will be set by bot.py)
QUEUE_CHANNEL_ID = None
QUEUE_CHANNEL_ID_2 = None  # Second MLG 4v4 queue channel
QUEUE_2_BANNED_ROLE = None  # Role banned from queue 2

def get_queue_progress_image(player_count: int) -> str:
    """Get the queue progress image URL for current player count, or None if empty"""
    if player_count < 1:
        return None  # No image for empty queue
    if player_count > 8:
        player_count = 8
    return f"{MATCHMAKING_IMAGE_BASE}/{player_count}outof8.png"

# Queue State
class QueueState:
    def __init__(self):
        self.queue: List[int] = []
        self.queue_join_times: dict = {}  # user_id -> datetime (when they joined, for display)
        self.last_activity_times: dict = {}  # user_id -> datetime (for inactivity check)
        self.current_series = None
        self.pregame_timer_task: Optional[asyncio.Task] = None
        self.pregame_timer_end: Optional[datetime] = None
        self.recent_action: Optional[dict] = None
        self.test_mode: bool = False  # Kid mode is a crybaby
        self.test_team: Optional[str] = None
        self.testers: List[int] = []  # List of tester IDs who can vote in test mode
        self.pregame_vc_id: Optional[int] = None  # Temporary pregame voice channel
        self.pregame_message: Optional[discord.Message] = None  # Pregame embed message
        self.auto_update_task: Optional[asyncio.Task] = None  # Auto-update task
        self.queue_channel: Optional[discord.TextChannel] = None  # Store channel for updates
        self.last_ping_time: Optional[datetime] = None  # Last time ping was used
        self.ping_message: Optional[discord.Message] = None  # Ping message in general chat
        self.hide_player_names: bool = False  # Hide player names in queue list
        self.guests: dict = {}  # guest_id -> {"host_id": int, "mmr": int, "name": str}
        self.guest_counter: int = 1000000  # Start guest IDs at 1 million to avoid conflicts
        self.paused: bool = False  # Matchmaking paused flag
        self.inactivity_pending: dict = {}  # user_id -> {"prompt_time": datetime, "dm_message": Message, "general_message": Message}
        self.inactivity_timer_task: Optional[asyncio.Task] = None  # Background task for inactivity checks
        self.locked: bool = False  # Queue locked when full - prevents leaving
        self.locked_players: List[int] = []  # Players locked into current match
        self.series_text_channel_id: Optional[int] = None  # Series text channel (created early, renamed when teams set)
        self.pending_match_number: Optional[int] = None  # Match number assigned when queue fills (for early role assignment)

# Global queue states - separate queues for each channel
queue_state = QueueState()  # Primary MLG 4v4 queue
queue_state_2 = QueueState()  # Second MLG 4v4 queue (with banned role restriction)

def get_queue_state(channel_id: int):
    """Get the appropriate queue state based on channel ID"""
    if channel_id == QUEUE_CHANNEL_ID_2:
        return queue_state_2
    return queue_state

# Constants (will be imported from bot.py)
MAX_QUEUE_SIZE = 8
PREGAME_TIMER_SECONDS = 60
GENERAL_CHANNEL_ID = 1403855176460406805
PING_COOLDOWN_MINUTES = 15
INACTIVITY_CHECK_MINUTES = 60  # Time before prompting user (1 hour)
INACTIVITY_RESPONSE_MINUTES = 5  # Time user has to respond

def log_action(message: str):
    """Log actions to log.txt (EST timezone)"""
    from datetime import timezone, timedelta
    EST = timezone(timedelta(hours=-5))
    timestamp = datetime.now(EST).strftime('%Y-%m-%d %H:%M:%S EST')
    with open('log.txt', 'a') as f:
        f.write(f"[{timestamp}] {message}\n")
    print(f"[LOG] {message}")


async def remove_players_from_other_queues(guild: discord.Guild, player_ids: list, current_queue=None):
    """Remove matched players from all other queues they might be in"""
    removed_from = []

    # Remove from other MLG 4v4 queue
    other_qs = queue_state_2 if current_queue == queue_state else queue_state
    for user_id in player_ids:
        if user_id in other_qs.queue:
            other_qs.queue.remove(user_id)
            if user_id in other_qs.queue_join_times:
                del other_qs.queue_join_times[user_id]
            if user_id in other_qs.last_activity_times:
                del other_qs.last_activity_times[user_id]
            removed_from.append(f"MLG 4v4 {'(Restricted)' if other_qs == queue_state_2 else ''}")

    # Remove from playlist queues
    try:
        from playlists import get_all_playlists
        for ps in get_all_playlists():
            for user_id in player_ids:
                if user_id in ps.queue:
                    ps.queue.remove(user_id)
                    if user_id in ps.queue_join_times:
                        del ps.queue_join_times[user_id]
                    removed_from.append(ps.name)
    except:
        pass

    if removed_from:
        log_action(f"Removed {len(player_ids)} matched players from other queues: {', '.join(set(removed_from))}")

    # Update other queue embeds
    if other_qs.queue_channel:
        try:
            await update_queue_embed(other_qs.queue_channel, other_qs)
        except:
            pass


async def add_active_match_roles(guild: discord.Guild, player_ids: list, playlist_name: str, match_number: int):
    """
    Add active matchmaking roles to players when they're locked into a match.
    - Removes SearchingMatchmaking role
    - Adds ActiveMatchmaking role (creates if doesn't exist)
    - Adds active{playlist}{match#} role (creates for this match)
    """
    # Clean playlist name for role (remove spaces)
    clean_playlist = playlist_name.replace(" ", "").replace("_", "")
    match_role_name = f"Active{clean_playlist}Match{match_number}"

    # Get or create ActiveMatchmaking role
    active_mm_role = discord.utils.get(guild.roles, name="ActiveMatchmaking")
    if not active_mm_role:
        try:
            active_mm_role = await guild.create_role(
                name="ActiveMatchmaking",
                color=discord.Color.orange(),
                reason="Auto-created for active match tracking"
            )
            log_action(f"Created ActiveMatchmaking role")
        except Exception as e:
            log_action(f"Failed to create ActiveMatchmaking role: {e}")

    # Create match-specific role
    match_role = discord.utils.get(guild.roles, name=match_role_name)
    if not match_role:
        try:
            match_role = await guild.create_role(
                name=match_role_name,
                color=discord.Color.purple(),
                reason=f"Auto-created for {playlist_name} Match #{match_number}"
            )
            log_action(f"Created role: {match_role_name}")
        except Exception as e:
            log_action(f"Failed to create {match_role_name} role: {e}")

    # Get SearchingMatchmaking role to remove
    searching_role = discord.utils.get(guild.roles, name="SearchingMatchmaking")

    # Apply roles to all players
    for user_id in player_ids:
        member = guild.get_member(user_id)
        if not member:
            continue

        try:
            # Remove searching role
            if searching_role and searching_role in member.roles:
                await member.remove_roles(searching_role)

            # Add active roles
            roles_to_add = []
            if active_mm_role:
                roles_to_add.append(active_mm_role)
            if match_role:
                roles_to_add.append(match_role)

            if roles_to_add:
                await member.add_roles(*roles_to_add)
        except Exception as e:
            log_action(f"Failed to update roles for {member.display_name}: {e}")

    log_action(f"Added active match roles to {len(player_ids)} players: ActiveMatchmaking + {match_role_name}")


async def remove_active_match_roles(guild: discord.Guild, player_ids: list, playlist_name: str, match_number: int):
    """
    Remove active matchmaking roles from players when series ends or is cancelled.
    - Removes ActiveMatchmaking role (only if no other active matches)
    - Removes and deletes the active{playlist}{match#} role
    """
    # Clean playlist name for role
    clean_playlist = playlist_name.replace(" ", "").replace("_", "")
    match_role_name = f"Active{clean_playlist}Match{match_number}"

    # Get roles
    active_mm_role = discord.utils.get(guild.roles, name="ActiveMatchmaking")
    match_role = discord.utils.get(guild.roles, name=match_role_name)

    # Remove roles from players
    for user_id in player_ids:
        member = guild.get_member(user_id)
        if not member:
            continue

        try:
            roles_to_remove = []
            if match_role and match_role in member.roles:
                roles_to_remove.append(match_role)

            # Check if player has any OTHER active match roles before removing ActiveMatchmaking
            if active_mm_role and active_mm_role in member.roles:
                has_other_active = False
                for role in member.roles:
                    if role.name.startswith("Active") and role.name != "ActiveMatchmaking" and role.name != match_role_name:
                        has_other_active = True
                        break
                if not has_other_active:
                    roles_to_remove.append(active_mm_role)

            if roles_to_remove:
                await member.remove_roles(*roles_to_remove)
        except Exception as e:
            log_action(f"Failed to remove roles from {member.display_name}: {e}")

    # Delete the match-specific role
    if match_role:
        try:
            await match_role.delete(reason=f"Match #{match_number} ended")
            log_action(f"Deleted role: {match_role_name}")
        except Exception as e:
            log_action(f"Failed to delete {match_role_name} role: {e}")

    log_action(f"Removed active match roles from {len(player_ids)} players for {playlist_name} Match #{match_number}")


async def auto_update_queue_times(qs=None):
    """Background task to update queue times every 10 seconds"""
    if qs is None:
        qs = queue_state  # Default to primary queue

    await asyncio.sleep(5)  # Wait 5 seconds on startup

    while True:
        try:
            # Only update if there are players in queue
            if qs.queue and qs.queue_channel:
                await update_queue_embed(qs.queue_channel, qs)
            await asyncio.sleep(10)  # Update every 10 seconds
        except asyncio.CancelledError:
            break
        except Exception as e:
            log_action(f"Error in auto-update: {e}")
            await asyncio.sleep(10)


class InactivityConfirmView(View):
    """View for inactivity confirmation with Yes/No buttons - uses dynamic custom_ids"""
    def __init__(self, user_id: int, qs=None):
        super().__init__(timeout=INACTIVITY_RESPONSE_MINUTES * 60)  # 5 minute timeout
        self.user_id = user_id
        self.responded = False
        self.qs = qs if qs else queue_state  # Store which queue this belongs to

        # Add buttons with dynamic custom_ids (include user_id so each user has unique buttons)
        yes_button = Button(
            label="Yes, Keep Me In Queue",
            style=discord.ButtonStyle.success,
            custom_id=f"inactivity_yes_{user_id}"
        )
        yes_button.callback = self.stay_in_queue
        self.add_item(yes_button)

        no_button = Button(
            label="No, Remove Me",
            style=discord.ButtonStyle.danger,
            custom_id=f"inactivity_no_{user_id}"
        )
        no_button.callback = self.leave_queue_btn
        self.add_item(no_button)

    async def stay_in_queue(self, interaction: discord.Interaction):
        """User wants to stay in queue"""
        # Only the original user can respond
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This confirmation is not for you!", ephemeral=True)
            return

        self.responded = True

        # Reset their activity time to give them another hour (keep original join time for display)
        if self.user_id in self.qs.queue:
            self.qs.last_activity_times[self.user_id] = datetime.now()
            log_action(f"User {interaction.user.display_name} confirmed to stay in queue - activity timer reset")

            # Clean up pending confirmation
            await cleanup_inactivity_messages(self.user_id, self.qs)

            # Update the message to show confirmation
            try:
                await interaction.response.edit_message(
                    content="✅ **You've been kept in the queue!** Your timer has been reset for another hour.",
                    embed=None,
                    view=None
                )
            except discord.errors.InteractionResponded:
                await interaction.followup.send("✅ You've been kept in the queue!", ephemeral=True)
            except:
                pass

            # Update queue embed
            if self.qs.queue_channel:
                await update_queue_embed(self.qs.queue_channel, self.qs)
        else:
            await interaction.response.send_message("You're no longer in the queue.", ephemeral=True)

    async def leave_queue_btn(self, interaction: discord.Interaction):
        """User wants to leave queue"""
        # Only the original user can respond
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This confirmation is not for you!", ephemeral=True)
            return

        # Check if user is locked into a match
        if self.user_id in self.qs.locked_players:
            await interaction.response.send_message("❌ Queue is locked! You cannot leave once the match has started.", ephemeral=True)
            return

        self.responded = True

        # Remove from queue
        if self.user_id in self.qs.queue:
            # Get guild - use interaction.guild if available, otherwise get from queue_channel (for DM buttons)
            guild = interaction.guild or (self.qs.queue_channel.guild if self.qs.queue_channel else None)
            if guild:
                await remove_inactive_user(guild, self.user_id, self.qs, reason="chose to leave")

            try:
                await interaction.response.edit_message(
                    content="👋 **You've been removed from the queue.** Feel free to rejoin anytime!",
                    embed=None,
                    view=None
                )
            except discord.errors.InteractionResponded:
                # Already responded, use followup instead
                await interaction.followup.send("👋 You've been removed from the queue.", ephemeral=True)
            except:
                pass
        else:
            await interaction.response.send_message("You're no longer in the queue.", ephemeral=True)

    async def on_timeout(self):
        """Called when the view times out (no response in 5 minutes)"""
        if not self.responded and self.user_id in self.qs.queue:
            # Need to get guild from somewhere - use stored channel
            if self.qs.queue_channel:
                guild = self.qs.queue_channel.guild
                await remove_inactive_user(guild, self.user_id, self.qs, reason="did not respond to inactivity check")


async def remove_inactive_user(guild: discord.Guild, user_id: int, qs=None, reason: str = "inactivity"):
    """Remove a user from queue due to inactivity"""
    if qs is None:
        qs = queue_state  # Default to primary queue

    if user_id not in qs.queue:
        return

    # Don't remove if user is locked into a match
    if user_id in qs.locked_players:
        return

    # Calculate time in queue
    time_in_queue = ""
    if user_id in qs.queue_join_times:
        join_time = qs.queue_join_times[user_id]
        elapsed = datetime.now() - join_time
        total_minutes = int(elapsed.total_seconds() / 60)

        if total_minutes >= 60:
            hours = total_minutes // 60
            mins = total_minutes % 60
            time_in_queue = f"{hours}h {mins}m"
        else:
            time_in_queue = f"{total_minutes}m"

        del qs.queue_join_times[user_id]
    if user_id in qs.last_activity_times:
        del qs.last_activity_times[user_id]

    # Get member for display name and role removal
    member = guild.get_member(user_id)
    display_name = member.display_name if member else f"User {user_id}"

    # Remove from queue
    qs.queue.remove(user_id)
    qs.recent_action = {
        'type': 'leave',
        'user_id': user_id,
        'name': display_name,
        'time_in_queue': time_in_queue,
        'reason': reason  # e.g., "AFK" for inactivity kicks
    }

    queue_name = "MLG 4v4 (Restricted)" if qs == queue_state_2 else "MLG 4v4"
    log_action(f"{display_name} removed from {queue_name} ({reason}) after {time_in_queue} ({len(qs.queue)}/{MAX_QUEUE_SIZE})")

    # Remove SearchingMatchmaking role
    if member:
        try:
            searching_role = discord.utils.get(guild.roles, name="SearchingMatchmaking")
            if searching_role:
                await member.remove_roles(searching_role)
                log_action(f"Removed SearchingMatchmaking role from {display_name}")
        except Exception as e:
            log_action(f"Failed to remove SearchingMatchmaking role: {e}")

    # Clean up pending confirmation messages
    await cleanup_inactivity_messages(user_id, qs)

    # Save state
    try:
        import state_manager
        state_manager.save_state()
    except:
        pass

    # Update queue embed
    if qs.queue_channel:
        await update_queue_embed(qs.queue_channel, qs)

    # Update ping message if exists (only for primary queue)
    if qs == queue_state:
        await update_ping_message(guild)


async def cleanup_inactivity_messages(user_id: int, qs=None):
    """Clean up DM and general chat messages for a user's inactivity prompt"""
    if qs is None:
        qs = queue_state  # Default to primary queue

    if user_id in qs.inactivity_pending:
        pending = qs.inactivity_pending[user_id]

        # Try to delete the general chat message
        if pending.get("general_message"):
            try:
                await pending["general_message"].delete()
            except:
                pass

        # Try to edit the DM message (can't delete DMs sent by bot)
        if pending.get("dm_message"):
            try:
                await pending["dm_message"].edit(
                    content="⏱️ *This inactivity check has expired.*",
                    embed=None,
                    view=None
                )
            except:
                pass

        del qs.inactivity_pending[user_id]


async def send_inactivity_prompt(guild: discord.Guild, user_id: int, qs=None):
    """Send inactivity prompt to user via DM only"""
    if qs is None:
        qs = queue_state  # Default to primary queue

    member = guild.get_member(user_id)
    if not member:
        return

    # Create the confirmation view
    view = InactivityConfirmView(user_id, qs)

    # Plain text DM message (no embed)
    dm_text = (
        f"⏰ **Queue Inactivity Check**\n\n"
        f"You've been in the matchmaking queue for **1 hour**.\n\n"
        f"Would you like to remain in the queue?\n\n"
        f"**If you don't respond within {INACTIVITY_RESPONSE_MINUTES} minutes, you'll be automatically removed.**"
    )

    dm_message = None
    dm_sent = False

    # Try to DM the user (plain text only)
    try:
        dm_message = await member.send(content=dm_text, view=view)
        dm_sent = True
        log_action(f"Sent inactivity DM to {member.display_name}")
    except discord.Forbidden:
        log_action(f"Could not DM {member.display_name} - DMs disabled, removing from queue")
        # If we can't DM them, remove them from queue
        await remove_inactive_user(guild, user_id, qs, reason="DMs disabled - could not send inactivity check")
        return
    except Exception as e:
        log_action(f"Error sending inactivity DM to {member.display_name}: {e}")
        return

    # Store the pending confirmation (only if DM was sent successfully)
    if dm_sent:
        qs.inactivity_pending[user_id] = {
            "prompt_time": datetime.now(),
            "dm_message": dm_message,
            "general_message": None
        }


async def check_queue_inactivity(qs=None):
    """Background task to check for inactive users in queue"""
    if qs is None:
        qs = queue_state  # Default to primary queue

    await asyncio.sleep(30)  # Wait 30 seconds on startup before first check

    while True:
        try:
            now = datetime.now()

            # Check each user in queue
            for user_id in list(qs.queue):  # Use list() to avoid modification during iteration
                # Skip if user already has a pending confirmation
                if user_id in qs.inactivity_pending:
                    # Check if the pending confirmation has timed out
                    pending = qs.inactivity_pending[user_id]
                    prompt_time = pending.get("prompt_time")
                    if prompt_time:
                        elapsed = now - prompt_time
                        if elapsed.total_seconds() >= INACTIVITY_RESPONSE_MINUTES * 60:
                            # Time's up - remove the user
                            if qs.queue_channel:
                                guild = qs.queue_channel.guild
                                await remove_inactive_user(guild, user_id, qs, reason="did not respond to inactivity check")
                    continue

                # Check if user is in a voice channel (exempt from AFK if in voice and not deafened)
                if qs.queue_channel:
                    guild = qs.queue_channel.guild
                    member = guild.get_member(user_id)
                    if member and member.voice:
                        voice_state = member.voice
                        # Check if they're in the AFK channel
                        is_in_afk = guild.afk_channel and voice_state.channel == guild.afk_channel
                        # Exempt if: in voice, NOT in AFK channel, and NOT deafened
                        if not is_in_afk and not voice_state.self_deaf and not voice_state.deaf:
                            # User is active in voice - reset their activity timer (not join time)
                            qs.last_activity_times[user_id] = now
                            continue

                # Check how long since last activity (for inactivity kick)
                last_activity = qs.last_activity_times.get(user_id)
                if last_activity:
                    elapsed = now - last_activity
                    if elapsed.total_seconds() >= INACTIVITY_CHECK_MINUTES * 60:
                        # User has been in queue for 1 hour - send prompt
                        if qs.queue_channel:
                            guild = qs.queue_channel.guild
                            await send_inactivity_prompt(guild, user_id, qs)

            # Check every 30 seconds for more responsive timeout handling
            await asyncio.sleep(30)

        except asyncio.CancelledError:
            break
        except Exception as e:
            log_action(f"Error in inactivity check: {e}")
            await asyncio.sleep(30)


class QueueView(View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="Join Matchmaking", style=discord.ButtonStyle.success, custom_id="join_queue")
    async def join_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        user_roles = [role.name for role in interaction.user.roles]

        # Get the correct queue state for this channel
        qs = get_queue_state(interaction.channel.id)

        # Check if matchmaking is paused
        if qs.paused:
            await interaction.response.send_message(
                "⏸️ **Sorry, Matchmaking is currently paused.**\n\nPlease wait for a staff member to resume it.",
                ephemeral=True
            )
            return

        # Check if user has banned role for queue channel 2
        if interaction.channel.id == QUEUE_CHANNEL_ID_2 and QUEUE_2_BANNED_ROLE:
            if QUEUE_2_BANNED_ROLE in user_roles:
                await interaction.response.send_message(
                    f"❌ **You cannot join from this queue.**\n\nPlayers with the {QUEUE_2_BANNED_ROLE} role must use the other MLG 4v4 queue.",
                    ephemeral=True
                )
                return

        # Check banned/required roles
        import json
        import os
        if os.path.exists('queue_config.json'):
            try:
                with open('queue_config.json', 'r') as f:
                    config = json.load(f)
                
                # Check banned roles
                banned = config.get('banned_roles', [])
                if any(role in banned for role in user_roles):
                    await interaction.response.send_message("❌ You have a banned role and cannot queue!", ephemeral=True)
                    return
                
                # Check required roles
                required = config.get('required_roles', [])
                if required and not any(role in required for role in user_roles):
                    await interaction.response.send_message(f"❌ You need one of these roles to queue: {', '.join(required)}", ephemeral=True)
                    return
            except:
                pass
        
        # Check if player has MMR stats
        import STATSRANKS
        player_stats = STATSRANKS.get_existing_player_stats(user_id)
        has_mmr = player_stats and 'mmr' in player_stats
        response_sent = False  # Track if we've already responded

        if not has_mmr:
            # Notify player they don't have MMR - they can still join but will get temp 500 MMR
            await interaction.response.send_message(
                "⚠️ **You don't have an MMR rating yet!**\n\n"
                "You can still join the queue, but you'll be assigned a **temporary 500 MMR** if a staff member doesn't set your MMR before the match starts.\n"
                "A staff member has been notified to set your MMR.",
                ephemeral=True
            )
            response_sent = True
            # Send alert to general chat for staff
            GENERAL_CHANNEL_ID = 1403855176460406805
            general_channel = interaction.guild.get_channel(GENERAL_CHANNEL_ID)
            if general_channel:
                embed = discord.Embed(
                    title="⚠️ New Player Needs MMR",
                    description=f"{interaction.user.mention} joined matchmaking but doesn't have an MMR rating.\n\n"
                               f"Please use `/mmr` to assign them a starting MMR before the match starts!\n"
                               f"**They will get 500 MMR temporarily if not set.**",
                    color=discord.Color.orange()
                )
                embed.set_footer(text="Player joined queue - set MMR ASAP")
                # Ping @Server Support role by name
                server_support_role = discord.utils.get(interaction.guild.roles, name="Server Support")
                role_ping = server_support_role.mention if server_support_role else "@Server Support"
                await general_channel.send(
                    content=role_ping,
                    embed=embed
                )
            # Continue to add them to queue (don't return)

        # Check if already in this queue
        if user_id in qs.queue:
            await interaction.response.send_message("You're already in this queue!", ephemeral=True)
            return

        # Allow joining multiple queues - no blocking checks
        # Players will be removed from other queues when they get matched

        # Check if queue is full
        if len(qs.queue) >= MAX_QUEUE_SIZE:
            await interaction.response.send_message("Matchmaking is full!", ephemeral=True)
            return

        # Check if player is in the current match (can't queue while playing)
        if qs.current_series:
            if user_id in qs.current_series.red_team or user_id in qs.current_series.blue_team:
                await interaction.response.send_message("You're in the current match! Finish it first.", ephemeral=True)
                return

        # Add to queue with join time
        qs.queue.append(user_id)
        qs.queue_join_times[user_id] = datetime.now()
        qs.last_activity_times[user_id] = datetime.now()  # For inactivity check

        # Clear recent action if this user was the one who left (they're rejoining)
        if qs.recent_action and qs.recent_action.get('user_id') == user_id:
            qs.recent_action = None

        queue_name = "MLG 4v4 (Restricted)" if qs == queue_state_2 else "MLG 4v4"
        mmr_display = player_stats['mmr'] if has_mmr else "PENDING (500)"
        log_action(f"{interaction.user.display_name} joined {queue_name} ({len(qs.queue)}/{MAX_QUEUE_SIZE}) - MMR: {mmr_display}")
        
        # Add SearchingMatchmaking role
        try:
            searching_role = discord.utils.get(interaction.guild.roles, name="SearchingMatchmaking")
            if searching_role:
                await interaction.user.add_roles(searching_role)
                log_action(f"Added SearchingMatchmaking role to {interaction.user.display_name}")
        except Exception as e:
            log_action(f"Failed to add SearchingMatchmaking role: {e}")
        
        # Save state
        try:
            import state_manager
            state_manager.save_state()
        except:
            pass

        # Only defer if we haven't already responded (no MMR warning sent)
        if not response_sent:
            await interaction.response.defer()
        await update_queue_embed(interaction.channel, qs)

        # Update ping message if exists (only for primary queue)
        if qs == queue_state:
            await update_ping_message(interaction.guild)

        # Start pregame if queue is full
        if len(qs.queue) == MAX_QUEUE_SIZE:
            # Lock players immediately - they cannot leave once queue is full
            qs.locked = True
            qs.locked_players = qs.queue[:]
            log_action(f"Queue full - locked {len(qs.locked_players)} players")

            # Assign match roles immediately so players can be pinged in team selection
            # Get the next match number (will be used when Series is created)
            from ingame import Series
            next_match_number = Series.match_counter + 1
            qs.pending_match_number = next_match_number
            log_action(f"Assigned pending match number: {next_match_number}")

            # Add active match roles to locked players immediately
            await add_active_match_roles(interaction.guild, qs.locked_players, "MLG4v4", next_match_number)

            # Remove matched players from all other queues they might be in
            await remove_players_from_other_queues(interaction.guild, qs.locked_players, current_queue=qs)

            # Clear the queue immediately so new players can join the next queue
            # The locked_players list holds the 8 matched players
            qs.queue.clear()
            qs.queue_join_times.clear()
            qs.last_activity_times.clear()
            qs.locked = False  # Queue is no longer locked - only players are locked
            log_action("Queue cleared - ready for new players")

            # Update queue embed to show empty/available
            await update_queue_embed(interaction.channel, qs)

            from pregame import start_pregame
            await start_pregame(interaction.channel, mlg_queue_state=qs)

    @discord.ui.button(label="Leave Matchmaking", style=discord.ButtonStyle.danger, custom_id="leave_queue")
    async def leave_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id

        # Get the correct queue state for this channel
        qs = get_queue_state(interaction.channel.id)

        # Check if user is locked into a match
        if user_id in qs.locked_players:
            await interaction.response.send_message("❌ Queue is locked! You cannot leave once the match has started.", ephemeral=True)
            return

        if user_id not in qs.queue:
            await interaction.response.send_message("You're not in matchmaking!", ephemeral=True)
            return

        # Calculate time spent in queue
        time_in_queue = ""
        if user_id in qs.queue_join_times:
            join_time = qs.queue_join_times[user_id]
            elapsed = datetime.now() - join_time
            total_minutes = int(elapsed.total_seconds() / 60)
            seconds = int(elapsed.total_seconds() % 60)

            if total_minutes >= 60:
                hours = total_minutes // 60
                mins = total_minutes % 60
                time_in_queue = f"{hours}h {mins}m"
            elif total_minutes > 0:
                time_in_queue = f"{total_minutes}m {seconds}s"
            else:
                time_in_queue = f"{seconds}s"

            del qs.queue_join_times[user_id]
        if user_id in qs.last_activity_times:
            del qs.last_activity_times[user_id]

        qs.queue.remove(user_id)
        qs.recent_action = {
            'type': 'leave',
            'user_id': user_id,
            'name': interaction.user.display_name,
            'time_in_queue': time_in_queue
        }

        queue_name = "MLG 4v4 (Restricted)" if qs == queue_state_2 else "MLG 4v4"
        log_action(f"{interaction.user.display_name} left {queue_name} after {time_in_queue} ({len(qs.queue)}/{MAX_QUEUE_SIZE})")

        # Clean up any pending inactivity confirmation
        await cleanup_inactivity_messages(user_id, qs)

        # Remove SearchingMatchmaking role
        try:
            searching_role = discord.utils.get(interaction.guild.roles, name="SearchingMatchmaking")
            if searching_role:
                await interaction.user.remove_roles(searching_role)
                log_action(f"Removed SearchingMatchmaking role from {interaction.user.display_name}")
        except Exception as e:
            log_action(f"Failed to remove SearchingMatchmaking role: {e}")

        # Save state
        try:
            import state_manager
            state_manager.save_state()
        except:
            pass

        # Just defer and update - no message shown
        await interaction.response.defer()
        await update_queue_embed(interaction.channel, qs)

        # Update ping message if exists (only for primary queue)
        if qs == queue_state:
            await update_ping_message(interaction.guild)
    
    @discord.ui.button(label="Ping", style=discord.ButtonStyle.secondary, custom_id="ping_queue")
    async def ping_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Ping general chat to recruit players"""
        # Get the correct queue state for this channel
        qs = get_queue_state(interaction.channel.id)

        # Ping feature disabled for restricted queue
        if qs == queue_state_2:
            await interaction.response.send_message("❌ Ping is not available for this queue.", ephemeral=True)
            return

        # Check if queue is empty
        if len(qs.queue) == 0:
            await interaction.response.send_message("❌ Queue is empty! Join first before pinging.", ephemeral=True)
            return

        # Check if queue is full
        if len(qs.queue) >= MAX_QUEUE_SIZE:
            await interaction.response.send_message("❌ Queue is already full!", ephemeral=True)
            return

        # Check cooldown (15 minutes)
        if qs.last_ping_time:
            elapsed = datetime.now() - qs.last_ping_time
            remaining = timedelta(minutes=PING_COOLDOWN_MINUTES) - elapsed

            if remaining.total_seconds() > 0:
                mins = int(remaining.total_seconds() // 60)
                secs = int(remaining.total_seconds() % 60)
                await interaction.response.send_message(
                    f"❌ Ping is on cooldown! Try again in **{mins}m {secs}s**",
                    ephemeral=True
                )
                return

        # Defer silently - no message to dismiss
        await interaction.response.defer()

        # Send ping to general chat
        guild = interaction.guild
        general_channel = guild.get_channel(GENERAL_CHANNEL_ID)

        if not general_channel:
            return

        # Update cooldown
        qs.last_ping_time = datetime.now()

        # Delete old ping message if exists
        if qs.ping_message:
            try:
                await qs.ping_message.delete()
            except:
                pass

        # Create embed with progress image (no title, simple description)
        current_count = len(qs.queue)

        # Use different name for restricted queue
        queue_title = "MLG 4v4 (Restricted)" if qs == queue_state_2 else "MLG 4v4"
        content_embed = discord.Embed(
            description=f"**{queue_title}** - We have **{current_count}/{MAX_QUEUE_SIZE}** players searching!",
            color=discord.Color.green()
        )
        progress_image = get_queue_progress_image(current_count)
        if progress_image:
            content_embed.set_image(url=progress_image)

        # Create view with join button - pass the queue state
        view = PingJoinView(qs)

        # Send @here first, then delete it (pings but disappears)
        here_msg = await general_channel.send("@here")
        await asyncio.sleep(0.1)
        try:
            await here_msg.delete()
        except:
            pass

        # Send embed
        qs.ping_message = await general_channel.send(embed=content_embed, view=view)

        queue_name = "MLG 4v4 (Restricted)" if qs == queue_state_2 else "MLG 4v4"
        log_action(f"{interaction.user.display_name} pinged general chat for {queue_name} ({current_count}/{MAX_QUEUE_SIZE})")


class PingJoinView(View):
    """View for the ping message in general chat with join button"""
    def __init__(self, qs=None):
        super().__init__(timeout=None)
        # Store which queue this ping belongs to (default to primary)
        self.is_restricted = (qs == queue_state_2) if qs else False

    @discord.ui.button(label="Join Matchmaking", style=discord.ButtonStyle.success, custom_id="ping_join_queue")
    async def join_from_ping(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Join queue from the ping message"""
        user_id = interaction.user.id
        user_roles = [role.name for role in interaction.user.roles]

        # Determine which queue to use based on the view's stored info
        qs = queue_state_2 if self.is_restricted else queue_state

        # Check if matchmaking is paused
        if qs.paused:
            await interaction.response.send_message(
                "⏸️ **Sorry, Matchmaking is currently paused.**\n\nPlease wait for a staff member to resume it.",
                ephemeral=True
            )
            return

        # Check if user has banned role for restricted queue
        if self.is_restricted and QUEUE_2_BANNED_ROLE:
            if QUEUE_2_BANNED_ROLE in user_roles:
                await interaction.response.send_message(
                    f"❌ **You cannot join this queue.**\n\nPlayers with the {QUEUE_2_BANNED_ROLE} role must use the other MLG 4v4 queue.",
                    ephemeral=True
                )
                return

        # Check banned/required roles
        import json
        import os
        if os.path.exists('queue_config.json'):
            try:
                with open('queue_config.json', 'r') as f:
                    config = json.load(f)

                banned = config.get('banned_roles', [])
                if any(role in banned for role in user_roles):
                    await interaction.response.send_message("❌ You have a banned role and cannot queue!", ephemeral=True)
                    return

                required = config.get('required_roles', [])
                if required and not any(role in required for role in user_roles):
                    await interaction.response.send_message(f"❌ You need one of these roles to queue: {', '.join(required)}", ephemeral=True)
                    return
            except:
                pass

        # Check if player has MMR stats
        import STATSRANKS
        player_stats = STATSRANKS.get_existing_player_stats(user_id)
        if not player_stats or 'mmr' not in player_stats:
            # Tell the player they need MMR
            await interaction.response.send_message(
                "❌ **You don't have an MMR rating yet!**\n\n"
                "You need to be assigned an MMR before you can join matchmaking.\n"
                "A staff member has been notified to set your MMR.",
                ephemeral=True
            )
            # Send separate alert to general chat for staff (NOT connected to the ping message)
            GENERAL_CHANNEL_ID = 1403855176460406805
            general_channel = interaction.guild.get_channel(GENERAL_CHANNEL_ID)
            if general_channel:
                embed = discord.Embed(
                    title="⚠️ New Player Needs MMR",
                    description=f"{interaction.user.mention} tried to join matchmaking but doesn't have an MMR rating.\n\n"
                               f"Please use `/mmr` to assign them a starting MMR.",
                    color=discord.Color.orange()
                )
                embed.set_footer(text="Player cannot queue until MMR is set")
                # Ping @Server Support role by name
                server_support_role = discord.utils.get(interaction.guild.roles, name="Server Support")
                role_ping = server_support_role.mention if server_support_role else "@Server Support"
                await general_channel.send(
                    content=role_ping,
                    embed=embed
                )
            return

        # Check if already in this queue
        if user_id in qs.queue:
            await interaction.response.send_message("You're already in this queue!", ephemeral=True)
            return

        # Allow joining multiple queues - no blocking checks
        # Players will be removed from other queues when they get matched

        # Check if queue is full
        if len(qs.queue) >= MAX_QUEUE_SIZE:
            await interaction.response.send_message("Matchmaking is full!", ephemeral=True)
            return

        # Check if player is in the current match (can't queue while playing)
        if qs.current_series:
            if user_id in qs.current_series.red_team or user_id in qs.current_series.blue_team:
                await interaction.response.send_message("You're in the current match! Finish it first.", ephemeral=True)
                return

        # Add to queue
        qs.queue.append(user_id)
        qs.queue_join_times[user_id] = datetime.now()
        qs.last_activity_times[user_id] = datetime.now()  # For inactivity check

        # Clear recent action if this user was the one who left (they're rejoining)
        if qs.recent_action and qs.recent_action.get('user_id') == user_id:
            qs.recent_action = None

        queue_name = "MLG 4v4 (Restricted)" if qs == queue_state_2 else "MLG 4v4"
        log_action(f"{interaction.user.display_name} joined {queue_name} from ping ({len(qs.queue)}/{MAX_QUEUE_SIZE}) - MMR: {player_stats['mmr']}")

        # Add SearchingMatchmaking role
        try:
            searching_role = discord.utils.get(interaction.guild.roles, name="SearchingMatchmaking")
            if searching_role:
                await interaction.user.add_roles(searching_role)
                log_action(f"Added SearchingMatchmaking role to {interaction.user.display_name}")
        except Exception as e:
            log_action(f"Failed to add SearchingMatchmaking role: {e}")

        # Save state
        try:
            import state_manager
            state_manager.save_state()
        except:
            pass

        await interaction.response.defer()

        # Update queue embed in queue channel
        if qs.queue_channel:
            await update_queue_embed(qs.queue_channel, qs)

        # Update or delete ping message (only for primary queue for now)
        if qs == queue_state:
            await update_ping_message(interaction.guild)

        # Start pregame if queue is full
        if len(qs.queue) >= MAX_QUEUE_SIZE:
            # Lock players immediately - they cannot leave once queue is full
            qs.locked = True
            qs.locked_players = qs.queue[:]
            log_action(f"Queue full - locked {len(qs.locked_players)} players")

            # Assign match roles immediately so players can be pinged in team selection
            # Get the next match number (will be used when Series is created)
            from ingame import Series
            next_match_number = Series.match_counter + 1
            qs.pending_match_number = next_match_number
            log_action(f"Assigned pending match number: {next_match_number}")

            # Add active match roles to locked players immediately
            await add_active_match_roles(interaction.guild, qs.locked_players, "MLG4v4", next_match_number)

            # Remove matched players from all other queues they might be in
            await remove_players_from_other_queues(interaction.guild, qs.locked_players, current_queue=qs)

            # Clear the queue immediately so new players can join the next queue
            qs.queue.clear()
            qs.queue_join_times.clear()
            qs.last_activity_times.clear()
            qs.locked = False
            log_action("Queue cleared - ready for new players")

            # Update queue embed to show empty/available
            if qs.queue_channel:
                await update_queue_embed(qs.queue_channel, qs)

                from pregame import start_pregame
                await start_pregame(qs.queue_channel, mlg_queue_state=qs)


async def update_ping_message(guild: discord.Guild):
    """Update or delete the ping message based on queue state"""
    if not queue_state.ping_message:
        return
    
    current_count = len(queue_state.queue)
    
    # Delete if queue is full
    if current_count >= MAX_QUEUE_SIZE:
        try:
            await queue_state.ping_message.delete()
            queue_state.ping_message = None
            log_action("Deleted ping message - queue is full")
        except:
            pass
        return
    
    # Delete if queue is empty
    if current_count == 0:
        try:
            await queue_state.ping_message.delete()
            queue_state.ping_message = None
            log_action("Deleted ping message - queue is empty")
        except:
            pass
        return
    
    # Update embed (no banner)
    needed = MAX_QUEUE_SIZE - current_count

    content_embed = discord.Embed(
        title="MLG 4v4 - Players Needed!",
        description=f"We have **{current_count}/{MAX_QUEUE_SIZE}** players searching.\nNeed **{needed}** more to start!",
        color=discord.Color.green()
    )
    progress_image = get_queue_progress_image(current_count)
    if progress_image:
        content_embed.set_image(url=progress_image)

    try:
        await queue_state.ping_message.edit(embed=content_embed)
    except:
        pass


async def delete_ping_message():
    """Delete the ping message"""
    if queue_state.ping_message:
        try:
            await queue_state.ping_message.delete()
            queue_state.ping_message = None
        except:
            pass


async def create_queue_embed(channel: discord.TextChannel, qs=None):
    """Create initial queue embed"""
    # Determine which queue state to use
    if qs is None:
        qs = get_queue_state(channel.id)

    # Store channel for auto-updates
    qs.queue_channel = channel

    # Determine title based on queue type
    is_restricted = (qs == queue_state_2)
    title = "MLG 4v4 Matchmaking (Restricted)" if is_restricted else "MLG 4v4 Matchmaking"
    description = "*Classic 4v4 with team selection vote*"
    if is_restricted:
        description += f"\n\n⚠️ *Players with the {QUEUE_2_BANNED_ROLE} role cannot join this queue.*"

    embed = discord.Embed(
        title=title,
        description=description,
        color=discord.Color.blue()
    )
    embed.add_field(
        name=f"Players in Queue (0/{MAX_QUEUE_SIZE})",
        value="*No players yet*",
        inline=False
    )
    # No progress image for empty queue

    view = QueueView()

    # Find existing queue message and check if it's at the bottom
    queue_message = None
    is_at_bottom = True
    message_count = 0

    async for message in channel.history(limit=50):
        if message.author.bot and message.embeds:
            for emb in message.embeds:
                if emb.title and "Matchmaking" in emb.title:
                    queue_message = message
                    is_at_bottom = (message_count == 0)
                    break
        if queue_message:
            break
        message_count += 1

    if queue_message:
        if is_at_bottom:
            # Already at bottom - just edit in place
            try:
                await queue_message.edit(embed=embed, view=view)
                # Start auto-update task if not already running
                if qs.auto_update_task is None or qs.auto_update_task.done():
                    qs.auto_update_task = asyncio.create_task(auto_update_queue_times(qs))
                    queue_name = "MLG 4v4 (Restricted)" if is_restricted else "MLG 4v4"
                    log_action(f"Started {queue_name} queue auto-update task")
                return
            except:
                pass
        # Not at bottom - delete and repost
        try:
            await queue_message.delete()
        except:
            pass

    # Post new message at bottom
    await channel.send(embed=embed, view=view)

    # Start auto-update task if not already running
    if qs.auto_update_task is None or qs.auto_update_task.done():
        qs.auto_update_task = asyncio.create_task(auto_update_queue_times(qs))
        queue_name = "MLG 4v4 (Restricted)" if is_restricted else "MLG 4v4"
        log_action(f"Started {queue_name} queue auto-update task")

async def update_queue_embed(channel: discord.TextChannel, qs=None):
    """Update the queue embed"""
    # Determine which queue state to use
    if qs is None:
        qs = get_queue_state(channel.id)

    is_restricted = (qs == queue_state_2)

    # Build player list with join times
    if qs.queue:
        player_list = []
        now = datetime.now()
        guild = channel.guild
        for uid in qs.queue:
            # Check if we should hide names
            if qs.hide_player_names:
                display_name = "Matched Player"
            elif uid in qs.guests:
                # This is a guest - use their custom name
                display_name = qs.guests[uid]["name"]
            else:
                # Get member to ensure we have their display name
                member = guild.get_member(uid)
                if member:
                    display_name = member.display_name
                else:
                    # Fallback to mention if member not in cache
                    display_name = f"<@{uid}>"

            join_time = qs.queue_join_times.get(uid)
            if join_time:
                elapsed = now - join_time
                total_seconds = int(elapsed.total_seconds())
                total_minutes = total_seconds // 60
                seconds = total_seconds % 60

                if total_minutes >= 60:
                    # Show hours and minutes only
                    hours = total_minutes // 60
                    mins = total_minutes % 60
                    time_str = f"{hours}h {mins}m"
                elif total_minutes > 0:
                    # Show minutes only (no seconds after 1 minute)
                    time_str = f"{total_minutes}m"
                else:
                    # Show seconds only for first minute
                    time_str = f"{seconds}s"
                player_list.append(f"**{display_name}** - {time_str}")
            else:
                player_list.append(f"**{display_name}**")
        player_mentions = "\n".join(player_list)
    else:
        player_mentions = "*No players yet*"

    # Create embed
    player_count = len(qs.queue)

    # Build description
    desc = "*Classic 4v4 with team selection vote*"

    if is_restricted:
        desc += f"\n\n⚠️ *Players with the {QUEUE_2_BANNED_ROLE} role cannot join this queue.*"

    title = "MLG 4v4 Matchmaking (Restricted)" if is_restricted else "MLG 4v4 Matchmaking"
    embed = discord.Embed(
        title=title,
        description=desc,
        color=discord.Color.blue()
    )
    embed.add_field(
        name=f"Players in Queue ({player_count}/{MAX_QUEUE_SIZE})",
        value=player_mentions,
        inline=False
    )

    # Add recent action - only show leaves (not joins)
    if qs.recent_action:
        action = qs.recent_action
        if action['type'] == 'leave':
            time_str = action.get('time_in_queue', '')
            reason = action.get('reason', '')
            # Show AFK annotation if kicked for inactivity
            afk_tag = " - AFK" if reason and "inactivity" in reason.lower() else ""
            if time_str:
                embed.add_field(
                    name="Recent Activity",
                    value=f"**{action['name']}** left matchmaking ({time_str}{afk_tag})",
                    inline=False
                )
            else:
                embed.add_field(
                    name="Recent Activity",
                    value=f"**{action['name']}** left matchmaking",
                    inline=False
                )

    # Progress image at the bottom (only if players in queue)
    progress_image = get_queue_progress_image(player_count)
    if progress_image:
        embed.set_image(url=progress_image)

    view = QueueView()

    # Find existing queue message and check if it's at the bottom
    queue_message = None
    is_at_bottom = True
    message_count = 0

    async for message in channel.history(limit=50):
        if message.author.bot and message.embeds:
            for emb in message.embeds:
                if emb.title and "Matchmaking" in emb.title:
                    queue_message = message
                    # If this isn't the first message we found, it's not at the bottom
                    is_at_bottom = (message_count == 0)
                    break
        if queue_message:
            break
        message_count += 1

    if queue_message:
        if is_at_bottom:
            # Already at bottom - just edit in place
            try:
                await queue_message.edit(embed=embed, view=view)
                return
            except:
                pass
        # Not at bottom or edit failed - delete and repost
        try:
            await queue_message.delete()
        except:
            pass

    # Post new message at bottom
    await channel.send(embed=embed, view=view)
