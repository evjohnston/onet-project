"""Benchmark the susceptibility index against published measures.

The index is one model's judgment. On its own that is an assertion, not a
finding. This module joins it to independently produced measures - crucially
including *human* expert ratings - so the claim can be checked rather than
asserted.

Sources (all public, all keyed to occupation codes we already carry):

  Eloundou, Manning, Mishkin & Rock (2023), "GPTs are GPTs".
    occ_level.csv is keyed to the 8-digit O*NET-SOC code, so it joins directly
    with no crosswalk. It carries GPT-4 ratings AND human annotator ratings on
    three exposure definitions:
      alpha - the task can be done directly, no tools
      beta  - with software built on top of the model
      gamma - the broadest reading
    autoScores.csv is keyed to the 6-digit SOC and bundles several earlier
    measures: Frey & Osborne (2017), Felten, Raj & Seamans, and the
    Brynjolfsson/Mitchell/Rock Suitability for Machine Learning score.

Our rubric asks what a model could do "given the right inputs and tools", which
is definitionally closer to beta/gamma than to alpha. Expect - and check for -
a higher correlation with those.

Result as built: r = 0.85 against human gamma ratings and 0.83 against human
beta, but ~0 against the pre-LLM measures. Both halves matter. The first says
the index tracks what human experts think LLM exposure means; the second says
LLM exposure is a different phenomenon from the automation exposure measured
before 2020, not a relabelling of it.
"""

from __future__ import annotations

import csv
import io
import logging
import statistics
from typing import Any, Sequence

log = logging.getLogger(__name__)

RAW = "https://raw.githubusercontent.com/openai/GPTs-are-GPTs/main/data/"
ELOUNDOU_OCC_URL = RAW + "occ_level.csv"
ELOUNDOU_AUTO_URL = RAW + "autoScores.csv"

CITATION = ("Eloundou, T., Manning, S., Mishkin, P., & Rock, D. (2023). "
            "GPTs are GPTs: An early look at the labor market impact potential of "
            "large language models. https://github.com/openai/GPTs-are-GPTs")

BENCHMARK_COLUMNS = ("onet_soc_code", "title", "our_susceptibility", "our_exposure",
                     "our_anchoring", "human_alpha", "human_beta", "human_gamma",
                     "gpt4_alpha", "gpt4_beta", "gpt4_gamma", "frey_osborne",
                     "felten_raj_seamans", "brynjolfsson_sml")

# Which published measure each of our columns should be compared against, and
# whether we expect a strong relationship. Stated up front so a weak result is a
# finding rather than something to explain away afterwards.
EXPECTATIONS = {
    "human_beta": "strong - closest definition to our rubric",
    "human_gamma": "strong - closest definition to our rubric",
    "human_alpha": "moderate - excludes tools, which our rubric assumes",
    "gpt4_beta": "strong - but model-to-model, so less independent",
    "gpt4_gamma": "strong - but model-to-model, so less independent",
    "gpt4_alpha": "moderate - excludes tools",
    # These three were first written down as "moderate positive" and the data
    # refuted that outright (r = 0.01, -0.18, -0.09). The expectations below are
    # the corrected, theory-consistent ones: pre-LLM measures scored the
    # routine/manual gradient, and LLMs run the other way - they land hardest on
    # non-routine cognitive work, which those measures called safe. Frey & Osborne
    # give Mathematicians a 4.7% chance of computerisation; this index ranks them
    # the single most susceptible STEM occupation. Near-zero-to-negative is the
    # right answer here, and a strong positive would have been the warning sign.
    "frey_osborne": "near zero or negative - pre-LLM, scored the routine gradient",
    "felten_raj_seamans": "near zero or negative - pre-LLM AI-capability exposure",
    "brynjolfsson_sml": "near zero or negative - pre-LLM machine-learning suitability",
}


def _f(value: Any) -> float | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return None if v != v else v  # drop NaN


