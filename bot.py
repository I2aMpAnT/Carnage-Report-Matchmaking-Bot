# bot.py - Simple launcher for HCRBot
# Pulls latest code from GitHub and runs HCRBot.py

import os
import sys
import subprocess
import shutil

# JSON data files to preserve (not overwritten by git)
DATA_FILES = [
    "rankstats.json",
    "matchhistory.json",
    "testmatchhistory.json",
    "gamestats.json",
    "queue_config.json",
    "xp_config.json",
    "matchmakingstate.json",
    "players.json"
]

def pull_from_github():
    """Pull latest code from GitHub before starting - ALWAYS uses latest code"""
    print("📥 Pulling latest code from GitHub...")
    try:
        # Backup JSON data files first
        backups = {}
        for filename in DATA_FILES:
            if os.path.exists(filename):
                backup_name = f"{filename}.backup"
                shutil.copy2(filename, backup_name)
                backups[filename] = backup_name

        if backups:
            print(f"📦 Backed up {len(backups)} data files")

        # Fetch latest from origin
        fetch_result = subprocess.run(
            ["git", "fetch", "origin", "main"],
            capture_output=True,
            text=True,
            timeout=30
        )
        if fetch_result.returncode != 0:
            print(f"⚠️ Git fetch warning: {fetch_result.stderr}")

        # Hard reset to origin/main - ALWAYS gets latest code
        reset_result = subprocess.run(
            ["git", "reset", "--hard", "origin/main"],
            capture_output=True,
            text=True,
            timeout=30
        )
        if reset_result.returncode == 0:
            print("✅ Updated to latest code from GitHub")
            # Show what commit we're on
            log_result = subprocess.run(
                ["git", "log", "-1", "--oneline"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if log_result.returncode == 0:
                print(f"   Commit: {log_result.stdout.strip()}")
        else:
            print(f"⚠️ Git reset warning: {reset_result.stderr}")

        # Restore JSON data files from backup
        for filename, backup_name in backups.items():
            if os.path.exists(backup_name):
                shutil.copy2(backup_name, filename)
                os.remove(backup_name)

        if backups:
            print(f"📦 Restored {len(backups)} data files")

    except subprocess.TimeoutExpired:
        print("⚠️ Git pull timed out - continuing with existing files")
    except FileNotFoundError:
        print("⚠️ Git not found - continuing with existing files")
    except Exception as e:
        print(f"⚠️ Git pull error: {e} - continuing with existing files")
    print()

def main():
    print()
    print("=" * 50)
    print("  Carnage Report Matchmaking Bot")
    print("=" * 50)
    print()

    # Pull latest from GitHub first
    pull_from_github()

    # Check if HCRBot.py exists
    if not os.path.exists("HCRBot.py"):
        print("❌ HCRBot.py not found!")
        print("Please upload all .py files to your server:")
        print("  - HCRBot.py")
        print("  - commands.py")
        print("  - searchmatchmaking.py")
        print("  - pregame.py")
        print("  - ingame.py")
        print("  - postgame.py")
        print("  - STATSRANKS.py")
        print("  - twitch.py")
        print("  - state_manager.py")
        print("  - github_webhook.py")
        print("  - stats_parser.py")
        sys.exit(1)

    print("🚀 Starting bot...")
    print()

    # Import and run HCRBot (this works better than exec)
    import HCRBot

if __name__ == "__main__":
    main()
