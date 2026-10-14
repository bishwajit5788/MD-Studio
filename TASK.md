# Project Engineering Task Tracking & Execution Plan

### PHASE 1: Web Scraper Backend Architecture Setup
- [x] Initialize standard Python workspace structure utilizing FastAPI framework rules. *(Verified via automated test suite)*
- [x] Deploy yt-dlp dependencies and configuration scripts. *(Verified via automated test suite)*
- [x] Enforce output filter rules to strip out raw video tracks, saving files purely into audio-only M4A containers. *(Verified via test_audio_only.py)*
- [x] Test the pipeline on local machines using sample YouTube links to verify pure audio output functionality. *(Verified via test_extraction_live.py)*

### PHASE 2: Core Hardware Diagnostics & Bench Tooling
- [x] Implement on-board hardware diagnostic self-test suite (`hardware_diagnostics.cpp` & `[env:diagnostics]`). *(Verified in firmware source tree)*
- [x] Implement uncompressed hardware test tone generators for bench frequency sweeps (`tools/generate_test_tones.py`). *(Verified via automated script)*
- [x] Implement MicroSD card FAT32 validator & throughput benchmark tool (`tools/sd_card_verifier.py`). *(Verified via CLI test)*
- [ ] **Physical bench verification (TEST-HW-01):** Perform multimeter tests on battery connector pins against PCB silkscreen (`RULE_POLARITY_CHECK`). *(See [docs/HARDWARE_VALIDATION_GATES.md](docs/HARDWARE_VALIDATION_GATES.md)) — [Status: PENDING]*
- [ ] **Physical bench verification (TEST-HW-02):** Wire dual 8Ω micro-speakers via JST-PH 2.0 headers and run on-board tone check sweep. *(See [docs/HARDWARE_VALIDATION_GATES.md](docs/HARDWARE_VALIDATION_GATES.md)) — [Status: PENDING]*
- [ ] **Physical bench verification (TEST-HW-03):** Insert physical <=32GB FAT32 MicroSD card and verify on-board mount via TCA9554 EXIO3 CS. *(See [docs/HARDWARE_VALIDATION_GATES.md](docs/HARDWARE_VALIDATION_GATES.md)) — [Status: PENDING]*

### PHASE 3: Memory-Safe Firmware Synthesis
- [x] Reconcile authoritative Waveshare ESP32-S3-Touch-LCD-1.85 original pin mapping (LCD, SD, PCM5101, I2C). *(Verified via tools/audit_pin_mappings.py)*
- [x] Eliminate prohibited ESP32-A2DP dependency; implement capability-gated `IBluetoothAudio` interface reporting `NOT_SUPPORTED` on ESP32-S3. *(Verified via CI & audit)*
- [x] Implement real finite state machine (`state_machine.h`) enforcing transition lifecycle: `ACTIVE_A -> mute -> stop -> destroy -> free -> clear pointers -> verify resources -> ACTIVE_B`. *(Verified in audio_manager.cpp)*
- [x] Build TCA9554 IO expander driver controlling MicroSD CS on EXIO3 (`tca9554.cpp` & `sd_manager.cpp`). *(Verified in firmware codebase)*
- [x] Implement deterministic hardware PCM/I2S test path and <=65% volume ceiling enforcement (`RULE_VOLUME_CEILING`). *(Verified in audio_manager.cpp)*
- [ ] **Physical bench verification (TEST-HW-04):** Run continuous start/stop playback cycles on physical ESP32-S3 hardware to record internal heap and PSRAM stability across repeated decoder lifecycles. *(See [docs/HARDWARE_VALIDATION_GATES.md](docs/HARDWARE_VALIDATION_GATES.md)) — [Status: PENDING]*

### PHASE 4: Visual Interface & Enclosure Design
- [x] Integrate LVGL 8.3 geometry loops for 360x360 ST77916 circular LCD with PSRAM framebuffers. *(Verified in display_manager.cpp)*
- [x] Implement Screen Alpha (clock, battery, local SD mode, capability-gated BT mode). *(Verified in display_manager.cpp)*
- [x] Implement Screen Beta with strictly 1Hz dynamic updates and volume ceiling indicator. *(Verified in display_manager.cpp)*
- [x] Implement Screen Gamma truthfully explaining Bluetooth Audio is unavailable on ESP32-S3 (no fake A2DP discovery). *(Verified in display_manager.cpp)*
- [x] Implement configurable 30-min idle sleep (`RULE_THERMAL_SHUTDOWN`) and 10s display dimming on GPIO5. *(Verified in power_manager.cpp)*
- [x] Create parametric 3D printable bedside enclosure in OpenSCAD with isolated battery tray and acoustic chambers (`enclosure/echonode_bedside_case.scad`). *(Verified in CAD model)*
- [x] Add high-resolution multi-angle product render, exploded view and visual media structure (`images/README.md`, `images/renders/`, `images/components/`, `images/assembly/`, `images/prototype/`). *(Verified)*

