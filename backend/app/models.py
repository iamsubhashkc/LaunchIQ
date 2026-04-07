from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


AggregationType = Literal["list", "count", "distribution", "timeline"]
FilterOperator = Literal[
    "=",
    "!=",
    "in",
    "not_in",
    "contains",
    "contains_any",
    "stack_contains",
    "stack_contains_any",
    "not_contains",
    "<=",
    ">=",
    "<",
    ">",
]
PlannerMode = Literal["heuristic", "hybrid", "llm"]


class PlanFilter(BaseModel):
    field: str
    operator: FilterOperator
    value: Any
    rationale: str | None = None


class ClarificationPrompt(BaseModel):
    question: str
    field: str
    options: list[str] = Field(default_factory=list)
    reason: str


class LlmSuggestion(BaseModel):
    intent: AggregationType | None = None
    data_view: Literal["vehicle", "launch_event"] | None = None
    confidence: float = 0.0
    reasoning: str = ""
    accepted_overrides: list[str] = Field(default_factory=list)


class PlanSnapshot(BaseModel):
    intent: AggregationType
    data_view: Literal["vehicle", "launch_event"]
    group_by: list[str] = Field(default_factory=list)
    filters: list[PlanFilter] = Field(default_factory=list)
    requested_columns: list[str] = Field(default_factory=list)
    region_scope: Literal["ANY", "ROS", "IPZ", "BOTH"] = "ANY"
    milestone_anchor: Literal["sopm", "mca_sopm", "mca2_sopm"] | None = None
    milestone_columns: list[str] = Field(default_factory=list)
    unsupported_reasons: list[str] = Field(default_factory=list)
    reasoning_summary: str = ""


class FeedbackHint(BaseModel):
    query: str
    rating: Literal["helpful", "incorrect", "needs_more_detail"]
    correction: str | None = None
    match_type: Literal["exact", "similar"] = "similar"
    score: float = 0.0
    stored_at: datetime | None = None


class PlannerDiagnostics(BaseModel):
    query_frame: str = "unknown"
    grounding_status: Literal["grounded", "salvageable", "ungrounded"] = "ungrounded"
    resolution_state: Literal["resolved", "clarification_needed", "unsupported"] = "resolved"
    heuristic_baseline: PlanSnapshot
    llm_suggestion: LlmSuggestion | None = None
    final_resolved_plan: PlanSnapshot
    feedback_context: list[FeedbackHint] = Field(default_factory=list)
    decision_notes: list[str] = Field(default_factory=list)


class QueryPlan(BaseModel):
    intent: AggregationType
    subject: str = "car_family"
    metric: str = "car_family"
    data_view: Literal["vehicle", "launch_event"] = "vehicle"
    analysis_mode: Literal["standard", "overlap"] = "standard"
    milestone_anchor: Literal["sopm", "mca_sopm", "mca2_sopm"] | None = None
    milestone_columns: list[str] = Field(default_factory=list)
    milestone_deliverable_codes: list[str] = Field(default_factory=list)
    sort_by: list[str] = Field(default_factory=list)
    group_by: list[str] = Field(default_factory=list)
    filters: list[PlanFilter] = Field(default_factory=list)
    time_window_months: int | None = None
    region_scope: Literal["ANY", "ROS", "IPZ", "BOTH"] = "ANY"
    requested_columns: list[str] = Field(default_factory=list)
    ambiguity_notes: list[str] = Field(default_factory=list)
    clarification_questions: list[ClarificationPrompt] = Field(default_factory=list)
    unsupported_reasons: list[str] = Field(default_factory=list)
    reasoning_summary: str = ""
    planner_diagnostics: PlannerDiagnostics | None = None


class QueryRequest(BaseModel):
    query: str
    planner_mode: PlannerMode | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class ClarifyRequest(BaseModel):
    original_query: str
    answers: dict[str, str] = Field(default_factory=dict)
    planner_mode: PlannerMode | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class FeedbackRequest(BaseModel):
    query: str
    plan: dict[str, Any]
    answer: Any
    rating: Literal["helpful", "incorrect", "needs_more_detail"]
    correction: str | None = None


class ExportRequest(BaseModel):
    query: str
    plan: dict[str, Any] = Field(default_factory=dict)
    answer_type: AggregationType | None = None
    answer: Any = None


class ExecutionExplanation(BaseModel):
    generated_sql: str
    applied_filters: list[dict[str, Any]]
    grouping: list[str]
    notes: list[str] = Field(default_factory=list)


class QueryResponse(BaseModel):
    status: Literal["ok", "clarification_needed", "unsupported"]
    query: str
    plan: QueryPlan
    answer_type: AggregationType | None = None
    answer: Any = None
    explanation: ExecutionExplanation | None = None
    clarification: list[ClarificationPrompt] = Field(default_factory=list)


class FeedbackResponse(BaseModel):
    stored: bool
    record_id: str
    stored_at: datetime


class FeedbackReportEntry(BaseModel):
    query: str
    rating: Literal["helpful", "incorrect", "needs_more_detail"]
    correction: str | None = None
    stored_at: datetime


class FeedbackReportResponse(BaseModel):
    total_feedback: int
    helpful_count: int
    incorrect_count: int
    needs_more_detail_count: int
    top_corrections: list[str] = Field(default_factory=list)
    recent_feedback: list[FeedbackReportEntry] = Field(default_factory=list)


class DataViewSummary(BaseModel):
    view: Literal["vehicle", "launch_event", "feedback", "milestones"]
    label: str
    row_count: int
    column_count: int
    columns: list[str] = Field(default_factory=list)


class DataCatalogResponse(BaseModel):
    source_kind: str
    source_path: str
    workbook_present: bool
    views: list[DataViewSummary] = Field(default_factory=list)


class DataPreviewResponse(BaseModel):
    view: Literal["vehicle", "launch_event", "feedback", "milestones"]
    label: str
    row_count: int
    limit: int
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)


class DataUploadResponse(BaseModel):
    stored: bool
    filename: str
    destination: str
    source_kind: str
    row_count: int
    launch_event_count: int


class MilestoneDeliverable(BaseModel):
    milestone_code: str
    milestone_label: str
    sequence_order: int
    governance_communication: str
    readiness_objectives: str
    timelines: str
    risks: str
    escalation_path: str
    ownership: str
    updated_at: datetime


class MilestoneDeliverableUpdateRequest(BaseModel):
    milestone_label: str | None = None
    sequence_order: int | None = None
    governance_communication: str | None = None
    readiness_objectives: str | None = None
    timelines: str | None = None
    risks: str | None = None
    escalation_path: str | None = None
    ownership: str | None = None


class MilestoneDeliverableListResponse(BaseModel):
    items: list[MilestoneDeliverable]
