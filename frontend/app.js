/* app.js — Hockey Shot Analyzer frontend logic */

const API = "";  // same origin — FastAPI serves frontend

// Tracks the currently-displayed job
let currentJob = null;

const ERROR_MESSAGES = {
  video_too_short:  { icon: "⏱️", title: "Clip too short", body: "The video needs to be at least a few seconds long. Record the full shot — setup, release and follow-through." },
  video_too_long:   { icon: "📏", title: "Clip too long", body: "Keep the clip to 5–10 seconds — one shot only. Trim it down and try again." },
  video_unreadable: { icon: "📂", title: "Can't read this file", body: "The video file appears to be corrupted or in an unsupported format. Try exporting it as MP4 and uploading again." },
  no_body_detected: { icon: "👀", title: "Couldn't find a player", body: "The AI couldn't see anyone in this clip. Check that:\n• The player fills most of the frame\n• Lighting is bright and even\n• The camera is at a side angle (not front-on)\n• There's no one else crossing the frame" },
  poor_detection:   { icon: "⚠️", title: "Hard to see the player", body: "The AI could only track the player in part of the clip. For better results:\n• Use brighter lighting\n• Film from the side (15–45°)\n• Make sure the full body is in frame the whole time\n• Avoid busy backgrounds" },
  metrics_failed:   { icon: "🔢", title: "Couldn't calculate scores", body: "Landmarks were found but angles couldn't be computed. Make sure the full body (head to ankles) is visible throughout the shot." },
  server_error:     { icon: "🛠️", title: "Something went wrong", body: "An unexpected error occurred on the server. Try a different clip, or restart the app." },
  youtube_download_failed: { icon: "📺", title: "Couldn't grab that clip", body: "YouTube blocked the download or the video is private/region-locked. Try a different link, or download it manually and upload the file." },
};

function showError(code) {
  // Codes may come with a colon suffix (e.g. "youtube_download_failed: bad url")
  const baseCode = typeof code === "string" ? code.split(":")[0].trim() : code;
  const msg = ERROR_MESSAGES[baseCode] || { icon: "❌", title: "Error", body: code };
  const overlay = document.createElement("div");
  overlay.style.cssText = "position:fixed;inset:0;background:rgba(0,0,0,0.7);display:flex;align-items:center;justify-content:center;z-index:999";
  overlay.innerHTML = `
    <div style="background:#161b22;border:1px solid #30363d;border-radius:14px;padding:36px;max-width:440px;text-align:center">
      <div style="font-size:3rem;margin-bottom:12px">${msg.icon}</div>
      <h2 style="margin-bottom:12px;color:#e6edf3">${msg.title}</h2>
      <p style="color:#8b949e;white-space:pre-line;line-height:1.7;margin-bottom:24px">${msg.body}</p>
      <button class="btn-primary" onclick="this.closest('div[style]').remove();resetUI()">Try Again</button>
    </div>
  `;
  document.body.appendChild(overlay);
}

const METRIC_META = {
  knee_bend:         { icon: "🦵", label: "Knee Bend",          unit: "°" },
  hip_rotation:      { icon: "🌀", label: "Hip Rotation",       unit: "°" },
  shoulder_rotation: { icon: "🏒", label: "Shoulder Rotation",  unit: "°" },
  weight_transfer:   { icon: "⚖️", label: "Weight Transfer",    unit: "" },
  follow_through:    { icon: "🎯", label: "Follow-Through",     unit: "" },
  head_stability:    { icon: "👤", label: "Head Stability",     unit: "" },
  release_timing:    { icon: "⚡", label: "Release Timing",     unit: " ms" },
};

function gradeClass(grade) {
  if (!grade) return "grade-unmeasured";
  return "grade-" + grade.replace(" ", "-");
}

// Shared metric-card renderer (handles unmeasured / null score cleanly)
function _metricCardHtml(key, meta, m, isPriority = false) {
  const isUnmeasured = m.status === "unmeasured" || m.score == null;
  if (isUnmeasured) {
    return `
      <div class="metric-card metric-unmeasured">
        <div class="metric-header">
          <span class="metric-icon">${meta.icon}</span>
          <span class="metric-name">${meta.label}</span>
          <span class="metric-grade grade-unmeasured">couldn't measure</span>
        </div>
        <p class="metric-tip metric-unmeasured-reason">${m.reason || "Not enough data in this clip."}</p>
        <p class="metric-tip">${m.tip || ""}</p>
      </div>`;
  }
  const color = scoreColor(m.score);
  const valueStr = (m.value != null && meta.unit !== undefined)
    ? `<span class="metric-value-line">measured: ${typeof m.value === "number" ? Math.round(m.value * 10) / 10 : m.value}${meta.unit}</span>`
    : "";
  const klass = isPriority ? "metric-card metric-priority" : "metric-card";
  return `
    <div class="${klass}">
      <div class="metric-header">
        <span class="metric-icon">${meta.icon}</span>
        <span class="metric-name">${meta.label}</span>
        <span class="metric-grade ${gradeClass(m.grade)}">${m.grade}</span>
      </div>
      <div class="metric-bar-wrap">
        <div class="metric-bar" style="width:0%;background:${color}" data-target="${m.score}"></div>
      </div>
      <span class="metric-score" style="color:${color}">${m.score}</span>
      <span style="color:var(--muted);font-size:0.85rem"> / 100</span>
      ${valueStr}
      <p class="metric-tip">${m.tip}</p>
    </div>`;
}

