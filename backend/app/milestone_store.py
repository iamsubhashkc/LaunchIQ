from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb

from .config import MILESTONE_DELIVERABLES_JSON, MILESTONE_DUCKDB


MILESTONE_FIELDS = [
    "milestone_code",
    "milestone_label",
    "sequence_order",
    "governance_communication",
    "readiness_objectives",
    "timelines",
    "risks",
    "escalation_path",
    "ownership",
    "updated_at",
]


class MilestoneStore:
    def __init__(
        self,
        seed_path: Path = MILESTONE_DELIVERABLES_JSON,
        duckdb_path: Path = MILESTONE_DUCKDB,
    ) -> None:
        self.seed_path = seed_path
        self.duckdb_path = duckdb_path
        self.duckdb_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_duckdb()
        self._seed_if_empty()

    def _initialize_duckdb(self) -> None:
        connection = duckdb.connect(str(self.duckdb_path))
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS milestone_deliverables (
                milestone_code VARCHAR PRIMARY KEY,
                milestone_label VARCHAR NOT NULL,
                sequence_order INTEGER NOT NULL,
                governance_communication VARCHAR,
                readiness_objectives VARCHAR,
                timelines VARCHAR,
                risks VARCHAR,
                escalation_path VARCHAR,
                ownership VARCHAR,
                updated_at TIMESTAMP NOT NULL
            )
            """
        )
        connection.close()

    def _seed_if_empty(self) -> None:
        connection = duckdb.connect(str(self.duckdb_path))
        count = connection.execute("SELECT COUNT(*) FROM milestone_deliverables").fetchone()[0]
        if count:
            connection.close()
            return

        rows = json.loads(self.seed_path.read_text(encoding="utf-8"))
        now = datetime.now(timezone.utc)
        for row in rows:
            connection.execute(
                """
                INSERT INTO milestone_deliverables
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    row["milestone_code"],
                    row["milestone_label"],
                    row["sequence_order"],
                    row["governance_communication"],
                    row["readiness_objectives"],
                    row["timelines"],
                    row["risks"],
                    row["escalation_path"],
                    row["ownership"],
                    now,
                ],
            )
        connection.close()

    def list_deliverables(self) -> list[dict[str, Any]]:
        connection = duckdb.connect(str(self.duckdb_path))
        rows = connection.execute(
            """
            SELECT milestone_code, milestone_label, sequence_order, governance_communication,
                   readiness_objectives, timelines, risks, escalation_path, ownership, updated_at
            FROM milestone_deliverables
            ORDER BY sequence_order, milestone_code
            """
        ).fetchdf()
        connection.close()
        return rows.to_dict(orient="records")

    def get_deliverable(self, milestone_code: str) -> dict[str, Any] | None:
        normalized_code = self.normalize_code(milestone_code)
        connection = duckdb.connect(str(self.duckdb_path))
        row = connection.execute(
            """
            SELECT milestone_code, milestone_label, sequence_order, governance_communication,
                   readiness_objectives, timelines, risks, escalation_path, ownership, updated_at
            FROM milestone_deliverables
            WHERE milestone_code = ?
            """,
            [normalized_code],
        ).fetchdf()
        connection.close()
        if row.empty:
            return None
        return row.iloc[0].to_dict()

    def get_deliverables(self, milestone_codes: list[str]) -> list[dict[str, Any]]:
        normalized_codes = [self.normalize_code(code) for code in milestone_codes if code]
        if not normalized_codes:
            return []
        connection = duckdb.connect(str(self.duckdb_path))
        placeholders = ", ".join(["?"] * len(normalized_codes))
        rows = connection.execute(
            f"""
            SELECT milestone_code, milestone_label, sequence_order, governance_communication,
                   readiness_objectives, timelines, risks, escalation_path, ownership, updated_at
            FROM milestone_deliverables
            WHERE milestone_code IN ({placeholders})
            ORDER BY sequence_order, milestone_code
            """,
            normalized_codes,
        ).fetchdf()
        connection.close()
        return rows.to_dict(orient="records")

    def upsert_deliverable(self, milestone_code: str, payload: dict[str, Any]) -> dict[str, Any]:
        normalized_code = self.normalize_code(milestone_code)
        current = self.get_deliverable(normalized_code)
        updated_at = datetime.now(timezone.utc)
        record = {
            "milestone_code": normalized_code,
            "milestone_label": payload.get("milestone_label") or (current["milestone_label"] if current else normalized_code),
            "sequence_order": payload.get("sequence_order") if payload.get("sequence_order") is not None else (current["sequence_order"] if current else 999),
            "governance_communication": payload.get("governance_communication")
            if payload.get("governance_communication") is not None
            else (current["governance_communication"] if current else ""),
            "readiness_objectives": payload.get("readiness_objectives")
            if payload.get("readiness_objectives") is not None
            else (current["readiness_objectives"] if current else ""),
            "timelines": payload.get("timelines") if payload.get("timelines") is not None else (current["timelines"] if current else ""),
            "risks": payload.get("risks") if payload.get("risks") is not None else (current["risks"] if current else ""),
            "escalation_path": payload.get("escalation_path")
            if payload.get("escalation_path") is not None
            else (current["escalation_path"] if current else ""),
            "ownership": payload.get("ownership") if payload.get("ownership") is not None else (current["ownership"] if current else ""),
            "updated_at": updated_at,
        }

        connection = duckdb.connect(str(self.duckdb_path))
        connection.execute(
            """
            INSERT OR REPLACE INTO milestone_deliverables
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                record["milestone_code"],
                record["milestone_label"],
                record["sequence_order"],
                record["governance_communication"],
                record["readiness_objectives"],
                record["timelines"],
                record["risks"],
                record["escalation_path"],
                record["ownership"],
                updated_at,
            ],
        )
        connection.close()
        return record

    @staticmethod
    def normalize_code(value: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9]+", "_", value.strip().upper()).strip("_")
        return cleaned or value.strip().upper()
