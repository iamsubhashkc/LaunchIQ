from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import duckdb
import pandas as pd

from .data_loader import LaunchDataLoader
from .milestone_store import MilestoneStore
from .milestones import ANCHOR_LABELS, MILESTONE_OFFSETS, derive_milestone_date
from .models import ExecutionExplanation, QueryPlan


DISPLAY_COLUMNS = [
    "car_family",
    "brand",
    "commercial_name",
    "initial_prod_zone",
    "region_of_sales",
    "eea",
    "tcu_details",
    "infotainment_details",
    "ota",
    "sopm",
    "platform",
    "program",
]


@dataclass
class ExecutionResult:
    answer_type: str
    answer: Any
    explanation: ExecutionExplanation


class ExecutionEngine:
    def __init__(
        self,
        data_loader: LaunchDataLoader | None = None,
        milestone_store: MilestoneStore | None = None,
    ) -> None:
        self.data_loader = data_loader or LaunchDataLoader()
        self.milestone_store = milestone_store or MilestoneStore()

    def execute(self, plan: QueryPlan) -> ExecutionResult:
        loaded = self.data_loader.load()
        dataframe = loaded.events_frame.copy() if plan.data_view == "launch_event" else loaded.frame.copy()
        if plan.milestone_anchor and plan.milestone_columns:
            dataframe = self._apply_derived_milestones(dataframe, plan.milestone_anchor, plan.milestone_columns)
        if plan.milestone_deliverable_codes:
            dataframe = self._apply_milestone_deliverables(dataframe, plan.milestone_deliverable_codes)
        table_name = "launch_events" if plan.data_view == "launch_event" else "launch_programs"

        connection = duckdb.connect()
        connection.register(table_name, dataframe)
        where_clauses, parameters, filter_notes = self._build_where(plan)
        sql = self._build_sql(plan, where_clauses, table_name)
        execution_parameters = parameters
        if plan.intent == "distribution" and table_name == "launch_programs" and plan.group_by[:2] == ["region_logic", "region_value"]:
            repeat_count = 2 if plan.region_scope in {"ANY", "BOTH"} else 1
            execution_parameters = parameters * repeat_count
        result = connection.execute(sql, execution_parameters).fetchdf()
        connection.close()

        answer = self._shape_answer(plan, result)
        explanation = ExecutionExplanation(
            generated_sql=sql,
            applied_filters=filter_notes,
            grouping=plan.group_by,
            notes=[
                "List and count intents use DISTINCT semantics for the active view.",
                f"Source dataset: {loaded.source_kind} ({loaded.source_path.name}).",
                f"Execution view: {plan.data_view}.",
                *(
                    [
                        f"Derived milestones anchored to {ANCHOR_LABELS[plan.milestone_anchor]} using fixed week offsets and nearest-Monday rounding."
                    ]
                    if plan.milestone_anchor and plan.milestone_columns
                    else []
                ),
                *(
                    [f"Attached milestone deliverables from the updateable milestone catalog for {', '.join(plan.milestone_deliverable_codes)}."]
                    if plan.milestone_deliverable_codes
                    else []
                ),
            ],
        )
        return ExecutionResult(answer_type=plan.intent, answer=answer, explanation=explanation)

    def _apply_derived_milestones(
        self,
        dataframe: pd.DataFrame,
        anchor_field: str,
        milestone_columns: list[str],
    ) -> pd.DataFrame:
        if anchor_field not in dataframe.columns:
            return dataframe

        enriched = dataframe.copy()
        anchor_series = pd.to_datetime(enriched[anchor_field], errors="coerce")
        enriched.loc[:, "milestone_anchor_date"] = anchor_series
        enriched.loc[:, "milestone_anchor_label"] = ANCHOR_LABELS[anchor_field]

        for column in milestone_columns:
            offset_weeks = MILESTONE_OFFSETS.get(column)
            if offset_weeks is None:
                continue
            enriched.loc[:, column] = anchor_series.apply(lambda value: derive_milestone_date(value, offset_weeks))
        return enriched

    def _apply_milestone_deliverables(self, dataframe: pd.DataFrame, milestone_codes: list[str]) -> pd.DataFrame:
        deliverables = self.milestone_store.get_deliverables(milestone_codes)
        if not deliverables:
            return dataframe

        merged = dataframe.copy()
        head = deliverables[0]
        merged.loc[:, "deliverable_milestone_code"] = head.get("milestone_code", "")
        merged.loc[:, "deliverable_milestone_label"] = head.get("milestone_label", "")
        merged.loc[:, "deliverable_governance_communication"] = head.get("governance_communication", "")
        merged.loc[:, "deliverable_readiness_objectives"] = head.get("readiness_objectives", "")
        merged.loc[:, "deliverable_timelines"] = head.get("timelines", "")
        merged.loc[:, "deliverable_risks"] = head.get("risks", "")
        merged.loc[:, "deliverable_escalation_path"] = head.get("escalation_path", "")
        merged.loc[:, "deliverable_ownership"] = head.get("ownership", "")
        return merged

    def _build_where(self, plan: QueryPlan) -> tuple[list[str], list[Any], list[dict[str, Any]]]:
        where_clauses = ["1 = 1"]
        parameters: list[Any] = []
        notes: list[dict[str, Any]] = []

        for item in plan.filters:
            clause, values = self._translate_filter(item.field, item.operator, item.value)
            where_clauses.append(clause)
            parameters.extend(values)
            notes.append({"field": item.field, "operator": item.operator, "value": item.value, "rationale": item.rationale})
        return where_clauses, parameters, notes

    def _translate_filter(self, field: str, operator: str, value: Any) -> tuple[str, list[Any]]:
        if field in {"sopm", "launch_date"} and value == "CURRENT_DATE":
            return (f"{field} >= CURRENT_DATE", [])
        if field in {"sopm", "launch_date"} and isinstance(value, str) and value.startswith("CURRENT_DATE + INTERVAL"):
            return (f"{field} <= {value}", [])
        if field == "launch_year":
            return ("launch_year = ?", [value])
        if field == "sopm_year":
            return ("sopm_year = ?", [value])
        if field == "active_year":
            year = int(value)
            return ("sopm <= ? AND eop >= ?", [f"{year}-12-31", f"{year}-01-01"])
        if field == "eop_within_months":
            months = int(value)
            return (f"eop BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '{months} months'", [])
        if operator == "=":
            return (f"{field} = ?", [value])
        if operator == "!=":
            return (f"{field} != ?", [value])
        if operator in {"<=", ">=", "<", ">"}:
            return (f"{field} {operator} ?", [value])
        if operator == "contains":
            return (f"LOWER({field}) LIKE ?", [f"%{str(value).lower()}%"])
        if operator == "not_contains":
            return (f"LOWER({field}) NOT LIKE ?", [f"%{str(value).lower()}%"])
        if operator == "in":
            placeholders = ", ".join(["?"] * len(value))
            return (f"{field} IN ({placeholders})", list(value))
        if operator == "not_in":
            placeholders = ", ".join(["?"] * len(value))
            return (f"{field} NOT IN ({placeholders})", list(value))
        raise ValueError(f"Unsupported filter operator: {operator}")

    def _build_sql(self, plan: QueryPlan, where_clauses: list[str], table_name: str) -> str:
        where_sql = " AND ".join(where_clauses)

        if plan.analysis_mode == "overlap":
            return self._build_overlap_sql(where_sql, table_name)

        if plan.intent == "count":
            aggregate = self._metric_aggregate(plan.metric)
            return f"""
                SELECT {aggregate} AS value
                FROM {table_name}
                WHERE {where_sql}
            """

        if plan.intent == "distribution":
            if table_name == "launch_programs" and plan.group_by[:2] == ["region_logic", "region_value"]:
                return self._build_region_distribution_sql(where_sql, plan.region_scope, plan.metric)
            group_sql = ", ".join(plan.group_by)
            aggregate = self._metric_aggregate(plan.metric)
            return f"""
                SELECT {group_sql}, {aggregate} AS value
                FROM {table_name}
                WHERE {where_sql}
                GROUP BY {group_sql}
                ORDER BY value DESC, {group_sql}
            """

        if plan.intent == "timeline":
            aggregate = self._metric_aggregate(plan.metric)
            time_field = "launch_month" if table_name == "launch_events" else "sopm_month"
            return f"""
                SELECT {time_field}, {aggregate} AS value
                FROM {table_name}
                WHERE {where_sql}
                GROUP BY {time_field}
                ORDER BY {time_field}
            """

        return self._build_list_sql(plan, where_sql, table_name)

    def _build_overlap_sql(self, where_sql: str, table_name: str) -> str:
        return f"""
            SELECT
                launch_month,
                COUNT(DISTINCT launch_event_id) AS event_count,
                COUNT(DISTINCT launch_stage) AS stage_count,
                STRING_AGG(DISTINCT launch_stage, ', ' ORDER BY launch_stage) AS stage_mix
            FROM {table_name}
            WHERE {where_sql}
            GROUP BY launch_month
            HAVING COUNT(DISTINCT launch_stage) > 1
            ORDER BY event_count DESC, launch_month
        """

    def _build_region_distribution_sql(self, where_sql: str, region_scope: str, metric: str) -> str:
        aggregate = self._metric_aggregate(metric)
        selects: list[str] = []
        if region_scope in {"ANY", "ROS", "BOTH"}:
            selects.append(
                f"""
                SELECT 'RoS' AS region_logic, region_of_sales AS region_value, {aggregate} AS value
                FROM launch_programs
                WHERE {where_sql}
                GROUP BY region_of_sales
                """
            )
        if region_scope in {"ANY", "IPZ", "BOTH"}:
            selects.append(
                f"""
                SELECT 'IPZ' AS region_logic, initial_prod_zone AS region_value, {aggregate} AS value
                FROM launch_programs
                WHERE {where_sql}
                GROUP BY initial_prod_zone
                """
            )
        union_sql = "\nUNION ALL\n".join(selects)
        return f"""
            {union_sql}
            ORDER BY region_logic, value DESC, region_value
        """

    def _build_list_sql(self, plan: QueryPlan, where_sql: str, table_name: str) -> str:
        requested = plan.requested_columns or DISPLAY_COLUMNS
        column_sql = ", ".join(requested)
        order_sql = self._list_order_sql(plan.sort_by, table_name)
        return f"""
            SELECT DISTINCT {column_sql}
            FROM {table_name}
            WHERE {where_sql}
            ORDER BY {order_sql}
        """

    def _aggregate_select(self, column: str) -> str:
        if column in {"car_family", "launch_event_id"}:
            return column
        if column in {"launch_volume", "total_volume", "volume_first_2_years"} or column.startswith("volume_"):
            return f"ROUND(SUM({column})) AS {column}"
        if column in {"region_of_sales_count", "initial_prod_zone_count"}:
            return f"MAX({column}) AS {column}"
        if column in {
            "ota_capability",
            "eea_available",
            "adas_capability",
            "connectivity_capability",
            "declining_post_sopm",
            "mixed_tcu",
            "mixed_architecture",
            "has_mca",
            "has_mca2",
        }:
            return f"BOOL_OR({column}) AS {column}"
        if column in {"sopm", "mca_sopm", "mca2_sopm", "launch_date", "milestone_anchor_date"}:
            return f"MIN({column}) AS {column}"
        if column == "eop":
            return "MAX(eop) AS eop"
        if column == "lifecycle_years":
            return "ROUND(MAX(lifecycle_years), 1) AS lifecycle_years"
        if column in {"months_sopm_to_mca", "months_mca_to_mca2", "min_transition_gap_months"}:
            return f"ROUND(MIN({column}), 1) AS {column}"
        return f"STRING_AGG(DISTINCT CAST({column} AS VARCHAR), ', ' ORDER BY CAST({column} AS VARCHAR)) AS {column}"

    def _metric_aggregate(self, metric: str) -> str:
        if metric == "car_family":
            return "COUNT(DISTINCT car_family)"
        if metric == "launch_event":
            return "COUNT(DISTINCT launch_event_id)"
        if metric.startswith("volume_") or metric in {"launch_volume", "total_volume"}:
            return f"ROUND(SUM({metric}))"
        return "COUNT(DISTINCT car_family)"

    def _list_order_sql(self, sort_by: list[str], table_name: str) -> str:
        if not sort_by:
            if table_name == "launch_events":
                return "launch_date, car_family, commercial_name, region_of_sales, initial_prod_zone"
            return "sopm, car_family, commercial_name, region_of_sales, initial_prod_zone"

        clauses: list[str] = []
        for item in sort_by:
            direction = "DESC" if item.startswith("-") else "ASC"
            field = item[1:] if item.startswith("-") else item
            clauses.append(f"{field} {direction}")
        clauses.extend(["car_family", "commercial_name", "region_of_sales", "initial_prod_zone"])
        return ", ".join(clauses)

    def _shape_answer(self, plan: QueryPlan, result: pd.DataFrame) -> Any:
        if plan.intent == "count":
            return {"value": int(result.iloc[0]["value"]) if not result.empty else 0}
        source = result.copy()
        formatted = result.copy().astype(object)
        for column in source.columns:
            if pd.api.types.is_datetime64_any_dtype(source[column]):
                series = source[column].dt.strftime("%Y-%m-%dT%H:%M:%S").fillna("").astype(object)
            else:
                series = source[column].where(source[column].notna(), "").astype(object)
            formatted.loc[:, column] = series
        return formatted.to_dict(orient="records")
