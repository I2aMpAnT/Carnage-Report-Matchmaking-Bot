# searchmatchmaking.py - MLG 4v4 Queue Management System
# !! REMEMBER TO UPDATE VERSION NUMBER WHEN MAKING CHANGES !!

MODULE_VERSION = "1.5.0"

import discord
from discord.ui import View, Button
from typing import List, Optional
from datetime import datetime, timedelta
import asyncio

# Header image for embeds and DMs (clean logo without text)
HEADER_IMAGE_URL = "https://raw.githubusercontent.com/I2aMpAnT/H2CarnageReport.com/main/H2CRFinal.png"

# Matchmaking progress images (1-8 players)
MATCHMAKING_IMAGE_BASE = "https://raw.githubusercontent.com/I2aMpAnT/H2CarnageReport.com/main/assets/matchmaking"

# Queue channel ID (will be set by bot.py)
QUEUE_CHANNEL_ID = None

def get_queue_progress_image(player_count: int) -> str:
    """Get the queue progress image URL for current player count"""
    if player_count < 1:
        return f"{MATCHMAKING_IMAGE_BASE}/1outof8.png"  # Show empty/1 for 0 players
    if player_count > 8:
        player_count = 8
    return f"{MATCHMAKING_IMAGE_BASE}/{player_count}outof8.png"

# Queue State
class QueueState:
    def __init__(self):
        self.queue: List[int] = []
        self.queue_join_times: dict = {}  # user_id -> datetime
        self.current_series = None
        self.pregame_timer_task: Optional[asyncio.Task] = None
        self.pregame_timer_end: Optional[datetime] = None
        self.recent_action: Optional[dict] = None
        self.test_mode: bool = False
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

# Global queue state
queue_state = QueueState()

# Constants (will be imported from bot.py)
MAX_QUEUE_SIZE = 8
PREGAME_TIMER_SECONDS = 60
GENERAL_CHANNEL_ID = 1403855176460406805
PING_COOLDOWN_MINUTES = 15
INACTIVITY_CHECK_MINUTES = 60  # Time before prompting user (1 hour)
INACTIVITY_RESPONSE_MINUTES = 5  # Time user has to respond

def log_action(message: str):
    """Log actions to log.txt"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open('log.txt', 'a') as f:
        f.write(f"[{timestamp}] {message}\n")
    print(f"[LOG] {message}")

async def auto_update_queue_times():
    """Background task to update queue times every 10 seconds"""
    await asyncio.sleep(5)  # Wait 5 seconds on startup
    
    while True:
        try:
            # Only update if there are players in queue
            if queue_state.queue and queue_state.queue_channel:
                await update_queue_embed(queue_state.queue_channel)
            await asyncio.sleep(10)  # Update every 10 seconds
        except asyncio.CancelledError:
            break
        except Exception as e:
            log_action(f"Error in auto-update: {e}")
            await asyncio.sleep(10)


class InactivityConfirmView(View):
    """View for inactivity confirmation with Yes/No buttons - uses dynamic custom_ids"""
    def __init__(self, user_id: int):
        super().__init__(timeout=INACTIVITY_RESPONSE_MINUTES * 60)  # 5 minute timeout
        self.user_id = user_id
        self.responded = False

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

        # Reset their join time to give them another hour
        if self.user_id in queue_state.queue:
            queue_state.queue_join_times[self.user_id] = datetime.now()
            log_action(f"User {interaction.user.display_name} confirmed to stay in queue - timer reset")

            # Clean up pending confirmation
            await cleanup_inactivity_messages(self.user_id)

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
            if queue_state.queue_channel:
                await update_queue_embed(queue_state.queue_channel)
        else:
            await interaction.response.send_message("You're no longer in the queue.", ephemeral=True)

    async def leave_queue_btn(self, interaction: discord.Interaction):
        """User wants to leave queue"""
        # Only the original user can respond
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This confirmation is not for you!", ephemeral=True)
            return

        self.responded = True

        # Remove from queue
        if self.user_id in queue_state.queue:
            # Get guild - use interaction.guild if available, otherwise get from queue_channel (for DM buttons)
            guild = interaction.guild or (queue_state.queue_channel.guild if queue_state.queue_channel else None)
            if guild:
                await remove_inactive_user(guild, self.user_id, reason="chose to leave")

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
        if not self.responded and self.user_id in queue_state.queue:
            # Need to get guild from somewhere - use stored channel
            if queue_state.queue_channel:
                guild = queue_state.queue_channel.guild
                await remove_inactive_user(guild, self.user_id, reason="did not respond to inactivity check")


async def remove_inactive_user(guild: discord.Guild, user_id: int, reason: str = "inactivity"):
    """Remove a user from queue due to inactivity"""
    if user_id not in queue_state.queue:
        return

    # Calculate time in queue
    time_in_queue = ""
    if user_id in queue_state.queue_join_times:
        join_time = queue_state.queue_join_times[user_id]
        elapsed = datetime.now() - join_time
        total_minutes = int(elapsed.total_seconds() / 60)

        if total_minutes >= 60:
            hours = total_minutes // 60
            mins = total_minutes % 60
            time_in_queue = f"{hours}h {mins}m"
        else:
            time_in_queue = f"{total_minutes}m"

        del queue_state.queue_join_times[user_id]

    # Get member for display name and role removal
    member = guild.get_member(user_id)
    display_name = member.display_name if member else f"User {user_id}"

    # Remove from queue
    queue_state.queue.remove(user_id)
    queue_state.recent_action = {
        'type': 'leave',
        'user_id': user_id,
        'name': display_name,
        'time_in_queue': time_in_queue
    }

    log_action(f"{display_name} removed from queue ({reason}) after {time_in_queue} ({len(queue_state.queue)}/{MAX_QUEUE_SIZE})")

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
    await cleanup_inactivity_messages(user_id)

    # Save state
    try:
        import state_manager
        state_manager.save_state()
    except:
        pass

    # Update queue embed
    if queue_state.queue_channel:
        await update_queue_embed(queue_state.queue_channel)

    # Update ping message if exists
    await update_ping_message(guild)


async def cleanup_inactivity_messages(user_id: int):
    """Clean up DM and general chat messages for a user's inactivity prompt"""
    if user_id in queue_state.inactivity_pending:
        pending = queue_state.inactivity_pending[user_id]

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

        del queue_state.inactivity_pending[user_id]


