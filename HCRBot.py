# HCRBot.py - Main Bot Entry Point
# Halo 2 Carnage Report Matchmaking Bot
# !! REMEMBER TO UPDATE VERSION NUMBER WHEN MAKING CHANGES !!

# ============================================
# VERSION INFO
# ============================================
BOT_VERSION = "1.6.4"
BOT_BUILD_DATE = "2025-12-12"
# ============================================

import discord
from discord.ext import commands
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# Configuration - Channel IDs
# MLG 4v4 (original queue)
QUEUE_CHANNEL_ID = 1403855421625733151
# Team Hardcore 4v4
TEAM_HARDCORE_CHANNEL_ID = 1443783840169721988
# Double Team 2v2
DOUBLE_TEAM_CHANNEL_ID = 1443784213135626260
# Head to Head 1v1
HEAD_TO_HEAD_CHANNEL_ID = 1443784290230865990

PREGAME_LOBBY_ID = 1442711504498221118
POSTGAME_LOBBY_ID = 1442711633518039072
RED_TEAM_VC_ID = 1442711726855553154
BLUE_TEAM_VC_ID = 1442711934662086859

# Team Emoji IDs
RED_TEAM_EMOJI_ID = 1442675426886418522
BLUE_TEAM_EMOJI_ID = 1442675472428433438

# Admin Roles
ADMIN_ROLES = ["Overlord", "Staff", "Server Support"]

# Bot Setup
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True
intents.guilds = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Setup commands BEFORE on_ready
# (Import will happen after bot object exists)
def setup_all_commands():
    """Setup all commands after imports"""
    import commands as cmd_module
    cmd_module.setup_commands(bot, PREGAME_LOBBY_ID, POSTGAME_LOBBY_ID, QUEUE_CHANNEL_ID)

# Export configuration to modules
def setup_module_config():
    """Pass configuration to all modules"""
    import searchmatchmaking
    import pregame
    import ingame
    import postgame
    import commands as cmd_module
    import twitch
    
    # Set constants in searchmatchmaking module
    searchmatchmaking.MAX_QUEUE_SIZE = 8
    searchmatchmaking.PREGAME_TIMER_SECONDS = 60
    
    # Set constants in pregame module
    pregame.PREGAME_LOBBY_ID = PREGAME_LOBBY_ID
    pregame.RED_TEAM_EMOJI_ID = RED_TEAM_EMOJI_ID
    pregame.BLUE_TEAM_EMOJI_ID = BLUE_TEAM_EMOJI_ID
    
    # Set constants in ingame module
    ingame.RED_TEAM_EMOJI_ID = RED_TEAM_EMOJI_ID
    ingame.BLUE_TEAM_EMOJI_ID = BLUE_TEAM_EMOJI_ID
    ingame.ADMIN_ROLES = ADMIN_ROLES
    ingame.QUEUE_CHANNEL_ID = QUEUE_CHANNEL_ID
    
    # Set constants in postgame module
    postgame.POSTGAME_LOBBY_ID = POSTGAME_LOBBY_ID
    postgame.QUEUE_CHANNEL_ID = QUEUE_CHANNEL_ID
    postgame.RED_TEAM_EMOJI_ID = RED_TEAM_EMOJI_ID
    postgame.BLUE_TEAM_EMOJI_ID = BLUE_TEAM_EMOJI_ID
    
    # Set constants in searchmatchmaking module
    import searchmatchmaking
    searchmatchmaking.QUEUE_CHANNEL_ID = QUEUE_CHANNEL_ID
    
    # Set constants in twitch module
    twitch.RED_TEAM_EMOJI_ID = RED_TEAM_EMOJI_ID
    twitch.BLUE_TEAM_EMOJI_ID = BLUE_TEAM_EMOJI_ID

