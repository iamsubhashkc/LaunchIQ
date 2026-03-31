export function ChatInput({ query, onQueryChange, onSubmit, sampleQueries, loading }) {
  function handleSubmit(event) {
    event.preventDefault();
    onSubmit(query);
  }

  return (
    <section className="panel input-panel">
      <div className="panel-header">
        <div>
          <h2>Ask LaunchIQ</h2>
          <p>Enter a portfolio, launch, milestone, readiness, or vehicle-specific question.</p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="query-form">
        <textarea
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          rows={4}
          placeholder="Example: What are the X0 deliverables for F2X, and when is the X0 for F2X?"
        />
        <div className="query-actions">
          <div className="query-primary-actions">
            <button type="submit" disabled={loading || !query.trim()}>
              {loading ? "Running analysis..." : "Run Query"}
            </button>
          </div>
          <div className="sample-queries">
            {sampleQueries.map((sample) => (
              <button key={sample} type="button" className="ghost-button" onClick={() => onQueryChange(sample)}>
                {sample}
              </button>
            ))}
          </div>
        </div>
      </form>
    </section>
  );
}
