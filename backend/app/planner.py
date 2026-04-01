from __future__ import annotations

import json
import os
import re
import urllib.request
from functools import lru_cache
from datetime import date
from typing import Any

from .clarification import detect_clarifications
from .data_loader import CONNECTIVITY_COLUMNS, INFOTAINMENT_COLUMNS, LaunchDataLoader
from .milestones import ANCHOR_LABELS, MILESTONE_COLUMN_ORDER, MILESTONE_COLUMN_TO_CODE
from .models import LlmSuggestion, PlanFilter, PlanSnapshot, PlannerDiagnostics, QueryPlan


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

HYBRID_INTERPRET_PROMPT = """
You are the LaunchIQ hybrid planner assistant.
Return only JSON with this schema:
{
  "intent": "list|count|distribution|timeline|null",
  "data_view": "vehicle|launch_event|null",
  "confidence": 0.0,
  "reasoning": "one sentence"
}

Rules:
- Do not invent fields, filters, or SQL.
- Only infer the aggregation shape and the best execution view.
- Use "launch_event" when the user is clearly asking about launch-stage timing windows such as SOPM, MCA, MCA2, or general launch windows.
- Use "vehicle" when the query is clearly about vehicle profile details, lifecycle, or backward-derived milestones.
- If uncertain, return null values with low confidence.
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
    "feature parity": "The uploaded LRP file does not contain an explicit feature parity metric.",
    "rollout complexity": "The uploaded LRP file does not contain an explicit rollout complexity metric.",
}


SCHEMA_MATCH_FIELDS = [
    "brand",
    "region_of_sales",
    "initial_prod_zone",
    "project_responsible_region",
    "platform",
    "program",
    "powertrain",
    "eea",
    "ota",
]

ENTITY_MATCH_FIELDS = [
    "car_family_code",
    "commercial_name",
    "car_family",
]

REGION_LIKE_FIELDS = {
    "region_of_sales",
    "initial_prod_zone",
    "project_responsible_region",
}

CAR_FAMILY_FALLBACK_EXCLUSIONS = {
    "EU",
    "EEU",
    "EER",
    "MEA",
    "IAP",
    "NAM",
    "SAM",
    "CHN",
    "MCA",
    "MCA2",
    "SOPM",
    "EOP",
    "OTA",
    "EEA",
    "TCU",
}

TCU_HINTS = {"tcu", "tcus", "connectivity"}
INFOTAINMENT_HINTS = {"infotainment", "infotainments", "ivi", "headunit", "hu"}
MILESTONE_FIELD_ALIASES = {
    "milestone_im": [r"\bim\b"],
    "milestone_pm": [r"\bpm\b"],
    "milestone_cm": [r"\bcm\b"],
    "milestone_dm": [r"\bdm\b"],
    "milestone_shrm": [r"\bshrm\b"],
    "milestone_x0": [r"\bx0\b"],
    "milestone_x1": [r"\bx1\b"],
    "milestone_sop_8": [r"\bsop(?:\s*-\s*|\s+)?8\b"],
    "milestone_sop_6": [r"\bsop(?:\s*-\s*|\s+)?6\b"],
    "milestone_x2": [r"\bx2\b"],
    "milestone_sop_3": [r"\bsop(?:\s*-\s*|\s+)?3\b"],
    "milestone_lrm": [r"\blrm\b"],
    "milestone_x3": [r"\bx3\b"],
}

MONTH_NAME_TO_NUMBER = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}


class Planner:
    def __init__(self) -> None:
        self.provider = os.getenv("LAUNCHIQ_LLM_PROVIDER", "heuristic").lower()
        self.mode = os.getenv(
            "LAUNCHIQ_PLANNER_MODE",
            "llm" if self.provider in {"openai", "ollama"} else "heuristic",
        ).lower()

    def build_plan(self, query: str, mode_override: str | None = None) -> QueryPlan:
        heuristic_plan = self._heuristic_plan(query)
        llm_suggestion: dict[str, Any] | None = None
        accepted_overrides: list[str] = []
        decision_notes: list[str] = []
        active_mode = mode_override if mode_override in {"heuristic", "hybrid", "llm"} else self.mode
        if mode_override in {"heuristic", "hybrid", "llm"}:
            decision_notes.append(f"Planner mode requested by UI: {mode_override}.")
        if active_mode == "hybrid":
            plan, llm_suggestion, accepted_overrides, hybrid_notes = self._hybrid_plan(query, heuristic_plan)
            decision_notes.extend(hybrid_notes)
        elif active_mode == "llm":
            llm_plan = self._plan_with_provider(query)
            if llm_plan is not None:
                plan = llm_plan
                decision_notes.append("Used full LLM planner output.")
            else:
                plan = heuristic_plan
                decision_notes.append("LLM planner was unavailable, so the heuristic planner was used.")
        else:
            plan = heuristic_plan
            decision_notes.append("Used heuristic planner only.")

        plan = detect_clarifications(plan, query)
        plan.planner_diagnostics = self._build_planner_diagnostics(
            query=query,
            heuristic_plan=heuristic_plan,
            final_plan=plan,
            llm_suggestion=llm_suggestion,
            accepted_overrides=accepted_overrides,
            decision_notes=decision_notes,
        )
        return plan

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

    def _hybrid_plan(
        self,
        query: str,
        heuristic_plan: QueryPlan,
    ) -> tuple[QueryPlan, dict[str, Any] | None, list[str], list[str]]:
        interpretation = self._interpret_with_provider(query)
        if interpretation is None:
            return heuristic_plan, None, [], ["Hybrid mode was requested, but no LLM provider was available, so LaunchIQ stayed on heuristics."]

        overrides, accepted_overrides, decision_notes = self._resolve_hybrid_overrides(query, heuristic_plan, interpretation)
        if not overrides:
            return heuristic_plan, interpretation, accepted_overrides, decision_notes

        plan = self._heuristic_plan(query, overrides=overrides)
        reason = str(interpretation.get("reasoning", "")).strip()
        if reason:
            plan.reasoning_summary = f"{plan.reasoning_summary} Hybrid assist: {reason}"
        return plan, interpretation, accepted_overrides, decision_notes

    def _interpret_with_provider(self, query: str) -> dict[str, Any] | None:
        if self.provider == "ollama":
            return self._call_ollama_interpretation(query)
        if self.provider == "openai":
            return self._call_openai_interpretation(query)
        return None

    def _call_ollama_interpretation(self, query: str) -> dict[str, Any] | None:
        base_url = os.getenv("LAUNCHIQ_OLLAMA_URL", "http://localhost:11434/api/chat")
        model = os.getenv("LAUNCHIQ_OLLAMA_MODEL", "llama3.1:8b")
        payload = {
            "model": model,
            "stream": False,
            "messages": [
                {"role": "system", "content": HYBRID_INTERPRET_PROMPT},
                {"role": "user", "content": query},
            ],
            "format": "json",
        }
        try:
            response = self._post_json(base_url, payload)
            return json.loads(response["message"]["content"])
        except Exception:
            return None

    def _call_openai_interpretation(self, query: str) -> dict[str, Any] | None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return None
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1/chat/completions")
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        payload = {
            "model": model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": HYBRID_INTERPRET_PROMPT},
                {"role": "user", "content": query},
            ],
        }
        try:
            response = self._post_json(base_url, payload, headers={"Authorization": f"Bearer {api_key}"})
            return json.loads(response["choices"][0]["message"]["content"])
        except Exception:
            return None

    def _resolve_hybrid_overrides(
        self,
        query: str,
        heuristic_plan: QueryPlan,
        interpretation: dict[str, Any],
    ) -> tuple[dict[str, Any], list[str], list[str]]:
        lowered = query.lower()
        strengths = self._heuristic_strengths(lowered)
        try:
            confidence = float(interpretation.get("confidence", 0.0) or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0

        overrides: dict[str, Any] = {}
        accepted_overrides: list[str] = []
        decision_notes = [f"Hybrid interpretation confidence: {confidence:.2f}."]
        suggested_intent = interpretation.get("intent")
        if (
            suggested_intent in {"list", "count", "distribution", "timeline"}
            and suggested_intent != heuristic_plan.intent
            and not strengths["intent_strong"]
            and confidence >= 0.75
        ):
            overrides["intent"] = suggested_intent
            accepted_overrides.append("intent")
            decision_notes.append(f"Accepted LLM intent override to {suggested_intent}.")
        elif suggested_intent in {"list", "count", "distribution", "timeline"} and suggested_intent != heuristic_plan.intent:
            decision_notes.append(f"Rejected LLM intent override to {suggested_intent} because heuristic intent was already strong or confidence was low.")

        suggested_view = interpretation.get("data_view")
        if (
            suggested_view in {"vehicle", "launch_event"}
            and suggested_view != heuristic_plan.data_view
            and not strengths["data_view_strong"]
            and confidence >= 0.75
        ):
            overrides["data_view"] = suggested_view
            accepted_overrides.append("data_view")
            decision_notes.append(f"Accepted LLM data-view override to {suggested_view}.")
        elif suggested_view in {"vehicle", "launch_event"} and suggested_view != heuristic_plan.data_view:
            decision_notes.append(f"Rejected LLM data-view override to {suggested_view} because heuristic view was already strong or confidence was low.")

        if not accepted_overrides:
            decision_notes.append("Final plan stayed on the heuristic baseline.")
        return overrides, accepted_overrides, decision_notes

    def _heuristic_strengths(self, lowered: str) -> dict[str, bool]:
        intent_strong = any(
            token in lowered
            for token in [
                "which vehicles",
                "which car families",
                "how many",
                "count",
                "split by",
                "distribution",
                "distributed",
                "timeline",
                "month-wise",
                "clustering",
            ]
        )
        data_view_strong = bool(self._detect_milestone_columns(lowered)) or re.search(r"^\s*when\s+(?:is|does)\b", lowered) is not None
        if not data_view_strong:
            data_view_strong = self._is_broad_launch_window_query(lowered) or any(
                token in lowered
                for token in [
                    "mca ",
                    "mca2",
                    "mca sopm",
                    "transition launch",
                    "design launch",
                ]
            )
        return {"intent_strong": intent_strong, "data_view_strong": data_view_strong}

    def _heuristic_plan(self, query: str, overrides: dict[str, Any] | None = None) -> QueryPlan:
        overrides = overrides or {}
        lowered = query.lower()
        entity_filters, masked_lowered = self._detect_entity_filters(lowered)
        temporal_window = self._extract_temporal_window(masked_lowered)
        time_window_months = self._extract_time_window_months(masked_lowered)
        analysis_year = self._extract_analysis_year(masked_lowered)
        data_view = overrides.get("data_view")
        if data_view not in {"vehicle", "launch_event"}:
            data_view = self._detect_data_view(masked_lowered, temporal_window, time_window_months)
        intent = overrides.get("intent")
        if intent not in {"list", "count", "distribution", "timeline"}:
            intent = self._detect_intent(masked_lowered)
        analysis_mode = self._detect_analysis_mode(masked_lowered)
        should_enrich_vehicle_brief = self._should_enrich_vehicle_brief(masked_lowered)
        group_by = self._detect_group_by(masked_lowered, intent, data_view)
        metric = self._detect_metric(masked_lowered, analysis_year, data_view)
        sort_by = self._detect_sort_by(masked_lowered, analysis_year)
        launch_window_view = data_view == "launch_event" and (
            self._is_broad_launch_window_query(masked_lowered)
            or (
                overrides.get("data_view") == "launch_event"
                and temporal_window is not None
                and not self._detect_milestone_columns(masked_lowered)
                and not re.search(r"^\s*when\s+(?:is|does)\b", masked_lowered)
            )
        )
        milestone_columns = self._detect_milestone_columns(masked_lowered)
        if data_view == "launch_event" and intent == "list" and launch_window_view and not milestone_columns:
            milestone_columns = list(MILESTONE_COLUMN_ORDER)
        if should_enrich_vehicle_brief and not milestone_columns:
            milestone_columns = list(MILESTONE_COLUMN_ORDER)
        milestone_anchor = self._detect_milestone_anchor(masked_lowered) if milestone_columns else None
        if data_view == "launch_event" and intent == "list" and launch_window_view:
            milestone_anchor = "sopm"
        filters = entity_filters + self._detect_filters(
            masked_lowered,
            time_window_months,
            analysis_year,
            data_view,
            analysis_mode,
            temporal_window,
            milestone_columns,
            force_launch_event_window=bool(launch_window_view and not self._is_broad_launch_window_query(masked_lowered)),
        )
        filters = self._add_stack_component_filters(masked_lowered, filters)
        filters = self._add_schema_value_filters(masked_lowered, filters)
        filters = self._add_fallback_car_family_filter(masked_lowered, filters)
        milestone_deliverable_codes = self._detect_milestone_deliverable_codes(masked_lowered, milestone_columns)
        filters = self._add_milestone_anchor_filters(filters, milestone_anchor)
        filters = self._dedupe_filters(filters)
        requested_columns = self._requested_columns(
            intent,
            masked_lowered,
            analysis_year,
            data_view,
            milestone_columns,
            milestone_anchor,
            milestone_deliverable_codes,
        )
        region_scope = self._detect_region_scope(masked_lowered)
        unsupported_reasons = self._detect_unsupported_reasons(masked_lowered)
        if not unsupported_reasons and self._is_low_signal_query(
            query=query,
            masked_lowered=masked_lowered,
            filters=filters,
            milestone_columns=milestone_columns,
            group_by=group_by,
            time_window_months=time_window_months,
            analysis_year=analysis_year,
            temporal_window=temporal_window,
        ):
            unsupported_reasons.append(
                "LaunchIQ could not map this question to a deterministic launch query. Rephrase with a vehicle, launch stage, milestone, region, platform, or time window."
            )
        summary = self._summary(
            intent,
            masked_lowered,
            group_by,
            time_window_months,
            analysis_year,
            data_view,
            temporal_window,
            milestone_anchor,
            milestone_columns,
        )

        if milestone_anchor and not sort_by:
            sort_by = [milestone_anchor]
        if temporal_window and data_view == "vehicle" and milestone_columns:
            sort_by = [milestone_columns[0]]

        return QueryPlan(
            intent=intent,
            metric=metric,
            data_view=data_view,
            analysis_mode=analysis_mode,
            milestone_anchor=milestone_anchor,
            milestone_columns=milestone_columns,
            milestone_deliverable_codes=milestone_deliverable_codes,
            sort_by=sort_by,
            group_by=group_by,
            filters=filters,
            time_window_months=time_window_months,
            region_scope=region_scope,
            requested_columns=requested_columns,
            unsupported_reasons=unsupported_reasons,
            reasoning_summary=summary,
        )

    def _is_low_signal_query(
        self,
        query: str,
        masked_lowered: str,
        filters: list[PlanFilter],
        milestone_columns: list[str],
        group_by: list[str],
        time_window_months: int | None,
        analysis_year: int | None,
        temporal_window: tuple[str, str, str] | None,
    ) -> bool:
        if filters or milestone_columns or group_by or time_window_months or analysis_year is not None or temporal_window is not None:
            return False

        business_cues = [
            "vehicle",
            "vehicles",
            "car family",
            "car families",
            "launch",
            "launches",
            "launching",
            "sopm",
            "mca",
            "mca2",
            "milestone",
            "region",
            "platform",
            "brand",
            "eea",
            "ota",
            "tcu",
            "infotainment",
            "volume",
            "active",
            "eop",
            "lifecycle",
        ]
        cue_count = sum(1 for cue in business_cues if cue in masked_lowered)
        tokens = re.findall(r"[a-z0-9]+", query.lower())
        non_trivial_tokens = [token for token in tokens if len(token) >= 3]
        if not non_trivial_tokens:
            return True
        if len(non_trivial_tokens) == 1:
            return True
        if cue_count == 0:
            return True
        if cue_count == 1 and len(non_trivial_tokens) <= 3:
            return True
        return False

    def _snapshot_plan(self, plan: QueryPlan) -> PlanSnapshot:
        return PlanSnapshot(
            intent=plan.intent,
            data_view=plan.data_view,
            group_by=list(plan.group_by),
            filters=list(plan.filters),
            requested_columns=list(plan.requested_columns),
            region_scope=plan.region_scope,
            milestone_anchor=plan.milestone_anchor,
            milestone_columns=list(plan.milestone_columns),
            unsupported_reasons=list(plan.unsupported_reasons),
            reasoning_summary=plan.reasoning_summary,
        )

    def _classify_query_frame(self, lowered: str, plan: QueryPlan) -> str:
        if plan.analysis_mode == "overlap":
            return "overlap"
        if plan.milestone_columns and any(item.field == "milestone_window" for item in plan.filters):
            return "milestone_window"
        if plan.data_view == "launch_event" and any(item.field in {"launch_date", "launch_year"} for item in plan.filters):
            if any(item.field == "launch_stage" for item in plan.filters):
                return "launch_stage_window"
            return "launch_window"
        if any(
            phrase in lowered
            for phrase in [
                "tell me about",
                "details for",
                "show launches for",
                "what launches are planned for",
                "which launches are planned for",
                "when is",
                "when does",
            ]
        ):
            return "vehicle_profile"
        if plan.intent == "distribution":
            return "distribution"
        if "compare" in lowered or " vs " in lowered:
            return "comparison"
        if any(item.field == "active_year" for item in plan.filters):
            return "portfolio_window"
        if any(item.field in {"region_of_sales", "initial_prod_zone", "platform", "brand", "eea", "ota", "tcu_details", "infotainment_details"} for item in plan.filters):
            return "portfolio_filter"
        return "unknown"

    def _assess_grounding(self, query: str, plan: QueryPlan) -> str:
        lowered = query.lower()
        if plan.unsupported_reasons and any(
            "could not map this question to a deterministic launch query" in reason.lower()
            for reason in plan.unsupported_reasons
        ):
            return "ungrounded"
        if plan.clarification_questions:
            return "salvageable"
        if self._classify_query_frame(lowered, plan) == "unknown":
            return "ungrounded"
        return "grounded"

    def _resolution_state(self, plan: QueryPlan) -> str:
        if plan.unsupported_reasons:
            return "unsupported"
        if plan.clarification_questions:
            return "clarification_needed"
        return "resolved"

    def _build_planner_diagnostics(
        self,
        query: str,
        heuristic_plan: QueryPlan,
        final_plan: QueryPlan,
        llm_suggestion: dict[str, Any] | None,
        accepted_overrides: list[str],
        decision_notes: list[str],
    ) -> PlannerDiagnostics:
        llm_diag = None
        if llm_suggestion is not None:
            llm_diag = LlmSuggestion(
                intent=llm_suggestion.get("intent"),
                data_view=llm_suggestion.get("data_view"),
                confidence=float(llm_suggestion.get("confidence", 0.0) or 0.0),
                reasoning=str(llm_suggestion.get("reasoning", "") or ""),
                accepted_overrides=accepted_overrides,
            )

        return PlannerDiagnostics(
            query_frame=self._classify_query_frame(query.lower(), final_plan),
            grounding_status=self._assess_grounding(query, final_plan),
            resolution_state=self._resolution_state(final_plan),
            heuristic_baseline=self._snapshot_plan(heuristic_plan),
            llm_suggestion=llm_diag,
            final_resolved_plan=self._snapshot_plan(final_plan),
            decision_notes=decision_notes,
        )

    def _should_enrich_vehicle_brief(self, lowered: str) -> bool:
        return any(
            phrase in lowered
            for phrase in [
                "tell me about",
                "details for",
                "show launches for",
                "what launches are planned for",
                "which launches are planned for",
                "when is",
                "when does",
            ]
        )

    def _matches_vehicle_subject(self, lowered: str) -> bool:
        return re.search(r"\b(which|what|show|list)\b.*\b(vehicles|vehicle|car families|car family|launches)\b", lowered) is not None

    def _detect_data_view(
        self,
        lowered: str,
        temporal_window: tuple[str, str, str] | None = None,
        time_window_months: int | None = None,
    ) -> str:
        if self._detect_milestone_columns(lowered):
            return "vehicle"
        if re.search(r"^\s*when\s+(?:is|does)\b", lowered):
            return "vehicle"
        if any(token in lowered for token in ["mca ", "mca2", "mca sopm", "transition launch", "design launch"]):
            return "launch_event"
        if self._is_broad_launch_window_query(lowered) and (temporal_window or time_window_months):
            return "launch_event"
        if "mca" in lowered:
            return "launch_event"
        return "vehicle"

    def _detect_intent(self, lowered: str) -> str:
        if "ratio" in lowered or "volume impact" in lowered:
            return "distribution"
        if "month-wise" in lowered and "mca" in lowered and "mca2" in lowered:
            return "distribution"
        if self._matches_vehicle_subject(lowered):
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
            if "ros vs ipz" in lowered or "(ros vs ipz)" in lowered:
                groups.extend(["region_logic", "region_value"])
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

    def _dedupe_filters(self, filters: list[PlanFilter]) -> list[PlanFilter]:
        seen: set[tuple[str, str, str]] = set()
        ordered: list[PlanFilter] = []
        for item in filters:
            key = (item.field, item.operator, json.dumps(item.value, sort_keys=True))
            if key in seen:
                continue
            seen.add(key)
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

    def _normalize_year(self, raw_year: str) -> int:
        year = int(raw_year)
        if len(raw_year) == 2:
            return 2000 + year
        return year

    def _month_range(self, year: int, month: int) -> tuple[str, str]:
        start = f"{year:04d}-{month:02d}-01"
        if month == 12:
            end = f"{year + 1:04d}-01-01"
        else:
            end = f"{year:04d}-{month + 1:02d}-01"
        return start, end

    def _extract_temporal_window(self, lowered: str) -> tuple[str, str, str] | None:
        month_names = "|".join(sorted(MONTH_NAME_TO_NUMBER.keys(), key=len, reverse=True))

        month_match = re.search(rf"\b({month_names})\s+(20\d{{2}}|\d{{2}})\b", lowered)
        if month_match:
            month = MONTH_NAME_TO_NUMBER[month_match.group(1)]
            year = self._normalize_year(month_match.group(2))
            start, end = self._month_range(year, month)
            return start, end, f"{month_match.group(1).title()} {year}"

        quarter_match = re.search(r"\b(?:cy\s*)?(20\d{2}|\d{2})\s*q([1-4])\b", lowered)
        if not quarter_match:
            quarter_match = re.search(r"\bq([1-4])\s*(?:cy\s*)?(20\d{2}|\d{2})\b", lowered)
            if quarter_match:
                quarter = int(quarter_match.group(1))
                year = self._normalize_year(quarter_match.group(2))
                start_month = (quarter - 1) * 3 + 1
                start, _ = self._month_range(year, start_month)
                end_year = year + 1 if start_month == 10 else year
                end_month = 1 if start_month == 10 else start_month + 3
                return start, f"{end_year:04d}-{end_month:02d}-01", f"{year} Q{quarter}"
        else:
            year = self._normalize_year(quarter_match.group(1))
            quarter = int(quarter_match.group(2))
            start_month = (quarter - 1) * 3 + 1
            start, _ = self._month_range(year, start_month)
            end_year = year + 1 if start_month == 10 else year
            end_month = 1 if start_month == 10 else start_month + 3
            return start, f"{end_year:04d}-{end_month:02d}-01", f"{year} Q{quarter}"

        half_match = re.search(r"\b(?:cy\s*)?(20\d{2}|\d{2})\s*h([12])\b", lowered)
        if not half_match:
            half_match = re.search(r"\bh([12])\s*(?:cy\s*)?(20\d{2}|\d{2})\b", lowered)
            if half_match:
                half = int(half_match.group(1))
                year = self._normalize_year(half_match.group(2))
                start_month = 1 if half == 1 else 7
                start = f"{year:04d}-{start_month:02d}-01"
                end = f"{year + 1:04d}-01-01" if half == 2 else f"{year:04d}-07-01"
                return start, end, f"{year} H{half}"
        else:
            year = self._normalize_year(half_match.group(1))
            half = int(half_match.group(2))
            start_month = 1 if half == 1 else 7
            start = f"{year:04d}-{start_month:02d}-01"
            end = f"{year + 1:04d}-01-01" if half == 2 else f"{year:04d}-07-01"
            return start, end, f"{year} H{half}"

        year_match = re.search(r"\b(?:cy\s*)?(20\d{2})\b", lowered)
        if not year_match:
            year_match = re.search(r"\bcy\s*(\d{2})\b", lowered)
        if year_match:
            year = self._normalize_year(year_match.group(1))
            return f"{year:04d}-01-01", f"{year + 1:04d}-01-01", f"CY {year}"
        return None

    def _is_broad_launch_window_query(self, lowered: str) -> bool:
        if not any(
            token in lowered
            for token in [
                "launching",
                "launches",
                "launch ",
                "sopm in",
                "have sopm",
                "has sopm",
                "mca in",
                "have mca",
                "has mca",
                "mca2 in",
                "have mca2",
                "has mca2",
            ]
        ):
            return False
        return self._matches_vehicle_subject(lowered)

    def _extract_brand(self, lowered: str) -> str | None:
        match = re.search(r"\b([a-z0-9][a-z0-9&/-]*)\s+brand(?:'s)?\b", lowered)
        if not match:
            return None
        return match.group(1).upper()

    @lru_cache(maxsize=1)
    def _schema_value_catalog(self) -> dict[str, list[str]]:
        try:
            frame = LaunchDataLoader().load().frame
        except Exception:
            return {}

        catalog: dict[str, list[str]] = {}
        for field in SCHEMA_MATCH_FIELDS:
            if field not in frame.columns:
                continue
            values = sorted(
                {
                    str(value).strip()
                    for value in frame[field].dropna()
                    if str(value).strip() and str(value).strip().lower() != "unknown"
                }
            )
            if not values or len(values) > 80:
                continue
            catalog[field] = values
        return catalog

    def _normalize_stack_label(self, value: str) -> str:
        return (
            value.replace(".1", "")
            .replace(".2", "")
            .replace("PARTNER.1", "PARTNER")
            .replace("PARTNER.2", "PARTNER")
            .replace("R2eX.1", "R2eX")
        )

    def _stack_aliases(self, label: str) -> set[str]:
        normalized = self._normalize_stack_label(label)
        lowered = normalized.lower()
        compact = re.sub(r"[^a-z0-9]+", "", lowered)
        aliases = {lowered, compact}
        if lowered.endswith(" v2"):
            aliases.add(lowered.replace(" v2", "v2"))
        if lowered.endswith(" v1"):
            aliases.add(lowered.replace(" v1", "v1"))
        if " (sps)" in lowered:
            aliases.add(lowered.replace(" (sps)", ""))
        return {alias for alias in aliases if alias}

    def _alias_mentioned(self, lowered: str, alias: str) -> bool:
        normalized = alias.lower().strip()
        if not normalized:
            return False
        pattern = rf"(?<![a-z0-9]){re.escape(normalized)}(?![a-z0-9])"
        if re.search(pattern, lowered) is not None:
            return True
        compact_alias = re.sub(r"[^a-z0-9]+", "", normalized)
        if not compact_alias:
            return False
        flexible_compact = r"[^a-z0-9]*".join(re.escape(char) for char in compact_alias)
        compact_pattern = rf"(?<![a-z0-9]){flexible_compact}(?![a-z0-9])"
        return re.search(compact_pattern, lowered) is not None

    @lru_cache(maxsize=1)
    def _stack_component_catalog(self) -> dict[str, list[str]]:
        connectivity = sorted(
            {self._normalize_stack_label(value) for value in CONNECTIVITY_COLUMNS},
            key=lambda value: (-len(value), value),
        )
        infotainment = sorted(
            {self._normalize_stack_label(value) for value in INFOTAINMENT_COLUMNS},
            key=lambda value: (-len(value), value),
        )
        return {"tcu_details": connectivity, "infotainment_details": infotainment}

    @lru_cache(maxsize=1)
    def _entity_value_catalog(self) -> dict[str, list[str]]:
        try:
            frame = LaunchDataLoader().load().frame
        except Exception:
            return {}

        catalog: dict[str, list[str]] = {}
        for field in ENTITY_MATCH_FIELDS:
            if field not in frame.columns:
                continue
            values = sorted(
                {
                    str(value).strip()
                    for value in frame[field].dropna()
                    if str(value).strip() and str(value).strip().lower() != "unknown"
                },
                key=lambda value: (-len(value), value),
            )
            if values:
                catalog[field] = values
        return catalog

    def _value_mentioned(self, lowered: str, value: str) -> bool:
        normalized = value.lower().strip()
        if not normalized:
            return False
        pattern = rf"(?<![a-z0-9]){re.escape(normalized)}(?![a-z0-9])"
        return re.search(pattern, lowered) is not None

    def _find_value_spans(self, lowered: str, value: str) -> list[tuple[int, int]]:
        normalized = value.lower().strip()
        if not normalized:
            return []
        pattern = rf"(?<![a-z0-9]){re.escape(normalized)}(?![a-z0-9])"
        return [(match.start(), match.end()) for match in re.finditer(pattern, lowered)]

    def _detect_entity_filters(self, lowered: str) -> tuple[list[PlanFilter], str]:
        candidates: list[tuple[int, int, int, int, str, str]] = []
        priorities = {field: index for index, field in enumerate(ENTITY_MATCH_FIELDS)}

        for field, values in self._entity_value_catalog().items():
            for value in values:
                for start, end in self._find_value_spans(lowered, value):
                    candidates.append((-(end - start), priorities[field], start, end, field, value))

        candidates.sort()
        selected: list[tuple[int, int, str, str]] = []
        occupied: list[tuple[int, int]] = []
        for _, _, start, end, field, value in candidates:
            if any(not (end <= taken_start or start >= taken_end) for taken_start, taken_end in occupied):
                continue
            occupied.append((start, end))
            selected.append((start, end, field, value))

        mask_chars = list(lowered)
        filters: list[PlanFilter] = []
        for start, end, field, value in sorted(selected, key=lambda item: item[0]):
            for index in range(start, end):
                mask_chars[index] = " "
            filters.append(
                PlanFilter(
                    field=field,
                    operator="=",
                    value=value,
                    rationale=f"Match the requested {field.replace('_', ' ')} from the uploaded LRP.",
                )
            )
        return filters, "".join(mask_chars)

    def _add_stack_component_filters(self, lowered: str, filters: list[PlanFilter]) -> list[PlanFilter]:
        updated = list(filters)

        def add_for_field(field: str, hints: set[str]) -> None:
            if not any(hint in lowered for hint in hints):
                return
            existing = {
                str(item.value).upper()
                for item in updated
                if item.field == field and item.operator == "contains"
            }
            for label in self._stack_component_catalog()[field]:
                aliases = self._stack_aliases(label)
                if not any(self._alias_mentioned(lowered, alias) for alias in aliases):
                    continue
                if label.upper() in existing:
                    continue
                updated.append(
                    PlanFilter(
                        field=field,
                        operator="contains",
                        value=label,
                        rationale=f"Match the requested {field.replace('_', ' ')} component from the uploaded LRP.",
                    )
                )

        add_for_field("tcu_details", TCU_HINTS)
        add_for_field("infotainment_details", INFOTAINMENT_HINTS)
        return updated

    def _add_schema_value_filters(self, lowered: str, filters: list[PlanFilter]) -> list[PlanFilter]:
        existing_exact = {(item.field, item.operator, str(item.value).upper()) for item in filters}
        updated = list(filters)

        for field, values in self._schema_value_catalog().items():
            if any(item.field == field for item in updated):
                continue
            if field in REGION_LIKE_FIELDS and any(item.field in REGION_LIKE_FIELDS for item in updated):
                continue
            matches = [value for value in values if self._value_mentioned(lowered, value)]
            if len(matches) != 1:
                continue
            value = matches[0]
            key = (field, "=", str(value).upper())
            if key in existing_exact:
                continue
            updated.append(
                PlanFilter(
                    field=field,
                    operator="=",
                    value=value,
                    rationale=f"Match the requested {field.replace('_', ' ')} value from the uploaded LRP.",
                )
            )
        return updated

    def _add_fallback_car_family_filter(self, lowered: str, filters: list[PlanFilter]) -> list[PlanFilter]:
        if any(item.field in {"car_family", "commercial_name", "car_family_code"} for item in filters):
            return filters

        focus_patterns = [
            r"tell me about\s+(.+)$",
            r"give me details for\s+(.+)$",
            r"details for\s+(.+)$",
            r"show launches for\s+(.+)$",
            r"what launches are planned for\s+(.+)$",
            r"which launches are planned for\s+(.+)$",
            r"when is\s+(.+?)\s+launching\??$",
            r"when does\s+(.+?)\s+launch\??$",
        ]
        subject: str | None = None
        for pattern in focus_patterns:
            match = re.search(pattern, lowered, flags=re.IGNORECASE)
            if match:
                subject = match.group(1).strip()
                break
        if not subject:
            return filters

        code_match = re.fullmatch(r"[A-Z][A-Z0-9_-]{2,}", subject.upper())
        if not code_match:
            return filters

        candidate = code_match.group(0)
        if candidate.isdigit() or candidate in CAR_FAMILY_FALLBACK_EXCLUSIONS:
            return filters
        return filters + [
            PlanFilter(
                field="car_family",
                operator="=",
                value=candidate,
                rationale="Use a car-family-like code in the question as an exact vehicle identifier.",
            )
        ]

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

    def _detect_milestone_columns(self, lowered: str) -> list[str]:
        explicit_matches = [
            column
            for column, patterns in MILESTONE_FIELD_ALIASES.items()
            if any(re.search(pattern, lowered) for pattern in patterns)
        ]
        if explicit_matches:
            return [column for column in MILESTONE_COLUMN_ORDER if column in explicit_matches]
        if "milestone" in lowered or "milestones" in lowered:
            return list(MILESTONE_COLUMN_ORDER)
        return []

    def _detect_milestone_anchor(self, lowered: str) -> str:
        if "mca2" in lowered or "mca 2" in lowered:
            return "mca2_sopm"
        if re.search(r"\bmca\b", lowered):
            return "mca_sopm"
        return "sopm"

    def _detect_milestone_deliverable_codes(self, lowered: str, milestone_columns: list[str]) -> list[str]:
        if not milestone_columns:
            return []
        if not any(
            token in lowered
            for token in ["deliverable", "deliverables", "governance", "readiness", "objective", "risk", "risks", "ownership", "timeline", "timelines", "escalation"]
        ):
            return []
        codes = [MILESTONE_COLUMN_TO_CODE[column] for column in milestone_columns if column in MILESTONE_COLUMN_TO_CODE]
        return self._dedupe(codes)

    def _add_milestone_anchor_filters(self, filters: list[PlanFilter], milestone_anchor: str | None) -> list[PlanFilter]:
        if milestone_anchor == "mca_sopm" and not any(item.field == "has_mca" for item in filters):
            return filters + [
                PlanFilter(
                    field="has_mca",
                    operator="=",
                    value=True,
                    rationale="Milestone derivation at MCA requires rows with an MCA date.",
                )
            ]
        if milestone_anchor == "mca2_sopm" and not any(item.field == "has_mca2" for item in filters):
            return filters + [
                PlanFilter(
                    field="has_mca2",
                    operator="=",
                    value=True,
                    rationale="Milestone derivation at MCA2 requires rows with an MCA2 date.",
                )
            ]
        return filters

    def _detect_filters(
        self,
        lowered: str,
        time_window_months: int | None,
        analysis_year: int | None,
        data_view: str,
        analysis_mode: str,
        temporal_window: tuple[str, str, str] | None,
        milestone_columns: list[str],
        force_launch_event_window: bool = False,
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
            if temporal_window is not None and (self._is_broad_launch_window_query(lowered) or force_launch_event_window):
                start_date, end_date, label = temporal_window
                filters.extend(
                    [
                        PlanFilter(
                            field="launch_date",
                            operator=">=",
                            value=start_date,
                            rationale=f"Restrict launch events to the deterministic launch window starting {label}.",
                        ),
                        PlanFilter(
                            field="launch_date",
                            operator="<",
                            value=end_date,
                            rationale=f"Restrict launch events to the deterministic launch window ending before {end_date}.",
                        ),
                    ]
                )
            elif analysis_year is not None and (launch_year_query or analysis_mode == "overlap"):
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
            elif "sopm" in lowered and not combined_stage_query:
                filters.append(
                    PlanFilter(
                        field="launch_stage",
                        operator="=",
                        value="SOPM",
                        rationale="Query specifically targets SOPM events.",
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
        elif temporal_window is not None and milestone_columns:
            start_date, end_date, label = temporal_window
            filters.append(
                PlanFilter(
                    field="milestone_window",
                    operator="in",
                    value={"columns": milestone_columns, "start": start_date, "end": end_date},
                    rationale=f"Restrict derived milestone dates to the deterministic launch window {label}.",
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
        elif analysis_year is not None and ("active in" in lowered or "active vehicles" in lowered):
            filters.append(
                PlanFilter(
                    field="active_year",
                    operator="=",
                    value=analysis_year,
                    rationale=f"Vehicle must be active during {analysis_year}.",
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
        if re.search(r"\bfota\b", lowered):
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
        matched_regions = [region for region in ["CHN", "EER", "EEU", "IAP", "MEA", "NAM", "SAM"] if region.lower() in lowered]
        if len(matched_regions) == 1:
            filters.append(
                PlanFilter(
                    field=region_field,
                    operator="contains",
                    value=matched_regions[0],
                    rationale=f"Filter to {matched_regions[0]} on the requested regional dimension.",
                )
            )
        elif len(matched_regions) > 1:
            filters.append(
                PlanFilter(
                    field=region_field,
                    operator="contains_any",
                    value=matched_regions,
                    rationale=f"Filter to any of {', '.join(matched_regions)} on the requested regional dimension.",
                )
            )
        requested_brand = self._extract_brand(lowered)
        if requested_brand:
            filters.append(
                PlanFilter(
                    field="brand",
                    operator="=",
                    value=requested_brand,
                    rationale=f"Filter to the {requested_brand} brand requested in the question.",
                )
            )
        return filters

    def _requested_columns(
        self,
        intent: str,
        lowered: str,
        analysis_year: int | None,
        data_view: str,
        milestone_columns: list[str],
        milestone_anchor: str | None,
        milestone_deliverable_codes: list[str],
    ) -> list[str]:
        if intent == "count":
            return ["car_family"]
        if data_view == "launch_event":
            columns = [
                "car_family",
                "brand",
                "commercial_name",
                "initial_prod_zone",
                "region_of_sales",
                "sopm",
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
            if milestone_columns:
                columns.extend(milestone_columns)
                columns.append("milestone_anchor_date")
                columns.append("milestone_anchor_label")
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
        if any(
            phrase in lowered
            for phrase in [
                "tell me about",
                "details for",
                "show launches for",
                "what launches are planned for",
                "which launches are planned for",
                "when is",
                "when does",
            ]
        ):
            columns.extend(["mca_sopm", "mca2_sopm", "eop"])
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
        if milestone_columns:
            columns.extend(milestone_columns)
            columns.append("milestone_anchor_date")
            columns.append("milestone_anchor_label")
            if milestone_anchor and milestone_anchor not in columns:
                columns.append(milestone_anchor)
        if milestone_deliverable_codes:
            columns.extend(
                [
                    "deliverable_milestone_code",
                    "deliverable_milestone_label",
                    "deliverable_governance_communication",
                    "deliverable_readiness_objectives",
                    "deliverable_timelines",
                    "deliverable_risks",
                    "deliverable_escalation_path",
                    "deliverable_ownership",
                ]
            )
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
        temporal_window: tuple[str, str, str] | None,
        milestone_anchor: str | None,
        milestone_columns: list[str],
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
        if temporal_window:
            clauses.append(f"Apply a deterministic launch window of {temporal_window[2]}.")
        if milestone_columns:
            clauses.append(f"Derive milestone dates backward from {ANCHOR_LABELS[milestone_anchor or 'sopm']} and round to the nearest Monday.")
        if "risk" in lowered:
            clauses.append("Surface deterministic signals only when the dataset contains explicit supporting fields.")
        return " ".join(clauses)