// Hero summary band + tagline (results screen)
function _renderHeroSummary(data) {
  const bandEl = document.getElementById("overallBand");
  const lineEl = document.getElementById("overallTagline");
  if (!bandEl || !lineEl) return;
  const overall = data.summary?.overall;
  if (overall == null) {
    bandEl.textContent = "";
    lineEl.textContent = "";
    return;
  }
  const allMetrics = Object.entries(data.metrics || {})
    .filter(([, m]) => m && m.score != null && m.status !== "unmeasured");
  const strengths = allMetrics.filter(([, m]) => m.score >= 75)
    .sort((a, b) => b[1].score - a[1].score);
  const focus = allMetrics.filter(([, m]) => m.score < 75)
    .sort((a, b) => a[1].score - b[1].score);
  const strongLabel = strengths[0]?.[1]?.coaching?.label || strengths[0]?.[0]?.replace(/_/g, " ");
  const focusLabel  = focus[0]?.[1]?.coaching?.label    || focus[0]?.[0]?.replace(/_/g, " ");
  let band;
  if (overall >= 85)      band = "Elite Form";
  else if (overall >= 70) band = "Solid Foundation";
  else if (overall >= 50) band = "Building Up";
  else if (overall >= 30) band = "Early Days";
  else                    band = "Just Starting";
  let tagline;
  if (strongLabel && focusLabel)
    tagline = `Strong ${strongLabel.toLowerCase()}. Focus on ${focusLabel.toLowerCase()} for the biggest gain.`;
  else if (focusLabel)
    tagline = `Biggest opportunity: ${focusLabel.toLowerCase()}.`;
  else if (strongLabel)
    tagline = `Everything we could measure looks strong — nice work on ${strongLabel.toLowerCase()}.`;
  else
    tagline = "Couldn't measure enough of this clip to score reliably — see the quality banner above.";
  bandEl.textContent = band.toUpperCase();
  bandEl.style.color = scoreColor(overall);
  lineEl.textContent = tagline;
}

// Quality / data-confidence banner
function _renderQualityBanner(q) {
  let el = document.getElementById("qualityBanner");
  if (!el) {
    el = document.createElement("div");
    el.id = "qualityBanner";
    el.className = "quality-banner hidden";
    const results = document.getElementById("resultsSection");
    const topbar = results?.querySelector(".topbar");
    const actions = topbar?.querySelector(".topbar-actions");
    if (topbar) topbar.insertBefore(el, actions || null);
    else if (results) results.insertBefore(el, results.firstChild);
  }
  if (!q) { el.classList.add("hidden"); return; }

  const warnings = Array.isArray(q.warnings) ? q.warnings : [];
  const measured = q.measured_metrics ?? null;
  const total = q.total_metrics ?? null;
  const view = q.camera_view;
  const hand = q.dominant_hand;

  let viewBadge = "";
  if (view === "side") viewBadge = `<span class="qb-good">\u2705 side-view clip</span>`;
  else if (view === "angled") viewBadge = `<span class="qb-warn">\u26a0\ufe0f angled view \u2014 some metrics may be off</span>`;
  else if (view) viewBadge = `<span class="qb-warn">\u26a0\ufe0f ${view.replace(/_/g, " ")} view \u2014 re-film from the side for full analysis</span>`;

  const handBadge = hand ? `<span class="qb-info">\ud83c\udfd2 detected: ${hand}-handed shooter</span>` : "";
  const measuredBadge = (measured != null && total != null)
    ? `<span class="${measured === total ? "qb-good" : "qb-warn"}">\ud83d\udcca measured ${measured} of ${total} metrics reliably</span>`
    : "";

  const warnHtml = warnings.length
    ? `<ul class="qb-warnings">${warnings.map(w => `<li>${w}</li>`).join("")}</ul>` : "";

  el.innerHTML = `
    <div class="qb-row">${viewBadge}${handBadge}${measuredBadge}</div>
    ${warnHtml}
  `;
  el.classList.remove("hidden");
}

function scoreColor(score) {
  if (score >= 80) return "#3fb950";   // green
  if (score >= 55) return "#58a6ff";   // blue
  if (score >= 35) return "#d29922";   // amber
  return "#f85149";                     // red
}

// ── Drag & drop ──────────────────────────────────────────────────────────────
const dropZone  = document.getElementById("dropZone");
const fileInput = document.getElementById("fileInput");

dropZone.addEventListener("dragover",  e => { e.preventDefault(); dropZone.classList.add("dragover"); });
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("dragover"));
dropZone.addEventListener("drop", e => {
  e.preventDefault();
  dropZone.classList.remove("dragover");
  const file = e.dataTransfer.files[0];
  if (file) uploadFile(file);
});

fileInput.addEventListener("change", () => {
  if (fileInput.files[0]) uploadFile(fileInput.files[0]);
});

// ── Window-wide drag/drop (works from results & history pages) ───────────────
const winOverlay = document.getElementById("windowDragOverlay");
let dragCounter = 0;
window.addEventListener("dragenter", e => {
  if (!e.dataTransfer || !e.dataTransfer.types.includes("Files")) return;
  e.preventDefault();
  dragCounter++;
  winOverlay.classList.remove("hidden");
});
window.addEventListener("dragover", e => {
  if (e.dataTransfer && e.dataTransfer.types.includes("Files")) e.preventDefault();
});
window.addEventListener("dragleave", e => {
  dragCounter = Math.max(0, dragCounter - 1);
  if (dragCounter === 0) winOverlay.classList.add("hidden");
});
window.addEventListener("drop", e => {
  e.preventDefault();
  dragCounter = 0;
  winOverlay.classList.add("hidden");
  const file = e.dataTransfer && e.dataTransfer.files[0];
  if (file) uploadFile(file);
});

// ── Upload & analyze ─────────────────────────────────────────────────────────
async function uploadFile(file) {
  const form = new FormData();
  form.append("file", file);
  const mb = file.size / 1024 / 1024;
  const initialMsg = mb > 200
    ? `Uploading ${mb.toFixed(0)} MB — this may take a minute…`
    : "Uploading clip…";
  await _submitAnalyze("/analyze", form, initialMsg);
}

async function submitYouTube() {
  const url = document.getElementById("ytUrl").value.trim();
  const start = document.getElementById("ytStart").value.trim();
  const end = document.getElementById("ytEnd").value.trim();
  if (!url) {
    showError("Please paste a YouTube URL first");
    return;
  }
  if (!/youtube\.com|youtu\.be/i.test(url)) {
    showError("That doesn't look like a YouTube link");
    return;
  }
  const form = new FormData();
  form.append("url", url);
  form.append("start", start);
  form.append("end", end);
  await _submitAnalyze("/analyze-youtube", form, "Downloading YouTube clip…");
}

// ── Player profile (optional, persisted locally) ───────────────────────────
const PLAYER_PROFILE_KEY = "hockeyPlayerProfile.v1";
const PLAYER_PROFILE_FIELDS = ["profileName", "profileAge", "profileShoots", "profilePosition"];

