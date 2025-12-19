# pregame.py - Pregame Lobby and Team Selection
# !! REMEMBER TO UPDATE VERSION NUMBER WHEN MAKING CHANGES !!
# Supports ALL playlists: MLG 4v4 (voting), Team Hardcore/Double Team (auto-balance), Head to Head (1v1)

MODULE_VERSION = "1.6.9"

import discord
from discord.ui import View, Button, Select
from typing import List, Optional, TYPE_CHECKING
import random
import json

if TYPE_CHECKING:
    from playlists import PlaylistQueueState, PlaylistMatch

# Will be imported from bot.py
PREGAME_LOBBY_ID = None
RED_TEAM_EMOJI_ID = None
BLUE_TEAM_EMOJI_ID = None

# Header image for DMs
HEADER_IMAGE_URL = "https://raw.githubusercontent.com/I2aMpAnT/H2CarnageReport.com/main/MessagefromCarnageReportHEADERSMALL.png"

def log_action(message: str):
    """Log actions"""
    from searchmatchmaking import log_action as queue_log
    queue_log(message)

async def get_player_mmr(user_id: int) -> int:
    """Get player MMR from STATSRANKS or guest data. Returns 500 for unranked players."""
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
    log_action(f"get_player_mmr({user_id}) = 500 (unranked default)")
    return 500  # Default MMR for unranked players


def get_player_rank(user_id: int) -> int:
    """Get player rank (level) from STATSRANKS. Returns 1 for unranked players."""
    import STATSRANKS
    stats = STATSRANKS.get_player_stats(user_id, skip_github=True)
    if stats and 'rank' in stats:
        return stats['rank']
    return 1  # Default rank for unranked players


def get_rank_emoji(guild: discord.Guild, level: int) -> str:
    """Get the custom rank emoji for a level"""
    if guild:
        emoji_name = str(level)
        emoji = discord.utils.get(guild.emojis, name=emoji_name)
        if emoji:
            return str(emoji)
        # Try underscore version for single digits
        if level <= 9:
            emoji = discord.utils.get(guild.emojis, name=f"{level}_")
            if emoji:
                return str(emoji)
    return f"Lv{level}"

async def start_pregame(channel: discord.TextChannel, test_mode: bool = False, test_players: List[int] = None,
                        playlist_state: 'PlaylistQueueState' = None, playlist_players: List[int] = None,
                        mlg_queue_state=None):
    """Start pregame phase for any playlist

    Args:
        channel: The channel to post embeds to
        test_mode: If True, this is a test match (MLG 4v4 only)
        test_players: List of player IDs for test mode (MLG 4v4 only)
        playlist_state: PlaylistQueueState object (for non-MLG playlists)
        playlist_players: List of player IDs (for non-MLG playlists)
        mlg_queue_state: QueueState object for MLG 4v4 (if None, uses default queue_state)
    """
    import asyncio

    guild = channel.guild
    voice_category_id = 1403916181554860112  # Voice Channels category
    category = guild.get_channel(voice_category_id)

    # Determine if this is a playlist match or MLG 4v4
    is_playlist_match = playlist_state is not None

    if is_playlist_match:
        # Playlist-specific pregame (Team Hardcore, Double Team, Head to Head)
        from playlists import get_queue_progress_image, PlaylistType

        ps = playlist_state
        players = playlist_players or []
        max_players = ps.max_players
        playlist_name = ps.name

        # Get projected match number based on completed matches in completed file
        from playlists import get_playlist_completed_file
        import os
        completed_file = get_playlist_completed_file(ps.playlist_type)
        completed_count = 0
        if os.path.exists(completed_file):
            try:
                with open(completed_file, 'r') as f:
                    completed_data = json.load(f)
                completed_count = len(completed_data.get("matches", []))
            except:
                pass
        match_number = completed_count + 1
        match_label = f"{playlist_name} #{match_number}"

        log_action(f"Starting {playlist_name} pregame phase with {len(players)} players")

        # Determine team selection mode
        # MLG 4v4: voting (Balanced, Captains, Players Pick)
        # Team Hardcore/Double Team: auto_balance (skip voting)
        # Head to Head: no teams (1v1)
        # Tournament: players_pick_only (skip voting, go straight to players pick)
        auto_balance = ps.auto_balance
        is_1v1 = ps.playlist_type == PlaylistType.HEAD_TO_HEAD
        players_pick_only = ps.config.get("players_pick_only", False)

        # Create pregame lobby VC
        pregame_vc = await guild.create_voice_channel(
            name=f"{playlist_name} Pregame Lobby",
            category=category,
            user_limit=max_players + 2
        )
        log_action(f"Created {playlist_name} Pregame Lobby VC: {pregame_vc.id}")

        # Move players already in voice to pregame lobby
        players_in_voice = []
        players_not_in_voice = []
        for uid in players:
            member = guild.get_member(uid)
            if member and member.voice and member.voice.channel and member.voice.channel.guild.id == guild.id:
                try:
                    await member.move_to(pregame_vc)
                    players_in_voice.append(uid)
                    log_action(f"Moved {member.name} to {playlist_name} Pregame Lobby")
                except Exception as e:
                    log_action(f"Failed to move {uid} to pregame: {e}")
                    players_not_in_voice.append(uid)
            else:
                players_not_in_voice.append(uid)

        # Show waiting embed
        embed = discord.Embed(
            title=f"{match_label} - Pregame Lobby",
            description=f"**{playlist_name}**\n\nWaiting for all players to join the pregame voice channel...",
            color=discord.Color.gold()
        )
        embed.set_image(url=get_queue_progress_image(len(players), max_players))

        player_list = "\n".join([f"<@{uid}>" for uid in players])
        embed.add_field(name=f"Players ({len(players)}/{max_players})", value=player_list, inline=False)

        if players_in_voice:
            in_voice_list = ", ".join([f"<@{uid}>" for uid in players_in_voice])
            embed.add_field(name=f"In Pregame Lobby ({len(players_in_voice)}/{len(players)})", value=in_voice_list, inline=False)

        if players_not_in_voice:
            not_in_voice_list = ", ".join([f"<@{uid}>" for uid in players_not_in_voice])
            embed.add_field(
                name="Not in Voice - 10 minutes to join!",
                value=f"{not_in_voice_list}\nJoin the Pregame Lobby or match is cancelled!",
                inline=False
            )

        # Ping players
        pings = " ".join([f"<@{uid}>" for uid in players])
        pregame_message = await channel.send(content=pings, embed=embed)

        # DM players not in voice to let them know to join
        for uid in players_not_in_voice:
            member = guild.get_member(uid)
            if member:
                try:
                    dm_embed = discord.Embed(
                        title=f"{match_label} - Join Pregame Lobby!",
                        description=f"Your **{playlist_name}** match is starting! Please join the **Pregame Lobby** voice channel within 10 minutes or the match may be cancelled.",
                        color=discord.Color.gold()
                    )
                    dm_embed.set_image(url=HEADER_IMAGE_URL)
                    await member.send(embed=dm_embed)
                    log_action(f"Sent pregame DM to {member.name}")
                except discord.Forbidden:
                    log_action(f"Could not DM {member.name} - DMs disabled")
                except Exception as e:
                    log_action(f"Error sending pregame DM to {member.name}: {e}")

        # Start task to wait for all players
        asyncio.create_task(wait_for_playlist_players(
            channel, pregame_message, players, pregame_vc.id,
            playlist_state=ps, match_number=match_number, match_label=match_label,
            auto_balance=auto_balance, is_1v1=is_1v1, players_pick_only=players_pick_only
        ))
        return

    # Original MLG 4v4 flow
    from searchmatchmaking import queue_state as default_queue_state, get_queue_progress_image, QUEUE_CHANNEL_ID, QUEUE_CHANNEL_ID_2

    # Use provided queue state or default
    qs = mlg_queue_state if mlg_queue_state else default_queue_state

    log_action(f"Starting MLG 4v4 pregame phase (test_mode={test_mode})")

    # Reset ping cooldown so players can ping again for new matches
    qs.last_ping_time = None
    log_action("Reset ping cooldown for new match")

    # Use test players if provided, otherwise use locked_players (set by searchmatchmaking when queue fills)
    players = test_players if test_players else qs.locked_players[:]

    # Verify we have players
    if not players:
        log_action("ERROR: No players found for pregame! Check queue/locked_players.")
        return

    # Lock these players into the match - they cannot leave
    if not test_mode:
        qs.locked = True
        # locked_players already set by searchmatchmaking.py when queue fills
        log_action(f"Pregame starting with {len(players)} locked players")

    # Store test mode info
    qs.test_mode = test_mode

    # Determine the correct queue channel
    from searchmatchmaking import queue_state_2, update_queue_embed
    if qs == queue_state_2:
        queue_channel_id = QUEUE_CHANNEL_ID_2
    else:
        queue_channel_id = QUEUE_CHANNEL_ID

    # Get queue channel for updating
    queue_channel = guild.get_channel(queue_channel_id)

    # Update the queue embed to show it's ready for new players
    if queue_channel:
        await update_queue_embed(queue_channel, qs)
        log_action("Updated queue embed - ready for new players")

    # Get the next match number for naming
    from ingame import Series
    if test_mode:
        next_num = Series.test_counter + 1
        match_label = f"Test Match {next_num}"
    else:
        next_num = Series.match_counter + 1
        match_label = f"Match {next_num}"

    # Create series text channel early - will be renamed with MMRs when teams are set
    text_category_id = 1403916181554860112  # Matchmaking category
    text_category = guild.get_channel(text_category_id)

    # Determine series label for channel name
    from ingame import Series as SeriesClass
    if test_mode:
        series_num = SeriesClass.test_counter + 1
        series_label = f"test-{series_num}"
    else:
        series_num = SeriesClass.match_counter + 1
        series_label = f"series-{series_num}"

    series_text_channel = await guild.create_text_channel(
        name=f"{series_label}-team-selection",
        category=text_category,
        topic=f"Team selection and match channel - {match_label}",
        position=998  # Position at bottom of category, just above voice channels
    )
    log_action(f"Created Series Text Channel: {series_text_channel.id}")

    # Store the series text channel ID for later use
    qs.series_text_channel_id = series_text_channel.id

    pregame_vc = await guild.create_voice_channel(
        name=f"Pregame Lobby - {match_label}",
        category=category,
        user_limit=10
    )
    log_action(f"Created Pregame Lobby VC: {pregame_vc.id}")

    # Store the pregame VC ID for cleanup later
    qs.pregame_vc_id = pregame_vc.id

    # Use series text channel for all team selection
    target_channel = series_text_channel

    # Move players to pregame lobby
    # In TEST MODE: Only move the 2 testers, not the random fillers
    # In REAL MODE: Move all players who are in voice
    players_in_voice = []
    players_not_in_voice = []

    # Get testers list for test mode
    testers = getattr(qs, 'testers', []) if test_mode else []

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
        description="Waiting for all players to join the Pregame Lobby voice channel...\n\nTeam selection will begin once everyone is in voice!",
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
        embed.add_field(name="In Pregame Lobby", value=in_voice_list, inline=False)

    if players_not_in_voice and not test_mode:
        not_in_voice_list = ", ".join([f"<@{uid}>" for uid in players_not_in_voice])
        embed.add_field(
            name="Not in Voice - 10 minutes to join!",
            value=f"{not_in_voice_list}\nJoin the Pregame Lobby or be replaced!",
            inline=False
        )
    elif players_not_in_voice and test_mode:
        # In test mode, only show warning for testers not in voice (not fillers)
        testers_not_in_voice = [uid for uid in players_not_in_voice if uid in testers]
        if testers_not_in_voice:
            not_in_voice_list = ", ".join([f"<@{uid}>" for uid in testers_not_in_voice])
            embed.add_field(
                name="Testers Not in Voice",
                value=f"{not_in_voice_list}\nPlease join the Pregame Lobby!",
                inline=False
            )

    # Ping players in channel
    pings = " ".join([f"<@{uid}>" for uid in players])
    pregame_message = await target_channel.send(content=pings, embed=embed)
    qs.pregame_message = pregame_message

    # DM players not in voice to let them know to join
    for uid in players_not_in_voice:
        member = guild.get_member(uid)
        if member:
            try:
                dm_embed = discord.Embed(
                    title=f"{match_label} - Join Pregame Lobby!",
                    description=f"Your match is starting! Please join the **Pregame Lobby** voice channel within 10 minutes or the match will be cancelled.",
                    color=discord.Color.gold()
                )
                dm_embed.set_image(url=HEADER_IMAGE_URL)
                await member.send(embed=dm_embed)
                log_action(f"Sent pregame DM to {member.name}")
            except discord.Forbidden:
                log_action(f"Could not DM {member.name} - DMs disabled")
            except Exception as e:
                log_action(f"Error sending pregame DM to {member.name}: {e}")

    # Start task to wait for all players and then show team selection
    asyncio.create_task(wait_for_players_and_show_selection(
        target_channel, pregame_message, players, pregame_vc.id,
        test_mode=test_mode, testers=testers, match_label=match_label,
        mlg_queue_state=qs
    ))


