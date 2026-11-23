// Django ORM 집계 결과(json_script)로 Chart.js 차트를 그립니다. FastAPI는 DB를 조회하지 않습니다.
(function () {
  if (typeof Chart === "undefined") {
    document.querySelectorAll("canvas").forEach((c) => c.insertAdjacentHTML("afterend", '<p class="muted">Chart.js를 불러오지 못했습니다.</p>'));
    return;
  }
  const read = (id) => JSON.parse(document.getElementById(id).textContent);
  const actions = read("action-data");
  const statuses = read("status-data");
  const inputs = read("input-data");
  const css = getComputedStyle(document.documentElement);
  const v = (name, fallback) => css.getPropertyValue(name).trim() || fallback;
  const C = { primary: v("--primary", "#8b5cf6"), primary2: v("--primary2", "#c4b5fd"), muted: v("--muted", "#9a9fbd"),
    line: v("--line2", "#272b45"), ok: v("--ok", "#34d399"), warn: v("--warn", "#fbbf24"), bad: v("--bad", "#fb7185"),
    text: v("--text", "#e8e9f3"), card: v("--card", "#181c2e") };
  Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
  Chart.defaults.color = C.muted;
  Chart.defaults.borderColor = C.line;

  const STATUS_COLORS = { PENDING: C.muted, STARTED: C.warn, SUCCESS: C.ok, FAILURE: C.bad };

  new Chart(document.getElementById("actionChart"), {
    type: "bar",
    data: { labels: actions.labels, datasets: [{ label: "예측 건수", data: actions.values,
      backgroundColor: actions.labels.map((_, i) => (i === actions.labels.length - 1 ? C.muted + "88" : C.primary)), borderRadius: 6 }] },
    options: { maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, ticks: { precision: 0 } } } },
  });

  new Chart(document.getElementById("statusChart"), {
    type: "doughnut",
    data: { labels: statuses.labels, datasets: [{ data: statuses.values, backgroundColor: statuses.keys.map((k) => STATUS_COLORS[k]), borderColor: C.card, borderWidth: 2 }] },
    options: { maintainAspectRatio: false, cutout: "58%", plugins: { legend: { position: "bottom", labels: { color: C.text } } } },
  });

  new Chart(document.getElementById("inputChart"), {
    type: "bar",
    data: { labels: inputs.labels, datasets: [
      { label: "작업 수", data: inputs.values, backgroundColor: C.primary, borderRadius: 6, yAxisID: "y" },
      { label: "평균 AI 처리 시간(초)", data: inputs.avg_seconds, backgroundColor: C.warn, borderRadius: 6, yAxisID: "y1" },
    ] },
    options: { maintainAspectRatio: false, indexAxis: "x", scales: { y: { beginAtZero: true, ticks: { precision: 0 }, position: "left" },
      y1: { beginAtZero: true, position: "right", grid: { drawOnChartArea: false } } } },
  });
})();
