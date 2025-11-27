# ingame.py - In-Game Series Management and Voting

MODULE_VERSION = "1.1.0"

import discord
from discord.ui import View, Button
from typing import List, Dict, Optional

# Will be imported from bot.py
RED_TEAM_EMOJI_ID = None
BLUE_TEAM_EMOJI_ID = None
ADMIN_ROLES = []
GENERAL_CHANNEL_ID = 1403855176460406805
QUEUE_CHANNEL_ID = None

def log_action(message: str):
    """Log actions"""
    from searchmatchmaking import log_action as queue_log
    queue_log(message)

def format_game_result(game_num: int, winner: str, game_stats: dict) -> str:
    """Format a game result line with map/gametype if available"""
    if winner == 'RED':
        emoji = f"<:redteam:{RED_TEAM_EMOJI_ID}>"
    else:
        emoji = f"<:blueteam:{BLUE_TEAM_EMOJI_ID}>"
    
    # Check if stats exist for this game
    if game_num in game_stats:
        stats = game_stats[game_num]
        map_name = stats.get("map", "")
        gametype = stats.get("gametype", "")
        if map_name and gametype:
            return f"{emoji} Game {game_num} Winner - {map_name} - {gametype}\n"
        elif map_name:
            return f"{emoji} Game {game_num} Winner - {map_name}\n"
        elif gametype:
            return f"{emoji} Game {game_num} Winner - {gametype}\n"
    
    return f"{emoji} Game {game_num} Winner\n"

async def update_general_chat_embed(guild: discord.Guild, series):
    """Send/update match-in-progress embed in general chat with Twitch links and multistream buttons"""
    channel = guild.get_channel(GENERAL_CHANNEL_ID)
    if not channel:
        return
    
    # Import twitch module for links
    try:
        import twitch
        twitch.RED_TEAM_EMOJI_ID = RED_TEAM_EMOJI_ID
        twitch.BLUE_TEAM_EMOJI_ID = BLUE_TEAM_EMOJI_ID
        
        # Build embed with Twitch links
        embed, view = twitch.build_match_embed_with_twitch(series, guild)
    except Exception as e:
        log_action(f"Twitch module error, falling back: {e}")
        # Fallback to basic embed
        embed = discord.Embed(
            title=f"Match In Progress - {series.series_number}",
            description="**Halo 2 MLG 2007 Matchmaking**",
            color=discord.Color.from_rgb(0, 112, 192)
        )
        
        red_mentions = "\n".join([f"<@{uid}>" for uid in series.red_team])
        blue_mentions = "\n".join([f"<@{uid}>" for uid in series.blue_team])
        
        red_wins = series.games.count('RED')
        blue_wins = series.games.count('BLUE')
        
        embed.add_field(
            name=f"<:redteam:{RED_TEAM_EMOJI_ID}> Red Team - {red_wins}", 
            value=red_mentions, 
            inline=True
        )
        embed.add_field(
            name=f"<:blueteam:{BLUE_TEAM_EMOJI_ID}> Blue Team - {blue_wins}", 
            value=blue_mentions, 
            inline=True
        )
        embed.set_footer(text="Match in progress - voting in matchmaking channel")
        view = None
    
    # Check if test mode
    is_test = getattr(series, 'test_mode', False)
    
    # Find existing message or create new one
    if hasattr(series, 'general_message') and series.general_message:
        try:
            if view:
                await series.general_message.edit(embed=embed, view=view)
            else:
                await series.general_message.edit(embed=embed)
            return
        except:
            pass
    
    # Look for existing message
    async for message in channel.history(limit=20):
        if message.author.bot and message.embeds:
            if message.embeds[0].title and "Match In Progress" in message.embeds[0].title:
                try:
                    if view:
                        await message.edit(embed=embed, view=view)
                    else:
                        await message.edit(embed=embed)
                    series.general_message = message
                    return
                except:
                    pass
    
    # Send new message - only ping @here for real matches, not test matches
    if not is_test:
        here_msg = await channel.send("@here")
        try:
            await here_msg.delete()
        except:
            pass
    
    # Send the actual embed with multistream buttons
    if view:
        series.general_message = await channel.send(embed=embed, view=view)
    else:
        series.general_message = await channel.send(embed=embed)