function _readPlayerProfile() {
  const profile = {};
  for (const id of PLAYER_PROFILE_FIELDS) {
    const el = document.getElementById(id);
    if (!el) continue;
    const value = (el.value || "").trim();
    if (value !== "") profile[id] = value;
  }
  return profile;
}

function _savePlayerProfile() {
  const profile = _readPlayerProfile();
  if (Object.keys(profile).length === 0) localStorage.removeItem(PLAYER_PROFILE_KEY);
  else localStorage.setItem(PLAYER_PROFILE_KEY, JSON.stringify(profile));
  const status = document.getElementById("profileStatus");
  if (status) {
    status.textContent = "Saved";
    clearTimeout(_savePlayerProfile._t);
    _savePlayerProfile._t = setTimeout(() => { status.textContent = ""; }, 1200);
  }
}

function _loadPlayerProfile() {
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(PLAYER_PROFILE_KEY) || "{}"); }
  catch (e) { saved = {}; }
  for (const id of PLAYER_PROFILE_FIELDS) {
    const el = document.getElementById(id);
    if (el && saved[id] != null) el.value = saved[id];
  }
}

function togglePlayerProfile() {
  const card = document.getElementById("playerProfile");
  const btn = document.getElementById("playerProfileBtn");
  if (!card) return;
  const open = !card.classList.contains("profile-open");
  card.classList.toggle("profile-open", open);
  card.open = open;
  if (btn) btn.setAttribute("aria-expanded", open ? "true" : "false");
}

function clearPlayerProfile() {
  for (const id of PLAYER_PROFILE_FIELDS) {
    const el = document.getElementById(id);
    if (el) el.value = "";
  }
  localStorage.removeItem(PLAYER_PROFILE_KEY);
  const status = document.getElementById("profileStatus");
  if (status) { status.textContent = "Cleared"; setTimeout(() => { status.textContent = ""; }, 1200); }
}

window.addEventListener("DOMContentLoaded", () => {
  _loadPlayerProfile();
  for (const id of PLAYER_PROFILE_FIELDS) {
    const el = document.getElementById(id);
    if (el) el.addEventListener("change", _savePlayerProfile);
  }
});

async function _submitAnalyze(endpoint, form, initialMsg) {
  showSection("progressSection");
  setProgress(10, initialMsg);

  setProgress(25, "Running pose detection… (may take 30–60 seconds)");
  let fakePct = 25;
  const fakeTimer = setInterval(() => {
    if (fakePct < 85) {
      fakePct += (85 - fakePct) * 0.04;
      document.getElementById("progressFill").style.width = fakePct + "%";
    }
  }, 800);
  let data;
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 300000);
    const resp = await fetch(`${API}${endpoint}`, {
      method: "POST",
      body: form,
      signal: controller.signal,
    });
    clearTimeout(timeoutId);
    clearInterval(fakeTimer);
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: "server_error" }));
      showError(err.detail || "server_error");
      resetUI();
      return;
    }
    setProgress(80, "Computing scores…");
    data = await resp.json();
  } catch (e) {
    clearInterval(fakeTimer);
    if (e.name === "AbortError") {
      showError("video_too_long");
    } else {
      showError("server_error");
    }
    resetUI();
    return;
  }

  setProgress(100, "Done!");
  setTimeout(() => renderResults(data), 300);
}

function setProgress(pct, msg) {
  document.getElementById("progressFill").style.width = pct + "%";
  document.getElementById("progressMsg").textContent = msg;
}

// ── Background render polling ─────────────────────────────────────────────────
function _pollPoster(videoEl, url, maxTries) {
  // Key frame becomes the video poster as soon as it's ready.
  let tries = 0;
  const check = () => {
    fetch(url, { method: "HEAD" }).then(r => {
      if (r.ok) {
        videoEl.poster = url + "?t=" + Date.now();
      } else if (++tries < maxTries) {
        setTimeout(check, 2000);
      }
    }).catch(() => { if (++tries < maxTries) setTimeout(check, 2000); });
  };
  check();
}

function _pollVideo(videoEl, url, maxTries) {
  const statusEl = document.getElementById("videoStatus");
  const sourceEl = document.getElementById("overlayVideoSource");
  let tries = 0;
  const check = () => {
    fetch(url, { method: "HEAD" }).then(r => {
      if (r.ok) {
        const fullUrl = url + "?t=" + Date.now();
        if (sourceEl) {
          sourceEl.src = fullUrl;
        } else {
          videoEl.src = fullUrl;
        }
        videoEl.load();
        if (statusEl) statusEl.textContent = "▶ Press play to watch your skeleton overlay";
      } else if (++tries < maxTries) {
        setTimeout(check, 3000);
      } else if (statusEl) {
        statusEl.textContent = "⚠️ Overlay video didn't render — try a shorter clip";
      }
    }).catch(() => { if (++tries < maxTries) setTimeout(check, 3000); });
  };
  setTimeout(check, 4000);
}

function _isDebugResultsMode() {
  const params = new URLSearchParams(window.location.search);
  const host = window.location.hostname;
  const allowedHost = ["localhost", "127.0.0.1", ""].includes(host) || host.endsWith(".trycloudflare.com");
  return params.get("debugResults") === "1" && allowedHost;
}

function _debugMetric(score, grade, value, tip, label, why, drill) {
  return {
    score,
    grade,
    value,
    tip,
    coaching: { label, tier: grade, tip, why, drill },
  };
}

