# pregame.py - Pregame Lobby and Team Selection
# !! REMEMBER TO UPDATE VERSION NUMBER WHEN MAKING CHANGES !!

MODULE_VERSION = "1.2.1"

import discord
from discord.ui import View, Button, Select
from typing import List
import random

# Will be imported from bot.py
PREGAME_LOBBY_ID = None
RED_TEAM_EMOJI_ID = None
BLUE_TEAM_EMOJI_ID = None

def log_action(message: str):
    """Log actions"""
    from searchmatchmaking import log_action as queue_log
    queue_log(message)

async def get_player_mmr(user_id: int) -> int:
    """Get player MMR from STATSRANKS or guest data"""
    from searchmatchmaking import queue_state
    
    # Check if this is a guest
    if user_id in queue_state.guests:
        mmr = queue_state.guests[user_id]["mmr"]
        log_action(f"get_player_mmr({user_id}) = {mmr} (guest)")
        return mmr
    
    import STATSRANKS
    stats = STATSRANKS.get_player_stats(user_id, skip_github=True)
    if stats and 'mmr' in stats:
        mmr = stats['mmr']
        log_action(f"get_player_mmr({user_id}) = {mmr}")
        return mmr
    log_action(f"get_player_mmr({user_id}) = 1500 (default)")
    return 1500  # Default MMR

async def start_pregame(channel: discord.TextChannel, test_mode: bool = False, test_players: List[int] = None):
    """Start pregame phase"""
    from searchmatchmaking import queue_state, get_queue_progress_image, QUEUE_CHANNEL_ID
    import asyncio
    
    log_action(f"Starting pregame phase (test_mode={test_mode})")

    # Reset ping cooldown so players can ping again for new matches
    queue_state.last_ping_time = None
    log_action("Reset ping cooldown for new match")

    # Use test players if provided, otherwise use queue
    players = test_players if test_players else queue_state.queue[:]
    
    # Store test mode info
    queue_state.test_mode = test_mode
    
    guild = channel.guild
    
    # Always use queue channel for pregame embed
    queue_channel = guild.get_channel(QUEUE_CHANNEL_ID)
    target_channel = queue_channel if queue_channel else channel
    
    # Get the next match number for naming
    from ingame import Series
    if test_mode:
        next_num = Series.test_counter + 1
        match_label = f"Test Match {next_num}"
    else:
        next_num = Series.match_counter + 1
        match_label = f"Match {next_num}"
    
    # Create a temporary Pregame Lobby voice channel (no emoji)
    voice_category_id = 1403916181554860112  # Voice Channels category
    category = guild.get_channel(voice_category_id)
    
    pregame_vc = await guild.create_voice_channel(
        name=f"Pregame Lobby - {match_label}",
        category=category,
        user_limit=10
    )
    log_action(f"Created Pregame Lobby VC: {pregame_vc.id}")
    
    # Store the pregame VC ID for cleanup later
    queue_state.pregame_vc_id = pregame_vc.id
    
    # Move players to pregame lobby
    # In TEST MODE: Only move the 2 testers, not the random fillers
    # In REAL MODE: Move all players who are in voice
    players_in_voice = []
    players_not_in_voice = []
    
    # Get testers list for test mode
    testers = getattr(queue_state, 'testers', []) if test_mode else []
    
    for user_id in players:
        member = guild.get_member(user_id)
        if member:
            # In test mode, only move testers (not random fillers)
            if test_mode and user_id not in testers:
                # This is a filler in test mode - don't try to move them
                players_not_in_voice.append(user_id)
                continue
            
            if member.voice and member.voice.channel and member.voice.channel.guild.id == guild.id:
                try:
                    await member.move_to(pregame_vc)
                    players_in_voice.append(user_id)
                    log_action(f"Moved {member.name} to Pregame Lobby")
                except Exception as e:
                    log_action(f"Failed to move {user_id} to pregame: {e}")
                    players_not_in_voice.append(user_id)
            else:
                players_not_in_voice.append(user_id)
    
    # Show waiting embed - team selection appears once all players join voice
    embed = discord.Embed(
        title=f"Pregame Lobby - {match_label}",
        description="⏳ **Waiting for all players to join the Pregame Lobby voice channel...**\n\nTeam selection will begin once everyone is in voice!",
        color=discord.Color.gold()
    )

    # Add 8/8 image
    embed.set_image(url=get_queue_progress_image(8))

    # Show player count
    player_count = f"{len(players)}/8 players"
    if test_mode:
        player_count += " (TEST MODE)"

    player_list = "\n".join([f"<@{uid}>" for uid in players])
    embed.add_field(name=f"Players ({player_count})", value=player_list, inline=False)

    # Show who's in voice and who's not
    if players_in_voice:
        in_voice_list = ", ".join([f"<@{uid}>" for uid in players_in_voice])
        embed.add_field(name="✅ In Pregame Lobby", value=in_voice_list, inline=False)

    if players_not_in_voice and not test_mode:
        not_in_voice_list = ", ".join([f"<@{uid}>" for uid in players_not_in_voice])
        embed.add_field(
            name="⚠️ Not in Voice - 5 minutes to join!",
            value=f"{not_in_voice_list}\nJoin the Pregame Lobby or be replaced!",
            inline=False
        )
    elif players_not_in_voice and test_mode:
        # In test mode, only show warning for testers not in voice (not fillers)
        testers_not_in_voice = [uid for uid in players_not_in_voice if uid in testers]
        if testers_not_in_voice:
            not_in_voice_list = ", ".join([f"<@{uid}>" for uid in testers_not_in_voice])
            embed.add_field(
                name="⚠️ Testers Not in Voice",
                value=f"{not_in_voice_list}\nPlease join the Pregame Lobby!",
                inline=False
            )

    # Send waiting embed (no buttons yet)
    pregame_message = await target_channel.send(embed=embed)
    queue_state.pregame_message = pregame_message

    # Start task to wait for all players and then show team selection
    asyncio.create_task(wait_for_players_and_show_selection(
        target_channel, pregame_message, players, pregame_vc.id,
        test_mode=test_mode, testers=testers, match_label=match_label
    ))


