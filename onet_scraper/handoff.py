"""Watson's handoff framework, mapped onto the scored O*NET corpus.

Phil Watson, "Considering Handoffs of Cognitive Leadership from Humans to AI as
a Driving Element of Strategic Technical Surprise" (Applied Emergence, July
2026) proposes scoring work on two independent axes and locating each unit on a
six-stage scale of cognitive leadership. A handoff is a crossing between stages.

  Tractability - can AI lead?  recurrence, feedback speed and clarity, whether
    the state of the world is machine readable, how formalizable the options are
  Resistance  - will it be permitted?  stakes and irreversibility of error, and
    whether legitimacy requires a human to own the decision regardless of
    performance

WHAT MAPS CLEANLY, AND WHAT DOES NOT. Our rubric was written before this paper
and measures six of Watson's properties, not all eight:

  tractability
    machine-readable state   <- 100 - physical_embodiment_required
    formalizable options     <- 100 - judgment_under_uncertainty
    (general capability)     <- llm_exposure
    recurrence               MISSING - available as O*NET's FT scale in
                             task_ratings.csv (--with-ratings), not yet used
    feedback speed/clarity   MISSING - not in O*NET at all; needs new scoring
  resistance
    stakes / irreversibility <- error_cost
    legitimacy needs a human <- accountability_requirement
    (relational demand)      <- interpersonal_demand

The deeper mismatch is the unit of analysis. Watson's unit is the recurring
*decision*; ours is the O*NET task. He is explicit that "the novel work is to
identify which tasks are decisions". We have not done that, so everything here
treats tasks as a proxy for decisions - serviceable for ranking work by exposure,
but not yet a decision-system map. Read the stage numbers as provisional.

Watson scores capability and deployment separately and reads the gap between
them as willingness to permit the handoff. We already had that gap; this module
renames it to what he shows it means.
"""

from __future__ import annotations

import logging
import statistics
from typing import Any, Sequence

log = logging.getLogger(__name__)

# The six-stage scale of cognitive leadership (Watson, step 3).
STAGES = (
    "Human only",
    "AI informed",
    "AI recommended",
    "AI executed, human veto",
    "AI led, human audit",
    "AI led, unreviewed",
)

# Watson expects two crossings to carry most of the strategic weight:
# proposing action -> taking it (2 -> 3), and human veto -> after-the-fact
# audit (3 -> 4). The second is his "handoff by erosion".
WEIGHTY_CROSSINGS = {2: "proposing action to taking it",
                     3: "human veto to after-the-fact audit (erosion)"}

HANDOFF_COLUMNS = ("onet_soc_code", "title", "stem_occupation_types",
                   "total_employment", "tractability", "resistance",
                   "frontier_distance", "stage_now", "stage_now_label",
                   "stage_reachable", "stage_reachable_label", "pending_crossings",
                   "willingness_gap", "classification", "erosion_risk",
                   "surprise_potential", "weighty_crossing")


def _f(row: dict[str, Any], key: str, default: float = 0.0) -> float:
    value = row.get(key)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def axes(row: dict[str, Any]) -> tuple[float, float]:
    """(tractability, resistance) on 0-100, from the rated dimensions."""
    tractability = statistics.fmean([
        _f(row, "llm_exposure"),
        100 - _f(row, "physical_embodiment_required"),
        100 - _f(row, "judgment_under_uncertainty"),
    ])
    resistance = statistics.fmean([
        _f(row, "accountability_requirement"),
        _f(row, "error_cost"),
        _f(row, "interpersonal_demand"),
    ])
    return round(tractability, 1), round(resistance, 1)


def stage(capability: float, resistance: float) -> int:
    """Where cognitive leadership sits: the lower of what AI can do and what is allowed.

    Watson's first four properties decide whether AI *can* lead; the last two
    decide whether it *will be permitted*. So the observed stage is the minimum
    of the two ceilings, not an average of them.
    """
    can = capability / 100 * 5
    permitted = (1 - resistance / 100) * 5
    return max(0, min(5, round(min(can, permitted))))


# CALIBRATION, NOT THEORY. Watson's figure shows the frontier's shape but no
# numbers, and nothing fixes where it sits on our 0-100 axes. FRONTIER_K is set
# so the curve passes through the median of the observed cloud (T=59, R=48),
# which makes the four categories relative positions within STEM rather than
# absolute claims about when a handoff occurs. CROSSING_BAND is half the width
# of the "crossing now" strip, roughly a quarter of the resistance IQR.
# Re-fit both if the corpus changes; do not read them as measurements.
FRONTIER_K = 53.0
CROSSING_BAND = 5.0

