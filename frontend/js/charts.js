// charts.js — draws the dashboard charts with Chart.js.

const COLOR = "#1f4e79";
const COLOR_LIGHT = "rgba(31, 78, 121, 0.15)";
const chartObjects = {};

// Create the chart the first time, then just swap its data on later calls.
function drawChart(canvasId, type, labels, values, label) {
  if (chartObjects[canvasId]) {
    chartObjects[canvasId].data.labels = labels;
    chartObjects[canvasId].data.datasets[0].data = values;
    chartObjects[canvasId].update();
    return;
  }
  chartObjects[canvasId] = new Chart(document.getElementById(canvasId), {
    type: type,
    data: {
      labels: labels,
      datasets: [{
        label: label,
        data: values,
        borderColor: COLOR,
        backgroundColor: type === "line" ? COLOR_LIGHT : COLOR,
        fill: type === "line",
        tension: 0.25,
        pointRadius: type === "line" ? 2 : 0,
      }],
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: { y: { beginAtZero: type === "bar" } },
    },
  });
}

function hourLabel(h) {
  if (h === 0) return "12am";
  if (h === 12) return "12pm";
  return h < 12 ? h + "am" : (h - 12) + "pm";
}

const charts = {
  daily(rows) {
    drawChart("chart-daily", "line",
      rows.map(r => r.date.slice(5)),            // "01-15"
      rows.map(r => r.trips), "Trips");
  },
  hourly(rows) {
    drawChart("chart-hourly", "bar",
      rows.map(r => hourLabel(r.hour)),
      rows.map(r => Math.round(r.trips / r.days)), "Trips per hour");
    drawChart("chart-speed", "line",
      rows.map(r => hourLabel(r.hour)),
      rows.map(r => r.avg_speed), "Average speed (mph)");
  },
  distance(rows) {
    drawChart("chart-distance", "bar",
      rows.map(r => r.label),
      rows.map(r => r.fare_per_mile), "Fare per mile ($)");
  },
};
