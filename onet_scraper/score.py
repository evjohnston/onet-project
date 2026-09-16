"""Score the subtask vocabulary for automation exposure, then propagate.

Why score subtasks and not tasks: there are 5,717 tasks but only ~963 distinct
detailed work activities behind them. Rating the subtask layer once is ~6x less
work AND more consistent - the same activity cannot receive different ratings in
two different occupations, which is exactly the artefact that makes task-level
ratings hard to compare across jobs.

Scores propagate: subtask -> task (mean over the task's subtasks) -> occupation
(importance-weighted mean over the occupation's tasks).
"""

from __future__ import annotations

import collections
import hashlib
import json
import logging
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Literal, Sequence

log = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-opus-5"

# Bump when the rubric or dimensions change: cached scores from an older rubric
# are not comparable and are re-run rather than silently mixed in.
RUBRIC_VERSION = "2026-09-16.1"

DIMENSIONS = (
    "automation_feasibility_today",
    "llm_exposure",
    "physical_embodiment_required",
    "interpersonal_demand",
    "judgment_under_uncertainty",
    "accountability_requirement",
    "error_cost",
)

SYSTEM_PROMPT = """\
You are an expert in labour economics and the automation of work, building a \
research instrument. You rate standardised work activities from the O*NET \
taxonomy (Detailed Work Activities) on their exposure to automation.

Rate each activity on these seven dimensions, each 0-100:

1. automation_feasibility_today - Could technology that is commercially \
deployed TODAY perform this activity end-to-end with no human in the loop? \
0 = no deployed system can do any meaningful part; 100 = routinely fully \
automated in practice right now. Judge deployment reality, not laboratory \
demos or near-future promise.

2. llm_exposure - How much of the COGNITIVE core of this activity could a \
current frontier language or multimodal model perform, given the right inputs \
and tools? 0 = nothing (purely physical or purely relational); 100 = the \
activity is essentially reading, writing, analysing or reasoning over \
information.

3. physical_embodiment_required - Does this require manipulating physical \
objects or being bodily present in a specific place? 0 = fully doable from a \
terminal anywhere; 100 = impossible without hands on matter in situ.

4. interpersonal_demand - Does this require reading, persuading, caring for, \
teaching, or coordinating with other people as the substance of the work \
(not merely reporting results to them)? 0 = solitary; 100 = the human \
relationship IS the work.

5. judgment_under_uncertainty - Does it require weighing incomplete, \
conflicting or ambiguous evidence, where reasonable experts could disagree? \
0 = deterministic, one correct answer by rule; 100 = irreducibly contested \
professional judgment.

6. accountability_requirement - Must an identifiable human be answerable for \
the outcome, for legal, ethical, professional-licensure or safety reasons? \
0 = nobody needs to sign; 100 = the law or professional ethics requires a \
named responsible human.

7. error_cost - How severe and how irreversible is a mistake? 0 = trivial and \
instantly correctable; 100 = catastrophic, irreversible, life-threatening.

Then assign a verdict:
- "largely_automatable" - deployed technology can already do most of this
- "augmentable" - technology substantially speeds a human up but cannot own it
- "resistant" - only narrow slices are automatable with today's approaches
- "human_anchored" - a human must remain responsible regardless of capability, \
because of accountability, embodiment or the relational nature of the work

Calibration discipline:
- Use the full 0-100 range. Resist clustering everything at 50-70.
- Dimensions are independent. High llm_exposure with high \
accountability_requirement is common and correct (e.g. drafting a legal \
opinion) - do not let one dimension drag another.
- "human_anchored" is about who must be RESPONSIBLE, not about capability. An \
activity can score high on llm_exposure and still be human_anchored.
- Rate the activity as written and at the generality it is written. Do not \
imagine a specific occupation's version of it.
- confidence "low" is a legitimate answer for vague or heterogeneous activities.

Give a rationale of one or two sentences naming the binding constraint - the \
specific thing that stops or permits automation. Avoid restating the scores.
"""


def _pydantic_models():
    """Imported lazily so the scraper works without the scoring dependency."""
    from pydantic import BaseModel, Field

    class SubtaskScore(BaseModel):
        dwa_id: str = Field(description="The O*NET DWA element id exactly as given")
        automation_feasibility_today: int = Field(ge=0, le=100)
        llm_exposure: int = Field(ge=0, le=100)
        physical_embodiment_required: int = Field(ge=0, le=100)
        interpersonal_demand: int = Field(ge=0, le=100)
        judgment_under_uncertainty: int = Field(ge=0, le=100)
        accountability_requirement: int = Field(ge=0, le=100)
        error_cost: int = Field(ge=0, le=100)
        verdict: Literal["largely_automatable", "augmentable", "resistant", "human_anchored"]
        confidence: Literal["low", "medium", "high"]
        rationale: str

    class ScoreBatch(BaseModel):
        scores: list[SubtaskScore]

    return SubtaskScore, ScoreBatch