### PHASE 5: Deployment, CI/CD & Open-Source Release
- [x] Create `check_partitions.py` tool verifying 4KB sector alignment, 64KB MMU OTA alignment, and no overlaps. *(Verified against partitions_16MB.csv)*
- [x] Create `audit_pin_mappings.py` verifying exact GPIOs against authoritative Waveshare original board mapping. *(Verified)*
- [x] Update GitHub Actions CI workflow (`.github/workflows/ci.yml`) to run pin audits, partition checks, backend tests, and firmware builds. *(Verified)*
- [x] Synchronize all master documentation files (`PDR.md`, `ARCHITECTURE.md`, `RULES.md`, `DESIGN.md`, `MEMORY.md`, `README.md`, `docs/wiring_guide.md`). *(Verified)*

### PHASE 6: Cloud Deployment & Serverless Runtime Hardening
- [x] Harden backend for serverless deployment on Vercel (`downloads_dir` fallback to writable `/tmp/downloads`). *(Verified on live Vercel)*
- [x] Mitigate serverless container freeze by awaiting extraction within request lifecycle on `VERCEL=1`. *(Verified on live Vercel)*
- [x] Add player client fallbacks (`android`, `ios`, `mweb`, `web`) and `YTDLP_COOKIES` environment variable support to bypass datacenter IP bot detection. *(Verified in extractor.py)*
- [x] Surface real-time backend errors (`job.error`) directly inside web dashboard UI. *(Verified in index.html)*
- [x] Document local vs cloud deployment architectures in `backend/README.md`. *(Verified)*

### PHASE 7: Decoupled Extraction Architecture & Production YouTube Audio Engine
- [x] Root-cause diagnosis of YouTube BotGuard datacenter IP challenges and Vercel serverless execution limits. *(Documented in implementation_plan.md)*
- [x] Implement persistent SQLite-backed `JobStore` surviving serverless cold starts and worker restarts. *(Verified via test_job_store.py)*
- [x] Implement pluggable `StorageService` supporting local staging and S3/R2/MinIO cloud object storage. *(Verified via test_storage.py)*
- [x] Implement error message sanitization preventing credentials, session tokens, or private paths from leaking to logs or API responses. *(Verified via test_job_store.py)*
- [x] Implement standalone worker service entrypoint (`backend/worker.py`) with FFmpeg transcoding, pure audio validation, and secure temporary cookie handling. *(Verified via worker.py)*
- [x] Implement Vercel proxy coordinator mode (`WORKER_URL`) maintaining identical API routes (`/api/extract`, `/api/jobs`, `/api/files`, `/api/download/{filename}`). *(Verified via test_backend.py)*
- [x] Enforce pure audio stream validation (0 video tracks), $\le 60$ MB size limits, and FAT32 filename sanitization. *(Verified via test_audio_only.py)*
- [x] Create comprehensive Phase 7 verification test suite (`backend/tests/test_phase7_verification.py`). *(Verified via 11 automated test cases)*
- [x] Update GitHub Actions CI workflow to run all backend test suites and compile production firmware (`pio run -e waveshare_esp32s3_round`). *(Verified in .github/workflows/ci.yml)*

### PHASE 8: Production Ingestion Pipeline Hardening & 22-Requirement Suite
- [x] Eliminate silent serverless fallback in Vercel: return predictable HTTP 503 (`{"error": "Extraction worker is not configured"}`) when `WORKER_URL` is unset. *(Verified on live Vercel)*
- [x] Standardize `/api/system-info` and `/health` with non-secret operational diagnostics. *(Verified live on Vercel)*
- [x] Deploy Proof-of-Origin (POT) provider support (`bgutil-ytdlp-pot-provider`) and `ejs:github` JavaScript challenge solving. *(Verified in extractor.py)*
- [x] Enforce pure audio format selector (`140/bestaudio[ext=m4a]/bestaudio`) preventing video fallback. *(Verified via test_all_22_requirements.py)*
- [x] Implement comprehensive 22-requirement test suite (`backend/tests/test_all_22_requirements.py`). *(22/22 passed)*
- [x] Provide production Dockerfile and `docker-compose.yml` for persistent extraction worker with BgUtils POT daemon and Node.js challenge solver. *(Verified)*
- [x] Update frontend dashboard (`index.html`) with dynamic worker connection status badges. *(Verified live on Vercel)*
- [x] Update GitHub Actions CI with `workflow_dispatch` opt-in live YouTube extraction test. *(Verified in .github/workflows/ci.yml)*