# Bot Events
@bot.event
async def on_ready():
    print()
    print("=" * 50)
    print(f"  HCR BOT v{BOT_VERSION}")
    print(f"  Build Date: {BOT_BUILD_DATE}")
    print("=" * 50)
    print()
    
    # Show all module versions
    print("Module Versions:")
    print("-" * 30)
    try:
        import commands as cmd_module
        print(f"  commands.py:         v{cmd_module.MODULE_VERSION}")
    except:
        print(f"  commands.py:         (no version)")
    try:
        import searchmatchmaking
        print(f"  searchmatchmaking.py: v{searchmatchmaking.MODULE_VERSION}")
    except:
        print(f"  searchmatchmaking.py: (no version)")
    try:
        import pregame
        print(f"  pregame.py:          v{pregame.MODULE_VERSION}")
    except:
        print(f"  pregame.py:          (no version)")
    try:
        import ingame
        print(f"  ingame.py:           v{ingame.MODULE_VERSION}")
    except:
        print(f"  ingame.py:           (no version)")
    try:
        import postgame
        print(f"  postgame.py:         v{postgame.MODULE_VERSION}")
    except:
        print(f"  postgame.py:         (no version)")
    try:
        import STATSRANKS
        print(f"  STATSRANKS.py:       v{STATSRANKS.MODULE_VERSION}")
    except:
        print(f"  STATSRANKS.py:       (no version)")
    try:
        import twitch
        print(f"  twitch.py:           v{twitch.MODULE_VERSION}")
    except:
        print(f"  twitch.py:           (no version)")
    try:
        import state_manager
        print(f"  state_manager.py:    v{state_manager.MODULE_VERSION}")
    except:
        print(f"  state_manager.py:    (no version)")
    try:
        import playlists
        print(f"  playlists.py:        v{playlists.MODULE_VERSION}")
    except:
        print(f"  playlists.py:        (no version)")
    print("-" * 30)
    print()
    
    print(f'✅ {bot.user} connected to Discord!')
    print(f'Bot ID: {bot.user.id}')
    print(f'Guilds: {len(bot.guilds)}')
    
    from searchmatchmaking import log_action, create_queue_embed
    log_action(f"Bot v{BOT_VERSION} started as {bot.user}")
    
    # Setup module configuration
    setup_module_config()
    
    # Setup commands FIRST
    try:
        setup_all_commands()
        print('✅ Commands registered!')
    except Exception as e:
        print(f'❌ Failed to register commands: {e}')
        import traceback
        traceback.print_exc()
    
    # Setup Stats Dedi module (Vultr VPS management)
    try:
        await bot.load_extension('statsdedi')
        print('✅ Stats Dedi module loaded!')
    except Exception as e:
        print(f'⚠️ Stats Dedi module not loaded: {e}')

    # Sync slash commands
    try:
        synced = await bot.tree.sync()
        print(f'✅ Synced {len(synced)} slash commands')
    except Exception as e:
        print(f'❌ Failed to sync commands: {e}')
    
    # Initialize queue embed (MLG 4v4)
    channel = bot.get_channel(QUEUE_CHANNEL_ID)
    if channel:
        await create_queue_embed(channel)
        print(f'✅ MLG 4v4 queue embed created in {channel.name}')

        # Start inactivity timer task
        from searchmatchmaking import queue_state, check_queue_inactivity
        import asyncio
        if queue_state.inactivity_timer_task is None or queue_state.inactivity_timer_task.done():
            queue_state.inactivity_timer_task = asyncio.create_task(check_queue_inactivity())
            print('✅ Queue inactivity timer started')
    else:
        print(f'⚠️ Could not find queue channel {QUEUE_CHANNEL_ID}')

    # Initialize all other playlist embeds
    try:
        import playlists
        await playlists.initialize_all_playlists(bot)
        print('✅ All playlist embeds initialized')
    except Exception as e:
        print(f'⚠️ Failed to initialize playlists: {e}')
        import traceback
        traceback.print_exc()
    
    # Register persistent views for buttons to work after restart
    from searchmatchmaking import QueueView, PingJoinView
    from ingame import SeriesView
    bot.add_view(QueueView())
    bot.add_view(PingJoinView())

    # Register playlist views for all playlist types
    try:
        from playlists import PlaylistQueueView, PlaylistPingJoinView, PlaylistMatchView, get_playlist_state, PlaylistType
        for ptype in [PlaylistType.TEAM_HARDCORE, PlaylistType.DOUBLE_TEAM, PlaylistType.HEAD_TO_HEAD]:
            ps = get_playlist_state(ptype)
            bot.add_view(PlaylistQueueView(ps))
            bot.add_view(PlaylistPingJoinView(ps))
        print('✅ All persistent views registered')
    except Exception as e:
        print(f'⚠️ Playlist views not registered: {e}')
        print('✅ Basic persistent views registered')
    
    # Restore saved state if exists
    try:
        import state_manager
        if state_manager.has_saved_state():
            print('📁 Found saved state, attempting to restore...')
            restored = await state_manager.restore_state(bot)
            if restored:
                print('✅ State restored successfully!')
                log_action("Restored saved matchmaking state after restart")
                
                # Update queue embed with restored state
                if channel:
                    from searchmatchmaking import update_queue_embed, queue_state
                    await update_queue_embed(channel)
                    
                    # If series was active, recreate the series embed
                    if queue_state.current_series:
                        from ingame import SeriesView
                        series = queue_state.current_series
                        view = SeriesView(series)
                        await view.update_series_embed(channel)
                        print(f'✅ Restored active series: {series.series_number}')
            else:
                print('⚠️ State restoration failed')
    except Exception as e:
        print(f'⚠️ State restoration error: {e}')
        import traceback
        traceback.print_exc()

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return

    from searchmatchmaking import log_action
    log_action(f"Command error: {error}")
    await ctx.send(f"❌ Error: {error}")

