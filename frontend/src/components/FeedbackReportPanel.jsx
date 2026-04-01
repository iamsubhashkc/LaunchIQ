function formatStoredAt(value) {
  if (!value) {
    return "Unknown time";
  }
  const timestamp = new Date(value);
  if (Number.isNaN(timestamp.getTime())) {
    return String(value);
  }
  return timestamp.toLocaleString();
}

export function FeedbackReportPanel({ report, loading, error, onRefresh }) {
  const total = report?.total_feedback ?? 0;
  const recentFeedback = report?.recent_feedback ?? [];
  const topCorrections = report?.top_corrections ?? [];

  return (
    <section className="panel feedback-report-panel">
      <div className="panel-header">
        <div>
          <h2>Feedback Report</h2>
          <p>Review recent answer ratings and repeated correction patterns for planner tuning.</p>
        </div>
        <div className="panel-header-actions">
          <button type="button" className="ghost-button" onClick={onRefresh} disabled={loading}>
            {loading ? "Refreshing..." : "Refresh"}
          </button>
        </div>
      </div>

      {error ? <div className="status-card error-card">{error}</div> : null}

      <div className="feedback-report-summary">
        <div className="feedback-report-stat">
          <span>Total Feedback</span>
          <strong>{total}</strong>
        </div>
        <div className="feedback-report-stat">
          <span>Accurate</span>
          <strong>{report?.helpful_count ?? 0}</strong>
        </div>
        <div className="feedback-report-stat">
          <span>Incorrect</span>
          <strong>{report?.incorrect_count ?? 0}</strong>
        </div>
        <div className="feedback-report-stat">
          <span>Needs More Detail</span>
          <strong>{report?.needs_more_detail_count ?? 0}</strong>
        </div>
      </div>

      <div className="feedback-report-grid">
        <div className="explanation-card">
          <span className="label">Top Corrections</span>
          {topCorrections.length ? (
            <ul className="detail-list">
              {topCorrections.map((correction) => (
                <li key={correction}>{correction}</li>
              ))}
            </ul>
          ) : (
            <p className="empty-state">No correction notes have been captured yet.</p>
          )}
        </div>

        <div className="explanation-card">
          <span className="label">Recent Feedback</span>
          {recentFeedback.length ? (
            <div className="feedback-report-recent">
              {recentFeedback.map((item, index) => (
                <article className="feedback-report-entry" key={`${item.query}-${item.stored_at}-${index}`}>
                  <div className="feedback-report-entry-top">
                    <strong>{item.rating.replaceAll("_", " ")}</strong>
                    <span>{formatStoredAt(item.stored_at)}</span>
                  </div>
                  <p className="feedback-report-query">{item.query}</p>
                  {item.correction ? <p className="feedback-report-correction">{item.correction}</p> : null}
                </article>
              ))}
            </div>
          ) : (
            <p className="empty-state">No feedback has been stored yet.</p>
          )}
        </div>
      </div>
    </section>
  );
}
