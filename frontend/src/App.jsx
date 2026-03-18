import { useState } from "react";
import { clarifyLaunchIQ, queryLaunchIQ, sendFeedback } from "./api";
import { AnswerCard } from "./components/AnswerCard";
import { ChatInput } from "./components/ChatInput";
import { ClarificationBox } from "./components/ClarificationBox";
import { ExplanationPanel } from "./components/ExplanationPanel";
import { FeedbackButtons } from "./components/FeedbackButtons";

const SAMPLE_QUERIES = [
  "Which Car Families are launching in the next 24 months, and how are they distributed across regions (RoS vs IPZ)?",
  "Which vehicles are still on legacy SDP and scheduled to transition to SSDP before EOP?",
  "How many vehicles lack FOTA/FOTA IVI capability, and what is the customer impact at launch?",
];

export default function App() {
  const [query, setQuery] = useState(SAMPLE_QUERIES[0]);
  const [response, setResponse] = useState(null);
  const [pendingClarification, setPendingClarification] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [feedbackState, setFeedbackState] = useState("");

  const hasAnswer = response?.status === "ok";

  const summary = response?.plan
    ? response.plan.reasoning_summary || "Deterministic execution completed."
    : "Planner output will appear here once a query is executed.";

  async function handleSubmit(nextQuery) {
    setLoading(true);
    setError("");
    setFeedbackState("");
    setPendingClarification(null);
    try {
      const payload = await queryLaunchIQ(nextQuery);
      setQuery(nextQuery);
      setResponse(payload);
      if (payload.status === "clarification_needed") {
        setPendingClarification(payload);
      }
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleClarify(answers) {
    if (!pendingClarification) {
      return;
    }
    setLoading(true);
    setError("");
    try {
      const payload = await clarifyLaunchIQ(pendingClarification.query, answers);
      setPendingClarification(null);
      setResponse(payload);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleFeedback(rating, correction) {
    if (!hasAnswer) {
      return;
    }
    setFeedbackState("Saving feedback...");
    try {
      await sendFeedback(response.query, response.plan, response.answer, rating, correction);
      setFeedbackState("Feedback stored for future planner tuning.");
    } catch (requestError) {
      setFeedbackState(`Feedback failed: ${requestError.message}`);
    }
  }

  return (
    <div className="app-shell">
      <div className="hero">
        <div>
          <p className="eyebrow">LaunchIQ</p>
          <h1>Deterministic launch reasoning for platform, region, and readiness decisions.</h1>
          <p className="hero-copy">
            LaunchIQ uses the model only for planning. Every answer is executed against structured launch data with
            explainable filters, grouping, and logic.
          </p>
        </div>
        <div className="hero-metrics">
          <div className="metric-card">
            <span>Execution mode</span>
            <strong>DuckDB + Pandas</strong>
          </div>
          <div className="metric-card">
            <span>Planner mode</span>
            <strong>{response?.plan ? "Structured JSON" : "Awaiting query"}</strong>
          </div>
        </div>
      </div>

      <ChatInput
        query={query}
        onQueryChange={setQuery}
        onSubmit={handleSubmit}
        sampleQueries={SAMPLE_QUERIES}
        loading={loading}
      />

      {error ? <div className="status-card error-card">{error}</div> : null}

      {pendingClarification ? (
        <ClarificationBox questions={pendingClarification.clarification} onSubmit={handleClarify} loading={loading} />
      ) : null}

      <div className="workspace-grid">
        <AnswerCard response={response} loading={loading} />
        <ExplanationPanel plan={response?.plan} explanation={response?.explanation} summary={summary} />
      </div>

      <FeedbackButtons disabled={!hasAnswer || loading} onSubmit={handleFeedback} status={feedbackState} />
    </div>
  );
}
