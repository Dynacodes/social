from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp
import os
import tempfile
import shutil
import re
import uuid

app = FastAPI(title="Social Media Downloader", version="1.0")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def sanitize_filename(filename):
    """Remove emojis and non-ASCII characters from filename."""
    if not filename:
        return "media"
    filename = filename.encode('ascii', 'ignore').decode('ascii')
    filename = re.sub(r'[^\w\-_. ]', '', filename)
    filename = ' '.join(filename.split())
    return filename.strip() or "media"

def is_image_url(url):
    """Check if the URL is likely an image post (Instagram, Facebook, etc.)"""
    image_domains = [
        'instagram.com/p/',
        'instagram.com/reel/',
        'fb.watch',
        'facebook.com/photo',
        'facebook.com/watch',
        'twitter.com',
        'x.com',
        'pinterest.com',
        'flickr.com',
        'imgur.com',
        'tumblr.com'
    ]
    url_lower = url.lower()
    for domain in image_domains:
        if domain in url_lower:
            return True
    return False

def is_video_url(url):
    """Check if the URL is likely a video"""
    video_domains = [
        'youtube.com',
        'youtu.be',
        'tiktok.com',
        'vimeo.com',
        'dailymotion.com',
        'twitch.tv',
        'reddit.com'
    ]
    url_lower = url.lower()
    for domain in video_domains:
        if domain in url_lower:
            return True
    return False

@app.get("/")
async def root():
    return {
        "message": "Social Media Downloader API is running",
        "endpoints": {
            "/ping": "Health check",
            "/download?url=VIDEO_URL": "Download video (YouTube, TikTok, etc.)",
            "/download/image?url=IMAGE_URL": "Download image (Instagram, Facebook, etc.)"
        }
    }

@app.get("/ping")
async def ping():
    return {"status": "alive"}

@app.get("/download")
async def download_video(url: str = Query(..., description="Full URL of the video")):
    """Download video from any supported platform."""
    temp_dir = tempfile.mkdtemp()
    try:
        # Get video info first
        with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            
            title = info.get('title', 'video')
            ext = info.get('ext', 'mp4')
            
            safe_title = sanitize_filename(title)
            unique_id = str(uuid.uuid4())[:8]
            filename = f"{safe_title}_{unique_id}.{ext}"
            
            if len(filename) > 200:
                filename = f"{safe_title[:100]}_{unique_id}.{ext}"

        ydl_opts = {
            'outtmpl': os.path.join(temp_dir, filename),
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'format': 'bestvideo+bestaudio/best',
            'ignoreerrors': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.extract_info(url, download=True)

        downloaded_file = None
        for file in os.listdir(temp_dir):
            if file.endswith(('.mp4', '.mkv', '.webm', '.mp3', '.m4a', '.mp4')):
                downloaded_file = os.path.join(temp_dir, file)
                break

        if not downloaded_file or not os.path.exists(downloaded_file):
            raise Exception("No media file was downloaded")

        return FileResponse(
            path=downloaded_file,
            media_type="video/mp4",
            filename=os.path.basename(downloaded_file),
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{os.path.basename(downloaded_file)}"
            }
        )

    except Exception as e:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
        error_msg = str(e)
        if "UnicodeEncodeError" in error_msg or "latin-1" in error_msg:
            error_msg = "Video contains special characters. Please try again."
        raise HTTPException(status_code=400, detail=error_msg)

@app.get("/download/image")
async def download_image(url: str = Query(..., description="Full URL of the image/video post")):
    """
    Download image from Instagram, Facebook, Twitter, Pinterest, etc.
    Also works for video posts from these platforms.
    """
    temp_dir = tempfile.mkdtemp()
    try:
        # First, get the info to determine what we're downloading
        with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            
            title = info.get('title', 'media')
            ext = info.get('ext', 'jpg')
            
            # If it's a video from Instagram/Facebook, use mp4
            if ext in ['mp4', 'webm', 'mkv']:
                ext = 'mp4'
                media_type = "video/mp4"
            else:
                # Default to image
                ext = 'jpg'
                media_type = "image/jpeg"
            
            safe_title = sanitize_filename(title)
            unique_id = str(uuid.uuid4())[:8]
            filename = f"{safe_title}_{unique_id}.{ext}"
            
            if len(filename) > 200:
                filename = f"{safe_title[:100]}_{unique_id}.{ext}"

        # Download with specific options
        ydl_opts = {
            'outtmpl': os.path.join(temp_dir, filename),
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'format': 'best',  # This gets best quality image or video
            'ignoreerrors': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.extract_info(url, download=True)

        # Find the downloaded file
        downloaded_file = None
        for file in os.listdir(temp_dir):
            if file.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.mp4', '.webm', '.mkv')):
                downloaded_file = os.path.join(temp_dir, file)
                break

        if not downloaded_file or not os.path.exists(downloaded_file):
            raise Exception("No media file was downloaded")

        # Determine content type
        file_ext = os.path.splitext(downloaded_file)[1].lower()
        content_type_map = {
            '.jpg': "image/jpeg",
            '.jpeg': "image/jpeg",
            '.png': "image/png",
            '.gif': "image/gif",
            '.webp': "image/webp",
            '.bmp': "image/bmp",
            '.mp4': "video/mp4",
            '.webm': "video/webm",
            '.mkv': "video/x-matroska"
        }
        media_type = content_type_map.get(file_ext, "application/octet-stream")

        return FileResponse(
            path=downloaded_file,
            media_type=media_type,
            filename=os.path.basename(downloaded_file),
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{os.path.basename(downloaded_file)}"
            }
        )

    except Exception as e:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
        error_msg = str(e)
        raise HTTPException(status_code=400, detail=error_msg)