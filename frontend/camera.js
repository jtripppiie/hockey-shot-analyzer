/*
 * camera.js — In-app camera capture (SKELETON).
 *
 * Phase 1 of the live-capture roadmap: record an attempt with the laptop/phone
 * camera instead of selecting a file, then hand the recorded blob to the EXISTING
 * upload path (window.uploadFile → POST /analyze). No backend change required.
 *
 * See docs/ROADMAP-live-capture-session-report.md (Phase 1).
 *
 * This is a SKELETON: getUserMedia + MediaRecorder wiring is real and works, but
 * the UX is deliberately minimal (start/stop, live preview, then analyze). Polish
 * — countdown, framing guide, re-take, max length, mobile facing-mode toggle — is
 * left as TODOs. Auto-segmentation of a long recording into multiple attempts is
 * a LATER phase (Phase 3) and intentionally NOT done here.
 */

(function () {
  "use strict";

  let mediaStream = null;
  let recorder = null;
  let chunks = [];

  function $(id) { return document.getElementById(id); }

  function supported() {
    return !!(navigator.mediaDevices &&
              navigator.mediaDevices.getUserMedia &&
              window.MediaRecorder);
  }

  // Pick a container/codec the browser actually supports. MP4 is preferred so the
  // backend sees a familiar extension; fall back to WebM (the analyzer reads it
  // via OpenCV/ffmpeg either way).
  function pickMimeType() {
    const candidates = [
      "video/mp4",
      "video/webm;codecs=vp9",
      "video/webm;codecs=vp8",
      "video/webm",
    ];
    for (const t of candidates) {
      if (window.MediaRecorder.isTypeSupported &&
          window.MediaRecorder.isTypeSupported(t)) {
        return t;
      }
    }
    return "";
  }

  async function openCamera() {
    if (!supported()) {
      alert("Camera capture isn't supported in this browser.");
      return;
    }
    try {
      // TODO(Phase 1): facingMode toggle for phones (user vs environment).
      // TODO(Phase 1): let the user pick a device from enumerateDevices().
      mediaStream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 1920 }, height: { ideal: 1080 } },
        audio: false,
      });
    } catch (err) {
      alert("Couldn't access the camera: " + (err && err.message ? err.message : err));
      return;
    }
    const preview = $("camPreview");
    if (preview) {
      preview.srcObject = mediaStream;
      preview.play().catch(() => {});
    }
    _setState("ready");
  }

  function startRecording() {
    if (!mediaStream) return;
    chunks = [];
    const mimeType = pickMimeType();
    try {
      recorder = mimeType
        ? new MediaRecorder(mediaStream, { mimeType })
        : new MediaRecorder(mediaStream);
    } catch (err) {
      alert("Couldn't start recording: " + (err && err.message ? err.message : err));
      return;
    }
    recorder.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };
    recorder.onstop = _onRecordingStopped;
    recorder.start();
    _setState("recording");
    // TODO(Phase 1): max-length auto-stop + visible elapsed timer.
  }

  function stopRecording() {
    if (recorder && recorder.state !== "inactive") recorder.stop();
    _setState("processing");
  }

  function _onRecordingStopped() {
    const type = (recorder && recorder.mimeType) || "video/webm";
    const blob = new Blob(chunks, { type });
    chunks = [];
    const ext = type.indexOf("mp4") !== -1 ? "mp4" : "webm";
    const file = new File([blob], `camera_${Date.now()}.${ext}`, { type });

    _closeStream();

    // Hand off to the existing analyze pipeline. uploadFile lives in app.js and
    // is global; it builds the FormData and POSTs to /analyze.
    if (typeof window.uploadFile === "function") {
      window.uploadFile(file);
    } else {
      alert("Recorded clip is ready but the upload handler wasn't found.");
    }
    // TODO(Phase 2): instead of analyzing immediately, offer "add to session" so
    // several recorded attempts roll up into one session report.
  }

  function _closeStream() {
    if (mediaStream) {
      mediaStream.getTracks().forEach((t) => t.stop());
      mediaStream = null;
    }
    const preview = $("camPreview");
    if (preview) preview.srcObject = null;
  }

  function cancelCamera() {
    if (recorder && recorder.state !== "inactive") {
      try { recorder.stop(); } catch (_) {}
    }
    recorder = null;
    chunks = [];
    _closeStream();
    _setState("idle");
  }

  // Drives which controls are visible. The matching markup lives in index.html
  // (id="cameraPanel" with [data-cam-state] children). SKELETON: if the markup
  // isn't present yet this is a harmless no-op.
  function _setState(state) {
    const panel = $("cameraPanel");
    if (panel) panel.setAttribute("data-cam-state", state);
  }

  // Expose a tiny API for index.html buttons / app.js to call.
  window.HockeyCamera = {
    supported,
    open: openCamera,
    start: startRecording,
    stop: stopRecording,
    cancel: cancelCamera,
  };
})();
