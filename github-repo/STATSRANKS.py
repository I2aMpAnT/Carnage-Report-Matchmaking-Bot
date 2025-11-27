"""
STATSRANKS.py - Stats and Ranks Management Module
Handles player statistics, XP-based ranks, and game details tracking

Import this module in bot.py with:
    import STATSRANKS
    await bot.load_extension('STATSRANKS')
"""

MODULE_VERSION = "1.1.0"

import discord
from discord import app_commands
from discord.ext import commands
import json
import os
import asyncio
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import math

# Map and Gametype Configuration
MAP_GAMETYPES = {
    "Midship": ["MLG CTF5", "MLG Team Slayer", "MLG Oddball", "MLG Bomb"],
    "Beaver Creek": ["MLG Team Slayer"],
    "Lockout": ["MLG Team Slayer", "MLG Oddball"],
    "Warlock": ["MLG Team Slayer", "MLG CTF5"],
    "Sanctuary": ["MLG CTF3", "MLG Team Slayer"]
}

ALL_MAPS = list(MAP_GAMETYPES.keys())
ALL_GAMETYPES = ["MLG CTF5", "MLG CTF3", "MLG Team Slayer", "MLG Oddball", "MLG Bomb"]

# Admin roles
ADMIN_ROLES = ["Overlord", "Staff", "Server Support"]

# File paths
GAMESTATS_FILE = "gamestats.json"
RANKSTATS_FILE = "rankstats.json"
XP_CONFIG_FILE = "xp_config.json"

# Rank icon URLs (for DMs)
RANK_ICON_BASE = "https://r2-cdn.insignia.live/h2-rank"

def get_rank_icon_url(level: int) -> str:
    """Get the rank icon URL for a given level"""
    return f"{RANK_ICON_BASE}/{level}.png"

def load_json_file(filepath: str) -> dict:
    """Load JSON file, create if doesn't exist"""
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            return json.load(f)
    return {}

def save_json_file(filepath: str, data: dict, skip_github: bool = False):
    """Save data to JSON file and optionally push to GitHub"""
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)
    
    # Push to GitHub unless skipped
    if not skip_github:
        try:
            import github_webhook
            if filepath == RANKSTATS_FILE:
                github_webhook.update_rankstats_on_github()
            elif filepath == GAMESTATS_FILE:
                github_webhook.update_gamestats_on_github()
            elif filepath == XP_CONFIG_FILE:
                github_webhook.update_xp_config_on_github()
        except Exception as e:
            print(f"GitHub push failed for {filepath}: {e}")

def get_xp_config() -> dict:
    """Get XP reward configuration and rank thresholds"""
    config = load_json_file(XP_CONFIG_FILE)
    if not config:
        # Default XP values and rank thresholds
        config = {
            "game_win": 50,
            "game_loss": 10,
            "rank_thresholds": {
                "1": [0, 88],
                "2": [89, 188],
                "3": [189, 288],
                "4": [289, 388],
                "5": [389, 488],
                "6": [489, 588],
                "7": [589, 688],
                "8": [689, 788],
                "9": [789, 888],
                "10": [889, 988],
                "11": [989, 1088],
                "12": [1089, 1188],
                "13": [1189, 1388],
                "14": [1389, 1588],
                "15": [1589, 1788],
                "16": [1789, 1988],
                "17": [1989, 2238],
                "18": [2239, 2488],
                "19": [2489, 2738],
                "20": [2739, 2988],
                "21": [2989, 3238],
                "22": [3239, 3488],
                "23": [3489, 3738],
                "24": [3739, 3988],
                "25": [3989, 4238],
                "26": [4239, 4488],
                "27": [4489, 4738],
                "28": [4739, 4988],
                "29": [4989, 5238],
                "30": [5239, 5488],
                "31": [5489, 5738],
                "32": [5739, 5988],
                "33": [5989, 6238],
                "34": [6239, 6488],
                "35": [6489, 6738],
                "36": [6739, 6988],
                "37": [6989, 7238],
                "38": [7239, 7488],
                "39": [7489, 7738],
                "40": [7739, 7988],
                "41": [7989, 8238],
                "42": [8239, 8488],
                "43": [8489, 8738],
                "44": [8739, 8988],
                "45": [8989, 9238],
                "46": [9239, 9488],
                "47": [9489, 9738],
                "48": [9739, 9988],
                "49": [9989, 10238],
                "50": [10239, 1000000000]
            }
        }
        save_json_file(XP_CONFIG_FILE, config)
    return config

