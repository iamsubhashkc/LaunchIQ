const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function request(path, payload) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}`);
  }

  return response.json();
}

export function queryLaunchIQ(query, plannerMode) {
  return request("/query", { query, planner_mode: plannerMode });
}

export function clarifyLaunchIQ(originalQuery, answers, plannerMode) {
  return request("/clarify", { original_query: originalQuery, answers, planner_mode: plannerMode });
}

export async function exportLaunchIQResult(responsePayload) {
  const response = await fetch(`${API_BASE_URL}/export`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      query: responsePayload?.query ?? "LaunchIQ Export",
      plan: responsePayload?.plan ?? {},
      answer_type: responsePayload?.answer_type ?? null,
      answer: responsePayload?.answer ?? [],
    }),
  });

  if (!response.ok) {
    throw new Error(`Export failed with status ${response.status}`);
  }

  const blob = await response.blob();
  const url = window.URL.createObjectURL(blob);
  const disposition = response.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename=\"?([^"]+)\"?/i);
  const filename = match?.[1] || "launchiq_export.xlsx";
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

export function sendFeedback(query, plan, answer, rating, correction) {
  return request("/feedback", {
    query,
    plan,
    answer,
    rating,
    correction,
  });
}

export async function getMilestoneDeliverables() {
  const response = await fetch(`${API_BASE_URL}/milestones/deliverables`);
  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}`);
  }
  return response.json();
}

export async function getFeedbackReport() {
  const response = await fetch(`${API_BASE_URL}/feedback/report`);
  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}`);
  }
  return response.json();
}
