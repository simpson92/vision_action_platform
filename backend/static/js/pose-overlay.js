// 결과 영상 위 관절·사람 번호 표시: /api/analyses/{id}/pose/ 좌표를 받아 <video> 위 canvas에 그립니다.
// 영상을 다시 만들지 않고 브라우저에서 그리므로, 끄고 켜기 쉽고 원본 영상은 그대로입니다.
(function () {
  // COCO 17 관절 연결선 (머리, 팔, 몸통, 다리)
  const EDGES = [[0, 1], [0, 2], [1, 3], [2, 4], [5, 6], [5, 7], [7, 9], [6, 8], [8, 10],
    [5, 11], [6, 12], [11, 12], [11, 13], [13, 15], [12, 14], [14, 16]];
  const COLORS = ["#a78bfa", "#34d399", "#fbbf24", "#60a5fa", "#fb7185", "#22d3ee"];
  const handles = new WeakMap();

  function lastIndexAtOrBefore(frames, target) {
    let lo = 0;
    let hi = frames.length - 1;
    let found = -1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (frames[mid] <= target) { found = mid; lo = mid + 1; } else hi = mid - 1;
    }
    return found;
  }

  function attach(video, toggle) {
    if (handles.has(video)) return handles.get(video);
    const wrap = document.createElement("div");
    wrap.className = "pose-wrap";
    video.parentNode.insertBefore(wrap, video);
    wrap.appendChild(video);
    const canvas = document.createElement("canvas");
    canvas.className = "pose-canvas";
    wrap.appendChild(canvas);
    const ctx = canvas.getContext("2d");
    const state = { pose: null, url: null, on: toggle ? toggle.checked : true, raf: null };

    function draw() {
      // canvas를 영상 칸과 같은 위치·크기로 맞춤 (테두리 안쪽)
      const w = video.clientWidth;
      const h = video.clientHeight;
      const dpr = window.devicePixelRatio || 1;
      canvas.style.left = `${video.offsetLeft + video.clientLeft}px`;
      canvas.style.top = `${video.offsetTop + video.clientTop}px`;
      canvas.style.width = `${w}px`;
      canvas.style.height = `${h}px`;
      if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
        canvas.width = Math.round(w * dpr);
        canvas.height = Math.round(h * dpr);
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      const pose = state.pose;
      if (!state.on || !pose || !pose.tracks || !pose.tracks.length || !video.videoWidth) return;

      // 영상은 칸 안에 비율을 지켜 들어가므로(object-fit: contain) 실제 화면 영역을 계산
      const scale = Math.min(w / video.videoWidth, h / video.videoHeight);
      const dw = video.videoWidth * scale;
      const dh = video.videoHeight * scale;
      const ox = (w - dw) / 2;
      const oy = (h - dh) / 2;
      const sx = dw / (pose.width || video.videoWidth);
      const sy = dh / (pose.height || video.videoHeight);
      const fps = pose.fps || 30;
      const frame = Math.floor(video.currentTime * fps + 1e-3);
      const lineWidth = Math.max(2, Math.min(4, dw / 220));

      pose.tracks.forEach((track, t) => {
        const i = lastIndexAtOrBefore(track.frames, frame);
        if (i < 0) return;
        const gap = track.frames.length > 1 ? Math.max(3, (track.frames[track.frames.length - 1] - track.frames[0]) / track.frames.length * 2) : 3;
        if (frame - track.frames[i] > gap) return; // 이 순간에는 그 사람을 못 찾음
        const p = track.points[i];
        const pt = (j) => (p[j * 2] < 0 ? null : [ox + p[j * 2] * sx, oy + p[j * 2 + 1] * sy]);
        const color = COLORS[t % COLORS.length];
        ctx.lineWidth = lineWidth;
        ctx.lineCap = "round";
        ctx.strokeStyle = color;
        EDGES.forEach(([a, b]) => {
          const A = pt(a);
          const B = pt(b);
          if (!A || !B) return;
          ctx.beginPath();
          ctx.moveTo(A[0], A[1]);
          ctx.lineTo(B[0], B[1]);
          ctx.stroke();
        });
        ctx.fillStyle = "#ffffff";
        let top = null;
        for (let j = 0; j < 17; j += 1) {
          const P = pt(j);
          if (!P) continue;
          ctx.beginPath();
          ctx.arc(P[0], P[1], lineWidth * 0.9, 0, Math.PI * 2);
          ctx.fill();
          if (!top || P[1] < top[1]) top = P;
        }
        if (!top) return;
        // 사람 번호표: 머리 위
        const label = `#${track.id}`;
        ctx.font = `800 ${Math.max(12, Math.round(dw / 40))}px system-ui, sans-serif`;
        const tw = ctx.measureText(label).width + 10;
        const th = Math.max(18, Math.round(dw / 28));
        const lx = Math.min(Math.max(top[0] - tw / 2, 2), w - tw - 2);
        const ly = Math.max(top[1] - th - 10, 2);
        ctx.fillStyle = color;
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(lx, ly, tw, th, 5); else ctx.rect(lx, ly, tw, th);
        ctx.fill();
        ctx.fillStyle = "#14182a";
        ctx.textBaseline = "middle";
        ctx.fillText(label, lx + 5, ly + th / 2 + 1);
      });
    }

    function loop() {
      draw();
      if (!video.paused && !video.ended) state.raf = requestAnimationFrame(loop);
      else state.raf = null;
    }
    const kick = () => { if (!state.raf) loop(); };
    ["play", "seeked", "loadedmetadata", "loadeddata", "timeupdate"].forEach((e) => video.addEventListener(e, kick));
    window.addEventListener("resize", draw);
    toggle?.addEventListener("change", () => { state.on = toggle.checked; draw(); });

    const handle = {
      async load(url) {
        if (state.url === url) return;
        state.url = url;
        state.pose = null;
        draw();
        try {
          const res = await fetch(url, { credentials: "same-origin" });
          if (!res.ok || state.url !== url) return;
          state.pose = await res.json();
          handle.hasData = !!(state.pose.tracks && state.pose.tracks.length);
          video.dispatchEvent(new CustomEvent("posedata", { detail: handle.hasData }));
          draw();
        } catch (_) { /* 좌표가 없어도 영상은 그대로 재생 */ }
      },
      hasData: false,
      draw,
    };
    handles.set(video, handle);
    return handle;
  }

  window.PoseOverlay = { attach };

  // 상세 화면처럼 처음부터 있는 영상: <video data-pose-url="..."> 와 <input data-pose-toggle>
  document.querySelectorAll("video[data-pose-url]").forEach((video) => {
    const toggle = document.querySelector(`[data-pose-toggle="${video.id}"]`);
    attach(video, toggle).load(video.dataset.poseUrl);
  });
})();
