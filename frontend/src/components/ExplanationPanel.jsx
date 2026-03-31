export function ExplanationPanel({ plan, explanation, summary }) {
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
          <span className="label">Planner Output</span>
          {plan ? (
            <ul className="detail-list">
              <li>Intent: {plan.intent}</li>
              <li>Group by: {plan.group_by.length ? plan.group_by.join(", ") : "none"}</li>
              <li>Region scope: {plan.region_scope}</li>
              <li>Requested columns: {plan.requested_columns.length ? plan.requested_columns.join(", ") : "default set"}</li>
            </ul>
          ) : (
            <p>No planner output yet.</p>
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
