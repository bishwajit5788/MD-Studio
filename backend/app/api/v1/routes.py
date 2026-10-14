import json
import logging
import os
import shutil
import time
import urllib.parse
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status
)
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse

from ...config import settings, get_job_workspace, sanitize_fat32_filename
from ...models import (
    CapabilitiesResponse,
    JobCreateRequest,
    JobDetailResponse,
    JobStage,
    ModeCapability,
    OutputFormat,
    ProcessingMode,
    RestorationSettings,
    SourceType
)
from ..routes import validate_youtube_url
from ...services.database import database_job_store
from ...services.job_worker import job_worker, verify_audio_file_signature
from ...services.storage import storage_service

logger = logging.getLogger("moodaudio.v1.routes")

router = APIRouter(prefix="/v1", tags=["MoodAudio Studio Engine v1"])

MAX_UPLOAD_BYTES = settings.max_upload_size_mb * 1024 * 1024

@router.get("/capabilities", response_model=CapabilitiesResponse)
async def get_capabilities():
    """
    Expose available processing modes, supported formats, limits,
    and capability flags so the UI dynamically adapts to backend reality.
    """
    import yt_dlp
    yt_avail = True
    try:
        _ = yt_dlp.YoutubeDL
    except Exception:
        yt_avail = False

    ffmpeg_avail = shutil.which("ffmpeg") is not None or Path("/opt/homebrew/bin/ffmpeg").exists()

    modes = [
        ModeCapability(
            id=ProcessingMode.DOLBY_ATMOS.value,
            name="Dolby Atmos",
            description="Immersive spatial master authoring with verified 3D audio object metadata.",
            enabled=False,
            status_badge="Coming Soon",
            notice="Compatible Atmos authoring workflow not yet validated. Strict open-source and delivery compliance required.",
            features=[
                "Spatial Bed & Object Authoring (Roadmap)",
                "ADM BWF Profile Verification (Roadmap)",
                "Disabled until certified rendering workflow is proven"
            ]
        ),
        ModeCapability(
            id=ProcessingMode.IMMERSIVE_AUDIO.value,
            name="Immersive Audio",
            description="Genuine 3D binaural headphone spatialization with room reflection simulation.",
            enabled=True,
            status_badge="Active",
            notice=None,
            features=[
                "Virtual source positioning & binaural HRTF crossfeed",
                "Stereo headphone soundstage expansion",
                "Acoustic depth & room reflection simulation",
                "User-controlled spatial width intensity (Subtle, Moderate, Wide)",
                "Natural timbre preservation with conservative true-peak limiter"
            ]
        ),
        ModeCapability(
            id=ProcessingMode.STEREO_SOUND.value,
            name="Stereo Sound",
            description="High-fidelity input-preserving mastering, channel balance, and headroom optimization.",
            enabled=True,
            status_badge="Active",
            notice=None,
            features=[
                "Source fidelity priority (no artificial widening by default)",
                "Channel balance and stereo correlation verification",
                "Lossless stream-copy path when formats align",
                "Sub-bass DC offset removal and inter-sample clipping prevention",
                "Audiophile FLAC / WAV / 320k AAC export options"
            ]
        ),
        ModeCapability(
            id=ProcessingMode.AUDIO_ENHANCER.value,
            name="Audio Enhancer",
            description="Adaptive, conservative multi-stage restoration tailored for speech or musical dynamics.",
            enabled=True,
            status_badge="Active",
            notice=None,
            features=[
                "Content-aware processing (Speech vs. Music dynamics)",
                "Acoustic noise analysis and conservative SNR-aware denoising",
                "Voice articulation and dialog presence clarity",
                "Musical low-end warmth and smooth high-frequency sheen",
                "EBU R128 loudness normalization (-14 LUFS standard)"
            ]
        )
    ]

    return CapabilitiesResponse(
        product_name=settings.product_name,
        version=settings.version,
        max_upload_size_mb=settings.max_upload_size_mb,
        max_audio_duration_seconds=settings.max_audio_duration_seconds,
        supported_formats=["m4a", "mp3", "flac", "wav"],
        modes=modes,
        ffmpeg_available=ffmpeg_avail,
        yt_dlp_available=yt_avail,
        database_backend="PostgreSQL" if database_job_store.is_postgres else "SQLite",
        storage_backend=settings.storage_backend,
        disclaimer=(
            "MoodAudio Studio implements genuine acoustic DSP and conservative audio restoration. "
            "Restoration reduces audible defects and optimizes balance, but cannot guarantee perfect recovery of the original lossless master."
        )
    )

