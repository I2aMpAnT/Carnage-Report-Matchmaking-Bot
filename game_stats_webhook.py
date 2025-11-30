"""
game_stats_webhook.py - Game Stats Webhook Receiver
Receives webhook notifications when new game stats are available,
processes identity files to map Machine IDs to Discord IDs,
and updates stats accordingly.

!! REMEMBER TO UPDATE VERSION NUMBER WHEN MAKING CHANGES !!
"""

MODULE_VERSION = "1.0.0"

import os
import json
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from aiohttp import web
import asyncio
import pandas as pd

# Configuration
WEBHOOK_PORT = 8080
WEBHOOK_HOST = "0.0.0.0"

# Stats directories on VPS
STATS_DIR = "/home/carnagereport/stats"
PUBLIC_STATS_DIR = os.path.join(STATS_DIR, "public")
PRIVATE_STATS_DIR = os.path.join(STATS_DIR, "private")

# Local files
PLAYERS_FILE = "players.json"
GAMES_HISTORY_FILE = "gameshistory.json"

# Timestamp pattern for valid stats files (YYYYMMDD_HHMMSS.xlsx)
TIMESTAMP_PATTERN = re.compile(r'^(\d{8}_\d{6})\.xlsx$')
IDENTITY_PATTERN = re.compile(r'^(\d{8}_\d{6})_identity\.xlsx$')


