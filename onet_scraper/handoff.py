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
    recurrence               MEASURED but not folded in. O*NET's FT scale, via
                             --with-ratings, for 262 of 268 occupations, and
                             reported in occupation_handoff.csv. Averaging it
                             into tractability compresses the axis by a third
                             and invalidates the frontier calibration - see
                             axes(). Closing this properly needs the frontier
                             re-derived.
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

import dataclasses
import logging
import math
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
                   "total_employment", "tractability", "resistance", "recurrence",
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


def axes(row: dict[str, Any], recurrence: float | None = None) -> tuple[float, float]:
    """(tractability, resistance) on 0-100, from the rated dimensions.

    `recurrence` is O*NET's FT scale, and the pipeline does NOT pass it.

    It is one of the two tractability properties Watson names and our rubric
    never measured, so measuring it was worth doing - onet_ratings.recurrence
    now does, for 262 of 268 occupations, and occupation_handoff.csv reports it.
    Folding it into this average is a separate decision, and not a free one.

    Recurrence does not point the same way as the terms already here. Against
    the 3-term axis it correlates at r = -0.53, and the components explain why:

        r(recurrence, llm_exposure)                = -0.53
        r(recurrence, physical_embodiment_required) = +0.53
        r(recurrence, judgment_under_uncertainty)   = -0.04

    The most repetitive work in this corpus is the most physically embodied and
    the least exposed to language models. Emergency medicine physicians,
    physician assistants and orthodontists score highest on recurrence because
    they repeat the same procedures; anthropologists and nuclear engineers score
    lowest because their work is rare and novel. That is a finding about STEM
    work, and it is also a warning: averaging a term in at r = -0.53 cancels
    much of the existing signal rather than adding to it. The axis spread falls
    by a third (sd 9.95 -> 6.44, range 27.5-79.8 -> 35.3-72.7), and since
    TRACTABILITY_FLOOR and FRONTIER_K were calibrated against the wider
    distribution, 24 occupations move out of "Human held" and 24 into "Handed
    off" - which would be reported as AI having quietly taken over a quarter
    more of the corpus, when nothing about the world changed.

    Whether Watson's recurrence *should* raise tractability for hands-on
    procedural work is a real question and not one the arithmetic can settle.

    Using it properly means re-deriving the frontier against the new
    distribution, or expressing the constants as percentiles of the observed
    axis rather than absolutes so that adding a term cannot silently
    reclassify. That is analytical work with a judgment in it, so it is left
    undone and visible rather than done badly. The parameter exists so the
    comparison can be run.
    """
    terms = [
        _f(row, "llm_exposure"),
        100 - _f(row, "physical_embodiment_required"),
        100 - _f(row, "judgment_under_uncertainty"),
    ]
    if recurrence is not None:
        terms.append(recurrence)
    tractability = statistics.fmean(terms)
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
# --------------------------------------------------------------------------- #
# Calibration
# --------------------------------------------------------------------------- #
# These were absolute values on the 0-100 scales, chosen by eye against release
# 31.0. That made them silently fragile: the thresholds are meaningful only
# relative to the spread of the axis they cut, and the axis is a mean of terms
# that can be added to or reweighted. Adding recurrence to tractability - a term
# correlated at -0.53 with the other three - narrows the spread by a third, and
# the fixed thresholds then reclassified 24 occupations out of "human held" and
# 24 into "handed off". Nothing about the world had changed. Any future change
# to the rubric would do the same thing, quietly.
#
# So the calibration now travels with the distribution. Each constant is
# expressed as a quantile of the observed values, and the quantiles below were
# obtained by *inverting* the original absolutes against release 31.0 - so on
# that release they reproduce the previous thresholds to four decimal places and
# every classification is unchanged. A test asserts that identity. The point is
# not to move today's answer; it is that tomorrow's answer moves for a reason.
FLOOR_QUANTILE = 0.191011        # was TRACTABILITY_FLOOR = 50.0
FRONTIER_QUANTILE = 0.385560     # was FRONTIER_K = 53.0, i.e. T*R = 2809
WATCH_TRACT_QUANTILE = 0.353933  # was tractability >= 55
WATCH_RESIST_QUANTILE = 0.575531 # was resistance >= 50
WATCH_GAP_QUANTILE = 0.750936    # was willingness_gap >= 40
CROSSING_BAND_SD = 0.39117889    # was CROSSING_BAND = 5.0, i.e. 0.39 sd of resistance
# The extra digits are not false precision, they are how the identity test
# passes. Architects sit at a frontier margin of +4.999362, within 0.0007 of the
# old 5.0 band, so rounding the coefficient to 0.391 moves them from "crossing
# now" to "human held". That is worth knowing on its own: their classification
# was never really determined by the data.

