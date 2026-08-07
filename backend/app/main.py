import sys
import os
import asyncio
import logging

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from app.api.endpoints import router
from app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url="/openapi.json",
    docs_url="/docs"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs(settings.TEMP_DIR, exist_ok=True)

@app.get("/temp/{path:path}")
async def serve_temp_media(path: str, request: Request):
    file_path = os.path.join(settings.TEMP_DIR, path)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    file_size = os.path.getsize(file_path)
    if file_size == 0:
        raise HTTPException(status_code=404, detail="File is empty")

    content_type = (
        "video/mp4" if path.endswith(".mp4")
        else "audio/mpeg" if path.endswith(".mp3")
        else "image/jpeg" if path.endswith(".jpg") or path.endswith(".jpeg")
        else "image/png" if path.endswith(".png")
        else "application/pdf" if path.endswith(".pdf")
        else "application/octet-stream"
    )

    range_header = request.headers.get("range")
    if range_header and path.endswith((".mp4", ".mp3")):
        try:
            byte1, byte2 = 0, None
            match = range_header.replace("bytes=", "").split("-")
            if match[0]:
                byte1 = int(match[0])
            if len(match) > 1 and match[1]:
                byte2 = int(match[1])

            chunk_size = 1024 * 1024
            byte2 = byte2 if byte2 is not None else min(byte1 + chunk_size - 1, file_size - 1)
            byte1 = min(byte1, file_size - 1)
            byte2 = min(byte2, file_size - 1)
            length = byte2 - byte1 + 1

            def stream_file():
                with open(file_path, "rb") as f:
                    f.seek(byte1)
                    remaining = length
                    while remaining > 0:
                        read_len = min(1024 * 64, remaining)
                        data = f.read(read_len)
                        if not data:
                            break
                        remaining -= len(data)
                        yield data

            headers = {
                "Content-Range": f"bytes {byte1}-{byte2}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(length),
                "Content-Type": content_type,
            }
            return StreamingResponse(stream_file(), status_code=206, headers=headers)
        except Exception as e:
            logging.warning(f"[Streaming] Range request fallback: {e}")

    return FileResponse(file_path, media_type=content_type)

app.include_router(router, prefix=settings.API_V1_STR)

@app.get("/")
def root():
    return {"message": "Sard-AI Automation Service Running", "engine": "Google NotebookLM"}
