# commands.py - All Bot Commands
# !! REMEMBER TO UPDATE VERSION NUMBER WHEN MAKING CHANGES !!

MODULE_VERSION = "1.4.9"

import discord
from discord import app_commands
from discord.ext import commands
import random
from datetime import datetime
import json
import os
import asyncio
from itertools import combinations
import github_webhook

# Admin role configuration (highest level - can manage staff roles)
ADMIN_ROLES = ["Overlord"]

# Staff role configuration (can use staff commands)
STAFF_ROLES = ["Overlord", "Staff", "Server Tech Support"]

# Command permission overrides - loaded from file
COMMAND_PERMISSIONS = {}

def load_command_permissions():
    """Load command permissions from file"""
    global COMMAND_PERMISSIONS
    try:
        if os.path.exists('command_permissions.json'):
            with open('command_permissions.json', 'r') as f:
                COMMAND_PERMISSIONS = json.load(f)
    except:
        COMMAND_PERMISSIONS = {}

# Load permissions on module import
load_command_permissions()

def find_optimal_teams(player_ids: list, player_mmrs: dict) -> tuple:
    """Find the optimal team split using exhaustive search.
    Returns (red_team, blue_team, mmr_diff)"""
    best_diff = float('inf')
    best_team1 = None
    best_team2 = None

    # Try all possible 4-player combinations for team 1
    for team1_combo in combinations(player_ids, 4):
        team1 = list(team1_combo)
        team2 = [p for p in player_ids if p not in team1]

        team1_mmr = sum(player_mmrs[uid] for uid in team1)
        team2_mmr = sum(player_mmrs[uid] for uid in team2)
        diff = abs(team1_mmr - team2_mmr)

        if diff < best_diff:
            best_diff = diff
            best_team1 = team1[:]
            best_team2 = team2[:]

            # Perfect balance found
            if diff == 0:
                break

    # Sort teams so higher MMR team is red
    team1_avg = sum(player_mmrs[uid] for uid in best_team1) / 4
    team2_avg = sum(player_mmrs[uid] for uid in best_team2) / 4

    if team2_avg > team1_avg:
        best_team1, best_team2 = best_team2, best_team1

    return best_team1, best_team2, best_diff

def has_admin_role():
    """Check if user has admin role (Overlord only)"""
    async def predicate(interaction: discord.Interaction):
        user_roles = [role.name for role in interaction.user.roles]
        if any(role in ADMIN_ROLES for role in user_roles):
            return True
        await interaction.response.send_message("❌ You need Overlord role!", ephemeral=True)
        return False
    return app_commands.check(predicate)

def has_staff_role():
    """Check if user has staff role"""
    async def predicate(interaction: discord.Interaction):
        user_roles = [role.name for role in interaction.user.roles]
        if any(role in STAFF_ROLES for role in user_roles):
            return True
        await interaction.response.send_message("❌ You need Overlord, Staff, or Server Tech Support role!", ephemeral=True)
        return False
    return app_commands.check(predicate)

def check_command_permission(command_name: str):
    """Dynamic permission check based on COMMAND_PERMISSIONS overrides"""
    async def predicate(interaction: discord.Interaction):
        global COMMAND_PERMISSIONS
        
        # Reload permissions in case they changed
        load_command_permissions()
        
        user_roles = [role.name for role in interaction.user.roles]
        permission_level = COMMAND_PERMISSIONS.get(command_name, None)
        
        # If no override, use default (allow - let the decorator handle it)
        if permission_level is None:
            return True
        
        if permission_level == "all":
            return True
        elif permission_level == "staff":
            if any(role in STAFF_ROLES for role in user_roles):
                return True
            await interaction.response.send_message("❌ You need Overlord, Staff, or Server Tech Support role!", ephemeral=True)
            return False
        elif permission_level == "admin":
            if any(role in ADMIN_ROLES for role in user_roles):
                return True
            await interaction.response.send_message("❌ You need Overlord role!", ephemeral=True)
            return False
        
        return True
    return app_commands.check(predicate)

def log_action(message: str):
    """Log actions"""
    from searchmatchmaking import log_action as queue_log
    queue_log(message)

async def get_player_mmr(user_id: int) -> int:
    """Get player MMR"""
    import STATSRANKS
    stats = STATSRANKS.get_player_stats(user_id)
    if stats and 'mmr' in stats:
        return stats['mmr']
    return 1500