@router.get("/health")
async def health_check():
    """Detailed health check for v1 audio processing service."""
    ffmpeg_avail = shutil.which("ffmpeg") is not None or Path("/opt/homebrew/bin/ffmpeg").exists()
    return {
        "status": "healthy",
        "product": settings.product_name,
        "version": settings.version,
        "ffmpeg_available": ffmpeg_avail,
        "database_backend": "PostgreSQL" if database_job_store.is_postgres else "SQLite",
        "storage_backend": settings.storage_backend,
        "timestamp": time.time()
    }

@router.post("/jobs", response_model=JobDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_job(
    background_tasks: BackgroundTasks,
    request: Request,
    file: Optional[UploadFile] = File(None),
    source_type: str = Form(None),
    url: Optional[str] = Form(None),
    processing_mode: str = Form("stereo_sound"),
    output_format: str = Form("m4a"),
    custom_title: Optional[str] = Form(None),
    settings_json: Optional[str] = Form(None)
):
    """
    Create a new audio processing job.
    Accepts direct audio upload via multipart/form-data or authorized source URL.
    """
    # Also support JSON body if submitted without multipart
    content_type = request.headers.get("content-type", "")
    restoration_settings = RestorationSettings()

    if "application/json" in content_type:
        try:
            body = await request.json()
            source_type = body.get("source_type", "url")
            url = body.get("url")
            processing_mode = body.get("processing_mode", "stereo_sound")
            output_format = body.get("output_format", "m4a")
            custom_title = body.get("custom_title")
            if "settings" in body and body["settings"]:
                restoration_settings = RestorationSettings(**body["settings"])
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Malformed JSON request: {e}")
    else:
        if settings_json:
            try:
                parsed = json.loads(settings_json)
                restoration_settings = RestorationSettings(**parsed)
            except Exception:
                pass

    # Validate Mode
    try:
        mode_enum = ProcessingMode(processing_mode)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid processing mode '{processing_mode}'. Supported: {[m.value for m in ProcessingMode]}"
        )

    if mode_enum == ProcessingMode.DOLBY_ATMOS:
        raise HTTPException(
            status_code=400,
            detail="Dolby Atmos mode is currently disabled. Atmos authoring workflow is pending validation."
        )

    # Validate Format
    try:
        format_enum = OutputFormat(output_format)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid output format '{output_format}'. Supported: {[f.value for f in OutputFormat]}"
        )

    job_id = str(uuid.uuid4())
    workspace = get_job_workspace(job_id)

    # Branch: File Upload
    if file:
        src_type_enum = SourceType.UPLOAD
        filename = file.filename or "uploaded_track"
        target_upload_path = workspace / f"uploaded_source{Path(filename).suffix}"

        # Stream upload to disk with size boundary limit
        total_bytes = 0
        with open(target_upload_path, "wb") as dest:
            while True:
                chunk = await file.read(1024 * 64)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > MAX_UPLOAD_BYTES:
                    target_upload_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"Upload exceeded maximum limit of {settings.max_upload_size_mb} MB."
                    )
                dest.write(chunk)

        # Validate file signature
        is_valid, sig_msg = verify_audio_file_signature(target_upload_path)
        if not is_valid:
            target_upload_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=400,
                detail=f"Uploaded file signature validation failed: {sig_msg}"
            )

        job_record = JobDetailResponse(
            job_id=job_id,
            product_name=settings.product_name,
            source_type=src_type_enum,
            source_filename=custom_title or Path(filename).stem,
            source_url=None,
            processing_mode=mode_enum,
            requested_format=format_enum,
            status=JobStage.QUEUED,
            current_stage="Job queued for processing...",
            stages_completed=[],
            progress=0.0,
            created_at=time.time(),
            updated_at=time.time(),
            can_cancel=True
        )

    # Branch: Authorized URL
    elif url:
        clean_url = url.strip()
        if not validate_youtube_url(clean_url):
            raise HTTPException(
                status_code=400,
                detail="Invalid or unauthorized source URL. Please provide a supported audio URL or upload directly."
            )

        src_type_enum = SourceType.URL
        job_record = JobDetailResponse(
            job_id=job_id,
            product_name=settings.product_name,
            source_type=src_type_enum,
            source_filename=custom_title or "Source Audio Stream",
            source_url=clean_url,
            processing_mode=mode_enum,
            requested_format=format_enum,
            status=JobStage.QUEUED,
            current_stage="Job queued for processing...",
            stages_completed=[],
            progress=0.0,
            created_at=time.time(),
            updated_at=time.time(),
            can_cancel=True
        )
    else:
        raise HTTPException(
            status_code=400,
            detail="Either a file upload or an authorized source URL is required."
        )

    # Save to database
    database_job_store.save_job(job_record)

    # Dispatch to asynchronous background worker
    background_tasks.add_task(job_worker.execute_job, job_id, restoration_settings)

    return job_record

