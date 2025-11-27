# bot.py - Launcher (Do not modify this file)
# This file launches HCRBot.py which contains all the bot logic.
# The bot auto-updates from GitHub when AUTO_UPDATE=1
# This launcher file stays on the server and never needs updates.

import traceback

if __name__ == '__main__':
    print("=" * 50)
    print("  Carnage Report Matchmaking Bot Launcher")
    print("=" * 50)
    print()
    
    try:
        # Import and run the main bot (same directory)
        import HCRBot
    except Exception as e:
        print(f"❌ ERROR: {e}")
        print()
        traceback.print_exc()
        print()
        print("Bot failed to start. Check the error above.")