function _debugResultsData() {
  return {
    job_id: "debug-hockey",
    filename: "debug-shot-dashboard.mp4",
    frame_url: "",
    video_url: "",
    debug: true,
    summary: { overall: 72, power: 78, technique: 66, timing: 74 },
    quality_report: {
      camera_view: "side",
      dominant_hand: "right",
      measured_metrics: 6,
      total_metrics: 7,
      warnings: ["Debug fixture: no upload or backend analysis was run."],
    },
    metrics: {
      knee_bend: _debugMetric(82, "good", 118, "Good load depth. Keep the knees active without sitting too low.", "Knee Bend", "A strong knee load helps create power before release.", "Do 3 sets of 10 slow load-and-release reps, pausing at your deepest knee bend."),
      hip_rotation: _debugMetric(69, "ok", 42, "Start the hips a little earlier so the shot is not mostly arms.", "Hip Rotation", "Earlier hip rotation links your lower body to the stick path.", "Take 20 half-speed shots focused only on opening the hips before the hands fire."),
      shoulder_rotation: _debugMetric(76, "good", 58, "Shoulders are rotating well. Keep them stacked over the puck lane.", "Shoulder Rotation", "Clean shoulder rotation keeps the blade moving through the target line.", "Use a pause-at-load drill, then rotate shoulders through the shot on command."),
      weight_transfer: _debugMetric(61, "ok", 64, "Push more fully from the back skate into the front side.", "Weight Transfer", "Better transfer turns the body load into puck speed.", "Shoot 15 pucks while exaggerating the back-foot push and front-side brace."),
      follow_through: _debugMetric(84, "good", 88, "Follow-through is strong and pointed toward the target.", "Follow-Through", "A complete finish keeps direction and power through contact.", "Place a target high corner and freeze your finish for one second after every shot."),
      head_stability: _debugMetric(73, "ok", 71, "Head is mostly stable. Keep eyes quieter through release.", "Head Stability", "A quiet head makes the release more repeatable.", "Take 10 shots while tracking the puck until after contact, then check your finish."),
      release_timing: { status: "unmeasured", score: null, reason: "Debug fixture leaves one metric unmeasured.", tip: "This lets you see the unmeasured card state while designing." },
    },
  };
}

// ── Render results ────────────────────────────────────────────────────────────
function renderResults(data) {
  currentJob = data;
  showSection("resultsSection");

  // Video — keyframe becomes poster, then src is set when overlay video is ready
  const video = document.getElementById("overlayVideo");
  const source = document.getElementById("overlayVideoSource");
  if (source) source.removeAttribute("src");
  video.removeAttribute("poster");
  video.load();
  const statusEl = document.getElementById("videoStatus");
  if (data.debug) {
    if (statusEl) statusEl.textContent = "Debug fixture: no overlay video loaded.";
  } else {
    if (statusEl) statusEl.textContent = "⏳ Building overlay video…";
    _pollPoster(video, data.frame_url, 30);
    _pollVideo(video, data.video_url, 60);
  }

  // Overall badge
  const s = data.summary;
  const overallEl = document.getElementById("overallNum");
  overallEl.textContent = s.overall == null ? "—" : s.overall;
  overallEl.style.color = scoreColor(s.overall || 0);

  // Hero band + tagline (derived from score band + coach report)
  _renderHeroSummary(data);

  document.getElementById("powerNum").textContent     = s.power     == null ? "—" : s.power;
  document.getElementById("techniqueNum").textContent = s.technique == null ? "—" : s.technique;
  document.getElementById("timingNum").textContent    = s.timing    == null ? "—" : s.timing;

  document.getElementById("sub-power").querySelector(".sub-val").style.color     = scoreColor(s.power     || 0);
  document.getElementById("sub-technique").querySelector(".sub-val").style.color = scoreColor(s.technique || 0);
  document.getElementById("sub-timing").querySelector(".sub-val").style.color    = scoreColor(s.timing    || 0);

  const fnEl = document.getElementById("filenameLabel");
  if (fnEl) fnEl.textContent = data.filename || "";

  // Data-quality banner (camera angle warnings, unmeasured metrics, etc.)
  _renderQualityBanner(data.quality_report);

  // Metric cards — sorted weakest-first; top card flagged as priority
  const grid = document.getElementById("metricGrid");
  grid.innerHTML = "";
  const measured = Object.entries(METRIC_META)
    .map(([key, meta]) => [key, meta, data.metrics[key]])
    .filter(([, , m]) => m);
  const measuredScored = measured.filter(([, , m]) => m.score != null && m.status !== "unmeasured");
  const unmeasured     = measured.filter(([, , m]) => m.score == null || m.status === "unmeasured");
  measuredScored.sort((a, b) => (a[2].score ?? 999) - (b[2].score ?? 999));
  const topPriorityKey = measuredScored.length && measuredScored[0][2].score < 75 ? measuredScored[0][0] : null;
  for (const [key, meta, m] of [...measuredScored, ...unmeasured]) {
    grid.insertAdjacentHTML("beforeend", _metricCardHtml(key, meta, m, key === topPriorityKey));
  }

  // Animate bars
  requestAnimationFrame(() => {
    document.querySelectorAll(".metric-bar").forEach(bar => {
      bar.style.width = bar.dataset.target + "%";
    });
  });

  // ── Coach's Report ─────────────────────────────────────────────────────────
  document.getElementById("coachStrengths").innerHTML = "";
  document.getElementById("coachFocus").innerHTML = "";
  document.getElementById("coachDrills").innerHTML = "";

  const parts = _buildCoachReportParts(data);
  document.getElementById("coachStrengths").innerHTML =
    parts.encouragement + parts.topPriority + parts.strengths;
  document.getElementById("coachFocus").innerHTML = parts.focus;
  document.getElementById("coachDrills").innerHTML = parts.drills;
}

window.addEventListener("DOMContentLoaded", () => {
  if (_isDebugResultsMode()) renderResults(_debugResultsData());
});

// ── History ───────────────────────────────────────────────────────────────────
async function showHistory() {
  showSection("historySection");
  document.getElementById("historyDetail").classList.add("hidden");
  document.getElementById("historyList").classList.remove("hidden");

  const rows = await fetch(`${API}/history`).then(r => r.json()).catch(() => []);
  const listEl = document.getElementById("historyList");
  listEl.innerHTML = "";

  if (!rows.length) {
    listEl.innerHTML = `<div class="history-empty">No shots analyzed yet.<br>Upload a clip to get started!</div>`;
    return;
  }

  [...rows].reverse().forEach(row => {
    const scoreColor_ = scoreColor(+row.overall);
    const card = document.createElement("div");
    card.className = "history-card";
    card.innerHTML = `
      <img class="history-thumb" src="/output/${row.job_id}_frame.jpg" onerror="this.outerHTML='<div class=\'history-thumb-placeholder\'>🏒</div>'" />
      <div class="history-body">
        <div class="history-filename" title="${row.filename}">${row.filename}</div>
        <div class="history-date">${row.date}</div>
        <div class="history-score-row">
          <div class="history-score-big" style="color:${scoreColor_}">${row.overall}</div>
          <div class="history-pills">
            <span class="history-pill" style="color:#58a6ff">💪 ${row.power}</span>
            <span class="history-pill" style="color:#3fb950">🎯 ${row.technique}</span>
            <span class="history-pill" style="color:#d29922">⚡ ${row.timing}</span>
          </div>
        </div>
      </div>
      <button class="history-delete" title="Delete this shot" onclick="deleteHistoryItem(event,'${row.job_id}')">🗑</button>
    `;
    card.addEventListener("click", (e) => {
      if (e.target.closest(".history-delete")) return;
      openHistoryDetail(row.job_id);
    });
    listEl.appendChild(card);
  });
}

