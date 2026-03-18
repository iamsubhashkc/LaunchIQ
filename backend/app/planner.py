from __future__ import annotations

import json
import os
import re
import urllib.request
from datetime import date
from typing import Any

from .clarification import detect_clarifications
from .models import PlanFilter, QueryPlan


PLANNER_PROMPT = """
You are the LaunchIQ query planner. Convert the user's question into strict JSON with this schema:
{
  "intent": "list|count|distribution|timeline",
  "subject": "car_family",
  "metric": "car_family",
  "data_view": "vehicle|launch_event",
  "analysis_mode": "standard|overlap",
  "sort_by": ["-field_name"],
  "group_by": ["field"],
  "filters": [{"field": "field_name", "operator": "=|!=|in|not_in|contains|not_contains|<=|>=|<|>", "value": "value", "rationale": "why"}],
  "time_window_months": 6,
  "region_scope": "ANY|ROS|IPZ|BOTH",
  "requested_columns": ["car_family", "platform"],
  "ambiguity_notes": [],
  "clarification_questions": [],
  "unsupported_reasons": [],
  "reasoning_summary": "one sentence"
}

Rules:
- Only produce JSON.
- Use vehicle fields when possible: car_family, car_family_code, brand, region_of_sales, initial_prod_zone,
  commercial_name, project_responsible_region, sopm, mca_sopm, mca2_sopm, eop, platform, program, powertrain, eea_available,
  ota, ota_capability, eea, adas_capability, connectivity_capability, architecture, tcu_generation, tcu_details,
  infotainment_details, launch_volume, total_volume,
  lifecycle_years, volume_first_2_years, declining_post_sopm, mixed_tcu, mixed_architecture,
  region_of_sales_count, initial_prod_zone_count, months_sopm_to_mca, months_mca_to_mca2, min_transition_gap_months.
- Use launch event fields for transition launches: launch_stage, launch_category, launch_date, launch_month, launch_year.
- Use "timeline" for month-wise date grouping.
- Use "distribution" for grouped counts or sums.
- Use DISTINCT car_family semantics for vehicle-level lists and counts.
- Use DISTINCT launch_event_id semantics for launch-event counts.
- If the data does not contain the required fields, return unsupported_reasons.
"""


BASE_UNSUPPORTED_PATTERNS = {
    "ssdp": "The uploaded LRP file does not contain SSDP, SPACE, or target migration fields.",
    "space": "The uploaded LRP file does not contain SSDP, SPACE, or target migration fields.",
    "scep": "The uploaded LRP file does not contain SSDP, SPACE, or target migration fields.",
    "target sdp": "The uploaded LRP file does not contain target SDP columns.",
    "current sdp": "The uploaded LRP file does not contain current SDP columns.",
    "migration": "The uploaded LRP file does not contain migration plan or readiness columns.",
    "legacy sdp": "The uploaded LRP file does not contain stage-level SDP migration columns.",
    "double life": "The uploaded LRP file does not contain a double-life strategy flag.",
    "dual-stack": "The uploaded LRP file does not contain a double-life strategy flag.",
    "milestone": "The uploaded LRP file does not contain CM/IM/PM milestone columns.",
    "cm/im/pm": "The uploaded LRP file does not contain CM/IM/PM milestone columns.",
    "feature parity": "The uploaded LRP file does not contain an explicit feature parity metric.",
    "rollout complexity": "The uploaded LRP file does not contain an explicit rollout complexity metric.",
}


