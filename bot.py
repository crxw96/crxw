import discord
from discord.ext import commands, tasks
import os
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Bot configuration
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix='/', intents=intents, help_command=None)

# File to store bump data
BUMP_DATA_FILE = 'bump_data.json'

def load_bump_data():
    """Load bump data from JSON file"""
    try:
        with open(BUMP_DATA_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_bump_data(data):
    """Save bump data to JSON file"""
    with open(BUMP_DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

@bot.event
async def on_ready():
    print(f'{bot.user} is now online!')
    print(f'Bot is in {len(bot.guilds)} server(s)')
    check_bump_reminders.start()  # Start the reminder checker

@bot.event
async def on_message(message):
    """
    Listen for Disboard's bump confirmation message.
    Disboard bot ID: 302050872383242240
    """
    # Ignore messages from this bot
    if message.author.id == bot.user.id:
        return
    
    # Check if message is from Disboard bot
    DISBOARD_BOT_ID = 302050872383242240
    if message.author.id == DISBOARD_BOT_ID:
        # Check if it's a successful bump message
        # Disboard sends an embed with "Bump done!" in the description
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
                bump_data = load_bump_data()
                
                # Store the bump information
                bump_data[guild_id] = {
                    'channel_id': channel_id,
                    'bump_time': bump_ready_time.isoformat(),
                    'reminded': False
                }
                
                # Save to file
                save_bump_data(bump_data)
                
                # Get bumper role
                bumper_role_id = get_bumper_role_id(message.guild)
                
                # Confirm to users
                if bumper_role_id:
                    await message.channel.send(f"✅ Bump detected! I'll remind <@&{bumper_role_id}> in 2 hours.")
                else:
                    await message.channel.send(f"✅ Bump detected! I'll send a reminder in 2 hours. (Create a @bumper role to get pinged!)")
    
    # Process commands (important for other bot commands to work)
    await bot.process_commands(message)

@tasks.loop(minutes=1)
async def check_bump_reminders():
    """Check every minute if any bump reminders are due"""
    bump_data = load_bump_data()
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
            guild = bot.get_guild(int(guild_id))
            if guild is None:
                continue
            
            channel = guild.get_channel(data['channel_id'])
            if channel is None:
                continue
            
            # Get the bumper role
            bumper_role_id = get_bumper_role_id(guild)
            if bumper_role_id is None:
                await channel.send("⚠️ Bump is ready, but I couldn't find the @bumper role!")
            else:
                await channel.send(f"🔔 <@&{bumper_role_id}> The server is ready to be bumped again!")
            
            # Mark as reminded
            data['reminded'] = True
            bump_data[guild_id] = data
            save_bump_data(bump_data)

def get_bumper_role_id(guild):
    """Find the bumper role in the guild"""
    for role in guild.roles:
        if role.name.lower() == 'bumper':
            return role.id
    return None

@bot.command(name='bumpstatus')
async def bump_status(ctx):
    """Check when the next bump reminder is due"""
    guild_id = str(ctx.guild.id)
    bump_data = load_bump_data()
    
    if guild_id not in bump_data:
        await ctx.send("❌ No bump recorded yet. Use `!bump` after bumping the server!")
        return
    
    data = bump_data[guild_id]
    
    if data.get('reminded', False):
        await ctx.send("✅ Bump reminder has already been sent. Use `!bump` after your next bump!")
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

@bot.command(name='help')
async def help_command(ctx):
    """Display help information"""
    embed = discord.Embed(
        title="🤖 Bump Bot Commands",
        description="Automatic bump reminder bot - detects when you use `/bump` with Disboard!",
        color=discord.Color.blue()
    )
    embed.add_field(
        name="Automatic Detection",
        value="Just use `/bump` normally with Disboard - I'll detect it and remind @bumper in 2 hours!",
        inline=False
    )
    embed.add_field(
        name="!bumpstatus",
        value="Check when the next bump reminder is due",
        inline=False
    )
    embed.add_field(
        name="!help",
        value="Show this help message",
        inline=False
    )
    embed.set_footer(text="Made with 🔥 | Self-hosted on Raspberry Pi")
    
    await ctx.send(embed=embed)

# Run the bot
if __name__ == "__main__":
    TOKEN = os.getenv('DISCORD_BOT_TOKEN')
    if not TOKEN:
        print("❌ Error: DISCORD_BOT_TOKEN not found in .env file!")
        exit(1)
    
    bot.run(TOKEN)
