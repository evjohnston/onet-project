"""Error bars, from the noise that was measured rather than assumed.

The reliability work established that two runs of the same model differ by 3.8
points on average (METHODOLOGY.md 7.1), and then every figure in the project
carried on being a bare point estimate. This closes that: the measured noise is
pushed back through the real derivation - propagation to tasks and occupations,
the susceptibility index, the quadrant split - so each published number acquires
an interval and each published classification acquires a stability.

WHY A PARAMETRIC BOOTSTRAP AND NOT AN ANALYTIC INTERVAL. The derivation is not
a formula whose variance can be written down: it averages subtask scores into
tasks by importance weight, averages those into occupations, collapses two
near-collinear dimensions, and then cuts at the corpus median. A median that
moves with the data is the part that defeats analysis, because it makes every
occupation's classification depend on every other occupation's score. Resampling
is the only honest way to get at it.

WHERE THE NOISE COMES FROM. Not a guess and not the observed three-rater
spread, which mixes sampling noise with the calibration difference between two
different models. It is estimated from the two SAME-model passes: the difference
of two independent draws has sd sqrt(2)*sigma, so sigma is sd(difference)/sqrt(2)
- between 3.1 and 4.2 points depending on the dimension.

WHAT THIS IS NOT. It is the uncertainty from one model's run-to-run variation
and nothing else. It says nothing about whether the rubric asks the right
questions, whether the model understands the activity text, or whether O*NET's
task list is complete. Those are larger sources of error and none of them is
quantified here. An interval from this procedure is a lower bound on how wrong
a number could be.
"""

from __future__ import annotations

import json
import logging
import random
import statistics
from typing import Any, Sequence

log = logging.getLogger(__name__)

DIMENSIONS = (
    "automation_feasibility_today", "llm_exposure", "physical_embodiment_required",
    "interpersonal_demand", "judgment_under_uncertainty",
    "accountability_requirement", "error_cost",
)

# O*NET's scales and this rubric's are 0-100; a perturbed score has to stay there.
FLOOR, CEILING = 0.0, 100.0


def _f(row: dict[str, Any], key: str) -> float | None:
    v = row.get(key)
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def noise_model(first: Sequence[dict[str, Any]],
                second: Sequence[dict[str, Any]],
                key: str = "dwa_id") -> dict[str, float]:
    """Per-dimension sampling sd, from two passes of the same model.

    Passing two DIFFERENT models here would overstate the noise, because their
    disagreement is mostly calibration - 59% of it, per 7.1 - and calibration is
    not something a re-run would resample.
    """
    a = {r[key]: r for r in first if r.get(key)}
    b = {r[key]: r for r in second if r.get(key)}
    shared = sorted(set(a) & set(b))
    out: dict[str, float] = {}
    for dim in DIMENSIONS:
        diffs = [y - x for x, y in
                 ((_f(a[k], dim), _f(b[k], dim)) for k in shared)
                 if x is not None and y is not None]
        if len(diffs) > 2:
            out[dim] = round(statistics.pstdev(diffs) / (2 ** 0.5), 4)
    return out


