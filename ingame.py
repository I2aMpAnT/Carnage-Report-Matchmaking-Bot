# ingame.py - In-Game Series Management and Voting

MODULE_VERSION = "1.5.0"

import discord
from discord.ui import View, Button
from typing import List, Dict, Optional

# Will be imported from bot.py
RED_TEAM_EMOJI_ID = None
BLUE_TEAM_EMOJI_ID = None
ADMIN_ROLES = []
GENERAL_CHANNEL_ID = 1403855176460406805
QUEUE_CHANNEL_ID = None

# Header image for embeds
HEADER_IMAGE_URL = "https://raw.githubusercontent.com/I2aMpAnT/H2CarnageReport.com/main/H2CRFinal.png"

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
    
    # Send the actual embed with multistream buttons (no @here ping)
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

    def __init__(self, red_team: List[int], blue_team: List[int], test_mode: bool = False, testers: List[int] = None, pending_match_number: int = None):
        from datetime import datetime

        self.test_mode = test_mode
        self.testers = testers or []  # List of user IDs who can vote in test mode

        if test_mode:
            Series.test_counter += 1
            self.match_number = Series.test_counter
            self.series_number = f"Test {Series.test_counter}"
        else:
            # Use pending match number if provided (roles already assigned), otherwise increment
            if pending_match_number:
                self.match_number = pending_match_number
                # Make sure match_counter is at least this value
                if Series.match_counter < pending_match_number:
                    Series.match_counter = pending_match_number
            else:
                Series.match_counter += 1
                self.match_number = Series.match_counter
            self.series_number = f"Series {self.match_number}"

        self.red_team = red_team
        self.blue_team = blue_team
        self.games: List[str] = []
        self.game_stats: Dict[int, dict] = {}  # game_number -> {"map": str, "gametype": str, "parsed_stats": dict}
        self.votes: Dict[int, str] = {}
        self.current_game = 1
        self.series_message: Optional[discord.Message] = None
        self.end_series_votes: set = set()
        self.red_vc_id: Optional[int] = None
        self.blue_vc_id: Optional[int] = None

        # Time window for stats matching
        self.start_time: datetime = datetime.now()
        self.end_time: Optional[datetime] = None

        # Results message for updating after stats parse
        self.results_message: Optional[discord.Message] = None
        self.results_channel_id: Optional[int] = None

        # Series text channel (created for each match)
        self.text_channel_id: Optional[int] = None

