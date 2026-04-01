export function ChatInput({ query, onQueryChange, onSubmit, loading, plannerMode, onPlannerModeChange }) {
  function handleSubmit(event) {
    event.preventDefault();
    onSubmit(query);
  }

  function handleReset() {
    window.location.reload();
  }

  return (
    <section className="panel input-panel">
      <div className="panel-header">
        <div>
          <h2>Ask LaunchIQ</h2>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="query-form">
        <div className="planner-mode-control">
          <div>
            <span className="label">Planner Mode</span>
            <p>{plannerMode === "hybrid" ? "Hybrid uses backend-configured LLM assistance when available." : "Heuristic uses deterministic planner rules only."}</p>
          </div>
          <div className="planner-mode-switch" role="tablist" aria-label="Planner mode">
            <button
              type="button"
              className={plannerMode === "heuristic" ? "view-switch-button active" : "view-switch-button"}
              onClick={() => onPlannerModeChange("heuristic")}
            >
              Heuristic
            </button>
            <button
              type="button"
              className={plannerMode === "hybrid" ? "view-switch-button active" : "view-switch-button"}
              onClick={() => onPlannerModeChange("hybrid")}
            >
              Hybrid
            </button>
          </div>
        </div>
        <textarea
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          rows={4}
          placeholder="Ask a portfolio, launch, milestone, readiness, or vehicle-specific question."
        />
        <div className="query-actions">
          <div className="query-primary-actions">
            <button type="button" className="ghost-button" onClick={handleReset} disabled={loading}>
              Reset
            </button>
            <button type="submit" disabled={loading || !query.trim()}>
              {loading ? "Running analysis..." : "Ask"}
            </button>
          </div>
        </div>
      </form>
    </section>
  );
}