def coerce(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Numbers as numbers.

    read_table hands back strings, and propagate() averages without coercing,
    so a CSV round-trip raises TypeError inside statistics.fmean. Cheaper to fix
    here than to thread types through the whole pipeline.
    """
    out = []
    for r in rows:
        row = dict(r)
        for dim in DIMENSIONS:
            v = _f(r, dim)
            if v is not None:
                row[dim] = v
        for extra in ("importance", "n_subtasks_scored", "confidence"):
            v = _f(r, extra)
            if v is not None:
                row[extra] = v
        out.append(row)
    return out


def perturb(scores: Sequence[dict[str, Any]], noise: dict[str, float],
            rng: random.Random) -> list[dict[str, Any]]:
    """One resample: every subtask score jittered by its dimension's sd."""
    out = []
    for r in scores:
        row = dict(r)
        for dim, sigma in noise.items():
            v = _f(r, dim)
            if v is None or not sigma:
                continue
            row[dim] = min(CEILING, max(FLOOR, v + rng.gauss(0.0, sigma)))
        out.append(row)
    return out


def summarise(draws: Sequence[float]) -> dict[str, float]:
    """A point estimate and an interval, from the resampled values."""
    v = sorted(draws)
    n = len(v)
    q = lambda p: v[min(n - 1, max(0, int(p * (n - 1))))]
    return {"mean": round(statistics.fmean(v), 2),
            "sd": round(statistics.pstdev(v), 2) if n > 1 else 0.0,
            "p05": round(q(0.05), 2), "p95": round(q(0.95), 2),
            "width": round(q(0.95) - q(0.05), 2)}


def stability(labels: Sequence[str], published: str) -> dict[str, Any]:
    """How often a classification survives the noise."""
    import collections
    c = collections.Counter(labels)
    n = len(labels) or 1
    top, top_n = c.most_common(1)[0]
    return {
        "published": published,
        "holds": round(c.get(published, 0) / n, 4),
        "modal": top,
        "modal_share": round(top_n / n, 4),
        # a label that survives under half the time is being reported with more
        # confidence than the measurement supports
        "unstable": c.get(published, 0) / n < 0.5,
    }


def bootstrap(scores: Sequence[dict[str, Any]], tasks: Sequence[dict[str, Any]],
              links: Sequence[dict[str, Any]], occupations: Sequence[dict[str, Any]],
              noise: dict[str, float], *, trials: int = 400,
              seed: int = 20260918) -> dict[str, Any]:
    """Resample the subtask scores and re-derive everything, `trials` times.

    Seeded, because a figure that moves between runs of the analysis is no
    better than a figure with no interval at all.
    """
    from .handoff import axes, calibrate as h_cal, classify
    from .scenarios import SCENARIOS, calibrate as s_cal, fate
    from .score import propagate
    from .susceptibility import build as susc_build

    rng = random.Random(seed)
    per_occ: dict[str, dict[str, list[float]]] = {}
    quadrants: dict[str, list[str]] = {}
    handoffs: dict[str, list[str]] = {}
    scen_counts: dict[str, list[float]] = {k: [] for k in SCENARIOS}

    for _ in range(trials):
        jittered = perturb(scores, noise, rng)
        task_rows, occ_rows = propagate(jittered, tasks, links, occupations)
        res = susc_build(jittered, task_rows, occ_rows, links, occupations)

        for row in res["occupation_susceptibility"]:
            code = row["onet_soc_code"]
            slot = per_occ.setdefault(code, {"susceptibility": [], "exposure": [],
                                             "anchoring": []})
            for k in slot:
                v = _f(row, k)
                if v is not None:
                    slot[k].append(v)
            quadrants.setdefault(code, []).append(row.get("quadrant", ""))

        # the handoff axes and their frontier, recalibrated on each resample -
        # the whole point of making that calibration distribution-relative
        pairs = [axes(r) for r in occ_rows]
        gaps = [(_f(r, "llm_exposure") or 0) - (_f(r, "automation_feasibility_today") or 0)
                for r in occ_rows]
        cal = h_cal([t for t, _ in pairs], [x for _, x in pairs], gaps)
        for row, (t, x), g in zip(occ_rows, pairs, gaps):
            handoffs.setdefault(row["onet_soc_code"], []).append(classify(t, x, g, cal))

        # scenario counts, likewise recalibrated
        t_rows = res["task_susceptibility"]
        scal = s_cal(t_rows)
        for name in SCENARIOS:
            scen_counts[name].append(
                sum(1 for r in t_rows if fate(r, name, scal) == "automated"))

    return {"per_occupation": per_occ, "quadrants": quadrants,
            "handoffs": handoffs, "scenario_counts": scen_counts,
            "trials": trials, "seed": seed, "noise": noise}


def report(raw: dict[str, Any], published: Sequence[dict[str, Any]],
           handoff_published: Sequence[dict[str, Any]],
           scenarios_published: dict[str, Any]) -> dict[str, Any]:
    """Turn the resamples into intervals and stabilities."""
    pub_q = {r["onet_soc_code"]: r.get("quadrant", "") for r in published}
    pub_h = {r["onet_soc_code"]: r.get("classification", "")
             for r in handoff_published}
    titles = {r["onet_soc_code"]: r.get("title", "") for r in published}

    occs = []
    for code, slots in raw["per_occupation"].items():
        entry = {"onet_soc_code": code, "title": titles.get(code, "")}
        for measure, draws in slots.items():
            if draws:
                entry[measure] = summarise(draws)
        entry["quadrant"] = stability(raw["quadrants"].get(code, []),
                                      pub_q.get(code, ""))
        entry["handoff"] = stability(raw["handoffs"].get(code, []),
                                     pub_h.get(code, ""))
        occs.append(entry)

    scen = {}
    for name, draws in raw["scenario_counts"].items():
        s = summarise(draws)
        s["published"] = (scenarios_published.get("scenarios", {})
                          .get(name, {}).get("automated"))
        scen[name] = s

    unstable_q = [o for o in occs if o["quadrant"]["unstable"]]
    unstable_h = [o for o in occs if o["handoff"]["unstable"]]
    widths = [o["susceptibility"]["width"] for o in occs if "susceptibility" in o]
    return {
        "trials": raw["trials"], "seed": raw["seed"], "noise": raw["noise"],
        "occupations": len(occs),
        "median_susceptibility_ci_width": round(statistics.median(widths), 2)
        if widths else None,
        "quadrant_unstable": len(unstable_q),
        "handoff_unstable": len(unstable_h),
        "scenarios": scen,
        "least_stable_quadrant": sorted(
            ({"title": o["title"], "published": o["quadrant"]["published"],
              "holds": o["quadrant"]["holds"], "modal": o["quadrant"]["modal"]}
             for o in occs), key=lambda d: d["holds"])[:12],
        "per_occupation": occs,
    }