# --------------------------------------------------------------------------- #
# Input assembly                                                                #
# --------------------------------------------------------------------------- #
def subtask_catalogue(
    task_subtasks: Sequence[dict[str, Any]],
    hierarchy: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """The distinct subtasks to score, with hierarchy context for the prompt."""
    hier = {h["dwa_id"]: h for h in hierarchy}
    occs: dict[str, set[str]] = collections.defaultdict(set)
    titles: dict[str, str] = {}
    for link in task_subtasks:
        if not link["dwa_id"]:
            continue
        occs[link["dwa_id"]].add(link["onet_soc_code"])
        titles[link["dwa_id"]] = link["dwa_title"]
    return [
        {
            "dwa_id": dwa,
            "dwa_title": titles[dwa],
            "iwa_title": hier.get(dwa, {}).get("iwa_title", ""),
            "gwa_title": hier.get(dwa, {}).get("gwa_title", ""),
            "n_occupations": len(codes),
        }
        for dwa, codes in sorted(occs.items())
    ]


def _render_chunk(chunk: Sequence[dict[str, Any]]) -> str:
    lines = ["Rate each of the following work activities.", ""]
    for item in chunk:
        lines.append(f"- id: {item['dwa_id']}")
        lines.append(f"  activity: {item['dwa_title']}")
        if item["iwa_title"]:
            lines.append(f"  broader category: {item['iwa_title']}")
        if item["gwa_title"]:
            lines.append(f"  general domain: {item['gwa_title']}")
        lines.append("")
    lines.append(f"Return exactly {len(chunk)} score objects, one per id, in the same order.")
    return "\n".join(lines)


def _checkpoint_path(raw_dir: Path) -> Path:
    return raw_dir / "subtask_scores.jsonl"


def load_scores(raw_dir: Path) -> dict[str, dict[str, Any]]:
    path = _checkpoint_path(raw_dir)
    scores: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return scores
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            log.warning("dropping corrupt score line")
            continue
        if row.get("rubric_version") == RUBRIC_VERSION:
            scores[row["dwa_id"]] = row
    return scores


# --------------------------------------------------------------------------- #
# Scoring run                                                                   #
# --------------------------------------------------------------------------- #
def estimate_cost(catalogue: Sequence[dict[str, Any]], chunk_size: int, model: str) -> dict[str, Any]:
    """Rough pre-flight estimate so nobody starts a run blind."""
    prices = {  # USD per 1M tokens (input, output)
        "claude-opus-5": (5.0, 25.0),
        "claude-sonnet-5": (2.0, 10.0),
        "claude-haiku-4-5": (1.0, 5.0),
    }
    rate_in, rate_out = prices.get(model, (5.0, 25.0))
    requests = (len(catalogue) + chunk_size - 1) // chunk_size
    # ~1.4k system + ~55 tokens per activity in; ~180 output tokens per activity
    # plus thinking overhead, which dominates at default effort.
    tokens_in = requests * 1400 + len(catalogue) * 55
    tokens_out = len(catalogue) * 180 + requests * 1500
    return {
        "subtasks": len(catalogue),
        "requests": requests,
        "est_input_tokens": tokens_in,
        "est_output_tokens": tokens_out,
        "est_cost_usd": round(tokens_in / 1e6 * rate_in + tokens_out / 1e6 * rate_out, 2),
        "model": model,
        "note": "estimate only; adaptive thinking makes output tokens variable",
    }


def score_subtasks(
    catalogue: Sequence[dict[str, Any]],
    raw_dir: Path,
    *,
    model: str = DEFAULT_MODEL,
    chunk_size: int = 12,
    workers: int = 4,
    refresh: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "the scoring stage needs the Anthropic SDK: pip install 'anthropic>=1.0'"
        ) from exc

    _, ScoreBatch = _pydantic_models()
    client = anthropic.Anthropic()

    done = {} if refresh else load_scores(raw_dir)
    todo = [item for item in catalogue if item["dwa_id"] not in done]
    log.info("scoring: %d subtasks total, %d already scored at rubric %s, %d to do",
             len(catalogue), len(catalogue) - len(todo), RUBRIC_VERSION, len(todo))
    if not todo:
        return [done[i["dwa_id"]] for i in catalogue if i["dwa_id"] in done], []

    chunks = [todo[i:i + chunk_size] for i in range(0, len(todo), chunk_size)]
    by_id = {item["dwa_id"]: item for item in catalogue}
    failures: list[dict[str, str]] = []
    write_lock = threading.Lock()
    path = _checkpoint_path(raw_dir)
    if refresh and path.exists():
        path.unlink()
    sink = path.open("a")

    def run(chunk: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
        response = client.messages.parse(
            model=model,
            max_tokens=16000,
            thinking={"type": "adaptive"},
            system=[{"type": "text", "text": SYSTEM_PROMPT,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": _render_chunk(chunk)}],
            output_format=ScoreBatch,
        )
        if response.stop_reason == "refusal":
            raise RuntimeError(f"model declined: {response.stop_details}")
        parsed = response.parsed_output
        expected = {item["dwa_id"] for item in chunk}
        rows = []
        for score in parsed.scores:
            if score.dwa_id not in expected:
                log.warning("model returned unrequested id %r, dropping", score.dwa_id)
                continue
            row = score.model_dump()
            row["dwa_title"] = by_id[score.dwa_id]["dwa_title"]
            row["rubric_version"] = RUBRIC_VERSION
            row["model"] = model
            row["scored_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            rows.append(row)
        returned = {r["dwa_id"] for r in rows}
        if missing := expected - returned:
            raise RuntimeError(f"model omitted {len(missing)} of {len(expected)} ids")
        return rows

    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(run, chunk): chunk for chunk in chunks}
            for n, future in enumerate(as_completed(futures), start=1):
                chunk = futures[future]
                try:
                    rows = future.result()
                except Exception as exc:
                    log.error("chunk of %d failed: %s", len(chunk), exc)
                    failures.extend({"dwa_id": i["dwa_id"], "error": str(exc)} for i in chunk)
                    continue
                with write_lock:
                    for row in rows:
                        done[row["dwa_id"]] = row
                        sink.write(json.dumps(row, ensure_ascii=False) + "\n")
                    sink.flush()
                if n % 10 == 0 or n == len(chunks):
                    log.info("  scored %d/%d chunks (%d subtasks)", n, len(chunks), len(done))
    finally:
        sink.close()

    ordered = [done[i["dwa_id"]] for i in catalogue if i["dwa_id"] in done]
    return ordered, failures


# --------------------------------------------------------------------------- #
# Propagation: subtask -> task -> occupation                                    #
# --------------------------------------------------------------------------- #
SUBTASK_SCORE_COLUMNS = ("dwa_id", "dwa_title", *DIMENSIONS, "verdict", "confidence",
                         "rationale", "rubric_version", "model", "scored_at")
TASK_SCORE_COLUMNS = ("onet_soc_code", "occupation_title", "task_id", "task",
                      "task_category", "importance", "n_subtasks_scored",
                      *DIMENSIONS, "dominant_verdict")
OCC_SCORE_COLUMNS = ("onet_soc_code", "title", "stem_occupation_types", "job_zone",
                     "n_tasks_scored", "task_coverage", *DIMENSIONS,
                     "share_largely_automatable", "share_human_anchored")


def propagate(
    scores: Sequence[dict[str, Any]],
    tasks: Sequence[dict[str, Any]],
    task_subtasks: Sequence[dict[str, Any]],
    occupations: Sequence[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_dwa = {s["dwa_id"]: s for s in scores}
    links: dict[tuple[str, Any], list[dict[str, Any]]] = collections.defaultdict(list)
    for link in task_subtasks:
        score = by_dwa.get(link["dwa_id"])
        if score:
            links[(link["onet_soc_code"], link["task_id"])].append(score)

    task_rows = []
    for task in tasks:
        matched = links.get((task["onet_soc_code"], task["task_id"]), [])
        if not matched:
            continue
        row = {
            "onet_soc_code": task["onet_soc_code"],
            "occupation_title": task["occupation_title"],
            "task_id": task["task_id"],
            "task": task["task"],
            "task_category": task["task_category"],
            "importance": task["importance"],
            "n_subtasks_scored": len(matched),
        }
        for dim in DIMENSIONS:
            row[dim] = round(statistics.fmean(s[dim] for s in matched), 1)
        row["dominant_verdict"] = collections.Counter(
            s["verdict"] for s in matched).most_common(1)[0][0]
        task_rows.append(row)

    by_occ: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in task_rows:
        by_occ[row["onet_soc_code"]].append(row)
    total_tasks = collections.Counter(t["onet_soc_code"] for t in tasks)

    occ_rows = []
    for occ in occupations:
        code = occ["onet_soc_code"]
        rows = by_occ.get(code, [])
        if not rows:
            continue
        # Weight by task importance: a job is characterised by what matters in it.
        weights = [float(r["importance"]) if r["importance"] not in (None, "") else 50.0
                   for r in rows]
        total_w = sum(weights) or 1.0
        out = {
            "onet_soc_code": code,
            "title": occ.get("title", ""),
            "stem_occupation_types": occ.get("stem_occupation_types", ""),
            "job_zone": occ.get("job_zone"),
            "n_tasks_scored": len(rows),
            "task_coverage": round(len(rows) / total_tasks[code], 3) if total_tasks[code] else 0.0,
        }
        for dim in DIMENSIONS:
            out[dim] = round(sum(r[dim] * w for r, w in zip(rows, weights)) / total_w, 1)
        verdicts = collections.Counter(r["dominant_verdict"] for r in rows)
        out["share_largely_automatable"] = round(verdicts["largely_automatable"] / len(rows), 3)
        out["share_human_anchored"] = round(verdicts["human_anchored"] / len(rows), 3)
        occ_rows.append(out)

    return (sorted(task_rows, key=lambda r: (r["onet_soc_code"], r["task_id"] or 0)),
            sorted(occ_rows, key=lambda r: r["onet_soc_code"]))


def rubric_fingerprint() -> str:
    return hashlib.sha256((RUBRIC_VERSION + SYSTEM_PROMPT).encode()).hexdigest()[:16]
