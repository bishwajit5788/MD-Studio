import asyncio
import logging
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Dict, Optional, Set, Tuple
import yt_dlp

from ..config import settings, get_job_workspace, sanitize_fat32_filename
from ..models import (
    JobDetailResponse,
    JobStage,
    ProcessingMode,
    OutputFormat,
    SourceType,
    RestorationSettings,
    AudioAnalysisReport
)
from .database import database_job_store
from .audio_analyzer import audio_analyzer
from .audio_restorer import audio_restorer
from .audio_validator import audio_validator
from .storage import storage_service
from .extractor import inspect_mp4_container_tracks, validate_youtube_url

logger = logging.getLogger("moodaudio.worker")

# Concurrency control for CPU-intensive DSP and separation
PIPELINE_SEMAPHORE = asyncio.Semaphore(2)

# In-memory cancellation registry
CANCELLED_JOBS: Set[str] = set()

def verify_audio_file_signature(file_path: Path) -> Tuple[bool, str]:
    """
    Validate real binary magic bytes for supported audio files.
    Rejects disguised non-audio files or script payloads.
    """
    try:
        with open(file_path, "rb") as f:
            header = f.read(32)

        if len(header) < 4:
            return False, "File is empty or truncated"

        # MP3 (ID3v2 or sync frame 0xFFFB/0xFFF3/0xFFF2)
        if header.startswith(b"ID3") or (header[0] == 0xFF and (header[1] & 0xE0) == 0xE0):
            return True, "mp3"

        # MP4 / M4A (ftyp box at offset 4)
        if len(header) >= 8 and header[4:8] == b"ftyp":
            return True, "m4a"

        # FLAC (fLaC)
        if header.startswith(b"fLaC"):
            return True, "flac"

        # WAV (RIFF....WAVE)
        if header.startswith(b"RIFF") and len(header) >= 12 and header[8:12] == b"WAVE":
            return True, "wav"

        # OGG / Opus (OggS)
        if header.startswith(b"OggS"):
            return True, "ogg"

        # AAC ADTS header (0xFFF1 or 0xFFF9)
        if header[0] == 0xFF and (header[1] & 0xF6) == 0xF0:
            return True, "aac"

        return False, "Unrecognized audio container or file signature"
    except Exception as e:
        return False, str(e)


