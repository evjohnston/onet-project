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


# The thresholds above are absolute points on the 0-100 scales, and the
# cross-model retest (METHODOLOGY.md 7.1) showed what that costs. Two models
# scoring the same rubric agreed on the RANKING of exposure at r = 0.935 and
# disagreed about the LEVEL of the scale by 9.7 points - nearly the same
# distribution shape (sd 23.9 against 23.4), a different centre (median 68
# against 55). Absolute cuts cannot survive that: the automated count moved by
# -51%, -35% and -26% across the three scenarios purely because the second
# rater read the scale lower.
#
# Expressed as quantiles of the corpus's own exposure distribution, the same
# thresholds move the count by +16%, +14% and +5% instead. The quantiles below
# were obtained by inverting each absolute threshold against the consolidated
# corpus, so on that corpus they reproduce the previous cuts and nothing moves;
# what changes is that a rescoring no longer walks a third of the catalogue
# across a fixed line.
#
# This is the same fix already applied to the handoff frontier in handoff.py,
# for the same reason, and it was left undone here only because nothing had yet
# measured the calibration.
# Each absolute threshold, expressed as its quantile of the REFERENCE corpus -
# the 5,612 tasks as propagated from the original single-model pass, which is
# the distribution the numbers above were chosen against. These are fixed
# constants, which is the whole point: applying them to whatever distribution is
# present is what makes the cut travel with the scale.
#
# A first version computed q(vals, pct_of(vals, 80)) on the live corpus, which
# recovers 80 by construction - circular, and a no-op on every corpus. The
# frontier in handoff.py gets this right by hardcoding its quantiles, and this
# is the same treatment.
REFERENCE_QUANTILES: dict[str, dict[str, float]] = {
    "modest":      {"auto_exposure": 0.679615, "auto_anchoring_max": 0.317177,
                    "augment_exposure": 0.328225},
    "substantial": {"auto_exposure": 0.467035, "auto_anchoring_max": 0.677299,
                    "augment_exposure": 0.228261},
    "extreme":     {"auto_exposure": 0.306664, "auto_anchoring_max": 0.935852,
                    "augment_exposure": 0.158945},
}


def calibrate(tasks: Sequence[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Read each scenario's thresholds off the corpus being classified."""
    exposure = sorted(v for v in (_f(t, "exposure") for t in tasks) if v is not None)
    anchoring = sorted(v for v in (_f(t, "anchoring") for t in tasks) if v is not None)
    if not exposure or not anchoring:
        return {k: dict(v) for k, v in SCENARIOS.items()}

    def q(vals: list[float], p: float) -> float:
        pos = p * (len(vals) - 1)
        lo = int(pos)
        hi = min(lo + 1, len(vals) - 1)
        return vals[lo] + (pos - lo) * (vals[hi] - vals[lo])

    return {
        name: {
            "auto_exposure": q(exposure, qs["auto_exposure"]),
            "auto_anchoring_max": q(anchoring, qs["auto_anchoring_max"]),
            "augment_exposure": q(exposure, qs["augment_exposure"]),
        }
        for name, qs in REFERENCE_QUANTILES.items()
    }


def fate(task: dict[str, Any], scenario: str,
         cal: dict[str, dict[str, float]] | None = None) -> str:
    """automated / augmented / unchanged for one task under one scenario.

    `cal` comes from calibrate() over the corpus being classified. Passing None
    falls back to the absolute thresholds, which is right for a single task
    scored in isolation and wrong for a whole corpus.
    """
    s = (cal or {}).get(scenario) or SCENARIOS[scenario]
    exposure, anchoring = _f(task, "exposure"), _f(task, "anchoring")
    if exposure >= s["auto_exposure"] and anchoring < s["auto_anchoring_max"]:
        return "automated"
    if exposure >= s["augment_exposure"]:
        return "augmented"
    return "unchanged"


def task_fates(tasks: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    cal = calibrate(tasks)
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
        row.update({name: fate(t, name, cal) for name in SCENARIOS})
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
