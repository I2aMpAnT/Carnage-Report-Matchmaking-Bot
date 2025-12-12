# bot.py - Simple launcher for HCRBot
# Pulls latest code from GitHub and runs HCRBot.py

import os
import sys
import subprocess
import shutil
import glob

# GitHub raw URL for bot.py (to self-update before backup)
GITHUB_RAW_URL = "https://raw.githubusercontent.com/I2aMpAnT/Carnage-Report-Matchmaking-Bot/main/bot.py"

def self_update():
    """Update bot.py itself BEFORE doing anything else.

    This ensures the latest backup logic is used, avoiding chicken-and-egg
    issues where new JSON files aren't backed up because the old bot.py
    doesn't know about them.
    """
    try:
        import urllib.request

        # Fetch latest bot.py from GitHub
        with urllib.request.urlopen(GITHUB_RAW_URL, timeout=10) as response:
            latest_code = response.read().decode('utf-8')

        # Read current bot.py
        with open(__file__, 'r') as f:
            current_code = f.read()

        # If different, update and re-exec
        if latest_code != current_code:
            print("🔄 Updating bot.py to latest version...")
            with open(__file__, 'w') as f:
                f.write(latest_code)
            print("✅ bot.py updated, restarting...")
            # Re-exec with same arguments
            os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception as e:
        print(f"⚠️ Self-update check failed: {e} - continuing with current version")

def get_json_files_to_backup():
    """Get all JSON files that should be preserved across git pulls"""
    # Backup ALL .json files to ensure no data is lost
    # This avoids issues where new json files are added to the repo
    # but the local bot.py doesn't know about them yet
    json_files = glob.glob("*.json")
    # Exclude any config files that should come from git
    exclude = ["package.json", "package-lock.json"]
    return [f for f in json_files if f not in exclude]

def pull_from_github():
    """Pull latest code from GitHub before starting - ALWAYS uses latest code"""
    print("📥 Pulling latest code from GitHub...")
    try:
        # Backup ALL JSON data files first (dynamically discovered)
        # This ensures new json files are backed up even if bot.py is old
        backups = {}
        for filename in get_json_files_to_backup():
            if os.path.exists(filename):
                backup_name = f"{filename}.backup"
                shutil.copy2(filename, backup_name)
                backups[filename] = backup_name

        if backups:
            print(f"📦 Backed up {len(backups)} JSON files: {', '.join(backups.keys())}")

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

    # Self-update bot.py FIRST (ensures latest backup logic is used)
    self_update()

    # Pull latest from GitHub
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
        sys.exit(1)

    print("🚀 Starting bot...")
    print()

    # Import and run HCRBot (this works better than exec)
    import HCRBot

if __name__ == "__main__":
    main()