class StudioJobWorker:
    """
    Background Audio Engineering Pipeline Worker.
    Executes staged audio workflows:
    validating -> extracting -> analyzing -> restoring -> rendering -> validating_output -> completed
    """
    def is_cancelled(self, job_id: str) -> bool:
        return job_id in CANCELLED_JOBS

    def cancel_job(self, job_id: str) -> bool:
        CANCELLED_JOBS.add(job_id)
        job = database_job_store.get_job(job_id)
        if job and job.status not in (JobStage.COMPLETED, JobStage.FAILED):
            job.status = JobStage.CANCELLED
            job.current_stage = "Job was cancelled by user."
            job.updated_at = time.time()
            database_job_store.save_job(job)
            logger.info(f"Job {job_id} marked CANCELLED.")
            return True
        return False

    async def execute_job(
        self,
        job_id: str,
        settings_override: Optional[RestorationSettings] = None
    ):
        """Execute the complete multi-stage audio processing pipeline."""
        async with PIPELINE_SEMAPHORE:
            job = database_job_store.get_job(job_id)
            if not job or self.is_cancelled(job_id):
                return

            workspace = get_job_workspace(job_id)
            restoration_settings = settings_override or RestorationSettings()

            try:
                # -------------------------------------------------------------
                # STAGE 1: VALIDATING
                # -------------------------------------------------------------
                job.status = JobStage.VALIDATING
                job.current_stage = "Validating audio source and media signatures..."
                job.progress = 5.0
                job.updated_at = time.time()
                database_job_store.save_job(job)

                original_source_file = workspace / "source_original"

                if job.source_type == SourceType.UPLOAD:
                    # Find uploaded source file in workspace
                    candidates = list(workspace.glob("uploaded_source.*"))
                    if not candidates or not candidates[0].exists():
                        raise FileNotFoundError("Uploaded audio file was not found in workspace.")
                    uploaded_file = candidates[0]

                    # Verify signature
                    is_valid, sig_fmt = verify_audio_file_signature(uploaded_file)
                    if not is_valid:
                        raise ValueError(f"Security validation failed: {sig_fmt}")

                    original_source_file = workspace / f"original.{sig_fmt}"
                    shutil.move(str(uploaded_file), str(original_source_file))

                elif job.source_type == SourceType.URL:
                    # ---------------------------------------------------------
                    # STAGE 2: EXTRACTING
                    # ---------------------------------------------------------
                    if not job.source_url or not validate_youtube_url(job.source_url):
                        raise ValueError("Invalid, unsupported, or unauthorized source URL.")

                    job.status = JobStage.EXTRACTING
                    job.current_stage = "Extracting verified audio-only stream from source..."
                    job.progress = 15.0
                    job.updated_at = time.time()
                    database_job_store.save_job(job)

                    # Extract via yt-dlp strictly for best audio
                    raw_out = workspace / "downloaded_raw.%(ext)s"
                    ydl_opts = {
                        "outtmpl": str(raw_out),
                        "noplaylist": True,
                        "quiet": True,
                        "no_warnings": True,
                        "format": "140/bestaudio[ext=m4a]/bestaudio",
                        "extractor_args": {
                            "youtube": {
                                "player_client": ["mweb", "web_safari", "android_vr", "web_embedded", "web", "android", "ios"]
                            }
                        }
                    }

                    loop = asyncio.get_running_loop()
                    def _dl():
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            info = ydl.extract_info(job.source_url, download=True)
                            return info.get("title", f"stream_{job_id[:8]}")

                    title = await loop.run_in_executor(None, _dl)
                    job.source_filename = title

                    # Locate extracted raw audio
                    extracted_files = list(workspace.glob("downloaded_raw.*"))
                    if not extracted_files:
                        raise RuntimeError("Audio extraction failed to produce a file.")
                    raw_file = extracted_files[0]

                    # Verify pure audio container (reject video streams)
                    if raw_file.suffix.lower() == ".m4a":
                        audio_tracks, video_tracks = inspect_mp4_container_tracks(raw_file)
                        if video_tracks > 0:
                            raw_file.unlink(missing_ok=True)
                            raise ValueError(f"Security violation: Stream contains {video_tracks} video track(s). Must be audio-only!")
                        if audio_tracks < 1:
                            raw_file.unlink(missing_ok=True)
                            raise ValueError("Stream contains no audio tracks.")

                    original_source_file = workspace / f"original{raw_file.suffix}"
                    shutil.move(str(raw_file), str(original_source_file))

                if self.is_cancelled(job_id):
                    return

                job.stages_completed.append("extraction_validated")

                # -------------------------------------------------------------
                # STAGE 3: ANALYZING (Pre-restoration Analysis)
                # -------------------------------------------------------------
                job.status = JobStage.ANALYZING
                job.current_stage = "Performing acoustic analysis and EBU R128 loudness scanning..."
                job.progress = 30.0
                job.updated_at = time.time()
                database_job_store.save_job(job)

                loop = asyncio.get_running_loop()
                raw_analysis = await loop.run_in_executor(None, audio_analyzer.analyze, original_source_file)
                job.raw_analysis = raw_analysis

                # Generate 30s loudness-matched original preview
                original_preview_file = workspace / "preview_original.m4a"
                await loop.run_in_executor(
                    None,
                    audio_restorer.generate_preview,
                    original_source_file,
                    original_preview_file,
                    -16.0
                )
                if original_preview_file.exists():
                    job.original_preview_url = f"/api/v1/jobs/{job_id}/preview?source=original"

                job.stages_completed.append("analysis_completed")

                if self.is_cancelled(job_id):
                    return

                # -------------------------------------------------------------
                # STAGE 4: RESTORING (Pre-restoration stage)
                # -------------------------------------------------------------
                job.status = JobStage.RESTORING
                job.current_stage = "Applying conservative DC correction, noise evaluation, and peak control..."
                job.progress = 50.0
                job.updated_at = time.time()
                database_job_store.save_job(job)

                restored_working_file = workspace / "working_restored.wav"
                await loop.run_in_executor(
                    None,
                    audio_restorer.pre_restore,
                    original_source_file,
                    restored_working_file,
                    raw_analysis,
                    restoration_settings
                )
                job.stages_completed.append("restoration_completed")

                if self.is_cancelled(job_id):
                    return

                # -------------------------------------------------------------
                # STAGE 5: RENDERING (Four Mode Processing)
                # -------------------------------------------------------------
                job.status = JobStage.RENDERING
                job.current_stage = f"Rendering {job.processing_mode.value.replace('_', ' ').title()} in {job.requested_format.value.upper()}..."
                job.progress = 70.0
                job.updated_at = time.time()
                database_job_store.save_job(job)

                sanitized_title = sanitize_fat32_filename(job.source_filename or f"track_{job_id[:8]}")
                mode_suffix = job.processing_mode.value
                rendered_filename = f"{sanitized_title}_{mode_suffix}.{job.requested_format.value}"
                final_output_file = workspace / rendered_filename

                await loop.run_in_executor(
                    None,
                    audio_restorer.process_mode,
                    restored_working_file,
                    final_output_file,
                    job.processing_mode,
                    job.requested_format,
                    raw_analysis,
                    restoration_settings
                )

                if not final_output_file.exists():
                    raise RuntimeError("Audio rendering did not generate an output file.")

                # Generate processed loudness-matched preview
                processed_preview_file = workspace / "preview_processed.m4a"
                await loop.run_in_executor(
                    None,
                    audio_restorer.generate_preview,
                    final_output_file,
                    processed_preview_file,
                    -16.0
                )
                if processed_preview_file.exists():
                    job.processed_preview_url = f"/api/v1/jobs/{job_id}/preview?source=processed"

                # Post-restoration analysis
                restored_analysis = await loop.run_in_executor(None, audio_analyzer.analyze, final_output_file)
                job.restored_analysis = restored_analysis
                job.stages_completed.append("rendering_completed")

                if self.is_cancelled(job_id):
                    return

                # -------------------------------------------------------------
                # STAGE 6: VALIDATING_OUTPUT (Media Validation Gate)
                # -------------------------------------------------------------
                job.status = JobStage.VALIDATING_OUTPUT
                job.current_stage = "Running automated quality assurance and stream validation..."
                job.progress = 90.0
                job.updated_at = time.time()
                database_job_store.save_job(job)

                validation = await loop.run_in_executor(
                    None,
                    audio_validator.validate_output,
                    final_output_file,
                    job.requested_format,
                    raw_analysis.duration_seconds,
                    2  # Stereo/binaural channel count
                )
                job.validation_result = validation

                if not validation.is_valid:
                    issues_str = "; ".join(validation.issues)
                    raise ValueError(f"Output media validation failed: {issues_str}")

                job.stages_completed.append("output_validated")

                # -------------------------------------------------------------
                # STAGE 7: COMPLETED (Persist to Storage)
                # -------------------------------------------------------------
                download_url = storage_service.save_file(
                    filename=rendered_filename,
                    source_path=final_output_file,
                    content_type=f"audio/{job.requested_format.value}"
                )

                job.status = JobStage.COMPLETED
                job.current_stage = "Processing completed and verified."
                job.progress = 100.0
                job.output_filename = rendered_filename
                job.output_file_size = final_output_file.stat().st_size
                job.download_url = download_url
                job.completed_at = time.time()
                job.updated_at = time.time()
                job.expires_at = time.time() + (settings.output_retention_hours * 3600)
                database_job_store.save_job(job)
                logger.info(f"Job {job_id} successfully COMPLETED: {rendered_filename}")

            except Exception as e:
                raw_err = str(e)
                logger.error(f"Job {job_id} failed: {raw_err}")
                job.status = JobStage.FAILED
                job.current_stage = f"Processing stopped: {raw_err}"
                job.error = raw_err
                job.updated_at = time.time()
                job.completed_at = time.time()
                database_job_store.save_job(job)

            finally:
                # Clean up intermediate wav files, keeping original and preview files
                try:
                    for temp_f in workspace.glob("working_*.wav"):
                        temp_f.unlink(missing_ok=True)
                except Exception:
                    pass

job_worker = StudioJobWorker()
