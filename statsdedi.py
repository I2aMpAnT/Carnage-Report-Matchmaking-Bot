# statsdedi.py - Vultr VPS Management for Stats Dedi
# !! REMEMBER TO UPDATE VERSION NUMBER WHEN MAKING CHANGES !!

MODULE_VERSION = "1.0.0"

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button
import aiohttp
import asyncio
import os
from datetime import datetime
from typing import Optional, Dict, List

# Vultr API Configuration
VULTR_API_KEY = os.getenv('VULTR_API_KEY')
VULTR_API_BASE = "https://api.vultr.com/v2"

# Vultr Settings
VULTR_REGION = "ewr"  # NYC/New Jersey region
VULTR_PLAN = "vc2-1c-1gb"  # Basic plan - adjust as needed
VULTR_SNAPSHOT_ID = os.getenv('VULTR_SNAPSHOT_ID')  # Set in .env

# Default password for the dedi
DEDI_PASSWORD = "2s-V-A#Ywo(]PJmN"

# Allowed roles
ALLOWED_ROLES = ["Dedi", "Staff", "Overlord"]

# Track active dedis (instance_id -> user_id)
active_dedis: Dict[str, int] = {}


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


async def get_instance_bandwidth(instance_id: str) -> dict:
    """Get bandwidth usage for billing estimation"""
    try:
        result = await vultr_request("GET", f"/instances/{instance_id}/bandwidth")
        return result
    except:
        return {}


async def wait_for_instance_ready(instance_id: str, user: discord.User, initial_ip: str):
    """Background task to wait for instance to be ready and DM user"""
    max_attempts = 60  # 5 minutes max (5 second intervals)

    for attempt in range(max_attempts):
        await asyncio.sleep(5)

        try:
            instance = await get_instance(instance_id)
            status = instance.get("status", "")
            power_status = instance.get("power_status", "")
            server_status = instance.get("server_status", "")
            main_ip = instance.get("main_ip", initial_ip)

            # Check if ready
            if status == "active" and power_status == "running" and server_status == "ok":
                try:
                    embed = discord.Embed(
                        title="Stats Dedi Ready!",
                        description="Your Stats Dedi is now ready to use!",
                        color=discord.Color.green()
                    )
                    embed.add_field(name="IP Address", value=f"`{main_ip}`", inline=True)
                    embed.add_field(name="Password", value=f"`{DEDI_PASSWORD}`", inline=True)
                    embed.add_field(name="Status", value="Running", inline=False)
                    embed.set_footer(text="Connect via Remote Desktop (RDP)")

                    await user.send(embed=embed)
                    print(f"[DEDI] {user.name}'s StatsDedi is ready at {main_ip}")
                except discord.Forbidden:
                    print(f"[DEDI] Could not DM {user.name} - DMs disabled")
                return

        except Exception as e:
            print(f"[DEDI] Error checking instance status: {e}")

    # Timeout - still not ready after 5 minutes
    try:
        await user.send(
            embed=discord.Embed(
                title="Stats Dedi Status",
                description="Your Stats Dedi is taking longer than expected to start. It may still be setting up. Check back in a few minutes.",
                color=discord.Color.orange()
            )
        )
    except:
        pass


