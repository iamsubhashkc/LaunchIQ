import { useState } from "react";

export function FeedbackButtons({ disabled, onSubmit, status }) {
  const [correction, setCorrection] = useState("");

  return (
    <section className="panel feedback-panel">
      <div className="panel-header">
        <div>
          <h2>Review This Answer</h2>
          <p>Capture corrections or gaps so LaunchIQ can improve future planning behavior.</p>
        </div>
      </div>

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

      <textarea
        rows={3}
        placeholder="Optional note on what should change in the answer, logic, or interpretation."
        value={correction}
        onChange={(event) => setCorrection(event.target.value)}
      />
      <p className="feedback-status">{status || "Feedback is stored for future planner refinement."}</p>
    </section>
  );
}
