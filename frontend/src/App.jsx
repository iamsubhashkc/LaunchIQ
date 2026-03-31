import { useState } from "react";
import { clarifyLaunchIQ, queryLaunchIQ, sendFeedback } from "./api";
import { AnswerCard } from "./components/AnswerCard";
import { ChatInput } from "./components/ChatInput";
import { ClarificationBox } from "./components/ClarificationBox";
import { ExplanationPanel } from "./components/ExplanationPanel";
import { FeedbackButtons } from "./components/FeedbackButtons";

const SAMPLE_QUERIES = [
  "Which vehicles are launching in the next 24 months across RoS and IPZ?",
  "Tell me about Jeep Recon",
  "What are the X0 deliverables for F2X, and when is the X0 for F2X?",
];

export default function App() {
  const [query, setQuery] = useState(SAMPLE_QUERIES[0]);
  const [response, setResponse] = useState(null);
  const [pendingClarification, setPendingClarification] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [feedbackState, setFeedbackState] = useState("");
  const [activeView, setActiveView] = useState("workspace");

  const hasAnswer = response?.status === "ok";

  const summary = response?.plan
    ? response.plan.reasoning_summary || "Deterministic execution completed."
    : "Planner output will appear here once a query is executed.";

  async function handleSubmit(nextQuery) {
    setLoading(true);
    setError("");
    setFeedbackState("");
    setPendingClarification(null);
    setActiveView("workspace");
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
      <header className="masthead">
        <div className="brand-lockup">
          <div className="brand-badge">
            <span className="brand-mark">LaunchIQ</span>
          </div>
        </div>
      </header>

      <div className="topbar">
        <div className="view-switch">
          <button
            type="button"
            className={activeView === "workspace" ? "view-switch-button active" : "view-switch-button"}
            onClick={() => setActiveView("workspace")}
          >
            Workspace
          </button>
          <button
            type="button"
            className={activeView === "analysis" ? "view-switch-button active" : "view-switch-button"}
            onClick={() => setActiveView("analysis")}
          >
            Analysis
          </button>
        </div>
        {response?.query ? (
          <div className="active-query-pill">
            <span>Current question</span>
            <strong>{response.query}</strong>
          </div>
        ) : null}
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

      {activeView === "workspace" ? (
        <div className="workspace-stage">
          <AnswerCard response={response} loading={loading} />
        </div>
      ) : (
        <div className="analysis-stage">
          <ExplanationPanel plan={response?.plan} explanation={response?.explanation} summary={summary} />
        </div>
      )}

      <FeedbackButtons disabled={!hasAnswer || loading} onSubmit={handleFeedback} status={feedbackState} />
    </div>
  );
}