async function openHistoryDetail(jobId) {
  const data = await fetch(`${API}/history/${jobId}`).then(r => r.json()).catch(() => null);
  if (!data) { alert("Could not load this shot's details."); return; }

  currentJob = data;

  document.getElementById("historyList").classList.add("hidden");
  const detail = document.getElementById("historyDetail");
  detail.classList.remove("hidden");
  const content = document.getElementById("historyDetailContent");
  content.innerHTML = "";

  // Build metric cards HTML for the right-side breakdown
  let metricCards = "";
  for (const [key, meta_] of Object.entries(METRIC_META)) {
    const m = data.metrics[key];
    if (!m) continue;
    metricCards += _metricCardHtml(key, meta_, m);
  }

  const fakeSection = document.createElement("div");
  fakeSection.innerHTML = `
    <div class="results-top">
      <div class="left-panel">
        <h3>Skeleton Overlay</h3>
        <video controls loop playsinline preload="metadata"
               poster="${data.frame_url}?t=${Date.now()}"
               src="${data.video_url}"
               style="width:100%;max-height:55vh;border-radius:8px;background:#000;object-fit:contain"></video>
        <div class="overall-badge">
          <span class="overall-label">Shot Score</span>
          <span class="overall-num" style="color:${scoreColor(data.summary.overall || 0)}">${data.summary.overall ?? "\u2014"}</span>
          <span class="overall-100">/ 100</span>
        </div>
        <div class="sub-scores">
          <div class="sub-score"><span class="sub-icon">\ud83d\udcaa</span><span class="sub-label">Power</span><span class="sub-val" style="color:${scoreColor(data.summary.power || 0)}">${data.summary.power ?? "\u2014"}</span></div>
          <div class="sub-score"><span class="sub-icon">\ud83c\udfaf</span><span class="sub-label">Technique</span><span class="sub-val" style="color:${scoreColor(data.summary.technique || 0)}">${data.summary.technique ?? "\u2014"}</span></div>
          <div class="sub-score"><span class="sub-icon">\u26a1</span><span class="sub-label">Timing</span><span class="sub-val" style="color:${scoreColor(data.summary.timing || 0)}">${data.summary.timing ?? "\u2014"}</span></div>
        </div>
        <p class="filename-label">📁 ${data.filename}<br>${data.date || ""}</p>
      </div>
      <div class="breakdown-panel">
        <h3 class="section-title section-title-inline">Shot Breakdown</h3>
        <div class="metric-grid metric-grid-side">${metricCards}</div>
      </div>
    </div>
  `;
  content.appendChild(fakeSection);

  // Coach report
  _renderCoachReport(content, data);
}

function _renderCoachReport(container, data) {
  const parts = _buildCoachReportParts(data);

  const h = document.createElement("h3");
  h.className = "section-title";
  h.textContent = "🏒 Coach's Report";
  container.appendChild(h);

  const intro = document.createElement("div");
  intro.className = "coach-block strengths";
  intro.innerHTML = parts.encouragement + parts.topPriority + parts.strengths;
  container.appendChild(intro);

  const f = document.createElement("div");
  f.className = "coach-block focus";
  f.innerHTML = parts.focus;
  container.appendChild(f);

  const drillsWrap = document.createElement("div");
  drillsWrap.className = "coach-drills";
  drillsWrap.innerHTML = parts.drills;
  container.appendChild(drillsWrap);
}

// Shared builder for the coach report (used by live results AND history detail).
// We deliberately give kids LOTS of feedback — a kid wants to know exactly what
// to try next, not just a number. So: encouragement banner + top-priority
// callout + every strength + every focus area + drill cards for every focus.
function _buildCoachReportParts(data) {
  // Exclude unmeasured metrics from praise/critique \u2014 we don't praise OR
  // ding what we couldn't measure. They're surfaced separately in the quality
  // banner, and individual cards still explain why.
  const allMetrics = Object.entries(data.metrics)
    .filter(([, m]) => m && m.score != null && m.status !== "unmeasured");
  const strengths  = allMetrics.filter(([, m]) => m.score >= 75).sort((a,b) => b[1].score - a[1].score);
  const focusAreas = allMetrics.filter(([, m]) => m.score < 75).sort((a,b) => a[1].score - b[1].score);
  const overall    = data.summary?.overall ?? 0;

  const enc = _encouragement(overall, strengths.length);
  const encouragement = `
    <div class="coach-encourage">
      <span class="coach-encourage-emoji">${enc.emoji}</span>
      <div>
        <div class="coach-encourage-title">${enc.title}</div>
        <div class="coach-encourage-body">${enc.body}</div>
      </div>
    </div>`;

  let topPriority = "";
  if (focusAreas.length) {
    const [topKey, topMetric] = focusAreas[0];
    const c = topMetric.coaching;
    topPriority = `
      <div class="coach-priority">
        <div class="coach-priority-label">🔥 Next Time, Try This First</div>
        <div class="coach-priority-title">${METRIC_META[topKey]?.icon || "🏒"} ${c.label}</div>
        <div class="coach-priority-tip">${c.tip}</div>
        <div class="coach-priority-why"><strong>Why it matters:</strong> ${c.why}</div>
      </div>`;
  }

  let strengthsHtml = "";
  if (strengths.length) {
    strengthsHtml = `<h4>✅ What You Did Great</h4><ul>${
      strengths.map(([k, m]) => `
        <li>
          <strong>${METRIC_META[k]?.icon || "🏒"} ${m.coaching.label}:</strong>
          ${m.coaching.tip}
        </li>`).join("")
    }</ul>`;
  }

  const focus = focusAreas.length
    ? `<h4>🎯 Things to Work On</h4>
       <p class="coach-intro">Don't stress — every pro had a list like this once. Pick one and try it on your next shot.</p>
       <ul>${focusAreas.map(([k, m]) => `
         <li>
           <strong>${METRIC_META[k]?.icon || "🏒"} ${m.coaching.label}:</strong>
           ${m.coaching.tip}
         </li>`).join("")}</ul>`
    : `<h4>🎯 Things to Work On</h4>
       <p style="color:var(--muted)">Nothing major — you're dialled in! Keep doing what you're doing and challenge yourself with harder shots (off-balance, one-timers, from your off-wing).</p>`;

  const drillTargets = focusAreas.length ? focusAreas : strengths.slice(0, 3);
  const drills = drillTargets.map(([key, m]) => {
    const c = m.coaching;
    const tierColor = { great: "#3fb950", good: "#58a6ff", ok: "#d29922", "needs work": "#f85149" }[c.tier] || "#8b949e";
    return `
      <div class="drill-card">
        <div class="drill-header">
          <span class="drill-icon">${METRIC_META[key]?.icon || "🏒"}</span>
          <span class="drill-name">${c.label}</span>
          <span class="drill-tier" style="color:${tierColor}">${c.tier}</span>
        </div>
        <div class="drill-why"><strong>What's happening:</strong> ${c.why}</div>
        <div class="drill-tip"><strong>💡 Quick Tip:</strong> ${c.tip}</div>
        <div class="drill-label">📋 Practice Drill</div>
        <div class="drill-text">${c.drill}</div>
      </div>`;
  }).join("");

  return { encouragement, topPriority, strengths: strengthsHtml, focus, drills };
}

