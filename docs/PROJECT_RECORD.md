# LaunchIQ Project Record

This document captures the current state of LaunchIQ, what was built, what was changed during the buildout, how the app works today, what was verified, and what is queued next.

## 1. Project Goal

LaunchIQ is a full-stack semantic reasoning engine for launch-planning questions.

Core product principles:

- natural-language query in
- LLM used only for planning
- deterministic execution only
- explainable output
- clarification instead of hallucination
- feedback capture for future tuning

The current stack is:

- Frontend: React + Vite
- Backend: FastAPI
- Data: Pandas + DuckDB
- Planner: heuristic by default, with optional Ollama or OpenAI-compatible planner integration

## 2. Current Repository State

Repo root:
- [/Volumes/Subhash/LaunchIQ](/Volumes/Subhash/LaunchIQ)

Current git `HEAD`:
- `d42a9fa`

Main top-level assets:
- [README.md](/Volumes/Subhash/LaunchIQ/README.md)
- [sample_lrp.xlsx](/Volumes/Subhash/LaunchIQ/sample_lrp.xlsx)
- [backend](/Volumes/Subhash/LaunchIQ/backend)
- [frontend](/Volumes/Subhash/LaunchIQ/frontend)
- [docs/PROJECT_RECORD.md](/Volumes/Subhash/LaunchIQ/docs/PROJECT_RECORD.md)

## 3. Data Source Status

### Primary data source

LaunchIQ currently uses:
- [sample_lrp.xlsx](/Volumes/Subhash/LaunchIQ/sample_lrp.xlsx)

Workbook facts from the current sample:
- sheet count: `1`
- sheet name: `Sheet1`
- raw Excel shape: `292 x 107`
- normalized backend shape: `292 x 64`
- unique car families: `21`
- unique commercial names: `24`
- brands present:
  - `CHRYSLER`
  - `DS`
  - `FIAT`
  - `JEEP`
  - `LANCIA`
  - `MASERATI`
  - `OPEL`
  - `PEUGEOT`
  - `RAM`

### Fallback data source

If no workbook is present, the backend can fall back to:
- [launch_programs.csv](/Volumes/Subhash/LaunchIQ/backend/data/launch_programs.csv)

That CSV is only a fallback/demo path now. The workbook is the active source.

## 4. Data Loading and Normalization

Primary loader:
- [data_loader.py](/Volumes/Subhash/LaunchIQ/backend/app/data_loader.py)

### Important header mapping decisions

The Excel does not use the app’s internal schema names directly, so LaunchIQ normalizes the workbook into a canonical dataframe.

Important mapping fixes made during development:

- `car_family` comes from Excel `Car Family`
- `commercial_name` comes from Excel `Commercial Name`
- `car_family_code` comes from Excel `Carline Code w. Final Prod Zone`

This mapping was initially wrong and was corrected after output validation.

### Normalized business columns exposed today

Core business fields:
- `brand`
- `car_family`
- `commercial_name`
- `car_family_code`
- `region_of_sales`
- `initial_prod_zone`
- `project_responsible_region`
- `platform`
- `program`
- `powertrain`
- `sopm`
- `mca_sopm`
- `mca2_sopm`
- `eop`
- `eea`
- `ota`

Derived volume fields:
- `launch_volume`
- `total_volume`
- `volume_<year>`
- `volume_first_2_years`

Derived time/lifecycle fields:
- `sopm_month`
- `sopm_year`
- `eop_year`
- `lifecycle_years`
- `months_sopm_to_mca`
- `months_mca_to_mca2`
- `min_transition_gap_months`

Derived readiness / architecture fields:
- `eea_available`
- `ota_capability`
- `adas_capability`
- `connectivity_capability`
- `architecture`
- `tcu_generation`
- `tcu_details`
- `infotainment_details`
- `mixed_tcu`
- `mixed_architecture`

Derived regional scope fields:
- `region_pair`
- `region_of_sales_count`
- `initial_prod_zone_count`

Transition milestone presence flags:
- `has_mca`
- `has_mca2`

Trend field:
- `declining_post_sopm`