@bot.event
async def on_interaction(interaction: discord.Interaction):
    """Handle interactions, including inactivity confirmation buttons after restart"""
    if interaction.type != discord.InteractionType.component:
        return

    custom_id = interaction.data.get("custom_id", "")

    # Handle inactivity confirmation buttons (dynamic custom_ids)
    if custom_id.startswith("inactivity_yes_") or custom_id.startswith("inactivity_no_"):
        from searchmatchmaking import (
            queue_state, cleanup_inactivity_messages, remove_inactive_user,
            update_queue_embed, log_action
        )
        from datetime import datetime

        # Extract user_id from custom_id
        try:
            user_id = int(custom_id.split("_")[-1])
        except ValueError:
            return

        # Only the target user can respond
        if interaction.user.id != user_id:
            await interaction.response.send_message("This confirmation is not for you!", ephemeral=True)
            return

        if custom_id.startswith("inactivity_yes_"):
            # User wants to stay in queue
            if user_id in queue_state.queue:
                queue_state.queue_join_times[user_id] = datetime.now()
                log_action(f"User {interaction.user.display_name} confirmed to stay in queue - timer reset")

                await cleanup_inactivity_messages(user_id)

                try:
                    await interaction.response.edit_message(
                        content="✅ **You've been kept in the queue!** Your timer has been reset for another hour.",
                        embed=None,
                        view=None
                    )
                except:
                    await interaction.response.send_message("✅ You've been kept in the queue!", ephemeral=True)

                if queue_state.queue_channel:
                    await update_queue_embed(queue_state.queue_channel)
            else:
                await interaction.response.send_message("You're no longer in the queue.", ephemeral=True)

        elif custom_id.startswith("inactivity_no_"):
            # User wants to leave queue
            if user_id in queue_state.queue:
                # Get guild - use interaction.guild if available, otherwise get from queue_channel (for DM buttons)
                guild = interaction.guild or (queue_state.queue_channel.guild if queue_state.queue_channel else None)
                if guild:
                    await remove_inactive_user(guild, user_id, reason="chose to leave")

                try:
                    await interaction.response.edit_message(
                        content="👋 **You've been removed from the queue.** Feel free to rejoin anytime!",
                        embed=None,
                        view=None
                    )
                except:
                    await interaction.response.send_message("👋 You've been removed from the queue.", ephemeral=True)
            else:
                await interaction.response.send_message("You're no longer in the queue.", ephemeral=True)

# Channel ID for populate_stats.py refresh trigger
REFRESH_TRIGGER_CHANNEL_ID = 1427929973125156924

