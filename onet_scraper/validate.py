"""Post-build quality checks.

Each check returns a severity. ``error`` means the dataset is wrong and the run
exits non-zero; ``warn`` means something worth eyeballing (O*NET genuinely has
occupations with no mapped activities, for instance).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Sequence

log = logging.getLogger(__name__)


def _check(name: str, severity: str, ok: bool, detail: str, sample: Any = None) -> dict[str, Any]:
    return {
        "check": name,
        "severity": severity if not ok else "ok",
        "passed": ok,
        "detail": detail,
        "sample": sample if not ok else None,
    }


def validate(
    tables: dict[str, list[dict[str, Any]]],
    index: dict[str, Any],
    occupation_records: Sequence[dict[str, Any]],
    failures: Sequence[dict[str, str]],
    out_dir: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    occupations = tables["occupations"]
    tasks = tables["tasks"]
    task_subtasks = tables["task_subtasks"]
    hierarchy = tables["subtask_hierarchy"]
    wide = tables["tasks_wide"]

    # 1. Every rostered occupation actually got a detail page.
    missing = [o["onet_soc_code"] for o in occupations if not o["detail_fetched"]]
    checks.append(_check("all_occupations_fetched", "error", not missing,
                         f"{len(missing)} of {len(occupations)} occupations missing a detail page",
                         missing[:10]))

    # 2. No fetch/parse failures were swallowed.
    checks.append(_check("no_fetch_failures", "error", not failures,
                         f"{len(failures)} occupations failed to fetch or parse",
                         list(failures)[:10]))

    # 3. Row counts agree with the count O*NET prints on each page.
    mismatches = []
    for record in occupation_records:
        counts = record.get("counts", {})
        for kind in ("tasks", "dwas"):
            declared = counts.get(f"{kind}_declared")
            parsed = counts.get(f"{kind}_parsed")
            if declared is not None and declared != parsed:
                mismatches.append(
                    {"onet_soc_code": record["onet_soc_code"], "kind": kind,
                     "declared": declared, "parsed": parsed}
                )
    checks.append(_check("parsed_matches_page_count", "error", not mismatches,
                         f"{len(mismatches)} sections where parsed rows != the page's own count",
                         mismatches[:10]))

    # 4. Task identifiers are present; they are the join key to the subtask crosswalk.
    no_id = [t for t in tasks if t["task_id"] is None]
    checks.append(_check("tasks_have_ids", "error", not no_id,
                         f"{len(no_id)} tasks scraped without an O*NET task id",
                         [t["task"][:80] for t in no_id[:5]]))

    # 5. Crosswalk task ids resolve to scraped tasks.
    known = {(t["onet_soc_code"], t["task_id"]) for t in tasks}
    orphans = [l for l in task_subtasks if (l["onet_soc_code"], l["task_id"]) not in known]
    checks.append(_check("subtask_links_resolve", "warn", not orphans,
                         f"{len(orphans)} task->subtask links reference a task not on the live page "
                         "(normal when the bulk release lags the website)",
                         [{k: l[k] for k in ('onet_soc_code', 'task_id')} for l in orphans[:10]]))

    # 6. Every subtask id has a place in the activity hierarchy.
    hierarchy_ids = {h["dwa_id"] for h in hierarchy}
    unmapped = sorted({l["dwa_id"] for l in task_subtasks if l["dwa_id"] not in hierarchy_ids})
    checks.append(_check("subtasks_in_hierarchy", "warn", not unmapped,
                         f"{len(unmapped)} subtask ids absent from the GWA/IWA/DWA hierarchy",
                         unmapped[:10]))

    # 7. Occupations with no tasks at all. SOC "All Other" residual categories
    #    legitimately carry no task data anywhere in O*NET, so they are counted
    #    separately rather than treated as a problem.
    empty = [o for o in occupations if o["detail_fetched"] and o["n_tasks"] == 0]
    residual = [o["onet_soc_code"] for o in empty if "All Other" in o["title"]]
    unexpected = [o["onet_soc_code"] for o in empty if "All Other" not in o["title"]]
    checks.append(_check("occupations_have_tasks", "warn", not unexpected,
                         f"{len(unexpected)} occupations unexpectedly report zero tasks "
                         f"({len(residual)} SOC 'All Other' residual categories excluded, "
                         "which have no task data by design)",
                         unexpected[:10]))

    # 8. Task coverage of the subtask crosswalk.
    linked = {(l["onet_soc_code"], l["task_id"]) for l in task_subtasks}
    unlinked = sorted(known - linked)
    coverage = 1 - len(unlinked) / len(known) if known else 0.0
    checks.append(_check("task_subtask_coverage", "warn", coverage >= 0.90,
                         f"{coverage:.1%} of tasks have at least one subtask "
                         f"({len(unlinked)} unlinked - typically tasks added to the site "
                         "since the last bulk database release)",
                         [{'onet_soc_code': c, 'task_id': t} for c, t in unlinked[:10]]))

    # 8b. Ratings must sit on the published 0-100 scale; anything outside it is a
    #     sentinel that leaked through the parser.
    out_of_range = [
        {"onet_soc_code": t["onet_soc_code"], "task_id": t["task_id"],
         "importance": t["importance"]}
        for t in tasks
        if t["importance"] not in (None, "") and not 0 <= float(t["importance"]) <= 100
    ]
    checks.append(_check("importance_in_range", "error", not out_of_range,
                         f"{len(out_of_range)} tasks have an importance outside 0-100",
                         out_of_range[:10]))

    # 9. The wide table must not drop or duplicate any task.
    wide_tasks = {(r["onet_soc_code"], r["task_id"]) for r in wide}
    checks.append(_check("wide_table_covers_tasks", "error", wide_tasks == known,
                         f"wide table covers {len(wide_tasks)} of {len(known)} tasks",
                         sorted(known - wide_tasks)[:10]))

    # 10. STEM roster size sanity: the union page must equal the sum of the parts.
    union = {o["onet_soc_code"] for o in index["occupations"]}
    from_links = {row["onet_soc_code"] for row in tables["occupation_stem_categories"]}
    only_union = sorted(union - from_links)
    checks.append(_check("category_membership_complete", "warn", not only_union,
                         f"{len(only_union)} occupations on the 'All STEM' page appear in no "
                         "individual STEM category",
                         only_union[:10]))

    summary = {
        "occupations": len(occupations),
        "occupations_without_tasks": len(empty),
        "residual_all_other_occupations": len(residual),
        "tasks": len(tasks),
        "task_subtask_links": len(task_subtasks),
        "occupation_subtask_links": len(tables["occupation_subtasks"]),
        "distinct_subtasks": len({l["dwa_id"] for l in task_subtasks}),
        "wide_rows": len(wide),
        "mean_tasks_per_occupation": round(len(tasks) / len(occupations), 2) if occupations else 0,
        "task_subtask_coverage": round(coverage, 4),
        "errors": sum(1 for c in checks if c["severity"] == "error"),
        "warnings": sum(1 for c in checks if c["severity"] == "warn"),
    }

    report = {"summary": summary, "checks": checks}
    (out_dir / "validation_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    return checks, summary


def log_report(checks: Sequence[dict[str, Any]], summary: dict[str, Any]) -> int:
    log.info("-" * 68)
    for check in checks:
        marker = {"ok": "PASS", "warn": "WARN", "error": "FAIL"}[check["severity"]]
        log.info("%-5s %-32s %s", marker, check["check"], check["detail"])
    log.info("-" * 68)
    for key, value in summary.items():
        log.info("%-32s %s", key, value)
    return summary["errors"]
