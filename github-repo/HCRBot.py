# HCRBot.py - Main Bot Entry Point
# Halo 2 Carnage Report Matchmaking Bot

# ============================================
# VERSION INFO
# ============================================
BOT_VERSION = "1.1.0"
BOT_BUILD_DATE = "2025-11-27"
# ============================================

import discord
from discord.ext import commands
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# Configuration - Channel IDs
QUEUE_CHANNEL_ID = 1403855421625733151
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
    twitch.ADMIN_ROLES = ADMIN_ROLES
    
    # Setup twitch commands
    twitch.setup_twitch_commands(bot)

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
    
    # Setup stats module
    try:
        await bot.load_extension('STATSRANKS')
        print('✅ Stats module loaded!')
    except Exception as e:
        print(f'⚠️ Stats module not loaded: {e}')
    
    # Sync slash commands - guild-specific for instant updates
    try:
        # Get the main guild for instant sync
        guild = bot.guilds[0] if bot.guilds else None
        if guild:
            synced = await bot.tree.sync(guild=guild)
            print(f'✅ Synced {len(synced)} slash commands to guild {guild.name}')
        else:
            synced = await bot.tree.sync()
            print(f'✅ Synced {len(synced)} slash commands globally')
    except Exception as e:
        print(f'❌ Failed to sync commands: {e}')
        import traceback
        traceback.print_exc()
    
    # Initialize queue embed
    channel = bot.get_channel(QUEUE_CHANNEL_ID)
    if channel:
        await create_queue_embed(channel)
        print(f'✅ Queue embed created in {channel.name}')
    else:
        print(f'⚠️ Could not find queue channel {QUEUE_CHANNEL_ID}')
    
    # Register persistent views for buttons to work after restart
    from searchmatchmaking import QueueView, PingJoinView
    from ingame import SeriesView
    bot.add_view(QueueView())
    bot.add_view(PingJoinView())
    print('✅ Persistent views registered')
    
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

# Run bot - works both when imported and when run directly
if not TOKEN:
    print("❌ Error: No Discord token found!")
    print("Please set DISCORD_TOKEN in your .env file")
else:
    print("🚀 Starting bot...")
    bot.run(TOKEN)
