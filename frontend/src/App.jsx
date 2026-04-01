import { useEffect, useState } from "react";
import { clarifyLaunchIQ, exportLaunchIQResult, getFeedbackReport, queryLaunchIQ, sendFeedback } from "./api";
import { AnswerCard } from "./components/AnswerCard";
import { ChatInput } from "./components/ChatInput";
import { ClarificationBox } from "./components/ClarificationBox";
import { ExplanationPanel } from "./components/ExplanationPanel";
import { FeedbackButtons } from "./components/FeedbackButtons";
import { FeedbackReportPanel } from "./components/FeedbackReportPanel";
import stellantisLogo from "./assets/stellantis-logo.svg";
const PLANNER_MODE_KEY = "launchiq_planner_mode";

export default function App() {
  const [query, setQuery] = useState("");
  const [response, setResponse] = useState(null);
  const [pendingClarification, setPendingClarification] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [feedbackState, setFeedbackState] = useState("");
  const [feedbackSubmitted, setFeedbackSubmitted] = useState(false);
  const [activeView, setActiveView] = useState("workspace");
  const [exporting, setExporting] = useState(false);
  const [feedbackReport, setFeedbackReport] = useState(null);
  const [feedbackReportLoading, setFeedbackReportLoading] = useState(false);
  const [feedbackReportError, setFeedbackReportError] = useState("");
  const [feedbackReportLoaded, setFeedbackReportLoaded] = useState(false);
  const [plannerMode, setPlannerMode] = useState(() => {
    if (typeof window === "undefined") {
      return "heuristic";
    }
    const stored = window.localStorage.getItem(PLANNER_MODE_KEY);
    return stored === "hybrid" ? "hybrid" : "heuristic";
  });

  const hasAnswer = response?.status === "ok";
  const shouldShowWorkspace = loading || Boolean(response);
  const shouldShowFeedback = hasAnswer && !feedbackSubmitted;

  const summary = response?.plan
    ? response.plan.reasoning_summary || "Deterministic execution completed."
    : "Planner output will appear here once a query is executed.";

  useEffect(() => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(PLANNER_MODE_KEY, plannerMode);
    }
  }, [plannerMode]);

  useEffect(() => {
    if (activeView === "feedback" && !feedbackReportLoaded) {
      void loadFeedbackReport();
    }
  }, [activeView, feedbackReportLoaded]);

  async function loadFeedbackReport() {
    setFeedbackReportLoading(true);
    setFeedbackReportError("");
    try {
      const payload = await getFeedbackReport();
      setFeedbackReport(payload);
      setFeedbackReportLoaded(true);
    } catch (requestError) {
      setFeedbackReportError(requestError.message);
    } finally {
      setFeedbackReportLoading(false);
    }
  }

  async function handleSubmit(nextQuery) {
    setLoading(true);
    setError("");
    setFeedbackState("");
    setFeedbackSubmitted(false);
    setPendingClarification(null);
    setActiveView("workspace");
    try {
      const payload = await queryLaunchIQ(nextQuery, plannerMode);
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
    setFeedbackState("");
    setFeedbackSubmitted(false);
    try {
      const payload = await clarifyLaunchIQ(pendingClarification.query, answers, plannerMode);
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
      setFeedbackState("Thank you. Feedback saved for future planner tuning.");
      setFeedbackSubmitted(true);
      setFeedbackReportLoaded(false);
      if (activeView === "feedback") {
        void loadFeedbackReport();
      }
    } catch (requestError) {
      setFeedbackSubmitted(false);
      setFeedbackState(`Feedback failed: ${requestError.message}`);
    }
  }

  async function handleExport() {
    if (!response || response.status !== "ok") {
      return;
    }
    setExporting(true);
    setError("");
    try {
      await exportLaunchIQResult(response);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="app-shell">
      <header className="masthead">
        <div className="brand-lockup">
          <img className="brand-logo" src={stellantisLogo} alt="Stellantis" />
          <span className="brand-wordmark">LaunchIQ</span>
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
          <button
            type="button"
            className={activeView === "feedback" ? "view-switch-button active" : "view-switch-button"}
            onClick={() => setActiveView("feedback")}
          >
            Feedback Report
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
        loading={loading}
        plannerMode={plannerMode}
        onPlannerModeChange={setPlannerMode}
      />

      {error ? <div className="status-card error-card">{error}</div> : null}

      {pendingClarification ? (
        <ClarificationBox questions={pendingClarification.clarification} onSubmit={handleClarify} loading={loading} />
      ) : null}

      {activeView === "workspace" && shouldShowWorkspace ? (
        <div className="workspace-stage">
          <AnswerCard response={response} loading={loading} onExport={handleExport} exporting={exporting} />
        </div>
      ) : activeView === "analysis" ? (
        <div className="analysis-stage">
          <ExplanationPanel plan={response?.plan} explanation={response?.explanation} summary={summary} />
        </div>
      ) : activeView === "feedback" ? (
        <div className="analysis-stage">
          <FeedbackReportPanel
            report={feedbackReport}
            loading={feedbackReportLoading}
            error={feedbackReportError}
            onRefresh={loadFeedbackReport}
          />
        </div>
      ) : null}

      {feedbackSubmitted ? (
        <div className="status-card success-card feedback-thanks-card">
          <div className="feedback-thanks">
            <span className="feedback-check" aria-hidden="true">
              ✓
            </span>
            <div>
              <strong>Thank you.</strong>
              <p>{feedbackState || "Your feedback was saved for future planner tuning."}</p>
            </div>
          </div>
        </div>
      ) : null}

      {shouldShowFeedback ? (
        <FeedbackButtons disabled={!hasAnswer || loading} onSubmit={handleFeedback} status={feedbackState} />
      ) : null}
    </div>
  );
}
