from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import re

# === Configuration ===
api_id = 28015531           # Your API ID (int)
api_hash = "2ab4ba37fd5d9ebf1353328fc915ad28" # Your API hash (str)
bot_token = "7514636092:AAFY3O_h8NAaRMUlDv1dDEuZDhzxItCHHy0"  # Your bot token (str)

DB_CHANNEL = -1002316552580    # Database channel ID
POST_CHANNEL = -1002445548441  # Target channel ID

app = Client("file_sharing_bot", api_id=api_id, api_hash=api_hash, bot_token=bot_token)

# Sessions: user_id -> session data
sessions = {}

# Regex to parse filenames like "Title S01 Ep02 [720p].mkv"
FILENAME_REGEX = re.compile(r"^(.+?) S(\d+) Ep?(\d+)? (\d+p)\.mkv$")

def parse_filename(filename):
    """
    Parse a filename of the form "Title S01 Ep02 [720p].mkv".
    Returns (title, season, episode, resolution) or None on failure.
    """
    match = FILENAME_REGEX.match(filename)
    if not match:
        return None
    title, season, episode, res = match.groups()
    return title.strip(), int(season), int(episode), res

@app.on_message(filters.command("start"))
async def start_handler(client, message):
    """
    Handle /start. If a deep-link parameter vid_<id> is given, forward the video.
    Otherwise, send a welcome message.
    """
    args = message.text.split()
    if len(args) > 1 and args[1].startswith("vid_"):
        # Deep link to a video in the DB channel
        vid_str = args[1].split("_", 1)[1]
        if not vid_str.isdigit():
            await message.reply_text("⚠️ Invalid file identifier.")
            return
        msg_id = int(vid_str)
        try:
            # Copy (forward) the video from DB channel to the user
            await client.copy_message(chat_id=message.chat.id,
                                      from_chat_id=DB_CHANNEL,
                                      message_id=msg_id)
        except Exception as e:
            await message.reply_text("⚠️ File not found or not accessible.")
        return
    # No parameter: normal /start
    await message.reply_text(
        "👋 Welcome! To create a new post, send /upload"
    )

@app.on_message(filters.command("upload"))
async def upload_handler(client, message):
    """
    Starts a new upload session for the user.
    """
    user_id = message.from_user.id
    if user_id in sessions:
        await message.reply_text("⚠️ You have an unfinished session. Send /cancel to abort or continue the current upload.")
        return
    # Initiate session and ask for cover image
    sessions[user_id] = {'step': 'awaiting_cover'}
    await message.reply_text("📷 Please send the cover image (as photo or document).")

@app.on_message(filters.command("cancel"))
async def cancel_handler(client, message):
    """
    Cancel any ongoing session for the user.
    """
    user_id = message.from_user.id
    if user_id in sessions:
        del sessions[user_id]
        await message.reply_text("✅ Upload cancelled.")
    else:
        await message.reply_text("ℹ️ No active upload session to cancel.")

