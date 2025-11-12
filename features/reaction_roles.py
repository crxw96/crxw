import discord
from discord.ext import commands
from discord import app_commands
import json
import re

class ReactionRoles(commands.Cog):
    """Reaction role system with categories"""
    
    def __init__(self, bot):
        self.bot = bot
        self.DATA_FILE = 'data/reaction_roles.json'
        self.reaction_roles = self.load_data()
    
    def load_data(self):
        """Load reaction role data from JSON file"""
        try:
            with open(self.DATA_FILE, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
    
    def save_data(self):
        """Save reaction role data to JSON file"""
        with open(self.DATA_FILE, 'w') as f:
            json.dump(self.reaction_roles, f, indent=4)
    
    def is_mod_or_owner(self, member):
        """Check if user is mod or server owner"""
        if member.guild.owner_id == member.id:
            return True
        return member.guild_permissions.administrator or member.guild_permissions.manage_roles
    
    reactionrole = app_commands.Group(name="reactionrole", description="Manage reaction role messages")
    
    @reactionrole.command(name='create', description='Create a new reaction role message')
    @app_commands.describe(
        category='Category name for this reaction role message',
        channel='Channel where the message will be posted',
        title='Title of the reaction role embed',
        roles='Emoji:Role pairs (e.g., 🎮:Valorant 🔫:COD ⚔️:Apex)'
    )
    async def create_reaction_role(
        self, 
        interaction: discord.Interaction, 
        category: str,
        channel: discord.TextChannel,
        title: str,
        roles: str
    ):
        """Create a new reaction role message"""
        # Check permissions
        if not self.is_mod_or_owner(interaction.user):
            await interaction.response.send_message("❌ You need to be a moderator or server owner to use this command!", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        # Parse emoji:role pairs
        pairs = roles.split()
        
        if len(pairs) == 0:
            await interaction.followup.send("❌ No emoji:role pairs provided!\n**Example:** `🎮:Valorant 🔫:COD ⚔️:Apex`")
            return
        
        role_mappings = []
        
        for pair in pairs:
            if ':' not in pair:
                continue
            
            parts = pair.split(':', 1)
            if len(parts) != 2:
                continue
            
            emoji = parts[0]
            role_name = parts[1]
            
            # Check if role exists, if not create it
            role = discord.utils.get(interaction.guild.roles, name=role_name)
            if role is None:
                try:
                    role = await interaction.guild.create_role(name=role_name, mentionable=True)
                    await interaction.followup.send(f"✅ Created new role: {role.mention}")
                except discord.Forbidden:
                    await interaction.followup.send(f"❌ I don't have permission to create roles!")
                    return
                except Exception as e:
                    await interaction.followup.send(f"❌ Error creating role {role_name}: {e}")
                    return
            
            role_mappings.append({
                'emoji': emoji,
                'role_id': role.id,
                'role_name': role.name
            })
        
        if len(role_mappings) == 0:
            await interaction.followup.send("❌ No valid emoji:role pairs found!\n**Example:** `🎮:Valorant 🔫:COD ⚔️:Apex`")
            return
        
        # Create the embed message
        embed = discord.Embed(
            title=f"⭐ {title}",
            description=f"**Category:** {category}\n\nReact to get your roles!",
            color=discord.Color.blue()
        )
        
        # Add role information to embed
        roles_text = "\n".join([f"{mapping['emoji']} - {mapping['role_name']}" for mapping in role_mappings])
        embed.add_field(name="Available Roles", value=roles_text, inline=False)
        embed.set_footer(text="React with the emoji to get the role!")
        
        # Send the message
        try:
            message = await channel.send(embed=embed)
        except discord.Forbidden:
            await interaction.followup.send(f"❌ I don't have permission to send messages in {channel.mention}!")
            return
        
        # Add reactions
        for mapping in role_mappings:
            try:
                await message.add_reaction(mapping['emoji'])
            except discord.HTTPException:
                await interaction.followup.send(f"⚠️ Couldn't add reaction {mapping['emoji']} - invalid emoji?")
        
        # Store the reaction role data
        message_id = str(message.id)
        self.reaction_roles[message_id] = {
            'guild_id': interaction.guild.id,
            'channel_id': channel.id,
            'category': category,
            'title': title,
            'mappings': role_mappings
        }
        self.save_data()
        
        await interaction.followup.send(f"✅ Reaction role message created in {channel.mention}! Message ID: `{message.id}`")
    
    @reactionrole.command(name='list', description='List all reaction role messages in this server')
    async def list_reaction_roles(self, interaction: discord.Interaction):
        """List all reaction role messages in this server"""
        guild_messages = {
            msg_id: data for msg_id, data in self.reaction_roles.items()
            if data['guild_id'] == interaction.guild.id
        }
        
        if not guild_messages:
            await interaction.response.send_message("❌ No reaction role messages found in this server!", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="📋 Reaction Role Messages",
            description=f"Found {len(guild_messages)} reaction role message(s)",
            color=discord.Color.green()
        )
        
        for msg_id, data in guild_messages.items():
            channel = interaction.guild.get_channel(data['channel_id'])
            channel_name = channel.mention if channel else "Unknown Channel"
            
            roles = ", ".join([mapping['role_name'] for mapping in data['mappings']])
            
            embed.add_field(
                name=f"{data['category']} - {data['title']}",
                value=f"**Channel:** {channel_name}\n**Message ID:** `{msg_id}`\n**Roles:** {roles}",
                inline=False
            )
        
        await interaction.response.send_message(embed=embed)
    
    @reactionrole.command(name='delete', description='Delete a reaction role message')
    @app_commands.describe(message_id='The ID of the reaction role message to delete')
    async def delete_reaction_role(self, interaction: discord.Interaction, message_id: str):
        """Delete a reaction role message"""
        # Check permissions
        if not self.is_mod_or_owner(interaction.user):
            await interaction.response.send_message("❌ You need to be a moderator or server owner to use this command!", ephemeral=True)
            return
        
        if message_id not in self.reaction_roles:
            await interaction.response.send_message("❌ Reaction role message not found!", ephemeral=True)
            return
        
        data = self.reaction_roles[message_id]
        
        # Verify it's from this guild
        if data['guild_id'] != interaction.guild.id:
            await interaction.response.send_message("❌ That message is not from this server!", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        # Try to delete the actual message
        try:
            channel = interaction.guild.get_channel(data['channel_id'])
            if channel:
                message = await channel.fetch_message(int(message_id))
                await message.delete()
        except:
            pass  # Message might already be deleted
        
        # Remove from data
        del self.reaction_roles[message_id]
        self.save_data()
        
        await interaction.followup.send(f"✅ Reaction role message `{message_id}` has been deleted!")
    
    @reactionrole.command(name='info', description='Show detailed info about a reaction role message')
    @app_commands.describe(message_id='The ID of the reaction role message')
    async def info_reaction_role(self, interaction: discord.Interaction, message_id: str):
        """Show detailed info about a reaction role message"""
        if message_id not in self.reaction_roles:
            await interaction.response.send_message("❌ Reaction role message not found!", ephemeral=True)
            return
        
        data = self.reaction_roles[message_id]
        
        # Verify it's from this guild
        if data['guild_id'] != interaction.guild.id:
            await interaction.response.send_message("❌ That message is not from this server!", ephemeral=True)
            return
        
        channel = interaction.guild.get_channel(data['channel_id'])
        channel_name = channel.mention if channel else "Unknown Channel"
        
        embed = discord.Embed(
            title=f"ℹ️ Reaction Role Info",
            description=f"**Category:** {data['category']}\n**Title:** {data['title']}",
            color=discord.Color.blue()
        )
        
        embed.add_field(name="Channel", value=channel_name, inline=True)
        embed.add_field(name="Message ID", value=f"`{message_id}`", inline=True)
        
        # List all mappings
        mappings_text = "\n".join([
            f"{mapping['emoji']} → {mapping['role_name']} (ID: {mapping['role_id']})"
            for mapping in data['mappings']
        ])
        embed.add_field(name="Role Mappings", value=mappings_text, inline=False)
        
        await interaction.response.send_message(embed=embed)
    
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        """Handle when someone adds a reaction"""
        # Ignore bot reactions
        if payload.user_id == self.bot.user.id:
            return
        
        message_id = str(payload.message_id)
        
        # Check if this message has reaction roles
        if message_id not in self.reaction_roles:
            return
        
        data = self.reaction_roles[message_id]
        
        # Find the role for this emoji
        role_id = None
        emoji_str = str(payload.emoji)
        
        for mapping in data['mappings']:
            if mapping['emoji'] == emoji_str:
                role_id = mapping['role_id']
                break
        
        if role_id is None:
            return
        
        # Get guild and member
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        
        member = guild.get_member(payload.user_id)
        if member is None:
            return
        
        role = guild.get_role(role_id)
        if role is None:
            return
        
        # Add the role
        try:
            await member.add_roles(role)
            print(f"✅ Added role {role.name} to {member.name}")
        except discord.Forbidden:
            print(f"❌ No permission to add role {role.name}")
        except Exception as e:
            print(f"❌ Error adding role: {e}")
    
    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        """Handle when someone removes a reaction"""
        # Ignore bot reactions
        if payload.user_id == self.bot.user.id:
            return
        
        message_id = str(payload.message_id)
        
        # Check if this message has reaction roles
        if message_id not in self.reaction_roles:
            return
        
        data = self.reaction_roles[message_id]
        
        # Find the role for this emoji
        role_id = None
        emoji_str = str(payload.emoji)
        
        for mapping in data['mappings']:
            if mapping['emoji'] == emoji_str:
                role_id = mapping['role_id']
                break
        
        if role_id is None:
            return
        
        # Get guild and member
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        
        member = guild.get_member(payload.user_id)
        if member is None:
            return
        
        role = guild.get_role(role_id)
        if role is None:
            return
        
        # Remove the role
        try:
            await member.remove_roles(role)
            print(f"✅ Removed role {role.name} from {member.name}")
        except discord.Forbidden:
            print(f"❌ No permission to remove role {role.name}")
        except Exception as e:
            print(f"❌ Error removing role: {e}")

async def setup(bot):
    await bot.add_cog(ReactionRoles(bot))