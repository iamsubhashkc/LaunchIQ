export function ChatInput({ query, onQueryChange, onSubmit, sampleQueries, loading }) {
  function handleSubmit(event) {
    event.preventDefault();
    onSubmit(query);
  }

  return (
    <section className="panel input-panel">
      <div className="panel-header">
        <div>
          <h2>Query Workspace</h2>
          <p>Submit a business question and review the plan before using the answer.</p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="query-form">
        <textarea
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          rows={4}
          placeholder="Which vehicles are launching in the next 24 months, and how are they distributed across regions?"
        />
        <div className="query-actions">
          <button type="submit" disabled={loading || !query.trim()}>
            {loading ? "Running..." : "Run LaunchIQ"}
          </button>
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

