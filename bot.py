import os
import asyncio
import subprocess
import shutil
import re
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
import pymongo

# =============== CONFIGURATION ===============
# Ye sab environment variables mein daalna
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
MONGO_URI = os.environ.get("MONGO_URI", "")
ADMIN = [int(x) for x in os.environ.get("ADMIN", "").split()] if os.environ.get("ADMIN") else []

# Bot start
app = Client("media_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# MongoDB setup
mongo_client = pymongo.MongoClient(MONGO_URI)
db = mongo_client["telegram_bot"]
users_db = db["users"]
thumb_db = db["thumbnails"]
rename_db = db["pending_rename"]

# =============== HELPER FUNCTIONS ===============

async def save_user(user_id, username=None, first_name=None):
    """Save user to database"""
    users_db.update_one(
        {"user_id": user_id},
        {"$set": {
            "username": username,
            "first_name": first_name,
            "last_active": datetime.now()
        }},
        upsert=True
    )

async def get_thumbnail(user_id):
    """Get user's saved thumbnail"""
    data = thumb_db.find_one({"user_id": user_id})
    return data["file_id"] if data else None

async def set_thumbnail(user_id, file_id):
    """Save thumbnail for user"""
    thumb_db.update_one(
        {"user_id": user_id},
        {"$set": {"file_id": file_id}},
        upsert=True
    )

async def delete_thumbnail(user_id):
    """Delete user's thumbnail"""
    thumb_db.delete_one({"user_id": user_id})

async def convert_video(input_path, output_path):
    """Convert video to MP4 format"""
    cmd = [
        "ffmpeg", "-i", input_path,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        output_path
    ]
    
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    await process.communicate()
    return process.returncode == 0

async def compress_video(input_path, output_path, quality="medium"):
    """Compress video with quality options"""
    # quality: high, medium, low
    crf_values = {"high": 18, "medium": 23, "low": 28}
    crf = crf_values.get(quality, 23)
    
    cmd = [
        "ffmpeg", "-i", input_path,
        "-c:v", "libx264",
        "-preset", "slow",
        "-crf", str(crf),
        "-c:a", "aac",
        "-b:a", "96k",
        output_path
    ]
    
    process = await asyncio.create_subprocess_exec(*cmd)
    await process.communicate()
    return process.returncode == 0

# =============== COMMANDS ===============

@app.on_message(filters.command("start"))
async def start_command(client, message):
    user = message.from_user
    await save_user(user.id, user.username, user.first_name)
    
    await message.reply_text(
        f"🎬 **Welcome {user.first_name}!**\n\n"
        "Main ek powerful media manager bot hoon.\n\n"
        "**What I can do:**\n"
        "✏️ Rename any file\n"
        "🎥 Convert videos to MP4\n"
        "🖼️ Set permanent thumbnails\n"
        "📦 Compress videos\n"
        "🔄 Batch rename files\n\n"
        "**Commands:**\n"
        "/rename - Rename file\n"
        "/setthumb - Set thumbnail\n"
        "/delthumb - Delete thumbnail\n"
        "/viewthumb - View thumbnail\n"
        "/convert - Convert video to MP4\n"
        "/compress - Compress video\n"
        "/batch - Batch rename\n\n"
        "**Simply send me any file!** 🚀",
        disable_web_page_preview=True
    )

@app.on_message(filters.command("setthumb"))
async def set_thumb_command(client, message):
    """Set permanent thumbnail"""
    if message.reply_to_message:
        if message.reply_to_message.photo:
            await set_thumbnail(message.from_user.id, message.reply_to_message.photo.file_id)
            await message.reply_text("✅ **Thumbnail saved!** Ab ye automatically videos ke saath use hoga.")
        elif message.reply_to_message.document and message.reply_to_message.document.mime_type.startswith("image/"):
            await set_thumbnail(message.from_user.id, message.reply_to_message.document.file_id)
            await message.reply_text("✅ **Thumbnail saved from document!**")
        else:
            await message.reply_text("❌ Please reply to an **image** with /setthumb")
    else:
        await message.reply_text(
            "📸 **How to set thumbnail:**\n\n"
            "1. Send any image\n"
            "2. Reply to that image with `/setthumb`\n\n"
            "Thumbnail will be used for all your videos!"
        )

@app.on_message(filters.command("delthumb"))
async def del_thumb_command(client, message):
    """Delete thumbnail"""
    await delete_thumbnail(message.from_user.id)
    await message.reply_text("🗑️ **Thumbnail deleted!**")

@app.on_message(filters.command("viewthumb"))
async def view_thumb_command(client, message):
    """View current thumbnail"""
    thumb = await get_thumbnail(message.from_user.id)
    if thumb:
        await message.reply_photo(thumb, caption="🖼️ **Your current thumbnail**")
    else:
        await message.reply_text("❌ **No thumbnail set.**\n\nUse /setthumb to set one.")

@app.on_message(filters.command("convert"))
async def convert_command(client, message):
    """Convert video to MP4"""
    if not message.reply_to_message or not message.reply_to_message.video:
        await message.reply_text("❌ Reply to a **video** with /convert")
        return
    
    msg = await message.reply_text("🎬 **Converting video to MP4...**\n\n⏳ Please wait...")
    
    try:
        # Download video
        video = message.reply_to_message.video
        input_path = await client.download_media(video)
        
        # Convert
        output_path = f"converted_{datetime.now().timestamp()}.mp4"
        success = await convert_video(input_path, output_path)
        
        if success:
            # Get thumbnail
            thumb = await get_thumbnail(message.from_user.id)
            
            # Send converted video
            await client.send_video(
                message.chat.id,
                output_path,
                thumb=thumb,
                caption=f"✅ **Converted to MP4!**\n\nOriginal: {video.file_name}\nSize: {video.file_size/1024/1024:.1f} MB → {os.path.getsize(output_path)/1024/1024:.1f} MB"
            )
            await msg.edit_text("✅ **Conversion complete!**")
        else:
            await msg.edit_text("❌ **Conversion failed!**")
        
        # Cleanup
        if os.path.exists(input_path):
            os.remove(input_path)
        if os.path.exists(output_path):
            os.remove(output_path)
            
    except Exception as e:
        await msg.edit_text(f"❌ Error: {str(e)}")

@app.on_message(filters.command("compress"))
async def compress_command(client, message):
    """Compress video"""
    if not message.reply_to_message or not message.reply_to_message.video:
        await message.reply_text("❌ Reply to a **video** with /compress")
        return
    
    # Quality options
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎯 High Quality", callback_data="compress_high")],
        [InlineKeyboardButton("⚖️ Medium Quality", callback_data="compress_medium")],
        [InlineKeyboardButton("📦 Low Quality (Smallest)", callback_data="compress_low")]
    ])
    
    await message.reply_text(
        "📦 **Select compression quality:**\n\n"
        "• High - Slightly smaller, good quality\n"
        "• Medium - Balanced\n"
        "• Low - Maximum compression",
        reply_markup=keyboard
    )

