"""How much of a score is the rubric, and how much is the model.

Every number in this project rested on a single scoring pass by one model, with
no measure of its own stability. That is the largest remaining validity gap:
the plausibility anchors in validate_derived assert bands without knowing the
measurement's spread, and the frontier is calibrated to percentiles of a
distribution whose noise was unquantified.

TWO DIFFERENT QUESTIONS, and it matters which one a run answers:

  test-retest      the same model scoring the same rubric twice. Isolates
                   sampling noise in one model's judgment.
  cross-model      a different model scoring the same rubric once. Isolates how
                   much of a score is the rubric and how much is the particular
                   disposition of the model that produced it.

This module computes agreement for either - the arithmetic is the same - but the
report records which was run, because they do not license the same claims. A
high cross-model correlation says the rubric is doing the work. A high
test-retest correlation says only that the model is consistent with itself,
which a systematically biased rubric would also produce.

WHY ICC AND NOT JUST r. Pearson's r is invariant to a shift or a rescale: two
raters who disagree by a constant twenty points correlate at 1.0. For ratings
meant to be interchangeable that is the wrong question, so the intraclass
correlation (ICC(2,1), two-way random effects, absolute agreement) is reported
alongside, and it penalises exactly that. Where the two diverge, the gap is
systematic bias rather than noise.
"""

from __future__ import annotations

import logging
import statistics
from typing import Any, Sequence

log = logging.getLogger(__name__)

# The rated dimensions, which are what has to agree.
DIMENSIONS = (
    "automation_feasibility_today",
    "llm_exposure",
    "physical_embodiment_required",
    "interpersonal_demand",
    "judgment_under_uncertainty",
    "accountability_requirement",
    "error_cost",
)


def _f(row: dict[str, Any], key: str) -> float | None:
    v = row.get(key)
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def pearson(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    n = len(xs)
    if n < 3:
        return None
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sx, sy = statistics.pstdev(xs), statistics.pstdev(ys)
    if sx == 0 or sy == 0:
        return None
    cov = sum((a - mx) * (b - my) for a, b in zip(xs, ys)) / n
    return cov / (sx * sy)


def icc21(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    """ICC(2,1): two-way random effects, absolute agreement, single measures.

    Unlike r this is sensitive to a constant offset between the raters, which is
    the failure mode that matters when two scores are meant to be substitutable.
    """
    n = len(xs)
    if n < 3:
        return None
    grand = statistics.fmean(list(xs) + list(ys))
    # between-targets, between-raters, and residual mean squares
    row_means = [(a + b) / 2 for a, b in zip(xs, ys)]
    ms_rows = 2 * sum((m - grand) ** 2 for m in row_means) / (n - 1)
    col_means = [statistics.fmean(xs), statistics.fmean(ys)]
    ms_cols = n * sum((c - grand) ** 2 for c in col_means) / 1
    ss_total = sum((v - grand) ** 2 for v in list(xs) + list(ys))
    ss_rows = 2 * sum((m - grand) ** 2 for m in row_means)
    ss_cols = n * sum((c - grand) ** 2 for c in col_means)
    ss_err = ss_total - ss_rows - ss_cols
    if n - 1 <= 0:
        return None
    ms_err = ss_err / (n - 1)
    denom = ms_rows + (ms_cols - ms_err) / n
    if denom == 0:
        return None
    return (ms_rows - ms_err) / denom


def compare(first: Sequence[dict[str, Any]], second: Sequence[dict[str, Any]],
            key: str = "dwa_id", kind: str = "cross-model") -> dict[str, Any]:
    """Agreement between two scoring passes over the same catalogue."""
    a = {r[key]: r for r in first if r.get(key)}
    b = {r[key]: r for r in second if r.get(key)}
    shared = sorted(set(a) & set(b))

    dims: dict[str, Any] = {}
    for dim in DIMENSIONS:
        xs, ys = [], []
        for k in shared:
            x, y = _f(a[k], dim), _f(b[k], dim)
            if x is not None and y is not None:
                xs.append(x)
                ys.append(y)
        if len(xs) < 3:
            dims[dim] = {"n": len(xs)}
            continue
        diffs = [abs(x - y) for x, y in zip(xs, ys)]
        r = pearson(xs, ys)
        dims[dim] = {
            "n": len(xs),
            "pearson": None if r is None else round(r, 4),
            "icc": (lambda v: None if v is None else round(v, 4))(icc21(xs, ys)),
            "mean_abs_diff": round(statistics.fmean(diffs), 2),
            "median_abs_diff": round(statistics.median(diffs), 2),
            "within_10": round(sum(1 for d in diffs if d <= 10) / len(diffs), 4),
            "within_20": round(sum(1 for d in diffs if d <= 20) / len(diffs), 4),
            # A signed mean separates bias from noise: a large signed gap with a
            # high r means one rater is simply reading the scale higher.
            "mean_signed_diff": round(statistics.fmean(
                [y - x for x, y in zip(xs, ys)]), 2),
            "mean_first": round(statistics.fmean(xs), 2),
            "mean_second": round(statistics.fmean(ys), 2),
        }

    scored = [d for d in dims.values() if d.get("pearson") is not None]
    return {
        "kind": kind,
        "subtasks_compared": len(shared),
        "only_in_first": len(set(a) - set(b)),
        "only_in_second": len(set(b) - set(a)),
        "dimensions": dims,
        "mean_pearson": round(statistics.fmean(
            [d["pearson"] for d in scored]), 4) if scored else None,
        "mean_icc": round(statistics.fmean(
            [d["icc"] for d in scored if d["icc"] is not None]), 4) if scored else None,
        "mean_abs_diff": round(statistics.fmean(
            [d["mean_abs_diff"] for d in scored]), 2) if scored else None,
    }


def log_report(rep: dict[str, Any]) -> None:
    log.info("-" * 78)
    log.info("%s agreement over %d subtasks", rep["kind"], rep["subtasks_compared"])
    log.info("%-32s %6s %6s %7s %7s %7s", "dimension", "r", "ICC", "mean|d|",
             "<=10", "bias")
    for dim, d in rep["dimensions"].items():
        if d.get("pearson") is None:
            log.info("%-32s %6s  (n=%d)", dim, "-", d.get("n", 0))
            continue
        log.info("%-32s %6.3f %6.3f %7.1f %6.0f%% %+7.1f", dim, d["pearson"],
                 d["icc"] if d["icc"] is not None else float("nan"),
                 d["mean_abs_diff"], 100 * d["within_10"], d["mean_signed_diff"])
    log.info("-" * 78)
    log.info("mean r %.3f · mean ICC %.3f · mean absolute difference %.1f points",
             rep["mean_pearson"] or 0, rep["mean_icc"] or 0, rep["mean_abs_diff"] or 0)
