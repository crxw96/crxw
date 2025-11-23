import discord
from discord.ext import commands
from discord import app_commands
import json
import re
from datetime import datetime, timedelta
from collections import defaultdict

class AutoMod(commands.Cog):
    """Automated moderation system for spam, links, and bad words"""

    def __init__(self, bot):
        self.bot = bot
        self.SETTINGS_FILE = 'data/automod_settings.json'
        self.settings = self.load_settings()

        # Spam tracking
        self.message_cache = defaultdict(list)  # {user_id: [timestamps]}
        self.duplicate_cache = defaultdict(list)  # {user_id: [(message, timestamp)]}

        # Raid tracking
        self.recent_joins = []  # [(user_id, timestamp)]

    def load_settings(self):
        """Load automod settings from JSON file"""
        try:
            with open(self.SETTINGS_FILE, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            # Default settings
            return {
                'spam_detection': {
                    'enabled': True,
                    'max_messages': 5,  # Max messages in time window
                    'time_window': 5,  # Seconds
                    'action': 'timeout',  # timeout, kick, ban, warn
                    'duration': 300  # Timeout duration in seconds (5 min)
                },
                'duplicate_spam': {
                    'enabled': True,
                    'max_duplicates': 3,  # Max identical messages
                    'time_window': 30,  # Seconds
                    'action': 'timeout',
                    'duration': 600  # 10 min
                },
                'mass_mentions': {
                    'enabled': True,
                    'max_mentions': 5,  # Max mentions per message
                    'action': 'timeout',
                    'duration': 600  # 10 min
                },
                'link_filter': {
                    'enabled': False,
                    'mode': 'blacklist',  # blacklist or whitelist
                    'blacklist': [],  # Blocked domains
                    'whitelist': [],  # Allowed domains (if whitelist mode)
                    'action': 'delete'  # delete, timeout, kick, ban
                },
                'bad_words': {
                    'enabled': False,
                    'words': [],  # List of bad words
                    'action': 'delete',  # delete, timeout, warn
                    'duration': 300  # Timeout duration if action is timeout
                },
                'raid_protection': {
                    'enabled': True,
                    'join_threshold': 5,  # Number of joins
                    'time_window': 10,  # Seconds
                    'action': 'kick'  # kick or ban
                },
                'immune_roles': [],  # Role IDs that bypass automod
                'log_channel_id': None  # Channel for automod logs
            }

    def save_settings(self):
        """Save automod settings to JSON file"""
        with open(self.SETTINGS_FILE, 'w') as f:
            json.dump(self.settings, f, indent=4)

    def is_mod_or_owner(self, member):
        """Check if user is mod or server owner"""
        if member.guild.owner_id == member.id:
            return True
        return member.guild_permissions.administrator or member.guild_permissions.manage_guild

    def is_immune(self, member):
        """Check if member is immune to automod"""
        # Mods and admins are immune
        if self.is_mod_or_owner(member):
            return True

        # Check immune roles
        immune_roles = self.settings.get(str(member.guild.id), {}).get('immune_roles', [])
        for role in member.roles:
            if role.id in immune_roles:
                return True

        return False

    async def log_action(self, guild, action_type: str, user: discord.Member, reason: str, moderator=None):
        """Log automod actions to log channel"""
        guild_id = str(guild.id)
        if guild_id not in self.settings:
            return

        log_channel_id = self.settings[guild_id].get('log_channel_id')
        if not log_channel_id:
            return

        log_channel = guild.get_channel(log_channel_id)
        if not log_channel:
            return

        # Color based on action
        colors = {
            'delete': discord.Color.orange(),
            'timeout': discord.Color.red(),
            'kick': discord.Color.dark_red(),
            'ban': discord.Color.from_rgb(139, 0, 0),
            'warn': discord.Color.yellow()
        }

        embed = discord.Embed(
            title=f"🤖 AutoMod: {action_type.title()}",
            description=f"**User:** {user.mention} ({user.name})\n**Reason:** {reason}",
            color=colors.get(action_type, discord.Color.blue()),
            timestamp=datetime.utcnow()
        )

        embed.set_thumbnail(url=user.display_avatar.url)
        embed.set_footer(text=f"User ID: {user.id}")

        try:
            await log_channel.send(embed=embed)
        except:
            pass

    async def take_action(self, message, action: str, reason: str, duration: int = None):
        """Execute moderation action"""
        if action == 'delete':
            try:
                await message.delete()
                await self.log_action(message.guild, 'delete', message.author, reason)
            except:
                pass

        elif action == 'timeout' and duration:
            try:
                timeout_until = datetime.utcnow() + timedelta(seconds=duration)
                await message.author.timeout(timeout_until, reason=f"AutoMod: {reason}")
                await message.delete()
                await self.log_action(message.guild, 'timeout', message.author, f"{reason} (Duration: {duration}s)")

                # Try to DM user
                try:
                    await message.author.send(
                        f"⚠️ You have been timed out in **{message.guild.name}**\n"
                        f"**Reason:** {reason}\n"
                        f"**Duration:** {duration} seconds"
                    )
                except:
                    pass
            except:
                pass

        elif action == 'kick':
            try:
                await message.author.kick(reason=f"AutoMod: {reason}")
                await message.delete()
                await self.log_action(message.guild, 'kick', message.author, reason)
            except:
                pass

        elif action == 'ban':
            try:
                await message.author.ban(reason=f"AutoMod: {reason}", delete_message_seconds=86400)
                await message.delete()
                await self.log_action(message.guild, 'ban', message.author, reason)
            except:
                pass

        elif action == 'warn':
            await self.log_action(message.guild, 'warn', message.author, reason)

    def extract_urls(self, text: str):
        """Extract URLs from text"""
        url_pattern = r'https?://(?:www\.)?([a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)'
        matches = re.findall(url_pattern, text)
        return [match for match in matches]

    @commands.Cog.listener()
    async def on_message(self, message):
        """Main automod message listener"""
        # Ignore bots
        if message.author.bot:
            return

        # Ignore DMs
        if not message.guild:
            return

        # Check if member is immune
        if self.is_immune(message.author):
            return

        guild_id = str(message.guild.id)

        # Initialize guild settings if not exists
        if guild_id not in self.settings:
            self.settings[guild_id] = self.load_settings()

        guild_settings = self.settings[guild_id]

        # --- Spam Detection ---
        if guild_settings['spam_detection']['enabled']:
            user_id = message.author.id
            now = datetime.now()

            # Add message timestamp
            self.message_cache[user_id].append(now)

            # Remove old timestamps outside time window
            time_window = guild_settings['spam_detection']['time_window']
            cutoff = now - timedelta(seconds=time_window)
            self.message_cache[user_id] = [ts for ts in self.message_cache[user_id] if ts > cutoff]

            # Check if exceeded limit
            max_messages = guild_settings['spam_detection']['max_messages']
            if len(self.message_cache[user_id]) > max_messages:
                action = guild_settings['spam_detection']['action']
                duration = guild_settings['spam_detection']['duration']
                await self.take_action(message, action, f"Spam: {len(self.message_cache[user_id])} messages in {time_window}s", duration)
                self.message_cache[user_id].clear()
                return

        # --- Duplicate Message Spam ---
        if guild_settings['duplicate_spam']['enabled']:
            user_id = message.author.id
            now = datetime.now()

            # Add message content and timestamp
            self.duplicate_cache[user_id].append((message.content, now))

            # Remove old messages outside time window
            time_window = guild_settings['duplicate_spam']['time_window']
            cutoff = now - timedelta(seconds=time_window)
            self.duplicate_cache[user_id] = [(msg, ts) for msg, ts in self.duplicate_cache[user_id] if ts > cutoff]

            # Count identical messages
            content_counts = {}
            for msg_content, _ in self.duplicate_cache[user_id]:
                content_counts[msg_content] = content_counts.get(msg_content, 0) + 1

            max_duplicates = guild_settings['duplicate_spam']['max_duplicates']
            for content, count in content_counts.items():
                if count > max_duplicates:
                    action = guild_settings['duplicate_spam']['action']
                    duration = guild_settings['duplicate_spam']['duration']
                    await self.take_action(message, action, f"Duplicate spam: {count} identical messages", duration)
                    self.duplicate_cache[user_id].clear()
                    return

        # --- Mass Mentions ---
        if guild_settings['mass_mentions']['enabled']:
            mention_count = len(message.mentions) + len(message.role_mentions)
            max_mentions = guild_settings['mass_mentions']['max_mentions']

            if mention_count > max_mentions:
                action = guild_settings['mass_mentions']['action']
                duration = guild_settings['mass_mentions']['duration']
                await self.take_action(message, action, f"Mass mentions: {mention_count} mentions", duration)
                return

        # --- Link Filter ---
        if guild_settings['link_filter']['enabled']:
            urls = self.extract_urls(message.content)

            if urls:
                mode = guild_settings['link_filter']['mode']
                blacklist = guild_settings['link_filter']['blacklist']
                whitelist = guild_settings['link_filter']['whitelist']

                blocked = False

                if mode == 'blacklist':
                    # Block if any URL matches blacklist
                    for url in urls:
                        for blocked_domain in blacklist:
                            if blocked_domain.lower() in url.lower():
                                blocked = True
                                break
                        if blocked:
                            break

                elif mode == 'whitelist':
                    # Block if any URL is NOT in whitelist
                    for url in urls:
                        allowed = False
                        for allowed_domain in whitelist:
                            if allowed_domain.lower() in url.lower():
                                allowed = True
                                break
                        if not allowed:
                            blocked = True
                            break

                if blocked:
                    action = guild_settings['link_filter']['action']
                    await self.take_action(message, action, f"Blocked link: {urls[0]}")
                    return

        # --- Bad Words Filter ---
        if guild_settings['bad_words']['enabled']:
            content_lower = message.content.lower()
            bad_words = guild_settings['bad_words']['words']

            for bad_word in bad_words:
                if bad_word.lower() in content_lower:
                    action = guild_settings['bad_words']['action']
                    duration = guild_settings['bad_words']['duration']
                    await self.take_action(message, action, f"Inappropriate language", duration)
                    return

    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Raid protection - detect mass joins"""
        guild_id = str(member.guild.id)

        if guild_id not in self.settings:
            return

        guild_settings = self.settings[guild_id]

        if not guild_settings['raid_protection']['enabled']:
            return

        now = datetime.now()
        self.recent_joins.append((member.id, now))

        # Remove old joins outside time window
        time_window = guild_settings['raid_protection']['time_window']
        cutoff = now - timedelta(seconds=time_window)
        self.recent_joins = [(uid, ts) for uid, ts in self.recent_joins if ts > cutoff]

        # Check if raid detected
        join_threshold = guild_settings['raid_protection']['join_threshold']

        if len(self.recent_joins) >= join_threshold:
            action = guild_settings['raid_protection']['action']

            # Take action on the joining member
            try:
                if action == 'kick':
                    await member.kick(reason="AutoMod: Raid protection")
                elif action == 'ban':
                    await member.ban(reason="AutoMod: Raid protection", delete_message_seconds=0)

                await self.log_action(member.guild, action, member, f"Raid protection: {len(self.recent_joins)} joins in {time_window}s")
            except:
                pass

    automod = app_commands.Group(name="automod", description="Configure auto-moderation settings")

    @automod.command(name='spam', description='Configure spam detection')
    @app_commands.describe(
        enabled='Enable or disable spam detection',
        max_messages='Max messages allowed in time window',
        time_window='Time window in seconds',
        action='Action to take (delete, timeout, kick, ban)',
        duration='Timeout duration in seconds (if action is timeout)'
    )
    async def configure_spam(
        self,
        interaction: discord.Interaction,
        enabled: bool,
        max_messages: int = None,
        time_window: int = None,
        action: str = None,
        duration: int = None
    ):
        """Configure spam detection settings"""
        if not self.is_mod_or_owner(interaction.user):
            await interaction.response.send_message("❌ You need to be a moderator to configure automod!", ephemeral=True)
            return

        guild_id = str(interaction.guild.id)

        if guild_id not in self.settings:
            self.settings[guild_id] = self.load_settings()

        if 'spam_detection' not in self.settings[guild_id]:
            self.settings[guild_id]['spam_detection'] = {}

        self.settings[guild_id]['spam_detection']['enabled'] = enabled

        if max_messages is not None:
            self.settings[guild_id]['spam_detection']['max_messages'] = max_messages
        if time_window is not None:
            self.settings[guild_id]['spam_detection']['time_window'] = time_window
        if action is not None:
            if action not in ['delete', 'timeout', 'kick', 'ban']:
                await interaction.response.send_message("❌ Invalid action! Use: delete, timeout, kick, or ban", ephemeral=True)
                return
            self.settings[guild_id]['spam_detection']['action'] = action
        if duration is not None:
            self.settings[guild_id]['spam_detection']['duration'] = duration

        self.save_settings()

        status = "✅ Enabled" if enabled else "❌ Disabled"
        await interaction.response.send_message(
            f"{status} spam detection!\n"
            f"**Max messages:** {self.settings[guild_id]['spam_detection']['max_messages']}\n"
            f"**Time window:** {self.settings[guild_id]['spam_detection']['time_window']}s\n"
            f"**Action:** {self.settings[guild_id]['spam_detection']['action']}"
        )

    @automod.command(name='links', description='Configure link filtering')
    @app_commands.describe(
        enabled='Enable or disable link filtering',
        mode='Filter mode (blacklist or whitelist)',
        domains='Comma-separated list of domains',
        action='Action to take (delete, timeout, kick, ban)'
    )
    async def configure_links(
        self,
        interaction: discord.Interaction,
        enabled: bool,
        mode: str = None,
        domains: str = None,
        action: str = None
    ):
        """Configure link filtering"""
        if not self.is_mod_or_owner(interaction.user):
            await interaction.response.send_message("❌ You need to be a moderator to configure automod!", ephemeral=True)
            return

        guild_id = str(interaction.guild.id)

        if guild_id not in self.settings:
            self.settings[guild_id] = self.load_settings()

        if 'link_filter' not in self.settings[guild_id]:
            self.settings[guild_id]['link_filter'] = {'enabled': False, 'mode': 'blacklist', 'blacklist': [], 'whitelist': [], 'action': 'delete'}

        self.settings[guild_id]['link_filter']['enabled'] = enabled

        if mode is not None:
            if mode not in ['blacklist', 'whitelist']:
                await interaction.response.send_message("❌ Invalid mode! Use: blacklist or whitelist", ephemeral=True)
                return
            self.settings[guild_id]['link_filter']['mode'] = mode

        if domains is not None:
            domain_list = [d.strip() for d in domains.split(',')]
            if self.settings[guild_id]['link_filter']['mode'] == 'blacklist':
                self.settings[guild_id]['link_filter']['blacklist'] = domain_list
            else:
                self.settings[guild_id]['link_filter']['whitelist'] = domain_list

        if action is not None:
            if action not in ['delete', 'timeout', 'kick', 'ban']:
                await interaction.response.send_message("❌ Invalid action! Use: delete, timeout, kick, or ban", ephemeral=True)
                return
            self.settings[guild_id]['link_filter']['action'] = action

        self.save_settings()

        status = "✅ Enabled" if enabled else "❌ Disabled"
        current_mode = self.settings[guild_id]['link_filter']['mode']
        domain_key = 'blacklist' if current_mode == 'blacklist' else 'whitelist'
        current_domains = self.settings[guild_id]['link_filter'][domain_key]

        await interaction.response.send_message(
            f"{status} link filtering!\n"
            f"**Mode:** {current_mode}\n"
            f"**Domains:** {', '.join(current_domains) if current_domains else 'None'}\n"
            f"**Action:** {self.settings[guild_id]['link_filter']['action']}"
        )

    @automod.command(name='badwords', description='Configure bad word filter')
    @app_commands.describe(
        enabled='Enable or disable bad word filter',
        words='Comma-separated list of words to filter',
        action='Action to take (delete, timeout, warn)'
    )
    async def configure_badwords(
        self,
        interaction: discord.Interaction,
        enabled: bool,
        words: str = None,
        action: str = None
    ):
        """Configure bad word filter"""
        if not self.is_mod_or_owner(interaction.user):
            await interaction.response.send_message("❌ You need to be a moderator to configure automod!", ephemeral=True)
            return

        guild_id = str(interaction.guild.id)

        if guild_id not in self.settings:
            self.settings[guild_id] = self.load_settings()

        if 'bad_words' not in self.settings[guild_id]:
            self.settings[guild_id]['bad_words'] = {'enabled': False, 'words': [], 'action': 'delete', 'duration': 300}

        self.settings[guild_id]['bad_words']['enabled'] = enabled

        if words is not None:
            word_list = [w.strip() for w in words.split(',')]
            self.settings[guild_id]['bad_words']['words'] = word_list

        if action is not None:
            if action not in ['delete', 'timeout', 'warn']:
                await interaction.response.send_message("❌ Invalid action! Use: delete, timeout, or warn", ephemeral=True)
                return
            self.settings[guild_id]['bad_words']['action'] = action

        self.save_settings()

        status = "✅ Enabled" if enabled else "❌ Disabled"
        word_count = len(self.settings[guild_id]['bad_words']['words'])

        await interaction.response.send_message(
            f"{status} bad word filter!\n"
            f"**Words filtered:** {word_count}\n"
            f"**Action:** {self.settings[guild_id]['bad_words']['action']}"
        )

    @automod.command(name='raid', description='Configure raid protection')
    @app_commands.describe(
        enabled='Enable or disable raid protection',
        join_threshold='Number of joins to trigger protection',
        time_window='Time window in seconds',
        action='Action to take (kick or ban)'
    )
    async def configure_raid(
        self,
        interaction: discord.Interaction,
        enabled: bool,
        join_threshold: int = None,
        time_window: int = None,
        action: str = None
    ):
        """Configure raid protection"""
        if not self.is_mod_or_owner(interaction.user):
            await interaction.response.send_message("❌ You need to be a moderator to configure automod!", ephemeral=True)
            return

        guild_id = str(interaction.guild.id)

        if guild_id not in self.settings:
            self.settings[guild_id] = self.load_settings()

        if 'raid_protection' not in self.settings[guild_id]:
            self.settings[guild_id]['raid_protection'] = {'enabled': False, 'join_threshold': 5, 'time_window': 10, 'action': 'kick'}

        self.settings[guild_id]['raid_protection']['enabled'] = enabled

        if join_threshold is not None:
            self.settings[guild_id]['raid_protection']['join_threshold'] = join_threshold
        if time_window is not None:
            self.settings[guild_id]['raid_protection']['time_window'] = time_window
        if action is not None:
            if action not in ['kick', 'ban']:
                await interaction.response.send_message("❌ Invalid action! Use: kick or ban", ephemeral=True)
                return
            self.settings[guild_id]['raid_protection']['action'] = action

        self.save_settings()

        status = "✅ Enabled" if enabled else "❌ Disabled"
        await interaction.response.send_message(
            f"{status} raid protection!\n"
            f"**Join threshold:** {self.settings[guild_id]['raid_protection']['join_threshold']}\n"
            f"**Time window:** {self.settings[guild_id]['raid_protection']['time_window']}s\n"
            f"**Action:** {self.settings[guild_id]['raid_protection']['action']}"
        )

    @automod.command(name='logchannel', description='Set the automod log channel')
    @app_commands.describe(channel='Channel for automod logs')
    async def set_log_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Set the automod log channel"""
        if not self.is_mod_or_owner(interaction.user):
            await interaction.response.send_message("❌ You need to be a moderator to configure automod!", ephemeral=True)
            return

        guild_id = str(interaction.guild.id)

        if guild_id not in self.settings:
            self.settings[guild_id] = self.load_settings()

        self.settings[guild_id]['log_channel_id'] = channel.id
        self.save_settings()

        await interaction.response.send_message(f"✅ Automod logs will be sent to {channel.mention}")

    @automod.command(name='settings', description='View all automod settings')
    async def view_settings(self, interaction: discord.Interaction):
        """View current automod settings"""
        guild_id = str(interaction.guild.id)

        if guild_id not in self.settings:
            await interaction.response.send_message("❌ No automod settings found! Use `/automod` commands to configure.", ephemeral=True)
            return

        settings = self.settings[guild_id]

        embed = discord.Embed(
            title="🤖 AutoMod Settings",
            color=discord.Color.blue()
        )

        # Spam detection
        spam = settings.get('spam_detection', {})
        status = "✅ Enabled" if spam.get('enabled') else "❌ Disabled"
        embed.add_field(
            name="📨 Spam Detection",
            value=f"{status}\n"
                  f"Max messages: {spam.get('max_messages', 5)}\n"
                  f"Time window: {spam.get('time_window', 5)}s\n"
                  f"Action: {spam.get('action', 'timeout')}",
            inline=True
        )

        # Duplicate spam
        dup = settings.get('duplicate_spam', {})
        status = "✅ Enabled" if dup.get('enabled') else "❌ Disabled"
        embed.add_field(
            name="📋 Duplicate Spam",
            value=f"{status}\n"
                  f"Max duplicates: {dup.get('max_duplicates', 3)}\n"
                  f"Time window: {dup.get('time_window', 30)}s\n"
                  f"Action: {dup.get('action', 'timeout')}",
            inline=True
        )

        # Mass mentions
        mentions = settings.get('mass_mentions', {})
        status = "✅ Enabled" if mentions.get('enabled') else "❌ Disabled"
        embed.add_field(
            name="📢 Mass Mentions",
            value=f"{status}\n"
                  f"Max mentions: {mentions.get('max_mentions', 5)}\n"
                  f"Action: {mentions.get('action', 'timeout')}",
            inline=True
        )

        # Link filter
        links = settings.get('link_filter', {})
        status = "✅ Enabled" if links.get('enabled') else "❌ Disabled"
        mode = links.get('mode', 'blacklist')
        domain_key = 'blacklist' if mode == 'blacklist' else 'whitelist'
        domains = links.get(domain_key, [])
        embed.add_field(
            name="🔗 Link Filter",
            value=f"{status}\n"
                  f"Mode: {mode}\n"
                  f"Domains: {len(domains)}\n"
                  f"Action: {links.get('action', 'delete')}",
            inline=True
        )

        # Bad words
        badwords = settings.get('bad_words', {})
        status = "✅ Enabled" if badwords.get('enabled') else "❌ Disabled"
        embed.add_field(
            name="🚫 Bad Words",
            value=f"{status}\n"
                  f"Words filtered: {len(badwords.get('words', []))}\n"
                  f"Action: {badwords.get('action', 'delete')}",
            inline=True
        )

        # Raid protection
        raid = settings.get('raid_protection', {})
        status = "✅ Enabled" if raid.get('enabled') else "❌ Disabled"
        embed.add_field(
            name="🛡️ Raid Protection",
            value=f"{status}\n"
                  f"Join threshold: {raid.get('join_threshold', 5)}\n"
                  f"Time window: {raid.get('time_window', 10)}s\n"
                  f"Action: {raid.get('action', 'kick')}",
            inline=True
        )

        # Log channel
        log_channel_id = settings.get('log_channel_id')
        if log_channel_id:
            log_channel = interaction.guild.get_channel(log_channel_id)
            log_text = log_channel.mention if log_channel else "Not set"
        else:
            log_text = "Not set"

        embed.add_field(name="📝 Log Channel", value=log_text, inline=False)

        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(AutoMod(bot))
