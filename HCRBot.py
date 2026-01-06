# HCRBot.py - Main Bot Entry Point
# Halo 2 Carnage Report Matchmaking Bot
# !! REMEMBER TO UPDATE VERSION NUMBER WHEN MAKING CHANGES !!

# ============================================
# VERSION INFO
# ============================================
BOT_VERSION = "1.6.6"
BOT_BUILD_DATE = "2026-01-05"
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
# MLG 4v4 (second queue - with banned role restriction)
QUEUE_CHANNEL_ID_2 = 1449951027183882321
QUEUE_2_BANNED_ROLE = "☢️"  # Users with this role cannot join queue 2
# Team Hardcore 4v4 (DISABLED - channel deleted)
TEAM_HARDCORE_CHANNEL_ID = None  # Channel deleted, set to None
# Double Team 2v2
DOUBLE_TEAM_CHANNEL_ID = 1443784213135626260
# Head to Head 1v1
HEAD_TO_HEAD_CHANNEL_ID = 1443784290230865990

PREGAME_LOBBY_ID = 1442711504498221118
POSTGAME_LOBBY_ID = 1442711633518039072
RED_TEAM_VC_ID = 1442711726855553154
BLUE_TEAM_VC_ID = 1442711934662086859

# General chat channel (for live notifications)
GENERAL_CHANNEL_ID = 1403855176460406805

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
    searchmatchmaking.QUEUE_CHANNEL_ID_2 = QUEUE_CHANNEL_ID_2
    searchmatchmaking.QUEUE_2_BANNED_ROLE = QUEUE_2_BANNED_ROLE
    
    # Set constants in twitch module
    twitch.RED_TEAM_EMOJI_ID = RED_TEAM_EMOJI_ID
    twitch.BLUE_TEAM_EMOJI_ID = BLUE_TEAM_EMOJI_ID
    twitch.LIVE_NOTIFICATION_CHANNEL_ID = GENERAL_CHANNEL_ID

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

    # Sync slash commands - guild-specific for instant updates
    try:
        # Get the main guild for instant sync
        guild = bot.guilds[0] if bot.guilds else None
        if guild:
            # Copy global commands to guild FIRST (before clearing)
            bot.tree.copy_global_to(guild=guild)

            # Now clear global commands (prevents duplicates)
            bot.tree.clear_commands(guild=None)
            await bot.tree.sync()  # Sync empty global commands
            print(f'✅ Cleared global commands (using guild-specific only)')

            # Sync guild commands
            synced = await bot.tree.sync(guild=guild)
            print(f'✅ Synced {len(synced)} slash commands to guild {guild.name}')
            # Check for specific commands
            cmd_names = [cmd.name for cmd in synced]
            if 'dotcomrefresh' in cmd_names:
                print(f'   ✓ dotcomrefresh command found')
            else:
                print(f'   ✗ dotcomrefresh command MISSING')
            if 'backfillgamedata' in cmd_names:
                print(f'   ✓ backfillgamedata command found')
            else:
                print(f'   ✗ backfillgamedata command MISSING')
        else:
            synced = await bot.tree.sync()
            print(f'✅ Synced {len(synced)} slash commands globally')
    except Exception as e:
        print(f'❌ Failed to sync commands: {e}')
        import traceback
        traceback.print_exc()
    
    # Initialize queue embed (MLG 4v4 - primary channel)
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

    # Initialize queue embed (MLG 4v4 - second channel with banned role)
    channel2 = bot.get_channel(QUEUE_CHANNEL_ID_2)
    if channel2:
        from searchmatchmaking import queue_state_2, check_queue_inactivity
        await create_queue_embed(channel2, queue_state_2)
        print(f'✅ MLG 4v4 queue embed (restricted) created in {channel2.name}')

        # Start inactivity timer task for second queue
        if queue_state_2.inactivity_timer_task is None or queue_state_2.inactivity_timer_task.done():
            queue_state_2.inactivity_timer_task = asyncio.create_task(check_queue_inactivity(queue_state_2))
            print('✅ Queue 2 inactivity timer started')
    else:
        print(f'⚠️ Could not find second queue channel {QUEUE_CHANNEL_ID_2}')

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

                # Update main queue embed with restored state
                if channel:
                    from searchmatchmaking import update_queue_embed, queue_state, queue_state_2
                    await update_queue_embed(channel)
                    print(f'✅ Restored main queue: {len(queue_state.queue)} players')

                    # If series was active, recreate the series embed and register the view
                    if queue_state.current_series:
                        from ingame import SeriesView
                        series = queue_state.current_series
                        view = SeriesView(series)
                        bot.add_view(view)  # Register view so buttons work after restart
                        await view.update_series_embed(channel)
                        print(f'✅ Restored active series: {series.series_number}')

                # Update queue 2 embed with restored state
                if channel2:
                    from searchmatchmaking import update_queue_embed, queue_state_2
                    await update_queue_embed(channel2, queue_state_2)
                    print(f'✅ Restored queue 2: {len(queue_state_2.queue)} players')

                    # If series was active on queue 2, recreate the series embed and register the view
                    if queue_state_2.current_series:
                        from ingame import SeriesView
                        series = queue_state_2.current_series
                        view = SeriesView(series)
                        bot.add_view(view)  # Register view so buttons work after restart
                        await view.update_series_embed(channel2)
                        print(f'✅ Restored queue 2 series: {series.series_number}')
            else:
                print('⚠️ State restoration failed')

            # Resume any pregame tasks that were in progress
            try:
                resumed = await state_manager.resume_pregame_tasks(bot)
                if resumed > 0:
                    print(f'✅ Resumed {resumed} pregame task(s)')
            except Exception as e:
                print(f'⚠️ Failed to resume pregame tasks: {e}')
    except Exception as e:
        print(f'⚠️ State restoration error: {e}')
        import traceback
        traceback.print_exc()

    # Initialize permanent leaderboard
    await initialize_leaderboard()

    # Start Twitch EventSub for live stream notifications
    try:
        import twitch
        twitch.start_eventsub(bot)
        print('✅ Twitch EventSub started for live notifications')
    except Exception as e:
        print(f'⚠️ Twitch EventSub not started: {e}')

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

