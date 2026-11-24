// 분석 화면: 입력 방식 전환 → POST /api/analyses/ → 작업 ID로 상태를 주기적으로 조회 → 결과 표시
// 상단 지표·그래프는 지금 보고 있는 영상 한 건의 데이터(구간별 확률, 구간 일치율, 관절 인식)를 그립니다.
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

  // ---- 색: CSS 변수에서 읽어 Chart.js와 맞춤 (다크/라이트 전환 때 다시 읽음) ----
  const C = {};
  const hasChart = typeof Chart !== "undefined";
  function readColors() {
    const css = getComputedStyle(document.documentElement);
    ["--primary", "--primary2", "--muted", "--line2", "--ok", "--warn", "--bad", "--text", "--card"]
      .forEach((n) => (C[n.slice(2)] = css.getPropertyValue(n).trim()));
    C.soft = css.getPropertyValue("--bar-soft").trim() || C.primary2; // 라이트 모드에서 1등 색과 구분되는 연보라
    if (hasChart) {
      Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
      Chart.defaults.color = C.muted;
      Chart.defaults.borderColor = C.line2;
    }
  }
  readColors();

  // ---- 지금 보고 있는 영상 한 건: 상단 지표 4개 + 그래프 2개 ----
  // 데이터는 그 작업의 status API 응답(사람별 details: 구간별 확률, 일치율, 관절 인식)에서 바로 가져옵니다.
  const ACTION_KEYS = Object.keys(EXPECTED);
  const lineColor = (i) => [C.primary, C.soft, "#60a5fa", C.warn, C.ok, "#22d3ee"][i];
  const charts = {};
  let focusJob = null;
  let focusTrack = null;

  function setText(key, html) {
    const el = document.querySelector(`[data-k="${key}"]`);
    if (el) el.innerHTML = html;
  }
  function setRing(key, ratio, color) {
    const el = document.querySelector(`[data-ring="${key}"]`);
    if (!el) return;
    el.style.setProperty("--pct", ratio == null ? 0 : Math.max(0, Math.min(1, ratio)) * 100);
    el.style.setProperty("--col", color || C.primary);
  }
  function chartEmpty(canvas, text) {
    let note = canvas.parentElement.querySelector(".chart-empty");
    if (!note) {
      note = document.createElement("div");
      note.className = "chart-empty";
      canvas.parentElement.appendChild(note);
    }
    note.textContent = text || "";
    note.hidden = !text;
    canvas.style.visibility = text ? "hidden" : "visible";
  }

  function showFocus(job, trackId) {
    focusJob = job;
    const people = (job.predictions || []).filter((p) => p.action_label !== "INSUFFICIENT_INPUT");
    const person = people.find((p) => p.track_id === trackId) || people[0] || (job.predictions || [])[0];
    focusTrack = person ? person.track_id : null;
    document.querySelectorAll("#history tr[data-id]").forEach((tr) => tr.classList.toggle("selected", Number(tr.dataset.id) === job.id));
    document.querySelectorAll("#people .person").forEach((el) => el.classList.toggle("selected", Number(el.dataset.track) === focusTrack));

    const name = job.title || job.video_name || job.input_type_display || "";
    const who = person && (job.predictions || []).length > 1 ? ` · 사람 #${person.track_id} (카드를 눌러 바꾸기)` : "";
    document.getElementById("focus-text").innerHTML =
      `지금 보고 있는 분석: <b>#${job.user_seq ?? job.id}</b> ${escapeHtml(name)}${who}`;

    const d = (person && person.details) || {};
    const meta = job.video_meta || {};
    if (!person || job.status !== "SUCCESS") {
      ["conf", "margin", "agree", "pose"].forEach((k) => { setText(k, "-"); setRing(k, 0); });
      // 이전 영상의 설명 문구가 남지 않도록 모두 비움
      const why = job.status === "FAILURE" ? "분석 실패" : job.is_finished ? "사람을 찾지 못함" : "분석 중";
      ["conf-sub", "margin-sub", "agree-sub", "pose-sub"].forEach((k) => setText(k, why));
      drawTimeline(null);
      drawCompare(null);
      return;
    }
    const decided = isDecided(person.action_label);
    setText("conf", pct(person.confidence));
    setText("conf-sub", `무작위 ${pct(RULES.chance)}의 <b>${(person.confidence / RULES.chance).toFixed(1)}배</b>`);
    setRing("conf", person.confidence / 0.5, decided ? C.primary : C.warn);

    const marginOk = person.margin >= RULES.margin;
    setText("margin", `${(person.margin * 100).toFixed(1)}%p`);
    setText("margin-sub", `확정 기준 ${(RULES.margin * 100).toFixed(0)}%p ${marginOk ? '<span class="up">✓ 넘음</span>' : '<span class="down">✗ 못 넘음</span>'}`);
    setRing("margin", person.margin / 0.2, marginOk ? C.ok : C.bad);

    if (d.window_agreement != null) {
      const total = person.window_count || (d.timeline || []).length;
      const same = Math.round(d.window_agreement * total);
      setText("agree", `${Math.round(d.window_agreement * 100)}%`);
      setText("agree-sub", `${total}개 구간 중 ${same}개가 1등 동작과 같음`);
      setRing("agree", d.window_agreement, d.window_agreement >= 0.5 ? C.ok : C.warn);
    } else {
      setText("agree", "-");
      setText("agree-sub", "이전 분석이라 구간 데이터 없음");
      setRing("agree", 0);
    }

    if (d.mean_keypoint_conf != null) {
      const detected = meta.frame_count ? d.detected_frames / meta.frame_count : null;
      setText("pose", d.mean_keypoint_conf.toFixed(2));
      const parts = [];
      if (detected != null) parts.push(`사람 검출 ${Math.round(Math.min(detected, 1) * 100)}%`);
      parts.push(`관절 보간 ${d.interpolated_joints || 0}개`);
      setText("pose-sub", parts.join(" · "));
      setRing("pose", d.mean_keypoint_conf, person.input_quality === "good" ? C.ok : person.input_quality === "fair" ? C.warn : C.bad);
    } else {
      setText("pose", QUALITY[person.input_quality] || "-");
      setText("pose-sub", `Frame ${person.valid_frames}개`);
      setRing("pose", person.input_quality === "good" ? 0.9 : person.input_quality === "fair" ? 0.6 : 0.3);
    }
    drawTimeline(person);
    drawCompare(person);
  }

  function drawTimeline(person) {
    const canvas = document.getElementById("timelineChart");
    const timeline = (person && person.details && person.details.timeline) || [];
    charts.timeline?.destroy();
    document.getElementById("timeline-sub").textContent = "2초 구간을 0.5초씩 옮기며 예측";
    if (!person) return chartEmpty(canvas, "분석 결과가 생기면 표시됩니다.");
    if (!timeline.length) return chartEmpty(canvas, "이 분석에는 구간 데이터가 없습니다. 새로 분석하면 표시됩니다.");
    chartEmpty(canvas, "");
    document.getElementById("timeline-sub").textContent =
      timeline.length > 1 ? `2초 구간 ${timeline.length}개 (0.5초씩 이동)` : "영상이 짧아 전체를 한 구간으로 예측";
    const top = person.raw_label;
    const order = [top, ...ACTION_KEYS.filter((k) => k !== top)];
    if (!hasChart) return;
    charts.timeline = new Chart(canvas, {
      type: "line",
      data: {
        labels: timeline.map((w) => `${w.start_sec.toFixed(1)}~${w.end_sec.toFixed(1)}초`),
        datasets: [
          ...order.map((key) => {
            const color = lineColor(ACTION_KEYS.indexOf(key));
            const main = key === top;
            return { label: LABELS[key], data: timeline.map((w) => +((w.probabilities[key] || 0) * 100).toFixed(1)),
              borderColor: color, backgroundColor: main ? color + "22" : color, fill: main, tension: 0.3,
              borderWidth: main ? 3 : 1.5, pointRadius: main ? 4 : 2, order: main ? 0 : 1 };
          }),
          { label: `확정 기준 ${pct(RULES.confidence, 0)}`, data: timeline.map(() => RULES.confidence * 100), borderColor: C.muted,
            borderDash: [4, 4], borderWidth: 1.2, pointRadius: 0, fill: false },
        ],
      },
      options: { maintainAspectRatio: false, animation: false, interaction: { mode: "index", intersect: false },
        plugins: { legend: { position: "bottom", labels: { boxWidth: 10, color: C.text, font: { size: 11 } } },
          tooltip: { callbacks: { label: (ctx) => `${ctx.dataset.label} ${ctx.parsed.y}%` } } },
        scales: { y: { min: 0, suggestedMax: 50, ticks: { callback: (v) => `${v}%` } }, x: { grid: { display: false } } } },
    });
  }

  function drawCompare(person) {
    const canvas = document.getElementById("compareChart");
    const d = (person && person.details) || {};
    charts.compare?.destroy();
    if (!person) return chartEmpty(canvas, "분석 결과가 생기면 표시됩니다.");
    if (!d.whole_probabilities) return chartEmpty(canvas, "이 분석에는 비교 데이터가 없습니다. 새로 분석하면 표시됩니다.");
    chartEmpty(canvas, "");
    if (!hasChart) return;
    const keys = [...ACTION_KEYS].sort((a, b) => (person.probabilities[b] || 0) - (person.probabilities[a] || 0));
    const row = (src) => keys.map((k) => +(((src || {})[k] || 0) * 100).toFixed(1));
    charts.compare = new Chart(canvas, {
      type: "bar",
      data: { labels: keys.map((k) => LABELS[k]), datasets: [
        { label: "전체 구간(학습과 같은 방식)", data: row(d.whole_probabilities), backgroundColor: C.soft, borderRadius: 3 },
        { label: "2초 구간 평균", data: row(d.window_mean_probabilities), backgroundColor: "#60a5fa", borderRadius: 3 },
        { label: "최종", data: row(person.probabilities), backgroundColor: C.primary, borderRadius: 3 },
      ] },
      options: { indexAxis: "y", maintainAspectRatio: false, animation: false,
        plugins: { legend: { position: "bottom", labels: { boxWidth: 10, color: C.text, font: { size: 11 } } },
          tooltip: { callbacks: { label: (ctx) => `${ctx.dataset.label} ${ctx.parsed.x}%` } } },
        scales: { x: { min: 0, suggestedMax: 40, ticks: { callback: (v) => `${v}%` } }, y: { grid: { display: false }, ticks: { color: C.text } } } },
    });
  }

  // 이력 행을 누르면 그 작업을 위 결과 카드·지표·그래프에 표시
  async function loadJob(id) {
    try {
      const res = await fetch(`/api/analyses/${id}/status/`, { credentials: "same-origin" });
      if (!res.ok) return;
      const job = await res.json();
      activeId = id;
      document.getElementById("result-empty").hidden = true;
      document.getElementById("result-body").hidden = false;
      document.getElementById("result-error").hidden = true;
      document.getElementById("detail-link").href = `/analyses/${id}/`;
      render(job);
      if (!job.is_finished && !timers[id]) poll(id, 0);
    } catch (_) { /* 무시: 다음 클릭에서 다시 시도 */ }
  }
  document.getElementById("people").addEventListener("click", (event) => {
    const card = event.target.closest(".person");
    if (card && focusJob) showFocus(focusJob, Number(card.dataset.track));
  });

  // ---- 최근 분석 이력 접기/펴기 (브라우저에 상태 기억) ----
  const foldBtn = document.getElementById("fold-history");
  const historyWrap = document.getElementById("history-body");
  function setFold(open) {
    historyWrap.hidden = !open;
    foldBtn.setAttribute("aria-expanded", String(open));
    foldBtn.classList.toggle("closed", !open);
    try { localStorage.setItem("historyOpen", open ? "1" : "0"); } catch (_) { /* 저장 못 해도 동작 */ }
  }
  foldBtn.addEventListener("click", () => setFold(historyWrap.hidden));
  try { if (localStorage.getItem("historyOpen") === "0") setFold(false); } catch (_) { /* 기본: 펼침 */ }
  function updateCount() {
    document.getElementById("history-count").textContent = document.querySelectorAll("#history tr[data-id]").length;
  }

  // ---- 입력 방식 탭 ----
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t === tab));
      inputType.value = tab.dataset.input;
      document.querySelectorAll(".pane").forEach((p) => (p.hidden = p.dataset.pane !== tab.dataset.input));
      if (tab.dataset.input === "ip_webcam") startPreview();
      else stopPreview();
    });
  });

  // ---- IP Webcam 미리보기: 서버가 대신 받아 주는 사진을 짧은 간격으로 계속 바꿔 보여 줌 ----
  // (카메라 주소는 브라우저에 노출하지 않고, 영상 스트림을 계속 붙잡지 않음)
  const cam = document.getElementById("cam");
  const camLive = document.getElementById("cam-live");
  const camRecorded = document.getElementById("cam-recorded");
  const camMsg = document.getElementById("cam-msg");
  const camTag = document.getElementById("cam-tag");
  const camSelect = form.querySelector("[name=camera_index]");
  let previewOn = false;
  let previewTimer = null;
  let countdownTimer = null;

  function camLabel(text, recording) {
    if (!camTag) return;
    camTag.textContent = text;
    camTag.classList.toggle("rec", !!recording);
  }
  function nextFrame() {
    if (!previewOn) return;
    camLive.src = `/cameras/${camSelect ? camSelect.value : 0}/snapshot.jpg?t=${Date.now()}`;
  }
  function startPreview() {
    if (!cam) return;
    clearTimeout(previewTimer);
    camRecorded.pause?.();
    camRecorded.hidden = true;
    camLive.hidden = false;
    if (!countdownTimer) camLabel("미리보기");
    camMsg.textContent = "카메라에 연결하는 중…";
    camMsg.hidden = false;
    previewOn = true;
    nextFrame();
  }
  function stopPreview() {
    previewOn = false;
    clearTimeout(previewTimer);
  }
  if (cam) {
    camLive.addEventListener("load", () => {
      camMsg.hidden = true;
      if (previewOn) previewTimer = setTimeout(nextFrame, 150);
    });
    camLive.addEventListener("error", () => {
      camMsg.textContent = "카메라 화면을 받지 못했습니다. 휴대폰 IP Webcam 앱에서 Start server를 눌렀는지, 같은 Wi-Fi인지 확인해 주세요. (2초 뒤 다시 시도)";
      camMsg.hidden = false;
      if (previewOn) previewTimer = setTimeout(nextFrame, 2000);
    });
    camSelect?.addEventListener("change", startPreview);
    camTag.addEventListener("click", () => { if (!camRecorded.hidden) startPreview(); });
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) stopPreview();
      else if (inputType.value === "ip_webcam" && camRecorded.hidden) startPreview();
    });
  }
  // 분석 중 표시: 서버가 녹화를 시작하면(STARTED) 남은 초를 보여 주고, 끝나면 녹화된 영상을 재생
  function updateCam(job) {
    if (!cam || job.input_type !== "ip_webcam" || inputType.value !== "ip_webcam") return;
    if (job.status === "STARTED" && !countdownTimer && !job.is_finished) {
      let left = Number(cam.dataset.seconds) || 8;
      camLabel(`녹화 중 ${left}초`, true);
      countdownTimer = setInterval(() => {
        left -= 1;
        if (left > 0) camLabel(`녹화 중 ${left}초`, true);
        else { clearInterval(countdownTimer); countdownTimer = -1; camLabel("AI 분석 중…"); }
      }, 1000);
    }
    if (job.is_finished) {
      if (countdownTimer > 0) clearInterval(countdownTimer);
      countdownTimer = null;
      if (job.video_url) {
        stopPreview();
        camLive.hidden = true;
        camMsg.hidden = true;
        camRecorded.src = job.video_url;
        camRecorded.hidden = false;
        camLabel("녹화된 영상 · 눌러서 미리보기로");
      } else {
        camLabel("미리보기");
      }
    }
  }

  // ---- 업로드 미리보기 (여러 개면 첫 영상을 보여 주고 이름을 나열) ----
  const MAX_FILES = 10;
  fileInput.addEventListener("change", () => {
    const files = [...fileInput.files];
    const file = files[0];
    if (!file) return;
    const mb = (f) => `${(f.size / 1024 / 1024).toFixed(1)}MB`;
    if (files.length === 1) {
      dropText.textContent = `${file.name} (${mb(file)}) · 끌어다 놓아 교체`;
    } else {
      const names = files.slice(0, 4).map((f) => f.name).join(", ") + (files.length > 4 ? ` 외 ${files.length - 4}개` : "");
      dropText.textContent = `영상 ${files.length}개: ${names} · 각각 따로 분석해요` + (files.length > MAX_FILES ? ` (한 번에 ${MAX_FILES}개까지)` : "");
    }
    if (preview.src.startsWith("blob:")) URL.revokeObjectURL(preview.src);
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

  // ---- 분석 시작: 영상 여러 개면 각각 작업을 만들고, 첫 작업을 위 결과 카드에 보여 줌 ----
  async function submitJob(data) {
    const res = await fetch("/api/analyses/", {
      method: "POST", body: data, headers: { "X-CSRFToken": csrf }, credentials: "same-origin",
    });
    const body = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
    if (!res.ok) throw new Error(flattenErrors(body));
    return body;
  }
  const stem = (name) => name.replace(/\.[^.]+$/, "");

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    formError.hidden = true;
    const files = [...fileInput.files];
    if (inputType.value === "upload" && !files.length) {
      return showFormError("분석할 영상을 선택해 주세요.");
    }
    if (inputType.value === "upload" && files.length > MAX_FILES) {
      return showFormError(`한 번에 ${MAX_FILES}개까지 올릴 수 있습니다.`);
    }
    const base = new FormData(form);
    base.delete("video");
    if (inputType.value !== "ip_webcam") base.delete("camera_index");
    const title = (base.get("title") || "").trim();
    const expected = base.get("expected_action") || "";

    startBtn.disabled = true;
    const errors = [];
    try {
      if (inputType.value !== "upload") {
        startBtn.textContent = "작업 등록 중…";
        const body = await submitJob(base);
        startTracking(body.id, body.user_seq, expected, title);
      } else {
        let first = true;
        for (const [i, file] of files.entries()) {
          startBtn.textContent = files.length > 1 ? `업로드 중… (${i + 1}/${files.length})` : "업로드 중…";
          const data = new FormData();
          for (const [k, v] of base.entries()) data.append(k, v);
          data.set("video", file);
          // 여러 개일 때 제목: 입력한 제목 + 번호, 비어 있으면 파일 이름
          const jobTitle = files.length > 1 ? (title ? `${title} (${i + 1})` : stem(file.name)).slice(0, 100) : title;
          data.set("title", jobTitle);
          try {
            const body = await submitJob(data);
            startTracking(body.id, body.user_seq, expected, jobTitle, first);
            first = false;
          } catch (err) {
            errors.push(`${file.name}: ${err.message}`);
          }
        }
      }
    } catch (err) {
      errors.push(err.message || "요청에 실패했습니다.");
    } finally {
      startBtn.disabled = false;
      startBtn.textContent = "AI 분석 시작";
    }
    if (errors.length) showFormError(errors.join(" / "));
  });

  // ---- 한 번 클릭 샘플 영상: 저장소에 넣어 둔 S03 영상을 받아 업로드와 똑같이 분석 ----
  document.getElementById("samples")?.addEventListener("click", async (event) => {
    const btn = event.target.closest(".sample-btn");
    if (!btn) return;
    formError.hidden = true;
    btn.disabled = true;
    try {
      const res = await fetch(btn.dataset.src, { credentials: "same-origin" });
      if (!res.ok) throw new Error(`샘플 영상을 불러오지 못했습니다 (HTTP ${res.status})`);
      const name = btn.dataset.src.split("/").pop();
      const file = new File([await res.blob()], name, { type: "video/mp4" });
      preview.src = btn.dataset.src;
      preview.hidden = false;
      dropText.textContent = `샘플: ${btn.dataset.label} (${name})`;
      const data = new FormData();
      data.set("input_type", "upload");
      data.set("video", file);
      data.set("title", `샘플 · ${btn.dataset.label}`);
      data.set("expected_action", btn.dataset.action);
      const body = await submitJob(data);
      startTracking(body.id, body.user_seq, btn.dataset.action, `샘플 · ${btn.dataset.label}`);
    } catch (err) {
      showFormError(err.message || "샘플 분석을 시작하지 못했습니다.");
    } finally {
      btn.disabled = false;
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
  // 여러 작업을 동시에 지켜볼 수 있게 작업마다 따로 조회합니다. 위 결과 카드에는 activeId 작업만 그립니다.
  let activeId = null;
  const timers = {};
  const watching = new Set(); // 이 화면에서 등록해 끝나기를 기다리는 작업 (끝나면 알림)
  function startTracking(id, seq, expected, title, focus = true) {
    watching.add(id);
    upsertHistory({ id, user_seq: seq, title: title || "", status: "PENDING", status_display: "대기", predictions: [], expected_action: expected });
    if (focus) {
      activeId = id;
      document.getElementById("result-empty").hidden = true;
      document.getElementById("result-body").hidden = false;
      document.getElementById("people").innerHTML = "";
      document.getElementById("result-error").hidden = true;
      document.getElementById("job-metrics").hidden = true;
      document.getElementById("detail-link").href = `/analyses/${id}/`;
      setSteps("PENDING");
      if (inputType.value === "ip_webcam") startPreview();
      document.getElementById("result-meta").textContent = `작업 #${seq ?? id} 등록됨`;
    }
    poll(id, 0);
  }

  async function poll(id, attempt) {
    clearTimeout(timers[id]);
    try {
      const res = await fetch(`/api/analyses/${id}/status/`, { credentials: "same-origin" });
      if (res.status === 404) { delete timers[id]; watching.delete(id); return; } // 그 사이 삭제됨
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const job = await res.json();
      if (id === activeId) render(job);
      upsertHistory(job);
      if (job.is_finished) {
        delete timers[id];
        if (watching.delete(id)) notifyDone(job);
        return;
      }
    } catch (err) {
      if (id === activeId) document.getElementById("result-meta").textContent = `상태 조회 실패, 다시 시도 중… (${err.message})`;
    }
    const delay = Math.min(1000 + attempt * 250, 3000);
    timers[id] = setTimeout(() => poll(id, attempt + 1), delay);
  }

  // ---- 분석 완료 알림: 소리 + (다른 탭에 있을 때) 브라우저 알림 + 탭 제목 표시 ----
  // 켜고 끄는 상태는 브라우저에 기억합니다. 브라우저 알림은 localhost 또는 HTTPS 주소에서만 됩니다.
  const notifyBtn = document.getElementById("notify-btn");
  const baseTitle = document.title;
  let audioCtx = null;
  let notifyOn = false;
  try { notifyOn = localStorage.getItem("notify") === "1"; } catch (_) { /* 기본: 끔 */ }
  function paintNotify() {
    if (!notifyBtn) return;
    notifyBtn.textContent = notifyOn ? "🔔 완료 알림 켜짐" : "🔕 완료 알림 꺼짐";
    notifyBtn.classList.toggle("on", notifyOn);
  }
  function beep(ok) {
    try {
      audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
      const notes = ok ? [660, 880] : [330, 247];
      notes.forEach((freq, i) => {
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        const at = audioCtx.currentTime + i * 0.16;
        osc.frequency.value = freq;
        osc.type = "sine";
        gain.gain.setValueAtTime(0.0001, at);
        gain.gain.exponentialRampToValueAtTime(0.2, at + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.0001, at + 0.15);
        osc.connect(gain).connect(audioCtx.destination);
        osc.start(at);
        osc.stop(at + 0.16);
      });
    } catch (_) { /* 소리를 못 내는 브라우저 */ }
  }
  notifyBtn?.addEventListener("click", async () => {
    notifyOn = !notifyOn;
    try { localStorage.setItem("notify", notifyOn ? "1" : "0"); } catch (_) { /* 이번 화면에서만 적용 */ }
    paintNotify();
    if (!notifyOn) return;
    beep(true); // 버튼을 누를 때 한 번 울려 소리 재생을 허용받음
    if ("Notification" in window && Notification.permission === "default") {
      try { await Notification.requestPermission(); } catch (_) { /* 거부해도 소리는 울림 */ }
    }
  });
  paintNotify();
  function notifyDone(job) {
    const ok = job.status === "SUCCESS";
    const top = (job.predictions || []).reduce((a, b) => (!a || b.confidence > a.confidence ? b : a), null);
    const name = job.title || job.video_name || "";
    const body = ok ? (top ? `${LABELS[top.action_label] || top.action_label} (${pct(top.confidence, 0)})` : (job.result_message || "사람을 찾지 못했습니다."))
      : (job.error_message || "분석에 실패했습니다.");
    if (document.hidden) document.title = `${ok ? "✓ 완료" : "✗ 실패"} · ${baseTitle}`;
    if (!notifyOn) return;
    beep(ok);
    if (document.hidden && "Notification" in window && Notification.permission === "granted") {
      try {
        const n = new Notification(`분석 #${job.user_seq ?? job.id} ${ok ? "완료" : "실패"}${name ? ` · ${name}` : ""}`, { body, tag: `job-${job.id}` });
        n.onclick = () => { window.focus(); loadJob(job.id); n.close(); };
      } catch (_) { /* 알림을 못 띄우는 환경 */ }
    }
  }
  document.addEventListener("visibilitychange", () => { if (!document.hidden) document.title = baseTitle; });

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
    updateCam(job);
    document.getElementById("result-meta").textContent = `작업 #${job.user_seq ?? job.id} · ${job.status_display}`;

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
    showResultVideo(job);
    const people = document.getElementById("people");
    if (job.status === "SUCCESS" && !job.predictions.length) {
      people.innerHTML = `<p class="muted">${escapeHtml(job.result_message || "영상에서 사람을 찾지 못했습니다.")}</p>`;
    } else {
      people.innerHTML = job.predictions.map((p) => personCard(p, job.expected_action, job.predictions.length > 1)).join("");
    }
    if (job.is_finished) showFocus(job, focusJob && focusJob.id === job.id ? focusTrack : null);
  }

  // ---- 결과 영상 + 관절·사람 번호 표시 (좌표는 /api/analyses/{id}/pose/) ----
  const resultBox = document.getElementById("result-video-box");
  const resultVideo = document.getElementById("result-video");
  const poseNote = document.getElementById("pose-note");
  const overlay = window.PoseOverlay && resultVideo ? window.PoseOverlay.attach(resultVideo, document.getElementById("pose-toggle")) : null;
  resultVideo?.addEventListener("posedata", (event) => {
    poseNote.textContent = event.detail ? "" : "(이 분석에는 관절 좌표가 없습니다. 새로 분석하면 표시돼요)";
  });
  function showResultVideo(job) {
    if (!resultBox) return;
    const show = job.status === "SUCCESS" && !!job.video_url;
    resultBox.hidden = !show;
    if (!show) {
      resultVideo.pause();
      return;
    }
    if (resultVideo.dataset.job !== String(job.id)) {
      resultVideo.dataset.job = job.id;
      resultVideo.src = job.video_url;
      poseNote.textContent = "";
      overlay?.load(`/api/analyses/${job.id}/pose/`);
    }
  }

  function personCard(p, expected, many) {
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
      <article class="person ${decided ? "" : "uncertain"}${many ? " clickable" : ""}" data-track="${p.track_id}">
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
      row.dataset.seq = job.user_seq ?? job.id;
      row.dataset.expected = job.expected_action || "";
      row.className = "pick";
      const now = new Date();
      const two = (n) => String(n).padStart(2, "0");
      row.innerHTML = `<td class="sel"><input type="checkbox" class="row-check" aria-label="분석 ${row.dataset.seq} 선택"></td>
        <td>${row.dataset.seq}</td><td class="title-cell"></td>
        <td>${two(now.getMonth() + 1)}/${two(now.getDate())} ${two(now.getHours())}:${two(now.getMinutes())}</td>
        <td>${inputType.value === "upload" ? "영상 업로드" : "IP Webcam"}</td><td></td><td></td><td><span class="muted">-</span></td><td></td>
        <td class="actions"><a href="/analyses/${job.id}/">상세</a> <button type="button" class="link danger del-job">삭제</button></td>`;
      row.children[2].innerHTML = titleButton(job.title || "");
      tbody.prepend(row);
      updateCount();
    }
    row.dataset.status = job.status;
    const cells = row.children;
    const titleBtn = cells[2].querySelector(".title-edit");
    if (titleBtn && job.title != null && titleBtn.dataset.title !== job.title) cells[2].innerHTML = titleButton(job.title);
    cells[5].innerHTML = `<span class="badge s-${job.status}">${job.status_display}</span>`;
    if (job.predictions && job.predictions.length) {
      cells[6].innerHTML = job.predictions.map((p) =>
        `<span class="chip${isDecided(p.action_label) ? "" : " hold"}">#${p.track_id} ${LABELS[p.action_label] || p.action_label}</span>`).join("");
      const top = job.predictions.reduce((a, b) => (b.confidence > a.confidence ? b : a));
      cells[7].innerHTML = `<span class="mini"><i style="width:${(top.confidence * 100).toFixed(0)}%"></i></span>${top.confidence.toFixed(2)}`;
    } else if (job.status === "FAILURE") {
      cells[6].innerHTML = `<span class="muted">${escapeHtml((job.error_message || "").slice(0, 40))}</span>`;
    } else if (job.status === "SUCCESS") {
      cells[6].innerHTML = `<span class="muted">${escapeHtml(job.result_message || "-")}</span>`;
    }
    cells[8].innerHTML = matchCell({ ...job, expected_action: job.expected_action ?? row.dataset.expected });
  }
  function titleButton(title) {
    const text = title ? escapeHtml(title) : '<span class="muted">제목 없음</span>';
    return `<button type="button" class="title-edit" data-title="${escapeHtml(title)}" title="눌러서 제목 수정">${text} <span class="pen">✎</span></button>`;
  }

  // ---- 이력 삭제 (한 건 / 전체) ----
  const historyBody = document.querySelector("#history tbody");
  function showEmptyIfNeeded() {
    if (historyBody && !historyBody.querySelector("tr[data-id]")) {
      historyBody.innerHTML = '<tr class="empty"><td colspan="10" class="muted">아직 분석 기록이 없습니다.</td></tr>';
    }
    updateSelection();
  }
  historyBody?.addEventListener("click", async (event) => {
    const edit = event.target.closest(".title-edit");
    if (edit) return startTitleEdit(edit);
    if (event.target.closest(".sel, .title-cell, input")) return; // 체크박스·제목 칸은 행 선택과 따로
    const btn = event.target.closest(".del-job");
    if (!btn) {
      const tr = event.target.closest("tr[data-id]");
      if (tr && !event.target.closest("a")) loadJob(Number(tr.dataset.id));
      return;
    }
    const row = btn.closest("tr");
    if (!confirm(`분석 #${row.dataset.seq || row.dataset.id} 기록과 영상을 삭제할까요?`)) return;
    btn.disabled = true;
    const res = await fetch(`/api/analyses/${row.dataset.id}/`, {
      method: "DELETE", credentials: "same-origin", headers: { "X-CSRFToken": csrf },
    });
    if (res.ok || res.status === 404) {
      row.remove();
      showEmptyIfNeeded();
      updateCount();
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
    updateCount();
  });

  // ---- 체크박스로 여러 건 골라 삭제 ----
  const selectAll = document.getElementById("select-all");
  const deleteSelected = document.getElementById("delete-selected");
  const checkedRows = () => [...document.querySelectorAll("#history .row-check:checked")].map((c) => c.closest("tr"));
  function updateSelection() {
    const all = document.querySelectorAll("#history .row-check");
    const n = checkedRows().length;
    if (deleteSelected) {
      deleteSelected.disabled = n === 0;
      deleteSelected.textContent = n ? `선택 삭제 (${n})` : "선택 삭제";
    }
    if (selectAll) {
      selectAll.checked = all.length > 0 && n === all.length;
      selectAll.indeterminate = n > 0 && n < all.length;
    }
  }
  historyBody?.addEventListener("change", (event) => { if (event.target.classList.contains("row-check")) updateSelection(); });
  selectAll?.addEventListener("change", () => {
    document.querySelectorAll("#history .row-check").forEach((c) => (c.checked = selectAll.checked));
    updateSelection();
  });
  deleteSelected?.addEventListener("click", async () => {
    const rows = checkedRows();
    if (!rows.length) return;
    const seqs = rows.map((r) => `#${r.dataset.seq}`).join(", ");
    if (!confirm(`분석 ${seqs} (${rows.length}건) 기록과 영상을 삭제할까요? (처리 중인 작업은 남습니다)`)) return;
    deleteSelected.disabled = true;
    const res = await fetch("/api/analyses/bulk-delete/", {
      method: "POST", credentials: "same-origin",
      headers: { "X-CSRFToken": csrf, "Content-Type": "application/json" },
      body: JSON.stringify({ ids: rows.map((r) => Number(r.dataset.id)) }),
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      alert(flattenErrors(body) || `삭제 실패 (HTTP ${res.status})`);
      return updateSelection();
    }
    body.deleted_ids.forEach((id) => historyBody.querySelector(`tr[data-id="${id}"]`)?.remove());
    if (body.skipped) alert(`처리 중인 ${body.skipped}건은 끝난 뒤에 삭제할 수 있어 남겨 두었습니다.`);
    showEmptyIfNeeded();
    updateCount();
    updateSelection();
  });

  // ---- 이력 표에서 제목 바로 수정 (Enter 저장, Esc 취소, 칸 밖을 누르면 저장) ----
  function startTitleEdit(btn) {
    const cell = btn.closest("td");
    const row = btn.closest("tr");
    const before = btn.dataset.title || "";
    const input = document.createElement("input");
    input.type = "text";
    input.maxLength = 100;
    input.value = before;
    input.className = "title-input";
    input.placeholder = "제목 입력";
    cell.replaceChildren(input);
    input.focus();
    input.select();
    let done = false;
    const finish = async (save) => {
      if (done) return;
      done = true;
      const title = input.value.trim();
      if (!save || title === before) {
        cell.innerHTML = titleButton(before);
        return;
      }
      input.disabled = true;
      const res = await fetch(`/api/analyses/${row.dataset.id}/`, {
        method: "PATCH", credentials: "same-origin",
        headers: { "X-CSRFToken": csrf, "Content-Type": "application/json" },
        body: JSON.stringify({ title }),
      }).catch(() => null);
      if (!res || !res.ok) {
        cell.innerHTML = titleButton(before);
        alert("제목을 저장하지 못했습니다.");
        return;
      }
      cell.innerHTML = titleButton(title);
      if (focusJob && focusJob.id === Number(row.dataset.id)) {
        focusJob.title = title;
        showFocus(focusJob, focusTrack);
      }
    };
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") { event.preventDefault(); finish(true); }
      else if (event.key === "Escape") finish(false);
    });
    input.addEventListener("blur", () => finish(true));
  }

  // 처음 열면 가장 최근에 완료된 분석을 위에 보여 줌
  const firstDone = document.querySelector('#history tr[data-status="SUCCESS"]');
  if (firstDone) loadJob(Number(firstDone.dataset.id));
  else showFocusEmpty();
  function showFocusEmpty() {
    drawTimeline(null);
    drawCompare(null);
  }

  // 다크/라이트 전환: 색을 다시 읽고 지금 보고 있는 그래프를 새 색으로 다시 그림
  window.addEventListener("themechange", () => {
    readColors();
    if (focusJob) showFocus(focusJob, focusTrack);
    else showFocusEmpty();
  });

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
})();
