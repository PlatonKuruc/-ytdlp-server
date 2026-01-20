from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import cloudinary
import cloudinary.uploader
import os
import uuid
import tempfile
import requests

app = FastAPI()

# Cloudinary config
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

class DownloadURLRequest(BaseModel):
    video_url: str
    title: str = "video"
    video_id: str = None

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

@app.post("/download-url", response_model=DownloadResponse)
def download_from_url(request: DownloadURLRequest):
    """Download video from direct URL (streaming URL from RapidAPI)"""
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            video_id = request.video_id or uuid.uuid4().hex[:8]
            output_file = os.path.join(tmpdir, f"{video_id}.mp4")
            
            # Download video from streaming URL
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'https://www.youtube.com/',
                'Accept': '*/*',
            }
            
            response = requests.get(request.video_url, headers=headers, stream=True, timeout=300)
            response.raise_for_status()
            
            with open(output_file, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            # Upload to Cloudinary
            upload_result = cloudinary.uploader.upload(
                output_file,
                resource_type="video",
                public_id=f"youtube/{video_id}_{uuid.uuid4().hex[:8]}",
                overwrite=True
            )
            
            return DownloadResponse(
                success=True,
                video_url=upload_result['secure_url'],
                video_id=video_id,
                title=request.title
            )
            
    except requests.exceptions.RequestException as e:
        return DownloadResponse(success=False, error=f"Download failed: {str(e)}")
    except Exception as e:
        return DownloadResponse(success=False, error=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
```

Commitni zmenu a počkaj na redeploy.

Potom pošli Base44:
```
Nový flow s RapidAPI + Render:

1. Uprav downloadYouTubeVideo:

async function downloadYouTubeVideo(youtube_url) {
  // Krok 1: Získaj streaming URL z N8N (RapidAPI)
  const n8nResponse = await fetch('https://pl5pl0mb.app.n8n.cloud/webhook/youtube-download', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ video_url: youtube_url })
  });
  const n8nData = await n8nResponse.json();
  
  if (!n8nData.mp4_url) {
    throw new Error('N8N nevrátil streaming URL');
  }
  
  // Krok 2: Pošli streaming URL na Render server
  const renderResponse = await fetch('https://ytdlp-server-ajwh.onrender.com/download-url', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      video_url: n8nData.mp4_url,
      title: n8nData.title || 'video',
      video_id: n8nData.video_id
    })
  });
  const renderData = await renderResponse.json();
  
  return {
    success: renderData.success,
    cloudinary_url: renderData.video_url,
    title: renderData.title,
    video_id: renderData.video_id
  };
}