### Stack extraction logic

The loader expands weighted connectivity and infotainment mixes out of the workbook’s percentage columns.

Examples:
- `tcu_details: ATB4S V2 (5%), R2eX (95%)`
- `infotainment_details: PCSA (SPS) (5%), CRONY 2 (49%), CRONY 2 NAV (46%)`

These string fields are now used directly by the planner for human-style component queries.

## 5. Backend Architecture

### API entrypoint

- [main.py](/Volumes/Subhash/LaunchIQ/backend/app/main.py)

Exposed endpoints:
- `POST /query`
- `POST /clarify`
- `POST /feedback`

### Schemas

- [models.py](/Volumes/Subhash/LaunchIQ/backend/app/models.py)

Important models:
- `QueryPlan`
- `PlanFilter`
- `QueryRequest`
- `QueryResponse`
- `FeedbackRequest`
- `FeedbackResponse`
- `ExecutionExplanation`

### Planner

- [planner.py](/Volumes/Subhash/LaunchIQ/backend/app/planner.py)

Planner modes:
- heuristic planner by default
- optional Ollama planner
- optional OpenAI-compatible planner

### Clarification engine

- [clarification.py](/Volumes/Subhash/LaunchIQ/backend/app/clarification.py)

Used when a query is ambiguous and deterministic execution should not proceed yet.

### Execution engine

- [execution.py](/Volumes/Subhash/LaunchIQ/backend/app/execution.py)

Execution is done using:
- Pandas for normalized in-memory datasets
- DuckDB for deterministic SQL execution

### Learning engine

- [learning.py](/Volumes/Subhash/LaunchIQ/backend/app/learning.py)

Feedback stores:
- query
- plan
- answer
- rating
- correction

## 6. Deterministic Query Execution Rules

LaunchIQ does not answer directly from the LLM.

The planner decides:
- intent
- filters
- groupings
- metric
- view

The executor then runs those instructions deterministically.

### Supported answer types

- `list`
- `count`
- `distribution`
- `timeline`

### Supported data views

- `vehicle`
- `launch_event`

### Region logic

Supported region handling:
- `RoS`
- `IPZ`
- `BOTH`

For `RoS vs IPZ` style asks, execution builds unioned deterministic grouped outputs.

### Transition launch handling

Launch event view includes:
- `SOPM`
- `MCA`
- `MCA2`

Derived event fields:
- `launch_stage`
- `launch_category`
- `launch_date`
- `launch_month`
- `launch_year`
- `launch_event_id`

## 7. Frontend Architecture

Main app:
- [App.jsx](/Volumes/Subhash/LaunchIQ/frontend/src/App.jsx)

Components:
- [AnswerCard.jsx](/Volumes/Subhash/LaunchIQ/frontend/src/components/AnswerCard.jsx)
- [ChatInput.jsx](/Volumes/Subhash/LaunchIQ/frontend/src/components/ChatInput.jsx)
- [ClarificationBox.jsx](/Volumes/Subhash/LaunchIQ/frontend/src/components/ClarificationBox.jsx)
- [ExplanationPanel.jsx](/Volumes/Subhash/LaunchIQ/frontend/src/components/ExplanationPanel.jsx)
- [FeedbackButtons.jsx](/Volumes/Subhash/LaunchIQ/frontend/src/components/FeedbackButtons.jsx)

Styling:
- [styles.css](/Volumes/Subhash/LaunchIQ/frontend/src/styles.css)

API client:
- [api.js](/Volumes/Subhash/LaunchIQ/frontend/src/api.js)

## 8. UI Evolution

### Initial UI state

The first UI version rendered most answers as a table.

### Important UI fixes made

1. Table truncation bug fixed
- the answer table originally displayed only the first `14` rows
- this made the tool appear to miss vehicles even when the backend was returning the correct result set
- the truncation was removed

2. Answer summary added
- row count
- unique car family count
- unique commercial name count

### Current answer modes

The UI is now dynamic and not table-only.

