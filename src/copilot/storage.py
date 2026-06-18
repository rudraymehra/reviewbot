"""SQLite persistence for review history — read by the Streamlit dashboard."""

import json
import sqlite3
from datetime import datetime, timezone

from .config import get_settings
from .models import ReviewResult

SCHEMA = """
CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    repo TEXT NOT NULL,
    pr_number INTEGER NOT NULL,
    pr_title TEXT NOT NULL,
    model TEXT NOT NULL,
    quality_score INTEGER NOT NULL,
    recommendation TEXT NOT NULL,
    finding_count INTEGER NOT NULL,
    input_tokens INTEGER NOT NULL,
    cached_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    result_json TEXT NOT NULL
);
"""


def _connect(db_path: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or get_settings().copilot_db_path)
    conn.row_factory = sqlite3.Row

    conn.execute(SCHEMA)
    return conn


def save_review(result: ReviewResult, db_path: str | None = None) -> int:
    with _connect(db_path) as conn:
        cur = conn.execute(
            """INSERT INTO reviews
               (created_at, repo, pr_number, pr_title, model, quality_score,
                recommendation, finding_count, input_tokens, cached_tokens,
                output_tokens, result_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.now(timezone.utc).isoformat(),
                result.repo,
                result.pr_number,
                result.pr_title,
                result.model,
                result.summary.quality_score,
                result.summary.merge_recommendation,
                len(result.findings),
                result.input_tokens,
                result.cached_tokens,
                result.output_tokens,
                result.model_dump_json(),
            ),
        )
        return cur.lastrowid


def list_reviews(db_path: str | None = None) -> list[dict]:
    with _connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM reviews ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


def get_review(review_id: int, db_path: str | None = None) -> dict | None:
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM reviews WHERE id = ?", (review_id,)).fetchone()
        if row is None:
            return None
        
        d = dict(row)
        d["result"] = json.loads(d.pop("result_json"))

        return d
