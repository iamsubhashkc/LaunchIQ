function renderPlanSnapshot(title, snapshot) {
  if (!snapshot) {
    return null;
  }

  return (
    <div className="explanation-card">
      <span className="label">{title}</span>
      <ul className="detail-list">
        <li>Intent: {snapshot.intent}</li>
        <li>Data view: {snapshot.data_view}</li>
        <li>Group by: {snapshot.group_by.length ? snapshot.group_by.join(", ") : "none"}</li>
        <li>Region scope: {snapshot.region_scope}</li>
        <li>Milestones: {snapshot.milestone_columns.length ? snapshot.milestone_columns.join(", ") : "none"}</li>
        <li>Requested columns: {snapshot.requested_columns.length ? snapshot.requested_columns.join(", ") : "default set"}</li>
      </ul>
    </div>
  );
}

export function ExplanationPanel({ plan, explanation, summary }) {
  const diagnostics = plan?.planner_diagnostics;

  return (
    <section className="panel explanation-panel">
      <div className="panel-header">
        <div>
          <h2>Analysis Trace</h2>
          <p>Technical trace for audit, verification, and planner review.</p>
        </div>
      </div>

      <div className="explanation-stack">
        <div className="explanation-card">
          <span className="label">Summary</span>
          <p>{summary}</p>
        </div>

        <div className="explanation-card">
          <span className="label">Planner Diagnostics</span>
          {diagnostics ? (
            <ul className="detail-list">
              <li>Query frame: {diagnostics.query_frame}</li>
              <li>Grounding status: {diagnostics.grounding_status}</li>
              <li>Resolution state: {diagnostics.resolution_state}</li>
            </ul>
          ) : (
            <p>No diagnostics yet.</p>
          )}
        </div>

        {renderPlanSnapshot("Heuristic Baseline", diagnostics?.heuristic_baseline)}

        <div className="explanation-card">
          <span className="label">LLM Suggestion</span>
          {diagnostics?.llm_suggestion ? (
            <ul className="detail-list">
              <li>Intent: {diagnostics.llm_suggestion.intent || "none"}</li>
              <li>Data view: {diagnostics.llm_suggestion.data_view || "none"}</li>
              <li>Confidence: {Number(diagnostics.llm_suggestion.confidence || 0).toFixed(2)}</li>
              <li>Accepted overrides: {diagnostics.llm_suggestion.accepted_overrides.length ? diagnostics.llm_suggestion.accepted_overrides.join(", ") : "none"}</li>
              <li>Reasoning: {diagnostics.llm_suggestion.reasoning || "No LLM suggestion was used."}</li>
            </ul>
          ) : (
            <p>No LLM suggestion was used for this plan.</p>
          )}
        </div>

        <div className="explanation-card">
          <span className="label">Feedback Context</span>
          {diagnostics?.feedback_context?.length ? (
            <ul className="detail-list">
              {diagnostics.feedback_context.map((item, index) => (
                <li key={`${item.query}-${index}`}>
                  {item.rating} match ({item.match_type}, score {Number(item.score || 0).toFixed(2)}): "{item.query}"
                  {item.correction ? ` -> ${item.correction}` : ""}
                </li>
              ))}
            </ul>
          ) : (
            <p>No relevant prior feedback was used for this plan.</p>
          )}
        </div>

        {renderPlanSnapshot("Final Resolved Plan", diagnostics?.final_resolved_plan || plan)}

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
          <span className="label">Applied Filters</span>
          {explanation?.applied_filters?.length ? (
            <ul className="detail-list">
              {explanation.applied_filters.map((filter, index) => (
                <li key={`${filter.field}-${index}`}>
                  {filter.field} {filter.operator} {JSON.stringify(filter.value)}
                </li>
              ))}
            </ul>
          ) : (
            <p>No explicit filters applied.</p>
          )}
        </div>

        <div className="explanation-card sql-card">
          <span className="label">Generated SQL</span>
          <pre>{explanation?.generated_sql ?? "SQL will be generated after execution."}</pre>
        </div>
      </div>
    </section>
  );
}
