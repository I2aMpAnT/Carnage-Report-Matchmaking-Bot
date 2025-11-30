# bot.py - Simple launcher for HCRBot
# Pulls latest code from GitHub and runs HCRBot.py

import os
import sys
import subprocess

def pull_from_github():
    """Pull latest code from GitHub before starting"""
    print("📥 Pulling latest code from GitHub...")
    try:
        result = subprocess.run(
            ["git", "pull", "origin", "main"],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            if "Already up to date" in result.stdout:
                print("✅ Already up to date")
            else:
                print("✅ Updated from GitHub:")
                print(result.stdout)
        else:
            print(f"⚠️ Git pull warning: {result.stderr}")
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
