// 다크/라이트 모드 전환: 오른쪽 위 버튼. 고른 모드는 브라우저에 기억하고, 그래프는 themechange 이벤트로 다시 그림
(function () {
  const root = document.documentElement;
  const btn = document.getElementById("theme-btn");
  const current = () => (root.dataset.theme === "light" ? "light" : "dark");
  function paint() {
    if (!btn) return;
    const light = current() === "light";
    btn.textContent = light ? "☾ 다크" : "☀ 라이트";
    btn.title = light ? "다크 모드로 바꾸기" : "라이트 모드로 바꾸기";
  }
  btn?.addEventListener("click", () => {
    const next = current() === "light" ? "dark" : "light";
    root.dataset.theme = next;
    try { localStorage.setItem("theme", next); } catch (_) { /* 저장 못 해도 이번 화면에는 적용 */ }
    paint();
    window.dispatchEvent(new CustomEvent("themechange", { detail: next }));
  });
  paint();
})();
