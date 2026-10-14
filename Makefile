.PHONY: help install run-backend dev-backend dev-frontend build-frontend test test-backend audit-pins check-partitions test-tones verify-sd build-firmware flash-firmware flash-diagnostics monitor docker-up docker-down

PYTHON := backend/.venv/bin/python
PIP := backend/.venv/bin/pip

help:
	@echo "MoodAudio Studio / EchoNode Developer Commands:"
	@echo "  make dev-backend        - Start FastAPI backend with uvicorn reload on http://localhost:8000"
	@echo "  make dev-frontend       - Start Next.js DAW interface on http://localhost:3000"
	@echo "  make build-frontend     - Compile optimized production Next.js application"
	@echo "  make test               - Run full pytest suite across all audio DSP, API, and validation services"
	@echo "  make docker-up          - Launch complete multi-tier stack (Frontend, API, Postgres, Worker)"
	@echo "  make docker-down        - Stop docker-compose stack"
	@echo "  make install            - Initialize backend virtual environment and dependencies"
	@echo "  make audit-pins         - Verify hardware pin definitions against authoritative Waveshare original spec"
	@echo "  make check-partitions   - Verify 4KB/64KB flash partition alignments and overlaps"
	@echo "  make run-backend        - Start the legacy FastAPI extraction hub on http://localhost:8000"
	@echo "  make test-backend       - Run legacy backend unit tests and audio-only validation"
	@echo "  make test-tones         - Generate uncompressed hardware test tones in backend/downloads/"
	@echo "  make verify-sd          - Check and benchmark connected MicroSD card (default: /Volumes/ECHONODE)"
	@echo "  make build-firmware     - Compile main ESP32-S3 firmware with PlatformIO"
	@echo "  make flash-firmware     - Upload firmware to connected Waveshare ESP32-S3 via USB-C"
	@echo "  make flash-diagnostics  - Upload on-board hardware diagnostic self-test to ESP32-S3"
	@echo "  make monitor            - Open serial monitor at 115200 baud"

dev-backend:
	uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000

dev-frontend:
	cd frontend && npm run dev

build-frontend:
	cd frontend && npm run build

test:
	pytest -v backend/tests

docker-up:
	docker compose up --build

docker-down:
	docker compose down

install:
	@python3 -m venv backend/.venv
	@$(PIP) install --upgrade pip
	@$(PIP) install -r backend/requirements.txt
	@echo "✓ Virtual environment initialized in backend/.venv"

audit-pins:
	@python3 tools/audit_pin_mappings.py

check-partitions:
	@python3 tools/check_partitions.py firmware/partitions_16MB.csv

run-backend:
	@$(PYTHON) backend/run.py

run-worker:
	@$(PYTHON) backend/worker.py

test-backend: audit-pins check-partitions
	@$(PYTHON) backend/tests/test_job_store.py
	@$(PYTHON) backend/tests/test_storage.py
	@$(PYTHON) backend/tests/test_backend.py
	@$(PYTHON) backend/tests/test_audio_only.py
	@$(PYTHON) backend/tests/test_phase7_verification.py

test-tones:
	@$(PYTHON) tools/generate_test_tones.py

verify-sd:
	@$(PYTHON) tools/sd_card_verifier.py /Volumes/ECHONODE

build-firmware:
	@cd firmware && pio run -e waveshare_esp32s3_round

flash-firmware:
	@cd firmware && pio run -e waveshare_esp32s3_round --target upload

flash-diagnostics:
	@cd firmware && pio run -e diagnostics --target upload

monitor:
	@cd firmware && pio run --target monitor
