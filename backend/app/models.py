from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, HttpUrl, Field

# Legacy EchoNode models (preserved for backward compatibility and test stability)
class ExtractionRequest(BaseModel):
    url: str = Field(..., description="YouTube URL to extract audio from")
    format_preference: Optional[str] = Field("m4a", description="Target audio format ('m4a' or 'mp3')")
    custom_title: Optional[str] = Field(None, description="Optional custom filename override")

class JobStatus(BaseModel):
    job_id: str
    url: str
    status: str = Field(..., description="'queued' | 'processing' | 'downloading' | 'completed' | 'failed'")
    progress: float = 0.0
    title: Optional[str] = None
    filename: Optional[str] = None
    download_url: Optional[str] = None
    file_size_bytes: Optional[int] = None
    duration_seconds: Optional[float] = None
    error: Optional[str] = None
    created_at: float
    completed_at: Optional[float] = None

class AudioFileItem(BaseModel):
    filename: str
    title: str
    size_bytes: int
    duration_seconds: Optional[float] = None
    extension: str
    download_url: str
    sd_ready: bool = True
    created_at: float

class ExtractionResponse(BaseModel):
    job_id: str
    message: str
    status: str

class SyncRequest(BaseModel):
    target_path: str = Field(..., description="Target MicroSD mount path (e.g. /Volumes/ECHONODE)")

class SyncResponse(BaseModel):
    copied_count: int
    failed_count: int
    target_path: str
    message: str


# MoodAudio Studio Audio Engineering Enums & Schemas
class ProcessingMode(str, Enum):
    DOLBY_ATMOS = "dolby_atmos"
    IMMERSIVE_AUDIO = "immersive_audio"
    STEREO_SOUND = "stereo_sound"
    AUDIO_ENHANCER = "audio_enhancer"

class OutputFormat(str, Enum):
    M4A = "m4a"
    MP3 = "mp3"
    FLAC = "flac"
    WAV = "wav"

class JobStage(str, Enum):
    QUEUED = "queued"
    VALIDATING = "validating"
    EXTRACTING = "extracting"
    ANALYZING = "analyzing"
    RESTORING = "restoring"
    RENDERING = "rendering"
    VALIDATING_OUTPUT = "validating_output"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class SourceType(str, Enum):
    UPLOAD = "upload"
    URL = "url"

class AudioAnalysisReport(BaseModel):
    duration_seconds: float = 0.0
    sample_rate: int = 44100
    channels: int = 2
    channel_layout: str = "stereo"
    codec: str = "aac"
    bit_rate_kbps: Optional[int] = None
    peak_dbfs: float = 0.0
    rms_dbfs: float = -20.0
    integrated_lufs: Optional[float] = None
    loudness_range_lra: Optional[float] = None
    true_peak_dbtp: Optional[float] = None
    dc_offset: float = 0.0
    channel_imbalance_db: float = 0.0
    clipping_samples: int = 0
    has_clipping: bool = False
    silence_detected: bool = False
    noise_floor_dbfs: Optional[float] = None
    detected_content_type: str = "clean"
    waveform_peaks: List[float] = Field(default_factory=list, description="Real sampled peaks (0.0 to 1.0) for waveform visualization")

class RestorationSettings(BaseModel):
    highpass_cutoff_hz: int = Field(20, description="High-pass filter cutoff to remove sub-bass DC offset")
    noise_reduction_enabled: bool = Field(True, description="Enable conservative spectral denoising if noise is detected")
    noise_reduction_level_db: float = Field(12.0, ge=3.0, le=24.0, description="Conservative noise reduction intensity in dB")
    declick_enabled: bool = Field(False, description="Enable gentle de-click / artifact reduction")
    loudness_normalization: bool = Field(True, description="Normalize to standard EBU R128 loudness")
    target_lufs: float = Field(-14.0, ge=-24.0, le=-9.0, description="Target integrated loudness in LUFS")
    true_peak_ceiling_db: float = Field(-1.0, ge=-3.0, le=-0.1, description="True peak ceiling in dBTP to prevent inter-sample clipping")
    spatial_intensity: str = Field("moderate", description="Spatial width intensity: subtle, moderate, wide")
    enhancer_profile: str = Field("auto", description="Enhancer profile: auto, speech, music")
    lossless_stream_copy: bool = Field(False, description="Preserve untouched stream without re-encoding if format matches")

class EchoNodeCompatibility(BaseModel):
    is_compatible: bool = False
    safe_fat32_name: str = ""
    zero_video_streams: bool = True
    supported_codec: bool = False
    supported_sample_rate: bool = False
    supported_channels: bool = False
    size_within_limit: bool = True
    recommended_for_hardware: bool = False
    transfer_method_available: str = "manual_sd_transfer"
    hardware_notes: List[str] = Field(default_factory=list)

class ValidationResult(BaseModel):
    is_valid: bool = False
    file_size_bytes: int = 0
    duration_seconds: float = 0.0
    channels: int = 2
    sample_rate: int = 44100
    format_matched: bool = False
    clipping_detected: bool = False
    peak_dbfs: float = 0.0
    rms_dbfs: float = -20.0
    decodable: bool = False
    issues: List[str] = Field(default_factory=list)
    echonode_compatibility: Optional[EchoNodeCompatibility] = None

class JobCreateRequest(BaseModel):
    source_type: SourceType = SourceType.URL
    url: Optional[str] = None
    processing_mode: ProcessingMode = ProcessingMode.STEREO_SOUND
    output_format: OutputFormat = OutputFormat.M4A
    custom_title: Optional[str] = None
    settings: Optional[RestorationSettings] = None

class JobDetailResponse(BaseModel):
    job_id: str
    product_name: str = "MoodAudio Studio"
    source_type: SourceType
    source_filename: Optional[str] = None
    source_url: Optional[str] = None
    processing_mode: ProcessingMode
    requested_format: OutputFormat
    status: JobStage
    current_stage: str
    stages_completed: List[str] = Field(default_factory=list)
    progress: float = 0.0
    raw_analysis: Optional[AudioAnalysisReport] = None
    restored_analysis: Optional[AudioAnalysisReport] = None
    validation_result: Optional[ValidationResult] = None
    original_preview_url: Optional[str] = None
    processed_preview_url: Optional[str] = None
    download_url: Optional[str] = None
    output_filename: Optional[str] = None
    output_file_size: Optional[int] = None
    error: Optional[str] = None
    created_at: float
    updated_at: float
    completed_at: Optional[float] = None
    expires_at: Optional[float] = None
    retry_count: int = 0
    can_retry: bool = False
    can_cancel: bool = False

class ModeCapability(BaseModel):
    id: str
    name: str
    description: str
    enabled: bool
    status_badge: str
    notice: Optional[str] = None
    features: List[str]

class CapabilitiesResponse(BaseModel):
    product_name: str
    version: str
    max_upload_size_mb: int
    max_audio_duration_seconds: int
    supported_formats: List[str]
    modes: List[ModeCapability]
    ffmpeg_available: bool
    yt_dlp_available: bool
    database_backend: str
    storage_backend: str
    disclaimer: str
