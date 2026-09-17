"""Task churn: has the task content of these jobs already moved?

Every other measure in this project depends on a model's judgment. This one does
not. O*NET archives each database release, so the task statements attached to an
occupation can be diffed across a decade and the turnover measured directly.

Two things make the diff harder than it looks:

  Task IDs are stable but not permanent. A task can be retired and a near-
  identical one added under a new id, which would read as churn where there is
  none. So a task counts as surviving if its id persists OR its normalised text
  matches something in the later release for the same occupation.

  The SOC taxonomy was revised in 2010 and 2019. Codes were split, merged and
  renumbered, so an occupation missing from an earlier release is usually a
  taxonomy change rather than a new job. Occupations are only compared where the
  code exists in both releases, and the count of skipped codes is reported
  rather than buried.
"""

from __future__ import annotations

import io
import logging
import re
import zipfile
from typing import Any, Iterable, Sequence

log = logging.getLogger(__name__)

ARCHIVE_URL = "https://www.onetcenter.org/dl_files/database/db_{release}_text.zip"

# A decade of releases, roughly every other year, tightening after 2022.
# Not every major version has a .0 - the 20.x series starts at 20.1 - so the
# build verifies each one and drops the ones that are not published rather than
# failing the whole run on a guessed filename.
DEFAULT_RELEASES = ("20_1", "22_0", "24_0", "26_0", "28_0", "29_0", "30_0", "31_0")

CHURN_COLUMNS = ("release", "year", "occupations_compared", "occupations_skipped",
                 "tasks_start", "tasks_end", "added", "retired", "survived",
                 "turnover_rate", "added_rate")
OCC_CHURN_COLUMNS = ("onet_soc_code", "title", "susceptibility", "tasks_first",
                     "tasks_last", "added", "retired", "turnover_rate", "net_change",
                     "last_reviewed")

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^a-z0-9 ]+")


def normalise(text: str) -> str:
    """Loose match key: a task reworded slightly is the same task."""
    return _WS.sub(" ", _PUNCT.sub(" ", text.lower())).strip()


def release_year(release: str) -> int:
    """O*NET cut roughly three releases a year from 20.0 (2015) onward."""
    major = int(release.split("_")[0])
    return 2015 + (major - 20)


def fetch_release(client, release: str) -> dict[str, list[dict[str, str]]]:
    """Pull one archived release and return its task statements by occupation."""
    url = ARCHIVE_URL.format(release=release)
    page = client.get(url)
    with zipfile.ZipFile(io.BytesIO(page.content)) as archive:
        # Match the basename exactly. A suffix test also catches "Green Task
        # Statements.txt", which ships in the 2019-era releases, sorts first in
        # the archive, and is a 140-occupation subset - it parsed cleanly and
        # silently replaced the real file for that release.
        name = next((n for n in archive.namelist()
                     if n.rsplit("/", 1)[-1].lower() == "task statements.txt"), None)
        if name is None:
            raise RuntimeError(f"no Task Statements.txt in {url}")
        raw = archive.read(name).decode("utf-8", errors="replace")

    lines = raw.splitlines()
    header = lines[0].split("\t")
    idx = {h.strip(): i for i, h in enumerate(header)}
    code_i = idx.get("O*NET-SOC Code")
    task_i = idx.get("Task")
    id_i = idx.get("Task ID")
    if code_i is None or task_i is None:
        raise RuntimeError(f"unexpected columns in {name}: {header[:6]}")

    date_i = idx.get("Date")
    out: dict[str, list[dict[str, str]]] = {}
    for line in lines[1:]:
        parts = line.split("\t")
        if len(parts) <= max(code_i, task_i):
            continue
        year = ""
        if date_i is not None and len(parts) > date_i and "/" in parts[date_i]:
            year = parts[date_i].rsplit("/", 1)[-1]
        out.setdefault(parts[code_i], []).append({
            "id": parts[id_i] if id_i is not None and len(parts) > id_i else "",
            "task": parts[task_i],
            "key": normalise(parts[task_i]),
            "year": year,
        })
    log.info("release %-5s %5d occupations, %6d task statements",
             release.replace("_", "."), len(out), sum(len(v) for v in out.values()))
    return out


