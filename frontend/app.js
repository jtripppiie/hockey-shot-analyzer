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
function _metricCardHtml(key, meta, m) {
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
  return `
    <div class="metric-card">
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

// Quality / data-confidence banner
function _renderQualityBanner(q) {
  let el = document.getElementById("qualityBanner");
  if (!el) {
    el = document.createElement("div");
    el.id = "qualityBanner";
    el.className = "quality-banner hidden";
    const results = document.getElementById("resultsSection");
    if (results) results.insertBefore(el, results.firstChild);
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
  if (statusEl) statusEl.textContent = "⏳ Building overlay video…";
  _pollPoster(video, data.frame_url, 30);
  _pollVideo(video, data.video_url, 60);

  // Overall badge
  const s = data.summary;
  const overallEl = document.getElementById("overallNum");
  overallEl.textContent = s.overall == null ? "—" : s.overall;
  overallEl.style.color = scoreColor(s.overall || 0);

  document.getElementById("powerNum").textContent     = s.power     == null ? "—" : s.power;
  document.getElementById("techniqueNum").textContent = s.technique == null ? "—" : s.technique;
  document.getElementById("timingNum").textContent    = s.timing    == null ? "—" : s.timing;

  document.getElementById("sub-power").querySelector(".sub-val").style.color     = scoreColor(s.power     || 0);
  document.getElementById("sub-technique").querySelector(".sub-val").style.color = scoreColor(s.technique || 0);
  document.getElementById("sub-timing").querySelector(".sub-val").style.color    = scoreColor(s.timing    || 0);

  document.getElementById("filenameLabel").textContent = "📁 " + data.filename;

  // Data-quality banner (camera angle warnings, unmeasured metrics, etc.)
  _renderQualityBanner(data.quality_report);

  // Metric cards (null-safe — unmeasured metrics render as a greyed card)
  const grid = document.getElementById("metricGrid");
  grid.innerHTML = "";
  for (const [key, meta] of Object.entries(METRIC_META)) {
    const m = data.metrics[key];
    if (!m) continue;
    grid.insertAdjacentHTML("beforeend", _metricCardHtml(key, meta, m));
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
      <img class="history-thumb" src="/output/${row.job_id}_frame.jpg" onerror="this.style.display='none'" />
      <div class="history-info">
        <div class="history-filename" title="${row.filename}">${row.filename}</div>
        <div class="history-date">📅 ${row.date}</div>
        <div class="history-pills">
          <span class="history-pill" style="color:#58a6ff">💪 ${row.power}</span>
          <span class="history-pill" style="color:#3fb950">🎯 ${row.technique}</span>
          <span class="history-pill" style="color:#d29922">⚡ ${row.timing}</span>
        </div>
      </div>
      <div class="history-score-big" style="color:${scoreColor_}">${row.overall}</div>
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
