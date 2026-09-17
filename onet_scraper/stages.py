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


def run_scroller(settings: Settings) -> Path:
    """Render the scroll-driven narrative from the built tables."""
    from .scroller import build_payload, build_scroller

    occ = read_table(settings.out_dir, "occupation_susceptibility")
    handoff = read_table(settings.out_dir, "occupation_handoff")
    benchmarks = read_table(settings.out_dir, "external_benchmarks")
    soc = read_table(settings.out_dir, "soc_susceptibility")
    if not (occ and handoff):
        raise SystemExit("run the report stage first (and score before that)")
    for name, table in (("external_benchmarks", benchmarks), ("soc_susceptibility", soc)):
        if not table:
            log.warning("%s missing - that chapter will be thin", name)

    emp_path = settings.out_dir / "employment_report.json"
    emp = json.loads(emp_path.read_text()) if emp_path.exists() else {}
    score_path = settings.out_dir / "scoring_report.json"
    meta = json.loads(score_path.read_text()) if score_path.exists() else {}

    tasks = read_table(settings.out_dir, "task_susceptibility")
    subtasks = read_table(settings.out_dir, "subtask_susceptibility")
    links = read_table(settings.out_dir, "task_subtasks")
    pw_path = settings.out_dir / "pathways_report.json"
    pathways = json.loads(pw_path.read_text()) if pw_path.exists() else {}
    if pathways:
        pathways["deciles"] = read_table(settings.out_dir, "wage_deciles")
        moves = read_table(settings.out_dir, "transitions")
        stranded = read_table(settings.out_dir, "stranded_occupations")
        # a handful of each, biggest first, for the figure
        pathways["moveSample"] = [
            {"t": m["title"][:28], "d": m["destination"][:28],
             "s": float(m["susceptibility"]), "ds": float(m["destination_susceptibility"]),
             "v": m["verdict"]}
            for m in moves[:6]]
        pathways["strandedSample"] = [
            {"t": r["title"][:28], "s": float(r["susceptibility"])}
            for r in stranded[:6]]
    ch_path = settings.out_dir / "churn_report.json"
    churn = json.loads(ch_path.read_text()) if ch_path.exists() else {}
    if churn:
        churn["steps"] = read_table(settings.out_dir, "task_churn_steps")
        rows = [r for r in read_table(settings.out_dir, "task_churn_occupations")
                if r.get("susceptibility") and r.get("last_reviewed")
                and int(r["last_reviewed"]) >= churn.get("review_cutoff", 2022)
                and int(r["tasks_first"]) >= 8]
        churn["byExposure"] = []
        for label, lo, hi in (("Highly exposed", 65, 200), ("Middling", 55, 65),
                              ("Low exposure", 0, 55)):
            g = [r for r in rows if lo <= float(r["susceptibility"]) < hi]
            if g:
                churn["byExposure"].append({
                    "label": label, "n": len(g),
                    "turnover": round(sum(float(r["turnover_rate"]) for r in g)/len(g), 4)})
    payload = build_payload(occ, tasks, subtasks, links, handoff, benchmarks, soc, emp,
                            pathways, churn)
    return build_scroller(settings.out_dir / "story.html", payload, meta)


def run_churn(settings: Settings, client, releases: tuple[str, ...] = ()) -> dict[str, Any]:
    """Diff task statements across archived O*NET releases."""
    from .churn import CHURN_COLUMNS, DEFAULT_RELEASES, OCC_CHURN_COLUMNS, build

    occ = read_table(settings.out_dir, "occupation_susceptibility")
    if not occ:
        raise SystemExit("run the report stage first")
    titles = {o["onet_soc_code"]: o["title"] for o in occ}
    susc = {o["onet_soc_code"]: float(o["susceptibility"]) for o in occ}

    steps, occ_rows, summary = build(
        client, releases or DEFAULT_RELEASES, titles.keys(), titles, susc)

    COLUMNS["task_churn_steps"] = CHURN_COLUMNS
    COLUMNS["task_churn_occupations"] = OCC_CHURN_COLUMNS
    tables = {"task_churn_steps": steps, "task_churn_occupations": occ_rows}
    for name, rows in tables.items():
        write_csv(settings.out_dir / f"{name}.csv", rows, COLUMNS[name])
    append_sqlite(settings.out_dir / "onet_stem.sqlite", tables)
    (settings.out_dir / "churn_report.json").write_text(json.dumps(summary, indent=2))

    log.info("-" * 70)
    log.info("task churn %s (%s)", summary["span"], summary["years"])
    log.info("  %d occupations compared, %d skipped on taxonomy change",
             summary["occupations_compared"], summary["occupations_skipped"])
    log.info("  %d tasks -> %d tasks  (%d added, %d retired, %d survived)",
             summary["tasks_start"], summary["tasks_end"],
             summary["added"], summary["retired"], summary["survived"])
    log.info("  turnover %.1f%% · %.1f%% of today's tasks did not exist at the start",
             100*summary["turnover_rate"], 100*summary["added_rate"])
    f, st = summary["refreshed_only"], summary["stale_only"]
    log.info("  split on whether O*NET re-surveyed the occupation since %d:",
             summary["review_cutoff"])
    log.info("    re-surveyed    %3d occupations - turnover %.1f%%, %.1f%% of tasks new",
             summary["reviewed_since_cutoff"], 100*f["turnover_rate"], 100*f["added_rate"])
    log.info("    never looked at %3d occupations - turnover %.1f%%, %.1f%% new",
             summary["not_reviewed_since_cutoff"], 100*st["turnover_rate"],
             100*st["added_rate"])
    log.info("  the overall figure is diluted by occupations nobody checked")
    return summary