# Leaderboard channel ID - permanent leaderboard embed
LEADERBOARD_CHANNEL_ID = 1403859019235463189

# Store leaderboard message reference
leaderboard_message = None

@bot.event
async def on_message(message: discord.Message):
    """Handle messages - keep queue embeds and match embeds at bottom of their channels"""
    # Handle rank refresh trigger from populate_stats.py (allows webhooks)
    if message.channel.id == REFRESH_TRIGGER_CHANNEL_ID:
        # Allow webhooks but not regular bots
        if message.author.bot and not message.webhook_id:
            return
        if message.content == "!refresh_ranks_trigger":
            print("[RANKS] Received rank refresh trigger from webhook")
            try:
                import STATSRANKS
                # Get all players from ranks.json (website source of truth)
                ranks = STATSRANKS.load_json_file(STATSRANKS.RANKS_FILE)
                player_ids = [int(uid) for uid in ranks.keys() if uid.isdigit()]

                # Refresh all ranks (Discord roles)
                await STATSRANKS.refresh_all_ranks(message.guild, player_ids, send_dm=False)
                print(f"[RANKS] Rank refresh completed - {len(player_ids)} players updated")

                # Update any active series embeds with new rank data
                try:
                    from searchmatchmaking import queue_state
                    import ingame
                    if queue_state.current_series:
                        series = queue_state.current_series
                        print(f"[RANKS] Updating active series embed with new ranks...")

                        # Update series channel embed
                        if series.text_channel_id:
                            series_channel = message.guild.get_channel(series.text_channel_id)
                            if series_channel and series.series_message:
                                view = ingame.SeriesView(series)
                                await view.update_series_embed(series_channel)

                        # Update general chat embed
                        await ingame.update_general_chat_embed(message.guild, series)
                        print(f"[RANKS] Active series embeds updated")
                except Exception as embed_error:
                    print(f"[RANKS] Could not update series embeds: {embed_error}")

                # Post NEW game data to playlist channels (only unposted series)
                try:
                    import statsdata
                    from playlists import PLAYLIST_CONFIG, PlaylistType

                    playlists = [
                        ("mlg_4v4", PlaylistType.MLG_4V4),
                        ("team_hardcore", PlaylistType.TEAM_HARDCORE),
                        ("double_team", PlaylistType.DOUBLE_TEAM),
                        ("head_to_head", PlaylistType.HEAD_TO_HEAD),
                    ]

                    total_posted = 0
                    total_series_count = 0

                    for playlist_key, playlist_type in playlists:
                        if playlist_type not in PLAYLIST_CONFIG:
                            continue

                        target_channel_id = PLAYLIST_CONFIG[playlist_type]["channel_id"]
                        target_channel = message.guild.get_channel(target_channel_id)

                        if not target_channel:
                            continue

                        # Get all series and filter to only unposted ones
                        all_series = statsdata.get_all_series(playlist_key)
                        unposted = statsdata.get_unposted_series(playlist_key, all_series)

                        # Count total series (each series = +1)
                        total_series_count += len(all_series)

                        if not unposted:
                            continue

                        print(f"[RANKS] Found {len(unposted)} new series for {playlist_key}")

                        # Generate embeds only for unposted series
                        for series in unposted:
                            embed = await statsdata.build_series_embed(
                                series=series,
                                guild=message.guild,
                                playlist=playlist_key,
                                red_emoji_id=RED_TEAM_EMOJI_ID,
                                blue_emoji_id=BLUE_TEAM_EMOJI_ID
                            )
                            if embed:
                                try:
                                    await target_channel.send(embed=embed)
                                    statsdata.mark_series_posted(playlist_key, series.get("series_label"))
                                    total_posted += 1
                                except Exception as e:
                                    print(f"[RANKS] Failed to post series: {e}")

                    # Set MLG 4v4 Series counter (playlists derive number from completed matches)
                    mlg_series = statsdata.get_all_series("mlg_4v4")
                    if mlg_series:
                        from ingame import Series
                        Series.match_counter = len(mlg_series)
                        print(f"[RANKS] Set MLG 4v4 Series counter to {Series.match_counter}")

                    # Save state
                    try:
                        from state_manager import save_state
                        save_state()
                    except:
                        pass

                    if total_posted > 0:
                        print(f"[RANKS] Posted {total_posted} new series embeds")
                except Exception as backfill_error:
                    print(f"[RANKS] Backfill error: {backfill_error}")

                print("[RANKS] Webhook completed successfully")
            except Exception as e:
                print(f"[RANKS] Error during rank refresh: {e}")
                import traceback
                traceback.print_exc()
            finally:
                # Always delete trigger message
                try:
                    await message.delete()
                except:
                    pass
            return

    # Ignore bot messages for other handlers
    if message.author.bot:
        return

    # List of all queue channel IDs (filter out None for disabled playlists)
    QUEUE_CHANNELS = [ch for ch in [
        QUEUE_CHANNEL_ID,           # MLG 4v4
        QUEUE_CHANNEL_ID_2,         # MLG 4v4 Chill Queue
        TEAM_HARDCORE_CHANNEL_ID,   # Team Hardcore (disabled)
        DOUBLE_TEAM_CHANNEL_ID,     # Double Team
        HEAD_TO_HEAD_CHANNEL_ID,    # Head to Head
    ] if ch is not None]

    # Handle queue channels - keep queue embed at bottom
    if message.channel.id in QUEUE_CHANNELS:
        await repost_queue_embed_if_needed(message)
        return

    # Handle leaderboard channel - keep leaderboard at bottom
    if message.channel.id == LEADERBOARD_CHANNEL_ID:
        await repost_leaderboard_if_needed(message)
        return

    # Handle general chat - disabled auto-refresh to avoid spam
    # if message.channel.id == GENERAL_CHANNEL_ID:
    #     await repost_match_embed_if_needed(message)
    #     return


