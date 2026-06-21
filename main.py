from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import FileResponse
import yt_dlp
import os
import tempfile
import shutil

app = FastAPI(title="Social Media Downloader", version="1.0")

@app.get("/")
async def root():
    return {"message": "Send a GET request to /download?url=VIDEO_URL"}

@app.get("/ping")
async def ping():
    """Simple health check for uptime monitoring."""
    return {"status": "alive"}

@app.get("/download")
async def download_video(url: str = Query(..., description="Full URL of the video")):
    """
    Download a video/audio from any supported platform (TikTok, Instagram, Facebook, YouTube, etc.)
    Returns the file as an attachment.
    """
    # Create a temporary directory for this download
    temp_dir = tempfile.mkdtemp()
    try:
        # yt-dlp options
        ydl_opts = {
            'outtmpl': os.path.join(temp_dir, '%(title).50s_%(id)s.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'format': 'bestvideo+bestaudio/best',  # best quality
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

        # Find the downloaded file
        downloaded_file = None
        for file in os.listdir(temp_dir):
            if file.endswith(('.mp4', '.mkv', '.webm', '.mp3', '.m4a')):
                downloaded_file = os.path.join(temp_dir, file)
                break

        if not downloaded_file:
            raise Exception("No media file was downloaded")

        # Return the file directly to the user
        return FileResponse(
            path=downloaded_file,
            media_type="video/mp4",
            filename=os.path.basename(downloaded_file),
            headers={"Content-Disposition": f"attachment; filename={os.path.basename(downloaded_file)}"}
        )

    except Exception as e:
        # Clean up the temporary folder on error
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=str(e))

    finally:
        # Note: FastAPI's FileResponse will keep the file open until it's sent,
        # then it will automatically delete it (because it's in a temporary directory).
        # We can let FastAPI handle the cleanup.
        pass