import base64
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery

API_ID = 28015531
API_HASH = "2ab4ba37fd5d9ebf1353328fc915ad28"
BOT_TOKEN = "7514636092:AAFY3O_h8NAaRMUlDv1dDEuZDhzxItCHHy0"

DB_CHANNEL = -1002316552580  # your DB channel ID
TARGET_CHANNEL = -1002445548441  # your post channel ID
BOT_USERNAME = "FastAutoRenamebot"  # your bot's username without @

app = Client("anime_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

user_data = {}
shared_files = {}  # stores file_id to send later via /start link


# Step 1: Get cover photo
@app.on_message(filters.private & filters.photo)
async def ask_videos(client, message: Message):
    user_data[message.from_user.id] = {"cover": message.photo.file_id}
    await message.reply("✅ Cover received.\nNow send 3 video files (480p, 720p, 1080p).")


# Step 2: Get videos and generate deep links
@app.on_message(filters.private & filters.video)
async def handle_video(client, message: Message):
    user_id = message.from_user.id
    if user_id not in user_data or "cover" not in user_data[user_id]:
        await message.reply("❗ Please send a cover photo first.")
        return

    file = message.video
    filename = file.file_name or ""
    quality = None

    if "480p" in filename:
        quality = "480p"
    elif "720p" in filename:
        quality = "720p"
    elif "1080p" in filename:
        quality = "1080p"
    else:
        await message.reply("❌ Filename must include quality like 480p/720p/1080p.")
        return

    # Extract title and episode
    parts = filename.split()
    title = parts[0] if parts else "Unknown"
    season = "S01"
    episode = "E01"
    for part in parts:
        if part.startswith("S"):
            season = part
        elif "Ep" in part or part.startswith("E"):
            episode = part

    user_data[user_id]["title"] = title
    user_data[user_id]["season"] = season
    user_data[user_id]["episode"] = episode

    # Forward to DB channel
    forwarded = await file.copy(chat_id=DB_CHANNEL)
    file_id = forwarded.video.file_id
    encoded = base64.urlsafe_b64encode(f"get-{file_id}".encode()).decode()

    shared_files[encoded] = file_id
    user_data[user_id][quality] = encoded

    # Once all 3 qualities are ready
    if all(k in user_data[user_id] for k in ["480p", "720p", "1080p"]):
        buttons = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("480p", url=f"https://t.me/{BOT_USERNAME}?start={user_data[user_id]['480p']}"),
                InlineKeyboardButton("720p", url=f"https://t.me/{BOT_USERNAME}?start={user_data[user_id]['720p']}"),
                InlineKeyboardButton("1080p", url=f"https://t.me/{BOT_USERNAME}?start={user_data[user_id]['1080p']}")
            ],
            [InlineKeyboardButton("✅ Post", callback_data="send"), InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
        ])
        caption = f"**{title} {season} {episode}**"
        await message.reply_photo(user_data[user_id]["cover"], caption=caption, reply_markup=buttons)


# Step 3: Handle send/cancel
@app.on_callback_query(filters.regex("send|cancel"))
async def confirm_post(client, query: CallbackQuery):
    user_id = query.from_user.id
    if query.data == "cancel":
        user_data.pop(user_id, None)
        await query.message.edit("❌ Post canceled.")
        return

    data = user_data.get(user_id)
    if not data:
        await query.message.edit("⚠️ Session expired.")
        return

    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("480p", url=f"https://t.me/{BOT_USERNAME}?start={data['480p']}"),
            InlineKeyboardButton("720p", url=f"https://t.me/{BOT_USERNAME}?start={data['720p']}"),
            InlineKeyboardButton("1080p", url=f"https://t.me/{BOT_USERNAME}?start={data['1080p']}")
        ]
    ])
    caption = f"**{data['title']} {data['season']} {data['episode']}**"
    await client.send_photo(chat_id=TARGET_CHANNEL, photo=data["cover"], caption=caption, reply_markup=buttons)
    await query.message.edit("✅ Posted to channel.")
    user_data.pop(user_id)


# Step 4: Deep link handler
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message: Message):
    if len(message.command) > 1:
        param = message.command[1]
        try:
            decoded = base64.urlsafe_b64decode(param).decode()
            if decoded.startswith("get-"):
                file_id = decoded[4:]
                await message.reply_video(video=file_id, caption="🎬 Here's your file!")
                return
        except Exception:
            pass
        await message.reply("❌ Invalid or expired file link.")
    else:
        await message.reply("👋 Send a cover photo to begin creating an anime post.")

app.run()
