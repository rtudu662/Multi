import os
import asyncio
import subprocess
import shutil
import re
from datetime import datetime
from typing import Tuple, Optional

# Video quality presets
VIDEO_PRESETS = {
    "high": {"crf": 18, "preset": "slow", "bitrate": "2M"},
    "medium": {"crf": 23, "preset": "fast", "bitrate": "1M"},
    "low": {"crf": 28, "preset": "veryfast", "bitrate": "512k"}
}

# Audio bitrate presets
AUDIO_BITRATES = {
    "high": "192k",
    "medium": "128k", 
    "low": "64k"
}

async def convert_video(
    input_path: str, 
    output_path: str, 
    quality: str = "medium",
    output_format: str = "mp4"
) -> bool:
    """
    Convert video to specified format with quality options
    
    Args:
        input_path: Source video path
        output_path: Output video path
        quality: "high", "medium", or "low"
        output_format: Output format (mp4, mkv, etc.)
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        preset = VIDEO_PRESETS.get(quality, VIDEO_PRESETS["medium"])
        audio_bitrate = AUDIO_BITRATES.get(quality, AUDIO_BITRATES["medium"])
        
        cmd = [
            "ffmpeg", "-i", input_path,
            "-c:v", "libx264",
            "-preset", preset["preset"],
            "-crf", str(preset["crf"]),
            "-c:a", "aac",
            "-b:a", audio_bitrate,
            "-movflags", "+faststart",
            "-y",  # Overwrite output file
            output_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        return process.returncode == 0
        
    except Exception as e:
        print(f"Video conversion error: {e}")
        return False

async def compress_video(
    input_path: str, 
    output_path: str, 
    compression_level: str = "medium",
    target_size_mb: Optional[int] = None
) -> Tuple[bool, str]:
    """
    Compress video with various options
    
    Args:
        input_path: Source video path
        output_path: Output video path
        compression_level: "high", "medium", "low"
        target_size_mb: Target size in MB (optional)
    
    Returns:
        Tuple[bool, str]: (success, message)
    """
    try:
        original_size = os.path.getsize(input_path) / (1024 * 1024)
        
        if target_size_mb and target_size_mb < original_size:
            # Calculate required bitrate for target size
            duration = await get_video_duration(input_path)
            if duration > 0:
                target_bitrate = (target_size_mb * 8 * 1024) / duration
                cmd = [
                    "ffmpeg", "-i", input_path,
                    "-c:v", "libx264",
                    "-b:v", f"{target_bitrate:.0f}k",
                    "-c:a", "aac",
                    "-b:a", "96k",
                    "-y", output_path
                ]
        else:
            preset = VIDEO_PRESETS.get(compression_level, VIDEO_PRESETS["medium"])
            cmd = [
                "ffmpeg", "-i", input_path,
                "-c:v", "libx264",
                "-preset", preset["preset"],
                "-crf", str(preset["crf"]),
                "-c:a", "aac",
                "-b:a", "96k",
                "-y", output_path
            ]
        
        process = await asyncio.create_subprocess_exec(*cmd)
        await process.communicate()
        
        if process.returncode == 0:
            new_size = os.path.getsize(output_path) / (1024 * 1024)
            saved = original_size - new_size
            return True, f"Compressed! {original_size:.1f}MB → {new_size:.1f}MB (Saved {saved:.1f}MB)"
        
        return False, "Compression failed"
        
    except Exception as e:
        return False, f"Error: {str(e)}"

async def extract_thumbnail(
    video_path: str, 
    output_path: str, 
    time_offset: float = 5.0
) -> bool:
    """
    Extract thumbnail from video at specific time
    
    Args:
        video_path: Source video path
        output_path: Output thumbnail path
        time_offset: Time in seconds to extract thumbnail from
    
    Returns:
        bool: True if successful
    """
    try:
        cmd = [
            "ffmpeg", "-i", video_path,
            "-ss", str(time_offset),
            "-vframes", "1",
            "-vf", "scale=320:-1",
            "-y", output_path
        ]
        
        process = await asyncio.create_subprocess_exec(*cmd)
        await process.communicate()
        
        return process.returncode == 0
        
    except Exception as e:
        print(f"Thumbnail extraction error: {e}")
        return False

async def get_video_duration(video_path: str) -> float:
    """Get video duration in seconds"""
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, _ = await process.communicate()
        
        if stdout:
            return float(stdout.decode().strip())
        
        return 0.0
        
    except Exception as e:
        print(f"Duration error: {e}")
        return 0.0

async def get_file_info(file_path: str) -> dict:
    """Get detailed file information"""
    info = {
        "size_mb": os.path.getsize(file_path) / (1024 * 1024),
        "exists": os.path.exists(file_path),
        "extension": os.path.splitext(file_path)[1].lower()
    }
    
    # Get video info if it's a video file
    if info["extension"] in ['.mp4', '.mkv', '.avi', '.mov', '.flv', '.webm']:
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height,duration,codec_name",
                "-of", "json",
                file_path
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, _ = await process.communicate()
            
            if stdout:
                import json
                data = json.loads(stdout)
                if data.get("streams"):
                    stream = data["streams"][0]
                    info["width"] = stream.get("width", 0)
                    info["height"] = stream.get("height", 0)
                    info["video_codec"] = stream.get("codec_name", "unknown")
                    info["duration"] = float(stream.get("duration", 0))
                    
        except Exception as e:
            print(f"Video info error: {e}")
    
    return info

async def sanitize_filename(filename: str) -> str:
    """
    Remove invalid characters from filename
    """
    # Remove invalid characters
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    # Remove multiple spaces
    filename = re.sub(r'\s+', ' ', filename)
    # Trim
    filename = filename.strip()
    
    # Limit length
    if len(filename) > 200:
        name, ext = os.path.splitext(filename)
        filename = name[:196] + ext
    
    return filename

async def format_size(bytes_size: int) -> str:
    """Format bytes to human readable size"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} PB"