async def send_inactivity_prompt(guild: discord.Guild, user_id: int):
    """Send inactivity prompt to user via DM only"""
    member = guild.get_member(user_id)
    if not member:
        return

    # Create the confirmation view
    view = InactivityConfirmView(user_id)

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
        await remove_inactive_user(guild, user_id, reason="DMs disabled - could not send inactivity check")
        return
    except Exception as e:
        log_action(f"Error sending inactivity DM to {member.display_name}: {e}")
        return

    # Store the pending confirmation (only if DM was sent successfully)
    if dm_sent:
        queue_state.inactivity_pending[user_id] = {
            "prompt_time": datetime.now(),
            "dm_message": dm_message,
            "general_message": None
        }


async def check_queue_inactivity():
    """Background task to check for inactive users in queue"""
    await asyncio.sleep(30)  # Wait 30 seconds on startup before first check

    while True:
        try:
            now = datetime.now()

            # Check each user in queue
            for user_id in list(queue_state.queue):  # Use list() to avoid modification during iteration
                # Skip if user already has a pending confirmation
                if user_id in queue_state.inactivity_pending:
                    # Check if the pending confirmation has timed out
                    pending = queue_state.inactivity_pending[user_id]
                    prompt_time = pending.get("prompt_time")
                    if prompt_time:
                        elapsed = now - prompt_time
                        if elapsed.total_seconds() >= INACTIVITY_RESPONSE_MINUTES * 60:
                            # Time's up - remove the user
                            if queue_state.queue_channel:
                                guild = queue_state.queue_channel.guild
                                await remove_inactive_user(guild, user_id, reason="did not respond to inactivity check")
                    continue

                # Check how long they've been in queue
                join_time = queue_state.queue_join_times.get(user_id)
                if join_time:
                    elapsed = now - join_time
                    if elapsed.total_seconds() >= INACTIVITY_CHECK_MINUTES * 60:
                        # User has been in queue for 1 hour - send prompt
                        if queue_state.queue_channel:
                            guild = queue_state.queue_channel.guild
                            await send_inactivity_prompt(guild, user_id)

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
        
        # Check if matchmaking is paused
        if queue_state.paused:
            await interaction.response.send_message(
                "⏸️ **Sorry, Matchmaking is currently paused.**\n\nPlease wait for a staff member to resume it.",
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
        if not player_stats or 'mmr' not in player_stats:
            # Tell the player they need MMR
            await interaction.response.send_message(
                "❌ **You don't have an MMR rating yet!**\n\n"
                "You need to be assigned an MMR before you can join matchmaking.\n"
                "A staff member has been notified to set your MMR.",
                ephemeral=True
            )
            # Send separate alert to general chat for staff
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
        
        # Check if already in queue
        if user_id in queue_state.queue:
            await interaction.response.send_message("You're already in matchmaking!", ephemeral=True)
            return
        
        # Check if queue is full
        if len(queue_state.queue) >= MAX_QUEUE_SIZE:
            await interaction.response.send_message("Matchmaking is full!", ephemeral=True)
            return
        
        # Check if match in progress
        if queue_state.current_series:
            await interaction.response.send_message("Match in progress! Wait for it to end.", ephemeral=True)
            return
        
        # Add to queue with join time
        queue_state.queue.append(user_id)
        queue_state.queue_join_times[user_id] = datetime.now()
        
        # Clear recent action if this user was the one who left (they're rejoining)
        if queue_state.recent_action and queue_state.recent_action.get('user_id') == user_id:
            queue_state.recent_action = None
        
        log_action(f"{interaction.user.display_name} joined matchmaking ({len(queue_state.queue)}/{MAX_QUEUE_SIZE}) - MMR: {player_stats['mmr']}")
        
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
        
        # Just defer and update - no message shown
        await interaction.response.defer()
        await update_queue_embed(interaction.channel)
        
        # Update ping message if exists
        await update_ping_message(interaction.guild)
        
        # Start pregame if queue is full
        if len(queue_state.queue) == MAX_QUEUE_SIZE:
            from pregame import start_pregame
            await start_pregame(interaction.channel)
    
    @discord.ui.button(label="Leave Matchmaking", style=discord.ButtonStyle.danger, custom_id="leave_queue")
    async def leave_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        
        if user_id not in queue_state.queue:
            await interaction.response.send_message("You're not in matchmaking!", ephemeral=True)
            return
        
        # Calculate time spent in queue
        time_in_queue = ""
        if user_id in queue_state.queue_join_times:
            join_time = queue_state.queue_join_times[user_id]
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
            
            del queue_state.queue_join_times[user_id]
        
        queue_state.queue.remove(user_id)
        queue_state.recent_action = {
            'type': 'leave',
            'user_id': user_id,
            'name': interaction.user.display_name,
            'time_in_queue': time_in_queue
        }
        
        log_action(f"{interaction.user.display_name} left matchmaking after {time_in_queue} ({len(queue_state.queue)}/{MAX_QUEUE_SIZE})")

        # Clean up any pending inactivity confirmation
        await cleanup_inactivity_messages(user_id)

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
        await update_queue_embed(interaction.channel)
        
        # Update ping message if exists
        await update_ping_message(interaction.guild)
    
    @discord.ui.button(label="Ping", style=discord.ButtonStyle.secondary, custom_id="ping_queue")
    async def ping_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Ping general chat to recruit players"""
        # Check if queue is empty
        if len(queue_state.queue) == 0:
            await interaction.response.send_message("❌ Queue is empty! Join first before pinging.", ephemeral=True)
            return
        
        # Check if queue is full
        if len(queue_state.queue) >= MAX_QUEUE_SIZE:
            await interaction.response.send_message("❌ Queue is already full!", ephemeral=True)
            return
        
        # Check cooldown (15 minutes)
        if queue_state.last_ping_time:
            elapsed = datetime.now() - queue_state.last_ping_time
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
        queue_state.last_ping_time = datetime.now()
        
        # Delete old ping message if exists
        if queue_state.ping_message:
            try:
                await queue_state.ping_message.delete()
            except:
                pass
        
        # Create single embed with just the progress image (image already contains player count info)
        current_count = len(queue_state.queue)

        # Simple embed with just the progress image - no redundant text
        embed = discord.Embed(color=discord.Color.green())
        embed.set_image(url=get_queue_progress_image(current_count))

        # Create view with join button
        view = PingJoinView()

        # Send @here first, then delete it (pings but disappears)
        here_msg = await general_channel.send("@here")
        await asyncio.sleep(0.1)
        try:
            await here_msg.delete()
        except:
            pass

        # Send single embed with just the image
        queue_state.ping_message = await general_channel.send(embed=embed, view=view)
        
        log_action(f"{interaction.user.display_name} pinged general chat for queue ({current_count}/{MAX_QUEUE_SIZE})")


class PingJoinView(View):
    """View for the ping message in general chat with join button"""
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="Join Matchmaking", style=discord.ButtonStyle.success, custom_id="ping_join_queue")
    async def join_from_ping(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Join queue from the ping message"""
        user_id = interaction.user.id
        user_roles = [role.name for role in interaction.user.roles]
        
        # Check if matchmaking is paused
        if queue_state.paused:
            await interaction.response.send_message(
                "⏸️ **Sorry, Matchmaking is currently paused.**\n\nPlease wait for a staff member to resume it.",
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
        
        # Check if already in queue
        if user_id in queue_state.queue:
            await interaction.response.send_message("You're already in matchmaking!", ephemeral=True)
            return
        
        # Check if queue is full
        if len(queue_state.queue) >= MAX_QUEUE_SIZE:
            await interaction.response.send_message("Matchmaking is full!", ephemeral=True)
            return
        
        # Check if match in progress
        if queue_state.current_series:
            await interaction.response.send_message("Match in progress! Wait for it to end.", ephemeral=True)
            return
        
        # Add to queue
        queue_state.queue.append(user_id)
        queue_state.queue_join_times[user_id] = datetime.now()
        
        # Clear recent action if this user was the one who left (they're rejoining)
        if queue_state.recent_action and queue_state.recent_action.get('user_id') == user_id:
            queue_state.recent_action = None
        
        log_action(f"{interaction.user.display_name} joined from ping ({len(queue_state.queue)}/{MAX_QUEUE_SIZE}) - MMR: {player_stats['mmr']}")
        
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
        if queue_state.queue_channel:
            await update_queue_embed(queue_state.queue_channel)
        
        # Update or delete ping message
        await update_ping_message(interaction.guild)
        
        # Start pregame if queue is full
        if len(queue_state.queue) >= MAX_QUEUE_SIZE:
            if queue_state.queue_channel:
                from pregame import start_pregame
                await start_pregame(queue_state.queue_channel)


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
    
    # Update the message with just the progress image
    embed = discord.Embed(color=discord.Color.green())
    embed.set_image(url=get_queue_progress_image(current_count))

    try:
        await queue_state.ping_message.edit(embed=embed)
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


async def create_queue_embed(channel: discord.TextChannel):
    """Create initial queue embed"""
    # Store channel for auto-updates
    queue_state.queue_channel = channel

    embed = discord.Embed(
        title="MLG 4v4 Matchmaking",
        description="Click **Join Matchmaking** to start searching for a Match!\n*Classic 4v4 with team selection vote*",
        color=discord.Color.blue()
    )
    embed.add_field(
        name=f"Players in Queue (0/{MAX_QUEUE_SIZE})",
        value="*No players yet*",
        inline=False
    )
    embed.set_image(url=get_queue_progress_image(0))

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
                if queue_state.auto_update_task is None or queue_state.auto_update_task.done():
                    queue_state.auto_update_task = asyncio.create_task(auto_update_queue_times())
                    log_action("Started queue auto-update task")
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
    if queue_state.auto_update_task is None or queue_state.auto_update_task.done():
        queue_state.auto_update_task = asyncio.create_task(auto_update_queue_times())
        log_action("Started queue auto-update task")

async def update_queue_embed(channel: discord.TextChannel):
    """Update the queue embed"""
    # Build player list with join times
    if queue_state.queue:
        player_list = []
        now = datetime.now()
        guild = channel.guild
        for uid in queue_state.queue:
            # Check if we should hide names
            if queue_state.hide_player_names:
                display_name = "Matched Player"
            elif uid in queue_state.guests:
                # This is a guest - use their custom name
                display_name = queue_state.guests[uid]["name"]
            else:
                # Get member to ensure we have their display name
                member = guild.get_member(uid)
                if member:
                    display_name = member.display_name
                else:
                    # Fallback to mention if member not in cache
                    display_name = f"<@{uid}>"
            
            join_time = queue_state.queue_join_times.get(uid)
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
    player_count = len(queue_state.queue)

    embed = discord.Embed(
        title="MLG 4v4 Matchmaking",
        description="Click **Join Matchmaking** to start searching for a Match!\n*Classic 4v4 with team selection vote*",
        color=discord.Color.blue()
    )
    embed.add_field(
        name=f"Players in Queue ({player_count}/{MAX_QUEUE_SIZE})",
        value=player_mentions,
        inline=False
    )

    # Add recent action - only show leaves (not joins)
    if queue_state.recent_action:
        action = queue_state.recent_action
        if action['type'] == 'leave':
            time_str = action.get('time_in_queue', '')
            if time_str:
                embed.add_field(
                    name="Recent Activity",
                    value=f"**{action['name']}** left matchmaking (was in queue {time_str})",
                    inline=False
                )
            else:
                embed.add_field(
                    name="Recent Activity",
                    value=f"**{action['name']}** left matchmaking",
                    inline=False
                )

    # Progress image at the bottom
    embed.set_image(url=get_queue_progress_image(player_count))

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
