import logging
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
import re

# Credentials (Only for test use; don't expose in production)
API_ID = 28015531
API_HASH = "2ab4ba37fd5d9ebf1353328fc915ad28"
BOT_TOKEN = "7514636092:AAFY3O_h8NAaRMUlDv1dDEuZDhzxItCHHy0"
TARGET_CHANNEL = -1002445548441
DB_CHANNEL = -1002316552580

logging.basicConfig(level=logging.INFO)
bot = Client("AnimePostBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

user_data = {}

@bot.on_message(filters.private & filters.command("start"))
async def start_cmd(client, message: Message):
    if message.text.startswith("/start vid_"):
        video_id = message.text.split("vid_")[1]
        try:
            await client.forward_messages(
                chat_id=message.chat.id,
                from_chat_id=DB_CHANNEL,
                message_ids=int(video_id)
            )
        except Exception:
            await message.reply("❌ File not found or expired.")
        return

    await message.reply("👋 Hello! Please send the **cover photo** to begin.")

@bot.on_message(filters.private & filters.photo)
async def handle_cover(client, message: Message):
    user_id = message.from_user.id
    user_data[user_id] = {"cover": message.photo.file_id, "videos": []}
    await message.reply("✅ Cover received.\n\nNow send **3 video/document files** (480p, 720p, 1080p).")

@bot.on_message(filters.private & (filters.video | filters.document))
async def handle_file(client, message: Message):
    user_id = message.from_user.id
    if user_id not in user_data or "cover" not in user_data[user_id]:
        await message.reply("❗ Please send the **cover photo** first.")
        return

    file = message.video or message.document
    file_name = file.file_name
    file_id = file.file_id

    # Parse title, episode, quality
    match = re.search(r"(.*?)\s*[Ss](\d+)\s*[Ee]p(\d+).*?(\d{3,4}p)", file_name)
    if not match:
        await message.reply("❌ Filename must be like: `Title S01 Ep[01] [720p].mkv`")
        return

    title = match.group(1).strip()
    season = match.group(2)
    episode = match.group(3)
    quality = match.group(4)

    user_data[user_id].update({"title": title, "season": season, "episode": episode})

    # Save file to DB channel
    sent_msg = await client.send_document(DB_CHANNEL, file_id) if message.document else await client.send_video(DB_CHANNEL, file_id)

    user_data[user_id]["videos"].append({
        "file_id": sent_msg.message_id,
        "quality": quality
    })

    await message.reply(f"✅ Saved **{quality}** file.")

    # All 3 files received
    if len(user_data[user_id]["videos"]) == 3:
        buttons = [
            [InlineKeyboardButton(v["quality"], url=f"https://t.me/{(await client.get_me()).username}?start=vid_{v['file_id']}")]
            for v in user_data[user_id]["videos"]
        ]
        buttons.append([
            InlineKeyboardButton("✅ Send", callback_data="send"),
            InlineKeyboardButton("❌ Cancel", callback_data="cancel")
        ])

        caption = f"**{title}** - S{season.zfill(2)}E{episode.zfill(2)}\n\n🎥 Available Qualities:"
        for v in user_data[user_id]["videos"]:
            caption += f"\n🔹 {v['quality']}"

        await message.reply_photo(
            photo=user_data[user_id]["cover"],
            caption=caption,
            reply_markup=InlineKeyboardMarkup(buttons)
        )

@bot.on_callback_query()
async def callback_handler(client, cb):
    user_id = cb.from_user.id
    if user_id not in user_data:
        await cb.answer("❌ Session expired.", show_alert=True)
        return

    if cb.data == "cancel":
        del user_data[user_id]
        await cb.message.edit("❌ Post creation cancelled.")
        return

    if cb.data == "send":
        data = user_data[user_id]
        buttons = [
            [InlineKeyboardButton(v["quality"], url=f"https://t.me/{(await client.get_me()).username}?start=vid_{v['file_id']}")]
            for v in data["videos"]
        ]

        caption = f"**{data['title']}** - S{data['season'].zfill(2)}E{data['episode'].zfill(2)}\n\n🎥 Available Qualities:"
        for v in data["videos"]:
            caption += f"\n🔹 {v['quality']}"

        await client.send_photo(
            chat_id=TARGET_CHANNEL,
            photo=data["cover"],
            caption=caption,
            reply_markup=InlineKeyboardMarkup(buttons)
        )

        await cb.message.edit("✅ Post sent to channel!")
        del user_data[user_id]

bot.run()