# A constant-product curve alone misclassifies the bottom-left. R = k^2/T is the
# locus where T*R is constant, so "high tractability, low resistance" and "low on
# both" sit on the same side of it - and the second is not a handoff, it is work
# AI cannot lead at any level of consequence. Watson is explicit that the first
# four properties decide whether AI *can* lead; below this floor, resistance is
# simply not the binding constraint.
TRACTABILITY_FLOOR = 50.0


def frontier_resistance(tractability: float, k: float = FRONTIER_K) -> float:
    """The frontier curve: the resistance a given tractability can currently overcome.

    The hyperbola R = k^2 / T matches the shape in Watson's figure - highly
    tractable work crosses even at some consequence, while intractable work
    stays human-held however low the stakes. Over our observed range
    (T 28-80) the curve is close to linear, so the shape is doing less work
    here than the ordering is.
    """
    return min(100.0, (k * k) / max(tractability, 1.0))


def classify(tractability: float, resistance: float, willingness_gap: float) -> str:
    """Watson's four figure categories.

    'Watch point' is the strategically interesting one: capability is present,
    resistance is what is holding the line, and the willingness gap is wide - so
    an actor with looser accountability norms could cross first.
    """
    if tractability < TRACTABILITY_FLOOR:
        # AI cannot lead this work yet; consequence is not what is holding it.
        return "Human held"
    margin = resistance - frontier_resistance(tractability)
    if tractability >= 55 and resistance >= 50 and willingness_gap >= 40:
        return "Watch point"
    if margin < -CROSSING_BAND:
        return "Handed off"
    if margin <= CROSSING_BAND:
        return "Crossing now"
    return "Human held"


def build(
    scored: Sequence[dict[str, Any]],
    employment: dict[str, float] | None = None,
    reach: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    employment = employment or {}
    reach = reach or {}
    rows = []
    for row in scored:
        code = row["onet_soc_code"]
        tract, resist = axes(row)
        deployed = _f(row, "automation_feasibility_today")
        capability = _f(row, "llm_exposure")
        gap = round(capability - deployed, 1)

        now = stage(deployed, resist)
        reachable = stage(capability, resist)
        cls = classify(tract, resist, gap)

        # Erosion: AI can already do the work, a human still nominally signs off,
        # and the sign-off is the only thing in the way. Watson's merge-approval
        # case - the crossing happens by review thinning, with no event to observe.
        erosion = round(min(100.0, max(0.0,
            (capability - 50) * 0.9 + (_f(row, "accountability_requirement") - 40) * 0.5
            - _f(row, "physical_embodiment_required") * 0.35)), 1)

        # Surprise potential. Watson uses three factors: magnitude of change,
        # asymmetry of incentive to cross early, and low external visibility.
        # We can compute the first two. Visibility is not measurable from O*NET,
        # so erosion risk stands in for it - a crossing with no discrete event is
        # exactly the low-visibility case - and that substitution is a judgment,
        # not a measurement.
        magnitude = (reachable - now) / 5
        scale_weight = employment.get(code) or reach.get(code) or 1.0
        surprise = round(magnitude * (gap / 100) * (erosion / 100) * 100, 1)

        rows.append({
            "onet_soc_code": code,
            "title": row.get("title", ""),
            "stem_occupation_types": row.get("stem_occupation_types", ""),
            "total_employment": employment.get(code),
            "tractability": tract,
            "resistance": resist,
            "frontier_distance": round(frontier_resistance(tract) - resist, 1),
            "stage_now": now,
            "stage_now_label": STAGES[now],
            "stage_reachable": reachable,
            "stage_reachable_label": STAGES[reachable],
            "pending_crossings": reachable - now,
            "willingness_gap": gap,
            "classification": cls,
            "erosion_risk": erosion,
            "surprise_potential": surprise,
            "weighty_crossing": WEIGHTY_CROSSINGS.get(now, "") if reachable > now else "",
            "_scale": scale_weight,
        })
    return sorted(rows, key=lambda r: -r["surprise_potential"])


def summarise(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    import collections
    by_class = collections.Counter(r["classification"] for r in rows)
    by_stage = collections.Counter(r["stage_now_label"] for r in rows)
    pending = [r for r in rows if r["pending_crossings"] > 0]
    weighty = [r for r in pending if r["weighty_crossing"]]
    emp = lambda rs: sum(r["total_employment"] or 0 for r in rs)
    return {
        "occupations": len(rows),
        "by_classification": dict(by_class),
        "by_current_stage": dict(by_stage),
        "with_pending_crossing": len(pending),
        "at_a_weighty_crossing": len(weighty),
        "employment_at_weighty_crossing": emp(weighty),
        "employment_at_watch_points": emp([r for r in rows
                                           if r["classification"] == "Watch point"]),
        "mean_willingness_gap": round(
            statistics.fmean(r["willingness_gap"] for r in rows), 1) if rows else 0,
    }