# =============== FILE HANDLING ===============

@app.on_message(filters.document | filters.video)
async def handle_file(client, message):
    """Handle any file sent to bot"""
    user = message.from_user
    await save_user(user.id, user.username, user.first_name)
    
    media = message.document or message.video
    file_name = media.file_name if media.file_name else "Unknown"
    file_size = media.file_size / 1024 / 1024
    
    # Show options
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Rename File", callback_data=f"rename_{message.id}")],
        [InlineKeyboardButton("🎬 Convert to MP4", callback_data=f"convert_{message.id}")] if message.video else [],
        [InlineKeyboardButton("🖼️ Change Thumbnail", callback_data=f"thumb_{message.id}")],
        [InlineKeyboardButton("📦 Compress", callback_data=f"compress_{message.id}")] if message.video else [],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ])
    
    await message.reply_text(
        f"📁 **File received:**\n\n"
        f"📄 Name: `{file_name}`\n"
        f"💾 Size: {file_size:.1f} MB\n\n"
        f"**What do you want to do?**",
        reply_markup=keyboard,
        quote=True
    )

# =============== CALLBACK HANDLERS ===============

@app.on_callback_query()
async def handle_callback(client, callback: CallbackQuery):
    data = callback.data
    user_id = callback.from_user.id
    
    if data == "cancel":
        await callback.message.delete()
        await callback.answer("Cancelled!")
        return
    
    elif data.startswith("rename_"):
        msg_id = int(data.split("_")[1])
        original_msg = await client.get_messages(callback.message.chat.id, msg_id)
        
        if original_msg and (original_msg.document or original_msg.video):
            # Store pending rename
            rename_db.update_one(
                {"user_id": user_id},
                {"$set": {"message_id": msg_id, "chat_id": callback.message.chat.id}},
                upsert=True
            )
            
            await callback.message.delete()
            await callback.message.reply_text(
                "✏️ **Send me the new filename**\n\n"
                "Examples:\n"
                "`my_video.mp4`\n"
                "`document.pdf`\n"
                "`image.jpg`\n\n"
                "Send `/cancel` to cancel",
                quote=True
            )
        await callback.answer()
    
    elif data.startswith("convert_"):
        await callback.answer("Converting...")
        msg_id = int(data.split("_")[1])
        original_msg = await client.get_messages(callback.message.chat.id, msg_id)
        
        if original_msg and original_msg.video:
            status = await callback.message.reply_text("🎬 **Converting video...**")
            
            try:
                input_path = await client.download_media(original_msg.video)
                output_path = f"converted_{datetime.now().timestamp()}.mp4"
                
                success = await convert_video(input_path, output_path)
                
                if success:
                    thumb = await get_thumbnail(user_id)
                    await client.send_video(
                        callback.message.chat.id,
                        output_path,
                        thumb=thumb,
                        caption="✅ **Converted to MP4!**"
                    )
                    await status.delete()
                else:
                    await status.edit_text("❌ Conversion failed!")
                
                # Cleanup
                if os.path.exists(input_path):
                    os.remove(input_path)
                if os.path.exists(output_path):
                    os.remove(output_path)
                    
            except Exception as e:
                await status.edit_text(f"❌ Error: {str(e)}")
        
        await callback.message.delete()
    
    elif data.startswith("compress_"):
        quality = data.split("_")[1]
        await callback.answer(f"Compressing with {quality} quality...")
        
        # Get original message
        # Similar to convert logic
        pass
    
    elif data.startswith("thumb_"):
        await callback.answer("Use /setthumb command to set thumbnail!", show_alert=True)

