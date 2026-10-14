import os
import shutil
import logging
import urllib.parse
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional
from ..models import AudioFileItem
from ..config import settings

logger = logging.getLogger("echonode.storage")

class StorageService(ABC):
    """Abstract interface for media file storage."""

    @abstractmethod
    def save_file(self, filename: str, source_path: Path, content_type: str = "audio/mp4") -> str:
        """Persist file into storage and return its stable download URL."""
        pass

    @abstractmethod
    def get_file_path(self, filename: str) -> Optional[Path]:
        """Return local file path if available on disk, else None."""
        pass

    @abstractmethod
    def get_download_url(self, filename: str) -> str:
        """Return stable download URL for the file."""
        pass

    @abstractmethod
    def list_files(self) -> List[AudioFileItem]:
        """List all stored audio tracks."""
        pass

    @abstractmethod
    def delete_file(self, filename: str) -> bool:
        """Delete an audio track from storage."""
        pass

    @abstractmethod
    def file_exists(self, filename: str) -> bool:
        """Check if file exists in storage."""
        pass


class LocalStorageService(StorageService):
    """
    Local filesystem storage provider.
    Serves files from downloads_dir via /api/download/{filename}.
    Ideal for local development, home server/Pi, and local MicroSD provisioning.
    """
    def __init__(self, storage_dir: Optional[Path] = None):
        self.storage_dir = storage_dir or settings.downloads_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def save_file(self, filename: str, source_path: Path, content_type: str = "audio/mp4") -> str:
        dest_path = self.storage_dir / filename
        if source_path.resolve() != dest_path.resolve():
            shutil.copy2(source_path, dest_path)
        return self.get_download_url(filename)

    def get_file_path(self, filename: str) -> Optional[Path]:
        safe_path = (self.storage_dir / filename).resolve()
        if not str(safe_path).startswith(str(self.storage_dir.resolve())):
            return None
        if safe_path.exists() and safe_path.is_file():
            return safe_path
        return None

    def get_download_url(self, filename: str) -> str:
        quoted = urllib.parse.quote(filename)
        return f"/api/download/{quoted}"

    def list_files(self) -> List[AudioFileItem]:
        files: List[AudioFileItem] = []
        if not self.storage_dir.exists():
            return files

        valid_extensions = {".m4a", ".mp3", ".aac", ".ogg", ".opus"}
        try:
            for path in sorted(self.storage_dir.iterdir(), key=os.path.getmtime, reverse=True):
                if path.is_file() and path.suffix.lower() in valid_extensions:
                    stat = path.stat()
                    files.append(AudioFileItem(
                        filename=path.name,
                        title=path.stem.replace("_", " "),
                        size_bytes=stat.st_size,
                        extension=path.suffix.lower().lstrip("."),
                        download_url=self.get_download_url(path.name),
                        sd_ready=True,
                        created_at=stat.st_mtime
                    ))
        except Exception as e:
            logger.error(f"Error listing local storage files: {e}")
        return files

    def delete_file(self, filename: str) -> bool:
        p = self.get_file_path(filename)
        if p and p.exists():
            p.unlink()
            return True
        return False

    def file_exists(self, filename: str) -> bool:
        p = self.get_file_path(filename)
        return p is not None and p.exists()


class S3StorageService(StorageService):
    """
    S3 / Cloudflare R2 / MinIO Persistent Object Storage provider.
    Returns persistent public/signed URLs for completed tracks.
    """
    def __init__(self):
        self.bucket_name = os.environ.get("STORAGE_BUCKET") or os.environ.get("S3_BUCKET_NAME", "echonode-audio")
        self.endpoint_url = os.environ.get("STORAGE_ENDPOINT") or os.environ.get("S3_ENDPOINT_URL")
        self.access_key = os.environ.get("STORAGE_ACCESS_KEY_ID") or os.environ.get("S3_ACCESS_KEY_ID")
        self.secret_key = os.environ.get("STORAGE_SECRET_ACCESS_KEY") or os.environ.get("S3_SECRET_ACCESS_KEY")
        self.region = os.environ.get("STORAGE_REGION") or os.environ.get("S3_REGION_NAME", "auto")
        self.public_url_prefix = os.environ.get("STORAGE_PUBLIC_URL_PREFIX")

        # Fallback local cache
        self.local_cache_dir = settings.downloads_dir
        self.local_cache_dir.mkdir(parents=True, exist_ok=True)

        self._s3_client = None

    def _get_client(self):
        if self._s3_client is None:
            try:
                import boto3
                self._s3_client = boto3.client(
                    "s3",
                    endpoint_url=self.endpoint_url,
                    aws_access_key_id=self.access_key,
                    aws_secret_access_key=self.secret_key,
                    region_name=self.region,
                )
            except ImportError:
                logger.error("boto3 is not installed. S3StorageService cannot connect.")
                raise RuntimeError("boto3 is required for S3StorageService")
        return self._s3_client

    def save_file(self, filename: str, source_path: Path, content_type: str = "audio/mp4") -> str:
        client = self._get_client()
        client.upload_file(
            Filename=str(source_path),
            Bucket=self.bucket_name,
            Key=filename,
            ExtraArgs={"ContentType": content_type}
        )
        return self.get_download_url(filename)

    def get_file_path(self, filename: str) -> Optional[Path]:
        local = self.local_cache_dir / filename
        if local.exists():
            return local
        # If not cached locally, download to local cache
        try:
            client = self._get_client()
            client.download_file(self.bucket_name, filename, str(local))
            return local
        except Exception as e:
            logger.error(f"Failed to fetch {filename} from S3: {e}")
            return None

    def get_download_url(self, filename: str) -> str:
        if self.public_url_prefix:
            return f"{self.public_url_prefix.rstrip('/')}/{urllib.parse.quote(filename)}"
        try:
            client = self._get_client()
            # Generate pre-signed URL valid for 24 hours
            return client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": filename},
                ExpiresIn=86400
            )
        except Exception:
            return f"/api/download/{urllib.parse.quote(filename)}"

    def list_files(self) -> List[AudioFileItem]:
        client = self._get_client()
        files: List[AudioFileItem] = []
        try:
            res = client.list_objects_v2(Bucket=self.bucket_name)
            for item in res.get("Contents", []):
                key = item["Key"]
                size = item["Size"]
                ext = Path(key).suffix.lower().lstrip(".")
                mtime = item["LastModified"].timestamp()
                files.append(AudioFileItem(
                    filename=key,
                    title=Path(key).stem.replace("_", " "),
                    size_bytes=size,
                    extension=ext,
                    download_url=self.get_download_url(key),
                    sd_ready=True,
                    created_at=mtime
                ))
        except Exception as e:
            logger.error(f"Error listing files from S3: {e}")
        return files

    def delete_file(self, filename: str) -> bool:
        try:
            client = self._get_client()
            client.delete_object(Bucket=self.bucket_name, Key=filename)
            local = self.local_cache_dir / filename
            if local.exists():
                local.unlink()
            return True
        except Exception as e:
            logger.error(f"Error deleting {filename} from S3: {e}")
            return False

    def file_exists(self, filename: str) -> bool:
        try:
            client = self._get_client()
            client.head_object(Bucket=self.bucket_name, Key=filename)
            return True
        except Exception:
            return False


def get_storage_service() -> StorageService:
    backend_choice = os.environ.get("STORAGE_BACKEND", "local").lower()
    if backend_choice == "s3":
        return S3StorageService()
    return LocalStorageService()

# Global default storage service
storage_service = get_storage_service()
