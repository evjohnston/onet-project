"""Three assumption sets about how much of the capability gap gets realised.

These are **not forecasts and carry no dates.** Each scenario is a pair of
thresholds saying how capable a model has to be, and how little accountability a
task has to carry, before that task is treated as automated rather than
augmented. Everything else follows from the scores already in the dataset.

The mechanism is deliberately the one Watson identifies as the real variable.
Capability is roughly fixed and measured; what differs between scenarios is
**willingness to permit the handoff** — how much accountability an actor is
prepared to hand over. `modest` only counts what is comfortably deployable today
against work carrying almost no accountability; `extreme` hands over work with
substantial accountability attached. Nothing about the underlying scores changes.

The fourth category, new tasks, is not modelled. It comes from O*NET's own
`emerging_tasks` file — 121 statements it has flagged as new or revised work in
these occupations — so the arrival of new work is observed rather than assumed.
"""

from __future__ import annotations

import collections
import logging
from typing import Any, Iterable, Sequence

log = logging.getLogger(__name__)

# (exposure needed to automate, anchoring ceiling for automation,
#  exposure needed to augment)
SCENARIOS: dict[str, dict[str, Any]] = {
    "modest": {
        "label": "Modest",
        "auto_exposure": 80.0, "auto_anchoring_max": 38.0, "augment_exposure": 60.0,
        "blurb": "Only work that is comfortably deployable today, and only where "
                 "almost no accountability attaches to it.",
    },
    "substantial": {
        "label": "Substantial",
        "auto_exposure": 70.0, "auto_anchoring_max": 52.0, "augment_exposure": 50.0,
        "blurb": "Current capability applied where accountability is moderate — "
                 "roughly the gap between what models can do and what is deployed.",
    },
    "extreme": {
        "label": "Extreme",
        "auto_exposure": 58.0, "auto_anchoring_max": 70.0, "augment_exposure": 40.0,
        "blurb": "Capability handed substantial accountability as well — work "
                 "signed off by a machine that a human would answer for today.",
    },
}
DEFAULT_SCENARIO = "substantial"

# An occupation counts as reshaped when this much of its task list automates.
RESHAPED_AT = 0.50

TASK_FATE_COLUMNS = ("onet_soc_code", "occupation_title", "task_id", "task",
                     "importance", "exposure", "anchoring", "modest",
                     "substantial", "extreme")
OCC_SCENARIO_COLUMNS = ("onet_soc_code", "title", "scenario", "tasks",
                        "automated", "augmented", "unchanged", "new_tasks",
                        "share_automated", "reshaped", "total_employment",
                        "has_destination")


