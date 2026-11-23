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
  Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
  Chart.defaults.color = getComputedStyle(document.body).getPropertyValue("--muted").trim() || "#667";

  const STATUS_COLORS = { PENDING: "#9aa4b2", STARTED: "#e0a526", SUCCESS: "#2e9e6a", FAILURE: "#d6455d" };

  new Chart(document.getElementById("actionChart"), {
    type: "bar",
    data: { labels: actions.labels, datasets: [{ label: "예측 건수", data: actions.values,
      backgroundColor: actions.labels.map((_, i) => (i === actions.labels.length - 1 ? "#b8bfca" : "#2f6fde")), borderRadius: 6 }] },
    options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, ticks: { precision: 0 } } } },
  });

  new Chart(document.getElementById("statusChart"), {
    type: "doughnut",
    data: { labels: statuses.labels, datasets: [{ data: statuses.values, backgroundColor: statuses.keys.map((k) => STATUS_COLORS[k]) }] },
    options: { plugins: { legend: { position: "bottom" } } },
  });

  new Chart(document.getElementById("inputChart"), {
    type: "bar",
    data: { labels: inputs.labels, datasets: [
      { label: "작업 수", data: inputs.values, backgroundColor: "#2f6fde", borderRadius: 6, yAxisID: "y" },
      { label: "평균 AI 처리 시간(초)", data: inputs.avg_seconds, backgroundColor: "#e0a526", borderRadius: 6, yAxisID: "y1" },
    ] },
    options: { indexAxis: "x", scales: { y: { beginAtZero: true, ticks: { precision: 0 }, position: "left" },
      y1: { beginAtZero: true, position: "right", grid: { drawOnChartArea: false } } } },
  });
})();
