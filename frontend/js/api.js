// api.js — all fetch calls to the backend live here.
// If the backend is not running (or the page is opened with ?mock=1),
// responses are read from mock/sample_responses.json instead.

const API_BASE = "";   // same server that serves the page
let useMock = new URLSearchParams(location.search).has("mock");
let mockData = null;

function buildQuery(params) {
  const q = new URLSearchParams();
  for (const [key, value] of Object.entries(params || {})) {
    if (value !== "" && value !== null && value !== undefined) q.set(key, value);
  }
  const s = q.toString();
  return s ? "?" + s : "";
}

async function getMock(path) {
  if (!mockData) mockData = await (await fetch("mock/sample_responses.json")).json();
  const key = mockData[path] ? path : path.replace(/\/\d+$/, "/:id");
  return mockData[key];
}

async function apiGet(path, params) {
  if (useMock) return getMock(path);
  let res;
  try {
    res = await fetch(API_BASE + path + buildQuery(params));
  } catch (err) {
    console.warn("Backend not reachable, using mock data.");
    useMock = true;
    return getMock(path);
  }
  const body = await res.json();
  if (!res.ok) throw new Error(body.message || "Request failed");
  return body;
}

const api = {
  meta:        ()                      => apiGet("/api/meta"),
  quality:     ()                      => apiGet("/api/quality"),
  summary:     (f)                     => apiGet("/api/summary", f),
  insights:    (f)                     => apiGet("/api/insights", f),
  daily:       (f)                     => apiGet("/api/timeseries/daily", f),
  hourly:      (f)                     => apiGet("/api/timeseries/hourly", f),
  byDistance:  (f)                     => apiGet("/api/breakdown/distance", f),
  zoneRank:    (f, metric, order)      => apiGet("/api/zones/rank", { ...f, metric, order, k: 10 }),
  topRoutes:   (f, by, order)          => apiGet("/api/routes/top", { ...f, by, order, k: 10 }),
  trips:       (f, sort, order, page)  => apiGet("/api/trips", { ...f, sort, order, page, page_size: 20 }),
  trip:        (id)                    => apiGet("/api/trips/" + id),
  isMock:      ()                      => useMock,
};
