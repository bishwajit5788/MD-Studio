import json
import logging
import os
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
from ..config import settings
from ..models import (
    JobDetailResponse,
    JobStage,
    ProcessingMode,
    OutputFormat,
    SourceType,
    AudioAnalysisReport,
    ValidationResult
)
from .job_store import sanitize_error_message

logger = logging.getLogger("moodaudio.database")

class DatabaseJobStore:
    """
    Unified database repository supporting Railway PostgreSQL and local SQLite.
    Stores comprehensive audio job records, analysis reports, and validation verdicts.
    """
    def __init__(self, db_url: Optional[str] = None):
        self.lock = threading.Lock()
        self.db_url = db_url or settings.database_url
        self.is_postgres = bool(
            self.db_url and (
                self.db_url.startswith("postgres://") or
                self.db_url.startswith("postgresql://")
            )
        )
        self._sqlite_conn: Optional[sqlite3.Connection] = None
        self._sqlite_path: str = ""

        if not self.is_postgres:
            try:
                db_dir = settings.downloads_dir
                db_dir.mkdir(parents=True, exist_ok=True)
                self._sqlite_path = str(db_dir / "moodaudio_jobs.db")
            except Exception:
                self._sqlite_path = ":memory:"

        self._init_schema()

    def _get_sqlite_conn(self) -> sqlite3.Connection:
        if self._sqlite_conn is None:
            self._sqlite_conn = sqlite3.connect(self._sqlite_path, check_same_thread=False)
            self._sqlite_conn.row_factory = sqlite3.Row
        return self._sqlite_conn

    def _get_pg_conn(self):
        import psycopg2
        import psycopg2.extras
        return psycopg2.connect(self.db_url)

    def close(self):
        with self.lock:
            if self._sqlite_conn is not None:
                try:
                    self._sqlite_conn.close()
                except Exception:
                    pass
                self._sqlite_conn = None

    def _init_schema(self):
        with self.lock:
            if self.is_postgres:
                try:
                    import psycopg2
                    with self._get_pg_conn() as conn:
                        with conn.cursor() as cur:
                            cur.execute("""
                                CREATE TABLE IF NOT EXISTS studio_jobs (
                                    job_id VARCHAR(64) PRIMARY KEY,
                                    product_name VARCHAR(64) NOT NULL,
                                    source_type VARCHAR(32) NOT NULL,
                                    source_filename TEXT,
                                    source_url TEXT,
                                    processing_mode VARCHAR(32) NOT NULL,
                                    requested_format VARCHAR(16) NOT NULL,
                                    status VARCHAR(32) NOT NULL,
                                    current_stage VARCHAR(64) NOT NULL,
                                    stages_completed TEXT NOT NULL,
                                    progress REAL NOT NULL DEFAULT 0.0,
                                    raw_analysis_json TEXT,
                                    restored_analysis_json TEXT,
                                    validation_result_json TEXT,
                                    original_preview_url TEXT,
                                    processed_preview_url TEXT,
                                    download_url TEXT,
                                    output_filename TEXT,
                                    output_file_size BIGINT,
                                    error TEXT,
                                    created_at DOUBLE PRECISION NOT NULL,
                                    updated_at DOUBLE PRECISION NOT NULL,
                                    completed_at DOUBLE PRECISION,
                                    expires_at DOUBLE PRECISION,
                                    retry_count INT DEFAULT 0
                                );
                                CREATE INDEX IF NOT EXISTS idx_studio_jobs_status ON studio_jobs(status);
                                CREATE INDEX IF NOT EXISTS idx_studio_jobs_created ON studio_jobs(created_at DESC);
                            """)
                        conn.commit()
                    logger.info("Connected to PostgreSQL database and initialized schema.")
                    return
                except Exception as e:
                    logger.warning(f"PostgreSQL initialization failed ({e}), falling back to SQLite.")
                    self.is_postgres = False
                    self._sqlite_path = str(settings.downloads_dir / "moodaudio_jobs.db")

            # SQLite initialization
            try:
                conn = self._get_sqlite_conn()
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS studio_jobs (
                        job_id TEXT PRIMARY KEY,
                        product_name TEXT NOT NULL,
                        source_type TEXT NOT NULL,
                        source_filename TEXT,
                        source_url TEXT,
                        processing_mode TEXT NOT NULL,
                        requested_format TEXT NOT NULL,
                        status TEXT NOT NULL,
                        current_stage TEXT NOT NULL,
                        stages_completed TEXT NOT NULL,
                        progress REAL NOT NULL DEFAULT 0.0,
                        raw_analysis_json TEXT,
                        restored_analysis_json TEXT,
                        validation_result_json TEXT,
                        original_preview_url TEXT,
                        processed_preview_url TEXT,
                        download_url TEXT,
                        output_filename TEXT,
                        output_file_size INTEGER,
                        error TEXT,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL,
                        completed_at REAL,
                        expires_at REAL,
                        retry_count INTEGER DEFAULT 0
                    );
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_studio_jobs_created ON studio_jobs(created_at DESC);")
                conn.commit()
            except Exception as e:
                logger.error(f"SQLite initialization failed: {e}")

    def save_job(self, job: JobDetailResponse) -> None:
        stages_str = json.dumps(job.stages_completed)
        raw_analysis_str = job.raw_analysis.model_dump_json() if job.raw_analysis else None
        restored_analysis_str = job.restored_analysis.model_dump_json() if job.restored_analysis else None
        validation_str = job.validation_result.model_dump_json() if job.validation_result else None
        cleaned_error = sanitize_error_message(job.error)

        with self.lock:
            if self.is_postgres:
                try:
                    with self._get_pg_conn() as conn:
                        with conn.cursor() as cur:
                            cur.execute("""
                                INSERT INTO studio_jobs (
                                    job_id, product_name, source_type, source_filename, source_url,
                                    processing_mode, requested_format, status, current_stage, stages_completed,
                                    progress, raw_analysis_json, restored_analysis_json, validation_result_json,
                                    original_preview_url, processed_preview_url, download_url, output_filename,
                                    output_file_size, error, created_at, updated_at, completed_at, expires_at, retry_count
                                ) VALUES (
                                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                                )
                                ON CONFLICT (job_id) DO UPDATE SET
                                    product_name = EXCLUDED.product_name,
                                    status = EXCLUDED.status,
                                    current_stage = EXCLUDED.current_stage,
                                    stages_completed = EXCLUDED.stages_completed,
                                    progress = EXCLUDED.progress,
                                    raw_analysis_json = EXCLUDED.raw_analysis_json,
                                    restored_analysis_json = EXCLUDED.restored_analysis_json,
                                    validation_result_json = EXCLUDED.validation_result_json,
                                    original_preview_url = EXCLUDED.original_preview_url,
                                    processed_preview_url = EXCLUDED.processed_preview_url,
                                    download_url = EXCLUDED.download_url,
                                    output_filename = EXCLUDED.output_filename,
                                    output_file_size = EXCLUDED.output_file_size,
                                    error = EXCLUDED.error,
                                    updated_at = EXCLUDED.updated_at,
                                    completed_at = EXCLUDED.completed_at,
                                    expires_at = EXCLUDED.expires_at,
                                    retry_count = EXCLUDED.retry_count;
                            """, (
                                job.job_id, job.product_name, job.source_type.value, job.source_filename, job.source_url,
                                job.processing_mode.value, job.requested_format.value, job.status.value, job.current_stage,
                                stages_str, job.progress, raw_analysis_str, restored_analysis_str, validation_str,
                                job.original_preview_url, job.processed_preview_url, job.download_url, job.output_filename,
                                job.output_file_size, cleaned_error, job.created_at, job.updated_at, job.completed_at,
                                job.expires_at, job.retry_count
                            ))
                        conn.commit()
                    return
                except Exception as e:
                    logger.error(f"PostgreSQL save_job failed: {e}")

            # SQLite fallback
            conn = self._get_sqlite_conn()
            conn.execute("""
                INSERT OR REPLACE INTO studio_jobs (
                    job_id, product_name, source_type, source_filename, source_url,
                    processing_mode, requested_format, status, current_stage, stages_completed,
                    progress, raw_analysis_json, restored_analysis_json, validation_result_json,
                    original_preview_url, processed_preview_url, download_url, output_filename,
                    output_file_size, error, created_at, updated_at, completed_at, expires_at, retry_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job.job_id, job.product_name, job.source_type.value, job.source_filename, job.source_url,
                job.processing_mode.value, job.requested_format.value, job.status.value, job.current_stage,
                stages_str, job.progress, raw_analysis_str, restored_analysis_str, validation_str,
                job.original_preview_url, job.processed_preview_url, job.download_url, job.output_filename,
                job.output_file_size, cleaned_error, job.created_at, job.updated_at, job.completed_at,
                job.expires_at, job.retry_count
            ))
            conn.commit()

    def _row_to_job(self, row: Any) -> JobDetailResponse:
        stages = []
        try:
            stages = json.loads(row["stages_completed"]) if row["stages_completed"] else []
        except Exception:
            pass

        raw_analysis = None
        if row["raw_analysis_json"]:
            try:
                raw_analysis = AudioAnalysisReport.model_validate_json(row["raw_analysis_json"])
            except Exception:
                pass

        restored_analysis = None
        if row["restored_analysis_json"]:
            try:
                restored_analysis = AudioAnalysisReport.model_validate_json(row["restored_analysis_json"])
            except Exception:
                pass

        validation_result = None
        if row["validation_result_json"]:
            try:
                validation_result = ValidationResult.model_validate_json(row["validation_result_json"])
            except Exception:
                pass

        status_enum = JobStage(row["status"])
        can_retry = status_enum in (JobStage.FAILED, JobStage.CANCELLED)
        can_cancel = status_enum in (JobStage.QUEUED, JobStage.VALIDATING, JobStage.EXTRACTING, JobStage.ANALYZING, JobStage.RESTORING, JobStage.RENDERING)

        return JobDetailResponse(
            job_id=row["job_id"],
            product_name=row["product_name"],
            source_type=SourceType(row["source_type"]),
            source_filename=row["source_filename"],
            source_url=row["source_url"],
            processing_mode=ProcessingMode(row["processing_mode"]),
            requested_format=OutputFormat(row["requested_format"]),
            status=status_enum,
            current_stage=row["current_stage"],
            stages_completed=stages,
            progress=row["progress"],
            raw_analysis=raw_analysis,
            restored_analysis=restored_analysis,
            validation_result=validation_result,
            original_preview_url=row["original_preview_url"],
            processed_preview_url=row["processed_preview_url"],
            download_url=row["download_url"],
            output_filename=row["output_filename"],
            output_file_size=row["output_file_size"],
            error=row["error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            completed_at=row["completed_at"],
            expires_at=row["expires_at"],
            retry_count=row["retry_count"] or 0,
            can_retry=can_retry,
            can_cancel=can_cancel
        )

    def get_job(self, job_id: str) -> Optional[JobDetailResponse]:
        with self.lock:
            if self.is_postgres:
                try:
                    import psycopg2.extras
                    with self._get_pg_conn() as conn:
                        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                            cur.execute("SELECT * FROM studio_jobs WHERE job_id = %s", (job_id,))
                            row = cur.fetchone()
                            if row:
                                return self._row_to_job(dict(row))
                            return None
                except Exception as e:
                    logger.error(f"PostgreSQL get_job failed: {e}")

            conn = self._get_sqlite_conn()
            cur = conn.execute("SELECT * FROM studio_jobs WHERE job_id = ?", (job_id,))
            row = cur.fetchone()
            if not row:
                return None
            return self._row_to_job(row)

    def list_jobs(self, limit: int = 50) -> List[JobDetailResponse]:
        with self.lock:
            if self.is_postgres:
                try:
                    import psycopg2.extras
                    with self._get_pg_conn() as conn:
                        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                            cur.execute("SELECT * FROM studio_jobs ORDER BY created_at DESC LIMIT %s", (limit,))
                            rows = cur.fetchall()
                            return [self._row_to_job(dict(r)) for r in rows]
                except Exception as e:
                    logger.error(f"PostgreSQL list_jobs failed: {e}")

            conn = self._get_sqlite_conn()
            cur = conn.execute("SELECT * FROM studio_jobs ORDER BY created_at DESC LIMIT ?", (limit,))
            rows = cur.fetchall()
            return [self._row_to_job(r) for r in rows]

    def delete_job(self, job_id: str) -> bool:
        with self.lock:
            if self.is_postgres:
                try:
                    with self._get_pg_conn() as conn:
                        with conn.cursor() as cur:
                            cur.execute("DELETE FROM studio_jobs WHERE job_id = %s", (job_id,))
                            cnt = cur.rowcount
                        conn.commit()
                        return cnt > 0
                except Exception as e:
                    logger.error(f"PostgreSQL delete_job failed: {e}")

            conn = self._get_sqlite_conn()
            cur = conn.execute("DELETE FROM studio_jobs WHERE job_id = ?", (job_id,))
            conn.commit()
            return cur.rowcount > 0

database_job_store = DatabaseJobStore()
