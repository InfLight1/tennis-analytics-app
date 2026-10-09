// Shared by every page: top bar, light/dark switch, and the list of this
// device's reports ("My reports" on the home page). Reports are remembered
// in the browser only (no accounts): each entry is {job, title, added}.
(() => {
  const KEY = "tennis_reports";

  function load() {
    try { return JSON.parse(localStorage.getItem(KEY)) || []; } catch (e) { return []; }
  }
  function save(list) {
    try { localStorage.setItem(KEY, JSON.stringify(list.slice(0, 20))); } catch (e) {}
  }

  const EXAMPLE_JOB = "76a383379d90";   // showcase match, linked from the home page
  if (load().some((r) => r.job === EXAMPLE_JOB)) save(load().filter((r) => r.job !== EXAMPLE_JOB));

  window.Site = {
    EXAMPLE_JOB,
    reportUrl: (job) => `/report?job=${encodeURIComponent(job)}`,
    reports: load,
    // Add or update a report (newest first). Keeps the first "added" date.
    rememberReport(job, title) {
      if (job === EXAMPLE_JOB) return;
      const list = load();
      const old = list.find((r) => r.job === job);
      const entry = { job, title: title || old?.title || "Match", added: old?.added || new Date().toISOString() };
      save([entry, ...list.filter((r) => r.job !== job)]);
    },
    forgetReport(job) { save(load().filter((r) => r.job !== job)); },
  };

  // Theme: OS default; the viewer's choice wins both ways.
  try { const t = localStorage.getItem("theme"); if (t) document.documentElement.dataset.theme = t; } catch (e) {}
  function toggleTheme() {
    const root = document.documentElement;
    const dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    root.dataset.theme = dark ? "light" : "dark";
    try { localStorage.setItem("theme", root.dataset.theme); } catch (e) {}
  }

  // Top bar into <header id="topbar" data-page="home|report">.
  document.addEventListener("DOMContentLoaded", () => {
    const bar = document.getElementById("topbar");
    if (!bar) return;
    const page = bar.dataset.page;
    bar.className = "topbar";
    bar.innerHTML = `
      <a class="brand" href="/"><img src="icon-192.png" alt=""><span>Tennis Analytics</span></a>
      <a class="navlink" href="/#new"${page === "home" ? ' aria-current="page"' : ""}>New analysis</a>
      <a class="navlink" href="/#reports">My reports</a>
      <button type="button" id="themeBtn" title="Switch light/dark" aria-label="Switch light/dark">◐</button>`;
    document.getElementById("themeBtn").addEventListener("click", toggleTheme);
  });
})();
