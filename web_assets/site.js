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
    // Signed in: player-name boxes suggest teammates' names. Typing a teammate's
    // name adds the match to their progress, so exact names matter.
    async teamNameHints(inputs) {
      if (!window.Site.session()) return false;
      const data = await fetch("/api/team/names").then((r) => r.json()).catch(() => ({}));
      if (!data.names || !data.names.length) return false;
      let list = document.getElementById("teamNames");
      if (!list) {
        list = document.createElement("datalist");
        list.id = "teamNames";
        document.body.appendChild(list);
      }
      list.replaceChildren(...data.names.map((n) => Object.assign(document.createElement("option"), { value: n })));
      inputs.forEach((i) => i && i.setAttribute("list", "teamNames"));
      return true;
    },
    // Delete a report for good (report, stats and its video on the server), then drop it here.
    async deleteReport(job) {
      const res = await fetch(`/api/job/${encodeURIComponent(job)}`, { method: "DELETE" });
      if (res.ok || res.status === 404) { window.Site.forgetReport(job); return { ok: true }; }
      const data = await res.json().catch(() => ({}));
      return { ok: false, error: data.error || `The server said ${res.status}.` };
    },
  };

  // Logo: a tennis ball. `uid` is kept so callers don't change.
  const emblem = (size, uid) => `<svg class="emblem" width="${size}" height="${size}" viewBox="0 0 32 32" aria-hidden="true">
      <circle cx="16" cy="16" r="14" fill="#C6DA2C"/>
      <path d="M5 8c6 4 6 12 0 16M27 8c-6 4-6 12 0 16" fill="none" stroke="#0F1A14" stroke-width="1.8" stroke-linecap="round"/>
    </svg>`;
  const wordmark = '<span class="wm">Advantage</span><span class="wm-ai">AI</span>';

  // Header into <header id="topbar" data-page="home|report">, footer into <footer id="sitefoot">.
  document.addEventListener("DOMContentLoaded", () => {
    const bar = document.getElementById("topbar");
    if (bar) {
      bar.className = "topbar";
      const signedIn = !!window.Site.session();
      const page = bar.dataset.page;
      const cur = (p) => (page === p ? ' aria-current="page"' : "");
      // One bar for the whole site: same logo and look; the links depend on being signed in.
      bar.innerHTML = `<div class="wrap">
        <a class="brand" href="${signedIn ? "/?stay=1" : "/"}" aria-label="Advantage AI, about">${emblem(32, "h")}${wordmark}</a>
        <nav class="nav" aria-label="Main">${signedIn
          ? `<a class="opt" href="/?stay=1"${cur("landing")}>About</a>
             <a class="opt" href="/app"${cur("app")}>Dashboard</a>
             <a class="opt" href="/app#matches">Matches</a>
             <a href="/account"${cur("account")}>Account</a>
             <a class="cta" href="/new"${cur("home")}>New match</a>`
          : `<a class="opt" href="/#how">How it works</a>
             <a class="opt" href="/example">Example report</a>
             <a class="opt" href="/#coaches">For coaches</a>
             <a class="opt" href="/app">Dashboard</a>
             <a href="/account"${cur("account")}>Sign in</a>
             <a class="cta" href="/new">Try it</a>`}</nav></div>`;
      // Phones, signed in: the four app tabs along the bottom (not on Home, which has its own full-screen steps).
      if (signedIn && ["app", "report", "account", "landing"].includes(page)) {
        const tabs = document.createElement("nav");
        tabs.className = "tabbar";
        tabs.setAttribute("aria-label", "App");
        tabs.innerHTML = `<a href="/app"${cur("app")}><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" aria-hidden="true"><path d="M4 11l8-6 8 6v9H4z"/></svg>Dashboard</a>
          <a href="/app#matches"${cur("report")}><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><path d="M5 6h14M5 12h14M5 18h9"/></svg>Matches</a>
          <a href="/new#record"><span class="c" aria-hidden="true"><i></i></span>Record</a>
          <a href="/account"${cur("account")}><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="9" r="3.5"/><path d="M5 20c1.5-4 12.5-4 14 0"/></svg>Account</a>`;
        document.body.appendChild(tabs);
        document.body.classList.add("has-tabs");
      }
    }
    const foot = document.getElementById("sitefoot");
    if (foot) {
      foot.className = "brand-foot";
      foot.innerHTML = `<svg class="bf-court" viewBox="0 0 360 200" aria-hidden="true"><g fill="none" stroke="currentColor" stroke-width="1.2">
          <path d="M40 190 L320 190 L250 20 L110 20 Z"/><path d="M68 122 H292 M96 54 H264 M180 122 V54"/><path d="M84 88 H276" stroke-width="2.4"/>
          <path d="M54 156 H306" stroke-dasharray="2 4"/></g></svg>
        <div class="wrap">
          <div class="bf-top">
            <a class="brand brand-lg" href="${window.Site.session() ? "/?stay=1" : "/"}" aria-label="About Advantage AI">${emblem(44, "f")}${wordmark}</a>
            <p class="bf-tag">Turn match data into <em>match wins</em>.</p>
          </div>
          <nav class="bf-nav" aria-label="Footer">${(() => {
            const home = window.Site.session() ? "/?stay=1" : "/";
            return `<a href="${home}#how">How it works</a><a href="/example">Example report</a><a href="${home}#coaches">For coaches</a><a href="${home}#parents">For parents</a><a href="/new">New analysis</a><a href="/new#reports">My reports</a>`;
          })()}</nav>
          <p class="bf-note">Built by a player, for players. Made to work alongside your coach, not replace one.</p>
          ${dev ? '<p class="bf-note">Dev mode is on for this device (add ?dev=0 to the address to turn it off).</p>' : ""}
        </div>`;
    }
  });
})();