def log_webhook(message: str):
    """Log webhook actions with timestamp"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[WEBHOOK] [{timestamp}] {message}")


# ============================================================
# PLAYERS.JSON - MAC Address to Discord ID Mapping
# ============================================================

def load_players() -> Dict:
    """Load players.json which contains MAC→Discord mappings"""
    if os.path.exists(PLAYERS_FILE):
        try:
            with open(PLAYERS_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            log_webhook(f"Error loading {PLAYERS_FILE}: {e}")
    return {}


def normalize_mac(mac: str) -> str:
    """
    Normalize MAC address to consistent format (uppercase, colon-separated)
    Input formats: 0050F22C4A45, 00:50:F2:2C:4A:45, 00-50-F2-2C-4A-45
    Output: 00:50:F2:2C:4A:45
    """
    # Remove all separators and convert to uppercase
    clean = re.sub(r'[:\-]', '', mac).upper()

    # Insert colons every 2 characters
    if len(clean) == 12:
        return ':'.join(clean[i:i+2] for i in range(0, 12, 2))
    return mac.upper()


def find_discord_id_by_mac(mac: str, players: Dict) -> Optional[str]:
    """
    Find Discord ID associated with a MAC address

    Args:
        mac: Machine Identifier from identity file
        players: Players dict from players.json

    Returns:
        Discord ID string or None if not found
    """
    normalized_mac = normalize_mac(mac)

    for discord_id, player_data in players.items():
        if "mac_addresses" in player_data:
            for stored_mac in player_data["mac_addresses"]:
                if normalize_mac(stored_mac) == normalized_mac:
                    return discord_id
    return None


def get_player_display_name(discord_id: str, players: Dict) -> str:
    """Get display name for a Discord ID"""
    if discord_id in players:
        return players[discord_id].get("display_name", f"User_{discord_id[:8]}")
    return f"User_{discord_id[:8]}"


# ============================================================
# IDENTITY FILE PARSER
# ============================================================

def parse_identity_file(filepath: str) -> Dict[str, Dict]:
    """
    Parse identity XLSX file to extract Player Name → Machine ID mapping

    Args:
        filepath: Path to the _identity.xlsx file

    Returns:
        Dict mapping player names to their identity info:
        {
            "I2aMpAnT": {
                "xbox_id": "BAD00000454A2CF2",
                "machine_id": "0050F22C4A45",
                "emblem_url": "https://..."
            }
        }
    """
    try:
        df = pd.read_excel(filepath, sheet_name='Player Identities')

        identities = {}
        for _, row in df.iterrows():
            player_name = str(row.get('Player Name', '')).strip()
            if player_name:
                identities[player_name] = {
                    "xbox_id": str(row.get('Xbox Identifier', '')),
                    "machine_id": str(row.get('Machine Identifier', '')),
                    "emblem_url": str(row.get('Emblem URL', ''))
                }

        log_webhook(f"Parsed {len(identities)} player identities from {os.path.basename(filepath)}")
        return identities

    except Exception as e:
        log_webhook(f"Error parsing identity file {filepath}: {e}")
        return {}


def find_identity_file(stats_filepath: str) -> Optional[str]:
    """
    Find the corresponding identity file for a stats file

    Args:
        stats_filepath: Path to stats file (e.g., /path/20251128_074332.xlsx)

    Returns:
        Path to identity file or None if not found
    """
    # Extract timestamp from stats filename
    basename = os.path.basename(stats_filepath)
    match = TIMESTAMP_PATTERN.match(basename)

    if not match:
        return None

    timestamp = match.group(1)
    directory = os.path.dirname(stats_filepath)

    # Look for identity file with same timestamp
    identity_filename = f"{timestamp}_identity.xlsx"
    identity_path = os.path.join(directory, identity_filename)

    if os.path.exists(identity_path):
        return identity_path

    # Also check parent stats directory
    for subdir in [PUBLIC_STATS_DIR, PRIVATE_STATS_DIR, STATS_DIR]:
        alt_path = os.path.join(subdir, identity_filename)
        if os.path.exists(alt_path):
            return alt_path

    return None


# ============================================================
# STATS FILE PARSER (with Discord ID integration)
# ============================================================

def parse_stats_file_with_identity(stats_filepath: str, identities: Dict[str, Dict], players: Dict) -> Optional[Dict]:
    """
    Parse stats XLSX file and enrich with Discord IDs from identity mapping

    Args:
        stats_filepath: Path to stats XLSX file
        identities: Player identities from identity file
        players: Players dict with MAC→Discord mappings

    Returns:
        Game data dict with Discord IDs included
    """
    try:
        xlsx = pd.ExcelFile(stats_filepath)

        # Parse Game Details
        details_df = pd.read_excel(xlsx, sheet_name='Game Details')
        if details_df.empty:
            log_webhook(f"Empty Game Details in {stats_filepath}")
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
        game_players = []

        for _, row in players_df.iterrows():
            player_name = str(row.get('name', '')).strip()

            # Look up identity and Discord ID
            discord_id = None
            machine_id = None

            if player_name in identities:
                machine_id = identities[player_name].get("machine_id", "")
                if machine_id:
                    discord_id = find_discord_id_by_mac(machine_id, players)

            player = {
                "name": player_name,
                "discord_id": discord_id,
                "machine_id": machine_id,
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
            game_players.append(player)

            # Log the mapping
            if discord_id:
                log_webhook(f"  Mapped {player_name} (MAC: {machine_id}) -> Discord ID: {discord_id}")
            elif machine_id:
                log_webhook(f"  {player_name} (MAC: {machine_id}) -> No Discord link found")

        # Parse Game Statistics
        stats_df = pd.read_excel(xlsx, sheet_name='Game Statistics')
        stats = []
        skip_columns = {'Player', 'Emblem URL'}

        for _, row in stats_df.iterrows():
            stat = {"Player": str(row.get('Player', ''))}
            if 'Emblem URL' in stats_df.columns:
                stat['emblem_url'] = str(row.get('Emblem URL', ''))
            for col in stats_df.columns:
                if col not in skip_columns:
                    val = row.get(col, 0)
                    try:
                        stat[col] = int(val) if pd.notna(val) else 0
                    except (ValueError, TypeError):
                        pass
            stats.append(stat)

        # Merge best_spree and total_time_alive into players
        stats_by_player = {s['Player']: s for s in stats}
        for player in game_players:
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
            "players": game_players,
            "stats": stats,
            "medals": medals,
            "weapons": weapons,
            "source_file": os.path.basename(stats_filepath),
            "identity_file": os.path.basename(find_identity_file(stats_filepath) or ""),
            "parsed_at": datetime.now().isoformat(),
            "has_discord_mappings": any(p.get("discord_id") for p in game_players)
        }

        return game

    except Exception as e:
        log_webhook(f"Error parsing {stats_filepath}: {e}")
        return None


# ============================================================
# MAIN PROCESSING FUNCTION
# ============================================================

def process_game_files(stats_filepath: str) -> Optional[Dict]:
    """
    Process a game stats file with its corresponding identity file

    Args:
        stats_filepath: Path to the stats XLSX file

    Returns:
        Processed game data with Discord ID mappings, or None on failure
    """
    log_webhook(f"Processing game: {os.path.basename(stats_filepath)}")

    # Load players.json for MAC→Discord mapping
    players = load_players()
    log_webhook(f"Loaded {len(players)} players from {PLAYERS_FILE}")

    # Find and parse identity file
    identity_filepath = find_identity_file(stats_filepath)
    identities = {}

    if identity_filepath:
        log_webhook(f"Found identity file: {os.path.basename(identity_filepath)}")
        identities = parse_identity_file(identity_filepath)
    else:
        log_webhook(f"No identity file found for {os.path.basename(stats_filepath)}")

    # Parse stats with identity integration
    game_data = parse_stats_file_with_identity(stats_filepath, identities, players)

    if game_data:
        mapped_count = sum(1 for p in game_data.get("players", []) if p.get("discord_id"))
        total_count = len(game_data.get("players", []))
        log_webhook(f"Processed game: {mapped_count}/{total_count} players mapped to Discord IDs")

    return game_data


def save_game_to_history(game_data: Dict) -> bool:
    """
    Save processed game data to gameshistory.json

    Args:
        game_data: Processed game data dict

    Returns:
        True if saved successfully
    """
    try:
        # Load existing history
        history = []
        if os.path.exists(GAMES_HISTORY_FILE):
            with open(GAMES_HISTORY_FILE, 'r') as f:
                history = json.load(f)

        # Check for duplicates by source_file
        source_file = game_data.get("source_file", "")
        existing_files = {g.get("source_file") for g in history}

        if source_file in existing_files:
            log_webhook(f"Game {source_file} already in history, skipping")
            return False

        # Add new game at the beginning (newest first)
        history.insert(0, game_data)

        # Save
        with open(GAMES_HISTORY_FILE, 'w') as f:
            json.dump(history, f, indent=2)

        log_webhook(f"Saved game to {GAMES_HISTORY_FILE} (total: {len(history)} games)")
        return True

    except Exception as e:
        log_webhook(f"Error saving game to history: {e}")
        return False


# ============================================================
# WEBHOOK SERVER
# ============================================================

async def handle_game_webhook(request: web.Request) -> web.Response:
    """
    Handle incoming webhook when new game stats are available

    Expected POST body (JSON):
    {
        "filename": "20251128_074332.xlsx",
        "directory": "private",  // or "public"
        "timestamp": "2025-11-28T07:43:32"
    }
    """
    try:
        data = await request.json()
        log_webhook(f"Received webhook: {data}")

        filename = data.get("filename", "")
        directory = data.get("directory", "private")

        if not filename:
            return web.json_response({"error": "Missing filename"}, status=400)

        # Determine full path
        if directory == "public":
            stats_dir = PUBLIC_STATS_DIR
        else:
            stats_dir = PRIVATE_STATS_DIR

        stats_filepath = os.path.join(stats_dir, filename)

        # Check if file exists
        if not os.path.exists(stats_filepath):
            # Try other directories
            for alt_dir in [STATS_DIR, PUBLIC_STATS_DIR, PRIVATE_STATS_DIR]:
                alt_path = os.path.join(alt_dir, filename)
                if os.path.exists(alt_path):
                    stats_filepath = alt_path
                    break
            else:
                return web.json_response({"error": f"File not found: {filename}"}, status=404)

        # Process the game
        game_data = process_game_files(stats_filepath)

        if not game_data:
            return web.json_response({"error": "Failed to process game"}, status=500)

        # Save to history
        saved = save_game_to_history(game_data)

        # Push to GitHub (import here to avoid circular imports)
        try:
            from github_webhook import push_file_to_github
            push_file_to_github(GAMES_HISTORY_FILE, "gameshistory.json",
                              f"Game stats: {filename}")
        except Exception as e:
            log_webhook(f"GitHub push error: {e}")

        return web.json_response({
            "success": True,
            "game": game_data.get("details", {}),
            "players_mapped": sum(1 for p in game_data.get("players", []) if p.get("discord_id")),
            "players_total": len(game_data.get("players", [])),
            "saved_to_history": saved
        })

    except json.JSONDecodeError:
        return web.json_response({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        log_webhook(f"Webhook error: {e}")
        return web.json_response({"error": str(e)}, status=500)


async def handle_health(request: web.Request) -> web.Response:
    """Health check endpoint"""
    return web.json_response({
        "status": "ok",
        "module": "game_stats_webhook",
        "version": MODULE_VERSION
    })


async def handle_process_manual(request: web.Request) -> web.Response:
    """
    Manual processing endpoint - process a specific file
    GET /process?file=20251128_074332.xlsx&dir=private
    """
    filename = request.query.get("file", "")
    directory = request.query.get("dir", "private")

    if not filename:
        return web.json_response({"error": "Missing file parameter"}, status=400)

    # Simulate webhook data
    data = {"filename": filename, "directory": directory}

    # Create a mock request and process
    # (reuse the webhook handler logic)
    if directory == "public":
        stats_dir = PUBLIC_STATS_DIR
    else:
        stats_dir = PRIVATE_STATS_DIR

    stats_filepath = os.path.join(stats_dir, filename)

    if not os.path.exists(stats_filepath):
        return web.json_response({"error": f"File not found: {stats_filepath}"}, status=404)

    game_data = process_game_files(stats_filepath)

    if not game_data:
        return web.json_response({"error": "Failed to process"}, status=500)

    saved = save_game_to_history(game_data)

    return web.json_response({
        "success": True,
        "game": game_data.get("details", {}),
        "players": game_data.get("players", []),
        "saved": saved
    })


def create_webhook_app() -> web.Application:
    """Create the webhook web application"""
    app = web.Application()
    app.router.add_post('/webhook/game', handle_game_webhook)
    app.router.add_get('/health', handle_health)
    app.router.add_get('/process', handle_process_manual)
    return app


async def start_webhook_server():
    """Start the webhook server"""
    app = create_webhook_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, WEBHOOK_HOST, WEBHOOK_PORT)
    await site.start()
    log_webhook(f"Webhook server started on {WEBHOOK_HOST}:{WEBHOOK_PORT}")
    log_webhook(f"Endpoints:")
    log_webhook(f"  POST /webhook/game - Receive game notifications")
    log_webhook(f"  GET  /health - Health check")
    log_webhook(f"  GET  /process?file=X&dir=Y - Manual processing")
    return runner


# ============================================================
# STANDALONE TESTING
# ============================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        # Test mode: process a specific file
        test_file = sys.argv[1]
        print(f"Testing with file: {test_file}")

        game_data = process_game_files(test_file)

        if game_data:
            print("\n=== GAME DATA ===")
            print(json.dumps(game_data, indent=2, default=str))
        else:
            print("Failed to process file")
    else:
        # Start webhook server
        print("Starting webhook server...")
        loop = asyncio.get_event_loop()
        loop.run_until_complete(start_webhook_server())
        loop.run_forever()
