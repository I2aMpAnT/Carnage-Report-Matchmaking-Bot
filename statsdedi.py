# statsdedi.py - Vultr VPS Management for Stats Dedi
# !! REMEMBER TO UPDATE VERSION NUMBER WHEN MAKING CHANGES !!

MODULE_VERSION = "1.1.0"

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button
import aiohttp
import asyncio
import os
import re
import time
from datetime import datetime
from typing import Optional, Dict, List

# Vultr API Configuration
VULTR_API_KEY = os.getenv('VULTR_API_KEY')
VULTR_API_BASE = "https://api.vultr.com/v2"

# Vultr Settings
VULTR_REGION = "ewr"  # NYC/New Jersey region
VULTR_PLAN = "vcg-a16-3c-32g-8vram"  # Cloud GPU: 3 vCPUs, 32GB RAM, 170GB NVMe, 8GB VRAM - $0.236/hr
VULTR_SNAPSHOT_ID = os.getenv('VULTR_SNAPSHOT_ID')  # Set in .env

# Hourly rate for cost calculation
HOURLY_RATE = 0.236  # $0.236/hr for vcg-a16-3c-32g-8vram

# Default password for the dedi
DEDI_PASSWORD = "2s-V-A#Ywo(]PJmN"

# Allowed roles
ALLOWED_ROLES = ["Dedi", "Staff", "Overlord"]

# Track active dedis (instance_id -> user_id)
active_dedis: Dict[str, int] = {}

# Track spin-up times for averaging
spinup_times: List[float] = []  # List of spin-up times in seconds
pending_creates: Dict[str, float] = {}  # instance_id -> start_time


