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

def get_ydl_opts(temp_dir, filename, cookies_file_path, format_spec='best'):
    """Generate yt-dlp options with common settings"""
    return {
        'outtmpl': os.path.join(temp_dir, filename),
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'format': format_spec,
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
        'cookiefile': cookies_file_path if cookies_file_path else None,
        'allow_unplayable_formats': True,
        'extract_flat': False,
        'force_generic_extractor': False,
        'quiet': True,
    }

@app.get("/download")
async def download_video(url: str = Query(..., description="Full URL of the video")):
    """
    Download video from YouTube, TikTok, Vimeo, Dailymotion, etc.
    Uses aggressive format fallback strategy.
    """
    temp_dir = tempfile.mkdtemp()
    try:
        cookies_file_path = COOKIES_FILE if os.path.exists(COOKIES_FILE) else None

        # Step 1: Get video info to see what formats are available
        logger.info(f"Fetching info for: {url}")
        info = None
        try:
            with yt_dlp.YoutubeDL({
                'quiet': True,
                'no_warnings': True,
                'user_agent': DEFAULT_USER_AGENT,
                'cookiefile': cookies_file_path,
            }) as ydl:
                info = ydl.extract_info(url, download=False)
                logger.info(f"Video title: {info.get('title', 'Unknown')}")
                logger.info(f"Available formats: {len(info.get('formats', []))}")
        except Exception as e:
            logger.error(f"Failed to get info: {e}")
            raise Exception(f"Could not fetch video info: {str(e)[:200]}")

        if not info:
            raise Exception("Could not fetch video information")

        title = info.get('title', 'video')
        safe_title = sanitize_filename(title)
        unique_id = str(uuid.uuid4())[:8]
        base_filename = f"{safe_title}_{unique_id}"
        ext = 'mp4'  # Default extension

        # Step 2: Try multiple format strategies in order
        format_strategies = [
            # Strategy 1: Best video + best audio (default)
            {'format': 'bestvideo+bestaudio/best', 'desc': 'Best video + audio'},
            # Strategy 2: Best MP4
            {'format': 'best[ext=mp4]', 'desc': 'Best MP4'},
            # Strategy 3: Best video + best audio (any container)
            {'format': 'bestvideo+bestaudio', 'desc': 'Best video + audio (any)'},
            # Strategy 4: Best format
            {'format': 'best', 'desc': 'Best format'},
            # Strategy 5: WebM format
            {'format': 'bestvideo[ext=webm]+bestaudio[ext=webm]/best[ext=webm]', 'desc': 'WebM'},
            # Strategy 6: 3GP format (smallest)
            {'format': 'best[ext=3gp]', 'desc': '3GP (small)'},
            # Strategy 7: Worst quality (guaranteed to work)
            {'format': 'worst', 'desc': 'Worst quality'},
            # Strategy 8: Audio only (last resort)
            {'format': 'bestaudio/best', 'desc': 'Audio only'},
        ]

        downloaded_file = None
        last_error = None

        for strategy in format_strategies:
            try:
                # Clear temp directory for each attempt
                for f in os.listdir(temp_dir):
                    try:
                        os.remove(os.path.join(temp_dir, f))
                    except:
                        pass

                format_spec = strategy['format']
                desc = strategy['desc']
                logger.info(f"Trying format: {desc} ({format_spec})")

                # Generate filename with extension hint
                if 'mp4' in format_spec or 'mp4' in desc.lower():
                    filename = f"{base_filename}.mp4"
                elif 'webm' in format_spec or 'webm' in desc.lower():
                    filename = f"{base_filename}.webm"
                elif '3gp' in format_spec or '3gp' in desc.lower():
                    filename = f"{base_filename}.3gp"
                elif 'audio' in desc.lower() or 'audio' in format_spec:
                    filename = f"{base_filename}.mp3"
                else:
                    filename = f"{base_filename}.mp4"

                ydl_opts = get_ydl_opts(temp_dir, filename, cookies_file_path, format_spec)
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.extract_info(url, download=True)

                # Find the downloaded file
                for f in os.listdir(temp_dir):
                    if f.endswith(('.mp4', '.mkv', '.webm', '.mp3', '.m4a', '.flv', '.avi', '.3gp')):
                        downloaded_file = os.path.join(temp_dir, f)
                        break

                if downloaded_file and os.path.exists(downloaded_file):
                    logger.info(f"✅ Success with format: {desc}")
                    break
                else:
                    logger.warning(f"⚠️ No file downloaded for format: {desc}")

            except Exception as e:
                last_error = str(e)
                logger.warning(f"❌ Format '{desc}' failed: {str(e)[:100]}")
                continue

        # Step 3: If all strategies failed, try a direct approach
        if not downloaded_file:
            logger.info("All strategies failed, trying direct approach...")
            try:
                ydl_opts = {
                    'outtmpl': os.path.join(temp_dir, f"{base_filename}.%(ext)s"),
                    'quiet': True,
                    'no_warnings': True,
                    'format': 'best',
                    'ignoreerrors': True,
                    'user_agent': DEFAULT_USER_AGENT,
                    'cookiefile': cookies_file_path,
                    'allow_unplayable_formats': True,
                    'force_generic_extractor': False,
                    'extract_flat': False,
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.extract_info(url, download=True)
                
                for f in os.listdir(temp_dir):
                    if f.endswith(('.mp4', '.mkv', '.webm', '.mp3', '.m4a', '.flv', '.avi', '.3gp')):
                        downloaded_file = os.path.join(temp_dir, f)
                        break
            except Exception as e:
                last_error = str(e)
                logger.error(f"Direct approach failed: {e}")

        # Step 4: Check if video is DRM protected
        if not downloaded_file:
            error_msg = "Could not find a compatible video format. "
            if last_error and ('drm' in last_error.lower() or 'DRM' in last_error):
                error_msg += "This video appears to be DRM protected and cannot be downloaded."
            else:
                error_msg += "The video may be DRM protected, age-restricted, or have restricted formats."
                error_msg += f"\nLast error: {last_error[:200] if last_error else 'Unknown'}"
            raise Exception(error_msg)

        # Step 5: Determine content type and return file
        file_ext = os.path.splitext(downloaded_file)[1].lower()
        content_type_map = {
            '.mp4': "video/mp4",
            '.mkv': "video/x-matroska",
            '.webm': "video/webm",
            '.mp3': "audio/mpeg",
            '.m4a': "audio/mp4",
            '.flv': "video/x-flv",
            '.avi': "video/x-msvideo",
            '.3gp': "video/3gpp"
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

        # Provide helpful error messages
        if "Sign in to confirm" in error_msg or "bot" in error_msg.lower():
            error_msg = "YouTube is blocking automated access. The cookies file may be expired. Please refresh your cookies."
        elif "UnicodeEncodeError" in error_msg or "latin-1" in error_msg:
            error_msg = "Video contains special characters. Please try again."
        elif "Private video" in error_msg:
            error_msg = "This video is private and cannot be downloaded."
        elif "Video unavailable" in error_msg:
            error_msg = "This video is unavailable or has been removed."
        elif "drm" in error_msg.lower() or "DRM" in error_msg:
            error_msg = "This video is DRM protected and cannot be downloaded."
        elif "format" in error_msg.lower():
            error_msg = "Could not find a compatible video format. The video may be DRM protected or age-restricted."

        raise HTTPException(status_code=400, detail=error_msg)