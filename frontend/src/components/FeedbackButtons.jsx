import { useState } from "react";

export function FeedbackButtons({ disabled, onSubmit, status }) {
  const [correction, setCorrection] = useState("");

  return (
    <section className="panel feedback-panel">
      <div className="panel-header">
        <div>
          <h2>Feedback</h2>
          <p>Capture planner corrections without changing deterministic execution.</p>
        </div>
      </div>

      <div className="feedback-grid">
        <button disabled={disabled} onClick={() => onSubmit("helpful", correction)}>
          Helpful
        </button>
        <button disabled={disabled} onClick={() => onSubmit("needs_more_detail", correction)}>
          Needs Detail
        </button>
        <button disabled={disabled} onClick={() => onSubmit("incorrect", correction)}>
          Incorrect
        </button>
      </div>

      <textarea
        rows={3}
        placeholder="Optional correction for the planner or dataset interpretation."
        value={correction}
        onChange={(event) => setCorrection(event.target.value)}
      />
      <p className="feedback-status">{status || "Corrections are stored in the learning log for future planner tuning."}</p>
    </section>
  );
}

