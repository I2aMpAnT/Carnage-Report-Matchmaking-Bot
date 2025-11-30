"""
stats_parser.py - XLSX Stats File Parser
Parses Halo 2 game statistics from XLSX files exported from the game.

Reads files from VPS directories:
- /home/carnagereport/stats/public/  (public games)
- /home/carnagereport/stats/private/ (private/ranked games)

Converts XLSX files to gameshistory.json format for the website.

!! REMEMBER TO UPDATE VERSION NUMBER WHEN MAKING CHANGES !!
"""

MODULE_VERSION = "1.2.0"

import os
import re
import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import pandas as pd

# VPS Stats directories
STATS_DIRS = {
    "public": "/home/carnagereport/stats/public",
    "private": "/home/carnagereport/stats/private"
}

# Output file
GAMES_HISTORY_FILE = "gameshistory.json"

# Timestamp pattern for valid stats files (YYYYMMDD_HHMMSS.xlsx)
TIMESTAMP_PATTERN = re.compile(r'^\d{8}_\d{6}\.xlsx$')


def is_valid_stats_file(filename: str) -> bool:
    """Check if filename matches the timestamp pattern (YYYYMMDD_HHMMSS.xlsx)"""
    return bool(TIMESTAMP_PATTERN.match(filename))


def parse_xlsx_file(filepath: str) -> Optional[Dict]:
    """
    Parse a single XLSX stats file into gameshistory.json format.

    Args:
        filepath: Full path to the XLSX file

    Returns:
        Dict with game data or None if parsing fails
    """
    try:
        xlsx = pd.ExcelFile(filepath)

        # Parse Game Details
        details_df = pd.read_excel(xlsx, sheet_name='Game Details')
        if details_df.empty:
            print(f"⚠️ Empty Game Details in {filepath}")
            return None

        details = {
            "Game Type": str(details_df.iloc[0].get('Game Type', '')),
            "Variant Name": str(details_df.iloc[0].get('Variant Name', '')),
            "Map Name": str(details_df.iloc[0].get('Map Name', '')),
            "Start Time": str(details_df.iloc[0].get('Start Time', '')),
            "End Time": str(details_df.iloc[0].get('End Time', '')),
            "Duration": str(details_df.iloc[0].get('Duration', ''))
        }

        # Parse Post Game Report (player summary)
        players_df = pd.read_excel(xlsx, sheet_name='Post Game Report')
        players = []
        for _, row in players_df.iterrows():
            player = {
                "name": str(row.get('name', '')),
                "team": str(row.get('team', 'none')),
                "score": int(row.get('score', 0)) if pd.notna(row.get('score')) else 0,
                "kills": int(row.get('kills', 0)) if pd.notna(row.get('kills')) else 0,
                "deaths": int(row.get('deaths', 0)) if pd.notna(row.get('deaths')) else 0,
                "assists": int(row.get('assists', 0)) if pd.notna(row.get('assists')) else 0,
                "kda": float(row.get('kda', 0)) if pd.notna(row.get('kda')) else 0,
                "accuracy": int(row.get('accuracy', 0)) if pd.notna(row.get('accuracy')) else 0,
                "suicides": int(row.get('suicides', 0)) if pd.notna(row.get('suicides')) else 0,
                "place": str(row.get('place', ''))
            }
            players.append(player)

        # Parse Game Statistics (detailed stats per player)
        stats_df = pd.read_excel(xlsx, sheet_name='Game Statistics')
        stats = []
        # Columns to skip (non-numeric data)
        skip_columns = {'Player', 'Emblem URL'}
        for _, row in stats_df.iterrows():
            stat = {"Player": str(row.get('Player', ''))}
            # Store emblem URL separately if present
            if 'Emblem URL' in stats_df.columns:
                stat['emblem_url'] = str(row.get('Emblem URL', ''))
            # Add all numeric columns
            for col in stats_df.columns:
                if col not in skip_columns:
                    val = row.get(col, 0)
                    # Only convert numeric values
                    try:
                        stat[col] = int(val) if pd.notna(val) else 0
                    except (ValueError, TypeError):
                        # Skip non-numeric values
                        pass
            stats.append(stat)

        # Merge best_spree and total_time_alive into players
        stats_by_player = {s['Player']: s for s in stats}
        for player in players:
            player_stats = stats_by_player.get(player['name'], {})
            player['best_spree'] = player_stats.get('best_spree', 0)
            player['total_time_alive'] = player_stats.get('total_time_alive', 0)

        # Parse Medal Stats
        medals_df = pd.read_excel(xlsx, sheet_name='Medal Stats')
        medals = []
        for _, row in medals_df.iterrows():
            medal = {"player": str(row.get('player', ''))}
            for col in medals_df.columns:
                if col != 'player':
                    val = row.get(col, 0)
                    medal[col] = int(val) if pd.notna(val) else 0
            medals.append(medal)

        # Parse Weapon Statistics
        weapons_df = pd.read_excel(xlsx, sheet_name='Weapon Statistics')
        weapons = []
        for _, row in weapons_df.iterrows():
            weapon = {"Player": str(row.get('Player', ''))}
            for col in weapons_df.columns:
                if col != 'Player':
                    val = row.get(col, 0)
                    weapon[col] = int(val) if pd.notna(val) else 0
            weapons.append(weapon)

        # Build final game object
        game = {
            "details": details,
            "players": players,
            "stats": stats,
            "medals": medals,
            "weapons": weapons,
            "source_file": os.path.basename(filepath),
            "parsed_at": datetime.now().isoformat()
        }

        return game

    except Exception as e:
        print(f"❌ Error parsing {filepath}: {e}")
        return None


