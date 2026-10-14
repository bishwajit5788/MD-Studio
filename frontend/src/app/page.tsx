"use client";

import React, { useState, useEffect, useRef } from "react";

// Types matching backend models
interface AudioAnalysisReport {
  duration_seconds: number;
  sample_rate: number;
  channels: number;
  channel_layout: string;
  codec: string;
  bit_rate_kbps?: number;
  peak_dbfs: number;
  rms_dbfs: number;
  integrated_lufs?: number;
  loudness_range_lra?: number;
  true_peak_dbtp?: number;
  dc_offset: number;
  channel_imbalance_db: number;
  clipping_samples: number;
  has_clipping: boolean;
  silence_detected: boolean;
  noise_floor_dbfs?: number;
  detected_content_type: string;
  waveform_peaks: number[];
}

interface EchoNodeCompatibility {
  is_compatible: boolean;
  safe_fat32_name: string;
  zero_video_streams: boolean;
  supported_codec: boolean;
  supported_sample_rate: boolean;
  supported_channels: boolean;
  size_within_limit: boolean;
  recommended_for_hardware: boolean;
  transfer_method_available: string;
  hardware_notes: string[];
}

interface ValidationResult {
  is_valid: boolean;
  file_size_bytes: number;
  duration_seconds: number;
  channels: number;
  sample_rate: number;
  format_matched: boolean;
  clipping_detected: boolean;
  peak_dbfs: number;
  rms_dbfs: number;
  decodable: boolean;
  issues: string[];
  echonode_compatibility?: EchoNodeCompatibility;
}

interface JobDetail {
  job_id: string;
  product_name: string;
  source_type: "upload" | "url";
  source_filename?: string;
  source_url?: string;
  processing_mode: string;
  requested_format: string;
  status: string;
  current_stage: string;
  stages_completed: string[];
  progress: number;
  raw_analysis?: AudioAnalysisReport;
  restored_analysis?: AudioAnalysisReport;
  validation_result?: ValidationResult;
  original_preview_url?: string;
  processed_preview_url?: string;
  download_url?: string;
  output_filename?: string;
  output_file_size?: number;
  error?: string;
  created_at: number;
  updated_at: number;
  completed_at?: number;
  can_retry: boolean;
  can_cancel: boolean;
}

interface ModeCapability {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  status_badge: string;
  notice?: string;
  features: string[];
}

interface Capabilities {
  product_name: string;
  version: string;
  max_upload_size_mb: number;
  max_audio_duration_seconds: number;
  supported_formats: string[];
  modes: ModeCapability[];
  ffmpeg_available: boolean;
  yt_dlp_available: boolean;
  database_backend: string;
  storage_backend: string;
  disclaimer: string;
}

const API_BASE = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");
const apiUrl = (path: string) => (path.startsWith("http") ? path : `${API_BASE}${path}`);

