import { useState } from "react";

export function FeedbackButtons({ disabled, onSubmit, status }) {
  const [correction, setCorrection] = useState("");

  return (
    <section className="panel feedback-panel">
      <div className="panel-header">
        <div>
          <h2>Review This Answer</h2>
          <p>Share what was wrong or missing in this answer. Use feedback for query understanding, filters, grouping, or missing detail, not for UI styling issues.</p>
        </div>
      </div>

      <textarea
        rows={3}
        placeholder="Optional note: explain what LaunchIQ misunderstood, filtered incorrectly, grouped incorrectly, or left out. Skip UI/layout comments here."
        value={correction}
        onChange={(event) => setCorrection(event.target.value)}
      />

      <div className="feedback-grid">
        <button disabled={disabled} onClick={() => onSubmit("helpful", correction)}>
          Accurate
        </button>
        <button disabled={disabled} onClick={() => onSubmit("needs_more_detail", correction)}>
          Needs More Detail
        </button>
        <button disabled={disabled} onClick={() => onSubmit("incorrect", correction)}>
          Incorrect
        </button>
      </div>

      <p className="feedback-status">{status || "Feedback is stored for future planner refinement."}</p>
    </section>
  );
}