async def repost_queue_embed_if_needed(message: discord.Message):
    """Repost queue embed to keep it at the bottom of the channel"""
    from searchmatchmaking import queue_state, queue_state_2, update_queue_embed, log_action

    channel = message.channel

    # Check if this is an MLG 4v4 queue channel (main or chill)
    if channel.id == QUEUE_CHANNEL_ID:
        qs = queue_state
        queue_name = "MLG"
    elif channel.id == QUEUE_CHANNEL_ID_2:
        qs = queue_state_2
        queue_name = "Chill"
    else:
        qs = None
        queue_name = None

    if qs is not None:
        # Check if queue has active series - don't mess with embeds
        if qs.current_series:
            return

        try:
            # Find the queue embed message based on queue type
            queue_message = None
            if channel.id == QUEUE_CHANNEL_ID:
                search_terms = ["MLG", "Matchmaking"]
            else:  # QUEUE_CHANNEL_ID_2
                search_terms = ["Chill", "Lobby"]

            async for msg in channel.history(limit=20):
                if msg.author.bot and msg.embeds:
                    title = msg.embeds[0].title or ""
                    if all(term in title for term in search_terms):
                        queue_message = msg
                        break

            if queue_message:
                # Delete and repost
                try:
                    await queue_message.delete()
                except:
                    pass

                # Repost the queue embed
                await update_queue_embed(channel, qs)
                log_action(f"Reposted {queue_name} queue embed (triggered by {message.author.display_name})")

        except Exception as e:
            print(f"Error reposting {queue_name} queue embed: {e}")
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


