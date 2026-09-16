"""A defensible composite: how susceptible is this work to being replaced?

The seven rated dimensions are not seven independent things. Two pairs are close
to collinear in the scored data:

    llm_exposure  <->  physical_embodiment_required      r = -0.89
    accountability_requirement <-> error_cost            r = +0.90

So a naive mean of all seven silently double-counts "can a machine do it" and
double-counts "how much is at stake". This module collapses each pair to one
factor first, which is why the index is built here rather than inline.

Two axes come out of it:

  exposure  - can the work be done by a machine (llm_exposure; physical
              embodiment is its mirror image, so it is not added again)
  anchoring - must a human do it or answer for it (stakes, interpersonal
              demand, judgment under uncertainty, physical embodiment)

susceptibility = 50 + (exposure - anchoring) / 2, clamped to 0-100.

Validation: the index is computed only from the numeric dimensions, yet it
orders the model's *independently produced* categorical verdict monotonically
(largely_automatable 74.9 > augmentable 65.9 > resistant 43.6 > human_anchored
40.3). That convergence is the main evidence the composite measures what it says.
"""

from __future__ import annotations

import collections
import logging
import statistics
from typing import Any, Sequence

log = logging.getLogger(__name__)

COMPONENTS = ("exposure", "anchoring", "susceptibility", "deployment_gap", "stakes")

SUBTASK_SUSC_COLUMNS = ("dwa_id", "dwa_title", "susceptibility", "exposure", "anchoring",
                        "stakes", "deployment_gap", "verdict", "confidence",
                        "n_occupations", "n_tasks", "rationale")
TASK_SUSC_COLUMNS = ("onet_soc_code", "occupation_title", "task_id", "task",
                     "task_category", "importance", "susceptibility", "exposure",
                     "anchoring", "deployment_gap", "dominant_verdict", "n_subtasks_scored")
OCC_SUSC_COLUMNS = ("onet_soc_code", "title", "stem_occupation_types", "job_zone",
                    "n_tasks_scored", "susceptibility", "exposure", "anchoring",
                    "deployment_gap", "share_tasks_high_susceptibility",
                    "share_largely_automatable", "share_human_anchored", "quadrant")

HIGH_SUSCEPTIBILITY = 70.0   # a task is "highly susceptible" at or above this


def _f(row: dict[str, Any], key: str) -> float:
    value = row.get(key)
    return float(value) if value not in (None, "") else 0.0


def add_axes(row: dict[str, Any]) -> dict[str, Any]:
    """Attach exposure / anchoring / susceptibility to one scored row."""
    stakes = (_f(row, "accountability_requirement") + _f(row, "error_cost")) / 2
    exposure = _f(row, "llm_exposure")
    anchoring = statistics.fmean([
        stakes,
        _f(row, "interpersonal_demand"),
        _f(row, "judgment_under_uncertainty"),
        _f(row, "physical_embodiment_required"),
    ])
    row["stakes"] = round(stakes, 1)
    row["exposure"] = round(exposure, 1)
    row["anchoring"] = round(anchoring, 1)
    row["susceptibility"] = round(max(0.0, min(100.0, 50 + (exposure - anchoring) / 2)), 1)
    # Where capability already exceeds deployment, change is pending rather than done.
    row["deployment_gap"] = round(exposure - _f(row, "automation_feasibility_today"), 1)
    return row


def quadrant(exposure: float, anchoring: float,
             x_split: float, y_split: float) -> str:
    """Name the quadrant, so the scatter can be read without a colour key."""
    if exposure >= x_split:
        return "Displaceable" if anchoring < y_split else "Contested"
    return "Insulated" if anchoring < y_split else "Human-anchored"


