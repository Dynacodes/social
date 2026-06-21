from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp
import os
import tempfile
import shutil
import re
import uuid
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
    return {
        "message": "Video Downloader API is running",
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
        logger.info(f"Downloading: {url}")

        # Step 1: Try to get video info
        info = None
        try:
            with yt_dlp.YoutubeDL({
                'quiet': True,
                'no_warnings': True,
                'user_agent': DEFAULT_USER_AGENT,
                'ignoreerrors': True,
            }) as ydl:
                info = ydl.extract_info(url, download=False)
                logger.info(f"Video title: {info.get('title', 'Unknown') if info else 'Unknown'}")
        except Exception as e:
            logger.warning(f"Info fetch failed: {e}")

        # Step 2: Get title (fallback to 'video' if no info)
        title = 'video'
        if info and isinstance(info, dict):
            title = info.get('title', 'video')
        
        safe_title = sanitize_filename(title)
        unique_id = str(uuid.uuid4())[:8]
        base_filename = f"{safe_title}_{unique_id}"

        # Step 3: Try direct download with best format
        downloaded_file = None
        last_error = None

        # Try different format strategies
        format_strategies = [
            'bestvideo+bestaudio/best',  # Best quality
            'best[ext=mp4]',              # Best MP4
            'best',                       # Best format
            'worst',                      # Worst quality (last resort)
        ]

        for fmt in format_strategies:
            try:
                logger.info(f"Trying format: {fmt}")
                
                # Clear temp directory
                for f in os.listdir(temp_dir):
                    try:
                        os.remove(os.path.join(temp_dir, f))
                    except:
                        pass

                ydl_opts = {
                    'outtmpl': os.path.join(temp_dir, f"{base_filename}.%(ext)s"),
                    'quiet': True,
                    'no_warnings': True,
                    'format': fmt,
                    'ignoreerrors': True,
                    'user_agent': DEFAULT_USER_AGENT,
                    'headers': {
                        'User-Agent': DEFAULT_USER_AGENT,
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.5',
                        'Accept-Encoding': 'gzip, deflate, br',
                        'DNT': '1',
                        'Connection': 'keep-alive',
                        'Upgrade-Insecure-Requests': '1',
                    },
                    'allow_unplayable_formats': True,
                }

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.extract_info(url, download=True)

                # Find the downloaded file
                for f in os.listdir(temp_dir):
                    if f.endswith(('.mp4', '.mkv', '.webm', '.mp3', '.m4a', '.flv', '.avi')):
                        downloaded_file = os.path.join(temp_dir, f)
                        break

                if downloaded_file and os.path.exists(downloaded_file):
                    logger.info(f"✅ Downloaded: {os.path.basename(downloaded_file)}")
                    break

            except Exception as e:
                last_error = str(e)
                logger.warning(f"Format '{fmt}' failed: {e}")
                continue

        if not downloaded_file:
            error_msg = "Could not download video. "
            if last_error:
                error_msg += f"Last error: {last_error[:150]}"
            else:
                error_msg += "No compatible format found."
            raise Exception(error_msg)

        # Step 4: Return the file
        file_ext = os.path.splitext(downloaded_file)[1].lower()
        content_type_map = {
            '.mp4': "video/mp4",
            '.mkv': "video/x-matroska",
            '.webm': "video/webm",
            '.mp3': "audio/mpeg",
            '.m4a': "audio/mp4",
            '.flv': "video/x-flv",
            '.avi': "video/x-msvideo"
        }
        media_type = content_type_map.get(file_ext, "video/mp4")

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
        
        # Clean up error messages
        if "Sign in to confirm" in error_msg or "bot" in error_msg.lower():
            error_msg = "YouTube is blocking automated access. Please try again later or use a different video."
        elif "Private video" in error_msg:
            error_msg = "This video is private and cannot be downloaded."
        elif "Video unavailable" in error_msg:
            error_msg = "This video is unavailable or has been removed."
        elif "format" in error_msg.lower():
            error_msg = "Could not find a compatible video format."
        
        raise HTTPException(status_code=400, detail=error_msg)