def get_rank_thresholds() -> dict:
    """Get rank thresholds from config"""
    config = get_xp_config()
    thresholds = config.get("rank_thresholds", {})
    # Convert string keys to integers and lists to tuples
    return {int(k): tuple(v) for k, v in thresholds.items()}

def get_player_stats(user_id: int, skip_github: bool = False) -> dict:
    """Get player stats from rankstats.json"""
    stats = load_json_file(RANKSTATS_FILE)
    user_key = str(user_id)
    
    if user_key not in stats:
        stats[user_key] = {
            "xp": 0,
            "wins": 0,
            "losses": 0,
            "series_wins": 0,
            "series_losses": 0,
            "total_games": 0,
            "total_series": 0,
            "mmr": 1500  # Default MMR
        }
        save_json_file(RANKSTATS_FILE, stats, skip_github=skip_github)
    
    return stats[user_key]

def get_existing_player_stats(user_id: int) -> dict:
    """Get player stats ONLY if they already exist (don't create new entry)"""
    stats = load_json_file(RANKSTATS_FILE)
    user_key = str(user_id)
    
    if user_key in stats:
        return stats[user_key]
    return None

def update_player_stats(user_id: int, stats_update: dict):
    """Update player stats - XP never goes below 0"""
    stats = load_json_file(RANKSTATS_FILE)
    user_key = str(user_id)
    
    if user_key not in stats:
        stats[user_key] = {
            "xp": 0,
            "wins": 0,
            "losses": 0,
            "series_wins": 0,
            "series_losses": 0,
            "total_games": 0,
            "total_series": 0,
            "mmr": 1500
        }
    
    for key, value in stats_update.items():
        if key in stats[user_key]:
            stats[user_key][key] += value
        else:
            stats[user_key][key] = value
    
    # Ensure XP never goes below 0
    stats[user_key]["xp"] = max(0, stats[user_key]["xp"])
    
    save_json_file(RANKSTATS_FILE, stats)

def calculate_rank(xp: int) -> int:
    """Calculate rank level based on XP from config"""
    thresholds = get_rank_thresholds()
    for level in range(50, 0, -1):
        min_xp, max_xp = thresholds[level]
        if xp >= min_xp:
            return level
    return 1

def get_rank_progress(xp: int) -> Tuple[int, int, int]:
    """Get current rank, XP in rank, and XP needed for next rank"""
    rank = calculate_rank(xp)
    if rank == 50:
        return rank, xp, 0  # Max rank
    
    thresholds = get_rank_thresholds()
    current_min, current_max = thresholds[rank]
    next_min, next_max = thresholds[rank + 1]
    
    xp_in_rank = xp - current_min
    xp_for_next = next_min - xp
    
    return rank, xp_in_rank, xp_for_next

# Rank icon URLs (for DMs)
RANK_ICON_BASE = "https://r2-cdn.insignia.live/h2-rank"

def get_rank_icon_url(level: int) -> str:
    """Get the rank icon URL for a given level"""
    return f"{RANK_ICON_BASE}/{level}.png"

def get_rank_role_name(level: int) -> str:
    """Get the role name for a rank level"""
    return f"Level {level}"