async def wait_for_players_and_show_selection(
    channel: discord.TextChannel,
    pregame_message: discord.Message,
    players: List[int],
    pregame_vc_id: int,
    test_mode: bool = False,
    testers: List[int] = None,
    match_label: str = "Match"
):
    """Wait for all players to join pregame VC, then show team selection"""
    import asyncio
    from searchmatchmaking import queue_state, get_queue_progress_image

    guild = channel.guild
    testers = testers or []
    timeout_seconds = 300  # 5 minutes

    # In test mode, only wait for testers (not filler players)
    players_to_wait_for = [uid for uid in players if uid in testers] if test_mode else players[:]

    start_time = asyncio.get_event_loop().time()

    while True:
        # Check if pregame was cancelled
        if not hasattr(queue_state, 'pregame_vc_id') or queue_state.pregame_vc_id != pregame_vc_id:
            return  # Pregame was cancelled

        pregame_vc = guild.get_channel(pregame_vc_id)
        if not pregame_vc:
            return  # VC was deleted

        # Check who's in voice now
        members_in_vc = [m.id for m in pregame_vc.members if not m.bot]
        players_in_voice = [uid for uid in players_to_wait_for if uid in members_in_vc]
        players_not_in_voice = [uid for uid in players_to_wait_for if uid not in members_in_vc]

        elapsed = asyncio.get_event_loop().time() - start_time
        time_remaining = max(0, timeout_seconds - int(elapsed))
        minutes_left = time_remaining // 60
        seconds_left = time_remaining % 60

        # Update embed to show current status
        embed = discord.Embed(
            title=f"Pregame Lobby - {match_label}",
            description="⏳ **Waiting for all players to join the Pregame Lobby voice channel...**\n\nTeam selection will begin once everyone is in voice!",
            color=discord.Color.gold()
        )
        embed.set_image(url=get_queue_progress_image(8))

        player_count = f"{len(players)}/8 players"
        if test_mode:
            player_count += " (TEST MODE)"
        player_list = "\n".join([f"<@{uid}>" for uid in players])
        embed.add_field(name=f"Players ({player_count})", value=player_list, inline=False)

        if players_in_voice:
            in_voice_list = ", ".join([f"<@{uid}>" for uid in players_in_voice])
            embed.add_field(name=f"✅ In Pregame Lobby ({len(players_in_voice)}/{len(players_to_wait_for)})", value=in_voice_list, inline=False)

        if players_not_in_voice:
            not_in_voice_list = ", ".join([f"<@{uid}>" for uid in players_not_in_voice])
            embed.add_field(
                name=f"⚠️ Not in Voice - {minutes_left}m {seconds_left}s remaining!",
                value=f"{not_in_voice_list}\nJoin the Pregame Lobby or be replaced!",
                inline=False
            )

        try:
            await pregame_message.edit(embed=embed)
        except:
            pass

        # Check if all players are in voice
        if len(players_not_in_voice) == 0:
            log_action(f"All players in pregame voice - showing team selection")
            await show_team_selection(channel, pregame_message, players, pregame_vc_id, test_mode, testers, match_label)
            return

        # Check timeout
        if elapsed >= timeout_seconds:
            log_action(f"Pregame timeout - {len(players_not_in_voice)} players missing")
            # Handle no-shows: replace with people from pregame VC or proceed anyway
            await handle_pregame_timeout(channel, pregame_message, players, players_not_in_voice, pregame_vc_id, test_mode, testers, match_label)
            return

        # Wait 5 seconds before checking again
        await asyncio.sleep(5)