@app.on_message(filters.photo | filters.document)
async def handle_cover_or_video(client, message):
    """
    Handles cover image or video documents based on session state.
    """
    user_id = message.from_user.id
    if user_id not in sessions:
        # No session: interpret a photo/doc as the cover to start a session
        # Only if it's an image (photo or document with image MIME)
        if message.photo or (message.document and (message.document.mime_type or "").startswith("image/")):
            # Start a new session with this cover
            sessions[user_id] = {'step': 'awaiting_video_480'}
            # Save cover info
            if message.photo:
                sessions[user_id]['cover_id'] = message.photo[-1].file_id
                sessions[user_id]['cover_type'] = 'photo'
            else:
                sessions[user_id]['cover_id'] = message.document.file_id
                sessions[user_id]['cover_type'] = 'document'
            await message.reply_text(
                "✅ Cover image received.\nNow send the **480p** video file "
                "(e.g. `Title S01 Ep01 [480p].mkv`).", 
                parse_mode="markdown"
            )
            return
        else:
            # Ignoring non-media outside a session
            return

    # If session exists, handle based on expected step
    session = sessions[user_id]
    step = session.get('step')

    # If expecting cover
    if step == 'awaiting_cover':
        if message.photo or (message.document and (message.document.mime_type or "").startswith("image/")):
            # Save cover and move to 480p
            if message.photo:
                session['cover_id'] = message.photo[-1].file_id
                session['cover_type'] = 'photo'
            else:
                session['cover_id'] = message.document.file_id
                session['cover_type'] = 'document'
            session['step'] = 'awaiting_video_480'
            await message.reply_text(
                "✅ Cover image saved.\nNow send the **480p** video file "
                "(e.g. `Title S01 Ep01 [480p].mkv`).",
                parse_mode="markdown"
            )
        else:
            await message.reply_text("⚠️ Please send a valid cover image as photo or document.")
        return

    # If expecting videos (480p, 720p, 1080p)
    if step in ['awaiting_video_480', 'awaiting_video_720', 'awaiting_video_1080']:
        # Check that the message is a video or document with .mkv
        file_name = None
        if message.document and message.document.file_name:
            file_name = message.document.file_name
            file_id = message.document.file_id
        elif message.video and message.video.file_name:
            file_name = message.video.file_name
            file_id = message.video.file_id
        else:
            await message.reply_text("⚠️ Please send a video file in MKV format with the correct filename.")
            return

        # Check extension
        if not file_name.lower().endswith(".mkv"):
            await message.reply_text("⚠️ The file must be an MKV. Please resend with the correct extension.")
            return

        parsed = parse_filename(file_name)
        if not parsed:
            await message.reply_text(
                "⚠️ Filename format incorrect. It should be like:\n"
                "`Title S01 Ep01 [480p].mkv`\n"
                "Make sure the title, Sxx, EpYY, and [resolution] are correct.",
                parse_mode="markdown"
            )
            return

        title, season, episode, resolution = parsed
        # Determine which resolution we are expecting
        expected_res = None
        if step == 'awaiting_video_480':
            expected_res = "480p"
        elif step == 'awaiting_video_720':
            expected_res = "720p"
        elif step == 'awaiting_video_1080':
            expected_res = "1080p"

        if resolution != expected_res:
            await message.reply_text(f"⚠️ This is a {resolution} file. Please send the *{expected_res}* version.")
            return

        # First video: record title/season/episode
        if 'title' not in session:
            session['title'] = title
            session['season'] = season
            session['episode'] = episode
        else:
            # Check consistency with previous title/season/episode
            if title != session['title'] or season != session['season'] or episode != session['episode']:
                await message.reply_text(
                    "⚠️ Title, season or episode does not match the first video. "
                    "Please make sure all filenames use the same Title, Sxx and EpYY."
                )
                return

        # Forward (copy) this video to the DB channel
        try:
            forwarded = await client.copy_message(
                chat_id=DB_CHANNEL,
                from_chat_id=message.chat.id,
                message_id=message.message_id
            )
        except Exception as e:
            await message.reply_text("⚠️ Failed to forward video to database. Please try again.")
            return

        # Store DB message ID for this resolution
        session.setdefault('files', {})[resolution] = forwarded.message_id

        # Advance to next step or preview
        if step == 'awaiting_video_480':
            session['step'] = 'awaiting_video_720'
            await message.reply_text(
                "✅ 480p video saved.\nNow send the **720p** video file (e.g. `Title S01 Ep01 [720p].mkv`).",
                parse_mode="markdown"
            )
        elif step == 'awaiting_video_720':
            session['step'] = 'awaiting_video_1080'
            await message.reply_text(
                "✅ 720p video saved.\nNow send the **1080p** video file (e.g. `Title S01 Ep01 [1080p].mkv`).",
                parse_mode="markdown"
            )
        else:
            # Received 1080p, move to preview
            session['step'] = 'awaiting_confirmation'
            # Prepare preview caption
            title_html = session['title']
            season_num = session['season']
            episode_num = session['episode']
            caption = f"<b>{title_html}</b> S{season_num:02d} Ep{episode_num:02d}\n"
            caption += "Available Quality:\n"
            caption += "• 480p\n• 720p\n• 1080p"
            # Build the inline keyboard for preview (including Send button)
            me = await client.get_me()
            bot_username = me.username
            id480 = session['files']['480p']
            id720 = session['files']['720p']
            id1080 = session['files']['1080p']
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("480p", url=f"https://t.me/{bot_username}?start=vid_{id480}"),
                    InlineKeyboardButton("720p", url=f"https://t.me/{bot_username}?start=vid_{id720}"),
                    InlineKeyboardButton("1080p", url=f"https://t.me/{bot_username}?start=vid_{id1080}")
                ],
                [InlineKeyboardButton("Send ✅", callback_data="send")]
            ])
            # Send preview (cover + caption + buttons)
            if session['cover_type'] == 'photo':
                await client.send_photo(
                    chat_id=message.chat.id,
                    photo=session['cover_id'],
                    caption=caption,
                    reply_markup=keyboard,
                    parse_mode="html"
                )
            else:
                await client.send_document(
                    chat_id=message.chat.id,
                    document=session['cover_id'],
                    caption=caption,
                    reply_markup=keyboard,
                    parse_mode="html"
                )
            # Optionally delete the last bot message to keep chat clean
            await message.reply_text("✅ 1080p video saved. Sending preview below...")
        return

    # Any other state where we received an image or document unexpectedly
    if step == 'awaiting_confirmation':
        await message.reply_text("⚠️ Please press the **Send** button to post the preview, or /cancel to abort.")
   @app.on_message(filters.text)
