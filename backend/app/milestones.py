from __future__ import annotations

import pandas as pd


MILESTONE_SPECS = [
    ("IM", "milestone_im", -243.0),
    ("PM", "milestone_pm", -204.0),
    ("CM", "milestone_cm", -175.0),
    ("DM", "milestone_dm", -156.0),
    ("SHRM", "milestone_shrm", -92.0),
    ("X0", "milestone_x0", -54.0),
    ("X1", "milestone_x1", -36.0),
    ("SOP-8", "milestone_sop_8", -34.7),
    ("SOP-6", "milestone_sop_6", -26.0),
    ("X2", "milestone_x2", -17.0),
    ("SOP-3", "milestone_sop_3", -13.0),
    ("LRM", "milestone_lrm", -12.0),
    ("X3", "milestone_x3", -10.0),
]

MILESTONE_LABELS = {column: label for label, column, _ in MILESTONE_SPECS}
MILESTONE_OFFSETS = {column: weeks for _, column, weeks in MILESTONE_SPECS}
MILESTONE_COLUMN_ORDER = [column for _, column, _ in MILESTONE_SPECS]
MILESTONE_COLUMN_TO_CODE = {
    "milestone_im": "POST_IM",
    "milestone_pm": "PM",
    "milestone_cm": "CM",
    "milestone_dm": "CM",
    "milestone_shrm": "SHRM",
    "milestone_x0": "X0",
    "milestone_x1": "X0",
    "milestone_sop_8": "SOP_8",
    "milestone_sop_6": "SOP_6",
    "milestone_x2": "SOP_6",
    "milestone_sop_3": "SOP_3",
    "milestone_lrm": "LRM",
    "milestone_x3": "LRM",
}
ANCHOR_LABELS = {
    "sopm": "SOPM",
    "mca_sopm": "MCA",
    "mca2_sopm": "MCA2",
}


def nearest_monday(value: pd.Timestamp | None) -> pd.Timestamp | pd.NaT:
    if value is None or pd.isna(value):
        return pd.NaT
    current = pd.Timestamp(value)
    previous_monday = current - pd.Timedelta(days=current.weekday())
    next_monday = previous_monday + pd.Timedelta(days=7)
    return previous_monday.normalize() if current - previous_monday <= next_monday - current else next_monday.normalize()


def derive_milestone_date(anchor_date: pd.Timestamp | None, offset_weeks: float) -> pd.Timestamp | pd.NaT:
    if anchor_date is None or pd.isna(anchor_date):
        return pd.NaT
    shifted = pd.Timestamp(anchor_date) + pd.to_timedelta(offset_weeks * 7, unit="D")
    return nearest_monday(shifted)


def derive_milestone_map(anchor_date: pd.Timestamp | None) -> dict[str, pd.Timestamp | pd.NaT]:
    return {
        column: derive_milestone_date(anchor_date, offset_weeks)
        for column, offset_weeks in MILESTONE_OFFSETS.items()
    }
