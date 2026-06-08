"""HTML report renderer for analyzed shots.

Two modes:
  - normal:  player-facing — AI scores, sub-scores, coaching tips, frame notes
  - expert:  adds Expert Feedback comparison (AI vs human, deltas, reviewer notes)
"""
from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Any

_METRIC_LABELS = {
    "knee_bend": "🦵 Knee Bend",
    "hip_rotation": "🌀 Hip Rotation",
    "shoulder_rotation": "🏒 Shoulder Rotation",
    "weight_transfer": "⚖️ Weight Transfer",
    "follow_through": "🎯 Follow-Through",
    "head_stability": "👤 Head Stability",
    "release_timing": "⚡ Release Timing",
}


def _score_color(score: int | None) -> str:
    if score is None:
        return "#9aa0aa"
    if score >= 80:
        return "#16a34a"
    if score >= 55:
        return "#2563eb"
    if score >= 35:
        return "#ca8a04"
    return "#dc2626"


def _checkbox_to_label(key: str) -> str:
    return key.replace("_", " ").capitalize()


def render_report(
    result: dict[str, Any],
    *,
    feedback: list[dict] | None = None,
    expert: bool = False,
) -> str:
    """Return a self-contained HTML report. Browser → Ctrl+P → Save as PDF."""
    filename = escape(result.get("filename") or "shot.mp4")
    date = escape(result.get("date") or datetime.now().strftime("%Y-%m-%d %H:%M"))
    summary = result.get("summary") or {}
    metrics = result.get("metrics") or {}
    overall = summary.get("overall")

    metric_rows = []
    for key, label in _METRIC_LABELS.items():
        m = metrics.get(key) or {}
        score = m.get("score")
        grade = m.get("grade") or "—"
        tip = (m.get("coaching") or {}).get("tip") or m.get("tip") or ""
        unmeasured = m.get("status") == "unmeasured" or score is None
        if unmeasured:
            metric_rows.append(
                f"<tr><td>{label}</td><td colspan='2' class='muted'>couldn't measure — "
                f"{escape(m.get('reason') or '')}</td><td class='muted'>{escape(tip)}</td></tr>"
            )
        else:
            metric_rows.append(
                f"<tr><td>{label}</td>"
                f"<td><strong style='color:{_score_color(score)}'>{score}</strong>/100</td>"
                f"<td>{escape(str(grade))}</td>"
                f"<td>{escape(tip)}</td></tr>"
            )

    expert_block = ""
    if expert and feedback:
        cards = []
        for fb in feedback:
            ai = fb.get("ai_score")
            human = fb.get("human_score")
            delta = fb.get("score_delta")
            delta_color = "#16a34a" if (delta or 0) <= 5 and (delta or 0) >= -5 else "#dc2626"
            checks = fb.get("human_checkboxes") or []
            checks_html = (
                "<ul>" + "".join(f"<li>{escape(_checkbox_to_label(c))}</li>" for c in checks) + "</ul>"
                if checks else "<p class='muted'>(no checkboxes selected)</p>"
            )
            note = (fb.get("human_note") or "").strip()
            note_html = (
                f"<blockquote>{escape(note)}</blockquote>" if note else "<p class='muted'>(no note)</p>"
            )
            reviewer = escape(fb.get("reviewer") or "anonymous")
            ts = escape(fb.get("timestamp") or "")
            cards.append(f"""
              <div class='fb-card'>
                <div class='fb-head'>
                  <span class='fb-when'>🕒 {ts}</span>
                  <span class='fb-by'>by {reviewer}</span>
                </div>
                <div class='fb-scores'>
                  <div><span class='fb-label'>AI score</span><span class='fb-val'>{ai if ai is not None else '—'}</span></div>
                  <div><span class='fb-label'>Human score</span><span class='fb-val'>{human if human is not None else '—'}</span></div>
                  <div><span class='fb-label'>Delta</span><span class='fb-val' style='color:{delta_color}'>{'+' if (delta or 0) > 0 else ''}{delta if delta is not None else '—'}</span></div>
                  <div><span class='fb-label'>Quality call</span><span class='fb-val'>{escape((fb.get('human_quality_label') or '—').replace('_',' '))}</span></div>
                </div>
                <h4>Reviewer flags</h4>
                {checks_html}
                <h4>Reviewer notes</h4>
                {note_html}
              </div>
            """)
        expert_block = f"""
          <section class='expert'>
            <h2>🧑‍🏫 Expert Feedback ({len(feedback)} {'entry' if len(feedback)==1 else 'entries'})</h2>
            {''.join(cards)}
          </section>
        """
    elif expert:
        expert_block = """
          <section class='expert'>
            <h2>🧑‍🏫 Expert Feedback</h2>
            <p class='muted'>No expert feedback recorded for this clip yet.</p>
          </section>
        """

    expert_badge = "<span class='expert-badge'>EXPERT MODE</span>" if expert else ""
    style = """
      body { font-family: -apple-system, Segoe UI, Roboto, sans-serif; background: #fff; color: #1a2030; margin: 0; padding: 40px; max-width: 880px; margin: 0 auto; }
      h1 { margin: 0 0 4px; font-size: 28px; }
      .sub { color: #6b7280; margin-bottom: 24px; }
      .overall { display: inline-block; padding: 18px 28px; border-radius: 14px; background: #f6f8fb; margin-bottom: 24px; }
      .overall .num { font-size: 56px; font-weight: 800; }
      .overall .lbl { display: block; color: #6b7280; font-size: 12px; text-transform: uppercase; letter-spacing: .5px; }
      .subscores { display: flex; gap: 24px; margin-bottom: 28px; }
      .subscores div { background: #f6f8fb; padding: 12px 18px; border-radius: 10px; }
      table { width: 100%; border-collapse: collapse; margin-bottom: 28px; }
      th, td { text-align: left; padding: 10px 12px; border-bottom: 1px solid #e2e6ee; vertical-align: top; }
      th { background: #f6f8fb; font-size: 13px; color: #6b7280; text-transform: uppercase; letter-spacing: .5px; }
      .muted { color: #6b7280; }
      .expert { margin-top: 36px; padding: 24px; background: #fff7ed; border: 1px solid #fdba74; border-radius: 14px; }
      .expert h2 { margin-top: 0; }
      .expert-badge { display: inline-block; background: #ea580c; color: white; padding: 4px 10px; border-radius: 6px; font-size: 11px; letter-spacing: 1px; margin-left: 10px; vertical-align: middle; }
      .fb-card { background: white; padding: 18px; border-radius: 10px; margin-bottom: 14px; border: 1px solid #fed7aa; }
      .fb-head { display: flex; justify-content: space-between; color: #6b7280; font-size: 13px; margin-bottom: 12px; }
      .fb-scores { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 14px; }
      .fb-scores > div { background: #f6f8fb; padding: 10px 12px; border-radius: 8px; }
      .fb-label { display: block; color: #6b7280; font-size: 11px; text-transform: uppercase; letter-spacing: .5px; }
      .fb-val { font-size: 22px; font-weight: 700; }
      .fb-card ul { margin: 6px 0 0 18px; padding: 0; }
      .fb-card blockquote { margin: 6px 0 0; padding: 10px 14px; background: #f6f8fb; border-left: 3px solid #ea580c; border-radius: 4px; white-space: pre-wrap; }
      footer { color: #6b7280; font-size: 12px; margin-top: 40px; padding-top: 16px; border-top: 1px solid #e2e6ee; }
      @media print {
        body { padding: 20px; }
        .expert { break-inside: avoid; }
        .fb-card { break-inside: avoid; }
      }
    """
    return f"""<!DOCTYPE html><html lang='en'><head>
      <meta charset='utf-8'><title>Shot Report — {filename}</title>
      <style>{style}</style>
    </head><body>
      <h1>🏒 Shot Report {expert_badge}</h1>
      <p class='sub'>{filename} · {date}</p>
      <div class='overall'>
        <span class='lbl'>Overall AI Score</span>
        <span class='num' style='color:{_score_color(overall)}'>{overall if overall is not None else '—'}</span> / 100
      </div>
      <div class='subscores'>
        <div><span class='lbl'>💪 Power</span><strong style='font-size:22px;color:{_score_color(summary.get('power'))}'>{summary.get('power') if summary.get('power') is not None else '—'}</strong></div>
        <div><span class='lbl'>🎯 Technique</span><strong style='font-size:22px;color:{_score_color(summary.get('technique'))}'>{summary.get('technique') if summary.get('technique') is not None else '—'}</strong></div>
        <div><span class='lbl'>⚡ Timing</span><strong style='font-size:22px;color:{_score_color(summary.get('timing'))}'>{summary.get('timing') if summary.get('timing') is not None else '—'}</strong></div>
      </div>
      <h2>Shot Breakdown</h2>
      <table>
        <thead><tr><th>Metric</th><th>Score</th><th>Grade</th><th>Coaching tip</th></tr></thead>
        <tbody>{''.join(metric_rows)}</tbody>
      </table>
      {expert_block}
      <footer>Hockey Shot Analyzer · generated {escape(datetime.now().strftime('%Y-%m-%d %H:%M'))} · Print → Save as PDF for offline use.</footer>
    </body></html>"""
