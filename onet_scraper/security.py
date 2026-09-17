"""A national-security reading of the corpus: efficiency, risk, reconstitution.

The susceptibility and handoff modules ask what AI *can* do and what we would
*permit*. Neither asks the question a defence planner asks, which is not "will
this be automated" but "if we hand it over and we are wrong, can we get the
capability back, and how fast". That is a third, independent axis, and it is the
reason this module exists rather than another view over the same two.

THE THREE AXES

  x  efficiency        what deploying AI actually buys. Not raw exposure: an
                       occupation whose one exposed task carries 3% of its
                       importance mass is not an efficiency opportunity. This is
                       the importance-weighted share of task mass AI can carry,
                       with automated tasks at full credit and augmented tasks at
                       partial credit, so it moves with the scenario selector.

  y  removal_risk      the cost of taking the human out of the loop. Built from
                       error cost (how bad a wrong answer is), accountability
                       (whether legitimacy requires a person to answer for the
                       decision) and judgment under uncertainty (how often the
                       situation is one no rule anticipated).

  z  reconstitution    how hard the human capability is to rebuild once it has
                       thinned. Training depth from O*NET's Job Zone, workforce
                       scarcity, and how isolated the work is from occupations
                       that could cross-train into it.

WHY THESE WEIGHTS AND NOT OTHERS. The removal-risk weights are a judgment, not a
measurement. We deliberately do NOT reuse `anchoring` from susceptibility.py,
which averages stakes, interpersonal demand, judgment and physical embodiment.
Two of those do not belong here:

  interpersonal_demand        a service-quality property. A call centre scores
                              high and carries no national-security risk.
  physical_embodiment         a capability *limit*, not a consequence. Work a
                              robot cannot reach is not thereby high-stakes.

Including them is what makes a generic "human-centred work" index; excluding them
is what makes this a risk index. That single choice is the main thing to argue
with in this module.

WHAT THIS IS NOT. O*NET carries no industry, clearance, or criticality field, so
nothing here identifies an occupation as defence-relevant. This module scores
*properties* that make a handoff strategically dangerous, over the whole STEM
corpus. Which fields matter is the reader's overlay, not our measurement.
"""

from __future__ import annotations

import collections
import logging
import math
import statistics
from statistics import fmean
from typing import Any, Iterable, Sequence

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Axis construction
# ---------------------------------------------------------------------------

# An augmented task still has a human in it, so AI carries part of the load, not
# all of it. Half is a round number standing in for "some"; the ranking is not
# sensitive to it between about 0.35 and 0.65, which we test.
AUGMENTED_CREDIT = 0.5

# Removal-risk weights. Error cost leads because it sets the magnitude of being
# wrong; accountability follows because a legitimacy requirement survives good
# performance; judgment is third because it drives how often the unanticipated
# case arrives at all.
RISK_WEIGHTS = {
    "error_cost": 0.45,
    "accountability_requirement": 0.35,
    "judgment_under_uncertainty": 0.20,
}

# Reconstitution weights. Training depth dominates: no amount of money shortens a
# doctorate. Scarcity matters because a small cohort has no slack. Isolation
# matters least because cross-training is the one lever a planner can pull.
RECONSTITUTION_WEIGHTS = {"training_depth": 0.50, "scarcity": 0.30, "isolation": 0.20}

# O*NET Job Zone -> years of preparation, mapped to 0-100. Zone 5 is "extensive
# preparation" (doctoral / professional); zone 1 is "little or none".
JOB_ZONE_DEPTH = {1: 0.0, 2: 25.0, 3: 50.0, 4: 75.0, 5: 100.0}

MIDPOINT = 50.0


