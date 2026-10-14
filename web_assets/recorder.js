// Records the match from the phone's back camera in the browser, handing over
// small pieces as it goes (so they can be uploaded while play continues).
// Used by "Record match" on Home and by the camera check page (/camera-test).
(() => {
  // Formats the server can turn into a normal video file, best first
  // (iPhone Safari records MP4; Android Chrome records WebM).
  const TYPES = ["video/mp4;codecs=avc1", "video/mp4", "video/webm;codecs=vp9", "video/webm;codecs=vp8", "video/webm"];

  function pickType() {
    if (!window.MediaRecorder) return null;
    return TYPES.find((t) => MediaRecorder.isTypeSupported(t)) || "";
  }

  // Ask for 4K at 30 fps; the phone gives the closest it can.
  async function openCamera() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw new Error("This browser can't use the camera from a web page.");
    }
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: { facingMode: { ideal: "environment" }, width: { ideal: 3840 }, height: { ideal: 2160 }, frameRate: { ideal: 30 } },
    });
    const track = stream.getVideoTracks()[0];
    return { stream, track, settings: track.getSettings() };
  }

  // Bitrate close to what the phone's own camera app uses (~17 Mbps at 4K 30 fps, the size of
  // the footage our accuracy was measured on), so the far-court ball keeps its detail. Browsers
  // default far lower. At least 8 Mbps: 1080p has fewer pixels on the ball to lose.
  function bitrateFor(settings) {
    const w = settings.width || 1920, h = settings.height || 1080, fps = settings.frameRate || 30;
    return Math.round(Math.min(Math.max(w * h * fps * 0.07, 8e6), 25e6));
  }

  // start(stream, onPiece, sliceMs, onEnd) -> {stop(): Promise, type, bitrate}
  // onPiece(blob, index) is called for every piece, in order; the last one arrives before stop() resolves.
  // onEnd() is called if recording stops by itself (camera lost, phone call), not after stop().
  function start(stream, onPiece, sliceMs = 4000, onEnd = null) {
    const type = pickType();
    if (type === null) throw new Error("This browser can't record video from a web page.");
    const settings = stream.getVideoTracks()[0].getSettings();
    const bitrate = bitrateFor(settings);
    const rec = new MediaRecorder(stream, { ...(type ? { mimeType: type } : {}), videoBitsPerSecond: bitrate });
    let index = 0;
    let pending = Promise.resolve();
    rec.addEventListener("dataavailable", (e) => {
      if (!e.data || !e.data.size) return;
      const i = index++;
      pending = pending.then(() => onPiece(e.data, i));   // keep pieces in order
    });
    let byUs = false;
    const stopped = new Promise((resolve) => rec.addEventListener("stop", resolve));
    stopped.then(() => { if (!byUs && onEnd) pending.then(onEnd); });
    rec.addEventListener("error", () => { if (rec.state !== "inactive") rec.stop(); });
    rec.start(sliceMs);
    return {
      type: rec.mimeType || type,
      bitrate,
      get state() { return rec.state; },
      async stop() {
        byUs = true;
        if (rec.state !== "inactive") rec.stop();
        await stopped;
        await pending;
        return index;
      },
    };
  }

  // A still picture from the live preview at full camera size (used to mark the court).
  function still(video) {
    const c = document.createElement("canvas");
    c.width = video.videoWidth;
    c.height = video.videoHeight;
    c.getContext("2d").drawImage(video, 0, 0);
    return new Promise((resolve) => c.toBlob(resolve, "image/jpeg", 0.92));
  }

  window.Recorder = { pickType, openCamera, start, still, bitrateFor };
})();