async def show_team_selection(
    channel: discord.TextChannel,
    pregame_message: discord.Message,
    players: List[int],
    pregame_vc_id: int,
    test_mode: bool,
    testers: List[int],
    match_label: str
):
    """Show team selection buttons once all players are in voice"""
    from searchmatchmaking import queue_state, get_queue_progress_image

    embed = discord.Embed(
        title=f"Pregame Lobby - {match_label}",
        description="✅ **All players are in voice!**\n\nSelect your preferred team selection method:",
        color=discord.Color.green()
    )
    embed.set_image(url=get_queue_progress_image(8))

    player_count = f"{len(players)}/8 players"
    if test_mode:
        player_count += " (TEST MODE - Both testers must vote same)"
    player_list = "\n".join([f"<@{uid}>" for uid in players])
    embed.add_field(name=f"Players ({player_count})", value=player_list, inline=False)

    view = TeamSelectionView(players, test_mode=test_mode, testers=testers, pregame_vc_id=pregame_vc_id, match_label=match_label)
    view.pregame_message = pregame_message
    queue_state.pregame_message = pregame_message

    try:
        await pregame_message.edit(embed=embed, view=view)
    except:
        # If edit fails, send new message
        new_message = await channel.send(embed=embed, view=view)
        view.pregame_message = new_message
        queue_state.pregame_message = new_message


async def handle_pregame_timeout(
    channel: discord.TextChannel,
    pregame_message: discord.Message,
    players: List[int],
    no_show_players: List[int],
    pregame_vc_id: int,
    test_mode: bool,
    testers: List[int],
    match_label: str
):
    """Handle timeout - replace no-shows if possible, then proceed to team selection"""
    from searchmatchmaking import queue_state, get_queue_progress_image

    guild = channel.guild
    pregame_vc = guild.get_channel(pregame_vc_id)

    if not pregame_vc:
        return

    # Find replacement players from the pregame VC who weren't in the original 8
    current_vc_members = [m.id for m in pregame_vc.members if not m.bot]
    original_players = set(players)
    potential_replacements = [uid for uid in current_vc_members if uid not in original_players]

    replacements_made = []
    updated_players = players[:]

    for no_show_id in no_show_players:
        if potential_replacements:
            replacement_id = potential_replacements.pop(0)

            # Replace in player list
            idx = updated_players.index(no_show_id)
            updated_players[idx] = replacement_id

            no_show_member = guild.get_member(no_show_id)
            replacement_member = guild.get_member(replacement_id)

            no_show_name = no_show_member.display_name if no_show_member else str(no_show_id)
            replacement_name = replacement_member.display_name if replacement_member else str(replacement_id)

            replacements_made.append(f"<@{no_show_id}> → <@{replacement_id}>")
            log_action(f"Replaced no-show {no_show_name} with {replacement_name}")

    # Show team selection with updated player list
    embed = discord.Embed(
        title=f"Pregame Lobby - {match_label}",
        description="⏰ **Time's up!** Proceeding to team selection.\n\nSelect your preferred team selection method:",
        color=discord.Color.orange()
    )
    embed.set_image(url=get_queue_progress_image(8))

    player_count = f"{len(updated_players)}/8 players"
    if test_mode:
        player_count += " (TEST MODE)"
    player_list = "\n".join([f"<@{uid}>" for uid in updated_players])
    embed.add_field(name=f"Players ({player_count})", value=player_list, inline=False)

    if replacements_made:
        embed.add_field(name="🔄 Replacements Made", value="\n".join(replacements_made), inline=False)

    remaining_no_shows = [uid for uid in no_show_players if uid in updated_players]
    if remaining_no_shows:
        embed.add_field(
            name="⚠️ Still Missing (no replacements available)",
            value=", ".join([f"<@{uid}>" for uid in remaining_no_shows]),
            inline=False
        )

    view = TeamSelectionView(updated_players, test_mode=test_mode, testers=testers, pregame_vc_id=pregame_vc_id, match_label=match_label)
    view.pregame_message = pregame_message
    queue_state.pregame_message = pregame_message

    try:
        await pregame_message.edit(embed=embed, view=view)
    except:
        new_message = await channel.send(embed=embed, view=view)
        view.pregame_message = new_message
        queue_state.pregame_message = new_message


