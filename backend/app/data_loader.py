from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .config import PROGRAMS_CSV, SAMPLE_LRP_XLSX


INFOTAINMENT_COLUMNS = [
    "VP2R",
    "VP2NG",
    "VP4R",
    "NAC/RCC",
    "PCSA (SPS)",
    "CRONY 1",
    "CRONY 2",
    "CRONY 2 NAV",
    "AIO",
    "IVI R1 M",
    "IVI R1 H",
    "IVI R2 M",
    "IVI R2 H",
    "G2.5",
    "F7",
    "B7 LOW",
    "J10",
    "A7",
    "A7+",
    "R1L",
    "R1H",
    "R2eX",
    "R2MS E",
    "R2MS H",
    "R2P0",
    "R2P0+",
    "PARTNER.1",
    "No Infotainment",
]

CONNECTIVITY_COLUMNS = [
    "VP2R.1",
    "VP4R.1",
    "ITU4G",
    "BSRF V1",
    "BSRF V2 EVO",
    "RTBM",
    "ATB3S",
    "ATB4S V1",
    "ATB4S V2",
    "R2eX.1",
    "TBM 2.0",
    "TBM 2.0H",
    "RTCU",
    "PARTNER.2",
    "No Connectivity",
]

ADAS_COLUMNS = [
    "ADAS Wave 2",
    "ADAS Wave 3",
    "Wave 3 L2+ Buy",
    "Smart Sensors SEA",
    "FCA Gen 1",
    "FCA Gen 1a",
    "FCA Gen 2",
    "FCA Gen 3",
    "FCA Gen 3a",
    "FCA Gen 3b",
    "FCA Gen 3c",
    "FCA Gen 3d",
    "FCA Gen 4",
    "FCA Gen 4a",
    "Gen 5 L2",
    "Gen 5 L2+",
    "FCA Gen 6",
    "SS L2",
    "SS L2+",
    "Hawkeye",
    "AD 1.0 Entry",
    "AD 1.0 L2+",
    "PARTNER",
]


@dataclass
class LoadedDataset:
    frame: pd.DataFrame
    events_frame: pd.DataFrame
    source_path: Path
    source_kind: str