def _f(row: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        value = row.get(key)
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def weights(tasks: Sequence[dict[str, Any]]) -> list[float]:
    """One weight per task, with no task silently dropped.

    O*NET does not rate task importance for every occupation - 159 of 5,612
    tasks here carry none, and for six occupations (Cardiologists, Pediatric and
    Orthopedic Surgeons, Emergency Medical Technicians, Hydrologic Technicians,
    Health Information Technologists) *every* task is unrated. Skipping unrated
    tasks left those occupations with a zero denominator, which returned 0.0 and
    filed surgeons under "nothing is pushing this work toward AI".

    So: an unrated task takes the mean of the rated tasks in the same
    occupation, and an occupation with nothing rated falls back to equal
    weighting. Equal weighting is the honest default - it says we do not know
    which of these tasks matters more, not that none of them matters.
    """
    rated = [_f(t, "importance") for t in tasks if _f(t, "importance") > 0]
    fill = fmean(rated) if rated else 1.0
    return [_f(t, "importance") if _f(t, "importance") > 0 else fill for t in tasks]


def efficiency(tasks: Sequence[dict[str, Any]], scenario: str) -> float:
    """Importance-weighted share of an occupation's task mass AI can carry."""
    num = den = 0.0
    for t, weight in zip(tasks, weights(tasks)):
        fate = (t.get(scenario) or "").strip()
        credit = 1.0 if fate == "automated" else (
            AUGMENTED_CREDIT if fate == "augmented" else 0.0)
        num += weight * credit
        den += weight
    return round(100.0 * num / den, 1) if den else 0.0


def removal_risk(tasks: Sequence[dict[str, Any]]) -> float:
    """Importance-weighted cost of taking the human out of the loop."""
    num = den = 0.0
    for t, weight in zip(tasks, weights(tasks)):
        score = sum(w * _f(t, key) for key, w in RISK_WEIGHTS.items())
        num += weight * score
        den += weight
    return round(num / den, 1) if den else 0.0


def risk_at_stake(tasks: Sequence[dict[str, Any]], scenario: str) -> float:
    """Removal risk restricted to the task mass actually being handed over.

    An occupation can be high-risk overall while everything AI would take is
    low-risk. That is a materially different situation from one where the risky
    work is exactly the work being handed over, and this separates them.
    """
    num = den = 0.0
    for t, base in zip(tasks, weights(tasks)):
        fate = (t.get(scenario) or "").strip()
        credit = 1.0 if fate == "automated" else (
            AUGMENTED_CREDIT if fate == "augmented" else 0.0)
        weight = base * credit
        if weight <= 0:
            continue
        num += weight * sum(w * _f(t, key) for key, w in RISK_WEIGHTS.items())
        den += weight
    return round(num / den, 1) if den else 0.0


def _scarcity(employment: float | None, lo: float, hi: float) -> float:
    """Small cohorts are harder to rebuild. Log scale: the corpus spans 4 orders
    of magnitude, so a linear read would call everything except nurses scarce."""
    if not employment or employment <= 0 or hi <= lo:
        return MIDPOINT
    span = math.log10(max(employment, 1.0))
    return round(100.0 * (1.0 - (span - lo) / (hi - lo)), 1)


def reconstitution(
    job_zone: float | None,
    employment: float | None,
    similarity: float | None,
    lo: float,
    hi: float,
) -> dict[str, float]:
    """How hard it is to rebuild this human capability once it has thinned."""
    zone = int(job_zone) if job_zone else 0
    depth = JOB_ZONE_DEPTH.get(zone, MIDPOINT)
    scarce = _scarcity(employment, lo, hi)
    # mean_similarity is share of activities shared with neighbouring
    # occupations: high similarity means people can convert in, so isolation -
    # and therefore reconstitution difficulty - is its inverse.
    isolation = MIDPOINT if similarity is None else round(
        100.0 * (1.0 - min(max(similarity, 0.0), 1.0)), 1)
    total = (RECONSTITUTION_WEIGHTS["training_depth"] * depth
             + RECONSTITUTION_WEIGHTS["scarcity"] * scarce
             + RECONSTITUTION_WEIGHTS["isolation"] * isolation)
    return {"training_depth": depth, "scarcity": scarce,
            "isolation": isolation, "reconstitution": round(total, 1)}


# ---------------------------------------------------------------------------
# The matrix itself
# ---------------------------------------------------------------------------

# Eight cells, keyed (efficiency high?, risk high?, reconstitution hard?).
OCTANTS: dict[tuple[bool, bool, bool], tuple[str, str]] = {
    (True, True, True): ("Strategic trap",
        "Strong pull to automate, severe consequences if it fails, and the human "
        "capability cannot be rebuilt on a crisis timeline."),
    (True, True, False): ("Reversible gamble",
        "Real risk in handing it over, but the workforce can be reconstituted, so "
        "the decision is recoverable."),
    (True, False, True): ("Guard the pipeline",
        "Safe to hand over on its merits; the exposure is losing the training "
        "pipeline that produces the people you would need later."),
    (True, False, False): ("Clear win",
        "High efficiency, low consequence, replaceable skills. Automate."),
    (False, True, True): ("Protect",
        "Little efficiency on offer, severe downside, irreplaceable people. "
        "Nothing here justifies a handoff."),
    (False, True, False): ("Hold the line",
        "Not much to gain and a real downside, but recoverable if it happens."),
    (False, False, True): ("Quiet attrition",
        "Nothing is pushing this work toward AI, but it is fragile: if the cohort "
        "drifts away for unrelated reasons it does not come back."),
    (False, False, False): ("Low stakes",
        "No strong pull, no severe consequence, replaceable. Leave it."),
}


# How much strategic attention each cell demands, as four ordinal tiers. This is
# NOT a ranking of the axes - it is a ranking of urgency, which is why "Protect"
# (severe but nothing is pulling it) sits below "Strategic trap" (severe and
# being pulled), and why "Quiet attrition" outranks "Hold the line" despite
# scoring lower on risk: an irreversible loss you are not watching for is worse
# than a reversible one you are.
SEVERITY: dict[str, int] = {
    "Strategic trap": 3,
    "Guard the pipeline": 2,
    "Protect": 2,
    "Reversible gamble": 1,
    "Quiet attrition": 1,
    "Hold the line": 0,
    "Clear win": 0,
    "Low stakes": 0,
}
SEVERITY_LABELS = ("Low", "Moderate", "High", "Critical")


def severity(octant_name: str) -> int:
    return SEVERITY.get(octant_name, 0)


def octant(eff: float, risk: float, recon: float,
           midpoint: float = MIDPOINT) -> tuple[str, str]:
    return OCTANTS[(eff >= midpoint, risk >= midpoint, recon >= midpoint)]


def trap_score(eff: float, risk: float, recon: float) -> float:
    """Rank on the product, so a low value on any axis pulls the score down.

    A sum would let an occupation with overwhelming efficiency and no risk
    outrank one that is dangerous on all three, which is the opposite of what a
    planner wants to read off the top of the list.
    """
    return round(100.0 * (eff / 100.0) * (risk / 100.0) * (recon / 100.0), 1)


def employment_shares(codes: Sequence[str], employment: dict[str, float],
                      soc_of: dict[str, str]) -> dict[str, float]:
    """Split each SOC's employment evenly across its O*NET occupations.

    Employment is published at 6-digit SOC. Collapsing to SOC before summing is
    correct for a *total* but not for a *partition*: 18 of the 37 multi-occupation
    SOCs have members that land in different cells of this matrix, and if each
    cell claims the SOC's full figure the cell shares sum to 130%.

    An even split is an assumption - O*NET does not publish how a SOC's workers
    divide among its constituent occupations - but it is a stated one, and it
    makes every slice of this dataset sum exactly to the corpus total no matter
    how the reader cuts it. The alternative, classifying whole SOCs, would throw
    away the occupation-level distinctions the matrix exists to show.
    """
    members: dict[str, list[str]] = {}
    for code in codes:
        members.setdefault(soc_of.get(code, code), []).append(code)
    out: dict[str, float] = {}
    for soc, group in members.items():
        total = next((employment[c] for c in group if c in employment), None)
        if total is None:
            continue
        for code in group:
            out[code] = total / len(group)
    return out


SECURITY_COLUMNS = (
    "onet_soc_code", "title", "stem_occupation_types", "field", "job_zone",
    "total_employment", "employment_share", "n_tasks", "scenario", "efficiency", "removal_risk",
    "risk_at_stake", "reconstitution", "training_depth", "scarcity", "isolation",
    "octant", "trap_score", "erosion_risk", "willingness_gap",
)

FIELD_COLUMNS = (
    "field", "scenario", "occupations", "total_employment", "efficiency",
    "removal_risk", "reconstitution", "octant", "trap_score",
)


# The role-type categories O*NET puts at the top of its STEM tree. These are not
# disciplines - an occupation is "Managerial" the way it is "full-time", not the
# way it is "Computer and Mathematical" - so they are only used as a field label
# when the occupation has no leaf discipline at all.
ROLE_TYPES = ("Research, Development, Design, and Practitioners",
              "Technologists and Technicians",
              "Postsecondary Teaching", "Managerial", "Sales")


def field_map(memberships: Sequence[dict[str, Any]],
              categories: Sequence[dict[str, Any]]) -> dict[str, str]:
    """Pick one field per occupation from its STEM category memberships.

    O*NET's STEM tree mixes two kinds of node: four leaf *disciplines*
    (Architecture and Engineering, Computer and Mathematical, Healthcare
    Practitioners and Technical, Life/Physical/Social Science) and five
    top-level *role types*. A security matrix wants the discipline, so we prefer
    a leaf and fall back to the role type for the 31 occupations - teaching,
    management and sales - that have no leaf membership.

    An occupation with several leaf memberships gets the lowest category id, so
    the choice is deterministic across runs rather than dict-order dependent.
    """
    leaf = {c["stem_category_id"] for c in categories
            if str(c.get("is_leaf")) == "1"}
    names = {c["stem_category_id"]: c["stem_category_name"] for c in categories}
    best: dict[str, tuple[int, str]] = {}
    for row in memberships:
        code = row["onet_soc_code"]
        cid = row["stem_category_id"]
        name = names.get(cid) or row.get("stem_category_name") or "Unclassified"
        # rank 0 beats rank 1: a discipline always wins over a role type.
        rank = 0 if cid in leaf else 1
        current = best.get(code)
        if current is None or (rank, cid) < current[0]:
            best[code] = ((rank, cid), name)
    return {code: name for code, (_, name) in best.items()}


def build(
    fates: Sequence[dict[str, Any]],
    task_scores: Sequence[dict[str, Any]],
    occupations: Sequence[dict[str, Any]],
    employment: dict[str, float] | None = None,
    similarity: dict[str, float] | None = None,
    handoff: dict[str, dict[str, Any]] | None = None,
    fields: dict[str, str] | None = None,
    soc_of: dict[str, str] | None = None,
    scenarios: Sequence[str] = ("modest", "substantial", "extreme"),
) -> list[dict[str, Any]]:
    """One row per occupation per scenario."""
    employment = employment or {}
    similarity = similarity or {}
    handoff = handoff or {}
    fields = fields or {}
    soc_of = soc_of or {}

    # Join the risk components onto the fate rows by task id. task_fates carries
    # importance and the per-scenario verdict; the raw dimensions live in
    # task_automation_scores.
    risk_by_task = {t["task_id"]: t for t in task_scores}
    by_occ: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in fates:
        merged = dict(row)
        extra = risk_by_task.get(row["task_id"])
        if extra:
            for key in RISK_WEIGHTS:
                merged[key] = extra.get(key)
        by_occ[row["onet_soc_code"]].append(merged)

    # Corpus-wide log-employment bounds for the scarcity scale.
    sizes = [math.log10(max(v, 1.0)) for v in employment.values() if v and v > 0]
    lo, hi = (min(sizes), max(sizes)) if sizes else (0.0, 1.0)
    shares = employment_shares([o["onet_soc_code"] for o in occupations],
                               employment, soc_of)

    rows: list[dict[str, Any]] = []
    for occ in occupations:
        code = occ["onet_soc_code"]
        tasks = by_occ.get(code) or []
        if not tasks:
            continue
        emp = employment.get(code)
        parts = reconstitution(
            _f(occ, "job_zone") or None, emp, similarity.get(code), lo, hi)
        hand = handoff.get(code) or {}
        risk = removal_risk(tasks)
        for scenario in scenarios:
            eff = efficiency(tasks, scenario)
            name, _ = octant(eff, risk, parts["reconstitution"])
            rows.append({
                "onet_soc_code": code,
                "title": occ.get("title", ""),
                "stem_occupation_types": occ.get("stem_occupation_types", ""),
                "field": fields.get(code, "Unclassified"),
                "job_zone": occ.get("job_zone"),
                "total_employment": emp,
                "employment_share": shares.get(code),
                "n_tasks": len(tasks),
                "scenario": scenario,
                "efficiency": eff,
                "removal_risk": risk,
                "risk_at_stake": risk_at_stake(tasks, scenario),
                "reconstitution": parts["reconstitution"],
                "training_depth": parts["training_depth"],
                "scarcity": parts["scarcity"],
                "isolation": parts["isolation"],
                "octant": name,
                "severity": SEVERITY[name],
                "severity_label": SEVERITY_LABELS[SEVERITY[name]],
                "trap_score": trap_score(eff, risk, parts["reconstitution"]),
                "erosion_risk": hand.get("erosion_risk"),
                "willingness_gap": hand.get("willingness_gap"),
            })
    return sorted(rows, key=lambda r: (r["scenario"], -r["trap_score"]))


def by_field(rows: Sequence[dict[str, Any]],
             soc_of: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """Aggregate to STEM field - the grain the matrix is read at.

    Employment is collapsed to 6-digit SOC before summing. Several O*NET
    occupations can share one SOC and each carries that SOC's full employment
    figure, so summing the O*NET rows double-counts. See METHODOLOGY.md 6.3.
    """
    soc_of = soc_of or {}
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = collections.defaultdict(list)
    for row in rows:
        grouped[(row["field"], row["scenario"])].append(row)

    out: list[dict[str, Any]] = []
    for (field, scenario), members in sorted(grouped.items()):
        # Per-occupation shares, so two fields cannot both claim a straddling
        # SOC's workers and the field totals add to the corpus total.
        emp = sum(float(m.get("employment_share") or 0) for m in members)
        # Weight the axes by employment where we have it, so a field is
        # positioned by where its workers are, not by where its job titles are.
        def wmean(key: str) -> float:
            num = den = 0.0
            for m in members:
                w = float(m["total_employment"] or 0) or 1.0
                num += w * m[key]
                den += w
            return round(num / den, 1) if den else 0.0
        eff, risk = wmean("efficiency"), wmean("removal_risk")
        recon = wmean("reconstitution")
        name, _ = octant(eff, risk, recon)
        out.append({
            "field": field, "scenario": scenario, "occupations": len(members),
            "total_employment": emp, "efficiency": eff, "removal_risk": risk,
            "reconstitution": recon, "octant": name,
            "trap_score": trap_score(eff, risk, recon),
        })
    return out


def summarise(rows: Sequence[dict[str, Any]],
              soc_of: dict[str, str] | None = None) -> dict[str, Any]:
    soc_of = soc_of or {}
    report: dict[str, Any] = {"occupations": len({r["onet_soc_code"] for r in rows}),
                              "scenarios": {}}
    for scenario in sorted({r["scenario"] for r in rows}):
        members = [r for r in rows if r["scenario"] == scenario]
        counts = collections.Counter(r["octant"] for r in members)
        # Partition on the per-occupation share, not the SOC figure: a SOC whose
        # members land in different cells would otherwise be counted once per
        # cell. The shares sum to the same corpus total.
        def emp_of(subset: Iterable[dict[str, Any]]) -> float:
            return sum(float(m["employment_share"] or 0) for m in subset)
        total_emp = emp_of(members)
        by_octant = {}
        for name, _ in OCTANTS.values():
            subset = [m for m in members if m["octant"] == name]
            e = emp_of(subset)
            by_octant[name] = {
                "occupations": counts.get(name, 0),
                "employment": e,
                "share_employment": round(e / total_emp, 4) if total_emp else 0.0,
            }
        traps = [m for m in members if m["octant"] == "Strategic trap"]
        report["scenarios"][scenario] = {
            "by_octant": by_octant,
            "total_employment": total_emp,
            "mean_efficiency": round(statistics.fmean(
                m["efficiency"] for m in members), 1) if members else 0.0,
            "mean_removal_risk": round(statistics.fmean(
                m["removal_risk"] for m in members), 1) if members else 0.0,
            "mean_reconstitution": round(statistics.fmean(
                m["reconstitution"] for m in members), 1) if members else 0.0,
            "top_traps": [{"title": m["title"], "trap_score": m["trap_score"],
                           "efficiency": m["efficiency"],
                           "removal_risk": m["removal_risk"],
                           "reconstitution": m["reconstitution"]}
                          for m in sorted(traps, key=lambda m: -m["trap_score"])[:10]],
        }
    return report
