import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import json
import math
import time
from datetime import datetime

class Leveling(commands.Cog):
    """XP and leveling system with role rewards"""
    
    def __init__(self, bot):
        self.bot = bot
        self.db_file = 'data/leveling.db'
        self.settings_file = 'data/leveling_settings.json'
        self.init_database()
        self.settings = self.load_settings()
        self.xp_cooldowns = {}  # Track cooldowns per user
    
    def init_database(self):
        """Initialize SQLite database for leveling"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                guild_id INTEGER,
                user_id INTEGER,
                xp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 1,
                total_messages INTEGER DEFAULT 0,
                last_message_time REAL DEFAULT 0,
                PRIMARY KEY (guild_id, user_id)
            )
        ''')
        
        # Level roles table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS level_roles (
                guild_id INTEGER,
                level INTEGER,
                role_id INTEGER,
                PRIMARY KEY (guild_id, level)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def load_settings(self):
        """Load leveling settings from JSON"""
        try:
            with open(self.settings_file, 'r') as f:
                settings = json.load(f)
                # Ensure each guild has its own settings
                if not isinstance(settings, dict):
                    return self.get_default_settings()
                return settings
        except FileNotFoundError:
            return self.get_default_settings()
    
    def get_default_settings(self):
        """Get default settings structure"""
        return {
            'xp_per_message_min': 15,
            'xp_per_message_max': 25,
            'message_cooldown': 60,  # seconds
            'level_up_message': True,
        }
    
    def get_guild_setting(self, guild_id, key, default=None):
        """Get a specific guild setting"""
        guild_id_str = str(guild_id)
        if guild_id_str not in self.settings:
            self.settings[guild_id_str] = {}
        return self.settings[guild_id_str].get(key, default)
    
    def set_guild_setting(self, guild_id, key, value):
        """Set a specific guild setting"""
        guild_id_str = str(guild_id)
        if guild_id_str not in self.settings:
            self.settings[guild_id_str] = {}
        self.settings[guild_id_str][key] = value
        self.save_settings()
    
    def save_settings(self):
        """Save leveling settings to JSON"""
        with open(self.settings_file, 'w') as f:
            json.dump(self.settings, f, indent=4)
    
    def calculate_xp_for_level(self, level):
        """Calculate total XP needed to reach a level"""
        # Formula: 5 * (level ^ 2) + 50 * level + 100
        return 5 * (level ** 2) + 50 * level + 100
    
    def get_level_from_xp(self, xp):
        """Calculate level from total XP"""
        level = 1
        while xp >= self.calculate_xp_for_level(level):
            xp -= self.calculate_xp_for_level(level)
            level += 1
        return level, xp  # Returns (level, remaining_xp)
    
    def add_xp(self, guild_id, user_id, xp_amount):
        """Add XP to a user and return if they leveled up"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        # Get current user data
        cursor.execute('''
            SELECT xp, level FROM users 
            WHERE guild_id = ? AND user_id = ?
        ''', (guild_id, user_id))
        
        result = cursor.fetchone()
        
        if result:
            current_xp, current_level = result
            new_xp = current_xp + xp_amount
        else:
            # New user
            cursor.execute('''
                INSERT INTO users (guild_id, user_id, xp, level, total_messages)
                VALUES (?, ?, ?, 1, 0)
            ''', (guild_id, user_id, 0))
            current_xp = 0
            current_level = 1
            new_xp = xp_amount
        
        # Calculate new level
        new_level, remaining_xp = self.get_level_from_xp(new_xp)
        leveled_up = new_level > current_level
        
        # Update database
        cursor.execute('''
            UPDATE users 
            SET xp = ?, level = ?, total_messages = total_messages + 1, last_message_time = ?
            WHERE guild_id = ? AND user_id = ?
        ''', (new_xp, new_level, time.time(), guild_id, user_id))
        
        conn.commit()
        conn.close()
        
        return leveled_up, new_level, new_xp
    
    def get_user_data(self, guild_id, user_id):
        """Get user's leveling data"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT xp, level, total_messages FROM users
            WHERE guild_id = ? AND user_id = ?
        ''', (guild_id, user_id))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return {
                'xp': result[0],
                'level': result[1],
                'total_messages': result[2]
            }
        return None
    
    def get_leaderboard(self, guild_id, limit=10):
        """Get top users by level and XP"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT user_id, xp, level, total_messages
            FROM users
            WHERE guild_id = ?
            ORDER BY level DESC, xp DESC
            LIMIT ?
        ''', (guild_id, limit))
        
        results = cursor.fetchall()
        conn.close()
        
        return [
            {
                'user_id': r[0],
                'xp': r[1],
                'level': r[2],
                'total_messages': r[3]
            }
            for r in results
        ]
    
    def get_user_rank(self, guild_id, user_id):
        """Get user's rank in the server"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT COUNT(*) + 1 FROM users
            WHERE guild_id = ?
            AND (level > (SELECT level FROM users WHERE guild_id = ? AND user_id = ?)
                OR (level = (SELECT level FROM users WHERE guild_id = ? AND user_id = ?)
                    AND xp > (SELECT xp FROM users WHERE guild_id = ? AND user_id = ?)))
        ''', (guild_id, guild_id, user_id, guild_id, user_id, guild_id, user_id))
        
        rank = cursor.fetchone()[0]
        conn.close()
        
        return rank
    
    async def assign_level_roles(self, member, new_level):
        """Assign roles for reaching a level"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT role_id FROM level_roles
            WHERE guild_id = ? AND level <= ?
        ''', (member.guild.id, new_level))
        
        role_ids = [r[0] for r in cursor.fetchall()]
        conn.close()
        
        for role_id in role_ids:
            role = member.guild.get_role(role_id)
            if role and role not in member.roles:
                try:
                    await member.add_roles(role)
                    print(f"✅ Assigned level role {role.name} to {member.name}")
                except discord.Forbidden:
                    print(f"❌ No permission to assign role {role.name}")
    
    @commands.Cog.listener()
    async def on_message(self, message):
        """Award XP for messages"""
        # Ignore bots and DMs
        if message.author.bot or not message.guild:
            return
        
        guild_id = message.guild.id
        user_id = message.author.id
        
        # Check cooldown
        cooldown_key = f"{guild_id}_{user_id}"
        current_time = time.time()
        cooldown_duration = self.get_guild_setting(guild_id, 'message_cooldown', 60)
        
        if cooldown_key in self.xp_cooldowns:
            time_since_last = current_time - self.xp_cooldowns[cooldown_key]
            if time_since_last < cooldown_duration:
                return  # Still on cooldown
        
        # Update cooldown
        self.xp_cooldowns[cooldown_key] = current_time
        
        # Award random XP within configured range
        import random
        xp_min = self.get_guild_setting(guild_id, 'xp_per_message_min', 15)
        xp_max = self.get_guild_setting(guild_id, 'xp_per_message_max', 25)
        xp_gain = random.randint(xp_min, xp_max)
        
        leveled_up, new_level, total_xp = self.add_xp(guild_id, user_id, xp_gain)
        
        # Handle level up
        if leveled_up:
            # Assign level roles
            await self.assign_level_roles(message.author, new_level)
            
            # Send level up message
            if self.get_guild_setting(guild_id, 'level_up_message', True):
                # Get dedicated level-up channel
                level_channel_id = self.get_guild_setting(guild_id, 'level_up_channel', None)
                
                if level_channel_id:
                    level_channel = message.guild.get_channel(level_channel_id)
                    if not level_channel:
                        # Channel was deleted, fall back to current channel
                        level_channel = message.channel
                else:
                    # No dedicated channel set, use current channel
                    level_channel = message.channel
                
                xp_needed = self.calculate_xp_for_level(new_level)
                
                # Choose emoji based on milestone
                if new_level % 25 == 0:
                    emoji = "🎊"
                    title = f"🌟 MILESTONE! Level {new_level}!"
                elif new_level % 10 == 0:
                    emoji = "🎉"
                    title = f"🎉 Major Level Up!"
                else:
                    emoji = "⭐"
                    title = "Level Up!"
                
                embed = discord.Embed(
                    title=title,
                    description=f"{message.author.mention} just reached **Level {new_level}**! {emoji}",
                    color=discord.Color.gold() if new_level % 10 == 0 else discord.Color.green()
                )
                embed.set_thumbnail(url=message.author.display_avatar.url)
                embed.add_field(
                    name="Progress",
                    value=f"**Total XP:** {total_xp:,} 💎\n**Next Level:** {xp_needed:,} XP needed",
                    inline=False
                )
                
                try:
                    await level_channel.send(embed=embed)
                except discord.Forbidden:
                    # Bot doesn't have permission in that channel
                    print(f"❌ No permission to send level-up message in {level_channel.name}")
    
    @app_commands.command(name='rank', description='Check your or someone else\'s rank and level')
    @app_commands.describe(user='The user to check (optional, defaults to you)')
    async def rank(self, interaction: discord.Interaction, user: discord.Member = None):
        """Display user's rank, level, and XP"""
        target = user or interaction.user
        
        data = self.get_user_data(interaction.guild.id, target.id)
        
        if not data:
            await interaction.response.send_message(
                f"❌ {target.mention} hasn't earned any XP yet!",
                ephemeral=True
            )
            return
        
        rank = self.get_user_rank(interaction.guild.id, target.id)
        xp_needed = self.calculate_xp_for_level(data['level'])
        _, current_level_xp = self.get_level_from_xp(data['xp'])
        progress = (current_level_xp / xp_needed) * 100
        
        # Choose color based on level
        if data['level'] >= 50:
            color = discord.Color.gold()
        elif data['level'] >= 25:
            color = discord.Color.purple()
        elif data['level'] >= 10:
            color = discord.Color.blue()
        else:
            color = discord.Color.green()
        
        embed = discord.Embed(
            title=f"{target.display_name}'s Profile",
            description=f"Progress and statistics for {target.mention}",
            color=color
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        
        # Stats in a cleaner format
        stats = (
            f"**Rank:** #{rank} 🏆\n"
            f"**Level:** {data['level']} ⭐\n"
            f"**Total XP:** {data['xp']:,} 💎\n"
            f"**Messages:** {data['total_messages']:,} 💬"
        )
        embed.add_field(name="📊 Statistics", value=stats, inline=False)
        
        # Progress bar with better visuals
        bar_length = 15
        filled = int(bar_length * progress / 100)
        empty = bar_length - filled
        
        # Use block characters for smoother progress bar
        bar = "▰" * filled + "▱" * empty
        
        progress_text = (
            f"**Level {data['level']} → {data['level'] + 1}**\n"
            f"{bar} {progress:.0f}%\n"
            f"`{current_level_xp:,} / {xp_needed:,} XP`"
        )
        embed.add_field(name="📈 Level Progress", value=progress_text, inline=False)
        
        # Add a nice footer
        embed.set_footer(
            text=f"Keep chatting to level up! • XP needed: {xp_needed - current_level_xp:,}",
            icon_url=interaction.guild.icon.url if interaction.guild.icon else None
        )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name='leaderboard', description='View the server leaderboard')
    async def leaderboard(self, interaction: discord.Interaction):
        """Display server leaderboard"""
        top_users = self.get_leaderboard(interaction.guild.id, 10)
        
        if not top_users:
            await interaction.response.send_message("❌ No users on the leaderboard yet!", ephemeral=True)
            return
        
        embed = discord.Embed(
            title=f"🏆 {interaction.guild.name} Leaderboard",
            description="**Top 10 Members by Level**",
            color=discord.Color.gold()
        )
        
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
        
        leaderboard_text = ""
        
        for i, user_data in enumerate(top_users, 1):
            user = interaction.guild.get_member(user_data['user_id'])
            if not user:
                continue
            
            # Medals for top 3
            if i == 1:
                medal = "🥇"
            elif i == 2:
                medal = "🥈"
            elif i == 3:
                medal = "🥉"
            else:
                medal = f"`#{i:2}`"
            
            # Create a clean line for each user
            leaderboard_text += (
                f"{medal} **{user.display_name}**\n"
                f"     Level {user_data['level']} • {user_data['xp']:,} XP • {user_data['total_messages']:,} msgs\n\n"
            )
        
        embed.add_field(name="Rankings", value=leaderboard_text or "No users found", inline=False)
        embed.set_footer(text=f"Compete for the top spot! • Total users tracked: {len(top_users)}")
        
        await interaction.response.send_message(embed=embed)
    
    leveling_group = app_commands.Group(name="leveling", description="Manage leveling system settings")
    
    @leveling_group.command(name='setlevelrole', description='Assign a role reward for reaching a level')
    @app_commands.describe(
        level='The level to assign the role at',
        role='The role to give when reaching this level'
    )
    async def set_level_role(self, interaction: discord.Interaction, level: int, role: discord.Role):
        """Set a role reward for a specific level"""
        # Check permissions
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need Administrator permission to use this!", ephemeral=True)
            return
        
        if level < 1:
            await interaction.response.send_message("❌ Level must be 1 or higher!", ephemeral=True)
            return
        
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO level_roles (guild_id, level, role_id)
            VALUES (?, ?, ?)
        ''', (interaction.guild.id, level, role.id))
        
        conn.commit()
        conn.close()
        
        await interaction.response.send_message(
            f"✅ {role.mention} will now be given to users who reach **Level {level}**!"
        )
    
    @leveling_group.command(name='removelevelrole', description='Remove a level role reward')
    @app_commands.describe(level='The level to remove the role reward from')
    async def remove_level_role(self, interaction: discord.Interaction, level: int):
        """Remove a level role reward"""
        # Check permissions
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need Administrator permission to use this!", ephemeral=True)
            return
        
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
            DELETE FROM level_roles
            WHERE guild_id = ? AND level = ?
        ''', (interaction.guild.id, level))
        
        if cursor.rowcount == 0:
            await interaction.response.send_message(f"❌ No role reward found for Level {level}!", ephemeral=True)
        else:
            await interaction.response.send_message(f"✅ Removed role reward for Level {level}!")
        
        conn.commit()
        conn.close()
    
    @leveling_group.command(name='levelroles', description='List all level role rewards')
    async def list_level_roles(self, interaction: discord.Interaction):
        """List all configured level roles"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT level, role_id FROM level_roles
            WHERE guild_id = ?
            ORDER BY level ASC
        ''', (interaction.guild.id,))
        
        results = cursor.fetchall()
        conn.close()
        
        if not results:
            await interaction.response.send_message("❌ No level role rewards configured yet!", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="⭐ Level Role Rewards",
            description=f"Roles automatically assigned when reaching specific levels",
            color=discord.Color.purple()
        )
        
        roles_text = ""
        for level, role_id in results:
            role = interaction.guild.get_role(role_id)
            if role:
                roles_text += f"**Level {level}** → {role.mention}\n"
            else:
                roles_text += f"**Level {level}** → ⚠️ Role Deleted (ID: {role_id})\n"
        
        embed.add_field(name="Configured Rewards", value=roles_text or "None", inline=False)
        embed.set_footer(text=f"Total role rewards: {len(results)} • Use /leveling setlevelrole to add more")
        
        await interaction.response.send_message(embed=embed)
    
    @leveling_group.command(name='settings', description='View leveling system settings')
    async def view_settings(self, interaction: discord.Interaction):
        """View current leveling settings"""
        guild_id = interaction.guild.id
        
        embed = discord.Embed(
            title="⚙️ Leveling Settings",
            color=discord.Color.blue()
        )
        
        xp_min = self.get_guild_setting(guild_id, 'xp_per_message_min', 15)
        xp_max = self.get_guild_setting(guild_id, 'xp_per_message_max', 25)
        cooldown = self.get_guild_setting(guild_id, 'message_cooldown', 60)
        level_up_enabled = self.get_guild_setting(guild_id, 'level_up_message', True)
        level_channel_id = self.get_guild_setting(guild_id, 'level_up_channel', None)
        
        embed.add_field(
            name="XP Per Message",
            value=f"{xp_min}-{xp_max} XP",
            inline=True
        )
        embed.add_field(
            name="Message Cooldown",
            value=f"{cooldown} seconds",
            inline=True
        )
        embed.add_field(
            name="Level Up Messages",
            value="✅ Enabled" if level_up_enabled else "❌ Disabled",
            inline=True
        )
        
        if level_channel_id:
            channel = interaction.guild.get_channel(level_channel_id)
            channel_mention = channel.mention if channel else f"⚠️ Channel Deleted (ID: {level_channel_id})"
        else:
            channel_mention = "Same as message channel"
        
        embed.add_field(
            name="Level-Up Channel",
            value=channel_mention,
            inline=False
        )
        
        await interaction.response.send_message(embed=embed)
    
    @leveling_group.command(name='setchannel', description='Set a dedicated channel for level-up announcements')
    @app_commands.describe(channel='The channel where level-up messages will be posted')
    async def set_level_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Set the level-up announcement channel"""
        # Check permissions
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need Administrator permission to use this!", ephemeral=True)
            return
        
        self.set_guild_setting(interaction.guild.id, 'level_up_channel', channel.id)
        
        await interaction.response.send_message(
            f"✅ Level-up announcements will now be posted in {channel.mention}!"
        )
    
    @leveling_group.command(name='removechannel', description='Remove the dedicated level-up channel (use current channel)')
    async def remove_level_channel(self, interaction: discord.Interaction):
        """Remove the dedicated level-up channel"""
        # Check permissions
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ You need Administrator permission to use this!", ephemeral=True)
            return
        
        self.set_guild_setting(interaction.guild.id, 'level_up_channel', None)
        
        await interaction.response.send_message(
            "✅ Level-up announcements will now appear in the same channel where users level up!"
        )

async def setup(bot):
    await bot.add_cog(Leveling(bot))