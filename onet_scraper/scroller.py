"""A scroll-driven narrative built from the same tables as the dashboard.

The dashboard is for interrogating the data; this is for being walked through
what it says. Design system (tokens, hand-inked SVG marks, sticky-stage
scrollytelling) follows the sample scroller in sample_scroller/; the scenes,
copy and data are this project's.

Everything is inlined into one HTML file except the Google Fonts link, so it
works from disk with no server.
"""

from __future__ import annotations

import json
import logging
import statistics
from pathlib import Path
from typing import Any, Sequence

log = logging.getLogger(__name__)

ASSETS = Path(__file__).parent / "assets"


def _f(row: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        return float(row.get(key))
    except (TypeError, ValueError):
        return default


def build_payload(
    occ_susc: Sequence[dict[str, Any]],
    tasks: Sequence[dict[str, Any]],
    subtasks: Sequence[dict[str, Any]],
    links: Sequence[dict[str, Any]],
    handoff: Sequence[dict[str, Any]],
    benchmarks: Sequence[dict[str, Any]],
    soc: Sequence[dict[str, Any]],
    employment_report: dict[str, Any],
    pathways: dict[str, Any] | None = None,
    churn: dict[str, Any] | None = None,
    scenarios: dict[str, Any] | None = None,
    emerging: Sequence[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    # --- 01 inversion ------------------------------------------------------
    # Plot the ACTUAL values on each side, each scaled to its own range, rather
    # than percentile ranks. Within this STEM subset almost everything scores low
    # on Frey & Osborne (median 0.033), so ranks would make an unremarkable
    # position look extreme - 85 of the 150 score below Mathematicians' 0.047.
    pairs = [b for b in benchmarks
             if b.get("frey_osborne") not in (None, "")
             and b.get("our_susceptibility") not in (None, "")]
    fo_vals = [_f(b, "frey_osborne") for b in pairs]
    us_vals = [_f(b, "our_susceptibility") for b in pairs]
    fo_lo, fo_hi = min(fo_vals), max(fo_vals)
    us_lo, us_hi = min(us_vals), max(us_vals)
    # y runs 0 at the top to 1 at the bottom, so invert: high score sits high.
    # Frey & Osborne on a square-root scale - within STEM the scores bunch hard
    # at the low end (median 0.033 against a 0.96 maximum) and a linear axis
    # crushes five sixths of the field onto the baseline.
    import math
    norm = lambda v, lo, hi: round(1 - (v - lo) / ((hi - lo) or 1), 4)
    nsqrt = lambda v, lo, hi: round(
        1 - (math.sqrt(max(v, 0)) - math.sqrt(lo)) /
            ((math.sqrt(hi) - math.sqrt(lo)) or 1), 4)

    def entry(b, highlight=False):
        title = b["title"]
        return {"t": (title[:27] + "\u2026") if len(title) > 28 else title,
                "fo": nsqrt(_f(b, "frey_osborne"), fo_lo, fo_hi),
                "ours": norm(_f(b, "our_susceptibility"), us_lo, us_hi),
                "hl": highlight}

    risers = sorted(pairs, key=lambda b: (_f(b, "our_susceptibility") / 100)
                    - _f(b, "frey_osborne"))[::-1][:3]
    fallers = sorted(pairs, key=lambda b: -_f(b, "frey_osborne"))[:3]
    named = {b["onet_soc_code"] for b in risers + fallers}
    inversion = []
    for b in pairs:
        hl = b["title"].startswith("Mathematicians")
        if hl or b["onet_soc_code"] in named:
            inversion.append(entry(b, hl))
    inversion += [{"t": "", "fo": nsqrt(_f(b, "frey_osborne"), fo_lo, fo_hi),
                   "ours": norm(_f(b, "our_susceptibility"), us_lo, us_hi), "hl": False}
                  for b in pairs if b["onet_soc_code"] not in named
                  and not b["title"].startswith("Mathematicians")][:46]

    # --- 02b composition: every task of every job, for the explorer --------
    tasks_by_occ: dict[str, list[dict[str, Any]]] = {}
    for t in tasks:
        tasks_by_occ.setdefault(t["onet_soc_code"], []).append({
            "t": t["task"][:150],
            "s": round(_f(t, "susceptibility")),
            "e": round(_f(t, "exposure")),
            "a": round(_f(t, "anchoring")),
            "i": round(_f(t, "importance")) if t.get("importance") else None,
        })
    for v in tasks_by_occ.values():
        v.sort(key=lambda r: -r["s"])
    comp = []
    for o in occ_susc:
        code = o["onet_soc_code"]
        rows = tasks_by_occ.get(code, [])
        if not rows:
            continue
        comp.append({
            "c": code, "t": o["title"], "n": len(rows),
            "ty": (o.get("stem_occupation_types") or "").split(";")[0].strip(),
            "mean": round(_f(o, "susceptibility"), 1),
            "hi": round(sum(1 for r in rows if r["s"] >= 70) / len(rows), 3),
            "spread": round(statistics.stdev([r["s"] for r in rows]), 1)
                      if len(rows) > 1 else 0.0,
            "scores": [r["s"] for r in rows],
        })
    comp.sort(key=lambda r: -r["hi"])

    # --- 03b leverage: how far each subtask reaches across the field -------
    reach: dict[str, set[str]] = {}
    task_hits: dict[str, int] = {}
    for link in links:
        dwa = link.get("dwa_id")
        if not dwa:
            continue
        reach.setdefault(dwa, set()).add(link["onet_soc_code"])
        task_hits[dwa] = task_hits.get(dwa, 0) + 1
    sub_by_id = {r["dwa_id"]: r for r in subtasks}
    lev = []
    for dwa, codes in reach.items():
        row = sub_by_id.get(dwa)
        if not row:
            continue
        title = row["dwa_title"]
        lev.append({"d": dwa,
                    "t": (title[:54] + "\u2026") if len(title) > 55 else title,
                    "n": len(codes), "k": task_hits[dwa],
                    "s": round(_f(row, "susceptibility"))})
    lev.sort(key=lambda r: -r["n"])
    by_reach = sorted((r["n"] for r in lev), reverse=True)
    total_links = sum(by_reach) or 1
    cum = []
    run = 0
    for i, v in enumerate(by_reach, 1):
        run += v
        if i in (10, 25, 50, 100, 200, 400, len(by_reach)):
            cum.append({"k": i, "share": round(run / total_links, 4)})

    # occupation -> its subtask ids, for the side-by-side comparison
    occ_dwa: dict[str, list[str]] = {}
    for link in links:
        if link.get("dwa_id"):
            bucket = occ_dwa.setdefault(link["onet_soc_code"], [])
            if link["dwa_id"] not in bucket:
                bucket.append(link["dwa_id"])
    dwa_title = {r["d"]: r["t"] for r in lev}
    dwa_susc = {r["d"]: r["s"] for r in lev}

    # --- 03 axes ------------------------------------------------------------
    axes = [{"e": _f(o, "exposure"), "a": _f(o, "anchoring"), "s": _f(o, "susceptibility")}
            for o in occ_susc]
    quad: dict[str, int] = {}
    for o in occ_susc:
        quad[o.get("quadrant", "")] = quad.get(o.get("quadrant", ""), 0) + 1

    # --- 04 frontier --------------------------------------------------------
    frontier = [{"T": _f(h, "tractability"), "R": _f(h, "resistance"),
                 "cls": h.get("classification", "")} for h in handoff]
    watch = [{"t": h["title"][:30], "T": _f(h, "tractability"), "R": _f(h, "resistance")}
             for h in handoff if h.get("classification") == "Watch point"][:6]

    # --- 05 ladder ----------------------------------------------------------
    labels = ["Human only", "AI informed", "AI recommended",
              "AI executed, human veto", "AI led, human audit", "AI led, unreviewed"]
    now = [0] * 6
    reach = [0] * 6
    for h in handoff:
        now[int(_f(h, "stage_now"))] += 1
        reach[int(_f(h, "stage_reachable"))] += 1

    # --- 06 people ----------------------------------------------------------
    head = employment_report.get("headline", {})
    by_q = head.get("by_quadrant", {})
    order = ["Displaceable", "Human-anchored", "Contested", "Insulated"]
    quadrants = [{"name": q, "share": by_q[q]["share_of_employment"],
                  "employment": by_q[q]["employment"]}
                 for q in order if q in by_q]
    top = sorted((s for s in soc if s.get("total_employment")),
                 key=lambda s: -_f(s, "total_employment"))[:5]
    people = {
        "total_m": round(head.get("total_employment", 0) / 1e6, 1),
        "quadrants": quadrants,
        "top": [{"t": s["soc_title"][:30], "emp": _f(s, "total_employment"),
                 "s": _f(s, "susceptibility")} for s in top],
        "shift": f"{head.get('weighting_shifts_result_by', 0):+.1f}",
    }

    # --- 07 validation ------------------------------------------------------
    vpairs = [(_f(b, "our_susceptibility"), _f(b, "human_gamma"))
              for b in benchmarks if b.get("human_gamma") not in (None, "")]
    validation = [{"x": round(x, 1), "y": round(y, 3)} for x, y in vpairs]
    mx = statistics.fmean(p[0] for p in vpairs) if vpairs else 0
    my = statistics.fmean(p[1] for p in vpairs) if vpairs else 0
    num = sum((p[0] - mx) * (p[1] - my) for p in vpairs)
    den = sum((p[0] - mx) ** 2 for p in vpairs) or 1
    slope = num / den

    # Fate is derived client-side from exposure and anchoring, which the task
    # payload already carries, so the thresholds travel instead of a second copy
    # of every task.
    scen = scenarios or {}
    new_by_occ: dict[str, list[str]] = {}
    for e in (emerging or []):
        new_by_occ.setdefault(e["onet_soc_code"], []).append(e["task"][:90])
    churn = churn or {}
    pathways = pathways or {}
    wages = pathways.get("wages", {})
    trans = pathways.get("transitions", {})

    return {
        "scen": {
            "thresholds": {k: v["thresholds"] for k, v in
                           scen.get("scenarios", {}).items()},
            "meta": {k: {"label": v["label"], "blurb": v["blurb"],
                         "automated": v["automated"], "augmented": v["augmented"],
                         "unchanged": v["unchanged"],
                         "reshaped": v["occupations_reshaped"]}
                     for k, v in scen.get("scenarios", {}).items()},
            "flows": scen.get("flows", {}),
            "order": ["modest", "substantial", "extreme"],
            "gridDefault": "29-1161.00",
        },
        "newTasks": new_by_occ,
        "churn": churn,
        "wage": {
            "deciles": pathways.get("deciles", []),
            "rExposure": wages.get("wage_vs_exposure"),
            "rAnchoring": wages.get("wage_vs_anchoring"),
            "rSusc": wages.get("wage_vs_susceptibility"),
            "protection": wages.get("by_protection", {}),
        },
        "trans": {
            "moves": pathways.get("moveSample", []),
            "stranded": trans.get("stranded"),
            "strandedShare": trans.get("stranded_share"),
            "withDest": trans.get("with_a_destination"),
            "exposedStranded": trans.get("exposed_and_stranded"),
            "exposedStrandedWorkers": trans.get("exposed_and_stranded_workers"),
            "realMoves": trans.get("real_moves"),
            "carries": trans.get("carries_exposure"),
            "sensitivity": trans.get("sensitivity", []),
        },
        "lev": lev,
        "cum": cum,
        "levStats": {
            "unique": sum(1 for r in lev if r["n"] == 1),
            "total": len(lev),
            "top100": next((c["share"] for c in cum if c["k"] == 100), 0),
            "widest": lev[0] if lev else None,
        },
        "occDwa": occ_dwa,
        "dwaTitle": dwa_title,
        "dwaSusc": dwa_susc,
        "comp": comp,
        "tasks": tasks_by_occ,
        "exemplars": {
            "pairA": "15-1242.00", "pairB": "15-1243.00",
            "all": next((c["c"] for c in comp if c["hi"] >= 0.99), comp[0]["c"]),
            "none": next((c["c"] for c in reversed(comp) if c["n"] >= 12), comp[-1]["c"]),
            "split": max(comp, key=lambda c: c["spread"])["c"],
        },
        "inversion": inversion,
        "axes": axes,
        "splits": {"x": 65.3, "y": 43.5},
        "quad": {"disp": quad.get("Displaceable", 0), "anch": quad.get("Human-anchored", 0)},
        "frontier": frontier,
        "watch": watch,
        "counts": {"watch": sum(1 for h in handoff
                                if h.get("classification") == "Watch point")},
        "ladder": {"labels": labels, "now": now, "reach": reach},
        "people": people,
        "validation": validation,
        "fit": {"a": round(my - slope * mx, 4), "b": round(slope, 5)},
    }


# --------------------------------------------------------------------------- #
# Markup                                                                        #
# --------------------------------------------------------------------------- #
def _beat(tag: str, head: str, body: str, eg: str = "") -> str:
    eg_html = f'<p class="egs">{eg}</p>' if eg else ""
    return (f'<article class="beat" data-beat><span class="beat-tag"><i></i>{tag}</span>'
            f"<h3>{head}</h3><p>{body}</p>{eg_html}</article>")


def _scene(sid: str, number: str, title: str, standfirst: str, fig: str,
           aria: str, readout_k: str, readout_v: str, note: str,
           beats: list[str], tint: bool = False, controls: str = "") -> str:
    cls = "scene on-tint" if tint else "scene"
    return f"""
  <section class="{cls}" id="{sid}" data-scene="{sid}">
    <div class="scene-head">
      <p class="chapter-number">{number}</p>
      <div><h2>{title}</h2><p class="standfirst">{standfirst}</p>{controls}</div>
    </div>
    <div class="scrolly">
      <div class="stage"><div class="stage-frame">
        <div class="stage-hud"><span class="hud-name">{fig}</span>
          <span class="hud-count"><b data-hud-i>01</b> / {len(beats):02d}</span></div>
        <svg class="plot" viewBox="0 0 1600 900" preserveAspectRatio="xMidYMid meet"
             role="img" aria-label="{aria}"></svg>
        <div class="stage-readout" data-readout><span data-readout-k>{readout_k}</span>
          <b data-readout-v>{readout_v}</b></div>
        <div class="stage-note">{note}</div>
      </div></div>
      <div class="beats">{''.join(beats)}</div>
    </div>
  </section>"""


TG_CONTROLS = '<div class="scenbar" id="tg-scen"></div><p class="scenblurb" data-scenblurb></p><label class="ctl">Occupation <select id="tg-occ"></select></label>'
FL_CONTROLS = '<div class="scenbar" id="fl-scen"></div><p class="scenblurb" data-scenblurb></p>'

SCENES: list[dict[str, Any]] = [
    dict(sid="inversion", number="01 / The inversion", rail="The inversion",
         title="The jobs most at risk in 2013 are not the jobs most at risk now.",
         standfirst="Frey and Osborne scored every US occupation for its probability of "
                    "computerisation. Score the same occupations for exposure to large "
                    "language models and the ordering does not weaken \u2014 it comes "
                    "apart entirely.",
         fig="Fig. 01 \u2014 Two measures, same occupations",
         aria="Occupations plotted by their 2013 computerisation probability on the left "
              "and their LLM susceptibility on the right; the connecting lines cross "
              "heavily, showing no relationship between the two.",
         rk="Mathematicians, 2013", rv="4.7% chance",
         note="Left axis square-root scaled; right axis linear. 150 occupations.",
         beats=[
             ("01 / 2013", "Automation meant routine and manual",
              "Frey and Osborne built their measure on the bottlenecks of that era: "
              "perception and manipulation, creative intelligence, social intelligence. "
              "Repetitive physical work scored high. Analytical work scored low \u2014 "
              "mathematicians landed in their lowest-risk band.",
              "Mathematicians \u2014 <b>4.7% probability of computerisation</b>"),
             ("02 / 2026", "Language models run the other way",
              "Rate the same occupations for what a current model could do and the "
              "analytical professions move to the top. Mathematicians ranks third of 268. "
              "Nothing about the work changed; the capability arriving to meet it did.",
              "Mathematicians \u2014 <b>3rd most exposed of 268</b>"),
             ("03 / The disagreement", "And the old risk ordering does not survive",
              "The occupations Frey and Osborne rated most at risk \u2014 surveying "
              "technicians at 96 per cent, pharmacy technicians at 92 \u2014 sit in the "
              "middle of the LLM ranking. Across all 150 the correlation is 0.006. A "
              "measure written before 2020 tells you close to nothing about exposure now.",
              "Pearson <b>r = 0.006</b> \u00b7 Spearman 0.119"),
         ]),
    dict(sid="vocabulary", number="02 / The vocabulary", rail="The vocabulary",
         title="Five thousand tasks stand on a thousand shared activities.",
         standfirst="O*NET decomposes each occupation into tasks, and each task into "
                    "standardised detailed work activities. The activities repeat across "
                    "jobs, which is what makes the corpus tractable to score at all.",
         fig="Fig. 02 — Occupations, tasks, subtasks",
         aria="Three columns of marks: 287 occupations, 5,717 tasks, and 963 distinct "
              "subtasks, with the scoring flowing back out from the smallest column.",
         rk="Occupations", rv="287",
         note="Counts are exact. Marks are illustrative.",
         beats=[
             ("01 / The corpus", "287 STEM occupations, 5,717 tasks",
              "Every occupation O*NET flags as STEM, scraped with its full task list — "
              "each task carrying an importance rating and a Core, Supplemental or New "
              "label from the incumbent survey.",
              "<b>5,717</b> task statements"),
             ("02 / The shared layer", "Only 963 distinct activities underneath",
              "Those tasks map onto a much smaller vocabulary of detailed work activities. "
              "“Analyse data to inform operational decisions” is one activity "
              "appearing in dozens of different jobs.",
              "<b>963</b> distinct subtasks · 7,215 links"),
             ("03 / Why it matters", "Score the vocabulary, not the tasks",
              "Rating 963 activities instead of 5,717 tasks is six times less work, and "
              "it removes an artefact: the same activity cannot be scored one way in "
              "nursing and another in engineering. Consistency comes from the structure "
              "rather than from discipline.",
              "Every task inherits the score of its activities"),
         ]),
    dict(sid="composition", number="03 / Inside a job", rail="Inside a job",
         title="A job is a bundle of tasks, and the bundles differ.",
         standfirst="Asking whether an occupation is exposed hides the thing that "
                    "matters. Almost every job has some tasks a model could take and "
                    "some it could not. What separates one job from another is the "
                    "mix.",
         fig="Fig. 03 \u2014 Every task, three jobs",
         aria="Three occupations shown as columns of horizontal bars, one bar per task, "
              "sorted by susceptibility, followed by a histogram of the whole field.",
         rk="A whole job", rv="100% of tasks",
         note="One bar per task. Length is susceptibility.",
         beats=[
             ("01 / All of it", "Some jobs are exposed all the way down",
              "Business intelligence analysts have seventeen tasks in O*NET. Every one of "
              "them scores above the high-exposure threshold. There is no part of the "
              "documented job that sits outside it \u2014 which is rare.",
              "<b>100%</b> of 17 tasks \u00b7 spread ±2.4"),
             ("02 / Part of it", "Most jobs split, and the split is the story",
              "Naturopathic physicians have the widest internal spread in the corpus. "
              "Their record-keeping, literature review and treatment-planning tasks sit "
              "near the top of the exposure range; examining a patient and administering "
              "care sit near the bottom. The job does not vanish. It loses one half and "
              "keeps the other.",
              "Widest internal spread \u00b7 <b>30% of 20 tasks</b>"),
             ("03 / Almost none of it", "And some barely move",
              "Prosthodontists, chemists and medical laboratory technicians have no task "
              "above the threshold at all. Not because the work is simple \u2014 it is "
              "among the most skilled in the corpus \u2014 but because the documented "
              "tasks are chairside, bench and instrument work.",
              "<b>0%</b> of tasks above threshold"),
             ("04 / The field", "Most jobs lose some tasks, not all",
              "Across 268 scored occupations, 121 have fewer than a fifth of their tasks "
              "highly exposed. Eleven have more than four fifths. The common case is "
              "partial \u2014 a job reshaped around what is left, not one that disappears.",
              "<b>121</b> under 20% \u00b7 <b>11</b> over 80%"),
         ]),
    dict(sid="leverage", number="04 / The shared spine", rail="The shared spine",
         title="A few activities run through almost every job.",
         standfirst="The subtask vocabulary is not evenly used. Most activities belong to "
                    "one occupation. A small number appear everywhere \u2014 and those "
                    "are disproportionately the exposed ones.",
         fig="Fig. 04 \u2014 Reach against susceptibility",
         aria="Each subtask plotted by how many occupations use it against its "
              "susceptibility, with a concentration curve beneath.",
         rk="Used by one job only", rv="261 of 963",
         note="Reach axis square-root scaled. 963 distinct activities.",
         beats=[
             ("01 / The tail", "Most activities belong to a single job",
              "Two hundred and sixty-one of the 963 activities \u2014 more than a "
              "quarter \u2014 appear in exactly one occupation. These are the "
              "specialised core of a profession, and automating one of them changes "
              "that profession and nothing else.",
              "<b>261</b> of 963 used by one job"),
             ("02 / The spine", "A handful appear almost everywhere",
              "\u201cRecord patient medical histories\u201d appears in 56 different "
              "occupations. \u201cPrepare scientific or technical reports\u201d in 40. "
              "\u201cTrain medical providers\u201d in 49. These are the connective "
              "tissue of STEM work rather than anyone\u2019s speciality.",
              "Widest reach \u2014 <b>56 occupations</b>"),
             ("03 / The overlap", "And the shared ones are the exposed ones",
              "The activities with the widest reach are documentation, reporting, "
              "literature review and grant writing \u2014 exactly the work that scores "
              "highest. \u201cResearch topics in area of expertise\u201d reaches 27 "
              "jobs at a susceptibility of 84.",
              "Reach and exposure point the same way"),
             ("04 / The concentration", "So a hundred activities carry most of the field",
              "The 100 most widely used activities account for 38 per cent of every "
              "job-to-activity link in the corpus. Automating that set would touch most "
              "of STEM work at once \u2014 which is where the leverage sits, and where "
              "a single scoring error propagates furthest.",
              "<b>100</b> activities \u00b7 <b>38%</b> of all links"),
         ]),
    dict(sid="axes", number="03 / Two questions", rail="Two questions", tint=True,
         title="Whether a machine can do the work is not whether it will.",
         standfirst="The seven rated dimensions collapse into two that behave "
                    "independently. Treating them as one number is the most common way "
                    "this analysis goes wrong.",
         fig="Fig. 03 — Exposure against anchoring",
         aria="Occupations plotted by exposure against anchoring, splitting into four "
              "quadrants at the observed medians.",
         rk="Exposure", rv="can a machine do it",
         note="Positions are relative to other STEM occupations.",
         beats=[
             ("01 / Capability", "Exposure asks what a machine could do",
              "How much of the cognitive core of this work could a current model perform, "
              "given the right inputs and tools? Document handling, retrieval, drafting "
              "and analysis score high. Work requiring hands in the world scores low.",
              "Highest — <b>proofread documents</b> · exposure 95"),
             ("02 / Permission", "Anchoring asks whether a human must own it",
              "Accountability, the cost and irreversibility of error, judgment under "
              "uncertainty, and whether the relationship is the substance of the work. "
              "A surgeon and a data analyst can both be highly capable targets and sit at "
              "opposite ends of this axis.",
              "Highest — <b>operate on patients</b> · anchoring 80+"),
             ("03 / Independence", "The two barely correlate",
              "Drafting a legal opinion is almost entirely language work and still "
              "requires a named human to answer for it. Ninety-two of the 963 activities "
              "score high on both. A single “automation risk” number cannot "
              "represent them.",
              "Exposure vs anchoring — <b>r = −0.03</b>"),
             ("04 / The split", "The field divides almost in half",
              "Ninety-eight STEM occupations sit in the displaceable quadrant and a "
              "hundred in the human-anchored one. Which half a job lands in is decided "
              "more by accountability than by capability.",
              "<b>98</b> displaceable · <b>100</b> human-anchored"),
         ]),
    dict(sid="frontier", number="04 / The frontier", rail="The frontier",
         title="Capability is not what is holding most of this work.",
         standfirst="Watson's handoff framework scores work on tractability — whether "
                    "AI can lead it — and resistance — whether it will be "
                    "permitted to. The interesting cases are where those two disagree.",
         fig="Fig. 04 — Tractability against resistance",
         aria="Occupations plotted by tractability against resistance with a frontier "
              "curve; watch points are highlighted above it.",
         rk="Tractability", rv="can AI lead it",
         note="Framework: Watson 2026. Curve calibrated to this corpus.",
         beats=[
             ("01 / Two axes", "Can it, and will it be allowed to",
              "Recurrence, feedback, observability and structure decide whether AI can "
              "lead a decision. Stakes and legitimacy decide whether it is permitted to. "
              "The first four are engineering questions; the last two are not.",
              "Six of Watson's eight properties are covered here"),
             ("02 / The line", "The frontier is where work crosses",
              "Below the curve, the handoff has happened. Above it, a human still leads. "
              "Highly tractable work crosses even at some consequence; work that is not "
              "tractable stays human-led however low the stakes.",
              "<b>36</b> handed off · <b>98</b> crossing now"),
             ("03 / Watch points", "Capability present, accountability holding",
              "Twenty-nine occupations sit above the frontier with a wide gap between "
              "what AI could do and what is deployed. Watson reads that gap as "
              "willingness to permit the handoff — and an actor with looser norms "
              "can close it first.",
              "<b>29</b> watch points"),
             ("04 / Who they are", "Mostly clinical judgment and risk",
              "Genetic counsellors, actuaries, preventive medicine physicians, "
              "epidemiologists. In each the analytical core is well within reach and a "
              "named human is still required to sign.",
              "Mean willingness gap among them — <b>+45</b>"),
         ]),
    dict(sid="ladder", number="05 / The ladder", rail="The ladder", tint=True,
         title="Eight occupations have crossed. A hundred and forty could.",
         standfirst="Watson scores cognitive leadership on six stages, from human-only to "
                    "AI-led and unreviewed. A handoff is a crossing between stages. "
                    "Scoring what is deployed and what is reachable separately shows how "
                    "much travel is pending.",
         fig="Fig. 05 — Stage today, stage reachable",
         aria="Six stages of cognitive leadership, each showing how many occupations sit "
              "there today against how many current capability could support.",
         rk="Six stages", rv="of cognitive leadership",
         note="Stage is the lower of the capability and permission ceilings.",
         beats=[
             ("01 / The scale", "From informed to unreviewed",
              "Human only. AI informed. AI recommended. AI executed with a human veto. "
              "AI led with a human audit. AI led, unreviewed. Each step moves authority, "
              "not just capability.",
              "Six stages · a handoff is a crossing"),
             ("02 / Today", "Most STEM work sits at recommendation",
              "On what is actually deployed, 158 occupations sit at “AI "
              "recommended” and 101 at “AI informed”. Eight have reached "
              "“AI executed with a human veto”.",
              "<b>8</b> occupations at AI-executed today"),
             ("03 / Reachable", "Capability has already moved past that",
              "Rate the same occupations on what a current model could do rather than "
              "what is deployed, and 140 reach “AI executed with a human veto”. "
              "The distance between those two numbers is pending handoff.",
              "<b>140</b> could be there now"),
             ("04 / The quiet one", "The second crossing has no event",
              "Watson expects two crossings to carry most of the weight: proposing action "
              "to taking it, and human veto to after-the-fact audit. The second happens "
              "by erosion — review thinning toward ceremony, with nothing to observe.",
              "<b>120</b> occupations sit at one of the two"),
         ]),
    dict(sid="people", number="06 / The people", rail="The people",
         title="Twenty-one million workers, pulling in opposite directions.",
         standfirst="Occupation counts weight a nurse the same as an actuary. Joining BLS "
                    "employment asks a different question: not which jobs are exposed, "
                    "but how many people are in them.",
         fig="Fig. 06 — Workers by handoff quadrant",
         aria="A bar divided by share of employment in each quadrant, and the five "
              "largest STEM occupations by headcount.",
         rk="Workers covered", rv="21.5 million",
         note="BLS OEWS national file. Employment counted once per SOC code.",
         beats=[
             ("01 / The count", "21.5 million across 195 occupation codes",
              "O*NET reports at a finer grain than BLS, so several O*NET occupations roll "
              "into one SOC code. Attaching employment to each would count 3.4 million "
              "registered nurses five times over. Susceptibility is averaged up first.",
              "<b>195</b> SOC codes · 37 of them collapsed"),
             ("02 / The split", "Forty-three per cent in the displaceable half",
              "Weighted by headcount, 9.2 million STEM workers sit in the displaceable "
              "quadrant and 8.9 million in the human-anchored one — a wage bill of "
              "1.1 trillion dollars on the exposed side.",
              "<b>43%</b> displaceable · <b>41%</b> human-anchored"),
             ("03 / The cancellation", "The two largest occupations disagree",
              "Registered nurses, 3.4 million people, sit at the human-anchored end. "
              "Software developers, 1.7 million, sit near the top of the exposed end. "
              "They very nearly cancel.",
              "Nurses susceptibility 50 · developers 69"),
             ("04 / The null result", "Weighting barely moves the answer",
              "Employment weighting shifts mean susceptibility by half a point. Headcount "
              "is not concentrated at either end, which means the unweighted ranking was "
              "not misleading. That is worth reporting precisely because it could have "
              "gone the other way.",
              "Mean susceptibility <b>58.2 → 58.7</b>"),
         ]),
    dict(sid="wages", number="08 / The premium", rail="The premium", tint=True,
         title="What protects well-paid work is not that AI cannot do it.",
         standfirst="The Frey and Osborne era found automation risk falling as wages "
                    "rose. Run the same test against LLM exposure and the two "
                    "components of susceptibility pull in opposite directions.",
         fig="Fig. 08 \u2014 Exposure and anchoring by wage decile",
         aria="Exposure, anchoring and net susceptibility plotted across ten "
              "employment-weighted wage deciles.",
         rk="Wage vs exposure", rv="r = 0.03",
         note="Each decile holds 2.15M workers; r values are across occupations.",
         beats=[
             ("01 / Capability", "Exposure does not care what a job pays",
              "Across the 195 occupation codes with wage data, the correlation between "
              "pay and exposure is 0.03. Whatever decides how much of a job a model "
              "could do, it is not the salary.",
              "Wage vs exposure \u2014 <b>r = 0.03</b>"),
             ("02 / Permission", "Anchoring is what tracks pay instead",
              "Across those same occupations, accountability and the cost of error "
              "correlate with the wage at 0.40. Better-paid STEM work is not harder for "
              "a model to attempt \u2014 it is work someone has to answer for. The line "
              "on screen is employment-weighted and does not climb smoothly: it dips "
              "through the software and engineering-management deciles and rises again "
              "at the clinical top.",
              "Wage vs anchoring \u2014 <b>r = 0.40</b> across occupations"),
             ("03 / The peak", "Exposure peaks just below the top of the scale",
              "Susceptibility climbs from 52 in the bottom wage decile to 69 in the "
              "seventh \u2014 and then falls back to 58 at the very top. The "
              "highest-paid decile is physicians, dentists and specialists, where "
              "anchoring climbs again. The most exposed workers are not the "
              "best-paid; they are the well-paid tier just beneath them.",
              "Peak at the <b>7th decile</b> \u00b7 69, falling to 58 at the top"),
             ("04 / The share", "And accountability protects a minority",
              "Sorting every occupation by what is actually holding it: 42 per cent of "
              "STEM workers are in work a model largely cannot do, and only 9 per cent "
              "in work it could do but is not permitted to. The accountability premium "
              "is real, and it is narrow.",
              "<b>9%</b> of workers protected by accountability"),
         ]),
    dict(sid="pathways", number="09 / Nowhere adjacent", rail="Nowhere adjacent",
         title="The jobs next door are exposed too.",
         standfirst="The standard answer to displacement is to move into an adjacent "
                    "occupation. That assumes adjacency and exposure are independent. "
                    "In the activity network they are not.",
         fig="Fig. 09 \u2014 Where an exposed job could move",
         aria="Arrows from exposed occupations to the nearest less-exposed occupation "
              "that shares enough activities, above a count of those with no such "
              "destination.",
         rk="Moves that exist", rv="107 of 268",
         note="Destination must share activities and be meaningfully less exposed.",
         beats=[
             ("01 / The test", "A destination has to clear three bars",
              "Enough shared activities that the move is plausible. Meaningfully lower "
              "susceptibility, not noise. And the shared activities have to include the "
              "destination\u2019s protected work \u2014 otherwise the worker carries "
              "their exposure with them.",
              "Overlap \u00b7 relief \u00b7 direction"),
             ("02 / The moves", "Where a move exists, it is usually genuine",
              "A hundred and seven occupations have a destination that clears all three. "
              "Ninety-eight of those are real moves into better-protected work; nine "
              "share only the exposed half, and would carry the problem along.",
              "<b>98</b> real \u00b7 <b>9</b> carry the exposure"),
             ("03 / The stranded", "But most occupations have nowhere to go",
              "A hundred and sixty-one of 268 have no close neighbour that is "
              "meaningfully safer. Fifty-nine of those are themselves highly exposed, "
              "covering 11.5 million workers. Database administrators, data scientists, "
              "programmers and web developers sit in a neighbourhood where everything "
              "is exposed.",
              "<b>11.5M</b> workers exposed and stranded"),
             ("04 / How firm", "The direction holds; the number does not",
              "Sweeping the thresholds moves the stranded count between 105 and 240 of "
              "268. How much relief you demand changes the answer a great deal, and how "
              "much overlap you require barely changes it at all. The finding is that "
              "exposure is clustered \u2014 not that the number is 161.",
              "Sweep \u2014 <b>105 to 240</b> stranded"),
         ]),
    dict(sid="churn", number="10 / Has it moved yet", rail="Has it moved yet",
         title="The work has already started changing \u2014 where anyone looked.",
         standfirst="Every other measure here rests on a model\u2019s judgment about "
                    "what could happen. This one does not. O*NET archives every "
                    "release, so the task statements attached to a job can be diffed "
                    "across eleven years and the turnover counted directly.",
         fig="Fig. 10 \u2014 Task turnover, 2015 to 2026",
         aria="Task turnover per release, then turnover split by whether O*NET "
              "re-surveyed the occupation, then by exposure.",
         rk="Turnover since 2015", rv="5.2% overall",
         note="175 occupations tracked; 93 skipped on the 2019 SOC revision.",
         beats=[
             ("01 / The raw number", "Almost nothing changed",
              "Across 175 STEM occupations present in both the 2015 and 2026 releases, "
              "3,553 task statements became 3,666. Two hundred and forty-three were "
              "added, 130 retired, and 3,423 survived untouched. Seventy-four "
              "occupations have identical task lists to eleven years ago.",
              "<b>5.2%</b> turnover \u00b7 <b>6.6%</b> of today\u2019s tasks are new"),
             ("02 / And no inflection", "The turnover did not accelerate after 2022",
              "If language models had already reshaped these jobs, the diff would show "
              "it. The largest single step in the series is 2019 to 2021 \u2014 before "
              "ChatGPT. Every step since 2022 is smaller than the ones before it.",
              "Largest step <b>2019\u20132021</b>, at 2.5%"),
             ("03 / The confound", "But O*NET only re-surveys on a rolling cycle",
              "An occupation whose tasks did not change may simply not have been looked "
              "at. Splitting on the date O*NET last reviewed each one: the 153 "
              "re-surveyed since 2022 turned over 8.1 per cent, the 115 that were not "
              "turned over 2.4. The headline figure is diluted by occupations nobody "
              "checked, and no amount of care with the diff fixes that.",
              "<b>8.1%</b> where checked \u00b7 <b>2.4%</b> where not"),
             ("04 / The signal", "And exposed jobs moved roughly three times faster",
              "Among occupations O*NET did re-survey, the highly exposed ones turned "
              "over 13.2 per cent of their tasks against 4.6 for the least exposed. "
              "Small sample \u2014 sixteen occupations \u2014 and O*NET does not pick "
              "what to re-survey at random. But it points the same way the scores do, "
              "from data that knows nothing about them.",
              "<b>13.2%</b> exposed \u00b7 <b>4.6%</b> not \u00b7 n=16"),
         ]),
    dict(sid="taskgrid", number="11 / One job, task by task", rail="Task by task",
         title="What happens to each task, and what is left.",
         standfirst="The same bundle, coloured by what becomes of each task under a "
                    "chosen set of assumptions. Nothing here is a forecast \u2014 the "
                    "scenario sets how much accountability an actor is willing to hand "
                    "over, and everything else follows from the scores already measured.",
         fig="Fig. 11 \u2014 A single job\u2019s tasks by fate",
         aria="One occupation's tasks drawn as a grid of squares, coloured by whether "
              "each is unchanged, augmented, automated, or newly arrived.",
         rk="A bundle of tasks", rv="21 tasks",
         note="New tasks are observed from O*NET, not modelled.",
         controls=TG_CONTROLS,
         beats=[
             ("01 / The bundle", "Start with everything the job contains",
              "O*NET lists each occupation as a set of task statements. Laid out flat "
              "they are just a bundle \u2014 no ordering, no weighting, and nothing yet "
              "said about which of them a machine could take.",
              "Every square is one documented task"),
             ("02 / What stays", "Some of it a model cannot touch",
              "Work needing hands on a patient, presence in a room, or a judgement "
              "someone has to own. These stay grey at every setting \u2014 no scenario "
              "moves them, because the constraint is not capability.",
              "Grey at every scenario"),
             ("03 / What gets help", "Some gets faster rather than taken",
              "A model drafts, summarises, plans or checks, and a person keeps the work. "
              "This is the largest category in the middle scenario \u2014 the least "
              "dramatic result in the dataset, and the most plausible.",
              "The largest group under <b>Substantial</b>"),
             ("04 / What gets taken", "And some of it goes",
              "High exposure, little accountability attached: retrieval, formatting, "
              "routine documentation, scheduling. Move the scenario and watch this "
              "category eat into the middle one. That movement is the whole argument.",
              "21% \u2192 45% \u2192 69% of all tasks"),
             ("05 / What arrives", "New work appears too",
              "Not modelled \u2014 observed. O*NET flags newly emerging task statements, "
              "121 of them across these occupations. For a nurse midwife: evaluating "
              "patients\u2019 mental health, screening for gynaecologic conditions.",
              "<b>121</b> new tasks recorded in O*NET"),
             ("06 / What is left", "The job is not smaller, it is different",
              "What remains gets more room. The tasks a model touched carry more volume "
              "per hour of human attention; the ones it cannot touch are what the job "
              "becomes. Whether that is a better job is not a question this data can "
              "answer.",
              "Scale shows capacity, not headcount"),
         ]),
    dict(sid="flows", number="12 / Where people end up", rail="Where people end up",
         tint=True,
         title="Reshaped is not the same as displaced.",
         standfirst="Weighted by employment, and crossed with whether a worker\u2019s "
                    "occupation has anywhere adjacent to go. Move the scenario and both "
                    "halves move \u2014 but not by the same amount, which is the point.",
         fig="Fig. 12 \u2014 Workers by outcome",
         aria="A bar of all STEM workers on the left, split on the right into little "
              "change, could move to safer work, and nowhere adjacent to go.",
         rk="Workers reshaped", rv="43.8%",
         note="Employment counted once per SOC code. Undated.",
         controls=FL_CONTROLS,
         beats=[
             ("01 / Reshaped", "Start with whose job changes at all",
              "An occupation counts as reshaped when half its task list or more falls "
              "into the automated category. Under the middle scenario that is 35 per "
              "cent of STEM workers; under the modest one 12; under the extreme one 83.",
              "<b>12%</b> \u2192 <b>44%</b> \u2192 <b>83%</b> of workers"),
             ("02 / Little change", "Most of the workforce, at most settings",
              "The remainder are in occupations whose documented task list survives the "
              "threshold largely intact. That is the majority everywhere except the "
              "extreme case, and it is the part headlines tend to drop.",
              "The majority in two of three scenarios"),
             ("03 / Could move", "Some have somewhere to go",
              "Crossing the reshaped group with the transition map: these workers are in "
              "occupations with a close, meaningfully less exposed neighbour that shares "
              "the destination\u2019s protected work.",
              "2% \u2192 12% \u2192 44% of workers"),
             ("04 / And some do not", "The rest are in a neighbourhood that is all exposed",
              "This is the number that does not scale kindly. Between 9 and 34 per cent "
              "of STEM workers are in reshaped occupations with no adjacent destination. "
              "Under the modest scenario, four in five of those affected have nowhere to "
              "go.",
              "<b>9%</b> \u2192 <b>32%</b> \u2192 <b>39%</b> stranded"),
         ]),
    dict(sid="validation", number="07 / The check", rail="The check", tint=True,
         title="A model rating work is an assertion until someone checks it.",
         standfirst="Every other number here is internally consistent by construction. "
                    "This is the only part that could have come out wrong in a way the "
                    "rest of the pipeline would not catch.",
         fig="Fig. 07 — Against human expert ratings",
         aria="Our susceptibility index plotted against human expert exposure ratings, "
              "with a fitted line.",
         rk="A model rating work", rv="is an assertion",
         note="Benchmark: Eloundou, Manning, Mishkin & Rock (2023).",
         beats=[
             ("01 / The problem", "Self-consistency is not evidence",
              "The scores order the model's own categorical verdicts monotonically, which "
              "is reassuring and proves nothing — both come from the same model. An "
              "external benchmark is the only thing that can fail.",
              "Convergent validity <b>74.9 &gt; 65.9 &gt; 43.6 &gt; 40.3</b>"),
             ("02 / The benchmark", "Human annotators rated the same occupations",
              "Eloundou and colleagues published exposure ratings keyed to the same O*NET "
              "codes, from human annotators as well as a model. All 268 of our "
              "occupations matched with no crosswalk.",
              "<b>268 of 268</b> matched"),
             ("03 / The result", "They agree closely",
              "Correlation of 0.85 with the human ratings. The weaker agreement with "
              "their no-tools definition is expected: this rubric explicitly asks what a "
              "model could do given the right tools.",
              "<b>r = 0.85</b> against human experts"),
         ]),
]


def build_scroller(path: Path, payload: dict[str, Any], meta: dict[str, Any]) -> Path:
    css = (ASSETS / "scroller.css").read_text()
    core = (ASSETS / "scroller_core.js").read_text()
    scenes_js = (ASSETS / "scroller_scenes.js").read_text()
    core = core.replace("/* __SCENES__ */", scenes_js)

    def render_scene(sc):
        return _scene(sc["sid"], sc["number"], sc["title"], sc["standfirst"], sc["fig"],
                      sc["aria"], sc["rk"], sc["rv"], sc["note"],
                      [_beat(*b) for b in sc["beats"]], sc.get("tint", False),
                      sc.get("controls", ""))

    # The explorer breaks the story after the within-job chapter: the reader has
    # just been shown three bundles and should get to open the rest themselves.
    # Each interactive follows the chapter that motivates it: the explorer after
    # the within-job chapter, the comparison after the shared-activity one.
    cut1 = next(i for i, sc in enumerate(SCENES) if sc["sid"] == "composition") + 1
    cut2 = next(i for i, sc in enumerate(SCENES) if sc["sid"] == "leverage") + 1
    sections_before = "".join(render_scene(sc) for sc in SCENES[:cut1])
    sections_mid = "".join(render_scene(sc) for sc in SCENES[cut1:cut2])
    sections_after = "".join(render_scene(sc) for sc in SCENES[cut2:])
    rail = "".join(
        f'<a href="#{s["sid"]}"><span class="dot"></span>'
        f'<span class="rail-label">{s["rail"]}</span></a>' for s in SCENES
    )

    html = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#1c1c18">
<title>The safest job in 2013 — STEM work and the handoff to AI</title>
<meta name="description" content="What 287 STEM occupations, 5,717 tasks and 963 subtasks
say about which work is exposed to automation, and which is held by accountability.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=IBM+Plex+Mono:wght@400;500&family=Manrope:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>{css}</style>
</head>
<body>
<div class="progress"><i id="progressBar"></i></div>
<header class="site-header" id="siteHeader">
  <a class="mark" href="#hero">O*NET · STEM &amp; AUTOMATION</a>
  <span class="header-note" id="headerNote">Scroll to draw the story</span>
</header>
<nav class="rail" id="rail" aria-label="Chapters">{rail}</nav>

<section class="hero" id="hero">
  <svg class="hero-canvas" id="heroCanvas" viewBox="0 0 1200 800"
       preserveAspectRatio="xMidYMid slice" aria-hidden="true"></svg>
  <div class="hero-inner">
    <p class="eyebrow">287 STEM occupations · 5,717 tasks · 963 subtasks</p>
    <h1>Two measures of automation risk. The same jobs. No relationship at all.</h1>
    <div class="hero-bottom">
      <p class="dek">Frey and Osborne put mathematicians in their lowest-risk band in
      2013 \u2014 a 4.7 per cent chance of computerisation. Score the same occupations
      for exposure to large language models and mathematicians ranks third of 268.
      Across the 150 jobs carrying both measures the correlation is 0.006. Not weak
      agreement. None.</p>
      <div class="credit"><p>Scored by {meta.get('model','a model')}<br>
      Validated against human expert ratings at r&nbsp;=&nbsp;0.85</p></div>
    </div>
  </div>
</section>

<section class="prose">
  <p>This is what the data says. Every number below comes from a pipeline that scrapes
  O*NET, scores the 963 distinct work activities underneath 5,717 STEM tasks, propagates
  those scores back out to every task and occupation, joins BLS employment, and checks
  itself against published human ratings. The dashboard alongside it lets you interrogate
  the same tables directly.</p>
</section>
{sections_before}

<section class="explorer" id="explorer">
  <div class="xhead">
    <p class="chapter-number">Interlude / Work it through</p>
    <h2>Pick a job. Decide what counts as exposed.</h2>
    <p class="standfirst">Every task of every scored occupation, with the score it
    received. Move the threshold to set how capable you think a model has to be before a
    task is genuinely at risk \u2014 the share of the job it covers moves with you. The
    ranking of occupations is not fixed; it depends on where you draw that line.</p>
  </div>
  <div class="xwrap">
    <div class="xpanel">
      <div class="xfield">
        <label for="x-occ">Occupation</label>
        <select id="x-occ"></select>
      </div>
      <div class="xlegend">
        Jump to &mdash;
        <a href="#explorer" data-xpick="all">exposed throughout</a> &middot;
        <a href="#explorer" data-xpick="split">split down the middle</a> &middot;
        <a href="#explorer" data-xpick="none">barely moves</a>
      </div>
      <div class="xtasks" id="x-list"></div>
    </div>
    <div class="xpanel">
      <div class="xcontrols">
        <div class="xfield">
          <label for="x-thr">Exposure threshold &mdash; <span id="x-thr-out">70</span></label>
          <input type="range" id="x-thr" min="40" max="95" step="1" value="70">
        </div>
        <div class="xstat">
          <div class="k">Share of this job</div>
          <div class="n" id="x-n">&mdash;</div>
          <div class="k" id="x-k">&mdash;</div>
          <p class="sub" id="x-sub"></p>
        </div>
        <div>
          <div class="k">Against all 268 occupations</div>
          <div class="xstrip" id="x-strip"></div>
        </div>
      </div>
    </div>
  </div>
</section>

{sections_mid}

<section class="compare" id="compare">
  <div class="cwrap">
    <div class="xhead" style="margin-bottom:26px">
      <p class="chapter-number">Interlude / Side by side</p>
      <h2>Two jobs. What do they actually share?</h2>
      <p class="standfirst">Occupations overlap through the activity vocabulary, not
      through their task statements. Put two side by side and the shared spine separates
      from the speciality \u2014 and you can see whether what they have in common is the
      exposed part or the protected one.</p>
    </div>
    <div class="cpick">
      <select id="c-a"></select>
      <select id="c-b"></select>
    </div>
    <div class="xlegend" style="margin:-6px 0 16px">
      Try &mdash;
      <a href="#compare" data-cpick="pairA,pairB">two database roles</a> &middot;
      <a href="#compare" data-cpick="all,none">opposite ends</a> &middot;
      <a href="#compare" data-cpick="all,split">exposed vs split</a>
    </div>
    <div class="csum" id="c-sum"></div>
    <div class="ccols" id="c-out"></div>
  </div>
</section>

{sections_after}


<section class="ending coda">
  <svg class="coda-canvas" id="codaCanvas" viewBox="0 0 1200 300"
       preserveAspectRatio="xMidYMid meet" aria-hidden="true"></svg>
  <div class="coda-inner">
    <p class="eyebrow">What this cannot tell you</p>
    <h2>Three limits worth stating before anyone cites it.</h2>
    <p class="dek"><b>The unit is the task, not the decision.</b> Watson's framework scores
    recurring decisions, and he is explicit that identifying which tasks are decisions is
    the novel work. It has not been done here, so the stage numbers are provisional.</p>
    <p class="dek"><b>The scores are model judgment.</b> They agree with human annotators at
    r&nbsp;=&nbsp;0.85, which is evidence of validity, not a substitute for it. No
    reliability estimate exists yet — nobody has checked whether a second run agrees
    with the first.</p>
    <p class="dek"><b>Exposure is not displacement.</b> Nothing here measures what
    employers will do, what regulation will permit, or how fast anything diffuses. It
    measures the shape of the work and where accountability sits.</p>
  </div>
</section>

<script>window.__STORY__ = {json.dumps(payload, separators=(',', ':'))};</script>
<script>{core}</script>
</body></html>"""
    path.write_text(html, encoding="utf-8")
    log.info("wrote %-28s %.2f MB", path.name, path.stat().st_size / 1e6)
    return path
