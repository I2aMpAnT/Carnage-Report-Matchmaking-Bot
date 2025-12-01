"""
One-time fix script to correct Discord IDs for keylord and josiah in rankstats.json
Run this once, then delete this file.
"""

import json
import os
import base64
import urllib.request
import urllib.error

# Load .env file if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# GitHub Configuration
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
GITHUB_REPO = "I2aMpAnT/H2CarnageReport.com"
GITHUB_BRANCH = "main"

# Corrections to make (wrong_id -> correct_id)
ID_CORRECTIONS = {
    "449344331426203546": "652998057087991838",   # TwoDash (2D)
}

def pull_rankstats():
    """Pull rankstats.json from GitHub"""
    raw_url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/rankstats.json"

    try:
        with urllib.request.urlopen(raw_url, timeout=30) as response:
            text = response.read().decode('utf-8')
            return json.loads(text)
    except Exception as e:
        print(f"Failed to pull rankstats: {e}")
        return None

class RedirectHandler(urllib.request.HTTPRedirectHandler):
    """Handler that follows redirects for all HTTP methods including PUT"""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new_req = urllib.request.Request(
            newurl,
            data=req.data,
            headers=dict(req.headers),
            method=req.get_method()
        )
        return new_req

def push_rankstats(data: dict):
    """Push updated rankstats.json to GitHub"""
    if not GITHUB_TOKEN:
        print("ERROR: GITHUB_TOKEN not set!")
        return False

    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/rankstats.json"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Python-Script",
        "Content-Type": "application/json"
    }

    try:
        # Get current SHA
        req = urllib.request.Request(api_url, headers=headers)
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode('utf-8'))
            current_sha = result["sha"]
    except Exception as e:
        print(f"Failed to get SHA: {e}")
        return False

    # Prepare content
    content = json.dumps(data, indent=2)
    content_base64 = base64.b64encode(content.encode('utf-8')).decode('utf-8')

    payload = {
        "message": "Fix Discord IDs for keylord and josiah",
        "content": content_base64,
        "branch": GITHUB_BRANCH,
        "sha": current_sha
    }

    def do_put(url):
        """Perform PUT request, following redirects manually"""
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers=headers,
            method='PUT'
        )
        try:
            with urllib.request.urlopen(req) as response:
                return response.status in [200, 201]
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode('utf-8')
            except:
                pass

            # Check for redirect (307, 308, etc)
            print(f"   DEBUG: HTTP error {e.code}")
            if e.code in [301, 302, 303, 307, 308]:
                print(f"   DEBUG: Is redirect code")
                # First try Location header
                redirect_url = e.headers.get('Location')
                if redirect_url:
                    print(f"   Following redirect (header) to: {redirect_url}")
                    return do_put(redirect_url)
                print(f"   DEBUG: No Location header, checking body")

                # Try to extract redirect URL from response body
                if body:
                    print(f"   DEBUG: Body length: {len(body)}")
                    try:
                        error_data = json.loads(body)
                        print(f"   DEBUG: Parsed JSON, keys: {list(error_data.keys())}")
                        if 'url' in error_data:
                            new_url = error_data['url']
                            print(f"   Following redirect (body) to: {new_url}")
                            return do_put(new_url)
                        else:
                            print(f"   DEBUG: No 'url' key in response")
                    except json.JSONDecodeError as je:
                        print(f"   DEBUG: JSON parse failed: {je}")
                else:
                    print(f"   DEBUG: Body is empty")

            print(f"Failed to push: {e.code} - {body}")
            return False

    try:
        if do_put(api_url):
            print("Successfully pushed to GitHub!")
            return True
    except Exception as e:
        print(f"Failed to push: {e}")
        return False

    return False

def fix_discord_ids():
    """Main function to fix Discord IDs"""
    print("=" * 60)
    print("Discord ID Fix Script")
    print("=" * 60)

    # Pull current data
    print("\n1. Pulling rankstats.json from GitHub...")
    data = pull_rankstats()

    if not data:
        print("Failed to pull data!")
        return False

    print(f"   Found {len(data)} players in rankstats")

    # Apply corrections
    print("\n2. Applying Discord ID corrections...")
    changes_made = []

    for wrong_id, correct_id in ID_CORRECTIONS.items():
        if wrong_id in data:
            player_data = data[wrong_id]
            player_name = player_data.get('discord_name', 'Unknown')

            print(f"\n   Fixing {player_name}:")
            print(f"     Wrong ID:   {wrong_id}")
            print(f"     Correct ID: {correct_id}")
            print(f"     Stats: XP={player_data.get('xp', 0)}, Rank={player_data.get('highest_rank', 1)}")

            # Check if correct ID already exists
            if correct_id in data:
                print(f"     WARNING: Correct ID already exists with data:")
                existing = data[correct_id]
                print(f"              discord_name={existing.get('discord_name')}, XP={existing.get('xp', 0)}")
                print(f"     Merging: keeping higher stats...")

                # Merge - keep higher values
                for key in ['xp', 'wins', 'losses', 'kills', 'deaths', 'assists', 'headshots',
                           'highest_rank', 'rank', 'total_games']:
                    if key in player_data:
                        existing[key] = max(existing.get(key, 0), player_data.get(key, 0))

                # Keep in_game_names from both
                if 'in_game_names' in player_data:
                    existing_names = existing.get('in_game_names', [])
                    for name in player_data['in_game_names']:
                        if name not in existing_names:
                            existing_names.append(name)
                    existing['in_game_names'] = existing_names
            else:
                # Move data to correct ID
                data[correct_id] = player_data

            # Remove old wrong ID
            del data[wrong_id]
            changes_made.append(f"{player_name}: {wrong_id} -> {correct_id}")
            print(f"     DONE!")
        else:
            print(f"\n   ID {wrong_id} not found in data (may already be fixed)")

    if not changes_made:
        print("\n   No changes needed!")
        return True

    # Push updated data
    print("\n3. Pushing fixed data to GitHub...")
    success = push_rankstats(data)

    if success:
        print("\n" + "=" * 60)
        print("SUCCESS! Changes made:")
        for change in changes_made:
            print(f"  - {change}")
        print("=" * 60)

    return success

if __name__ == "__main__":
    fix_discord_ids()
