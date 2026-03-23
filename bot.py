import os
import asyncio
import subprocess
import shutil
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.enums import MessageMediaType
from config import Config
import pymongo
import re

# Initialize bot
app = Client(
    "media_bot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN
)

# Initialize MongoDB
mongo_client = pymongo.MongoClient(Config.MONGO_URI)
db = mongo_client[Config.DB_NAME]
thumb_collection = db["thumbnails"]
user_collection = db["users"]

# Helper function to save user
async def save_user(user_id, username=None):
    user_collection.update_one(
        {"user_id": user_id},
        {"$set": {"username": username, "last_active": datetime.now()}},
        upsert=True
    )

# Helper function to get thumbnail
async def get_thumbnail(user_id):
    data = thumb_collection.find_one({"user_id": user_id})
    return data["file_id"] if data else None

# Helper function to set thumbnail
async def set_thumbnail(user_id, file_id):
    thumb_collection.update_one(
        {"user_id": user_id},
        {"$set": {"file_id": file_id}},
        upsert=True
    )

# Helper function to delete thumbnail
async def del_thumbnail(user_id):
    thumb_collection.delete_one({"user_id": user_id})

# Progress callback
async def progress_callback(current, total, message, start_time):
    percent = current * 100 / total
    elapsed = datetime.now() - start_time
    speed = current / elapsed.total_seconds()
    eta = (total - current) / speed if speed > 0 else 0
    
    progress_text = f"📥 Downloading: {percent:.1f}%\n"
    progress_text += f"⚡ Speed: {speed/1024/1024:.1f} MB/s\n"
    progress_text += f"⏱️ ETA: {eta//60:.0f}m {eta%60:.0f}s"
    
    await message.edit_text(progress_text)

# ==================== COMMANDS ====================

@app.on_message(filters.command("start"))
async def start_command(client, message: Message):
    user = message.from_user
    await save_user(user.id, user.username)
    
    await message.reply_text(
        f"👋 **Hello {user.first_name}!**\n\n"
        "I can help you manage your media files:\n\n"
        "📝 **Commands:**\n"
        "• `/rename` - Rename any file\n"
        "• `/convert` - Convert videos to MP4\n"
        "• `/setthumb` - Set permanent thumbnail\n"
        "• `/delthumb` - Delete thumbnail\n"
        "• `/viewthumb` - View current thumbnail\n"
        "• `/batch` - Batch rename files\n\n"
        "🎬 **Features:**\n"
        "• Custom thumbnail for videos\n"
        "• Video compression & conversion\n"
        "• Batch file processing\n\n"
        "Send me any file to get started!",
        disable_web_page_preview=True
    )

@app.on_message(filters.command("setthumb"))
async def set_thumb(client, message: Message):
    if message.reply_to_message and message.reply_to_message.photo:
        photo = message.reply_to_message.photo
        file_id = photo.file_id
        await set_thumbnail(message.from_user.id, file_id)
        await message.reply_text("✅ **Thumbnail saved!** This will be used for all your videos.")
    elif message.reply_to_message and message.reply_to_message.document:
        # Handle document image
        doc = message.reply_to_message.document
        if doc.mime_type and doc.mime_type.startswith("image/"):
            await set_thumbnail(message.from_user.id, doc.file_id)
            await message.reply_text("✅ **Thumbnail saved from document!**")
    else:
        await message.reply_text(
            "❌ **Usage:** Reply to an image with `/setthumb`\n\n"
            "Send any image and reply with /setthumb to set it as your permanent thumbnail."
        )

@app.on_message(filters.command("delthumb"))
async def del_thumb(client, message: Message):
    await del_thumbnail(message.from_user.id)
    await message.reply_text("🗑️ **Thumbnail deleted!**")

@app.on_message(filters.command("viewthumb"))
async def view_thumb(client, message: Message):
    thumb_id = await get_thumbnail(message.from_user.id)
    if thumb_id:
        await message.reply_photo(thumb_id, caption="🖼️ Your current thumbnail")
    else:
        await message.reply_text("❌ No thumbnail set. Use `/setthumb` to set one.")

@app.on_message(filters.command("rename"))
async def rename_command(client, message: Message):
    if message.reply_to_message and message.reply_to_message.document:
        await message.reply_text(
            "📝 **Send me the new filename**\n\n"
            "Example: `my_video.mp4`\n"
            "Send /cancel to cancel.",
            quote=True
        )
        # Store original message ID for callback
        # (In production, use a dictionary or database)
    else:
        await message.reply_text(
            "❌ **Usage:** Reply to a file with `/rename`",
            quote=True
        )