async def update_player_rank_role(guild: discord.Guild, user_id: int, new_level: int, send_dm: bool = True):
    """Update player's rank role with DM notification on rank change"""
    member = guild.get_member(user_id)
    if not member:
        return
    
    # Check current level before making changes
    old_level = None
    for i in range(1, 51):
        check_role = discord.utils.get(guild.roles, name=f"Level {i}")
        if check_role and check_role in member.roles:
            old_level = i
            break
    
    # Remove all level roles (1-50)
    roles_to_remove = []
    for role in member.roles:
        if role.name.startswith("Level "):
            roles_to_remove.append(role)
    
    if roles_to_remove:
        await member.remove_roles(*roles_to_remove, reason="Rank update")
    
    # Add new level role
    new_role_name = get_rank_role_name(new_level)
    new_role = discord.utils.get(guild.roles, name=new_role_name)
    
    if new_role:
        await member.add_roles(new_role, reason=f"Reached {new_role_name}")
        
        # DMs DISABLED - uncomment below to re-enable
        # Send DM notification if rank changed and send_dm is enabled
        # if send_dm and old_level is not None and old_level != new_level:
        #     try:
        #         embed = discord.Embed(color=discord.Color.blue())
        #         
        #         # Add header image
        #         embed.set_image(url="https://raw.githubusercontent.com/I2aMpAnT/H2CarnageReport.com/main/MessagefromCarnageReportHEADER.png")
        #         
        #         if new_level > old_level:
        #             # Level up - show new rank icon in description
        #             embed.set_thumbnail(url=get_rank_icon_url(new_level))
        #             embed.description = f"Congratulations, you have ranked up to"
        #             embed.color = discord.Color.green()
        #         elif new_level < old_level:
        #             # Derank - show old and new rank icons
        #             embed.set_thumbnail(url=get_rank_icon_url(new_level))
        #             embed.description = f"Sorry, you have deranked from"
        #             embed.color = discord.Color.red()
        #         
        #         await member.send(embed=embed)
        #         print(f"Sent rank change DM to {member.name}: {old_level} -> {new_level}")
        #     except discord.Forbidden:
        #         print(f"Could not DM {member.name} - DMs disabled")
        #     except Exception as e:
        #         print(f"Error sending DM to {member.name}: {e}")
    else:
        print(f"⚠️ Role '{new_role_name}' not found in guild")

def add_game_stats(match_number: int, game_number: int, map_name: str, gametype: str) -> bool:
    """Add game stats to gamestats.json with timestamp"""
    # Validate map and gametype combination
    if map_name not in MAP_GAMETYPES:
        return False
    
    if gametype not in MAP_GAMETYPES[map_name]:
        return False
    
    # Load existing stats
    stats = load_json_file(GAMESTATS_FILE)
    
    # Create match key
    match_key = f"match_{match_number}"
    if match_key not in stats:
        stats[match_key] = {}
    
    # Add game data with date timestamp
    game_key = f"game_{game_number}"
    stats[match_key][game_key] = {
        "map": map_name,
        "gametype": gametype,
        "timestamp": datetime.now().isoformat(),
        "date": datetime.now().strftime("%Y-%m-%d")  # For rank resets
    }
    
    # Save
    save_json_file(GAMESTATS_FILE, stats)
    return True

def record_match_results(winners: List[int], losers: List[int], is_series_end: bool = False):
    """Record match results for all players with XP (no series bonuses)"""
    from searchmatchmaking import queue_state
    
    xp_config = get_xp_config()
    
    # Update winners (skip guests - they don't track stats)
    for user_id in winners:
        if user_id in queue_state.guests:
            continue  # Skip guests
        update = {
            "wins": 1,
            "total_games": 1,
            "xp": xp_config["game_win"]  # No series bonus
        }
        if is_series_end:
            update["series_wins"] = 1
            update["total_series"] = 1
        update_player_stats(user_id, update)
    
    # Update losers (skip guests - they don't track stats)
    for user_id in losers:
        if user_id in queue_state.guests:
            continue  # Skip guests
        update = {
            "losses": 1,
            "total_games": 1,
            "xp": xp_config["game_loss"]  # No series penalty
        }
        if is_series_end:
            update["series_losses"] = 1
            update["total_series"] = 1
        update_player_stats(user_id, update)

