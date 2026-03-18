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

export function queryLaunchIQ(query) {
  return request("/query", { query });
}

export function clarifyLaunchIQ(originalQuery, answers) {
  return request("/clarify", { original_query: originalQuery, answers });
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