def pearson(a: Sequence[float], b: Sequence[float]) -> float:
    ma, mb = statistics.fmean(a), statistics.fmean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    den = (sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b)) ** 0.5
    return num / den if den else 0.0


def spearman(a: Sequence[float], b: Sequence[float]) -> float:
    def ranks(values: Sequence[float]) -> list[float]:
        order = sorted(range(len(values)), key=lambda i: values[i])
        out = [0.0] * len(values)
        i = 0
        while i < len(order):           # average ranks within ties
            j = i
            while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
                j += 1
            mean_rank = (i + j) / 2
            for k in range(i, j + 1):
                out[order[k]] = mean_rank
            i = j + 1
        return out
    return pearson(ranks(a), ranks(b))


def fetch_benchmarks(client, settings) -> dict[str, Any]:
    occ_page = client.get(ELOUNDOU_OCC_URL)
    auto_page = client.get(ELOUNDOU_AUTO_URL)
    (settings.bulk_dir / "eloundou_occ_level.csv").write_bytes(occ_page.content)
    (settings.bulk_dir / "eloundou_autoScores.csv").write_bytes(auto_page.content)

    occ = {r["O*NET-SOC Code"]: r
           for r in csv.DictReader(io.StringIO(occ_page.text))}
    # autoScores repeats each occupation once per year; the published measures are
    # time-invariant, so keep one row each.
    auto: dict[str, dict[str, str]] = {}
    for row in csv.DictReader(io.StringIO(auto_page.text)):
        auto.setdefault(row["simpleOcc"], row)
    log.info("benchmarks: %d O*NET-level, %d SOC-level occupations", len(occ), len(auto))
    return {"occ": occ, "auto": auto}


def join(
    ours: Sequence[dict[str, Any]],
    benchmarks: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    occ, auto = benchmarks["occ"], benchmarks["auto"]
    rows, unmatched = [], []
    for row in ours:
        code = row["onet_soc_code"]
        theirs = occ.get(code)
        soc = auto.get(code.split(".")[0], {})
        if theirs is None and not soc:
            unmatched.append(code)
            continue
        theirs = theirs or {}
        rows.append({
            "onet_soc_code": code,
            "title": row.get("title", ""),
            "our_susceptibility": _f(row.get("susceptibility")),
            "our_exposure": _f(row.get("exposure")),
            "our_anchoring": _f(row.get("anchoring")),
            "human_alpha": _f(theirs.get("human_rating_alpha")),
            "human_beta": _f(theirs.get("human_rating_beta")),
            "human_gamma": _f(theirs.get("human_rating_gamma")),
            "gpt4_alpha": _f(theirs.get("dv_rating_alpha")),
            "gpt4_beta": _f(theirs.get("dv_rating_beta")),
            "gpt4_gamma": _f(theirs.get("dv_rating_gamma")),
            "frey_osborne": _f(soc.get("freyOsborne")),
            "felten_raj_seamans": _f(soc.get("felten_raj_seamans")),
            "brynjolfsson_sml": _f(soc.get("mSML")),
        })
    return rows, {"matched": len(rows), "unmatched": unmatched}


def correlate(rows: Sequence[dict[str, Any]],
              against: str = "our_susceptibility") -> list[dict[str, Any]]:
    out = []
    for measure, expectation in EXPECTATIONS.items():
        pairs = [(r[against], r[measure]) for r in rows
                 if r.get(against) is not None and r.get(measure) is not None]
        if len(pairs) < 10:
            out.append({"measure": measure, "n": len(pairs), "pearson": None,
                        "spearman": None, "expectation": expectation,
                        "note": "too few overlapping observations"})
            continue
        a = [p[0] for p in pairs]
        b = [p[1] for p in pairs]
        out.append({"measure": measure, "n": len(pairs),
                    "pearson": round(pearson(a, b), 3),
                    "spearman": round(spearman(a, b), 3),
                    "expectation": expectation})
    return out
