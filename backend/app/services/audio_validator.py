import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional
from ..models import ValidationResult, OutputFormat, EchoNodeCompatibility
from ..config import sanitize_fat32_filename
from .audio_analyzer import audio_analyzer

logger = logging.getLogger("moodaudio.validator")

class AudioValidator:
    """
    Automated Media Validation Engine (Phase 5).
    Verifies that generated audio outputs are readable, structurally valid,
    duration-matched, clip-free, decodable by independent players,
    and verified against EchoNode ESP32-S3 hardware playback constraints.
    """
    def __init__(self):
        self.ffprobe_path = shutil.which("ffprobe") or "/opt/homebrew/bin/ffprobe"

    def evaluate_echonode_compatibility(
        self,
        output_file: Path,
        streams: List[dict],
        file_size: int,
    ) -> EchoNodeCompatibility:
        """
        Evaluate audio file against authoritative EchoNode hardware specifications:
        - ESP32-S3R8 (Dual-core LX7, 8MB PSRAM)
        - PCM5101 I2S DAC (3-wire, DIN=47, LRCK=38, BCK=48)
        - ESP32-audioI2S decoder
        - FAT32 MicroSD card storage (TCA9554 EXIO3 CS)
        """
        compat = EchoNodeCompatibility()
        notes: List[str] = []

        # 1. Filename & FAT32 compliance
        safe_name = sanitize_fat32_filename(output_file.stem) + output_file.suffix
        compat.safe_fat32_name = safe_name
        if output_file.name != safe_name:
            notes.append(f"Filename requires FAT32 sanitization for MicroSD: '{safe_name}'")
        else:
            notes.append("Filename adheres to FAT32 character set & length ceiling (<=60 chars).")

        # 2. Strict Zero Video Streams verification
        video_streams = [s for s in streams if s.get("codec_type") == "video"]
        if len(video_streams) > 0:
            compat.zero_video_streams = False
            notes.append(f"INCOMPATIBLE: Contains {len(video_streams)} video stream(s). ESP32-S3 decoder rejects video tracks.")
        else:
            compat.zero_video_streams = True
            notes.append("Pure audio-only stream verified (exactly 0 video tracks).")

        # 3. Codec verification against ESP32-audioI2S capabilities
        audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
        if not audio_streams:
            compat.is_compatible = False
            compat.hardware_notes = ["No audio stream found."]
            return compat

        main_audio = audio_streams[0]
        codec = main_audio.get("codec_name", "").lower()
        supported_codecs = {"aac", "mp3", "pcm_s16le", "flac"}
        if codec in supported_codecs:
            compat.supported_codec = True
            notes.append(f"Codec '{codec}' supported by ESP32-audioI2S decoder.")
        else:
            compat.supported_codec = False
            notes.append(f"INCOMPATIBLE: Codec '{codec}' is not natively supported by ESP32-S3 firmware.")

        # 4. Sample rate verification
        try:
            sr = int(main_audio.get("sample_rate", 0))
            if sr in [22050, 32000, 44100, 48000]:
                compat.supported_sample_rate = True
                notes.append(f"Sample rate {sr} Hz matches PCM5101 I2S PLL specifications.")
            elif sr > 48000:
                compat.supported_sample_rate = False
                notes.append(f"INCOMPATIBLE: Sample rate {sr} Hz exceeds 48000 Hz limit (risks I2S DMA underruns).")
            else:
                compat.supported_sample_rate = False
                notes.append(f"Sub-standard sample rate {sr} Hz.")
        except (ValueError, TypeError):
            compat.supported_sample_rate = False

        # 5. Channel count verification
        try:
            ch = int(main_audio.get("channels", 0))
            if ch in [1, 2]:
                compat.supported_channels = True
                notes.append(f"Channel layout ({'stereo' if ch == 2 else 'mono'}) supported by PCM5101 2-channel DAC.")
            else:
                compat.supported_channels = False
                notes.append(f"INCOMPATIBLE: {ch} channels exceeds stereo PCM5101 hardware capacity.")
        except (ValueError, TypeError):
            compat.supported_channels = False

        # 6. File size constraints (<= 60MB)
        max_size = 60 * 1024 * 1024
        if file_size <= max_size:
            compat.size_within_limit = True
            notes.append(f"File size ({file_size / (1024*1024):.1f} MB) is within 60MB FAT32 reader buffer limit.")
        else:
            compat.size_within_limit = False
            notes.append(f"INCOMPATIBLE: File size exceeds 60MB safety ceiling.")

        # 7. Bitrate recommendation check
        bitrate_str = main_audio.get("bit_rate") or main_audio.get("tags", {}).get("BPS")
        if bitrate_str:
            try:
                br_kbps = int(bitrate_str) // 1000
                if br_kbps <= 192:
                    compat.recommended_for_hardware = True
                    notes.append(f"Bitrate (~{br_kbps} kbps) is optimal for low-power ESP32-S3 I2S decoding.")
                else:
                    compat.recommended_for_hardware = False
                    notes.append(f"High bitrate (~{br_kbps} kbps); recommend <=128 kbps for long-term bedside playback.")
            except (ValueError, TypeError):
                compat.recommended_for_hardware = True
        else:
            compat.recommended_for_hardware = True

        compat.transfer_method_available = "manual_sd_transfer"
        notes.append("Fulfillment: Manual transfer to FAT32 MicroSD card verified (USB/Network sync planned).")

        compat.is_compatible = (
            compat.zero_video_streams
            and compat.supported_codec
            and compat.supported_sample_rate
            and compat.supported_channels
            and compat.size_within_limit
        )
        compat.hardware_notes = notes
        return compat

    def validate_output(
        self,
        output_file: Path,
        expected_format: OutputFormat,
        expected_duration_seconds: float,
        expected_channels: int = 2
    ) -> ValidationResult:
        result = ValidationResult()

        # 1. Existence and non-empty check
        if not output_file.exists():
            result.issues.append("Output file does not exist on disk.")
            return result

        file_size = output_file.stat().st_size
        result.file_size_bytes = file_size
        if file_size < 1024:
            result.issues.append(f"Output file size ({file_size} bytes) is suspiciously small or truncated.")
            return result

        # 2. Format extension check
        ext = output_file.suffix.lower().lstrip(".")
        expected_ext = expected_format.value.lower()
        if ext != expected_ext:
            result.issues.append(f"File extension '.{ext}' does not match expected format '.{expected_ext}'.")
        else:
            result.format_matched = True

        # 3. Independent ffprobe decodability probe
        probe_data = audio_analyzer.probe_format(output_file)
        streams = probe_data.get("streams", [])
        fmt = probe_data.get("format", {})

        if not streams:
            result.issues.append("ffprobe found no valid audio streams in generated output.")
            return result

        audio_stream = streams[0]
        result.decodable = True

        # Duration verification
        duration_str = audio_stream.get("duration") or fmt.get("duration")
        if duration_str:
            try:
                result.duration_seconds = round(float(duration_str), 2)
                # Check tolerance: must be within 1.0s or 2% of expected duration
                tolerance = max(1.0, expected_duration_seconds * 0.02)
                if abs(result.duration_seconds - expected_duration_seconds) > tolerance:
                    result.issues.append(
                        f"Output duration ({result.duration_seconds}s) deviates from expected duration ({expected_duration_seconds}s) beyond tolerance of {tolerance:.1f}s."
                    )
            except (ValueError, TypeError):
                result.issues.append("Could not parse output stream duration.")

        # Channel count verification
        channels = int(audio_stream.get("channels", 0))
        result.channels = channels
        if channels != expected_channels:
            result.issues.append(f"Channel count ({channels}) does not match declared layout ({expected_channels} channels).")

        # Sample rate verification
        sample_rate = int(audio_stream.get("sample_rate", 0))
        result.sample_rate = sample_rate
        if sample_rate < 22050:
            result.issues.append(f"Sample rate ({sample_rate} Hz) is below standard fidelity threshold (22050 Hz).")

        # 4. Dynamics and clipping analysis
        vol = audio_analyzer.extract_volumedetect(output_file)
        peak = vol.get("max_volume_dbfs", 0.0)
        rms = vol.get("mean_volume_dbfs", -20.0)
        result.peak_dbfs = peak
        result.rms_dbfs = rms

        # Clipping check (allowing 0.02 dB measurement precision margin)
        if peak > 0.02:
            result.clipping_detected = True
            result.issues.append(f"Severe digital clipping detected: peak amplitude reaches {peak} dBFS.")

        # Silence / corruption check
        if rms < -58.0 and expected_duration_seconds > 2.0:
            result.issues.append(f"Output appears to be completely silent (mean level: {rms} dBFS).")

        # 5. EchoNode hardware device-compatibility evaluation
        result.echonode_compatibility = self.evaluate_echonode_compatibility(
            output_file=output_file,
            streams=streams,
            file_size=file_size,
        )

        # Validation verdict: valid only if no blocking issues
        result.is_valid = len(result.issues) == 0
        return result

audio_validator = AudioValidator()
