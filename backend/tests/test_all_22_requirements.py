import os
import sys
import time
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.config import sanitize_fat32_filename, settings
from app.services.extractor import (
    AudioExtractor,
    inspect_mp4_container_tracks,
    validate_youtube_url,
    MAX_ALLOWED_FILE_BYTES,
    extractor_service
)
from app.services.job_store import JobStore, sanitize_error_message
from app.services.storage import LocalStorageService, S3StorageService
from app.models import ExtractionRequest, JobStatus
from app.api.routes import (
    submit_extraction,
    get_job_status,
    get_all_jobs,
    list_audio_files,
    download_file,
    delete_file,
    proxy_to_worker,
    is_cookie_configured,
    is_po_token_provider_configured,
    is_persistent_storage,
    system_info
)
from fastapi import HTTPException


class TestAll22Requirements(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_dir = tempfile.TemporaryDirectory()
        cls.test_path = Path(cls.test_dir.name)
        cls.db_path = cls.test_path / "req22_test.db"
        cls.downloads_dir = cls.test_path / "downloads"
        cls.downloads_dir.mkdir(parents=True, exist_ok=True)

        cls.job_store = JobStore(db_path=cls.db_path)
        cls.storage = LocalStorageService(storage_dir=cls.downloads_dir)
        cls.extractor = AudioExtractor(downloads_dir=cls.downloads_dir)

    @classmethod
    def tearDownClass(cls):
        cls.job_store.close()
        cls.test_dir.cleanup()

    def setUp(self):
        self.job_store.clear()
        self.orig_env = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.orig_env)

    # 1. Invalid YouTube URL rejection
    def test_01_invalid_youtube_url(self):
        invalid_urls = [
            "https://evil.attacker.com/payload.mp4",
            "http://malicious.org/watch?v=123",
            "https://youtube.com/watch?v=123;rm -rf /",
            "https://youtube.com/watch?v=123|whoami",
            "javascript:alert(1)",
            "ftp://youtube.com/video",
            "not_even_a_url"
        ]
        for url in invalid_urls:
            self.assertFalse(validate_youtube_url(url), f"Should reject invalid URL: {url}")

        valid_urls = [
            "https://www.youtube.com/watch?v=aqz-KE-bpKQ",
            "https://youtu.be/aqz-KE-bpKQ",
            "https://m.youtube.com/watch?v=aqz-KE-bpKQ",
            "https://music.youtube.com/watch?v=aqz-KE-bpKQ"
        ]
        for url in valid_urls:
            self.assertTrue(validate_youtube_url(url), f"Should accept valid URL: {url}")

    # 2. Job creation
    def test_02_job_creation(self):
        job = JobStatus(
            job_id="job-req-02",
            url="https://www.youtube.com/watch?v=aqz-KE-bpKQ",
            status="queued",
            progress=0.0,
            created_at=time.time()
        )
        self.job_store.create_job(job)
        stored = self.job_store.get_job("job-req-02")
        self.assertIsNotNone(stored)
        self.assertEqual(stored.job_id, "job-req-02")
        self.assertEqual(stored.status, "queued")
        self.assertEqual(stored.progress, 0.0)

    # 3. Queued -> running/processing
    def test_03_queued_to_running(self):
        job = JobStatus(
            job_id="job-req-03",
            url="https://www.youtube.com/watch?v=aqz-KE-bpKQ",
            status="queued",
            progress=0.0,
            created_at=time.time()
        )
        self.job_store.create_job(job)
        self.job_store.update_job("job-req-03", status="processing", progress=25.0)

        updated = self.job_store.get_job("job-req-03")
        self.assertEqual(updated.status, "processing")
        self.assertEqual(updated.progress, 25.0)

    # 4. Running -> completed
    def test_04_running_to_completed(self):
        job = JobStatus(
            job_id="job-req-04",
            url="https://www.youtube.com/watch?v=aqz-KE-bpKQ",
            status="processing",
            progress=50.0,
            created_at=time.time()
        )
        self.job_store.create_job(job)
        self.job_store.update_job(
            "job-req-04",
            status="completed",
            progress=100.0,
            filename="output.m4a",
            download_url="/api/download/output.m4a",
            completed_at=time.time()
        )

        completed = self.job_store.get_job("job-req-04")
        self.assertEqual(completed.status, "completed")
        self.assertEqual(completed.progress, 100.0)
        self.assertEqual(completed.filename, "output.m4a")
        self.assertEqual(completed.download_url, "/api/download/output.m4a")

    # 5. Running -> failed
    def test_05_running_to_failed(self):
        job = JobStatus(
            job_id="job-req-05",
            url="https://www.youtube.com/watch?v=aqz-KE-bpKQ",
            status="processing",
            progress=50.0,
            created_at=time.time()
        )
        self.job_store.create_job(job)
        self.job_store.update_job("job-req-05", status="failed", error="BotGuard challenge failed")

        failed = self.job_store.get_job("job-req-05")
        self.assertEqual(failed.status, "failed")
        self.assertIn("BotGuard challenge failed", failed.error)

    # 6. Sanitized error scrubbing
    def test_06_sanitized_error(self):
        leaky_error = (
            "Error: /Users/secretuser/project/cookies.txt auth=super_secret_token_12345 "
            "cookiefile=/etc/secrets.txt Bearer my_jwt_token_here "
            ".youtube.com TRUE / FALSE 1789783217 SAPISID=very_secret_cookie_val"
        )
        sanitized = sanitize_error_message(leaky_error)
        self.assertNotIn("secretuser", sanitized)
        self.assertNotIn("super_secret_token_12345", sanitized)
        self.assertNotIn("my_jwt_token_here", sanitized)
        self.assertNotIn("very_secret_cookie_val", sanitized)
        self.assertIn("[REDACTED", sanitized)

    # 7. Storage listing
    def test_07_storage_listing(self):
        track1 = self.downloads_dir / "track_alpha.m4a"
        track1.write_bytes(b"\x00\x00\x00\x18ftypM4A ")
        track2 = self.downloads_dir / "track_beta.mp3"
        track2.write_bytes(b"ID3\x03\x00\x00\x00")

        files = self.storage.list_files()
        filenames = [f.filename for f in files]
        self.assertIn("track_alpha.m4a", filenames)
        self.assertIn("track_beta.mp3", filenames)

    # 8. Storage retrieval
    def test_08_storage_retrieval(self):
        track = self.downloads_dir / "retrieval_test.m4a"
        track.write_bytes(b"\x00\x00\x00\x18ftypM4A ")

        p = self.storage.get_file_path("retrieval_test.m4a")
        self.assertIsNotNone(p)
        self.assertTrue(p.exists())
        self.assertTrue(self.storage.file_exists("retrieval_test.m4a"))

    # 9. Storage deletion
    def test_09_storage_deletion(self):
        track = self.downloads_dir / "delete_target.m4a"
        track.write_bytes(b"temp data")
        self.assertTrue(self.storage.file_exists("delete_target.m4a"))

        deleted = self.storage.delete_file("delete_target.m4a")
        self.assertTrue(deleted)
        self.assertFalse(self.storage.file_exists("delete_target.m4a"))

    # 10. Path traversal rejection
    def test_10_path_traversal_rejection(self):
        traversal_attempts = [
            "../../etc/passwd",
            "../../../secret.env",
            "..\\..\\windows\\system32",
            "/etc/shadow"
        ]
        for bad_path in traversal_attempts:
            resolved = self.storage.get_file_path(bad_path)
            self.assertIsNone(resolved, f"Path traversal attempt must be rejected: {bad_path}")

    # 11. Filename sanitization
    def test_11_filename_sanitization(self):
        unsafe_name = 'Track: "Episode 1" * 2026? <Uncut> | Audio / Part\\1'
        safe_name = sanitize_fat32_filename(unsafe_name, max_length=60)
        self.assertLessEqual(len(safe_name), 60)
        for bad_char in r'/\:*?"<>|':
            self.assertNotIn(bad_char, safe_name)

    # 12. 60 MB limit enforcement
    def test_12_60mb_limit(self):
        self.assertEqual(MAX_ALLOWED_FILE_BYTES, 60 * 1024 * 1024)
        oversized = 61 * 1024 * 1024
        self.assertGreater(oversized, MAX_ALLOWED_FILE_BYTES)

    # 13. Video-track rejection
    def test_13_video_track_rejection(self):
        # Create container atom with a 'vide' handler type
        video_payload = b"\x00\x00\x00\x00\x00\x00\x00\x00vide\x00\x00\x00\x00\x00\x00\x00\x00"
        hdlr_video = struct.pack(">I", 8 + len(video_payload)) + b"hdlr" + video_payload
        moov_video = struct.pack(">I", 8 + len(hdlr_video)) + b"moov" + hdlr_video
        fake_video_file = self.downloads_dir / "contain_video.m4a"
        fake_video_file.write_bytes(b"\x00\x00\x00\x18ftypM4A " + moov_video)

        audio_tracks, video_tracks = inspect_mp4_container_tracks(fake_video_file)
        self.assertGreater(video_tracks, 0, "Video track must be detected")

    # 14. Worker unavailable behavior (503)
    def test_14_worker_unavailable_behavior(self):
        os.environ["WORKER_URL"] = "http://127.0.0.1:59999"
        os.environ["ECHONODE_WORKER_TOKEN"] = "test-token"
        with self.assertRaises(HTTPException) as ctx:
            proxy_to_worker("GET", "/api/jobs")
        self.assertEqual(ctx.exception.status_code, 503)
        self.assertIn("Persistent extraction worker is currently unreachable", ctx.exception.detail)

    # 15. Missing WORKER_URL behavior in production (503)
    async def test_15_missing_worker_url_behavior(self):
        os.environ["VERCEL"] = "1"
        os.environ["WORKER_URL"] = ""
        os.environ["EXTRACTION_MODE"] = "worker"

        req = ExtractionRequest(url="https://www.youtube.com/watch?v=aqz-KE-bpKQ")
        with self.assertRaises(HTTPException) as ctx:
            await submit_extraction(req)

        self.assertEqual(ctx.exception.status_code, 503)
        self.assertEqual(ctx.exception.detail, "Extraction worker is not configured")

    # 16. Configured worker behavior
    @patch("urllib.request.urlopen")
    def test_16_configured_worker_behavior(self, mock_urlopen):
        os.environ["WORKER_URL"] = "http://mock-worker:8001"
        os.environ["ECHONODE_WORKER_TOKEN"] = "test-token"
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"job_id": "remote-123", "status": "queued", "message": "queued on worker"}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = proxy_to_worker("POST", "/api/extract", {"url": "https://www.youtube.com/watch?v=aqz-KE-bpKQ"})
        self.assertEqual(result["job_id"], "remote-123")
        self.assertEqual(result["status"], "queued")

    # 17. Cookie configuration detection
    def test_17_cookie_configuration_detection(self):
        os.environ.pop("YTDLP_COOKIES", None)
        os.environ.pop("YTDLP_COOKIES_PATH", None)
        self.assertFalse(is_cookie_configured())

        os.environ["YTDLP_COOKIES"] = "# Netscape HTTP Cookie File"
        self.assertTrue(is_cookie_configured())

    # 18. PO-token-provider configuration detection
    def test_18_po_token_provider_configuration_detection(self):
        # bgutil-ytdlp-pot-provider is installed in .venv
        self.assertTrue(is_po_token_provider_configured())

    # 19. FFmpeg detection
    def test_19_ffmpeg_detection(self):
        import shutil
        expected = shutil.which("ffmpeg") is not None
        self.assertEqual(extractor_service.has_ffmpeg, expected)

    # 20. JobStore persistence
    def test_20_jobstore_persistence(self):
        job = JobStatus(
            job_id="persist-01",
            url="https://youtu.be/persistent",
            status="completed",
            progress=100.0,
            filename="saved_track.m4a",
            created_at=time.time(),
            completed_at=time.time()
        )
        self.job_store.create_job(job)
        self.job_store.close()

        reopened_store = JobStore(db_path=self.db_path)
        retrieved = reopened_store.get_job("persist-01")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.status, "completed")
        self.assertEqual(retrieved.filename, "saved_track.m4a")
        reopened_store.close()

    # 21. Worker restart recovery
    def test_21_worker_restart_recovery(self):
        # Write 3 jobs
        for i in range(3):
            self.job_store.create_job(JobStatus(
                job_id=f"restart-job-{i}",
                url=f"https://youtu.be/job_{i}",
                status="completed" if i == 0 else "queued",
                created_at=time.time() + i
            ))

        self.job_store.close()

        restarted_store = JobStore(db_path=self.db_path)
        jobs = restarted_store.list_jobs()
        job_ids = [j.job_id for j in jobs]
        for i in range(3):
            self.assertIn(f"restart-job-{i}", job_ids)
        restarted_store.close()

    # 22. S3/R2 storage tests if backend is enabled
    @patch("boto3.client")
    def test_22_s3_storage_tests(self, mock_boto_client):
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        mock_s3.generate_presigned_url.return_value = "https://s3.amazonaws.com/echonode/track.m4a?signed=1"
        mock_s3.list_objects_v2.return_value = {
            "Contents": [
                {
                    "Key": "s3_track.m4a",
                    "Size": 1048576,
                    "LastModified": MagicMock(timestamp=lambda: 1700000000.0)
                }
            ]
        }

        os.environ["STORAGE_BACKEND"] = "s3"
        os.environ["S3_BUCKET_NAME"] = "test-bucket"
        s3_service = S3StorageService()

        # Test save
        dummy_file = self.downloads_dir / "s3_test.m4a"
        dummy_file.write_bytes(b"test-audio-bytes")
        url = s3_service.save_file("s3_track.m4a", dummy_file)
        self.assertIn("https://s3.amazonaws.com", url)
        mock_s3.upload_file.assert_called_once()

        # Test list
        items = s3_service.list_files()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].filename, "s3_track.m4a")

        # Test delete
        deleted = s3_service.delete_file("s3_track.m4a")
        self.assertTrue(deleted)
        mock_s3.delete_object.assert_called_with(Bucket="test-bucket", Key="s3_track.m4a")


if __name__ == "__main__":
    unittest.main()