def diff(before: dict[str, list[dict[str, str]]],
         after: dict[str, list[dict[str, str]]],
         codes: Iterable[str]) -> dict[str, Any]:
    codes = list(codes)
    compared, skipped = 0, 0
    add = ret = surv = start = end = 0
    per_occ: dict[str, dict[str, int]] = {}

    for code in codes:
        a, b = before.get(code), after.get(code)
        if not a or not b:
            skipped += 1        # taxonomy change, not churn
            continue
        compared += 1
        a_ids = {t["id"] for t in a if t["id"]}
        b_ids = {t["id"] for t in b if t["id"]}
        a_keys = {t["key"] for t in a}
        b_keys = {t["key"] for t in b}
        # survived on id OR on text - a reworded task is not a new one
        survived = [t for t in a if (t["id"] and t["id"] in b_ids) or t["key"] in b_keys]
        added = [t for t in b if not ((t["id"] and t["id"] in a_ids) or t["key"] in a_keys)]
        retired = [t for t in a if t not in survived]
        per_occ[code] = {"first": len(a), "last": len(b),
                         "added": len(added), "retired": len(retired)}
        add += len(added); ret += len(retired); surv += len(survived)
        start += len(a); end += len(b)

    return {
        "occupations_compared": compared,
        "occupations_skipped": skipped,
        "tasks_start": start,
        "tasks_end": end,
        "added": add,
        "retired": ret,
        "survived": surv,
        "turnover_rate": round((add + ret) / max(start + end, 1), 4),
        "added_rate": round(add / max(end, 1), 4),
        "per_occupation": per_occ,
    }


def last_reviewed(snapshot: dict[str, list[dict[str, str]]]) -> dict[str, int]:
    """Most recent task date per occupation - when O*NET last looked at it."""
    out: dict[str, int] = {}
    for code, tasks in snapshot.items():
        years = [int(t["year"]) for t in tasks if t.get("year", "").isdigit()]
        if years:
            out[code] = max(years)
    return out


def build(client, releases: Sequence[str], codes: Iterable[str],
          titles: dict[str, str], susceptibility: dict[str, float]
          ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    codes = list(codes)
    snapshots: dict[str, dict[str, list[dict[str, str]]]] = {}
    missing = []
    for r in releases:
        try:
            snapshots[r] = fetch_release(client, r)
        except Exception as exc:
            log.warning("release %s unavailable (%s); dropping it from the span",
                        r.replace("_", "."), exc)
            missing.append(r)
    releases = [r for r in releases if r in snapshots]
    if len(releases) < 2:
        raise RuntimeError("need at least two published releases to measure churn")

    steps = []
    for prev, cur in zip(releases, releases[1:]):
        d = diff(snapshots[prev], snapshots[cur], codes)
        steps.append({
            "release": prev.replace("_", ".") + " → " + cur.replace("_", "."),
            "year": release_year(cur),
            **{k: v for k, v in d.items() if k != "per_occupation"},
        })

    # Cumulative first-to-last, which is what the occupation table reports.
    span = diff(snapshots[releases[0]], snapshots[releases[-1]], codes)
    reviewed_all = last_reviewed(snapshots[releases[-1]])
    occ_rows = []
    for code, v in span["per_occupation"].items():
        occ_rows.append({
            "onet_soc_code": code,
            "title": titles.get(code, ""),
            "susceptibility": susceptibility.get(code),
            "tasks_first": v["first"],
            "tasks_last": v["last"],
            "added": v["added"],
            "retired": v["retired"],
            "turnover_rate": round((v["added"] + v["retired"]) / max(v["first"] + v["last"], 1), 4),
            "net_change": v["last"] - v["first"],
            "last_reviewed": reviewed_all.get(code),
        })
    occ_rows.sort(key=lambda r: -r["turnover_rate"])

    # THE CONFOUND. O*NET re-surveys occupations on a rolling cycle, so an
    # occupation whose tasks did not change may simply not have been looked at.
    # Splitting on the last review date separates "the work did not change" from
    # "nobody checked", and only the first subset can answer the question.
    reviewed = last_reviewed(snapshots[releases[-1]])
    cutoff = 2022
    fresh = [c for c in codes if reviewed.get(c, 0) >= cutoff]
    stale = [c for c in codes if 0 < reviewed.get(c, 0) < cutoff]
    fresh_span = diff(snapshots[releases[0]], snapshots[releases[-1]], fresh)
    stale_span = diff(snapshots[releases[0]], snapshots[releases[-1]], stale)

    summary = {
        "releases": list(releases),
        "releases_unavailable": missing,
        "review_cutoff": cutoff,
        "reviewed_since_cutoff": len(fresh),
        "not_reviewed_since_cutoff": len(stale),
        "refreshed_only": {k: v for k, v in fresh_span.items() if k != "per_occupation"},
        "stale_only": {k: v for k, v in stale_span.items() if k != "per_occupation"},
        "span": releases[0].replace("_", ".") + " → " + releases[-1].replace("_", "."),
        "years": f"{release_year(releases[0])}–{release_year(releases[-1])}",
        **{k: v for k, v in span.items() if k != "per_occupation"},
    }
    return steps, occ_rows, summary
