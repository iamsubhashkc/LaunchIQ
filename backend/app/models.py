from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


AggregationType = Literal["list", "count", "distribution", "timeline"]
FilterOperator = Literal["=", "!=", "in", "not_in", "contains", "not_contains", "<=", ">=", "<", ">"]


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


class QueryRequest(BaseModel):
    query: str
    context: dict[str, Any] = Field(default_factory=dict)


class ClarifyRequest(BaseModel):
    original_query: str
    answers: dict[str, str] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)


class FeedbackRequest(BaseModel):
    query: str
    plan: dict[str, Any]
    answer: Any
    rating: Literal["helpful", "incorrect", "needs_more_detail"]
    correction: str | None = None


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
