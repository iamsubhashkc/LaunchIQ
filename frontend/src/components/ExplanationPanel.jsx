function humanize(value) {
  return String(value || "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (match) => match.toUpperCase());
}

function formatPlanValue(value) {
  if (value === null || value === undefined || value === "") {
    return "Not provided";
  }
  if (Array.isArray(value)) {
    return value.join(", ");
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
}

function inferPlannerMode(diagnostics) {
  const notes = diagnostics?.decision_notes || [];
  if (notes.some((note) => note.toLowerCase().includes("no llm provider was available"))) {
    return "Hybrid Fallback";
  }
  if (notes.some((note) => note.toLowerCase().includes("used heuristic planner only"))) {
    return "Heuristic";
  }
  if (diagnostics?.llm_suggestion) {
    return "Hybrid";
  }
  return "Heuristic";
}

function buildScopeChips(plan, explanation) {
  const chips = [];
  (explanation?.applied_filters || []).forEach((filter, index) => {
    if (filter.field === "milestone_window" && filter.value?.start && filter.value?.end) {
      chips.push({ key: `filter-${index}`, text: `Milestone window: ${filter.value.start} to ${filter.value.end}` });
      return;
    }
    chips.push({
      key: `filter-${index}`,
      text: `${humanize(filter.field)} ${filter.operator} ${formatPlanValue(filter.value)}`,
    });
  });
  if (!chips.length && plan?.group_by?.length) {
    chips.push({ key: "grouping", text: `Grouped by ${plan.group_by.join(", ")}` });
  }
  if (!chips.length) {
    chips.push({ key: "scope-none", text: "No explicit filters applied" });
  }
  return chips;
}

function buildResultSummary(response, explanation) {
  const answer = response?.answer;
  const answerType = response?.answer_type || response?.plan?.intent || "unknown";
  const items = [
    { label: "Output", value: humanize(answerType) },
    { label: "Execution View", value: humanize(response?.plan?.data_view || "unknown") },
  ];

  if (Array.isArray(answer)) {
    items.push({ label: "Rows Returned", value: String(answer.length) });
  } else if (answer && typeof answer === "object" && "value" in answer) {
    items.push({ label: "Metric Result", value: String(answer.value) });
  }

  if (explanation?.grouping?.length) {
    items.push({ label: "Grouping", value: explanation.grouping.join(", ") });
  } else {
    items.push({ label: "Grouping", value: "None" });
  }

  const sourceNote = (explanation?.notes || []).find((note) => note.startsWith("Source dataset:"));
  if (sourceNote) {
    items.push({ label: "Source Dataset", value: sourceNote.replace("Source dataset:", "").trim() });
  }

  return items;
}

function buildTrustItems(diagnostics, explanation) {
  const items = [
    { label: "Planner Mode", value: inferPlannerMode(diagnostics) },
    { label: "Grounding", value: humanize(diagnostics?.grounding_status || "unknown") },
    { label: "Resolution", value: humanize(diagnostics?.resolution_state || "unknown") },
    { label: "Feedback Used", value: diagnostics?.feedback_context?.length ? `${diagnostics.feedback_context.length} hint(s)` : "No" },
  ];

  const executionNotes = explanation?.notes || [];
  const derivedNote = executionNotes.find((note) => note.toLowerCase().includes("derived milestones anchored"));
  if (derivedNote) {
    items.push({ label: "Milestone Logic", value: "Derived from anchor dates" });
  }

  return items;
}

function renderSnapshotCard(title, snapshot) {
  if (!snapshot) {
    return null;
  }

  return (
    <div className="comparison-card explanation-card">
      <span className="label">{title}</span>
      <ul className="detail-list">
        <li>Intent: {humanize(snapshot.intent)}</li>
        <li>Data View: {humanize(snapshot.data_view)}</li>
        <li>Group By: {snapshot.group_by.length ? snapshot.group_by.join(", ") : "None"}</li>
        <li>Region Scope: {snapshot.region_scope}</li>
        <li>Milestones: {snapshot.milestone_columns.length ? snapshot.milestone_columns.join(", ") : "None"}</li>
      </ul>
    </div>
  );
}

export function ExplanationPanel({ response, plan, explanation, summary }) {
  const diagnostics = plan?.planner_diagnostics;
  const scopeChips = buildScopeChips(plan, explanation);
  const resultSummary = buildResultSummary(response, explanation);
  const trustItems = buildTrustItems(diagnostics, explanation);

  return (
    <section className="panel explanation-panel">
      <div className="panel-header">
        <div>
          <h2>Analysis Trace</h2>
          <p>Product audit view for understanding how LaunchIQ interpreted, resolved, and executed the question.</p>
        </div>
      </div>

      <div className="explanation-stack">
        <div className="hero-insight audit-hero">
          <span className="insight-kicker">Decision Summary</span>
          <p className="audit-summary-copy">{summary}</p>
          <p>{response?.query || "No question has been executed yet."}</p>
          <div className="audit-badge-row">
            <span className="badge">{inferPlannerMode(diagnostics)}</span>
            <span className="badge">{humanize(diagnostics?.query_frame || "unknown")}</span>
            <span className="badge">{humanize(plan?.data_view || "unknown")}</span>
            <span className="badge">{humanize(response?.answer_type || plan?.intent || "unknown")}</span>
          </div>
        </div>

        <div className="audit-grid">
          <div className="explanation-card">
            <span className="label">Query Understanding</span>
            <ul className="detail-list">
              <li>Interpreted Ask: {humanize(diagnostics?.query_frame || "unknown")}</li>
              <li>Resolved Output: {humanize(response?.answer_type || plan?.intent || "unknown")}</li>
              <li>Execution View: {humanize(plan?.data_view || "unknown")}</li>
              <li>Reasoning Summary: {summary}</li>
            </ul>
          </div>

          <div className="explanation-card">
            <span className="label">Trust And Readiness</span>
            <div className="audit-stat-grid">
              {trustItems.map((item) => (
                <div className="audit-stat-card" key={item.label}>
                  <span>{item.label}</span>
                  <strong>{item.value}</strong>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="explanation-card">
          <span className="label">Resolved Scope</span>
          <div className="audit-chip-list">
            {scopeChips.map((item) => (
              <span className="audit-chip" key={item.key}>
                {item.text}
              </span>
            ))}
          </div>
        </div>

        <div className="explanation-card">
          <span className="label">Result Summary</span>
          <div className="audit-stat-grid">
            {resultSummary.map((item) => (
              <div className="audit-stat-card" key={item.label}>
                <span>{item.label}</span>
                <strong>{item.value}</strong>
              </div>
            ))}
          </div>
        </div>

        <div className="explanation-card">
          <span className="label">Planner Comparison</span>
          <div className="comparison-grid audit-comparison-grid">
            {renderSnapshotCard("Heuristic Baseline", diagnostics?.heuristic_baseline)}

            <div className="comparison-card explanation-card">
              <span className="label">LLM Suggestion</span>
              {diagnostics?.llm_suggestion ? (
                <ul className="detail-list">
                  <li>Intent: {diagnostics.llm_suggestion.intent ? humanize(diagnostics.llm_suggestion.intent) : "None"}</li>
                  <li>Data View: {diagnostics.llm_suggestion.data_view ? humanize(diagnostics.llm_suggestion.data_view) : "None"}</li>
                  <li>Confidence: {Number(diagnostics.llm_suggestion.confidence || 0).toFixed(2)}</li>
                  <li>Accepted Overrides: {diagnostics.llm_suggestion.accepted_overrides.length ? diagnostics.llm_suggestion.accepted_overrides.join(", ") : "None"}</li>
                  <li>Why: {diagnostics.llm_suggestion.reasoning || "No reasoning provided."}</li>
                </ul>
              ) : (
                <p>No LLM suggestion was used for this plan.</p>
              )}
            </div>

            {renderSnapshotCard("Final Resolved Plan", diagnostics?.final_resolved_plan || plan)}
          </div>
        </div>

        <div className="audit-grid">
          <div className="explanation-card">
            <span className="label">Decision Notes</span>
            {diagnostics?.decision_notes?.length ? (
              <ul className="detail-list">
                {diagnostics.decision_notes.map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
            ) : (
              <p>No decision notes recorded.</p>
            )}
          </div>

          <div className="explanation-card">
            <span className="label">Feedback Context</span>
            {diagnostics?.feedback_context?.length ? (
              <ul className="detail-list">
                {diagnostics.feedback_context.map((item, index) => (
                  <li key={`${item.query}-${index}`}>
                    {humanize(item.rating)} ({item.match_type}, score {Number(item.score || 0).toFixed(2)}): "{item.query}"
                    {item.correction ? ` -> ${item.correction}` : ""}
                  </li>
                ))}
              </ul>
            ) : (
              <p>No relevant prior feedback was used for this plan.</p>
            )}
          </div>
        </div>

        <div className="explanation-card">
          <span className="label">Technical Detail</span>
          <ul className="detail-list">
            {(explanation?.notes || []).map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
          <details className="sql-disclosure">
            <summary>Generated SQL</summary>
            <div className="sql-card">
              <pre>{explanation?.generated_sql ?? "SQL will be generated after execution."}</pre>
            </div>
          </details>
        </div>
      </div>
    </section>
  );
}
