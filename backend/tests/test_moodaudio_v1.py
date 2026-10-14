import io
import math
import os
import shutil
import struct
import sys
import tempfile
import time
import wave
from pathlib import Path
import unittest

# Ensure backend directory is in sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.models import (
    ProcessingMode,
    OutputFormat,
    SourceType,
    JobStage,
    RestorationSettings,
    JobDetailResponse
)
from app.services.audio_analyzer import audio_analyzer
from app.services.audio_restorer import audio_restorer
from app.services.audio_validator import audio_validator
from app.services.database import database_job_store
from app.services.job_worker import verify_audio_file_signature, job_worker

client = TestClient(app)

def create_synthetic_wav(path: Path, duration_sec: float = 2.0, freq: float = 440.0, peak_amp: float = 0.5):
    """Generate a clean uncompressed stereo sine wave for automated testing."""
    sample_rate = 44100
    num_samples = int(sample_rate * duration_sec)
    max_val = 32767 * peak_amp

    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(2)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)

        raw = bytearray()
        for i in range(num_samples):
            val = int(max_val * math.sin(2 * math.pi * freq * (i / sample_rate)))
            raw.extend(struct.pack("<hh", val, val))
        wav_file.writeframes(raw)


class TestMoodAudioStudioV1(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_dir = tempfile.TemporaryDirectory()
        cls.test_path = Path(cls.test_dir.name)
        cls.sample_wav = cls.test_path / "test_440hz.wav"
        create_synthetic_wav(cls.sample_wav, duration_sec=2.5, freq=440.0, peak_amp=0.5)

    @classmethod
    def tearDownClass(cls):
        cls.test_dir.cleanup()

    # 1. Capabilities endpoint verification
    def test_01_capabilities_endpoint(self):
        resp = client.get("/api/v1/capabilities")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["product_name"], settings.product_name)
        self.assertIn("m4a", data["supported_formats"])
        self.assertIn("flac", data["supported_formats"])

        # Atmos must be explicitly DISABLED
        modes = {m["id"]: m for m in data["modes"]}
        self.assertIn("dolby_atmos", modes)
        self.assertFalse(modes["dolby_atmos"]["enabled"])
        self.assertEqual(modes["dolby_atmos"]["status_badge"], "Coming Soon")
        self.assertIn("not yet validated", modes["dolby_atmos"]["notice"].lower())

        # Immersive Audio and Stereo Sound must be active
        self.assertTrue(modes["immersive_audio"]["enabled"])
        self.assertTrue(modes["stereo_sound"]["enabled"])
        self.assertTrue(modes["audio_enhancer"]["enabled"])

    # 2. Health endpoint verification
    def test_02_health_endpoint(self):
        resp = client.get("/api/v1/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "healthy")
        self.assertTrue(data["ffmpeg_available"])

    # 3. Binary Magic Bytes / File Signature Validation
    def test_03_file_signature_validation(self):
        # Valid WAV
        valid, fmt = verify_audio_file_signature(self.sample_wav)
        self.assertTrue(valid)
        self.assertEqual(fmt, "wav")

        # Fake audio (plain text with .wav extension)
        fake_file = self.test_path / "fake.wav"
        fake_file.write_text("Hello, I am a disguised text file, not audio!")
        valid_fake, msg = verify_audio_file_signature(fake_file)
        self.assertFalse(valid_fake)
        self.assertIn("Unrecognized", msg)

    # 4. Real Audio DSP Analysis
    def test_04_audio_analysis_metrics(self):
        report = audio_analyzer.analyze(self.sample_wav)
        self.assertEqual(report.channels, 2)
        self.assertEqual(report.sample_rate, 44100)
        self.assertAlmostEqual(report.duration_seconds, 2.5, delta=0.2)
        self.assertFalse(report.has_clipping)
        # 50% amplitude is ~ -6.0 dBFS
        self.assertAlmostEqual(report.peak_dbfs, -6.0, delta=1.5)
        # Verify genuine waveform peaks
        self.assertEqual(len(report.waveform_peaks), 100)
        self.assertTrue(all(0.0 <= p <= 1.0 for p in report.waveform_peaks))
        self.assertTrue(any(p > 0.0 for p in report.waveform_peaks))

    # 5. Pre-restoration and 4 Modes Processing
    def test_05_restorer_modes(self):
        analysis = audio_analyzer.analyze(self.sample_wav)
        restored_wav = self.test_path / "restored.wav"
        st = RestorationSettings()

        # Phase 1 Pre-restoration
        ok = audio_restorer.pre_restore(self.sample_wav, restored_wav, analysis, st)
        self.assertTrue(ok)
        self.assertTrue(restored_wav.exists())

        # Mode 1: Dolby Atmos must raise NotImplementedError
        with self.assertRaises(NotImplementedError):
            audio_restorer.process_mode(
                restored_wav,
                self.test_path / "out_atmos.m4a",
                ProcessingMode.DOLBY_ATMOS,
                OutputFormat.M4A,
                analysis,
                st
            )

        # Mode 2: Immersive Audio (Binaural)
        immersive_out = self.test_path / "out_immersive.m4a"
        ok_imm = audio_restorer.process_mode(
            restored_wav,
            immersive_out,
            ProcessingMode.IMMERSIVE_AUDIO,
            OutputFormat.M4A,
            analysis,
            st
        )
        self.assertTrue(ok_imm)
        self.assertTrue(immersive_out.exists())

        # Mode 3: Stereo Sound
        stereo_out = self.test_path / "out_stereo.wav"
        ok_stereo = audio_restorer.process_mode(
            restored_wav,
            stereo_out,
            ProcessingMode.STEREO_SOUND,
            OutputFormat.WAV,
            analysis,
            st
        )
        self.assertTrue(ok_stereo)
        self.assertTrue(stereo_out.exists())

        # Mode 4: Audio Enhancer
        enhancer_out = self.test_path / "out_enhancer.m4a"
        ok_enh = audio_restorer.process_mode(
            restored_wav,
            enhancer_out,
            ProcessingMode.AUDIO_ENHANCER,
            OutputFormat.M4A,
            analysis,
            st
        )
        self.assertTrue(ok_enh)
        self.assertTrue(enhancer_out.exists())

    # 6. Automated Output Validation Gate
    def test_06_audio_validation(self):
        # Validate good stereo file
        stereo_out = self.test_path / "out_stereo.wav"
        val = audio_validator.validate_output(
            output_file=stereo_out,
            expected_format=OutputFormat.WAV,
            expected_duration_seconds=2.5,
            expected_channels=2
        )
        self.assertTrue(val.is_valid)
        self.assertTrue(val.decodable)
        self.assertFalse(val.clipping_detected)

        # EchoNode hardware compatibility checks
        self.assertIsNotNone(val.echonode_compatibility)
        self.assertTrue(val.echonode_compatibility.is_compatible)
        self.assertTrue(val.echonode_compatibility.zero_video_streams)
        self.assertTrue(val.echonode_compatibility.supported_codec)
        self.assertTrue(val.echonode_compatibility.supported_sample_rate)
        self.assertTrue(val.echonode_compatibility.supported_channels)
        self.assertEqual(val.echonode_compatibility.transfer_method_available, "manual_sd_transfer")
        self.assertIn("Filename adheres to FAT32", " ".join(val.echonode_compatibility.hardware_notes))

        # Truncated or empty file rejection
        empty_out = self.test_path / "empty.wav"
        empty_out.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")
        val_bad = audio_validator.validate_output(
            output_file=empty_out,
            expected_format=OutputFormat.WAV,
            expected_duration_seconds=2.5,
            expected_channels=2
        )
        self.assertFalse(val_bad.is_valid)
        self.assertGreater(len(val_bad.issues), 0)

    # 7. End-to-End File Upload and Processing Job Lifecycle
    def test_07_v1_upload_and_preview_flow(self):
        with open(self.sample_wav, "rb") as f:
            resp = client.post(
                "/api/v1/jobs",
                data={
                    "source_type": "upload",
                    "processing_mode": "stereo_sound",
                    "output_format": "m4a",
                    "custom_title": "Automated_Test_Track"
                },
                files={"file": ("test_track.wav", f, "audio/wav")}
            )

        self.assertEqual(resp.status_code, 201)
        job_data = resp.json()
        job_id = job_data["job_id"]
        self.assertIsNotNone(job_id)
        self.assertEqual(job_data["status"], "queued")

        # Let the async pipeline worker process the job
        retries = 20
        final_job = None
        while retries > 0:
            time.sleep(0.5)
            chk = client.get(f"/api/v1/jobs/{job_id}")
            self.assertEqual(chk.status_code, 200)
            final_job = chk.json()
            if final_job["status"] in ("completed", "failed"):
                break
            retries -= 1

        self.assertIsNotNone(final_job)
        self.assertEqual(final_job["status"], "completed", f"Job failed: {final_job.get('error')}")
        self.assertIsNotNone(final_job["raw_analysis"])
        self.assertIsNotNone(final_job["validation_result"])
        self.assertTrue(final_job["validation_result"]["is_valid"])

        # Test preview endpoint
        prev_resp = client.get(f"/api/v1/jobs/{job_id}/preview?source=processed")
        self.assertEqual(prev_resp.status_code, 200)
        self.assertEqual(prev_resp.headers.get("content-type"), "audio/mp4")

        # Test download endpoint
        dl_resp = client.get(f"/api/v1/jobs/{job_id}/download")
        self.assertEqual(dl_resp.status_code, 200)
        self.assertIn("Automated_Test_Track", dl_resp.headers.get("content-disposition", ""))

    # 8. Cancel and Retry API Controls
    def test_08_cancel_and_retry_api(self):
        # Create a mock failed job directly in database
        failed_job = JobDetailResponse(
            job_id="failed-test-job-99",
            product_name=settings.product_name,
            source_type=SourceType.URL,
            source_url="https://youtube.com/watch?v=aqz-KE-bpKQ",
            processing_mode=ProcessingMode.STEREO_SOUND,
            requested_format=OutputFormat.M4A,
            status=JobStage.FAILED,
            current_stage="Failed simulated test",
            error="Simulated network failure",
            created_at=time.time(),
            updated_at=time.time(),
            can_retry=True
        )
        database_job_store.save_job(failed_job)

        # Retry the job
        retry_resp = client.post(f"/api/v1/jobs/{failed_job.job_id}/retry")
        self.assertEqual(retry_resp.status_code, 200)
        retry_data = retry_resp.json()
        self.assertEqual(retry_data["status"], "queued")
        self.assertEqual(retry_data["retry_count"], 1)

        # Cancel active job
        cancel_resp = client.post(f"/api/v1/jobs/{failed_job.job_id}/cancel")
        self.assertEqual(cancel_resp.status_code, 200)
        msg = cancel_resp.json()["message"].lower()
        self.assertTrue("cancel" in msg or "terminal" in msg)


if __name__ == "__main__":
    unittest.main()