Current named answer modes:
- `Metric Readout`
- `Vehicle Profile`
- `Launch Timeline`
- `Evidence Check`
- `Regional Footprint`
- `Component Match`
- `Compare`
- `Overlap Load`
- `Launch Cards`
- `Structured Table`

### Current mode behavior

`Vehicle Profile`
- used for `tell me about ...` and entity-style questions
- shows a profile card, launch footprint, lifecycle dates, TCU, infotainment, OTA, and row-level launch footprint

`Launch Timeline`
- used for `when is ... launching?`
- shows launch timing chronologically
- milestone strip is shown if lifecycle dates are present

`Evidence Check`
- used for yes/no style questions like:
  - `Does F1H comes with R2eX and ATB4Sv2 TCUs?`
- shows a positive or negative deterministic statement plus evidence rows

`Regional Footprint`
- used for region-oriented grouped or filtered outputs
- shows region summary cards instead of raw tables where possible

`Component Match`
- used for TCU / infotainment / architecture / OTA / EEA style asks
- surfaces matched component evidence cleanly

`Compare`
- reserved for `compare` or `vs` style asks
- shows a side-by-side card layout

`Overlap Load`
- used for month overlap analysis in launch-event mode

`Launch Cards`
- used for smaller focused list outputs

`Structured Table`
- used as the fallback for larger row-heavy outputs

## 9. Major Functional Changes Made During Development

### A. Mapping and output corrections

Fixed:
- `Car Family` vs `Commercial Name` vs `Car Family Code` mapping
- default OTA output changed from boolean-like behavior to real source values like:
  - `FOTA`
  - `FOTA IVI`
  - `TBD`

### B. Default list output shape corrected

For general list-style asks, default columns now include:
- `car_family`
- `brand`
- `commercial_name`
- `initial_prod_zone`
- `region_of_sales`
- `eea`
- `tcu_details`
- `infotainment_details`
- `ota`
- `platform`
- `program`
- `sopm`

Volume is intentionally not shown by default unless the query asks for it.

### C. Brand matching improved

Brand detection started as a small hard-coded path, then was replaced with generic query parsing and workbook-backed schema value matching.

### D. Schema-aware filtering added

Planner can now match real workbook values for fields like:
- `brand`
- `region_of_sales`
- `initial_prod_zone`
- `platform`
- `program`
- `powertrain`
- `eea`
- `ota`

### E. Human-style entity recognition added

Planner now matches actual workbook entities for:
- `car_family`
- `commercial_name`
- `car_family_code`

This is what enables:
- `When is F2X launching?`
- `Tell me about Recon`
- `Tell me about Jeep Recon`
- `What launches are planned for J-WL?`
- `Give me details for Tipo, SAM: F2X`

### F. Entity masking added

Matched entities are masked before generic field matching so words inside names do not accidentally trigger unrelated filters.

Example fixed:
- `Tipo, SAM: F2X` no longer triggers `SAM` as a region filter

### G. Code-like fallback added and scoped

If the user asks for an unknown-looking code in a natural phrase, LaunchIQ can still try it as a `car_family` exact identifier.

Example:
- `Tell me about B618`
  now returns `0` rows rather than returning the whole dataset

### H. Stack component matching added

Planner now supports component-level matching using workbook-derived labels from:
- connectivity columns
- infotainment columns

This fixed questions like:
- `Does F1H comes with R2eX and ATB4Sv2 TCUs?`
- `Is F1H being sold in MEA region with R2eX TCU?`
- `Which Vehicles are Launched with PCSA Infotainments?`

### I. False-positive token fixes

Fixed issues like:
- `infotainments` accidentally triggering the `FOTA` rule because of substring overlap
- `TBD` accidentally being read as a region in OTA-style queries
- `TBM 2.0` and `TBM 2.0H` partial-match collision

### J. Region distribution execution fix

The region distribution SQL path was corrected so prepared statement parameters align correctly even when filters are repeated into both `RoS` and `IPZ` branches.

### K. Lifecycle date serialization fix

Entity-focused answers now include:
- `mca_sopm`
- `mca2_sopm`
- `eop`

The executor now converts datetime outputs into plain strings before API serialization.

