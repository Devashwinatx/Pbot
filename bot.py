import re
import os
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

API_ID = 28015531
API_HASH = "2ab4ba37fd5d9ebf1353328fc915ad28"
BOT_TOKEN = "7514636092:AAFY3O_h8NAaRMUlDv1dDEuZDhzxItCHHy0"
TARGET_CHANNEL = -1002445548441
DB_CHANNEL = -1002316552580

bot = Client(
    "AutoPostBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

user_sessions = {}

# Extract title, season, episode from filename
def parse_filename(filename: str):
    match = re.search(r"(.+?)\s+[sS](\d+)[\s_-]*[eE]p?\[?(\d+)\]?.*\[(\d+p)\]", filename)
    if match:
        title = match.group(1).strip()
        season = match.group(2)
        episode = match.group(3)
        quality = match.group(4)
        return title, season, episode, quality
    return None, None, None, None

@bot.on_message(filters.private & filters.command("start"))
async def start_command(client, message):
    user_sessions[message.from_user.id] = {"stage": "cover"}
    await message.reply("👋 Send the **cover photo**.")

@bot.on_message(filters.private & filters.photo)
async def handle_cover(client, message):
    session = user_sessions.get(message.from_user.id)
    if session and session.get("stage") == "cover":
        session["cover"] = message.photo.file_id
        session["stage"] = "files"
        session["videos"] = []
        await message.reply("📁 Now send the **3 video files** (480p, 720p, 1080p).")

@bot.on_message(filters.private & (filters.document | filters.video))
async def handle_files(client, message):
    session = user_sessions.get(message.from_user.id)
    if not session or session.get("stage") != "files":
        return

    file_name = message.document.file_name if message.document else message.video.file_name

    # Validate resolution
    if not re.search(r"\[(480p|720p|1080p)\]", file_name):
        await message.reply("❗ Filename must contain [480p], [720p], or [1080p].")
        return

    # Save message and parse metadata
    session["videos"].append(message)

    if len(session["videos"]) == 3:
        # Extract metadata from one of the files
        title, season, episode, _ = parse_filename(file_name)
        if not all([title, season, episode]):
            await message.reply("❌ Couldn't parse title, season, or episode from filename.")
            return

        session["title"] = title
        session["season"] = season
        session["episode"] = episode
        session["stage"] = "confirm"

        caption = f"▶️ <b>{title}</b>\n\n» Season : {season}\n» Episode : {episode}\n» Language : Tamil\n» Codec : HEVC\n» Quality : 480p, 720p, 1080p"

        buttons = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("480p", url="https://t.me/AnimeTamilFilesBot"),
                InlineKeyboardButton("720p", url="https://t.me/AnimeTamilFilesBot"),
                InlineKeyboardButton("1080p", url="https://t.me/AnimeTamilFilesBot")
            ],
            [InlineKeyboardButton("✅ Send", callback_data="send"), InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
        ])

        await message.reply_photo(
            photo=session["cover"],
            caption=caption,
            reply_markup=buttons
        )

@bot.on_callback_query()
async def handle_buttons(client, callback_query):
    data = callback_query.data
    user_id = callback_query.from_user.id
    session = user_sessions.get(user_id)

    if not session:
        await callback_query.answer("Session expired.", show_alert=True)
        return

    if data == "cancel":
        user_sessions.pop(user_id, None)
        await callback_query.message.edit("❌ Cancelled.")
    elif data == "send":
        cover = session["cover"]
        title = session["title"]
        season = session["season"]
        episode = session["episode"]
        videos = session["videos"]

        caption = f"▶️ <b>{title}</b>\n\n» Season : {season}\n» Episode : {episode}\n» Language : Tamil\n» Codec : HEVC\n» Quality : 480p, 720p, 1080p"

        buttons = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("480p", url=f"https://t.me/{client.me.username}?start=dl480_{videos[0].id}"),
                InlineKeyboardButton("720p", url=f"https://t.me/{client.me.username}?start=dl720_{videos[1].id}"),
                InlineKeyboardButton("1080p", url=f"https://t.me/{client.me.username}?start=dl1080_{videos[2].id}")
            ]
        ])

        # Forward files to DB channel
        for vid in videos:
            await vid.forward(DB_CHANNEL)

        # Post to target channel
        await client.send_photo(
            chat_id=TARGET_CHANNEL,
            photo=cover,
            caption=caption,
            reply_markup=buttons
        )

        await callback_query.message.edit("✅ Sent to channel.")
        user_sessions.pop(user_id, None)

bot.run()
    
