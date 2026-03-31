from __future__ import annotations

from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BASE_DIR.parent
DATA_DIR = BASE_DIR / "data"
PROGRAMS_CSV = DATA_DIR / "launch_programs.csv"
LEARNING_JSONL = DATA_DIR / "learning_log.jsonl"
LEARNING_DUCKDB = DATA_DIR / "learning.duckdb"
MILESTONE_DELIVERABLES_JSON = DATA_DIR / "milestone_deliverables.json"
MILESTONE_DUCKDB = DATA_DIR / "milestones.duckdb"
SAMPLE_LRP_XLSX = PROJECT_DIR / "sample_lrp.xlsx"
