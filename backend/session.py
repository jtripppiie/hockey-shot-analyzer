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


def summarize_session(session: dict, jobs: list[dict]) -> dict:
    """Aggregate per-attempt results into a session-level summary.

    `jobs` is the list of {job_id}_result.json dicts for this session's job_ids,
    in attempt order.

    SKELETON — returns the shape the session report will consume, but the trend
    math is stubbed. Fill in during Phase 2/4.
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

    # TODO(Phase 2): compute averages across attempts (overall + each sub-score).
    # TODO(Phase 2): compute per-metric trend (slope / first-vs-last delta) so the
    #   report can say "release timing improved across reps 1→N".
    # TODO(Phase 2): flag best / worst attempt and most-improved metric.
    return {
        "session_id":   session["session_id"],
        "label":        session.get("label"),
        "created":      session.get("created"),
        "attempt_count": len(attempts),
        "attempts":     attempts,
        "averages":     {},     # TODO
        "trends":       {},     # TODO
    }