async def wait_for_players_and_show_selection(
    channel: discord.TextChannel,
    pregame_message: discord.Message,
    players: List[int],
    pregame_vc_id: int,
    test_mode: bool = False,
    testers: List[int] = None,
    match_label: str = "Match",
    mlg_queue_state=None
):
    """Wait for all players to join pregame VC, then show team selection"""
    import asyncio
    from searchmatchmaking import queue_state as default_queue_state, get_queue_progress_image

    # Use provided queue state or default
    qs = mlg_queue_state if mlg_queue_state else default_queue_state

    guild = channel.guild
    testers = testers or []
    timeout_seconds = 600  # 10 minutes
    warning_sent = False  # Track if 5-minute warning has been sent

    # In test mode, only wait for testers (not filler players)
    players_to_wait_for = [uid for uid in players if uid in testers] if test_mode else players[:]

    start_time = asyncio.get_event_loop().time()

    while True:
        # Check if pregame was cancelled
        if not hasattr(qs, 'pregame_vc_id') or qs.pregame_vc_id != pregame_vc_id:
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

        # Send 5-minute warning DM and channel ping at halfway point
        if elapsed >= 300 and not warning_sent and players_not_in_voice:
            warning_sent = True
            # Ping in channel
            missing_pings = " ".join([f"<@{uid}>" for uid in players_not_in_voice])
            await channel.send(f"⚠️ **5 MINUTES REMAINING!** {missing_pings} - Join the Pregame Lobby NOW or the match will be cancelled!")
            # DM each missing player
            for uid in players_not_in_voice:
                member = guild.get_member(uid)
                if member:
                    try:
                        warning_embed = discord.Embed(
                            title=f"⚠️ {match_label} - 5 Minutes Remaining!",
                            description=f"You have **5 minutes** to join the **Pregame Lobby** voice channel or the match will be **cancelled**!",
                            color=discord.Color.red()
                        )
                        warning_embed.set_image(url=HEADER_IMAGE_URL)
                        await member.send(embed=warning_embed)
                        log_action(f"Sent 5-minute warning DM to {member.name}")
                    except discord.Forbidden:
                        log_action(f"Could not DM {member.name} - DMs disabled")
                    except Exception as e:
                        log_action(f"Error sending warning DM to {member.name}: {e}")

        # Check timeout
        if elapsed >= timeout_seconds:
            log_action(f"Pregame timeout - {len(players_not_in_voice)} players missing")
            # Handle no-shows: cancel match and return players to postgame
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
    """Handle timeout - cancel match and return players to postgame lobby if not all players showed up"""
    from searchmatchmaking import queue_state, create_queue_embed, QUEUE_CHANNEL_ID

    guild = channel.guild
    pregame_vc = guild.get_channel(pregame_vc_id)

    # Get the postgame lobby VC
    POSTGAME_CARNAGE_REPORT_ID = 1424845826362048643
    postgame_vc = guild.get_channel(POSTGAME_CARNAGE_REPORT_ID)

    # Move all members from pregame VC to postgame (including spectators)
    if pregame_vc and postgame_vc:
        for member in list(pregame_vc.members):
            try:
                await member.move_to(postgame_vc)
                log_action(f"Moved {member.name} to Postgame Carnage Report (no-show cancellation)")
            except Exception as e:
                log_action(f"Failed to move {member.name} to postgame: {e}")

    # Also move members from red/blue team VCs if they exist (including spectators/listeners)
    series = queue_state.current_series if hasattr(queue_state, 'current_series') else None
    if series and postgame_vc:
        # Red team VC
        red_vc_id = getattr(series, 'red_vc_id', None)
        if red_vc_id:
            red_vc = guild.get_channel(red_vc_id)
            if red_vc:
                for member in list(red_vc.members):
                    try:
                        await member.move_to(postgame_vc)
                        log_action(f"Moved {member.name} from Red VC to Postgame (cancellation)")
                    except Exception as e:
                        log_action(f"Failed to move {member.name} from Red VC: {e}")
                try:
                    await red_vc.delete(reason="Match cancelled")
                    log_action(f"Deleted Red team VC for {match_label}")
                except Exception as e:
                    log_action(f"Failed to delete Red VC: {e}")

        # Blue team VC
        blue_vc_id = getattr(series, 'blue_vc_id', None)
        if blue_vc_id:
            blue_vc = guild.get_channel(blue_vc_id)
            if blue_vc:
                for member in list(blue_vc.members):
                    try:
                        await member.move_to(postgame_vc)
                        log_action(f"Moved {member.name} from Blue VC to Postgame (cancellation)")
                    except Exception as e:
                        log_action(f"Failed to move {member.name} from Blue VC: {e}")
                try:
                    await blue_vc.delete(reason="Match cancelled")
                    log_action(f"Deleted Blue team VC for {match_label}")
                except Exception as e:
                    log_action(f"Failed to delete Blue VC: {e}")

    # Delete the pregame VC
    if pregame_vc:
        try:
            await pregame_vc.delete(reason="Match cancelled - not all players showed up")
            log_action(f"Deleted pregame VC for {match_label}")
        except Exception as e:
            log_action(f"Failed to delete pregame VC: {e}")

    # Build the cancellation embed showing who no-showed
    no_show_mentions = ", ".join([f"<@{uid}>" for uid in no_show_players])
    players_who_showed = [uid for uid in players if uid not in no_show_players]
    showed_mentions = ", ".join([f"<@{uid}>" for uid in players_who_showed]) if players_who_showed else "None"

    embed = discord.Embed(
        title=f"❌ {match_label} - Cancelled",
        description="**Match cancelled - not all players joined the pregame lobby in time.**\n\nAll players have been returned to the Postgame Carnage Report lobby.",
        color=discord.Color.red()
    )
    embed.add_field(name="⚠️ No-Shows", value=no_show_mentions, inline=False)
    embed.add_field(name="✅ Players Who Showed Up", value=showed_mentions, inline=False)

    # Post cancellation to queue channel (not the series channel we're about to delete)
    queue_channel = guild.get_channel(QUEUE_CHANNEL_ID)
    if queue_channel:
        all_player_pings = " ".join([f"<@{uid}>" for uid in players])
        await queue_channel.send(content=all_player_pings, embed=embed)

    log_action(f"{match_label} cancelled due to no-shows: {[guild.get_member(uid).display_name if guild.get_member(uid) else str(uid) for uid in no_show_players]}")

    # Delete the series text channel
    series_channel_id = getattr(queue_state, 'series_text_channel_id', None)
    if series_channel_id:
        series_channel = guild.get_channel(series_channel_id)
        if series_channel:
            try:
                await series_channel.delete(reason="Match cancelled - not all players showed up")
                log_action(f"Deleted series text channel for {match_label}")
            except Exception as e:
                log_action(f"Failed to delete series text channel: {e}")

    # Reset queue state
    queue_state.locked = False
    queue_state.locked_players.clear()
    queue_state.pregame_vc_id = None
    queue_state.pregame_message = None
    queue_state.series_text_channel_id = None
    queue_state.test_mode = False

    # Recreate the queue embed in the queue channel
    if queue_channel:
        await create_queue_embed(queue_channel)


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
            description=f"Select your preferred team selection method:",
            color=discord.Color.gold()
        )

        embed.set_image(url=get_queue_progress_image(8))

        player_count = f"{len(self.players)}/8 players"
        if self.test_mode:
            player_count += " (TEST MODE)"

        player_list = "\n".join([f"<@{uid}>" for uid in self.players])
        embed.add_field(name=f"Players ({player_count})", value=player_list, inline=False)

        # Show votes with counts - ALL votes count toward majority (players + staff + admins)
        if self.votes:
            # Count ALL votes per option
            vote_counts = {}
            for vote in self.votes.values():
                vote_counts[vote] = vote_counts.get(vote, 0) + 1

            # Format vote summary (just show counts, threshold logged internally)
            option_labels = {"balanced": "Balanced (MMR)", "captains": "Captains Pick", "players_pick": "Players Pick"}
            vote_summary = []
            for option in ["balanced", "captains", "players_pick"]:
                count = vote_counts.get(option, 0)
                if count > 0:
                    label = option_labels.get(option, option)
                    vote_summary.append(f"**{label}**: {count}")

            # Individual votes
            vote_text = "\n".join([f"<@{uid}>: {vote}" for uid, vote in self.votes.items()])

            if self.test_mode and votes_mismatch:
                embed.add_field(name=f"⚠️ Votes Don't Match", value=vote_text + "\n\n*Change your vote to match!*", inline=False)
            else:
                embed.add_field(name=f"Votes", value="\n".join(vote_summary) if vote_summary else "No votes yet", inline=False)

        try:
            await self.pregame_message.edit(embed=embed, view=self)
        except:
            pass
    
    async def handle_vote(self, interaction: discord.Interaction, method: str):
        """Handle team selection vote - requires majority (5+ of 8) OR 2 staff OR 2 admin"""
        from searchmatchmaking import queue_state

        # Define roles
        ADMIN_ROLES = ["Overlord"]
        STAFF_ROLES = ["Staff", "Server Support"]

        # Check user roles
        user_roles = [role.name for role in interaction.user.roles]
        is_admin = any(role in ADMIN_ROLES for role in user_roles)
        is_staff = any(role in STAFF_ROLES for role in user_roles)

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
            # Normal mode - players, staff, and admins can vote
            # Admins can ALWAYS vote (even if not in match)
            # Players in match can vote
            # Staff can vote
            can_vote = (interaction.user.id in self.players) or is_admin or is_staff

            if not can_vote:
                await interaction.response.send_message("❌ Only players in this match, staff, or admins can vote!", ephemeral=True)
                return

            # Initialize vote tracking if needed
            if not hasattr(self, 'admin_votes'):
                self.admin_votes = {}  # admin_id -> method
            if not hasattr(self, 'staff_votes'):
                self.staff_votes = {}  # staff_id -> method

            # Record vote in appropriate category
            if is_admin:
                self.admin_votes[interaction.user.id] = method
            elif is_staff:
                self.staff_votes[interaction.user.id] = method

            # Always record in main votes too
            self.votes[interaction.user.id] = method
            await interaction.response.defer()

            # Check win conditions:
            # 1. 2 admins agree on same method
            # 2. 2 staff agree on same method
            # 3. Majority of players (5+ of 8)

            winning_method = None

            # Check admin votes (2 admins agreeing wins)
            admin_vote_counts = {}
            for vote in self.admin_votes.values():
                admin_vote_counts[vote] = admin_vote_counts.get(vote, 0) + 1
            for option, count in admin_vote_counts.items():
                if count >= 2:
                    winning_method = option
                    log_action(f"Team selection decided by 2 admins: {option}")
                    break

            # Check staff votes (2 staff agreeing wins)
            if not winning_method:
                staff_vote_counts = {}
                for vote in self.staff_votes.values():
                    staff_vote_counts[vote] = staff_vote_counts.get(vote, 0) + 1
                for option, count in staff_vote_counts.items():
                    if count >= 2:
                        winning_method = option
                        log_action(f"Team selection decided by 2 staff: {option}")
                        break

            # Check majority (5+ votes) - count ALL votes (players + staff + admins)
            # So 4 players + 1 staff = 5 votes = majority
            if not winning_method:
                vote_counts = {}
                for vote in self.votes.values():
                    vote_counts[vote] = vote_counts.get(vote, 0) + 1

                majority_needed = (len(self.players) // 2) + 1  # 5 for 8 players
                for option, count in vote_counts.items():
                    if count >= majority_needed:
                        winning_method = option
                        log_action(f"Team selection decided by majority: {option} ({count}/{majority_needed} votes)")
                        break

            if not winning_method:
                # No winner yet - update embed to show votes
                await self.update_embed_with_votes(interaction)
                return

            # Found winner - use the winning method
            method = winning_method

        # Execute the selected method - edit existing embed instead of posting new ones
        if method == "balanced":
            await self.create_balanced_teams(interaction)
        elif method == "captains":
            await self.start_captains_draft(interaction)
        elif method == "players_pick":
            await self.start_players_pick(interaction)
    
    async def create_balanced_teams(self, interaction: discord.Interaction):
        """Create balanced teams using MMR - keeps guests with their hosts via exhaustive search"""
        from searchmatchmaking import queue_state
        from itertools import combinations

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

        # Create balance items: pairs count as single unit, solos are individual
        balance_items = []
        for host_id, guest_id, combined_mmr in pairs:
            balance_items.append({
                "type": "pair",
                "ids": [host_id, guest_id],
                "mmr": combined_mmr,
                "count": 2  # Takes 2 team slots
            })
        for uid in solo_players:
            balance_items.append({
                "type": "solo",
                "ids": [uid],
                "mmr": player_mmrs[uid],
                "count": 1  # Takes 1 team slot
            })

        # Exhaustive search: try all valid team combinations
        # A valid combination has exactly 4 players on each team
        # Pairs must stay together (both on same team)
        best_diff = float('inf')
        best_red = []
        best_blue = []
        combinations_checked = 0

        def try_all_assignments(items, red_items, blue_items, red_count, blue_count):
            """Recursively try all valid assignments of items to teams"""
            nonlocal best_diff, best_red, best_blue, combinations_checked

            # Base case: all items assigned
            if not items:
                if red_count == 4 and blue_count == 4:
                    combinations_checked += 1
                    # Calculate teams
                    red_team = []
                    blue_team = []
                    for item in red_items:
                        red_team.extend(item["ids"])
                    for item in blue_items:
                        blue_team.extend(item["ids"])

                    red_mmr = sum(player_mmrs[uid] for uid in red_team)
                    blue_mmr = sum(player_mmrs[uid] for uid in blue_team)
                    diff = abs(red_mmr - blue_mmr)

                    if diff < best_diff:
                        best_diff = diff
                        best_red = red_team[:]
                        best_blue = blue_team[:]
                return

            # Get next item to assign
            item = items[0]
            remaining = items[1:]
            item_count = item["count"]

            # Try adding to red team (if room)
            if red_count + item_count <= 4:
                try_all_assignments(remaining, red_items + [item], blue_items,
                                    red_count + item_count, blue_count)

            # Try adding to blue team (if room)
            if blue_count + item_count <= 4:
                try_all_assignments(remaining, red_items, blue_items + [item],
                                    red_count, blue_count + item_count)

        # Run exhaustive search
        try_all_assignments(balance_items, [], [], 0, 0)

        # Sort teams so higher MMR team is red (for consistency)
        if best_red and best_blue:
            red_avg = sum(player_mmrs[uid] for uid in best_red) / len(best_red)
            blue_avg = sum(player_mmrs[uid] for uid in best_blue) / len(best_blue)
            if blue_avg > red_avg:
                best_red, best_blue = best_blue, best_red

        log_action(f"Balanced teams created - MMR diff: {best_diff} (checked {combinations_checked} valid combinations)")

        # Show balanced teams for 10-second confirmation
        # If majority doesn't vote NO, teams proceed automatically
        await show_balanced_teams_confirmation(
            interaction.channel, best_red, best_blue, player_mmrs,
            self.players, self.test_mode, self.testers, self.pregame_vc_id, self.match_label,
            self.pregame_message  # Pass the existing message to edit
        )

    async def start_captains_draft(self, interaction: discord.Interaction):
        """Start captain draft - edits existing pregame embed"""
        from searchmatchmaking import queue_state

        # Pick 2 random captains
        captains = random.sample(self.players, 2)
        remaining = [p for p in self.players if p not in captains]

        # Create view and initialize buttons with MMR
        view = CaptainDraftView(captains, remaining, test_mode=self.test_mode, match_label=self.match_label, guild=interaction.guild)
        await view.initialize_buttons()

        # Build initial embed (MMR shown in buttons only)
        embed = view.build_draft_embed()

        # Edit the existing pregame message instead of posting new one
        if self.pregame_message:
            try:
                await self.pregame_message.edit(embed=embed, view=view)
                view.draft_message = self.pregame_message
                return
            except:
                pass

        # Fallback: send new message if edit fails
        msg = await interaction.followup.send(embed=embed, view=view)
        view.draft_message = msg

    async def start_players_pick(self, interaction: discord.Interaction):
        """Start players pick teams - edits existing pregame embed"""
        embed = discord.Embed(
            title=f"Players Pick Teams - {self.match_label}",
            description="Click a button to join a team!\n\nTeams must be **4v4** to proceed.",
            color=discord.Color.green()
        )

        embed.add_field(name=f"<:redteam:{RED_TEAM_EMOJI_ID}> Red Team (0/4)", value="*No players yet*", inline=True)
        embed.add_field(name=f"<:blueteam:{BLUE_TEAM_EMOJI_ID}> Blue Team (0/4)", value="*No players yet*", inline=True)

        view = PlayersPickView(self.players, test_mode=self.test_mode, match_label=self.match_label)

        # Edit the existing pregame message instead of posting new one
        if self.pregame_message:
            try:
                await self.pregame_message.edit(embed=embed, view=view)
                view.pick_message = self.pregame_message
                return
            except:
                pass

        # Fallback: send new message if edit fails
        msg = await interaction.followup.send(embed=embed, view=view)
        view.pick_message = msg


async def show_balanced_teams_confirmation(
    channel: discord.TextChannel,
    red_team: List[int],
    blue_team: List[int],
    player_mmrs: dict,
    all_players: List[int],
    test_mode: bool,
    testers: List[int],
    pregame_vc_id: int,
    match_label: str,
    pregame_message: discord.Message = None
):
    """Show balanced teams with 15-second confirmation timer.
    If majority doesn't reject, teams proceed automatically.
    Edits existing pregame_message instead of creating new one."""
    import asyncio
    from searchmatchmaking import get_queue_progress_image

    guild = channel.guild

    # Create confirmation view
    view = BalancedTeamsRejectView(all_players, test_mode, testers)
    view.confirmation_message = pregame_message  # Use existing message

    # Build team display (just player names, no MMR)
    red_mentions = "\n".join([f"<@{uid}>" for uid in red_team])
    blue_mentions = "\n".join([f"<@{uid}>" for uid in blue_team])

    # 15-second countdown
    for seconds_left in range(15, -1, -1):
        embed = discord.Embed(
            title=f"Balanced Teams - {match_label}",
            description=f"Teams will be locked in **{seconds_left}** seconds...\n\nVote **Reject** if you want to re-pick teams.",
            color=discord.Color.gold()
        )

        embed.add_field(
            name=f"<:redteam:{RED_TEAM_EMOJI_ID}> Red Team Voice",
            value=red_mentions,
            inline=True
        )
        embed.add_field(
            name=f"<:blueteam:{BLUE_TEAM_EMOJI_ID}> Blue Team Voice",
            value=blue_mentions,
            inline=True
        )

        # Show reject votes
        reject_count = len(view.reject_votes)
        embed.add_field(
            name=f"Reject Votes ({reject_count})",
            value=", ".join([f"<@{uid}>" for uid in view.reject_votes]) if view.reject_votes else "None",
            inline=False
        )

        embed.set_image(url=get_queue_progress_image(8))

        # Edit existing message or create new one if needed
        if view.confirmation_message:
            try:
                await view.confirmation_message.edit(embed=embed, view=view)
            except:
                view.confirmation_message = await channel.send(embed=embed, view=view)
        else:
            view.confirmation_message = await channel.send(embed=embed, view=view)

        # Check if majority rejected
        if view.rejected:
            log_action(f"Balanced teams rejected by majority - returning to team selection")
            try:
                await view.confirmation_message.delete()
            except:
                pass
            # Go back to team selection
            await show_team_selection_after_reject(channel, all_players, test_mode, testers, pregame_vc_id, match_label)
            return

        if seconds_left > 0:
            await asyncio.sleep(1)

    # Timer expired - proceed with teams
    log_action(f"Balanced teams confirmed (no majority reject)")
    try:
        await view.confirmation_message.delete()
    except:
        pass

    await finalize_teams(channel, red_team, blue_team, test_mode=test_mode, testers=testers)


async def show_team_selection_after_reject(
    channel: discord.TextChannel,
    players: List[int],
    test_mode: bool,
    testers: List[int],
    pregame_vc_id: int,
    match_label: str
):
    """Show team selection again after balanced teams were rejected"""
    from searchmatchmaking import queue_state, get_queue_progress_image

    embed = discord.Embed(
        title=f"Pregame Lobby - {match_label}",
        description="Balanced teams were rejected!\n\nSelect your preferred team selection method:",
        color=discord.Color.gold()
    )
    embed.set_image(url=get_queue_progress_image(8))

    player_count = f"{len(players)}/8 players"
    if test_mode:
        player_count += " (TEST MODE)"
    player_list = "\n".join([f"<@{uid}>" for uid in players])
    embed.add_field(name=f"Players ({player_count})", value=player_list, inline=False)

    view = TeamSelectionView(players, test_mode=test_mode, testers=testers, pregame_vc_id=pregame_vc_id, match_label=match_label)
    pregame_message = await channel.send(embed=embed, view=view)
    view.pregame_message = pregame_message
    queue_state.pregame_message = pregame_message


class BalancedTeamsRejectView(View):
    """View for rejecting balanced teams within 15 seconds"""
    def __init__(self, players: List[int], test_mode: bool = False, testers: List[int] = None):
        super().__init__(timeout=None)
        self.players = players
        self.test_mode = test_mode
        self.testers = testers or []
        self.reject_votes = set()
        self.rejected = False
        self.confirmation_message = None

    @discord.ui.button(label="Reject Teams", style=discord.ButtonStyle.danger, custom_id="reject_balanced")
    async def reject_btn(self, interaction: discord.Interaction, button: Button):
        await self.handle_reject(interaction)

    async def handle_reject(self, interaction: discord.Interaction):
        """Handle reject vote"""
        # Check if player is in match
        if self.test_mode:
            if interaction.user.id not in self.testers:
                await interaction.response.send_message("Only testers can vote!", ephemeral=True)
                return
        else:
            if interaction.user.id not in self.players:
                await interaction.response.send_message("Only players in this match can vote!", ephemeral=True)
                return

        # Toggle vote
        if interaction.user.id in self.reject_votes:
            self.reject_votes.remove(interaction.user.id)
        else:
            self.reject_votes.add(interaction.user.id)

        await interaction.response.defer()

        # Check if majority rejected
        if self.test_mode:
            # Test mode: need 2 tester votes to reject
            tester_rejects = sum(1 for uid in self.reject_votes if uid in self.testers)
            if tester_rejects >= 2:
                self.rejected = True
        else:
            # Normal mode: need majority (5 of 8) to reject
            majority_needed = (len(self.players) // 2) + 1
            if len(self.reject_votes) >= majority_needed:
                self.rejected = True


class PickConfirmationView(View):
    """View with Yes/No buttons to confirm player pick during captain draft"""
    def __init__(self, draft_view: 'CaptainDraftView', selected_id: int, picker_id: int):
        super().__init__(timeout=60)  # 60 second timeout
        self.draft_view = draft_view
        self.selected_id = selected_id
        self.picker_id = picker_id

        # Get player name for button labels
        member = draft_view.guild.get_member(selected_id) if draft_view.guild else None
        player_name = member.display_name if member else f"Player {selected_id}"

        # Green Yes button
        yes_button = Button(
            label=f"✅ Yes, pick {player_name}",
            style=discord.ButtonStyle.success,
            custom_id=f"confirm_pick_{selected_id}"
        )
        yes_button.callback = self.confirm_callback
        self.add_item(yes_button)

        # Red No button
        no_button = Button(
            label="❌ No, go back",
            style=discord.ButtonStyle.danger,
            custom_id=f"cancel_pick_{selected_id}"
        )
        no_button.callback = self.cancel_callback
        self.add_item(no_button)

    async def confirm_callback(self, interaction: discord.Interaction):
        """Handle confirmation - proceed with the pick"""
        if interaction.user.id != self.picker_id:
            await interaction.response.send_message("❌ Only the captain who selected can confirm!", ephemeral=True)
            return
        await self.draft_view.confirm_pick(interaction, self.selected_id, self.picker_id)

    async def cancel_callback(self, interaction: discord.Interaction):
        """Handle cancellation - go back to draft view"""
        if interaction.user.id != self.picker_id:
            await interaction.response.send_message("❌ Only the captain who selected can cancel!", ephemeral=True)
            return
        await self.draft_view.cancel_pick(interaction)


class CaptainDraftView(View):
    def __init__(self, captains: List[int], remaining: List[int], test_mode: bool = False, match_label: str = "Match", guild: discord.Guild = None):
        super().__init__(timeout=None)
        self.captain1 = captains[0]
        self.captain2 = captains[1]
        self.remaining = remaining
        self.red_team = [self.captain1]
        self.blue_team = [self.captain2]
        self.test_mode = test_mode
        self.match_label = match_label
        self.draft_message = None  # Will be set after sending/editing
        self.guild = guild
        self.player_mmrs = {}  # Cache MMR values
        self.player_ranks = {}  # Cache rank values
        self.pick_history = []  # Track picks for undo: [(player_id, team), ...]

    async def initialize_buttons(self):
        """Initialize buttons with player names, ranks, and MMR - must be called after __init__"""
        # Fetch MMR and rank for captains (already on teams)
        self.player_mmrs[self.captain1] = await get_player_mmr(self.captain1)
        self.player_mmrs[self.captain2] = await get_player_mmr(self.captain2)
        self.player_ranks[self.captain1] = get_player_rank(self.captain1)
        self.player_ranks[self.captain2] = get_player_rank(self.captain2)
        # Fetch MMR and rank for all remaining players
        for uid in self.remaining:
            self.player_mmrs[uid] = await get_player_mmr(uid)
            self.player_ranks[uid] = get_player_rank(uid)
        self.update_buttons()

    def update_buttons(self):
        """Update player selection buttons - show all players with team colors and rank emojis"""
        self.clear_items()

        # Row 0: Captains (always shown with team colors)
        # Red captain - format: {rank_emoji} - {name} - {MMR} MMR (C)
        c1_member = self.guild.get_member(self.captain1) if self.guild else None
        c1_name = c1_member.display_name if c1_member else f"Captain"
        if len(c1_name) > 10:
            c1_name = c1_name[:7] + "..."
        c1_mmr = self.player_mmrs.get(self.captain1, 500)
        c1_rank = self.player_ranks.get(self.captain1, 1)
        c1_rank_emoji = get_rank_emoji(self.guild, c1_rank)
        captain1_btn = Button(
            label=f"🔴 {c1_rank_emoji} {c1_name} - {c1_mmr} MMR (C)",
            style=discord.ButtonStyle.danger,
            custom_id=f"captain_{self.captain1}",
            disabled=True,
            row=0
        )
        self.add_item(captain1_btn)

        # Blue captain
        c2_member = self.guild.get_member(self.captain2) if self.guild else None
        c2_name = c2_member.display_name if c2_member else f"Captain"
        if len(c2_name) > 10:
            c2_name = c2_name[:7] + "..."
        c2_mmr = self.player_mmrs.get(self.captain2, 500)
        c2_rank = self.player_ranks.get(self.captain2, 1)
        c2_rank_emoji = get_rank_emoji(self.guild, c2_rank)
        captain2_btn = Button(
            label=f"🔵 {c2_rank_emoji} {c2_name} - {c2_mmr} MMR (C)",
            style=discord.ButtonStyle.primary,
            custom_id=f"captain_{self.captain2}",
            disabled=True,
            row=0
        )
        self.add_item(captain2_btn)

        # Build button list for other players: picked players first, then available
        button_order = []
        # Add red team picks (excluding captain)
        for uid in self.red_team:
            if uid != self.captain1:
                button_order.append((uid, 'RED'))
        # Add blue team picks (excluding captain)
        for uid in self.blue_team:
            if uid != self.captain2:
                button_order.append((uid, 'BLUE'))
        # Add remaining (available) sorted by MMR (highest to lowest)
        sorted_remaining = sorted(self.remaining, key=lambda uid: self.player_mmrs.get(uid, 500), reverse=True)
        for uid in sorted_remaining:
            button_order.append((uid, None))

        # Create buttons for each player (rows 1-2 for up to 6 players)
        for i, (uid, team) in enumerate(button_order):
            member = self.guild.get_member(uid) if self.guild else None
            player_name = member.display_name if member else f"Player {uid}"
            if len(player_name) > 10:
                player_name = player_name[:7] + "..."

            mmr = self.player_mmrs.get(uid, 500)
            rank = self.player_ranks.get(uid, 1)
            rank_emoji = get_rank_emoji(self.guild, rank)
            row = 1 + (i // 3)  # Start at row 1 (row 0 is captains)

            if team == 'RED':
                # Picked for red team - red button, disabled
                button = Button(
                    label=f"🔴 {rank_emoji} {player_name} - {mmr} MMR",
                    style=discord.ButtonStyle.danger,
                    custom_id=f"picked_{uid}",
                    disabled=True,
                    row=row
                )
            elif team == 'BLUE':
                # Picked for blue team - blue button, disabled
                button = Button(
                    label=f"🔵 {rank_emoji} {player_name} - {mmr} MMR",
                    style=discord.ButtonStyle.primary,
                    custom_id=f"picked_{uid}",
                    disabled=True,
                    row=row
                )
            else:
                # Available - grey button, clickable by either captain
                button = Button(
                    label=f"{rank_emoji} {player_name} - {mmr} MMR",
                    style=discord.ButtonStyle.secondary,
                    custom_id=f"pick_{uid}",
                    row=row
                )
                button.callback = self.make_pick_callback(uid)

            self.add_item(button)

        # Row 3: Undo Last Pick button (only show if there are picks to undo)
        if hasattr(self, 'pick_history') and self.pick_history:
            undo_btn = Button(
                label="↩️ Undo Last Pick",
                style=discord.ButtonStyle.secondary,
                custom_id="undo_pick",
                row=3
            )
            undo_btn.callback = self.undo_last_pick
            self.add_item(undo_btn)

    def make_pick_callback(self, player_id: int):
        """Create a callback for picking a specific player"""
        async def callback(interaction: discord.Interaction):
            await self.show_pick_confirmation(interaction, player_id)
        return callback

    async def show_pick_confirmation(self, interaction: discord.Interaction, selected_id: int):
        """Show confirmation buttons before picking a player - either captain can pick"""
        picker_id = interaction.user.id

        # Only captains can pick
        if picker_id != self.captain1 and picker_id != self.captain2:
            await interaction.response.send_message("❌ Only captains can pick players!", ephemeral=True)
            return

        # Check if captain's team is already full (4 players)
        if picker_id == self.captain1 and len(self.red_team) >= 4:
            await interaction.response.send_message("❌ Your team is already full!", ephemeral=True)
            return
        if picker_id == self.captain2 and len(self.blue_team) >= 4:
            await interaction.response.send_message("❌ Your team is already full!", ephemeral=True)
            return

        # Get player name and rank for confirmation message
        member = self.guild.get_member(selected_id) if self.guild else None
        player_name = member.display_name if member else f"Player {selected_id}"
        mmr = self.player_mmrs.get(selected_id, 500)
        rank = self.player_ranks.get(selected_id, 1)
        rank_emoji = get_rank_emoji(self.guild, rank)

        # Determine which team they'll join based on who's picking
        team_name = "Red" if picker_id == self.captain1 else "Blue"
        team_emoji = "🔴" if team_name == "Red" else "🔵"

        # Build confirmation embed
        embed = discord.Embed(
            title=f"Confirm Pick - {self.match_label}",
            description=f"**<@{picker_id}>**, are you sure you want to pick:\n\n"
                       f"**{team_emoji} {rank_emoji} {player_name}** ({mmr} MMR)\n\n"
                       f"This player will join **{team_name} Team**.",
            color=discord.Color.gold()
        )

        # Show current team status
        red_text = "\n".join([f"<@{uid}>" for uid in self.red_team]) or "*Captain only*"
        blue_text = "\n".join([f"<@{uid}>" for uid in self.blue_team]) or "*Captain only*"
        embed.add_field(name=f"🔴 Red Team ({len(self.red_team)}/4)", value=red_text, inline=True)
        embed.add_field(name=f"🔵 Blue Team ({len(self.blue_team)}/4)", value=blue_text, inline=True)

        # Create confirmation view - pass the picker who clicked
        confirm_view = PickConfirmationView(self, selected_id, picker_id)

        await interaction.response.edit_message(embed=embed, view=confirm_view)

    async def confirm_pick(self, interaction: discord.Interaction, selected_id: int, picker_id: int):
        """Actually execute the pick after confirmation"""
        # Add to the picking captain's team
        if picker_id == self.captain1:
            self.red_team.append(selected_id)
            self.pick_history.append((selected_id, 'RED'))
        else:
            self.blue_team.append(selected_id)
            self.pick_history.append((selected_id, 'BLUE'))

        self.remaining.remove(selected_id)

        if not self.remaining:
            # Draft complete - update embed one last time then finalize
            await interaction.response.defer()
            embed = self.build_draft_embed(complete=True)
            try:
                if self.draft_message:
                    await self.draft_message.edit(embed=embed, view=None)
            except:
                pass
            await finalize_teams(interaction.channel, self.red_team, self.blue_team, test_mode=self.test_mode)
        else:
            # Update buttons and embed with current teams
            self.update_buttons()
            embed = self.build_draft_embed()
            await interaction.response.edit_message(embed=embed, view=self)

    async def cancel_pick(self, interaction: discord.Interaction):
        """Cancel the pick and return to normal view"""
        self.update_buttons()
        embed = self.build_draft_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def undo_last_pick(self, interaction: discord.Interaction):
        """Undo the last pick - only captains can undo"""
        if interaction.user.id != self.captain1 and interaction.user.id != self.captain2:
            await interaction.response.send_message("❌ Only captains can undo picks!", ephemeral=True)
            return

        if not self.pick_history:
            await interaction.response.send_message("❌ No picks to undo!", ephemeral=True)
            return

        # Pop the last pick
        player_id, team = self.pick_history.pop()

        # Remove from team and add back to remaining
        if team == 'RED':
            self.red_team.remove(player_id)
        else:
            self.blue_team.remove(player_id)
        self.remaining.append(player_id)

        # Update buttons and embed
        self.update_buttons()
        embed = self.build_draft_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    def build_draft_embed(self, complete: bool = False) -> discord.Embed:
        """Build the captain draft embed showing current team status (MMR shown in buttons only)"""
        if complete:
            embed = discord.Embed(
                title=f"Captains Draft - {self.match_label}",
                description="✅ **Draft Complete!** Finalizing teams...",
                color=discord.Color.green()
            )
        else:
            embed = discord.Embed(
                title=f"Captains Draft - {self.match_label}",
                description=f"🔴 **<@{self.captain1}>** and 🔵 **<@{self.captain2}>** - pick your players!",
                color=discord.Color.purple()
            )

        # Red team - just names/mentions
        red_text = "\n".join([f"<@{uid}>" for uid in self.red_team])
        embed.add_field(
            name=f"<:redteam:{RED_TEAM_EMOJI_ID}> Red Team ({len(self.red_team)}/4)",
            value=red_text or "*No players yet*",
            inline=True
        )

        # Blue team - just names/mentions
        blue_text = "\n".join([f"<@{uid}>" for uid in self.blue_team])
        embed.add_field(
            name=f"<:blueteam:{BLUE_TEAM_EMOJI_ID}> Blue Team ({len(self.blue_team)}/4)",
            value=blue_text or "*No players yet*",
            inline=True
        )

        # Available players section removed - MMR shown in buttons
        if self.remaining:
            embed.add_field(
                name="Available Players",
                value="*Click a button below to pick*",
                inline=False
            )

        return embed


class PlayersPickView(View):
    def __init__(self, players: List[int], test_mode: bool = False, match_label: str = "Match"):
        super().__init__(timeout=None)
        self.players = players
        self.red_team = []
        self.blue_team = []
        self.votes = {}  # user_id -> 'RED' or 'BLUE'
        self.ready = set()  # Players who clicked SET TEAMS
        self.test_mode = test_mode
        self.match_label = match_label
        self.pick_message = None  # Will be set after sending/editing

    @discord.ui.button(label="Red Team", style=discord.ButtonStyle.danger, custom_id="pick_red")
    async def pick_red(self, interaction: discord.Interaction, button: Button):
        await self.handle_pick(interaction, 'RED')

    @discord.ui.button(label="Blue Team", style=discord.ButtonStyle.primary, custom_id="pick_blue")
    async def pick_blue(self, interaction: discord.Interaction, button: Button):
        await self.handle_pick(interaction, 'BLUE')

    @discord.ui.button(label="SET TEAMS", style=discord.ButtonStyle.success, custom_id="set_teams", row=1)
    async def set_teams(self, interaction: discord.Interaction, button: Button):
        await self.handle_ready(interaction)

    async def handle_pick(self, interaction: discord.Interaction, team: str):
        """Handle team pick - allows switching teams until SET TEAMS is clicked"""
        if interaction.user.id not in self.players:
            await interaction.response.send_message("❌ You're not in this match!", ephemeral=True)
            return

        # If already ready, can't switch
        if interaction.user.id in self.ready:
            await interaction.response.send_message("❌ You already locked in! Can't switch teams.", ephemeral=True)
            return

        # Get current team (if any)
        current_team = self.votes.get(interaction.user.id)

        # If switching to same team, do nothing
        if current_team == team:
            await interaction.response.send_message(f"You're already on {team} team!", ephemeral=True)
            return

        # Remove from old team if switching
        if current_team == 'RED':
            self.red_team.remove(interaction.user.id)
        elif current_team == 'BLUE':
            self.blue_team.remove(interaction.user.id)

        # Add to new team
        self.votes[interaction.user.id] = team
        if team == 'RED':
            self.red_team.append(interaction.user.id)
        else:
            self.blue_team.append(interaction.user.id)

        # Update embed with current picks
        embed = self.build_pick_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def handle_ready(self, interaction: discord.Interaction):
        """Handle SET TEAMS button - locks in player's team choice"""
        if interaction.user.id not in self.players:
            await interaction.response.send_message("❌ You're not in this match!", ephemeral=True)
            return

        # Must pick a team first
        if interaction.user.id not in self.votes:
            await interaction.response.send_message("❌ Pick a team first before locking in!", ephemeral=True)
            return

        # Toggle ready status
        if interaction.user.id in self.ready:
            self.ready.remove(interaction.user.id)
        else:
            self.ready.add(interaction.user.id)

        # Check if all players are ready
        if len(self.ready) == len(self.players):
            await interaction.response.defer()
            await self.finalize_vote(interaction)
        else:
            # Update embed with current picks
            embed = self.build_pick_embed()
            await interaction.response.edit_message(embed=embed, view=self)

    def build_pick_embed(self, complete: bool = False, error: str = None) -> discord.Embed:
        """Build the players pick embed showing current team status"""
        if error:
            embed = discord.Embed(
                title=f"Players Pick Teams - {self.match_label}",
                description=f"❌ {error}\n\nClick a button to join a team!",
                color=discord.Color.red()
            )
        elif complete:
            embed = discord.Embed(
                title=f"Players Pick Teams - {self.match_label}",
                description="✅ **Teams Complete!** Finalizing...",
                color=discord.Color.green()
            )
        else:
            not_picked = len(self.players) - len(self.votes)
            not_ready = len(self.players) - len(self.ready)
            embed = discord.Embed(
                title=f"Players Pick Teams - {self.match_label}",
                description=(
                    f"Click **Red Team** or **Blue Team** to pick your team.\n"
                    f"Click **SET TEAMS** when you're happy with your choice.\n"
                    f"You can switch teams until you click SET TEAMS!\n\n"
                    f"**{not_ready} players** need to click SET TEAMS."
                ),
                color=discord.Color.green()
            )

        # Red team - show who's ready with ✓
        red_text = ""
        for uid in self.red_team:
            ready_mark = " ✓" if uid in self.ready else ""
            red_text += f"<@{uid}>{ready_mark}\n"
        red_text = red_text.strip() if red_text else "*No players yet*"
        embed.add_field(
            name=f"<:redteam:{RED_TEAM_EMOJI_ID}> Red Team ({len(self.red_team)}/4)",
            value=red_text,
            inline=True
        )

        # Blue team - show who's ready with ✓
        blue_text = ""
        for uid in self.blue_team:
            ready_mark = " ✓" if uid in self.ready else ""
            blue_text += f"<@{uid}>{ready_mark}\n"
        blue_text = blue_text.strip() if blue_text else "*No players yet*"
        embed.add_field(
            name=f"<:blueteam:{BLUE_TEAM_EMOJI_ID}> Blue Team ({len(self.blue_team)}/4)",
            value=blue_text,
            inline=True
        )

        return embed

    async def finalize_vote(self, interaction: discord.Interaction):
        """Finalize after all players clicked SET TEAMS"""
        # Check if teams are balanced (4v4)
        if len(self.red_team) != 4 or len(self.blue_team) != 4:
            # Teams are uneven - unready everyone and let them try again
            embed = self.build_pick_embed(error=f"Teams must be 4v4! Currently {len(self.red_team)}v{len(self.blue_team)}. Everyone has been unreadied - rearrange teams!")
            self.ready.clear()
            try:
                if self.pick_message:
                    await self.pick_message.edit(embed=embed, view=self)
            except:
                pass
            return

        # Update embed to show completion
        embed = self.build_pick_embed(complete=True)
        try:
            if self.pick_message:
                await self.pick_message.edit(embed=embed, view=None)
        except:
            pass

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

    # Get the existing series text channel (created in start_pregame) and rename it with MMRs
    series_text_channel = None
    if hasattr(queue_state, 'series_text_channel_id') and queue_state.series_text_channel_id:
        series_text_channel = guild.get_channel(queue_state.series_text_channel_id)

    if series_text_channel:
        # Rename existing channel with MMRs
        series_text_channel_name = f"{series_label}-🔴{red_avg_mmr}-vs-🔵{blue_avg_mmr}"
        try:
            await series_text_channel.edit(
                name=series_text_channel_name,
                topic=f"Series channel for {series_label} - Auto-deleted when series ends"
            )
            log_action(f"Renamed series text channel to: {series_text_channel_name}")
        except Exception as e:
            log_action(f"Failed to rename series text channel: {e}")
    else:
        # Fallback: create new channel if none exists (shouldn't happen normally)
        text_category_id = 1403916181554860112  # Matchmaking category
        text_category = guild.get_channel(text_category_id)
        series_text_channel_name = f"{series_label}-🔴{red_avg_mmr}-vs-🔵{blue_avg_mmr}"
        series_text_channel = await guild.create_text_channel(
            name=series_text_channel_name,
            category=text_category,
            topic=f"Series channel for {series_label} - Auto-deleted when series ends",
            position=998  # Position at bottom of category, just above voice channels
        )
        log_action(f"Created series text channel (fallback): {series_text_channel.name}")

    temp_series.text_channel_id = series_text_channel.id

    # Create Red/Blue voice channels in Matchmaking category (below text channel)
    text_category_id = 1403916181554860112  # Matchmaking category
    mm_category = guild.get_channel(text_category_id)

    # Create Red Team voice channel with team emoji and series number (no "Red" text)
    red_vc_name = f"🔴 {series_label}"
    red_vc = await guild.create_voice_channel(
        name=red_vc_name,
        category=mm_category,
        user_limit=None,
        position=999  # Position at bottom (below text channel)
    )

    # Create Blue Team voice channel with team emoji and series number (no "Blue" text)
    blue_vc_name = f"🔵 {series_label}"
    blue_vc = await guild.create_voice_channel(
        name=blue_vc_name,
        category=mm_category,
        user_limit=None,
        position=999  # Position at bottom (below text channel)
    )

    # Move players from pregame (or any voice channel) to their team channels
    # Track players who couldn't be moved (not in voice)
    players_not_moved = []

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
                        players_not_moved.append(user_id)
                else:
                    players_not_moved.append(user_id)

        for user_id in blue_team:
            if user_id in testers:
                member = guild.get_member(user_id)
                if member and member.voice and member.voice.channel:
                    try:
                        await member.move_to(blue_vc)
                        log_action(f"Moved tester {member.name} to Blue VC")
                    except Exception as e:
                        log_action(f"Failed to move tester {user_id} to blue VC: {e}")
                        players_not_moved.append(user_id)
                else:
                    players_not_moved.append(user_id)
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
                    players_not_moved.append(user_id)
            else:
                players_not_moved.append(user_id)

        for user_id in blue_team:
            member = guild.get_member(user_id)
            if member and member.voice and member.voice.channel:
                try:
                    await member.move_to(blue_vc)
                    log_action(f"Moved {member.name} to Blue VC")
                except Exception as e:
                    log_action(f"Failed to move {user_id} to blue VC: {e}")
                    players_not_moved.append(user_id)
            else:
                players_not_moved.append(user_id)
    
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

    # Clear the series text channel ID from queue state (now owned by the series)
    queue_state.series_text_channel_id = None

    # Assign the series we created earlier and set VC IDs
    queue_state.current_series = temp_series
    queue_state.current_series.red_vc_id = red_vc.id
    queue_state.current_series.blue_vc_id = blue_vc.id
    
    # Add active matchmaking roles to all players (only for real matches)
    if not test_mode:
        try:
            from searchmatchmaking import add_active_match_roles
            all_players = red_team + blue_team
            await add_active_match_roles(guild, all_players, "MLG4v4", temp_series.match_number)
        except Exception as e:
            log_action(f"Failed to add active match roles: {e}")
        
        # Clear queue since match is starting (only for real matches)
        queue_state.queue.clear()
        queue_state.queue_join_times.clear()

        # Update queue embed to show it's empty and ready for new players
        from searchmatchmaking import update_queue_embed, QUEUE_CHANNEL_ID
        queue_channel = guild.get_channel(QUEUE_CHANNEL_ID)
        if queue_channel:
            await update_queue_embed(queue_channel)
            log_action("Updated queue embed after match started")

    await show_series_embed(channel)

    # Notify players who couldn't be moved to voice
    if players_not_moved and series_text_channel:
        # Ping them in the series text channel
        mentions = " ".join([f"<@{uid}>" for uid in players_not_moved])
        warning_msg = await series_text_channel.send(
            f"⚠️ **Could not move to team voice channel:** {mentions}\n"
            f"Please join your team's voice channel manually!"
        )
        log_action(f"Notified {len(players_not_moved)} players not in voice: {players_not_moved}")

        # Also DM each player
        for uid in players_not_moved:
            member = guild.get_member(uid)
            if member:
                try:
                    team_name = "Red" if uid in red_team else "Blue"
                    team_vc = red_vc if uid in red_team else blue_vc
                    dm_embed = discord.Embed(
                        title=f"⚠️ {series_label} - Join Voice Channel!",
                        description=(
                            f"Your match has started but you weren't in voice chat.\n\n"
                            f"Please join **{team_vc.name}** to play with your team!"
                        ),
                        color=discord.Color.orange()
                    )
                    await member.send(embed=dm_embed)
                    log_action(f"Sent join voice DM to {member.name}")
                except discord.Forbidden:
                    log_action(f"Could not DM {member.name} - DMs disabled")
                except Exception as e:
                    log_action(f"Error sending voice DM to {member.name}: {e}")

    # Save to active_matches
    try:
        from postgame import save_active_match
        save_active_match(queue_state.current_series)
    except Exception as e:
        log_action(f"Failed to save active match: {e}")

    # Save state
    try:
        import state_manager
        state_manager.save_state()
    except:
        pass


# ============================================================================
# PLAYLIST-SPECIFIC PREGAME FUNCTIONS (Team Hardcore, Double Team, Head to Head)
# ============================================================================

async def wait_for_playlist_players(
    channel: discord.TextChannel,
    pregame_message: discord.Message,
    players: List[int],
    pregame_vc_id: int,
    playlist_state: 'PlaylistQueueState',
    match_number: int,
    match_label: str,
    auto_balance: bool = False,
    is_1v1: bool = False,
    players_pick_only: bool = False
):
    """Wait for all players to join pregame VC for playlist matches, then assign teams"""
    import asyncio
    from playlists import (
        get_queue_progress_image, PlaylistMatch, update_playlist_embed,
        balance_teams_by_mmr, show_playlist_match_embed, save_match_to_history,
        select_random_map_gametype, get_player_mmr
    )

    guild = channel.guild
    ps = playlist_state
    timeout_seconds = 600  # 10 minutes
    warning_sent = False  # Track if 5-minute warning has been sent
    start_time = asyncio.get_event_loop().time()

    while True:
        # Check timeout
        elapsed = asyncio.get_event_loop().time() - start_time
        if elapsed >= timeout_seconds:
            log_action(f"{match_label} pregame timeout - cancelling match")
            await cancel_playlist_match(channel, pregame_message, pregame_vc_id, ps, match_label)
            return

        # Get pregame VC
        pregame_vc = guild.get_channel(pregame_vc_id)
        if not pregame_vc:
            log_action(f"{match_label} pregame VC deleted - cancelling match")
            await cancel_playlist_match(channel, pregame_message, None, ps, match_label)
            return

        # Check who's in voice
        members_in_vc = [m.id for m in pregame_vc.members if not m.bot]
        players_in_voice = [uid for uid in players if uid in members_in_vc]
        players_not_in_voice = [uid for uid in players if uid not in members_in_vc]

        time_remaining = max(0, timeout_seconds - int(elapsed))
        minutes = time_remaining // 60
        seconds = time_remaining % 60

        # Update embed with status
        embed = discord.Embed(
            title=f"{match_label} - Pregame Lobby",
            description=f"**{ps.name}**\n\nTime remaining: **{minutes}m {seconds}s**",
            color=discord.Color.gold()
        )
        embed.set_image(url=get_queue_progress_image(len(players), ps.max_players))

        # Show player status
        player_status = []
        for uid in players:
            member = guild.get_member(uid)
            name = member.display_name if member else f"<@{uid}>"
            if uid in players_in_voice:
                player_status.append(f"[OK] {name}")
            else:
                player_status.append(f"[--] {name}")
        embed.add_field(name=f"Players ({len(players_in_voice)}/{len(players)})", value="\n".join(player_status), inline=False)

        try:
            await pregame_message.edit(embed=embed)
        except:
            pass

        # All players joined!
        if len(players_in_voice) == len(players):
            log_action(f"All players in {match_label} pregame - proceeding to team assignment")
            break

        # Send 5-minute warning DM and channel ping at halfway point
        if elapsed >= 300 and not warning_sent and players_not_in_voice:
            warning_sent = True
            # Ping in channel
            missing_pings = " ".join([f"<@{uid}>" for uid in players_not_in_voice])
            await channel.send(f"⚠️ **5 MINUTES REMAINING!** {missing_pings} - Join the Pregame Lobby NOW or the match will be cancelled!")
            # DM each missing player
            for uid in players_not_in_voice:
                member = guild.get_member(uid)
                if member:
                    try:
                        warning_embed = discord.Embed(
                            title=f"⚠️ {match_label} - 5 Minutes Remaining!",
                            description=f"You have **5 minutes** to join the **Pregame Lobby** voice channel or the match will be **cancelled**!",
                            color=discord.Color.red()
                        )
                        warning_embed.set_image(url=HEADER_IMAGE_URL)
                        await member.send(embed=warning_embed)
                        log_action(f"Sent 5-minute warning DM to {member.name}")
                    except discord.Forbidden:
                        log_action(f"Could not DM {member.name} - DMs disabled")
                    except Exception as e:
                        log_action(f"Error sending warning DM to {member.name}: {e}")

        await asyncio.sleep(5)

    # All players are in voice - proceed with team assignment
    await proceed_with_playlist_teams(
        channel, pregame_message, players, pregame_vc_id,
        ps, match_number, match_label, auto_balance, is_1v1, players_pick_only
    )


async def proceed_with_playlist_teams(
    channel: discord.TextChannel,
    pregame_message: discord.Message,
    players: List[int],
    pregame_vc_id: int,
    playlist_state: 'PlaylistQueueState',
    match_number: int,
    match_label: str,
    auto_balance: bool,
    is_1v1: bool,
    players_pick_only: bool = False
):
    """Assign teams and start the match for playlist matches"""
    from playlists import (
        PlaylistMatch, balance_teams_by_mmr, show_playlist_match_embed,
        save_match_to_history, select_random_map_gametype, get_player_mmr
    )

    guild = channel.guild
    ps = playlist_state
    voice_category_id = 1403916181554860112
    category = guild.get_channel(voice_category_id)

    # Select map/gametype
    map_name, gametype = ("", "")
    if ps.config.get("show_map_gametype", False):
        map_name, gametype = select_random_map_gametype(ps.playlist_type)

    # Assign teams
    if is_1v1:
        # 1v1 - no teams, just two players
        team1 = [players[0]]
        team2 = [players[1]]
        log_action(f"{match_label}: 1v1 match - {players[0]} vs {players[1]}")
    elif players_pick_only:
        # Players pick their own teams (Tournament mode)
        log_action(f"{match_label}: Starting players pick (tournament mode)")
        await start_playlist_players_pick(
            channel, pregame_message, players, pregame_vc_id,
            ps, match_number, match_label
        )
        return  # Players pick flow will handle the rest
    elif auto_balance:
        # Auto-balance by MMR
        team1, team2 = await balance_teams_by_mmr(players, ps.team_size)
        log_action(f"{match_label}: Auto-balanced teams")
    else:
        # This shouldn't happen for non-MLG playlists, but fallback to auto-balance
        team1, team2 = await balance_teams_by_mmr(players, ps.team_size)
        log_action(f"{match_label}: Fallback to auto-balanced teams")

    # Create match object
    match = PlaylistMatch(ps, players, team1, team2)
    match.match_number = match_number  # Use projected number from pregame start
    match.map_name = map_name
    match.gametype = gametype
    ps.current_match = match

    # Add active matchmaking roles to all players
    try:
        from searchmatchmaking import add_active_match_roles
        await add_active_match_roles(guild, players, ps.name, match_number)
    except Exception as e:
        log_action(f"Failed to add active match roles: {e}")

    # Delete pregame message
    try:
        await pregame_message.delete()
    except:
        pass

    # Create voice channels and move players
    pregame_vc = guild.get_channel(pregame_vc_id)

    if is_1v1:
        # 1v1: Rename pregame VC to "Player1 vs Player2"
        player1 = guild.get_member(team1[0])
        player2 = guild.get_member(team2[0])
        p1_name = player1.display_name if player1 else "Player 1"
        p2_name = player2.display_name if player2 else "Player 2"

        try:
            await pregame_vc.edit(name=f"{p1_name} vs {p2_name}")
        except:
            pass
        match.shared_vc_id = pregame_vc_id
        match.pregame_vc_id = None
    else:
        # Team match: Create team voice channels
        team1_mmrs = [await get_player_mmr(uid) for uid in team1]
        team2_mmrs = [await get_player_mmr(uid) for uid in team2]
        team1_avg = int(sum(team1_mmrs) / len(team1_mmrs)) if team1_mmrs else 1500
        team2_avg = int(sum(team2_mmrs) / len(team2_mmrs)) if team2_mmrs else 1500

        team1_vc = await guild.create_voice_channel(
            name=f"Red {match_label} - {team1_avg} MMR",
            category=category,
            user_limit=ps.team_size + 2
        )
        team2_vc = await guild.create_voice_channel(
            name=f"Blue {match_label} - {team2_avg} MMR",
            category=category,
            user_limit=ps.team_size + 2
        )

        match.team1_vc_id = team1_vc.id
        match.team2_vc_id = team2_vc.id

        # Move players to team VCs
        for uid in team1:
            member = guild.get_member(uid)
            if member and member.voice:
                try:
                    await member.move_to(team1_vc)
                except:
                    pass

        for uid in team2:
            member = guild.get_member(uid)
            if member and member.voice:
                try:
                    await member.move_to(team2_vc)
                except:
                    pass

        # Delete pregame VC
        if pregame_vc:
            try:
                await pregame_vc.delete()
            except:
                pass
        match.pregame_vc_id = None

    # Show match embed
    await show_playlist_match_embed(channel, match)

    # Update queue embed to show "match in progress"
    await update_playlist_embed(channel, ps)

    # Save to history
    save_match_to_history(match, "STARTED", guild)

    log_action(f"{match_label} started - Team1: {team1}, Team2: {team2}")


async def cancel_playlist_match(
    channel: discord.TextChannel,
    pregame_message: discord.Message,
    pregame_vc_id: int,
    playlist_state: 'PlaylistQueueState',
    match_label: str
):
    """Cancel a playlist match due to timeout or other reasons"""
    from playlists import update_playlist_embed, remove_match_from_active

    guild = channel.guild
    ps = playlist_state

    # Remove from active_matches BEFORE clearing current_match
    # The match number is temporary until completion - just remove the entry
    if ps.current_match:
        remove_match_from_active(ps.current_match)

    # Delete pregame VC
    if pregame_vc_id:
        pregame_vc = guild.get_channel(pregame_vc_id)
        if pregame_vc:
            try:
                await pregame_vc.delete()
            except:
                pass

    # Delete pregame message
    try:
        await pregame_message.delete()
    except:
        pass

    # Send cancellation message
    await channel.send(
        embed=discord.Embed(
            title=f"{match_label} - Cancelled",
            description="Match cancelled - not all players joined the pregame lobby in time.",
            color=discord.Color.red()
        )
    )

    # Clear current match if set
    ps.current_match = None

    # Update queue embed
    await update_playlist_embed(channel, ps)

    log_action(f"{match_label} cancelled - players did not join pregame")


# ============================================================================
# PLAYLIST PLAYERS PICK (Tournament mode - players pick their own teams)
# ============================================================================

async def start_playlist_players_pick(
    channel: discord.TextChannel,
    pregame_message: discord.Message,
    players: List[int],
    pregame_vc_id: int,
    playlist_state: 'PlaylistQueueState',
    match_number: int,
    match_label: str
):
    """Start players pick for playlist matches (Tournament mode)"""
    from playlists import get_player_mmr
    ps = playlist_state

    # Delete pregame message
    try:
        await pregame_message.delete()
    except:
        pass

    # Get MMR for all players and determine captains (two highest MMR)
    player_mmrs = []
    for uid in players:
        mmr = await get_player_mmr(uid)
        player_mmrs.append((uid, mmr))

    # Sort by MMR descending - top 2 become captains
    player_mmrs.sort(key=lambda x: x[1], reverse=True)
    captain1_id = player_mmrs[0][0]
    captain2_id = player_mmrs[1][0]

    # Get captain display names
    guild = channel.guild
    captain1_member = guild.get_member(captain1_id)
    captain2_member = guild.get_member(captain2_id)
    captain1_name = captain1_member.display_name if captain1_member else f"Captain 1"
    captain2_name = captain2_member.display_name if captain2_member else f"Captain 2"

    log_action(f"{match_label}: Captains determined by MMR - {captain1_name} ({player_mmrs[0][1]}) and {captain2_name} ({player_mmrs[1][1]})")

    # Create players pick view with captain info
    view = PlaylistPlayersPickView(
        players=players,
        playlist_state=ps,
        match_number=match_number,
        match_label=match_label,
        pregame_vc_id=pregame_vc_id,
        team_size=ps.team_size,
        captain1_id=captain1_id,
        captain2_id=captain2_id,
        captain1_name=captain1_name,
        captain2_name=captain2_name
    )

    # Build initial embed
    embed = view.build_pick_embed()

    # Send the players pick message
    pings = " ".join([f"<@{uid}>" for uid in players])
    pick_message = await channel.send(content=pings, embed=embed, view=view)
    view.pick_message = pick_message

    log_action(f"{match_label}: Captain pick started - Team {captain1_name} vs Team {captain2_name}")


class PlaylistPlayersPickView(View):
    """Players pick view for playlist matches (Tournament mode) - players pick their captain"""

    def __init__(self, players: List[int], playlist_state: 'PlaylistQueueState',
                 match_number: int, match_label: str, pregame_vc_id: int, team_size: int = 4,
                 captain1_id: int = None, captain2_id: int = None,
                 captain1_name: str = "Captain 1", captain2_name: str = "Captain 2"):
        super().__init__(timeout=None)
        self.players = players
        self.playlist_state = playlist_state
        self.match_number = match_number
        self.match_label = match_label
        self.pregame_vc_id = pregame_vc_id
        self.team_size = team_size
        self.captain1_id = captain1_id
        self.captain2_id = captain2_id
        self.captain1_name = captain1_name
        self.captain2_name = captain2_name
        # Teams are now based on captain, not color - colors assigned randomly at end
        self.team1 = [captain1_id] if captain1_id else []  # Captain 1's team
        self.team2 = [captain2_id] if captain2_id else []  # Captain 2's team
        self.votes = {}  # user_id -> 'TEAM1' or 'TEAM2'
        # Captains are auto-assigned to their own team
        if captain1_id:
            self.votes[captain1_id] = 'TEAM1'
        if captain2_id:
            self.votes[captain2_id] = 'TEAM2'
        self.ready = set()  # Players who clicked SET TEAMS
        self.pick_message = None

        # Update button labels with captain names
        self.pick_team1.label = f"Team {captain1_name}"
        self.pick_team2.label = f"Team {captain2_name}"

    @discord.ui.button(label="Team Captain1", style=discord.ButtonStyle.secondary, custom_id="playlist_pick_team1")
    async def pick_team1(self, interaction: discord.Interaction, button: Button):
        await self.handle_pick(interaction, 'TEAM1')

    @discord.ui.button(label="Team Captain2", style=discord.ButtonStyle.secondary, custom_id="playlist_pick_team2")
    async def pick_team2(self, interaction: discord.Interaction, button: Button):
        await self.handle_pick(interaction, 'TEAM2')

    @discord.ui.button(label="SET TEAMS", style=discord.ButtonStyle.success, custom_id="playlist_set_teams", row=1)
    async def set_teams(self, interaction: discord.Interaction, button: Button):
        await self.handle_ready(interaction)

    async def handle_pick(self, interaction: discord.Interaction, team: str):
        """Handle team pick - allows switching until SET TEAMS clicked"""
        if interaction.user.id not in self.players:
            await interaction.response.send_message("❌ You're not in this match!", ephemeral=True)
            return

        # Captains can't switch teams
        if interaction.user.id == self.captain1_id or interaction.user.id == self.captain2_id:
            await interaction.response.send_message("❌ You're a captain! You can't switch teams.", ephemeral=True)
            return

        if interaction.user.id in self.ready:
            await interaction.response.send_message("❌ You already locked in! Can't switch teams.", ephemeral=True)
            return

        current_team = self.votes.get(interaction.user.id)

        if current_team == team:
            captain_name = self.captain1_name if team == 'TEAM1' else self.captain2_name
            await interaction.response.send_message(f"You're already on Team {captain_name}!", ephemeral=True)
            return

        # Remove from old team if switching
        if current_team == 'TEAM1':
            self.team1.remove(interaction.user.id)
        elif current_team == 'TEAM2':
            self.team2.remove(interaction.user.id)

        # Add to new team
        self.votes[interaction.user.id] = team
        if team == 'TEAM1':
            self.team1.append(interaction.user.id)
        else:
            self.team2.append(interaction.user.id)

        embed = self.build_pick_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def handle_ready(self, interaction: discord.Interaction):
        """Handle SET TEAMS button"""
        if interaction.user.id not in self.players:
            await interaction.response.send_message("❌ You're not in this match!", ephemeral=True)
            return

        if interaction.user.id not in self.votes:
            await interaction.response.send_message("❌ Pick a team first before locking in!", ephemeral=True)
            return

        # Toggle ready
        if interaction.user.id in self.ready:
            self.ready.remove(interaction.user.id)
        else:
            self.ready.add(interaction.user.id)

        # Check if all ready
        if len(self.ready) == len(self.players):
            await interaction.response.defer()
            await self.finalize_teams(interaction)
        else:
            embed = self.build_pick_embed()
            await interaction.response.edit_message(embed=embed, view=self)

    def build_pick_embed(self, complete: bool = False, error: str = None) -> discord.Embed:
        """Build the captain pick embed"""
        if error:
            embed = discord.Embed(
                title=f"Pick Your Captain - {self.match_label}",
                description=f"❌ {error}\n\nClick a button to join a team!",
                color=discord.Color.red()
            )
        elif complete:
            embed = discord.Embed(
                title=f"Pick Your Captain - {self.match_label}",
                description="✅ **Teams Complete!** Starting match...",
                color=discord.Color.green()
            )
        else:
            not_ready = len(self.players) - len(self.ready)
            embed = discord.Embed(
                title=f"Pick Your Captain - {self.match_label}",
                description=(
                    f"**Captains** (highest MMR): <@{self.captain1_id}> and <@{self.captain2_id}>\n\n"
                    f"Click **Team {self.captain1_name}** or **Team {self.captain2_name}** to pick your captain.\n"
                    f"Click **SET TEAMS** when you're happy with your choice.\n"
                    f"You can switch teams until you click SET TEAMS!\n\n"
                    f"**{not_ready} players** need to click SET TEAMS."
                ),
                color=discord.Color.green()
            )

        # Team 1 (Captain 1)
        team1_text = ""
        for uid in self.team1:
            ready_mark = " ✓" if uid in self.ready else ""
            captain_mark = " 👑" if uid == self.captain1_id else ""
            team1_text += f"<@{uid}>{captain_mark}{ready_mark}\n"
        team1_text = team1_text.strip() if team1_text else "*No players yet*"
        embed.add_field(
            name=f"Team {self.captain1_name} ({len(self.team1)}/{self.team_size})",
            value=team1_text,
            inline=True
        )

        # Team 2 (Captain 2)
        team2_text = ""
        for uid in self.team2:
            ready_mark = " ✓" if uid in self.ready else ""
            captain_mark = " 👑" if uid == self.captain2_id else ""
            team2_text += f"<@{uid}>{captain_mark}{ready_mark}\n"
        team2_text = team2_text.strip() if team2_text else "*No players yet*"
        embed.add_field(
            name=f"Team {self.captain2_name} ({len(self.team2)}/{self.team_size})",
            value=team2_text,
            inline=True
        )

        return embed

    async def finalize_teams(self, interaction: discord.Interaction):
        """Finalize teams and start the playlist match"""
        from playlists import (
            PlaylistMatch, show_playlist_match_embed, save_match_to_history
        )

        # Check teams are balanced
        if len(self.team1) != self.team_size or len(self.team2) != self.team_size:
            embed = self.build_pick_embed(
                error=f"Teams must be {self.team_size}v{self.team_size}! Currently {len(self.team1)}v{len(self.team2)}. Everyone has been unreadied - rearrange teams!"
            )
            self.ready.clear()
            try:
                if self.pick_message:
                    await self.pick_message.edit(embed=embed, view=self)
            except:
                pass
            return

        # Teams are valid - complete
        embed = self.build_pick_embed(complete=True)
        try:
            if self.pick_message:
                await self.pick_message.edit(embed=embed, view=None)
        except:
            pass

        guild = interaction.guild
        ps = self.playlist_state
        voice_category_id = 1403916181554860112
        category = guild.get_channel(voice_category_id)

        # Text channel category (Matchmaking)
        text_category_id = 1403916181554860112
        text_category = guild.get_channel(text_category_id)

        # Randomly assign team colors (team1/team2 -> red/blue)
        if random.choice([True, False]):
            red_team = self.team1
            blue_team = self.team2
            red_captain_name = self.captain1_name
            blue_captain_name = self.captain2_name
        else:
            red_team = self.team2
            blue_team = self.team1
            red_captain_name = self.captain2_name
            blue_captain_name = self.captain1_name

        log_action(f"{self.match_label}: Random color assignment - Team {red_captain_name} is RED, Team {blue_captain_name} is BLUE")

        # Create match object with assigned colors
        match = PlaylistMatch(ps, self.players, red_team, blue_team)
        match.match_number = self.match_number  # Use projected number from pregame start
        ps.current_match = match

        # Add active matchmaking roles to all players
        try:
            from searchmatchmaking import add_active_match_roles
            await add_active_match_roles(guild, self.players, ps.name, self.match_number)
        except Exception as e:
            log_action(f"Failed to add active match roles: {e}")

        # Create text channel for this match: "Team {captain1} vs Team {captain2}"
        text_channel_name = f"Team {red_captain_name} vs Team {blue_captain_name}"
        match_text_channel = await guild.create_text_channel(
            name=text_channel_name,
            category=text_category,
            topic=f"{self.match_label} - Auto-deleted when match ends"
        )
        match.text_channel_id = match_text_channel.id
        log_action(f"Created tournament text channel: {text_channel_name} (ID: {match_text_channel.id})")

        # Create team voice channels with captain names
        red_vc = await guild.create_voice_channel(
            name=f"🔴 - Team {red_captain_name}",
            category=category,
            user_limit=self.team_size + 2
        )

        blue_vc = await guild.create_voice_channel(
            name=f"🔵 - Team {blue_captain_name}",
            category=category,
            user_limit=self.team_size + 2
        )

        match.team1_vc_id = red_vc.id
        match.team2_vc_id = blue_vc.id

        # Delete pregame VC
        if self.pregame_vc_id:
            pregame_vc = guild.get_channel(self.pregame_vc_id)
            if pregame_vc:
                # Move players before deleting
                for uid in red_team:
                    member = guild.get_member(uid)
                    if member and member.voice and member.voice.channel == pregame_vc:
                        try:
                            await member.move_to(red_vc)
                        except:
                            pass
                for uid in blue_team:
                    member = guild.get_member(uid)
                    if member and member.voice and member.voice.channel == pregame_vc:
                        try:
                            await member.move_to(blue_vc)
                        except:
                            pass
                try:
                    await pregame_vc.delete()
                except:
                    pass

        # Show match embed in the new text channel
        await show_playlist_match_embed(match_text_channel, match)

        # Post to general chat
        await post_tournament_to_general(guild, match, red_captain_name, blue_captain_name)

        # Save to history
        save_match_to_history(match, "IN_PROGRESS")

        log_action(f"{self.match_label}: Teams finalized - Red (Team {red_captain_name}): {red_team}, Blue (Team {blue_captain_name}): {blue_team}")


async def post_tournament_to_general(guild: discord.Guild, match, red_captain_name: str, blue_captain_name: str):
    """Post tournament match to general chat with Twitch links"""
    from playlists import GENERAL_CHANNEL_ID

    channel = guild.get_channel(GENERAL_CHANNEL_ID)
    if not channel:
        return

    # Try to use twitch module for links
    view = None
    try:
        import twitch
        twitch.RED_TEAM_EMOJI_ID = RED_TEAM_EMOJI_ID
        twitch.BLUE_TEAM_EMOJI_ID = BLUE_TEAM_EMOJI_ID

        # Build embed with Twitch links
        embed = discord.Embed(
            title=f"Tournament Match In Progress - {match.get_match_label()}",
            description=f"**Team {red_captain_name}** vs **Team {blue_captain_name}**",
            color=discord.Color.gold()
        )

        # Format teams with clickable Twitch links
        red_text = twitch.format_team_with_links(match.team1, guild)
        blue_text = twitch.format_team_with_links(match.team2, guild)

        embed.add_field(
            name=f"<:redteam:{RED_TEAM_EMOJI_ID}> Team {red_captain_name}",
            value=red_text,
            inline=True
        )
        embed.add_field(
            name=f"<:blueteam:{BLUE_TEAM_EMOJI_ID}> Team {blue_captain_name}",
            value=blue_text,
            inline=True
        )

        embed.set_footer(text="Tournament match in progress - Click player names to view streams")

        # Get Twitch names for multistream buttons
        red_twitch = twitch.get_team_twitch_names(match.team1)
        blue_twitch = twitch.get_team_twitch_names(match.team2)

        if red_twitch or blue_twitch:
            view = twitch.MultiStreamView(
                red_twitch, blue_twitch,
                red_label=f"Team {red_captain_name}",
                blue_label=f"Team {blue_captain_name}"
            )

    except Exception as e:
        log_action(f"Twitch module error in tournament, falling back: {e}")
        # Fallback to basic embed
        embed = discord.Embed(
            title=f"Tournament Match In Progress - {match.get_match_label()}",
            description=f"**Team {red_captain_name}** vs **Team {blue_captain_name}**",
            color=discord.Color.gold()
        )

        red_mentions = "\n".join([f"<@{uid}>" for uid in match.team1])
        blue_mentions = "\n".join([f"<@{uid}>" for uid in match.team2])

        embed.add_field(
            name=f"<:redteam:{RED_TEAM_EMOJI_ID}> Team {red_captain_name}",
            value=red_mentions,
            inline=True
        )
        embed.add_field(
            name=f"<:blueteam:{BLUE_TEAM_EMOJI_ID}> Team {blue_captain_name}",
            value=blue_mentions,
            inline=True
        )

        embed.set_footer(text="Tournament match in progress")

    # Send embed and store reference (no @here ping)
    if view:
        match.general_message = await channel.send(embed=embed, view=view)
    else:
        match.general_message = await channel.send(embed=embed)