class LaunchDataLoader:
    def __init__(self, excel_path: Path = SAMPLE_LRP_XLSX, csv_path: Path = PROGRAMS_CSV) -> None:
        self.excel_path = excel_path
        self.csv_path = csv_path

    def load(self) -> LoadedDataset:
        if self.excel_path.exists():
            frame = self._load_excel(self.excel_path)
            return LoadedDataset(
                frame=frame,
                events_frame=self._build_launch_events(frame),
                source_path=self.excel_path,
                source_kind="lrp_excel",
            )

        frame = pd.read_csv(self.csv_path, parse_dates=["sopm", "eop", "milestone_cm", "milestone_im", "milestone_pm"])
        return LoadedDataset(frame=frame, events_frame=pd.DataFrame(), source_path=self.csv_path, source_kind="demo_csv")

    def _load_excel(self, path: Path) -> pd.DataFrame:
        raw = pd.read_excel(path, sheet_name="Sheet1")
        volume_columns = [column for column in raw.columns if str(column).startswith("Volume ")]
        volume_years = [int(str(column).split()[-1]) for column in volume_columns]
        current_year = pd.Timestamp.today().year
        current_cycle_columns = [
            column for column in volume_columns if current_year <= int(str(column).split()[-1]) <= current_year + 4
        ]

        frame = pd.DataFrame(
            {
                "brand": raw["Brand"].fillna(""),
                "car_family": raw["Car Family"].fillna("").astype(str),
                "commercial_name": raw["Commercial Name"].fillna(raw["Car Family"]).astype(str),
                "car_family_code": raw["Carline Code w. Final Prod Zone"].fillna("").astype(str),
                "region_of_sales": raw["Region of Sales"].fillna("").astype(str),
                "initial_prod_zone": raw["Initial Prod Zone"].fillna("").astype(str),
                "project_responsible_region": raw["Project Responsible Region"].fillna("").astype(str),
                "platform": raw["Platform"].fillna("").astype(str),
                "program": raw["Program"].fillna("").astype(str),
                "powertrain": raw["PWT Energy and Technology"].fillna("").astype(str),
                "sopm": pd.to_datetime(raw["SOPM"], errors="coerce"),
                "mca_sopm": pd.to_datetime(raw["MCA SOPM"], errors="coerce"),
                "mca2_sopm": pd.to_datetime(raw["MCA 2 SOPM"], errors="coerce"),
                "eop": pd.to_datetime(raw["EOPM"], errors="coerce"),
                "eea": raw["EEA"].fillna(""),
                "ota": raw["OTA"].fillna(""),
                "launch_volume": raw[current_cycle_columns].fillna(0).sum(axis=1) if current_cycle_columns else 0,
                "total_volume": raw[volume_columns].fillna(0).sum(axis=1),
            }
        )
        for column, year in zip(volume_columns, volume_years, strict=False):
            frame[f"volume_{year}"] = raw[column].fillna(0)

        frame = frame.assign(
            sopm_month=frame["sopm"].dt.strftime("%Y-%m"),
            sopm_year=frame["sopm"].dt.year,
            eop_year=frame["eop"].dt.year,
            region_pair=frame["region_of_sales"] + " -> " + frame["initial_prod_zone"],
            eea_available=frame["eea"].astype(str).str.strip().ne(""),
            ota_capability=frame["ota"].astype(str).str.strip().ne(""),
            adas_capability=raw[ADAS_COLUMNS].fillna(0).gt(0).any(axis=1),
            infotainment_stack=raw.apply(lambda row: self._extract_active_stack(row, INFOTAINMENT_COLUMNS), axis=1),
            infotainment_details=raw.apply(lambda row: self._extract_weighted_stack(row, INFOTAINMENT_COLUMNS), axis=1),
            connectivity_stack=raw.apply(lambda row: self._extract_active_stack(row, CONNECTIVITY_COLUMNS), axis=1),
            tcu_details=raw.apply(lambda row: self._extract_weighted_stack(row, CONNECTIVITY_COLUMNS), axis=1),
        )

        frame = frame.assign(
            connectivity_capability=~frame["connectivity_stack"].str.contains("No Connectivity", case=False, na=False),
            architecture=frame["infotainment_stack"],
            tcu_generation=frame["connectivity_stack"],
            legacy_program=frame["program"].str.lower().eq("legacy"),
            mixed_tcu=frame["connectivity_stack"].str.contains(",", regex=False),
            mixed_architecture=frame["infotainment_stack"].str.contains(",", regex=False),
            lifecycle_years=((frame["eop"] - frame["sopm"]).dt.days / 365.25).round(1),
            has_mca=frame["mca_sopm"].notna(),
            has_mca2=frame["mca2_sopm"].notna(),
        )
        frame = frame.assign(
            volume_first_2_years=frame.apply(lambda row: self._volume_first_2_years(row, volume_years), axis=1),
            declining_post_sopm=frame.apply(lambda row: self._declining_post_sopm(row, volume_years), axis=1),
            months_sopm_to_mca=frame.apply(lambda row: self._month_gap(row["sopm"], row["mca_sopm"]), axis=1),
            months_mca_to_mca2=frame.apply(lambda row: self._month_gap(row["mca_sopm"], row["mca2_sopm"]), axis=1),
        )
        frame = frame.assign(
            min_transition_gap_months=frame[["months_sopm_to_mca", "months_mca_to_mca2"]].min(axis=1, skipna=True)
        )
        return frame.assign(
            region_of_sales_count=frame.groupby("car_family")["region_of_sales"].transform("nunique"),
            initial_prod_zone_count=frame.groupby("car_family")["initial_prod_zone"].transform("nunique"),
        )

    def _extract_active_stack(self, row: pd.Series, columns: list[str]) -> str:
        matches: list[tuple[str, float]] = []
        for column in columns:
            value = row.get(column)
            if pd.isna(value):
                continue
            score = float(value) if isinstance(value, (int, float)) else 1.0
            if score <= 0:
                continue
            label = (
                column.replace(".1", "")
                .replace(".2", "")
                .replace("PARTNER.1", "PARTNER")
                .replace("PARTNER.2", "PARTNER")
                .replace("R2eX.1", "R2eX")
            )
            matches.append((label, score))

        if not matches:
            return "Unknown"

        matches.sort(key=lambda item: (-item[1], item[0]))
        labels = [label for label, _ in matches]
        return ", ".join(dict.fromkeys(labels))

    def _extract_weighted_stack(self, row: pd.Series, columns: list[str]) -> str:
        matches: list[tuple[str, float | None]] = []
        for column in columns:
            value = row.get(column)
            if pd.isna(value):
                continue
            numeric_value: float | None = None
            if isinstance(value, (int, float)):
                numeric_value = float(value)
                if numeric_value <= 0:
                    continue
            label = (
                column.replace(".1", "")
                .replace(".2", "")
                .replace("PARTNER.1", "PARTNER")
                .replace("PARTNER.2", "PARTNER")
                .replace("R2eX.1", "R2eX")
            )
            matches.append((label, numeric_value))

        if not matches:
            return "Unknown"

        formatted: list[str] = []
        for label, numeric_value in matches:
            if numeric_value is not None and 0 < numeric_value < 1:
                formatted.append(f"{label} ({round(numeric_value * 100)}%)")
            else:
                formatted.append(label)
        return ", ".join(dict.fromkeys(formatted))

    def _volume_first_2_years(self, row: pd.Series, volume_years: list[int]) -> float:
        if pd.isna(row["sopm"]):
            return 0.0
        launch_year = int(row["sopm"].year)
        relevant_years = [year for year in volume_years if launch_year <= year <= launch_year + 1]
        return float(sum(float(row.get(f"volume_{year}", 0) or 0) for year in relevant_years))

    def _declining_post_sopm(self, row: pd.Series, volume_years: list[int]) -> bool:
        if pd.isna(row["sopm"]):
            return False
        launch_year = int(row["sopm"].year)
        series = [float(row.get(f"volume_{year}", 0) or 0) for year in volume_years if year >= launch_year]
        positive = [value for value in series if value > 0]
        if len(positive) < 3:
            return False
        return positive[-1] < positive[0] and any(curr < prev for prev, curr in zip(positive, positive[1:], strict=False))

    def _month_gap(self, start: pd.Timestamp | None, end: pd.Timestamp | None) -> float | None:
        if pd.isna(start) or pd.isna(end):
            return None
        return round((end.year - start.year) * 12 + (end.month - start.month), 1)

    def _build_launch_events(self, frame: pd.DataFrame) -> pd.DataFrame:
        event_specs = [
            ("SOPM", "sopm", "Design Launch"),
            ("MCA", "mca_sopm", "Transition Launch"),
            ("MCA2", "mca2_sopm", "Transition Launch"),
        ]
        event_frames: list[pd.DataFrame] = []
        for launch_stage, date_field, launch_category in event_specs:
            rows = frame.loc[frame[date_field].notna()].copy()
            if rows.empty:
                continue
            rows = rows.assign(
                launch_stage=launch_stage,
                launch_category=launch_category,
                launch_date=rows[date_field],
            )
            rows = rows.assign(
                launch_month=rows["launch_date"].dt.strftime("%Y-%m"),
                launch_year=rows["launch_date"].dt.year,
                launch_event_id=rows.apply(
                    lambda row: f"{row['car_family']}|{row['car_family_code']}|{launch_stage}|{row['launch_date'].date()}",
                    axis=1,
                ),
            )
            event_frames.append(rows)

        if not event_frames:
            return pd.DataFrame()
        return pd.concat(event_frames, ignore_index=True)