# The absolutes, kept as the fallback for a caller with no corpus to calibrate
# against, and as the reference the identity test checks.
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


def _quantile(sorted_values: Sequence[float], q: float) -> float:
    """Linear-interpolated quantile. statistics.quantiles cuts at fixed
    fractions; this needs an arbitrary one."""
    if not sorted_values:
        return 0.0
    if q <= 0:
        return sorted_values[0]
    if q >= 1:
        return sorted_values[-1]
    pos = q * (len(sorted_values) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    return sorted_values[lo] + (pos - lo) * (sorted_values[hi] - sorted_values[lo])


@dataclasses.dataclass(frozen=True)
class Calibration:
    """The frontier, derived from a corpus rather than asserted against it."""

    tractability_floor: float
    frontier_k: float
    crossing_band: float
    watch_tractability: float
    watch_resistance: float
    watch_gap: float

    @classmethod
    def absolute(cls) -> "Calibration":
        """The original hand-chosen values, for a caller with no corpus."""
        return cls(TRACTABILITY_FLOOR, FRONTIER_K, CROSSING_BAND, 55.0, 50.0, 40.0)


def calibrate(tractability: Sequence[float], resistance: Sequence[float],
              gaps: Sequence[float]) -> Calibration:
    """Read the thresholds off the distribution they are meant to cut."""
    if not tractability or not resistance:
        return Calibration.absolute()
    t = sorted(tractability)
    r = sorted(resistance)
    g = sorted(gaps) if gaps else [0.0]
    products = sorted(a * b for a, b in zip(tractability, resistance))
    sd = statistics.pstdev(r) if len(r) > 1 else 0.0
    return Calibration(
        tractability_floor=_quantile(t, FLOOR_QUANTILE),
        # The frontier is the locus T*R = k^2, so calibrating it is a threshold
        # on the product, and the product is what gets a quantile.
        frontier_k=math.sqrt(max(_quantile(products, FRONTIER_QUANTILE), 1.0)),
        crossing_band=CROSSING_BAND_SD * sd,
        watch_tractability=_quantile(t, WATCH_TRACT_QUANTILE),
        watch_resistance=_quantile(r, WATCH_RESIST_QUANTILE),
        watch_gap=_quantile(g, WATCH_GAP_QUANTILE),
    )


def classify(tractability: float, resistance: float, willingness_gap: float,
             cal: Calibration | None = None) -> str:
    """Watson's four figure categories.

    'Watch point' is the strategically interesting one: capability is present,
    resistance is what is holding the line, and the willingness gap is wide - so
    an actor with looser accountability norms could cross first.
    """
    cal = cal or Calibration.absolute()
    if tractability < cal.tractability_floor:
        # AI cannot lead this work yet; consequence is not what is holding it.
        return "Human held"
    margin = resistance - frontier_resistance(tractability, cal.frontier_k)
    if (tractability >= cal.watch_tractability
            and resistance >= cal.watch_resistance
            and willingness_gap >= cal.watch_gap):
        return "Watch point"
    if margin < -cal.crossing_band:
        return "Handed off"
    if margin <= cal.crossing_band:
        return "Crossing now"
    return "Human held"


def build(
    scored: Sequence[dict[str, Any]],
    employment: dict[str, float] | None = None,
    reach: dict[str, float] | None = None,
    recurrence: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    employment = employment or {}
    reach = reach or {}
    recurrence = recurrence or {}

    # Calibrate against this corpus, on these axes, before classifying anything.
    axis_pairs = [axes(r, recurrence.get(r["onet_soc_code"])) for r in scored]
    cal = calibrate([t for t, _ in axis_pairs], [r for _, r in axis_pairs],
                    [_f(r, "llm_exposure") - _f(r, "automation_feasibility_today")
                     for r in scored])

    rows = []
    for row, (tract, resist) in zip(scored, axis_pairs):
        code = row["onet_soc_code"]
        deployed = _f(row, "automation_feasibility_today")
        capability = _f(row, "llm_exposure")
        gap = round(capability - deployed, 1)

        now = stage(deployed, resist)
        reachable = stage(capability, resist)
        cls = classify(tract, resist, gap, cal)

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
            "recurrence": recurrence.get(code),
            "frontier_distance": round(
                frontier_resistance(tract, cal.frontier_k) - resist, 1),
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