@app.on_message(filters.command("convert"))
async def convert_command(client, message: Message):
    if message.reply_to_message and message.reply_to_message.video:
        await message.reply_text(
            "🎬 **Video conversion started!**\n\n"
            "Converting to MP4 (H.264)...\n"
            "This may take a few moments.",
            quote=True
        )
        
        video = message.reply_to_message.video
        file_path = await client.download_media(video)
        
        # Convert video
        output_path = f"converted_{datetime.now().timestamp()}.mp4"
        
        cmd = [
            "ffmpeg", "-i", file_path,
            "-c:v", "libx264", "-preset", "fast",
            "-b:v", Config.VIDEO_BITRATE,
            "-r", str(Config.VIDEO_FPS),
            "-c:a", "aac", "-b:a", "128k",
            output_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()
        
        # Send converted video
        thumb_id = await get_thumbnail(message.from_user.id)
        caption = f"✅ **Converted to MP4**\n\nOriginal: {video.file_name}\nSize: {video.file_size / 1024 / 1024:.1f} MB"
        
        await client.send_video(
            message.chat.id,
            output_path,
            thumb=thumb_id,
            caption=caption
        )
        
        # Cleanup
        os.remove(file_path)
        os.remove(output_path)
        await message.delete()
        
    else:
        await message.reply_text("❌ **Usage:** Reply to a video with `/convert`", quote=True)

@app.on_message(filters.command("batch"))
async def batch_command(client, message: Message):
    if message.reply_to_message and message.reply_to_message.media_group_id:
        # Handle media group (multiple files)
        await message.reply_text("📦 **Batch mode:** Send me all filenames, one per line.\n\nSend /cancel to cancel.")
        # Store media group ID for processing
    else:
        await message.reply_text("❌ **Usage:** Reply to a media group (multiple files) with `/batch`", quote=True)

@app.on_message(filters.document | filters.video)
async def handle_file(client, message: Message):
    # Check force subscribe
    if Config.FORCE_SUB_CHANNEL:
        try:
            member = await client.get_chat_member(Config.FORCE_SUB_CHANNEL, message.from_user.id)
            if member.status == "left":
                await message.reply_text(
                    f"⚠️ **Please join our channel first:**\n{Config.FORCE_SUB_CHANNEL}",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("Join Channel", url=f"https://t.me/{Config.FORCE_SUB_CHANNEL[1:]}")
                    ]])
                )
                return
        except:
            pass
    
    media = message.document or message.video
    if not media:
        return
    
    # Show options
    buttons = [
        [InlineKeyboardButton("✏️ Rename", callback_data=f"rename_{message.id}")],
        [InlineKeyboardButton("🎬 Convert to MP4", callback_data=f"convert_{message.id}")],
        [InlineKeyboardButton("🖼️ Change Thumbnail", callback_data=f"thumb_{message.id}")]
    ]
    
    if message.video:
        buttons.append([InlineKeyboardButton("📦 Compress Video", callback_data=f"compress_{message.id}")])
    
    await message.reply_text(
        "🎯 **What would you like to do with this file?**",
        reply_markup=InlineKeyboardMarkup(buttons),
        quote=True
    )

@app.on_callback_query()
async def handle_callback(client, callback: CallbackQuery):
    data = callback.data
    user_id = callback.from_user.id
    
    if data.startswith("rename_"):
        await callback.message.delete()
        await callback.message.reply_text(
            "📝 **Send me the new filename**\n\n"
            "Example: `my_file.mp4`\n\n"
            "Use extension: .mp4, .mkv, .jpg, .pdf, etc.\n"
            "Send /cancel to cancel.",
            quote=True
        )
        # Store for next message
        # In production, use a dictionary or database
        # For now, we'll use a global variable (not recommended for production)
        if not hasattr(app, 'pending_renames'):
            app.pending_renames = {}
        app.pending_renames[user_id] = callback.message.reply_to_message.id
        
    elif data.startswith("convert_"):
        await callback.answer("Converting video...")
        # Get the original message and convert
        # Similar to convert_command logic
        
    elif data.startswith("thumb_"):
        await callback.answer("Thumbnail change coming soon!")
        
    elif data.startswith("compress_"):
        await callback.answer("Compressing video...")
    
    await callback.answer()

# Handle rename input
@app.on_message(filters.text & filters.private)
async def handle_rename_input(client, message: Message):
    if not hasattr(app, 'pending_renames'):
        return
    
    if message.text == "/cancel":
        if message.from_user.id in app.pending_renames:
            del app.pending_renames[message.from_user.id]
            await message.reply_text("❌ **Cancelled!**")
        return
    
    if message.from_user.id in app.pending_renames:
        original_msg_id = app.pending_renames[message.from_user.id]
        new_name = message.text.strip()
        
        # Get original message
        original_msg = await client.get_messages(message.chat.id, original_msg_id)
        if not original_msg or not original_msg.document:
            del app.pending_renames[message.from_user.id]
            await message.reply_text("❌ Original file not found!")
            return
        
        media = original_msg.document
        
        # Download file
        status_msg = await message.reply_text("📥 **Downloading file...**")
        file_path = await client.download_media(media)
        
        await status_msg.edit_text("🔄 **Renaming file...**")
        
        # Get thumbnail
        thumb_id = await get_thumbnail(message.from_user.id)
        
        # Send renamed file
        caption = f"✅ **Renamed:** `{new_name}`\n\nOriginal: {media.file_name}\nSize: {media.file_size / 1024 / 1024:.1f} MB"
        
        if new_name.endswith(('.mp4', '.mkv', '.avi')):
            await client.send_video(
                message.chat.id,
                file_path,
                caption=caption,
                thumb=thumb_id,
                file_name=new_name
            )
        else:
            await client.send_document(
                message.chat.id,
                file_path,
                caption=caption,
                thumb=thumb_id,
                file_name=new_name
            )
        
        # Cleanup
        os.remove(file_path)
        await status_msg.delete()
        del app.pending_renames[message.from_user.id]

print("🤖 Bot started!")
app.run()