async def delete_general_chat_embed(guild: discord.Guild, series):
    """Delete the match-in-progress embed from general chat"""
    if hasattr(series, 'general_message') and series.general_message:
        try:
            await series.general_message.delete()
        except:
            pass
    
    # Also try to find and delete any orphaned messages
    channel = guild.get_channel(GENERAL_CHANNEL_ID)
    if channel:
        async for message in channel.history(limit=20):
            if message.author.bot and message.embeds:
                if message.embeds[0].title and "Match In Progress" in message.embeds[0].title:
                    try:
                        await message.delete()
                    except:
                        pass

class Series:
    match_counter = 0  # For real matches
    test_counter = 0   # For test matches
    
    def __init__(self, red_team: List[int], blue_team: List[int], test_mode: bool = False, testers: List[int] = None):
        self.test_mode = test_mode
        self.testers = testers or []  # List of user IDs who can vote in test mode
        
        if test_mode:
            Series.test_counter += 1
            self.match_number = Series.test_counter
            self.series_number = f"Test {Series.test_counter}"
        else:
            Series.match_counter += 1
            self.match_number = Series.match_counter
            self.series_number = f"Series {Series.match_counter}"
        
        self.red_team = red_team
        self.blue_team = blue_team
        self.games: List[str] = []
        self.game_stats: Dict[int, dict] = {}  # game_number -> {"map": str, "gametype": str}
        self.votes: Dict[int, str] = {}
        self.current_game = 1
        self.series_message: Optional[discord.Message] = None
        self.end_series_votes: set = set()
        self.red_vc_id: Optional[int] = None
        self.blue_vc_id: Optional[int] = None

