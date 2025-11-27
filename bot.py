# bot.py - Launcher that updates from GitHub then runs the bot
# Files are pulled directly into root directory for easy manual editing

import os
import sys

# GitHub repo info
GITHUB_USER = "I2aMpAnT"
GITHUB_REPO = "HCR-Bot"
GITHUB_BRANCH = "main"

# Files to pull from GitHub (these go in root alongside bot.py)
GITHUB_FILES = [
    "HCRBot.py",
    "commands.py", 
    "searchmatchmaking.py",
    "pregame.py",
    "ingame.py",
    "postgame.py",
    "STATSRANKS.py",
    "twitch.py",
    "state_manager.py",
    "github_webhook.py"
]

def update_from_github():
    """Pull latest files from GitHub into root directory using requests"""
    try:
        import requests
    except ImportError:
        print("⚠️ requests module not available, skipping GitHub update")
        return False
    
    print("📥 Downloading latest files from GitHub...")
    
    downloaded = 0
    failed = 0
    
    for filename in GITHUB_FILES:
        url = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/{GITHUB_BRANCH}/{filename}"
        
        try:
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(response.text)
                print(f"  ✅ {filename}")
                downloaded += 1
            else:
                print(f"  ❌ {filename} (HTTP {response.status_code})")
                failed += 1
                
        except Exception as e:
            print(f"  ❌ {filename} ({e})")
            failed += 1
    
    print(f"📦 Downloaded {downloaded} files, {failed} failed")
    return downloaded > 0

def main():
    print()
    print("=" * 50)
    print("  Carnage Report Matchmaking Bot Launcher")
    print("=" * 50)
    print()
    
    # Update from GitHub on startup
    update_from_github()
    
    print()
    print("🚀 Starting bot...")
    
    # Check if HCRBot.py exists
    if not os.path.exists("HCRBot.py"):
        print("❌ HCRBot.py not found!")
        print("Make sure the GitHub repo contains HCRBot.py")
        print("Or manually upload HCRBot.py to your server")
        sys.exit(1)
    
    # Run HCRBot.py (exec replaces this process)
    exec(open("HCRBot.py", encoding='utf-8').read())

if __name__ == "__main__":
    main()
