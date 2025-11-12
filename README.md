# CRXW Bot - Slash Commands Update! 🎉

## What's New
✅ **Proper Discord slash commands with autocomplete!**
- Commands now show up when you type `/` in Discord
- Autocomplete suggestions for parameters
- Professional command interface
- Automatic parameter validation

## Updated Commands

### Bump Commands
- `/bumpstatus` - Check when next bump is ready (slash command)
- Disboard bump detection still works automatically!

### Reaction Role Commands (All with autocomplete!)
- `/reactionrole create` - Create a reaction role message
  - **Parameters:**
    - `category` - Category name
    - `channel` - Channel to post in
    - `title` - Message title
    - `roles` - Emoji:Role pairs (e.g., `🎮:Valorant 🔫:COD`)
  
- `/reactionrole list` - Show all reaction role messages
- `/reactionrole delete` - Delete a reaction role message
  - `message_id` - ID of the message to delete
  
- `/reactionrole info` - View role mappings
  - `message_id` - ID of the message

### Help Command
- `/help` - Show all commands and features

## How to Update on Raspberry Pi

### Step 1: Backup and Stop Bot
```bash
cd ~/developer
cp -r crxw crxw-backup-old-commands
cd crxw
pm2 stop crxw
```

### Step 2: Pull Changes from GitHub
```bash
git pull
```

### Step 3: Update Dependencies
```bash
source venv/bin/activate
pip install -r requirements.txt --upgrade
```

### Step 4: Make Sure Data Directory Exists
```bash
mkdir -p data
# Move old data files if needed
mv bump_data.json data/ 2>/dev/null || true
```

### Step 5: Restart Bot
```bash
pm2 restart crxw
pm2 logs crxw --lines 30
```

You should see:
```
✅ Loaded features.bump
✅ Loaded features.reaction_roles
Syncing commands with Discord...
✅ Commands synced!
ℭ𝔯𝔬𝔴#5564 is now online!
```

**Important:** The first time you start the bot with slash commands, Discord needs to sync them. This can take up to an hour to propagate to all servers, but usually happens in 1-5 minutes.

## Using Slash Commands

### How It Works Now
1. Type `/` in Discord
2. You'll see a menu of available commands
3. Select the command you want
4. Fill in the parameters (Discord shows you what's needed!)
5. Press Enter

### Example: Creating Reaction Roles

**Old way (message-based):**
```
/reactionrole create games #general "Pick your games!" 🎮:Valorant 🔫:COD
```

**New way (slash commands):**
1. Type `/reactionrole` and select `create` from the menu
2. Discord will prompt you for each parameter:
   - `category`: type `games`
   - `channel`: select #general from the dropdown
   - `title`: type `Pick your games!`
   - `roles`: type `🎮:Valorant 🔫:COD ⚔️:Apex`
3. Press Enter!

### Example: Check Bump Status

**Old way:**
```
/bumpstatus
```

**New way:**
1. Type `/bumpstatus`
2. Select it from the autocomplete menu
3. Press Enter!

Much cleaner and more intuitive!

## Troubleshooting

### Commands not showing up?
- Wait 5-10 minutes after first restart (Discord needs time to sync)
- Make sure the bot restarted successfully: `pm2 logs crxw`
- Look for "✅ Commands synced!" in the logs
- Try kicking and re-inviting the bot to your server

### Bot says "Application did not respond"?
- Check logs: `pm2 logs crxw`
- Bot might have crashed, restart it: `pm2 restart crxw`

### Missing permissions?
Make sure the bot has:
- ✅ Use Application Commands (for slash commands to work)
- ✅ Manage Roles
- ✅ Add Reactions
- ✅ Send Messages
- ✅ Embed Links
- ✅ Read Message History

### Roles still being created/assigned?
- Bot's role must be ABOVE the roles it manages
- Check in Server Settings → Roles → Drag bot role higher

## What Changed Behind the Scenes

### Technical Changes
- Migrated from `@commands.command()` to `@app_commands.command()`
- Uses `discord.Interaction` instead of `ctx`
- Added command syncing with `await bot.tree.sync()`
- Reaction role commands use `app_commands.Group`
- Better parameter validation and type hints

### File Structure (Same)
```
crxw/
├── crxw.py
├── features/
│   ├── __init__.py
│   ├── bump.py
│   └── reaction_roles.py
├── data/
│   ├── bump_data.json
│   └── reaction_roles.json
├── .env
└── requirements.txt
```

## Benefits of Slash Commands

✅ **Better UX** - Autocomplete and visual parameter selection
✅ **Validation** - Discord validates parameters before sending
✅ **Professional** - Standard Discord interface
✅ **Discoverable** - Users can see all commands by typing `/`
✅ **Mobile-friendly** - Easier to use on phones

## Coming Soon
- Leveling system
- Moderation commands
- Logging system
- All with slash commands!

---
Made with 🔥 | Self-hosted on Raspberry Pi