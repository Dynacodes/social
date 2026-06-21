from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp
import os
import tempfile
import shutil
import re
import uuid

app = FastAPI(title="Video Downloader API", version="1.0")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Default User-Agent (mimics a real browser)
DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# Path to cookies file
COOKIES_FILE = "cookies.txt"

def sanitize_filename(filename):
    """Remove emojis and non-ASCII characters from filename."""
    if not filename:
        return "video"
    filename = filename.encode('ascii', 'ignore').decode('ascii')
    filename = re.sub(r'[^\w\-_. ]', '', filename)
    filename = ' '.join(filename.split())
    return filename.strip() or "video"

@app.get("/")
async def root():
    # Check if cookies file exists
    cookies_status = "✅ Present" if os.path.exists(COOKIES_FILE) else "❌ Missing"
    return {
        "message": "Video Downloader API is running",
        "cookies": cookies_status,
        "endpoints": {
            "/ping": "Health check",
            "/download?url=VIDEO_URL": "Download video (YouTube, TikTok, Vimeo, etc.)"
        }
    }

@app.get("/ping")
async def ping():
    return {"status": "alive"}

@app.get("/download")
async def download_video(url: str = Query(..., description="Full URL of the video")):
    """
    Download video from YouTube, TikTok, Vimeo, Dailymotion, etc.
    Returns the video file as an attachment.
    """
    temp_dir = tempfile.mkdtemp()
    try:
        # Check if cookies file exists
        cookies_file_path = COOKIES_FILE
        if not os.path.exists(cookies_file_path):
            cookies_file_path = None

        # Get video info first
        with yt_dlp.YoutubeDL({
            'quiet': True, 
            'no_warnings': True,
            'user_agent': DEFAULT_USER_AGENT,
            'cookiefile': cookies_file_path if cookies_file_path else None,
        }) as ydl:
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
            'user_agent': DEFAULT_USER_AGENT,
            # Add headers to mimic a real browser
            'headers': {
                'User-Agent': DEFAULT_USER_AGENT,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            },
            # Use cookies file if it exists
            'cookiefile': cookies_file_path if cookies_file_path else None,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.extract_info(url, download=True)

        # Find the downloaded file
        downloaded_file = None
        for file in os.listdir(temp_dir):
            if file.endswith(('.mp4', '.mkv', '.webm', '.mp3', '.m4a')):
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
        
        # Provide helpful error messages
        if "Sign in to confirm" in error_msg or "bot" in error_msg.lower():
            error_msg = "YouTube is blocking automated access. The cookies file may be expired. Please refresh your cookies."
        elif "UnicodeEncodeError" in error_msg or "latin-1" in error_msg:
            error_msg = "Video contains special characters. Please try again."
        elif "Private video" in error_msg:
            error_msg = "This video is private and cannot be downloaded."
        elif "Video unavailable" in error_msg:
            error_msg = "This video is unavailable or has been removed."
            
        raise HTTPException(status_code=400, detail=error_msg)