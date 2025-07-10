from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
import re

# ------------------ Configuration ------------------
API_ID = 28015531
API_HASH = "2ab4ba37fd5d9ebf1353328fc915ad28"
BOT_TOKEN = "7514636092:AAFY3O_h8NAaRMUlDv1dDEuZDhzxItCHHy0"

TARGET_CHANNEL = -1002445548441  # Your Post Channel
DB_CHANNEL = -1002316552580      # Your DB Channel

# ------------------ Runtime Storage ------------------
user_data = {}
video_store = {}

# ------------------ Start Client ------------------
app = Client("anime_auto_post_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)


@app.on_message(filters.command("start") & filters.private)
async def start_bot(_, message):
    user_data[message.from_user.id] = {}
    await message.reply("👋 Hi kuty! Please send the **cover photo** for the anime.")


@app.on_message(filters.private & filters.photo)
async def get_cover(_, message):
    uid = message.from_user.id
    if uid not in user_data:
        return await message.reply("⚠️ Start with /start")

    user_data[uid]["cover"] = message.photo.file_id
    user_data[uid]["videos"] = {}
    await message.reply("✅ Cover saved!\nNow send the 480p video file (as video or document).")


@app.on_message(filters.private & (filters.video | filters.document))
async def get_video(_, message):
    uid = message.from_user.id
    if uid not in user_data or "cover" not in user_data[uid]:
        return await message.reply("⚠️ Please send the cover photo first.")

    file_name = None

    if message.video:
        file_name = message.video.file_name
    elif message.document and message.document.mime_type.startswith("video/"):
        file_name = message.document.file_name
    else:
        return await message.reply("❌ This file is not a valid video.")

    quality_match = re.search(r"(\d{3,4}p)", file_name)
    if not quality_match:
        return await message.reply("❗ Filename must contain [480p], [720p], or [1080p].")

    quality = quality_match.group(1)

    # Forward to DB channel and store message ID
    forwarded = await message.forward(DB_CHANNEL)
    user_data[uid]["videos"][quality] = forwarded.message_id

    if len(user_data[uid]["videos"]) == 1:
        await message.reply("📥 Now send the 720p video file.")
    elif len(user_data[uid]["videos"]) == 2:
        await message.reply("📥 Now send the 1080p video file.")
    elif len(user_data[uid]["videos"]) == 3:
        await generate_preview(_, message)


async def generate_preview(client: Client, message):
    uid = message.from_user.id
    data = user_data[uid]

    first_msg_id = list(data["videos"].values())[0]
    first_msg = await client.get_messages(DB_CHANNEL, first_msg_id)
    filename = first_msg.video.file_name if first_msg.video else first_msg.document.file_name

    title_match = re.match(r"(.+?)\sS(\d+)\s+Ep(\d+)]", filename)
    if not title_match:
        return await message.reply("❌ Filename format must be:\nClevatess S01 Ep[01] [480p].mkv")

    title, season, episode = title_match.groups()
    data["title"] = title.strip()
    data["season"] = season
    data["episode"] = episode

    caption = f"""
🔰 <b>{title}</b> 🔰

▶️ <b>Season</b> : {season}
▶️ <b>Episode</b> : {episode}
▶️ <b>Language</b> : Tamil
▶️ <b>Codec</b> : HEVC
▶️ <b>Quality</b> : 480p, 720p, 1080p

➤ <b>EPISODE {episode}</b> ADDED 🔥
""".strip()

    data["caption"] = caption

    await message.reply_photo(
        photo=data["cover"],
        caption=caption,
        parse_mode="html",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Send to Channel", callback_data="send_post")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_post")]
        ])
    )


@app.on_callback_query()
async def handle_callbacks(client: Client, query: CallbackQuery):
    uid = query.from_user.id
    data = user_data.get(uid)

    if query.data == "cancel_post":
        await query.message.edit_caption("❌ Post creation cancelled.")
        user_data.pop(uid, None)
        return

    if query.data == "send_post":
        if not data:
            return await query.answer("⚠️ Session expired. Use /start again.", show_alert=True)

        msg = await client.send_photo(
            chat_id=TARGET_CHANNEL,
            photo=data["cover"],
            caption=data["caption"],
            parse_mode="html"
        )

        buttons = []
        for quality, msg_id in sorted(data["videos"].items()):
            unique_id = f"{uid}_{quality}"
            video_store[unique_id] = msg_id
            buttons.append([
                InlineKeyboardButton(quality, callback_data=f"sendfile|{unique_id}")
            ])

        await client.edit_message_reply_markup(
            chat_id=TARGET_CHANNEL,
            message_id=msg.message_id,
            reply_markup=InlineKeyboardMarkup(buttons)
        )

        await query.message.edit_caption("✅ Post sent to channel with buttons.")
        user_data.pop(uid, None)
        return

    if query.data.startswith("sendfile|"):
        _, unique_id = query.data.split("|")
        msg_id = video_store.get(unique_id)

        if not msg_id:
            return await query.answer("⚠️ File not found.", show_alert=True)

        try:
            await client.copy_message(
                chat_id=query.from_user.id,
                from_chat_id=DB_CHANNEL,
                message_id=msg_id
            )
        except Exception as e:
            await query.answer("❗ Please /start the bot first to receive files.", show_alert=True)


app.run()
