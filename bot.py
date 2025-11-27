# bot.py - Simple launcher for HCRBot
# Just runs HCRBot.py directly - upload all .py files to your server manually

import os
import sys

def main():
    print()
    print("=" * 50)
    print("  Carnage Report Matchmaking Bot")
    print("=" * 50)
    print()
    
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
