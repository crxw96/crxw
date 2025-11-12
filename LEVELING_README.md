# CRXW Bot - Leveling System Added! 📊

## What's New
✅ **Complete XP and Leveling System!**
- Earn XP for every message you send
- Level up and climb the leaderboard
- Automatic role rewards at specific levels
- Anti-spam cooldown system
- Beautiful rank cards and leaderboards

## New Commands

### User Commands (Everyone)
- `/rank` - View your or someone else's rank, level, and XP progress
- `/leaderboard` - View the top 10 users in the server

### Admin Commands (Administrator Only)
- `/leveling setlevelrole <level> <role>` - Assign a role reward for reaching a level
- `/leveling removelevelrole <level>` - Remove a level role reward
- `/leveling levelroles` - List all configured level role rewards
- `/leveling settings` - View current leveling settings

## How It Works

### XP System
- Users earn **15-25 XP per message** (randomized)
- **60-second cooldown** between XP gains (prevents spam)
- XP and levels persist across bot restarts (SQLite database)

### Level Progression
- **Level 1 → 2**: 155 XP needed
- **Level 2 → 3**: 220 XP needed
- **Level 3 → 4**: 295 XP needed
- Formula: `5 * (level²) + 50 * level + 100`
- Gets progressively harder as you level up

### Level-Up Announcements
- Beautiful embed message when you level up
- Shows new level and XP progress
- Posted in the same channel where you leveled up

### Level Roles
- Automatically assign roles when users reach specific levels
- Example: Level 5 = "Active Member", Level 10 = "Veteran"
- Users keep all level roles they've earned

## Update Instructions

### Step 1: Backup (Optional but Recommended)
```bash
cd ~/developer
cp -r crxw crxw-backup-before-leveling
```

### Step 2: Download New Files
You need to download and replace:
- `crxw.py` - Updated to load leveling feature
- `features/leveling.py` - NEW leveling system
- Keep your existing files (they're compatible)

### Step 3: Update on Windows
```bash
# Replace the files, then:
git add .
git commit -m "Add leveling system"
git push
```

### Step 4: Update on Raspberry Pi
```bash
# Stop bot
pm2 stop crxw

# Pull changes
cd ~/developer/crxw
git pull

# Create data directory (if needed)
mkdir -p data

# Restart bot
pm2 restart crxw
pm2 logs crxw --lines 30
```

You should see:
```
✅ Loaded features.bump
✅ Loaded features.reaction_roles
✅ Loaded features.leveling
Syncing commands with Discord...
✅ Commands synced!
```

## Usage Examples

### Setting Up Level Roles
```
/leveling setlevelrole level:5 role:@Active Member
/leveling setlevelrole level:10 role:@Veteran
/leveling setlevelrole level:20 role:@Elite
/leveling setlevelrole level:50 role:@Legend
```

### Checking Your Progress
```
/rank
```
Shows your beautiful rank card with:
- Current rank position
- Current level
- Total messages sent
- XP progress bar
- XP needed for next level

### Viewing Leaderboard
```
/leaderboard
```
Shows top 10 users with 🥇🥈🥉 medals for top 3!

### Managing Level Roles
```
/leveling levelroles         # View all level roles
/leveling removelevelrole level:5   # Remove level 5 role reward
```

## Features in Detail

### Anti-Spam Protection
- Users can only earn XP once per 60 seconds
- Prevents spam farming
- Encourages quality conversation over quantity

### Progress Tracking
- Total XP tracked
- Current level tracked
- Total messages sent tracked
- All data persists in SQLite database

### Beautiful UI
- Progress bars showing XP progress
- Colorful embeds
- Medals for top 3 on leaderboard
- User avatars in rank cards

### Automatic Role Assignment
- Roles automatically given when reaching levels
- Users keep all earned roles
- Works retroactively (if you add a Level 5 role, users at Level 5+ get it)

## File Structure
```
crxw/
├── crxw.py                     # Updated with leveling
├── features/
│   ├── __init__.py
│   ├── bump.py
│   ├── reaction_roles.py
│   └── leveling.py            # NEW!
├── data/
│   ├── bump_data.json
│   ├── reaction_roles.json
│   ├── leveling.db            # NEW! SQLite database
│   └── leveling_settings.json # NEW! Settings file
├── .env
└── requirements.txt
```

## Database Schema

### Users Table
- `guild_id` - Server ID
- `user_id` - User ID
- `xp` - Total XP earned
- `level` - Current level
- `total_messages` - Messages sent
- `last_message_time` - For cooldown tracking

### Level Roles Table
- `guild_id` - Server ID
- `level` - Level requirement
- `role_id` - Role to assign

## Customization

Current settings (can be modified in code if needed):
```python
'xp_per_message_min': 15      # Minimum XP per message
'xp_per_message_max': 25      # Maximum XP per message
'message_cooldown': 60         # Seconds between XP gains
'level_up_message': True       # Show level-up announcements
```

## Troubleshooting

### Commands not showing up?
- Wait 5 minutes for Discord to sync
- Restart bot: `pm2 restart crxw`

### "Database is locked" errors?
- Normal if restarting frequently
- Just restart once more: `pm2 restart crxw`

### Users not getting roles?
- Make sure bot's role is ABOVE the level roles
- Bot needs "Manage Roles" permission
- Check `/leveling levelroles` to see configured roles

### Level-up messages not appearing?
- This is enabled by default
- Messages appear in the same channel where user leveled up
- Make sure bot has "Send Messages" permission

## Bot Permissions Required
Make sure your bot has:
- ✅ Send Messages
- ✅ Embed Links
- ✅ Read Message History
- ✅ Manage Roles (for level role rewards)

## Performance Notes
- SQLite database is very lightweight
- Cooldown system prevents database spam
- No impact on message latency
- Database file typically <1MB even with thousands of users

## Coming Soon
- Moderation commands (kick, ban, timeout, warnings)
- Logging system (message edits, deletes, member joins/leaves)
- Custom leveling settings via commands (adjust XP rates)

## All Current Features

### ✅ Bump Reminders
- Auto-detects Disboard bumps
- 2-hour reminders

### ✅ Reaction Roles
- Multiple reaction role messages
- Auto-create roles
- Multi-role support

### ✅ Leveling System (NEW!)
- XP per message
- Level progression
- Role rewards
- Leaderboards
- Rank cards

---
Made with 🔥 | Self-hosted on Raspberry Pi