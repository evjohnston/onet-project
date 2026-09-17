"""The network and scoring stages, which run on top of a built dataset."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .build import COLUMNS, append_sqlite, read_table, write_csv
from .config import Settings
from .network import (
    backbone,
    build_incidence,
    force_layout,
    occupation_edges,
    occupation_nodes,
    subtask_network,
    validate_against_related,
    write_graphml,
)
from .score import (
    RUBRIC_VERSION,
    estimate_cost,
    propagate,
    rubric_fingerprint,
    score_subtasks,
    subtask_catalogue,
)

log = logging.getLogger(__name__)


def run_network(settings: Settings, *, min_shared: int, min_co_occurring: int,
                exclude_soc: tuple[str, ...]) -> dict[str, Any]:
    tasks = read_table(settings.out_dir, "tasks")
    task_subtasks = read_table(settings.out_dir, "task_subtasks")
    hierarchy = read_table(settings.out_dir, "subtask_hierarchy")
    occupations = {o["onet_soc_code"]: o for o in read_table(settings.out_dir, "occupations")}
    related = read_table(settings.out_dir, "related_occupations")

    if not task_subtasks:
        raise SystemExit("no task_subtasks table - run the build stage with the bulk crosswalk first")
    if exclude_soc:
        log.info("excluding SOC prefixes %s from the network", ", ".join(exclude_soc))

    occ_dwa, weights, dwa_occ = build_incidence(task_subtasks, tasks, exclude_soc)
    edges = occupation_edges(occ_dwa, weights, occupations, min_shared=min_shared)
    nodes = occupation_nodes(occ_dwa, weights, edges, occupations)

    # Precompute the drawing here: it is O(n^2) per iteration and static, so
    # doing it in the browser just blocks the page on load.
    bone = backbone(edges)
    log.info("laying out %d nodes over a %d-edge backbone", len(nodes), len(bone))
    positions = force_layout([n["onet_soc_code"] for n in nodes], bone)
    for node in nodes:
        x, y = positions.get(node["onet_soc_code"], (0.5, 0.5))
        node["layout_x"], node["layout_y"] = x, y
    dwa_edges, dwa_nodes = subtask_network(dwa_occ, hierarchy, task_subtasks,
                                           min_shared=min_co_occurring)

    tables = {
        "network_occupation_edges": edges,
        "network_occupation_nodes": nodes,
        "network_subtask_edges": dwa_edges,
        "network_subtask_nodes": dwa_nodes,
    }
    for name, rows in tables.items():
        write_csv(settings.out_dir / f"{name}.csv", rows, COLUMNS[name])
    append_sqlite(settings.out_dir / "onet_stem.sqlite", tables)

    write_graphml(settings.out_dir / "network_occupations.graphml", nodes, edges,
                  "onet_soc_code", "cosine")
    write_graphml(settings.out_dir / "network_subtasks.graphml", dwa_nodes, dwa_edges,
                  "dwa_id", "co_occurring_occupations")

    check = validate_against_related(edges, related)
    report = {
        "occupation_nodes": len(nodes),
        "occupation_edges": len(edges),
        "subtask_nodes": len(dwa_nodes),
        "subtask_edges": len(dwa_edges),
        "density": round(2 * len(edges) / (len(nodes) * (len(nodes) - 1)), 4) if len(nodes) > 1 else 0,
        "min_shared_subtasks": min_shared,
        "excluded_soc_prefixes": list(exclude_soc),
        "validation_vs_onet_related": check,
    }
    (settings.out_dir / "network_report.json").write_text(json.dumps(report, indent=2))
    for key, value in report.items():
        log.info("%-28s %s", key, value)
    if check.get("available"):
        log.info("recall@%d vs O*NET's own related list: %.1f%% "
                 "(ceiling %.1f%%, so %.1f%% of what is reachable)",
                 check["k"], 100 * check["recall_at_k"],
                 100 * check["max_achievable_recall_at_k"],
                 100 * check["recall_vs_ceiling"])
    else:
        log.info("no related_occupations table - run fetch-descriptors to enable validation")
    return report


def run_score(settings: Settings, *, model: str, chunk_size: int, workers: int,
              refresh: bool, dry_run: bool) -> dict[str, Any]:
    task_subtasks = read_table(settings.out_dir, "task_subtasks")
    hierarchy = read_table(settings.out_dir, "subtask_hierarchy")
    tasks = read_table(settings.out_dir, "tasks")
    occupations = read_table(settings.out_dir, "occupations")
    if not task_subtasks:
        raise SystemExit("no task_subtasks table - run the build stage first")

    catalogue = subtask_catalogue(task_subtasks, hierarchy)
    estimate = estimate_cost(catalogue, chunk_size, model)
    log.info("rubric %s (fingerprint %s)", RUBRIC_VERSION, rubric_fingerprint())
    for key, value in estimate.items():
        log.info("  %-22s %s", key, value)
    if dry_run:
        log.info("dry run: nothing sent to the API")
        return {"estimate": estimate, "dry_run": True}

    scores, failures = score_subtasks(catalogue, settings.raw_dir, model=model,
                                      chunk_size=chunk_size, workers=workers,
                                      refresh=refresh)
    if failures:
        (settings.raw_dir / "score_failures.json").write_text(json.dumps(failures, indent=2))
        log.error("%d subtasks failed to score; re-run to retry only those", len(failures))

    task_scores, occ_scores = propagate(scores, tasks, task_subtasks, occupations)
    tables = {
        "subtask_automation_scores": scores,
        "task_automation_scores": task_scores,
        "occupation_automation_scores": occ_scores,
    }
    for name, rows in tables.items():
        write_csv(settings.out_dir / f"{name}.csv", rows, COLUMNS[name])
    append_sqlite(settings.out_dir / "onet_stem.sqlite", tables)

    report = {
        "rubric_version": RUBRIC_VERSION,
        "rubric_fingerprint": rubric_fingerprint(),
        "model": model,
        "subtasks_scored": len(scores),
        "subtasks_requested": len(catalogue),
        "tasks_scored": len(task_scores),
        "occupations_scored": len(occ_scores),
        "failures": len(failures),
        "estimate": estimate,
    }
    (settings.out_dir / "scoring_report.json").write_text(json.dumps(report, indent=2))
    log.info("scored %d/%d subtasks -> %d tasks -> %d occupations",
             len(scores), len(catalogue), len(task_scores), len(occ_scores))
    return report


def run_report(settings: Settings) -> dict[str, Any]:
    """Compute the susceptibility index and render the dashboard."""
    from .dashboard import build_dashboard
    from .susceptibility import (
        OCC_SUSC_COLUMNS,
        SUBTASK_SUSC_COLUMNS,
        TASK_SUSC_COLUMNS,
        build,
        convergent_validity,
    )

    subtask_scores = read_table(settings.out_dir, "subtask_automation_scores")
    if not subtask_scores:
        raise SystemExit("no subtask_automation_scores - run the score stage first")
    task_scores = read_table(settings.out_dir, "task_automation_scores")
    occ_scores = read_table(settings.out_dir, "occupation_automation_scores")
    task_subtasks = read_table(settings.out_dir, "task_subtasks")
    occupations = read_table(settings.out_dir, "occupations")

    result = build(subtask_scores, task_scores, occ_scores, task_subtasks, occupations)
    splits = result.pop("_splits")[0]

    columns = {"subtask_susceptibility": SUBTASK_SUSC_COLUMNS,
               "task_susceptibility": TASK_SUSC_COLUMNS,
               "occupation_susceptibility": OCC_SUSC_COLUMNS}
    for name, rows in result.items():
        COLUMNS[name] = columns[name]
        write_csv(settings.out_dir / f"{name}.csv", rows, columns[name])
    append_sqlite(settings.out_dir / "onet_stem.sqlite", result)

    # Watson handoff framing, computed from the same scored dimensions.
    from .handoff import HANDOFF_COLUMNS, build as build_handoff, summarise as sum_handoff
    occ_scores = read_table(settings.out_dir, "occupation_automation_scores")
    soc_emp = read_table(settings.out_dir, "soc_susceptibility")
    emp_by_onet: dict[str, float] = {}
    for srow in soc_emp:
        for code in (srow.get("onet_codes") or "").split(";"):
            if code and srow.get("total_employment"):
                # SOC employment, carried for scale only - never summed across
                # the O*NET occupations inside one SOC.
                emp_by_onet[code] = float(srow["total_employment"])
    occ_titles = {o["onet_soc_code"]: o for o in occupations}
    for row in occ_scores:
        meta = occ_titles.get(row["onet_soc_code"], {})
        row.setdefault("title", meta.get("title", ""))
        row["stem_occupation_types"] = meta.get("stem_occupation_types", "")
    handoff_rows = build_handoff(occ_scores, employment=emp_by_onet)
    COLUMNS["occupation_handoff"] = HANDOFF_COLUMNS
    write_csv(settings.out_dir / "occupation_handoff.csv", handoff_rows, HANDOFF_COLUMNS)
    append_sqlite(settings.out_dir / "onet_stem.sqlite",
                  {"occupation_handoff": handoff_rows})
    handoff_summary = sum_handoff(handoff_rows)
    log.info("handoff framing: %s", handoff_summary["by_classification"])
    log.info("  %d occupations have a pending crossing, %d of them at one of the "
             "two weighty crossings", handoff_summary["with_pending_crossing"],
             handoff_summary["at_a_weighty_crossing"])

    validity = convergent_validity(result["subtask_susceptibility"])
    log.info("convergent validity (mean index by the model's own verdict): %s", validity)
    if not validity.get("monotonic"):
        log.warning("index does NOT order the verdicts monotonically - treat it with suspicion")

    scoring_meta = {}
    report_path = settings.out_dir / "scoring_report.json"
    if report_path.exists():
        scoring_meta = json.loads(report_path.read_text())

    # Optional: the employment layer, if the employment stage has been run.
    soc_rows = read_table(settings.out_dir, "soc_susceptibility")
    employment_meta: dict[str, Any] = {}
    emp_report = settings.out_dir / "employment_report.json"
    if emp_report.exists():
        payload = json.loads(emp_report.read_text())
        employment_meta = dict(payload.get("headline", {}))
        employment_meta["release"] = payload.get("oews_release", "")

    dashboard = build_dashboard(
        settings.out_dir / "dashboard.html",
        result["occupation_susceptibility"],
        result["task_susceptibility"],
        result["subtask_susceptibility"],
        splits,
        {"model": scoring_meta.get("model", ""),
         "rubric_version": scoring_meta.get("rubric_version", "")},
        soc=soc_rows,
        employment=employment_meta,
        benchmarks=read_table(settings.out_dir, "external_benchmarks"),
        net_edges=read_table(settings.out_dir, "network_occupation_edges"),
        net_nodes=read_table(settings.out_dir, "network_occupation_nodes"),
        handoff=handoff_rows,
        dimensions=read_table(settings.out_dir, "occupation_automation_scores"),
    )

    report = {"splits": splits, "convergent_validity": validity,
              "handoff": handoff_summary,
              "rows": {k: len(v) for k, v in result.items()},
              "dashboard": str(dashboard)}
    (settings.out_dir / "susceptibility_report.json").write_text(json.dumps(report, indent=2))
    log.info("open %s", dashboard)
    return report


def run_employment(settings: Settings, client) -> dict[str, Any]:
    """Join BLS OEWS employment and wages at the SOC level."""
    from .employment import (
        OEWS_COLUMNS,
        SOC_SUSC_COLUMNS,
        build_soc_table,
        fetch_oews,
        headline_stats,
    )

    occ = read_table(settings.out_dir, "occupation_susceptibility")
    if not occ:
        raise SystemExit("no occupation_susceptibility - run the report stage first")

    oews = fetch_oews(client, settings)
    soc_rows, diagnostics = build_soc_table(occ, oews["rows"])

    matched = {r["soc_code"] for r in soc_rows}
    tables = {
        "oews_occupations": [v for k, v in sorted(oews["rows"].items()) if k in matched],
        "soc_susceptibility": soc_rows,
    }
    COLUMNS["oews_occupations"] = OEWS_COLUMNS
    COLUMNS["soc_susceptibility"] = SOC_SUSC_COLUMNS
    for name, rows in tables.items():
        write_csv(settings.out_dir / f"{name}.csv", rows, COLUMNS[name])
    append_sqlite(settings.out_dir / "onet_stem.sqlite", tables)

    stats = headline_stats(soc_rows)
    report = {"oews_release": f"May 20{oews['release']}", "join": diagnostics,
              "headline": stats}
    (settings.out_dir / "employment_report.json").write_text(json.dumps(report, indent=2))

    log.info("-" * 68)
    log.info("%d O*NET occupations collapsed to %d SOC codes (%d SOCs had >1 detail "
             "occupation, which a naive join would have multi-counted)",
             diagnostics["onet_occupations_in"], diagnostics["soc_codes_out"],
             diagnostics["collapsed_socs"])
    if diagnostics["unmatched_onet_codes"]:
        log.warning("%d O*NET codes had no OEWS match: %s",
                    len(diagnostics["unmatched_onet_codes"]),
                    diagnostics["unmatched_onet_codes"][:6])
    log.info("total employment covered: %s", f"{stats['total_employment']:,}")
    log.info("employment-weighted susceptibility: %s (unweighted %s, shift %+.1f)",
             stats["employment_weighted_susceptibility"],
             stats["unweighted_susceptibility"], stats["weighting_shifts_result_by"])
    log.info("workers in high-susceptibility occupations: %s (%.1f%%)",
             f"{stats['workers_in_high_susceptibility_occupations']:,}",
             100 * stats["share_workers_high_susceptibility"])
    for q, v in sorted(stats["by_quadrant"].items(), key=lambda kv: -kv[1]["employment"]):
        log.info("  %-16s %12s workers (%.1f%%)  $%.0fB wage bill",
                 q, f"{v['employment']:,.0f}", 100 * v["share_of_employment"],
                 v["wage_bill_usd"] / 1e9)
    return report


def run_external(settings: Settings, client) -> dict[str, Any]:
    """Benchmark the index against published exposure measures, incl. human ratings."""
    from .external import (
        BENCHMARK_COLUMNS,
        CITATION,
        correlate,
        fetch_benchmarks,
        join,
    )

    ours = read_table(settings.out_dir, "occupation_susceptibility")
    if not ours:
        raise SystemExit("no occupation_susceptibility - run the report stage first")

    benchmarks = fetch_benchmarks(client, settings)
    rows, coverage = join(ours, benchmarks)
    COLUMNS["external_benchmarks"] = BENCHMARK_COLUMNS
    write_csv(settings.out_dir / "external_benchmarks.csv", rows, BENCHMARK_COLUMNS)
    append_sqlite(settings.out_dir / "onet_stem.sqlite", {"external_benchmarks": rows})

    by_index = correlate(rows, "our_susceptibility")
    by_exposure = correlate(rows, "our_exposure")
    report = {"citation": CITATION, "coverage": coverage,
              "susceptibility_vs": by_index, "exposure_vs": by_exposure}
    (settings.out_dir / "external_validation.json").write_text(json.dumps(report, indent=2))

    log.info("-" * 74)
    log.info("matched %d of %d occupations against published measures",
             coverage["matched"], len(ours))
    log.info("%-22s %5s %8s %9s   %s", "measure", "n", "pearson", "spearman", "expectation")
    for c in by_index:
        log.info("%-22s %5d %8s %9s   %s", c["measure"], c["n"],
                 c["pearson"], c["spearman"], c["expectation"])
    human = [c for c in by_index if c["measure"].startswith("human") and c["pearson"]]
    if human:
        best = max(human, key=lambda c: c["pearson"])
        log.info("-" * 74)
        log.info("strongest agreement with HUMAN expert ratings: %s r=%.3f (n=%d)",
                 best["measure"], best["pearson"], best["n"])
        log.info("this is the external check - the rest of the pipeline is self-consistent "
                 "by construction, but this is not")
    return report


def run_figures(settings: Settings, *, chrome: str | None, dark: bool,
                scale: int, only: tuple[str, ...]) -> list[Path]:
    """Export each dashboard chart as a PNG."""
    from .figures import render

    dashboard = settings.out_dir / "dashboard.html"
    if not dashboard.exists():
        raise SystemExit("no dashboard.html - run the report stage first")
    out_dir = settings.out_dir / "figures"
    written = render(dashboard, out_dir, chrome=chrome, dark=dark, scale=scale, only=only)
    log.info("%d figure(s) in %s", len(written), out_dir)
    return written