function _encouragement(overall, strengthsCount) {
  if (overall >= 85) return {
    emoji: "🔥",
    title: "Sick shot!",
    body: "You're shooting at a really high level. Everything's clicking — keep filming so you can spot tiny things to sharpen even more."
  };
  if (overall >= 70) return {
    emoji: "💪",
    title: "Strong shot!",
    body: `You nailed ${strengthsCount} of the big things. A couple small tweaks and this becomes a goal-scoring weapon.`
  };
  if (overall >= 55) return {
    emoji: "🚀",
    title: "Solid foundation — you're getting there!",
    body: "The basics are showing up. Focus on ONE thing per practice from the list below — don't try to fix everything at once. Pick the top priority, do 20 shots focused only on that."
  };
  if (overall >= 35) return {
    emoji: "🏒",
    title: "Good start — plenty to build on!",
    body: "Every great shooter started exactly here. Pick ONE thing to focus on (see Next Time below) and stick with it for a whole practice session before moving on."
  };
  return {
    emoji: "🎯",
    title: "Every pro started here — let's build it up!",
    body: "Don't worry about the number — worry about the fix. The single most important thing right now is the 'Next Time Try This First' below. Just that one thing. Twenty shots, focused only on that. You'll see the score climb fast."
  };
}

function closeHistoryDetail() {
  document.getElementById("historyDetail").classList.add("hidden");
  document.getElementById("historyList").classList.remove("hidden");
}

async function deleteHistoryItem(e, jobId) {
  e.stopPropagation();
  if (!confirm("Delete this shot from history?")) return;
  await fetch(`${API}/history/${jobId}`, { method: "DELETE" });
  showHistory();
}

async function clearAllHistory() {
  if (!confirm("Delete ALL shot history? This cannot be undone.")) return;
  await fetch(`${API}/history`, { method: "DELETE" });
  showHistory();
}

// ── Navigation helpers ────────────────────────────────────────────────────────
function showSection(id) {
  ["uploadSection","progressSection","resultsSection","historySection"]
    .forEach(s => document.getElementById(s).classList.toggle("hidden", s !== id));
  // Hide "new clip" FAB on upload page (redundant there)
  const fab = document.getElementById("fabNewClip");
  if (fab) fab.classList.toggle("hidden", id === "uploadSection" || id === "progressSection");
}
function showUpload()  { showSection("uploadSection"); }
function resetUI() {
  fileInput.value = "";
  const v = document.getElementById("overlayVideo");
  const s = document.getElementById("overlayVideoSource");
  v.pause();
  if (s) s.removeAttribute("src");
  v.removeAttribute("poster");
  v.load();
  showSection("uploadSection");
}

// ── Expert Feedback Mode (desktop only) ──────────────────────────────────────
// Toggle: Ctrl+Shift+F  (or Cmd+Shift+F on Mac).  Persists in localStorage.
// The form is also CSS-hidden on touch/narrow devices — see style.css media query.

const FB_CHECKBOXES = [
  ["head_dropped",              "Head dropped"],
  ["good_head_position",        "Good head position"],
  ["knee_drive_strong",         "Knee drive was strong"],
  ["knee_drive_weak",           "Knee drive was weak"],
  ["weight_transfer_good",      "Weight transfer was good"],
  ["weight_transfer_weak",      "Weight transfer was weak"],
  ["follow_through_good",       "Follow-through was good"],
  ["follow_through_short",      "Follow-through was short"],
  ["blade_puck_contact_good",   "Stick/puck contact looked good"],
  ["balance_issue",             "Balance issue"],
  ["camera_angle_unreliable",   "Camera angle made analysis unreliable"],
  ["ai_score_too_high",         "AI score seemed too high"],
  ["ai_score_too_low",          "AI score seemed too low"],
];

function _isDesktopExpertCapable() {
  // Same rule as the CSS guard, so JS never tries to show a hidden form.
  if (!window.matchMedia) return true;
  return window.matchMedia("(hover: hover) and (pointer: fine) and (min-width: 1024px)").matches;
}

function expertModeEnabled() {
  return localStorage.getItem("expertMode") === "1";
}

function setExpertMode(on) {
  if (on && !_isDesktopExpertCapable()) {
    alert("Expert Feedback Mode is desktop-only (needs a keyboard + larger screen).");
    return;
  }
  if (on) localStorage.setItem("expertMode", "1");
  else localStorage.removeItem("expertMode");
  _refreshExpertVisibility();
}

function _refreshExpertVisibility() {
  const on = expertModeEnabled() && _isDesktopExpertCapable();
  document.getElementById("expertIndicator")?.classList.toggle("hidden", !on);
  document.getElementById("expertPanel")?.classList.toggle("hidden", !on);
  if (on && currentJob) _loadFeedbackHistory(currentJob.job_id);
}