### L. Derived milestone engine added

Milestone logic is now implemented as a derived capability rather than a workbook dependency.

Source rule provided by the user:
- milestones are calculated backward from a target anchor date
- anchor can be `SOPM`, `MCA SOPM`, or `MCA2 SOPM` depending on the query
- computed dates are rounded to the nearest Monday

Current milestone offsets in weeks:
- `IM`: `-243`
- `PM`: `-204`
- `CM`: `-175`
- `DM`: `-156`
- `SHRM`: `-92`
- `X0`: `-54`
- `X1`: `-36`
- `SOP-8`: `-34.7`
- `SOP-6`: `-26`
- `X2`: `-17`
- `SOP-3`: `-13`
- `LRM`: `-12`
- `X3`: `-10`

Implementation:
- [milestones.py](/Volumes/Subhash/LaunchIQ/backend/app/milestones.py)
- [planner.py](/Volumes/Subhash/LaunchIQ/backend/app/planner.py)
- [execution.py](/Volumes/Subhash/LaunchIQ/backend/app/execution.py)

Planner behavior now:
- milestone questions are no longer marked unsupported just because the workbook lacks CM/IM/PM columns
- LaunchIQ derives them from the requested anchor date
- default milestone anchor is `SOPM`
- if the query explicitly mentions `MCA` or `MCA2`, LaunchIQ anchors backward calculation there instead

Derived response fields now available:
- `milestone_anchor_label`
- `milestone_anchor_date`
- `milestone_im`
- `milestone_pm`
- `milestone_cm`
- `milestone_dm`
- `milestone_shrm`
- `milestone_x0`
- `milestone_x1`
- `milestone_sop_8`
- `milestone_sop_6`
- `milestone_x2`
- `milestone_sop_3`
- `milestone_lrm`
- `milestone_x3`

Examples now supported:
- `When is IM for F2X?`
- `What are the PM and CM milestones for F2X at MCA?`

### M. Milestone-first answer mode added

The frontend now recognizes derived milestone answers and renders them in a dedicated mode:
- `Milestone Plan`

This mode surfaces:
- anchor type
- anchor date
- backward milestone strip
- matched vehicle cards
- requested milestone dates in a more human-readable layout

### N. Milestone deliverables moved into database-backed master data

The milestone deliverables shared by the user are no longer intended to live in code.

Implementation:
- seed file: [milestone_deliverables.json](/Volumes/Subhash/LaunchIQ/backend/data/milestone_deliverables.json)
- store layer: [milestone_store.py](/Volumes/Subhash/LaunchIQ/backend/app/milestone_store.py)
- API wiring: [main.py](/Volumes/Subhash/LaunchIQ/backend/app/main.py)

Behavior:
- deliverables are seeded into DuckDB on first run
- they are not overwritten on every startup
- they can be updated through API calls instead of source edits

Current API endpoints:
- `GET /milestones/deliverables`
- `GET /milestones/deliverables/{milestone_code}`
- `PUT /milestones/deliverables/{milestone_code}`

Current seeded milestone deliverable codes:
- `POST_IM`
- `PM`
- `CM`
- `SHRM`
- `X0`
- `SOP_8`
- `SOP_6`
- `SOP_3`
- `LRM`
- `SOPM`

## 10. Query Classes Currently Supported

### Launch identification

Examples:
- launches in next `12/24/36` months
- launches in specific year
- month-wise SOPM distribution
- vehicles with SOPM but no volume in first 2 years

### Lifecycle

Examples:
- active in year
- nearing EOP
- long lifecycle

### Region-based planning

Examples:
- launches in RoS / IPZ / both
- widest regional spread
- active vehicles by region in a year
- volume split by region in a year

### Volume and trend

Examples:
- highest volume vehicles in a year
- declining post-SOPM volumes

### Transition launch analysis

Examples:
- MCA launches
- MCA2 launches
- month-wise MCA / MCA2 distribution
- overlap months across SOPM / MCA / MCA2
- design vs transition mix
- volume impact of MCA vs SOPM

### Architecture / readiness / component matching

