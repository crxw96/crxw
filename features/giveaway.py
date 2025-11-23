import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import random
from datetime import datetime, timedelta

class GiveawayView(discord.ui.View):
    """Persistent view for giveaway entry buttons"""
    def __init__(self, giveaway_id: str, cog):
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id
        self.cog = cog

    @discord.ui.button(label="🎉 Enter Giveaway", style=discord.ButtonStyle.green, custom_id="giveaway_enter")
    async def enter_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle giveaway entry"""
        giveaway = self.cog.giveaways.get(self.giveaway_id)

        if not giveaway:
            await interaction.response.send_message("❌ This giveaway no longer exists!", ephemeral=True)
            return

        # Check if giveaway has ended
        end_time = datetime.fromisoformat(giveaway['end_time'])
        if datetime.now() >= end_time:
            await interaction.response.send_message("❌ This giveaway has already ended!", ephemeral=True)
            return

        # Check role requirements
        if giveaway.get('required_role_id'):
            role = interaction.guild.get_role(giveaway['required_role_id'])
            if role and role not in interaction.user.roles:
                role_name = giveaway.get('required_role_name', 'required role')
                await interaction.response.send_message(f"❌ You need the **{role_name}** role to enter this giveaway!", ephemeral=True)
                return

        # Check if already entered
        user_id = str(interaction.user.id)
        if user_id in giveaway['entries']:
            await interaction.response.send_message("❌ You're already entered in this giveaway!", ephemeral=True)
            return

        # Add entry
        giveaway['entries'].append(user_id)
        self.cog.save_data()

        # Update the embed with new entry count
        try:
            await self.cog.update_giveaway_message(interaction.guild, self.giveaway_id)
        except:
            pass

        await interaction.response.send_message("✅ You've been entered into the giveaway! Good luck! 🍀", ephemeral=True)

class Giveaway(commands.Cog):
    """Giveaway system with automatic winner selection"""

    def __init__(self, bot):
        self.bot = bot
        self.DATA_FILE = 'data/giveaways.json'
        self.giveaways = self.load_data()
        self.check_giveaways.start()

    def cog_unload(self):
        """Stop the background task when cog is unloaded"""
        self.check_giveaways.cancel()

    def load_data(self):
        """Load giveaway data from JSON file"""
        try:
            with open(self.DATA_FILE, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

    def save_data(self):
        """Save giveaway data to JSON file"""
        with open(self.DATA_FILE, 'w') as f:
            json.dump(self.giveaways, f, indent=4)

    def is_mod_or_owner(self, member):
        """Check if user is mod or server owner"""
        if member.guild.owner_id == member.id:
            return True
        return member.guild_permissions.administrator or member.guild_permissions.manage_guild

    def parse_duration(self, duration_str: str):
        """Parse duration string like '1h', '30m', '2d' into timedelta"""
        duration_str = duration_str.lower().strip()

        # Extract number and unit
        if duration_str[-1] == 's':
            value = int(duration_str[:-1])
            return timedelta(seconds=value)
        elif duration_str[-1] == 'm':
            value = int(duration_str[:-1])
            return timedelta(minutes=value)
        elif duration_str[-1] == 'h':
            value = int(duration_str[:-1])
            return timedelta(hours=value)
        elif duration_str[-1] == 'd':
            value = int(duration_str[:-1])
            return timedelta(days=value)
        else:
            raise ValueError("Invalid duration format. Use: 30s, 5m, 2h, or 1d")

    def format_time_remaining(self, end_time: datetime):
        """Format time remaining for display"""
        now = datetime.now()
        if now >= end_time:
            return "Ended"

        delta = end_time - now
        days = delta.days
        hours, remainder = divmod(delta.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        if seconds > 0 and days == 0:
            parts.append(f"{seconds}s")

        return " ".join(parts) if parts else "Less than 1s"

    async def update_giveaway_message(self, guild, giveaway_id: str):
        """Update giveaway message with current entry count"""
        giveaway = self.giveaways.get(giveaway_id)
        if not giveaway:
            return

        try:
            channel = guild.get_channel(giveaway['channel_id'])
            if not channel:
                return

            message = await channel.fetch_message(int(giveaway_id))
            if not message:
                return

            # Rebuild embed with updated entry count
            end_time = datetime.fromisoformat(giveaway['end_time'])
            time_remaining = self.format_time_remaining(end_time)

            embed = discord.Embed(
                title="🎉 GIVEAWAY 🎉",
                description=f"**Prize:** {giveaway['prize']}\n\n"
                           f"Click the button below to enter!\n"
                           f"Winner{'s' if giveaway['winners'] > 1 else ''} will be randomly selected.",
                color=discord.Color.gold(),
                timestamp=end_time
            )

            embed.add_field(name="⏰ Ends In", value=time_remaining, inline=True)
            embed.add_field(name="🏆 Winners", value=str(giveaway['winners']), inline=True)
            embed.add_field(name="📝 Entries", value=str(len(giveaway['entries'])), inline=True)

            if giveaway.get('required_role_name'):
                embed.add_field(name="🎫 Requirement", value=f"Must have **{giveaway['required_role_name']}** role", inline=False)

            embed.set_footer(text=f"Hosted by {giveaway['host_name']}")

            await message.edit(embed=embed)
        except Exception as e:
            print(f"Error updating giveaway message: {e}")

    async def end_giveaway(self, guild, giveaway_id: str, reroll: bool = False):
        """End a giveaway and select winners"""
        giveaway = self.giveaways.get(giveaway_id)
        if not giveaway:
            return None

        try:
            channel = guild.get_channel(giveaway['channel_id'])
            if not channel:
                return None

            message = await channel.fetch_message(int(giveaway_id))
            if not message:
                return None

            # Select winners
            entries = giveaway['entries']
            winner_count = min(giveaway['winners'], len(entries))

            if winner_count == 0:
                # No entries
                embed = discord.Embed(
                    title="🎉 GIVEAWAY ENDED 🎉",
                    description=f"**Prize:** {giveaway['prize']}\n\n"
                               f"❌ No valid entries! No winners selected.",
                    color=discord.Color.red()
                )
                embed.set_footer(text=f"Hosted by {giveaway['host_name']}")

                # Disable button
                view = discord.ui.View(timeout=None)
                button = discord.ui.Button(label="🎉 Giveaway Ended", style=discord.ButtonStyle.gray, disabled=True)
                view.add_item(button)

                await message.edit(embed=embed, view=view)

                if not reroll:
                    await channel.send(f"🎉 **GIVEAWAY ENDED**\n\nNo one entered the giveaway for **{giveaway['prize']}**!")

                return []

            # Randomly select winners
            winner_ids = random.sample(entries, winner_count)
            winners = [guild.get_member(int(wid)) for wid in winner_ids]
            winners = [w for w in winners if w is not None]  # Filter out members who left

            if not winners:
                # Winners left the server
                embed = discord.Embed(
                    title="🎉 GIVEAWAY ENDED 🎉",
                    description=f"**Prize:** {giveaway['prize']}\n\n"
                               f"❌ All selected winners left the server!",
                    color=discord.Color.red()
                )
                embed.set_footer(text=f"Hosted by {giveaway['host_name']}")

                view = discord.ui.View(timeout=None)
                button = discord.ui.Button(label="🎉 Giveaway Ended", style=discord.ButtonStyle.gray, disabled=True)
                view.add_item(button)

                await message.edit(embed=embed, view=view)
                return []

            # Update embed to show winners
            winner_mentions = ", ".join([w.mention for w in winners])

            embed = discord.Embed(
                title="🎉 GIVEAWAY ENDED 🎉",
                description=f"**Prize:** {giveaway['prize']}\n\n"
                           f"**Winner{'s' if len(winners) > 1 else ''}:** {winner_mentions}",
                color=discord.Color.green()
            )
            embed.add_field(name="📝 Total Entries", value=str(len(entries)), inline=True)
            embed.set_footer(text=f"Hosted by {giveaway['host_name']}")

            # Disable button
            view = discord.ui.View(timeout=None)
            button = discord.ui.Button(label="🎉 Giveaway Ended", style=discord.ButtonStyle.gray, disabled=True)
            view.add_item(button)

            await message.edit(embed=embed, view=view)

            # Announce winners
            if not reroll:
                await channel.send(
                    f"🎊 **CONGRATULATIONS** 🎊\n\n"
                    f"{winner_mentions} won **{giveaway['prize']}**!\n\n"
                    f"[Jump to Giveaway]({message.jump_url})"
                )
            else:
                await channel.send(
                    f"🎊 **REROLL WINNERS** 🎊\n\n"
                    f"{winner_mentions} won **{giveaway['prize']}**!\n\n"
                    f"[Jump to Giveaway]({message.jump_url})"
                )

            return winners

        except Exception as e:
            print(f"Error ending giveaway: {e}")
            return None

    @tasks.loop(seconds=10)
    async def check_giveaways(self):
        """Background task to check for ended giveaways"""
        now = datetime.now()
        ended_giveaways = []

        for giveaway_id, giveaway in self.giveaways.items():
            if giveaway.get('ended'):
                continue

            end_time = datetime.fromisoformat(giveaway['end_time'])

            if now >= end_time:
                # Giveaway should end
                guild = self.bot.get_guild(giveaway['guild_id'])
                if guild:
                    await self.end_giveaway(guild, giveaway_id)
                    ended_giveaways.append(giveaway_id)

        # Mark giveaways as ended
        for giveaway_id in ended_giveaways:
            self.giveaways[giveaway_id]['ended'] = True

        if ended_giveaways:
            self.save_data()

    @check_giveaways.before_loop
    async def before_check_giveaways(self):
        """Wait until bot is ready before starting task"""
        await self.bot.wait_until_ready()

    giveaway = app_commands.Group(name="giveaway", description="Manage giveaways")

    @giveaway.command(name='start', description='Start a new giveaway')
    @app_commands.describe(
        duration='Duration (e.g., 30m, 2h, 1d)',
        winners='Number of winners',
        prize='What are you giving away?',
        channel='Channel to post the giveaway (optional, defaults to current)',
        required_role='Role required to enter (optional)'
    )
    async def start_giveaway(
        self,
        interaction: discord.Interaction,
        duration: str,
        winners: int,
        prize: str,
        channel: discord.TextChannel = None,
        required_role: discord.Role = None
    ):
        """Start a new giveaway"""
        # Check permissions
        if not self.is_mod_or_owner(interaction.user):
            await interaction.response.send_message("❌ You need to be a moderator or server owner to start giveaways!", ephemeral=True)
            return

        # Validate inputs
        if winners < 1:
            await interaction.response.send_message("❌ Number of winners must be at least 1!", ephemeral=True)
            return

        if winners > 20:
            await interaction.response.send_message("❌ Maximum 20 winners per giveaway!", ephemeral=True)
            return

        try:
            duration_delta = self.parse_duration(duration)
        except ValueError as e:
            await interaction.response.send_message(f"❌ {str(e)}", ephemeral=True)
            return

        # Calculate end time
        end_time = datetime.now() + duration_delta

        # Use current channel if not specified
        if channel is None:
            channel = interaction.channel

        await interaction.response.defer()

        # Create embed
        embed = discord.Embed(
            title="🎉 GIVEAWAY 🎉",
            description=f"**Prize:** {prize}\n\n"
                       f"Click the button below to enter!\n"
                       f"Winner{'s' if winners > 1 else ''} will be randomly selected.",
            color=discord.Color.gold(),
            timestamp=end_time
        )

        time_remaining = self.format_time_remaining(end_time)
        embed.add_field(name="⏰ Ends In", value=time_remaining, inline=True)
        embed.add_field(name="🏆 Winners", value=str(winners), inline=True)
        embed.add_field(name="📝 Entries", value="0", inline=True)

        if required_role:
            embed.add_field(name="🎫 Requirement", value=f"Must have **{required_role.name}** role", inline=False)

        embed.set_footer(text=f"Hosted by {interaction.user.display_name}")

        # Create view with button
        view = GiveawayView(giveaway_id="temp", cog=self)

        # Send message
        try:
            message = await channel.send(embed=embed, view=view)
        except discord.Forbidden:
            await interaction.followup.send(f"❌ I don't have permission to send messages in {channel.mention}!", ephemeral=True)
            return

        # Update view with correct giveaway ID
        view.giveaway_id = str(message.id)

        # Store giveaway data
        giveaway_id = str(message.id)
        self.giveaways[giveaway_id] = {
            'guild_id': interaction.guild.id,
            'channel_id': channel.id,
            'host_id': interaction.user.id,
            'host_name': interaction.user.display_name,
            'prize': prize,
            'winners': winners,
            'entries': [],
            'end_time': end_time.isoformat(),
            'required_role_id': required_role.id if required_role else None,
            'required_role_name': required_role.name if required_role else None,
            'ended': False
        }
        self.save_data()

        await interaction.followup.send(
            f"✅ Giveaway started in {channel.mention}!\n"
            f"**Prize:** {prize}\n"
            f"**Duration:** {duration}\n"
            f"**Winners:** {winners}"
        )

    @giveaway.command(name='end', description='End a giveaway early and pick winners')
    @app_commands.describe(message_id='The ID of the giveaway message')
    async def end_giveaway_command(self, interaction: discord.Interaction, message_id: str):
        """Manually end a giveaway early"""
        # Check permissions
        if not self.is_mod_or_owner(interaction.user):
            await interaction.response.send_message("❌ You need to be a moderator or server owner to end giveaways!", ephemeral=True)
            return

        if message_id not in self.giveaways:
            await interaction.response.send_message("❌ Giveaway not found!", ephemeral=True)
            return

        giveaway = self.giveaways[message_id]

        if giveaway['guild_id'] != interaction.guild.id:
            await interaction.response.send_message("❌ That giveaway is not from this server!", ephemeral=True)
            return

        if giveaway.get('ended'):
            await interaction.response.send_message("❌ This giveaway has already ended!", ephemeral=True)
            return

        await interaction.response.defer()

        # End the giveaway
        winners = await self.end_giveaway(interaction.guild, message_id)

        if winners is None:
            await interaction.followup.send("❌ Failed to end giveaway. Message may have been deleted.")
            return

        # Mark as ended
        self.giveaways[message_id]['ended'] = True
        self.save_data()

        if winners:
            await interaction.followup.send(f"✅ Giveaway ended! {len(winners)} winner(s) selected.")
        else:
            await interaction.followup.send("✅ Giveaway ended with no winners.")

    @giveaway.command(name='reroll', description='Reroll winners for a giveaway')
    @app_commands.describe(message_id='The ID of the giveaway message')
    async def reroll_giveaway(self, interaction: discord.Interaction, message_id: str):
        """Reroll winners for an ended giveaway"""
        # Check permissions
        if not self.is_mod_or_owner(interaction.user):
            await interaction.response.send_message("❌ You need to be a moderator or server owner to reroll giveaways!", ephemeral=True)
            return

        if message_id not in self.giveaways:
            await interaction.response.send_message("❌ Giveaway not found!", ephemeral=True)
            return

        giveaway = self.giveaways[message_id]

        if giveaway['guild_id'] != interaction.guild.id:
            await interaction.response.send_message("❌ That giveaway is not from this server!", ephemeral=True)
            return

        if not giveaway.get('ended'):
            await interaction.response.send_message("❌ This giveaway hasn't ended yet! Use `/giveaway end` first.", ephemeral=True)
            return

        await interaction.response.defer()

        # Reroll winners
        winners = await self.end_giveaway(interaction.guild, message_id, reroll=True)

        if winners is None:
            await interaction.followup.send("❌ Failed to reroll giveaway. Message may have been deleted.")
            return

        if winners:
            await interaction.followup.send(f"✅ Giveaway rerolled! {len(winners)} new winner(s) selected.")
        else:
            await interaction.followup.send("❌ No valid entries to reroll.")

    @giveaway.command(name='list', description='List all active giveaways in this server')
    async def list_giveaways(self, interaction: discord.Interaction):
        """List all active giveaways"""
        active = []
        ended = []

        for giveaway_id, giveaway in self.giveaways.items():
            if giveaway['guild_id'] != interaction.guild.id:
                continue

            if giveaway.get('ended'):
                ended.append((giveaway_id, giveaway))
            else:
                active.append((giveaway_id, giveaway))

        if not active and not ended:
            await interaction.response.send_message("❌ No giveaways found in this server!", ephemeral=True)
            return

        embed = discord.Embed(
            title="🎁 Giveaway List",
            color=discord.Color.gold()
        )

        if active:
            active_text = ""
            for giveaway_id, giveaway in active[:5]:  # Show max 5
                channel = interaction.guild.get_channel(giveaway['channel_id'])
                channel_mention = channel.mention if channel else "Unknown"
                end_time = datetime.fromisoformat(giveaway['end_time'])
                time_left = self.format_time_remaining(end_time)

                active_text += f"**{giveaway['prize']}**\n"
                active_text += f"└─ {channel_mention} • {len(giveaway['entries'])} entries • Ends in {time_left}\n"
                active_text += f"└─ ID: `{giveaway_id}`\n\n"

            embed.add_field(name=f"🟢 Active Giveaways ({len(active)})", value=active_text or "None", inline=False)

        if ended:
            ended_text = ""
            for giveaway_id, giveaway in ended[:3]:  # Show max 3
                ended_text += f"**{giveaway['prize']}** • {len(giveaway['entries'])} entries\n"

            embed.add_field(name=f"⚫ Recently Ended ({len(ended)})", value=ended_text or "None", inline=False)

        await interaction.response.send_message(embed=embed)

async def setup(bot):
    """Setup function to load the cog"""
    cog = Giveaway(bot)

    # Re-add persistent views for existing giveaways
    for giveaway_id in cog.giveaways:
        if not cog.giveaways[giveaway_id].get('ended'):
            view = GiveawayView(giveaway_id, cog)
            bot.add_view(view, message_id=int(giveaway_id))

    await bot.add_cog(cog)
