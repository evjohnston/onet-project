"""Plausibility checks on the derived measures.

validate.py checks the *scrape*: did every page arrive, do the row counts match
the counts O*NET prints, do the ids resolve. Nothing checked the numbers we
compute from it, and every serious defect this project has had lived exactly
there, in output that was the right shape and the wrong value:

  release 24.0 returned 140 occupations against ~923 everywhere else, because
    `endswith("task statements.txt")` also matched Green Task Statements.txt
  employment summed to 49.3 M against a true 21.5 M, because 37 SOC codes hold
    several O*NET occupations that each carry the same figure
  the security matrix returned Pediatric Surgeons at removal risk 0.0 and filed
    them under "nothing is pushing this work toward AI", because O*NET rates no
    task importance for that occupation and the weighted mean divided by zero

None of those crashed. None tripped a scrape check. Two of them were found by
eye, days later, and one only because a figure in the methodology looked wrong
while it was being written up.

So this module asserts things about the *values*. Two kinds of check:

  structural   invariants that must hold arithmetically - shares sum to one,
               nothing outside its declared range, no index exactly zero unless
               it is genuinely zero.
  anchored     a dozen occupations whose position we are willing to stake a
               claim on. Surgeons are high-stakes work. Data entry is not. If a
               change moves a named anchor out of the band it was pinned to, the
               build fails and someone has to decide whether the anchor or the
               change is wrong.

The anchors are the part that catches the interesting bugs. A structural check
cannot tell you that surgeons scoring zero is absurd; it can only tell you the
number is inside [0, 100], which zero is.
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

log = logging.getLogger(__name__)


def _check(name: str, severity: str, ok: bool, detail: str,
           sample: Any = None) -> dict[str, Any]:
    return {"check": name, "severity": severity if ok else severity,
            "passed": ok, "detail": detail, "sample": None if ok else sample}


def _ok(name: str, detail: str) -> dict[str, Any]:
    return {"check": name, "severity": "ok", "passed": True, "detail": detail,
            "sample": None}


def _f(row: dict[str, Any], key: str) -> float | None:
    v = row.get(key)
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# Anchors
# --------------------------------------------------------------------------- #
# Each anchor is (substring of the title, measure, low, high, why).
#
# These are deliberately wide - they are not a regression lock on exact values,
# they are a claim that the measure is not nonsense. A band of 55-100 on
# surgeons' removal risk would have failed the zero bug while leaving every
# legitimate rescoring free to move.
RISK_ANCHORS: tuple[tuple[str, float, float, str], ...] = (
    ("Pediatric Surgeons", 55.0, 100.0,
     "operating on a child is irreversible, high-accountability work"),
    ("Cardiologists", 55.0, 100.0, "diagnostic error is life-threatening"),
    ("Anesthesiologists", 55.0, 100.0, "continuous judgment, immediate lethality"),
    ("Emergency Medical Technicians", 50.0, 100.0,
     "unscripted situations, no supervisor present"),
    ("Oral and Maxillofacial Surgeons", 55.0, 100.0,
     "irreversible surgical work on the airway and face"),
    ("Video Game Designers", 0.0, 50.0,
     "a wrong call ships a patch; nothing is irreversible and nobody is liable"),
    ("Business Intelligence Analysts", 0.0, 52.0,
     "an analysis can be redone, and a human signs the decision it informs"),
)

EXPOSURE_ANCHORS: tuple[tuple[str, float, float, str], ...] = (
    ("Business Intelligence Analysts", 55.0, 100.0,
     "querying, summarising and charting is what these models are best at"),
    ("Mathematicians", 55.0, 100.0,
     "symbolic work a model does well, whatever one thinks of the result"),
    ("Anesthesiologists", 0.0, 55.0, "the work is physical and continuous"),
    ("Paramedics", 0.0, 55.0, "hands on a patient in an unscripted setting"),
)


def _anchor_checks(rows: Sequence[dict[str, Any]], key: str, title_key: str,
                   anchors: tuple[tuple[str, float, float, str], ...],
                   label: str) -> list[dict[str, Any]]:
    checks = []
    by_title = {r.get(title_key, ""): r for r in rows}
    missed, broken = [], []
    for needle, low, high, why in anchors:
        match = next((r for t, r in by_title.items() if needle.lower() in t.lower()),
                     None)
        if match is None:
            missed.append(needle)
            continue
        value = _f(match, key)
        if value is None or not (low <= value <= high):
            broken.append({"occupation": match.get(title_key), key: value,
                           "expected": [low, high], "because": why})
    checks.append(_check(
        f"{label}_anchors_hold", "error", not broken,
        f"{len(broken)} of {len(anchors) - len(missed)} anchored occupations sit "
        f"outside the band their work implies", broken))
    if missed:
        checks.append(_check(
            f"{label}_anchors_present", "warn", False,
            f"{len(missed)} anchor occupations are not in this corpus, so their "
            f"check did not run", missed))
    return checks


# --------------------------------------------------------------------------- #
def validate_derived(
    susceptibility: Sequence[dict[str, Any]],
    handoff: Sequence[dict[str, Any]],
    security: Sequence[dict[str, Any]],
    security_report: dict[str, Any],
    soc: Sequence[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    checks: list[dict[str, Any]] = []

    # -- 1. Ranges. Every index is declared 0-100. ------------------------
    ranged = [
        ("occupation_susceptibility", susceptibility,
         ("susceptibility", "exposure", "anchoring")),
        ("occupation_handoff", handoff, ("tractability", "resistance", "erosion_risk")),
        ("security_matrix", security,
         ("efficiency", "removal_risk", "reconstitution", "trap_score")),
    ]
    out_of_range = []
    for table, rows, keys in ranged:
        for r in rows:
            for k in keys:
                v = _f(r, k)
                if v is not None and not (0.0 <= v <= 100.0):
                    out_of_range.append({"table": table, "key": k, "value": v,
                                         "occupation": r.get("title")})
    checks.append(_check("indices_in_range", "error", not out_of_range,
                         f"{len(out_of_range)} index values fall outside 0-100",
                         out_of_range[:10]))

    # -- 2. Exactly zero is almost always a divide-by-zero, not a score. --
    # This is the check that would have caught the surgeons. A composite built
    # from several 0-100 dimensions reaching exactly 0.0 means the denominator
    # was empty, not that the work is genuinely free of stakes.
    zeros = []
    for r in security:
        for k in ("removal_risk", "reconstitution"):
            if _f(r, k) == 0.0:
                zeros.append({"occupation": r.get("title"), "measure": k,
                              "scenario": r.get("scenario")})
    checks.append(_check("no_composite_is_exactly_zero", "error", not zeros,
                         f"{len(zeros)} rows score exactly 0.0 on a composite "
                         f"measure, which indicates an empty denominator rather "
                         f"than a genuine floor", zeros[:10]))

    # -- 3. Employment partitions. ---------------------------------------
    share_bad = []
    for scenario, s in (security_report.get("scenarios") or {}).items():
        total = sum(c.get("share_employment", 0)
                    for c in (s.get("by_octant") or {}).values())
        if abs(total - 1.0) > 0.005:
            share_bad.append({"scenario": scenario, "sum_of_shares": round(total, 4)})
    checks.append(_check("cell_shares_partition", "error", not share_bad,
                         f"{len(share_bad)} scenarios have cell employment shares "
                         f"that do not sum to 1.0, so a SOC is being counted in "
                         f"more than one cell", share_bad))

    # -- 4. The matrix total must equal the SOC rollup. -------------------
    soc_total = sum(_f(r, "total_employment") or 0.0 for r in soc)
    reported = {sc: (s.get("total_employment") or 0.0)
                for sc, s in (security_report.get("scenarios") or {}).items()}
    mismatch = {sc: v for sc, v in reported.items()
                if soc_total and abs(v - soc_total) / soc_total > 0.02}
    checks.append(_check("employment_matches_soc_rollup", "error", not mismatch,
                         f"matrix employment differs from the SOC rollup "
                         f"({soc_total:,.0f}) by more than 2% in "
                         f"{len(mismatch)} scenarios", mismatch))

    # -- 5. Scenario monotonicity. ---------------------------------------
    # More permissive assumptions cannot automate less work. This is the check
    # that catches a threshold edit applied to the wrong scenario.
    by_occ: dict[str, dict[str, float]] = {}
    for r in security:
        v = _f(r, "efficiency")
        if v is not None:
            by_occ.setdefault(r["onet_soc_code"], {})[r["scenario"]] = v
    non_mono = [
        {"occupation": code, **vals} for code, vals in by_occ.items()
        if {"modest", "substantial", "extreme"} <= set(vals)
        and not (vals["modest"] <= vals["substantial"] <= vals["extreme"] + 1e-9)
    ]
    checks.append(_check("efficiency_rises_with_scenario", "error", not non_mono,
                         f"{len(non_mono)} occupations do not have efficiency "
                         f"rising monotonically from modest to extreme",
                         non_mono[:10]))

    # -- 6. Anchors. -----------------------------------------------------
    substantial = [r for r in security if r.get("scenario") == "substantial"]
    checks += _anchor_checks(substantial, "removal_risk", "title",
                             RISK_ANCHORS, "removal_risk")
    checks += _anchor_checks(susceptibility, "exposure", "title",
                             EXPOSURE_ANCHORS, "exposure")

    # -- 7. Nothing is silently absent. ----------------------------------
    missing_axis = [r.get("title") for r in substantial
                    if _f(r, "efficiency") is None or _f(r, "removal_risk") is None
                    or _f(r, "reconstitution") is None]
    checks.append(_check("every_occupation_has_all_three_axes", "error",
                         not missing_axis,
                         f"{len(missing_axis)} occupations are missing at least one "
                         f"matrix axis", missing_axis[:10]))

    summary = {
        "occupations_checked": len(substantial),
        "errors": sum(1 for c in checks if not c["passed"] and c["severity"] == "error"),
        "warnings": sum(1 for c in checks if not c["passed"] and c["severity"] == "warn"),
        "soc_employment_total": soc_total,
    }
    return checks, summary


def log_report(checks: Sequence[dict[str, Any]], summary: dict[str, Any]) -> int:
    log.info("-" * 72)
    for c in checks:
        level = {"ok": "PASS", "warn": "WARN", "error": "FAIL"}[
            "ok" if c["passed"] else c["severity"]]
        log.info("%-5s %-38s %s", level, c["check"], c["detail"])
    log.info("-" * 72)
    return summary["errors"]
