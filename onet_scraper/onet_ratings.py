"""Three measures O*NET publishes that the project was not using.

All three were free and sitting in files we had either never downloaded or had
downloaded and read only the point estimate from.

RECURRENCE (task_ratings.csv, FT scale). handoff.py's docstring has said since
it was written that Watson's tractability axis wants recurrence and our rubric
does not measure it, with a note that it is "available as O*NET's FT scale in
task_ratings.csv (--with-ratings), not yet used". This closes that. FT is a
distribution over seven frequency bands per task, so it gives a real
occurrence rate rather than a judgment about one.

MEASUREMENT PRECISION (the N and Standard Error columns, everywhere). Every
descriptor table in this dataset carries `n` and `standard_error` and nothing
ever read them: an importance rating from 4 incumbents was treated exactly like
one from 225. That is not a rounding concern - it decides whether an
occupation's position is a finding or noise.

EDUCATION DEPTH (education.csv, RL scale). The reconstitution axis leans hardest
on training depth, and took it from Job Zone: five levels, of which only three
occur across this corpus. The RL scale is a distribution over twelve education
categories, which is the same question asked at four times the resolution.

WHAT THE SCALES MEAN, and the judgment in each mapping:

  FT categories are roughly log-spaced in frequency ("yearly or less" up to
  "hourly or more"), so averaging the category *numbers* would treat the step
  from monthly to weekly as equal to the step from daily to hourly. We map each
  band to an approximate rate per year and average the logs. The rates are
  order-of-magnitude estimates, not O*NET's - O*NET gives the bands names, not
  numbers - and the ranking is insensitive to the exact figures, which is
  tested.

  RL categories are ordinal but unevenly spaced in time: 5 (associate's) to 6
  (bachelor's) is two years, 8 (master's) to 9 (post-master's certificate) is
  one. We map to years of schooling and average, so the result is in a unit that
  means something for reconstitution - how long to rebuild the cohort.
"""

from __future__ import annotations

import collections
import logging
import math
import statistics
from typing import Any, Iterable, Sequence

log = logging.getLogger(__name__)

# O*NET's FT bands, mapped to an order-of-magnitude rate per year. O*NET names
# the bands; the numbers are ours. Working year taken as 250 days.
FT_PER_YEAR: dict[int, float] = {
    1: 1.0,        # yearly or less
    2: 4.0,        # more than yearly
    3: 24.0,       # more than monthly
    4: 100.0,      # more than weekly
    5: 250.0,      # daily
    6: 750.0,      # several times daily
    7: 2000.0,     # hourly or more
}

# Required Level of Education, categories 1-12, as years of schooling.
EDUCATION_YEARS: dict[int, float] = {
    1: 10.0,   # less than high school
    2: 12.0,   # high school diploma
    3: 13.0,   # post-secondary certificate
    4: 13.5,   # some college, no degree
    5: 14.0,   # associate's
    6: 16.0,   # bachelor's
    7: 17.0,   # post-baccalaureate certificate
    8: 18.0,   # master's
    9: 19.0,   # post-master's certificate
    10: 20.0,  # first professional degree
    11: 21.0,  # doctoral
    12: 23.0,  # post-doctoral training
}

# The scale the education depth is rescaled onto: 10 years of schooling is 0,
# post-doctoral training is 100.
ED_FLOOR, ED_CEILING = 10.0, 23.0

# Below this many respondents an occupation's O*NET ratings are too thin to
# carry a claim about where it sits relative to others. O*NET's own suppression
# threshold is lower; this is a reporting threshold, not a validity one.
THIN_SAMPLE = 10


def _f(value: Any, default: float | None = None) -> float | None:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _distribution(rows: Iterable[dict[str, Any]], scale: str,
                  key: tuple[str, ...]) -> dict[tuple, dict[int, float]]:
    """Collect a category distribution keyed by whatever `key` names."""
    out: dict[tuple, dict[int, float]] = collections.defaultdict(dict)
    for row in rows:
        if (row.get("Scale ID") or "").strip() != scale:
            continue
        cat = _f(row.get("Category"))
        val = _f(row.get("Data Value"))
        if cat is None or val is None:
            continue
        out[tuple(row[k] for k in key)][int(cat)] = val
    return dict(out)


