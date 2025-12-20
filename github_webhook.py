"""
github_webhook.py - Automatic GitHub Updates
Pushes all JSON data files to GitHub whenever they're updated
"""

MODULE_VERSION = "1.2.2"

import json
import base64
import os
from datetime import datetime, timezone, timedelta

# EST timezone
EST = timezone(timedelta(hours=-5))

# Try to import requests, but don't fail if not available
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

# aiohttp for async operations (always available with discord.py)
import aiohttp

# GitHub Configuration
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')  # Personal Access Token
GITHUB_REPO = "I2aMpAnT/CarnageReport.com"
GITHUB_BRANCH = "main"

# JSON files to sync (local filename -> GitHub path)
# Does NOT include:
#   - matchmakingstate.json (internal bot state only)
#   - players.json (confidential player data - stays on server only)
JSON_FILES = {
    # Playlist match histories
    "MLG4v4.json": "MLG4v4.json",
    "team_hardcore.json": "team_hardcore.json",
    "double_team.json": "double_team.json",
    "head_to_head.json": "head_to_head.json",
    "testMLG4v4.json": "testMLG4v4.json",
    # Stats and config (MMR.json excluded - local is always most recent)
    "gamestats.json": "gamestats.json",
    "queue_config.json": "queue_config.json",
    "xp_config.json": "xp_config.json",
    "playlists.json": "playlists.json"
}

def log_github_action(message: str):
    """Log GitHub webhook actions (EST timezone)"""
    timestamp = datetime.now(EST).strftime('%Y-%m-%d %H:%M:%S EST')
    print(f"[GITHUB] [{timestamp}] {message}")


def pull_file_from_github(github_path: str) -> dict:
    """
    Pull a JSON file from GitHub repo (raw content, no auth needed for public repos)

    Args:
        github_path: Path in the GitHub repo

    Returns:
        dict: Parsed JSON content, or None if failed
    """
    raw_url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/{github_path}"

    try:
        response = requests.get(raw_url, timeout=10)

        if response.status_code == 200:
            data = response.json()
            log_github_action(f"✅ Pulled {github_path} from GitHub")
            return data
        else:
            log_github_action(f"❌ Failed to pull {github_path}: {response.status_code}")
            return None

    except json.JSONDecodeError as e:
        log_github_action(f"⚠️ Invalid JSON in {github_path}: {e}")
        return None
    except Exception as e:
        log_github_action(f"❌ Exception pulling {github_path}: {e}")
        return None


def pull_rankstats_from_github() -> dict:
    """Pull rankstats.json from GitHub (sync version)"""
    return pull_file_from_github("rankstats.json")


async def async_pull_file_from_github(github_path: str) -> dict:
    """
    Async version: Pull a JSON file from GitHub repo using aiohttp
    Uses GitHub API instead of raw.githubusercontent.com to avoid caching issues.

    Args:
        github_path: Path in the GitHub repo

    Returns:
        dict: Parsed JSON content, or None if failed
    """
    # Use GitHub API to avoid raw.githubusercontent.com cache (can be 5-10 min stale)
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{github_path}"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "CarnageReportBot"
    }
    # Add auth token if available for higher rate limits
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    result = await response.json()
                    # GitHub API returns base64 encoded content
                    content_b64 = result.get("content", "")
                    content = base64.b64decode(content_b64).decode('utf-8')
                    data = json.loads(content)
                    log_github_action(f"✅ Pulled {github_path} from GitHub API (async, no cache)")
                    return data
                else:
                    log_github_action(f"❌ Failed to pull {github_path}: {response.status}")
                    return None

    except json.JSONDecodeError as e:
        log_github_action(f"⚠️ Invalid JSON in {github_path}: {e}")
        return None
    except Exception as e:
        log_github_action(f"❌ Exception pulling {github_path}: {e}")
        return None


async def async_pull_rankstats_from_github() -> dict:
    """Async version: Pull rankstats.json from GitHub"""
    return await async_pull_file_from_github("rankstats.json")


async def async_pull_ranks_from_github() -> dict:
    """Async version: Pull ranks.json from GitHub (website source of truth)"""
    return await async_pull_file_from_github("ranks.json")


async def async_pull_emblems_from_github() -> dict:
    """Async version: Pull emblems.json from GitHub (player emblem data)"""
    return await async_pull_file_from_github("emblems.json")


