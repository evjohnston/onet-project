"""Which tasks are decisions — the rubric, not yet a run.

Watson scores recurring *decisions*. This project scores O*NET *tasks* and uses
them as a proxy, which handoff.py has said plainly since it was written: "the
novel work is to identify which tasks are decisions, and we have not done it".
This is the rubric for doing it. Nothing here has been run; the cost is at the
bottom and the decision to spend is not mine.

WHY A TASK IS NOT A DECISION. O*NET task statements mix at least three things:

    action      "Operate drilling equipment."
    process     "Prepare and maintain records of patient care."
    decision    "Determine whether a patient requires surgical intervention."

Only the third is a point where someone selects among options and owns the
selection. Watson's tractability and resistance axes are defined over that kind
of unit, so applying them to the first two is a category error - the frontier is
currently drawn over a population that is mostly not decisions at all. How much
that distorts the picture is unknown, and is the first thing this measures.

WHAT THIS ALSO CLOSES. handoff.py lists two of Watson's eight properties as
missing. Recurrence was closed by O*NET's FT scale (§4.4). The other is
**feedback speed and clarity**, which is not in O*NET in any form and needs new
scoring - and it is a property of a decision, not of a task, so it belongs
exactly here rather than in a separate pass. Getting it is nearly free once the
model is already reading each task to judge whether it is a decision.

THE FIELDS

  is_decision            bool. Does the task turn on selecting among options
                         that could reasonably have gone otherwise? An action
                         carried out under instruction is not a decision even
                         when it requires great skill.

  decision_kind          one of: diagnosis (classify a state of the world),
                         allocation (distribute limited resources), approval
                         (authorise or refuse), prioritisation (order competing
                         claims), design (choose among constructions),
                         escalation (decide whether to involve someone else),
                         none. Not scored for its own sake - it is the handle
                         for checking whether the measure behaves sensibly by
                         kind, the way the susceptibility index was checked
                         against its own verdicts.

  options_enumerable     0-100. Can the alternatives be listed in advance? A
                         radiologist choosing among named findings scores high;
                         a planner choosing what to propose scores low. This is
                         Watson's "formalizable options", currently proxied by
                         100 - judgment_under_uncertainty, and worth measuring
                         directly to find out how good that proxy was.

  feedback_latency       0-100, where 100 is immediate. How soon does the person
                         choosing learn whether the choice was right? A trader
                         learns in minutes, a structural engineer in decades, a
                         teacher arguably never. THE SECOND MISSING PROPERTY.

  feedback_clarity       0-100. When the answer arrives, is it unambiguous? A
                         diagnosis confirmed by biopsy is clear; a hiring
                         decision is confounded by everything that happened
                         afterwards. Watson pairs this with latency and they
                         come apart: fast and murky is common.

  decision_owner         one of: individual, supervisor, committee, protocol,
                         none. Who owns the choice. Bears on resistance rather
                         than tractability - a decision a protocol already makes
                         has little accountability left to hand over, while one
                         a named person signs has a great deal.

WHAT WILL BE DONE WITH IT, stated before the data exists so the analysis is not
chosen to suit the answer:

  1. Report what share of tasks are decisions, overall and by occupation. If it
     is very high, the proxy was harmless and this was cheap insurance. If it is
     low, every frontier figure in the project is drawn over the wrong
     population and 6.2 says so.
  2. Recompute the handoff axes over decisions only, and report both. Not
     replace: the task-level version is what is published and the two should be
     comparable.
  3. Test the two existing proxies. Is 100 - judgment_under_uncertainty a good
     stand-in for options_enumerable? The answer is a correlation, and it is
     checkable now rather than assumed.
  4. Add feedback to tractability - but only after re-deriving the frontier,
     because that is what recurrence taught: adding a term to a calibrated
     average without recalibrating moved 24 occupations for no reason.

WHAT WOULD MAKE THIS A BAD IDEA, and the honest version of each:

  - A binary gate is exactly the shape of thing this project keeps getting
    wrong: a threshold with unmeasured calibration. Two passes are budgeted
    from the start for that reason, and agreement on the gate is Cohen's kappa,
    not Pearson's r - a correlation on a boolean is not meaningful.
  - "Is this a decision" may simply be underspecified. If two models disagree
    badly, the finding is about the rubric and the right response is to fix the
    definition rather than to publish the scores.
  - 5,612 tasks is 5.8x the subtask catalogue, so this is the most expensive
    thing the project has done by a factor of four.
"""

from __future__ import annotations

RUBRIC_VERSION = "decisions-2026-09-18.1"

DECISION_KINDS = ("diagnosis", "allocation", "approval", "prioritisation",
                  "design", "escalation", "none")
DECISION_OWNERS = ("individual", "supervisor", "committee", "protocol", "none")

# The ordinal fields, which take the same 0-100 treatment as the existing rubric
# so the two are comparable.
SCALES = ("options_enumerable", "feedback_latency", "feedback_clarity")

# Estimated with score.estimate_cost over the 5,612-task catalogue at 40 per
# chunk. Two passes, because a fresh rubric with no calibration is the thing
# this project has most often been wrong about.
COST_ESTIMATE_USD = {
    "claude-opus-5":    {"one_pass": 33.07, "two_passes": 66.14},
    "claude-sonnet-5":  {"one_pass": 13.23, "two_passes": 26.46},
    "claude-haiku-4-5": {"one_pass": 6.61,  "two_passes": 13.22},
}
