import os
import re
from pathlib import Path
from pydantic import BaseModel

# Base directory for EchoNode backend
BACKEND_DIR = Path(__file__).resolve().parent.parent

def get_downloads_dir() -> Path:
    env_dir = os.environ.get("DOWNLOADS_DIR")
    if env_dir:
        p = Path(env_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p
    default_dir = BACKEND_DIR / "downloads"
    try:
        default_dir.mkdir(parents=True, exist_ok=True)
        test_file = default_dir / ".write_test"
        test_file.touch()
        test_file.unlink()
        return default_dir
    except (OSError, PermissionError):
        tmp_dir = Path("/tmp/downloads")
        tmp_dir.mkdir(parents=True, exist_ok=True)
        return tmp_dir

DOWNLOADS_DIR = get_downloads_dir()
STATIC_DIR = BACKEND_DIR / "static"
try:
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
except (OSError, PermissionError):
    pass

class Settings(BaseModel):
    product_name: str = os.environ.get("PRODUCT_NAME", "MoodAudio Studio")
    app_name: str = "EchoNode Ingestion Hub"  # preserved for firmware/legacy compatibility
    version: str = "2.0.0"
    downloads_dir: Path = DOWNLOADS_DIR
    static_dir: Path = STATIC_DIR
    default_audio_format: str = "m4a"
    max_title_length: int = 60
    # Maximum recommended bitrates for ESP32-S3 I2S stream decoding (kbps)
    target_audio_bitrate_kbps: int = 128
    # Storage & processing limits
    max_upload_size_mb: int = int(os.environ.get("MAX_UPLOAD_SIZE_MB", "100"))
    max_audio_duration_seconds: int = int(os.environ.get("MAX_AUDIO_DURATION_SECONDS", "3600"))
    job_timeout_seconds: int = int(os.environ.get("JOB_TIMEOUT_SECONDS", "600"))
    temp_file_retention_hours: int = int(os.environ.get("TEMP_FILE_RETENTION_HOURS", "24"))
    output_retention_hours: int = int(os.environ.get("OUTPUT_RETENTION_HOURS", "72"))
    database_url: str = os.environ.get("DATABASE_URL", "")
    storage_backend: str = os.environ.get("STORAGE_BACKEND", "local")

settings = Settings()

def get_job_workspace(job_id: str) -> Path:
    """Create and return an isolated temporary workspace directory for a job."""
    workspace = settings.downloads_dir / f"job_{job_id}"
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace

def sanitize_fat32_filename(name: str, max_length: int = 60) -> str:
    """
    Sanitize string to guarantee safe compatibility with FAT32 MicroSD cards.
    Eliminates illegal characters: / \\ : * ? " < > | and non-ASCII or problematic control symbols.
    Limits base length to prevent path overflow on 8.3 / FAT32 systems.
    """
    # Replace illegal FAT32 characters with underscores
    cleaned = re.sub(r'[\\/*?:"<>|]', '_', name)
    # Remove leading/trailing periods or spaces
    cleaned = cleaned.strip(". ")
    # Replace non-ascii characters with close ASCII or underscores
    cleaned = cleaned.encode("ascii", "ignore").decode("ascii")
    # Collapse multiple consecutive underscores or spaces
    cleaned = re.sub(r'[\s_]+', '_', cleaned)
    if not cleaned:
        cleaned = "audio_track"
    return cleaned[:max_length]
