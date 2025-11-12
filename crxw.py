import discord
from discord.ext import commands
from discord import app_commands
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Bot configuration
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.reactions = True

class Bot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='/', intents=intents, help_command=None)
        self.initial_extensions = ['features.bump', 'features.reaction_roles', 'features.leveling']
    
    async def setup_hook(self):
        """Load all features when bot starts"""
        for extension in self.initial_extensions:
            try:
                await self.load_extension(extension)
                print(f'✅ Loaded {extension}')
            except Exception as e:
                print(f'❌ Failed to load {extension}: {e}')
        
        # Sync commands with Discord
        print("Syncing commands with Discord...")
        await self.tree.sync()
        print("✅ Commands synced!")

bot = Bot()

@bot.event
async def on_ready():
    print(f'{bot.user} is now online!')
    print(f'Bot is in {len(bot.guilds)} server(s)')
    print('Loaded features:')
    for cog in bot.cogs:
        print(f'  - {cog}')

@bot.tree.command(name='help', description='Show all bot commands and features')
async def help_command(interaction: discord.Interaction):
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
        value="`/reactionrole create` - Create a reaction role message\n"
              "`/reactionrole list` - Show all reaction role messages\n"
              "`/reactionrole delete` - Remove a reaction role setup\n"
              "`/reactionrole info` - View role mappings",
        inline=False
    )
    
    # Leveling commands
    embed.add_field(
        name="📊 Leveling System",
        value="`/rank` - View your rank and level\n"
              "`/leaderboard` - Server leaderboard\n"
              "`/leveling setlevelrole` - Set role rewards (admin)\n"
              "`/leveling levelroles` - List level role rewards\n"
              "`/leveling settings` - View leveling settings",
        inline=False
    )
    
    embed.set_footer(text="Made with 🔥 | Self-hosted on Raspberry Pi")
    await interaction.response.send_message(embed=embed)

# Run the bot
if __name__ == "__main__":
    TOKEN = os.getenv('DISCORD_BOT_TOKEN')
    if not TOKEN:
        print("❌ Error: DISCORD_BOT_TOKEN not found in .env file!")
        exit(1)
    
    bot.run(TOKEN)