async def handle_text_fallback(client, message):
    """
    Catch-all for when text is sent instead of expected media.
    """
    user_id = message.from_user.id
    if user_id in sessions:
        step = sessions[user_id]['step']
        if step == 'awaiting_video_480':
            await message.reply_text("⚠️ Please send the 480p video file as specified.")
        elif step == 'awaiting_video_720':
            await message.reply_text("⚠️ Please send the 720p video file as specified.")
        elif step == 'awaiting_video_1080':
            await message.reply_text("⚠️ Please send the 1080p video file as specified.")
        elif step == 'awaiting_confirmation':
            await message.reply_text("⚠️ Press **Send** to publish or /cancel to abort.")
        else:
            return

@app.on_callback_query()
async def callback_query_handler(client, callback_query):
    """
    Handle callback queries (the Send button).
    """
    user_id = callback_query.from_user.id
    data = callback_query.data
    if data == "send" and user_id in sessions:
        session = sessions[user_id]
        # Build final post caption and buttons (same as preview, without 'Send')
        title_html = session['title']
        season_num = session['season']
        episode_num = session['episode']
        caption = f"<b>{title_html}</b> S{season_num:02d} Ep{episode_num:02d}\n"
        caption += "Available Quality:\n"
        caption += "• 480p\n• 720p\n• 1080p"
        me = await client.get_me()
        bot_username = me.username
        id480 = session['files']['480p']
        id720 = session['files']['720p']
        id1080 = session['files']['1080p']
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("480p", url=f"https://t.me/{bot_username}?start=vid_{id480}"),
                InlineKeyboardButton("720p", url=f"https://t.me/{bot_username}?start=vid_{id720}"),
                InlineKeyboardButton("1080p", url=f"https://t.me/{bot_username}?start=vid_{id1080}")
            ]
        ])
        # Send to target channel
        if session['cover_type'] == 'photo':
            await client.send_photo(
                chat_id=POST_CHANNEL,
                photo=session['cover_id'],
                caption=caption,
                reply_markup=keyboard,
                parse_mode="html"
            )
        else:
            await client.send_document(
                chat_id=POST_CHANNEL,
                document=session['cover_id'],
                caption=caption,
                reply_markup=keyboard,
                parse_mode="html"
            )
        # Inform the user and clean up session
        await callback_query.answer("✅ Post sent to channel!")
        await client.send_message(chat_id=user_id, text="🎉 Your post has been published to the channel.")
        del sessions[user_id]
    else:
        await callback_query.answer()  # Just to stop loading if something else

app.run()