def _f(row: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        return float(row.get(key))
    except (TypeError, ValueError):
        return default


def fate(task: dict[str, Any], scenario: str) -> str:
    """automated / augmented / unchanged for one task under one scenario."""
    s = SCENARIOS[scenario]
    exposure, anchoring = _f(task, "exposure"), _f(task, "anchoring")
    if exposure >= s["auto_exposure"] and anchoring < s["auto_anchoring_max"]:
        return "automated"
    if exposure >= s["augment_exposure"]:
        return "augmented"
    return "unchanged"


def task_fates(tasks: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for t in tasks:
        row = {
            "onet_soc_code": t["onet_soc_code"],
            "occupation_title": t.get("occupation_title", ""),
            "task_id": t.get("task_id"),
            "task": t["task"],
            "importance": t.get("importance"),
            "exposure": _f(t, "exposure"),
            "anchoring": _f(t, "anchoring"),
        }
        row.update({name: fate(t, name) for name in SCENARIOS})
        out.append(row)
    return out


def by_occupation(
    fates: Sequence[dict[str, Any]],
    emerging: Iterable[dict[str, Any]],
    titles: dict[str, str],
    employment: dict[str, float],
    destinations: set[str],
) -> list[dict[str, Any]]:
    new_counts = collections.Counter(e["onet_soc_code"] for e in emerging)
    grouped: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in fates:
        grouped[row["onet_soc_code"]].append(row)

    out = []
    for code, rows in grouped.items():
        for name in SCENARIOS:
            counts = collections.Counter(r[name] for r in rows)
            share = counts["automated"] / len(rows)
            out.append({
                "onet_soc_code": code, "title": titles.get(code, ""),
                "scenario": name, "tasks": len(rows),
                "automated": counts["automated"], "augmented": counts["augmented"],
                "unchanged": counts["unchanged"], "new_tasks": new_counts.get(code, 0),
                "share_automated": round(share, 3),
                "reshaped": int(share >= RESHAPED_AT),
                "total_employment": employment.get(code),
                "has_destination": int(code in destinations),
            })
    return sorted(out, key=lambda r: (r["scenario"], -r["share_automated"]))


def flows(occ_rows: Sequence[dict[str, Any]],
          soc_of: dict[str, str] | None = None) -> dict[str, Any]:
    """Employment-weighted outcome per scenario. No dates, no rates.

    Employment is summed **per SOC code, once**. Several O*NET occupations share
    one SOC and carry the same employment figure, so summing across O*NET rows
    counts those workers repeatedly - it turns 21.5M into 49.3M. The O*NET rows
    are collapsed to their SOC first: an SOC counts as reshaped if most of its
    constituent occupations are, and as having a destination if any of them does.
    """
    soc_of = soc_of or {}
    out: dict[str, Any] = {}
    for name in SCENARIOS:
        onet = [r for r in occ_rows if r["scenario"] == name and r["total_employment"]]
        grouped: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
        for r in onet:
            grouped[soc_of.get(r["onet_soc_code"], r["onet_soc_code"])].append(r)
        rows = []
        for soc, members in grouped.items():
            rows.append({
                "total_employment": members[0]["total_employment"],
                "reshaped": int(sum(m["reshaped"] for m in members) * 2 >= len(members)),
                "has_destination": int(any(m["has_destination"] for m in members)),
                "share_automated": sum(m["share_automated"] for m in members) / len(members),
            })
        total = sum(r["total_employment"] for r in rows) or 1.0
        reshaped = [r for r in rows if r["reshaped"]]
        movable = [r for r in reshaped if r["has_destination"]]
        stuck = [r for r in reshaped if not r["has_destination"]]
        emp = lambda rs: sum(r["total_employment"] for r in rs)
        out[name] = {
            "workers": round(total),
            "in_reshaped_occupations": round(emp(reshaped)),
            "share_reshaped": round(emp(reshaped) / total, 4),
            "reshaped_with_a_destination": round(emp(movable)),
            "share_with_destination": round(emp(movable) / total, 4),
            "reshaped_and_stranded": round(emp(stuck)),
            "share_stranded": round(emp(stuck) / total, 4),
            "soc_codes": len(rows),
            "occupations_reshaped": len(reshaped),
            # Mean share of the task list that automates, weighted by headcount.
            "mean_task_share_automated": round(
                sum(r["share_automated"] * r["total_employment"] for r in rows) / total, 4),
        }
    return out


def summarise(fates: Sequence[dict[str, Any]], occ_rows: Sequence[dict[str, Any]],
              emerging_total: int) -> dict[str, Any]:
    per = {}
    for name in SCENARIOS:
        c = collections.Counter(r[name] for r in fates)
        per[name] = {
            "label": SCENARIOS[name]["label"],
            "blurb": SCENARIOS[name]["blurb"],
            "thresholds": {k: SCENARIOS[name][k] for k in
                           ("auto_exposure", "auto_anchoring_max", "augment_exposure")},
            "automated": c["automated"], "augmented": c["augmented"],
            "unchanged": c["unchanged"],
            "share_automated": round(c["automated"] / max(len(fates), 1), 4),
            "occupations_reshaped": sum(1 for r in occ_rows
                                        if r["scenario"] == name and r["reshaped"]),
        }
    return {
        "tasks": len(fates),
        "new_tasks_observed": emerging_total,
        "reshaped_at": RESHAPED_AT,
        "scenarios": per,
        "note": ("Scenarios are assumption sets about willingness to hand over "
                 "accountability, not forecasts. They carry no dates. New tasks are "
                 "observed from O*NET's emerging_tasks file, not modelled."),
    }