async def format_duration(seconds: float) -> str:
    """Format seconds to HH:MM:SS"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes:02d}:{secs:02d}"

async def cleanup_files(*file_paths):
    """Delete multiple files safely"""
    for file_path in file_paths:
        try:
            if file_path and os.path.exists(file_path):
                if os.path.isfile(file_path):
                    os.remove(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
        except Exception as e:
            print(f"Cleanup error for {file_path}: {e}")

async def create_temp_dir() -> str:
    """Create temporary directory"""
    temp_dir = f"temp_{datetime.now().timestamp()}"
    os.makedirs(temp_dir, exist_ok=True)
    return temp_dir

def is_valid_extension(filename: str, allowed_extensions: list) -> bool:
    """Check if file has allowed extension"""
    ext = os.path.splitext(filename)[1].lower().lstrip('.')
    return ext in allowed_extensions

# Progress callback for downloads/uploads
class ProgressTracker:
    def __init__(self, message, total_size):
        self.message = message
        self.total_size = total_size
        self.start_time = datetime.now()
    
    async def update(self, current, total):
        percent = current * 100 / self.total_size
        elapsed = (datetime.now() - self.start_time).total_seconds()
        
        if elapsed > 0:
            speed = current / elapsed
            eta = (self.total_size - current) / speed if speed > 0 else 0
            
            progress_bar = self._create_progress_bar(percent)
            
            text = f"{progress_bar} {percent:.1f}%\n"
            text += f"⚡ Speed: {speed/1024/1024:.1f} MB/s\n"
            text += f"⏱️ ETA: {int(eta//60)}m {int(eta%60)}s"
            
            await self.message.edit_text(text)
    
    def _create_progress_bar(self, percent, length=20):
        filled = int(length * percent / 100)
        bar = '█' * filled + '░' * (length - filled)
        return bar
