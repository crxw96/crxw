import discord
from discord.ext import commands, tasks
import json
from datetime import datetime, timedelta

class BumpReminder(commands.Cog):
    """Automatic bump reminder system that detects Disboard bumps"""
    
    def __init__(self, bot):
        self.bot = bot
        self.BUMP_DATA_FILE = 'data/bump_data.json'
        self.DISBOARD_BOT_ID = 302050872383242240
        self.check_bump_reminders.start()
    
    def cog_unload(self):
        self.check_bump_reminders.cancel()
    
    def load_bump_data(self):
        """Load bump data from JSON file"""
        try:
            with open(self.BUMP_DATA_FILE, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
    
    def save_bump_data(self, data):
        """Save bump data to JSON file"""
        with open(self.BUMP_DATA_FILE, 'w') as f:
            json.dump(data, f, indent=4)
    
    def get_bumper_role_id(self, guild):
        """Find the bumper role in the guild"""
        for role in guild.roles:
            if role.name.lower() == 'bumper':
                return role.id
        return None
    
    @commands.Cog.listener()
    async def on_message(self, message):
        """Listen for Disboard's bump confirmation message"""
        # Ignore messages from this bot
        if message.author.id == self.bot.user.id:
            return
        
        # Check if message is from Disboard bot
        if message.author.id == self.DISBOARD_BOT_ID:
            # Check if it's a successful bump message
            if message.embeds:
                embed = message.embeds[0]
                description = embed.description if embed.description else ""
                
                # Look for bump success indicators
                if "Bump done" in description or ":thumbsup:" in description:
                    # Get the server ID and channel ID
                    guild_id = str(message.guild.id)
                    channel_id = message.channel.id
                    
                    # Calculate when the bump will be ready (2 hours from now)
                    bump_ready_time = datetime.now() + timedelta(hours=2)
                    
                    # Load current bump data
                    bump_data = self.load_bump_data()
                    
                    # Store the bump information
                    bump_data[guild_id] = {
                        'channel_id': channel_id,
                        'bump_time': bump_ready_time.isoformat(),
                        'reminded': False
                    }
                    
                    # Save to file
                    self.save_bump_data(bump_data)
                    
                    # Get bumper role
                    bumper_role_id = self.get_bumper_role_id(message.guild)
                    
                    # Confirm to users
                    if bumper_role_id:
                        await message.channel.send(f"✅ Bump detected! I'll remind <@&{bumper_role_id}> in 2 hours.")
                    else:
                        await message.channel.send(f"✅ Bump detected! I'll send a reminder in 2 hours. (Create a @bumper role to get pinged!)")
    
    @tasks.loop(minutes=1)
    async def check_bump_reminders(self):
        """Check every minute if any bump reminders are due"""
        bump_data = self.load_bump_data()
        current_time = datetime.now()
        
        for guild_id, data in list(bump_data.items()):
            # Skip if already reminded
            if data.get('reminded', False):
                continue
            
            # Parse the bump ready time
            bump_ready_time = datetime.fromisoformat(data['bump_time'])
            
            # Check if it's time to remind
            if current_time >= bump_ready_time:
                # Get the guild and channel
                guild = self.bot.get_guild(int(guild_id))
                if guild is None:
                    continue
                
                channel = guild.get_channel(data['channel_id'])
                if channel is None:
                    continue
                
                # Get the bumper role
                bumper_role_id = self.get_bumper_role_id(guild)
                if bumper_role_id is None:
                    await channel.send("⚠️ Bump is ready, but I couldn't find the @bumper role!")
                else:
                    await channel.send(f"🔔 <@&{bumper_role_id}> The server is ready to be bumped again!")
                
                # Mark as reminded
                data['reminded'] = True
                bump_data[guild_id] = data
                self.save_bump_data(bump_data)
    
    @check_bump_reminders.before_loop
    async def before_check_bump_reminders(self):
        """Wait until bot is ready before starting the loop"""
        await self.bot.wait_until_ready()
    
    @commands.command(name='bumpstatus')
    async def bump_status(self, ctx):
        """Check when the next bump reminder is due"""
        guild_id = str(ctx.guild.id)
        bump_data = self.load_bump_data()
        
        if guild_id not in bump_data:
            await ctx.send("❌ No bump recorded yet. Wait for someone to use `/bump` with Disboard!")
            return
        
        data = bump_data[guild_id]
        
        if data.get('reminded', False):
            await ctx.send("✅ Bump reminder has already been sent. Use `/bump` again after bumping!")
            return
        
        bump_ready_time = datetime.fromisoformat(data['bump_time'])
        time_remaining = bump_ready_time - datetime.now()
        
        if time_remaining.total_seconds() <= 0:
            await ctx.send("🔔 The bump is ready right now!")
        else:
            minutes_remaining = int(time_remaining.total_seconds() / 60)
            hours = minutes_remaining // 60
            minutes = minutes_remaining % 60
            await ctx.send(f"⏳ Bump will be ready in **{hours}h {minutes}m**")

async def setup(bot):
    await bot.add_cog(BumpReminder(bot))