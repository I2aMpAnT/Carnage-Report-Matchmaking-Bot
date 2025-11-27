# queue.py - Queue Management System

import discord
from discord.ui import View, Button
from typing import List, Optional
from datetime import datetime, timedelta
import asyncio

# Header image for embeds and DMs
HEADER_IMAGE_URL = "https://raw.githubusercontent.com/I2aMpAnT/H2CarnageReport.com/main/MessagefromCarnageReportHEADER.png"

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

# Global queue state
queue_state = QueueState()

# Constants (will be imported from bot.py)
MAX_QUEUE_SIZE = 8
PREGAME_TIMER_SECONDS = 60
GENERAL_CHANNEL_ID = 1403855176460406805
PING_COOLDOWN_MINUTES = 15

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

class QueueView(View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="Join Matchmaking", style=discord.ButtonStyle.success, custom_id="join_queue")
    async def join_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        user_roles = [role.name for role in interaction.user.roles]
        
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
                               f"Please use `/setmmr` to assign them a starting MMR.",
                    color=discord.Color.orange()
                )
                embed.set_footer(text="Player cannot queue until MMR is set")
                # This is a separate message, not connected to any ping
                await general_channel.send(
                    content="<@&1403858215707504642>",  # Server Tech Support role
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
        
        # Create single combined embed for cleaner look
        current_count = len(queue_state.queue)
        needed = MAX_QUEUE_SIZE - current_count
        
        main_embed = discord.Embed(
            title="Message To All Friends:",
            description=f"We have **{current_count}** players searching in Matchmaking, need **{needed}** more to start a Match!",
            color=discord.Color.blue()
        )
        
        # Set header as thumbnail for continuous look
        main_embed.set_thumbnail(url=HEADER_IMAGE_URL)
        
        # Add queue progress image as main image
        main_embed.set_image(url=get_queue_progress_image(current_count))
        
        # Create view with join button
        view = PingJoinView()
        
        # Send @here first, then delete it (pings but disappears)
        here_msg = await general_channel.send("@here")
        await asyncio.sleep(0.1)
        try:
            await here_msg.delete()
        except:
            pass
        
        # Send single embed
        queue_state.ping_message = await general_channel.send(embed=main_embed, view=view)
        
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
                               f"Please use `/setmmr` to assign them a starting MMR.",
                    color=discord.Color.orange()
                )
                embed.set_footer(text="Player cannot queue until MMR is set")
                # This is a completely separate message from the ping
                await general_channel.send(
                    content="<@&1403858215707504642>",  # Server Tech Support role
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
    
    # Update the message with single combined embed
    needed = MAX_QUEUE_SIZE - current_count
    
    main_embed = discord.Embed(
        title="Message To All Friends:",
        description=f"We have **{current_count}** players searching in Matchmaking, need **{needed}** more to start a Match!",
        color=discord.Color.green()
    )
    main_embed.set_thumbnail(url=HEADER_IMAGE_URL)
    main_embed.set_image(url=get_queue_progress_image(current_count))
    
    try:
        await queue_state.ping_message.edit(embed=main_embed)
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
        title="Matchmaking",
        description="Click **Join Matchmaking** to start searching for a Match!",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name=f"Players in Matchmaking (0/{MAX_QUEUE_SIZE})",
        value="*No players yet*",
        inline=False
    )
    
    view = QueueView()
    
    # Try to find existing queue message
    async for message in channel.history(limit=50):
        if message.author.bot and message.embeds:
            if "Matchmaking" in message.embeds[0].title:
                try:
                    await message.edit(embed=embed, view=view)
                    
                    # Start auto-update task if not already running
                    if queue_state.auto_update_task is None or queue_state.auto_update_task.done():
                        queue_state.auto_update_task = asyncio.create_task(auto_update_queue_times())
                        log_action("Started queue auto-update task")
                    
                    return
                except:
                    pass
    
    # Create new message if not found
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
    embed = discord.Embed(
        title="Matchmaking",
        description="Click **Join Matchmaking** to start searching for a Match!",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name=f"Players in Matchmaking ({len(queue_state.queue)}/{MAX_QUEUE_SIZE})",
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
    
    # Add queue progress image (shows X/8 players visually)
    player_count = len(queue_state.queue)
    if player_count > 0:
        embed.set_image(url=get_queue_progress_image(player_count))
    
    view = QueueView()
    
    # Find and update existing message
    async for message in channel.history(limit=50):
        if message.author.bot and message.embeds:
            if "Matchmaking" in message.embeds[0].title:
                try:
                    await message.edit(embed=embed, view=view)
                    return
                except:
                    pass
    
    # Create new if not found
    await channel.send(embed=embed, view=view)
