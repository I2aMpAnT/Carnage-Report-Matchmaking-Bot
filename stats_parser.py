"""
stats_parser.py - XLSX Stats File Parser
Parses Halo 2 game statistics from XLSX files exported from the game.

Reads files from VPS directories:
- /home/carnagereport/stats/public/  (public games)
- /home/carnagereport/stats/private/ (private/ranked games)

Converts XLSX files to gameshistory.json format for the website.
"""

MODULE_VERSION = "1.0.0"

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

            await interaction.followup.send(
                f"📊 **Stats Parsing Complete**\n"
                f"• New games parsed: **{new_count}**\n"
                f"• Total games: **{total_count}**\n"
                f"• {github_status}",
                ephemeral=True
            )
            print(f"[STATS PARSER] {interaction.user.name} parsed stats: {new_count} new, {total_count} total")

        except Exception as e:
            await interaction.followup.send(f"❌ Error parsing stats: {e}", ephemeral=True)
            print(f"[STATS PARSER] Error: {e}")

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