def run_pathways(settings: Settings) -> dict[str, Any]:
    """Wage protection analysis and the transition map. Both run on local tables."""
    from .transitions import (
        STRANDED_COLUMNS,
        TRANSITION_COLUMNS,
        build as build_moves,
        sweep,
    )
    from .wages import DECILE_COLUMNS, WAGE_COLUMNS, build as build_wages

    occ = read_table(settings.out_dir, "occupation_susceptibility")
    soc = read_table(settings.out_dir, "soc_susceptibility")
    edges = read_table(settings.out_dir, "network_occupation_edges")
    links = read_table(settings.out_dir, "task_subtasks")
    subs = read_table(settings.out_dir, "subtask_susceptibility")
    if not (occ and edges and links):
        raise SystemExit("run report and network first")

    tables: dict[str, list[dict[str, Any]]] = {}
    report: dict[str, Any] = {}

    # --- 1. what protects well-paid work ---------------------------------
    if soc:
        w = build_wages(soc)
        if w.get("available"):
            COLUMNS["wage_deciles"] = DECILE_COLUMNS
            COLUMNS["wage_protection"] = WAGE_COLUMNS
            tables["wage_deciles"] = w["deciles"]
            tables["wage_protection"] = w["detail"]
            report["wages"] = w["summary"]
            s = w["summary"]
            log.info("-" * 70)
            log.info("wage vs exposure r=%s · vs anchoring r=%s · vs susceptibility r=%s",
                     s["wage_vs_exposure"], s["wage_vs_anchoring"],
                     s["wage_vs_susceptibility"])
            log.info("susceptibility, bottom wage decile %s → top %s",
                     s["decile_1_susceptibility"], s["decile_10_susceptibility"])
            for k, v in sorted(s["by_protection"].items(),
                               key=lambda kv: -kv[1]["workers"]):
                log.info("  %-44s %2d occs · %5.1f%% of workers",
                         k, v["occupations"], 100*v["share_of_workers"])
    else:
        log.warning("no soc_susceptibility - run the employment stage for the wage half")

    # --- 2. where the people could go ------------------------------------
    occ_dwa: dict[str, set[str]] = {}
    for l in links:
        if l.get("dwa_id"):
            occ_dwa.setdefault(l["onet_soc_code"], set()).add(l["dwa_id"])
    dwa_susc = {s["dwa_id"]: float(s["susceptibility"]) for s in subs}
    employment: dict[str, float] = {}
    for r in soc:
        if r.get("total_employment"):
            for c in (r.get("onet_codes") or "").split(";"):
                if c:
                    employment[c] = float(r["total_employment"])

    moves, stranded, msum = build_moves(edges, occ, occ_dwa, dwa_susc, employment)
    COLUMNS["transitions"] = TRANSITION_COLUMNS
    COLUMNS["stranded_occupations"] = STRANDED_COLUMNS
    tables["transitions"] = moves
    tables["stranded_occupations"] = stranded
    msum["sensitivity"] = sweep(edges, occ, occ_dwa, dwa_susc, employment)
    report["transitions"] = msum

    log.info("-" * 70)
    log.info("%d of %d occupations have a plausible less-exposed destination; "
             "%d are stranded (%.0f%%)", msum["with_a_destination"], msum["occupations"],
             msum["stranded"], 100*msum["stranded_share"])
    log.info("  of the moves that exist, %d are real and %d carry the exposure along",
             msum["real_moves"], msum["carries_exposure"])
    log.info("  %d exposed occupations are stranded (%s workers)",
             msum["exposed_and_stranded"],
             f"{msum['exposed_and_stranded_workers']:,}")
    log.info("  sensitivity: stranded ranges %d-%d across the threshold sweep",
             min(s["stranded"] for s in msum["sensitivity"]),
             max(s["stranded"] for s in msum["sensitivity"]))

    for name, rows in tables.items():
        write_csv(settings.out_dir / f"{name}.csv", rows, COLUMNS[name])
    append_sqlite(settings.out_dir / "onet_stem.sqlite", tables)
    (settings.out_dir / "pathways_report.json").write_text(json.dumps(report, indent=2))
    return report