class SeriesView(View):
    def __init__(self, series: Series):
        super().__init__(timeout=None)
        self.series = series
        self.game_voters = {}  # user_id -> 'RED' or 'BLUE'
        self.end_voters = set()
        self.update_buttons()
    
    def update_buttons(self):
        self.clear_items()
        
        # Only add current game vote buttons and end series button
        # Past games shown in embed, not as buttons
        
        # Current game vote buttons - stacked vertically
        red_button = Button(
            label=f"Game {self.series.current_game} Winner",
            style=discord.ButtonStyle.danger,
            custom_id=f"vote_red_{self.series.current_game}",
            row=0
        )
        red_button.callback = self.vote_red
        self.add_item(red_button)
        
        blue_button = Button(
            label=f"Game {self.series.current_game} Winner",
            style=discord.ButtonStyle.primary,
            custom_id=f"vote_blue_{self.series.current_game}",
            row=1
        )
        blue_button.callback = self.vote_blue
        self.add_item(blue_button)
        
        # End series button
        end_button = Button(
            label="END SERIES",
            style=discord.ButtonStyle.secondary,
            custom_id="end_series",
            row=2
        )
        end_button.callback = self.vote_end_series
        self.add_item(end_button)
    
    async def vote_red(self, interaction: discord.Interaction):
        await self.process_vote(interaction, 'RED')
    
    async def vote_blue(self, interaction: discord.Interaction):
        await self.process_vote(interaction, 'BLUE')
    
    async def process_vote(self, interaction: discord.Interaction, team: str):
        """Process game winner vote"""
        all_players = self.series.red_team + self.series.blue_team
        total_players = len(all_players)
        
        # Test mode: only testers can vote, need 2 matching votes
        if self.series.test_mode:
            # Check if user is a tester (if testers list exists)
            if self.series.testers and interaction.user.id not in self.series.testers:
                await interaction.response.send_message(
                    "❌ Only testers can vote in test mode!",
                    ephemeral=True
                )
                return
            
            # Allow vote changes - just update the vote
            self.game_voters[interaction.user.id] = team
            self.series.votes[interaction.user.id] = team
            
            await interaction.response.defer()
            await self.update_series_embed(interaction.channel)
            
            # Count tester votes for each team
            red_votes = sum(1 for uid, v in self.game_voters.items() if v == 'RED' and uid in self.series.testers)
            blue_votes = sum(1 for uid, v in self.game_voters.items() if v == 'BLUE' and uid in self.series.testers)
            
            # Need 2 tester votes for same team to win
            if red_votes >= 2:
                from postgame import record_game_winner
                await record_game_winner(self, 'RED', interaction.channel)
            elif blue_votes >= 2:
                from postgame import record_game_winner
                await record_game_winner(self, 'BLUE', interaction.channel)
            return
        
        # Real mode: Check if staff or player
        user_roles = [role.name for role in interaction.user.roles]
        is_staff = any(role in ADMIN_ROLES for role in user_roles)
        
        # Only staff or players can vote
        if not is_staff and interaction.user.id not in all_players:
            await interaction.response.send_message(
                "❌ Only players in the series or Staff can vote!",
                ephemeral=True
            )
            return
        
        # Allow vote changes - just update the vote
        self.game_voters[interaction.user.id] = team
        self.series.votes[interaction.user.id] = team
        
        await interaction.response.defer()
        
        # Count staff votes
        staff_red_votes = 0
        staff_blue_votes = 0
        for uid, v in self.series.votes.items():
            member = interaction.guild.get_member(uid)
            if member:
                member_roles = [role.name for role in member.roles]
                if any(role in ADMIN_ROLES for role in member_roles):
                    if v == 'RED':
                        staff_red_votes += 1
                    else:
                        staff_blue_votes += 1
        
        await self.update_series_embed(interaction.channel)
        
        # Win condition: Just 1 staff vote
        if staff_red_votes >= 1:
            from postgame import record_game_winner
            await record_game_winner(self, 'RED', interaction.channel)
        elif staff_blue_votes >= 1:
            from postgame import record_game_winner
            await record_game_winner(self, 'BLUE', interaction.channel)
    
    async def vote_end_series(self, interaction: discord.Interaction):
        """Process end series vote"""
        all_players = self.series.red_team + self.series.blue_team
        total_players = len(all_players)
        
        # Test mode: only testers can vote, need 2 votes to end
        if self.series.test_mode:
            # Check if user is a tester (if testers list exists)
            if self.series.testers and interaction.user.id not in self.series.testers:
                await interaction.response.send_message(
                    "❌ Only testers can vote in test mode!",
                    ephemeral=True
                )
                return
            
            # Toggle vote - if already voted, remove vote
            if interaction.user.id in self.end_voters:
                self.end_voters.remove(interaction.user.id)
            else:
                self.end_voters.add(interaction.user.id)
            
            await interaction.response.defer()
            await self.update_series_embed(interaction.channel)
            
            # In test mode, need 2 tester votes to end
            tester_end_votes = sum(1 for uid in self.end_voters if uid in self.series.testers)
            if tester_end_votes >= 2:
                from postgame import end_series
                await end_series(self, interaction.channel)
            return
        
        # Real mode
        user_roles = [role.name for role in interaction.user.roles]
        is_staff = any(role in ADMIN_ROLES for role in user_roles)
        
        if not is_staff and interaction.user.id not in all_players:
            await interaction.response.send_message(
                "❌ Only players or Staff can vote!",
                ephemeral=True
            )
            return
        
        # Toggle vote - if already voted, remove vote
        if interaction.user.id in self.end_voters:
            self.end_voters.remove(interaction.user.id)
        else:
            self.end_voters.add(interaction.user.id)
        
        await interaction.response.defer()
        await self.update_series_embed(interaction.channel)
        
        # Count staff votes
        staff_votes = sum(1 for uid in self.end_voters 
                         if any(role in ADMIN_ROLES 
                               for role in interaction.guild.get_member(uid).roles))
        
        # End conditions: 5 total votes OR 2 staff votes
        if len(self.end_voters) >= 5 or staff_votes >= 2:
            from postgame import end_series
            await end_series(self, interaction.channel)
    
    async def update_series_embed(self, channel: discord.TextChannel):
        """Update the series embed"""
        series = self.series
        total_players = len(series.red_team + series.blue_team)
        
        embed = discord.Embed(
            title=f"Match #{series.match_number} in Progress",
            description="**Halo 2 MLG 2007 Matchmaking**",
            color=discord.Color.from_rgb(0, 112, 192)
        )
        
        red_mentions = "\n".join([f"<@{uid}>" for uid in series.red_team])
        blue_mentions = "\n".join([f"<@{uid}>" for uid in series.blue_team])
        
        # Count wins for each team
        red_wins = series.games.count('RED')
        blue_wins = series.games.count('BLUE')
        
        # Set base description
        embed.description = "**Halo 2 MLG 2007 Matchmaking**"
        
        # Add team fields with win counts
        embed.add_field(
            name=f"<:redteam:{RED_TEAM_EMOJI_ID}> Red Team - {red_wins}", 
            value=red_mentions, 
            inline=True
        )
        embed.add_field(
            name=f"<:blueteam:{BLUE_TEAM_EMOJI_ID}> Blue Team - {blue_wins}", 
            value=blue_mentions, 
            inline=True
        )
        
        # Add completed games section if any
        if series.games:
            games_text = ""
            for i, winner in enumerate(series.games, 1):
                games_text += format_game_result(i, winner, series.game_stats)
            
            embed.add_field(
                name="Completed Games",
                value=games_text.strip(),
                inline=False
            )
        
        # Show end series votes
        end_vote_count = len(self.end_voters)
        
        embed.add_field(
            name=f"End Series Votes ({end_vote_count}/{total_players})",
            value=f"{end_vote_count} vote{'s' if end_vote_count != 1 else ''}",
            inline=False
        )
        
        if series.series_message:
            try:
                await series.series_message.edit(embed=embed, view=self)
            except:
                pass
        
        # Also update general chat embed
        try:
            await update_general_chat_embed(channel.guild, series)
        except Exception as e:
            log_action(f"Failed to update general chat embed: {e}")