function _buildFeedbackForm() {
  const grid = document.getElementById("fbCheckGrid");
  if (!grid || grid.dataset.built === "1") return;
  grid.innerHTML = FB_CHECKBOXES.map(([key, label]) =>
    `<label class='fb-check'><input type='checkbox' value='${key}'>${label}</label>`
  ).join("");
  grid.dataset.built = "1";

  const slider = document.getElementById("fbScore");
  const valEl = document.getElementById("fbScoreVal");
  slider?.addEventListener("input", () => { valEl.textContent = slider.value; });
}

async function _loadFeedbackHistory(jobId) {
  const wrap = document.getElementById("fbHistory");
  if (!wrap) return;
  wrap.innerHTML = "";
  if (!jobId) return;
  try {
    const rows = await fetch(`/feedback/${jobId}`).then(r => r.json());
    if (!rows.length) {
      wrap.innerHTML = "<p class='muted small'>No feedback recorded for this clip yet.</p>";
      return;
    }
    wrap.innerHTML = `<h4>Previous feedback for this clip (${rows.length})</h4>` +
      rows.slice().reverse().map(r => `
        <div class='fb-prev'>
          <span class='fb-prev-when'>${r.timestamp || ""}</span>
          <span class='fb-prev-by'>${(r.reviewer || "anonymous")}</span>
          <span class='fb-prev-score'>AI ${r.ai_score ?? "—"} → Human ${r.human_score ?? "—"}</span>
          <span class='fb-prev-label'>${(r.human_quality_label || "").replace(/_/g," ")}</span>
          ${r.human_note ? `<div class='fb-prev-note'>${r.human_note.replace(/</g,"&lt;")}</div>` : ""}
        </div>
      `).join("");
  } catch (e) { /* ignore */ }
}

async function submitFeedback() {
  if (!currentJob || !currentJob.job_id) { alert("No analyzed clip in view."); return; }
  const checks = Array.from(document.querySelectorAll("#fbCheckGrid input:checked")).map(c => c.value);
  const payload = {
    job_id: currentJob.job_id,
    corrected_score: parseInt(document.getElementById("fbScore").value, 10),
    quality_label: document.getElementById("fbQuality").value,
    checkboxes: checks,
    note: document.getElementById("fbNote").value,
    reviewer: document.getElementById("fbReviewer").value,
    frame_url: document.getElementById("fbFrameUrl").value || "",
  };
  const status = document.getElementById("fbStatus");
  status.textContent = "Saving…"; status.style.color = "var(--muted)";
  try {
    const res = await fetch("/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      status.textContent = "❌ " + (err.detail || res.statusText);
      status.style.color = "#f85149";
      return;
    }
    status.textContent = "✅ Saved";
    status.style.color = "#3fb950";
    // Clear checkboxes + note (keep score + reviewer for batch reviewing)
    document.querySelectorAll("#fbCheckGrid input").forEach(c => c.checked = false);
    document.getElementById("fbNote").value = "";
    _clearCapture("fb");
    _loadFeedbackHistory(currentJob.job_id);
    setTimeout(() => { status.textContent = ""; }, 4000);
  } catch (e) {
    status.textContent = "❌ " + e.message;
    status.style.color = "#f85149";
  }
}

function openPlayerReport() {
  if (!currentJob?.job_id) return;
  window.open(`/report/${currentJob.job_id}`, "_blank");
}

function openExpertReport() {
  if (!currentJob?.job_id) return;
  window.open(`/report/${currentJob.job_id}?expert=1`, "_blank");
}

// Keyboard shortcut + first-time setup
window.addEventListener("DOMContentLoaded", () => {
  _buildFeedbackForm();
  _refreshExpertVisibility();
});
window.addEventListener("keydown", (e) => {
  const isToggle = (e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === "F" || e.key === "f");
  if (!isToggle) return;
  e.preventDefault();
  setExpertMode(!expertModeEnabled());
});

// Refresh expert panel after each renderResults (hook into existing function)
const _origRenderResults = renderResults;
renderResults = function(data) {
  _origRenderResults(data);
  _refreshExpertVisibility();
};

// ── Measurement-quality Feedback (about the AI, not the player) ──────────────
// Lives inside the same desktop-only Expert panel. Anonymous.

const MFB_CHECKBOXES = [
  ["pose_lost",              "Pose tracking lost the player"],
  ["wrong_release_frame",    "Wrong release frame detected"],
  ["wrong_load_frame",       "Wrong load / stride frame detected"],
  ["camera_unreliable",      "Camera angle made measurement unreliable"],
  ["subscores_off",          "Sub-scores don't match what I see"],
  ["coaching_tip_irrelevant","Coaching tip / drill was irrelevant"],
  ["analyzer_worked_well",   "Analyzer worked well overall"],
];

function _buildMeasurementForm() {
  // Build the analyzer-flag checkboxes once.
  const flagGrid = document.getElementById("mfbCheckGrid");
  if (flagGrid && flagGrid.dataset.built !== "1") {
    flagGrid.innerHTML = MFB_CHECKBOXES.map(([key, label]) =>
      `<label class='fb-check'><input type='checkbox' value='${key}'>${label}</label>`
    ).join("");
    flagGrid.dataset.built = "1";
  }
}

function _renderMeasurementMetricGrid() {
  // (Re)render the per-metric thumbs grid from the current job's metrics.
  const grid = document.getElementById("mfbMetricGrid");
  if (!grid) return;
  const metrics = (currentJob && currentJob.metrics) || {};
  const keys = Object.keys(metrics);
  if (!keys.length) {
    grid.innerHTML = "<p class='muted small'>Analyze a clip to populate metrics.</p>";
    return;
  }
  grid.innerHTML = keys.map(k => {
    const m = metrics[k] || {};
    const label = (m.coaching && m.coaching.label) || k.replace(/_/g, " ");
    const aiScore = (m.score != null) ? `${m.score}/100` : "—";
    return `
      <div class='mfb-row' data-metric='${k}'>
        <span class='mfb-row-label'>${label} <span class='muted small'>(AI: ${aiScore})</span></span>
        <span class='mfb-thumbs'>
          <label class='mfb-thumb'><input type='radio' name='mfb_${k}' value='good'><span>👍</span></label>
          <label class='mfb-thumb'><input type='radio' name='mfb_${k}' value='bad'><span>👎</span></label>
          <label class='mfb-thumb'><input type='radio' name='mfb_${k}' value='not_measured'><span>⊘</span></label>
          <label class='mfb-thumb mfb-skip'><input type='radio' name='mfb_${k}' value='' checked><span>—</span></label>
        </span>
      </div>
    `;
  }).join("");
}