class StatsDediView(View):
    """View with List, Create, and Destroy buttons"""

    def __init__(self):
        super().__init__(timeout=300)  # 5 minute timeout

    @discord.ui.button(label="List Dedis", style=discord.ButtonStyle.primary, custom_id="dedi_list")
    async def list_btn(self, interaction: discord.Interaction, button: Button):
        await self.handle_list(interaction)

    @discord.ui.button(label="Create Dedi", style=discord.ButtonStyle.success, custom_id="dedi_create")
    async def create_btn(self, interaction: discord.Interaction, button: Button):
        await self.handle_create(interaction)

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
            user_label = f"{interaction.user.display_name}'s StatsDedi"

            existing = [i for i in instances if i.get("label") == user_label]
            if existing:
                await interaction.followup.send(
                    embed=discord.Embed(
                        title="Already Have a Dedi",
                        description=f"You already have a Stats Dedi running!\n\n"
                                    f"**IP:** `{existing[0].get('main_ip', 'N/A')}`\n"
                                    f"**Status:** {existing[0].get('status', 'Unknown')}\n\n"
                                    f"Destroy it first if you want to create a new one.",
                        color=discord.Color.orange()
                    ),
                    ephemeral=True
                )
                return

            # Create the instance
            instance = await create_instance(user_label)
            instance_id = instance.get("id")
            main_ip = instance.get("main_ip", "Assigning...")

            # Track this dedi
            active_dedis[instance_id] = interaction.user.id

            # Send confirmation in channel
            await interaction.followup.send(
                embed=discord.Embed(
                    title="Stats Dedi Creating",
                    description=f"Creating **{user_label}**...\n\nYou will receive a DM with connection details.",
                    color=discord.Color.green()
                ),
                ephemeral=True
            )

            # DM user with initial info
            try:
                dm_embed = discord.Embed(
                    title="Stats Dedi Creating",
                    description="Your Stats Dedi is being set up. This usually takes 1-3 minutes.",
                    color=discord.Color.gold()
                )
                dm_embed.add_field(name="IP Address", value=f"`{main_ip}`" if main_ip != "0.0.0.0" else "Assigning...", inline=True)
                dm_embed.add_field(name="Password", value=f"`{DEDI_PASSWORD}`", inline=True)
                dm_embed.add_field(name="Status", value="Setting up...", inline=False)
                dm_embed.set_footer(text="You'll receive another message when it's ready!")

                await interaction.user.send(embed=dm_embed)
                print(f"[DEDI] Creating {user_label} (ID: {instance_id})")
            except discord.Forbidden:
                print(f"[DEDI] Could not DM {interaction.user.name} - DMs disabled")

            # Start background task to wait for ready
            asyncio.create_task(wait_for_instance_ready(instance_id, interaction.user, main_ip))

        except Exception as e:
            await interaction.followup.send(f"Error creating dedi: {e}", ephemeral=True)

    async def handle_destroy(self, interaction: discord.Interaction):
        """Destroy user's StatsDedi"""
        await interaction.response.defer(ephemeral=True)

        try:
            # Find user's dedi
            instances = await list_instances()
            user_label = f"{interaction.user.display_name}'s StatsDedi"

            user_dedi = None
            for i in instances:
                if i.get("label") == user_label:
                    user_dedi = i
                    break

            # Staff/Overlord can destroy any dedi - show selection
            user_roles = [role.name for role in interaction.user.roles]
            is_admin = any(role in ["Staff", "Overlord"] for role in user_roles)

            if not user_dedi and not is_admin:
                await interaction.followup.send(
                    embed=discord.Embed(
                        title="No Dedi Found",
                        description="You don't have a Stats Dedi running.",
                        color=discord.Color.red()
                    ),
                    ephemeral=True
                )
                return

            # If admin and no personal dedi, show all dedis to choose from
            if not user_dedi and is_admin:
                stats_dedis = [i for i in instances if "StatsDedi" in i.get("label", "")]
                if not stats_dedis:
                    await interaction.followup.send("No Stats Dedis to destroy.", ephemeral=True)
                    return

                # Show selection view
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
                return

            # Destroy the user's dedi
            instance_id = user_dedi.get("id")

            # Get billing info before destroying
            # Note: Vultr charges by the hour, minimum 1 hour
            # We'll estimate based on the instance age
            date_created = user_dedi.get("date_created", "")

            # Calculate approximate cost (vc2-1c-1gb is ~$5/month = ~$0.007/hour)
            hourly_rate = 0.007
            try:
                created_time = datetime.fromisoformat(date_created.replace("Z", "+00:00"))
                hours_running = (datetime.now(created_time.tzinfo) - created_time).total_seconds() / 3600
                hours_running = max(1, hours_running)  # Minimum 1 hour
                estimated_cost = hours_running * hourly_rate
            except:
                estimated_cost = hourly_rate  # Default to 1 hour if can't parse

            # Destroy it
            await destroy_instance(instance_id)

            # Remove from tracking
            if instance_id in active_dedis:
                del active_dedis[instance_id]

            # Send confirmation
            await interaction.followup.send(
                embed=discord.Embed(
                    title="Stats Dedi Destroyed",
                    description=f"Thank you for using the Carnage Report Stats Dedi!\n\n"
                                f"**Estimated Cost:** ${estimated_cost:.2f}",
                    color=discord.Color.green()
                ),
                ephemeral=True
            )

            print(f"[DEDI] Destroyed {user_label} (ID: {instance_id}) - Est. cost: ${estimated_cost:.2f}")

        except Exception as e:
            await interaction.followup.send(f"Error destroying dedi: {e}", ephemeral=True)


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
            hourly_rate = 0.007
            try:
                created_time = datetime.fromisoformat(date_created.replace("Z", "+00:00"))
                hours_running = (datetime.now(created_time.tzinfo) - created_time).total_seconds() / 3600
                hours_running = max(1, hours_running)
                estimated_cost = hours_running * hourly_rate
            except:
                estimated_cost = hourly_rate

            try:
                await destroy_instance(instance_id)

                await interaction.followup.send(
                    embed=discord.Embed(
                        title="Stats Dedi Destroyed",
                        description=f"**{label}** has been destroyed.\n\n"
                                    f"**Estimated Cost:** ${estimated_cost:.2f}",
                        color=discord.Color.green()
                    ),
                    ephemeral=True
                )
                print(f"[DEDI] Admin destroyed {label} (ID: {instance_id})")
            except Exception as e:
                await interaction.followup.send(f"Error: {e}", ephemeral=True)

        return callback


class StatsDediCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="statsdedi", description="Manage Stats Dedi VPS instances")
    @has_allowed_role()
    async def statsdedi(self, interaction: discord.Interaction):
        """Main command - shows control panel"""
        if not VULTR_API_KEY:
            await interaction.response.send_message(
                "Vultr API key not configured. Please set VULTR_API_KEY in .env",
                ephemeral=True
            )
            return

        if not VULTR_SNAPSHOT_ID:
            await interaction.response.send_message(
                "Vultr snapshot ID not configured. Please set VULTR_SNAPSHOT_ID in .env",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="Stats Dedi Control Panel",
            description="Manage Vultr VPS instances for stats processing.\n\n"
                        "**List** - View all running Stats Dedis\n"
                        "**Create** - Spin up a new Stats Dedi\n"
                        "**Destroy** - Shut down your Stats Dedi",
            color=discord.Color.blue()
        )
        embed.set_footer(text="Stats Dedis are billed hourly. Remember to destroy when done!")

        view = StatsDediView()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot):
    """Setup function to add cog to bot"""
    await bot.add_cog(StatsDediCog(bot))
    print(f"[DEDI] Stats Dedi module loaded (v{MODULE_VERSION})")