async def check_no_shows(channel: discord.TextChannel, view, no_show_players: List[int], pregame_vc_id: int, timeout_seconds: int):
    """Check for no-show players after timeout and replace them with players from pregame VC"""
    import asyncio
    from searchmatchmaking import queue_state
    
    await asyncio.sleep(timeout_seconds)
    
    # Check if pregame is still active (not already finalized)
    if not hasattr(queue_state, 'pregame_vc_id') or queue_state.pregame_vc_id != pregame_vc_id:
        return  # Pregame already ended
    
    guild = channel.guild
    pregame_vc = guild.get_channel(pregame_vc_id)
    
    if not pregame_vc:
        return  # VC was deleted
    
    # Check which players still haven't joined
    actual_no_shows = []
    for user_id in no_show_players:
        member = guild.get_member(user_id)
        if member:
            # Check if they're in the pregame VC now
            if not member.voice or member.voice.channel != pregame_vc:
                actual_no_shows.append(user_id)
    
    if not actual_no_shows:
        return  # Everyone showed up
    
    # Find replacement players from the pregame VC who weren't in the original 8
    current_vc_members = [m.id for m in pregame_vc.members if not m.bot]
    original_players = set(view.players)
    potential_replacements = [uid for uid in current_vc_members if uid not in original_players]
    
    replacements_made = []
    
    for no_show_id in actual_no_shows:
        if potential_replacements:
            replacement_id = potential_replacements.pop(0)
            
            # Replace in view.players
            idx = view.players.index(no_show_id)
            view.players[idx] = replacement_id
            
            no_show_member = guild.get_member(no_show_id)
            replacement_member = guild.get_member(replacement_id)
            
            no_show_name = no_show_member.display_name if no_show_member else str(no_show_id)
            replacement_name = replacement_member.display_name if replacement_member else str(replacement_id)
            
            replacements_made.append(f"<@{no_show_id}> → <@{replacement_id}>")
            log_action(f"Replaced no-show {no_show_name} with {replacement_name}")
    
    if replacements_made:
        # Update the embed
        embed = discord.Embed(
            title="⚔️ Pregame Lobby",
            description="Select your preferred team selection method:",
            color=discord.Color.gold()
        )
        
        player_list = "\n".join([f"<@{uid}>" for uid in view.players])
        embed.add_field(name=f"Players ({len(view.players)}/8 players)", value=player_list, inline=False)
        
        embed.add_field(
            name="🔄 Replacements Made",
            value="\n".join(replacements_made),
            inline=False
        )
        
        try:
            await view.pregame_message.edit(embed=embed, view=view)
        except:
            pass
        
        await channel.send(f"⚠️ **No-show replacements:** {', '.join(replacements_made)}")


