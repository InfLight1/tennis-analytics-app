// Shared app passcode (Week 3 guardrail). Every /api/ request carries an
// X-Passcode header; the server answers 401 without the right one. The code
// is asked for once, then remembered on this device. Loaded by both pages
// before their own scripts, so their plain fetch() calls are covered.
(() => {
  const KEY = "tennis_passcode";
  let code = null;
  try { code = localStorage.getItem(KEY); } catch (e) {}
  let asking = null;

  function ask(wrong) {
    if (asking) return asking;
    asking = new Promise((resolve) => {
      const box = document.createElement("div");
      box.setAttribute("role", "dialog");
      box.setAttribute("aria-modal", "true");
      box.style.cssText = "position:fixed;inset:0;z-index:1000;display:grid;place-items:center;padding:16px;" +
        "background:rgba(0,0,0,.6);font:18px/1.4 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif";
      box.innerHTML = `<form style="background:var(--tile,#fff);color:var(--ink,#0F1A14);border-radius:20px;padding:22px;width:100%;max-width:360px">
          <div style="font-size:1.3rem;font-weight:700;margin-bottom:6px">Enter the app passcode</div>
          <div style="color:${wrong ? "var(--lost,#C2412F)" : "var(--ink-2,#47534D)"};font-size:.95rem;margin-bottom:14px">${
            wrong ? "That passcode didn't work. Try again." : "You only need to do this once on this device."}</div>
          <input type="password" autocomplete="current-password" aria-label="Passcode" required
            style="width:100%;font:inherit;padding:10px 12px;border-radius:10px;border:1px solid var(--line-2,#C3CBCF);background:var(--tile-2,#F4F6F7);color:inherit;box-sizing:border-box">
          <button type="submit" style="margin-top:12px;width:100%;font:inherit;font-weight:700;padding:10px;border:0;
            border-radius:999px;background:#C6DA2C;color:#0F1A14;cursor:pointer;min-height:48px">Continue</button>
          <a href="/account" style="display:block;margin-top:12px;text-align:center;color:inherit;font-size:.95rem">On a team? Sign in instead</a></form>`;
      document.body.appendChild(box);
      const input = box.querySelector("input");
      input.focus();
      box.querySelector("form").addEventListener("submit", (e) => {
        e.preventDefault();
        code = input.value.trim();
        try { localStorage.setItem(KEY, code); } catch (err) {}
        box.remove();
        asking = null;
        resolve(code);
      });
    });
    return asking;
  }

  const isApi = (url) => String(url instanceof Request ? url.url : url).includes("/api/");
  const realFetch = window.fetch.bind(window);

  // The example report's data (and its test-site copy) is public: no prompt for first-time visitors.
  // Its video is not: clips show real players, so watching always needs the passcode or a sign-in.
  const isPublic = (url) => /\/api\/profile\/(76a383379d90|e0e0e0e0e0e0)$/.test(String(url instanceof Request ? url.url : url));

  // Private matches open with a sign-in, never the passcode (Nov 4), so don't ask for a code that can't help.
  const needsAccount = (url) => /\/api\/(profile|status|names|job|frame|court-guess|debug|upload|record|calibrate|aim|point-labels|team)(\/|$)/.test(String(url instanceof Request ? url.url : url));

  // Accounts (2026-10-28): a signed-in player or coach sends their session (X-Session) instead,
  // and is never asked for the passcode. Sign-in routes need neither.
  const session = () => (window.Site && Site.session()) || null;
  const isAuth = (url) => /\/api\/auth\/(signin|join)/.test(String(url instanceof Request ? url.url : url));

  // Sign-in lost while working (Nov 4): it ran out, or they signed out in another tab. The server
  // refuses with a 403, which alone would look like a bad signal, so say it once and let the page
  // ask in place: leaving would stop a recording, and an upload would have to pick its file again.
  let lost = false, wrongAccount = false, signingIn = null;
  const signInGone = (wrong) => {
    if (lost) return;
    lost = true;
    wrongAccount = wrong;
    if (!wrong && window.Site) Site.setSession(null);
    window.dispatchEvent(new Event("signin-needed"));
  };
  window.signInPending = () => lost;
  // Also called by the upload's XMLHttpRequest, which doesn't go through fetch.
  window.signInCheck = (url, status, body) => {
    if (status !== 403) return;
    let data = {};
    try { data = JSON.parse(body); } catch (e) {}
    if (data.signin) signInGone(false);
    else if (/\/api\/(upload|record)\//.test(String(url))) signInGone(true);   // signed in, but to another account
  };

  window.askSignIn = () => {
    if (signingIn) return signingIn;
    signingIn = new Promise((resolve) => {
      const box = document.createElement("div");
      const field = "width:100%;font:inherit;padding:10px 12px;margin-bottom:10px;border-radius:10px;border:1px solid var(--line-2,#C3CBCF);" +
        "background:var(--tile-2,#F4F6F7);color:inherit;box-sizing:border-box";
      box.setAttribute("role", "dialog");
      box.setAttribute("aria-modal", "true");
      box.setAttribute("aria-label", "Sign in to keep going");
      box.style.cssText = "position:fixed;inset:0;z-index:1000;display:grid;place-items:center;padding:16px;" +
        "background:rgba(0,0,0,.6);font:18px/1.4 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif";
      box.innerHTML = `<form style="background:var(--tile,#fff);color:var(--ink,#0F1A14);border-radius:20px;padding:22px;width:100%;max-width:360px">
          <div style="font-size:1.3rem;font-weight:700;margin-bottom:6px">Sign in to keep going</div>
          <div style="color:var(--ink-2,#47534D);font-size:.95rem;margin-bottom:14px">${wrongAccount
            ? "This match belongs to a different account. Sign in to that one." : "You've been signed out."} Anything you've filmed or uploaded stays safe.</div>
          <input name="username" autocomplete="username" autocapitalize="none" aria-label="Username" placeholder="Username" required style="${field}">
          <input name="password" type="password" autocomplete="current-password" aria-label="Password" placeholder="Password" required style="${field}">
          <div role="alert" style="color:var(--lost,#C2412F);font-size:.95rem"></div>
          <button type="submit" style="margin-top:6px;width:100%;font:inherit;font-weight:700;padding:10px;border:0;
            border-radius:999px;background:#C6DA2C;color:#0F1A14;cursor:pointer;min-height:48px">Sign in</button>
          <button type="button" style="margin-top:6px;width:100%;font:inherit;font-size:.95rem;border:0;background:none;color:inherit;cursor:pointer;min-height:48px">Not now</button></form>`;
      document.body.appendChild(box);
      const form = box.querySelector("form");
      const msg = box.querySelector("[role=alert]");
      const close = () => { box.remove(); signingIn = null; resolve(); };
      form.username.focus();
      form.querySelector("button[type=button]").addEventListener("click", close);
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const btn = form.querySelector("button[type=submit]");
        msg.textContent = "";
        btn.disabled = true;
        try {
          const res = await realFetch("/api/auth/signin", { method: "POST", body: new FormData(form) });
          const data = await res.json().catch(() => ({}));
          if (!res.ok) { msg.textContent = data.error || `Something went wrong (${res.status}).`; return; }
          Site.setSession(data.session);
          if (data.user && data.user.role) Site.setRole(data.user.role);
          lost = false;
          close();
          window.dispatchEvent(new Event("signin-back"));
        } catch (err) {
          msg.textContent = "Couldn't reach the server. Check your connection and try again.";
        } finally { btn.disabled = false; }
      });
    });
    return signingIn;
  };

  window.fetch = async (url, opts = {}) => {
    if (!isApi(url)) return realFetch(url, opts);
    if (isAuth(url)) return realFetch(url, opts);
    if (!code && !session() && isPublic(url) && (opts.method || "GET").toUpperCase() === "GET") return realFetch(url, opts);
    if (!code && !session() && needsAccount(url)) return realFetch(url, opts);
    // creating a team and watching match video always need the passcode, even for someone signed in
    const needsCode = /\/api\/(auth\/create-team|watch\/|ball\/)/.test(String(url instanceof Request ? url.url : url));
    if (!code && (!session() || needsCode)) await ask(false);
    for (;;) {
      const headers = new Headers(opts.headers || {});
      if (code) headers.set("X-Passcode", code);
      if (session()) headers.set("X-Session", session());
      const res = await realFetch(url, { ...opts, headers });
      if (res.status === 403) window.signInCheck(url, 403, await res.clone().text().catch(() => ""));
      if (res.status !== 401) return res;
      if (session() && !code) {                         // expired or signed out elsewhere
        signInGone(false);
        if (needsAccount(url)) return res;
      }
      code = null;
      try { localStorage.removeItem(KEY); } catch (e) {}
      await ask(true);
    }
  };

  // For XMLHttpRequest callers (upload pieces): call after xhr.open().
  window.passcodeHeader = (xhr) => {
    if (code) xhr.setRequestHeader("X-Passcode", code);
    if (session()) xhr.setRequestHeader("X-Session", session());
  };
})();
