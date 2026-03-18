from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .clarification import merge_clarification_answers
from .execution import ExecutionEngine
from .learning import LearningStore
from .models import ClarifyRequest, FeedbackRequest, FeedbackResponse, QueryRequest, QueryResponse
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
