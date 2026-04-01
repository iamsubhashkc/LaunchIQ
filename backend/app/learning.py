from __future__ import annotations

import json
import re
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

    def relevant_feedback(self, query: str, limit: int = 3) -> list[dict[str, Any]]:
        rows = self._load_feedback_rows(limit=250)
        normalized_query = self._normalize_query(query)
        query_tokens = self._query_tokens(query)
        ranked: list[dict[str, Any]] = []

        for row in rows:
            normalized_row = self._normalize_query(str(row.get("query", "")))
            match_type = "exact" if normalized_row == normalized_query and normalized_query else "similar"
            overlap = len(query_tokens & self._query_tokens(str(row.get("query", ""))))
            score = 0.0
            if match_type == "exact":
                score += 10.0
            score += overlap
            if row.get("rating") in {"incorrect", "needs_more_detail"}:
                score += 2.0
            if row.get("correction"):
                score += 1.0
            if score <= 0:
                continue
            ranked.append(
                {
                    "query": row.get("query", ""),
                    "rating": row.get("rating", "helpful"),
                    "correction": row.get("correction"),
                    "match_type": match_type,
                    "score": score,
                    "stored_at": row.get("stored_at"),
                }
            )

        ranked.sort(
            key=lambda item: (
                -float(item["score"]),
                item["match_type"] != "exact",
                not bool(item.get("correction")),
                item.get("stored_at") or "",
            )
        )

        deduped: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for item in ranked:
            key = (str(item["query"]), str(item["rating"]), str(item.get("correction") or ""))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
            if len(deduped) >= limit:
                break
        return deduped

    def feedback_report(self, limit_recent: int = 25) -> dict[str, Any]:
        rows = self._load_feedback_rows(limit=500)
        helpful_count = sum(1 for row in rows if row.get("rating") == "helpful")
        incorrect_count = sum(1 for row in rows if row.get("rating") == "incorrect")
        needs_more_detail_count = sum(1 for row in rows if row.get("rating") == "needs_more_detail")

        correction_counts: dict[str, int] = {}
        for row in rows:
            correction = str(row.get("correction") or "").strip()
            if not correction:
                continue
            correction_counts[correction] = correction_counts.get(correction, 0) + 1

        recent_feedback = sorted(
            rows,
            key=lambda item: item.get("stored_at") or "",
            reverse=True,
        )[:limit_recent]

        return {
            "total_feedback": len(rows),
            "helpful_count": helpful_count,
            "incorrect_count": incorrect_count,
            "needs_more_detail_count": needs_more_detail_count,
            "top_corrections": [
                correction
                for correction, _ in sorted(correction_counts.items(), key=lambda item: (-item[1], item[0]))[:5]
            ],
            "recent_feedback": recent_feedback,
        }

    def _load_feedback_rows(self, limit: int = 250) -> list[dict[str, Any]]:
        connection = duckdb.connect(str(self.duckdb_path), read_only=True)
        try:
            records = connection.execute(
                """
                SELECT stored_at, query_text, rating, correction
                FROM learning_feedback
                ORDER BY stored_at DESC
                LIMIT ?
                """,
                [limit],
            ).fetchall()
        finally:
            connection.close()

        rows: list[dict[str, Any]] = []
        for stored_at, query_text, rating, correction in records:
            rows.append(
                {
                    "stored_at": stored_at,
                    "query": query_text,
                    "rating": rating,
                    "correction": correction,
                }
            )
        return rows

    def _normalize_query(self, query: str) -> str:
        return " ".join(re.findall(r"[a-z0-9]+", query.lower()))

    def _query_tokens(self, query: str) -> set[str]:
        return {
            token
            for token in re.findall(r"[a-z0-9]+", query.lower())
            if len(token) >= 3 and token not in {"what", "which", "show", "with", "have", "launch", "launches", "vehicles", "vehicle"}
        }
