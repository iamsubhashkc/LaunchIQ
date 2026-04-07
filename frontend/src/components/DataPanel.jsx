const VIEW_ORDER = ["vehicle", "launch_event", "feedback", "milestones"];

function formatSourceKind(value) {
  return String(value || "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (match) => match.toUpperCase());
}

export function DataPanel({
  catalog,
  preview,
  activeDataView,
  onDataViewChange,
  loading,
  error,
  uploadStatus,
  uploading,
  onUpload,
  onRefresh,
}) {
  const orderedViews = VIEW_ORDER.map((view) => catalog?.views?.find((item) => item.view === view)).filter(Boolean);

  function handleFileChange(event) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }
    onUpload(file);
    event.target.value = "";
  }

  return (
    <section className="panel data-panel">
      <div className="panel-header">
        <div>
          <h2>Data</h2>
          <p>Inspect the active LRP dataset, generated launch events, feedback records, and milestone deliverables.</p>
        </div>
        <div className="panel-header-actions">
          <button type="button" className="ghost-button" onClick={onRefresh} disabled={loading || uploading}>
            {loading ? "Refreshing..." : "Refresh"}
          </button>
          <label className={`upload-button${uploading ? " disabled" : ""}`}>
            <input type="file" accept=".xlsx,.xlsm" onChange={handleFileChange} disabled={uploading} />
            {uploading ? "Uploading..." : "Upload Latest LRP"}
          </label>
        </div>
      </div>

      {error ? <div className="status-card error-card">{error}</div> : null}
      {uploadStatus ? <div className="status-card">{uploadStatus}</div> : null}

      <div className="data-source-card">
        <div>
          <span className="label">Active Source</span>
          <strong>{formatSourceKind(catalog?.source_kind || "unknown")}</strong>
        </div>
        <div>
          <span className="label">Workbook Present</span>
          <strong>{catalog?.workbook_present ? "Yes" : "No"}</strong>
        </div>
        <div className="data-source-path">
          <span className="label">Source Path</span>
          <strong>{catalog?.source_path || "Not available"}</strong>
        </div>
      </div>

      <div className="data-summary-grid">
        {orderedViews.map((view) => (
          <button
            type="button"
            key={view.view}
            className={activeDataView === view.view ? "data-summary-card active" : "data-summary-card"}
            onClick={() => onDataViewChange(view.view)}
          >
            <span>{view.label}</span>
            <strong>{view.row_count}</strong>
            <small>{view.column_count} columns</small>
          </button>
        ))}
      </div>

      <div className="explanation-card">
        <span className="label">{preview?.label || "Data Preview"}</span>
        <p className="data-preview-meta">
          Showing {preview?.rows?.length ?? 0} of {preview?.row_count ?? 0} rows
        </p>
        {preview?.rows?.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  {(preview.columns || []).map((column) => (
                    <th key={column}>{column}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {preview.rows.map((row, index) => (
                  <tr key={`${preview.view}-${index}`}>
                    {preview.columns.map((column) => (
                      <td key={`${column}-${index}`}>{row[column] || "—"}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="empty-state">No rows are available for this data view.</p>
        )}
      </div>
    </section>
  );
}
