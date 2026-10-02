"""SQLite-backed resumable storage for SAT tariff processing."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable

from .models import ProcessingState

SECTION_TABLES = {
    "rights": "rights_taxes_rows",
    "nomenclature": "nomenclature_rows",
    "restrictions": "restriction_rows",
    "quotas": "quota_rows",
}


class Storage:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.initialize()

    def close(self) -> None:
        self.connection.close()

    def initialize(self) -> None:
        with self.transaction() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS hs_codes (
                    code TEXT PRIMARY KEY,
                    raw_code TEXT NOT NULL,
                    state TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            for table_name in SECTION_TABLES.values():
                conn.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {table_name} (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        code TEXT NOT NULL,
                        row_index INTEGER NOT NULL,
                        section_status TEXT,
                        extracted_json TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        FOREIGN KEY(code) REFERENCES hs_codes(code) ON DELETE CASCADE
                    )
                    """
                )
                conn.execute(
                    f"CREATE INDEX IF NOT EXISTS idx_{table_name}_code ON {table_name}(code, row_index)"
                )

    @contextmanager
    def transaction(self):
        try:
            yield self.connection
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _serialize_row(row: Any) -> str:
        if is_dataclass(row):
            payload = asdict(row)
        elif isinstance(row, dict):
            payload = row
        else:
            raise TypeError(f"Unsupported row type: {type(row)!r}")
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

    def upsert_code(
        self,
        code: str,
        raw_code: str,
        state: ProcessingState = ProcessingState.pending,
        last_error: str | None = None,
    ) -> None:
        now = self._now()
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO hs_codes(code, raw_code, state, attempts, last_error, created_at, updated_at)
                VALUES(?, ?, ?, 0, ?, ?, ?)
                ON CONFLICT(code) DO UPDATE SET
                    raw_code=excluded.raw_code,
                    state=excluded.state,
                    last_error=excluded.last_error,
                    updated_at=excluded.updated_at
                """,
                (code, raw_code, state.value, last_error, now, now),
            )

    def update_state(self, code: str, state: ProcessingState, last_error: str | None = None) -> None:
        with self.transaction() as conn:
            conn.execute(
                "UPDATE hs_codes SET state = ?, last_error = ?, updated_at = ? WHERE code = ?",
                (state.value, last_error, self._now(), code),
            )

    def record_attempt(self, code: str, last_error: str | None = None) -> int:
        with self.transaction() as conn:
            conn.execute(
                "UPDATE hs_codes SET attempts = attempts + 1, last_error = ?, updated_at = ? WHERE code = ?",
                (last_error, self._now(), code),
            )
            row = conn.execute("SELECT attempts FROM hs_codes WHERE code = ?", (code,)).fetchone()
        return int(row[0]) if row else 0

    def save_section_rows(
        self,
        code: str,
        section: str,
        rows: Iterable[Any],
        *,
        section_status: str | None = None,
    ) -> None:
        table_name = SECTION_TABLES[section]
        serialized_rows = list(rows)
        now = self._now()
        with self.transaction() as conn:
            conn.execute(f"DELETE FROM {table_name} WHERE code = ?", (code,))
            for index, row in enumerate(serialized_rows):
                conn.execute(
                    f"INSERT INTO {table_name}(code, row_index, section_status, extracted_json, created_at) VALUES (?, ?, ?, ?, ?)",
                    (code, index, section_status, self._serialize_row(row), now),
                )
            if not serialized_rows:
                conn.execute(
                    f"INSERT INTO {table_name}(code, row_index, section_status, extracted_json, created_at) VALUES (?, ?, ?, ?, ?)",
                    (code, 0, section_status, json.dumps({}, ensure_ascii=False), now),
                )

    def load_all_for_export(self) -> list[dict[str, Any]]:
        codes = self.connection.execute(
            "SELECT code, raw_code, state, attempts, last_error FROM hs_codes ORDER BY code"
        ).fetchall()
        payload: list[dict[str, Any]] = []
        for code_row in codes:
            bundle = {
                "code": code_row["code"],
                "raw_code": code_row["raw_code"],
                "state": code_row["state"],
                "attempts": code_row["attempts"],
                "last_error": code_row["last_error"],
            }
            for section, table_name in SECTION_TABLES.items():
                rows = self.connection.execute(
                    f"SELECT row_index, section_status, extracted_json FROM {table_name} WHERE code = ? ORDER BY row_index",
                    (code_row["code"],),
                ).fetchall()
                parsed_rows = [json.loads(row["extracted_json"]) for row in rows if row["extracted_json"] != "{}"]
                section_status = next((row["section_status"] for row in rows if row["section_status"]), None)
                bundle[section] = {
                    "rows": parsed_rows,
                    "status": section_status,
                }
            payload.append(bundle)
        return payload

    def get_status_summary(self) -> dict[str, int]:
        rows = self.connection.execute(
            "SELECT state, COUNT(*) AS total FROM hs_codes GROUP BY state ORDER BY state"
        ).fetchall()
        return {row["state"]: row["total"] for row in rows}

    def get_codes_to_resume(self) -> list[sqlite3.Row]:
        return self.connection.execute(
            """
            SELECT code, raw_code, state, attempts, last_error
            FROM hs_codes
            WHERE state NOT IN (?, ?)
            ORDER BY created_at, code
            """,
            (ProcessingState.completed.value, ProcessingState.permanent_error.value),
        ).fetchall()

    def get_processed_sections(self, code: str) -> set[str]:
        processed: set[str] = set()
        for section, table_name in SECTION_TABLES.items():
            row = self.connection.execute(
                f"SELECT 1 FROM {table_name} WHERE code = ? LIMIT 1",
                (code,),
            ).fetchone()
            if row is not None:
                processed.add(section)
        return processed

    def get_code(self, code: str) -> sqlite3.Row | None:
        return self.connection.execute(
            "SELECT code, raw_code, state, attempts, last_error, created_at, updated_at FROM hs_codes WHERE code = ?",
            (code,),
        ).fetchone()

    def reset_states(self, states: Iterable[ProcessingState], target_state: ProcessingState = ProcessingState.pending) -> int:
        state_values = [state.value for state in states]
        if not state_values:
            return 0
        placeholders = ",".join("?" for _ in state_values)
        with self.transaction() as conn:
            cursor = conn.execute(
                f"UPDATE hs_codes SET state = ?, last_error = NULL, updated_at = ? WHERE state IN ({placeholders})",
                [target_state.value, self._now(), *state_values],
            )
        return cursor.rowcount