Examples:
- TCU distribution
- mixed architecture
- mixed TCU
- OTA presence
- infotainment component matching
- connectivity component matching

### Human-style natural asks

Examples now working:
- `When is F2X launching?`
- `Tell me about Recon`
- `Tell me about Jeep Recon`
- `What launches are planned for J-WL?`
- `Which Vehicles are Launched with PCSA Infotainments?`

### Derived milestone asks

Examples now working:
- `When is IM for F2X?`
- `What are the PM and CM milestones for F2X at MCA?`
- milestone questions anchored to `SOPM`, `MCA`, or `MCA2`

## 11. Questions Explicitly Unsupported Today

LaunchIQ intentionally returns `unsupported` instead of hallucinating for dataset gaps.

Still unsupported from the current sample workbook:
- SSDP / SPACE / SCEP logic
- target/current SDP migration logic
- legacy SDP to SSDP at MCA or MCA2
- CM / IM / PM milestone alignment from workbook columns
- stage-specific OTA snapshots from SOPM vs MCA
- stage-specific architecture deltas from SOPM vs MCA

These need real source fields or explicit derived milestone logic.

## 12. Important Real-World Query Validations Done

### Brand / region / year

Validated:
- `Which of Jeep brand's Vehicle is Launching in EEU region in 2026?`
  - returns `2` rows

### Human-style entity asks

Validated:
- `When is F2X launching?`
  - matches `car_family = F2X`
- `Tell me about Recon`
  - matches `commercial_name = Recon`
- `Tell me about Jeep Recon`
  - matches `brand = JEEP` and `commercial_name = Recon`
- `What launches are planned for J-WL?`
  - matches `car_family = J-WL`

### Component asks

Validated:
- `Does F1H comes with R2eX and ATB4Sv2 TCUs?`
  - yes, matching row exists in `SAM`
- `Is F1H being sold in MEA region with R2eX TCU?`
  - no, returns `0`
- `Which Vehicles are Launched with PCSA Infotainments?`
  - matches families `F1H` and `K0 Combi`

## 13. Verification Status

Latest backend verification:
- `27 passed`

Frontend verification:
- `npm run build` passes

## 14. Run Instructions

### Backend

From:
- [/Volumes/Subhash/LaunchIQ/backend](/Volumes/Subhash/LaunchIQ/backend)

Run:

```bash
../.venv/bin/uvicorn app.main:app --reload --port 8000
```

### Frontend

From:
- [/Volumes/Subhash/LaunchIQ/frontend](/Volumes/Subhash/LaunchIQ/frontend)

Run:

```bash
npm run dev
```

## 15. Current Git / Remote Status

Local repo initialized and committed.

Remote configured and pushed:
- [https://github.com/iamsubhashkc/LaunchIQ](https://github.com/iamsubhashkc/LaunchIQ)

Note:
- `sample_lrp.xlsx` was included in the initial commit and push
- user later chose to remove it from the remote going forward manually

## 16. What Is Ready for the Next Phase

The app is now prepared for derived milestone calculations even though milestone columns are not present in the LRP.

Why it is ready:
- entity-focused and launch-focused answers already surface lifecycle anchor dates
- UI already has milestone strips in:
  - vehicle profile
  - launch cards
  - launch timeline
- backend has normalized:
  - `sopm`
  - `mca_sopm`
  - `mca2_sopm`
  - `eop`

So the next phase can add:
- backward milestone calculation from `SOPM`
- backward milestone calculation from `MCA SOPM`
- backward milestone calculation from `MCA2 SOPM`
- query-aware milestone base selection depending on the ask

## 17. Suggested Next Step

Next input needed from the user:
- milestone calculation logic

Specifically needed:
- milestone names
- offset rules
- whether offsets are in days / weeks / months
- whether they anchor from `SOPM`, `MCA SOPM`, or `MCA2 SOPM`
- whether different vehicle/program classes use different rules

Once those rules are shared, LaunchIQ can add:
- deterministic milestone engine
- milestone-aware query planning
- milestone cards / milestone timeline output in the UI
