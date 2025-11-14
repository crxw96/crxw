import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import json
from datetime import datetime, timedelta

class Moderation(commands.Cog):
    """Moderation system with warnings, timeouts, kicks, and bans"""

    def __init__(self, bot):
        self.bot = bot
        self.db_file = 'data/moderation.db'
        self.settings_file = 'data/moderation_settings.json'
        self.init_database()
        self.settings = self.load_settings()

    def init_database(self):
        """Initialize SQLite database for moderation"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()

        # Warnings table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER,
                user_id INTEGER,
                moderator_id INTEGER,
                reason TEXT,
                timestamp TEXT,
                active INTEGER DEFAULT 1
            )
        ''')

        # Mod actions table (for logging)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS mod_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER,
                user_id INTEGER,
                moderator_id INTEGER,
                action_type TEXT,
                reason TEXT,
                duration TEXT,
                timestamp TEXT
            )
        ''')

        conn.commit()
        conn.close()

    def load_settings(self):
        """Load moderation settings from JSON"""
        try:
            with open(self.settings_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

    def save_settings(self):
        """Save moderation settings to JSON"""
        with open(self.settings_file, 'w') as f:
            json.dump(self.settings, f, indent=4)

    def get_guild_settings(self, guild_id):
        """Get settings for a specific guild"""
        guild_id_str = str(guild_id)
        if guild_id_str not in self.settings:
            self.settings[guild_id_str] = {
                'mod_log_channel_id': None,
                'auto_timeout_warnings': 3,  # Auto-timeout at 3 warnings
                'timeout_duration': 3600  # 1 hour in seconds
            }
            self.save_settings()
        return self.settings[guild_id_str]

    def is_moderator(self, member):
        """Check if user has moderator permissions"""
        return (member.guild_permissions.kick_members or
                member.guild_permissions.ban_members or
                member.guild_permissions.moderate_members or
                member.guild.owner_id == member.id)

    async def log_action(self, guild, moderator, user, action_type, reason, duration=None):
        """Log moderation action to database and mod log channel"""
        # Save to database
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO mod_actions (guild_id, user_id, moderator_id, action_type, reason, duration, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (guild.id, user.id, moderator.id, action_type, reason, duration, datetime.now().isoformat()))

        conn.commit()
        conn.close()

        # Send to mod log channel
        settings = self.get_guild_settings(guild.id)
        mod_log_channel_id = settings.get('mod_log_channel_id')

        if mod_log_channel_id:
            channel = guild.get_channel(mod_log_channel_id)
            if channel:
                embed = discord.Embed(
                    title=f"🔨 {action_type.upper()}",
                    color=self.get_action_color(action_type),
                    timestamp=datetime.now()
                )
                embed.add_field(name="User", value=f"{user.mention} ({user.name})", inline=True)
                embed.add_field(name="Moderator", value=f"{moderator.mention}", inline=True)
                embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)

                if duration:
                    embed.add_field(name="Duration", value=duration, inline=True)

                embed.set_footer(text=f"User ID: {user.id}")

                try:
                    await channel.send(embed=embed)
                except:
                    pass

    def get_action_color(self, action_type):
        """Get color for action type"""
        colors = {
            'warn': discord.Color.yellow(),
            'timeout': discord.Color.orange(),
            'kick': discord.Color.red(),
            'ban': discord.Color.dark_red(),
            'unban': discord.Color.green()
        }
        return colors.get(action_type.lower(), discord.Color.greyple())

    def add_warning(self, guild_id, user_id, moderator_id, reason):
        """Add a warning to database"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO warnings (guild_id, user_id, moderator_id, reason, timestamp)
            VALUES (?, ?, ?, ?, ?)
        ''', (guild_id, user_id, moderator_id, reason, datetime.now().isoformat()))

        conn.commit()
        conn.close()

    def get_user_warnings(self, guild_id, user_id, active_only=True):
        """Get all warnings for a user"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()

        if active_only:
            cursor.execute('''
                SELECT id, moderator_id, reason, timestamp
                FROM warnings
                WHERE guild_id = ? AND user_id = ? AND active = 1
                ORDER BY timestamp DESC
            ''', (guild_id, user_id))
        else:
            cursor.execute('''
                SELECT id, moderator_id, reason, timestamp, active
                FROM warnings
                WHERE guild_id = ? AND user_id = ?
                ORDER BY timestamp DESC
            ''', (guild_id, user_id))

        warnings = cursor.fetchall()
        conn.close()
        return warnings

    def clear_warnings(self, guild_id, user_id):
        """Clear all warnings for a user"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE warnings
            SET active = 0
            WHERE guild_id = ? AND user_id = ?
        ''', (guild_id, user_id))

        conn.commit()
        conn.close()

    @app_commands.command(name='warn', description='Warn a user')
    @app_commands.describe(
        user='The user to warn',
        reason='Reason for the warning'
    )
    async def warn(self, interaction: discord.Interaction, user: discord.Member, reason: str = "No reason provided"):
        """Warn a user"""
        if not self.is_moderator(interaction.user):
            await interaction.response.send_message("❌ You don't have permission to use this command!", ephemeral=True)
            return

        # Can't warn yourself
        if user.id == interaction.user.id:
            await interaction.response.send_message("❌ You can't warn yourself!", ephemeral=True)
            return

        # Can't warn bots
        if user.bot:
            await interaction.response.send_message("❌ You can't warn bots!", ephemeral=True)
            return

        # Can't warn server owner
        if user.id == interaction.guild.owner_id:
            await interaction.response.send_message("❌ You can't warn the server owner!", ephemeral=True)
            return

        # Add warning
        self.add_warning(interaction.guild.id, user.id, interaction.user.id, reason)

        # Log action
        await self.log_action(interaction.guild, interaction.user, user, 'warn', reason)

        # Get warning count
        warnings = self.get_user_warnings(interaction.guild.id, user.id)
        warning_count = len(warnings)

        # Send response
        embed = discord.Embed(
            title="⚠️ User Warned",
            description=f"{user.mention} has been warned.",
            color=discord.Color.yellow()
        )
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Total Warnings", value=f"{warning_count}", inline=True)
        embed.add_field(name="Moderator", value=interaction.user.mention, inline=True)

        await interaction.response.send_message(embed=embed)

        # Try to DM the user
        try:
            dm_embed = discord.Embed(
                title=f"⚠️ Warning from {interaction.guild.name}",
                description=f"You have been warned by {interaction.user.name}",
                color=discord.Color.yellow()
            )
            dm_embed.add_field(name="Reason", value=reason, inline=False)
            dm_embed.add_field(name="Total Warnings", value=f"{warning_count}", inline=False)
            await user.send(embed=dm_embed)
        except:
            pass

        # Check for auto-timeout
        settings = self.get_guild_settings(interaction.guild.id)
        auto_timeout_warnings = settings.get('auto_timeout_warnings', 3)

        if warning_count >= auto_timeout_warnings:
            timeout_duration = settings.get('timeout_duration', 3600)
            try:
                await user.timeout(timedelta(seconds=timeout_duration), reason=f"Auto-timeout: {warning_count} warnings")
                await interaction.followup.send(f"⏱️ {user.mention} has been automatically timed out for {timeout_duration // 60} minutes due to {warning_count} warnings.")
                await self.log_action(interaction.guild, self.bot.user, user, 'timeout', f"Auto-timeout: {warning_count} warnings", f"{timeout_duration // 60} minutes")
            except:
                pass

    @app_commands.command(name='warnings', description='View warnings for a user')
    @app_commands.describe(user='The user to check warnings for')
    async def warnings(self, interaction: discord.Interaction, user: discord.Member):
        """View user warnings"""
        if not self.is_moderator(interaction.user):
            await interaction.response.send_message("❌ You don't have permission to use this command!", ephemeral=True)
            return

        warnings = self.get_user_warnings(interaction.guild.id, user.id)

        if not warnings:
            await interaction.response.send_message(f"✅ {user.mention} has no active warnings!", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"⚠️ Warnings for {user.name}",
            description=f"Total active warnings: **{len(warnings)}**",
            color=discord.Color.yellow()
        )

        for i, warning in enumerate(warnings, 1):
            warning_id, moderator_id, reason, timestamp = warning
            moderator = interaction.guild.get_member(moderator_id)
            moderator_name = moderator.name if moderator else f"User ID: {moderator_id}"

            # Parse timestamp
            try:
                dt = datetime.fromisoformat(timestamp)
                time_str = dt.strftime("%Y-%m-%d %H:%M")
            except:
                time_str = "Unknown"

            embed.add_field(
                name=f"Warning #{i} (ID: {warning_id})",
                value=f"**Reason:** {reason}\n**By:** {moderator_name}\n**Date:** {time_str}",
                inline=False
            )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='clearwarnings', description='Clear all warnings for a user')
    @app_commands.describe(user='The user to clear warnings for')
    async def clearwarnings(self, interaction: discord.Interaction, user: discord.Member):
        """Clear all warnings for a user"""
        if not self.is_moderator(interaction.user):
            await interaction.response.send_message("❌ You don't have permission to use this command!", ephemeral=True)
            return

        warnings = self.get_user_warnings(interaction.guild.id, user.id)

        if not warnings:
            await interaction.response.send_message(f"ℹ️ {user.mention} has no active warnings to clear!", ephemeral=True)
            return

        warning_count = len(warnings)
        self.clear_warnings(interaction.guild.id, user.id)

        await interaction.response.send_message(f"✅ Cleared **{warning_count}** warning(s) for {user.mention}")

    @app_commands.command(name='timeout', description='Timeout a user')
    @app_commands.describe(
        user='The user to timeout',
        duration='Duration in minutes',
        reason='Reason for the timeout'
    )
    async def timeout(self, interaction: discord.Interaction, user: discord.Member, duration: int, reason: str = "No reason provided"):
        """Timeout a user"""
        if not self.is_moderator(interaction.user):
            await interaction.response.send_message("❌ You don't have permission to use this command!", ephemeral=True)
            return

        if user.id == interaction.user.id:
            await interaction.response.send_message("❌ You can't timeout yourself!", ephemeral=True)
            return

        if user.bot:
            await interaction.response.send_message("❌ You can't timeout bots!", ephemeral=True)
            return

        if user.id == interaction.guild.owner_id:
            await interaction.response.send_message("❌ You can't timeout the server owner!", ephemeral=True)
            return

        if duration < 1 or duration > 40320:  # Max 28 days
            await interaction.response.send_message("❌ Duration must be between 1 minute and 28 days (40320 minutes)!", ephemeral=True)
            return

        try:
            await user.timeout(timedelta(minutes=duration), reason=reason)

            # Log action
            await self.log_action(interaction.guild, interaction.user, user, 'timeout', reason, f"{duration} minutes")

            embed = discord.Embed(
                title="⏱️ User Timed Out",
                description=f"{user.mention} has been timed out.",
                color=discord.Color.orange()
            )
            embed.add_field(name="Duration", value=f"{duration} minutes", inline=True)
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="Moderator", value=interaction.user.mention, inline=True)

            await interaction.response.send_message(embed=embed)

            # Try to DM the user
            try:
                dm_embed = discord.Embed(
                    title=f"⏱️ Timeout from {interaction.guild.name}",
                    description=f"You have been timed out by {interaction.user.name}",
                    color=discord.Color.orange()
                )
                dm_embed.add_field(name="Duration", value=f"{duration} minutes", inline=False)
                dm_embed.add_field(name="Reason", value=reason, inline=False)
                await user.send(embed=dm_embed)
            except:
                pass

        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to timeout this user!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(name='kick', description='Kick a user from the server')
    @app_commands.describe(
        user='The user to kick',
        reason='Reason for the kick'
    )
    async def kick(self, interaction: discord.Interaction, user: discord.Member, reason: str = "No reason provided"):
        """Kick a user"""
        if not self.is_moderator(interaction.user):
            await interaction.response.send_message("❌ You don't have permission to use this command!", ephemeral=True)
            return

        if user.id == interaction.user.id:
            await interaction.response.send_message("❌ You can't kick yourself!", ephemeral=True)
            return

        if user.bot:
            await interaction.response.send_message("❌ You can't kick bots with this command!", ephemeral=True)
            return

        if user.id == interaction.guild.owner_id:
            await interaction.response.send_message("❌ You can't kick the server owner!", ephemeral=True)
            return

        # Try to DM before kicking
        try:
            dm_embed = discord.Embed(
                title=f"👢 Kicked from {interaction.guild.name}",
                description=f"You have been kicked by {interaction.user.name}",
                color=discord.Color.red()
            )
            dm_embed.add_field(name="Reason", value=reason, inline=False)
            await user.send(embed=dm_embed)
        except:
            pass

        try:
            await user.kick(reason=reason)

            # Log action
            await self.log_action(interaction.guild, interaction.user, user, 'kick', reason)

            embed = discord.Embed(
                title="👢 User Kicked",
                description=f"{user.mention} has been kicked from the server.",
                color=discord.Color.red()
            )
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="Moderator", value=interaction.user.mention, inline=True)

            await interaction.response.send_message(embed=embed)

        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to kick this user!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(name='ban', description='Ban a user from the server')
    @app_commands.describe(
        user='The user to ban',
        reason='Reason for the ban',
        delete_messages='Delete messages from the last X days (0-7)'
    )
    async def ban(self, interaction: discord.Interaction, user: discord.Member, reason: str = "No reason provided", delete_messages: int = 0):
        """Ban a user"""
        if not self.is_moderator(interaction.user):
            await interaction.response.send_message("❌ You don't have permission to use this command!", ephemeral=True)
            return

        if user.id == interaction.user.id:
            await interaction.response.send_message("❌ You can't ban yourself!", ephemeral=True)
            return

        if user.bot:
            await interaction.response.send_message("❌ You can't ban bots with this command!", ephemeral=True)
            return

        if user.id == interaction.guild.owner_id:
            await interaction.response.send_message("❌ You can't ban the server owner!", ephemeral=True)
            return

        if delete_messages < 0 or delete_messages > 7:
            await interaction.response.send_message("❌ Delete messages days must be between 0 and 7!", ephemeral=True)
            return

        # Try to DM before banning
        try:
            dm_embed = discord.Embed(
                title=f"🔨 Banned from {interaction.guild.name}",
                description=f"You have been banned by {interaction.user.name}",
                color=discord.Color.dark_red()
            )
            dm_embed.add_field(name="Reason", value=reason, inline=False)
            await user.send(embed=dm_embed)
        except:
            pass

        try:
            await user.ban(reason=reason, delete_message_days=delete_messages)

            # Log action
            await self.log_action(interaction.guild, interaction.user, user, 'ban', reason)

            embed = discord.Embed(
                title="🔨 User Banned",
                description=f"{user.mention} has been banned from the server.",
                color=discord.Color.dark_red()
            )
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="Moderator", value=interaction.user.mention, inline=True)

            if delete_messages > 0:
                embed.add_field(name="Messages Deleted", value=f"Last {delete_messages} day(s)", inline=True)

            await interaction.response.send_message(embed=embed)

        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to ban this user!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    # Moderation settings group
    modsettings = app_commands.Group(name="modsettings", description="Configure moderation settings")

    @modsettings.command(name='setlogchannel', description='Set the mod log channel')
    @app_commands.describe(channel='The channel for moderation logs')
    async def set_log_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Set mod log channel"""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need administrator permission to use this command!", ephemeral=True)
            return

        guild_id = str(interaction.guild.id)
        if guild_id not in self.settings:
            self.settings[guild_id] = {}

        self.settings[guild_id]['mod_log_channel_id'] = channel.id
        self.save_settings()

        await interaction.response.send_message(f"✅ Mod log channel set to {channel.mention}")

    @modsettings.command(name='view', description='View current moderation settings')
    async def view_settings(self, interaction: discord.Interaction):
        """View moderation settings"""
        settings = self.get_guild_settings(interaction.guild.id)

        embed = discord.Embed(
            title="🛡️ Moderation Settings",
            color=discord.Color.blue()
        )

        # Mod log channel
        mod_log_channel_id = settings.get('mod_log_channel_id')
        if mod_log_channel_id:
            channel = interaction.guild.get_channel(mod_log_channel_id)
            embed.add_field(name="Mod Log Channel", value=channel.mention if channel else "Channel not found", inline=False)
        else:
            embed.add_field(name="Mod Log Channel", value="❌ Not set", inline=False)

        # Auto-timeout settings
        auto_timeout_warnings = settings.get('auto_timeout_warnings', 3)
        timeout_duration = settings.get('timeout_duration', 3600)

        embed.add_field(name="Auto-Timeout Warnings", value=f"{auto_timeout_warnings} warnings", inline=True)
        embed.add_field(name="Timeout Duration", value=f"{timeout_duration // 60} minutes", inline=True)

        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Moderation(bot))