class TeamSelectionView(View):
    def __init__(self, players: List[int], test_mode: bool = False, testers: List[int] = None, pregame_vc_id: int = None, match_label: str = "Match"):
        super().__init__(timeout=None)
        self.players = players
        self.test_mode = test_mode
        self.testers = testers or []
        self.votes = {}  # user_id -> method voted for
        self.pregame_message = None  # Will be set after sending
        self.pregame_vc_id = pregame_vc_id
        self.match_label = match_label
    
    @discord.ui.button(label="Balanced (MMR)", style=discord.ButtonStyle.primary, custom_id="balanced")
    async def balanced(self, interaction: discord.Interaction, button: Button):
        await self.handle_vote(interaction, "balanced")
    
    @discord.ui.button(label="Captains Pick", style=discord.ButtonStyle.secondary, custom_id="captains")
    async def captains(self, interaction: discord.Interaction, button: Button):
        await self.handle_vote(interaction, "captains")
    
    @discord.ui.button(label="Players Pick", style=discord.ButtonStyle.success, custom_id="players_pick")
    async def players_pick(self, interaction: discord.Interaction, button: Button):
        await self.handle_vote(interaction, "players_pick")
    
    async def update_embed_with_votes(self, interaction: discord.Interaction, votes_mismatch: bool = False):
        """Update the embed to show current votes"""
        from searchmatchmaking import get_queue_progress_image
        
        embed = discord.Embed(
            title=f"Pregame Lobby - {self.match_label}",
            description="Select your preferred team selection method:",
            color=discord.Color.gold()
        )
        
        embed.set_image(url=get_queue_progress_image(8))
        
        player_count = f"{len(self.players)}/8 players"
        if self.test_mode:
            player_count += " (TEST MODE)"
        
        player_list = "\n".join([f"<@{uid}>" for uid in self.players])
        embed.add_field(name=f"Players ({player_count})", value=player_list, inline=False)
        
        # Show votes
        if self.votes:
            vote_text = "\n".join([f"<@{uid}>: **{vote}**" for uid, vote in self.votes.items()])
            if votes_mismatch:
                embed.add_field(name=f"⚠️ Votes Don't Match ({len(self.votes)}/{len(self.testers)})", value=vote_text + "\n\n*Change your vote to match!*", inline=False)
            else:
                embed.add_field(name=f"Votes ({len(self.votes)}/{len(self.testers)})", value=vote_text, inline=False)
        
        try:
            await self.pregame_message.edit(embed=embed, view=self)
        except:
            pass
    
    async def handle_vote(self, interaction: discord.Interaction, method: str):
        """Handle team selection vote"""
        from searchmatchmaking import queue_state
        
        # In test mode, only testers can vote and both must agree
        if self.test_mode and self.testers:
            if interaction.user.id not in self.testers:
                await interaction.response.send_message("❌ Only testers can vote!", ephemeral=True)
                return
            
            # Record/update vote (allows changing vote)
            self.votes[interaction.user.id] = method
            
            # Check if all testers voted
            if len(self.votes) < len(self.testers):
                # Not all testers have voted yet - update embed to show votes
                await interaction.response.defer()
                await self.update_embed_with_votes(interaction)
                return
            
            # All testers voted - check if they agree
            vote_values = list(self.votes.values())
            if len(set(vote_values)) > 1:
                # Testers voted for different methods - just update embed, don't reset
                # They can change their votes until they match
                await interaction.response.defer()
                await self.update_embed_with_votes(interaction, votes_mismatch=True)
                return
            
            # All testers agree - proceed
            await interaction.response.defer()
        else:
            # Normal mode - any player can pick immediately
            await interaction.response.defer()
        
        # Delete the pregame embed
        try:
            if self.pregame_message:
                await self.pregame_message.delete()
            elif hasattr(queue_state, 'pregame_message') and queue_state.pregame_message:
                await queue_state.pregame_message.delete()
                queue_state.pregame_message = None
        except:
            pass
        
        # Execute the selected method
        if method == "balanced":
            await self.create_balanced_teams(interaction)
        elif method == "captains":
            await self.start_captains_draft(interaction)
        elif method == "players_pick":
            await self.start_players_pick(interaction)
    
    async def create_balanced_teams(self, interaction: discord.Interaction):
        """Create balanced teams using MMR - keeps guests with their hosts"""
        from searchmatchmaking import queue_state
        
        # Get all MMRs
        player_mmrs = {}
        for user_id in self.players:
            # Check if this is a guest - use their set MMR
            if user_id in queue_state.guests:
                player_mmrs[user_id] = queue_state.guests[user_id]["mmr"]
            else:
                player_mmrs[user_id] = await get_player_mmr(user_id)
        
        # Identify host-guest pairs (treat as single unit for balancing)
        pairs = []  # [(host_id, guest_id, combined_mmr)]
        paired_players = set()
        
        for guest_id, guest_info in queue_state.guests.items():
            if guest_id in self.players:
                host_id = guest_info["host_id"]
                if host_id in self.players:
                    combined_mmr = player_mmrs[host_id] + player_mmrs[guest_id]
                    pairs.append((host_id, guest_id, combined_mmr))
                    paired_players.add(host_id)
                    paired_players.add(guest_id)
        
        # Get solo players (not in a pair)
        solo_players = [uid for uid in self.players if uid not in paired_players]
        
        # Create items to balance: pairs count as single unit, solos are individual
        balance_items = []
        for host_id, guest_id, combined_mmr in pairs:
            balance_items.append({
                "type": "pair",
                "ids": [host_id, guest_id],
                "mmr": combined_mmr
            })
        for uid in solo_players:
            balance_items.append({
                "type": "solo",
                "ids": [uid],
                "mmr": player_mmrs[uid]
            })
        
        # Sort by MMR (high to low)
        balance_items.sort(key=lambda x: x["mmr"], reverse=True)
        
        # Snake draft for balance items
        red_items = []
        blue_items = []
        
        for i, item in enumerate(balance_items):
            if i % 2 == 0:
                red_items.append(item)
            else:
                blue_items.append(item)
        
        # Flatten to team lists
        red_team = []
        blue_team = []
        for item in red_items:
            red_team.extend(item["ids"])
        for item in blue_items:
            blue_team.extend(item["ids"])
        
        # Calculate current diff
        red_mmr = sum(player_mmrs[uid] for uid in red_team)
        blue_mmr = sum(player_mmrs[uid] for uid in blue_team)
        best_diff = abs(red_mmr - blue_mmr)
        best_red = red_team[:]
        best_blue = blue_team[:]
        
        # Try swapping solo players only (never break up pairs)
        red_solos = [uid for uid in red_team if uid not in paired_players]
        blue_solos = [uid for uid in blue_team if uid not in paired_players]
        
        for r_uid in red_solos:
            for b_uid in blue_solos:
                test_red = red_team[:]
                test_blue = blue_team[:]
                
                # Swap
                r_idx = test_red.index(r_uid)
                b_idx = test_blue.index(b_uid)
                test_red[r_idx] = b_uid
                test_blue[b_idx] = r_uid
                
                diff = abs(sum(player_mmrs[uid] for uid in test_red) - sum(player_mmrs[uid] for uid in test_blue))
                
                if diff < best_diff:
                    best_diff = diff
                    best_red = test_red[:]
                    best_blue = test_blue[:]
        
        # Also try swapping pairs between teams if there are multiple pairs
        if len(pairs) >= 2:
            red_pairs = [(h, g) for h, g, _ in pairs if h in best_red]
            blue_pairs = [(h, g) for h, g, _ in pairs if h in best_blue]
            
            for rp in red_pairs:
                for bp in blue_pairs:
                    test_red = best_red[:]
                    test_blue = best_blue[:]
                    
                    # Remove red pair from red, add to blue
                    test_red.remove(rp[0])
                    test_red.remove(rp[1])
                    test_blue.append(rp[0])
                    test_blue.append(rp[1])
                    
                    # Remove blue pair from blue, add to red
                    test_blue.remove(bp[0])
                    test_blue.remove(bp[1])
                    test_red.append(bp[0])
                    test_red.append(bp[1])
                    
                    diff = abs(sum(player_mmrs[uid] for uid in test_red) - sum(player_mmrs[uid] for uid in test_blue))
                    
                    if diff < best_diff:
                        best_diff = diff
                        best_red = test_red[:]
                        best_blue = test_blue[:]
        
        log_action(f"Balanced teams created - MMR diff: {best_diff}")
        await finalize_teams(interaction.channel, best_red, best_blue, test_mode=self.test_mode)
    
    async def start_captains_draft(self, interaction: discord.Interaction):
        """Start captain draft"""
        # Pick 2 random captains
        captains = random.sample(self.players, 2)
        remaining = [p for p in self.players if p not in captains]
        
        embed = discord.Embed(
            title="Captains Draft",
            description="Captains will pick their teams!",
            color=discord.Color.purple()
        )
        
        embed.add_field(name=f"<:redteam:{RED_TEAM_EMOJI_ID}> Captain 1 (Red)", value=f"<@{captains[0]}>", inline=True)
        embed.add_field(name=f"<:blueteam:{BLUE_TEAM_EMOJI_ID}> Captain 2 (Blue)", value=f"<@{captains[1]}>", inline=True)
        
        view = CaptainDraftView(captains, remaining, test_mode=self.test_mode)
        await interaction.followup.send(embed=embed, view=view)
    
    async def start_players_pick(self, interaction: discord.Interaction):
        """Start players pick teams"""
        embed = discord.Embed(
            title="Players Pick Teams",
            description="Click a button to join a team!",
            color=discord.Color.green()
        )
        
        view = PlayersPickView(self.players, test_mode=self.test_mode)
        await interaction.followup.send(embed=embed, view=view)


