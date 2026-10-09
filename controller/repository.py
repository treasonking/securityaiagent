from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Any

from common.sanitize import sanitize
from common.schemas import Evidence, RunReport, RunStatus, utc_now


class Repository:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS conversations (
                    conversation_id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    message_id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id) ON DELETE CASCADE,
                    owner_id TEXT NOT NULL,
                    scenario_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    provider_mode TEXT NOT NULL,
                    tool_transport TEXT NOT NULL,
                    status TEXT NOT NULL,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    report_json TEXT,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT
                );
                CREATE TABLE IF NOT EXISTS run_events (
                    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                    event_id INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (run_id, event_id)
                );
                CREATE TABLE IF NOT EXISTS findings (
                    finding_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                    finding_type TEXT NOT NULL,
                    verdict TEXT NOT NULL,
                    details_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS evidence_metadata (
                    evidence_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS controller_sessions (
                    nonce_hash TEXT PRIMARY KEY,
                    expires_at INTEGER NOT NULL,
                    revoked_at TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_version(version, applied_at) VALUES (?, ?)", (1, utc_now())
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_version(version, applied_at) VALUES (?, ?)", (2, utc_now())
            )

    def register_session(self, nonce_hash: str, expires_at: int, now: int) -> None:
        with self._write_lock, self._connect() as connection:
            connection.execute("DELETE FROM controller_sessions WHERE expires_at<=?", (now,))
            connection.execute(
                """
                INSERT INTO controller_sessions(nonce_hash, expires_at, revoked_at, created_at)
                VALUES (?, ?, NULL, ?)
                """,
                (nonce_hash, expires_at, utc_now()),
            )

    def session_is_active(self, nonce_hash: str, expires_at: int, now: int) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT 1 FROM controller_sessions
                WHERE nonce_hash=? AND expires_at=? AND expires_at>? AND revoked_at IS NULL
                """,
                (nonce_hash, expires_at, now),
            ).fetchone()
            return row is not None

    def revoke_session(self, nonce_hash: str, expires_at: int) -> None:
        with self._write_lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE controller_sessions SET revoked_at=?
                WHERE nonce_hash=? AND expires_at=?
                """,
                (utc_now(), nonce_hash, expires_at),
            )

    def journal_mode(self) -> str:
        with self._connect() as connection:
            return str(connection.execute("PRAGMA journal_mode").fetchone()[0]).lower()

    def interrupt_unfinished_runs(self) -> int:
        with self._write_lock, self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE runs SET status=?, finished_at=?, error_message=?
                WHERE status IN (?, ?)
                """,
                (
                    RunStatus.INTERRUPTED,
                    utc_now(),
                    "controller restarted before completion",
                    RunStatus.QUEUED,
                    RunStatus.RUNNING,
                ),
            )
            return cursor.rowcount

    def create_conversation(self, owner_id: str, title: str = "새 보안 검증") -> dict[str, Any]:
        conversation_id = f"conv_{uuid.uuid4().hex}"
        created_at = utc_now()
        with self._write_lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO conversations(conversation_id, owner_id, title, created_at) VALUES (?, ?, ?, ?)",
                (conversation_id, owner_id, str(sanitize(title))[:120], created_at),
            )
        return {"conversation_id": conversation_id, "title": str(sanitize(title))[:120], "created_at": created_at}

    def list_conversations(self, owner_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT conversation_id, title, created_at FROM conversations WHERE owner_id=? ORDER BY created_at DESC",
                (owner_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def conversation_owned(self, conversation_id: str, owner_id: str) -> bool:
        with self._connect() as connection:
            return (
                connection.execute(
                    "SELECT 1 FROM conversations WHERE conversation_id=? AND owner_id=?",
                    (conversation_id, owner_id),
                ).fetchone()
                is not None
            )

    def add_message(self, conversation_id: str, role: str, content: str) -> dict[str, Any]:
        message_id = f"msg_{uuid.uuid4().hex}"
        created_at = utc_now()
        safe_content = str(sanitize(content))
        with self._write_lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO messages(message_id, conversation_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
                (message_id, conversation_id, role, safe_content, created_at),
            )
        return {
            "message_id": message_id,
            "conversation_id": conversation_id,
            "role": role,
            "content": safe_content,
            "created_at": created_at,
        }

    def list_messages(self, conversation_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT message_id, conversation_id, role, content, created_at FROM messages WHERE conversation_id=? ORDER BY created_at, message_id",
                (conversation_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def create_run(
        self,
        *,
        conversation_id: str,
        owner_id: str,
        scenario_id: str,
        target_id: str,
        provider_mode: str,
        tool_transport: str,
    ) -> str:
        run_id = f"run_{uuid.uuid4().hex}"
        with self._write_lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO runs(
                    run_id, conversation_id, owner_id, scenario_id, target_id, provider_mode,
                    tool_transport, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    conversation_id,
                    owner_id,
                    scenario_id,
                    target_id,
                    provider_mode,
                    tool_transport,
                    RunStatus.QUEUED,
                    utc_now(),
                ),
            )
        return run_id

    def update_run_status(
        self,
        run_id: str,
        status: RunStatus,
        *,
        error_message: str | None = None,
        report: RunReport | None = None,
    ) -> None:
        started_at = utc_now() if status == RunStatus.RUNNING else None
        finished_at = utc_now() if status in {
            RunStatus.COMPLETED,
            RunStatus.CANCELLED,
            RunStatus.TIMED_OUT,
            RunStatus.FAILED,
            RunStatus.INTERRUPTED,
        } else None
        with self._write_lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE runs SET status=?,
                    started_at=COALESCE(started_at, ?),
                    finished_at=COALESCE(?, finished_at),
                    error_message=?, report_json=COALESCE(?, report_json)
                WHERE run_id=?
                """,
                (
                    status,
                    started_at,
                    finished_at,
                    str(sanitize(error_message)) if error_message else None,
                    report.model_dump_json() if report else None,
                    run_id,
                ),
            )

    def request_cancel(self, run_id: str, owner_id: str) -> bool:
        with self._write_lock, self._connect() as connection:
            cursor = connection.execute(
                "UPDATE runs SET cancel_requested=1 WHERE run_id=? AND owner_id=? AND status IN (?, ?)",
                (run_id, owner_id, RunStatus.QUEUED, RunStatus.RUNNING),
            )
            return cursor.rowcount == 1

    def is_cancel_requested(self, run_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT cancel_requested FROM runs WHERE run_id=?", (run_id,)
            ).fetchone()
            return bool(row and row["cancel_requested"])

    def complete_run(self, run_id: str, report: RunReport) -> bool:
        with self._write_lock, self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE runs SET status=?, finished_at=?, error_message=NULL, report_json=?
                WHERE run_id=? AND status=? AND cancel_requested=0
                """,
                (
                    RunStatus.COMPLETED,
                    utc_now(),
                    report.model_dump_json(),
                    run_id,
                    RunStatus.RUNNING,
                ),
            )
            return cursor.rowcount == 1

    def get_run(self, run_id: str, owner_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM runs WHERE run_id=? AND owner_id=?", (run_id, owner_id)
            ).fetchone()
            if row is None:
                return None
            result = dict(row)
            result["report"] = json.loads(result.pop("report_json")) if result.get("report_json") else None
            result["cancel_requested"] = bool(result["cancel_requested"])
            return result

    def get_run_internal(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if row is None:
                return None
            result = dict(row)
            result["report"] = json.loads(result.pop("report_json")) if result.get("report_json") else None
            result["cancel_requested"] = bool(result["cancel_requested"])
            return result

    def update_run_report(self, run_id: str, report: RunReport) -> None:
        with self._write_lock, self._connect() as connection:
            connection.execute(
                "UPDATE runs SET report_json=? WHERE run_id=? AND status=?",
                (report.model_dump_json(), run_id, RunStatus.COMPLETED),
            )

    def list_runs(self, conversation_id: str, owner_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM runs
                WHERE conversation_id=? AND owner_id=?
                ORDER BY created_at DESC, run_id DESC
                """,
                (conversation_id, owner_id),
            ).fetchall()
            results: list[dict[str, Any]] = []
            for row in rows:
                item = dict(row)
                item["report"] = json.loads(item.pop("report_json")) if item.get("report_json") else None
                item["cancel_requested"] = bool(item["cancel_requested"])
                results.append(item)
            return results

    def append_event(self, run_id: str, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        safe_payload = sanitize(payload)
        with self._write_lock, self._connect() as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(event_id), 0) + 1 FROM run_events WHERE run_id=?", (run_id,)
            ).fetchone()
            event_id = int(row[0])
            created_at = utc_now()
            connection.execute(
                "INSERT INTO run_events(run_id, event_id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (run_id, event_id, event_type, json.dumps(safe_payload, ensure_ascii=False), created_at),
            )
        return {
            "run_id": run_id,
            "event_id": event_id,
            "event_type": event_type,
            "payload": safe_payload,
            "created_at": created_at,
        }

    def list_events(self, run_id: str, after: int = 0) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT event_id, event_type, payload_json, created_at FROM run_events WHERE run_id=? AND event_id>? ORDER BY event_id",
                (run_id, after),
            ).fetchall()
            return [
                {
                    "run_id": run_id,
                    "event_id": row["event_id"],
                    "event_type": row["event_type"],
                    "payload": json.loads(row["payload_json"]),
                    "created_at": row["created_at"],
                }
                for row in rows
            ]

    def save_evidence(self, evidence: Evidence) -> None:
        with self._write_lock, self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO evidence_metadata(evidence_id, run_id, metadata_json, created_at) VALUES (?, ?, ?, ?)",
                (evidence.evidence_id, evidence.run_id, evidence.model_dump_json(), evidence.created_at),
            )

    def list_evidence(self, run_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT metadata_json FROM evidence_metadata WHERE run_id=? ORDER BY created_at, evidence_id", (run_id,)
            ).fetchall()
            return [json.loads(row["metadata_json"]) for row in rows]

    def mark_evidence_offline_correlated(self, run_id: str) -> None:
        with self._write_lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT evidence_id, metadata_json FROM evidence_metadata WHERE run_id=?",
                (run_id,),
            ).fetchall()
            for row in rows:
                item = Evidence.model_validate_json(row["metadata_json"])
                item.server_observation = "target_log_correlated"
                connection.execute(
                    "UPDATE evidence_metadata SET metadata_json=? WHERE evidence_id=?",
                    (item.model_dump_json(), row["evidence_id"]),
                )

    def save_findings(self, report: RunReport) -> None:
        with self._write_lock, self._connect() as connection:
            connection.execute("DELETE FROM findings WHERE run_id=?", (report.run_id,))
            for finding in report.verified_findings:
                connection.execute(
                    "INSERT INTO findings(finding_id, run_id, finding_type, verdict, details_json) VALUES (?, ?, ?, ?, ?)",
                    (
                        f"finding_{uuid.uuid4().hex}",
                        report.run_id,
                        finding.finding_type,
                        finding.verdict,
                        finding.model_dump_json(),
                    ),
                )
