# LaunchIQ

LaunchIQ is a full-stack launch intelligence workspace for querying LRP-style portfolio data in plain English. It uses deterministic planning and execution for trust, with optional LLM assistance only for query interpretation.

## What LaunchIQ Solves

LaunchIQ turns launch planning spreadsheets into a queryable analyst product. It is designed to answer questions about:

- vehicle launches across `SOPM`, `MCA`, and `MCA2`
- milestone timelines and deliverables
- regional footprint across `RoS` and `IPZ`
- EEA, TCU, infotainment, OTA, platform, and brand filters
- launch and volume comparisons
- launch windows like year, quarter, half-year, `CY`, and month

The goal is to avoid manual spreadsheet slicing while keeping outputs auditable and deterministic.

## Core Principles

- Execution is deterministic.
- LLMs are optional and used only for planning support.
- Temporal parsing and business rules stay coded.
- Unsupported or low-signal questions fail safely.
- Every answer can be inspected in the Analysis view.

## Architecture

### Backend

- `backend/app/main.py`
  FastAPI entrypoint and route wiring.
- `backend/app/planner.py`
  Query planning, heuristic parsing, hybrid/LLM interpretation, diagnostics.
- `backend/app/execution.py`
  Deterministic dataframe filtering, grouping, aggregation, and explanation generation.
- `backend/app/data_loader.py`
  Loads the LRP workbook or fallback CSV, derives stack fields, launch events, and sanitizes invalid lifecycle dates.
- `backend/app/clarification.py`
  Clarification detection and answer merge flow.
- `backend/app/milestones.py`
  Derived milestone offset logic.
- `backend/app/learning.py`
  Feedback storage, relevant feedback lookup, and feedback report generation.
- `backend/app/milestone_store.py`
  Editable milestone deliverables store.
- `backend/app/models.py`
  Shared API and planner contracts.

### Frontend

- `frontend/src/App.jsx`
  Main workspace shell, planner mode control, view switching, export, and feedback wiring.
- `frontend/src/components/AnswerCard.jsx`
  All answer renderers, including Vehicle Brief, Launch Brief, Launch Window, Regional Footprint, Component Match, charts, and tables.
- `frontend/src/components/ExplanationPanel.jsx`
  Planner diagnostics and SQL/execution trace.
- `frontend/src/components/FeedbackButtons.jsx`
  Review This Answer flow.
- `frontend/src/components/FeedbackReportPanel.jsx`
  Feedback operations view.
- `frontend/src/api.js`
  Frontend API client helpers.
- `frontend/src/styles.css`
  Shared styles for all views.

### Data Sources

- `sample_lrp.xlsx`
  Primary workbook when present.
- `backend/data/launch_programs.csv`
  Fallback dataset when no workbook is available.
- `backend/data/milestone_deliverables.json`
  Seed milestone deliverables catalog.

### Persistent Stores

- `backend/data/learning.duckdb`
  Feedback records.
- `backend/data/learning_log.jsonl`
  Feedback append-only log.
- `backend/data/milestones.duckdb`
  Editable milestone deliverables store.

## Data Flow

1. User submits a question in the React workspace.
2. Frontend calls `POST /query` with optional `planner_mode`.
3. Planner builds a `QueryPlan`:
   - `intent`
   - `data_view`
   - filters
   - grouping
   - date window
   - diagnostics
4. If ambiguous, backend returns `clarification_needed`.
5. Execution engine runs deterministic dataframe logic.
6. Backend returns:
   - plan
   - answer
   - explanation
7. Frontend renders the best-fit answer view.
8. User can inspect Analysis, export to Excel, or submit feedback.

## Planner Modes

- `heuristic`
  Fully deterministic local planner.
- `hybrid`
  Heuristic baseline plus optional LLM suggestion for intent and data-view interpretation.
- `llm`
  Full LLM planner attempt with deterministic execution afterward.

### Important

- Execution remains deterministic in all modes.
- Strong heuristic decisions are protected from weak or incorrect LLM overrides.
- If hybrid is requested without a configured provider, LaunchIQ falls back safely to heuristics.

## Current Feature Set

- Vehicle Brief
- Launch Brief
- Launch Window queries
- Launch-stage window queries
- Milestone-window queries
- Regional Footprint view
- Component Match view
- Volume totals, rankings, distributions, and comparisons
- Distribution charts for comparative questions
- Clarification flow for incomplete questions
- Excel export
- Planner diagnostics in Analysis view
- Feedback capture and feedback report
- Editable milestone deliverables

## Supported Query Types

Examples:

- `Which vehicles are launching in 26Q4?`
- `Which vehicles have SOPM in 26Q4?`
- `Which vehicles has SHRM in 26Q3?`
- `Tell me about Jeep Recon`
- `When is F2X launching?`
- `Which Jeep vehicles are launching in IAP and MEA regions in 2026?`
- `Which Vehicles are Launched with PCSA Infotainments?`
- `Which vehicles have the highest launch volume in 2026?`
- `Compare between TBM2.0 and TBM 2.0H Launch volumes in 2026`

## API Endpoints

### Querying

- `POST /query`
- `POST /clarify`

### Feedback And Reporting

- `POST /feedback`
- `GET /feedback/report`

### Export

- `POST /export`

### Milestone Deliverables

- `GET /milestones/deliverables`
- `GET /milestones/deliverables/{milestone_code}`
- `PUT /milestones/deliverables/{milestone_code}`

### Health

- `GET /health`

## Running The Backend

From `/Volumes/Subhash/LaunchIQ/backend`:

1. Create a virtual environment and install dependencies from [backend/requirements.txt](/Volumes/Subhash/LaunchIQ/backend/requirements.txt).
2. Start the API:

```bash
uvicorn app.main:app --reload --port 8000
```

3. Run tests:

```bash
pytest
```

## Running The Frontend

From `/Volumes/Subhash/LaunchIQ/frontend`:

1. Install dependencies.
2. Start the UI:

```bash
npm run dev
```

The UI uses `VITE_API_BASE_URL`, defaulting to `http://localhost:8000`.

## Optional LLM Providers

### Ollama

Set:

```bash
export LAUNCHIQ_LLM_PROVIDER=ollama
export LAUNCHIQ_OLLAMA_URL=http://127.0.0.1:11434/api/chat
export LAUNCHIQ_OLLAMA_MODEL=llama3.1:8b
```

### OpenAI-Compatible

Set:

```bash
export LAUNCHIQ_LLM_PROVIDER=openai
export OPENAI_API_KEY=your_key_here
export OPENAI_BASE_URL=https://api.openai.com/v1/chat/completions
export OPENAI_MODEL=gpt-4o-mini
```

### Planner Mode

Optional:

```bash
export LAUNCHIQ_PLANNER_MODE=heuristic
```

The UI also supports request-scoped switching between `Heuristic` and `Hybrid`.

## Notes And Constraints

- Main LRP query data is loaded into Pandas in memory; it is not persisted into a main analytical database.
- SQL shown in Analysis is an audit/debug artifact, not the execution engine of record.
- Feedback helps planning interpretation, not direct renderer/business-logic correction.
- Invalid lifecycle dates from the source workbook are sanitized during data load when they break basic ordering rules.
- The project is optimized for the current uploaded LRP schema rather than arbitrary spreadsheets.
