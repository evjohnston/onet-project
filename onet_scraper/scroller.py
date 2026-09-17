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
    handoff: Sequence[dict[str, Any]],
    benchmarks: Sequence[dict[str, Any]],
    soc: Sequence[dict[str, Any]],
    employment_report: dict[str, Any],
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

    return {
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
           beats: list[str], tint: bool = False) -> str:
    cls = "scene on-tint" if tint else "scene"
    return f"""
  <section class="{cls}" id="{sid}" data-scene="{sid}">
    <div class="scene-head">
      <p class="chapter-number">{number}</p>
      <div><h2>{title}</h2><p class="standfirst">{standfirst}</p></div>
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

    sections = "".join(
        _scene(s["sid"], s["number"], s["title"], s["standfirst"], s["fig"], s["aria"],
               s["rk"], s["rv"], s["note"],
               [_beat(*b) for b in s["beats"]], s.get("tint", False))
        for s in SCENES
    )
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
{sections}

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
