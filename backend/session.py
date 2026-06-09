"""
session.py — Multi-rep session model (SKELETON).

A "session" groups several individual analyzed attempts (jobs) recorded in one
sitting — e.g. a practice where the athlete takes 8 slap shots. Each attempt is
still a normal job (one clip → pose → metrics → score); a session just ties the
job ids together so we can render one combined report with per-rep scores and
trends.

This is a SKELETON. The data model and the tiny JSON-file store below are real
and usable; the analytics (`summarize_session`) is stubbed with TODOs. It is
wired up by the `/session/*` routes in main.py.

See docs/ROADMAP-live-capture-session-report.md (Phase 2 — manual multi-rep).

Storage: one JSON file per session at output/session_{id}.json. We deliberately
reuse the existing flat output/ dir + JSON-file convention (same as
{job_id}_result.json) so there is no new database to stand up.
"""

import json
import uuid
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = BASE_DIR / "output"
SESSION_PREFIX = "session_"


def new_session_id() -> str:
    return uuid.uuid4().hex[:10]


def _session_path(session_id: str) -> Path:
    return OUTPUT_DIR / f"{SESSION_PREFIX}{session_id}.json"


def create_session(label: str = "") -> dict:
    """Create and persist a new, empty session record."""
    session = {
        "session_id": new_session_id(),
        "label":      label or "Practice session",
        "created":    datetime.now().strftime("%Y-%m-%d %H:%M"),
        "status":     "open",        # open → recording/segmenting; closed → done
        "job_ids":    [],            # ordered list of attempt job ids
    }
    save_session(session)
    return session


def load_session(session_id: str) -> dict | None:
    p = _session_path(session_id)
    if not p.exists():
        return None
    with open(p) as f:
        return json.load(f)


def save_session(session: dict) -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    with open(_session_path(session["session_id"]), "w") as f:
        json.dump(session, f)


def add_job(session_id: str, job_id: str) -> dict | None:
    """Attach an analyzed attempt (job) to a session, preserving order."""
    session = load_session(session_id)
    if session is None:
        return None
    if job_id not in session["job_ids"]:
        session["job_ids"].append(job_id)
        save_session(session)
    return session


def list_sessions() -> list[dict]:
    """Return all session records, newest first."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    sessions = []
    for p in OUTPUT_DIR.glob(f"{SESSION_PREFIX}*.json"):
        try:
            with open(p) as f:
                sessions.append(json.load(f))
        except (json.JSONDecodeError, OSError):
            continue
    sessions.sort(key=lambda s: s.get("created", ""), reverse=True)
    return sessions


def delete_session(session_id: str) -> bool:
    """Delete the session record only. Does NOT delete the member jobs — they
    remain in history and may belong to other views."""
    p = _session_path(session_id)
    if not p.exists():
        return False
    p.unlink()
    return True


def _mean_round(vals: list) -> "int | None":
    """Mean of the numeric values, rounded to int. None if no numbers."""
    nums = [v for v in vals if isinstance(v, (int, float))]
    if not nums:
        return None
    return round(sum(nums) / len(nums))


def summarize_session(session: dict, jobs: list[dict]) -> dict:
    """Aggregate per-attempt results into a session-level summary.

    `jobs` is the list of {job_id}_result.json dicts for this session's job_ids,
    in attempt order.

    Sport-agnostic: the sub-score keys (e.g. power/technique/timing, or
    approach/takeoff/bar_work) are discovered from the attempts themselves, so
    the same code drives both the hockey and pole-vault session reports.

    Produces:
      averages — mean of `overall` + each numeric sub-score across attempts.
      trends   — first-vs-last delta per metric (rendered as readable strings),
                 plus `most_improved` / `needs_work` highlights when there are
                 at least two attempts to compare.
    """
    attempts = [
        {
            "job_id":  j.get("job_id"),
            "date":    j.get("date"),
            "overall": j.get("summary", {}).get("overall"),
            "summary": j.get("summary", {}),
        }
        for j in jobs
    ]

    # Discover sub-score keys in first-seen order (skip `overall`; it's handled
    # separately so it always sorts first in the report).
    sub_keys: list[str] = []
    for a in attempts:
        for k, v in (a["summary"] or {}).items():
            if k != "overall" and isinstance(v, (int, float)) and k not in sub_keys:
                sub_keys.append(k)

    def _series(key: str) -> list:
        if key == "overall":
            return [a["overall"] for a in attempts]
        return [(a["summary"] or {}).get(key) for a in attempts]

    # Averages — only include metrics that have at least one numeric value.
    averages: dict[str, int] = {}
    for key in ["overall", *sub_keys]:
        m = _mean_round(_series(key))
        if m is not None:
            averages[key] = m

    # Trends — first-vs-last delta per metric (needs >= 2 numeric points).
    trends: dict[str, str] = {}
    deltas: dict[str, int] = {}
    for key in ["overall", *sub_keys]:
        nums = [v for v in _series(key) if isinstance(v, (int, float))]
        if len(nums) >= 2:
            first, last = round(nums[0]), round(nums[-1])
            d = last - first
            arrow = "▲" if d > 0 else ("▼" if d < 0 else "—")
            trends[key] = f"{arrow} {d:+d} ({first} → {last})"
            deltas[key] = d

    # Highlight the most-improved / most-regressed SUB-score (exclude overall).
    sub_deltas = {k: deltas[k] for k in sub_keys if k in deltas}
    if sub_deltas:
        best = max(sub_deltas, key=sub_deltas.get)
        worst = min(sub_deltas, key=sub_deltas.get)
        if sub_deltas[best] > 0:
            trends["most_improved"] = f"{best.replace('_', ' ')} ({sub_deltas[best]:+d})"
        if sub_deltas[worst] < 0:
            trends["needs_work"] = f"{worst.replace('_', ' ')} ({sub_deltas[worst]:+d})"

    return {
        "session_id":   session["session_id"],
        "label":        session.get("label"),
        "created":      session.get("created"),
        "attempt_count": len(attempts),
        "attempts":     attempts,
        "averages":     averages,
        "trends":       trends,
    }
