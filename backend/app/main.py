from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from .config import settings
from .api.routes import router as legacy_router, get_worker_url, check_worker_health
from .api.v1.routes import router as v1_router

app = FastAPI(
    title=settings.product_name,
    version=settings.version,
    description="Professional Audio Extraction, Restoration & Spatial Processing Platform (MoodAudio Studio)"
)

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    msg = exc.detail if isinstance(exc.detail, str) else exc.detail.get("error", exc.detail.get("detail", str(exc.detail)))
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": msg, "detail": msg},
        headers=exc.headers
    )

# Enable CORS for local cross-origin development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routers (both v1 and legacy for backward compatibility)
app.include_router(v1_router, prefix="/api")
app.include_router(legacy_router)

# Serve static web dashboard
if settings.static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(settings.static_dir)), name="static")

@app.get("/", include_in_schema=False)
async def serve_index():
    index_file = settings.static_dir / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "EchoNode Backend is running. Visit /docs for Swagger API documentation."}

@app.get("/health")
async def health_check():
    worker_url = get_worker_url()
    worker_configured = bool(worker_url)
    reachable = None
    if worker_configured:
        reachable, _ = check_worker_health(timeout=2.0)

    mode = "proxy_to_worker" if worker_configured else "standalone_local"

    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.version,
        "mode": mode,
        "worker_configured": worker_configured,
        "worker_reachable": reachable
    }
