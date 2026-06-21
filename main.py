from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import FileResponse
import yt_dlp
import os
import tempfile
import shutil
import re

app = FastAPI(title="Social Media Downloader", version="1.0")

def sanitize_filename(filename):
    """Remove emojis and non-ASCII characters from filename."""
    # Remove emojis and other non-ASCII characters
    filename = filename.encode('ascii', 'ignore').decode('ascii')
    # Replace any remaining problematic characters
    filename = re.sub(r'[^\w\-_. ]', '', filename)
    return filename.strip()

@app.get("/")
async def root():
    return {"message": "Social Media Downloader API is running. Use /download?url=VIDEO_URL"}

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
        # First, extract info without downloading to get the title
        with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get('title', 'video')
            ext = info.get('ext', 'mp4')
            # Sanitize the title to remove emojis
            safe_title = sanitize_filename(title)
            filename = f"{safe_title}.{ext}"

        # Now download with the sanitized filename
        ydl_opts = {
            'outtmpl': os.path.join(temp_dir, filename),
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'format': 'bestvideo+bestaudio/best',
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.extract_info(url, download=True)

        downloaded_file = os.path.join(temp_dir, filename)
        if not os.path.exists(downloaded_file):
            # Fallback: find any file in temp_dir
            for file in os.listdir(temp_dir):
                if file.endswith(('.mp4', '.mkv', '.webm', '.mp3', '.m4a')):
                    downloaded_file = os.path.join(temp_dir, file)
                    break

        if not os.path.exists(downloaded_file):
            raise Exception("No media file was downloaded")

        return FileResponse(
            path=downloaded_file,
            media_type="video/mp4",
            filename=os.path.basename(downloaded_file),
            headers={"Content-Disposition": f"attachment; filename={os.path.basename(downloaded_file)}"}
        )

    except Exception as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=str(e))