class SeriesView(View):
    def __init__(self, series: Series):
        super().__init__(timeout=None)
        self.series = series
        self.end_voters = set()
        self.update_buttons()

    def update_buttons(self):
        self.clear_items()

        # Only END SERIES button - game winners are determined from parsed stats
        end_button = Button(
            label="END SERIES",
            style=discord.ButtonStyle.secondary,
            custom_id="end_series",
            row=0
        )
        end_button.callback = self.vote_end_series
        self.add_item(end_button)
    
    async def vote_end_series(self, interaction: discord.Interaction):
        """Process end series vote"""
        try:
            all_players = self.series.red_team + self.series.blue_team
            total_players = len(all_players)

            log_action(f"[VOTE] {interaction.user.display_name} clicked End Series button")

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
                    log_action(f"[VOTE] {interaction.user.display_name} removed test vote")
                else:
                    self.end_voters.add(interaction.user.id)
                    log_action(f"[VOTE] {interaction.user.display_name} added test vote")

                await interaction.response.defer()
                await self.update_series_embed(interaction.channel)

                # In test mode, need 2 tester votes to end
                tester_end_votes = sum(1 for uid in self.end_voters if uid in self.series.testers)
                log_action(f"[VOTE] Test mode: {tester_end_votes}/2 tester votes")
                if tester_end_votes >= 2:
                    log_action(f"[VOTE] Test mode threshold met - ending series")
                    from postgame import end_series
                    await end_series(self, interaction.channel)
                return

            # Real mode
            user_roles = [role.name for role in interaction.user.roles]
            is_admin = "Overlord" in user_roles
            is_staff = any(role in ["Staff", "Server Support"] for role in user_roles)
            is_privileged = is_admin or is_staff

            if not is_privileged and interaction.user.id not in all_players:
                await interaction.response.send_message(
                    "❌ Only players or Staff can vote!",
                    ephemeral=True
                )
                return

            # Toggle vote - if already voted, remove vote
            if interaction.user.id in self.end_voters:
                self.end_voters.remove(interaction.user.id)
                log_action(f"[VOTE] {interaction.user.display_name} removed end series vote")
            else:
                self.end_voters.add(interaction.user.id)
                log_action(f"[VOTE] {interaction.user.display_name} added end series vote (admin={is_admin}, staff={is_staff})")

            await interaction.response.defer()
            await self.update_series_embed(interaction.channel)

            # Count privileged votes (admins count as staff too)
            admin_votes = 0
            staff_votes = 0  # This includes admins
            for uid in self.end_voters:
                member = interaction.guild.get_member(uid)
                if member:
                    member_roles = [role.name for role in member.roles]
                    if "Overlord" in member_roles:
                        admin_votes += 1
                        staff_votes += 1  # Admins count towards staff total
                    elif any(role in ["Staff", "Server Support"] for role in member_roles):
                        staff_votes += 1

            # End conditions: majority (5 of 8) OR 2 staff votes (admins count as staff)
            majority_needed = (len(all_players) // 2) + 1
            total_votes = len(self.end_voters)

            log_action(f"[VOTE] Counts: {total_votes} total, {admin_votes} admin, {staff_votes} staff/admin. Need {majority_needed} majority OR 2 staff/admin")

            should_end = False
            end_reason = ""

            if total_votes >= majority_needed:
                should_end = True
                end_reason = f"Majority threshold met ({total_votes}/{majority_needed})"
            elif staff_votes >= 2:
                should_end = True
                end_reason = f"Staff/Admin threshold met ({staff_votes}/2)"

            if should_end:
                log_action(f"[VOTE] {end_reason} - ending series")
                from postgame import end_series
                await end_series(self, interaction.channel)
        except Exception as e:
            log_action(f"[VOTE ERROR] vote_end_series failed: {e}")
            import traceback
            log_action(f"[VOTE ERROR] Traceback: {traceback.format_exc()}")
            try:
                # Try followup first (if already deferred), then response
                try:
                    await interaction.followup.send(f"❌ Error processing vote: {e}", ephemeral=True)
                except:
                    await interaction.response.send_message(f"❌ Error processing vote: {e}", ephemeral=True)
            except:
                pass
    
    async def update_series_embed(self, channel: discord.TextChannel):
        """Update the series embed"""
        series = self.series
        total_players = len(series.red_team + series.blue_team)

        embed = discord.Embed(
            title=f"Match #{series.match_number} in Progress",
            description="**Halo 2 MLG 2007 Matchmaking**\n*Game winners will be determined from parsed stats*",
            color=discord.Color.from_rgb(0, 112, 192)
        )

        red_mentions = "\n".join([f"<@{uid}>" for uid in series.red_team])
        blue_mentions = "\n".join([f"<@{uid}>" for uid in series.blue_team])

        # Count wins for each team (from parsed stats)
        red_wins = series.games.count('RED')
        blue_wins = series.games.count('BLUE')

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

        # Add completed games section if any (populated from parsed stats)
        if series.games:
            games_text = ""
            for i, winner in enumerate(series.games, 1):
                games_text += format_game_result(i, winner, series.game_stats)

            embed.add_field(
                name="Completed Games",
                value=games_text.strip(),
                inline=False
            )

        # Show end series votes (just count, threshold details are logged internally)
        end_vote_count = len(self.end_voters)

        embed.add_field(
            name=f"End Series Votes",
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


async def record_game_to_series(
    guild: discord.Guild,
    winner: str,  # 'RED' or 'BLUE'
    map_name: str = None,
    gametype: str = None,
    game_number: int = None,
    auto_end_threshold: int = None  # e.g., 3 for Bo5 (first to 3 wins)
) -> dict:
    """
    Record a game result to the active series and update all embeds.

    This function is called when a game is logged and linked as ranked.
    It updates:
    - The series games list with the winner
    - The series game_stats with map/gametype info
    - The series embed in the series channel
    - The match-in-progress embed in general chat

    Args:
        guild: Discord guild
        winner: 'RED' or 'BLUE' - which team won
        map_name: Name of the map played (optional)
        gametype: Name of the gametype played (optional)
        game_number: Specific game number (optional, auto-increments if not provided)
        auto_end_threshold: Number of wins to auto-end series (e.g., 3 for Bo5)

    Returns:
        dict with status info: {"success": bool, "message": str, "series_ended": bool}
    """
    from searchmatchmaking import queue_state

    # Check for active series
    if not queue_state.current_series:
        log_action("[GAME] No active series to record game to")
        return {"success": False, "message": "No active series", "series_ended": False}

    series = queue_state.current_series

    # Determine game number
    if game_number is None:
        game_number = len(series.games) + 1

    # Validate winner
    winner = winner.upper()
    if winner not in ['RED', 'BLUE']:
        log_action(f"[GAME] Invalid winner: {winner}")
        return {"success": False, "message": f"Invalid winner: {winner}", "series_ended": False}

    # Add to games list
    series.games.append(winner)

    # Add to game_stats with map/gametype info
    series.game_stats[game_number] = {
        "map": map_name or "",
        "gametype": gametype or "",
    }

    log_action(f"[GAME] Recorded Game {game_number}: {winner} wins on {map_name or 'Unknown'} - {gametype or 'Unknown'}")

    # Update the series embed
    series_channel = None
    if series.text_channel_id:
        series_channel = guild.get_channel(series.text_channel_id)

    if not series_channel:
        series_channel = guild.get_channel(QUEUE_CHANNEL_ID)

    # Find or create the view to update embed
    if series.series_message:
        view = SeriesView(series)
        try:
            await view.update_series_embed(series_channel)
            log_action(f"[GAME] Updated series embed with Game {game_number} result")
        except Exception as e:
            log_action(f"[GAME] Failed to update series embed: {e}")

    # Also update general chat embed
    try:
        await update_general_chat_embed(guild, series)
        log_action(f"[GAME] Updated general chat embed")
    except Exception as e:
        log_action(f"[GAME] Failed to update general chat embed: {e}")

    # Check for auto-end threshold
    red_wins = series.games.count('RED')
    blue_wins = series.games.count('BLUE')
    series_ended = False

    if auto_end_threshold:
        if red_wins >= auto_end_threshold or blue_wins >= auto_end_threshold:
            log_action(f"[GAME] Series reached auto-end threshold ({auto_end_threshold}): Red {red_wins} - Blue {blue_wins}")
            # Import and call end_series
            try:
                from postgame import end_series
                await end_series(series_channel)
                series_ended = True
                log_action(f"[GAME] Series auto-ended")
            except Exception as e:
                log_action(f"[GAME] Failed to auto-end series: {e}")

    return {
        "success": True,
        "message": f"Game {game_number} recorded: {winner} wins",
        "series_ended": series_ended,
        "red_wins": red_wins,
        "blue_wins": blue_wins
    }


async def get_active_series_info(guild: discord.Guild) -> dict:
    """
    Get information about the currently active series.

    Returns:
        dict with series info or None if no active series
    """
    from searchmatchmaking import queue_state

    if not queue_state.current_series:
        return None

    series = queue_state.current_series

    return {
        "match_number": series.match_number,
        "series_number": series.series_number,
        "test_mode": series.test_mode,
        "red_team": series.red_team,
        "blue_team": series.blue_team,
        "games": series.games,
        "game_stats": series.game_stats,
        "red_wins": series.games.count('RED'),
        "blue_wins": series.games.count('BLUE'),
        "start_time": series.start_time.isoformat() if series.start_time else None,
        "text_channel_id": series.text_channel_id,
    }


async def show_series_embed(channel: discord.TextChannel):
    """Show initial series embed - in series text channel if available, otherwise queue channel"""
    from searchmatchmaking import queue_state
    series = queue_state.current_series

    # Use series text channel if available, otherwise fall back to queue channel
    if series.text_channel_id:
        target_channel = channel.guild.get_channel(series.text_channel_id)
        if not target_channel:
            # Fallback to queue channel if series channel not found
            queue_channel = channel.guild.get_channel(QUEUE_CHANNEL_ID)
            target_channel = queue_channel if queue_channel else channel
    else:
        # No series text channel, use queue channel
        queue_channel = channel.guild.get_channel(QUEUE_CHANNEL_ID)
        target_channel = queue_channel if queue_channel else channel

    total_players = len(series.red_team + series.blue_team)

    embed = discord.Embed(
        title=f"Match #{series.match_number} in Progress",
        description="**Halo 2 MLG 2007 Matchmaking**\n*Game winners will be determined from parsed stats*",
        color=discord.Color.from_rgb(0, 112, 192)
    )

    red_mentions = "\n".join([f"<@{uid}>" for uid in series.red_team])
    blue_mentions = "\n".join([f"<@{uid}>" for uid in series.blue_team])

    embed.add_field(
        name=f"<:redteam:{RED_TEAM_EMOJI_ID}> Red Team - 0",
        value=red_mentions,
        inline=True
    )
    embed.add_field(
        name=f"<:blueteam:{BLUE_TEAM_EMOJI_ID}> Blue Team - 0",
        value=blue_mentions,
        inline=True
    )

    # End series votes (just count, threshold details are logged internally)
    embed.add_field(
        name=f"End Series Votes",
        value=f"0 votes",
        inline=False
    )

    view = SeriesView(series)
    series.series_message = await target_channel.send(embed=embed, view=view)

    # Ping the match role (separate from embed)
    match_number = series.match_number if hasattr(series, 'match_number') else 1
    match_role_name = f"ActiveMLG4v4Match{match_number}"
    match_role = discord.utils.get(channel.guild.roles, name=match_role_name)
    if match_role:
        await target_channel.send(match_role.mention)

    # Also send to general chat (no buttons)
    try:
        await update_general_chat_embed(channel.guild, series)
    except Exception as e:
        log_action(f"Failed to send general chat embed: {e}")
