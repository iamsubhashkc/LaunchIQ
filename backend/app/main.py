from __future__ import annotations

from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .clarification import merge_clarification_answers
from .execution import ExecutionEngine
from .learning import LearningStore
from .milestone_store import MilestoneStore
from .models import (
    ClarifyRequest,
    FeedbackRequest,
    FeedbackResponse,
    MilestoneDeliverable,
    MilestoneDeliverableListResponse,
    MilestoneDeliverableUpdateRequest,
    QueryRequest,
    QueryResponse,
)
from .planner import Planner


app = FastAPI(title="LaunchIQ API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

planner = Planner()
executor = ExecutionEngine()
learning_store = LearningStore()
milestone_store = MilestoneStore()


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/query", response_model=QueryResponse)
def query(request: QueryRequest) -> QueryResponse:
    plan = planner.build_plan(request.query)
    if plan.unsupported_reasons:
        return QueryResponse(status="unsupported", query=request.query, plan=plan)
    if plan.clarification_questions:
        return QueryResponse(
            status="clarification_needed",
            query=request.query,
            plan=plan,
            clarification=plan.clarification_questions,
        )
    result = executor.execute(plan)
    return QueryResponse(
        status="ok",
        query=request.query,
        plan=plan,
        answer_type=result.answer_type,
        answer=result.answer,
        explanation=result.explanation,
    )


@app.post("/clarify", response_model=QueryResponse)
def clarify(request: ClarifyRequest) -> QueryResponse:
    augmented_query = merge_clarification_answers(request.original_query, request.answers)
    plan = planner.build_plan(augmented_query)
    if plan.unsupported_reasons:
        return QueryResponse(status="unsupported", query=request.original_query, plan=plan)

    if "intent" in request.answers:
        plan.intent = request.answers["intent"]
    if request.answers.get("group_by") == "month":
        plan.group_by = ["sopm_month"]
    if request.answers.get("group_by") == "month_and_platform":
        plan.group_by = ["sopm_month", "platform"]
        if plan.intent == "timeline":
            plan.intent = "distribution"
    if request.answers.get("requested_columns") == "list_with_readiness_fields":
        for field in ["migration_readiness", "current_sdp", "target_sdp"]:
            if field not in plan.requested_columns:
                plan.requested_columns.append(field)

    plan.clarification_questions = []
    plan.ambiguity_notes = []
    result = executor.execute(plan)
    return QueryResponse(
        status="ok",
        query=request.original_query,
        plan=plan,
        answer_type=result.answer_type,
        answer=result.answer,
        explanation=result.explanation,
    )


@app.post("/feedback", response_model=FeedbackResponse)
def feedback(request: FeedbackRequest) -> FeedbackResponse:
    stored = learning_store.store_feedback(
        query=request.query,
        plan=request.plan,
        answer=request.answer,
        rating=request.rating,
        correction=request.correction,
    )
    return FeedbackResponse(stored=True, record_id=stored["record_id"], stored_at=stored["stored_at"])


@app.get("/milestones/deliverables", response_model=MilestoneDeliverableListResponse)
def list_milestone_deliverables() -> MilestoneDeliverableListResponse:
    items = [MilestoneDeliverable(**item) for item in milestone_store.list_deliverables()]
    return MilestoneDeliverableListResponse(items=items)


@app.get("/milestones/deliverables/{milestone_code}", response_model=MilestoneDeliverable)
def get_milestone_deliverable(milestone_code: str) -> MilestoneDeliverable:
    item = milestone_store.get_deliverable(milestone_code)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Unknown milestone deliverable: {milestone_code}")
    return MilestoneDeliverable(**item)


@app.put("/milestones/deliverables/{milestone_code}", response_model=MilestoneDeliverable)
def update_milestone_deliverable(
    milestone_code: str,
    request: MilestoneDeliverableUpdateRequest,
) -> MilestoneDeliverable:
    item = milestone_store.upsert_deliverable(milestone_code, request.model_dump(exclude_none=True))
    return MilestoneDeliverable(**item)