@router.get("/jobs/{job_id}", response_model=JobDetailResponse)
async def get_job_status(job_id: str):
    """Retrieve detailed state, technical metadata, stages, and validation results."""
    job = database_job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Audio processing job not found.")
    return job

@router.get("/jobs", response_model=List[JobDetailResponse])
async def list_recent_jobs(limit: int = Query(25, ge=1, le=100)):
    """List recent audio processing jobs for the studio."""
    return database_job_store.list_jobs(limit=limit)

@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    """Cancel an active processing job."""
    success = job_worker.cancel_job(job_id)
    job = database_job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    if not success:
        return {
            "message": f"Job is in terminal state '{job.status.value}'.",
            "job_id": job_id,
            "status": job.status.value
        }
    return {"message": "Job cancellation initiated.", "job_id": job_id, "status": "cancelled"}

@router.post("/jobs/{job_id}/retry", response_model=JobDetailResponse)
async def retry_job(job_id: str, background_tasks: BackgroundTasks):
    """Retry a failed or cancelled processing job."""
    job = database_job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    if job.status not in (JobStage.FAILED, JobStage.CANCELLED):
        raise HTTPException(
            status_code=400,
            detail=f"Only failed or cancelled jobs can be retried (current state: {job.status.value})."
        )

    job.status = JobStage.QUEUED
    job.current_stage = "Job retry queued..."
    job.progress = 0.0
    job.error = None
    job.retry_count += 1
    job.updated_at = time.time()
    database_job_store.save_job(job)

    # Re-dispatch worker
    background_tasks.add_task(job_worker.execute_job, job_id)

    return job

@router.get("/jobs/{job_id}/preview")
async def stream_preview(job_id: str, source: str = Query("processed", pattern="^(original|processed)$")):
    """
    Stream loudness-matched audio preview for A/B comparison without volume bias.
    """
    job = database_job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    workspace = get_job_workspace(job_id)
    preview_filename = "preview_original.m4a" if source == "original" else "preview_processed.m4a"
    preview_path = workspace / preview_filename

    # Fallback if specific preview not ready
    if not preview_path.exists():
        if source == "processed":
            # Check if final output exists
            if job.output_filename:
                cand = workspace / job.output_filename
                if cand.exists():
                    return FileResponse(cand, media_type=f"audio/{job.requested_format.value}")
        candidates = list(workspace.glob("original.*"))
        if candidates and candidates[0].exists():
            return FileResponse(candidates[0], media_type="audio/mp4")
        raise HTTPException(status_code=404, detail="Audio preview not yet available for this job.")

    return FileResponse(
        preview_path,
        media_type="audio/mp4",
        headers={"Accept-Ranges": "bytes", "Cache-Control": "no-cache"}
    )

@router.get("/jobs/{job_id}/download")
async def download_output(job_id: str):
    """
    Download the validated audio output.
    Downloads are strictly prohibited until output validation passes.
    """
    job = database_job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    if job.status != JobStage.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Output is not ready for download. Current status: {job.status.value}."
        )

    if not job.output_filename:
        raise HTTPException(status_code=404, detail="Output file not recorded.")

    # 1. Check local workspace
    workspace = get_job_workspace(job_id)
    local_output = workspace / job.output_filename
    if local_output.exists():
        return FileResponse(
            local_output,
            media_type=f"audio/{job.requested_format.value}",
            filename=job.output_filename,
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{urllib.parse.quote(job.output_filename)}"
            }
        )

    # 2. Check storage service
    stored_path = storage_service.get_file_path(job.output_filename)
    if stored_path and stored_path.exists():
        return FileResponse(
            stored_path,
            media_type=f"audio/{job.requested_format.value}",
            filename=job.output_filename
        )

    # 3. Check presigned URL
    if storage_service.file_exists(job.output_filename):
        return RedirectResponse(url=storage_service.get_download_url(job.output_filename))

    raise HTTPException(status_code=404, detail="Validated output file could not be retrieved from storage.")

@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    """Delete a job record and remove associated files from storage."""
    job = database_job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    # Remove workspace directory
    workspace = get_job_workspace(job_id)
    if workspace.exists():
        shutil.rmtree(workspace, ignore_errors=True)

    # Remove from storage if stored
    if job.output_filename:
        storage_service.delete_file(job.output_filename)

    database_job_store.delete_job(job_id)
    return {"message": f"Successfully deleted job {job_id} and its associated files."}
