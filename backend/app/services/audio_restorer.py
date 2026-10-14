import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from ..models import (
    ProcessingMode,
    OutputFormat,
    RestorationSettings,
    AudioAnalysisReport
)

logger = logging.getLogger("moodaudio.restorer")

class AudioRestorer:
    """
    Audio Restoration & Spatial Processing Engine.
    Implements conservative pre-restoration, genuine binaural immersive audio,
    fidelity-preserving stereo sound, and adaptive speech/music enhancement.
    Never fabricates Atmos metadata or unverified quality claims.
    """
    def __init__(self):
        self.ffmpeg_path = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"

    def _build_format_args(self, output_format: OutputFormat) -> List[str]:
        """Return FFmpeg encoding arguments for requested output format."""
        if output_format == OutputFormat.M4A:
            return ["-c:a", "aac", "-b:a", "256k"]
        elif output_format == OutputFormat.MP3:
            return ["-c:a", "libmp3lame", "-b:a", "320k"]
        elif output_format == OutputFormat.FLAC:
            return ["-c:a", "flac"]
        elif output_format == OutputFormat.WAV:
            return ["-c:a", "pcm_s16le"]
        return ["-c:a", "aac", "-b:a", "256k"]

    def pre_restore(
        self,
        input_file: Path,
        output_file: Path,
        analysis: AudioAnalysisReport,
        settings: RestorationSettings
    ) -> bool:
        """
        Phase 1: Pre-restoration stage.
        Conservative DC offset removal, SNR-aware denoising, and peak headroom control.
        """
        filter_chain = []

        # 1. Sub-bass DC offset removal
        hp_freq = max(15, min(60, settings.highpass_cutoff_hz or 20))
        filter_chain.append(f"highpass=f={hp_freq}")

        # 2. Conservative Denoising (only if noise detected and SNR warrants it)
        # Avoid destroying clean recordings with unnecessary spectral noise subtraction
        noise_floor = analysis.noise_floor_dbfs or -50.0
        if settings.noise_reduction_enabled and noise_floor > -55.0:
            # Conservative noise reduction (capped between 6dB and 16dB)
            nr_db = min(16.0, max(6.0, settings.noise_reduction_level_db))
            filter_chain.append(f"afftdn=nr={nr_db}:nf={noise_floor}:tn=1")

        # 3. Channel Balance Correction if significant imbalance (> 1.5 dB)
        if analysis.channel_imbalance_db > 1.5 and analysis.channels == 2:
            # Mild leveling towards center without mono collapse
            filter_chain.append("pan=stereo|c0=0.9*c0+0.1*c1|c1=0.1*c0+0.9*c1")

        # 4. Conservative True-Peak Headroom Limiter to prevent clipping
        ceiling = min(-0.5, max(-3.0, settings.true_peak_ceiling_db))
        filter_chain.append(f"alimiter=limit={ceiling}dB:attack=5:release=50:asc=1")

        cmd = [
            self.ffmpeg_path,
            "-y",
            "-hide_banner",
            "-i", str(input_file),
            "-af", ",".join(filter_chain),
            "-c:a", "pcm_s24le",
            "-vn", "-sn", "-dn",
            str(output_file)
        ]

        try:
            logger.info(f"Running pre-restoration: {','.join(filter_chain)}")
            subprocess.run(cmd, check=True, capture_output=True, timeout=180)
            return True
        except Exception as e:
            logger.error(f"Pre-restoration failed: {e}")
            # Fallback: copy untouched source
            shutil.copy2(input_file, output_file)
            return False

    def process_mode(
        self,
        working_file: Path,
        output_file: Path,
        mode: ProcessingMode,
        output_format: OutputFormat,
        analysis: AudioAnalysisReport,
        settings: RestorationSettings
    ) -> bool:
        """
        Execute selected mode DSP processing and render final output format.
        """
        # Mode 1: Dolby Atmos — Disabled by design until certified workflow is validated
        if mode == ProcessingMode.DOLBY_ATMOS:
            raise NotImplementedError(
                "Coming soon — compatible Dolby Atmos authoring workflow not yet validated. "
                "MoodAudio Studio strictly avoids fabricating object metadata or renaming multichannel PCM to Atmos."
            )

        filter_chain = []

        # Mode 2: Immersive Audio (Binaural Spatial Sound)
        if mode == ProcessingMode.IMMERSIVE_AUDIO:
            intensity = settings.spatial_intensity.lower()
            if intensity == "subtle":
                # Mild binaural crossfeed to reduce headphone fatigue
                filter_chain.append("pan=stereo|c0=0.88*c0+0.12*c1|c1=0.12*c0+0.88*c1")
                filter_chain.append("stereowiden=crossfeed=0.2:feedback=0.1")
            elif intensity == "wide":
                # Expansive binaural stage with gentle early acoustic reflections
                filter_chain.append("pan=stereo|c0=0.82*c0+0.18*c1|c1=0.18*c0+0.82*c1")
                filter_chain.append("stereowiden=crossfeed=0.45:feedback=0.2")
                filter_chain.append("aecho=0.8:0.88:25|45:0.12|0.06")
            else:  # moderate default
                filter_chain.append("pan=stereo|c0=0.85*c0+0.15*c1|c1=0.15*c0+0.85*c1")
                filter_chain.append("stereowiden=crossfeed=0.32:feedback=0.15")
                filter_chain.append("aecho=0.8:0.88:20:0.08")

            # Output peak limiter
            filter_chain.append(f"alimiter=limit={settings.true_peak_ceiling_db}dB:attack=5:release=50:asc=1")

        # Mode 3: Stereo Sound (Fidelity-first mastering)
        elif mode == ProcessingMode.STEREO_SOUND:
            if settings.lossless_stream_copy and output_format == OutputFormat.M4A and analysis.codec == "aac":
                # Lossless direct stream copy when format matches
                cmd = [
                    self.ffmpeg_path,
                    "-y",
                    "-hide_banner",
                    "-i", str(working_file),
                    "-c:a", "copy",
                    "-vn", "-sn", "-dn",
                    str(output_file)
                ]
                try:
                    subprocess.run(cmd, check=True, capture_output=True, timeout=60)
                    return True
                except Exception:
                    pass

            # High-fidelity mastering: transparent true-peak limiting & sample-rate preservation
            filter_chain.append(f"alimiter=limit={settings.true_peak_ceiling_db}dB:attack=4:release=40:asc=1")

        # Mode 4: Audio Enhancer (Adaptive conservative enhancement)
        elif mode == ProcessingMode.AUDIO_ENHANCER:
            profile = settings.enhancer_profile.lower()
            if profile == "auto":
                profile = analysis.detected_content_type

            if profile == "speech":
                # Speech enhancement: Clean speech fundamental, de-mud, clarity presence
                filter_chain.append("highpass=f=80")
                filter_chain.append("equalizer=f=250:t=q:w=1.2:g=-1.5")  # de-box / de-mud
                filter_chain.append("equalizer=f=3200:t=q:w=1.0:g=2.2") # articulation / dialog clarity
                filter_chain.append("equalizer=f=6500:t=q:w=1.5:g=-1.0") # mild sibilance control
                filter_chain.append("compand=attacks=0.03:decays=0.25:points=-60/-60|-28/-20|-14/-11|0/-2")
            else:
                # Music enhancement: Harmonic punch, warm low-end, silky top air
                filter_chain.append("highpass=f=24")
                filter_chain.append("equalizer=f=80:t=q:w=0.9:g=1.2")   # warm low punch
                filter_chain.append("equalizer=f=350:t=q:w=1.5:g=-1.0")  # cleanup mud
                filter_chain.append("equalizer=f=12500:t=q:w=0.7:g=1.4") # gentle air sheen
                filter_chain.append("alimiter=limit=-1.0dB:attack=5:release=50:asc=1")

            # Final loudness normalization if requested
            if settings.loudness_normalization:
                target_lufs = max(-24.0, min(-9.0, settings.target_lufs))
                filter_chain.append(f"loudnorm=I={target_lufs}:TP={settings.true_peak_ceiling_db}:LRA=11")

        # Build final encoding command
        format_args = self._build_format_args(output_format)
        cmd = [
            self.ffmpeg_path,
            "-y",
            "-hide_banner",
            "-i", str(working_file)
        ]

        if filter_chain:
            cmd.extend(["-af", ",".join(filter_chain)])

        cmd.extend(format_args)
        cmd.extend(["-vn", "-sn", "-dn", str(output_file)])

        try:
            logger.info(f"Rendering final output ({mode.value} -> {output_format.value})")
            subprocess.run(cmd, check=True, capture_output=True, timeout=180)
            return True
        except Exception as e:
            logger.error(f"Mode rendering failed for {mode.value}: {e}")
            # Fallback to standard conversion
            fallback_cmd = [
                self.ffmpeg_path,
                "-y",
                "-hide_banner",
                "-i", str(working_file)
            ] + format_args + ["-vn", str(output_file)]
            subprocess.run(fallback_cmd, check=True, capture_output=True, timeout=60)
            return False

    def generate_preview(
        self,
        source_file: Path,
        preview_file: Path,
        target_lufs: float = -16.0
    ) -> bool:
        """
        Generate loudness-matched 30-second preview (AAC in MP4 container)
        so A/B comparisons between original and processed audio are perceptually fair.
        """
        cmd = [
            self.ffmpeg_path,
            "-y",
            "-hide_banner",
            "-i", str(source_file),
            "-t", "30",
            "-af", f"loudnorm=I={target_lufs}:TP=-1.0:LRA=11",
            "-c:a", "aac",
            "-b:a", "192k",
            "-vn", "-sn", "-dn",
            str(preview_file)
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=45)
            return True
        except Exception as e:
            logger.warning(f"Preview generation failed on {source_file.name}: {e}")
            return False

audio_restorer = AudioRestorer()