# =============== HANDLE RENAME INPUT ===============

@app.on_message(filters.text & filters.private)
async def handle_rename_input(client, message):
    user_id = message.from_user.id
    
    if message.text == "/cancel":
        rename_db.delete_one({"user_id": user_id})
        await message.reply_text("❌ **Cancelled!**")
        return
    
    # Check if user has pending rename
    pending = rename_db.find_one({"user_id": user_id})
    if pending:
        chat_id = pending["chat_id"]
        msg_id = pending["message_id"]
        
        # Get original message
        original_msg = await client.get_messages(chat_id, msg_id)
        if original_msg and (original_msg.document or original_msg.video):
            media = original_msg.document or original_msg.video
            new_name = message.text.strip()
            
            status = await message.reply_text("📥 **Downloading file...**")
            
            try:
                # Download file
                file_path = await client.download_media(media)
                
                await status.edit_text("🔄 **Renaming...**")
                
                # Get thumbnail if exists
                thumb = await get_thumbnail(user_id)
                
                # Send renamed file
                if new_name.endswith(('.mp4', '.mkv', '.avi', '.mov')):
                    await client.send_video(
                        chat_id,
                        file_path,
                        thumb=thumb,
                        caption=f"✅ **Renamed to:** `{new_name}`",
                        file_name=new_name
                    )
                else:
                    await client.send_document(
                        chat_id,
                        file_path,
                        thumb=thumb,
                        caption=f"✅ **Renamed to:** `{new_name}`",
                        file_name=new_name
                    )
                
                await status.edit_text("✅ **File renamed successfully!**")
                
                # Cleanup
                if os.path.exists(file_path):
                    os.remove(file_path)
                    
            except Exception as e:
                await status.edit_text(f"❌ Error: {str(e)}")
        
        # Clear pending
        rename_db.delete_one({"user_id": user_id})
        await message.delete()

# =============== ADMIN COMMANDS ===============

@app.on_message(filters.command("stats") & filters.user(ADMIN))
async def stats_command(client, message):
    total_users = users_db.count_documents({})
    total_thumbnails = thumb_db.count_documents({})
    
    await message.reply_text(
        f"📊 **Bot Statistics**\n\n"
        f"👥 Total Users: {total_users}\n"
        f"🖼️ Thumbnails Saved: {total_thumbnails}"
    )

@app.on_message(filters.command("broadcast") & filters.user(ADMIN))
async def broadcast_command(client, message):
    if not message.reply_to_message:
        await message.reply_text("Reply to a message with /broadcast")
        return
    
    users = users_db.find({})
    count = 0
    
    for user in users:
        try:
            await message.reply_to_message.copy(user["user_id"])
            count += 1
        except:
            pass
    
    await message.reply_text(f"✅ Broadcast sent to {count} users")

# =============== RUN BOT ===============

print("🤖 Bot is starting...")
print("✅ Bot is running!")

app.run()
