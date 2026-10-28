// Shared by every page: the brand header and footer banner, and the list of this
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

  // Dev mode (for us, not players or judges): add ?dev=1 to any page address to turn it on for
  // this device, ?dev=0 to turn it off. It shows the step timings used for benchmarks.
  const DEV_KEY = "advantage_dev";
  const devParam = new URLSearchParams(location.search).get("dev");
  try {
    if (devParam === "1") localStorage.setItem(DEV_KEY, "1");
    if (devParam === "0") localStorage.removeItem(DEV_KEY);
  } catch (e) {}
  let dev = devParam === "1";
  try { dev = dev || localStorage.getItem(DEV_KEY) === "1"; } catch (e) {}
  if (load().some((r) => r.job === EXAMPLE_JOB)) save(load().filter((r) => r.job !== EXAMPLE_JOB));

  // Signed-in session (accounts, 2026-10-28); passcode.js sends it as X-Session.
  const SESSION_KEY = "advantage_session";

  window.Site = {
    EXAMPLE_JOB,
    dev,
    session() { try { return localStorage.getItem(SESSION_KEY); } catch (e) { return null; } },
    setSession(token) {
      try { token ? localStorage.setItem(SESSION_KEY, token) : localStorage.removeItem(SESSION_KEY); } catch (e) {}
    },
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
    // Delete a report for good (report, stats and its video on the server), then drop it here.
    async deleteReport(job) {
      const res = await fetch(`/api/job/${encodeURIComponent(job)}`, { method: "DELETE" });
      if (res.ok || res.status === 404) { window.Site.forgetReport(job); return { ok: true }; }
      const data = await res.json().catch(() => ({}));
      return { ok: false, error: data.error || `The server said ${res.status}.` };
    },
  };

  // Logo: a tennis ball on a green tile. `uid` keeps gradient ids unique when it appears twice.
  const emblem = (size, uid) => `<svg class="emblem" width="${size}" height="${size}" viewBox="0 0 32 32" aria-hidden="true">
      <defs><linearGradient id="emb-${uid}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#3E8657"/><stop offset="1" stop-color="#143424"/></linearGradient></defs>
      <rect x=".5" y=".5" width="31" height="31" rx="9" fill="url(#emb-${uid})" stroke="rgba(190,235,200,.38)"/>
      <circle cx="16" cy="16" r="8.6" fill="#D4EC7E"/>
      <path d="M9.4 10.4c3.1 2.3 3.1 8.9 0 11.2M22.6 10.4c-3.1 2.3-3.1 8.9 0 11.2" fill="none" stroke="#1A4330" stroke-width="1.5" stroke-linecap="round"/>
      <path d="M5.5 7.2a12 12 0 0 1 6-3.6" fill="none" stroke="rgba(255,255,255,.28)" stroke-width="1.2" stroke-linecap="round"/>
    </svg>`;
  const wordmark = '<span class="wm">Advantage</span><span class="wm-ai">AI</span>';

  // Light/dark switch, only on the report (Home keeps one dark palette). With no saved choice
  // the report follows the device setting; the report page sets data-theme early from storage.
  const themeButton = `<button type="button" class="theme-btn" aria-label="Switch between light and dark" title="Light or dark">
      <svg class="sun" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>
      <svg class="moon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/></svg>
    </button>`;
  function toggleTheme() {
    const root = document.documentElement;
    const dark = root.dataset.theme ? root.dataset.theme === "dark" : !matchMedia("(prefers-color-scheme: light)").matches;
    root.dataset.theme = dark ? "light" : "dark";
    try { localStorage.setItem("report_theme", root.dataset.theme); } catch (e) {}
  }

  // Header into <header id="topbar" data-page="home|report">, footer into <footer id="sitefoot">.
  document.addEventListener("DOMContentLoaded", () => {
    const bar = document.getElementById("topbar");
    if (bar) {
      const home = bar.dataset.page === "home";
      bar.className = "topbar";
      bar.innerHTML = `<div class="wrap">
        <a class="brand" href="/" aria-label="Advantage AI, home">${emblem(32, "h")}${wordmark}</a>
        <nav class="nav" aria-label="Main">
          <a href="/#new"${home ? ' aria-current="page"' : ""}>New analysis</a>
          <a href="/#reports">My reports</a>
          <a href="/account"${bar.dataset.page === "account" ? ' aria-current="page"' : ""}>${window.Site.session() ? "Account" : "Sign in"}</a>
        </nav>${bar.dataset.page === "report" ? themeButton : ""}</div>`;
      bar.querySelector(".theme-btn")?.addEventListener("click", toggleTheme);
    }
    const foot = document.getElementById("sitefoot");
    if (foot) {
      foot.className = "brand-foot";
      foot.innerHTML = `<svg class="bf-court" viewBox="0 0 360 200" aria-hidden="true"><g fill="none" stroke="currentColor" stroke-width="1.2">
          <path d="M40 190 L320 190 L250 20 L110 20 Z"/><path d="M68 122 H292 M96 54 H264 M180 122 V54"/><path d="M84 88 H276" stroke-width="2.4"/>
          <path d="M54 156 H306" stroke-dasharray="2 4"/></g></svg>
        <div class="wrap">
          <div class="bf-top">
            <a class="brand brand-lg" href="/" aria-label="Advantage AI, home">${emblem(44, "f")}${wordmark}</a>
            <p class="bf-tag">Turn match data into <em>match wins</em>.</p>
          </div>
          <nav class="bf-nav" aria-label="Footer"><a href="/#new">New analysis</a><a href="/#reports">My reports</a><a href="/report?job=${EXAMPLE_JOB}">Example report</a></nav>
          <p class="bf-note">Built by a player, for players. Made to work alongside your coach, not replace one.</p>
          ${dev ? '<p class="bf-note">Dev mode is on for this device (add ?dev=0 to the address to turn it off).</p>' : ""}
        </div>`;
    }
  });
})();
