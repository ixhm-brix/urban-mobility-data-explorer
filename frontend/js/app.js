// app.js — loads data from the API and fills every section of the page.

let currentFilters = {};
let sortBy = "pickup";
let sortOrder = "desc";
let page = 1;

const $ = (id) => document.getElementById(id);

// ---------- formatting helpers ----------
const fmtInt = (n) => (n == null ? "-" : Number(n).toLocaleString("en-US"));
const fmtMoney = (n) => (n == null ? "-" : "$" + Number(n).toFixed(2));
const fmt1 = (n) => (n == null ? "-" : Number(n).toFixed(1));
const fmtPct = (n) => (n == null ? "-" : Number(n).toFixed(1) + "%");

function setStatus(text) { $("status").textContent = text; }

// Build table rows from an array of cell arrays (uses textContent, not innerHTML).
function fillTable(tbodyId, rows, onClick) {
  const tbody = $(tbodyId);
  tbody.innerHTML = "";
  if (!rows.length) {
    const tr = tbody.insertRow();
    const td = tr.insertCell();
    td.colSpan = 10;
    td.textContent = "No data for these filters.";
    return;
  }
  rows.forEach((cells, i) => {
    const tr = tbody.insertRow();
    cells.forEach((value, j) => {
      const td = tr.insertCell();
      td.textContent = value;
      if (typeof value === "string" && /^[\d$,.\-%]+$/.test(value) && j > 0) td.className = "num";
    });
    if (onClick) tr.addEventListener("click", () => onClick(i));
  });
}

// ---------- sections ----------
async function loadSummary() {
  const { data } = await api.summary(currentFilters);
  const s = data.current;
  const cards = [
    ["Trips", fmtInt(s.trips)],
    ["Revenue", "$" + fmtInt(Math.round(s.revenue))],
    ["Average fare", fmtMoney(s.avg_fare)],
    ["Average distance", fmt1(s.avg_distance) + " mi"],
    ["Average speed", fmt1(s.avg_speed) + " mph"],
    ["Average tip (card)", fmtPct(s.tip_pct)],
  ];
  $("summary").innerHTML = "";
  for (const [label, value] of cards) {
    const div = document.createElement("div");
    div.className = "card";
    div.innerHTML = `<div class="label"></div><div class="value"></div>`;
    div.querySelector(".label").textContent = label;
    div.querySelector(".value").textContent = s.trips ? value : "-";
    $("summary").appendChild(div);
  }
}

async function loadInsights() {
  const { data } = await api.insights(currentFilters);
  $("insights").innerHTML = "";
  for (const ins of data) {
    const div = document.createElement("div");
    div.className = "insight";
    div.innerHTML = `<h3></h3><p class="headline"></p><p class="detail"></p>`;
    div.querySelector("h3").textContent = ins.title;
    div.querySelector(".headline").textContent = ins.headline;
    div.querySelector(".detail").textContent = ins.detail;
    $("insights").appendChild(div);
  }
}

async function loadCharts() {
  const [daily, hourly, distance] = await Promise.all([
    api.daily(currentFilters), api.hourly(currentFilters), api.byDistance(currentFilters),
  ]);
  charts.daily(daily.data);
  charts.hourly(hourly.data);
  charts.distance(distance.data);
}

const METRIC_NAMES = {
  trips: "Trips", avg_fare: "Avg fare", avg_speed: "Avg speed (mph)",
  tip_pct: "Tip %", detour_index: "Detour index",
};
function formatMetric(metric, value) {
  if (metric === "trips") return fmtInt(value);
  if (metric === "avg_fare") return fmtMoney(value);
  if (metric === "tip_pct") return fmtPct(value);
  if (metric === "detour_index") return Number(value).toFixed(2) + "x";
  return fmt1(value);
}

async function loadZones() {
  const [metric, order] = $("zone-metric").value.split("|");
  const { data } = await api.zoneRank(currentFilters, metric, order || "desc");
  $("zone-metric-head").textContent = METRIC_NAMES[metric];
  fillTable("zone-rows", data.map((z, i) => [i + 1, z.zone, z.borough, formatMetric(metric, z[metric])]));
}

async function loadRoutes() {
  const [metric, order] = $("route-metric").value.split("|");
  const { data, meta } = await api.topRoutes(currentFilters, metric, order || "desc");
  $("route-metric-head").textContent = METRIC_NAMES[metric];
  fillTable("route-rows", data.map((r, i) => [i + 1, r.pu_zone, r.do_zone, formatMetric(metric, r[metric])]));
  const names = { start: "dates", end: "dates", dist: "distance", fare: "fare", payment: "payment" };
  const ignored = [...new Set((meta.ignored_filters || []).map(k => names[k] || k))];
  $("route-note").textContent = ignored.length
    ? "Note: routes come from a summary table, so these filters are not applied here: " + ignored.join(", ") + "."
    : "";
}

