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


# --------------------------------------------------------------------------- #
# Consolidation
# --------------------------------------------------------------------------- #
# Averaging two raters raises reliability by the Spearman-Brown relation:
# r_2 = 2r / (1 + r). At the measured r = 0.934 that is 0.966, so the mean of
# the two passes is a better estimate than either alone. This is the one thing
# the second pass buys permanently rather than as a one-off report.
#
# It also finally gives the project an uncertainty measure. Every score until
# now was a point estimate with nothing attached; the spread between two
# independent raters is a per-subtask error bar, and the subtasks where they
# disagree are precisely the ones whose scores should not be leaned on.

def consolidate(*passes: Sequence[dict[str, Any]],
                key: str = "dwa_id") -> list[dict[str, Any]]:
    """Merge any number of scoring passes into one canonical set of scores.

    Was fixed at two, which stopped being right the moment a third pass was
    worth running: a second pass of the SAME model measures sampling noise,
    where a different model measures whether the rubric or the model is doing
    the work, and there is no reason to choose. Averaging over k raters lifts
    reliability further - Spearman-Brown gives kr/(1+(k-1)r), so three raters at
    r = 0.934 reach 0.977.

    One caveat that number does not carry: two passes of the same model are not
    independent the way two different models are, since they share whatever bias
    the model has. Treating them as k independent raters overstates the gain.
    The scores still improve; the reliability figure is an upper bound.

    A subtask reached by only some passes takes the mean of those, with n_raters
    recording how many. Disagreement is the mean pairwise absolute difference,
    and is null for a subtask only one pass reached - honest, and
    distinguishable from a measured agreement of zero.
    """
    sets = [{r[key]: r for r in p if r.get(key)} for p in passes if p]
    if not sets:
        return []
    everything: set[str] = set()
    for s in sets:
        everything |= set(s)

    out: list[dict[str, Any]] = []
    for k in sorted(everything):
        rows = [s[k] for s in sets if k in s]
        base = dict(rows[0])
        spreads: list[float] = []
        for dim in DIMENSIONS:
            vals = [v for v in (_f(r, dim) for r in rows) if v is not None]
            if not vals:
                continue
            base[dim] = round(statistics.fmean(vals), 1)
            if len(vals) > 1:
                pairs = [abs(a - b) for i, a in enumerate(vals)
                         for b in vals[i + 1:]]
                spreads.append(statistics.fmean(pairs))
        base["n_raters"] = len(rows)
        base["raters"] = ";".join(sorted({str(r.get("model", "?")) for r in rows}))
        base["score_disagreement"] = (round(statistics.fmean(spreads), 1)
                                      if spreads else None)
        out.append(base)
    return out


def consolidation_summary(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    both = [r for r in rows if r.get("n_raters") == 2]
    spread = [r["score_disagreement"] for r in both
              if r.get("score_disagreement") is not None]
    spread_sorted = sorted(spread)
    def pct(p: float) -> float:
        if not spread_sorted:
            return 0.0
        i = min(len(spread_sorted) - 1, int(p * len(spread_sorted)))
        return spread_sorted[i]
    return {
        "subtasks": len(rows),
        "scored_by_two": len(both),
        "scored_by_one": len(rows) - len(both),
        "median_disagreement": round(statistics.median(spread), 1) if spread else None,
        "p90_disagreement": round(pct(0.9), 1),
        "max_disagreement": round(max(spread), 1) if spread else None,
        # the tail is what a reader needs to know about: these are the scores
        # that should carry a caveat wherever they are cited
        "above_15_points": sum(1 for v in spread if v > 15),
        "share_above_15": round(sum(1 for v in spread if v > 15) / len(spread), 4)
        if spread else None,
    }