async def record_manual_match(red_team: List[int], blue_team: List[int], games: List[dict], 
                               series_winner: str, guild: discord.Guild, match_number: int = None):
    """Record a manually entered match with full stats tracking
    
    Args:
        red_team: List of red team player IDs
        blue_team: List of blue team player IDs
        games: List of game dicts with 'winner', 'map', 'gametype'
        series_winner: 'RED', 'BLUE', or 'TIE'
        guild: Discord guild for rank updates
        match_number: Optional match number for logging
    """
    xp_config = get_xp_config()
    
    # Count wins for each team
    red_game_wins = sum(1 for g in games if g["winner"] == "RED")
    blue_game_wins = sum(1 for g in games if g["winner"] == "BLUE")
    
    # Determine winners and losers lists
    if series_winner == "RED":
        series_winners = red_team
        series_losers = blue_team
    elif series_winner == "BLUE":
        series_winners = blue_team
        series_losers = red_team
    else:  # TIE
        series_winners = []
        series_losers = []
    
    # Update stats for red team players
    for user_id in red_team:
        update = {
            "wins": red_game_wins,
            "losses": blue_game_wins,
            "total_games": len(games),
            "total_series": 1,
            "xp": (red_game_wins * xp_config["game_win"]) + (blue_game_wins * xp_config["game_loss"])
        }
        
        if series_winner == "RED":
            update["series_wins"] = 1
            update["xp"] += xp_config.get("series_win_bonus", 0)
        elif series_winner == "BLUE":
            update["series_losses"] = 1
        # TIE: no series win/loss recorded
        
        update_player_stats(user_id, update)
    
    # Update stats for blue team players
    for user_id in blue_team:
        update = {
            "wins": blue_game_wins,
            "losses": red_game_wins,
            "total_games": len(games),
            "total_series": 1,
            "xp": (blue_game_wins * xp_config["game_win"]) + (red_game_wins * xp_config["game_loss"])
        }
        
        if series_winner == "BLUE":
            update["series_wins"] = 1
            update["xp"] += xp_config.get("series_win_bonus", 0)
        elif series_winner == "RED":
            update["series_losses"] = 1
        # TIE: no series win/loss recorded
        
        update_player_stats(user_id, update)
    
    # Record game stats (map/gametype tracking)
    for i, game in enumerate(games, 1):
        record_game_stat(game["map"], game["gametype"], game["winner"])
    
    # Refresh ranks for all players
    all_players = red_team + blue_team
    await refresh_all_ranks(guild, all_players, send_dm=True)
    
    match_label = f"#{match_number}" if match_number else ""
    print(f"✅ Manual match {match_label} recorded: {series_winner} wins ({red_game_wins}-{blue_game_wins})")

async def refresh_all_ranks(guild: discord.Guild, player_ids: List[int], send_dm: bool = True):
    """Refresh rank roles for all players in a match"""
    from searchmatchmaking import queue_state
    
    for user_id in player_ids:
        if user_id in queue_state.guests:
            continue  # Skip guests
        player_stats = get_player_stats(user_id)
        new_level = calculate_rank(player_stats["xp"])
        await update_player_rank_role(guild, user_id, new_level, send_dm=send_dm)

