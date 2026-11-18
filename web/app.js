/* Assembly Line Data Platform dashboard: renders JSON exported by `python -m assembly export`. */
(async function () {
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const fmt = (n, d = 0) => (n == null ? "–" : Number(n).toLocaleString("en-GB", { maximumFractionDigits: d, minimumFractionDigits: d }));
  const get = (f) => fetch("data/" + f + ".json").then((r) => (r.ok ? r.json() : null)).catch(() => null);
  const [meta, thr, stations, fpy, torque, incidents, batches, drills, bench] = await Promise.all(
    ["meta", "throughput", "stations", "fpy", "torque", "incidents", "batches", "fault_drills", "benchmarks"].map(get));

  const m = meta[0];
  $("#meta").textContent = `${fmt(m.events)} events · ${fmt(m.vehicles)} vehicles · ${m.first_event.slice(0, 16).replace("T", " ")} → ${m.last_event.slice(0, 16).replace("T", " ")} UTC`;

  // KPIs (full days only)
  const fullDays = fpy.filter((d) => d.vehicles_tested > 1000);
  const done = thr.reduce((a, r) => a + r.vehicles, 0);
  const prodHours = thr.filter((r) => r.vehicles > 0);
  const avgHour = prodHours.reduce((a, r) => a + r.vehicles, 0) / prodHours.length;
  const meanFpy = fullDays.reduce((a, d) => a + d.first_pass_yield, 0) / (fullDays.length || 1);
  const fullDaySet = new Set(fullDays.map((d) => d.day));
  const stopDay = stations.filter((s) => fullDaySet.has(s.day)).reduce((a, s) => a + s.stoppage_min, 0) / (fullDaySet.size || 1);
  const drillsPassed = drills ? drills.filter((d) => d.passed).length : 0;
  const best = bench ? bench.queries.reduce((a, q) => Math.max(a, q.speedup), 0) : null;
  const k = [
    ["Vehicles completed", fmt(done), `${Math.round((new Date(m.last_event) - new Date(m.first_event)) / 864e5)} simulated days`],
    ["Vehicles per hour", fmt(avgHour, 1), "target 60 (60 s takt)"],
    ["First-pass yield", (meanFpy * 100).toFixed(1) + "%", "end-of-line, full days"],
    ["Stoppage minutes", fmt(stopDay, 0), "per full day, all stations"],
    ["Fault drills", drills ? `${drillsPassed}/${drills.length}` : "–", "detected, 0 false alarms"],
    ["Best query speed-up", best ? `${fmt(best, 0)}×` : "–", "after indexing"],
  ];
  $("#kpis").innerHTML = k.map(([l, v, n]) => `<div class="kpi"><div class="l">${l}</div><div class="v">${v}</div><div class="n">${n}</div></div>`).join("");

  // Throughput chart (SVG, one bar per hour, dashed target line)
  const W = Math.max(640, thr.length * 12), H = 220, L = 34, B = 24, T = 10;
  const max = Math.max(70, ...thr.map((r) => r.vehicles));
  const y = (v) => T + (H - T - B) * (1 - v / max);
  const bw = (W - L - 8) / thr.length;
  let svg = `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="Vehicles per hour">`;
  [0, 20, 40, 60].forEach((v) => { svg += `<line class="g" x1="${L}" x2="${W}" y1="${y(v)}" y2="${y(v)}"/><text x="${L - 6}" y="${y(v) + 4}" text-anchor="end">${v}</text>`; });
  thr.forEach((r, i) => {
    const x = L + i * bw;
    svg += `<rect class="b${r.vehicles < 50 ? " low" : ""}" x="${x + 1}" y="${y(r.vehicles)}" width="${Math.max(1, bw - 2)}" height="${H - B - y(r.vehicles)}" rx="1.5" data-t="${esc(r.hour.slice(0, 13).replace("T", " "))}:00 · ${r.vehicles} vehicles"/>`;
    if (r.hour.slice(11, 13) === "00") svg += `<text x="${x}" y="${H - 6}">${esc(r.hour.slice(5, 10))}</text>`;
  });
  svg += `<line class="t" x1="${L}" x2="${W}" y1="${y(60)}" y2="${y(60)}"/><text x="${W - 4}" y="${y(60) - 5}" text-anchor="end">target 60</text></svg>`;
  $("#chart").innerHTML = svg;
  const tip = document.createElement("div"); tip.id = "tip"; tip.hidden = true; document.body.appendChild(tip);
  $("#chart").addEventListener("mousemove", (e) => {
    const t = e.target.dataset && e.target.dataset.t;
    if (!t) { tip.hidden = true; return; }
    tip.textContent = t; tip.hidden = false; tip.style.left = e.clientX + 12 + "px"; tip.style.top = e.clientY + 12 + "px";
  });
  $("#chart").addEventListener("mouseleave", () => (tip.hidden = true));

  // Stations table with day selector
  const days = [...new Set(stations.map((s) => s.day))];
  $("#day").innerHTML = days.map((d) => `<option>${d}</option>`).join("");
  $("#day").value = days[Math.min(1, days.length - 1)];
  function renderStations() {
    const rows = stations.filter((s) => s.day === $("#day").value).sort((a, b) => b.p95_dwell_s - a.p95_dwell_s);
    const top = rows.slice(0, 3).map((r) => r.station_id);
    $("#tbl-stations").innerHTML = `<thead><tr><th>Station</th><th>Zone</th><th class="n">Vehicles</th><th class="n">p50 dwell s</th><th class="n">p95 dwell s</th><th class="n">Over takt</th><th class="n">Stoppages</th><th class="n">Stoppage min</th></tr></thead><tbody>` +
      rows.map((r) => `<tr class="${top.includes(r.station_id) ? "hot" : ""}"><td>${esc(r.station_id)} <span class="code">${esc(r.station_name)}</span></td><td>${esc(r.zone)}</td><td class="n">${fmt(r.vehicles)}</td><td class="n">${fmt(r.p50_dwell_s, 1)}</td><td class="n">${fmt(r.p95_dwell_s, 1)}</td><td class="n">${(r.share_over_takt * 100).toFixed(1)}%</td><td class="n">${r.stoppages}</td><td class="n">${fmt(r.stoppage_min, 1)}</td></tr>`).join("") + "</tbody>";
  }
  $("#day").addEventListener("change", renderStations);
  renderStations();

  // Fault drills
  if (drills) {
    $("#drill-pill").textContent = `${drillsPassed}/${drills.length} passed`;
    $("#tbl-drills").innerHTML = `<thead><tr><th>Scenario</th><th>Fault</th><th>Caught by</th><th>Result</th></tr></thead><tbody>` +
      drills.map((d) => `<tr><td><b>${esc(d.scenario.replace(/_/g, " "))}</b></td><td>${esc(d.description)}<div class="code">${esc((d.summaries[0] || "no incident"))}</div></td><td class="code">${esc(d.fired.join(", ") || "—")}${d.dbt_test_failures.length ? `<br>dbt: ${esc(d.dbt_test_failures.join(", "))}` : ""}</td><td class="${d.passed ? "ok" : "no"}">${d.passed ? "✓ pass" : "✕ fail"}</td></tr>`).join("") + "</tbody>";
  }

  // Torque
  $("#tbl-torque").innerHTML = `<thead><tr><th>Joint</th><th>Day</th><th class="n">Target Nm</th><th class="n">Mean</th><th class="n">Cpk</th><th class="n">NOK</th></tr></thead><tbody>` +
    torque.slice(0, 15).map((t) => `<tr><td>${esc(t.joint_id)}</td><td class="code">${esc(t.day)}</td><td class="n">${fmt(t.target_nm)}</td><td class="n">${fmt(t.mean_nm, 1)}</td><td class="n ${t.cpk < 1.33 ? "no" : ""}">${fmt(t.cpk, 2)}</td><td class="n">${(t.nok_rate * 100).toFixed(1)}%</td></tr>`).join("") + "</tbody>";
  $("#incidents").innerHTML = incidents.length ? incidents.slice(0, 8).map((i) => `<li><b>${esc(i.check_name)}</b> · ${esc(i.summary)}</li>`).join("") : "<li>No incidents: every check passed on the latest run.</li>";

  // Benchmarks
  if (bench) {
    $("#bench-sub").textContent = `${fmt(bench.rows)} events (one simulated week). Median of ${bench.runs_per_query} EXPLAIN ANALYZE runs, before and after the indexes in sql/indexes.sql.`;
    const mx = Math.max(...bench.queries.map((q) => q.before_ms));
    $("#tbl-bench").innerHTML = `<thead><tr><th>Query</th><th class="n">Before</th><th>Plan</th><th class="n">After</th><th>Plan</th><th class="n">Speed-up</th></tr></thead><tbody>` +
      bench.queries.map((q) => `<tr><td><b>${esc(q.query.replace(/_/g, " "))}</b><div class="code">${esc(q.description)}</div></td><td class="n">${fmt(q.before_ms, 2)} ms<span class="mbar" style="width:${(60 * q.before_ms / mx).toFixed(1)}px"></span></td><td class="code">${esc(q.before_scan)}</td><td class="n">${fmt(q.after_ms, 2)} ms</td><td class="code">${esc(q.after_scan)}</td><td class="n ok">${fmt(q.speedup, 1)}×</td></tr>`).join("") + "</tbody>";
  }

  // Batches
  $("#tbl-batches").innerHTML = `<thead><tr><th>Batch</th><th class="n">Files</th><th class="n">Lines</th><th class="n">Loaded</th><th class="n">Duplicates</th><th class="n">Quarantined</th></tr></thead><tbody>` +
    batches.map((b) => `<tr><td>#${b.batch_id}</td><td class="n">${fmt(b.files)}</td><td class="n">${fmt(b.lines_read)}</td><td class="n">${fmt(b.loaded)}</td><td class="n">${fmt(b.duplicates)}</td><td class="n">${fmt(b.quarantined)}</td></tr>`).join("") + "</tbody>";
})();
