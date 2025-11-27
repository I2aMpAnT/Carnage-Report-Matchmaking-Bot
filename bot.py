# bot.py - Launcher (Do not modify this file)
# This file launches HCRBot.py which contains all the bot logic.
# Push updates to HCRBot.py and other module files on GitHub.
# This launcher file stays on the server and never needs updates.

import sys
import os

if __name__ == '__main__':
    print("=" * 50)
    print("  Carnage Report Matchmaking Bot Launcher")
    print("=" * 50)
    print()
    
    # Add the GitHub repo folder to Python path
    repo_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Carnage-Report-Matchmaking-Bot")
    
    if os.path.exists(repo_dir):
        sys.path.insert(0, repo_dir)
        os.chdir(repo_dir)
        print(f"📁 Loading from: {repo_dir}")
    else:
        print(f"❌ ERROR: Cannot find repo folder: {repo_dir}")
        print("Make sure you cloned the GitHub repo into this directory.")
        sys.exit(1)
    
    print()
    
    # Import and run the main bot
    import HCRBot
