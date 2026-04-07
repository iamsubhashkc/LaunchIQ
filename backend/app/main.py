from __future__ import annotations

from io import BytesIO
import re
from pathlib import Path

from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import Query
from fastapi import Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd

from .clarification import merge_clarification_answers
from .config import SAMPLE_LRP_XLSX
from .data_loader import LaunchDataLoader
from .execution import ExecutionEngine
from .learning import LearningStore
from .milestone_store import MilestoneStore
from .models import (
    ClarifyRequest,
    DataCatalogResponse,
    DataPreviewResponse,
    DataUploadResponse,
    ExportRequest,
    FeedbackRequest,
    FeedbackReportResponse,
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

learning_store = LearningStore()
planner = Planner(learning_store=learning_store)
executor = ExecutionEngine()
milestone_store = MilestoneStore()


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


def _active_data_loader() -> LaunchDataLoader:
    return LaunchDataLoader(excel_path=SAMPLE_LRP_XLSX)


def _format_frame_records(frame: pd.DataFrame, limit: int) -> list[dict[str, object]]:
    preview = frame.head(limit).copy()
    if preview.empty:
        return []
    source = preview.copy()
    formatted = preview.copy().astype(object)
    for column in source.columns:
        if pd.api.types.is_datetime64_any_dtype(source[column]):
            series = source[column].dt.strftime("%Y-%m-%dT%H:%M:%S").fillna("").astype(object)
        else:
            series = source[column].where(source[column].notna(), "").astype(object)
        formatted.loc[:, column] = series
    return formatted.to_dict(orient="records")


def _data_view_payload(view: str, limit: int) -> tuple[str, pd.DataFrame]:
    loaded = _active_data_loader().load()
    if view == "vehicle":
        return ("LRP Data", loaded.frame)
    if view == "launch_event":
        return ("Launch Events", loaded.events_frame)
    if view == "feedback":
        rows = learning_store.preview_feedback(limit=max(limit, 1))
        return ("Feedback", pd.DataFrame(rows))
    if view == "milestones":
        rows = milestone_store.list_deliverables()
        return ("Milestone Deliverables", pd.DataFrame(rows))
    raise HTTPException(status_code=400, detail=f"Unsupported data view: {view}")


def _catalog_response() -> DataCatalogResponse:
    loaded = _active_data_loader().load()
    feedback_rows = learning_store.feedback_report(limit_recent=1)
    milestone_rows = milestone_store.list_deliverables()
    views = [
        ("vehicle", "LRP Data", loaded.frame),
        ("launch_event", "Launch Events", loaded.events_frame),
        ("feedback", "Feedback", pd.DataFrame(learning_store.preview_feedback(limit=1))),
        ("milestones", "Milestone Deliverables", pd.DataFrame(milestone_rows)),
    ]
    summaries = []
    for view_id, label, frame in views:
        columns = list(frame.columns)
        row_count = feedback_rows["total_feedback"] if view_id == "feedback" else len(frame.index)
        summaries.append(
            {
                "view": view_id,
                "label": label,
                "row_count": row_count,
                "column_count": len(columns),
                "columns": columns,
            }
        )

    return DataCatalogResponse(
        source_kind=loaded.source_kind,
        source_path=str(loaded.source_path),
        workbook_present=SAMPLE_LRP_XLSX.exists(),
        views=summaries,
    )


@app.post("/query", response_model=QueryResponse)
def query(request: QueryRequest) -> QueryResponse:
    plan = planner.build_plan(request.query, mode_override=request.planner_mode)
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
    plan = planner.build_plan(augmented_query, mode_override=request.planner_mode)
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


@app.get("/feedback/report", response_model=FeedbackReportResponse)
def feedback_report() -> FeedbackReportResponse:
    report = learning_store.feedback_report()
    return FeedbackReportResponse(**report)


@app.get("/data/catalog", response_model=DataCatalogResponse)
def data_catalog() -> DataCatalogResponse:
    return _catalog_response()


@app.get("/data/preview", response_model=DataPreviewResponse)
def data_preview(
    view: str = Query("vehicle"),
    limit: int = Query(25, ge=1, le=200),
) -> DataPreviewResponse:
    label, frame = _data_view_payload(view, limit)
    row_count = learning_store.feedback_report(limit_recent=1)["total_feedback"] if view == "feedback" else len(frame.index)
    return DataPreviewResponse(
        view=view,
        label=label,
        row_count=row_count,
        limit=limit,
        columns=list(frame.columns),
        rows=_format_frame_records(frame, limit),
    )


@app.post("/data/upload", response_model=DataUploadResponse)
async def data_upload(
    request: Request,
    filename: str = Query(..., min_length=1),
) -> DataUploadResponse:
    suffix = Path(filename).suffix.lower()
    if suffix not in {".xlsx", ".xlsm"}:
        raise HTTPException(status_code=400, detail="LaunchIQ only accepts .xlsx or .xlsm LRP workbooks.")

    payload = await request.body()
    if not payload:
        raise HTTPException(status_code=400, detail="Upload body was empty.")

    temporary_path = SAMPLE_LRP_XLSX.with_name(f"{SAMPLE_LRP_XLSX.stem}.uploading{SAMPLE_LRP_XLSX.suffix}")
    try:
        temporary_path.write_bytes(payload)
        loaded = LaunchDataLoader(excel_path=temporary_path).load()
        temporary_path.replace(SAMPLE_LRP_XLSX)
    except Exception as exc:
        temporary_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"Uploaded workbook could not be loaded: {exc}") from exc

    return DataUploadResponse(
        stored=True,
        filename=filename,
        destination=str(SAMPLE_LRP_XLSX),
        source_kind=loaded.source_kind,
        row_count=len(loaded.frame.index),
        launch_event_count=len(loaded.events_frame.index),
    )


@app.post("/export")
def export_results(request: ExportRequest) -> StreamingResponse:
    answer = request.answer
    if isinstance(answer, list):
        frame = pd.DataFrame(answer)
    elif isinstance(answer, dict):
        frame = pd.DataFrame([answer])
    else:
        frame = pd.DataFrame([{"value": answer}])

    sheet_name = "LaunchIQ"
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name=sheet_name, index=False)

    output.seek(0)
    filename_stub = re.sub(r"[^a-z0-9]+", "_", request.query.lower()).strip("_")[:48] or "launchiq_export"
    filename = f"{filename_stub}.xlsx"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


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
