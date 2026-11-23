// 분석 화면: 입력 방식 전환 → POST /api/analyses/ → 작업 ID로 상태를 주기적으로 조회 → 결과 표시
// 상단 지표·그래프는 Django ORM 집계(stats)를 그리고, 분석이 끝나면 /api/analyses/stats/ 로 다시 그립니다.
(function () {
  const form = document.getElementById("analysis-form");
  if (!form) return;

  const csrf = form.querySelector("[name=csrfmiddlewaretoken]").value;
  const inputType = form.querySelector("[name=input_type]");
  const fileInput = form.querySelector("[name=video]");
  const startBtn = document.getElementById("start-btn");
  const formError = document.getElementById("form-error");
  const preview = document.getElementById("preview");
  const dropText = document.getElementById("drop-text");

  const readJson = (id) => JSON.parse(document.getElementById(id).textContent);
  const RULES = readJson("rules-data");
  const EXPECTED = Object.fromEntries(readJson("actions-data"));

  const LABELS = {
    bend_return: "허리 굽혔다 펴기", leg_raise_lower: "다리 들었다 내리기", walk_turn_walk: "걷다가 방향 바꿔 걷기",
    drink_return: "마시고 제자리로", sit_stand: "앉았다 일어나기", wave: "손 흔들기",
    UNCERTAIN: "판단 보류", INSUFFICIENT_INPUT: "입력 부족",
  };
  const QUALITY = { good: "좋음", fair: "보통", poor: "나쁨" };
  const isDecided = (label) => label !== "UNCERTAIN" && label !== "INSUFFICIENT_INPUT";
  const pct = (v, digits = 1) => `${(v * 100).toFixed(digits)}%`;

  // ---- 색: CSS 변수에서 읽어 Chart.js와 맞춤 ----
  const css = getComputedStyle(document.documentElement);
  const C = Object.fromEntries(["--primary", "--primary2", "--muted", "--line2", "--ok", "--warn", "--bad", "--text", "--card"]
    .map((n) => [n.slice(2), css.getPropertyValue(n).trim()]));
  const hasChart = typeof Chart !== "undefined";
  if (hasChart) {
    Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
    Chart.defaults.color = C.muted;
    Chart.defaults.borderColor = C.line2;
  }

  // ---- 상단 지표 + 그래프 ----
  const charts = {};
  function setText(key, text) {
    const el = document.querySelector(`[data-k="${key}"]`);
    if (el) el.innerHTML = text;
  }
  function spark(canvas, data, suffix) {
    if (!hasChart) return;
    charts[canvas.dataset.spark]?.destroy();
    charts[canvas.dataset.spark] = new Chart(canvas, {
      type: "line",
      data: { labels: data.map((_, i) => i), datasets: [{ data, borderColor: C.primary, backgroundColor: C.primary + "30",
        fill: true, tension: 0.35, pointRadius: 0, borderWidth: 2 }] },
      options: { responsive: false, animation: false, plugins: { legend: { display: false }, tooltip: { enabled: false } },
        scales: { x: { display: false }, y: { display: false, beginAtZero: true, suggestedMax: suffix === "%" ? 100 : undefined } } },
    });
  }
  function renderStats(s) {
    setText("total", `${s.total}건`);
    setText("total-sub", `오늘 <span class="up">+${s.today}</span>`);
    setText("success", s.success_rate == null ? "-" : `${s.success_rate}%`);
    setText("success-sub", `${s.success} / ${s.finished} 완료`);
    setText("decided", s.decided_rate == null ? "-" : `${s.decided_rate}%`);
    setText("decided-sub", s.labelled
      ? `실제 동작 일치 ${s.matched}/${s.labelled}`
      : `판단 보류 ${s.undecided}건`);
    setText("seconds", s.avg_seconds == null ? "-" : `${Number(s.avg_seconds).toFixed(1)}초`);
    setText("seconds-sub", s.last_seconds == null ? "성공한 분석 기준" : `최근 ${Number(s.last_seconds).toFixed(1)}초`);
    document.querySelectorAll("canvas.spark").forEach((c) => {
      const key = c.dataset.spark;
      spark(c, s.spark[key] || [], key === "success" || key === "decided" ? "%" : "");
    });

    // 최근 Confidence 추이: 1등 확률 + 확정 기준선 + 무작위 기준선
    const trendCanvas = document.getElementById("trendChart");
    const distCanvas = document.getElementById("distChart");
    toggleEmpty(trendCanvas, !s.trend.length, "완료된 분석이 생기면 표시됩니다.");
    toggleEmpty(distCanvas, !s.predictions, "예측 결과가 생기면 표시됩니다.");
    document.getElementById("dist-sub").textContent = `사람별 예측 ${s.predictions}건`;
    if (!hasChart) return;

    const flat = (y) => s.trend.map(() => y * 100);
    charts.trend?.destroy();
    charts.trend = new Chart(trendCanvas, {
      data: { labels: s.trend.map((t) => t.label), datasets: [
        { type: "line", label: "1등 확률", data: s.trend.map((t) => +(t.confidence * 100).toFixed(1)), borderColor: C.primary,
          backgroundColor: C.primary + "26", fill: true, tension: 0.3, borderWidth: 2.5, pointRadius: 4,
          pointBackgroundColor: s.trend.map((t) => (t.decided ? C.primary : C.warn)) },
        { type: "line", label: "확정 기준", data: flat(RULES.confidence), borderColor: C.warn, borderDash: [2, 3], borderWidth: 1.5, pointRadius: 0 },
        { type: "line", label: "무작위", data: flat(RULES.chance), borderColor: C.muted, borderDash: [5, 4], borderWidth: 1.5, pointRadius: 0 },
      ] },
      options: { maintainAspectRatio: false, animation: false, plugins: { legend: { display: false },
          tooltip: { callbacks: { label: (ctx) => `${ctx.dataset.label} ${ctx.parsed.y}%` } } },
        scales: { y: { min: 0, suggestedMax: 40, ticks: { callback: (v) => `${v}%` } }, x: { grid: { display: false } } } },
    });

    const palette = [C.primary, C.primary2, C.ok, C.warn, "#60a5fa", "#22d3ee", C.muted + "99"]; // 6개 동작 + 판단 보류
    const d = s.distribution;
    const keep = d.values.map((v, i) => i).filter((i) => d.values[i] > 0);
    charts.dist?.destroy();
    charts.dist = new Chart(distCanvas, {
      type: "doughnut",
      data: { labels: keep.map((i) => d.labels[i]), datasets: [{ data: keep.map((i) => d.values[i]),
        backgroundColor: keep.map((i) => palette[i]), borderColor: C.card, borderWidth: 2 }] },
      options: { maintainAspectRatio: false, animation: false, cutout: "58%",
        plugins: { legend: { position: "right", labels: { color: C.text, boxWidth: 12 } } } },
    });
  }
  function toggleEmpty(canvas, empty, text) {
    let note = canvas.parentElement.querySelector(".chart-empty");
    if (empty && !note) {
      note = document.createElement("div");
      note.className = "chart-empty";
      note.textContent = text;
      canvas.parentElement.appendChild(note);
    }
    if (note) note.hidden = !empty;
    canvas.style.visibility = empty ? "hidden" : "visible";
  }
  async function refreshStats() {
    try {
      const res = await fetch("/api/analyses/stats/", { credentials: "same-origin" });
      if (res.ok) renderStats(await res.json());
    } catch (_) { /* 지표 갱신 실패는 분석 결과에 영향 없음 */ }
  }
  renderStats(readJson("stats-data"));

  // ---- 입력 방식 탭 ----
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t === tab));
      inputType.value = tab.dataset.input;
      document.querySelectorAll(".pane").forEach((p) => (p.hidden = p.dataset.pane !== tab.dataset.input));
    });
  });

  // ---- 업로드 미리보기 ----
  fileInput.addEventListener("change", () => {
    const file = fileInput.files[0];
    if (!file) return;
    dropText.textContent = `${file.name} (${(file.size / 1024 / 1024).toFixed(1)}MB) · 끌어다 놓아 교체`;
    preview.src = URL.createObjectURL(file);
    preview.hidden = false;
  });

  // ---- 끌어다 놓기: 놓은 파일을 file input에 넣고 change 이벤트로 미리보기 재사용 ----
  const drop = document.getElementById("drop");
  ["dragenter", "dragover"].forEach((name) =>
    drop.addEventListener(name, (event) => {
      event.preventDefault();
      drop.classList.add("dragging");
    })
  );
  ["dragleave", "drop"].forEach((name) =>
    drop.addEventListener(name, (event) => {
      event.preventDefault();
      drop.classList.remove("dragging");
    })
  );
  drop.addEventListener("drop", (event) => {
    const files = event.dataTransfer.files;
    if (!files.length) return;
    fileInput.files = files;
    fileInput.dispatchEvent(new Event("change"));
  });
  // 칸 밖에 잘못 놓아도 브라우저가 영상을 새 탭으로 열지 않게 막음
  ["dragover", "drop"].forEach((name) => window.addEventListener(name, (event) => event.preventDefault()));

  // ---- 분석 시작 ----
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    formError.hidden = true;
    if (inputType.value === "upload" && !fileInput.files.length) {
      return showFormError("분석할 영상을 선택해 주세요.");
    }
    const data = new FormData(form);
    if (inputType.value !== "upload") data.delete("video");
    if (inputType.value !== "ip_webcam") data.delete("camera_index");

    startBtn.disabled = true;
    startBtn.textContent = inputType.value === "upload" ? "업로드 중…" : "작업 등록 중…";
    try {
      const res = await fetch("/api/analyses/", {
        method: "POST", body: data, headers: { "X-CSRFToken": csrf }, credentials: "same-origin",
      });
      const body = await res.json();
      if (!res.ok) throw new Error(flattenErrors(body));
      startTracking(body.id, data.get("expected_action") || "");
    } catch (err) {
      showFormError(err.message || "요청에 실패했습니다.");
    } finally {
      startBtn.disabled = false;
      startBtn.textContent = "AI 분석 시작";
    }
  });

  function showFormError(msg) {
    formError.textContent = msg;
    formError.hidden = false;
  }

  function flattenErrors(body) {
    if (typeof body === "string") return body;
    if (body.detail) return body.detail;
    return Object.values(body).flat().join(" ");
  }

  // ---- 상태 조회 (HTTP Polling) ----
  let timer = null;
  function startTracking(id, expected) {
    clearTimeout(timer);
    document.getElementById("result-empty").hidden = true;
    document.getElementById("result-body").hidden = false;
    document.getElementById("people").innerHTML = "";
    document.getElementById("result-error").hidden = true;
    document.getElementById("job-metrics").hidden = true;
    document.getElementById("detail-link").href = `/analyses/${id}/`;
    setSteps("PENDING");
    document.getElementById("result-meta").textContent = `작업 #${id} 등록됨`;
    upsertHistory({ id, status: "PENDING", status_display: "대기", predictions: [], expected_action: expected });
    poll(id, 0);
  }

  async function poll(id, attempt) {
    try {
      const res = await fetch(`/api/analyses/${id}/status/`, { credentials: "same-origin" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const job = await res.json();
      render(job);
      upsertHistory(job);
      if (job.is_finished) return refreshStats();
    } catch (err) {
      document.getElementById("result-meta").textContent = `상태 조회 실패, 다시 시도 중… (${err.message})`;
    }
    const delay = Math.min(1000 + attempt * 250, 3000);
    timer = setTimeout(() => poll(id, attempt + 1), delay);
  }

  function setSteps(status) {
    const order = ["PENDING", "STARTED", "DONE"];
    const current = status === "SUCCESS" || status === "FAILURE" ? "DONE" : status;
    const idx = order.indexOf(current);
    document.querySelectorAll("#steps li").forEach((li, i) => {
      li.classList.toggle("done", i < idx || (i === idx && current === "DONE"));
      li.classList.toggle("active", i === idx && current !== "DONE");
      li.classList.toggle("failed", status === "FAILURE" && li.dataset.step === "DONE");
      if (li.dataset.step === "DONE") li.textContent = status === "FAILURE" ? "실패" : "완료";
      else if (li.dataset.step === "PENDING") li.textContent = i < idx ? "대기 ✓" : "대기";
      else li.textContent = i < idx || current === "DONE" ? "처리 중 ✓" : "처리 중";
    });
  }

  function render(job) {
    setSteps(job.status);
    document.getElementById("result-meta").textContent = `작업 #${job.id} · ${job.status_display}`;

    const errorBox = document.getElementById("result-error");
    if (job.status === "FAILURE") {
      errorBox.textContent = job.error_message || "분석에 실패했습니다.";
      errorBox.hidden = false;
    }
    const metrics = document.getElementById("job-metrics");
    if (job.is_finished) {
      const m = (key, text) => (metrics.querySelector(`[data-m="${key}"]`).textContent = text);
      m("people", `${job.predictions.length}명`);
      m("ai", job.processing_ms ? `${(job.processing_ms / 1000).toFixed(1)}초` : "-");
      m("total", job.total_seconds ? `${job.total_seconds}초` : "-");
      m("video", job.video_duration_sec ? `${Number(job.video_duration_sec).toFixed(1)}초` : "-");
      metrics.hidden = false;
    }
    const people = document.getElementById("people");
    if (job.status === "SUCCESS" && !job.predictions.length) {
      people.innerHTML = `<p class="muted">${escapeHtml(job.result_message || "영상에서 사람을 찾지 못했습니다.")}</p>`;
      return;
    }
    people.innerHTML = job.predictions.map((p) => personCard(p, job.expected_action)).join("");
  }

  function personCard(p, expected) {
    const decided = isDecided(p.action_label);
    const probs = Object.entries(p.probabilities || {}).sort((a, b) => b[1] - a[1]);
    const scale = Math.max(0.4, probs.length ? probs[0][1] : 0); // 막대 오른쪽 끝 = 40% (넘으면 1등 기준)
    const chanceLeft = (RULES.chance / scale) * 100;
    const bars = probs.map(([label, v], i) => `
      <div class="bar${i === 0 ? " first" : ""}"><span>${LABELS[label] || label}</span>
        <span class="track"><i style="width:${(v / scale) * 100}%"></i><span class="chance" style="left:${chanceLeft}%"></span></span>
        <b>${pct(v, 0)}</b></div>`).join("");

    const ratio = p.confidence / RULES.chance;
    const confOk = p.confidence >= RULES.confidence;
    const marginOk = p.margin >= RULES.margin;
    const mark = (ok) => (ok ? '<span class="y">✓</span>' : '<span class="n">✗</span>');

    const pills = [];
    if (decided) pills.push('<span class="pill">확정</span>');
    else pills.push(`<span class="pill w">${LABELS[p.action_label]}</span>`);
    if (expected) {
      if (p.action_label === expected) pills.push('<span class="pill p">실제 동작과 일치 ✓</span>');
      else if (decided) pills.push(`<span class="pill b">실제: ${escapeHtml(EXPECTED[expected] || expected)}</span>`);
    }
    const hint = !decided && p.raw_label ? `<div class="muted">가장 가까운 동작: ${LABELS[p.raw_label] || p.raw_label}</div>` : "";

    return `
      <article class="person ${decided ? "" : "uncertain"}">
        <div class="top">
          <div class="gauge" style="--pct:${(p.confidence * 100).toFixed(1)}">
            <div class="c"><b>${pct(p.confidence, 0)}</b><span>무작위 ${pct(RULES.chance)}의</span><em>${ratio.toFixed(1)}배</em></div>
          </div>
          <div>
            <div class="who-line">사람 #${p.track_id} · <span class="quality q-${p.input_quality}">입력 품질 ${QUALITY[p.input_quality] || "-"}</span>
              · Frame ${p.valid_frames}개 · Window ${p.window_count}개</div>
            <div class="action">${LABELS[p.action_label] || p.action_label}</div>
            ${pills.join("")}
            ${hint}
            <div class="checks">
              <div><span>1등 확률 ${pct(RULES.confidence, 0)} 이상</span><span>${pct(p.confidence)} ${mark(confOk)}</span></div>
              <div><span>2등과 차이 ${(RULES.margin * 100).toFixed(0)}%p 이상</span><span>${(p.margin * 100).toFixed(1)}%p ${mark(marginOk)}</span></div>
            </div>
          </div>
        </div>
        <div class="bars">${bars}</div>
        <div class="bars-note">점선: 무작위 ${pct(RULES.chance)}</div>
      </article>`;
  }

  // ---- 이력 표 ----
  function matchCell(job) {
    const exp = job.expected_action;
    if (!exp) return '<span class="muted">-</span>';
    if (job.status !== "SUCCESS" || !job.predictions?.length) return `<span class="muted">${escapeHtml(EXPECTED[exp] || exp)}</span>`;
    const labels = job.predictions.map((p) => p.action_label);
    if (labels.includes(exp)) return '<span class="m-match">✓ 일치</span>';
    if (labels.every((l) => !isDecided(l))) return '<span class="m-hold">보류</span>';
    return `<span class="m-mismatch">✗ ${escapeHtml(EXPECTED[exp] || exp)}</span>`;
  }

  function upsertHistory(job) {
    const tbody = document.querySelector("#history tbody");
    if (!tbody) return;
    tbody.querySelector("tr.empty")?.remove();
    let row = tbody.querySelector(`tr[data-id="${job.id}"]`);
    if (!row) {
      row = document.createElement("tr");
      row.dataset.id = job.id;
      row.dataset.expected = job.expected_action || "";
      const now = new Date();
      const two = (n) => String(n).padStart(2, "0");
      row.innerHTML = `<td>${job.id}</td><td>${two(now.getMonth() + 1)}/${two(now.getDate())} ${two(now.getHours())}:${two(now.getMinutes())}</td>
        <td>${inputType.value === "upload" ? "영상 업로드" : "IP Webcam"}</td><td></td><td></td><td><span class="muted">-</span></td><td></td>
        <td class="actions"><a href="/analyses/${job.id}/">상세</a> <button type="button" class="link danger del-job">삭제</button></td>`;
      tbody.prepend(row);
    }
    const cells = row.children;
    cells[3].innerHTML = `<span class="badge s-${job.status}">${job.status_display}</span>`;
    if (job.predictions && job.predictions.length) {
      cells[4].innerHTML = job.predictions.map((p) =>
        `<span class="chip${isDecided(p.action_label) ? "" : " hold"}">#${p.track_id} ${LABELS[p.action_label] || p.action_label}</span>`).join("");
      const top = job.predictions.reduce((a, b) => (b.confidence > a.confidence ? b : a));
      cells[5].innerHTML = `<span class="mini"><i style="width:${(top.confidence * 100).toFixed(0)}%"></i></span>${top.confidence.toFixed(2)}`;
    } else if (job.status === "FAILURE") {
      cells[4].innerHTML = `<span class="muted">${escapeHtml((job.error_message || "").slice(0, 40))}</span>`;
    } else if (job.status === "SUCCESS") {
      cells[4].innerHTML = `<span class="muted">${escapeHtml(job.result_message || "-")}</span>`;
    }
    cells[6].innerHTML = matchCell({ ...job, expected_action: job.expected_action ?? row.dataset.expected });
  }

  // ---- 이력 삭제 (한 건 / 전체) ----
  const historyBody = document.querySelector("#history tbody");
  function showEmptyIfNeeded() {
    if (historyBody && !historyBody.querySelector("tr[data-id]")) {
      historyBody.innerHTML = '<tr class="empty"><td colspan="8" class="muted">아직 분석 기록이 없습니다.</td></tr>';
    }
  }
  historyBody?.addEventListener("click", async (event) => {
    const btn = event.target.closest(".del-job");
    if (!btn) return;
    const row = btn.closest("tr");
    if (!confirm(`분석 #${row.dataset.id} 기록과 영상을 삭제할까요?`)) return;
    btn.disabled = true;
    const res = await fetch(`/api/analyses/${row.dataset.id}/`, {
      method: "DELETE", credentials: "same-origin", headers: { "X-CSRFToken": csrf },
    });
    if (res.ok || res.status === 404) {
      row.remove();
      showEmptyIfNeeded();
      refreshStats();
    } else {
      const body = await res.json().catch(() => ({}));
      alert(flattenErrors(body) || `삭제 실패 (HTTP ${res.status})`);
      btn.disabled = false;
    }
  });
  document.getElementById("clear-history")?.addEventListener("click", async () => {
    if (!confirm("내 분석 이력을 모두 삭제할까요? 업로드한 영상도 함께 지워집니다. (처리 중인 작업은 남습니다)")) return;
    const res = await fetch("/api/analyses/clear/", {
      method: "POST", credentials: "same-origin", headers: { "X-CSRFToken": csrf },
    });
    if (!res.ok) return alert(`삭제 실패 (HTTP ${res.status})`);
    const body = await res.json();
    body.deleted_ids.forEach((id) => historyBody.querySelector(`tr[data-id="${id}"]`)?.remove());
    showEmptyIfNeeded();
    refreshStats();
  });

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
})();