let tripRows = [];
async function loadTrips() {
  const { data, meta } = await api.trips(currentFilters, sortBy, sortOrder, page);
  tripRows = data;
  fillTable("trip-rows", data.map(t => [
    t.pickup_datetime.slice(5, 16),
    t.pu_zone, t.do_zone,
    t.trip_distance.toFixed(2), t.trip_duration_min.toFixed(1), t.avg_speed_mph.toFixed(1),
    t.fare_amount.toFixed(2), t.tip_pct != null ? t.tip_amount.toFixed(2) : "-", t.payment,
  ]), (i) => showTrip(tripRows[i].trip_id));
  $("page-info").textContent = `Page ${meta.page} of ${fmtInt(meta.pages)} (${fmtInt(meta.total)} trips)`;
  $("prev").disabled = meta.page <= 1;
  $("next").disabled = meta.page >= meta.pages;

  document.querySelectorAll("th.sortable").forEach(th => {
    th.classList.remove("sorted-asc", "sorted-desc");
    if (th.dataset.sort === sortBy) th.classList.add(sortOrder === "asc" ? "sorted-asc" : "sorted-desc");
  });
}

async function loadQuality() {
  const { data } = await api.quality();
  const run = data.run;
  $("quality-summary").textContent =
    `Raw records: ${fmtInt(run.raw_rows)} — excluded: ${fmtInt(run.excluded_rows)} ` +
    `(${(100 * run.excluded_rows / run.raw_rows).toFixed(2)}%) — clean trips loaded: ${fmtInt(run.clean_rows)}.`;
  fillTable("quality-rows", data.rules
    .filter(r => r.record_count > 0)
    .map(r => [r.rule_code, r.action, r.description, fmtInt(r.record_count)]));
}

// ---------- trip detail popup ----------
async function showTrip(id) {
  const { data } = await api.trip(id);
  const t = data.trip, p = data.route_peers || {};
  const rows = [
    ["Trip ID", t.trip_id],
    ["Pickup", `${t.pickup_datetime} — ${t.pu_zone}, ${t.pu_borough}`],
    ["Dropoff", `${t.dropoff_datetime} — ${t.do_zone}, ${t.do_borough}`],
    ["Distance", t.trip_distance + " mi"],
    ["Duration", t.trip_duration_min + " min"],
    ["Average speed", t.avg_speed_mph + " mph"],
    ["Passengers", t.passenger_count ?? "Not recorded"],
    ["Payment", t.payment],
    ["Rate code", t.rate_code],
    ["Fare", fmtMoney(t.fare_amount)],
    ["Extras & taxes", fmtMoney(t.extra + t.mta_tax + t.improvement_surcharge + t.congestion_surcharge)],
    ["Tolls", fmtMoney(t.tolls_amount)],
    ["Tip", t.tip_pct != null ? `${fmtMoney(t.tip_amount)} (${fmtPct(t.tip_pct)})` : "Not recorded (cash)"],
    ["Total", fmtMoney(t.total_amount)],
    ["Fare per mile", fmtMoney(t.fare_per_mile)],
    ["Detour index", t.detour_index ? t.detour_index.toFixed(2) + "x" : "-"],
    ["Airport trip", t.is_airport_trip ? "Yes" : "No"],
    ["Crosses borough", t.is_cross_borough ? "Yes" : "No"],
  ];
  if (p.trips > 1) {
    rows.push(["Same route, same hour (avg)", `${fmtInt(p.trips)} trips · ${fmtMoney(p.avg_fare)} · ${p.avg_duration} min`]);
  }
  const table = document.createElement("table");
  table.className = "details";
  for (const [k, v] of rows) {
    const tr = table.insertRow();
    tr.insertCell().textContent = k;
    tr.insertCell().textContent = v;
  }
  $("modal-body").replaceChildren(table);
  $("modal").hidden = false;
}
function closeModal() { $("modal").hidden = true; }

// ---------- refresh everything ----------
async function refresh() {
  setStatus("Loading…");
  page = 1;
  try {
    await Promise.all([loadSummary(), loadInsights(), loadCharts(), loadZones(), loadRoutes(), loadTrips()]);
    setStatus(api.isMock() ? "Showing sample data (backend not running)." : "");
  } catch (err) {
    setStatus("Error: " + err.message);
  }
}

// ---------- events ----------
form.addEventListener("submit", (e) => {
  e.preventDefault();
  currentFilters = getFilters();
  refresh();
});
$("reset").addEventListener("click", () => {
  form.reset();
  currentFilters = {};
  refresh();
});
$("zone-metric").addEventListener("change", () => loadZones().catch(e => setStatus("Error: " + e.message)));
$("route-metric").addEventListener("change", () => loadRoutes().catch(e => setStatus("Error: " + e.message)));
document.querySelectorAll("th.sortable").forEach(th => {
  th.addEventListener("click", () => {
    if (sortBy === th.dataset.sort) sortOrder = sortOrder === "asc" ? "desc" : "asc";
    else { sortBy = th.dataset.sort; sortOrder = "desc"; }
    page = 1;
    loadTrips().catch(e => setStatus("Error: " + e.message));
  });
});
$("prev").addEventListener("click", () => { page--; loadTrips(); });
$("next").addEventListener("click", () => { page++; loadTrips(); });
$("modal-close").addEventListener("click", closeModal);
$("modal").addEventListener("click", (e) => { if (e.target.id === "modal") closeModal(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });

// ---------- start ----------
(async function init() {
  try {
    const { data } = await api.meta();
    setupFilters(data);
    $("subtitle").textContent = `NYC Yellow Taxi trips — ${data.date_range.min} to ${data.date_range.max}`;
  } catch (err) {
    setStatus("Could not load filters: " + err.message);
  }
  refresh();
  loadQuality().catch(err => console.error(err));
})();
