from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp
import os
import tempfile
import shutil
import re
import uuid
import requests
from bs4 import BeautifulSoup

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

@app.get("/")
async def root():
    return {
        "message": "Social Media Downloader API is running",
        "endpoints": {
            "/ping": "Health check",
            "/download?url=VIDEO_URL": "Download video (YouTube, TikTok, Vimeo, etc.)",
            "/download/image?url=IMAGE_URL": "Download image (Instagram, Pinterest, X/Twitter, Facebook)"
        }
    }

@app.get("/ping")
async def ping():
    return {"status": "alive"}

# ============================================================
# VIDEO / AUDIO DOWNLOADER (Works for YouTube, TikTok, etc.)
# ============================================================
@app.get("/download")
async def download_video(url: str = Query(..., description="Full URL of the video")):
    """
    Download video from YouTube, TikTok, Vimeo, Dailymotion, etc.
    Returns the video file as an attachment.
    """
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
        if "UnicodeEncodeError" in error_msg or "latin-1" in error_msg:
            error_msg = "Video contains special characters. Please try again."
        raise HTTPException(status_code=400, detail=error_msg)

# ============================================================
# IMAGE DOWNLOADER (Instagram, Pinterest, X/Twitter, Facebook)
# ============================================================
@app.get("/download/image")
async def download_image(url: str = Query(..., description="Full URL of the image")):
    """
    Download images from Instagram, Pinterest, X (Twitter), Facebook, etc.
    Uses a hybrid approach: yt-dlp first, then meta tags, then scraping.
    """
    temp_dir = tempfile.mkdtemp()
    try:
        image_url = None
        image_ext = 'jpg'
        image_title = 'image'
        downloaded_file = None

        # ============================================================
        # METHOD 1: Try yt-dlp first (best quality)
        # ============================================================
        try:
            ydl_opts = {
                'outtmpl': os.path.join(temp_dir, '%(title)s_%(id)s.%(ext)s'),
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'format': 'best',
                'ignoreerrors': True,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                
                # Find the downloaded file
                for file in os.listdir(temp_dir):
                    if file.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp')):
                        downloaded_file = os.path.join(temp_dir, file)
                        break

            if downloaded_file and os.path.exists(downloaded_file):
                file_ext = os.path.splitext(downloaded_file)[1].lower()
                content_type_map = {
                    '.jpg': "image/jpeg",
                    '.jpeg': "image/jpeg",
                    '.png': "image/png",
                    '.gif': "image/gif",
                    '.webp': "image/webp",
                    '.bmp': "image/bmp"
                }
                media_type = content_type_map.get(file_ext, "image/jpeg")
                
                return FileResponse(
                    path=downloaded_file,
                    media_type=media_type,
                    filename=os.path.basename(downloaded_file),
                    headers={
                        "Content-Disposition": f"attachment; filename*=UTF-8''{os.path.basename(downloaded_file)}"
                    }
                )
        except Exception as e:
            # yt-dlp failed, continue to next method
            print(f"yt-dlp method failed: {e}")

        # ============================================================
        # METHOD 2: Try Open Graph meta tags
        # ============================================================
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            
            response = requests.get(url, headers=headers, timeout=30)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for og:image meta tag
            og_image = soup.find('meta', property='og:image')
            if og_image and og_image.get('content'):
                image_url = og_image['content']
                image_title = 'image'
                
                # Download the image
                img_response = requests.get(image_url, headers=headers, timeout=30)
                if img_response.status_code == 200:
                    content_type = img_response.headers.get('content-type', 'image/jpeg')
                    ext_map = {
                        'image/jpeg': 'jpg',
                        'image/png': 'png',
                        'image/gif': 'gif',
                        'image/webp': 'webp',
                        'image/bmp': 'bmp'
                    }
                    image_ext = ext_map.get(content_type, 'jpg')
                    filename = f"image_{uuid.uuid4().hex[:8]}.{image_ext}"
                    filepath = os.path.join(temp_dir, filename)
                    
                    with open(filepath, 'wb') as f:
                        f.write(img_response.content)
                    
                    return FileResponse(
                        path=filepath,
                        media_type=content_type,
                        filename=filename,
                        headers={
                            "Content-Disposition": f"attachment; filename*=UTF-8''{filename}"
                        }
                    )
        except Exception as e:
            print(f"Meta tag method failed: {e}")

        # ============================================================
        # METHOD 3: Platform-specific image scraping (last resort)
        # ============================================================
        try:
            if not image_url:
                # X/Twitter
                tweet_photo = soup.find('img', class_=re.compile(r'photo|media|tweet|css-'))
                if tweet_photo and tweet_photo.get('src'):
                    image_url = tweet_photo['src']
                    if image_url.startswith('//'):
                        image_url = 'https:' + image_url
                
                # Instagram (fallback)
                if not image_url:
                    insta_img = soup.find('img', class_=re.compile(r'FFVAD|_aagv|_aagu|_aagw'))
                    if insta_img and insta_img.get('src'):
                        image_url = insta_img['src']
                
                # Pinterest
                if not image_url:
                    pin_img = soup.find('img', class_=re.compile(r'pin|Board|hCL|kVc'))
                    if pin_img and pin_img.get('src'):
                        image_url = pin_img['src']
                
                # Facebook
                if not image_url:
                    fb_img = soup.find('img', class_=re.compile(r'image|photo|story|scaled'))
                    if fb_img and fb_img.get('src'):
                        image_url = fb_img['src']
                
                if image_url:
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                    }
                    img_response = requests.get(image_url, headers=headers, timeout=30)
                    if img_response.status_code == 200:
                        content_type = img_response.headers.get('content-type', 'image/jpeg')
                        ext_map = {
                            'image/jpeg': 'jpg',
                            'image/png': 'png',
                            'image/gif': 'gif',
                            'image/webp': 'webp',
                            'image/bmp': 'bmp'
                        }
                        image_ext = ext_map.get(content_type, 'jpg')
                        filename = f"image_{uuid.uuid4().hex[:8]}.{image_ext}"
                        filepath = os.path.join(temp_dir, filename)
                        
                        with open(filepath, 'wb') as f:
                            f.write(img_response.content)
                        
                        return FileResponse(
                            path=filepath,
                            media_type=content_type,
                            filename=filename,
                            headers={
                                "Content-Disposition": f"attachment; filename*=UTF-8''{filename}"
                            }
                        )
        except Exception as e:
            print(f"Scraping method failed: {e}")

        # If all methods fail
        raise Exception("Could not find image. The post might be private or unsupported.")

    except Exception as e:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=str(e))