def push_file_to_github(local_file: str, github_path: str, commit_message: str = None) -> bool:
    """
    Push a local file to GitHub repo
    
    Args:
        local_file: Local filename
        github_path: Path in the GitHub repo
        commit_message: Git commit message (auto-generated if None)
    
    Returns:
        bool: True if successful, False otherwise
    """
    if not GITHUB_TOKEN:
        log_github_action("⚠️ GITHUB_TOKEN not set in .env file")
        return False
    
    if not os.path.exists(local_file):
        log_github_action(f"⚠️ {local_file} not found")
        return False
    
    # GitHub API endpoint
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{github_path}"
    
    # Headers
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    try:
        # Read local file
        with open(local_file, 'r') as f:
            content = f.read()
        
        # Verify it's valid JSON
        json.loads(content)
        
        # Get current file SHA (needed for updates)
        response = requests.get(api_url, headers=headers)
        
        if response.status_code == 200:
            current_sha = response.json()["sha"]
        else:
            current_sha = None  # File doesn't exist yet
        
        # Encode content to base64
        content_bytes = content.encode('utf-8')
        content_base64 = base64.b64encode(content_bytes).decode('utf-8')
        
        # Auto-generate commit message if not provided
        if commit_message is None:
            commit_message = f"Auto-update: {local_file} {datetime.now(EST).strftime('%Y-%m-%d %H:%M:%S EST')}"
        
        # Prepare payload
        payload = {
            "message": commit_message,
            "content": content_base64,
            "branch": GITHUB_BRANCH
        }
        
        # Add SHA if file exists (for updates)
        if current_sha:
            payload["sha"] = current_sha
        
        # Push to GitHub
        response = requests.put(api_url, headers=headers, json=payload)
        
        if response.status_code in [200, 201]:
            log_github_action(f"✅ Pushed {local_file} to GitHub")
            return True
        else:
            log_github_action(f"❌ Failed to push {local_file}: {response.status_code}")
            return False
    
    except json.JSONDecodeError as e:
        log_github_action(f"⚠️ Invalid JSON in {local_file}: {e}")
        return False
    except Exception as e:
        log_github_action(f"❌ Exception pushing {local_file}: {e}")
        return False


# Convenience functions for each file type
def update_matchhistory_on_github():
    """Push MLG4v4.json to GitHub (legacy name kept for compatibility)"""
    return push_file_to_github("MLG4v4.json", "MLG4v4.json")

def update_testmatchhistory_on_github():
    """Push testMLG4v4.json to GitHub (obsolete - kept for compatibility)"""
    return push_file_to_github("testMLG4v4.json", "testMLG4v4.json")

def update_mmr_on_github():
    """Push MMR.json to GitHub"""
    return push_file_to_github("MMR.json", "MMR.json")

def update_rankstats_on_github():
    """DEPRECATED: Use update_mmr_on_github instead. Kept for backwards compatibility."""
    return update_mmr_on_github()

def update_gamestats_on_github():
    """Push gamestats.json to GitHub"""
    return push_file_to_github("gamestats.json", "gamestats.json")

def update_players_on_github():
    """DISABLED - players.json contains confidential data and stays on server only"""
    log_github_action("⚠️ players.json is confidential - not pushing to GitHub")
    return False

def update_queue_config_on_github():
    """Push queue_config.json to GitHub"""
    return push_file_to_github("queue_config.json", "queue_config.json")

def update_xp_config_on_github():
    """Push xp_config.json to GitHub"""
    return push_file_to_github("xp_config.json", "xp_config.json")

def update_all_on_github():
    """Push all JSON files to GitHub"""
    results = {}
    for local_file, github_path in JSON_FILES.items():
        results[local_file] = push_file_to_github(local_file, github_path)
    return results


# Legacy function for backwards compatibility
def push_to_github(file_content: str, commit_message: str = "Update match history") -> bool:
    """Legacy function - pushes matchhistory.json content directly"""
    if not GITHUB_TOKEN:
        log_github_action("⚠️ GITHUB_TOKEN not set in .env file")
        return False
    
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/matchhistory.json"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    try:
        response = requests.get(api_url, headers=headers)
        current_sha = response.json()["sha"] if response.status_code == 200 else None
        
        content_base64 = base64.b64encode(file_content.encode('utf-8')).decode('utf-8')
        payload = {
            "message": commit_message,
            "content": content_base64,
            "branch": GITHUB_BRANCH
        }
        if current_sha:
            payload["sha"] = current_sha
        
        response = requests.put(api_url, headers=headers, json=payload)
        
        if response.status_code in [200, 201]:
            log_github_action(f"✅ Successfully pushed to GitHub: {commit_message}")
            return True
        else:
            log_github_action(f"❌ GitHub push failed: {response.status_code}")
            return False
    except Exception as e:
        log_github_action(f"❌ Exception during GitHub push: {e}")
        return False