async def show_series_embed(channel: discord.TextChannel):
    """Show initial series embed - ALWAYS in queue channel"""
    from searchmatchmaking import queue_state
    series = queue_state.current_series
    
    # Always post voting embed to queue channel, regardless of where command was run
    queue_channel = channel.guild.get_channel(QUEUE_CHANNEL_ID)
    target_channel = queue_channel if queue_channel else channel
    
    embed = discord.Embed(
        title=f"Match #{series.match_number} in Progress",
        description="**Halo 2 MLG 2007 Matchmaking**",
        color=discord.Color.from_rgb(0, 112, 192)
    )
    
    red_mentions = "\n".join([f"<@{uid}>" for uid in series.red_team])
    blue_mentions = "\n".join([f"<@{uid}>" for uid in series.blue_team])
    
    # Count wins for each team
    red_wins = series.games.count('RED')
    blue_wins = series.games.count('BLUE')
    
    embed.add_field(
        name=f"<:redteam:{RED_TEAM_EMOJI_ID}> Red Team - {red_wins}", 
        value=red_mentions, 
        inline=True
    )
    embed.add_field(
        name=f"<:blueteam:{BLUE_TEAM_EMOJI_ID}> Blue Team - {blue_wins}", 
        value=blue_mentions, 
        inline=True
    )
    
    # Current game
    embed.add_field(
        name="Current Game",
        value=f"Game {series.current_game}",
        inline=False
    )
    
    # Show completed games if any
    if series.games:
        games_text = ""
        for i, winner in enumerate(series.games, 1):
            games_text += format_game_result(i, winner, series.game_stats)
        
        embed.add_field(
            name="Completed Games",
            value=games_text.strip(),
            inline=False
        )
    
    # End series votes
    embed.add_field(
        name="End Series Votes (0/8)",
        value="0 votes",
        inline=False
    )
    
    view = SeriesView(series)
    series.series_message = await target_channel.send(embed=embed, view=view)
    
    # Also send to general chat (no voting buttons)
    try:
        await update_general_chat_embed(channel.guild, series)
    except Exception as e:
        log_action(f"Failed to send general chat embed: {e}")
