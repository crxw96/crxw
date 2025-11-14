import discord
from discord.ext import commands
from discord import app_commands
import json
from datetime import datetime

class Welcome(commands.Cog):
    """Welcome system for new members"""

    def __init__(self, bot):
        self.bot = bot
        self.settings_file = 'data/welcome_settings.json'
        self.settings = self.load_settings()

    def load_settings(self):
        """Load welcome settings from JSON"""
        try:
            with open(self.settings_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

    def save_settings(self):
        """Save welcome settings to JSON"""
        with open(self.settings_file, 'w') as f:
            json.dump(self.settings, f, indent=4)

    def get_guild_settings(self, guild_id):
        """Get settings for a specific guild"""
        guild_id_str = str(guild_id)
        if guild_id_str not in self.settings:
            self.settings[guild_id_str] = {
                'welcome_channel_id': None,
                'welcome_message': 'Welcome {mention} to **{server}**! 👋\n\nYou are member #{member_count}!',
                'auto_role_id': None,
                'dm_welcome': False,
                'dm_message': 'Welcome to **{server}**! We\'re glad to have you here. Make sure to read the rules!'
            }
            self.save_settings()
        return self.settings[guild_id_str]

    def format_message(self, message, member):
        """Format welcome message with placeholders"""
        return message.format(
            mention=member.mention,
            user=member.name,
            server=member.guild.name,
            member_count=member.guild.member_count
        )

    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Handle when a member joins the server"""
        settings = self.get_guild_settings(member.guild.id)

        # Send welcome message to channel
        welcome_channel_id = settings.get('welcome_channel_id')
        if welcome_channel_id:
            channel = member.guild.get_channel(welcome_channel_id)
            if channel:
                welcome_message = settings.get('welcome_message', 'Welcome {mention} to **{server}**!')
                formatted_message = self.format_message(welcome_message, member)

                # Create welcome embed
                embed = discord.Embed(
                    description=formatted_message,
                    color=discord.Color.green(),
                    timestamp=datetime.now()
                )
                embed.set_thumbnail(url=member.display_avatar.url)
                embed.set_footer(text=f"Account created")
                embed.timestamp = member.created_at

                try:
                    await channel.send(embed=embed)
                except Exception as e:
                    print(f"Error sending welcome message: {e}")

        # Send DM welcome message
        if settings.get('dm_welcome', False):
            dm_message = settings.get('dm_message', 'Welcome to **{server}**!')
            formatted_dm = self.format_message(dm_message, member)

            try:
                dm_embed = discord.Embed(
                    title=f"Welcome to {member.guild.name}!",
                    description=formatted_dm,
                    color=discord.Color.blue()
                )
                dm_embed.set_thumbnail(url=member.guild.icon.url if member.guild.icon else None)
                await member.send(embed=dm_embed)
            except:
                pass  # User has DMs disabled

        # Auto-assign role
        auto_role_id = settings.get('auto_role_id')
        if auto_role_id:
            role = member.guild.get_role(auto_role_id)
            if role:
                try:
                    await member.add_roles(role, reason="Auto-role on join")
                    print(f"✅ Assigned {role.name} to {member.name}")
                except Exception as e:
                    print(f"❌ Error assigning auto-role: {e}")

    # Welcome settings group
    welcomesettings = app_commands.Group(name="welcome", description="Configure welcome system")

    @welcomesettings.command(name='setchannel', description='Set the welcome channel')
    @app_commands.describe(channel='The channel where welcome messages will be sent')
    async def set_welcome_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Set welcome channel"""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permission to use this command!", ephemeral=True)
            return

        guild_id = str(interaction.guild.id)
        if guild_id not in self.settings:
            self.settings[guild_id] = {}

        self.settings[guild_id]['welcome_channel_id'] = channel.id
        self.save_settings()

        await interaction.response.send_message(f"✅ Welcome messages will be sent to {channel.mention}")

    @welcomesettings.command(name='setmessage', description='Set the welcome message')
    @app_commands.describe(message='The welcome message (use {mention}, {user}, {server}, {member_count})')
    async def set_welcome_message(self, interaction: discord.Interaction, message: str):
        """Set welcome message"""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permission to use this command!", ephemeral=True)
            return

        guild_id = str(interaction.guild.id)
        if guild_id not in self.settings:
            self.settings[guild_id] = {}

        self.settings[guild_id]['welcome_message'] = message
        self.save_settings()

        # Show preview
        preview = self.format_message(message, interaction.user)
        embed = discord.Embed(
            title="✅ Welcome Message Updated",
            description="**Preview:**\n" + preview,
            color=discord.Color.green()
        )
        embed.set_footer(text="Available placeholders: {mention}, {user}, {server}, {member_count}")

        await interaction.response.send_message(embed=embed)

    @welcomesettings.command(name='setautorole', description='Set a role to auto-assign to new members')
    @app_commands.describe(role='The role to automatically assign')
    async def set_auto_role(self, interaction: discord.Interaction, role: discord.Role):
        """Set auto-assign role"""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permission to use this command!", ephemeral=True)
            return

        # Check if bot can assign this role
        if role.position >= interaction.guild.me.top_role.position:
            await interaction.response.send_message("❌ I can't assign this role! Make sure my role is higher in the hierarchy.", ephemeral=True)
            return

        guild_id = str(interaction.guild.id)
        if guild_id not in self.settings:
            self.settings[guild_id] = {}

        self.settings[guild_id]['auto_role_id'] = role.id
        self.save_settings()

        await interaction.response.send_message(f"✅ New members will automatically receive {role.mention}")

    @welcomesettings.command(name='removeautorole', description='Remove the auto-role')
    async def remove_auto_role(self, interaction: discord.Interaction):
        """Remove auto-role"""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permission to use this command!", ephemeral=True)
            return

        guild_id = str(interaction.guild.id)
        if guild_id not in self.settings:
            self.settings[guild_id] = {}

        self.settings[guild_id]['auto_role_id'] = None
        self.save_settings()

        await interaction.response.send_message("✅ Auto-role has been removed")

    @welcomesettings.command(name='toggledm', description='Toggle DM welcome messages')
    async def toggle_dm(self, interaction: discord.Interaction):
        """Toggle DM welcome messages"""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permission to use this command!", ephemeral=True)
            return

        guild_id = str(interaction.guild.id)
        settings = self.get_guild_settings(interaction.guild.id)

        current = settings.get('dm_welcome', False)
        self.settings[guild_id]['dm_welcome'] = not current
        self.save_settings()

        status = "enabled" if not current else "disabled"
        await interaction.response.send_message(f"✅ DM welcome messages have been **{status}**")

    @welcomesettings.command(name='setdmmessage', description='Set the DM welcome message')
    @app_commands.describe(message='The DM message (use {user}, {server})')
    async def set_dm_message(self, interaction: discord.Interaction, message: str):
        """Set DM welcome message"""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permission to use this command!", ephemeral=True)
            return

        guild_id = str(interaction.guild.id)
        if guild_id not in self.settings:
            self.settings[guild_id] = {}

        self.settings[guild_id]['dm_message'] = message
        self.save_settings()

        # Show preview
        preview = self.format_message(message, interaction.user)
        embed = discord.Embed(
            title="✅ DM Welcome Message Updated",
            description="**Preview:**\n" + preview,
            color=discord.Color.green()
        )
        embed.set_footer(text="Available placeholders: {user}, {server}")

        await interaction.response.send_message(embed=embed)

    @welcomesettings.command(name='settings', description='View current welcome settings')
    async def view_settings(self, interaction: discord.Interaction):
        """View welcome settings"""
        settings = self.get_guild_settings(interaction.guild.id)

        embed = discord.Embed(
            title="👋 Welcome System Settings",
            color=discord.Color.blue()
        )

        # Welcome channel
        welcome_channel_id = settings.get('welcome_channel_id')
        if welcome_channel_id:
            channel = interaction.guild.get_channel(welcome_channel_id)
            embed.add_field(name="Welcome Channel", value=channel.mention if channel else "Channel not found", inline=False)
        else:
            embed.add_field(name="Welcome Channel", value="❌ Not set", inline=False)

        # Welcome message
        welcome_message = settings.get('welcome_message', 'Not set')
        preview = self.format_message(welcome_message, interaction.user)
        embed.add_field(name="Welcome Message Preview", value=preview, inline=False)

        # Auto-role
        auto_role_id = settings.get('auto_role_id')
        if auto_role_id:
            role = interaction.guild.get_role(auto_role_id)
            embed.add_field(name="Auto-Role", value=role.mention if role else "Role not found", inline=True)
        else:
            embed.add_field(name="Auto-Role", value="❌ Not set", inline=True)

        # DM welcome
        dm_welcome = settings.get('dm_welcome', False)
        embed.add_field(name="DM Welcome", value="✅ Enabled" if dm_welcome else "❌ Disabled", inline=True)

        if dm_welcome:
            dm_message = settings.get('dm_message', 'Not set')
            dm_preview = self.format_message(dm_message, interaction.user)
            embed.add_field(name="DM Message Preview", value=dm_preview, inline=False)

        await interaction.response.send_message(embed=embed)

    @welcomesettings.command(name='test', description='Test the welcome message with yourself')
    async def test_welcome(self, interaction: discord.Interaction):
        """Test welcome message"""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permission to use this command!", ephemeral=True)
            return

        settings = self.get_guild_settings(interaction.guild.id)

        welcome_message = settings.get('welcome_message', 'Welcome {mention} to **{server}**!')
        formatted_message = self.format_message(welcome_message, interaction.user)

        embed = discord.Embed(
            title="🧪 Welcome Message Test",
            description=formatted_message,
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="This is how the welcome message will look")

        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Welcome(bot))