def setup_commands(bot: commands.Bot, PREGAME_LOBBY_ID: int, POSTGAME_LOBBY_ID: int, QUEUE_CHANNEL_ID: int):
    """Setup all bot commands"""
    
    # Make STAFF_ROLES accessible for modification
    global STAFF_ROLES
    
    # ==== ADMIN COMMANDS ====
    
    @bot.tree.command(name="addstaffrole", description="[ADMIN] Add a role to the staff roles list")
    @has_admin_role()
    @app_commands.describe(role="The role to add to staff roles")
    async def add_staff_role(interaction: discord.Interaction, role: discord.Role):
        """Add a role to staff roles"""
        global STAFF_ROLES
        if role.name in STAFF_ROLES:
            await interaction.response.send_message(f"❌ **{role.name}** is already a staff role!", ephemeral=True)
            return
        
        STAFF_ROLES.append(role.name)
        log_action(f"Admin {interaction.user.name} added {role.name} to staff roles")
        await interaction.response.send_message(
            f"✅ Added **{role.name}** to staff roles!\n"
            f"Current staff roles: {', '.join(STAFF_ROLES)}",
            ephemeral=True
        )
    
    @bot.tree.command(name="removestaffrole", description="[ADMIN] Remove a role from the staff roles list")
    @has_admin_role()
    @app_commands.describe(role="The role to remove from staff roles")
    async def remove_staff_role(interaction: discord.Interaction, role: discord.Role):
        """Remove a role from staff roles"""
        global STAFF_ROLES
        if role.name not in STAFF_ROLES:
            await interaction.response.send_message(f"❌ **{role.name}** is not a staff role!", ephemeral=True)
            return
        
        if role.name == "Overlord":
            await interaction.response.send_message("❌ Cannot remove Overlord from staff roles!", ephemeral=True)
            return
        
        STAFF_ROLES.remove(role.name)
        log_action(f"Admin {interaction.user.name} removed {role.name} from staff roles")
        await interaction.response.send_message(
            f"✅ Removed **{role.name}** from staff roles!\n"
            f"Current staff roles: {', '.join(STAFF_ROLES)}",
            ephemeral=True
        )
    
    @bot.tree.command(name="liststaffroles", description="[ADMIN] List all current staff roles")
    @has_admin_role()
    async def list_staff_roles(interaction: discord.Interaction):
        """List all staff roles"""
        await interaction.response.send_message(
            f"📋 **Current Staff Roles:**\n{', '.join(STAFF_ROLES)}",
            ephemeral=True
        )
    
    @bot.tree.command(name="rolerulechange", description="[ADMIN] Change permission level for a command")
    @has_admin_role()
    @app_commands.describe(
        command_name="The command name (without /)",
        permission_level="Who can use this command"
    )
    @app_commands.choices(permission_level=[
        app_commands.Choice(name="Admin Only (Overlord)", value="admin"),
        app_commands.Choice(name="Staff (Overlord, Staff, Server Tech Support)", value="staff"),
        app_commands.Choice(name="Everyone", value="all")
    ])
    async def role_rule_change(interaction: discord.Interaction, command_name: str, permission_level: str):
        """Change permission level for a command"""
        global COMMAND_PERMISSIONS
        
        # List of valid commands
        valid_commands = [
            "addplayer", "removeplayer", "resetqueue", "cancelmatch", "cancelcurrent",
            "correctcurrent", "testmatchmaking", "swap", "ping", "silentping",
            "bannedroles", "requiredroles", "setupgameemojis",
            "logtestmatch", "adminunlinkalias", "linkalias", "unlinkalias", "myalias",
            "linktwitch", "unlinktwitch", "mytwitch", "stats", "leaderboard", "rank",
            "help", "addstaffrole", "removestaffrole", "liststaffroles", "rolerulechange",
            "listrolerules"
        ]
        
        # Protected commands that cannot be changed
        protected_commands = ["addstaffrole", "removestaffrole", "liststaffroles", "rolerulechange", "listrolerules"]
        
        command_name = command_name.lower().strip()
        
        if command_name.startswith("/"):
            command_name = command_name[1:]
        
        if command_name not in valid_commands:
            await interaction.response.send_message(
                f"❌ Unknown command: `{command_name}`\n"
                f"Valid commands: {', '.join(valid_commands[:10])}... (use /listrolerules to see all)",
                ephemeral=True
            )
            return
        
        if command_name in protected_commands:
            await interaction.response.send_message(
                f"❌ Cannot change permissions for `{command_name}` - it's a protected admin command!",
                ephemeral=True
            )
            return
        
        # Store the permission override
        COMMAND_PERMISSIONS[command_name] = permission_level
        
        # Save to file for persistence
        try:
            import json
            with open('command_permissions.json', 'w') as f:
                json.dump(COMMAND_PERMISSIONS, f, indent=2)
        except:
            pass
        
        level_display = {
            "admin": "Admin Only (Overlord)",
            "staff": "Staff (Overlord, Staff, Server Tech Support)",
            "all": "Everyone"
        }
        
        log_action(f"Admin {interaction.user.name} changed /{command_name} permission to {permission_level}")
        await interaction.response.send_message(
            f"✅ Changed `/{command_name}` permission to: **{level_display[permission_level]}**\n"
            f"⚠️ Note: Bot restart required to fully apply changes.",
            ephemeral=True
        )
    
    @bot.tree.command(name="listrolerules", description="[ADMIN] List all command permission overrides")
    @has_admin_role()
    async def list_role_rules(interaction: discord.Interaction):
        """List all command permission overrides"""
        global COMMAND_PERMISSIONS
        
        # Load from file
        try:
            import json
            import os
            if os.path.exists('command_permissions.json'):
                with open('command_permissions.json', 'r') as f:
                    COMMAND_PERMISSIONS = json.load(f)
        except:
            pass
        
        if not COMMAND_PERMISSIONS:
            await interaction.response.send_message(
                "📋 **Command Permission Overrides:**\nNo custom overrides set. All commands use default permissions.",
                ephemeral=True
            )
            return
        
        level_display = {
            "admin": "🔴 Admin",
            "staff": "🟡 Staff", 
            "all": "🟢 Everyone"
        }
        
        rules_text = "\n".join([
            f"`/{cmd}` → {level_display.get(level, level)}"
            for cmd, level in sorted(COMMAND_PERMISSIONS.items())
        ])
        
        await interaction.response.send_message(
            f"📋 **Command Permission Overrides:**\n{rules_text}",
            ephemeral=True
        )
    
    @bot.tree.command(name="addplayer", description="[STAFF] Add a player to the queue")
    @has_staff_role()
    async def add_player(interaction: discord.Interaction, user: discord.User):
        """Add player to queue"""
        from searchmatchmaking import queue_state, update_queue_embed, update_ping_message, MAX_QUEUE_SIZE
        from pregame import start_pregame
        
        if user.id in queue_state.queue:
            await interaction.response.send_message("❌ Player already in queue!", ephemeral=True)
            return
        
        if len(queue_state.queue) >= MAX_QUEUE_SIZE:
            await interaction.response.send_message("❌ Queue is full!", ephemeral=True)
            return
        
        queue_state.queue.append(user.id)
        queue_state.recent_action = {'type': 'join', 'user_id': user.id, 'name': user.name}
        log_action(f"Admin {interaction.user.name} added {user.name} to queue")
        
        channel = interaction.guild.get_channel(QUEUE_CHANNEL_ID)
        if channel:
            await update_queue_embed(channel)
        
        # Update ping message
        await update_ping_message(interaction.guild)
        
        # Check if queue is now full
        if len(queue_state.queue) == MAX_QUEUE_SIZE:
            await interaction.response.send_message(f"✅ Added {user.display_name} - Queue full! Starting pregame...", ephemeral=True)
            await start_pregame(channel if channel else interaction.channel)
        else:
            await interaction.response.send_message(f"✅ Added {user.display_name} to queue ({len(queue_state.queue)}/{MAX_QUEUE_SIZE})", ephemeral=True)
    
    @bot.tree.command(name="removeplayer", description="[STAFF] Remove a player from current matchmaking")
    @has_staff_role()
    async def remove_player(interaction: discord.Interaction, user: discord.User):
        """Remove player from active match"""
        from searchmatchmaking import queue_state
        from ingame import show_series_embed
        
        if not queue_state.current_series:
            await interaction.response.send_message("❌ No active match!", ephemeral=True)
            return
        
        series = queue_state.current_series
        all_players = series.red_team + series.blue_team
        
        if user.id not in all_players:
            await interaction.response.send_message("❌ Player not in current match!", ephemeral=True)
            return
        
        if user.id in series.red_team:
            series.red_team.remove(user.id)
            team = "Red"
        else:
            series.blue_team.remove(user.id)
            team = "Blue"
        
        log_action(f"Admin {interaction.user.name} removed {user.name} from {team} team")
        
        await interaction.response.defer()
        await show_series_embed(interaction.channel)
    
    @bot.tree.command(name="resetqueue", description="[STAFF] Reset the queue completely")
    @has_staff_role()
    async def reset_queue(interaction: discord.Interaction):
        """Reset queue"""
        from searchmatchmaking import queue_state, update_queue_embed, delete_ping_message
        
        queue_state.queue.clear()
        queue_state.queue_join_times.clear()
        queue_state.pregame_timer_task = None
        queue_state.pregame_timer_end = None
        queue_state.recent_action = None
        
        log_action(f"Admin {interaction.user.name} reset the queue")
        
        # Delete ping message since queue is empty
        await delete_ping_message()
        
        # Clear saved state
        try:
            import state_manager
            state_manager.clear_state()
        except:
            pass
        
        channel = interaction.guild.get_channel(QUEUE_CHANNEL_ID)
        if channel:
            await update_queue_embed(channel)
        
        # Send confirmation (not defer - that would leave "thinking")
        await interaction.response.send_message("✅ Queue reset!", ephemeral=True)
    
    @bot.tree.command(name="cancelmatch", description="[STAFF] Cancel a match by number (completed games stay recorded)")
    @has_staff_role()
    @app_commands.describe(
        match_number="The match/test number to cancel (e.g., 1 for Match #1 or Test 1)",
        test_mode="Is this a test match? (Default: False)"
    )
    async def cancel_queue(interaction: discord.Interaction, match_number: int, test_mode: bool = False):
        """Cancel match but register games"""
        from searchmatchmaking import queue_state, update_queue_embed
        from postgame import save_match_history
        
        # Check if there's a series OR if we're in pregame
        has_series = queue_state.current_series is not None
        has_pregame = hasattr(queue_state, 'pregame_vc_id') and queue_state.pregame_vc_id
        
        if not has_series and not has_pregame:
            await interaction.response.send_message("❌ No active match!", ephemeral=True)
            return
        
        # If we have a series, verify the match number and type
        if has_series:
            series = queue_state.current_series
            current_match_num = series.match_number
            current_is_test = series.test_mode
            
            if match_number != current_match_num or test_mode != current_is_test:
                current_type = "Test" if current_is_test else "Match #"
                requested_type = "Test" if test_mode else "Match #"
                await interaction.response.send_message(
                    f"❌ Match mismatch!\n"
                    f"You specified: **{requested_type}{match_number}**\n"
                    f"Current active match: **{current_type}{current_match_num}**",
                    ephemeral=True
                )
                return
        
        await interaction.response.defer()
        
        # Handle pregame cleanup
        if has_pregame:
            pregame_vc = interaction.guild.get_channel(queue_state.pregame_vc_id)
            if pregame_vc:
                try:
                    await pregame_vc.delete(reason="Match cancelled")
                    log_action("Deleted Pregame Lobby VC")
                except:
                    pass
            queue_state.pregame_vc_id = None
            
            # Delete pregame message
            if hasattr(queue_state, 'pregame_message') and queue_state.pregame_message:
                try:
                    await queue_state.pregame_message.delete()
                except:
                    pass
                queue_state.pregame_message = None
        
        match_type = "Test" if test_mode else "Match #"
        
        # Handle series cleanup
        if has_series:
            series = queue_state.current_series
            
            if series.games:
                log_action(f"Admin {interaction.user.name} cancelled {match_type}{match_number} - {len(series.games)} games played")
                save_match_history(series, 'CANCELLED')
            else:
                log_action(f"Admin {interaction.user.name} cancelled {match_type}{match_number} - no games played")
            
            # Move players to postgame
            postgame_vc = interaction.guild.get_channel(POSTGAME_LOBBY_ID)
            if postgame_vc:
                all_players = series.red_team + series.blue_team
                for user_id in all_players:
                    member = interaction.guild.get_member(user_id)
                    if member and member.voice:
                        try:
                            await member.move_to(postgame_vc)
                        except:
                            pass
            
            # Delete VCs
            if series.red_vc_id:
                red_vc = interaction.guild.get_channel(series.red_vc_id)
                if red_vc:
                    try:
                        await red_vc.delete(reason="Match cancelled")
                    except:
                        pass
            
            if series.blue_vc_id:
                blue_vc = interaction.guild.get_channel(series.blue_vc_id)
                if blue_vc:
                    try:
                        await blue_vc.delete(reason="Match cancelled")
                    except:
                        pass

            # Delete general chat embed
            try:
                from ingame import delete_general_chat_embed
                await delete_general_chat_embed(interaction.guild, series)
            except:
                pass

            # Delete series message in queue channel
            if series.series_message:
                try:
                    await series.series_message.delete()
                except:
                    pass

        # Clear state
        queue_state.current_series = None
        queue_state.queue.clear()
        queue_state.test_mode = False
        queue_state.testers = []

        # Clear saved state
        try:
            import state_manager
            state_manager.clear_state()
        except:
            pass

        channel = interaction.guild.get_channel(QUEUE_CHANNEL_ID)
        if channel:
            await update_queue_embed(channel)

        await interaction.followup.send(f"✅ {match_type}{match_number} has been cancelled!", ephemeral=True)
    
    @bot.tree.command(name="cancelcurrent", description="[STAFF] Cancel the current active match (any type)")
    @has_staff_role()
    async def cancel_current(interaction: discord.Interaction):
        """Cancel whatever match is currently active"""
        from searchmatchmaking import queue_state, update_queue_embed
        from postgame import save_match_history
        
        # Check if there's a series OR if we're in pregame
        has_series = queue_state.current_series is not None
        has_pregame = hasattr(queue_state, 'pregame_vc_id') and queue_state.pregame_vc_id
        
        if not has_series and not has_pregame:
            await interaction.response.send_message("❌ No active match or pregame!", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        # Handle pregame cleanup
        if has_pregame:
            pregame_vc = interaction.guild.get_channel(queue_state.pregame_vc_id)
            if pregame_vc:
                try:
                    await pregame_vc.delete(reason="Match cancelled")
                    log_action("Deleted Pregame Lobby VC")
                except:
                    pass
            queue_state.pregame_vc_id = None
            
            # Delete pregame message
            if hasattr(queue_state, 'pregame_message') and queue_state.pregame_message:
                try:
                    await queue_state.pregame_message.delete()
                except:
                    pass
                queue_state.pregame_message = None
        
        # Handle series cleanup
        if has_series:
            series = queue_state.current_series
            match_type = "Test" if series.test_mode else "Match #"
            match_num = series.match_number
            
            if series.games:
                log_action(f"Staff {interaction.user.name} cancelled {match_type}{match_num} - {len(series.games)} games played")
                save_match_history(series, 'CANCELLED')
            else:
                log_action(f"Staff {interaction.user.name} cancelled {match_type}{match_num} - no games played")
            
            # Move players to postgame
            postgame_vc = interaction.guild.get_channel(POSTGAME_LOBBY_ID)
            if postgame_vc:
                all_players = series.red_team + series.blue_team
                for user_id in all_players:
                    member = interaction.guild.get_member(user_id)
                    if member and member.voice:
                        try:
                            await member.move_to(postgame_vc)
                        except:
                            pass
            
            # Delete VCs
            if series.red_vc_id:
                red_vc = interaction.guild.get_channel(series.red_vc_id)
                if red_vc:
                    try:
                        await red_vc.delete(reason="Match cancelled")
                    except:
                        pass
            
            if series.blue_vc_id:
                blue_vc = interaction.guild.get_channel(series.blue_vc_id)
                if blue_vc:
                    try:
                        await blue_vc.delete(reason="Match cancelled")
                    except:
                        pass

            # Delete general chat embed
            try:
                from ingame import delete_general_chat_embed
                await delete_general_chat_embed(interaction.guild, series)
            except:
                pass

            # Delete series message in queue channel
            if series.series_message:
                try:
                    await series.series_message.delete()
                except:
                    pass

        # Clear all state
        queue_state.current_series = None
        queue_state.queue.clear()
        queue_state.test_mode = False
        queue_state.testers = []

        # Clear saved state
        try:
            import state_manager
            state_manager.clear_state()
        except:
            pass

        channel = interaction.guild.get_channel(QUEUE_CHANNEL_ID)
        if channel:
            await update_queue_embed(channel)

        if has_series:
            match_type = "Test" if queue_state.current_series is None and has_series else "Match"
            await interaction.followup.send(f"✅ Match cancelled!", ephemeral=True)
        else:
            await interaction.followup.send(f"✅ Pregame cancelled!", ephemeral=True)

    @bot.tree.command(name="deletematch", description="[STAFF] Delete a match from history by playlist and match number")
    @has_staff_role()
    @app_commands.describe(
        playlist="Which playlist's match to delete",
        match_number="The match number to delete"
    )
    @app_commands.choices(playlist=[
        app_commands.Choice(name="MLG 4v4", value="mlg_4v4"),
        app_commands.Choice(name="Team Hardcore", value="team_hardcore"),
        app_commands.Choice(name="Double Team", value="double_team"),
        app_commands.Choice(name="Head to Head", value="head_to_head"),
    ])
    async def delete_match(interaction: discord.Interaction, playlist: str, match_number: int):
        """Delete a match from history by playlist and match number"""
        # IMPORTANT: defer() must be called FIRST before any code that could fail
        await interaction.response.defer(ephemeral=True)

        try:
            import json
            import os

            # File paths for match history
            MLG_HISTORY_FILE = "MLG4v4.json"  # MLG 4v4 match history
            # Other playlists use per-playlist files via playlists.get_playlist_matches_file()

            playlist_names = {
                "mlg_4v4": "MLG 4v4",
                "team_hardcore": "Team Hardcore",
                "double_team": "Double Team",
                "head_to_head": "Head to Head"
            }
            playlist_name = playlist_names.get(playlist, playlist)

            if playlist == "mlg_4v4":
                # MLG 4v4 uses different history file
                history_file = MLG_HISTORY_FILE
                if not os.path.exists(history_file):
                    await interaction.followup.send(f"❌ No {playlist_name} match history found!", ephemeral=True)
                    return

                with open(history_file, 'r') as f:
                    history = json.load(f)

                # Find match by match number
                found_idx = None
                found_match = None
                for i, match in enumerate(history):
                    if match.get('match_number') == match_number:
                        found_idx = i
                        found_match = match
                        break

                if found_idx is None:
                    await interaction.followup.send(f"❌ Match #{match_number} not found in {playlist_name} history!", ephemeral=True)
                    return

                result = found_match.get('result', 'Unknown')
                timestamp = found_match.get('timestamp', 'Unknown')

                # Delete the match
                history.pop(found_idx)
                with open(history_file, 'w') as f:
                    json.dump(history, f, indent=2)

                log_action(f"Staff {interaction.user.name} deleted {playlist_name} Match #{match_number} from history")
                await interaction.followup.send(
                    f"✅ Deleted **{playlist_name} Match #{match_number}** from history\n"
                    f"Result: {result}\n"
                    f"Timestamp: {timestamp}",
                    ephemeral=True
                )
            else:
                # Other playlists use per-playlist history files
                from playlists import get_playlist_matches_file
                history_file = get_playlist_matches_file(playlist)

                if not os.path.exists(history_file):
                    await interaction.followup.send(f"❌ No {playlist_name} match history found! (file {history_file} does not exist)", ephemeral=True)
                    return

                with open(history_file, 'r') as f:
                    history = json.load(f)

                matches = history.get("matches", [])
                if len(matches) == 0:
                    await interaction.followup.send(f"❌ No matches found for {playlist_name}! (match list is empty)", ephemeral=True)
                    return

                # Find match by match number
                found_idx = None
                found_match = None
                for i, match in enumerate(matches):
                    if match.get('match_number') == match_number:
                        found_idx = i
                        found_match = match
                        break

                if found_idx is None:
                    # List available match numbers for helpfulness
                    available = [m.get('match_number') for m in matches if m.get('match_number')]
                    if available:
                        await interaction.followup.send(
                            f"❌ Match #{match_number} not found in {playlist_name} history!\n"
                            f"Available match numbers: {', '.join(map(str, sorted(available)))}",
                            ephemeral=True
                        )
                    else:
                        await interaction.followup.send(f"❌ Match #{match_number} not found in {playlist_name} history!", ephemeral=True)
                    return

                result = found_match.get('result', 'Unknown')
                timestamp = found_match.get('timestamp', 'Unknown')

                # Delete the match
                history["matches"].pop(found_idx)
                history["total_matches"] = len(history["matches"])
                with open(history_file, 'w') as f:
                    json.dump(history, f, indent=2)

                log_action(f"Staff {interaction.user.name} deleted {playlist_name} Match #{match_number} from {history_file}")
                await interaction.followup.send(
                    f"✅ Deleted **{playlist_name} Match #{match_number}** from history\n"
                    f"Result: {result}\n"
                    f"Timestamp: {timestamp}",
                    ephemeral=True
                )

        except Exception as e:
            log_action(f"Error in /deletematch: {e}")
            await interaction.followup.send(f"❌ Error deleting match: {e}", ephemeral=True)

    @bot.tree.command(name="correctcurrent", description="[STAFF] Correct a game result in a match")
    @has_staff_role()
    @app_commands.describe(
        playlist="Which playlist's match to correct",
        game_number="The game number to correct (1, 2, 3, etc.)",
        winner="The correct winner (RED/BLUE or TEAM1/TEAM2 or P1/P2)"
    )
    @app_commands.choices(playlist=[
        app_commands.Choice(name="MLG 4v4", value="mlg_4v4"),
        app_commands.Choice(name="Team Hardcore", value="team_hardcore"),
        app_commands.Choice(name="Double Team", value="double_team"),
        app_commands.Choice(name="Head to Head", value="head_to_head"),
    ])
    async def correct_current(interaction: discord.Interaction, playlist: str, game_number: int, winner: str):
        """Correct a game result in any playlist"""
        from searchmatchmaking import queue_state
        from ingame import show_series_embed

        if playlist == "mlg_4v4":
            # Original MLG 4v4 queue
            if not queue_state.current_series:
                await interaction.response.send_message("❌ No active MLG 4v4 match!", ephemeral=True)
                return

            series = queue_state.current_series

            if game_number < 1 or game_number > len(series.games):
                await interaction.response.send_message(
                    f"❌ Invalid game number! Must be between 1 and {len(series.games)}",
                    ephemeral=True
                )
                return

            winner_upper = winner.upper()
            if winner_upper not in ['RED', 'BLUE']:
                await interaction.response.send_message(
                    "❌ Winner must be 'RED' or 'BLUE'!",
                    ephemeral=True
                )
                return

            old_winner = series.games[game_number - 1]
            series.games[game_number - 1] = winner_upper

            log_action(f"Staff {interaction.user.name} corrected Game {game_number} from {old_winner} to {winner_upper} in MLG 4v4 Match #{series.match_number}")

            await interaction.response.defer()
            await show_series_embed(interaction.channel)
        else:
            # Other playlists
            try:
                import playlists
                ps = playlists.get_playlist_state(playlist)

                if not ps.current_match:
                    await interaction.response.send_message(f"❌ No active {ps.name} match!", ephemeral=True)
                    return

                match = ps.current_match

                if game_number < 1 or game_number > len(match.games):
                    await interaction.response.send_message(
                        f"❌ Invalid game number! Must be between 1 and {len(match.games)}",
                        ephemeral=True
                    )
                    return

                winner_upper = winner.upper()
                # Accept multiple formats
                if winner_upper in ['RED', 'TEAM1', 'P1', '1']:
                    winner_upper = 'TEAM1'
                elif winner_upper in ['BLUE', 'TEAM2', 'P2', '2']:
                    winner_upper = 'TEAM2'
                else:
                    await interaction.response.send_message(
                        "❌ Winner must be 'RED/BLUE', 'TEAM1/TEAM2', or 'P1/P2'!",
                        ephemeral=True
                    )
                    return

                old_winner = match.games[game_number - 1]
                match.games[game_number - 1] = winner_upper

                log_action(f"Staff {interaction.user.name} corrected Game {game_number} from {old_winner} to {winner_upper} in {match.get_match_label()}")

                await interaction.response.defer()
                await playlists.show_playlist_match_embed(interaction.channel, match)
            except Exception as e:
                await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)
    
    @bot.tree.command(name="bannedroles", description="[ADMIN] Set roles that cannot queue (comma separated)")
    @has_admin_role()
    async def banned_roles(interaction: discord.Interaction, roles: str):
        """Set banned roles"""
        import json
        role_list = [r.strip() for r in roles.split(',') if r.strip()]
        
        # Load existing config
        try:
            with open('queue_config.json', 'r') as f:
                config = json.load(f)
        except:
            config = {}
        
        config['banned_roles'] = role_list
        
        with open('queue_config.json', 'w') as f:
            json.dump(config, f, indent=2)
        
        # Push to GitHub
        try:
            import github_webhook
            github_webhook.update_queue_config_on_github()
        except:
            pass
        
        await interaction.response.defer()
        log_action(f"Admin {interaction.user.name} set banned roles: {role_list}")
    
    @bot.tree.command(name="requiredroles", description="[ADMIN] Set roles required to queue (comma separated)")
    @has_admin_role()
    async def required_roles(interaction: discord.Interaction, roles: str):
        """Set required roles"""
        import json
        role_list = [r.strip() for r in roles.split(',') if r.strip()]
        
        # Load existing config
        try:
            with open('queue_config.json', 'r') as f:
                config = json.load(f)
        except:
            config = {}
        
        config['required_roles'] = role_list
        
        with open('queue_config.json', 'w') as f:
            json.dump(config, f, indent=2)
        
        # Push to GitHub
        try:
            import github_webhook
            github_webhook.update_queue_config_on_github()
        except:
            pass
        
        await interaction.response.defer()
        log_action(f"Admin {interaction.user.name} set required roles: {role_list}")

    # NOTE: /silentrankrefresh removed - use /silentverify in STATSRANKS.py instead (duplicate functionality)

    @bot.tree.command(name='setupgameemojis', description='[ADMIN] Auto-detect game emoji IDs')
    @has_admin_role()
    async def setup_game_emojis(interaction: discord.Interaction):
        """Find all Game#RED and Game#BLUE emojis and save their IDs"""
        await interaction.response.defer(ephemeral=True)
        
        import json
        guild = interaction.guild
        
        # Find all game emojis
        game_emojis = {}
        found_count = 0
        missing = []
        
        for i in range(1, 21):
            red_name = f"Game{i}RED"
            blue_name = f"Game{i}BLUE"
            
            red_emoji = discord.utils.get(guild.emojis, name=red_name)
            blue_emoji = discord.utils.get(guild.emojis, name=blue_name)
            
            if red_emoji:
                if i not in game_emojis:
                    game_emojis[i] = {}
                game_emojis[i]["RED"] = str(red_emoji.id)
                found_count += 1
            else:
                missing.append(red_name)
            
            if blue_emoji:
                if i not in game_emojis:
                    game_emojis[i] = {}
                game_emojis[i]["BLUE"] = str(blue_emoji.id)
                found_count += 1
            else:
                missing.append(blue_name)
        
        # Save to file
        with open('game_emojis.json', 'w') as f:
            json.dump(game_emojis, f, indent=2)
        
        # Build response
        response = f"✅ **Game Emojis Setup Complete!**\n\n"
        response += f"**Found:** {found_count}/40 emojis\n"
        response += f"**Saved to:** game_emojis.json\n\n"
        
        if missing:
            response += f"**Missing ({len(missing)}):**\n"
            response += ", ".join(missing[:10])
            if len(missing) > 10:
                response += f"... and {len(missing) - 10} more"
        else:
            response += "🎉 All 40 game emojis found!"
        
        await interaction.followup.send(response, ephemeral=True)
        log_action(f"{interaction.user.display_name} ran game emoji setup - found {found_count}/40")
    
    @bot.tree.command(name='logtestmatch', description='[ADMIN] Log a test match with all map/gametype combinations')
    @has_admin_role()
    async def log_test_match(interaction: discord.Interaction):
        """Generate a test match with all valid map/gametype combinations"""
        await interaction.response.defer(ephemeral=True)
        
        import json
        import os
        from datetime import datetime
        import STATSRANKS
        
        guild = interaction.guild
        
        # Get 8 random members (exclude bots)
        all_members = [m for m in guild.members if not m.bot]
        if len(all_members) < 8:
            await interaction.followup.send("❌ Not enough members in server (need 8)", ephemeral=True)
            return
        
        random_players = random.sample(all_members, 8)
        player_ids = [m.id for m in random_players]
        
        # Get MMRs and balance teams
        player_mmrs = {}
        for user_id in player_ids:
            mmr = await get_player_mmr(user_id)
            player_mmrs[user_id] = mmr
        
        # Simple balance: sort by MMR and alternate
        sorted_players = sorted(player_ids, key=lambda x: player_mmrs[x], reverse=True)
        red_team = [sorted_players[i] for i in range(0, 8, 2)]
        blue_team = [sorted_players[i] for i in range(1, 8, 2)]
        
        red_avg = int(sum(player_mmrs[uid] for uid in red_team) / len(red_team))
        blue_avg = int(sum(player_mmrs[uid] for uid in blue_team) / len(blue_team))
        
        # Build all valid map/gametype combinations
        MAP_GAMETYPES = {
            "Midship": ["MLG CTF5", "MLG Team Slayer", "MLG Oddball", "MLG Bomb"],
            "Beaver Creek": ["MLG Team Slayer"],
            "Lockout": ["MLG Team Slayer", "MLG Oddball"],
            "Warlock": ["MLG Team Slayer", "MLG CTF5"],
            "Sanctuary": ["MLG CTF3", "MLG Team Slayer"]
        }
        
        all_combinations = []
        for map_name, gametypes in MAP_GAMETYPES.items():
            for gametype in gametypes:
                all_combinations.append((map_name, gametype))
        
        # Create games with RANDOM winners
        games = []
        for i, (map_name, gametype) in enumerate(all_combinations):
            winner = random.choice(["RED", "BLUE"])
            loser = "BLUE" if winner == "RED" else "RED"
            
            games.append({
                "game_number": i + 1,
                "winner": winner,
                "loser": loser,
                "map": map_name,
                "gametype": gametype
            })
        
        # Calculate final score
        red_wins = sum(1 for g in games if g["winner"] == "RED")
        blue_wins = sum(1 for g in games if g["winner"] == "BLUE")
        overall_winner = "RED" if red_wins > blue_wins else "BLUE" if blue_wins > red_wins else "TIE"
        
        # Create test match entry
        timestamp = datetime.now().isoformat()
        timestamp_display = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        match_entry = {
            "match_type": "TEST_LOG",
            "match_id": "test_log_" + datetime.now().strftime('%Y%m%d_%H%M%S'),
            "timestamp": timestamp,
            "timestamp_display": timestamp_display,
            "winner": overall_winner,
            "final_score": {
                "red": red_wins,
                "blue": blue_wins
            },
            "teams": {
                "red": {
                    "players": red_team,
                    "avg_mmr": red_avg
                },
                "blue": {
                    "players": blue_team,
                    "avg_mmr": blue_avg
                }
            },
            "games": games,
            "total_games_played": len(games),
            "logged_by": interaction.user.id,
            "logged_by_name": interaction.user.display_name
        }
        
        # Load or create testmatchhistory.json
        history_file = 'testmatchhistory.json'
        if os.path.exists(history_file):
            try:
                with open(history_file, 'r') as f:
                    history = json.load(f)
            except:
                history = {"total_test_logs": 0, "matches": []}
        else:
            history = {"total_test_logs": 0, "matches": []}
        
        # Add match
        history["total_test_logs"] = history.get("total_test_logs", 0) + 1
        history["matches"].append(match_entry)
        
        # Save
        with open(history_file, 'w') as f:
            json.dump(history, f, indent=2)
        
        log_action(f"{interaction.user.display_name} logged test match with {len(games)} games")
        
        # Push to GitHub
        try:
            import github_webhook
            github_webhook.update_testmatchhistory_on_github()
        except Exception as e:
            log_action(f"Failed to push test match history to GitHub: {e}")
        
        # Send summary
        await interaction.followup.send(
            f"✅ **Test match logged to testmatchhistory.json**\n\n"
            f"**Teams:**\n"
            f"🔴 Red Team (Avg MMR: {red_avg})\n"
            f"🔵 Blue Team (Avg MMR: {blue_avg})\n\n"
            f"**Games:** {len(games)} total\n"
            f"**Final Score:** Red {red_wins} - {blue_wins} Blue\n"
            f"**Winner:** {overall_winner}\n\n"
            f"All valid map/gametype combinations played with alternating wins!",
            ephemeral=True
        )
    
    # ==== TEST COMMANDS ====
    
    @bot.tree.command(name='testmatchmaking', description='[STAFF] Start a 4v4 test match with 2 testers + 6 random players with MMR')
    @has_staff_role()
    async def test_matchmaking(interaction: discord.Interaction):
        """Start a 4v4 test match - 2 testers from VC + 6 random players with MMR (only testers can vote)"""
        await interaction.response.defer()
        
        from searchmatchmaking import queue_state, log_action
        from pregame import start_pregame, PREGAME_LOBBY_ID
        import STATSRANKS
        
        guild = interaction.guild
        
        # Check if there's already a match in progress
        if queue_state.current_series:
            await interaction.followup.send("❌ A match is already in progress!", ephemeral=True)
            return
        
        # Check if pregame is active
        if hasattr(queue_state, 'pregame_vc_id') and queue_state.pregame_vc_id:
            await interaction.followup.send("❌ A pregame is already in progress!", ephemeral=True)
            return
        
        # Get members from test voice channel
        TEST_VC_ID = 1099821085714808883
        test_vc = guild.get_channel(TEST_VC_ID)
        
        if not test_vc:
            await interaction.followup.send("❌ Test voice channel not found!", ephemeral=True)
            return
        
        # Get members in the voice channel (exclude bots)
        vc_members = [m for m in test_vc.members if not m.bot]
        
        if len(vc_members) < 2:
            await interaction.followup.send(
                f"❌ Need at least 2 people in <#{TEST_VC_ID}> to start test match.\n"
                f"Currently: {len(vc_members)} member(s)",
                ephemeral=True
            )
            return
        
        # Use first 2 members as testers (they can vote)
        tester1 = vc_members[0]
        tester2 = vc_members[1]
        tester_ids = [tester1.id, tester2.id]
        
        # Check if testers have existing MMR stats
        tester1_stats = STATSRANKS.get_existing_player_stats(tester1.id)
        tester2_stats = STATSRANKS.get_existing_player_stats(tester2.id)
        
        if not tester1_stats or 'mmr' not in tester1_stats:
            await interaction.followup.send(
                f"❌ {tester1.mention} doesn't have MMR stats!\n"
                f"They need to be given an MMR before testing.",
                ephemeral=True
            )
            return
        
        if not tester2_stats or 'mmr' not in tester2_stats:
            await interaction.followup.send(
                f"❌ {tester2.mention} doesn't have MMR stats!\n"
                f"They need to be given an MMR before testing.",
                ephemeral=True
            )
            return
        
        tester1_mmr = tester1_stats['mmr']
        tester2_mmr = tester2_stats['mmr']
        
        log_action(f"Tester 1: {tester1.display_name} - MMR: {tester1_mmr}")
        log_action(f"Tester 2: {tester2.display_name} - MMR: {tester2_mmr}")
        
        # Get members with EXISTING stats only (exclude bots and testers)
        members_with_mmr = []
        for member in guild.members:
            if member.bot or member.id in tester_ids:
                continue
            # Only include players who already have stats in the file
            stats = STATSRANKS.get_existing_player_stats(member.id)
            if stats and 'mmr' in stats:
                members_with_mmr.append((member, stats['mmr']))
        
        if len(members_with_mmr) < 6:
            await interaction.followup.send(
                f"❌ Not enough members with MMR stats!\n"
                f"Found: {len(members_with_mmr)} players with MMR\n"
                f"Need: 6 players for fillers\n\n"
                f"Use `/setmmr` to give players an MMR rating.",
                ephemeral=True
            )
            return
        
        # Randomly select 6 players with stats
        filler_players = random.sample(members_with_mmr, 6)
        filler_ids = [m.id for m, mmr in filler_players]
        
        # Log selected fillers with their MMR
        for member, mmr in filler_players:
            log_action(f"Filler: {member.display_name} - MMR: {mmr}")
        
        # All 8 players for the match
        all_test_players = tester_ids + filler_ids
        
        log_action(f"Test matchmaking started: {tester1.display_name} ({tester1_mmr}) and {tester2.display_name} ({tester2_mmr}) + 6 fillers")
        log_action(f"Only testers can vote: {tester1.display_name}, {tester2.display_name}")
        
        # Store testers list in queue_state so pregame/ingame can access it
        queue_state.testers = tester_ids
        
        # Start pregame with all 8 players - this shows the team selection screen
        await start_pregame(interaction.channel, test_mode=True, test_players=all_test_players)
        
        # Send a followup to dismiss the "thinking" message (delete it immediately)
        try:
            msg = await interaction.followup.send("✅", ephemeral=True)
            await msg.delete()
        except:
            pass
    
    @bot.tree.command(name='swap', description='Swap a player on Red team with a player on Blue team')
    @app_commands.describe(
        red_player="Player currently on RED team to swap",
        blue_player="Player currently on BLUE team to swap"
    )
    async def swap_players(
        interaction: discord.Interaction,
        red_player: discord.Member,
        blue_player: discord.Member
    ):
        """Swap players between teams mid-series"""
        from searchmatchmaking import queue_state, log_action
        from pregame import get_player_mmr
        
        if not queue_state.current_series:
            await interaction.response.send_message("❌ No active series to swap players in!", ephemeral=True)
            return
        
        series = queue_state.current_series
        
        # Verify players are on correct teams
        if red_player.id not in series.red_team:
            await interaction.response.send_message(f"❌ {red_player.display_name} is not on Red team!", ephemeral=True)
            return
        
        if blue_player.id not in series.blue_team:
            await interaction.response.send_message(f"❌ {blue_player.display_name} is not on Blue team!", ephemeral=True)
            return
        
        # Perform swap
        red_index = series.red_team.index(red_player.id)
        blue_index = series.blue_team.index(blue_player.id)
        
        series.red_team[red_index] = blue_player.id
        series.blue_team[blue_index] = red_player.id
        
        # Track swap history
        if not hasattr(series, 'swap_history'):
            series.swap_history = []
        
        series.swap_history.append({
            "game": series.current_game,
            "red_to_blue": red_player.id,
            "blue_to_red": blue_player.id,
            "timestamp": datetime.now().isoformat()
        })
        
        log_action(f"Swap: {red_player.display_name} (RED→BLUE) ↔ {blue_player.display_name} (BLUE→RED)")
        
        # Move players to new VCs if they're in voice and VCs exist
        guild = interaction.guild
        if hasattr(series, 'red_vc_id') and hasattr(series, 'blue_vc_id'):
            red_vc = guild.get_channel(series.red_vc_id)
            blue_vc = guild.get_channel(series.blue_vc_id)
            
            if red_vc and blue_vc:
                # Move red_player to blue VC
                if red_player.voice and red_player.voice.channel:
                    try:
                        await red_player.move_to(blue_vc)
                    except:
                        pass
                
                # Move blue_player to red VC
                if blue_player.voice and blue_player.voice.channel:
                    try:
                        await blue_player.move_to(red_vc)
                    except:
                        pass
                
                # Recalculate MMR averages and rename VCs
                red_mmrs = []
                blue_mmrs = []
                for uid in series.red_team:
                    mmr = await get_player_mmr(uid)
                    red_mmrs.append(mmr)
                for uid in series.blue_team:
                    mmr = await get_player_mmr(uid)
                    blue_mmrs.append(mmr)
                
                new_red_avg = int(sum(red_mmrs) / len(red_mmrs)) if red_mmrs else 1500
                new_blue_avg = int(sum(blue_mmrs) / len(blue_mmrs)) if blue_mmrs else 1500
                
                # Rename VCs with new MMR averages
                series_label = series.series_number
                try:
                    await red_vc.edit(name=f"🔴 Red {series_label} - {new_red_avg} MMR")
                    await blue_vc.edit(name=f"🔵 Blue {series_label} - {new_blue_avg} MMR")
                    log_action(f"VCs renamed after swap - Red: {new_red_avg} MMR, Blue: {new_blue_avg} MMR")
                except Exception as e:
                    log_action(f"Failed to rename VCs: {e}")
        
        # Update series embed if it exists
        from ingame import SeriesView
        if series.series_message:
            try:
                view = SeriesView(series)
                await view.update_series_embed(interaction.channel)
            except:
                pass
        
        # Save state
        try:
            import state_manager
            state_manager.save_state()
        except:
            pass
        
        await interaction.response.send_message(
            f"✅ Swapped **{red_player.display_name}** ↔ **{blue_player.display_name}**\n"
            f"Voice channels updated with new MMR averages.",
            ephemeral=True
        )
    
    @bot.tree.command(name='setgamestats', description='[STAFF] Set map and gametype for a completed game')
    @app_commands.describe(
        game_number="The game number (1, 2, 3, etc.)",
        map_name="The map played",
        gametype="The gametype played"
    )
    @has_staff_role()
    async def set_game_stats(
        interaction: discord.Interaction,
        game_number: int,
        map_name: str,
        gametype: str
    ):
        """Set map and gametype stats for a completed game"""
        from searchmatchmaking import queue_state, log_action
        
        # Check if there's an active series
        if not queue_state.current_series:
            await interaction.response.send_message("❌ No active match!", ephemeral=True)
            return
        
        series = queue_state.current_series
        
        # Validate game number
        if game_number < 1:
            await interaction.response.send_message("❌ Game number must be 1 or higher!", ephemeral=True)
            return
        
        if game_number > len(series.games):
            await interaction.response.send_message(
                f"❌ Game {game_number} hasn't been played yet! Only {len(series.games)} game(s) completed.",
                ephemeral=True
            )
            return
        
        # Set the stats
        series.game_stats[game_number] = {
            "map": map_name.strip(),
            "gametype": gametype.strip()
        }
        
        log_action(f"Game {game_number} stats set: {map_name} - {gametype}")
        
        # Update series embed
        from ingame import SeriesView
        if series.series_message:
            try:
                view = SeriesView(series)
                await view.update_series_embed(interaction.channel)
            except Exception as e:
                log_action(f"Failed to update series embed: {e}")
        
        # Update general chat embed
        try:
            from ingame import update_general_chat_embed
            await update_general_chat_embed(interaction.guild, series)
        except Exception as e:
            log_action(f"Failed to update general chat embed: {e}")
        
        await interaction.response.send_message(
            f"✅ Set Game {game_number} stats: **{map_name}** - **{gametype}**",
            ephemeral=True
        )
    
    # ========== ALIAS COMMANDS ==========
    
    @bot.tree.command(name="linkalias", description="Link an in-game alias to your Discord account")
    @app_commands.describe(alias="Your in-game name/alias (e.g., your gamertag)")
    async def link_alias(interaction: discord.Interaction, alias: str):
        """Link an in-game alias - can have multiple"""
        import twitch
        
        alias = alias.strip()
        
        if not alias:
            await interaction.response.send_message("❌ Please provide an alias.", ephemeral=True)
            return
        
        if len(alias) > 50:
            await interaction.response.send_message("❌ Alias too long (max 50 characters).", ephemeral=True)
            return
        
        players = twitch.load_players()
        user_id = str(interaction.user.id)
        
        # Initialize player entry if doesn't exist
        if user_id not in players:
            players[user_id] = {}
        
        # Initialize aliases list if doesn't exist
        if "aliases" not in players[user_id]:
            players[user_id]["aliases"] = []
        
        # Check if alias already linked to this user
        if alias.lower() in [a.lower() for a in players[user_id]["aliases"]]:
            await interaction.response.send_message(
                f"❌ Alias **{alias}** is already linked to your account.",
                ephemeral=True
            )
            return
        
        # Check if alias is taken by someone else
        for other_id, other_data in players.items():
            if other_id != user_id:
                other_aliases = other_data.get("aliases", [])
                if alias.lower() in [a.lower() for a in other_aliases]:
                    await interaction.response.send_message(
                        f"❌ Alias **{alias}** is already linked to another user.",
                        ephemeral=True
                    )
                    return
        
        # Add alias
        players[user_id]["aliases"].append(alias)
        twitch.save_players(players)
        
        # Show all aliases
        all_aliases = players[user_id]["aliases"]
        await interaction.response.send_message(
            f"✅ Alias **{alias}** linked!\n"
            f"Your aliases: {', '.join(all_aliases)}",
            ephemeral=True
        )
        log_action(f"{interaction.user.name} linked alias: {alias}")
    
    @bot.tree.command(name="unlinkalias", description="[STAFF] Remove an in-game alias from a player")
    @app_commands.describe(alias="The alias to remove", user="The user to remove alias from (optional, defaults to yourself)")
    @has_staff_role()
    async def unlink_alias(interaction: discord.Interaction, alias: str, user: discord.Member = None):
        """Remove an in-game alias (staff only)"""
        import twitch

        # Target user (defaults to command user if not specified)
        target_user = user or interaction.user

        alias = alias.strip()
        players = twitch.load_players()
        user_id = str(target_user.id)

        if user_id not in players or "aliases" not in players[user_id]:
            await interaction.response.send_message(
                f"❌ **{target_user.display_name}** has no aliases linked.",
                ephemeral=True
            )
            return

        # Find alias (case-insensitive)
        found_alias = None
        for a in players[user_id]["aliases"]:
            if a.lower() == alias.lower():
                found_alias = a
                break

        if not found_alias:
            await interaction.response.send_message(
                f"❌ Alias **{alias}** not found in **{target_user.display_name}**'s linked aliases.",
                ephemeral=True
            )
            return

        # Remove alias
        players[user_id]["aliases"].remove(found_alias)
        twitch.save_players(players)

        remaining = players[user_id].get("aliases", [])
        if remaining:
            await interaction.response.send_message(
                f"✅ Alias **{found_alias}** removed from **{target_user.display_name}**.\n"
                f"Remaining aliases: {', '.join(remaining)}",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"✅ Alias **{found_alias}** removed. **{target_user.display_name}** has no more aliases.",
                ephemeral=True
            )
        log_action(f"{interaction.user.name} unlinked alias '{found_alias}' from {target_user.display_name}")
    
    @bot.tree.command(name="myaliases", description="View your linked in-game aliases")
    async def my_aliases(interaction: discord.Interaction):
        """View your linked aliases"""
        import twitch
        
        players = twitch.load_players()
        user_id = str(interaction.user.id)
        
        if user_id not in players or not players[user_id].get("aliases"):
            await interaction.response.send_message(
                "You have no aliases linked. Use `/linkalias` to add one.",
                ephemeral=True
            )
            return
        
        aliases = players[user_id]["aliases"]
        await interaction.response.send_message(
            f"Your aliases: **{', '.join(aliases)}**",
            ephemeral=True
        )
    
    @bot.tree.command(name="checkaliases", description="Check someone's in-game aliases")
    @app_commands.describe(user="The user to check")
    async def check_aliases(interaction: discord.Interaction, user: discord.Member):
        """Check someone's aliases"""
        import twitch
        
        players = twitch.load_players()
        user_id = str(user.id)
        
        if user_id not in players or not players[user_id].get("aliases"):
            await interaction.response.send_message(
                f"{user.display_name} has no aliases linked.",
                ephemeral=True
            )
            return
        
        aliases = players[user_id]["aliases"]
        await interaction.response.send_message(
            f"{user.display_name}'s aliases: **{', '.join(aliases)}**",
            ephemeral=True
        )
    
    @bot.tree.command(name="adminunlinkalias", description="[ADMIN] Remove an alias from someone")
    @has_admin_role()
    @app_commands.describe(user="The user", alias="The alias to remove")
    async def admin_unlink_alias(interaction: discord.Interaction, user: discord.Member, alias: str):
        """Admin: Remove someone's alias"""
        import twitch
        
        alias = alias.strip()
        players = twitch.load_players()
        user_id = str(user.id)
        
        if user_id not in players or "aliases" not in players[user_id]:
            await interaction.response.send_message(
                f"❌ {user.display_name} has no aliases linked.",
                ephemeral=True
            )
            return
        
        # Find alias (case-insensitive)
        found_alias = None
        for a in players[user_id]["aliases"]:
            if a.lower() == alias.lower():
                found_alias = a
                break
        
        if not found_alias:
            await interaction.response.send_message(
                f"❌ Alias **{alias}** not found for {user.display_name}.",
                ephemeral=True
            )
            return
        
        players[user_id]["aliases"].remove(found_alias)
        twitch.save_players(players)
        
        await interaction.response.defer()
        log_action(f"Admin {interaction.user.name} removed alias '{found_alias}' from {user.display_name}")
    
    @bot.tree.command(name='testmatchmakingred', description='[LEGACY] Test matchmaking as RED team')
    async def test_matchmaking_red(interaction: discord.Interaction):
        """Test queue for RED team - 8 random members, balanced, tester moved to red VC"""
        await interaction.response.defer(ephemeral=True)
        
        from searchmatchmaking import queue_state, log_action
        from pregame import finalize_teams, PREGAME_LOBBY_ID
        
        # Check if there's already a match in progress
        if queue_state.current_series:
            await interaction.followup.send("❌ A match is already in progress!", ephemeral=True)
            return
        
        guild = interaction.guild
        
        # Get 8 random members (exclude bots)
        all_members = [m for m in guild.members if not m.bot]
        if len(all_members) < 8:
            await interaction.followup.send("❌ Not enough members in server for test (need 8)")
            return
        
        random_players = random.sample(all_members, 8)
        player_ids = [m.id for m in random_players]
        
        # Get MMRs and balance teams
        player_mmrs = {}
        for user_id in player_ids:
            player_mmrs[user_id] = await get_player_mmr(user_id)
        
        # Sort by MMR and snake draft
        sorted_players = sorted(player_mmrs.items(), key=lambda x: x[1], reverse=True)
        red_team = []
        blue_team = []
        
        for i, (user_id, mmr) in enumerate(sorted_players):
            if i % 2 == 0:
                red_team.append(user_id)
            else:
                blue_team.append(user_id)
        
        # Optimize balance
        red_mmr = sum(player_mmrs[uid] for uid in red_team)
        blue_mmr = sum(player_mmrs[uid] for uid in blue_team)
        
        best_diff = abs(red_mmr - blue_mmr)
        best_red = red_team[:]
        best_blue = blue_team[:]
        
        for i in range(len(red_team)):
            for j in range(len(blue_team)):
                test_red = red_team[:]
                test_blue = blue_team[:]
                test_red[i], test_blue[j] = test_blue[j], test_red[i]
                
                test_red_mmr = sum(player_mmrs[uid] for uid in test_red)
                test_blue_mmr = sum(player_mmrs[uid] for uid in test_blue)
                diff = abs(test_red_mmr - test_blue_mmr)
                
                if diff < best_diff:
                    best_diff = diff
                    best_red = test_red
                    best_blue = test_blue
        
        # FIRST: Move tester to pregame lobby
        pregame_vc = guild.get_channel(PREGAME_LOBBY_ID)
        tester = interaction.user
        if tester.voice and pregame_vc:
            try:
                await tester.move_to(pregame_vc)
                log_action(f"Moved tester {tester.name} to pregame lobby")
            except Exception as e:
                log_action(f"Failed to move tester to pregame: {e}")
        
        log_action(f"Test RED queue started by {interaction.user.name} - Balanced teams (MMR diff: {best_diff})")
        
        # Use finalize_teams with test_mode=True - this doesn't touch main queue
        await finalize_teams(interaction.channel, best_red, best_blue, test_mode=True)
        
        # THEN: Manually move tester to RED VC since they're testing red
        if tester.voice and queue_state.current_series:
            red_vc = guild.get_channel(queue_state.current_series.red_vc_id)
            if red_vc:
                try:
                    await tester.move_to(red_vc)
                    log_action(f"Moved tester {tester.name} to RED VC for testing")
                except Exception as e:
                    log_action(f"Failed to move tester to red VC: {e}")
    
    @bot.tree.command(name='testmatchmakingblue', description='Test matchmaking as BLUE team')
    async def test_matchmaking_blue(interaction: discord.Interaction):
        """Test queue for BLUE team - 8 random members, balanced, tester moved to blue VC"""
        await interaction.response.defer(ephemeral=True)
        
        from searchmatchmaking import queue_state, log_action
        from pregame import finalize_teams, PREGAME_LOBBY_ID
        
        # Check if there's already a match in progress
        if queue_state.current_series:
            await interaction.followup.send("❌ A match is already in progress!", ephemeral=True)
            return
        
        guild = interaction.guild
        
        # Get 8 random members (exclude bots)
        all_members = [m for m in guild.members if not m.bot]
        if len(all_members) < 8:
            await interaction.followup.send("❌ Not enough members in server for test (need 8)")
            return
        
        random_players = random.sample(all_members, 8)
        player_ids = [m.id for m in random_players]
        
        # Get MMRs and balance teams
        player_mmrs = {}
        for user_id in player_ids:
            player_mmrs[user_id] = await get_player_mmr(user_id)
        
        # Sort by MMR and snake draft
        sorted_players = sorted(player_mmrs.items(), key=lambda x: x[1], reverse=True)
        red_team = []
        blue_team = []
        
        for i, (user_id, mmr) in enumerate(sorted_players):
            if i % 2 == 0:
                red_team.append(user_id)
            else:
                blue_team.append(user_id)
        
        # Optimize balance
        red_mmr = sum(player_mmrs[uid] for uid in red_team)
        blue_mmr = sum(player_mmrs[uid] for uid in blue_team)
        
        best_diff = abs(red_mmr - blue_mmr)
        best_red = red_team[:]
        best_blue = blue_team[:]
        
        for i in range(len(red_team)):
            for j in range(len(blue_team)):
                test_red = red_team[:]
                test_blue = blue_team[:]
                test_red[i], test_blue[j] = test_blue[j], test_red[i]
                
                test_red_mmr = sum(player_mmrs[uid] for uid in test_red)
                test_blue_mmr = sum(player_mmrs[uid] for uid in test_blue)
                diff = abs(test_red_mmr - test_blue_mmr)
                
                if diff < best_diff:
                    best_diff = diff
                    best_red = test_red
                    best_blue = test_blue
        
        # FIRST: Move tester to pregame lobby
        pregame_vc = guild.get_channel(PREGAME_LOBBY_ID)
        tester = interaction.user
        if tester.voice and pregame_vc:
            try:
                await tester.move_to(pregame_vc)
                log_action(f"Moved tester {tester.name} to pregame lobby")
            except Exception as e:
                log_action(f"Failed to move tester to pregame: {e}")
        
        log_action(f"Test BLUE queue started by {interaction.user.name} - Balanced teams (MMR diff: {best_diff})")
        
        # Use finalize_teams with test_mode=True - this doesn't touch main queue
        await finalize_teams(interaction.channel, best_red, best_blue, test_mode=True)
        
        # THEN: Manually move tester to BLUE VC since they're testing blue
        if tester.voice and queue_state.current_series:
            blue_vc = guild.get_channel(queue_state.current_series.blue_vc_id)
            if blue_vc:
                try:
                    await tester.move_to(blue_vc)
                    log_action(f"Moved tester {tester.name} to BLUE VC for testing")
                except Exception as e:
                    log_action(f"Failed to move tester to blue VC: {e}")
    
    # ==== PUBLIC COMMANDS ====
    
    @bot.tree.command(name='help', description='Show all available commands')
    async def help_command(interaction: discord.Interaction):
        """Show all commands with availability info"""
        user_roles = [role.name for role in interaction.user.roles]
        is_admin = any(role in ADMIN_ROLES for role in user_roles)
        is_staff = any(role in STAFF_ROLES for role in user_roles)

        # Build command list
        commands_list = []

        # Public Commands
        commands_list.append("**📊 STATS & INFO**")
        commands_list.append("`/playerstats` - View player stats and MMR")
        commands_list.append("`/leaderboard` - View MMR leaderboard")
        commands_list.append("`/verifystats` - Verify your stats are correct")
        commands_list.append("`/help` - Show this help message")
        commands_list.append("")

        commands_list.append("**🎮 MATCHMAKING**")
        commands_list.append("`/swap` - Swap teams with another player")
        commands_list.append("`/stream` - Set stream link for current match")
        commands_list.append("")

        commands_list.append("**📺 TWITCH**")
        commands_list.append("`/settwitch` - Link your Twitch account")
        commands_list.append("`/mytwitch` - View your linked Twitch")
        commands_list.append("`/checktwitch` - Check another player's Twitch")
        commands_list.append("")

        commands_list.append("**🏷️ ALIASES (Gamertags)**")
        commands_list.append("`/linkalias` - Link a gamertag to your account")
        commands_list.append("`/myaliases` - View your linked gamertags")
        commands_list.append("`/checkaliases` - Check another player's aliases")

        # Staff Commands
        if is_staff or is_admin:
            commands_list.append("")
            commands_list.append("**⚙️ STAFF - QUEUE** `[STAFF]`")
            commands_list.append("`/addplayer` - Add a player to queue")
            commands_list.append("`/removeplayer` - Remove a player from queue")
            commands_list.append("`/resetqueue` - Clear the queue")
            commands_list.append("`/pause` - Pause matchmaking")
            commands_list.append("`/unpause` - Resume matchmaking")
            commands_list.append("`/resetmatchmaking` - Full reset of matchmaking")
            commands_list.append("")

            commands_list.append("**⚙️ STAFF - MATCH** `[STAFF]`")
            commands_list.append("`/cancelmatch` - Cancel the current match")
            commands_list.append("`/correctcurrent` - Correct current match stats")
            commands_list.append("`/setgamestats` - Manually set game stats")
            commands_list.append("`/adminarrange` - Arrange teams manually")
            commands_list.append("`/adminguestmatch` - Start a guest match")
            commands_list.append("`/manualmatchentry` - Manual match entry")
            commands_list.append("")

            commands_list.append("**⚙️ STAFF - GUESTS** `[STAFF]`")
            commands_list.append("`/guest` - Add a guest player")
            commands_list.append("`/removeguest` - Remove a guest player")
            commands_list.append("")

            commands_list.append("**⚙️ STAFF - PLAYERS** `[STAFF]`")
            commands_list.append("`/mmr` - Set/view player MMR")
            commands_list.append("`/adminsettwitch` - Set a player's Twitch")
            commands_list.append("`/removetwitch` - Remove a player's Twitch")
            commands_list.append("`/unlinkalias` - Remove a player's alias")
            commands_list.append("`/linkmac` - Link MAC address to player")
            commands_list.append("`/unlinkmac` - Unlink MAC address")
            commands_list.append("`/checkmac` - Check MAC address links")
            commands_list.append("")

            commands_list.append("**⚙️ STAFF - CONFIG** `[STAFF]`")
            commands_list.append("`/bannedroles` - Manage banned roles")
            commands_list.append("`/requiredroles` - Manage required roles")
            commands_list.append("`/hideplayernames` - Hide names in queue")
            commands_list.append("`/showplayernames` - Show names in queue")
            commands_list.append("`/silentverify` - Refresh ranks silently")
            commands_list.append("")

            commands_list.append("**⚙️ STAFF - TESTING** `[STAFF]`")
            commands_list.append("`/testmatchmaking` - Start a test match")
            commands_list.append("`/testmatchmakingred` - Test as red team")
            commands_list.append("`/testmatchmakingblue` - Test as blue team")

        # Admin-only commands
        if is_admin:
            commands_list.append("")
            commands_list.append("**🔒 ADMIN ONLY** `[ADMIN]`")
            commands_list.append("`/addstaffrole` - Add a staff role")
            commands_list.append("`/removestaffrole` - Remove a staff role")
            commands_list.append("`/liststaffroles` - List staff roles")
            commands_list.append("`/rolerulechange` - Change command permissions")
            commands_list.append("`/listrolerules` - List permission overrides")

        # Create embed
        embed = discord.Embed(
            title="HCR Bot Commands",
            description="\n".join(commands_list),
            color=discord.Color.blue()
        )
        embed.set_footer(text="[STAFF] = Staff only | [ADMIN] = Admin only")

        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @bot.tree.command(name='hideplayernames', description='[STAFF] Hide player names in queue (show as "Matched Player")')
    @has_staff_role()
    @app_commands.describe(playlist="Which playlist to hide names in (default: MLG 4v4)")
    @app_commands.choices(playlist=[
        app_commands.Choice(name="MLG 4v4", value="mlg_4v4"),
        app_commands.Choice(name="Team Hardcore", value="team_hardcore"),
        app_commands.Choice(name="Double Team", value="double_team"),
        app_commands.Choice(name="Head to Head", value="head_to_head"),
    ])
    async def hide_player_names(interaction: discord.Interaction, playlist: str = "mlg_4v4"):
        """Hide player names in the queue list"""
        from searchmatchmaking import queue_state, update_queue_embed

        if playlist == "mlg_4v4":
            queue_state.hide_player_names = True
            if queue_state.queue_channel:
                await update_queue_embed(queue_state.queue_channel)
            await interaction.response.send_message("✅ MLG 4v4: Player names are now hidden.", ephemeral=True)
        else:
            try:
                import playlists
                playlists.set_playlist_hidden(playlist, True)
                ps = playlists.get_playlist_state(playlist)
                if ps.queue_channel:
                    await playlists.update_playlist_embed(ps.queue_channel, ps)
                await interaction.response.send_message(f"✅ {ps.name}: Player names are now hidden.", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    @bot.tree.command(name='showplayernames', description='[STAFF] Show real player names in queue')
    @has_staff_role()
    @app_commands.describe(playlist="Which playlist to show names in (default: MLG 4v4)")
    @app_commands.choices(playlist=[
        app_commands.Choice(name="MLG 4v4", value="mlg_4v4"),
        app_commands.Choice(name="Team Hardcore", value="team_hardcore"),
        app_commands.Choice(name="Double Team", value="double_team"),
        app_commands.Choice(name="Head to Head", value="head_to_head"),
    ])
    async def show_player_names(interaction: discord.Interaction, playlist: str = "mlg_4v4"):
        """Show real player names in the queue list"""
        from searchmatchmaking import queue_state, update_queue_embed

        if playlist == "mlg_4v4":
            queue_state.hide_player_names = False
            if queue_state.queue_channel:
                await update_queue_embed(queue_state.queue_channel)
            await interaction.response.send_message("✅ MLG 4v4: Player names are now visible.", ephemeral=True)
        else:
            try:
                import playlists
                playlists.set_playlist_hidden(playlist, False)
                ps = playlists.get_playlist_state(playlist)
                if ps.queue_channel:
                    await playlists.update_playlist_embed(ps.queue_channel, ps)
                await interaction.response.send_message(f"✅ {ps.name}: Player names are now visible.", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)
    
    @bot.tree.command(name='guest', description='[STAFF] Add a guest player attached to a host (MMR = half of host)')
    @app_commands.describe(
        host="The player this guest is attached to (will always be on same team)"
    )
    @has_staff_role()
    async def add_guest(
        interaction: discord.Interaction,
        host: discord.Member
    ):
        """Add a guest player to the queue attached to a host - guest MMR is half of host's MMR"""
        from searchmatchmaking import queue_state, update_queue_embed, log_action, MAX_QUEUE_SIZE
        from pregame import get_player_mmr
        
        # Check if host is in queue
        if host.id not in queue_state.queue:
            await interaction.response.send_message(
                f"❌ {host.display_name} is not in the queue! They must join first.", 
                ephemeral=True
            )
            return
        
        # Check if host already has a guest
        for guest_id, guest_info in queue_state.guests.items():
            if guest_info["host_id"] == host.id and guest_id in queue_state.queue:
                await interaction.response.send_message(
                    f"❌ {host.display_name} already has a guest in the queue!", 
                    ephemeral=True
                )
                return
        
        # Check if queue is full
        if len(queue_state.queue) >= MAX_QUEUE_SIZE:
            await interaction.response.send_message("❌ Queue is already full!", ephemeral=True)
            return
        
        # Get host's MMR and calculate guest MMR as HALF
        host_mmr = await get_player_mmr(host.id)
        guest_mmr = host_mmr // 2
        
        # Generate guest ID and name (always "Host's Guest")
        guest_id = queue_state.guest_counter
        queue_state.guest_counter += 1
        display_name = f"{host.display_name}'s Guest"
        
        # Add guest to tracking
        queue_state.guests[guest_id] = {
            "host_id": host.id,
            "mmr": guest_mmr,
            "name": display_name
        }
        
        # Add guest to queue
        queue_state.queue.append(guest_id)
        queue_state.queue_join_times[guest_id] = datetime.now()
        
        # Update embed
        if queue_state.queue_channel:
            await update_queue_embed(queue_state.queue_channel)
        
        log_action(f"Guest added: {display_name} (MMR: {guest_mmr}, half of {host.display_name}'s {host_mmr})")
        
        await interaction.response.send_message(
            f"✅ Added **{display_name}** to queue\n"
            f"**MMR:** {guest_mmr} (half of {host.display_name}'s {host_mmr})\n"
            f"They will always be on the same team as {host.mention}",
            ephemeral=True
        )
    
    @bot.tree.command(name='removeguest', description='[STAFF] Remove a guest from the queue')
    @app_commands.describe(host="The host whose guest should be removed")
    @has_staff_role()
    async def remove_guest(interaction: discord.Interaction, host: discord.Member):
        """Remove a guest from the queue"""
        from searchmatchmaking import queue_state, update_queue_embed, log_action
        
        # Find guest attached to this host
        guest_to_remove = None
        for guest_id, guest_info in queue_state.guests.items():
            if guest_info["host_id"] == host.id and guest_id in queue_state.queue:
                guest_to_remove = guest_id
                break
        
        if not guest_to_remove:
            await interaction.response.send_message(
                f"❌ {host.display_name} doesn't have a guest in the queue!", 
                ephemeral=True
            )
            return
        
        guest_name = queue_state.guests[guest_to_remove]["name"]
        
        # Remove from queue
        queue_state.queue.remove(guest_to_remove)
        if guest_to_remove in queue_state.queue_join_times:
            del queue_state.queue_join_times[guest_to_remove]
        del queue_state.guests[guest_to_remove]
        
        # Update embed
        if queue_state.queue_channel:
            await update_queue_embed(queue_state.queue_channel)
        
        log_action(f"Guest removed: {guest_name}")
        
        await interaction.response.send_message(f"✅ Removed **{guest_name}** from queue", ephemeral=True)
    
    @bot.tree.command(name='linkmac', description='[STAFF] Link a player to their MAC address for stat tracking')
    @app_commands.describe(
        player="The player to link",
        mac_address="The MAC address (copy/paste from game)"
    )
    @has_staff_role()
    async def link_mac(interaction: discord.Interaction, player: discord.Member, mac_address: str):
        """Link a player's Discord ID to their MAC address"""
        from searchmatchmaking import log_action
        import twitch

        # Clean up MAC address - remove extra spaces, normalize format
        mac_address = mac_address.strip().upper()

        # Basic validation - MAC should have colons or dashes
        # Accept various formats: AA:BB:CC:DD:EE:FF or AA-BB-CC-DD-EE-FF or AABBCCDDEEFF
        clean_mac = mac_address.replace("-", ":").replace(" ", "")

        # If no colons, try to format it
        if ":" not in clean_mac and len(clean_mac) == 12:
            clean_mac = ":".join(clean_mac[i:i+2] for i in range(0, 12, 2))

        # Load players.json using centralized cache
        players = twitch.load_players()
        
        user_id = str(player.id)
        
        # Initialize player entry if doesn't exist
        if user_id not in players:
            players[user_id] = {}
        
        # Check if this MAC is already linked to someone else
        for other_id, other_data in players.items():
            if other_id != user_id:
                other_macs = other_data.get("mac_addresses", [])
                if clean_mac in other_macs:
                    other_member = interaction.guild.get_member(int(other_id))
                    other_name = other_member.display_name if other_member else f"User {other_id}"
                    await interaction.response.send_message(
                        f"⚠️ This MAC address is already linked to **{other_name}**!\n"
                        f"Use `/unlinkmac` on them first if you want to reassign it.",
                        ephemeral=True
                    )
                    return
        
        # Initialize mac_addresses list if doesn't exist
        if "mac_addresses" not in players[user_id]:
            players[user_id]["mac_addresses"] = []
        
        # Check if already linked to this player
        if clean_mac in players[user_id]["mac_addresses"]:
            await interaction.response.send_message(
                f"ℹ️ MAC address `{clean_mac}` is already linked to **{player.display_name}**",
                ephemeral=True
            )
            return
        
        # Add the MAC address
        players[user_id]["mac_addresses"].append(clean_mac)

        # Save Discord nickname for website display
        if player.display_name:
            players[user_id]["display_name"] = player.display_name

        # Also save discord username
        players[user_id]["discord_name"] = player.name

        # Save players.json using centralized cache (also syncs to GitHub)
        twitch.save_players(players)

        mac_count = len(players[user_id]["mac_addresses"])
        log_action(f"MAC linked by {interaction.user.name}: {player.display_name} (ID: {user_id}) -> {clean_mac}")

        await interaction.response.send_message(
            f"✅ Linked MAC address to **{player.display_name}**\n"
            f"**Discord ID:** `{user_id}`\n"
            f"**MAC:** `{clean_mac}`\n"
            f"**Total MACs linked:** {mac_count}",
            ephemeral=True
        )
    
    @bot.tree.command(name='unlinkmac', description='[STAFF] Remove a MAC address from a player')
    @app_commands.describe(
        player="The player to unlink from",
        mac_address="The MAC address to remove (or 'all' to remove all)"
    )
    @has_staff_role()
    async def unlink_mac(interaction: discord.Interaction, player: discord.Member, mac_address: str):
        """Remove a MAC address from a player"""
        from searchmatchmaking import log_action
        import twitch

        # Load players.json using centralized cache
        players = twitch.load_players()
        
        user_id = str(player.id)
        
        if user_id not in players or "mac_addresses" not in players[user_id]:
            await interaction.response.send_message(
                f"❌ **{player.display_name}** has no MAC addresses linked!",
                ephemeral=True
            )
            return
        
        if not players[user_id]["mac_addresses"]:
            await interaction.response.send_message(
                f"❌ **{player.display_name}** has no MAC addresses linked!",
                ephemeral=True
            )
            return
        
        # Handle "all" to remove all MACs
        if mac_address.lower() == "all":
            count = len(players[user_id]["mac_addresses"])
            players[user_id]["mac_addresses"] = []

            # Save using centralized cache (also syncs to GitHub)
            twitch.save_players(players)

            log_action(f"All MACs unlinked from {player.display_name} ({count} removed)")
            
            await interaction.response.send_message(
                f"✅ Removed all **{count}** MAC addresses from **{player.display_name}**",
                ephemeral=True
            )
            return
        
        # Clean up MAC address
        clean_mac = mac_address.strip().upper().replace("-", ":").replace(" ", "")
        if ":" not in clean_mac and len(clean_mac) == 12:
            clean_mac = ":".join(clean_mac[i:i+2] for i in range(0, 12, 2))
        
        if clean_mac not in players[user_id]["mac_addresses"]:
            await interaction.response.send_message(
                f"❌ MAC address `{clean_mac}` is not linked to **{player.display_name}**!",
                ephemeral=True
            )
            return
        
        players[user_id]["mac_addresses"].remove(clean_mac)

        # Save using centralized cache (also syncs to GitHub)
        twitch.save_players(players)

        remaining = len(players[user_id]["mac_addresses"])
        log_action(f"MAC unlinked from {player.display_name}: {clean_mac}")
        
        await interaction.response.send_message(
            f"✅ Removed MAC `{clean_mac}` from **{player.display_name}**\n"
            f"**Remaining MACs:** {remaining}",
            ephemeral=True
        )
    
    @bot.tree.command(name='checkmac', description='[STAFF] Check MAC addresses linked to a player')
    @app_commands.describe(player="The player to check")
    @has_staff_role()
    async def check_mac(interaction: discord.Interaction, player: discord.Member):
        """Check what MAC addresses are linked to a player"""
        import twitch

        # Load players.json using centralized cache
        players = twitch.load_players()
        
        user_id = str(player.id)
        
        if user_id not in players or "mac_addresses" not in players[user_id]:
            await interaction.response.send_message(
                f"ℹ️ **{player.display_name}** has no MAC addresses linked.",
                ephemeral=True
            )
            return
        
        macs = players[user_id]["mac_addresses"]
        
        if not macs:
            await interaction.response.send_message(
                f"ℹ️ **{player.display_name}** has no MAC addresses linked.",
                ephemeral=True
            )
            return
        
        mac_list = "\n".join([f"• `{mac}`" for mac in macs])
        
        await interaction.response.send_message(
            f"**{player.display_name}**'s MAC Addresses ({len(macs)}):\n{mac_list}",
            ephemeral=True
        )
    
    @bot.tree.command(name='resetmatchmaking', description='[STAFF] Reset and empty the matchmaking queue')
    @has_staff_role()
    async def reset_matchmaking(interaction: discord.Interaction):
        """Reset the matchmaking queue completely"""
        from searchmatchmaking import queue_state, update_queue_embed, log_action
        
        old_count = len(queue_state.queue)
        
        # Clear queue
        queue_state.queue.clear()
        queue_state.queue_join_times.clear()
        queue_state.guests.clear()
        queue_state.recent_action = None
        
        # Update embed
        if queue_state.queue_channel:
            await update_queue_embed(queue_state.queue_channel)
        
        log_action(f"Queue reset by {interaction.user.display_name} - {old_count} players removed")
        
        await interaction.response.send_message(
            f"✅ Matchmaking queue has been reset! ({old_count} players removed)",
            ephemeral=True
        )
    
    @bot.tree.command(name='pause', description='[STAFF] Pause a matchmaking queue - prevents new players from joining')
    @has_staff_role()
    @app_commands.describe(playlist="Which playlist to pause (default: all)")
    @app_commands.choices(playlist=[
        app_commands.Choice(name="All Playlists", value="all"),
        app_commands.Choice(name="MLG 4v4", value="mlg_4v4"),
        app_commands.Choice(name="Team Hardcore", value="team_hardcore"),
        app_commands.Choice(name="Double Team", value="double_team"),
        app_commands.Choice(name="Head to Head", value="head_to_head"),
    ])
    async def pause_matchmaking(interaction: discord.Interaction, playlist: str = "all"):
        """Pause matchmaking queue(s)"""
        from searchmatchmaking import queue_state, log_action

        paused_list = []

        if playlist == "all" or playlist == "mlg_4v4":
            if not queue_state.paused:
                queue_state.paused = True
                paused_list.append("MLG 4v4")

        # Pause other playlists
        try:
            import playlists
            if playlist == "all":
                for ptype in [playlists.PlaylistType.TEAM_HARDCORE, playlists.PlaylistType.DOUBLE_TEAM, playlists.PlaylistType.HEAD_TO_HEAD]:
                    ps = playlists.get_playlist_state(ptype)
                    if not ps.paused:
                        ps.paused = True
                        paused_list.append(ps.name)
                        if ps.queue_channel:
                            await playlists.update_playlist_embed(ps.queue_channel, ps)
            elif playlist in [playlists.PlaylistType.TEAM_HARDCORE, playlists.PlaylistType.DOUBLE_TEAM, playlists.PlaylistType.HEAD_TO_HEAD]:
                ps = playlists.get_playlist_state(playlist)
                if not ps.paused:
                    ps.paused = True
                    paused_list.append(ps.name)
                    if ps.queue_channel:
                        await playlists.update_playlist_embed(ps.queue_channel, ps)
        except Exception as e:
            log_action(f"Error pausing playlists: {e}")

        if paused_list:
            log_action(f"Paused by {interaction.user.display_name}: {', '.join(paused_list)}")
            await interaction.response.send_message(
                f"⏸️ **PAUSED:** {', '.join(paused_list)}\n\nUse `/unpause` to resume.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message("⏸️ Selected queue(s) already paused!", ephemeral=True)

    @bot.tree.command(name='unpause', description='[STAFF] Unpause a matchmaking queue - allows players to join again')
    @has_staff_role()
    @app_commands.describe(playlist="Which playlist to unpause (default: all)")
    @app_commands.choices(playlist=[
        app_commands.Choice(name="All Playlists", value="all"),
        app_commands.Choice(name="MLG 4v4", value="mlg_4v4"),
        app_commands.Choice(name="Team Hardcore", value="team_hardcore"),
        app_commands.Choice(name="Double Team", value="double_team"),
        app_commands.Choice(name="Head to Head", value="head_to_head"),
    ])
    async def unpause_matchmaking(interaction: discord.Interaction, playlist: str = "all"):
        """Unpause matchmaking queue(s)"""
        from searchmatchmaking import queue_state, log_action

        unpaused_list = []

        if playlist == "all" or playlist == "mlg_4v4":
            if queue_state.paused:
                queue_state.paused = False
                unpaused_list.append("MLG 4v4")

        # Unpause other playlists
        try:
            import playlists
            if playlist == "all":
                for ptype in [playlists.PlaylistType.TEAM_HARDCORE, playlists.PlaylistType.DOUBLE_TEAM, playlists.PlaylistType.HEAD_TO_HEAD]:
                    ps = playlists.get_playlist_state(ptype)
                    if ps.paused:
                        ps.paused = False
                        unpaused_list.append(ps.name)
                        if ps.queue_channel:
                            await playlists.update_playlist_embed(ps.queue_channel, ps)
            elif playlist in [playlists.PlaylistType.TEAM_HARDCORE, playlists.PlaylistType.DOUBLE_TEAM, playlists.PlaylistType.HEAD_TO_HEAD]:
                ps = playlists.get_playlist_state(playlist)
                if ps.paused:
                    ps.paused = False
                    unpaused_list.append(ps.name)
                    if ps.queue_channel:
                        await playlists.update_playlist_embed(ps.queue_channel, ps)
        except Exception as e:
            log_action(f"Error unpausing playlists: {e}")

        if unpaused_list:
            log_action(f"Unpaused by {interaction.user.display_name}: {', '.join(unpaused_list)}")
            await interaction.response.send_message(
                f"▶️ **RESUMED:** {', '.join(unpaused_list)}\n\nPlayers can join again!",
                ephemeral=True
            )
        else:
            await interaction.response.send_message("▶️ Selected queue(s) not paused!", ephemeral=True)

    @bot.tree.command(name='clearqueue', description='[STAFF] Clear a matchmaking queue')
    @has_staff_role()
    @app_commands.describe(playlist="Which playlist queue to clear (default: all)")
    @app_commands.choices(playlist=[
        app_commands.Choice(name="All Playlists", value="all"),
        app_commands.Choice(name="MLG 4v4", value="mlg_4v4"),
        app_commands.Choice(name="Team Hardcore", value="team_hardcore"),
        app_commands.Choice(name="Double Team", value="double_team"),
        app_commands.Choice(name="Head to Head", value="head_to_head"),
    ])
    async def clear_queue(interaction: discord.Interaction, playlist: str = "all"):
        """Clear a matchmaking queue"""
        from searchmatchmaking import queue_state, update_queue_embed, log_action

        cleared_info = []

        if playlist == "all" or playlist == "mlg_4v4":
            count = len(queue_state.queue)
            if count > 0:
                queue_state.queue.clear()
                queue_state.queue_join_times.clear()
                queue_state.guests.clear()
                queue_state.recent_action = None
                cleared_info.append(f"MLG 4v4: {count} players")
                if queue_state.queue_channel:
                    await update_queue_embed(queue_state.queue_channel)

        # Clear other playlists
        try:
            import playlists
            ptypes_to_clear = []
            if playlist == "all":
                ptypes_to_clear = [playlists.PlaylistType.TEAM_HARDCORE, playlists.PlaylistType.DOUBLE_TEAM, playlists.PlaylistType.HEAD_TO_HEAD]
            elif playlist in [playlists.PlaylistType.TEAM_HARDCORE, playlists.PlaylistType.DOUBLE_TEAM, playlists.PlaylistType.HEAD_TO_HEAD]:
                ptypes_to_clear = [playlist]

            for ptype in ptypes_to_clear:
                count = playlists.clear_playlist_queue(ptype)
                if count > 0:
                    ps = playlists.get_playlist_state(ptype)
                    cleared_info.append(f"{ps.name}: {count} players")
                    if ps.queue_channel:
                        await playlists.update_playlist_embed(ps.queue_channel, ps)
        except Exception as e:
            log_action(f"Error clearing playlists: {e}")

        if cleared_info:
            log_action(f"Cleared by {interaction.user.display_name}: {', '.join(cleared_info)}")
            await interaction.response.send_message(
                f"✅ **Cleared:**\n" + "\n".join(f"• {info}" for info in cleared_info),
                ephemeral=True
            )
        else:
            await interaction.response.send_message("❌ No players in the selected queue(s)!", ephemeral=True)

    @bot.tree.command(name='stop', description='[STAFF] Stop a matchmaking queue - pauses and clears all players')
    @has_staff_role()
    @app_commands.describe(playlist="Which playlist to stop (default: all)")
    @app_commands.choices(playlist=[
        app_commands.Choice(name="All Playlists", value="all"),
        app_commands.Choice(name="MLG 4v4", value="mlg_4v4"),
        app_commands.Choice(name="Team Hardcore", value="team_hardcore"),
        app_commands.Choice(name="Double Team", value="double_team"),
        app_commands.Choice(name="Head to Head", value="head_to_head"),
    ])
    async def stop_matchmaking(interaction: discord.Interaction, playlist: str = "all"):
        """Stop matchmaking queue(s) - pauses and clears all players"""
        from searchmatchmaking import queue_state, update_queue_embed, log_action

        stopped_info = []

        if playlist == "all" or playlist == "mlg_4v4":
            count = len(queue_state.queue)
            was_paused = queue_state.paused
            # Pause the queue
            queue_state.paused = True
            # Hide player names
            queue_state.hide_player_names = True
            # Clear players
            if count > 0:
                queue_state.queue.clear()
                queue_state.queue_join_times.clear()
                queue_state.guests.clear()
                queue_state.recent_action = None
            if count > 0 or not was_paused:
                stopped_info.append(f"MLG 4v4: {count} players removed, queue hidden")
            if queue_state.queue_channel:
                await update_queue_embed(queue_state.queue_channel)

        # Stop other playlists
        try:
            import playlists
            ptypes_to_stop = []
            if playlist == "all":
                ptypes_to_stop = [playlists.PlaylistType.TEAM_HARDCORE, playlists.PlaylistType.DOUBLE_TEAM, playlists.PlaylistType.HEAD_TO_HEAD]
            elif playlist == "team_hardcore":
                ptypes_to_stop = [playlists.PlaylistType.TEAM_HARDCORE]
            elif playlist == "double_team":
                ptypes_to_stop = [playlists.PlaylistType.DOUBLE_TEAM]
            elif playlist == "head_to_head":
                ptypes_to_stop = [playlists.PlaylistType.HEAD_TO_HEAD]

            for ptype in ptypes_to_stop:
                ps = playlists.get_playlist_state(ptype)
                was_paused = ps.paused
                count = playlists.clear_playlist_queue(ptype)
                ps.paused = True
                # Hide player names
                playlists.set_playlist_hidden(ptype, True)
                if count > 0 or not was_paused:
                    stopped_info.append(f"{ps.name}: {count} players removed, queue hidden")
                if ps.queue_channel:
                    await playlists.update_playlist_embed(ps.queue_channel, ps)
        except Exception as e:
            log_action(f"Error stopping playlists: {e}")

        if stopped_info:
            log_action(f"Stopped by {interaction.user.display_name}: {', '.join(stopped_info)}")
            await interaction.response.send_message(
                f"🛑 **STOPPED:**\n" + "\n".join(f"• {info}" for info in stopped_info) + "\n\nUse `/unpause` to resume and `/showplayernames` to unhide.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message("🛑 Selected queue(s) already stopped (paused and hidden with no players)!", ephemeral=True)

    @bot.tree.command(name='adminarrange', description='[STAFF] Manually set teams and start a match')
    @app_commands.describe(
        red1="Red Team Player 1",
        red2="Red Team Player 2",
        red3="Red Team Player 3",
        red4="Red Team Player 4",
        blue1="Blue Team Player 1",
        blue2="Blue Team Player 2",
        blue3="Blue Team Player 3",
        blue4="Blue Team Player 4"
    )
    @has_staff_role()
    async def admin_set_teams(
        interaction: discord.Interaction,
        red1: discord.Member,
        red2: discord.Member,
        red3: discord.Member,
        red4: discord.Member,
        blue1: discord.Member,
        blue2: discord.Member,
        blue3: discord.Member,
        blue4: discord.Member
    ):
        """Manually set teams and start a match immediately"""
        from searchmatchmaking import queue_state, log_action, QUEUE_CHANNEL_ID
        from pregame import finalize_teams
        
        # Check for active series
        if queue_state.current_series:
            await interaction.response.send_message("❌ There's already an active match! End it first.", ephemeral=True)
            return
        
        # Build teams
        red_team = [red1.id, red2.id, red3.id, red4.id]
        blue_team = [blue1.id, blue2.id, blue3.id, blue4.id]
        
        # Check for duplicates
        all_players = red_team + blue_team
        if len(all_players) != len(set(all_players)):
            await interaction.response.send_message("❌ Duplicate players detected! Each player can only be on one team.", ephemeral=True)
            return
        
        # Clear the queue since we're manually setting teams
        queue_state.queue.clear()
        queue_state.queue_join_times.clear()
        
        log_action(f"Admin {interaction.user.display_name} manually set teams")
        log_action(f"Red: {[m.display_name for m in [red1, red2, red3, red4]]}")
        log_action(f"Blue: {[m.display_name for m in [blue1, blue2, blue3, blue4]]}")
        
        await interaction.response.send_message(
            f"✅ **Teams Set!**\n\n"
            f"🔴 **Red Team:** {red1.mention}, {red2.mention}, {red3.mention}, {red4.mention}\n"
            f"🔵 **Blue Team:** {blue1.mention}, {blue2.mention}, {blue3.mention}, {blue4.mention}\n\n"
            f"Starting match...",
            ephemeral=True
        )
        
        # Get the queue channel
        channel = interaction.guild.get_channel(QUEUE_CHANNEL_ID)
        if not channel:
            channel = interaction.channel
        
        # Start the match
        await finalize_teams(channel, red_team, blue_team, test_mode=False)
    
    @bot.tree.command(name='adminguestmatch', description='[STAFF] Set teams with guests (use guest:HostName format)')
    @app_commands.describe(
        red1="Red Team Player 1 (or guest:HostName)",
        red2="Red Team Player 2 (or guest:HostName)",
        red3="Red Team Player 3 (or guest:HostName)",
        red4="Red Team Player 4 (or guest:HostName)",
        blue1="Blue Team Player 1 (or guest:HostName)",
        blue2="Blue Team Player 2 (or guest:HostName)",
        blue3="Blue Team Player 3 (or guest:HostName)",
        blue4="Blue Team Player 4 (or guest:HostName)"
    )
    @has_staff_role()
    async def admin_guest_match(
        interaction: discord.Interaction,
        red1: str,
        red2: str,
        red3: str,
        red4: str,
        blue1: str,
        blue2: str,
        blue3: str,
        blue4: str
    ):
        """Set teams with guests - enter Discord username or 'guest:HostName'"""
        from searchmatchmaking import queue_state, log_action, QUEUE_CHANNEL_ID
        from pregame import finalize_teams, get_player_mmr
        
        # Check for active series
        if queue_state.current_series:
            await interaction.response.send_message("❌ There's already an active match! End it first.", ephemeral=True)
            return
        
        async def parse_player(player_str: str, guild: discord.Guild) -> tuple:
            """Parse player string - returns (user_id, display_name) or None if invalid"""
            player_str = player_str.strip()
            
            # Check if it's a guest format: guest:HostName
            if player_str.lower().startswith("guest:"):
                parts = player_str.split(":")
                if len(parts) >= 2:
                    host_name = parts[1]
                    
                    # Find host member
                    host_member = discord.utils.find(
                        lambda m: m.display_name.lower() == host_name.lower() or m.name.lower() == host_name.lower(),
                        guild.members
                    )
                    
                    if not host_member:
                        return None, f"Could not find host '{host_name}'"
                    
                    # Get host's MMR and set guest to HALF
                    host_mmr = await get_player_mmr(host_member.id)
                    guest_mmr = host_mmr // 2
                    
                    # Create guest - always named "Host's Guest"
                    guest_id = queue_state.guest_counter
                    queue_state.guest_counter += 1
                    display_name = f"{host_member.display_name}'s Guest"
                    
                    queue_state.guests[guest_id] = {
                        "host_id": host_member.id,
                        "mmr": guest_mmr,
                        "name": display_name
                    }
                    
                    return guest_id, display_name
                else:
                    return None, "Invalid guest format. Use: guest:HostName"
            
            # Try to find as Discord member
            # Try by mention format
            if player_str.startswith("<@") and player_str.endswith(">"):
                user_id = int(player_str.replace("<@", "").replace(">", "").replace("!", ""))
                member = guild.get_member(user_id)
                if member:
                    return member.id, member.display_name
            
            # Try by name/display name
            member = discord.utils.find(
                lambda m: m.display_name.lower() == player_str.lower() or m.name.lower() == player_str.lower(),
                guild.members
            )
            if member:
                return member.id, member.display_name
            
            # Try by ID
            try:
                user_id = int(player_str)
                member = guild.get_member(user_id)
                if member:
                    return member.id, member.display_name
            except:
                pass
            
            return None, f"Could not find player '{player_str}'"
        
        # Parse all players
        red_team = []
        blue_team = []
        red_names = []
        blue_names = []
        errors = []
        
        for i, p in enumerate([red1, red2, red3, red4], 1):
            user_id, result = await parse_player(p, interaction.guild)
            if user_id is None:
                errors.append(f"Red {i}: {result}")
            else:
                red_team.append(user_id)
                red_names.append(result)
        
        for i, p in enumerate([blue1, blue2, blue3, blue4], 1):
            user_id, result = await parse_player(p, interaction.guild)
            if user_id is None:
                errors.append(f"Blue {i}: {result}")
            else:
                blue_team.append(user_id)
                blue_names.append(result)
        
        if errors:
            await interaction.response.send_message(
                f"❌ **Errors parsing players:**\n" + "\n".join(errors) +
                "\n\n**Format:** Use Discord username OR `guest:HostName:GuestName:MMR`",
                ephemeral=True
            )
            return
        
        # Check for duplicates
        all_players = red_team + blue_team
        if len(all_players) != len(set(all_players)):
            await interaction.response.send_message("❌ Duplicate players detected!", ephemeral=True)
            return
        
        # Clear the queue
        queue_state.queue.clear()
        queue_state.queue_join_times.clear()
        
        log_action(f"Admin {interaction.user.display_name} set guest match")
        log_action(f"Red: {red_names}")
        log_action(f"Blue: {blue_names}")
        
        await interaction.response.send_message(
            f"✅ **Teams Set!**\n\n"
            f"🔴 **Red Team:** {', '.join(red_names)}\n"
            f"🔵 **Blue Team:** {', '.join(blue_names)}\n\n"
            f"Starting match...",
            ephemeral=True
        )
        
        # Get the queue channel
        channel = interaction.guild.get_channel(QUEUE_CHANNEL_ID)
        if not channel:
            channel = interaction.channel
        
        # Start the match
        await finalize_teams(channel, red_team, blue_team, test_mode=False)
    
    # ========== MANUAL MATCH ENTRY ==========
    
    # Store pending manual matches
    pending_manual_matches = {}  # user_id -> match_data
    
    class AddGameModal(discord.ui.Modal, title="Add Game Result"):
        """Modal for adding a game to a manual match"""
        
        def __init__(self, match_data: dict, game_number: int):
            super().__init__()
            self.match_data = match_data
            self.game_number = game_number
        
        winner = discord.ui.TextInput(
            label="Winner (RED or BLUE)",
            placeholder="RED or BLUE",
            max_length=4,
            required=True
        )
        
        map_name = discord.ui.TextInput(
            label="Map",
            placeholder="e.g., Lockout, Midship, Sanctuary",
            max_length=50,
            required=True
        )
        
        gametype = discord.ui.TextInput(
            label="Gametype",
            placeholder="e.g., TS, CTF, Ball, KOTH",
            max_length=50,
            required=True
        )
        
        async def on_submit(self, interaction: discord.Interaction):
            winner_input = self.winner.value.strip().upper()
            
            if winner_input not in ['RED', 'BLUE']:
                await interaction.response.send_message(
                    "❌ Winner must be RED or BLUE!",
                    ephemeral=True
                )
                return
            
            # Add game to match data
            self.match_data["games"].append({
                "winner": winner_input,
                "map": self.map_name.value.strip(),
                "gametype": self.gametype.value.strip()
            })
            
            game_count = len(self.match_data["games"])
            red_wins = sum(1 for g in self.match_data["games"] if g["winner"] == "RED")
            blue_wins = sum(1 for g in self.match_data["games"] if g["winner"] == "BLUE")
            
            # Show current games and prompt for more
            games_summary = ""
            for i, game in enumerate(self.match_data["games"], 1):
                emoji = "🔴" if game["winner"] == "RED" else "🔵"
                games_summary += f"{emoji} Game {i}: {game['winner']} - {game['map']} - {game['gametype']}\n"
            
            await interaction.response.send_message(
                f"✅ **Game {game_count} Added!**\n\n"
                f"**Current Score:** Red {red_wins} - {blue_wins} Blue\n\n"
                f"**Games:**\n{games_summary}\n"
                f"Use the buttons below to add more games or submit the match.",
                view=ManualMatchView(self.match_data, interaction.user.id),
                ephemeral=True
            )
    
    class ManualMatchView(discord.ui.View):
        """View with buttons to add games or submit manual match"""
        
        def __init__(self, match_data: dict, user_id: int):
            super().__init__(timeout=600)  # 10 minute timeout
            self.match_data = match_data
            self.user_id = user_id
        
        @discord.ui.button(label="Add Another Game", style=discord.ButtonStyle.primary)
        async def add_game(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("❌ This isn't your match entry!", ephemeral=True)
                return
            
            game_num = len(self.match_data["games"]) + 1
            await interaction.response.send_modal(AddGameModal(self.match_data, game_num))
        
        @discord.ui.button(label="Submit Match", style=discord.ButtonStyle.success)
        async def submit_match(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("❌ This isn't your match entry!", ephemeral=True)
                return
            
            if not self.match_data["games"]:
                await interaction.response.send_message("❌ You must add at least one game!", ephemeral=True)
                return
            
            await submit_manual_match(interaction, self.match_data)
        
        @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
        async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("❌ This isn't your match entry!", ephemeral=True)
                return
            
            await interaction.response.send_message("❌ Match entry cancelled.", ephemeral=True)
            self.stop()
    
    async def submit_manual_match(interaction: discord.Interaction, match_data: dict):
        """Submit the completed manual match"""
        from searchmatchmaking import log_action
        from ingame import RED_TEAM_EMOJI_ID, BLUE_TEAM_EMOJI_ID
        
        match_number = match_data["match_number"]
        red_team = match_data["red_team"]
        blue_team = match_data["blue_team"]
        games = match_data["games"]
        
        # Calculate winner
        red_wins = sum(1 for g in games if g["winner"] == "RED")
        blue_wins = sum(1 for g in games if g["winner"] == "BLUE")
        
        if red_wins > blue_wins:
            winner = "RED"
            embed_color = discord.Color.red()
        elif blue_wins > red_wins:
            winner = "BLUE"
            embed_color = discord.Color.blue()
        else:
            winner = "TIE"
            embed_color = discord.Color.greyple()
        
        # Create results embed
        if winner == "TIE":
            embed = discord.Embed(
                title=f"Match #{match_number} Results - TIE!",
                color=embed_color
            )
        else:
            embed = discord.Embed(
                title=f"Match #{match_number} Results - {winner} WINS!",
                color=embed_color
            )
        
        # Team mentions
        red_mentions = "\n".join([f"<@{uid}>" for uid in red_team])
        blue_mentions = "\n".join([f"<@{uid}>" for uid in blue_team])
        
        embed.add_field(
            name=f"<:redteam:{RED_TEAM_EMOJI_ID}> Red Team - {red_wins}", 
            value=red_mentions, 
            inline=True
        )
        embed.add_field(
            name=f"<:blueteam:{BLUE_TEAM_EMOJI_ID}> Blue Team - {blue_wins}", 
            value=blue_mentions, 
            inline=True
        )
        
        embed.add_field(name="Final Score", value=f"Red **{red_wins}** - **{blue_wins}** Blue", inline=False)
        
        # Game results with map/gametype
        results_text = ""
        for i, game in enumerate(games, 1):
            if game["winner"] == "RED":
                emoji = f"<:redteam:{RED_TEAM_EMOJI_ID}>"
            else:
                emoji = f"<:blueteam:{BLUE_TEAM_EMOJI_ID}>"
            results_text += f"{emoji} Game {i} Winner - {game['map']} - {game['gametype']}\n"
        
        embed.add_field(name="Game Results", value=results_text, inline=False)
        embed.set_footer(text="Manual Entry")
        
        # Post to queue channel
        queue_channel = interaction.guild.get_channel(QUEUE_CHANNEL_ID)
        if queue_channel:
            await queue_channel.send(embed=embed)
        
        # Record stats for all players
        try:
            import STATSRANKS
            
            # Record match using the manual match function
            await STATSRANKS.record_manual_match(
                red_team, blue_team, games, winner, interaction.guild, match_number
            )
            log_action(f"Manual match #{match_number} stats recorded")
        except Exception as e:
            log_action(f"Failed to record manual match stats: {e}")
            import traceback
            traceback.print_exc()
        
        log_action(f"Manual match #{match_number} submitted by {interaction.user.display_name}")
        log_action(f"Result: {winner} ({red_wins}-{blue_wins})")
        
        await interaction.response.send_message(
            f"✅ **Match #{match_number} submitted!**\n\n"
            f"**Winner:** {winner}\n"
            f"**Score:** Red {red_wins} - {blue_wins} Blue\n"
            f"**Games:** {len(games)}\n\n"
            f"Results posted to {queue_channel.mention if queue_channel else 'queue channel'}",
            ephemeral=True
        )
    
    @bot.tree.command(name='manualmatchentry', description='[STAFF] Manually enter a completed match with results')
    @app_commands.describe(
        match_number="The match number to register",
        red1="Red Team Player 1",
        red2="Red Team Player 2", 
        red3="Red Team Player 3",
        red4="Red Team Player 4",
        blue1="Blue Team Player 1",
        blue2="Blue Team Player 2",
        blue3="Blue Team Player 3",
        blue4="Blue Team Player 4"
    )
    @has_staff_role()
    async def manual_match_entry(
        interaction: discord.Interaction,
        match_number: int,
        red1: discord.Member,
        red2: discord.Member,
        red3: discord.Member,
        red4: discord.Member,
        blue1: discord.Member,
        blue2: discord.Member,
        blue3: discord.Member,
        blue4: discord.Member
    ):
        """Manually enter a completed match - opens a form to add games"""
        from searchmatchmaking import log_action
        
        # Validate match number
        if match_number < 1:
            await interaction.response.send_message("❌ Match number must be 1 or higher!", ephemeral=True)
            return
        
        # Check for duplicate players
        all_players = [red1, red2, red3, red4, blue1, blue2, blue3, blue4]
        player_ids = [p.id for p in all_players]
        
        if len(player_ids) != len(set(player_ids)):
            await interaction.response.send_message("❌ Duplicate players detected!", ephemeral=True)
            return
        
        red_team = [red1.id, red2.id, red3.id, red4.id]
        blue_team = [blue1.id, blue2.id, blue3.id, blue4.id]
        
        # Create match data structure
        match_data = {
            "match_number": match_number,
            "red_team": red_team,
            "blue_team": blue_team,
            "games": []
        }
        
        red_names = [p.display_name for p in [red1, red2, red3, red4]]
        blue_names = [p.display_name for p in [blue1, blue2, blue3, blue4]]
        
        log_action(f"Manual match entry started: Match #{match_number} by {interaction.user.display_name}")
        
        # Send initial message with Add Game button
        await interaction.response.send_message(
            f"📝 **Manual Match Entry - Match #{match_number}**\n\n"
            f"🔴 **Red Team:** {', '.join(red_names)}\n"
            f"🔵 **Blue Team:** {', '.join(blue_names)}\n\n"
            f"Click **Add Game** to enter each game's result.\n"
            f"When done, click **Submit Match** to post the results.",
            view=ManualMatchView(match_data, interaction.user.id),
            ephemeral=True
        )

    @bot.tree.command(name='version', description='Show bot and module version numbers')
    async def show_version(interaction: discord.Interaction):
        """Show all bot and module versions"""
        await interaction.response.defer(ephemeral=True)

        try:
            import HCRBot
            bot_version = getattr(HCRBot, 'BOT_VERSION', 'unknown')
            build_date = getattr(HCRBot, 'BOT_BUILD_DATE', 'unknown')
        except:
            bot_version = 'unknown'
            build_date = 'unknown'

        # Collect module versions
        modules = [
            ('commands', 'commands.py'),
            ('searchmatchmaking', 'searchmatchmaking.py'),
            ('pregame', 'pregame.py'),
            ('ingame', 'ingame.py'),
            ('postgame', 'postgame.py'),
            ('STATSRANKS', 'STATSRANKS.py'),
            ('twitch', 'twitch.py'),
            ('state_manager', 'state_manager.py'),
            ('playlists', 'playlists.py'),
            ('stats_parser', 'stats_parser.py'),
            ('github_webhook', 'github_webhook.py'),
        ]

        version_lines = []
        for mod_name, display_name in modules:
            try:
                mod = __import__(mod_name)
                version = getattr(mod, 'MODULE_VERSION', 'n/a')
                version_lines.append(f"`{display_name:22}` v{version}")
            except Exception as e:
                version_lines.append(f"`{display_name:22}` (error: {e})")

        embed = discord.Embed(
            title="🤖 Bot Version Info",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="HCR Bot",
            value=f"**Version:** {bot_version}\n**Build Date:** {build_date}",
            inline=False
        )
        embed.add_field(
            name="Module Versions",
            value="\n".join(version_lines),
            inline=False
        )

        await interaction.followup.send(embed=embed, ephemeral=True)

    @bot.tree.command(name='restart', description='[ADMIN] Restart the bot')
    @has_admin_role()
    async def restart_bot(interaction: discord.Interaction):
        """Restart the bot"""
        import sys
        import urllib.request

        log_action(f"Bot restart initiated by {interaction.user.display_name}")
        await interaction.response.send_message("🔄 Restarting bot...", ephemeral=True)

        # Update bot.py BEFORE restarting to ensure latest backup logic is used
        try:
            github_url = "https://raw.githubusercontent.com/I2aMpAnT/Carnage-Report-Matchmaking-Bot/main/bot.py"
            with urllib.request.urlopen(github_url, timeout=10) as response:
                latest_code = response.read().decode('utf-8')
            with open("bot.py", 'w') as f:
                f.write(latest_code)
            log_action("Updated bot.py from GitHub before restart")
        except Exception as e:
            log_action(f"Failed to update bot.py before restart: {e}")

        # Give time for the message to send
        await asyncio.sleep(1)

        # Exit and let pm2 restart the process
        sys.exit(0)

    @bot.tree.command(name='botlogs', description='[ADMIN] View recent bot logs')
    @has_admin_role()
    @app_commands.describe(
        lines="Number of log lines to show (default: 50, max: 100)"
    )
    async def bot_logs(interaction: discord.Interaction, lines: int = 50):
        """View recent bot logs"""
        import os

        await interaction.response.defer(ephemeral=True)

        # Cap at 100 lines
        lines = min(lines, 100)

        log_file = 'log.txt'
        if not os.path.exists(log_file):
            await interaction.followup.send("❌ No log file found!", ephemeral=True)
            return

        try:
            with open(log_file, 'r') as f:
                all_lines = f.readlines()

            # Get last N lines
            recent_lines = all_lines[-lines:] if len(all_lines) >= lines else all_lines
            log_content = ''.join(recent_lines)

            if not log_content.strip():
                await interaction.followup.send("📋 Log file is empty!", ephemeral=True)
                return

            # Discord message limit is 2000 chars, account for formatting
            if len(log_content) > 1900:
                log_content = log_content[-1900:]
                # Find first newline to start at a complete line
                first_newline = log_content.find('\n')
                if first_newline != -1:
                    log_content = log_content[first_newline + 1:]
                log_content = f"... (truncated)\n{log_content}"

            await interaction.followup.send(
                f"📋 **Last {lines} log entries:**\n```\n{log_content}\n```",
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Error reading logs: {e}", ephemeral=True)

    @bot.tree.command(name='playlistsync', description='[STAFF] Sync game results from website for active matches')
    @has_staff_role()
    @app_commands.describe(
        playlist="Playlist to sync (or 'all' for all playlists)"
    )
    @app_commands.choices(playlist=[
        app_commands.Choice(name="All Playlists", value="all"),
        app_commands.Choice(name="MLG 4v4", value="mlg_4v4"),
        app_commands.Choice(name="Team Hardcore", value="team_hardcore"),
        app_commands.Choice(name="Double Team", value="double_team"),
        app_commands.Choice(name="Head to Head", value="head_to_head"),
    ])
    async def playlist_sync(interaction: discord.Interaction, playlist: str = "all"):
        """Pull game winner data from website for active matches"""
        await interaction.response.defer(ephemeral=True)

        try:
            import playlists
            from playlists import PLAYLIST_HISTORY_FILES, get_playlist_state, show_playlist_match_embed
        except ImportError as e:
            await interaction.followup.send(f"❌ Import error: {e}", ephemeral=True)
            return

        results = []
        playlists_to_sync = PLAYLIST_HISTORY_FILES.keys() if playlist == "all" else [playlist]

        for ptype in playlists_to_sync:
            history_file = PLAYLIST_HISTORY_FILES.get(ptype)
            if not history_file:
                continue

            # Pull from GitHub
            try:
                github_data = await github_webhook.async_pull_file_from_github(history_file)
            except Exception as e:
                results.append(f"❌ {ptype}: Failed to pull from GitHub - {e}")
                continue

            if not github_data:
                results.append(f"⚠️ {ptype}: No data on GitHub")
                continue

            # Get active matches from website data
            website_active = github_data.get("active_matches", [])

            if not website_active:
                results.append(f"✓ {ptype}: No active matches on website")
                continue

            # Get the current match in memory
            ps = get_playlist_state(ptype)
            if not ps.current_match:
                results.append(f"✓ {ptype}: No active match locally")
                continue

            match = ps.current_match

            # Find matching match on website by match_number
            website_match = None
            for wm in website_active:
                if wm.get("match_number") == match.match_number:
                    website_match = wm
                    break

            if not website_match:
                results.append(f"✓ {ptype}: Match #{match.match_number} not found on website")
                continue

            # Sync game results from website
            website_games = website_match.get("games", [])
            games_synced = 0

            if len(website_games) > len(match.games):
                # Website has more game results - sync them
                for i in range(len(match.games), len(website_games)):
                    match.games.append(website_games[i])
                    games_synced += 1

                # Update match embed
                if match.match_message:
                    channel = interaction.guild.get_channel(ps.config["channel_id"])
                    if channel:
                        await show_playlist_match_embed(channel, match)

                # Update the history file
                playlists.update_active_match_in_history(match)

                results.append(f"✅ {ptype}: Synced {games_synced} game result(s) for match #{match.match_number}")
            else:
                results.append(f"✓ {ptype}: Match #{match.match_number} up to date")

        if not results:
            results.append("No playlists to sync")

        await interaction.followup.send(
            f"**Playlist Sync Results:**\n" + "\n".join(results),
            ephemeral=True
        )

        log_action(f"Playlist sync by {interaction.user.display_name}: {playlist}")

    @bot.tree.command(name='botdiag', description='[STAFF] Diagnostic check - verify bot has access to all required files')
    @has_staff_role()
    async def bot_diag(interaction: discord.Interaction):
        """Check if bot has access to all required files and modules"""
        await interaction.response.defer(ephemeral=True)

        import os
        import json

        results = []

        # Required JSON files
        json_files = [
            ("rankstats.json", "Player stats and ranks"),
            ("players.json", "MAC addresses and aliases"),
            ("gamestats.json", "Game statistics"),
            ("matchhistory.json", "MLG 4v4 match history (legacy)"),
            ("MLG4v4.json", "MLG 4v4 match history"),
            ("team_hardcore.json", "Team Hardcore match history"),
            ("double_team.json", "Double Team match history"),
            ("head_to_head.json", "Head to Head match history"),
            ("xp_config.json", "XP configuration"),
            ("playlists.json", "Playlist configuration"),
            ("queue_config.json", "Queue configuration"),
        ]

        results.append("**📁 File Access:**")
        for filename, description in json_files:
            if os.path.exists(filename):
                try:
                    with open(filename, 'r') as f:
                        data = json.load(f)
                    count = len(data) if isinstance(data, (dict, list)) else "N/A"
                    results.append(f"✅ `{filename}` - {count} entries")
                except json.JSONDecodeError as e:
                    results.append(f"⚠️ `{filename}` - Invalid JSON: {e}")
                except Exception as e:
                    results.append(f"❌ `{filename}` - Read error: {e}")
            else:
                results.append(f"❌ `{filename}` - Not found")

        # Check modules
        results.append("\n**📦 Modules:**")
        modules_to_check = [
            "twitch",
            "github_webhook",
            "STATSRANKS",
            "playlists",
            "searchmatchmaking",
            "pregame",
            "ingame",
            "postgame",
        ]

        for module in modules_to_check:
            try:
                mod = __import__(module)
                version = getattr(mod, 'MODULE_VERSION', 'N/A')
                results.append(f"✅ `{module}` v{version}")
            except ImportError as e:
                results.append(f"❌ `{module}` - Import failed: {e}")
            except Exception as e:
                results.append(f"⚠️ `{module}` - Error: {e}")

        # Check twitch cache
        results.append("\n**🔧 Cache Status:**")
        try:
            import twitch
            cache = twitch._PLAYERS_CACHE
            if cache is not None:
                results.append(f"✅ Players cache: {len(cache)} players loaded")
            else:
                results.append(f"⚠️ Players cache: Not loaded yet")
        except Exception as e:
            results.append(f"❌ Players cache: Error - {e}")

        # Check GitHub connectivity
        results.append("\n**🌐 GitHub:**")
        try:
            import github_webhook
            test_data = github_webhook.pull_rankstats_from_github()
            if test_data:
                results.append(f"✅ GitHub pull: {len(test_data)} players in rankstats")
            else:
                results.append(f"⚠️ GitHub pull: No data returned")
        except Exception as e:
            results.append(f"❌ GitHub pull: {e}")

        # Check custom emojis
        results.append("\n**😀 Custom Emojis:**")
        if interaction.guild:
            level_emojis = [e for e in interaction.guild.emojis if e.name.startswith("Level")]
            results.append(f"✅ Level emojis found: {len(level_emojis)}")
        else:
            results.append(f"⚠️ Not in a guild context")

        # Working directory
        results.append(f"\n**📂 Working Directory:**\n`{os.getcwd()}`")

        await interaction.followup.send("\n".join(results), ephemeral=True)

    return bot
