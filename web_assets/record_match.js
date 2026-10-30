// "Record match" on Home (2026-10-14): the page films the match itself and sends
// ~4 s pieces while play goes on, so the report is ready minutes after the last
// point instead of after an hour-long upload. The court is marked on a still
// from the camera before the first point (warm-ups are not recorded).
//
// Pieces wait on the phone's disk (IndexedDB) until the server has them, so a
// weak signal only builds a backlog, and a closed page can still send them
// later. If the camera stops mid-match (phone call, page left), "Continue
// recording" starts a new part; the server joins the parts (modal_app.py,
// finish_recording_remote).
//
// Uses recorder.js (window.Recorder) and, from the Home page script: $, sendPart,
// waitToRetry, keepAwake, store, formatBytes, aboutTime, setStage, showFrame,
// startPolling, renderReports, backendUrl and the court-marking state.
(() => {
  const ENABLED = true;              // false hides "Record the match" (Oct 18 go/no-go)
  const REC_KEY = "tennis_pending_record";
  const MAX_MIN = 60, WARN_MIN = 55;
  const PARALLEL = 3;                // pieces in flight at once (mobile data)

  // ── Pieces waiting to be sent: IndexedDB, or memory if the browser blocks it ──
  const mem = new Map();
  let dbPromise = null;
  function db() {
    if (!dbPromise) {
      dbPromise = new Promise((resolve, reject) => {
        const r = indexedDB.open("advantage_recording", 1);
        r.onupgradeneeded = () => r.result.createObjectStore("pieces");
        r.onsuccess = () => resolve(r.result);
        r.onerror = () => reject(r.error);
      }).catch(() => null);
    }
    return dbPromise;
  }
  const keyOf = (job, i) => `${job}:${String(i).padStart(6, "0")}`;
  function req(mode, run) {
    return db().then((d) => d && new Promise((resolve, reject) => {
      const t = d.transaction("pieces", mode);
      const r = run(t.objectStore("pieces"));
      t.oncomplete = () => resolve(r ? r.result : true);
      t.onerror = t.onabort = () => reject(t.error);
    }));
  }
  const pieces = {
    async put(job, i, blob) {
      try { if (await req("readwrite", (st) => st.put(blob, keyOf(job, i)))) return; } catch (e) { /* full: memory */ }
      mem.set(keyOf(job, i), blob);
    },
    async get(job, i) {
      if (mem.has(keyOf(job, i))) return mem.get(keyOf(job, i));
      try { return (await req("readonly", (st) => st.get(keyOf(job, i)))) || null; } catch (e) { return null; }
    },
    async del(job, i) {
      mem.delete(keyOf(job, i));
      try { await req("readwrite", (st) => st.delete(keyOf(job, i))); } catch (e) {}
    },
    // Waiting pieces for a job: [{i, size}], in order.
    async list(job) {
      const out = [];
      try {
        const range = IDBKeyRange.bound(`${job}:`, `${job}:￿`);
        const keys = (await req("readonly", (st) => st.getAllKeys(range))) || [];
        for (const k of keys) {
          const b = await req("readonly", (st) => st.get(k));
          out.push({ i: parseInt(String(k).split(":")[1], 10), size: b ? b.size : 0 });
        }
      } catch (e) {}
      for (const [k, b] of mem) if (k.startsWith(`${job}:`)) out.push({ i: parseInt(k.split(":")[1], 10), size: b.size });
      return out.sort((a, b) => a.i - b.i);
    },
    async clear(job) {
      for (const k of [...mem.keys()]) if (k.startsWith(`${job}:`)) mem.delete(k);
      try { await req("readwrite", (st) => st.delete(IDBKeyRange.bound(`${job}:`, `${job}:￿`))); } catch (e) {}
    },
  };

  // ── State (saved on this device so a closed page can still send what was recorded) ──
  const S = {
    job: null, cam: null, recorder: null, width: 0, height: 0,
    pieces: 0, size: 0, segments: [], elapsed: 0, sentCount: 0, sentBytes: 0,
    recording: false, stopped: false, finishing: false, segStart: 0, trouble: false,
    queue: [], active: 0, inflight: new Map(), rateStart: 0, rateBytes: 0, run: { stop: false },
  };
  function save() {
    if (!S.job) return;
    store.set(REC_KEY, { jobId: S.job, r2: !!S.r2, pieces: S.pieces, size: S.size, segments: S.segments, sentCount: S.sentCount, sentBytes: S.sentBytes,
      elapsed: S.elapsed + (S.recording ? Date.now() - S.segStart : 0), stopped: S.stopped, at: new Date().toISOString() });
  }
  const busy = () => !!S.job && (S.recording || (S.stopped && !S.finishing) || S.queue.length > 0 || S.active > 0);

  // ── Sending ──
  function enqueue(i) {
    if (!S.queue.includes(i)) { S.queue.push(i); S.queue.sort((a, b) => a - b); }
    pump();
  }
  function pump() {
    while (S.active < PARALLEL && S.queue.length) {
      const i = S.queue.shift();
      S.active++;
      sendOne(i).finally(() => { S.active--; pump(); maybeFinish(); });
    }
  }
  async function sendOne(i) {
    for (let attempt = 1; ; attempt++) {
      if (S.run.stop) return;
      const blob = await pieces.get(S.job, i);
      if (!blob) { fail("Part of the recording was lost on this phone, so it can't be sent. Please discard it and record again."); return; }
      try {
        if (!S.rateStart) S.rateStart = Date.now();
        await sendPart(S.job, i, blob, (b) => { S.inflight.set(i, b); render(); });
        S.inflight.delete(i);
        await pieces.del(S.job, i);
        S.sentCount++;
        S.sentBytes += blob.size;
        S.trouble = false;
        S.rateBytes += blob.size;
        save();
        render();
        return;
      } catch (err) {
        S.inflight.delete(i);
        if (err.expired) { fail("The server no longer knows this recording, so it can't be sent. Please record again."); return; }
        S.trouble = true;
        render();
        await waitToRetry(Math.min(2000 * 2 ** (attempt - 1), 30000), S.run);
      }
    }
  }
  const inflightBytes = () => [...S.inflight.values()].reduce((a, b) => a + b, 0);
  const rate = () => (S.rateStart && Date.now() - S.rateStart > 8000 ? (S.rateBytes + inflightBytes()) / ((Date.now() - S.rateStart) / 1000) : 0);

  function maybeFinish() {
    if (S.stopped && !S.finishing && !S.run.stop && S.queue.length === 0 && S.active === 0 && S.sentCount === S.pieces) finish();
  }

  async function finish() {
    S.finishing = true;
    render();
    const form = new FormData();
    form.append("pieces", S.pieces);
    form.append("size", S.size);
    form.append("segments", JSON.stringify(S.segments));
    for (let attempt = 1; ; attempt++) {
      try {
        const res = await fetch(`${backendUrl()}/api/record/${S.job}/finish`, { method: "POST", body: form });
        const data = await res.json().catch(() => ({}));
        if (res.status === 404) { fail("The server no longer knows this recording. Please record again."); return; }
        if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
        break;
      } catch (e) {
        render("Couldn't reach the server to finish. Trying again…");
        await waitToRetry(Math.min(2000 * 2 ** (attempt - 1), 30000), S.run);
        if (S.run.stop) return;
      }
    }
    await pieces.clear(S.job);
    store.del(REC_KEY);
    keepAwake(false);
    $("recOverlay").classList.add("hidden");
    document.body.style.overflow = "";
    jobId = S.job;
    S.job = null;
    STAGE_ORDER = RECORD_STAGES;
    setStage($("badge1"), "done");
    setStage($("badge2"), "done");
    setStage($("badge3"), "active");
    $("recordResume").classList.add("hidden");
    renderReports();
    $("processingPanel").classList.remove("hidden");
    $("processingPanel").scrollIntoView({ behavior: "smooth" });
    analysisStartedAt = Date.now();     // the analysis clock starts when the match video is complete
    startPolling();
  }

  function fail(msg) {
    S.run.stop = true;
    S.queue = [];
    $("recSent").textContent = msg;
    $("recSent").classList.add("error");
    $("recNote").textContent = "";
    ["recStartBtn", "recContinueBtn", "recStopBtn", "recCancelBtn"].forEach((id) => $(id).classList.add("hidden"));
    showDiscardInOverlay();
  }
  function showDiscardInOverlay() {
    if ($("recCloseBtn")) return;
    const b = document.createElement("button");
    b.type = "button";
    b.className = "btn rec-main rec-stop";
    b.id = "recCloseBtn";
    b.textContent = "Discard and close";
    b.addEventListener("click", async () => { await discard(); location.reload(); });
    $("recOverlay").querySelector(".rec-actions").appendChild(b);
  }

  // ── Recording ──
  function clock(ms) {
    const t = Math.floor(ms / 1000), h = Math.floor(t / 3600), m = Math.floor(t / 60) % 60, s = String(t % 60).padStart(2, "0");
    return h ? `${h}:${String(m).padStart(2, "0")}:${s}` : `${m}:${s}`;
  }
  const elapsedMs = () => S.elapsed + (S.recording ? Date.now() - S.segStart : 0);

  async function onPiece(blob) {
    const i = S.pieces++;
    S.size += blob.size;
    await pieces.put(S.job, i, blob);
    save();
    enqueue(i);
  }

  // Start (or carry on) filming. The camera may have closed while the court was being
  // marked (screen locked, another app), so it is opened again first if needed.
  async function startRecording() {
    const btn = S.pieces ? $("recContinueBtn") : $("recStartBtn");
    btn.disabled = true;
    try {
      if (!S.cam || S.cam.track.readyState === "ended") {
        S.cam = await Recorder.openCamera();
        watchTrack();
        $("recLive").srcObject = S.cam.stream;
        $("recLive").play().catch(() => {});
      }
      startSegment();
    } catch (e) {
      $("recNote").textContent = S.pieces
        ? `The camera didn't open again (${e.message}). Press Stop to send what was filmed.`
        : `The camera didn't start (${e.message}). Check the camera is allowed for this site, then press Start recording again.`;
    } finally {
      btn.disabled = false;
    }
  }

  function startSegment() {
    const rec = Recorder.start(S.cam.stream, onPiece, 4000, interrupted);   // throws if this browser can't record
    S.segments.push(S.pieces);
    S.recorder = rec;
    S.recording = true;
    S.segStart = Date.now();
    save();
    $("recOverlay").classList.add("live");
    $("recKicker").textContent = "Recording";
    $("recTitle").textContent = "Recording the match";
    $("recStartBtn").classList.add("hidden");
    $("recContinueBtn").classList.add("hidden");
    $("recCancelBtn").classList.add("hidden");
    $("recStopBtn").classList.remove("hidden");
    $("recNote").textContent = "Keep this page open; the screen stays on. Press Stop after the last point.";
    if (!$("recLive").classList.contains("off")) toggleLive();   // hide the picture while filming (battery)
    keepAwake(true);
  }

  // The camera or recorder stopped by itself (phone call, page left, camera taken by another app).
  async function interrupted() {
    if (!S.recording) return;
    S.elapsed += Date.now() - S.segStart;
    S.recording = false;
    try { await S.recorder.stop(); } catch (e) {}
    save();
    $("recOverlay").classList.remove("live");
    $("recKicker").textContent = "Paused";
    $("recTitle").textContent = "The camera stopped";
    $("recContinueBtn").classList.remove("hidden");
    $("recStopBtn").classList.remove("hidden");
    $("recNote").textContent = "What was filmed is kept. Don't move the phone, and press Continue recording to carry on.";
    render();
  }

  async function stopRecording() {
    if (!confirm("Stop recording? This ends the match video.")) return;
    if (S.recording) {
      S.elapsed += Date.now() - S.segStart;
      S.recording = false;
      await S.recorder.stop();
    }
    if (!S.pieces) { fail("Nothing was filmed, so there's nothing to send. Please record again."); return; }
    S.stopped = true;
    save();
    if (S.cam) S.cam.stream.getTracks().forEach((t) => t.stop());
    $("recOverlay").classList.remove("live");
    $("recKicker").textContent = "Match recorded";
    $("recTitle").textContent = "Sending the video";
    ["recStartBtn", "recContinueBtn", "recStopBtn"].forEach((id) => $(id).classList.add("hidden"));
    $("recLive").classList.add("off");
    $("toggleLiveBtn").classList.add("hidden");
    $("recNote").textContent = "Keep this page open until it's sent. Your report opens when it's ready.";
    render();
    maybeFinish();
  }

  function watchTrack() {
    S.cam.track.addEventListener("ended", interrupted);
  }

  function toggleLive() {
    const v = $("recLive");
    const off = v.classList.toggle("off");
    if (off) v.pause(); else v.play().catch(() => {});
    $("toggleLiveBtn").textContent = off ? "Show the camera picture" : "Hide the camera picture (saves battery)";
  }

  // ── What the overlay says ──
  function render(note) {
    if (S.recording) {
      const ms = elapsedMs();
      $("recTimer").textContent = clock(ms);
      if (ms >= MAX_MIN * 60000) { autoStop(); return; }
      if (ms >= WARN_MIN * 60000) $("recNote").textContent = `The limit is ${MAX_MIN} minutes: recording stops by itself at ${MAX_MIN}:00.`;
    } else {
      $("recTimer").textContent = clock(elapsedMs());
    }
    if (!S.job || $("recSent").classList.contains("error")) return;
    const sent = S.sentBytes + inflightBytes();
    const waiting = Math.max(0, S.size - sent);
    const r = rate();
    let line;
    if (S.finishing) line = "All sent. Putting the video together…";
    else if (note) line = note;
    else if (!navigator.onLine || S.trouble) line = `${navigator.onLine ? "The signal is weak" : "No signal right now"}: ` +
      `${formatBytes(waiting)} is waiting on this phone and is sent as soon as it gets through.`;
    else if (S.stopped) line = `Sending the last ${formatBytes(waiting)} · ${r ? `${aboutTime(waiting / r)} left` : "working out the time left…"}`;
    else if (!S.pieces) line = "";
    else line = `${formatBytes(sent)} of ${formatBytes(S.size)} sent · ` +
      (S.queue.length + S.active <= 2 ? "keeping up" : r ? `${aboutTime(waiting / r)} behind` : "sending…");
    $("recSent").textContent = line;
  }
  let autoStopping = false;
  async function autoStop() {
    if (autoStopping) return;
    autoStopping = true;
    S.elapsed += Date.now() - S.segStart;
    S.recording = false;
    await S.recorder.stop();
    S.stopped = true;
    save();
    if (S.cam) S.cam.stream.getTracks().forEach((t) => t.stop());
    $("recOverlay").classList.remove("live");
    $("recKicker").textContent = "Match recorded";
    $("recTitle").textContent = `Stopped at ${MAX_MIN} minutes`;
    ["recStartBtn", "recContinueBtn", "recStopBtn"].forEach((id) => $(id).classList.add("hidden"));
    $("recLive").classList.add("off");
    $("toggleLiveBtn").classList.add("hidden");
    $("recNote").textContent = "Keep this page open until it's sent. Your report opens when it's ready.";
    maybeFinish();
  }
  setInterval(() => { if (S.job && !$("recOverlay").classList.contains("hidden")) render(); }, 1000);

  // ── Before recording: camera, still, court ──
  // The button to go on is always shown (it used to vanish below 1080p, leaving nothing
  // to press); only a phone held upright has to be turned first.
  function describe(w, h) {
    const short = Math.min(w, h);
    if (!w || !h) return { ok: false, text: "" };
    if (h > w) return { ok: false, text: "Turn the phone sideways to carry on." };
    if (short >= 2160) return { ok: true, text: "Recording in 4K." };
    if (short >= 1080) return { ok: true, text: `Recording in ${short}p: quick results, a little less accurate than 4K. For the most accurate report, film in 4K with the camera app and upload at home.` };
    return { ok: true, text: `This camera only gives ${short}p here, so the report will be less accurate. For a better report, film in 4K with the camera app and use "Upload video".` };
  }

  async function openCamera() {
    $("openCameraBtn").disabled = true;
    $("recStatus").classList.remove("error");
    $("recStatus").textContent = "Opening the camera…";
    try {
      S.cam = await Recorder.openCamera();
      watchTrack();
      const v = $("recPreview");
      v.srcObject = S.cam.stream;
      v.classList.remove("hidden");
      await v.play().catch(() => {});
      const check = () => {
        const d = describe(v.videoWidth, v.videoHeight);
        $("recQuality").textContent = d.text;
        if (S.job) return;              // already past this step
        $("useViewBtn").disabled = !d.ok;
        $("useViewBtn").textContent = d.ok || !d.text ? "Use this view and mark the court" : "Turn the phone sideways";
      };
      v.addEventListener("resize", check);
      v.addEventListener("loadedmetadata", check);
      check();
      $("recStatus").textContent = "Point the phone at the whole court, then press the button below.";
      $("openCameraBtn").classList.add("hidden");
      $("useViewBtn").classList.remove("hidden");
      $("handsFreeBtn").classList.remove("hidden");
      $("useViewBtn").scrollIntoView({ behavior: "smooth", block: "nearest" });
    } catch (e) {
      $("recStatus").classList.add("error");
      $("recStatus").textContent = e.name === "NotAllowedError"
        ? "The camera wasn't allowed. Allow the camera for this site in your browser settings, then try again."
        : `The camera didn't open: ${e.message}`;
      $("openCameraBtn").disabled = false;
    }
  }

  async function useView() {
    $("useViewBtn").disabled = true;
    $("recStatus").classList.remove("error");
    $("recStatus").textContent = "Getting ready…";
    try {
      const v = $("recPreview");
      const still = await Recorder.still(v);
      const initForm = new FormData();
      initForm.append("mime", Recorder.pickType() || "");
      let res = await fetch(`${backendUrl()}/api/record/init`, { method: "POST", body: initForm });
      if (!res.ok) throw new Error(`could not start (HTTP ${res.status})`);
      const init = await res.json();
      const job = init.job_id;
      useR2(job, init.r2);
      const form = new FormData();
      form.append("file", still, "court.jpg");
      res = await fetch(`${backendUrl()}/api/record/${job}/frame`, { method: "POST", body: form });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
      Object.assign(S, { job, r2: !!init.r2, width: v.videoWidth, height: v.videoHeight, pieces: 0, size: 0, segments: [], elapsed: 0,
        sentCount: 0, sentBytes: 0, stopped: false, finishing: false });
      S.run = { stop: false };
      save();
      // Same court-marking screen as uploads, on the still.
      jobId = job;
      POINT_LABELS = data.point_labels;
      INSTRUCTIONS = { ...data.instructions, ...FRIENDLY_POINTS };
      clickedPoints = {};
      clickOrder = [];
      fit = null;
      v.pause();
      document.querySelector('[data-step="1"] .step-done-note').textContent = "✓ Camera ready.";
      $("submitCalibrationBtn").textContent = "Done: get ready to record";
      $("recStatus").textContent = "";
      setStage($("badge1"), "done");
      setStage($("badge2"), "active");
      $("calibratePanel").classList.remove("hidden");
      $("calibratePanel").scrollIntoView({ behavior: "smooth" });
      showFrame(URL.createObjectURL(still));
      await guessCourt();
      return true;
    } catch (e) {
      $("recStatus").classList.add("error");
      $("recStatus").textContent = `Couldn't get ready: ${e.message}. Check the signal and try again.`;
      $("useViewBtn").disabled = false;
      return false;
    }
  }

  // ── Hands-free (2026-10-29): the phone is up on the fence where nobody can see the screen.
  // Every few seconds a small picture goes to /api/aim (Code/aim_guide.py) and the tip is
  // said out loud. Two "good" answers in a row (the phone has stopped moving) mark the court
  // from the court finder's points, then a spoken countdown starts the recording.
  const HF = { on: false, run: null, lastCode: "", lastSpoke: 0, goods: 0 };
  const AIM_W = 1280, REPEAT_MS = 9000;

  function say(text) {
    $("aimTip").textContent = text;
    if (!("speechSynthesis" in window)) return;
    try {
      speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text);
      u.lang = "en-US";
      u.rate = 1.0;
      speechSynthesis.speak(u);
    } catch (e) { /* the words on screen are enough */ }
  }
  const pause = (ms, run) => new Promise((r) => { const t = setTimeout(r, ms); if (run) run.cancel = () => { clearTimeout(t); r(); }; });

  function aimPicture(video) {
    const k = Math.min(1, AIM_W / video.videoWidth);
    const c = document.createElement("canvas");
    c.width = Math.round(video.videoWidth * k);
    c.height = Math.round(video.videoHeight * k);
    c.getContext("2d").drawImage(video, 0, 0, c.width, c.height);
    return new Promise((resolve) => c.toBlob(resolve, "image/jpeg", 0.85));
  }

  function showHandsFree(on) {
    HF.on = on;
    $("aimTip").classList.toggle("hidden", !on);
    $("handsFreeStopBtn").classList.toggle("hidden", !on);
    $("handsFreeBtn").classList.toggle("hidden", on);
    $("useViewBtn").classList.toggle("hidden", on);
  }

  function stopHandsFree(note) {
    if (HF.run) { HF.run.stop = true; if (HF.run.cancel) HF.run.cancel(); }
    HF.run = null;
    showHandsFree(false);
    if (note) $("recStatus").textContent = note;
    if ("speechSynthesis" in window) speechSynthesis.cancel();
  }

  async function handsFree() {
    if (!S.cam) return;
    const run = { stop: false };
    HF.run = run;
    Object.assign(HF, { lastCode: "", lastSpoke: 0, goods: 0 });
    showHandsFree(true);
    keepAwake(true);
    $("recStatus").textContent = "";
    say("Put the phone up on the fence, sideways, pointing at the court. I'll tell you how to aim it.");   // said inside the tap, so phones allow the voice
    await pause(6000, run);
    while (!run.stop) {
      if (!S.cam || S.cam.track.readyState === "ended") { stopHandsFree("The camera stopped. Press Open camera to try again."); return; }
      let ans = null;
      try {
        const form = new FormData();
        form.append("file", await aimPicture($("recPreview")), "aim.jpg");
        const res = await fetch(`${backendUrl()}/api/aim`, { method: "POST", body: form });
        if (res.ok) ans = await res.json();
      } catch (e) { /* weak signal: try again */ }
      if (run.stop) return;
      if (!ans || !ans.tip) {
        if (Date.now() - HF.lastSpoke > REPEAT_MS) { say("I can't reach the server. Check the signal."); HF.lastSpoke = Date.now(); }
        await pause(3000, run);
        continue;
      }
      HF.goods = ans.ok ? HF.goods + 1 : 0;
      if (HF.goods >= 2) break;
      if (ans.code !== HF.lastCode || Date.now() - HF.lastSpoke > REPEAT_MS) {
        say(ans.tip);
        HF.lastCode = ans.code;
        HF.lastSpoke = Date.now();
      }
      await pause(ans.ok ? 500 : 1500, run);
    }
    if (run.stop) return;
    say("Good spot. Getting ready.");
    $("recPreview").pause();
    const ready = await useView();
    if (run.stop) return;
    if (ready && autoPlaced && !isDoubles()) {
      $("looksRight").checked = true;
      updateInstruction();
      if (!$("submitCalibrationBtn").disabled) {
        HF.marked = false;
        $("submitCalibrationBtn").click();                // -> courtMarked() counts down
        await pause(20000, run);
        if (!run.stop && !HF.marked) { stopHandsFree(""); say("Something went wrong. Please take the phone down and check the screen."); }
        return;
      }
    }
    stopHandsFree("");
    say("Please take the phone down and check the court lines on the screen.");
  }

  async function countdownAndStart() {
    const run = HF.run || { stop: false };
    for (const [n, words] of [[10, "Recording starts in 10 seconds."], [5, "5"], [3, "3"], [2, "2"], [1, "1"]]) {
      if (run.stop || S.recording) return;
      $("recNote").textContent = `Hands-free: recording starts in ${n}…`;
      say(words);
      await pause(n === 10 ? 5000 : n === 5 ? 2000 : 1000, run);
    }
    if (run.stop || S.recording) return;
    await startRecording();
    say("Recording. Good luck!");
    stopHandsFree("");
  }

  // Called by the Home page once /api/calibrate answers "recording".
  function courtMarked() {
    setStage($("badge2"), "done");
    $("recOverlay").classList.remove("hidden");
    document.body.style.overflow = "hidden";
    $("recLive").srcObject = S.cam.stream;
    $("recLive").play().catch(() => {});
    keepAwake(true);
    render();
    $("recStartBtn").focus();
    if (HF.on) { HF.marked = true; countdownAndStart(); }
  }

  // "Not now" on the Ready to record screen: nothing was filmed, so drop it and start again.
  async function cancelBeforeStart() {
    if (!confirm("Leave without recording? You'll need to mark the court again next time.")) return;
    if (S.cam) S.cam.stream.getTracks().forEach((t) => t.stop());
    await discard();
    location.reload();
  }

  function closeCamera() {
    if (S.job || !S.cam) return;
    S.cam.stream.getTracks().forEach((t) => t.stop());
    S.cam = null;
    $("recPreview").classList.add("hidden");
    $("useViewBtn").classList.add("hidden");
    $("recQuality").textContent = "";
    $("recStatus").textContent = "";
    $("openCameraBtn").classList.remove("hidden");
    $("openCameraBtn").disabled = false;
  }

  // ── A recording left unsent when the page closed ──
  async function discard() {
    const p = store.get(REC_KEY);
    if (p && p.jobId) await pieces.clear(p.jobId);
    store.del(REC_KEY);
    S.job = null;
  }

  async function checkUnsent() {
    let p = store.get(REC_KEY);
    if (!p || !p.jobId) return;
    if (!p.pieces) { store.del(REC_KEY); return; }        // marked the court but never filmed
    // Rebuilt from what is on the phone (the saved counts can be one piece behind):
    // pieces = sent + waiting; a gap (a waiting piece numbered past that) means one was lost.
    const waiting = await pieces.list(p.jobId);
    const total = (p.sentCount || 0) + waiting.length;
    const lost = !total || waiting.some((w) => w.i >= total);
    const left = waiting.reduce((a, b) => a + b.size, 0);
    p = { ...p, pieces: total, size: (p.sentBytes || 0) + left };
    setMode(true);
    $("recordResume").classList.remove("hidden");
    $("recordSendBtn").classList.toggle("hidden", lost);
    $("recordResumeText").innerHTML = lost
      ? "<b>Unsent recording:</b> part of it was lost when the page closed, so it can't be sent."
      : `<b>Unsent recording</b> (${clock(p.elapsed || 0)} filmed, ${formatBytes(left)} still to send). ` +
        "Keep the signal on and press Send it now.";
    $("recordSendBtn").onclick = () => resumeSending(p, waiting);
  }

  function resumeSending(p, waiting) {
    useR2(p.jobId, !!p.r2);
    Object.assign(S, { job: p.jobId, r2: !!p.r2, pieces: p.pieces, size: p.size, segments: p.segments || [0], elapsed: p.elapsed || 0,
      sentCount: p.sentCount || 0, stopped: true, recording: false, finishing: false });
    S.sentBytes = p.sentBytes || 0;
    S.run = { stop: false };
    save();
    $("recOverlay").classList.remove("hidden");
    document.body.style.overflow = "hidden";
    $("recKicker").textContent = "Match recorded";
    $("recTitle").textContent = "Sending the video";
    ["recStartBtn", "recContinueBtn", "recStopBtn", "recCancelBtn"].forEach((id) => $(id).classList.add("hidden"));
    $("recLive").classList.add("off");
    $("toggleLiveBtn").classList.add("hidden");
    $("recNote").textContent = "Keep this page open until it's sent. Your report opens when it's ready.";
    keepAwake(true);
    waiting.forEach((w) => enqueue(w.i));
    maybeFinish();
    render();
  }

  // ── Upload / Record choice ──
  const supported = () => ENABLED && !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia) && Recorder.pickType() !== null;
  function setMode(record) {
    $("modeUpload").setAttribute("aria-pressed", String(!record));
    $("modeRecord").setAttribute("aria-pressed", String(record));
    $("uploadMode").classList.toggle("hidden", record);
    $("recordMode").classList.toggle("hidden", !record);
  }

  if (supported()) {
    $("modeSwitch").classList.remove("hidden");
    $("modeUpload").addEventListener("click", () => { if (!busy()) { closeCamera(); setMode(false); } });
    $("modeRecord").addEventListener("click", () => { if (!(upload && upload.running)) setMode(true); });
    $("openCameraBtn").addEventListener("click", openCamera);
    $("useViewBtn").addEventListener("click", useView);
    $("handsFreeBtn").addEventListener("click", handsFree);
    $("handsFreeStopBtn").addEventListener("click", () => stopHandsFree("Hands-free stopped."));
    $("recStartBtn").addEventListener("click", startRecording);
    $("recContinueBtn").addEventListener("click", startRecording);
    $("recCancelBtn").addEventListener("click", cancelBeforeStart);
    $("recStopBtn").addEventListener("click", stopRecording);
    $("toggleLiveBtn").addEventListener("click", toggleLive);
    $("recordDiscardBtn").addEventListener("click", async () => {
      if (!confirm("Discard this recording? It can't be sent afterwards.")) return;
      await discard();
      $("recordResume").classList.add("hidden");
    });
    window.addEventListener("online", () => { if (S.job) pump(); });
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState !== "visible" || !S.job) return;
      if (busy()) keepAwake(true);
      if (S.recording && S.cam && S.cam.track.readyState === "ended") interrupted();
    });
    checkUnsent();
  }

  window.RecordMatch = { busy, courtMarked };
})();
