# bot.py - Launcher that updates from GitHub then runs the bot
# Files are pulled directly into root directory for easy manual editing

import subprocess
import os
import sys

# GitHub repo URL
GITHUB_REPO = "https://github.com/I2aMpAnT/HCR-Bot.git"

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
    """Pull latest files from GitHub into root directory"""
    temp_dir = "/tmp/hcr-bot-repo"
    
    try:
        # Remove old temp directory if exists
        if os.path.exists(temp_dir):
            subprocess.run(["rm", "-rf", temp_dir], check=True)
        
        print("📥 Cloning latest from GitHub...")
        result = subprocess.run(
            ["git", "clone", "--depth", "1", GITHUB_REPO, temp_dir],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"⚠️ Git clone failed: {result.stderr}")
            print("Continuing with existing files...")
            return False
        
        # Copy each file from temp repo to root
        copied = 0
        for filename in GITHUB_FILES:
            src = os.path.join(temp_dir, filename)
            dst = filename  # Current directory (root)
            
            if os.path.exists(src):
                subprocess.run(["cp", src, dst], check=True)
                print(f"  ✅ {filename}")
                copied += 1
            else:
                print(f"  ⚠️ {filename} not found in repo")
        
        # Cleanup temp directory
        subprocess.run(["rm", "-rf", temp_dir], check=True)
        
        print(f"📦 Updated {copied} files from GitHub")
        return True
        
    except Exception as e:
        print(f"⚠️ GitHub update error: {e}")
        print("Continuing with existing files...")
        return False

def main():
    print("=" * 50)
    print("HCR Bot Launcher")
    print("=" * 50)
    
    # Update from GitHub on startup
    update_from_github()
    
    print()
    print("🚀 Starting HCRBot...")
    print("=" * 50)
    
    # Check if HCRBot.py exists
    if not os.path.exists("HCRBot.py"):
        print("❌ HCRBot.py not found!")
        print("Make sure the GitHub repo contains HCRBot.py")
        sys.exit(1)
    
    # Run HCRBot.py (exec replaces this process)
    exec(open("HCRBot.py").read())

if __name__ == "__main__":
    main()
