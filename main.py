from fastapi import FastAPI
from pydantic import BaseModel
import cloudinary
import cloudinary.uploader
import os
import uuid
import tempfile
import httpx
import json

app = FastAPI()

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

class DownloadRequest(BaseModel):
    video_url: str
    quality: str = "720p"

class DownloadResponse(BaseModel):
    success: bool
    video_url: str = None
    video_id: str = None
    title: str = None
    error: str = None

@app.get("/")
def health_check():
    return {"status": "ok", "service": "y2mate-server"}

async def get_y2mate_download_url(youtube_url: str, quality: str = "720p"):
    """Get download URL from Y2mate API"""
    
    # Extract video ID
    video_id = None
    if "youtube.com/watch?v=" in youtube_url:
        video_id = youtube_url.split("v=")[1].split("&")[0]
    elif "youtu.be/" in youtube_url:
        video_id = youtube_url.split("youtu.be/")[1].split("?")[0]
    
    if not video_id:
        raise Exception("Invalid YouTube URL")
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        # Step 1: Analyze video
        analyze_url = "https://www.y2mate.com/mates/analyzeV2/ajax"
        analyze_data = {
            "k_query": youtube_url,
            "k_page": "home",
            "hl": "en",
            "q_auto": 0
        }
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://www.y2mate.com",
            "Referer": "https://www.y2mate.com/"
        }
        
        resp = await client.post(analyze_url, data=analyze_data, headers=headers)
        data = resp.json()
        
        if data.get("status") != "ok":
            raise Exception("Y2mate analyze failed")
        
        title = data.get("title", "video")
        
        # Find quality key
        links = data.get("links", {}).get("mp4", {})
        quality_map = {"1080p": "137", "720p": "22", "480p": "135", "360p": "18"}
        
        k_value = None
        for q_key, link_data in links.items():
            if quality in link_data.get("q", ""):
                k_value = link_data.get("k")
                break
        
        # Fallback to any available quality
        if not k_value and links:
            first_key = list(links.keys())[0]
            k_value = links[first_key].get("k")
        
        if not k_value:
            raise Exception("No download link found")
        
        # Step 2: Convert
        convert_url = "https://www.y2mate.com/mates/convertV2/index"
        convert_data = {
            "vid": video_id,
            "k": k_value
        }
        
        resp2 = await client.post(convert_url, data=convert_data, headers=headers)
        data2 = resp2.json()
        
        if data2.get("status") != "ok":
            raise Exception("Y2mate convert failed")
        
        download_url = data2.get("dlink")
        
        return {"url": download_url, "title": title, "video_id": video_id}

@app.post("/download", response_model=DownloadResponse)
async def download_video(request: DownloadRequest):
    """Download YouTube video via Y2mate and upload to Cloudinary"""
    try:
        # Get Y2mate download URL
        y2mate_data = await get_y2mate_download_url(request.video_url, request.quality)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            video_id = y2mate_data["video_id"]
            output_file = os.path.join(tmpdir, f"{video_id}.mp4")
            
            # Download from Y2mate
            async with httpx.AsyncClient(timeout=300.0, follow_redirects=True) as client:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
                
                async with client.stream("GET", y2mate_data["url"], headers=headers) as resp:
                    with open(output_file, 'wb') as f:
                        async for chunk in resp.aiter_bytes(chunk_size=8192):
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
                title=y2mate_data["title"]
            )
            
    except Exception as e:
        return DownloadResponse(success=False, error=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
