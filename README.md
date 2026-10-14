# 🎧 MoodAudio Studio — Professional Audio Extraction, Restoration & Spatial Processing Platform

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Frontend: Next.js 16](https://img.shields.io/badge/Frontend-Next.js%2016%20%7C%20React%2019%20%7C%20TypeScript-black.svg)](https://nextjs.org)
[![Backend: FastAPI](https://img.shields.io/badge/Backend-FastAPI%20%7C%20Python%203.12-009688.svg)](https://fastapi.tiangolo.com)
[![DSP: FFmpeg 7](https://img.shields.io/badge/DSP-FFmpeg%207%20%7C%20EBU%20R128-green.svg)](https://ffmpeg.org)
[![Hardware: ESP32-S3](https://img.shields.io/badge/Hardware-EchoNode%20Bedside%20Player-blue.svg)](https://github.com/bishwajit5788/EchoNode)

**MoodAudio Studio** is an open-source, full-stack audio engineering workstation designed for high-fidelity audio extraction, conservative acoustic restoration, binaural spatial processing, and broadcast mastering. It pairs a modern, DAW-inspired Next.js frontend with an asynchronous FastAPI and FFmpeg DSP backend, while retaining native compatibility with the **EchoNode** bedside hardware player.

---

## 🧭 Product Principles

1. **Functional Software Over Decorative Mockups:** No simulated progress bars or fake waveform animations. All metrics, waveform envelopes, and progress indicators are computed from actual media files.
2. **Audio Fidelity Over Exaggerated Enhancement:** Lossy compression artifacts cannot be magically reversed. Restoration removes quantifiable acoustic defects (DC offset, stationary background noise, clipping distortion) and applies conservative psychoacoustic equalization.
3. **Measurable Quality Over Invented Percentages:** Acoustic parameters are reported in standard broadcast units: dBFS, dBTP, EBU R128 LUFS, and Loudness Range (LU).
4. **Original-Source Preservation:** Untouched input audio is preserved in private storage.
5. **Phase 5 Quality Assurance Gate:** Processed outputs must pass an automated validation gate (decodability, duration tolerance, channel count, and zero clipping) before download links are unlocked.
6. **Architectural Honesty Regarding Dolby Atmos:** Dolby Atmos authoring requires validated ADM BWF masters authored through a certified Dolby Atmos Renderer. In compliance with strict engineering principles, the Dolby Atmos mode remains disabled with a clear notice until a compliant open workflow is verified.

---

## 🎛️ Audio Processing Modes

| Mode | Status | Engine / Pipeline | Description |
| :--- | :---: | :--- | :--- |
| **Dolby Atmos** | 🔒 *Disabled* | Coming Soon | Kept strictly disabled until an open-source, certified Atmos master workflow is validated. No deceptive channel renaming or fake metadata. |
| **Immersive Audio** | ✅ *Active* | Open-source Binaural Spatial DSP | Virtual acoustic positioning for stereo headphones using crossfeed filtering, frequency-dependent interaural delay (ITD), and subtle early reflections. Intensity configurable: *Subtle*, *Moderate*, *Wide*. |
| **Stereo Sound** | ✅ *Active* | Bit-Perfect / Mastering DSP | Channel balance verification, DC offset removal (<20 Hz highpass), true-peak limiting (-1.0 dBTP headroom), and optional lossless stream-copy. |
| **Audio Enhancer** | ✅ *Active* | Adaptive Dynamic Processing | Content-aware processing. **Speech Mode:** spectral subtraction (`afftdn`), speech clarity EQ, gentle dynamic compression. **Music Mode:** conservative noise reduction, warm harmonic EQ, and transparent peak leveling. |

---

## 🏛️ System Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│                        Next.js Frontend (DAW UI)                      │
│      TypeScript • Vanilla CSS • A/B Loudness-Matched Audio Player      │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ HTTP / REST API (/api/v1)
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        FastAPI Backend Engine                          │
│   Validation • FFprobe Analysis • Background Job Queue • Health Check  │
└───────┬───────────────────────────┬────────────────────────────┬───────┘
        │                           │                            │
        ▼                           ▼                            ▼
┌─────────────────┐       ┌──────────────────┐       ┌──────────────────┐
│  FFmpeg 7 DSP   │       │ Database Layer   │       │ Storage Provider │
│ • ebur128       │       │ • PostgreSQL     │       │ • Local Disk     │
│ • afftdn        │       │   (Railway)      │       │ • Private S3/R2  │
│ • alimiter      │       │ • SQLite         │       │   (Signed URLs)  │
│ • stereowiden   │       │   (Fallback)     │       └──────────────────┘
└─────────────────┘       └──────────────────┘
```

---

## 📁 Repository Structure

```
EchoNode Web/
├── backend/                  # FastAPI backend and DSP pipeline
│   ├── app/
│   │   ├── api/v1/routes.py  # Versioned REST API endpoints
│   │   ├── services/
│   │   │   ├── audio_analyzer.py  # Real FFprobe analysis & waveform extraction
│   │   │   ├── audio_restorer.py  # 4-mode DSP processing & A/B preview generator
│   │   │   ├── audio_validator.py # Phase 5 QA validation gate
│   │   │   ├── database.py        # PostgreSQL (Railway) & SQLite persistence
│   │   │   ├── extractor.py       # Pure audio extraction with yt-dlp & PO token
│   │   │   ├── job_worker.py      # Async background stage-based worker
│   │   │   └── storage.py         # Local & private S3/R2 storage adapter
│   │   ├── models.py         # Pydantic v1 schemas & legacy models
│   │   ├── config.py         # Configurable settings & FAT32 sanitization
│   │   └── main.py           # Application entrypoint & CORS middleware
│   ├── tests/                # 7 test suites (62 unit, integration, & DSP tests)
│   ├── Dockerfile            # Container definition with FFmpeg 7 & Python 3.12
│   ├── requirements.txt      # Locked Python dependencies
│   ├── railway.toml          # Railway production deployment configuration
│   └── .env.example          # Environment variables template
├── frontend/                 # Next.js 16 Web Application (DAW Interface)
│   ├── src/app/
│   │   ├── page.tsx          # 4-Tab Workstation (Studio, Workspace, History, Docs)
│   │   ├── layout.tsx        # HTML shell & font definitions
│   │   └── globals.css       # DAW dark/light design system (Vanilla CSS)
│   ├── next.config.ts        # Standalone build output & API rewrite proxies
│   ├── Dockerfile            # Multi-stage production container build
│   └── vercel.json           # Vercel deployment configuration
├── firmware/                 # EchoNode ESP32-S3 hardware player firmware
├── tools/                    # Hardware pinout audits, test tones, partition validators
├── docker-compose.yml        # Full-stack composition (Frontend, API, Postgres, Worker)
└── Makefile                  # Unified developer targets
```

---

## 🚀 Quickstart & Local Development

### Prerequisites
- Python 3.11+
- Node.js 20+
- FFmpeg 6.0+ (`brew install ffmpeg` on macOS, `sudo apt-get install ffmpeg` on Ubuntu)

### Method A: Docker Compose (One-Command Launch)

```bash
docker compose up --build
```
- **Frontend Workstation:** [http://localhost:3000](http://localhost:3000)
- **FastAPI Backend:** [http://localhost:8000](http://localhost:8000)
- **Interactive Swagger Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Health Check:** [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)

### Method B: Native Local Development

1. **Backend Setup:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r backend/requirements.txt pytest httpx
   
   # Start backend API on port 8000
   uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
   ```

2. **Frontend Setup (in a separate terminal):**
   ```bash
   cd frontend
   npm install
   npm run dev
   ```
   Open [http://localhost:3000](http://localhost:3000).

3. **Running Test Suites:**
   ```bash
   # Run all 62 backend and DSP verification tests
   pytest -v backend/tests
   ```

---

## 📡 API Reference (v1)

All endpoints are versioned under `/api/v1`:

| Method | Path | Description |
| :--- | :--- | :--- |
| `GET` | `/api/v1/capabilities` | Exposes available processing modes, formats, size limits, and system health |
| `GET` | `/api/v1/health` | Diagnostic status (FFmpeg, yt-dlp, database, storage) |
| `POST` | `/api/v1/jobs` | Submit new audio processing job (multipart upload or URL) |
| `GET` | `/api/v1/jobs` | List recent processing jobs with status and metadata |
| `GET` | `/api/v1/jobs/{job_id}` | Retrieve real-time job status, stage, analysis, and validation results |
| `POST` | `/api/v1/jobs/{job_id}/cancel` | Safely abort an in-flight processing job |
| `POST` | `/api/v1/jobs/{job_id}/retry` | Retry a failed or cancelled processing job |
| `GET` | `/api/v1/jobs/{job_id}/preview` | Stream 30s loudness-matched (-16 LUFS) preview audio |
| `GET` | `/api/v1/jobs/{job_id}/download` | Download output file (gated by Phase 5 validation) |
| `DELETE` | `/api/v1/jobs/{job_id}` | Purge job records and associated temporary workspace |

---

## 🚢 Production Deployment

### Frontend (Vercel)
1. Import repository into [Vercel](https://vercel.com).
2. Set root directory to `frontend`.
3. Configure environment variable:
   - `NEXT_PUBLIC_API_URL=https://<your-backend-railway-domain>`
   - `NEXT_PUBLIC_PRODUCT_NAME="MoodAudio Studio"`
4. Deploy!

### Backend (Railway)
1. Create a new project in [Railway](https://railway.app).
2. Add a **PostgreSQL** database service.
3. Add a service from this GitHub repository pointing to `/backend`.
4. Railway will automatically detect `backend/Dockerfile` and `backend/railway.toml`.
5. Set environment variables:
   ```env
   PRODUCT_NAME="MoodAudio Studio"
   APP_ENV=production
   DATABASE_URL=${{Postgres.DATABASE_URL}}
   STORAGE_BACKEND=local
   FRONTEND_ORIGIN=https://<your-vercel-domain>
   ```
6. The backend healthcheck endpoint `/api/v1/health` verifies system readiness.

---

## 📻 Bedside Hardware Integration (EchoNode)

Processed audio files can be transferred directly to FAT32 MicroSD cards for the **EchoNode** bedside player:
- Sanitized FAT32 filenames (max 60 characters, no illegal characters).
- Stream-verified `.m4a` (AAC) or `.mp3` containers.
- Guaranteed zero video streams to prevent ESP32-S3 I2S decoder panics.
- Uncompromised RF-free playback on Waveshare ESP32-S3 with PCM5101 DAC.

### Physical Hardware Bench Gates (`docs/HARDWARE_VALIDATION_GATES.md`)
In compliance with strict engineering discipline, physical hardware bench gates are tracked individually and kept as **`PENDING`** until executed on bench hardware with logged evidence:

| Test ID | Gate Description | Target Hardware Component | Status |
| :--- | :--- | :--- | :---: |
| `TEST-HW-01` | Battery Connector Polarity (`RULE_POLARITY_CHECK`) | MX1.25 2-Pin Battery Port | ⏳ **PENDING** |
| `TEST-HW-02` | Dual Speaker & Audio Tone Sweep | Dual JST-PH 2.0 / PCM5101 I2S DAC + Amp | ⏳ **PENDING** |
| `TEST-HW-03` | MicroSD Mounting via TCA9554 EXIO3 CS | SPI Bus (`14, 16, 17`) + TCA9554 EXIO3 | ⏳ **PENDING** |
| `TEST-HW-04` | 50-Cycle Playback Lifecycle & Memory Stability | ESP32-S3 SRAM Heap & 8MB PSRAM | ⏳ **PENDING** |

For complete test protocols, safety directives, equipment requirements, and observation logs, refer to [docs/HARDWARE_VALIDATION_GATES.md](docs/HARDWARE_VALIDATION_GATES.md).

---

## 📄 License
This project is open-source under the [MIT License](LICENSE).