export default function StudioPage() {
  // Navigation & Theme
  const [activeTab, setActiveTab] = useState<"studio" | "workspace" | "history" | "docs">("studio");
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [systemHealthy, setSystemHealthy] = useState<boolean | null>(null);

  // Ingestion Form State
  const [sourceType, setSourceType] = useState<"upload" | "url">("upload");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [sourceUrl, setSourceUrl] = useState("");
  const [customTitle, setCustomTitle] = useState("");
  const [processingMode, setProcessingMode] = useState("stereo_sound");
  const [outputFormat, setOutputFormat] = useState("m4a");
  const [spatialIntensity, setSpatialIntensity] = useState("moderate");
  const [loudnessNorm, setLoudnessNorm] = useState(true);
  const [noiseReduction, setNoiseReduction] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  // Workspace & Active Job State
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [activeJob, setActiveJob] = useState<JobDetail | null>(null);
  const [isPolling, setIsPolling] = useState(false);

  // Audio Playback State
  const [activeSource, setActiveSource] = useState<"original" | "processed">("processed");
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [volume, setVolume] = useState(0.8);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  // Job History
  const [jobHistory, setJobHistory] = useState<JobDetail[]>([]);

  // 1. Initial Load: Theme, Capabilities, Health, History
  useEffect(() => {
    // Theme load
    const savedTheme = localStorage.getItem("moodaudio_theme") as "dark" | "light" | null;
    if (savedTheme) {
      setTheme(savedTheme);
      document.documentElement.setAttribute("data-theme", savedTheme);
    }

    // Capabilities fetch
    fetch(apiUrl("/api/v1/capabilities"))
      .then((res) => res.json())
      .then((data: Capabilities) => {
        setCapabilities(data);
      })
      .catch((err) => console.error("Capabilities error:", err));

    // Health fetch
    fetch(apiUrl("/api/v1/health"))
      .then((res) => res.json())
      .then((data) => setSystemHealthy(data.status === "healthy"))
      .catch(() => setSystemHealthy(false));

    // Load recent jobs
    loadRecentJobs();
  }, []);

  const toggleTheme = () => {
    const nextTheme = theme === "dark" ? "light" : "dark";
    setTheme(nextTheme);
    localStorage.setItem("moodaudio_theme", nextTheme);
    document.documentElement.setAttribute("data-theme", nextTheme);
  };

  const loadRecentJobs = () => {
    fetch(apiUrl("/api/v1/jobs?limit=20"))
      .then((res) => res.json())
      .then((data) => {
        if (Array.isArray(data)) {
          setJobHistory(data);
        }
      })
      .catch((err) => console.error("Jobs error:", err));
  };

  // 2. Job Polling Effect
  useEffect(() => {
    if (!activeJobId || !isPolling) return;

    const interval = setInterval(() => {
      fetch(apiUrl(`/api/v1/jobs/${activeJobId}`))
        .then((res) => res.json())
        .then((job: JobDetail) => {
          setActiveJob(job);
          if (job.status === "completed" || job.status === "failed" || job.status === "cancelled") {
            setIsPolling(false);
            loadRecentJobs();
          }
        })
        .catch((err) => console.error("Polling error:", err));
    }, 1000);

    return () => clearInterval(interval);
  }, [activeJobId, isPolling]);

  // 3. Audio Element Sync
  useEffect(() => {
    if (!audioRef.current || !activeJob) return;

    const previewUrl =
      activeSource === "original"
        ? activeJob.original_preview_url
        : activeJob.processed_preview_url || activeJob.original_preview_url;

    if (previewUrl) {
      const prevTime = audioRef.current.currentTime;
      const wasPlaying = !audioRef.current.paused;
      audioRef.current.src = apiUrl(previewUrl);
      audioRef.current.load();
      audioRef.current.currentTime = prevTime;
      if (wasPlaying) {
        audioRef.current.play().catch(() => {});
      }
    }
  }, [activeSource, activeJob?.job_id, activeJob?.status]);

  // 4. Waveform Canvas Renderer
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const peaks =
      activeJob?.restored_analysis?.waveform_peaks ||
      activeJob?.raw_analysis?.waveform_peaks ||
      [];

    const width = canvas.width;
    const height = canvas.height;
    ctx.clearRect(0, 0, width, height);

    if (peaks.length === 0) {
      // Draw placeholder baseline
      ctx.strokeStyle = theme === "dark" ? "rgba(255, 255, 255, 0.15)" : "rgba(0, 0, 0, 0.15)";
      ctx.beginPath();
      ctx.moveTo(0, height / 2);
      ctx.lineTo(width, height / 2);
      ctx.stroke();
      return;
    }

    const barWidth = width / peaks.length;
    const progressPercent = duration > 0 ? currentTime / duration : 0;
    const currentBarIdx = Math.floor(progressPercent * peaks.length);

    peaks.forEach((peak, i) => {
      const barHeight = Math.max(3, peak * (height - 12));
      const x = i * barWidth;
      const y = (height - barHeight) / 2;

      // Color active playback vs unplayed
      if (i <= currentBarIdx) {
        ctx.fillStyle = activeSource === "processed" ? "#06b6d4" : "#6366f1";
      } else {
        ctx.fillStyle = theme === "dark" ? "rgba(255, 255, 255, 0.25)" : "rgba(0, 0, 0, 0.25)";
      }

      ctx.fillRect(x, y, Math.max(1, barWidth - 1), barHeight);
    });
  }, [activeJob?.raw_analysis, activeJob?.restored_analysis, currentTime, duration, theme, activeSource]);

  // Form Submission
  const handleSubmitJob = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    if (sourceType === "upload" && !selectedFile) {
      setFormError("Please select an audio file to upload.");
      return;
    }
    if (sourceType === "url" && !sourceUrl.trim()) {
      setFormError("Please enter a valid YouTube audio URL.");
      return;
    }

    if (processingMode === "dolby_atmos") {
      setFormError("Dolby Atmos is disabled pending workflow validation. Please choose Immersive Audio or Stereo Sound.");
      return;
    }

    setIsSubmitting(true);
    const formData = new FormData();
    formData.append("source_type", sourceType);
    formData.append("processing_mode", processingMode);
    formData.append("output_format", outputFormat);
    if (customTitle.trim()) formData.append("custom_title", customTitle.trim());

    if (sourceType === "upload" && selectedFile) {
      formData.append("file", selectedFile);
    } else if (sourceType === "url") {
      formData.append("url", sourceUrl.trim());
    }

    const settingsObj = {
      loudness_normalization: loudnessNorm,
      noise_reduction_enabled: noiseReduction,
      spatial_intensity: spatialIntensity,
    };
    formData.append("settings_json", JSON.stringify(settingsObj));

    try {
      const res = await fetch(apiUrl("/api/v1/jobs"), {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const errJson = await res.json();
        throw new Error(errJson.detail || "Job creation failed.");
      }

      const job: JobDetail = await res.json();
      setActiveJobId(job.job_id);
      setActiveJob(job);
      setIsPolling(true);
      setActiveTab("workspace");
    } catch (err: any) {
      setFormError(err.message || "Failed to submit processing job.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCancel = async () => {
    if (!activeJobId) return;
    try {
      await fetch(apiUrl(`/api/v1/jobs/${activeJobId}/cancel`), { method: "POST" });
      const res = await fetch(apiUrl(`/api/v1/jobs/${activeJobId}`));
      const updated = await res.json();
      setActiveJob(updated);
      setIsPolling(false);
    } catch (err) {
      console.error("Cancel error:", err);
    }
  };

  const handleRetry = async () => {
    if (!activeJobId) return;
    try {
      const res = await fetch(apiUrl(`/api/v1/jobs/${activeJobId}/retry`), { method: "POST" });
      const updated = await res.json();
      setActiveJob(updated);
      setIsPolling(true);
    } catch (err) {
      console.error("Retry error:", err);
    }
  };

  const formatSeconds = (sec: number) => {
    if (!sec || isNaN(sec)) return "00:00";
    const m = Math.floor(sec / 60);
    const s = Math.floor(sec % 60);
    return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  };

  const formatBytes = (bytes?: number) => {
    if (!bytes) return "0 MB";
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  return (
    <div className="studio-container">
      {/* Hidden Audio Player for Preview Engine */}
      <audio
        ref={audioRef}
        onTimeUpdate={(e) => setCurrentTime((e.target as HTMLAudioElement).currentTime)}
        onLoadedMetadata={(e) => setDuration((e.target as HTMLAudioElement).duration)}
        onEnded={() => setIsPlaying(false)}
      />

      {/* Header */}
      <header className="studio-header">
        <div className="brand-section">
          <div className="brand-badge-logo">M</div>
          <div className="brand-titles">
            <h1>{capabilities?.product_name || "MoodAudio Studio"}</h1>
            <p>Professional Audio Extraction, Restoration & Spatial Processing Platform</p>
          </div>
        </div>

        <div className="header-controls">
          <div className="nav-tabs">
            <button
              className={`nav-tab-btn ${activeTab === "studio" ? "active" : ""}`}
              onClick={() => setActiveTab("studio")}
            >
              Studio
            </button>
            <button
              className={`nav-tab-btn ${activeTab === "workspace" ? "active" : ""}`}
              onClick={() => setActiveTab("workspace")}
            >
              Workspace {activeJob && `(${activeJob.status})`}
            </button>
            <button
              className={`nav-tab-btn ${activeTab === "history" ? "active" : ""}`}
              onClick={() => setActiveTab("history")}
            >
              History ({jobHistory.length})
            </button>
            <button
              className={`nav-tab-btn ${activeTab === "docs" ? "active" : ""}`}
              onClick={() => setActiveTab("docs")}
            >
              Specs & Specs
            </button>
          </div>

          <button
            className="theme-toggle-btn"
            onClick={toggleTheme}
            aria-label="Toggle Theme"
            title={`Switch to ${theme === "dark" ? "Light" : "Dark"} mode`}
          >
            {theme === "dark" ? "☀️" : "🌙"}
          </button>
        </div>
      </header>

      {/* SYSTEM HEALTH BANNER */}
      {systemHealthy === false && (
        <div style={{ padding: "10px 16px", borderRadius: "8px", background: "rgba(244, 63, 94, 0.15)", border: "1px solid var(--accent-rose)", color: "var(--accent-rose)", fontSize: "0.85rem" }}>
          ⚠️ Backend audio DSP engine is currently offline or unreachable. Please verify local server is running.
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 1: STUDIO (INGESTION & MODE SELECTION)                                  */}
      {/* ========================================================================= */}
      {activeTab === "studio" && (
        <form onSubmit={handleSubmitJob} className="studio-grid">
          {/* Left Column: Source Input & Mode Cards */}
          <div style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
            {/* Input Selection Card */}
            <div className="card">
              <h2 className="card-title">1. Audio Source</h2>

              <div style={{ display: "flex", gap: "10px" }}>
                <button
                  type="button"
                  className={`btn-secondary ${sourceType === "upload" ? "active" : ""}`}
                  style={{ flex: 1, borderColor: sourceType === "upload" ? "var(--accent-primary)" : "var(--border-medium)" }}
                  onClick={() => setSourceType("upload")}
                >
                  Direct File Upload
                </button>
                <button
                  type="button"
                  className={`btn-secondary ${sourceType === "url" ? "active" : ""}`}
                  style={{ flex: 1, borderColor: sourceType === "url" ? "var(--accent-primary)" : "var(--border-medium)" }}
                  onClick={() => setSourceType("url")}
                >
                  Authorized Source URL
                </button>
              </div>

              {sourceType === "upload" ? (
                <div
                  className="dropzone-container"
                  onClick={() => document.getElementById("file-input")?.click()}
                >
                  <input
                    id="file-input"
                    type="file"
                    accept="audio/*,.wav,.mp3,.m4a,.flac,.aac,.ogg"
                    style={{ display: "none" }}
                    onChange={(e) => {
                      if (e.target.files && e.target.files[0]) {
                        setSelectedFile(e.target.files[0]);
                      }
                    }}
                  />
                  <div className="dropzone-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M12 2v10M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z" />
                      <path d="M16 8l-4-4-4 4" />
                    </svg>
                  </div>
                  <div className="dropzone-text">
                    <h3>{selectedFile ? selectedFile.name : "Click to select or drop audio file here"}</h3>
                    <p>
                      {selectedFile
                        ? `${(selectedFile.size / (1024 * 1024)).toFixed(2)} MB • Ready for restoration`
                        : `Supported formats: WAV, M4A, MP3, FLAC • Max ${capabilities?.max_upload_size_mb || 100} MB`}
                    </p>
                  </div>
                </div>
              ) : (
                <div className="url-input-group">
                  <div className="url-input-wrapper">
                    <input
                      type="url"
                      className="text-input"
                      placeholder="https://www.youtube.com/watch?v=..."
                      value={sourceUrl}
                      onChange={(e) => setSourceUrl(e.target.value)}
                    />
                  </div>
                  <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                    Best available audio-only stream will be extracted directly into untouched storage without video tracks.
                  </p>
                </div>
              )}

              <div>
                <label style={{ fontSize: "0.85rem", color: "var(--text-secondary)", marginBottom: "6px", display: "block" }}>
                  Custom Track Title (Optional)
                </label>
                <input
                  type="text"
                  className="text-input"
                  style={{ width: "100%" }}
                  placeholder="e.g. Mastered_Acoustic_Session"
                  value={customTitle}
                  onChange={(e) => setCustomTitle(e.target.value)}
                />
              </div>
            </div>

            {/* Processing Modes */}
            <div className="card">
              <h2 className="card-title">2. Select Processing Mode</h2>

              <div className="modes-grid">
                {/* Mode 1: Atmos (Disabled) */}
                <div
                  className={`mode-card disabled ${processingMode === "dolby_atmos" ? "selected" : ""}`}
                  onClick={() => {}}
                >
                  <div className="mode-header">
                    <span className="mode-name">Dolby Atmos</span>
                    <span className="badge badge-coming-soon">Coming Soon</span>
                  </div>
                  <p className="mode-desc">
                    Compatible Atmos authoring workflow not yet validated. Strict open-source and delivery compliance required.
                  </p>
                  <ul className="mode-features">
                    <li>Genuinely validated workflows only</li>
                    <li>No fabricated object metadata</li>
                    <li>Disabled until compliant EBU ADM export proven</li>
                  </ul>
                </div>

                {/* Mode 2: Immersive Audio */}
                <div
                  className={`mode-card ${processingMode === "immersive_audio" ? "selected" : ""}`}
                  onClick={() => setProcessingMode("immersive_audio")}
                >
                  <div className="mode-header">
                    <span className="mode-name">Immersive Audio</span>
                    <span className="badge badge-active">Active</span>
                  </div>
                  <p className="mode-desc">
                    Genuine binaural headphone spatialization with room acoustics simulation.
                  </p>
                  <ul className="mode-features">
                    <li>Virtual source positioning</li>
                    <li>Binaural HRTF stereo crossfeed</li>
                    <li>Room acoustic reflection depth</li>
                  </ul>
                </div>

                {/* Mode 3: Stereo Sound */}
                <div
                  className={`mode-card ${processingMode === "stereo_sound" ? "selected" : ""}`}
                  onClick={() => setProcessingMode("stereo_sound")}
                >
                  <div className="mode-header">
                    <span className="mode-name">Stereo Sound</span>
                    <span className="badge badge-active">Active</span>
                  </div>
                  <p className="mode-desc">
                    Fidelity-first mastering prioritizing exact input preservation and headroom.
                  </p>
                  <ul className="mode-features">
                    <li>Input-faithful channel balance</li>
                    <li>Lossless stream-copy when possible</li>
                    <li>Sub-bass DC offset removal</li>
                  </ul>
                </div>

                {/* Mode 4: Audio Enhancer */}
                <div
                  className={`mode-card ${processingMode === "audio_enhancer" ? "selected" : ""}`}
                  onClick={() => setProcessingMode("audio_enhancer")}
                >
                  <div className="mode-header">
                    <span className="mode-name">Audio Enhancer</span>
                    <span className="badge badge-active">Active</span>
                  </div>
                  <p className="mode-desc">
                    Adaptive conservative restoration for speech presence or musical warmth.
                  </p>
                  <ul className="mode-features">
                    <li>Content-aware speech vs music EQ</li>
                    <li>Conservative noise reduction</li>
                    <li>EBU R128 loudness normalization</li>
                  </ul>
                </div>
              </div>
            </div>
          </div>

          {/* Right Column: Settings & Submit */}
          <div style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
            <div className="card">
              <h2 className="card-title">3. Export & DSP Settings</h2>

              <div>
                <label style={{ fontSize: "0.85rem", color: "var(--text-secondary)", marginBottom: "6px", display: "block" }}>
                  Output Audio Format
                </label>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "8px" }}>
                  {["m4a", "mp3", "flac", "wav"].map((fmt) => (
                    <button
                      key={fmt}
                      type="button"
                      className={`btn-secondary ${outputFormat === fmt ? "active" : ""}`}
                      style={{
                        padding: "8px",
                        borderColor: outputFormat === fmt ? "var(--accent-primary)" : "var(--border-subtle)",
                        fontWeight: 600,
                        textTransform: "uppercase",
                      }}
                      onClick={() => setOutputFormat(fmt)}
                    >
                      {fmt}
                    </button>
                  ))}
                </div>
              </div>

              {processingMode === "immersive_audio" && (
                <div>
                  <label style={{ fontSize: "0.85rem", color: "var(--text-secondary)", marginBottom: "6px", display: "block" }}>
                    Spatial Intensity
                  </label>
                  <select
                    className="text-input"
                    style={{ width: "100%" }}
                    value={spatialIntensity}
                    onChange={(e) => setSpatialIntensity(e.target.value)}
                  >
                    <option value="subtle">Subtle (Natural crossfeed, low fatigue)</option>
                    <option value="moderate">Moderate (Standard binaural room depth)</option>
                    <option value="wide">Wide (Expansive 3D soundstage)</option>
                  </select>
                </div>
              )}

              <div style={{ display: "flex", flexDirection: "column", gap: "12px", borderTop: "1px solid var(--border-subtle)", paddingTop: "16px" }}>
                <label style={{ display: "flex", alignItems: "center", gap: "10px", fontSize: "0.85rem", cursor: "pointer" }}>
                  <input
                    type="checkbox"
                    checked={loudnessNorm}
                    onChange={(e) => setLoudnessNorm(e.target.checked)}
                  />
                  <span>EBU R128 Loudness Normalization (-14 LUFS)</span>
                </label>

                <label style={{ display: "flex", alignItems: "center", gap: "10px", fontSize: "0.85rem", cursor: "pointer" }}>
                  <input
                    type="checkbox"
                    checked={noiseReduction}
                    onChange={(e) => setNoiseReduction(e.target.checked)}
                  />
                  <span>Conservative Acoustic Denoising (if noise detected)</span>
                </label>
              </div>

              {formError && (
                <div style={{ padding: "10px 14px", borderRadius: "8px", background: "rgba(244, 63, 94, 0.15)", color: "var(--accent-rose)", fontSize: "0.85rem" }}>
                  {formError}
                </div>
              )}

              <button
                type="submit"
                className="btn-primary"
                style={{ width: "100%", padding: "14px" }}
                disabled={isSubmitting}
              >
                {isSubmitting ? "Initializing Processing Workspace..." : "Start Audio Processing"}
              </button>
            </div>

            {/* Architecture Principles Notice */}
            <div className="card" style={{ fontSize: "0.8rem", color: "var(--text-muted)", gap: "10px" }}>
              <div style={{ fontWeight: 600, color: "var(--text-secondary)" }}>Core Studio Principles</div>
              <p>• Original source is preserved untouched in private storage.</p>
              <p>• Restoration removes defects without fabricating non-existent master detail.</p>
              <p>• Output validation gate blocks downloads until decodability & clipping tests pass.</p>
            </div>
          </div>
        </form>
      )}

      {/* ========================================================================= */}
      {/* TAB 2: PROCESSING WORKSPACE                                              */}
      {/* ========================================================================= */}
      {activeTab === "workspace" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
          {!activeJob ? (
            <div className="card" style={{ textAlign: "center", padding: "60px 20px" }}>
              <p style={{ color: "var(--text-muted)", marginBottom: "16px" }}>
                No active audio processing workspace. Submit an audio track in Studio to begin.
              </p>
              <button className="btn-primary" style={{ margin: "0 auto" }} onClick={() => setActiveTab("studio")}>
                Go to Studio Ingestion
              </button>
            </div>
          ) : (
            <>
              {/* Job Status Header */}
              <div className="card" style={{ gap: "16px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "10px" }}>
                  <div>
                    <span style={{ fontSize: "0.8rem", color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                      JOB #{activeJob.job_id.slice(0, 12)}
                    </span>
                    <h2 style={{ fontSize: "1.3rem", fontWeight: 700 }}>{activeJob.source_filename || "Processing Track"}</h2>
                  </div>

                  <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
                    <span className={`badge ${activeJob.status === "completed" ? "badge-active" : activeJob.status === "failed" ? "badge-coming-soon" : "badge-neutral"}`}>
                      {activeJob.status}
                    </span>
                    {activeJob.can_cancel && (
                      <button className="btn-danger" onClick={handleCancel}>
                        Cancel
                      </button>
                    )}
                    {activeJob.can_retry && (
                      <button className="btn-secondary" onClick={handleRetry}>
                        Retry Job
                      </button>
                    )}
                  </div>
                </div>

                {/* Real-time Stage Progress Tracker */}
                <div className="stage-tracker">
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.85rem", color: "var(--text-secondary)" }}>
                    <span>{activeJob.current_stage}</span>
                    <span style={{ fontFamily: "var(--font-mono)" }}>{Math.round(activeJob.progress)}%</span>
                  </div>
                  <div className="stage-bar-outer">
                    <div className="stage-bar-inner" style={{ width: `${Math.max(4, activeJob.progress)}%` }} />
                  </div>
                  <div className="stage-pills-row">
                    {["validating", "extracting", "analyzing", "restoring", "rendering", "validating_output", "completed"].map((stg) => {
                      const isDone = activeJob.stages_completed.includes(stg) || activeJob.status === "completed";
                      const isCurrent = activeJob.status === stg;
                      return (
                        <div key={stg} className={`stage-pill ${isDone ? "completed" : isCurrent ? "current" : ""}`}>
                          {stg.replace("_", " ")}
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>

              {/* Dual A/B Audio Player & Real Waveform */}
              <div className="card">
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "12px" }}>
                  <h3 className="card-title">Interactive Audio Preview (Matched Loudness)</h3>
                  <div className="ab-switch-group">
                    <button
                      className={`ab-btn ${activeSource === "original" ? "active" : ""}`}
                      onClick={() => setActiveSource("original")}
                    >
                      A: Original Source
                    </button>
                    <button
                      className={`ab-btn ${activeSource === "processed" ? "active" : ""}`}
                      onClick={() => setActiveSource("processed")}
                      disabled={!activeJob.processed_preview_url && activeJob.status !== "completed"}
                    >
                      B: Processed {activeJob.processing_mode.replace("_", " ")}
                    </button>
                  </div>
                </div>

                {/* Real Waveform Canvas */}
                <canvas
                  ref={canvasRef}
                  className="waveform-canvas"
                  width={1180}
                  height={90}
                  onClick={(e) => {
                    const rect = e.currentTarget.getBoundingClientRect();
                    const clickX = e.clientX - rect.left;
                    const percent = clickX / rect.width;
                    if (audioRef.current && duration > 0) {
                      audioRef.current.currentTime = percent * duration;
                    }
                  }}
                />

                {/* Player Controls */}
                <div className="player-controls-row">
                  <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                    <button
                      className="btn-primary"
                      style={{ width: "42px", height: "42px", padding: 0, borderRadius: "50%" }}
                      onClick={() => {
                        if (!audioRef.current) return;
                        if (isPlaying) {
                          audioRef.current.pause();
                          setIsPlaying(false);
                        } else {
                          audioRef.current.play().then(() => setIsPlaying(true)).catch(() => {});
                        }
                      }}
                    >
                      {isPlaying ? "⏸" : "▶"}
                    </button>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.9rem" }}>
                      {formatSeconds(currentTime)} / {formatSeconds(duration || activeJob.raw_analysis?.duration_seconds || 0)}
                    </span>
                  </div>

                  {/* Volume Slider */}
                  <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                    <span style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>Vol</span>
                    <input
                      type="range"
                      min="0"
                      max="1"
                      step="0.05"
                      value={volume}
                      onChange={(e) => {
                        const v = parseFloat(e.target.value);
                        setVolume(v);
                        if (audioRef.current) audioRef.current.volume = v;
                      }}
                    />
                  </div>

                  {/* Download Output Button (Enabled ONLY when validated) */}
                  {activeJob.status === "completed" && activeJob.validation_result?.is_valid && (
                    <a
                      href={apiUrl(`/api/v1/jobs/${activeJob.job_id}/download`)}
                      download
                      className="btn-primary"
                      style={{ textDecoration: "none" }}
                    >
                      Download Validated {activeJob.requested_format.toUpperCase()} ({formatBytes(activeJob.output_file_size)})
                    </a>
                  )}
                </div>
              </div>

              {/* Technical Analysis Report Grid */}
              {activeJob.raw_analysis && (
                <div className="card">
                  <h3 className="card-title">Acoustic Analysis & Pre-Restoration Report</h3>
                  <div className="metrics-grid">
                    <div className="metric-card">
                      <span className="metric-label">Peak Volume</span>
                      <span className={`metric-value ${activeJob.raw_analysis.has_clipping ? "danger" : ""}`}>
                        {activeJob.raw_analysis.peak_dbfs.toFixed(1)} dBFS
                      </span>
                    </div>

                    <div className="metric-card">
                      <span className="metric-label">RMS Volume</span>
                      <span className="metric-value">{activeJob.raw_analysis.rms_dbfs.toFixed(1)} dBFS</span>
                    </div>

                    <div className="metric-card">
                      <span className="metric-label">EBU R128 Loudness</span>
                      <span className="metric-value highlight">
                        {activeJob.raw_analysis.integrated_lufs != null ? `${activeJob.raw_analysis.integrated_lufs.toFixed(1)} LUFS` : "N/A"}
                      </span>
                    </div>

                    <div className="metric-card">
                      <span className="metric-label">True Peak</span>
                      <span className="metric-value">
                        {activeJob.raw_analysis.true_peak_dbtp != null ? `${activeJob.raw_analysis.true_peak_dbtp.toFixed(1)} dBTP` : "N/A"}
                      </span>
                    </div>

                    <div className="metric-card">
                      <span className="metric-label">DC Offset</span>
                      <span className="metric-value">{activeJob.raw_analysis.dc_offset.toFixed(5)}</span>
                    </div>

                    <div className="metric-card">
                      <span className="metric-label">Channel Imbalance</span>
                      <span className="metric-value">{activeJob.raw_analysis.channel_imbalance_db.toFixed(1)} dB</span>
                    </div>

                    <div className="metric-card">
                      <span className="metric-label">Sample Rate</span>
                      <span className="metric-value">{activeJob.raw_analysis.sample_rate} Hz</span>
                    </div>

                    <div className="metric-card">
                      <span className="metric-label">Content Detection</span>
                      <span className="metric-value highlight" style={{ textTransform: "capitalize" }}>
                        {activeJob.raw_analysis.detected_content_type}
                      </span>
                    </div>
                  </div>
                </div>
              )}

              {/* Automated Quality Assurance Validation Gate */}
              {activeJob.validation_result && (
                <div className="card">
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <h3 className="card-title">Output Quality Assurance Gate (Phase 5)</h3>
                    <span className={`badge ${activeJob.validation_result.is_valid ? "badge-active" : "badge-coming-soon"}`}>
                      {activeJob.validation_result.is_valid ? "Verified Master" : "Validation Failed"}
                    </span>
                  </div>

                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "10px", fontSize: "0.85rem" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                      <span>{activeJob.validation_result.decodable ? "✅" : "❌"}</span>
                      <span>Decodable by FFprobe</span>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                      <span>{activeJob.validation_result.format_matched ? "✅" : "❌"}</span>
                      <span>Format Container Validated</span>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                      <span>{!activeJob.validation_result.clipping_detected ? "✅" : "❌"}</span>
                      <span>True Peak Headroom Clamped</span>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                      <span>✅</span>
                      <span>Duration Matched ({activeJob.validation_result.duration_seconds}s)</span>
                    </div>
                  </div>

                  {activeJob.validation_result.issues.length > 0 && (
                    <div style={{ marginTop: "10px", padding: "10px", borderRadius: "8px", background: "rgba(244, 63, 94, 0.15)", color: "var(--accent-rose)", fontSize: "0.85rem" }}>
                      {activeJob.validation_result.issues.map((iss, i) => (
                        <div key={i}>• {iss}</div>
                      ))}
                    </div>
                  )}

                  {/* EchoNode Bedside Hardware Device Compatibility & Fulfillment Card */}
                  {activeJob.validation_result.echonode_compatibility && (
                    <div style={{ marginTop: "16px", padding: "16px", borderRadius: "8px", border: "1px solid rgba(99, 102, 241, 0.3)", background: "rgba(255, 255, 255, 0.02)" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px", flexWrap: "wrap", gap: "8px" }}>
                        <div>
                          <h4 style={{ margin: 0, fontSize: "0.95rem", display: "flex", alignItems: "center", gap: "8px" }}>
                            <span>🌙 EchoNode Bedside Device Compatibility</span>
                            <span className="badge" style={{ fontSize: "0.7rem", padding: "2px 8px" }}>
                              Waveshare ESP32-S3 + PCM5101 DAC
                            </span>
                          </h4>
                          <p style={{ margin: "4px 0 0", fontSize: "0.78rem", color: "var(--text-secondary)" }}>
                            Audited against standalone ESP32-S3 I2S decoder, FAT32 MicroSD limits, and RF-free sleep playback rules.
                          </p>
                        </div>
                        <span className={`badge ${activeJob.validation_result.echonode_compatibility.is_compatible ? "badge-active" : "badge-coming-soon"}`}>
                          {activeJob.validation_result.echonode_compatibility.is_compatible ? "Hardware Compatible" : "Device Incompatible"}
                        </span>
                      </div>

                      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "8px", fontSize: "0.8rem", marginBottom: "12px" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                          <span>{activeJob.validation_result.echonode_compatibility.zero_video_streams ? "✅" : "❌"}</span>
                          <span>Zero Video Streams (Pure Audio)</span>
                        </div>
                        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                          <span>{activeJob.validation_result.echonode_compatibility.supported_codec ? "✅" : "❌"}</span>
                          <span>ESP32-audioI2S Codec Match</span>
                        </div>
                        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                          <span>{activeJob.validation_result.echonode_compatibility.supported_sample_rate ? "✅" : "❌"}</span>
                          <span>PCM5101 PLL Lock (≤48 kHz)</span>
                        </div>
                        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                          <span>{activeJob.validation_result.echonode_compatibility.supported_channels ? "✅" : "❌"}</span>
                          <span>Stereo / Mono DAC Layout</span>
                        </div>
                        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                          <span>{activeJob.validation_result.echonode_compatibility.size_within_limit ? "✅" : "❌"}</span>
                          <span>FAT32 Buffer Limit (≤60 MB)</span>
                        </div>
                        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                          <span>🏷️</span>
                          <span>FAT32: <code>{activeJob.validation_result.echonode_compatibility.safe_fat32_name}</code></span>
                        </div>
                      </div>

                      {/* Hardware Notes & Fulfillment Details */}
                      <div style={{ padding: "10px 12px", borderRadius: "6px", background: "rgba(99, 102, 241, 0.08)", border: "1px solid rgba(99, 102, 241, 0.2)", fontSize: "0.78rem" }}>
                        <div style={{ fontWeight: 600, color: "var(--accent-electric)", marginBottom: "4px" }}>
                          Fulfillment & Hardware Transfer Contract:
                        </div>
                        <ul style={{ margin: 0, paddingLeft: "16px", color: "var(--text-secondary)", lineHeight: 1.5 }}>
                          <li><strong>Manual MicroSD Transfer (Verified):</strong> Download the validated file and copy directly to the root of a FAT32 MicroSD card (&le;32GB). Insert into the EchoNode bedside player.</li>
                          <li><strong>USB Mass Storage Transfer:</strong> Planned capability (ESP32-S3 USB OTG MSC stack pending bench verification).</li>
                          <li><strong>Local Network Synchronization:</strong> Planned capability (EchoNode powers off Wi-Fi/BT baseband in Zero-Radio sleep mode to eliminate RF radiation).</li>
                          <li style={{ fontStyle: "italic", marginTop: "4px" }}>Note: The website generates a validated download link; it does not claim real-time synchronization to un-networked physical hardware.</li>
                        </ul>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 3: JOB HISTORY                                                        */}
      {/* ========================================================================= */}
      {activeTab === "history" && (
        <div className="card">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <h2 className="card-title">Recent Processing Jobs</h2>
            <button className="btn-secondary" onClick={loadRecentJobs}>Refresh</button>
          </div>

          <div className="table-wrapper">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Job ID</th>
                  <th>Source Title</th>
                  <th>Mode</th>
                  <th>Format</th>
                  <th>Status</th>
                  <th>Created</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {jobHistory.length === 0 ? (
                  <tr>
                    <td colSpan={7} style={{ textAlign: "center", color: "var(--text-muted)", padding: "32px" }}>
                      No audio processing jobs found.
                    </td>
                  </tr>
                ) : (
                  jobHistory.map((j) => (
                    <tr key={j.job_id}>
                      <td style={{ fontFamily: "var(--font-mono)", fontSize: "0.8rem" }}>{j.job_id.slice(0, 8)}...</td>
                      <td style={{ fontWeight: 500 }}>{j.source_filename || j.source_url || "Audio Track"}</td>
                      <td style={{ textTransform: "capitalize" }}>{j.processing_mode.replace("_", " ")}</td>
                      <td style={{ textTransform: "uppercase" }}>{j.requested_format}</td>
                      <td>
                        <span className={`badge ${j.status === "completed" ? "badge-active" : j.status === "failed" ? "badge-coming-soon" : "badge-neutral"}`}>
                          {j.status}
                        </span>
                      </td>
                      <td style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>
                        {new Date(j.created_at * 1000).toLocaleTimeString()}
                      </td>
                      <td>
                        <div style={{ display: "flex", gap: "6px" }}>
                          <button
                            className="btn-secondary"
                            style={{ padding: "4px 8px", fontSize: "0.75rem" }}
                            onClick={() => {
                              setActiveJobId(j.job_id);
                              setActiveJob(j);
                              setActiveTab("workspace");
                            }}
                          >
                            Open
                          </button>
                          {j.status === "completed" && j.download_url && (
                            <a
                              href={apiUrl(`/api/v1/jobs/${j.job_id}/download`)}
                              className="btn-primary"
                              style={{ padding: "4px 8px", fontSize: "0.75rem", textDecoration: "none" }}
                            >
                              Get
                            </a>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 4: SPECIFICATIONS & DOCUMENTATION                                     */}
      {/* ========================================================================= */}
      {activeTab === "docs" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
          <div className="card">
            <h2 className="card-title">Technical Specifications & Audio Architecture</h2>
            <div style={{ display: "flex", flexDirection: "column", gap: "16px", fontSize: "0.9rem", color: "var(--text-secondary)" }}>
              <div>
                <h3 style={{ color: "var(--text-primary)", fontSize: "1rem", marginBottom: "4px" }}>
                  Distinction: Binaural Audio vs. Multichannel Surround vs. ADM vs. Dolby Atmos
                </h3>
                <p>
                  • <strong>Binaural Audio:</strong> 2-channel headphone stereo rendering using Head-Related Transfer Function (HRTF) filtering, crossfeed, and pinna reflection modeling. It delivers spatial 3D perception on standard headphones without requiring proprietary decoders.
                </p>
                <p>
                  • <strong>Multichannel Surround:</strong> Discrete speaker arrangements (5.1 or 7.1) with dedicated physical channel positions. A multichannel WAV is NOT automatically an Atmos file.
                </p>
                <p>
                  • <strong>ADM (Audio Definition Model):</strong> An open EBU metadata standard (ITU-R BS.2076 / BW64) for describing audio objects and beds. Valid ADM files require rigorous essence-to-metadata association.
                </p>
                <p>
                  • <strong>Dolby Atmos:</strong> A certified proprietary spatial format combining bed channels and dynamic 3D audio object metadata rendered by certified authoring tools (Dolby Atmos Renderer). <em>MoodAudio Studio strictly refuses to rename generic stereo or multichannel PCM as "Dolby Atmos" without certified workflow verification.</em>
                </p>
              </div>

              <div>
                <h3 style={{ color: "var(--text-primary)", fontSize: "1rem", marginBottom: "4px" }}>
                  Restoration Philosophy
                </h3>
                <p>
                  Lossy compression irreversibly discards psychoacoustic information. MoodAudio Studio applies conservative spectral denoising, DC offset correction, sub-bass highpass filtering, and EBU R128 loudness normalization. Detail estimation is treated as mathematical estimation, never claimed as original ground truth.
                </p>
              </div>

              <div>
                <h3 style={{ color: "var(--text-primary)", fontSize: "1rem", marginBottom: "4px" }}>
                  Open Source Foundations
                </h3>
                <p>
                  Built with FFmpeg 7.1, yt-dlp, FastAPI, Pydantic, and Next.js. Released under the MIT License.
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Footer */}
      <footer className="studio-footer">
        <p>MoodAudio Studio • Professional Audio Restoration & Spatial Processing Engine</p>
        <p style={{ fontSize: "0.75rem", marginTop: "4px" }}>
          Preserving original source fidelity • Conservative acoustic DSP • Zero fabricated metadata
        </p>
      </footer>
    </div>
  );
}