async function _loadMeasurementHistory(jobId) {
  const wrap = document.getElementById("mfbHistory");
  if (!wrap) return;
  wrap.innerHTML = "";
  if (!jobId) return;
  try {
    const rows = await fetch(`/measurement-feedback/${jobId}`).then(r => r.json());
    if (!rows.length) {
      wrap.innerHTML = "<p class='muted small'>No measurement feedback for this clip yet.</p>";
      return;
    }
    wrap.innerHTML = `<h4>Previous measurement feedback (${rows.length})</h4>` +
      rows.slice().reverse().map(r => {
        const ratings = r.metric_ratings || {};
        const ratingPills = Object.entries(ratings).map(([k,v]) => {
          const icon = v === "good" ? "👍" : v === "bad" ? "👎" : "⊘";
          return `<span class='mfb-pill'>${icon} ${k}</span>`;
        }).join("");
        return `
          <div class='fb-prev'>
            <span class='fb-prev-when'>${r.timestamp || ""}</span>
            <span class='fb-prev-by'>overall: <strong>${(r.overall_label || "—").replace(/_/g," ")}</strong></span>
            <span class='fb-prev-score'>${(r.checkboxes || []).length} flag(s)</span>
            <div class='mfb-pill-row'>${ratingPills}</div>
            ${r.note ? `<div class='fb-prev-note'>${r.note.replace(/</g,"&lt;")}</div>` : ""}
          </div>
        `;
      }).join("");
  } catch (e) { /* ignore */ }
}

async function submitMeasurementFeedback() {
  if (!currentJob || !currentJob.job_id) { alert("No analyzed clip in view."); return; }

  // Collect per-metric thumbs (skip rows where user picked "—" or didn't choose)
  const metric_ratings = {};
  document.querySelectorAll("#mfbMetricGrid .mfb-row").forEach(row => {
    const key = row.dataset.metric;
    const sel = row.querySelector("input[type=radio]:checked");
    if (sel && sel.value) metric_ratings[key] = sel.value;
  });
  const checkboxes = Array.from(
    document.querySelectorAll("#mfbCheckGrid input:checked")
  ).map(c => c.value);

  const payload = {
    job_id: currentJob.job_id,
    metric_ratings,
    checkboxes,
    overall_label: document.getElementById("mfbOverall").value,
    note: document.getElementById("mfbNote").value,
    frame_url: document.getElementById("mfbFrameUrl").value || "",
  };
  const status = document.getElementById("mfbStatus");
  status.textContent = "Saving…"; status.style.color = "var(--muted)";
  try {
    const res = await fetch("/measurement-feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      status.textContent = "❌ " + (err.detail || res.statusText);
      status.style.color = "#f85149";
      return;
    }
    status.textContent = "✅ Saved";
    status.style.color = "#3fb950";
    // Reset per-metric thumbs to "—" (skip) and clear flags + note
    document.querySelectorAll("#mfbMetricGrid .mfb-skip input").forEach(r => r.checked = true);
    document.querySelectorAll("#mfbCheckGrid input").forEach(c => c.checked = false);
    document.getElementById("mfbNote").value = "";
    _clearCapture("mfb");
    _loadMeasurementHistory(currentJob.job_id);
    setTimeout(() => { status.textContent = ""; }, 4000);
  } catch (e) {
    status.textContent = "❌ " + e.message;
    status.style.color = "#f85149";
  }
}

// Hook into the existing _refreshExpertVisibility so the measurement section
// also rebuilds when expert mode toggles on after a result is loaded.
const _origRefreshExpert = _refreshExpertVisibility;
_refreshExpertVisibility = function() {
  _origRefreshExpert();
  _buildMeasurementForm();
  _renderMeasurementMetricGrid();
  const on = expertModeEnabled() && _isDesktopExpertCapable();
  if (on && currentJob) _loadMeasurementHistory(currentJob.job_id);
};

window.addEventListener("DOMContentLoaded", _buildMeasurementForm);

// ── Frame capture (browser-side canvas) ─────────────────────────────────────
async function captureFrame(prefix) {
  if (!currentJob || !currentJob.job_id) { alert("No analyzed clip in view."); return; }
  const video = document.getElementById("overlayVideo");
  const status = document.getElementById(prefix + "CaptureStatus");
  if (!video || !video.videoWidth) {
    if (status) { status.textContent = "❌ No video loaded yet"; status.style.color = "#f85149"; }
    return;
  }
  if (status) { status.textContent = "Capturing…"; status.style.color = "var(--muted)"; }
  try {
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0);
    const blob = await new Promise(r => canvas.toBlob(r, "image/jpeg", 0.85));
    const fd = new FormData();
    fd.append("job_id", currentJob.job_id);
    fd.append("t_sec", String(video.currentTime || 0));
    fd.append("frame", blob, "capture.jpg");
    const res = await fetch("/capture-frame", { method: "POST", body: fd });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
    const { frame_url } = await res.json();
    document.getElementById(prefix + "FrameUrl").value = frame_url;
    const img = document.getElementById(prefix + "FramePreview");
    img.src = frame_url + "?t=" + Date.now();
    img.classList.remove("hidden");
    if (status) { status.textContent = "✅ Captured @ " + (video.currentTime || 0).toFixed(2) + "s"; status.style.color = "#3fb950"; }
  } catch (e) {
    if (status) { status.textContent = "❌ " + e.message; status.style.color = "#f85149"; }
  }
}

function _clearCapture(prefix) {
  const u = document.getElementById(prefix + "FrameUrl");
  const img = document.getElementById(prefix + "FramePreview");
  const s = document.getElementById(prefix + "CaptureStatus");
  if (u) u.value = "";
  if (img) { img.src = ""; img.classList.add("hidden"); }
  if (s) s.textContent = "";
}
