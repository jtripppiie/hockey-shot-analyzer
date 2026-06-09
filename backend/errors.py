"""
errors.py — Centralized, append-only error log (JSONL).

One place to record anything that goes wrong, backend OR frontend, so we can
learn from real failures instead of losing them to stderr. Mirrors the existing
feedback-log convention: one JSON object per line at output/error_log.jsonl,
append-only, nothing overwritten.

Use `log_error(where, exc)` anywhere you catch an exception, or `log_error(where,
message=...)` to record a non-exception problem. Browser errors arrive via the
/client-error route in main.py and are logged here with source="frontend".

Every entry is ALSO forwarded to Python's logging (stderr) so live-tailing the
server still shows failures during development.

Security notes:
- All free-text fields are length-capped so a malicious or buggy client cannot
  bloat the log with one giant entry.
- The reader tolerates malformed lines (skips them) rather than crashing.
There is intentionally no rotation (matches the feedback log); add one behind a
flag if the file ever gets large.
"""
from __future__ import annotations

import json
import logging
import traceback as _traceback
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from feedback import APP_VERSION
except Exception:  # pragma: no cover - keep logging working even if import shifts
    APP_VERSION = "unknown"

BASE_DIR = Path(__file__).parent.parent
ERROR_LOG = BASE_DIR / "output" / "error_log.jsonl"

# Field caps (characters). Keep entries bounded regardless of input.
_MAX_MESSAGE = 2000
_MAX_TRACEBACK = 8000
_MAX_WHERE = 200
_MAX_CONTEXT_JSON = 4000

_VALID_SEVERITY = {"info", "warning", "error", "critical"}


def _clip(s: Any, limit: int) -> str:
    s = "" if s is None else str(s)
    return s if len(s) <= limit else s[:limit] + "…[truncated]"


def _safe_context(context: Any) -> dict:
    """Coerce context into a small JSON-serializable dict, capped in size."""
    if not isinstance(context, dict):
        return {}
    out: dict[str, Any] = {}
    for k, v in list(context.items())[:30]:
        try:
            json.dumps(v)
            out[str(k)[:80]] = v
        except (TypeError, ValueError):
            out[str(k)[:80]] = _clip(v, 200)
    # Final guard on total serialized size.
    if len(json.dumps(out)) > _MAX_CONTEXT_JSON:
        return {"_note": "context omitted (too large)"}
    return out


def log_error(
    where: str,
    exc: BaseException | None = None,
    *,
    message: str | None = None,
    context: dict | None = None,
    severity: str = "error",
    source: str = "backend",
    log_path: Path | None = None,
) -> dict:
    """Append one error entry to the JSONL log and return the stored record.

    `where`    — short label for the failure site (route name, function, etc.).
    `exc`      — optional exception; its type + traceback are captured.
    `message`  — optional explicit message (defaults to str(exc)).
    `context`  — optional small dict of extra detail (job_id, url, …).
    Never raises: logging an error must not itself break the request.
    """
    path = log_path or ERROR_LOG
    if severity not in _VALID_SEVERITY:
        severity = "error"

    error_type = type(exc).__name__ if exc is not None else ""
    if message is None:
        message = str(exc) if exc is not None else ""

    tb = ""
    if exc is not None:
        tb = "".join(_traceback.format_exception(type(exc), exc, exc.__traceback__))

    entry = {
        "id":          uuid.uuid4().hex[:10],
        "ts":          datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "severity":    severity,
        "source":      source,
        "where":       _clip(where, _MAX_WHERE),
        "error_type":  _clip(error_type, 120),
        "message":     _clip(message, _MAX_MESSAGE),
        "traceback":   _clip(tb, _MAX_TRACEBACK),
        "context":     _safe_context(context),
        "app_version": APP_VERSION,
    }

    # Forward to stderr so live server logs still show it.
    logging.error("[%s] %s: %s", entry["where"], entry["error_type"] or severity,
                  entry["message"])

    try:
        path.parent.mkdir(exist_ok=True)
        with open(path, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        # Last resort: if we can't write the log file, don't crash the caller.
        logging.error("Failed to write error_log.jsonl:\n%s", _traceback.format_exc())

    return entry


def recent_errors(limit: int = 50, log_path: Path | None = None) -> list[dict]:
    """Return the most recent error entries (newest first). Tolerates bad lines."""
    path = log_path or ERROR_LOG
    if not path.exists():
        return []
    limit = max(1, min(int(limit), 500))
    try:
        with open(path) as f:
            lines = f.readlines()
    except OSError:
        return []
    out: list[dict] = []
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
        if len(out) >= limit:
            break
    return out
