import discord
from discord.ext import commands
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Bot configuration
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True  # Needed for role management
intents.reactions = True  # Needed for reaction roles

bot = commands.Bot(command_prefix='/', intents=intents, help_command=None)

@bot.event
async def on_ready():
    print(f'{bot.user} is now online!')
    print(f'Bot is in {len(bot.guilds)} server(s)')
    print('Loaded features:')
    for cog in bot.cogs:
        print(f'  - {cog}')

@bot.command(name='help')
async def help_command(ctx):
    """Display help information for all features"""
    embed = discord.Embed(
        title="🤖 CRXW Bot - All Features",
        description="Your all-in-one server management bot!",
        color=discord.Color.blue()
    )
    
    # Bump commands
    embed.add_field(
        name="📢 Bump Reminders",
        value="Automatically detects `/bump` and reminds @bumper in 2 hours\n"
              "`/bumpstatus` - Check when next bump is ready",
        inline=False
    )
    
    # Reaction role commands
    embed.add_field(
        name="⭐ Reaction Roles",
        value="`/reactionrole create <category> <#channel> \"<title>\" <emoji>:<role> ...` - Create reaction role message\n"
              "`/reactionrole list` - Show all reaction role messages\n"
              "`/reactionrole delete <message_id>` - Remove a reaction role setup\n"
              "`/reactionrole info <message_id>` - View role mappings",
        inline=False
    )
    
    embed.set_footer(text="Made with 🔥 | Self-hosted on Raspberry Pi")
    await ctx.send(embed=embed)

# Load all features
async def load_extensions():
    """Load all feature cogs"""
    features = ['bump', 'reaction_roles']
    for feature in features:
        try:
            await bot.load_extension(f'features.{feature}')
            print(f'✅ Loaded {feature}')
        except Exception as e:
            print(f'❌ Failed to load {feature}: {e}')

# Run the bot
if __name__ == "__main__":
    import asyncio
    
    TOKEN = os.getenv('DISCORD_BOT_TOKEN')
    if not TOKEN:
        print("❌ Error: DISCORD_BOT_TOKEN not found in .env file!")
        exit(1)
    
    async def main():
        async with bot:
            await load_extensions()
            await bot.start(TOKEN)
    
    asyncio.run(main())