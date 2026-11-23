// Talks to the Compass service. All numbers come from here; the website never computes results itself.

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(path, options);
  } catch (error) {
    throw new Error("The Compass service is not reachable. Start it with: python run.py");
  }
  let body = null;
  try {
    body = await response.json();
  } catch (error) {
    body = null;
  }
  if (!response.ok) {
    const detail = body?.detail;
    const message = Array.isArray(detail)
      ? detail.map((item) => item.msg ?? JSON.stringify(item)).join("; ")
      : detail ?? `The request failed (${response.status}).`;
    throw new Error(String(message));
  }
  return body;
}

const institutionCache = new Map();

export function institutionKey(settings = {}) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(settings)) {
    if (value !== undefined && value !== null && value !== "") query.set(key, String(value));
  }
  return query.toString();
}

/** The foundation's full analysis. Cached per settings so moving between sections never reloads. */
export function getInstitution(settings = {}) {
  const key = institutionKey(settings);
  if (!institutionCache.has(key)) {
    const promise = request(`/api/institution${key ? `?${key}` : ""}`).catch((error) => {
      institutionCache.delete(key);
      throw error;
    });
    institutionCache.set(key, promise);
  }
  return institutionCache.get(key);
}

export function postPersonalPlan(inputs) {
  return request("/api/personal/plan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(inputs),
  });
}

export function lookupTicker(ticker) {
  return request(`/api/universe/lookup?ticker=${encodeURIComponent(ticker)}`);
}

export function refreshPrices(tickers) {
  return request("/api/data/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tickers }),
  });
}

const legendCache = new Map();

/** Cached GET for the legend endpoints (13F filings change only once a quarter). */
export function getLegend(path) {
  if (!legendCache.has(path)) {
    const promise = request(path).catch((error) => {
      legendCache.delete(path);
      throw error;
    });
    legendCache.set(path, promise);
  }
  return legendCache.get(path);
}

export function postLiveCommittee(payload) {
  return request("/api/committee/live", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}
