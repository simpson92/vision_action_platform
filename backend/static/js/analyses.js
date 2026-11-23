// 분석 화면: 입력 방식 전환 → POST /api/analyses/ → 작업 ID로 상태를 주기적으로 조회 → 결과 표시
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

  const LABELS = {
    bend_return: "허리 굽혔다 펴기", leg_raise_lower: "다리 들었다 내리기", walk_turn_walk: "걷다가 방향 바꿔 걷기",
    drink_return: "마시고 제자리로", sit_stand: "앉았다 일어나기", wave: "손 흔들기",
    UNCERTAIN: "판단 보류", INSUFFICIENT_INPUT: "입력 부족",
  };
  const QUALITY = { good: "좋음", fair: "보통", poor: "나쁨" };

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
    dropText.textContent = `${file.name} (${(file.size / 1024 / 1024).toFixed(1)}MB)`;
    preview.src = URL.createObjectURL(file);
    preview.hidden = false;
  });

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
      startTracking(body.id);
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
  function startTracking(id) {
    clearTimeout(timer);
    document.getElementById("result-empty").hidden = true;
    document.getElementById("result-body").hidden = false;
    document.getElementById("people").innerHTML = "";
    document.getElementById("result-error").hidden = true;
    document.getElementById("detail-link").href = `/analyses/${id}/`;
    setSteps("PENDING");
    document.getElementById("result-meta").textContent = `작업 #${id} 등록됨. 결과를 기다리는 중…`;
    upsertHistory({ id, status: "PENDING", status_display: "대기", predictions: [] });
    poll(id, 0);
  }

  async function poll(id, attempt) {
    try {
      const res = await fetch(`/api/analyses/${id}/status/`, { credentials: "same-origin" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const job = await res.json();
      render(job);
      upsertHistory(job);
      if (job.is_finished) return;
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
    });
  }

  function render(job) {
    setSteps(job.status);
    const meta = document.getElementById("result-meta");
    const parts = [`작업 #${job.id} · ${job.status_display}`];
    if (job.processing_ms) parts.push(`AI 처리 ${(job.processing_ms / 1000).toFixed(1)}초`);
    if (job.total_seconds) parts.push(`전체 ${job.total_seconds}초`);
    meta.textContent = parts.join(" · ");

    const errorBox = document.getElementById("result-error");
    if (job.status === "FAILURE") {
      errorBox.textContent = job.error_message || "분석에 실패했습니다.";
      errorBox.hidden = false;
    }
    const people = document.getElementById("people");
    if (job.status === "SUCCESS" && !job.predictions.length) {
      people.innerHTML = `<p class="muted">${escapeHtml(job.result_message || "영상에서 사람을 찾지 못했습니다.")}</p>`;
      return;
    }
    people.innerHTML = job.predictions.map(personCard).join("");
  }

  function personCard(p) {
    const decided = p.action_label !== "UNCERTAIN" && p.action_label !== "INSUFFICIENT_INPUT";
    const probs = Object.entries(p.probabilities || {}).sort((a, b) => b[1] - a[1]);
    const bars = probs.map(([label, v]) => `
      <div class="bar"><span>${LABELS[label] || label}</span>
        <i style="width:${Math.round(v * 100 / Math.max(probs[0][1], 0.01))}%"></i><b>${(v * 100).toFixed(0)}%</b></div>`).join("");
    const hint = decided ? "" : (p.raw_label ? `<p class="muted">가장 가까운 동작: ${LABELS[p.raw_label] || p.raw_label}</p>` : "");
    return `
      <article class="person ${decided ? "" : "uncertain"}">
        <header><span class="track">사람 #${p.track_id}</span>
          <span class="quality q-${p.input_quality}">입력 품질 ${QUALITY[p.input_quality] || "-"}</span></header>
        <div class="action">${LABELS[p.action_label] || p.action_label}</div>
        <div class="muted">Confidence ${(p.confidence * 100).toFixed(1)}% · 2등과 차이 ${(p.margin * 100).toFixed(1)}%p · Frame ${p.valid_frames}개</div>
        ${hint}
        <div class="bars">${bars}</div>
      </article>`;
  }

  function upsertHistory(job) {
    const tbody = document.querySelector("#history tbody");
    if (!tbody) return;
    tbody.querySelector("tr.empty")?.remove();
    let row = tbody.querySelector(`tr[data-id="${job.id}"]`);
    if (!row) {
      row = document.createElement("tr");
      row.dataset.id = job.id;
      const now = new Date();
      row.innerHTML = `<td>${job.id}</td><td>${String(now.getMonth() + 1).padStart(2, "0")}/${String(now.getDate()).padStart(2, "0")} ${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}</td>
        <td>${inputType.value === "upload" ? "영상 업로드" : "IP Webcam"}</td><td class="st"></td><td class="res"></td><td><a href="/analyses/${job.id}/">상세</a></td>`;
      tbody.prepend(row);
    }
    const st = row.children[3];
    st.innerHTML = `<span class="badge s-${job.status}">${job.status_display}</span>`;
    const res = row.children[4];
    if (job.predictions && job.predictions.length) {
      res.innerHTML = job.predictions.map((p) => `<span class="chip">#${p.track_id} ${LABELS[p.action_label] || p.action_label} ${p.confidence.toFixed(2)}</span>`).join("");
    } else if (job.status === "FAILURE") {
      res.textContent = (job.error_message || "").slice(0, 40);
    } else if (job.status === "SUCCESS") {
      res.textContent = job.result_message || "-";
    }
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
})();
