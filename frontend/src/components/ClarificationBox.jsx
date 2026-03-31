import { useEffect, useState } from "react";

export function ClarificationBox({ questions, onSubmit, loading }) {
  const initialAnswers = questions.reduce((accumulator, question) => {
    accumulator[question.field] = question.options[0] ?? "";
    return accumulator;
  }, {});
  const [answers, setAnswers] = useState(initialAnswers);

  useEffect(() => {
    setAnswers(initialAnswers);
  }, [questions]);

  function handleSubmit(event) {
    event.preventDefault();
    onSubmit(answers);
  }

  return (
    <section className="panel clarification-panel">
      <div className="panel-header">
        <div>
          <h2>Clarification Required</h2>
          <p>One additional input is needed before the answer can be completed.</p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="clarification-form">
        {questions.map((question) => (
          <label key={question.field} className="clarification-question">
            <span>{question.question}</span>
            <select
              value={answers[question.field] ?? ""}
              onChange={(event) => setAnswers((current) => ({ ...current, [question.field]: event.target.value }))}
            >
              {question.options.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
            <small>{question.reason}</small>
          </label>
        ))}
        <button type="submit" disabled={loading}>
          {loading ? "Resolving..." : "Continue"}
        </button>
      </form>
    </section>
  );
}
