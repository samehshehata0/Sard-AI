import os

import uvicorn

if __name__ == "__main__":
    # Locally the API listens on loopback with auto-reload. In a container docker-compose sets
    # BACKEND_HOST=0.0.0.0 (so the published port reaches it) and BACKEND_RELOAD=false.
    uvicorn.run(
        "app.main:app",
        host=os.getenv("BACKEND_HOST", "127.0.0.1"),
        port=int(os.getenv("BACKEND_PORT", "8000")),
        reload=os.getenv("BACKEND_RELOAD", "true").lower() == "true",
    )
