// filters.js — fills the filter form and reads the user's choices.

const form = document.getElementById("filters");

function addOptions(select, items) {
  for (const item of items) {
    const opt = document.createElement("option");
    opt.value = item.id;
    opt.textContent = item.name;
    select.appendChild(opt);
  }
}

// Fill the dropdowns using the reference data from /api/meta.
function setupFilters(meta) {
  // The date pickers only allow dates that exist in the loaded data.
  for (const input of [form.start, form.end]) {
    input.min = meta.date_range.min;
    input.max = meta.date_range.max;
  }

  const hours = [];
  for (let h = 0; h < 24; h++) hours.push({ id: h, name: hourLabel(h) });
  addOptions(form.hour_from, [{ id: "", name: "Any" }, ...hours]);
  addOptions(form.hour_to, [{ id: "", name: "Any" }, ...hours]);

  addOptions(form.borough, meta.boroughs.filter(b => b.name !== "Unknown"));
  addOptions(form.zone, meta.zones.map(z => ({ id: z.id, name: `${z.name} (${z.borough})` })));
  addOptions(form.dist, meta.distance_bands);
  addOptions(form.fare, meta.fare_bands);
  addOptions(form.payment, meta.payment_types);
}

// Return the selected filters as an object, leaving out empty fields.
function getFilters() {
  const filters = {};
  for (const [key, value] of new FormData(form).entries()) {
    if (value !== "") filters[key] = value;
  }
  // If only one end of the hour window is chosen, fill in the other.
  if (filters.hour_from && !filters.hour_to) filters.hour_to = 23;
  if (filters.hour_to && !filters.hour_from) filters.hour_from = 0;
  return filters;
}