def get_file_timestamp(filename: str) -> Optional[datetime]:
    """Extract datetime from filename (YYYYMMDD_HHMMSS.xlsx)"""
    try:
        # Remove .xlsx extension
        timestamp_str = filename.replace('.xlsx', '')
        return datetime.strptime(timestamp_str, '%Y%m%d_%H%M%S')
    except ValueError:
        return None


def scan_stats_directory(directory: str) -> List[str]:
    """
    Scan a directory for valid stats XLSX files.

    Args:
        directory: Path to scan

    Returns:
        List of valid XLSX file paths, sorted by timestamp (newest first)
    """
    if not os.path.exists(directory):
        print(f"⚠️ Directory does not exist: {directory}")
        return []

    files = []
    for filename in os.listdir(directory):
        if is_valid_stats_file(filename):
            files.append(os.path.join(directory, filename))

    # Sort by timestamp (newest first)
    files.sort(key=lambda f: get_file_timestamp(os.path.basename(f)) or datetime.min, reverse=True)

    return files


def load_existing_games() -> List[Dict]:
    """Load existing games from gameshistory.json"""
    if os.path.exists(GAMES_HISTORY_FILE):
        try:
            with open(GAMES_HISTORY_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ Error loading {GAMES_HISTORY_FILE}: {e}")
    return []


def save_games(games: List[Dict]):
    """Save games to gameshistory.json"""
    with open(GAMES_HISTORY_FILE, 'w') as f:
        json.dump(games, f, indent=2)
    print(f"✅ Saved {len(games)} games to {GAMES_HISTORY_FILE}")


def get_parsed_files(games: List[Dict]) -> set:
    """Get set of already parsed source files"""
    return {g.get('source_file') for g in games if g.get('source_file')}


def parse_all_stats(directories: List[str] = None, force_reparse: bool = False) -> Tuple[int, int]:
    """
    Parse all XLSX stats files from specified directories.

    Args:
        directories: List of directory paths to scan (defaults to STATS_DIRS values)
        force_reparse: If True, reparse all files even if already in history

    Returns:
        Tuple of (new_games_count, total_games_count)
    """
    if directories is None:
        directories = list(STATS_DIRS.values())

    # Load existing games
    existing_games = [] if force_reparse else load_existing_games()
    parsed_files = get_parsed_files(existing_games)

    new_games = []

    for directory in directories:
        print(f"📂 Scanning {directory}...")
        files = scan_stats_directory(directory)
        print(f"   Found {len(files)} valid stats files")

        for filepath in files:
            filename = os.path.basename(filepath)

            # Skip already parsed files
            if filename in parsed_files and not force_reparse:
                continue

            print(f"   📄 Parsing {filename}...")
            game = parse_xlsx_file(filepath)

            if game:
                new_games.append(game)
                print(f"      ✅ Parsed: {game['details']['Map Name']} - {game['details']['Variant Name']}")
            else:
                print(f"      ❌ Failed to parse")

    # Combine and sort all games (newest first by start time)
    all_games = new_games + existing_games

    # Sort by start time (newest first)
    def get_start_time(game):
        try:
            start_str = game.get('details', {}).get('Start Time', '')
            # Try multiple date formats
            for fmt in ['%m/%d/%Y %I:%M %p', '%m/%d/%Y %H:%M', '%Y-%m-%d %H:%M:%S']:
                try:
                    return datetime.strptime(start_str, fmt)
                except ValueError:
                    continue
            return datetime.min
        except:
            return datetime.min

    all_games.sort(key=get_start_time, reverse=True)

    # Save updated games
    save_games(all_games)

    return len(new_games), len(all_games)


def parse_single_file(filepath: str) -> Optional[Dict]:
    """
    Parse a single XLSX file and add it to gameshistory.json.

    Args:
        filepath: Path to the XLSX file

    Returns:
        Parsed game dict or None if failed
    """
    game = parse_xlsx_file(filepath)

    if game:
        existing_games = load_existing_games()

        # Check for duplicates
        filename = os.path.basename(filepath)
        parsed_files = get_parsed_files(existing_games)

        if filename in parsed_files:
            print(f"⚠️ File {filename} already parsed, updating...")
            # Remove old entry
            existing_games = [g for g in existing_games if g.get('source_file') != filename]

        # Add new game at the beginning
        existing_games.insert(0, game)
        save_games(existing_games)

        return game

    return None


def push_gameshistory_to_github() -> bool:
    """Push gameshistory.json to GitHub"""
    try:
        import github_webhook
        # Use the existing push function
        return github_webhook.push_file_to_github(
            GAMES_HISTORY_FILE,
            GAMES_HISTORY_FILE,
            f"Auto-update: {GAMES_HISTORY_FILE} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
    except Exception as e:
        print(f"❌ Failed to push to GitHub: {e}")
        return False


# ============================================
# SERIES MATCHING FUNCTIONS
# ============================================

PENDING_SERIES_FILE = "pending_series.json"


def load_pending_series() -> List[Dict]:
    """Load pending series awaiting stats matching"""
    if os.path.exists(PENDING_SERIES_FILE):
        try:
            with open(PENDING_SERIES_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ Error loading pending series: {e}")
    return []


def save_pending_series(pending: List[Dict]):
    """Save pending series list"""
    with open(PENDING_SERIES_FILE, 'w') as f:
        json.dump(pending, f, indent=2)


def game_time_in_series_window(game_start_time: str, series_start: str, series_end: str) -> bool:
    """Check if a game's start time falls within the series time window"""
    try:
        # Parse series times
        series_start_dt = datetime.fromisoformat(series_start)
        series_end_dt = datetime.fromisoformat(series_end)

        # Try to parse game time (multiple formats)
        game_dt = None
        for fmt in ['%m/%d/%Y %I:%M %p', '%m/%d/%Y %H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S']:
            try:
                game_dt = datetime.strptime(game_start_time, fmt)
                break
            except ValueError:
                continue

        if game_dt is None:
            return False

        # Check if game is within window (with some buffer for lag)
        buffer_minutes = 5  # 5 minute buffer
        from datetime import timedelta
        window_start = series_start_dt - timedelta(minutes=buffer_minutes)
        window_end = series_end_dt + timedelta(minutes=buffer_minutes)

        return window_start <= game_dt <= window_end

    except Exception as e:
        print(f"Error checking game time: {e}")
        return False


def players_match_series(game_players: List[str], series_red: List[int], series_blue: List[int],
                          player_name_cache: Dict[int, str] = None) -> bool:
    """Check if game players match the series teams.
    Uses player names from the game and matches against known gamertags."""
    if player_name_cache is None:
        player_name_cache = {}

    # Normalize game player names
    game_player_names = set(name.lower().strip() for name in game_players if name)

    # Get known gamertags for series players
    all_series_players = series_red + series_blue

    # Try to load gamertag mapping from rankstats.json
    gamertags_file = "rankstats.json"
    if os.path.exists(gamertags_file):
        try:
            with open(gamertags_file, 'r') as f:
                rank_data = json.load(f)

            # Build set of known gamertags for series players
            series_gamertags = set()
            for uid in all_series_players:
                uid_str = str(uid)
                if uid_str in rank_data:
                    player_data = rank_data[uid_str]
                    if 'gamertag' in player_data:
                        series_gamertags.add(player_data['gamertag'].lower().strip())

            # Check for overlap - at least half the players should match
            matches = game_player_names.intersection(series_gamertags)
            threshold = len(all_series_players) // 2
            return len(matches) >= threshold

        except Exception as e:
            print(f"Error loading gamertags: {e}")

    # If no gamertag mapping, we can't match by player names
    return False


def determine_game_winner(game_data: Dict, series_red: List[int], series_blue: List[int]) -> Optional[str]:
    """Determine which team won a game based on player scores/teams"""
    players = game_data.get('players', [])

    if not players:
        return None

    # Group players by team from the game
    red_score = 0
    blue_score = 0

    for player in players:
        team = str(player.get('team', '')).lower()
        score = player.get('score', 0)

        if team == 'red':
            red_score += score
        elif team == 'blue':
            blue_score += score

    # Determine winner based on score
    if red_score > blue_score:
        return 'RED'
    elif blue_score > red_score:
        return 'BLUE'

    return None


def match_games_to_series(games: List[Dict]) -> Dict[str, List[Dict]]:
    """Match parsed games to pending series.

    Returns a dict mapping series_number to list of matched games.
    """
    pending = load_pending_series()
    matches = {}

    for series in pending:
        series_num = series.get('series_number', '')
        series_start = series.get('start_time')
        series_end = series.get('end_time')
        series_red = series.get('red_team', [])
        series_blue = series.get('blue_team', [])

        if not series_start or not series_end:
            continue

        matched_games = []
        for game in games:
            details = game.get('details', {})
            game_start = details.get('Start Time', '')
            game_players = [p.get('name', '') for p in game.get('players', [])]

            # Check time window
            if not game_time_in_series_window(game_start, series_start, series_end):
                continue

            # Check player match
            if not players_match_series(game_players, series_red, series_blue):
                continue

            # Determine winner
            winner = determine_game_winner(game, series_red, series_blue)

            matched_games.append({
                'game': game,
                'winner': winner,
                'map': details.get('Map Name', ''),
                'gametype': details.get('Variant Name', ''),
            })

        if matched_games:
            # Sort by start time
            matched_games.sort(key=lambda g: g['game'].get('details', {}).get('Start Time', ''))
            matches[series_num] = matched_games

    return matches


async def update_series_results(bot, series_data: Dict, matched_games: List[Dict]):
    """Update a series' results embed with matched game data"""
    from ingame import RED_TEAM_EMOJI_ID, BLUE_TEAM_EMOJI_ID

    results_channel_id = series_data.get('results_channel_id')
    results_message_id = series_data.get('results_message_id')

    if not results_channel_id or not results_message_id:
        print(f"⚠️ No results message stored for series {series_data.get('series_number')}")
        return False

    channel = bot.get_channel(results_channel_id)
    if not channel:
        print(f"⚠️ Could not find results channel {results_channel_id}")
        return False

    try:
        message = await channel.fetch_message(results_message_id)
    except Exception as e:
        print(f"⚠️ Could not fetch results message: {e}")
        return False

    # Count wins
    red_wins = sum(1 for g in matched_games if g['winner'] == 'RED')
    blue_wins = sum(1 for g in matched_games if g['winner'] == 'BLUE')

    # Determine winner
    if red_wins > blue_wins:
        winner = 'RED'
        embed_color = discord.Color.red()
    elif blue_wins > red_wins:
        winner = 'BLUE'
        embed_color = discord.Color.blue()
    else:
        winner = 'TIE'
        embed_color = discord.Color.greyple()

    match_number = series_data.get('match_number', '?')

    embed = discord.Embed(
        title=f"Match #{match_number} Results - {winner} WINS!",
        description=f"*Updated from parsed game stats*",
        color=embed_color
    )

    # Add team fields
    red_team = series_data.get('red_team', [])
    blue_team = series_data.get('blue_team', [])

    red_mentions = "\n".join([f"<@{uid}>" for uid in red_team])
    blue_mentions = "\n".join([f"<@{uid}>" for uid in blue_team])

    embed.add_field(
        name=f"<:redteam:{RED_TEAM_EMOJI_ID}> Red Team - {red_wins}",
        value=red_mentions or "Unknown",
        inline=True
    )
    embed.add_field(
        name=f"<:blueteam:{BLUE_TEAM_EMOJI_ID}> Blue Team - {blue_wins}",
        value=blue_mentions or "Unknown",
        inline=True
    )

    embed.add_field(name="Final Score", value=f"Red **{red_wins}** - **{blue_wins}** Blue", inline=False)

    # Game results
    results_text = ""
    for i, game_match in enumerate(matched_games, 1):
        game_winner = game_match['winner']
        map_name = game_match['map']
        gametype = game_match['gametype']

        if game_winner == 'RED':
            emoji = f"<:redteam:{RED_TEAM_EMOJI_ID}>"
        elif game_winner == 'BLUE':
            emoji = f"<:blueteam:{BLUE_TEAM_EMOJI_ID}>"
        else:
            emoji = "❓"

        if map_name and gametype:
            results_text += f"{emoji} Game {i} - {map_name} - {gametype}\n"
        elif map_name:
            results_text += f"{emoji} Game {i} - {map_name}\n"
        else:
            results_text += f"{emoji} Game {i}\n"

    if results_text:
        embed.add_field(name="Game Results", value=results_text.strip(), inline=False)

    embed.set_footer(text=f"Stats parsed at {datetime.now().strftime('%H:%M')}")

    # Update the message
    try:
        await message.edit(embed=embed)
        print(f"✅ Updated results for series {series_data.get('series_number')}")
        return True
    except Exception as e:
        print(f"❌ Failed to update results message: {e}")
        return False


async def process_stats_and_update_results(bot, games: List[Dict] = None):
    """Main function to match parsed games to series and update results.

    Call this after parsing stats to automatically update results embeds.
    """
    if games is None:
        games = load_existing_games()

    if not games:
        print("No parsed games to match")
        return

    matches = match_games_to_series(games)

    if not matches:
        print("No games matched to pending series")
        return

    pending = load_pending_series()
    updated_series = []

    for series in pending:
        series_num = series.get('series_number', '')
        if series_num in matches:
            matched_games = matches[series_num]
            success = await update_series_results(bot, series, matched_games)
            if success:
                updated_series.append(series_num)
                # Update series data with game results for future reference
                series['games'] = [g['winner'] for g in matched_games if g['winner']]
                series['game_stats'] = {
                    str(i): {'map': g['map'], 'gametype': g['gametype']}
                    for i, g in enumerate(matched_games, 1)
                }
                series['stats_matched'] = True

    # Save updated pending series
    save_pending_series(pending)

    # Clean up old/matched series after some time (keep for 24 hours)
    # For now, just mark them as matched

    print(f"✅ Updated results for {len(updated_series)} series")
    return updated_series


async def sync_discord_ranks_for_all_players(bot) -> int:
    """
    Sync Discord rank roles for all players in rankstats.json.
    Called after stats are parsed/populated to ensure Discord roles match current XP.

    Returns:
        Number of players updated
    """
    import STATSRANKS

    # Load all player stats
    stats = STATSRANKS.load_json_file(STATSRANKS.RANKSTATS_FILE)

    if not stats:
        print("No player stats to sync")
        return 0

    # Get the guild from the bot
    guild = None
    for g in bot.guilds:
        # Use the first guild (assuming single-server bot)
        guild = g
        break

    if not guild:
        print("❌ Could not find guild for rank sync")
        return 0

    updated_count = 0

    for user_id_str, player_stats in stats.items():
        try:
            user_id = int(user_id_str)
            member = guild.get_member(user_id)
            if not member:
                continue

            # Get current Discord rank
            current_rank = None
            for role in member.roles:
                if role.name.startswith("Level "):
                    try:
                        current_rank = int(role.name.replace("Level ", ""))
                        break
                    except:
                        pass

            # Ensure playlist_stats exists
            if "playlist_stats" not in player_stats:
                player_stats["playlist_stats"] = STATSRANKS.get_default_playlist_stats()

            # Calculate highest rank across all playlists
            highest = STATSRANKS.calculate_highest_rank(player_stats)
            player_stats["highest_rank"] = highest

            # Only update Discord role if:
            # 1. They don't have a rank yet, OR
            # 2. The calculated rank is HIGHER than current (never downgrade)
            if current_rank is None or highest > current_rank:
                await STATSRANKS.update_player_rank_role(guild, user_id, highest, send_dm=False)
                updated_count += 1

        except Exception as e:
            print(f"⚠️ Error syncing rank for user {user_id_str}: {e}")

    # Save any updates to highest_rank
    STATSRANKS.save_json_file(STATSRANKS.RANKSTATS_FILE, stats, skip_github=True)

    print(f"✅ Synced Discord ranks for {updated_count} players")
    return updated_count


# Discord Bot Integration
import discord
from discord import app_commands
from discord.ext import commands

# Admin roles for permission checks
ADMIN_ROLES = ["Overlord", "Staff", "Server Support"]


class StatsParserCommands(commands.Cog):
    """Discord commands for parsing XLSX stats files"""

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

    @app_commands.command(name="parsestats", description="[ADMIN] Parse XLSX stats files from VPS")
    @has_admin_role()
    @app_commands.describe(
        directory="Which directory to parse (default: all)",
        force="Force reparse all files even if already processed"
    )
    @app_commands.choices(directory=[
        app_commands.Choice(name="All directories", value="all"),
        app_commands.Choice(name="Public only", value="public"),
        app_commands.Choice(name="Private only", value="private"),
    ])
    async def parsestats(
        self,
        interaction: discord.Interaction,
        directory: str = "all",
        force: bool = False
    ):
        """Parse XLSX stats files and update gameshistory.json"""
        await interaction.response.defer(ephemeral=True)

        try:
            # Determine directories to scan
            if directory == "all":
                dirs = list(STATS_DIRS.values())
            else:
                dirs = [STATS_DIRS.get(directory)] if directory in STATS_DIRS else []

            if not dirs:
                await interaction.followup.send(f"❌ Invalid directory: {directory}", ephemeral=True)
                return

            # Parse files
            new_count, total_count = parse_all_stats(dirs, force_reparse=force)

            # Push to GitHub
            github_success = push_gameshistory_to_github()
            github_status = "✅ Pushed to GitHub" if github_success else "⚠️ GitHub push failed"

            # Auto-match games to pending series and update results
            updated_series = []
            if new_count > 0:
                try:
                    updated_series = await process_stats_and_update_results(self.bot) or []
                except Exception as e:
                    print(f"Error updating series results: {e}")

            series_status = f"✅ Updated {len(updated_series)} series results" if updated_series else "ℹ️ No matching series found"

            # Sync Discord ranks for all players after stats are parsed
            ranks_synced = 0
            try:
                ranks_synced = await sync_discord_ranks_for_all_players(self.bot)
            except Exception as e:
                print(f"Error syncing Discord ranks: {e}")

            ranks_status = f"✅ Synced ranks for {ranks_synced} players" if ranks_synced > 0 else "ℹ️ No ranks to sync"

            await interaction.followup.send(
                f"📊 **Stats Parsing Complete**\n"
                f"• New games parsed: **{new_count}**\n"
                f"• Total games: **{total_count}**\n"
                f"• {github_status}\n"
                f"• {series_status}\n"
                f"• {ranks_status}",
                ephemeral=True
            )
            print(f"[STATS PARSER] {interaction.user.name} parsed stats: {new_count} new, {total_count} total, {len(updated_series)} series updated, {ranks_synced} ranks synced")

        except Exception as e:
            await interaction.followup.send(f"❌ Error parsing stats: {e}", ephemeral=True)
            print(f"[STATS PARSER] Error: {e}")

    @app_commands.command(name="matchstats", description="[ADMIN] Match parsed stats to pending series")
    @has_admin_role()
    async def matchstats(self, interaction: discord.Interaction):
        """Manually trigger matching of parsed stats to pending series"""
        await interaction.response.defer(ephemeral=True)

        try:
            updated_series = await process_stats_and_update_results(self.bot) or []

            # Also sync Discord ranks after matching
            ranks_synced = 0
            try:
                ranks_synced = await sync_discord_ranks_for_all_players(self.bot)
            except Exception as e:
                print(f"Error syncing Discord ranks: {e}")

            if updated_series:
                await interaction.followup.send(
                    f"✅ **Updated {len(updated_series)} series results:**\n" +
                    "\n".join([f"• {s}" for s in updated_series]) +
                    f"\n\n✅ Synced ranks for {ranks_synced} players",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"ℹ️ No pending series matched to parsed games.\n"
                    f"Make sure games have been parsed and series are awaiting stats.\n\n"
                    f"✅ Synced ranks for {ranks_synced} players",
                    ephemeral=True
                )

        except Exception as e:
            await interaction.followup.send(f"❌ Error matching stats: {e}", ephemeral=True)
            print(f"[STATS PARSER] Match error: {e}")

    @app_commands.command(name="syncranks", description="[ADMIN] Sync all Discord rank roles with current stats")
    @has_admin_role()
    async def syncranks(self, interaction: discord.Interaction):
        """Manually sync Discord rank roles for all players"""
        await interaction.response.defer(ephemeral=True)

        try:
            ranks_synced = await sync_discord_ranks_for_all_players(self.bot)

            await interaction.followup.send(
                f"✅ **Discord Rank Sync Complete**\n"
                f"• Synced ranks for **{ranks_synced}** players",
                ephemeral=True
            )
            print(f"[STATS PARSER] {interaction.user.name} synced {ranks_synced} player ranks")

        except Exception as e:
            await interaction.followup.send(f"❌ Error syncing ranks: {e}", ephemeral=True)
            print(f"[STATS PARSER] Sync error: {e}")

    @app_commands.command(name="liststats", description="[ADMIN] List available XLSX stats files")
    @has_admin_role()
    @app_commands.describe(directory="Which directory to list")
    @app_commands.choices(directory=[
        app_commands.Choice(name="All directories", value="all"),
        app_commands.Choice(name="Public only", value="public"),
        app_commands.Choice(name="Private only", value="private"),
    ])
    async def liststats(self, interaction: discord.Interaction, directory: str = "all"):
        """List available XLSX stats files"""
        await interaction.response.defer(ephemeral=True)

        try:
            # Determine directories to scan
            if directory == "all":
                dirs_to_scan = STATS_DIRS.items()
            else:
                dirs_to_scan = [(directory, STATS_DIRS.get(directory))] if directory in STATS_DIRS else []

            # Get existing parsed files
            existing_games = load_existing_games()
            parsed_files = get_parsed_files(existing_games)

            output = []
            total_files = 0
            total_unparsed = 0

            for dir_name, dir_path in dirs_to_scan:
                if not dir_path:
                    continue

                files = scan_stats_directory(dir_path)
                unparsed = [f for f in files if os.path.basename(f) not in parsed_files]

                output.append(f"**{dir_name}** ({dir_path}):")
                output.append(f"  • Total files: {len(files)}")
                output.append(f"  • Unparsed: {len(unparsed)}")

                # Show last 5 unparsed files
                if unparsed[:5]:
                    output.append("  • Recent unparsed:")
                    for f in unparsed[:5]:
                        output.append(f"    - {os.path.basename(f)}")

                total_files += len(files)
                total_unparsed += len(unparsed)
                output.append("")

            output.append(f"**Summary:** {total_files} total files, {total_unparsed} unparsed")

            await interaction.followup.send("\n".join(output), ephemeral=True)

        except Exception as e:
            await interaction.followup.send(f"❌ Error listing stats: {e}", ephemeral=True)

    @app_commands.command(name="gamehistory", description="View recent parsed games")
    @app_commands.describe(count="Number of games to show (default: 5)")
    async def gamehistory(self, interaction: discord.Interaction, count: int = 5):
        """Show recent parsed games"""
        count = min(count, 10)  # Limit to 10

        games = load_existing_games()

        if not games:
            await interaction.response.send_message("No games have been parsed yet!", ephemeral=True)
            return

        embed = discord.Embed(
            title="📊 Recent Game History",
            color=discord.Color.blue()
        )

        for i, game in enumerate(games[:count], 1):
            details = game.get('details', {})
            players = game.get('players', [])

            map_name = details.get('Map Name', 'Unknown')
            variant = details.get('Variant Name', 'Unknown')
            duration = details.get('Duration', '?:??')
            start_time = details.get('Start Time', '')

            # Get top player
            top_player = players[0] if players else None
            top_info = f"{top_player['name']} ({top_player['kills']}K/{top_player['deaths']}D)" if top_player else "N/A"

            embed.add_field(
                name=f"{i}. {map_name} - {variant}",
                value=f"⏱️ {duration} | 🏆 {top_info}\n📅 {start_time}",
                inline=False
            )

        embed.set_footer(text=f"Total games: {len(games)}")
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    """Setup function to add cog to bot"""
    await bot.add_cog(StatsParserCommands(bot))


# CLI interface
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Parse Halo 2 XLSX stats files")
    parser.add_argument('--dir', '-d', help="Directory to scan (can be used multiple times)", action='append')
    parser.add_argument('--file', '-f', help="Parse a single XLSX file")
    parser.add_argument('--force', action='store_true', help="Force reparse all files")
    parser.add_argument('--list', '-l', action='store_true', help="List valid stats files without parsing")

    args = parser.parse_args()

    if args.file:
        # Parse single file
        print(f"Parsing single file: {args.file}")
        result = parse_single_file(args.file)
        if result:
            print(f"✅ Successfully parsed: {result['details']['Map Name']} - {result['details']['Variant Name']}")
        else:
            print("❌ Failed to parse file")

    elif args.list:
        # List files only
        directories = args.dir if args.dir else list(STATS_DIRS.values())
        for directory in directories:
            print(f"\n📂 {directory}:")
            files = scan_stats_directory(directory)
            for f in files:
                print(f"   {os.path.basename(f)}")
            print(f"   Total: {len(files)} files")

    else:
        # Parse all files
        directories = args.dir if args.dir else None
        new_count, total_count = parse_all_stats(directories, force_reparse=args.force)
        print(f"\n📊 Summary: {new_count} new games parsed, {total_count} total games")
