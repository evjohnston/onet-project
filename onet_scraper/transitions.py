"""Where could the people in an exposed job actually go?

The reskilling answer people reach for is "move to an adjacent occupation". That
assumes adjacency and exposure are independent. In this corpus they are not:
exposure is clustered in the activity network, so the jobs most adjacent to an
exposed job tend to be exposed too.

A destination has to clear three bars, and all three are arbitrary lines that
the sensitivity sweep is there to test:

  overlap   - enough shared activities that the move is plausible at all
  relief    - meaningfully lower susceptibility, not noise
  direction - the shared activities should include the destination's protected
              work, otherwise the worker carries their exposure with them

That last one is the part a plain similarity ranking misses. Two jobs can share
a great deal and share only the exposed half, in which case the move buys
nothing.
"""

from __future__ import annotations

import collections
import logging
import statistics
from typing import Any, Sequence

log = logging.getLogger(__name__)

MIN_OVERLAP = 0.12      # cosine on shared activities
MIN_RELIEF = 12.0       # susceptibility points
HIGH = 70.0             # an activity counts as exposed at or above this

TRANSITION_COLUMNS = ("onet_soc_code", "title", "susceptibility", "total_employment",
                      "destination_code", "destination", "destination_susceptibility",
                      "relief", "overlap", "shared_activities",
                      "shared_protected", "carries_exposure", "verdict")
STRANDED_COLUMNS = ("onet_soc_code", "title", "susceptibility", "total_employment",
                    "neighbours", "best_relief", "reason")


def _f(row: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        return float(row.get(key))
    except (TypeError, ValueError):
        return default


def build(
    edges: Sequence[dict[str, Any]],
    occupations: Sequence[dict[str, Any]],
    occ_dwa: dict[str, set[str]],
    dwa_susc: dict[str, float],
    employment: dict[str, float],
    min_overlap: float = MIN_OVERLAP,
    min_relief: float = MIN_RELIEF,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    susc = {o["onet_soc_code"]: _f(o, "susceptibility") for o in occupations}
    title = {o["onet_soc_code"]: o.get("title", "") for o in occupations}

    nb: dict[str, list[tuple[float, str]]] = collections.defaultdict(list)
    for e in edges:
        c = _f(e, "cosine")
        nb[e["source"]].append((c, e["target"]))
        nb[e["target"]].append((c, e["source"]))

    moves, stranded = [], []
    for code in sorted(susc):
        here = susc[code]
        options = []
        for overlap, other in nb.get(code, []):
            if overlap < min_overlap or other not in susc:
                continue
            relief = here - susc[other]
            if relief < min_relief:
                continue
            shared = occ_dwa.get(code, set()) & occ_dwa.get(other, set())
            dest_only = occ_dwa.get(other, set()) - occ_dwa.get(code, set())
            # Does the destination's protected work sit in the part they share,
            # or in the part the mover would have to learn from scratch?
            shared_protected = sum(1 for d in shared if dwa_susc.get(d, 100) < HIGH)
            dest_protected = sum(1 for d in dest_only if dwa_susc.get(d, 100) < HIGH)
            carries = sum(1 for d in shared if dwa_susc.get(d, 0) >= HIGH)
            options.append({
                "overlap": overlap, "other": other, "relief": relief,
                "shared": len(shared), "shared_protected": shared_protected,
                "dest_protected": dest_protected, "carries": carries,
            })
        if not options:
            best = max((here - susc[o] for _, o in nb.get(code, []) if o in susc),
                       default=None)
            stranded.append({
                "onet_soc_code": code, "title": title[code],
                "susceptibility": here, "total_employment": employment.get(code),
                "neighbours": len(nb.get(code, [])),
                "best_relief": round(best, 1) if best is not None else None,
                "reason": ("no neighbours above the overlap floor"
                           if not nb.get(code) else
                           "every close neighbour is about as exposed"),
            })
            continue
        options.sort(key=lambda o: -(o["relief"] * o["overlap"]))
        top = options[0]
        verdict = ("Real move" if top["shared_protected"] >= top["carries"]
                   else "Carries its exposure")
        moves.append({
            "onet_soc_code": code, "title": title[code],
            "susceptibility": here, "total_employment": employment.get(code),
            "destination_code": top["other"], "destination": title[top["other"]],
            "destination_susceptibility": susc[top["other"]],
            "relief": round(top["relief"], 1), "overlap": round(top["overlap"], 3),
            "shared_activities": top["shared"],
            "shared_protected": top["shared_protected"],
            "carries_exposure": top["carries"], "verdict": verdict,
        })

    moves.sort(key=lambda r: -r["susceptibility"])
    stranded.sort(key=lambda r: -r["susceptibility"])
    emp_of = lambda rs: sum(r["total_employment"] or 0 for r in rs)
    exposed_stranded = [r for r in stranded if r["susceptibility"] >= 65]
    summary = {
        "occupations": len(susc),
        "with_a_destination": len(moves),
        "stranded": len(stranded),
        "stranded_share": round(len(stranded) / max(len(susc), 1), 3),
        "stranded_workers": round(emp_of(stranded)),
        "exposed_and_stranded": len(exposed_stranded),
        "exposed_and_stranded_workers": round(emp_of(exposed_stranded)),
        "real_moves": sum(1 for m in moves if m["verdict"] == "Real move"),
        "carries_exposure": sum(1 for m in moves if m["verdict"] == "Carries its exposure"),
        "median_relief": round(statistics.median([m["relief"] for m in moves]), 1)
                         if moves else None,
        "thresholds": {"min_overlap": min_overlap, "min_relief": min_relief},
    }
    return moves, stranded, summary


def sweep(edges, occupations, occ_dwa, dwa_susc, employment) -> list[dict[str, Any]]:
    """The thresholds are arbitrary, so report how much the answer moves with them."""
    out = []
    for overlap in (0.08, 0.12, 0.18):
        for relief in (8.0, 12.0, 18.0):
            _, _, s = build(edges, occupations, occ_dwa, dwa_susc, employment,
                            min_overlap=overlap, min_relief=relief)
            out.append({"min_overlap": overlap, "min_relief": relief,
                        "stranded": s["stranded"],
                        "stranded_share": s["stranded_share"],
                        "real_moves": s["real_moves"]})
    return out