# --------------------------------------------------------------------------- #
# Recurrence
# --------------------------------------------------------------------------- #
def recurrence(task_ratings: Sequence[dict[str, Any]]) -> dict[tuple[str, str], float]:
    """Per (occupation, task) recurrence on 0-100, from the FT distribution.

    The log-average matters. A task done hourly and a task done yearly differ by
    three orders of magnitude; averaging the band numbers 7 and 1 to 4 would put
    it in the same place as a task done weekly, which is wrong by a factor of
    twenty in the thing the measure is about.
    """
    dist = _distribution(task_ratings, "FT", ("O*NET-SOC Code", "Task ID"))
    lo, hi = math.log10(FT_PER_YEAR[1]), math.log10(FT_PER_YEAR[7])
    out: dict[tuple[str, str], float] = {}
    for key, cats in dist.items():
        total = sum(cats.values())
        if total <= 0:
            continue
        mean_log = sum(
            (share / total) * math.log10(FT_PER_YEAR[cat])
            for cat, share in cats.items() if cat in FT_PER_YEAR)
        out[key] = round(100.0 * (mean_log - lo) / (hi - lo), 1)
    return out


def occupation_recurrence(
    task_recurrence: dict[tuple[str, str], float],
    importance: dict[tuple[str, str], float] | None = None,
) -> dict[str, float]:
    """Roll task recurrence up to the occupation, importance-weighted if given."""
    importance = importance or {}
    grouped: dict[str, list[tuple[float, float]]] = collections.defaultdict(list)
    for (code, task), value in task_recurrence.items():
        grouped[code].append((value, importance.get((code, task), 1.0) or 1.0))
    return {code: round(sum(v * w for v, w in pairs) / sum(w for _, w in pairs), 1)
            for code, pairs in grouped.items() if sum(w for _, w in pairs)}


# --------------------------------------------------------------------------- #
# Measurement precision
# --------------------------------------------------------------------------- #
def rating_precision(task_ratings: Sequence[dict[str, Any]],
                     scale: str = "IM") -> dict[str, dict[str, float]]:
    """Per occupation: how many people answered, and how precisely.

    `n` is the respondent count behind the ratings; `standard_error` is
    O*NET's own, in the units of the scale. Both are medians across the
    occupation's tasks, because one unusually well-surveyed task should not
    make the occupation look better measured than it is.
    """
    ns: dict[str, list[float]] = collections.defaultdict(list)
    ses: dict[str, list[float]] = collections.defaultdict(list)
    for row in task_ratings:
        if (row.get("Scale ID") or "").strip() != scale:
            continue
        code = row.get("O*NET-SOC Code")
        n, se = _f(row.get("N")), _f(row.get("Standard Error"))
        if code and n is not None:
            ns[code].append(n)
        if code and se is not None:
            ses[code].append(se)
    out: dict[str, dict[str, float]] = {}
    for code, values in ns.items():
        out[code] = {
            "respondents": round(statistics.median(values), 1),
            "respondents_min": min(values),
            "standard_error": round(statistics.median(ses[code]), 3) if ses.get(code) else None,
            "thin_sample": 1 if statistics.median(values) < THIN_SAMPLE else 0,
        }
    return out


def descriptor_precision(rows: Sequence[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """The same, for the already-built descriptor tables (lower-case columns)."""
    ns: dict[str, list[float]] = collections.defaultdict(list)
    for row in rows:
        code, n = row.get("onet_soc_code"), _f(row.get("n"))
        if code and n is not None:
            ns[code].append(n)
    return {code: {"respondents": round(statistics.median(v), 1),
                   "respondents_min": min(v)}
            for code, v in ns.items() if v}


# --------------------------------------------------------------------------- #
# Education depth
# --------------------------------------------------------------------------- #
def education_depth(education: Sequence[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Per occupation: mean years of required schooling, and that on 0-100.

    Returns the years as well as the rescaled figure, because years are the unit
    that means something when the question is how long a cohort takes to
    rebuild - and because a reader can check 18.2 years against their own sense
    of an occupation in a way they cannot check 63.1.
    """
    dist = _distribution(education, "RL", ("O*NET-SOC Code",))
    out: dict[str, dict[str, float]] = {}
    for (code,), cats in dist.items():
        total = sum(cats.values())
        if total <= 0:
            continue
        years = sum((share / total) * EDUCATION_YEARS[cat]
                    for cat, share in cats.items() if cat in EDUCATION_YEARS)
        depth = 100.0 * (years - ED_FLOOR) / (ED_CEILING - ED_FLOOR)
        out[code] = {"years": round(years, 2),
                     "depth": round(min(100.0, max(0.0, depth)), 1)}
    return out
