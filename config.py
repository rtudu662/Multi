import os

class Config:
    # Telegram API credentials (get from my.telegram.org)
    API_ID = int(os.environ.get("API_ID", 0))
    API_HASH = os.environ.get("API_HASH", "")
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
    
    # Admin user IDs (comma separated)
    ADMIN = [int(x) for x in os.environ.get("ADMIN", "").split()] if os.environ.get("ADMIN") else []
    
    # MongoDB (for storing thumbnails and user data)
    MONGO_URI = os.environ.get("MONGO_URI", "")
    DB_NAME = os.environ.get("DB_NAME", "media_bot")
    
    # Other settings
    MAX_FILE_SIZE = int(os.environ.get("MAX_FILE_SIZE", 2 * 1024 * 1024 * 1024))  # 2GB
    FORCE_SUB_CHANNEL = os.environ.get("FORCE_SUB_CHANNEL", "")  # @channel username
    
    # Video conversion settings
    ALLOWED_VIDEO_FORMATS = ["mp4", "mkv", "avi", "mov", "flv", "webm"]
    OUTPUT_VIDEO_FORMAT = "mp4"
    VIDEO_BITRATE = "1M"
    VIDEO_FPS = 30