def get_all_players_sorted(sort_by: str = "rank") -> List[Tuple[str, dict]]:
    """Get all players sorted by specified criteria"""
    stats = load_json_file(RANKSTATS_FILE)
    
    players = []
    for user_id, player_stats in stats.items():
        player_stats["rank"] = calculate_rank(player_stats["xp"])
        players.append((user_id, player_stats))
    
    # Sort based on criteria
    if sort_by == "rank":
        players.sort(key=lambda x: (x[1]["rank"], x[1]["xp"]), reverse=True)
    elif sort_by == "wins":
        players.sort(key=lambda x: x[1]["wins"], reverse=True)
    elif sort_by == "series_wins":
        players.sort(key=lambda x: x[1]["series_wins"], reverse=True)
    elif sort_by == "mmr":
        players.sort(key=lambda x: x[1].get("mmr", 1500), reverse=True)
    
    return players

class StatsCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    def has_admin_role():
        """Check if user has admin role"""
        async def predicate(interaction: discord.Interaction):
            user_roles = [role.name for role in interaction.user.roles]
            if any(role in ADMIN_ROLES for role in user_roles):
                return True
            await interaction.response.send_message("❌ You need Overlord, Staff, or Server Support role!", ephemeral=True)
            return False
        return app_commands.check(predicate)
    
    @app_commands.command(name="addgamestats", description="[ADMIN] Add game statistics")
    @has_admin_role()
    @app_commands.describe(
        match_number="Match number",
        game_number="Game number within the match",
        map_name="Map that was played",
        gametype="Gametype that was played"
    )
    @app_commands.choices(
        map_name=[
            app_commands.Choice(name="Midship", value="Midship"),
            app_commands.Choice(name="Beaver Creek", value="Beaver Creek"),
            app_commands.Choice(name="Lockout", value="Lockout"),
            app_commands.Choice(name="Warlock", value="Warlock"),
            app_commands.Choice(name="Sanctuary", value="Sanctuary"),
        ],
        gametype=[
            app_commands.Choice(name="MLG CTF5", value="MLG CTF5"),
            app_commands.Choice(name="MLG CTF3", value="MLG CTF3"),
            app_commands.Choice(name="MLG Team Slayer", value="MLG Team Slayer"),
            app_commands.Choice(name="MLG Oddball", value="MLG Oddball"),
            app_commands.Choice(name="MLG Bomb", value="MLG Bomb"),
        ]
    )
    async def addgamestats(
        self,
        interaction: discord.Interaction,
        match_number: int,
        game_number: int,
        map_name: str,
        gametype: str
    ):
        """Add game statistics"""
        # Validate combination
        if gametype not in MAP_GAMETYPES.get(map_name, []):
            await interaction.response.send_message(
                f"❌ Sorry, **{gametype}** is not played on **{map_name}**\n\n"
                f"Valid gametypes for {map_name}: {', '.join(MAP_GAMETYPES[map_name])}",
                ephemeral=True
            )
            return
        
        # Add to stats
        success = add_game_stats(match_number, game_number, map_name, gametype)
        
        if success:
            await interaction.response.send_message(
                f"✅ Game stats added!\n"
                f"**Match #{match_number}** - Game {game_number}\n"
                f"**Map:** {map_name}\n"
                f"**Gametype:** {gametype}",
                ephemeral=True
            )
            print(f"[STATS] Game stats added: Match {match_number}, Game {game_number}, {map_name}, {gametype}")
        else:
            await interaction.response.send_message(
                "❌ Failed to add game stats!",
                ephemeral=True
            )
    
    @app_commands.command(name="playerstats", description="View player matchmaking statistics")
    @app_commands.describe(user="User to view stats for (optional)")
    async def playerstats(self, interaction: discord.Interaction, user: discord.User = None):
        """Show player stats (NeatQueue style)"""
        target_user = user or interaction.user
        
        # Get stats
        player_stats = get_player_stats(target_user.id)
        
        # Calculate rank and XP progress
        xp = player_stats["xp"]
        rank, xp_in_rank, xp_for_next = get_rank_progress(xp)
        
        # Calculate win rate
        total_games = player_stats["total_games"]
        wins = player_stats["wins"]
        losses = player_stats["losses"]
        win_rate = (wins / total_games * 100) if total_games > 0 else 0
        
        # Get MMR
        mmr = player_stats.get("mmr", 1500)
        
        # Create embed (NeatQueue style)
        embed = discord.Embed(
            title=f"{target_user.name}'s ranked queue Stats",
            color=discord.Color.from_rgb(0, 112, 192)
        )
        
        # Header with player name and MMR
        embed.add_field(
            name="PLAYER",
            value=f"**{target_user.name}**",
            inline=True
        )
        
        embed.add_field(
            name="MMR",
            value=f"**{mmr:.1f}**",
            inline=True
        )
        
        embed.add_field(name="\u200b", value="\u200b", inline=False)  # Spacer
        
        # Rank
        embed.add_field(
            name="RANK",
            value=f"**#{rank}**\nTOP {rank*2}%",
            inline=True
        )
        
        # Win Rate
        embed.add_field(
            name="WINRATE",
            value=f"**{win_rate:.0f}%**\nTOP {100-win_rate:.0f}%",
            inline=True
        )
        
        # Points (XP)
        embed.add_field(
            name="POINTS",
            value=f"**{xp}**\nTOP {rank*2}%",
            inline=True
        )
        
        embed.add_field(name="\u200b", value="\u200b", inline=False)  # Spacer
        
        # Wins
        embed.add_field(
            name="WINS",
            value=f"**{wins}**\nTOP {100-win_rate:.0f}%",
            inline=True
        )
        
        # Losses
        embed.add_field(
            name="LOSSES",
            value=f"**{losses}**\nTOP {win_rate:.0f}%",
            inline=True
        )
        
        # Games
        embed.add_field(
            name="GAMES",
            value=f"**{total_games}**\nBOTTOM {rank}%",
            inline=True
        )
        
        # Progress to next rank
        if rank < 50:
            embed.add_field(
                name="📈 Next Rank",
                value=f"Level {rank+1} in **{xp_for_next} XP**",
                inline=False
            )
        else:
            embed.add_field(
                name="📈 Rank",
                value="🌟 **MAX LEVEL REACHED!** 🌟",
                inline=False
            )
        
        embed.set_thumbnail(url=target_user.display_avatar.url)
        embed.set_footer(text=f"Total Series: {player_stats['total_series']} | Series W/L: {player_stats['series_wins']}/{player_stats['series_losses']}")
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="verifystats", description="Update your rank role based on your current stats")
    async def verifystats(self, interaction: discord.Interaction):
        """Verify and update your own rank"""
        await interaction.response.defer(ephemeral=True)
        
        # Get player stats
        player_stats = get_player_stats(interaction.user.id)
        new_level = calculate_rank(player_stats["xp"])
        
        # Update role
        await update_player_rank_role(interaction.guild, interaction.user.id, new_level, send_dm=True)
        
        await interaction.followup.send(
            f"✅ Your rank has been verified!\n"
            f"**Level {new_level}** ({player_stats['xp']} XP)",
            ephemeral=True
        )
        print(f"[VERIFY] {interaction.user.name} verified rank: Level {new_level}")
    
    @app_commands.command(name="verifystatsall", description="[ADMIN] Refresh all players' rank roles")
    @has_admin_role()
    async def verifystatsall(self, interaction: discord.Interaction):
        """Refresh all ranks (Admin only)"""
        await interaction.response.send_message(
            "🔄 Starting rank refresh for all players... This may take a while.",
            ephemeral=True
        )
        
        guild = interaction.guild
        stats = load_json_file(RANKSTATS_FILE)
        
        updated_count = 0
        error_count = 0
        
        for user_id_str, player_stats in stats.items():
            try:
                user_id = int(user_id_str)
                new_level = calculate_rank(player_stats["xp"])
                
                await update_player_rank_role(guild, user_id, new_level, send_dm=False)
                updated_count += 1
                
                # Small delay to avoid rate limits
                await asyncio.sleep(0.5)
                
            except Exception as e:
                print(f"❌ Error updating user {user_id_str}: {e}")
                error_count += 1
        
        # Summary
        await interaction.followup.send(
            f"✅ Rank refresh complete!\n"
            f"**Updated:** {updated_count}\n"
            f"**Errors:** {error_count}",
            ephemeral=True
        )
        print(f"[VERIFY ALL] Refreshed {updated_count} ranks, {error_count} errors")
    
    @app_commands.command(name="mmr", description="[ADMIN] Set a player's MMR")
    @has_admin_role()
    @app_commands.describe(
        player="Player to set MMR for",
        value="MMR value (e.g., 1500)"
    )
    async def set_mmr(self, interaction: discord.Interaction, player: discord.User, value: int):
        """Set player MMR (Admin only)"""
        # Validate MMR value
        if value < 0 or value > 10000:
            await interaction.response.send_message(
                "❌ MMR must be between 0 and 10000!",
                ephemeral=True
            )
            return
        
        # Get player stats
        stats = load_json_file(RANKSTATS_FILE)
        user_key = str(player.id)
        
        # Initialize if doesn't exist
        if user_key not in stats:
            stats[user_key] = {
                "xp": 0,
                "wins": 0,
                "losses": 0,
                "series_wins": 0,
                "series_losses": 0,
                "total_games": 0,
                "total_series": 0,
                "mmr": value
            }
        else:
            stats[user_key]["mmr"] = value
        
        # Save
        save_json_file(RANKSTATS_FILE, stats)
        
        await interaction.response.send_message(
            f"✅ Set {player.mention}'s MMR to **{value}**",
            ephemeral=True
        )
        print(f"[MMR] {interaction.user.name} set {player.name}'s MMR to {value}")
    
    @app_commands.command(name="leaderboard", description="View the matchmaking leaderboard")
    @app_commands.describe(
        sort_by="How to sort the leaderboard",
        page="Page number to view"
    )
    @app_commands.choices(sort_by=[
        app_commands.Choice(name="Rank (Default)", value="rank"),
        app_commands.Choice(name="Wins/Losses", value="wins"),
        app_commands.Choice(name="Series Wins/Losses", value="series_wins"),
        app_commands.Choice(name="MMR", value="mmr")
    ])
    async def leaderboard(self, interaction: discord.Interaction, sort_by: str = "rank", page: int = 1):
        """Show leaderboard"""
        # Get all players sorted
        players = get_all_players_sorted(sort_by)
        
        if not players:
            await interaction.response.send_message("No players have stats yet!", ephemeral=True)
            return
        
        # Pagination
        per_page = 10
        total_pages = math.ceil(len(players) / per_page)
        page = max(1, min(page, total_pages))
        
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        page_players = players[start_idx:end_idx]
        
        # Create embed
        embed = discord.Embed(
            title="🏆 Halo 2 Matchmaking Leaderboard",
            description=f"Sorted by: **{sort_by.replace('_', ' ').title()}**",
            color=discord.Color.from_rgb(0, 112, 192)
        )
        
        # Add players
        leaderboard_text = ""
        for i, (user_id, stats) in enumerate(page_players, start=start_idx + 1):
            try:
                user = await self.bot.fetch_user(int(user_id))
                name = user.name
            except:
                name = f"User {user_id}"
            
            rank = stats["rank"]
            xp = stats["xp"]
            wins = stats["wins"]
            losses = stats["losses"]
            mmr = stats.get("mmr", 1500)
            win_rate = (wins / stats["total_games"] * 100) if stats["total_games"] > 0 else 0
            
            if sort_by == "rank":
                leaderboard_text += f"`{i}.` **{name}** - Level {rank} ({xp} XP)\n"
            elif sort_by == "wins":
                leaderboard_text += f"`{i}.` **{name}** - {wins}W / {losses}L ({win_rate:.1f}%)\n"
            elif sort_by == "series_wins":
                leaderboard_text += f"`{i}.` **{name}** - {stats['series_wins']}W / {stats['series_losses']}L (Series)\n"
            elif sort_by == "mmr":
                leaderboard_text += f"`{i}.` **{name}** - MMR: {mmr}\n"
        
        embed.description += f"\n\n{leaderboard_text}"
        embed.set_footer(text=f"Page {page}/{total_pages} • {len(players)} total players")
        
        # Add navigation buttons if needed
        if total_pages > 1:
            view = LeaderboardView(sort_by, page, total_pages, self.bot)
            await interaction.response.send_message(embed=embed, view=view)
        else:
            await interaction.response.send_message(embed=embed)