### PHASE 9: MoodAudio Studio Full-Stack Audio Workstation & EchoNode Hardware Compatibility Contract
- [x] Full-Stack Next.js 16 + React 19 + TypeScript audio workstation interface (`frontend/`) with dark-first DAW aesthetic (`#090c14`), light theme persistence, and zero decorative mockups. *(Verified via npm run build)*
- [x] Phase 1 Audio Extraction & Pre-Restoration Analysis Engine (`backend/app/services/audio_analyzer.py`): True Peak (`dBTP`), Max Peak (`dBFS`), RMS (`dBFS`), EBU R128 LUFS, Loudness Range (`LU`), DC offset, stereo imbalance, clipping detection, and 100-point normalized waveform peak envelopes. *(Verified via test_moodaudio_v1.py)*
- [x] 4 Differentiated Audio Processing Modes (`backend/app/services/audio_restorer.py`):
  - [x] Dolby Atmos: Strictly disabled (`enabled: false`, "Coming soon — compatible Atmos authoring workflow not yet validated") preventing deceptive multichannel/ADM renaming. *(Verified in capabilities and restorer)*
  - [x] Immersive Audio: Open-source binaural spatial DSP rendering (ITD, crossfeed, early room reflection simulation) with Subtle, Moderate, Wide intensity. *(Verified in test_moodaudio_v1.py)*
  - [x] Stereo Sound: Bit-perfect stream preservation / conservative mastering (<20Hz DC highpass, -1.0 dBTP true-peak ceiling). *(Verified in test_moodaudio_v1.py)*
  - [x] Audio Enhancer: Adaptive content-aware speech clarity vs music warmth restoration. *(Verified in test_moodaudio_v1.py)*
- [x] Fair A/B Preview Player with Matched Loudness: Dual original vs. processed audio playback normalized to -16 LUFS via EBU R128 to eliminate psychoacoustic volume bias. *(Verified in audio_restorer.py & frontend)*
- [x] Phase 5 Automated Quality Assurance Gate (`backend/app/services/audio_validator.py`): Automated media verification (format container, duration tolerance, decodability, zero clipping, non-silence) gating download controls. *(Verified via test_moodaudio_v1.py)*
- [x] EchoNode Bedside Hardware Device Compatibility Contract (`backend/app/models.py` & `audio_validator.py`):
  - [x] Strict validation of exactly zero video tracks (preventing ESP32-S3 I2S decoder panics). *(Verified)*
  - [x] Validation of supported codecs (`aac` in M4A, `mp3`, `pcm_s16le` in WAV) matching ESP32-audioI2S firmware decoder. *(Verified)*
  - [x] Sample rate verification (22050, 32000, 44100, 48000 Hz) matching PCM5101 I2S PLL lock range. *(Verified)*
  - [x] Stereo / mono DAC channel count verification (rejecting multichannel 5.1/7.1 for hardware DAC). *(Verified)*
  - [x] FAT32 filename compliance ($\le 60$ characters base length, safe ASCII characters). *(Verified)*
  - [x] File size safety boundary ($\le 60$ MB to avoid FAT32 SPI cluster exhaustion). *(Verified)*
  - [x] Explicit fulfillment contract: manual MicroSD transfer marked active/verified; USB Mass Storage and local network sync marked as planned capabilities. *(Verified in UI & API response)*
- [x] Unified PostgreSQL & SQLite Persistence (`backend/app/services/database.py`): Dynamic backend support for Railway PostgreSQL and local SQLite with UUID keys, audit timestamps, and retry/cancel state transitions. *(Verified via test_moodaudio_v1.py)*
- [x] Containerization & CI/CD: Multi-stage Next.js `Dockerfile`, Railway `backend/railway.toml`, Vercel `frontend/vercel.json`, complete `docker-compose.yml`, and updated GitHub Actions CI running 62 backend tests, hardware pinout checks, partition boundary checks, and Next.js production builds. *(Verified)*
- [ ] **Physical bench verification gates (Awaiting physical lab equipment — see [docs/HARDWARE_VALIDATION_GATES.md](docs/HARDWARE_VALIDATION_GATES.md)):**
  - [ ] **TEST-HW-01 (Battery Connector Polarity):** Multimeter polarity check on MX1.25 port against PCB silkscreen (`RULE_POLARITY_CHECK`). *[Status: PENDING]*
  - [ ] **TEST-HW-02 (Dual Speaker Tone Sweep):** Connect dual 8Ω micro-speakers via JST-PH 2.0 headers and run `[env:diagnostics]` sweep. *[Status: PENDING]*
  - [ ] **TEST-HW-03 (MicroSD Mount via TCA9554):** Insert physical <=32GB FAT32 MicroSD card and verify `EXIO3` CS mount at 20MHz. *[Status: PENDING]*
  - [ ] **TEST-HW-04 (Repeated Playback Lifecycle & Memory Stability):** 50-cycle start/stop stress test verifying zero cumulative heap/PSRAM leak. *[Status: PENDING]*