class CaptainDraftView(View):
    def __init__(self, captains: List[int], remaining: List[int], test_mode: bool = False):
        super().__init__(timeout=None)
        self.captain1 = captains[0]
        self.captain2 = captains[1]
        self.remaining = remaining
        self.red_team = [self.captain1]
        self.blue_team = [self.captain2]
        self.current_picker = self.captain1
        self.test_mode = test_mode
        
        # Add player selection dropdown
        self.update_dropdown()
    
    def update_dropdown(self):
        """Update player selection dropdown"""
        self.clear_items()
        
        if not self.remaining:
            # Draft complete
            return
        
        options = [
            discord.SelectOption(label=f"Player {i+1}", value=str(uid))
            for i, uid in enumerate(self.remaining)
        ]
        
        select = Select(
            placeholder=f"Captain <@{self.current_picker}> - Pick a player",
            options=options,
            custom_id="pick_player"
        )
        select.callback = self.pick_player
        self.add_item(select)
    
    async def pick_player(self, interaction: discord.Interaction):
        """Handle player pick"""
        if interaction.user.id != self.current_picker:
            await interaction.response.send_message("❌ Not your turn!", ephemeral=True)
            return
        
        selected_id = int(interaction.values[0])
        
        # Add to current team
        if self.current_picker == self.captain1:
            self.red_team.append(selected_id)
            self.current_picker = self.captain2
        else:
            self.blue_team.append(selected_id)
            self.current_picker = self.captain1
        
        self.remaining.remove(selected_id)
        
        if not self.remaining:
            # Draft complete
            await interaction.response.send_message("✅ Draft complete! Finalizing teams...")
            await finalize_teams(interaction.channel, self.red_team, self.blue_team, test_mode=self.test_mode)
        else:
            self.update_dropdown()
            await interaction.response.edit_message(view=self)