class LeaderboardView(discord.ui.View):
    def __init__(self, sort_by: str, current_page: int, total_pages: int, bot):
        super().__init__(timeout=300)
        self.sort_by = sort_by
        self.current_page = current_page
        self.total_pages = total_pages
        self.bot = bot
        
        # Disable buttons if needed
        if current_page <= 1:
            self.previous_button.disabled = True
        if current_page >= total_pages:
            self.next_button.disabled = True
    
    @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.primary, custom_id="lb_prev")
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        new_page = self.current_page - 1
        await self.update_leaderboard(interaction, new_page)
    
    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.primary, custom_id="lb_next")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        new_page = self.current_page + 1
        await self.update_leaderboard(interaction, new_page)
    
    async def update_leaderboard(self, interaction: discord.Interaction, page: int):
        # Get all players sorted
        players = get_all_players_sorted(self.sort_by)
        
        # Pagination
        per_page = 10
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        page_players = players[start_idx:end_idx]
        
        # Create embed
        embed = discord.Embed(
            title="🏆 Halo 2 Matchmaking Leaderboard",
            description=f"Sorted by: **{self.sort_by.replace('_', ' ').title()}**",
            color=discord.Color.from_rgb(0, 112, 192)
        )
        
        # Add players
        leaderboard_text = ""
        for i, (user_id, stats) in enumerate(page_players, start=start_idx + 1):
            try:
                user = await self.bot.fetch_user(int(user_id))
                name = user.name
            except:
                name = f"User {user_id}"
            
            rank = stats["rank"]
            xp = stats["xp"]
            wins = stats["wins"]
            losses = stats["losses"]
            mmr = stats.get("mmr", 1500)
            win_rate = (wins / stats["total_games"] * 100) if stats["total_games"] > 0 else 0
            
            if self.sort_by == "rank":
                leaderboard_text += f"`{i}.` **{name}** - Level {rank} ({xp} XP)\n"
            elif self.sort_by == "wins":
                leaderboard_text += f"`{i}.` **{name}** - {wins}W / {losses}L ({win_rate:.1f}%)\n"
            elif self.sort_by == "series_wins":
                leaderboard_text += f"`{i}.` **{name}** - {stats['series_wins']}W / {stats['series_losses']}L (Series)\n"
            elif self.sort_by == "mmr":
                leaderboard_text += f"`{i}.` **{name}** - MMR: {mmr}\n"
        
        embed.description += f"\n\n{leaderboard_text}"
        embed.set_footer(text=f"Page {page}/{self.total_pages} • {len(players)} total players")
        
        # Update view
        self.current_page = page
        if page <= 1:
            self.previous_button.disabled = True
        else:
            self.previous_button.disabled = False
        
        if page >= self.total_pages:
            self.next_button.disabled = True
        else:
            self.next_button.disabled = False
        
        await interaction.response.edit_message(embed=embed, view=self)

async def setup(bot):
    """Setup function to add cog to bot"""
    await bot.add_cog(StatsCommands(bot))

# Export functions for use in main bot
__all__ = [
    'record_match_results',
    'refresh_all_ranks',
    'get_player_stats',
    'calculate_rank',
    'setup'
]
