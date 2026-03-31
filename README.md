# LaunchIQ

LaunchIQ is a full-stack semantic reasoning engine that uses an LLM only for query planning and keeps execution deterministic with Pandas and DuckDB.

## Architecture

- `backend/`: FastAPI service with planning, clarification, execution, and feedback persistence.
- `frontend/`: React analyst workspace for query submission, answer review, clarification, and corrections.
- `sample_lrp.xlsx`: uploaded Excel workbook used as the primary data source when present.
- `backend/data/launch_programs.csv`: seeded fallback dataset used only when no workbook is available.
- `backend/data/milestone_deliverables.json`: seed file for milestone governance and readiness deliverables.

## Backend

1. Create a virtual environment and install the dependencies in [backend/requirements.txt](/Volumes/Subhash/LaunchIQ/backend/requirements.txt).
2. Run the API from `/Volumes/Subhash/LaunchIQ/backend` with:

```bash
uvicorn app.main:app --reload --port 8000
```

3. Execute tests from `/Volumes/Subhash/LaunchIQ/backend` with:

```bash
pytest
```

### Optional planner providers

- Default: heuristic planner for local testing.
- Ollama: set `LAUNCHIQ_LLM_PROVIDER=ollama` and optionally `LAUNCHIQ_OLLAMA_MODEL`.
- OpenAI-compatible API: set `LAUNCHIQ_LLM_PROVIDER=openai`, `OPENAI_API_KEY`, and optionally `OPENAI_BASE_URL` and `OPENAI_MODEL`.

### Milestone catalog

Milestone deliverables are persisted in DuckDB and seeded from [backend/data/milestone_deliverables.json](/Volumes/Subhash/LaunchIQ/backend/data/milestone_deliverables.json) on first run.

Endpoints:
- `GET /milestones/deliverables`
- `GET /milestones/deliverables/{milestone_code}`
- `PUT /milestones/deliverables/{milestone_code}`

## Frontend

1. Install dependencies from `/Volumes/Subhash/LaunchIQ/frontend`.
2. Run:

```bash
npm run dev
```

3. The UI uses `VITE_API_BASE_URL`, defaulting to `http://localhost:8000`.