class PlayersPickView(View):
    def __init__(self, players: List[int], test_mode: bool = False):
        super().__init__(timeout=None)
        self.players = players
        self.red_team = []
        self.blue_team = []
        self.votes = {}  # user_id -> 'RED' or 'BLUE'
        self.test_mode = test_mode
    
    @discord.ui.button(label="Red Team", style=discord.ButtonStyle.danger, custom_id="pick_red")
    async def pick_red(self, interaction: discord.Interaction, button: Button):
        await self.handle_pick(interaction, 'RED')
    
    @discord.ui.button(label="Blue Team", style=discord.ButtonStyle.primary, custom_id="pick_blue")
    async def pick_blue(self, interaction: discord.Interaction, button: Button):
        await self.handle_pick(interaction, 'BLUE')
    
    async def handle_pick(self, interaction: discord.Interaction, team: str):
        """Handle team pick"""
        if interaction.user.id not in self.players:
            await interaction.response.send_message("❌ You're not in this match!", ephemeral=True)
            return
        
        if interaction.user.id in self.votes:
            await interaction.response.send_message("❌ You already picked a team!", ephemeral=True)
            return
        
        self.votes[interaction.user.id] = team
        
        if team == 'RED':
            self.red_team.append(interaction.user.id)
        else:
            self.blue_team.append(interaction.user.id)
        
        await interaction.response.send_message(f"✅ You joined {team} team!", ephemeral=True)
        
        # Check if all players voted
        if len(self.votes) == len(self.players):
            await self.finalize_vote(interaction)
    
    async def finalize_vote(self, interaction: discord.Interaction):
        """Finalize after all votes"""
        # Balance teams if uneven
        if len(self.red_team) != 4 or len(self.blue_team) != 4:
            await interaction.channel.send("❌ Teams must be 4v4! Please re-pick.")
            return
        
        await finalize_teams(interaction.channel, self.red_team, self.blue_team, test_mode=self.test_mode)


