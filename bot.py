from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.enums import ParseMode

import re

API_ID = 28015531
API_HASH = "2ab4ba37fd5d9ebf1353328fc915ad28"
BOT_TOKEN = "7514636092:AAFY3O_h8NAaRMUlDv1dDEuZDhzxItCHHy0"
DB_CHANNEL = -1002316552580
TARGET_CHANNEL = -1002445548441

app = Client("anime_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
sessions = {}

# Regex for validating filenames
video_pattern = re.compile(r"^(.+?)\s+S(\d{2})\s+Ep(\d{2})\s+(480p|720p|1080p)\.mkv$")

@app.on_message(filters.command("upload") & filters.private)
async def cmd_upload(client, message):
    # Start a new upload session
    sessions[message.from_user.id] = {"state": "await_cover"}
    await message.reply("Please send the **cover image** as a photo (no documents).")

@app.on_message(filters.command("cancel") & filters.private)
async def cmd_cancel(client, message):
    # Cancel any active session
    uid = message.from_user.id
    if uid in sessions:
        del sessions[uid]
        await message.reply("Upload session canceled.")
    else:
        await message.reply("No active upload session to cancel.")

@app.on_message(filters.photo & filters.private)
async def receive_photo(client, message):
    uid = message.from_user.id
    # Check if expecting cover
    if uid in sessions and sessions[uid]["state"] == "await_cover":
        cover_file_id = message.photo.file_id  # Photo.file_id10
        sessions[uid].update({"cover_id": cover_file_id, "state": "await_video1"})
        await message.reply("Cover saved. Now send the *480p* video file.")
    else:
        await message.reply("Use /upload to start, then send a cover photo.")

@app.on_message((filters.video | filters.document) & filters.private)
async def receive_video(client, message):
    uid = message.from_user.id
    if uid not in sessions:
        return  # No active session
    state = sessions[uid]["state"]

    # Determine filename depending on type
    fname = ""
    if message.video:
        fname = message.video.file_name or ""
    elif message.document:
        fname = message.document.file_name or ""
    match = video_pattern.match(fname)
    if not match:
        await message.reply("Invalid filename format. Use: Title S01 Ep01 [480p].mkv")
        return

    title, season, episode, res = match.groups()

    # First video: expect 480p
    if state == "await_video1":
        if res != "480p":
            await message.reply("Expected [480p] file first.")
            return
        sessions[uid].update({"title": title, "season": season, "episode": episode})
        sessions[uid].setdefault("video_ids", []).append(message.message_id)
        sessions[uid]["state"] = "await_video2"
        await message.reply("480p video received. Now send the *720p* file.")

    # Second video: expect 720p
    elif state == "await_video2":
        if title != sessions[uid]["title"] or season != sessions[uid]["season"] or episode != sessions[uid]["episode"]:
            await message.reply("Title/season/episode does not match. Please resend.")
            return
        if res != "720p":
            await message.reply("Expected [720p] file second.")
            return
        sessions[uid]["video_ids"].append(message.message_id)
        sessions[uid]["state"] = "await_video3"
        await message.reply("720p video received. Now send the *1080p* file.")

    # Third video: expect 1080p
    elif state == "await_video3":
        if title != sessions[uid]["title"] or season != sessions[uid]["season"] or episode != sessions[uid]["episode"]:
            await message.reply("Title/season/episode does not match. Please resend.")
            return
        if res != "1080p":
            await message.reply("Expected [1080p] file third.")
            return
        sessions[uid]["video_ids"].append(message.message_id)
        # All videos received: finalize
        await finalize_submission(client, message)

async def finalize_submission(client, message):
    uid = message.from_user.id
    data = sessions[uid]
    user_chat = message.chat.id
    video_ids = data["video_ids"]

    # Forward videos to the database channel
    forwarded_ids = []
    for vid_id in video_ids:
        fwd_msg = await client.forward_messages(
            chat_id=DB_CHANNEL,
            from_chat_id=user_chat,
            message_ids=vid_id
        )  # Pyrogram forward_messages11
        # Ensure we get message_id(s)
        if isinstance(fwd_msg, list):
            forwarded_ids.extend([m.message_id for m in fwd_msg])
        else:
            forwarded_ids.append(fwd_msg.message_id)
    # Prepare preview
    data["fwd_ids"] = forwarded_ids
    # Build inline keyboard
    bot_user = (await client.get_me()).username
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("480p", url=f"https://t.me/{bot_user}?start=vid_{forwarded_ids[0]}"),
         InlineKeyboardButton("720p", url=f"https://t.me/{bot_user}?start=vid_{forwarded_ids[1]}"),
         InlineKeyboardButton("1080p", url=f"https://t.me/{bot_user}?start=vid_{forwarded_ids[2]}")],
        [InlineKeyboardButton("Send ✅", callback_data="send")]
    ])
    data["keyboard"] = keyboard

    # Send preview to user with cover photo and caption
    caption = (f"<b>{data['title']}</b> – S{data['season']} Ep{data['episode']}"
               "\nAvailable: 480p, 720p, 1080p")
    await client.send_photo(
        uid,
        data["cover_id"],
        caption=caption,
        parse_mode=ParseMode.HTML,  # Use HTML mode12
        reply_markup=keyboard
    )

@app.on_callback_query()
async def callback_handler(client, query):
    uid = query.from_user.id
    if query.data == "send" and uid in sessions:
        await query.answer()  # Acknowledge callback
        data = sessions[uid]
        # Post to target channel
        caption = (f"<b>{data['title']}</b> – S{data['season']} Ep{data['episode']}"
                   "\nAvailable: 480p, 720p, 1080p")
        await client.send_photo(
            TARGET_CHANNEL,
            data["cover_id"],
            caption=caption,
            parse_mode=ParseMode.HTML,
            reply_markup=data.get("keyboard")
        )
        # Optionally remove inline buttons from preview
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except:
            pass
        await client.send_message(uid, "Posted to the target channel ✅.")
        del sessions[uid]

@app.on_message(filters.regex(r"^/start") & filters.private)
async def start_handler(client, message):
    text = message.text or ""
    uid = message.from_user.id
    # Handle deep link for video
    if "vid_" in text:
        try:
            vid_id = int(text.split("vid_")[1])
            await client.forward_messages(uid, DB_CHANNEL, vid_id)
        except Exception:
            await message.reply("Invalid video link.")
    else:
        await message.reply("Welcome! Use /upload to post a new video.")

app.run()