@bot.event
async def on_message(message: discord.Message):
    """Handle messages - keep queue embeds and match embeds at bottom of their channels"""
    # Handle rank refresh trigger from populate_stats.py (allows webhooks)
    if message.channel.id == REFRESH_TRIGGER_CHANNEL_ID:
        # Allow webhooks but not regular bots
        if message.author.bot and not message.webhook_id:
            return
        if message.content == "!refresh_ranks_trigger":
            print("Received rank refresh trigger from populate_stats.py")
            try:
                import STATSRANKS
                # Get all players from rankstats
                stats = STATSRANKS.load_json_file(STATSRANKS.RANKSTATS_FILE)
                player_ids = [int(uid) for uid in stats.keys() if uid.isdigit()]

                # Refresh all ranks
                await STATSRANKS.refresh_all_ranks(message.guild, player_ids, send_dm=False)

                # Delete the trigger message
                await message.delete()
                print("Rank refresh completed successfully")
            except Exception as e:
                print(f"Error during rank refresh: {e}")
            return

    # Ignore bot messages for other handlers
    if message.author.bot:
        return

    # List of all queue channel IDs
    QUEUE_CHANNELS = [
        QUEUE_CHANNEL_ID,           # MLG 4v4
        TEAM_HARDCORE_CHANNEL_ID,   # Team Hardcore
        DOUBLE_TEAM_CHANNEL_ID,     # Double Team
        HEAD_TO_HEAD_CHANNEL_ID,    # Head to Head
    ]

    GENERAL_CHANNEL_ID = 1403855176460406805

    # Handle queue channels - keep queue embed at bottom
    if message.channel.id in QUEUE_CHANNELS:
        await repost_queue_embed_if_needed(message)
        return

    # Handle general chat - keep match embed at bottom during active series
    if message.channel.id == GENERAL_CHANNEL_ID:
        await repost_match_embed_if_needed(message)
        return


async def repost_queue_embed_if_needed(message: discord.Message):
    """Repost queue embed to keep it at the bottom of the channel"""
    from searchmatchmaking import queue_state, update_queue_embed, log_action

    channel = message.channel

    # Check if this is the MLG 4v4 queue channel
    if channel.id == QUEUE_CHANNEL_ID:
        # Check if queue is active (has players or no match in progress)
        if queue_state.current_series:
            return  # Don't mess with embeds during active series

        try:
            # Find the queue embed message
            queue_message = None
            async for msg in channel.history(limit=20):
                if msg.author.bot and msg.embeds:
                    title = msg.embeds[0].title or ""
                    if "Matchmaking" in title and "MLG" in title:
                        queue_message = msg
                        break

            if queue_message:
                # Delete and repost
                try:
                    await queue_message.delete()
                except:
                    pass

                # Repost the queue embed
                await update_queue_embed(channel)
                log_action(f"Reposted MLG queue embed (triggered by {message.author.display_name})")

        except Exception as e:
            print(f"Error reposting MLG queue embed: {e}")
        return

    # Handle other playlist channels
    try:
        from playlists import get_playlist_by_channel, update_playlist_embed

        playlist_state = get_playlist_by_channel(channel.id)
        if not playlist_state:
            return

        # Don't repost during active match
        if playlist_state.current_match:
            return

        # Find the playlist queue embed
        queue_message = None
        async for msg in channel.history(limit=20):
            if msg.author.bot and msg.embeds:
                title = msg.embeds[0].title or ""
                if playlist_state.name in title and "Matchmaking" in title:
                    queue_message = msg
                    break

        if queue_message:
            # Delete and repost
            try:
                await queue_message.delete()
            except:
                pass

            # Repost the queue embed
            await update_playlist_embed(channel, playlist_state)
            from searchmatchmaking import log_action
            log_action(f"Reposted {playlist_state.name} queue embed (triggered by {message.author.display_name})")

    except Exception as e:
        print(f"Error reposting playlist queue embed: {e}")


async def repost_match_embed_if_needed(message: discord.Message):
    """Repost match embed to keep it at the bottom of general chat during active series"""
    from searchmatchmaking import queue_state, log_action

    if not queue_state.current_series:
        return

    series = queue_state.current_series
    if not hasattr(series, 'general_message') or not series.general_message:
        return

    # Repost the match embed to keep it at the bottom
    try:
        from ingame import update_general_chat_embed

        # Delete the old message
        old_message = series.general_message
        try:
            await old_message.delete()
        except:
            pass

        # Clear the reference so update_general_chat_embed creates a new one
        series.general_message = None

        # Repost the embed
        await update_general_chat_embed(message.guild, series)
        log_action(f"Reposted match embed to bottom (triggered by {message.author.display_name})")

    except Exception as e:
        print(f"Error reposting match embed: {e}")

# Run bot - works both when imported and when run directly
if not TOKEN:
    print("❌ Error: No Discord token found!")
    print("Please set DISCORD_TOKEN in your .env file")
else:
    print("🚀 Starting bot...")
    bot.run(TOKEN)
