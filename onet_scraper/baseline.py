"""Compare a run against the previous run's manifest.

manifest.json has always recorded a row count for every table it writes and for
every bulk file it downloads. Nothing ever read it back, so it was a receipt
rather than a check, and the run that mattered went unnoticed:

  release 24.0 of the archived database came back with 140 occupations and 1,386
  task statements, against ~923 and ~19,000 everywhere else. The cause was
  `endswith("task statements.txt")` also matching "Green Task Statements.txt", a
  140-occupation subset that sorts first inside the zip and parses perfectly.
  Nothing failed. The numbers were simply a seventh of what they should have
  been, and the churn analysis ran on them.

An 85% drop in a row count is not a judgment call, and comparing this run's
counts with the last one's would have stopped it before anything downstream saw
the data. That is all this module does.

WHY THE THRESHOLDS ARE ASYMMETRIC AND LOOSE. O*NET releases genuinely move
counts - a release adds occupations, retires tasks, renames elements - so a
tight check would cry wolf every quarter and be turned off. The default fails
only on a change large enough to mean a different file was read (40%), warns on
one worth a glance (10%), and never complains about a table appearing for the
first time. The Green-Task case was -85% and -93%.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

WARN_AT = 0.10     # a tenth is worth a look
FAIL_AT = 0.40     # two fifths means a different file


def load(out_dir: Path) -> dict[str, Any]:
    """The previous run's manifest, or {} on the first run."""
    path = out_dir / "manifest.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("could not read the previous manifest (%s); no baseline "
                    "comparison this run", exc)
        return {}


def counts_of(manifest: dict[str, Any]) -> dict[str, int]:
    """Flatten a manifest into one name -> row count mapping."""
    out: dict[str, int] = {}
    for name, value in (manifest.get("row_counts") or {}).items():
        if isinstance(value, (int, float)):
            out[name] = int(value)
    for group in ("bulk_provenance", "descriptor_provenance"):
        for name, meta in (manifest.get(group) or {}).items():
            rows = (meta or {}).get("rows")
            if rows not in (None, ""):
                try:
                    out[f"{group.split('_')[0]}:{name}"] = int(rows)
                except (TypeError, ValueError):
                    continue
    return out


def compare(previous: dict[str, int], current: dict[str, int],
            warn_at: float = WARN_AT, fail_at: float = FAIL_AT) -> list[dict[str, Any]]:
    """One entry per table whose count moved beyond the warn threshold."""
    drifts: list[dict[str, Any]] = []
    for name, now in sorted(current.items()):
        before = previous.get(name)
        if before is None:
            continue                      # new table, nothing to compare
        if before == 0:
            continue                      # a zero baseline makes the ratio useless
        change = (now - before) / before
        if abs(change) < warn_at:
            continue
        drifts.append({
            "table": name, "previous": before, "current": now,
            "change": round(change, 4),
            "severity": "error" if abs(change) >= fail_at else "warn",
        })

    # A table that used to be written and now is not is the same class of
    # problem as one whose count collapsed, and the loop above cannot see it.
    for name, before in sorted(previous.items()):
        if name not in current and before > 0:
            drifts.append({"table": name, "previous": before, "current": 0,
                           "change": -1.0, "severity": "error"})
    return drifts


def log_report(drifts: list[dict[str, Any]], had_baseline: bool) -> int:
    if not had_baseline:
        log.info("no previous manifest; this run becomes the baseline")
        return 0
    if not drifts:
        log.info("row counts are in line with the previous run")
        return 0
    errors = 0
    for d in drifts:
        pct = 100 * d["change"]
        if d["severity"] == "error":
            errors += 1
            log.error("  %-42s %7d -> %7d  (%+.0f%%)",
                      d["table"], d["previous"], d["current"], pct)
        else:
            log.warning("  %-42s %7d -> %7d  (%+.0f%%)",
                        d["table"], d["previous"], d["current"], pct)
    if errors:
        log.error("%d row count(s) moved by %.0f%% or more. If the release "
                  "genuinely changed, re-run with --accept-baseline to adopt "
                  "the new counts.", errors, 100 * FAIL_AT)
    return errors
