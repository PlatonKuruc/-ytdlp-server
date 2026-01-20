from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import yt_dlp
import cloudinary
import cloudinary.uploader
import os
import uuid
import tempfile

app = FastAPI()

# Cloudinary config from environment variables
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

class DownloadRequest(BaseModel):
    video_url: str
    quality: str = "720p"  # 360p, 480p, 720p, 1080p

class DownloadResponse(BaseModel):
    success: bool
    video_url: str = None
    video_id: str = None
    title: str = None
    duration: int = None
    error: str = None

@app.get("/")
def health_check():
    return {"status": "ok", "service": "yt-dlp-server"}

@app.post("/download", response_model=DownloadResponse)
def download_video(request: DownloadRequest):
    try:
        # Create temp directory
        with tempfile.TemporaryDirectory() as tmpdir:
            # Set quality format
            if request.quality == "1080p":
                format_str = "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]"
            elif request.quality == "720p":
                format_str = "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]"
            elif request.quality == "480p":
                format_str = "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]"
            else:
                format_str = "bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360][ext=mp4]"
            
            output_file = os.path.join(tmpdir, "%(id)s.%(ext)s")
            
            ydl_opts = {
    'format': format_str,
    'outtmpl': output_file,
    'merge_output_format': 'mp4',
    'quiet': True,
    'no_warnings': True,
    'extractor_args': {'youtube': {'player_client': ['ios', 'android', 'web']}},
    'http_headers': {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1'
    },
    'socket_timeout': 30,
    'retries': 3,
    'ignoreerrors': False,
    'no_check_certificates': True,
}

            
            # Download video
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(request.video_url, download=True)
                video_id = info.get('id')
                title = info.get('title')
                duration = info.get('duration')
                
                # Find downloaded file
                downloaded_file = os.path.join(tmpdir, f"{video_id}.mp4")
                
                if not os.path.exists(downloaded_file):
                    # Try to find any mp4 file
                    for f in os.listdir(tmpdir):
                        if f.endswith('.mp4'):
                            downloaded_file = os.path.join(tmpdir, f)
                            break
                
                if not os.path.exists(downloaded_file):
                    raise Exception("Downloaded file not found")
                
                # Upload to Cloudinary
                upload_result = cloudinary.uploader.upload(
                    downloaded_file,
                    resource_type="video",
                    public_id=f"youtube/{video_id}_{uuid.uuid4().hex[:8]}",
                    overwrite=True
                )
                
                return DownloadResponse(
                    success=True,
                    video_url=upload_result['secure_url'],
                    video_id=video_id,
                    title=title,
                    duration=duration
                )
                
    except Exception as e:
        return DownloadResponse(
            success=False,
            error=str(e)
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
