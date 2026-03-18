function renderCount(answer) {
  return (
    <div className="count-answer">
      <span>Total distinct car families</span>
      <strong>{answer?.value ?? 0}</strong>
    </div>
  );
}

function toTitleCase(value) {
  return value
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function renderTable(answer) {
  if (!Array.isArray(answer) || answer.length === 0) {
    return <p className="empty-state">No rows matched the current deterministic plan.</p>;
  }

  const columns = Object.keys(answer[0]);
  const uniqueCarFamilies = new Set(answer.map((row) => row.car_family).filter(Boolean)).size;
  const uniqueCommercialNames = new Set(answer.map((row) => row.commercial_name).filter(Boolean)).size;

  return (
    <div className="table-answer">
      <div className="table-summary">
        <span>{answer.length} matching rows</span>
        <span>{uniqueCarFamilies} unique car families</span>
        <span>{uniqueCommercialNames} unique commercial names</span>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column}>{toTitleCase(column)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {answer.map((row, index) => (
              <tr key={`${row.car_family ?? "row"}-${index}`}>
                {columns.map((column) => (
                  <td key={column}>{String(row[column])}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function renderDistribution(answer) {
  if (!Array.isArray(answer) || answer.length === 0) {
    return <p className="empty-state">No grouped results available.</p>;
  }
  const max = Math.max(...answer.map((item) => item.value), 1);
  return (
    <div className="distribution-list">
      {answer.map((item, index) => {
        const label = Object.entries(item)
          .filter(([key]) => key !== "value")
          .map(([, value]) => value)
          .join(" / ");
        return (
          <div className="distribution-row" key={`${label}-${index}`}>
            <div className="distribution-meta">
              <span>{label || "Result"}</span>
              <strong>{item.value}</strong>
            </div>
            <div className="distribution-bar">
              <div style={{ width: `${(item.value / max) * 100}%` }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function AnswerCard({ response, loading }) {
  let body = <p className="empty-state">Run a query to see answer rows, counts, or grouped distributions.</p>;

  if (loading) {
    body = <p className="empty-state">Executing deterministic launch logic...</p>;
  } else if (response?.status === "unsupported") {
    body = (
      <div className="unsupported-state">
        <p>This query cannot be answered from the uploaded LRP sample without inventing missing fields.</p>
        <ul className="detail-list">
          {(response.plan?.unsupported_reasons ?? []).map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      </div>
    );
  } else if (response?.status === "clarification_needed") {
    body = <p className="empty-state">LaunchIQ needs one clarification before it can execute the plan.</p>;
  } else if (response?.status === "ok") {
    if (response.answer_type === "count") {
      body = renderCount(response.answer);
    } else if (response.answer_type === "distribution" || response.answer_type === "timeline") {
      body = renderDistribution(response.answer);
    } else {
      body = renderTable(response.answer);
    }
  }

  return (
    <section className="panel answer-panel">
      <div className="panel-header">
        <div>
          <h2>Answer</h2>
          <p>Only deterministic outputs are shown here.</p>
        </div>
        <span className="badge">{response?.answer_type ?? "idle"}</span>
      </div>
      {body}
    </section>
  );
}
