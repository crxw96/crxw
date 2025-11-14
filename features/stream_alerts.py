import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import os
import aiohttp
from datetime import datetime, timedelta

class StreamAlerts(commands.Cog):
    """Stream and YouTube notification system"""

    def __init__(self, bot):
        self.bot = bot
        self.DATA_FILE = 'data/stream_alerts.json'
        self.settings = self.load_settings()

        # Track last known state to avoid duplicate notifications
        self.live_status = {}  # guild_id -> bool
        self.last_video_ids = {}  # guild_id -> video_id

        # API credentials from environment
        self.twitch_client_id = os.getenv('TWITCH_CLIENT_ID')
        self.twitch_client_secret = os.getenv('TWITCH_CLIENT_SECRET')
        self.youtube_api_key = os.getenv('YOUTUBE_API_KEY')

        # Twitch OAuth token (will be fetched)
        self.twitch_token = None

        # Start background tasks
        self.check_twitch_streams.start()
        self.check_youtube_videos.start()

    def cog_unload(self):
        self.check_twitch_streams.cancel()
        self.check_youtube_videos.cancel()

    def load_settings(self):
        """Load stream alert settings from JSON"""
        try:
            with open(self.DATA_FILE, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

    def save_settings(self):
        """Save stream alert settings to JSON"""
        with open(self.DATA_FILE, 'w') as f:
            json.dump(self.settings, f, indent=4)

    def get_guild_settings(self, guild_id):
        """Get settings for a specific guild"""
        guild_id_str = str(guild_id)
        if guild_id_str not in self.settings:
            self.settings[guild_id_str] = {
                'notification_channel_id': None,
                'notification_role_id': None,
                'twitch_username': None,
                'youtube_channel_id': None
            }
            self.save_settings()
        return self.settings[guild_id_str]

    def is_admin(self, member):
        """Check if user has administrator permission"""
        return member.guild_permissions.administrator or member.guild.owner_id == member.id

    async def get_twitch_token(self):
        """Get Twitch OAuth token"""
        if not self.twitch_client_id or not self.twitch_client_secret:
            return None

        url = 'https://id.twitch.tv/oauth2/token'
        params = {
            'client_id': self.twitch_client_id,
            'client_secret': self.twitch_client_secret,
            'grant_type': 'client_credentials'
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data['access_token']
        except Exception as e:
            print(f"Error getting Twitch token: {e}")
        return None

    async def check_twitch_live(self, username):
        """Check if a Twitch user is currently live"""
        if not self.twitch_token:
            self.twitch_token = await self.get_twitch_token()
            if not self.twitch_token:
                return None

        url = 'https://api.twitch.tv/helix/streams'
        headers = {
            'Client-ID': self.twitch_client_id,
            'Authorization': f'Bearer {self.twitch_token}'
        }
        params = {'user_login': username}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params=params) as response:
                    if response.status == 401:  # Token expired
                        self.twitch_token = await self.get_twitch_token()
                        return None

                    if response.status == 200:
                        data = await response.json()
                        if data['data']:
                            # Stream is live
                            stream = data['data'][0]
                            return {
                                'title': stream['title'],
                                'game': stream['game_name'],
                                'viewer_count': stream['viewer_count'],
                                'thumbnail_url': stream['thumbnail_url'].replace('{width}', '1920').replace('{height}', '1080'),
                                'started_at': stream['started_at']
                            }
        except Exception as e:
            print(f"Error checking Twitch stream: {e}")
        return None

    async def check_youtube_latest_video(self, channel_id):
        """Check for the latest YouTube video"""
        if not self.youtube_api_key:
            return None

        url = 'https://www.googleapis.com/youtube/v3/search'
        params = {
            'part': 'snippet',
            'channelId': channel_id,
            'maxResults': 1,
            'order': 'date',
            'type': 'video',
            'key': self.youtube_api_key
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get('items'):
                            video = data['items'][0]
                            video_id = video['id']['videoId']
                            snippet = video['snippet']

                            # Check if this is a recent video (within last 24 hours)
                            published_at = datetime.fromisoformat(snippet['publishedAt'].replace('Z', '+00:00'))
                            if datetime.now(published_at.tzinfo) - published_at > timedelta(hours=24):
                                return None  # Too old

                            return {
                                'video_id': video_id,
                                'title': snippet['title'],
                                'description': snippet['description'],
                                'thumbnail_url': snippet['thumbnails']['high']['url'],
                                'published_at': snippet['publishedAt']
                            }
        except Exception as e:
            print(f"Error checking YouTube videos: {e}")
        return None

    @tasks.loop(minutes=2)
    async def check_twitch_streams(self):
        """Check all configured Twitch streams"""
        for guild_id_str, config in self.settings.items():
            twitch_username = config.get('twitch_username')
            if not twitch_username:
                continue

            guild_id = int(guild_id_str)
            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue

            # Check if stream is live
            stream_data = await self.check_twitch_live(twitch_username)
            is_live = stream_data is not None

            # Get previous state
            was_live = self.live_status.get(guild_id, False)

            # If just went live, send notification
            if is_live and not was_live:
                await self.send_twitch_notification(guild, config, stream_data, twitch_username)

            # Update state
            self.live_status[guild_id] = is_live

    @tasks.loop(minutes=10)
    async def check_youtube_videos(self):
        """Check all configured YouTube channels for new videos"""
        for guild_id_str, config in self.settings.items():
            youtube_channel_id = config.get('youtube_channel_id')
            if not youtube_channel_id:
                continue

            guild_id = int(guild_id_str)
            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue

            # Check for latest video
            video_data = await self.check_youtube_latest_video(youtube_channel_id)
            if not video_data:
                continue

            # Get previous video ID
            last_video_id = self.last_video_ids.get(guild_id)
            current_video_id = video_data['video_id']

            # If new video, send notification
            if last_video_id != current_video_id:
                # Only notify if we've seen a video before (prevents notification on bot startup)
                if last_video_id is not None:
                    await self.send_youtube_notification(guild, config, video_data)

                # Update last video ID
                self.last_video_ids[guild_id] = current_video_id

    @check_twitch_streams.before_loop
    async def before_check_twitch_streams(self):
        await self.bot.wait_until_ready()

    @check_youtube_videos.before_loop
    async def before_check_youtube_videos(self):
        await self.bot.wait_until_ready()

    async def send_twitch_notification(self, guild, config, stream_data, username):
        """Send a Twitch live notification"""
        channel_id = config.get('notification_channel_id')
        role_id = config.get('notification_role_id')

        if not channel_id:
            return

        channel = guild.get_channel(channel_id)
        if not channel:
            return

        # Create embed
        embed = discord.Embed(
            title=stream_data['title'],
            url=f"https://twitch.tv/{username}",
            description=f"🎮 Playing **{stream_data['game']}**",
            color=discord.Color.purple(),
            timestamp=datetime.fromisoformat(stream_data['started_at'].replace('Z', '+00:00'))
        )
        embed.set_author(name=f"{username} is now live on Twitch!", icon_url="https://static.twitchcdn.net/assets/favicon-32-e29e246c157142c94346.png")
        embed.set_image(url=stream_data['thumbnail_url'])
        embed.add_field(name="Viewers", value=f"{stream_data['viewer_count']:,}", inline=True)
        embed.set_footer(text="Started streaming")

        # Prepare mention
        mention = f"<@&{role_id}>" if role_id else "@here"

        try:
            await channel.send(content=mention, embed=embed)
            print(f"✅ Sent Twitch live notification for {username} in {guild.name}")
        except Exception as e:
            print(f"❌ Error sending Twitch notification: {e}")

    async def send_youtube_notification(self, guild, config, video_data):
        """Send a YouTube new video notification"""
        channel_id = config.get('notification_channel_id')
        role_id = config.get('notification_role_id')

        if not channel_id:
            return

        channel = guild.get_channel(channel_id)
        if not channel:
            return

        # Create embed
        embed = discord.Embed(
            title=video_data['title'],
            url=f"https://www.youtube.com/watch?v={video_data['video_id']}",
            description=video_data['description'][:200] + "..." if len(video_data['description']) > 200 else video_data['description'],
            color=discord.Color.red(),
            timestamp=datetime.fromisoformat(video_data['published_at'].replace('Z', '+00:00'))
        )
        embed.set_author(name="New YouTube Video!", icon_url="https://www.youtube.com/s/desktop/f506bd45/img/favicon_32.png")
        embed.set_image(url=video_data['thumbnail_url'])
        embed.set_footer(text="Published")

        # Prepare mention
        mention = f"<@&{role_id}>" if role_id else "@here"

        try:
            await channel.send(content=mention, embed=embed)
            print(f"✅ Sent YouTube video notification in {guild.name}")
        except Exception as e:
            print(f"❌ Error sending YouTube notification: {e}")

    # Slash command group
    streamalerts = app_commands.Group(name="streamalerts", description="Configure stream and video notifications")

    @streamalerts.command(name='setchannel', description='Set the channel for stream/video notifications')
    @app_commands.describe(channel='The channel where notifications will be posted')
    async def set_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Set notification channel"""
        if not self.is_admin(interaction.user):
            await interaction.response.send_message("❌ You need administrator permission to use this command!", ephemeral=True)
            return

        guild_id = str(interaction.guild.id)
        if guild_id not in self.settings:
            self.settings[guild_id] = {}

        self.settings[guild_id]['notification_channel_id'] = channel.id
        self.save_settings()

        await interaction.response.send_message(f"✅ Stream notifications will be posted in {channel.mention}")

    @streamalerts.command(name='setrole', description='Set the role to mention for notifications')
    @app_commands.describe(role='The role to mention when going live or posting a video')
    async def set_role(self, interaction: discord.Interaction, role: discord.Role):
        """Set notification role"""
        if not self.is_admin(interaction.user):
            await interaction.response.send_message("❌ You need administrator permission to use this command!", ephemeral=True)
            return

        guild_id = str(interaction.guild.id)
        if guild_id not in self.settings:
            self.settings[guild_id] = {}

        self.settings[guild_id]['notification_role_id'] = role.id
        self.save_settings()

        await interaction.response.send_message(f"✅ Will mention {role.mention} for stream notifications")

    @streamalerts.command(name='settwitch', description='Set your Twitch username')
    @app_commands.describe(username='Your Twitch username (without @)')
    async def set_twitch(self, interaction: discord.Interaction, username: str):
        """Set Twitch username"""
        if not self.is_admin(interaction.user):
            await interaction.response.send_message("❌ You need administrator permission to use this command!", ephemeral=True)
            return

        # Remove @ if user included it
        username = username.lstrip('@')

        guild_id = str(interaction.guild.id)
        if guild_id not in self.settings:
            self.settings[guild_id] = {}

        self.settings[guild_id]['twitch_username'] = username
        self.save_settings()

        await interaction.response.send_message(f"✅ Twitch username set to **{username}**\nThe bot will check for live streams every 2 minutes.")

    @streamalerts.command(name='setyoutube', description='Set your YouTube channel ID')
    @app_commands.describe(channel_id='Your YouTube channel ID (from your channel URL)')
    async def set_youtube(self, interaction: discord.Interaction, channel_id: str):
        """Set YouTube channel ID"""
        if not self.is_admin(interaction.user):
            await interaction.response.send_message("❌ You need administrator permission to use this command!", ephemeral=True)
            return

        guild_id = str(interaction.guild.id)
        if guild_id not in self.settings:
            self.settings[guild_id] = {}

        self.settings[guild_id]['youtube_channel_id'] = channel_id
        self.save_settings()

        await interaction.response.send_message(f"✅ YouTube channel ID set to **{channel_id}**\nThe bot will check for new videos every 10 minutes.")

    @streamalerts.command(name='settings', description='View current stream alert settings')
    async def view_settings(self, interaction: discord.Interaction):
        """View current settings"""
        config = self.get_guild_settings(interaction.guild.id)

        embed = discord.Embed(
            title="🔔 Stream Alert Settings",
            color=discord.Color.blue()
        )

        # Notification channel
        channel_id = config.get('notification_channel_id')
        if channel_id:
            channel = interaction.guild.get_channel(channel_id)
            embed.add_field(
                name="Notification Channel",
                value=channel.mention if channel else "Channel not found",
                inline=False
            )
        else:
            embed.add_field(name="Notification Channel", value="❌ Not set", inline=False)

        # Notification role
        role_id = config.get('notification_role_id')
        if role_id:
            role = interaction.guild.get_role(role_id)
            embed.add_field(
                name="Notification Role",
                value=role.mention if role else "Role not found",
                inline=False
            )
        else:
            embed.add_field(name="Notification Role", value="❌ Not set", inline=False)

        # Twitch username
        twitch_username = config.get('twitch_username')
        embed.add_field(
            name="Twitch Username",
            value=f"**{twitch_username}**" if twitch_username else "❌ Not set",
            inline=True
        )

        # YouTube channel
        youtube_channel_id = config.get('youtube_channel_id')
        embed.add_field(
            name="YouTube Channel ID",
            value=f"**{youtube_channel_id}**" if youtube_channel_id else "❌ Not set",
            inline=True
        )

        # API status
        api_status = []
        if self.twitch_client_id and self.twitch_client_secret:
            api_status.append("✅ Twitch API configured")
        else:
            api_status.append("❌ Twitch API not configured")

        if self.youtube_api_key:
            api_status.append("✅ YouTube API configured")
        else:
            api_status.append("❌ YouTube API not configured")

        embed.add_field(name="API Status", value="\n".join(api_status), inline=False)

        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(StreamAlerts(bot))
