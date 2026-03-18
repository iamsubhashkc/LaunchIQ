from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb

from .config import LEARNING_DUCKDB, LEARNING_JSONL


class LearningStore:
    def __init__(self, jsonl_path: Path = LEARNING_JSONL, duckdb_path: Path = LEARNING_DUCKDB) -> None:
        self.jsonl_path = jsonl_path
        self.duckdb_path = duckdb_path
        self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_duckdb()

    def _initialize_duckdb(self) -> None:
        connection = duckdb.connect(str(self.duckdb_path))
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS learning_feedback (
                record_id VARCHAR PRIMARY KEY,
                stored_at TIMESTAMP,
                query_text VARCHAR,
                plan_json JSON,
                answer_json JSON,
                rating VARCHAR,
                correction VARCHAR
            )
            """
        )
        connection.close()

    def store_feedback(self, query: str, plan: dict[str, Any], answer: Any, rating: str, correction: str | None) -> dict[str, Any]:
        stored_at = datetime.now(timezone.utc)
        record_id = str(uuid.uuid4())
        payload = {
            "record_id": record_id,
            "stored_at": stored_at.isoformat(),
            "query": query,
            "plan": plan,
            "answer": answer,
            "rating": rating,
            "correction": correction,
        }

        with self.jsonl_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload) + "\n")

        connection = duckdb.connect(str(self.duckdb_path))
        connection.execute(
            """
            INSERT INTO learning_feedback
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                record_id,
                stored_at,
                query,
                json.dumps(plan),
                json.dumps(answer),
                rating,
                correction,
            ],
        )
        connection.close()
        return {"record_id": record_id, "stored_at": stored_at}