def get_average_spinup_time() -> Optional[str]:
    """Get average spin-up time as formatted string"""
    if not spinup_times:
        return None
    avg_seconds = sum(spinup_times) / len(spinup_times)
    minutes = int(avg_seconds // 60)
    seconds = int(avg_seconds % 60)
    if minutes > 0:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


async def test_vultr_connection() -> tuple[bool, str]:
    """Test Vultr API connection and return (success, message)"""
    if not VULTR_API_KEY:
        return False, "VULTR_API_KEY not set in environment"

    headers = {
        "Authorization": f"Bearer {VULTR_API_KEY}",
        "Content-Type": "application/json"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{VULTR_API_BASE}/account", headers=headers) as resp:
                if resp.status == 200:
                    return True, "Connected"
                else:
                    text = await resp.text()
                    # Extract IP from error message if present
                    ip_match = re.search(r'(\d+\.\d+\.\d+\.\d+)', text)
                    if ip_match:
                        return False, f"IP not authorized: `{ip_match.group(1)}`\n\nAdd this IP to Vultr API Access Control."
                    return False, f"API error {resp.status}: {text}"
    except Exception as e:
        return False, f"Connection error: {e}"


def has_allowed_role():
    """Check if user has allowed role"""
    async def predicate(interaction: discord.Interaction):
        user_roles = [role.name for role in interaction.user.roles]
        if any(role in ALLOWED_ROLES for role in user_roles):
            return True
        await interaction.response.send_message(
            "You need the Dedi, Staff, or Overlord role to use this command!",
            ephemeral=True
        )
        return False
    return app_commands.check(predicate)


def is_admin():
    """Check if user has Staff or Overlord role"""
    async def predicate(interaction: discord.Interaction):
        user_roles = [role.name for role in interaction.user.roles]
        if any(role in ["Staff", "Overlord"] for role in user_roles):
            return True
        await interaction.response.send_message(
            "You need the Staff or Overlord role to use this command!",
            ephemeral=True
        )
        return False
    return app_commands.check(predicate)


async def vultr_request(method: str, endpoint: str, data: dict = None) -> dict:
    """Make a request to the Vultr API"""
    if not VULTR_API_KEY:
        raise ValueError("VULTR_API_KEY not set in environment")

    headers = {
        "Authorization": f"Bearer {VULTR_API_KEY}",
        "Content-Type": "application/json"
    }

    url = f"{VULTR_API_BASE}{endpoint}"

    async with aiohttp.ClientSession() as session:
        if method == "GET":
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    text = await resp.text()
                    raise Exception(f"Vultr API error {resp.status}: {text}")
        elif method == "POST":
            async with session.post(url, headers=headers, json=data) as resp:
                if resp.status in [200, 201, 202]:
                    return await resp.json()
                else:
                    text = await resp.text()
                    raise Exception(f"Vultr API error {resp.status}: {text}")
        elif method == "DELETE":
            async with session.delete(url, headers=headers) as resp:
                if resp.status in [200, 204]:
                    return {}
                else:
                    text = await resp.text()
                    raise Exception(f"Vultr API error {resp.status}: {text}")


async def list_instances() -> List[dict]:
    """List all VPS instances"""
    result = await vultr_request("GET", "/instances")
    return result.get("instances", [])


async def get_instance(instance_id: str) -> dict:
    """Get details of a specific instance"""
    result = await vultr_request("GET", f"/instances/{instance_id}")
    return result.get("instance", {})


async def create_instance(label: str) -> dict:
    """Create a new VPS instance from snapshot"""
    if not VULTR_SNAPSHOT_ID:
        raise ValueError("VULTR_SNAPSHOT_ID not set in environment")

    data = {
        "region": VULTR_REGION,
        "plan": VULTR_PLAN,
        "snapshot_id": VULTR_SNAPSHOT_ID,
        "label": label,
        "hostname": label.replace("'s StatsDedi", "").replace(" ", "-").lower()
    }

    result = await vultr_request("POST", "/instances", data)
    return result.get("instance", {})


async def destroy_instance(instance_id: str) -> dict:
    """Destroy a VPS instance"""
    # Get instance details first for billing info
    instance = await get_instance(instance_id)

    # Delete the instance
    await vultr_request("DELETE", f"/instances/{instance_id}")

    return instance


async def restart_instance(instance_id: str) -> dict:
    """Restart/reboot a VPS instance"""
    await vultr_request("POST", f"/instances/{instance_id}/reboot")
    return await get_instance(instance_id)


async def get_instance_bandwidth(instance_id: str) -> dict:
    """Get bandwidth usage for billing estimation"""
    try:
        result = await vultr_request("GET", f"/instances/{instance_id}/bandwidth")
        return result
    except:
        return {}


async def wait_for_instance_ready(instance_id: str, user: discord.User, initial_ip: str, start_time: float):
    """Background task to wait for instance to be ready and DM user"""
    max_attempts = 120  # 10 minutes max (5 second intervals)

    print(f"[DEDI] 🔄 Starting wait_for_instance_ready for {instance_id[:8]}... (user: {user.name})")

    for attempt in range(max_attempts):
        await asyncio.sleep(5)

        try:
            instance = await get_instance(instance_id)
            status = instance.get("status", "")
            power_status = instance.get("power_status", "")
            server_status = instance.get("server_status", "")
            main_ip = instance.get("main_ip", initial_ip)
            label = instance.get("label", "Stats Dedi")

            # Log status for debugging - more frequent at start, then every 30 seconds
            if attempt < 6 or attempt % 6 == 0:
                print(f"[DEDI] {instance_id[:8]}... attempt={attempt} status={status}, power={power_status}, server={server_status}, ip={main_ip}")

            # Check for error state (stopped means error)
            if power_status == "stopped" and status == "active":
                print(f"[DEDI] ❌ Instance {instance_id[:8]}... is in ERROR state (stopped)!")

                # Remove from pending
                if instance_id in pending_creates:
                    del pending_creates[instance_id]

                try:
                    embed = discord.Embed(
                        title="⚠️ Stats Dedi Error",
                        description=f"**{label}** has entered an error state and stopped unexpectedly.",
                        color=discord.Color.red()
                    )
                    embed.add_field(name="IP Address", value=f"`{main_ip}`", inline=True)
                    embed.add_field(name="Status", value="🔴 Stopped (Error)", inline=True)
                    embed.add_field(name="Instance ID", value=f"`{instance_id[:8]}...`", inline=True)
                    embed.set_footer(text="Would you like to restart this dedi?")

                    # Send error DM with restart option
                    view = ErrorRestartView(instance_id, user)
                    await user.send(embed=embed, view=view)
                    print(f"[DEDI] ❌ {user.name}'s StatsDedi stopped unexpectedly - Error DM sent")
                except discord.Forbidden:
                    print(f"[DEDI] ❌ Could not DM {user.name} - DMs disabled")
                except Exception as e:
                    print(f"[DEDI] ❌ Error sending error DM to {user.name}: {e}")
                return

            # Check if ready - just need active and running
            if status == "active" and power_status == "running":
                print(f"[DEDI] ✅ Instance {instance_id[:8]}... is now active and running!")
                # Calculate spin-up time
                elapsed = time.time() - start_time
                spinup_times.append(elapsed)

                # Remove from pending
                if instance_id in pending_creates:
                    del pending_creates[instance_id]

                # Format elapsed time
                elapsed_min = int(elapsed // 60)
                elapsed_sec = int(elapsed % 60)
                elapsed_str = f"{elapsed_min}m {elapsed_sec}s" if elapsed_min > 0 else f"{elapsed_sec}s"

                try:
                    embed = discord.Embed(
                        title=f"✅ Stats Dedi Ready!",
                        description=f"**{label}** is now ready to use!",
                        color=discord.Color.green()
                    )
                    embed.add_field(name="IP Address", value=f"`{main_ip}`", inline=True)
                    embed.add_field(name="Password", value=f"`{DEDI_PASSWORD}`", inline=True)
                    embed.add_field(name="Spin-up Time", value=elapsed_str, inline=True)
                    embed.set_footer(text="Connect via Remote Desktop (RDP)")

                    await user.send(embed=embed)
                    print(f"[DEDI] ✅ {user.name}'s StatsDedi is ready at {main_ip} (took {elapsed_str}) - DM sent")
                except discord.Forbidden:
                    print(f"[DEDI] ❌ Could not DM {user.name} - DMs disabled")
                except Exception as e:
                    print(f"[DEDI] ❌ Error sending ready DM to {user.name}: {e}")
                return

        except Exception as e:
            print(f"[DEDI] ❌ Error checking instance status on attempt {attempt}: {e}")

    # Timeout - remove from pending but don't DM
    if instance_id in pending_creates:
        del pending_creates[instance_id]
    print(f"[DEDI] ⏱️ TIMEOUT waiting for {instance_id[:8]}... after {max_attempts * 5} seconds")


class ErrorRestartView(View):
    """View for restarting a dedi from an error DM"""

    def __init__(self, instance_id: str, user: discord.User):
        super().__init__(timeout=300)  # 5 minute timeout
        self.instance_id = instance_id
        self.user = user

    @discord.ui.button(label="Restart Dedi", style=discord.ButtonStyle.success, custom_id="error_restart")
    async def restart_btn(self, interaction: discord.Interaction, button: Button):
        # Only the original user can restart
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Only the original owner can restart this dedi.", ephemeral=True)
            return

        await interaction.response.defer()

        try:
            instance = await restart_instance(self.instance_id)
            label = instance.get("label", "Stats Dedi")
            main_ip = instance.get("main_ip", "Unknown")

            embed = discord.Embed(
                title="🔄 Stats Dedi Restarting",
                description=f"**{label}** is being restarted.\n\nYou'll receive another message when it's ready.",
                color=discord.Color.gold()
            )
            embed.add_field(name="IP Address", value=f"`{main_ip}`", inline=True)

            await interaction.followup.send(embed=embed)

            # Disable buttons
            self.restart_btn.disabled = True
            self.cancel_btn.disabled = True
            await interaction.message.edit(view=self)

            # Start background task to wait for ready after restart
            print(f"[DEDI] 🔄 Restarting {label} (ID: {self.instance_id[:8]}...) - monitoring for ready state")
            task = asyncio.create_task(wait_for_instance_ready(self.instance_id, self.user, main_ip, time.time()))
            task.set_name(f"dedi_restart_{self.instance_id[:8]}")

        except Exception as e:
            await interaction.followup.send(f"Error restarting dedi: {e}")

    @discord.ui.button(label="Ignore", style=discord.ButtonStyle.secondary, custom_id="error_ignore")
    async def cancel_btn(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Only the original owner can dismiss this.", ephemeral=True)
            return

        await interaction.response.send_message("Ignored. Use `/statsdedi` to manage your dedis.", ephemeral=True)

        # Disable buttons
        self.restart_btn.disabled = True
        self.cancel_btn.disabled = True
        await interaction.message.edit(view=self)


class StatsDediView(View):
    """View with List, Create, Restart, and Destroy buttons"""

    def __init__(self):
        super().__init__(timeout=300)  # 5 minute timeout

    @discord.ui.button(label="List Dedis", style=discord.ButtonStyle.primary, custom_id="dedi_list")
    async def list_btn(self, interaction: discord.Interaction, button: Button):
        await self.handle_list(interaction)

    @discord.ui.button(label="Create Dedi", style=discord.ButtonStyle.success, custom_id="dedi_create")
    async def create_btn(self, interaction: discord.Interaction, button: Button):
        await self.handle_create(interaction)

    @discord.ui.button(label="Restart Dedi", style=discord.ButtonStyle.secondary, custom_id="dedi_restart")
    async def restart_btn(self, interaction: discord.Interaction, button: Button):
        await self.handle_restart(interaction)

    @discord.ui.button(label="Destroy Dedi", style=discord.ButtonStyle.danger, custom_id="dedi_destroy")
    async def destroy_btn(self, interaction: discord.Interaction, button: Button):
        await self.handle_destroy(interaction)

    async def handle_list(self, interaction: discord.Interaction):
        """List all StatsDedi instances"""
        await interaction.response.defer(ephemeral=True)

        try:
            instances = await list_instances()

            # Filter to only StatsDedi instances
            stats_dedis = [i for i in instances if "StatsDedi" in i.get("label", "")]

            if not stats_dedis:
                await interaction.followup.send(
                    embed=discord.Embed(
                        title="Stats Dedis",
                        description="No Stats Dedis currently running.",
                        color=discord.Color.blue()
                    ),
                    ephemeral=True
                )
                return

            embed = discord.Embed(
                title="Stats Dedis",
                description=f"Found {len(stats_dedis)} Stats Dedi(s):",
                color=discord.Color.blue()
            )

            for dedi in stats_dedis:
                status_emoji = "🟢" if dedi.get("power_status") == "running" else "🟡"
                embed.add_field(
                    name=f"{status_emoji} {dedi.get('label', 'Unknown')}",
                    value=f"**IP:** `{dedi.get('main_ip', 'N/A')}`\n"
                          f"**Status:** {dedi.get('status', 'Unknown')}\n"
                          f"**ID:** `{dedi.get('id', 'N/A')}`",
                    inline=False
                )

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            await interaction.followup.send(f"Error listing dedis: {e}", ephemeral=True)

    async def handle_create(self, interaction: discord.Interaction):
        """Create a new StatsDedi"""
        await interaction.response.defer(ephemeral=True)

        try:
            # Check if user already has a dedi
            instances = await list_instances()
            user_base_label = f"{interaction.user.display_name}'s StatsDedi"

            # Find all existing dedis for this user
            existing = [i for i in instances if i.get("label", "").startswith(user_base_label)]

            if existing:
                # User already has at least one dedi - ask for confirmation
                existing_count = len(existing)
                existing_info = "\n".join([
                    f"• **{e.get('label')}** - IP: `{e.get('main_ip', 'N/A')}` ({e.get('status', 'Unknown')})"
                    for e in existing
                ])

                # Create confirmation view
                confirm_view = SecondDediConfirmView(interaction.user, existing_count, self)

                await interaction.followup.send(
                    embed=discord.Embed(
                        title="⚠️ You Already Have a Dedi Running",
                        description=f"You currently have **{existing_count}** Stats Dedi(s) running:\n\n"
                                    f"{existing_info}\n\n"
                                    f"**Are you sure you want to create another one?**\n"
                                    f"This will incur additional hourly charges.",
                        color=discord.Color.orange()
                    ),
                    view=confirm_view,
                    ephemeral=True
                )
                return

            # No existing dedi - create normally
            await self._create_dedi(interaction, user_base_label)

        except Exception as e:
            await interaction.followup.send(f"Error creating dedi: {e}", ephemeral=True)

    async def _create_dedi(self, interaction: discord.Interaction, user_label: str):
        """Internal method to actually create the dedi"""
        try:
            # Record start time for spin-up tracking
            start_time = time.time()

            # Create the instance
            instance = await create_instance(user_label)
            instance_id = instance.get("id")

            # Track this dedi and start time
            active_dedis[instance_id] = interaction.user.id
            pending_creates[instance_id] = start_time

            # Send confirmation in channel
            await interaction.followup.send(
                embed=discord.Embed(
                    title=f"Stats Dedi Creating - {interaction.user.display_name}",
                    description=f"Creating **{user_label}** for {interaction.user.mention}...\n\nYou will receive a DM with connection details.",
                    color=discord.Color.green()
                ),
                ephemeral=True
            )

            # Wait for IP to be assigned (poll a few times)
            main_ip = None
            for _ in range(12):  # Try for up to 60 seconds
                await asyncio.sleep(5)
                try:
                    inst = await get_instance(instance_id)
                    ip = inst.get("main_ip", "")
                    if ip and ip != "0.0.0.0":
                        main_ip = ip
                        break
                except:
                    pass

            # DM user with IP once we have it
            if main_ip:
                try:
                    avg_time = get_average_spinup_time()
                    estimate_text = f"Average spin-up time: {avg_time}" if avg_time else "This usually takes 1-3 minutes."

                    dm_embed = discord.Embed(
                        title=f"Stats Dedi Creating - {interaction.user.display_name}",
                        description=f"**{interaction.user.display_name}**'s Stats Dedi is being set up. {estimate_text}",
                        color=discord.Color.gold()
                    )
                    dm_embed.add_field(name="Requested By", value=interaction.user.mention, inline=True)
                    dm_embed.add_field(name="IP Address", value=f"`{main_ip}`", inline=True)
                    dm_embed.add_field(name="Password", value=f"`{DEDI_PASSWORD}`", inline=True)
                    dm_embed.add_field(name="Status", value="🟡 Setting up...", inline=False)
                    dm_embed.set_footer(text="You'll receive another message when it's ready!")

                    await interaction.user.send(embed=dm_embed)
                    print(f"[DEDI] 📤 Creating {user_label} (ID: {instance_id}) - IP: {main_ip} - Initial DM sent")
                except discord.Forbidden:
                    print(f"[DEDI] ❌ Could not DM {interaction.user.name} - DMs disabled")
            else:
                main_ip = "Unknown"
                print(f"[DEDI] Creating {user_label} (ID: {instance_id}) - IP not yet assigned")

            # Start background task to wait for ready
            print(f"[DEDI] 🚀 Launching background task for {instance_id[:8]}...")
            task = asyncio.create_task(wait_for_instance_ready(instance_id, interaction.user, main_ip, start_time))
            # Add task name for debugging
            task.set_name(f"dedi_wait_{instance_id[:8]}")
            print(f"[DEDI] 🚀 Background task created: {task.get_name()}")

        except Exception as e:
            print(f"[DEDI] ❌ Error in _create_dedi: {e}")
            await interaction.followup.send(f"Error creating dedi: {e}", ephemeral=True)

    async def handle_restart(self, interaction: discord.Interaction):
        """Restart StatsDedi - shows all dedis for selection"""
        await interaction.response.defer(ephemeral=True)

        try:
            instances = await list_instances()
            stats_dedis = [i for i in instances if "StatsDedi" in i.get("label", "")]

            if not stats_dedis:
                await interaction.followup.send(
                    embed=discord.Embed(
                        title="No Dedis Found",
                        description="No Stats Dedis are currently running.",
                        color=discord.Color.orange()
                    ),
                    ephemeral=True
                )
                return

            # Show all dedis to all users
            view = DediRestartSelectView(stats_dedis, interaction.user)
            await interaction.followup.send(
                embed=discord.Embed(
                    title="Select Dedi to Restart",
                    description="Choose which Stats Dedi to restart:",
                    color=discord.Color.gold()
                ),
                view=view,
                ephemeral=True
            )

        except Exception as e:
            await interaction.followup.send(f"Error listing dedis: {e}", ephemeral=True)

    async def handle_destroy(self, interaction: discord.Interaction):
        """Destroy StatsDedi - shows all dedis for selection"""
        await interaction.response.defer(ephemeral=True)

        try:
            instances = await list_instances()
            stats_dedis = [i for i in instances if "StatsDedi" in i.get("label", "")]

            if not stats_dedis:
                await interaction.followup.send(
                    embed=discord.Embed(
                        title="No Dedis Found",
                        description="No Stats Dedis are currently running.",
                        color=discord.Color.red()
                    ),
                    ephemeral=True
                )
                return

            # Show all dedis to all users
            view = DediDestroySelectView(stats_dedis)
            await interaction.followup.send(
                embed=discord.Embed(
                    title="Select Dedi to Destroy",
                    description="Choose which Stats Dedi to destroy:",
                    color=discord.Color.orange()
                ),
                view=view,
                ephemeral=True
            )

        except Exception as e:
            await interaction.followup.send(f"Error destroying dedi: {e}", ephemeral=True)


class SecondDediConfirmView(View):
    """View to confirm creating a second (or additional) dedi"""

    def __init__(self, user: discord.User, existing_count: int, parent_view: StatsDediView):
        super().__init__(timeout=60)
        self.user = user
        self.existing_count = existing_count
        self.parent_view = parent_view

    @discord.ui.button(label="Yes, Create Another", style=discord.ButtonStyle.success, custom_id="confirm_second_dedi")
    async def confirm_btn(self, interaction: discord.Interaction, button: Button):
        # Only the original user can confirm
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Only the original requester can confirm this.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        # Create the dedi with a numbered label
        new_number = self.existing_count + 1
        user_label = f"{interaction.user.display_name}'s StatsDedi {new_number}"

        await self.parent_view._create_dedi(interaction, user_label)

        # Disable the buttons
        self.confirm_btn.disabled = True
        self.cancel_btn.disabled = True
        await interaction.message.edit(view=self)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="cancel_second_dedi")
    async def cancel_btn(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Only the original requester can cancel this.", ephemeral=True)
            return

        await interaction.response.send_message("Dedi creation cancelled.", ephemeral=True)

        # Disable the buttons
        self.confirm_btn.disabled = True
        self.cancel_btn.disabled = True
        await interaction.message.edit(view=self)


class DediDestroySelectView(View):
    """View for admins to select which dedi to destroy"""

    def __init__(self, dedis: List[dict]):
        super().__init__(timeout=60)
        self.dedis = dedis

        # Add a button for each dedi
        for dedi in dedis[:5]:  # Max 5 buttons
            btn = Button(
                label=dedi.get("label", "Unknown")[:40],
                style=discord.ButtonStyle.danger,
                custom_id=f"destroy_{dedi.get('id')}"
            )
            btn.callback = self.make_callback(dedi)
            self.add_item(btn)

    def make_callback(self, dedi: dict):
        async def callback(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)

            instance_id = dedi.get("id")
            label = dedi.get("label", "Unknown")

            # Calculate cost
            date_created = dedi.get("date_created", "")
            try:
                created_time = datetime.fromisoformat(date_created.replace("Z", "+00:00"))
                hours_running = (datetime.now(created_time.tzinfo) - created_time).total_seconds() / 3600
                hours_running = max(1, hours_running)
                estimated_cost = hours_running * HOURLY_RATE
            except:
                estimated_cost = HOURLY_RATE

            try:
                await destroy_instance(instance_id)

                await interaction.followup.send(
                    embed=discord.Embed(
                        title=f"Stats Dedi Destroyed - {interaction.user.display_name}",
                        description=f"**{label}** has been destroyed by {interaction.user.mention}.\n\n"
                                    f"**Estimated Cost:** ${estimated_cost:.2f}",
                        color=discord.Color.green()
                    ),
                    ephemeral=True
                )
                print(f"[DEDI] 🗑️ {interaction.user.name} destroyed {label} (ID: {instance_id})")
            except Exception as e:
                await interaction.followup.send(f"Error: {e}", ephemeral=True)

        return callback


class DediRestartSelectView(View):
    """View to select which dedi to restart"""

    def __init__(self, dedis: List[dict], user: discord.User):
        super().__init__(timeout=60)
        self.dedis = dedis
        self.user = user

        # Add a button for each dedi
        for dedi in dedis[:5]:  # Max 5 buttons
            status_emoji = "🟢" if dedi.get("power_status") == "running" else "🔴"
            btn = Button(
                label=f"{status_emoji} {dedi.get('label', 'Unknown')[:35]}",
                style=discord.ButtonStyle.secondary,
                custom_id=f"restart_{dedi.get('id')}"
            )
            btn.callback = self.make_callback(dedi)
            self.add_item(btn)

    def make_callback(self, dedi: dict):
        async def callback(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)

            instance_id = dedi.get("id")
            label = dedi.get("label", "Unknown")
            main_ip = dedi.get("main_ip", "Unknown")

            try:
                await restart_instance(instance_id)

                await interaction.followup.send(
                    embed=discord.Embed(
                        title="🔄 Stats Dedi Restarting",
                        description=f"**{label}** is being restarted.\n\nYou'll receive a DM when it's ready.",
                        color=discord.Color.gold()
                    ),
                    ephemeral=True
                )
                print(f"[DEDI] 🔄 {interaction.user.name} restarted {label} (ID: {instance_id})")

                # Start background task to wait for ready after restart
                task = asyncio.create_task(wait_for_instance_ready(instance_id, interaction.user, main_ip, time.time()))
                task.set_name(f"dedi_restart_{instance_id[:8]}")

            except Exception as e:
                await interaction.followup.send(f"Error restarting dedi: {e}", ephemeral=True)

        return callback


class StatsDediCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="statsdedi", description="Manage Stats Dedi VPS instances")
    @has_allowed_role()
    async def statsdedi(self, interaction: discord.Interaction):
        """Main command - shows control panel"""
        # Defer first so we can test the API
        await interaction.response.defer(ephemeral=True)

        if not VULTR_API_KEY:
            await interaction.followup.send(
                "Vultr API key not configured. Please set VULTR_API_KEY in .env",
                ephemeral=True
            )
            return

        if not VULTR_SNAPSHOT_ID:
            await interaction.followup.send(
                "Vultr snapshot ID not configured. Please set VULTR_SNAPSHOT_ID in .env",
                ephemeral=True
            )
            return

        # Test API connection first
        success, message = await test_vultr_connection()
        if not success:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="Vultr API Error",
                    description=message,
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
            return

        # Get average spin-up time
        avg_time = get_average_spinup_time()
        avg_text = f"\n\n**Avg Spin-up Time:** {avg_time}" if avg_time else ""

        embed = discord.Embed(
            title="Stats Dedi Control Panel",
            description=f"Manage Vultr VPS instances for stats processing.\n\n"
                        f"**List** - View all running Stats Dedis\n"
                        f"**Create** - Spin up a new Stats Dedi\n"
                        f"**Restart** - Reboot a Stats Dedi\n"
                        f"**Destroy** - Shut down your Stats Dedi{avg_text}",
            color=discord.Color.blue()
        )
        embed.set_footer(text="Stats Dedis are billed hourly. Remember to destroy when done!")

        view = StatsDediView()
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="snapshotupdate", description="Update the Vultr snapshot ID for Stats Dedis (Admin only)")
    @app_commands.describe(snapshot_id="The new Vultr snapshot ID to use")
    @is_admin()
    async def snapshotupdate(self, interaction: discord.Interaction, snapshot_id: str):
        """Update the snapshot ID used for creating Stats Dedis"""
        global VULTR_SNAPSHOT_ID

        old_snapshot = VULTR_SNAPSHOT_ID
        VULTR_SNAPSHOT_ID = snapshot_id

        # Update .env file
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
        env_updated = False

        try:
            # Read existing .env
            if os.path.exists(env_path):
                with open(env_path, 'r') as f:
                    lines = f.readlines()

                # Update or add VULTR_SNAPSHOT_ID
                found = False
                for i, line in enumerate(lines):
                    if line.startswith('VULTR_SNAPSHOT_ID='):
                        lines[i] = f'VULTR_SNAPSHOT_ID={snapshot_id}\n'
                        found = True
                        break

                if not found:
                    lines.append(f'VULTR_SNAPSHOT_ID={snapshot_id}\n')

                with open(env_path, 'w') as f:
                    f.writelines(lines)
                env_updated = True
            else:
                # Create .env with just this value
                with open(env_path, 'w') as f:
                    f.write(f'VULTR_SNAPSHOT_ID={snapshot_id}\n')
                env_updated = True
        except Exception as e:
            print(f"[DEDI] Failed to update .env: {e}")

        status_text = "Updated in .env file." if env_updated else "Failed to update .env file."

        await interaction.response.send_message(
            embed=discord.Embed(
                title="Snapshot Updated",
                description=f"Stats Dedi snapshot ID has been updated.\n\n"
                            f"**Old:** `{old_snapshot or 'Not set'}`\n"
                            f"**New:** `{snapshot_id}`\n\n"
                            f"{status_text}",
                color=discord.Color.green()
            ),
            ephemeral=True
        )
        print(f"[DEDI] Snapshot updated by {interaction.user.name}: {old_snapshot} -> {snapshot_id} (env_updated={env_updated})")


async def setup(bot):
    """Setup function to add cog to bot"""
    await bot.add_cog(StatsDediCog(bot))
    print(f"[DEDI] Stats Dedi module loaded (v{MODULE_VERSION})")