async def finalize_teams(channel: discord.TextChannel, red_team: List[int], blue_team: List[int], test_mode: bool = False, testers: List[int] = None):
    """Finalize teams, create voice channels with MMR, and start series"""
    log_action(f"Finalizing teams - Red: {red_team}, Blue: {blue_team}, Test: {test_mode}")
    
    from searchmatchmaking import queue_state
    queue_state.test_mode = test_mode
    
    # Use testers from parameter or from queue_state
    if testers is None and hasattr(queue_state, 'testers'):
        testers = queue_state.testers
    
    guild = channel.guild
    
    # Calculate average MMR for each team
    red_mmrs = []
    blue_mmrs = []
    for user_id in red_team:
        mmr = await get_player_mmr(user_id)
        red_mmrs.append(mmr)
        log_action(f"Red team player {user_id} MMR: {mmr}")
    for user_id in blue_team:
        mmr = await get_player_mmr(user_id)
        blue_mmrs.append(mmr)
        log_action(f"Blue team player {user_id} MMR: {mmr}")
    
    red_avg_mmr = int(sum(red_mmrs) / len(red_mmrs)) if red_mmrs else 1500
    blue_avg_mmr = int(sum(blue_mmrs) / len(blue_mmrs)) if blue_mmrs else 1500
    log_action(f"Team averages - Red: {red_avg_mmr}, Blue: {blue_avg_mmr}")
    
    # Create series first to get the series number
    from ingame import Series, show_series_embed
    from searchmatchmaking import queue_state
    
    temp_series = Series(red_team, blue_team, test_mode, testers=testers)
    series_label = temp_series.series_number  # "Series 1" or "Test 1"
    
    # Get the Voice Channels category (not the Matchmaking category)
    voice_category_id = 1403916181554860112
    category = guild.get_channel(voice_category_id)
    
    # Create Red Team voice channel with team emoji (red circle) and series number
    red_vc_name = f"🔴 Red {series_label} - {red_avg_mmr} MMR"
    red_vc = await guild.create_voice_channel(
        name=red_vc_name,
        category=category,
        user_limit=None,
        position=999  # Position at bottom
    )
    
    # Create Blue Team voice channel with team emoji (blue circle) and series number
    blue_vc_name = f"🔵 Blue {series_label} - {blue_avg_mmr} MMR"
    blue_vc = await guild.create_voice_channel(
        name=blue_vc_name,
        category=category,
        user_limit=None,
        position=999  # Position at bottom
    )
    
    # Set permissions: Non-players can connect and speak (can self-mute/unmute)
    # Team members get explicit speak permission
    everyone_role = guild.default_role
    await red_vc.set_permissions(everyone_role,
                                   connect=True,
                                   speak=True,  # Allow spectators to unmute themselves
                                   mute_members=False,
                                   use_voice_activation=True)
    await blue_vc.set_permissions(everyone_role,
                                    connect=True,
                                    speak=True,  # Allow spectators to unmute themselves
                                    mute_members=False,
                                    use_voice_activation=True)

    # Give team members explicit speak permissions (ensures they can always talk)
    for user_id in red_team:
        member = guild.get_member(user_id)
        if member:
            await red_vc.set_permissions(member, speak=True, mute_members=False)

    for user_id in blue_team:
        member = guild.get_member(user_id)
        if member:
            await blue_vc.set_permissions(member, speak=True, mute_members=False)
    
    # Move players from pregame (or any voice channel) to their team channels
    # In test mode, only move testers (they're the only real players in voice)
    # In real mode, move all players who are in voice
    if test_mode and testers:
        # Only move testers in test mode
        for user_id in red_team:
            if user_id in testers:
                member = guild.get_member(user_id)
                if member and member.voice and member.voice.channel:
                    try:
                        await member.move_to(red_vc)
                        log_action(f"Moved tester {member.name} to Red VC")
                    except Exception as e:
                        log_action(f"Failed to move tester {user_id} to red VC: {e}")
        
        for user_id in blue_team:
            if user_id in testers:
                member = guild.get_member(user_id)
                if member and member.voice and member.voice.channel:
                    try:
                        await member.move_to(blue_vc)
                        log_action(f"Moved tester {member.name} to Blue VC")
                    except Exception as e:
                        log_action(f"Failed to move tester {user_id} to blue VC: {e}")
    else:
        # Real mode - move all players in voice
        for user_id in red_team:
            member = guild.get_member(user_id)
            if member and member.voice and member.voice.channel:
                try:
                    await member.move_to(red_vc)
                    log_action(f"Moved {member.name} to Red VC")
                except Exception as e:
                    log_action(f"Failed to move {user_id} to red VC: {e}")

        for user_id in blue_team:
            member = guild.get_member(user_id)
            if member and member.voice and member.voice.channel:
                try:
                    await member.move_to(blue_vc)
                    log_action(f"Moved {member.name} to Blue VC")
                except Exception as e:
                    log_action(f"Failed to move {user_id} to blue VC: {e}")
    
    # NOW delete the pregame VC (after players have been moved)
    if hasattr(queue_state, 'pregame_vc_id') and queue_state.pregame_vc_id:
        pregame_vc = guild.get_channel(queue_state.pregame_vc_id)
        if pregame_vc:
            try:
                await pregame_vc.delete()
                log_action("Deleted Pregame Lobby VC")
            except:
                pass
        queue_state.pregame_vc_id = None
    
    # Assign the series we created earlier and set VC IDs
    queue_state.current_series = temp_series
    queue_state.current_series.red_vc_id = red_vc.id
    queue_state.current_series.blue_vc_id = blue_vc.id
    
    # Remove SearchingMatchmaking role from all players (only for real matches)
    if not test_mode:
        try:
            searching_role = discord.utils.get(guild.roles, name="SearchingMatchmaking")
            if searching_role:
                all_players = red_team + blue_team
                for user_id in all_players:
                    member = guild.get_member(user_id)
                    if member:
                        try:
                            await member.remove_roles(searching_role)
                        except:
                            pass
                log_action("Removed SearchingMatchmaking role from all players")
        except Exception as e:
            log_action(f"Failed to remove SearchingMatchmaking roles: {e}")
        
        # Clear queue since match is starting (only for real matches)
        queue_state.queue.clear()
        queue_state.queue_join_times.clear()
    
    await show_series_embed(channel)
    
    # Save state
    try:
        import state_manager
        state_manager.save_state()
    except:
        pass