def build(
    subtask_scores: Sequence[dict[str, Any]],
    task_scores: Sequence[dict[str, Any]],
    occupation_scores: Sequence[dict[str, Any]],
    task_subtasks: Sequence[dict[str, Any]],
    occupations: Sequence[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    occ_meta = {o["onet_soc_code"]: o for o in occupations}

    task_count: collections.Counter[str] = collections.Counter()
    occ_of_dwa: dict[str, set[str]] = collections.defaultdict(set)
    for link in task_subtasks:
        task_count[link["dwa_id"]] += 1
        occ_of_dwa[link["dwa_id"]].add(link["onet_soc_code"])

    sub_rows = []
    for row in subtask_scores:
        enriched = add_axes(dict(row))
        enriched["n_occupations"] = len(occ_of_dwa.get(row["dwa_id"], ()))
        enriched["n_tasks"] = task_count.get(row["dwa_id"], 0)
        sub_rows.append(enriched)

    task_rows = [add_axes(dict(row)) for row in task_scores]

    # Occupation axes are recomputed from its tasks, importance-weighted, rather
    # than from the already-averaged occupation scores - same weighting as score.py.
    by_occ: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in task_rows:
        by_occ[row["onet_soc_code"]].append(row)

    occ_rows = []
    for row in occupation_scores:
        code = row["onet_soc_code"]
        tasks = by_occ.get(code, [])
        if not tasks:
            continue
        weights = [float(t["importance"]) if t.get("importance") not in (None, "") else 50.0
                   for t in tasks]
        total = sum(weights) or 1.0
        wmean = lambda key: round(sum(t[key] * w for t, w in zip(tasks, weights)) / total, 1)
        meta = occ_meta.get(code, {})
        occ_rows.append({
            "onet_soc_code": code,
            "title": row.get("title") or meta.get("title", ""),
            "stem_occupation_types": row.get("stem_occupation_types")
                                     or meta.get("stem_occupation_types", ""),
            "job_zone": row.get("job_zone") or meta.get("job_zone"),
            "n_tasks_scored": len(tasks),
            "susceptibility": wmean("susceptibility"),
            "exposure": wmean("exposure"),
            "anchoring": wmean("anchoring"),
            "deployment_gap": wmean("deployment_gap"),
            "share_tasks_high_susceptibility": round(
                sum(1 for t in tasks if t["susceptibility"] >= HIGH_SUSCEPTIBILITY) / len(tasks), 3),
            "share_largely_automatable": row.get("share_largely_automatable"),
            "share_human_anchored": row.get("share_human_anchored"),
        })

    # Split the quadrants at the medians of what we actually observe, not at 50 -
    # these are relative positions within STEM, and saying so keeps the chart honest.
    x_split = statistics.median(r["exposure"] for r in occ_rows) if occ_rows else 50.0
    y_split = statistics.median(r["anchoring"] for r in occ_rows) if occ_rows else 50.0
    for row in occ_rows:
        row["quadrant"] = quadrant(row["exposure"], row["anchoring"], x_split, y_split)

    log.info("susceptibility: %d subtasks, %d tasks, %d occupations "
             "(quadrant splits: exposure %.1f, anchoring %.1f)",
             len(sub_rows), len(task_rows), len(occ_rows), x_split, y_split)
    log.info("quadrants: %s", dict(collections.Counter(r["quadrant"] for r in occ_rows)))

    return {
        "subtask_susceptibility": sorted(sub_rows, key=lambda r: -r["susceptibility"]),
        "task_susceptibility": sorted(task_rows, key=lambda r: -r["susceptibility"]),
        "occupation_susceptibility": sorted(occ_rows, key=lambda r: -r["susceptibility"]),
        "_splits": [{"x_split": round(x_split, 1), "y_split": round(y_split, 1)}],
    }


def convergent_validity(subtask_rows: Sequence[dict[str, Any]]) -> dict[str, float]:
    """Mean index per verdict. Should decrease monotonically; if not, say so."""
    by_verdict: dict[str, list[float]] = collections.defaultdict(list)
    for row in subtask_rows:
        by_verdict[row.get("verdict", "")].append(row["susceptibility"])
    order = ("largely_automatable", "augmentable", "resistant", "human_anchored")
    means = {v: round(statistics.fmean(by_verdict[v]), 1) for v in order if by_verdict[v]}
    values = list(means.values())
    means["monotonic"] = all(a >= b for a, b in zip(values, values[1:]))
    return means