async def repost_leaderboard_if_needed(message: discord.Message):
    """Repost leaderboard embed to keep it at the bottom of the leaderboard channel"""
    global leaderboard_message
    from searchmatchmaking import log_action

    try:
        channel = message.channel

        # Find and delete the old leaderboard message
        if leaderboard_message:
            try:
                await leaderboard_message.delete()
            except:
                pass
            leaderboard_message = None

        # Also search for any existing leaderboard embeds
        async for msg in channel.history(limit=20):
            if msg.author.bot and msg.embeds:
                title = msg.embeds[0].title or ""
                if "Leaderboard" in title:
                    try:
                        await msg.delete()
                    except:
                        pass

        # Create and post new leaderboard
        import STATSRANKS
        view = STATSRANKS.LeaderboardView(bot, guild=message.guild)
        embed = await view.build_embed()
        leaderboard_message = await channel.send(embed=embed, view=view)
        log_action(f"Reposted leaderboard to bottom (triggered by {message.author.display_name})")

    except Exception as e:
        print(f"Error reposting leaderboard: {e}")


async def initialize_leaderboard():
    """Initialize the permanent leaderboard embed on bot start"""
    global leaderboard_message
    from searchmatchmaking import log_action

    try:
        channel = bot.get_channel(LEADERBOARD_CHANNEL_ID)
        if not channel:
            print(f"⚠️ Could not find leaderboard channel {LEADERBOARD_CHANNEL_ID}")
            return

        # Delete any existing leaderboard embeds
        async for msg in channel.history(limit=50):
            if msg.author.bot and msg.embeds:
                title = msg.embeds[0].title or ""
                if "Leaderboard" in title:
                    try:
                        await msg.delete()
                    except:
                        pass

        # Create and post new leaderboard
        import STATSRANKS
        guild = channel.guild
        view = STATSRANKS.LeaderboardView(bot, guild=guild)
        embed = await view.build_embed()
        leaderboard_message = await channel.send(embed=embed, view=view)
        print(f"✅ Permanent leaderboard created in {channel.name}")
        log_action("Permanent leaderboard initialized")

    except Exception as e:
        print(f"⚠️ Error initializing leaderboard: {e}")
        import traceback
        traceback.print_exc()


# Run bot - works both when imported and when run directly
if not TOKEN:
    print("❌ Error: No Discord token found!")
    print("Please set DISCORD_TOKEN in your .env file")
else:
    print("🚀 Starting bot...")
    bot.run(TOKEN)
