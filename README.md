# Carnage Report Matchmaking Bot

A Discord bot for Halo 2 matchmaking with queue management, team selection, MMR tracking, and Twitch integration.

![Halo 2](https://img.shields.io/badge/Halo%202-Matchmaking-blue)
![Discord.py](https://img.shields.io/badge/discord.py-2.0+-blue)
![Python](https://img.shields.io/badge/python-3.8+-green)

## Features

- 🎮 **8-Player Queue System** - Join/leave matchmaking with visual progress
- ⚔️ **Team Selection Modes** - Balanced MMR, Captains Draft, Players Pick
- 📊 **MMR & Ranking System** - 50 levels with XP progression
- 🏆 **Series Tracking** - Best of 7 with game-by-game voting
- 📺 **Twitch Integration** - Link accounts, multistream buttons
- 🎤 **Voice Channel Management** - Auto-create team VCs, move players
- 💾 **State Persistence** - Survives bot restarts mid-match

## Server Setup

### Files on Your Server (Private - Never Push):
```
├── .env              # Your Discord token
├── bot.py            # Launcher script
```

### Create `.env`:
```
DISCORD_TOKEN=your_bot_token_here
```

### Create `bot.py`:
```python
# bot.py - Launcher (Do not modify)
if __name__ == '__main__':
    import HCRBot
```

### Clone & Install:
```bash
git clone https://github.com/I2aMpAnT/Carnage-Report-Matchmaking-Bot.git
cd Carnage-Report-Matchmaking-Bot
pip install -r requirements.txt
```

### Run:
```bash
python bot.py
```

## Updating the Bot

```bash
git pull
python bot.py
```

## Commands

### Matchmaking
| Command | Description |
|---------|-------------|
| `/queue` | Show current queue status |
| `/ping` | Ping general chat for more players |
| `/resetqueue` | Clear the queue |

### Match Management
| Command | Description |
|---------|-------------|
| `/cancelmatch` | Cancel current match |
| `/cancelcurrent` | Cancel pregame or active match |
| `/swap` | Swap players between teams |
| `/testmatchmaking` | Start a test match |

### Stats & Ranks
| Command | Description |
|---------|-------------|
| `/rank` | Check your rank and stats |
| `/leaderboard` | View top players |
| `/stats` | Detailed statistics |
| `/setmmr` | Set a player's MMR |
| `/refreshranks` | Refresh all player ranks |

### Twitch
| Command | Description |
|---------|-------------|
| `/linktwitch` | Link your Twitch account |
| `/unlinktwitch` | Unlink your Twitch account |
| `/setalias` | Set your in-game alias |

### Privacy
| Command | Description |
|---------|-------------|
| `/hideplayernames` | Show "Matched Player" in queue |
| `/showplayernames` | Show real names in queue |

---

## File Structure

```
├── HCRBot.py              # Main bot entry point & config
├── commands.py            # All slash commands
├── searchmatchmaking.py   # Queue system & embeds
├── pregame.py             # Team selection phase
├── ingame.py              # Active series & voting
├── postgame.py            # Match results & cleanup
├── STATSRANKS.py          # XP, MMR, ranking system
├── twitch.py              # Twitch integration
├── state_manager.py       # State persistence
├── github_webhook.py      # GitHub auto-sync
├── requirements.txt       # Dependencies
├── players.json           # Twitch links & aliases
├── rankstats.json         # Player MMR & stats
├── xp_config.json         # XP & rank configuration
├── queue_config.json      # Queue settings
├── matchhistory.json      # Match history
└── testmatchhistory.json  # Test match history
```

---

*Built for the Halo 2 community by I2aMpAnT GaminG* 🎮