class Planner:
    def __init__(self) -> None:
        self.provider = os.getenv("LAUNCHIQ_LLM_PROVIDER", "heuristic").lower()

    def build_plan(self, query: str) -> QueryPlan:
        llm_plan = self._plan_with_provider(query)
        if llm_plan is None:
            llm_plan = self._heuristic_plan(query)
        return detect_clarifications(llm_plan, query)

    def _plan_with_provider(self, query: str) -> QueryPlan | None:
        if self.provider == "ollama":
            return self._call_ollama(query)
        if self.provider == "openai":
            return self._call_openai_compatible(query)
        return None

    def _call_ollama(self, query: str) -> QueryPlan | None:
        base_url = os.getenv("LAUNCHIQ_OLLAMA_URL", "http://localhost:11434/api/chat")
        model = os.getenv("LAUNCHIQ_OLLAMA_MODEL", "llama3.1:8b")
        payload = {
            "model": model,
            "stream": False,
            "messages": [
                {"role": "system", "content": PLANNER_PROMPT},
                {"role": "user", "content": query},
            ],
            "format": "json",
        }
        try:
            response = self._post_json(base_url, payload)
            return QueryPlan.model_validate_json(response["message"]["content"])
        except Exception:
            return None

    def _call_openai_compatible(self, query: str) -> QueryPlan | None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return None
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1/chat/completions")
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        payload = {
            "model": model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": PLANNER_PROMPT},
                {"role": "user", "content": query},
            ],
        }
        try:
            response = self._post_json(base_url, payload, headers={"Authorization": f"Bearer {api_key}"})
            return QueryPlan.model_validate_json(response["choices"][0]["message"]["content"])
        except Exception:
            return None

    def _post_json(self, url: str, payload: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, Any]:
        request_headers = {"Content-Type": "application/json"}
        if headers:
            request_headers.update(headers)
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=request_headers,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    def _heuristic_plan(self, query: str) -> QueryPlan:
        lowered = query.lower()
        analysis_year = self._extract_analysis_year(lowered)
        data_view = self._detect_data_view(lowered)
        intent = self._detect_intent(lowered)
        analysis_mode = self._detect_analysis_mode(lowered)
        group_by = self._detect_group_by(lowered, intent, data_view)
        time_window_months = self._extract_time_window_months(lowered)
        metric = self._detect_metric(lowered, analysis_year, data_view)
        sort_by = self._detect_sort_by(lowered, analysis_year)
        filters = self._detect_filters(lowered, time_window_months, analysis_year, data_view)
        requested_columns = self._requested_columns(intent, lowered, analysis_year, data_view)
        region_scope = self._detect_region_scope(lowered)
        unsupported_reasons = self._detect_unsupported_reasons(lowered)
        summary = self._summary(intent, lowered, group_by, time_window_months, analysis_year, data_view)

        return QueryPlan(
            intent=intent,
            metric=metric,
            data_view=data_view,
            analysis_mode=analysis_mode,
            sort_by=sort_by,
            group_by=group_by,
            filters=filters,
            time_window_months=time_window_months,
            region_scope=region_scope,
            requested_columns=requested_columns,
            unsupported_reasons=unsupported_reasons,
            reasoning_summary=summary,
        )

    def _detect_data_view(self, lowered: str) -> str:
        if any(token in lowered for token in ["mca ", "mca2", "mca sopm", "transition launch", "design launch"]):
            return "launch_event"
        if "mca" in lowered:
            return "launch_event"
        return "vehicle"

    def _detect_intent(self, lowered: str) -> str:
        if "ratio" in lowered or "volume impact" in lowered:
            return "distribution"
        if "month-wise" in lowered and "mca" in lowered and "mca2" in lowered:
            return "distribution"
        if "which vehicles" in lowered or "which car families" in lowered:
            if "distribution" not in lowered and "distributed" not in lowered and "dominat" not in lowered:
                return "list"
        if "how many" in lowered or "count" in lowered:
            return "count"
        if "split by" in lowered:
            return "distribution"
        if "highest number" in lowered:
            return "distribution"
        if "timeline" in lowered or "month-wise" in lowered or "clustering" in lowered:
            return "timeline"
        if "distribution" in lowered or "distributed" in lowered or "dominat" in lowered or ("mix" in lowered and "which vehicles" not in lowered):
            return "distribution"
        return "list"

    def _detect_analysis_mode(self, lowered: str) -> str:
        if "overlap heavily" in lowered or "overlap" in lowered:
            return "overlap"
        return "standard"

    def _detect_group_by(self, lowered: str, intent: str, data_view: str) -> list[str]:
        groups: list[str] = []
        if data_view == "launch_event":
            if "design launch" in lowered or "transition launch" in lowered or "ratio" in lowered or "volume impact" in lowered:
                groups.append("launch_category")
            if ("mca" in lowered and "mca2" in lowered) or "mca and mca2" in lowered:
                groups.extend(["launch_month", "launch_stage"])
            elif "month-wise" in lowered or "timeline" in lowered or "distribution of mca" in lowered:
                groups.append("launch_month")
            if intent in {"list", "count"}:
                return []
            return self._dedupe(groups)

        if "ros vs ipz" in lowered or "(ros vs ipz)" in lowered:
            groups.extend(["region_logic", "region_value"])
        elif "region" in lowered or "region of sales" in lowered:
            groups.append("region_of_sales")
        elif "ipz" in lowered or "initial prod zone" in lowered:
            groups.append("initial_prod_zone")
        if "split by region" in lowered or "by region" in lowered or "regions have the highest number" in lowered:
            groups = ["region_of_sales"]
        if "platform" in lowered:
            groups.append("platform")
        if "tcu" in lowered:
            groups.append("tcu_generation")
        if "architecture" in lowered:
            groups.append("architecture")
        if "adas" in lowered:
            groups.append("adas_capability")
        if "month-wise" in lowered or "timeline" in lowered or "clustering" in lowered:
            groups = ["sopm_month"] + [group for group in groups if group != "sopm_month"]
        if intent in {"list", "count"}:
            return []
        return self._dedupe(groups)

    def _dedupe(self, items: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for item in items:
            if item not in seen:
                seen.add(item)
                ordered.append(item)
        return ordered

    def _extract_time_window_months(self, lowered: str) -> int | None:
        match = re.search(r"next\s+(\d+)\s*(?:-|to)?\s*(\d+)?\s*months?", lowered)
        if match:
            return int(match.group(2) or match.group(1))
        if "next cycle" in lowered:
            return 12
        if "near" in lowered:
            return 9
        return None

    def _extract_analysis_year(self, lowered: str) -> int | None:
        match = re.search(r"\b(20\d{2})\b", lowered)
        return int(match.group(1)) if match else None

    def _detect_metric(self, lowered: str, analysis_year: int | None, data_view: str) -> str:
        if analysis_year and "volume" in lowered:
            return f"volume_{analysis_year}"
        if data_view == "launch_event":
            return "launch_event"
        return "car_family"

    def _detect_sort_by(self, lowered: str, analysis_year: int | None) -> list[str]:
        sort_by: list[str] = []
        if analysis_year and ("highest volume" in lowered or "contribute the highest volume" in lowered):
            sort_by.append(f"-volume_{analysis_year}")
        if "widest regional spread" in lowered:
            sort_by.append("-region_of_sales_count")
        if "long lifecycle" in lowered:
            sort_by.append("-lifecycle_years")
        if "declining volume trends" in lowered:
            sort_by.append("car_family")
        if "mca2 sopm planned" in lowered or "mca sopm" in lowered:
            sort_by.append("launch_date")
        return sort_by

    def _detect_filters(
        self,
        lowered: str,
        time_window_months: int | None,
        analysis_year: int | None,
        data_view: str,
    ) -> list[PlanFilter]:
        filters: list[PlanFilter] = []
        launch_year_query = analysis_year is not None and any(
            token in lowered for token in ["launching in", "launch in", "launches in", "sopm in"]
        )

        if time_window_months is not None:
            target_field = "launch_date" if data_view == "launch_event" else "sopm"
            filters.append(
                PlanFilter(
                    field=target_field,
                    operator=">=",
                    value="CURRENT_DATE",
                    rationale="Only include future launches from today onward.",
                )
            )
            filters.append(
                PlanFilter(
                    field=target_field,
                    operator="<=",
                    value=f"CURRENT_DATE + INTERVAL '{time_window_months} months'",
                    rationale=f"Limit launches to the next {time_window_months} months.",
                )
            )
        elif "upcoming launches" in lowered or "upcoming launch" in lowered:
            target_field = "launch_date" if data_view == "launch_event" else "sopm"
            filters.append(
                PlanFilter(
                    field=target_field,
                    operator=">=",
                    value="CURRENT_DATE",
                    rationale="Upcoming launches should start from today onward.",
                )
            )

        if data_view == "launch_event":
            if analysis_year is not None and launch_year_query:
                filters.append(
                    PlanFilter(
                        field="launch_year",
                        operator="=",
                        value=analysis_year,
                        rationale=f"Restrict launch events to {analysis_year}.",
                    )
                )
            combined_stage_query = any(
                token in lowered
                for token in [
                    "sopm +",
                    "sopm+mca",
                    "sopm + mca + mca2",
                    "mca and mca2",
                    "mca vs sopm",
                    "design launch",
                    "transition launch",
                    "volume impact",
                    "overlap",
                ]
            )
            if "mca2" in lowered and not combined_stage_query:
                filters.append(
                    PlanFilter(
                        field="launch_stage",
                        operator="=",
                        value="MCA2",
                        rationale="Query specifically targets MCA2 events.",
                    )
                )
            elif "mca" in lowered and not combined_stage_query and not any(
                token in lowered
                for token in [
                    "mca2",
                    "moving from sopm",
                ]
            ):
                filters.append(
                    PlanFilter(
                        field="launch_stage",
                        operator="=",
                        value="MCA",
                        rationale="Query specifically targets MCA events.",
                    )
                )
            elif "mca" in lowered and "mca2" in lowered and "sopm +" not in lowered and "volume impact" not in lowered and "ratio" not in lowered:
                filters.append(
                    PlanFilter(
                        field="launch_stage",
                        operator="in",
                        value=["MCA", "MCA2"],
                        rationale="Query targets MCA and MCA2 transition events only.",
                    )
                )
        elif launch_year_query:
            filters.append(
                PlanFilter(
                    field="sopm_year",
                    operator="=",
                    value=analysis_year,
                    rationale=f"Restrict design launches to SOPM year {analysis_year}.",
                )
            )
        elif analysis_year is not None and "volume" not in lowered and "sopm" not in lowered:
            filters.append(
                PlanFilter(
                    field="active_year",
                    operator="=",
                    value=analysis_year,
                    rationale=f"Vehicle must be active during {analysis_year}.",
                )
            )

        if "nearing eop" in lowered or ("eop" in lowered and "next 12 months" in lowered):
            filters.append(
                PlanFilter(
                    field="eop_within_months",
                    operator="=",
                    value=time_window_months or 12,
                    rationale="Vehicle reaches EOP within the requested upcoming window.",
                )
            )
        if "no volume planned in the first 2 years" in lowered:
            filters.append(
                PlanFilter(
                    field="volume_first_2_years",
                    operator="<=",
                    value=0,
                    rationale="No planned volume across the launch year and following year.",
                )
            )
        if "moving from sopm" in lowered or "within short intervals" in lowered or "high engineering pressure" in lowered:
            filters.extend(
                [
                    PlanFilter(
                        field="has_mca",
                        operator="=",
                        value=True,
                        rationale="Progression analysis requires an MCA date.",
                    ),
                    PlanFilter(
                        field="has_mca2",
                        operator="=",
                        value=True,
                        rationale="This progression query explicitly needs MCA2.",
                    ),
                    PlanFilter(
                        field="min_transition_gap_months",
                        operator="<=",
                        value=18,
                        rationale="Treat short intervals as 18 months or less between milestones.",
                    ),
                ]
            )
        if "legacy" in lowered:
            filters.append(
                PlanFilter(
                    field="program",
                    operator="=",
                    value="legacy",
                    rationale="Query references legacy programs in the uploaded LRP.",
                )
            )
        if "ota" in lowered and ("missing" in lowered or "lack" in lowered or "lagging" in lowered):
            filters.append(
                PlanFilter(
                    field="ota_capability",
                    operator="=",
                    value=False,
                    rationale="Query asks about missing OTA capability.",
                )
            )
        if "fota" in lowered:
            operator = "not_contains" if any(token in lowered for token in ["lack", "missing", "without"]) else "contains"
            filters.append(
                PlanFilter(
                    field="ota",
                    operator=operator,
                    value="FOTA",
                    rationale="Use the OTA column to identify whether FOTA capability is present.",
                )
            )
        if "connectivity" in lowered and ("missing" in lowered or "lagging" in lowered or "lack" in lowered):
            filters.append(
                PlanFilter(
                    field="connectivity_capability",
                    operator="=",
                    value=False,
                    rationale="Query asks for missing connectivity capability.",
                )
            )
        if "high-volume" in lowered or ("highest volume" in lowered and "not aligned" in lowered):
            filters.append(
                PlanFilter(
                    field=f"volume_{analysis_year}" if analysis_year else "launch_volume",
                    operator=">=",
                    value=90000,
                    rationale="Use a deterministic threshold for high-volume programs.",
                )
            )
        if "long lifecycle" in lowered:
            filters.append(
                PlanFilter(
                    field="lifecycle_years",
                    operator=">",
                    value=10,
                    rationale="Long lifecycle is treated as more than 10 years.",
                )
            )
        if "declining volume trends" in lowered:
            filters.append(
                PlanFilter(
                    field="declining_post_sopm",
                    operator="=",
                    value=True,
                    rationale="Use annual post-launch volume trend to detect decline.",
                )
            )
        if "mixed architecture" in lowered or "multiple tcu" in lowered or "multiple tcu % split" in lowered:
            filters.append(
                PlanFilter(
                    field="mixed_architecture" if "mixed architecture" in lowered else "mixed_tcu",
                    operator="=",
                    value=True,
                    rationale="More than one TCU/connectivity stack is active for the vehicle.",
                )
            )
        if analysis_year and ("volume in" in lowered or "volume for" in lowered or "highest volume" in lowered or "weighted by volume" in lowered):
            filters.append(
                PlanFilter(
                    field=f"volume_{analysis_year}",
                    operator=">",
                    value=0,
                    rationale=f"Use only rows with planned volume in {analysis_year}.",
                )
            )

        region_field = "initial_prod_zone" if "ipz" in lowered or "initial prod zone" in lowered else "region_of_sales"
        for region in ["CHN", "EER", "EEU", "IAP", "MEA", "NAM", "SAM", "TBD"]:
            if region.lower() in lowered:
                filters.append(
                    PlanFilter(
                        field=region_field,
                        operator="contains",
                        value=region,
                        rationale=f"Filter to {region} on the requested regional dimension.",
                    )
                )
        return filters

    def _requested_columns(self, intent: str, lowered: str, analysis_year: int | None, data_view: str) -> list[str]:
        if intent == "count":
            return ["car_family"]
        if data_view == "launch_event":
            columns = [
                "car_family",
                "brand",
                "commercial_name",
                "initial_prod_zone",
                "region_of_sales",
                "eea",
                "tcu_details",
                "infotainment_details",
                "ota",
                "platform",
                "program",
                "launch_stage",
                "launch_category",
                "launch_date",
                "launch_month",
            ]
            if analysis_year and "volume" in lowered:
                columns.append(f"volume_{analysis_year}")
            return self._dedupe(columns)

        columns = [
            "car_family",
            "brand",
            "commercial_name",
            "initial_prod_zone",
            "region_of_sales",
            "eea",
            "tcu_details",
            "infotainment_details",
            "ota",
            "platform",
            "program",
            "sopm",
        ]
        if analysis_year and "volume" in lowered:
            columns.append(f"volume_{analysis_year}")
        if "lifecycle" in lowered:
            columns.extend(["eop", "lifecycle_years"])
        if "regional spread" in lowered:
            columns.append("region_of_sales_count")
        if "first 2 years" in lowered:
            columns.append("volume_first_2_years")
        if "architecture" in lowered:
            columns.append("architecture")
        if "tcu" in lowered:
            columns.extend(["tcu_generation", "mixed_tcu"])
        if "mixed architecture" in lowered:
            columns.append("mixed_architecture")
        if "connectivity" in lowered:
            columns.append("connectivity_capability")
        if "eea" in lowered:
            columns.append("eea")
        if "ota" in lowered:
            columns.append("ota")
        if "declining volume trends" in lowered:
            columns.append("declining_post_sopm")
        if "moving from sopm" in lowered or "within short intervals" in lowered:
            columns.extend(["months_sopm_to_mca", "months_mca_to_mca2", "min_transition_gap_months"])
        return self._dedupe(columns)

    def _detect_region_scope(self, lowered: str) -> str:
        if "ros vs ipz" in lowered or "(ros vs ipz)" in lowered:
            return "BOTH"
        if "both only" in lowered or "region_scope both" in lowered:
            return "BOTH"
        if "ros" in lowered and "ipz" not in lowered:
            return "ROS"
        if "ipz" in lowered and "ros" not in lowered:
            return "IPZ"
        return "ANY"

    def _detect_unsupported_reasons(self, lowered: str) -> list[str]:
        reasons: list[str] = []
        for pattern, reason in BASE_UNSUPPORTED_PATTERNS.items():
            if pattern in lowered and reason not in reasons:
                reasons.append(reason)

        if "architecture" in lowered and "mca" in lowered and any(
            token in lowered for token in ["change", "during mca", "not sopm", "between sopm and mca", "introduce new"]
        ):
            reasons.append("The uploaded LRP file does not contain stage-specific architecture snapshots at SOPM versus MCA.")

        if "ota" in lowered and "mca" in lowered and any(
            token in lowered for token in ["did not", "introduce", "where sopm did not"]
        ):
            reasons.append("The uploaded LRP file does not contain stage-specific OTA snapshots at SOPM versus MCA.")

        return reasons

    def _summary(
        self,
        intent: str,
        lowered: str,
        group_by: list[str],
        time_window_months: int | None,
        analysis_year: int | None,
        data_view: str,
    ) -> str:
        clauses = [f"Plan a {intent} query over launch programs."]
        if data_view == "launch_event":
            clauses.append("Use the transition launch event view.")
        if group_by:
            clauses.append(f"Group by {', '.join(group_by)}.")
        if time_window_months:
            clauses.append(f"Focus on the next {time_window_months} months from {date.today().isoformat()}.")
        if analysis_year:
            clauses.append(f"Use {analysis_year} as the analysis year.")
        if "risk" in lowered:
            clauses.append("Surface deterministic signals only when the dataset contains explicit supporting fields.")
        return " ".join(clauses)
