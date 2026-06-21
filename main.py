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

# Enable CORS (so your dashboard can call it)
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
        return "video"
    # Remove emojis and other non-ASCII characters
    filename = filename.encode('ascii', 'ignore').decode('ascii')
    # Replace any remaining problematic characters
    filename = re.sub(r'[^\w\-_. ]', '', filename)
    # Remove extra spaces
    filename = ' '.join(filename.split())
    return filename.strip() or "video"

@app.get("/")
async def root():
    return {
        "message": "Social Media Downloader API is running",
        "endpoints": {
            "/ping": "Health check",
            "/download?url=VIDEO_URL": "Download video from any platform"
        }
    }

@app.get("/ping")
async def ping():
    return {"status": "alive"}

@app.get("/download")
async def download_video(url: str = Query(..., description="Full URL of the video")):
    """
    Download video from any supported platform.
    Returns the video file as an attachment.
    """
    temp_dir = tempfile.mkdtemp()
    try:
        # Get video info first
        with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # Get title and extension
            title = info.get('title', 'video')
            ext = info.get('ext', 'mp4')
            
            # Sanitize title
            safe_title = sanitize_filename(title)
            
            # Use unique ID to avoid conflicts
            unique_id = str(uuid.uuid4())[:8]
            filename = f"{safe_title}_{unique_id}.{ext}"
            
            # If filename is too long, truncate
            if len(filename) > 200:
                filename = f"{safe_title[:100]}_{unique_id}.{ext}"

        # Download with sanitized filename
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

        # Find the downloaded file
        downloaded_file = None
        for file in os.listdir(temp_dir):
            if file.endswith(('.mp4', '.mkv', '.webm', '.mp3', '.m4a')):
                downloaded_file = os.path.join(temp_dir, file)
                break

        if not downloaded_file or not os.path.exists(downloaded_file):
            raise Exception("No media file was downloaded")

        # Return the file
        return FileResponse(
            path=downloaded_file,
            media_type="video/mp4",
            filename=os.path.basename(downloaded_file),
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{os.path.basename(downloaded_file)}"
            }
        )

    except Exception as e:
        # Clean up temp directory
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
        
        # Return a clear error message
        error_msg = str(e)
        if "UnicodeEncodeError" in error_msg or "latin-1" in error_msg:
            error_msg = "Video contains special characters. Please try again."
        
        raise HTTPException(status_code=400, detail=error_msg)