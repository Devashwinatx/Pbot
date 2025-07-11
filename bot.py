# bot.py
import re
import os
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# --- Configuration (replace placeholders) ---
API_ID = 28015531                 # e.g. 123456
API_HASH = "2ab4ba37fd5d9ebf1353328fc915ad28"           # e.g. "abcdef1234567890abcdef1234567890"
BOT_TOKEN = "7514636092:AAFY3O_h8NAaRMUlDv1dDEuZDhzxItCHHy0"         # e.g. "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
ADMIN_ID = 6121610691             # e.g. 123456789 (only this user can upload)
TARGET_CHANNEL = -1002445548441      # target channel ID (as given)
DB_CHANNEL = -1002316552580          # database channel ID (as given)

# Initialize the Pyrogram client
app = Client("anime_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# State storage for the current upload session (by admin user ID)
admin_data = {}  # will hold {'cover': file_id, 'title': str, 'season': int, 'episode': int, 'videos': {}, 'db_ids': {}}

# Regex pattern for filename: Title S01 Ep01 [720p].mkv
file_pattern = re.compile(r"^(.+?) S(\d+) Ep(\d+) (\d+p)\.mkv$")

# Handler: /cancel command (admin only) to reset the current upload
@app.on_message(filters.command("cancel") & filters.user(ADMIN_ID))
async def cancel_upload(client, message):
    """Allow admin to cancel the current upload process."""
    admin_data.pop(message.from_user.id, None)
    await message.reply("Upload cancelled. Send a cover image to start over.")

# Handler: Cover image from admin
@app.on_message(filters.photo & filters.user(ADMIN_ID) & filters.private)
async def handle_cover(client, message):
    """Accept the cover image and prompt for videos."""
    uid = message.from_user.id
    # Initialize or reset admin data
    if uid not in admin_data or admin_data[uid].get("videos"):
        # Start new session
        admin_data[uid] = {"cover": None, "videos": {}, "title": None, "season": None, "episode": None}
    # Save the cover file_id
    photo = message.photo[-1]  # largest size
    admin_data[uid]["cover"] = photo.file_id
    await message.reply("✅ Cover image received. Now send *exactly 3 videos* (480p, 720p, 1080p) with names like `Title S01 Ep01 [480p].mkv`.", 
                        parse_mode="markdown")

# Handler: Video files from admin
@app.on_message((filters.video | filters.document) & filters.user(ADMIN_ID) & filters.private)
async def handle_video(client, message):
    """Collect exactly 3 video files, validate them, and prepare the preview."""
    uid = message.from_user.id
    data = admin_data.get(uid)
    if not data or not data.get("cover"):
        await message.reply("❗ Please send a cover image first.")
        return

    # Ensure no more than 3 videos
    if len(data["videos"]) >= 3:
        await message.reply("❗ Already received 3 videos. Use /cancel to start again.")
        return

    # Get the filename (supports both Video and Document)
    file_name = None
    if message.video and message.video.file_name:
        file_name = message.video.file_name
    elif message.document and message.document.file_name:
        file_name = message.document.file_name
    else:
        await message.reply("❗ Video file must include a filename (e.g. `Title S01 Ep01 [480p].mkv`).")
        return

    # Validate filename pattern
    match = file_pattern.match(file_name)
    if not match:
        await message.reply("❗ Filename format incorrect.\nUse: `Title S01 Ep01 [480p].mkv`, where '480p' can be 480p, 720p, or 1080p.")
        return

    title, season_str, episode_str, quality = match.groups()
    season = int(season_str)
    episode = int(episode_str)
    quality = quality.lower()

    # Check resolution is one of expected
    if quality not in ("480p", "720p", "1080p"):
        await message.reply("❗ Quality must be one of: 480p, 720p, 1080p.")
        return

    # If this is the first video, store title/season/episode
    if not data["videos"]:
        data["title"] = title
        data["season"] = season
        data["episode"] = episode
    else:
        # Ensure consistency with previous videos
        if title != data["title"] or season != data["season"] or episode != data["episode"]:
            await message.reply("❗ Title, season, or episode does not match previous videos.")
            return

    # Check for duplicate quality
    if quality in data["videos"]:
        await message.reply(f"❗ Already received a {quality} video.")
        return

    # Save this video message object
    data["videos"][quality] = message
    await message.reply(f"✅ {quality} video received.")

    # If we have all 3 videos, process and send preview
    if len(data["videos"]) == 3:
        # Copy each video to the DB channel and save the message IDs
        db_ids = {}
        for q, msg_obj in data["videos"].items():
            # Use copy_message to avoid forwarding link to original
            forwarded = await client.copy_message(DB_CHANNEL, from_chat_id=msg_obj.chat.id, message_id=msg_obj.id)
            db_ids[q] = forwarded.id
        data["db_ids"] = db_ids

        # Build inline keyboard for qualities and Send button
        buttons = []
        # Two buttons on first row (480p, 720p), two on second (1080p, Send)
        # Ensure we have the bot username for deep links
        me = await client.get_me()
        bot_username = me.username
        # 480p and 720p buttons
        row1 = []
        for q in ("480p", "720p"):
            if q in db_ids:
                url = f"https://t.me/{bot_username}?start=vid_{db_ids[q]}"
                row1.append(InlineKeyboardButton(q, url=url))
        buttons.append(row1)
        # 1080p and Send buttons
        row2 = []
        if "1080p" in db_ids:
            url = f"https://t.me/{bot_username}?start=vid_{db_ids['1080p']}"
            row2.append(InlineKeyboardButton("1080p", url=url))
        row2.append(InlineKeyboardButton("Send", callback_data="send"))
        buttons.append(row2)

        # Send the preview with cover and inline buttons to the admin
        caption = f"*{data['title']}* S{data['season']:02d} Ep{data['episode']:02d}\nSelect a quality:"
        await client.send_photo(uid, photo=data["cover"], caption=caption, 
                                parse_mode="markdown", reply_markup=InlineKeyboardMarkup(buttons))

# Handler: Inline button callback (Send button)
@app.on_callback_query()
async def on_button_click(client, callback_query):
    """When admin clicks 'Send', post the preview to the target channel."""
    data = admin_data.get(callback_query.from_user.id)
    # Only handle the "send" callback from the current admin session
    if callback_query.data == "send":
        uid = callback_query.from_user.id
        if uid != ADMIN_ID:
            await callback_query.answer("Unauthorized", show_alert=True)
            return
        if not data or not data.get("db_ids"):
            await callback_query.answer("❗ No videos to send.", show_alert=True)
            return

        # Prepare inline keyboard for the target channel (qualities only)
        me = await client.get_me()
        bot_username = me.username
        db_ids = data["db_ids"]
        # Inline keyboard with 480p/720p in first row, 1080p in second
        kb = [
            [
                InlineKeyboardButton("480p", url=f"https://t.me/{bot_username}?start=vid_{db_ids['480p']}"),
                InlineKeyboardButton("720p", url=f"https://t.me/{bot_username}?start=vid_{db_ids['720p']}"),
            ],
            [
                InlineKeyboardButton("1080p", url=f"https://t.me/{bot_username}?start=vid_{db_ids['1080p']}")
            ]
        ]
        # Post the cover image with title caption to the target channel
        caption = f"*{data['title']}* S{data['season']:02d} Ep{data['episode']:02d}"
        await client.send_photo(TARGET_CHANNEL, photo=data["cover"], caption=caption, 
                                parse_mode="markdown", reply_markup=InlineKeyboardMarkup(kb))
        await callback_query.answer("Posted to channel ✅")
        # Reset admin data for next upload
        admin_data.pop(uid, None)

# Handler: /start for users requesting a file
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    """When a user sends /start vid_<id>, forward the corresponding file from the DB channel."""
    uid = message.from_user.id
    args = message.command
    # Check if there's a parameter like "vid_<msg_id>"
    if len(args) > 1 and args[1].startswith("vid_"):
        vid_str = args[1].split("_", 1)[1]
        if not vid_str.isdigit():
            await message.reply("❗ Invalid link format.")
            return
        vid_id = int(vid_str)
        try:
            # Copy the message from DB_CHANNEL to the user
            await client.copy_message(uid, from_chat_id=DB_CHANNEL, message_id=vid_id)
        except Exception:
            await message.reply("❗ Sorry, the requested file was not found.")
    else:
        await message.reply("👋 Welcome! Please use the download buttons to receive your files.")

# Run the bot
if __name__ == "__main__":
    app.run()
