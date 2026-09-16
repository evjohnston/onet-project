"""Turn the fetched pages and crosswalks into a normalised, joinable dataset.

Grain of each output table is stated in TABLE_GRAIN and enforced by the writer, so
a silent fan-out in a join shows up as an error rather than as inflated counts.
"""

from __future__ import annotations

import csv
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Sequence

from .config import STEM_CATEGORIES, Settings
from .descriptors import (
    DESCRIPTOR_COLUMNS,
    DESCRIPTOR_TABLES,
    INDEX_COLUMNS,
    build_emerging_tasks,
    build_indices,
    build_related_occupations,
    normalise_descriptor,
)
from .network import (
    DWA_EDGE_COLUMNS,
    DWA_NODE_COLUMNS,
    OCC_EDGE_COLUMNS,
    OCC_NODE_COLUMNS,
)
from .score import OCC_SCORE_COLUMNS, SUBTASK_SCORE_COLUMNS, TASK_SCORE_COLUMNS

log = logging.getLogger(__name__)

TABLE_GRAIN: dict[str, tuple[str, ...]] = {
    "occupations": ("onet_soc_code",),
    "stem_categories": ("stem_category_id",),
    "occupation_stem_categories": ("onet_soc_code", "stem_category_id"),
    "tasks": ("onet_soc_code", "task_id"),
    "task_subtasks": ("onet_soc_code", "task_id", "dwa_id"),
    "occupation_subtasks": ("onet_soc_code", "dwa_id"),
    "subtask_hierarchy": ("dwa_id",),
    "task_ratings": ("onet_soc_code", "task_id", "scale_id", "category"),
    "tasks_wide": ("onet_soc_code", "task_id", "dwa_id"),
    "occupation_work_context": ("onet_soc_code", "element_id", "scale_id", "category"),
    "occupation_abilities": ("onet_soc_code", "element_id", "scale_id", "category"),
    "occupation_work_activities": ("onet_soc_code", "element_id", "scale_id", "category"),
    "occupation_essential_skills": ("onet_soc_code", "element_id", "scale_id", "category"),
    "occupation_indices": ("onet_soc_code",),
    "emerging_tasks": (),
    "related_occupations": ("onet_soc_code", "related_onet_soc_code"),
    "network_occupation_edges": ("source", "target"),
    "network_occupation_nodes": ("onet_soc_code",),
    "network_subtask_edges": ("source", "target"),
    "network_subtask_nodes": ("dwa_id",),
    "subtask_automation_scores": ("dwa_id",),
    "task_automation_scores": ("onet_soc_code", "task_id"),
    "occupation_automation_scores": ("onet_soc_code",),
}


class BuildError(RuntimeError):
    pass


# --------------------------------------------------------------------------- #
# helpers                                                                       #
# --------------------------------------------------------------------------- #
def _num(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _int(value: str | None) -> int | None:
    val = _num(value)
    return int(val) if val is not None else None


def write_csv(path: Path, rows: Sequence[dict[str, Any]], columns: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    log.info("wrote %-28s %6d rows", path.name, len(rows))


def _assert_grain(name: str, rows: Iterable[dict[str, Any]]) -> None:
    keys = TABLE_GRAIN.get(name)
    if not keys:
        return
    seen: set[tuple] = set()
    for row in rows:
        key = tuple(row.get(k) for k in keys)
        if key in seen:
            raise BuildError(f"{name}: duplicate row at grain {keys} -> {key}")
        seen.add(key)


# --------------------------------------------------------------------------- #
# table builders                                                                #
# --------------------------------------------------------------------------- #
def build_occupations(
    index_rows: Sequence[dict[str, Any]],
    occupation_records: Sequence[dict[str, Any]],
    bulk: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    by_code = {r["onet_soc_code"]: r for r in occupation_records}
    bulk_desc = {}
    if bulk:
        for row in bulk["tables"].get("occupation_data.csv", []):
            bulk_desc[row["O*NET-SOC Code"]] = row["Description"]

    rows = []
    for entry in index_rows:
        code = entry["onet_soc_code"]
        detail = by_code.get(code, {})
        counts = detail.get("counts", {})
        rows.append(
            {
                "onet_soc_code": code,
                "title": detail.get("title") or entry["title"],
                "description": detail.get("description") or bulk_desc.get(code, ""),
                "stem_occupation_types": entry.get("occupation_types", ""),
                "bright_outlook": int(bool(entry.get("bright_outlook") or detail.get("bright_outlook"))),
                "job_zone": detail.get("job_zone"),
                "updated_year": detail.get("updated_year"),
                "reported_job_titles": "; ".join(detail.get("reported_job_titles", [])),
                "n_tasks": counts.get("tasks_parsed", 0),
                "n_subtasks": counts.get("dwas_parsed", 0),
                "detail_fetched": int(bool(detail)),
                "source_url": detail.get("source_url", ""),
                "fetched_at": detail.get("fetched_at", ""),
            }
        )
    return sorted(rows, key=lambda r: r["onet_soc_code"])


def build_stem_category_tables(
    memberships: Sequence[Sequence[str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    categories = [
        {
            "stem_category_id": cid,
            "stem_category_name": name,
            "parent_category_id": parent or "",
            "parent_category_name": STEM_CATEGORIES[parent][0] if parent else "",
            "is_leaf": int(parent is not None),
        }
        for cid, (name, parent) in STEM_CATEGORIES.items()
        if cid != "0"
    ]
    links = [
        {
            "onet_soc_code": code,
            "stem_category_id": cid,
            "stem_category_name": STEM_CATEGORIES[cid][0],
            "parent_category_name": (
                STEM_CATEGORIES[STEM_CATEGORIES[cid][1]][0] if STEM_CATEGORIES[cid][1] else ""
            ),
        }
        for code, cid in memberships
    ]
    return categories, sorted(links, key=lambda r: (r["onet_soc_code"], r["stem_category_id"]))


def build_tasks(occupation_records: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for record in occupation_records:
        code = record["onet_soc_code"]
        for task in record.get("tasks", []):
            rows.append(
                {
                    "onet_soc_code": code,
                    "occupation_title": record.get("title", ""),
                    "task_id": task["task_id"],
                    "task": task["task"],
                    "task_category": task.get("task_category"),
                    "importance": task.get("importance"),
                    "relevance": task.get("relevance"),
                    "display_rank": task.get("display_rank"),
                }
            )
    return sorted(rows, key=lambda r: (r["onet_soc_code"], -(r["importance"] or 0), r["task"]))


def build_occupation_subtasks(occupation_records: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for record in occupation_records:
        for dwa in record.get("dwas", []):
            rows.append(
                {
                    "onet_soc_code": record["onet_soc_code"],
                    "occupation_title": record.get("title", ""),
                    "dwa_id": dwa["dwa_id"],
                    "dwa_title": dwa["dwa_title"],
                    "display_rank": dwa.get("display_rank"),
                }
            )
    return sorted(rows, key=lambda r: (r["onet_soc_code"], r["dwa_id"] or ""))


def build_subtask_hierarchy(bulk: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in bulk["tables"].get("gwas_to_iwas_to_dwas.csv", []):
        rows.append(
            {
                "dwa_id": row["DWA Element ID"],
                "dwa_title": row["DWA Element Name"],
                "iwa_id": row["IWA Element ID"],
                "iwa_title": row["IWA Element Name"],
                "gwa_id": row["GWA Element ID"],
                "gwa_title": row["GWA Element Name"],
            }
        )
    return sorted(rows, key=lambda r: r["dwa_id"])


def build_task_subtasks(
    bulk: dict[str, Any],
    stem_codes: set[str],
    known_tasks: set[tuple[str, int]],
) -> list[dict[str, Any]]:
    """The task -> detailed-work-activity edge, restricted to STEM occupations."""
    rows = []
    for row in bulk["tables"].get("tasks_to_dwas.csv", []):
        code = row["O*NET-SOC Code"]
        if code not in stem_codes:
            continue
        task_id = _int(row["Task ID"])
        rows.append(
            {
                "onet_soc_code": code,
                "occupation_title": row.get("Title", ""),
                "task_id": task_id,
                "task": row["Task"],
                "dwa_id": row["DWA Element ID"],
                "dwa_title": row["DWA Element Name"],
                "linked_on_web_report": int((code, task_id) in known_tasks),
                "mapping_date": row.get("Date", ""),
                "mapping_source": row.get("Domain Source", ""),
            }
        )
    return sorted(rows, key=lambda r: (r["onet_soc_code"], r["task_id"] or 0, r["dwa_id"]))


def build_task_ratings(bulk: dict[str, Any], stem_codes: set[str]) -> list[dict[str, Any]]:
    rows = []
    for row in bulk["tables"].get("task_ratings.csv", []):
        if row["O*NET-SOC Code"] not in stem_codes:
            continue
        rows.append(
            {
                "onet_soc_code": row["O*NET-SOC Code"],
                "task_id": _int(row["Task ID"]),
                "scale_id": row["Scale ID"],
                "scale_name": row.get("Scale Name", ""),
                "category": row.get("Category", ""),
                "data_value": _num(row.get("Data Value")),
                "n": _int(row.get("N")),
                "standard_error": _num(row.get("Standard Error")),
                "recommend_suppress": row.get("Recommend Suppress", ""),
                "date": row.get("Date", ""),
                "domain_source": row.get("Domain Source", ""),
            }
        )
    return sorted(rows, key=lambda r: (r["onet_soc_code"], r["task_id"] or 0, r["scale_id"], r["category"]))


def build_tasks_wide(
    occupations: Sequence[dict[str, Any]],
    tasks: Sequence[dict[str, Any]],
    task_subtasks: Sequence[dict[str, Any]],
    hierarchy: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """One row per (occupation, task, subtask); tasks with no subtask keep one row."""
    occ_by_code = {o["onet_soc_code"]: o for o in occupations}
    hier_by_dwa = {h["dwa_id"]: h for h in hierarchy}

    links: dict[tuple[str, int | None], list[dict[str, Any]]] = {}
    for link in task_subtasks:
        links.setdefault((link["onet_soc_code"], link["task_id"]), []).append(link)

    rows = []
    for task in tasks:
        occ = occ_by_code.get(task["onet_soc_code"], {})
        base = {
            "onet_soc_code": task["onet_soc_code"],
            "occupation_title": task["occupation_title"],
            "stem_occupation_types": occ.get("stem_occupation_types", ""),
            "job_zone": occ.get("job_zone"),
            "bright_outlook": occ.get("bright_outlook"),
            "task_id": task["task_id"],
            "task": task["task"],
            "task_category": task["task_category"],
            "importance": task["importance"],
            "task_rank_in_occupation": task["display_rank"],
        }
        matches = links.get((task["onet_soc_code"], task["task_id"]), [])
        if not matches:
            rows.append({**base, "dwa_id": "", "dwa_title": "", "iwa_id": "",
                         "iwa_title": "", "gwa_id": "", "gwa_title": ""})
            continue
        for link in matches:
            hier = hier_by_dwa.get(link["dwa_id"], {})
            rows.append(
                {
                    **base,
                    "dwa_id": link["dwa_id"],
                    "dwa_title": link["dwa_title"],
                    "iwa_id": hier.get("iwa_id", ""),
                    "iwa_title": hier.get("iwa_title", ""),
                    "gwa_id": hier.get("gwa_id", ""),
                    "gwa_title": hier.get("gwa_title", ""),
                }
            )
    return sorted(rows, key=lambda r: (r["onet_soc_code"], -(r["importance"] or 0),
                                       r["task"], r["dwa_id"]))


# --------------------------------------------------------------------------- #
# orchestration                                                                 #
# --------------------------------------------------------------------------- #
COLUMNS: dict[str, tuple[str, ...]] = {
    "occupations": ("onet_soc_code", "title", "description", "stem_occupation_types",
                    "bright_outlook", "job_zone", "updated_year", "reported_job_titles",
                    "n_tasks", "n_subtasks", "detail_fetched", "source_url", "fetched_at"),
    "stem_categories": ("stem_category_id", "stem_category_name", "parent_category_id",
                        "parent_category_name", "is_leaf"),
    "occupation_stem_categories": ("onet_soc_code", "stem_category_id",
                                   "stem_category_name", "parent_category_name"),
    "tasks": ("onet_soc_code", "occupation_title", "task_id", "task", "task_category",
              "importance", "relevance", "display_rank"),
    "task_subtasks": ("onet_soc_code", "occupation_title", "task_id", "task", "dwa_id",
                      "dwa_title", "linked_on_web_report", "mapping_date", "mapping_source"),
    "occupation_subtasks": ("onet_soc_code", "occupation_title", "dwa_id", "dwa_title",
                            "display_rank"),
    "subtask_hierarchy": ("dwa_id", "dwa_title", "iwa_id", "iwa_title", "gwa_id", "gwa_title"),
    "task_ratings": ("onet_soc_code", "task_id", "scale_id", "scale_name", "category",
                     "data_value", "n", "standard_error", "recommend_suppress", "date",
                     "domain_source"),
    "tasks_wide": ("onet_soc_code", "occupation_title", "stem_occupation_types", "job_zone",
                   "bright_outlook", "task_id", "task", "task_category", "importance",
                   "task_rank_in_occupation", "dwa_id", "dwa_title", "iwa_id", "iwa_title",
                   "gwa_id", "gwa_title"),
    "occupation_work_context": DESCRIPTOR_COLUMNS,
    "occupation_abilities": DESCRIPTOR_COLUMNS,
    "occupation_work_activities": DESCRIPTOR_COLUMNS,
    "occupation_essential_skills": DESCRIPTOR_COLUMNS,
    "occupation_indices": INDEX_COLUMNS,
    "emerging_tasks": ("onet_soc_code", "task", "category", "original_task_id",
                       "original_task", "date", "domain_source"),
    "related_occupations": ("onet_soc_code", "related_onet_soc_code", "related_title",
                            "relatedness_tier", "rank", "related_is_stem"),
    "network_occupation_edges": OCC_EDGE_COLUMNS,
    "network_occupation_nodes": OCC_NODE_COLUMNS,
    "network_subtask_edges": DWA_EDGE_COLUMNS,
    "network_subtask_nodes": DWA_NODE_COLUMNS,
    "subtask_automation_scores": SUBTASK_SCORE_COLUMNS,
    "task_automation_scores": TASK_SCORE_COLUMNS,
    "occupation_automation_scores": OCC_SCORE_COLUMNS,
}


def build_all(
    settings: Settings,
    index: dict[str, Any],
    occupation_records: Sequence[dict[str, Any]],
    bulk: dict[str, Any] | None,
    augment: dict[str, Any] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    stem_codes = {r["onet_soc_code"] for r in index["occupations"]}

    occupations = build_occupations(index["occupations"], occupation_records, bulk)
    categories, links = build_stem_category_tables(index["memberships"])
    tasks = build_tasks(occupation_records)
    occupation_subtasks = build_occupation_subtasks(occupation_records)

    known_tasks = {(t["onet_soc_code"], t["task_id"]) for t in tasks}
    if bulk:
        hierarchy = build_subtask_hierarchy(bulk)
        task_subtasks = build_task_subtasks(bulk, stem_codes, known_tasks)
        task_ratings = build_task_ratings(bulk, stem_codes)
    else:
        # Without the crosswalk we can still emit the occupation-level subtask link.
        log.warning("bulk crosswalk disabled: task -> subtask edges will be empty")
        hierarchy, task_subtasks, task_ratings = [], [], []

    tables = {
        "occupations": occupations,
        "stem_categories": categories,
        "occupation_stem_categories": links,
        "tasks": tasks,
        "task_subtasks": task_subtasks,
        "occupation_subtasks": occupation_subtasks,
        "subtask_hierarchy": hierarchy,
        "tasks_wide": build_tasks_wide(occupations, tasks, task_subtasks, hierarchy),
    }
    if task_ratings:
        tables["task_ratings"] = task_ratings

    if augment:
        tables.update(build_augment_tables(augment, stem_codes, occupations))

    for name, rows in tables.items():
        _assert_grain(name, rows)
        write_csv(settings.out_dir / f"{name}.csv", rows, COLUMNS[name])

    write_sqlite(settings.out_dir / "onet_stem.sqlite", tables)
    write_json_bundle(settings.out_dir / "occupations.json", occupations, tasks,
                      task_subtasks, occupation_subtasks)
    return tables


def write_sqlite(path: Path, tables: dict[str, list[dict[str, Any]]]) -> None:
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    try:
        for name, rows in tables.items():
            columns = COLUMNS[name]
            quoted = ", ".join('"' + c + '"' for c in columns)
            conn.execute("CREATE TABLE " + name + " (" + quoted + ")")
            conn.executemany(
                f"INSERT INTO {name} VALUES ({', '.join('?' for _ in columns)})",
                [tuple(row.get(c) for c in columns) for row in rows],
            )
        for stmt in (
            "CREATE INDEX idx_tasks_code ON tasks(onet_soc_code)",
            "CREATE INDEX idx_tasks_id ON tasks(task_id)",
            "CREATE INDEX idx_ts_task ON task_subtasks(task_id)",
            "CREATE INDEX idx_ts_dwa ON task_subtasks(dwa_id)",
            "CREATE INDEX idx_wide_code ON tasks_wide(onet_soc_code)",
        ):
            conn.execute(stmt)
        conn.commit()
    finally:
        conn.close()
    log.info("wrote %-28s %s", path.name, f"{len(tables)} tables")


def write_json_bundle(path: Path, occupations, tasks, task_subtasks, occupation_subtasks) -> None:
    """Nested job -> task -> subtask view, for consumers that prefer documents."""
    subtasks_by_task: dict[tuple[str, int | None], list[dict[str, str]]] = {}
    for link in task_subtasks:
        subtasks_by_task.setdefault((link["onet_soc_code"], link["task_id"]), []).append(
            {"dwa_id": link["dwa_id"], "dwa_title": link["dwa_title"]}
        )
    tasks_by_code: dict[str, list[dict[str, Any]]] = {}
    for task in tasks:
        tasks_by_code.setdefault(task["onet_soc_code"], []).append(
            {
                "task_id": task["task_id"],
                "task": task["task"],
                "task_category": task["task_category"],
                "importance": task["importance"],
                "subtasks": subtasks_by_task.get((task["onet_soc_code"], task["task_id"]), []),
            }
        )
    occ_subtasks: dict[str, list[dict[str, str]]] = {}
    for link in occupation_subtasks:
        occ_subtasks.setdefault(link["onet_soc_code"], []).append(
            {"dwa_id": link["dwa_id"], "dwa_title": link["dwa_title"]}
        )

    payload = [
        {
            **{k: occ[k] for k in ("onet_soc_code", "title", "description",
                                   "stem_occupation_types", "job_zone", "bright_outlook")},
            "tasks": tasks_by_code.get(occ["onet_soc_code"], []),
            "occupation_subtasks": occ_subtasks.get(occ["onet_soc_code"], []),
        }
        for occ in occupations
    ]
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    log.info("wrote %-28s %6d occupations", path.name, len(payload))


def build_augment_tables(
    augment: dict[str, Any],
    stem_codes: set[str],
    occupations: Sequence[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Descriptor measures plus the composite collaboration / bottleneck indices."""
    source = augment["tables"]
    out: dict[str, list[dict[str, Any]]] = {}

    normalised: dict[str, list[dict[str, Any]]] = {}
    for filename, table in DESCRIPTOR_TABLES.items():
        rows = source.get(filename)
        if rows is None:
            continue
        normalised[filename] = normalise_descriptor(rows, stem_codes)
        out[table] = normalised[filename]

    if "emerging_tasks.csv" in source:
        out["emerging_tasks"] = build_emerging_tasks(source["emerging_tasks.csv"], stem_codes)
    if "related_occupations.csv" in source:
        out["related_occupations"] = build_related_occupations(
            source["related_occupations.csv"], stem_codes)

    indices, missing = build_indices(normalised, occupations)
    out["occupation_indices"] = indices
    if missing:
        log.warning("%d index element(s) not found in O*NET: %s", len(missing), missing)
    return out


def read_table(out_dir: Path, name: str) -> list[dict[str, Any]]:
    """Read a previously built CSV back, restoring numeric types."""
    path = out_dir / f"{name}.csv"
    if not path.exists():
        return []
    numeric = {"importance", "relevance", "data_value", "cosine", "jaccard",
               "weighted_cosine", "mean_similarity", "weighted_degree"}
    integer = {"task_id", "job_zone", "n_tasks", "n_subtasks", "display_rank",
               "bright_outlook", "degree", "shared_subtasks", "n_occupations",
               "co_occurring_occupations", "linked_on_web_report", "related_is_stem",
               "same_soc_major_group", "updated_year", "detail_fetched", "rank"}
    rows = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            for key, value in list(row.items()):
                if value == "":
                    row[key] = None
                elif key in numeric:
                    row[key] = _num(value)
                elif key in integer:
                    row[key] = _int(value)
            rows.append(row)
    return rows


def append_sqlite(path: Path, tables: dict[str, list[dict[str, Any]]]) -> None:
    """Add or replace tables in an existing database without rebuilding it."""
    conn = sqlite3.connect(path)
    try:
        for name, rows in tables.items():
            columns = COLUMNS[name]
            quoted = ", ".join('"' + c + '"' for c in columns)
            conn.execute(f"DROP TABLE IF EXISTS {name}")
            conn.execute("CREATE TABLE " + name + " (" + quoted + ")")
            conn.executemany(
                f"INSERT INTO {name} VALUES ({', '.join('?' for _ in columns)})",
                [tuple(row.get(c) for c in columns) for row in rows],
            )
        conn.commit()
    finally:
        conn.close()
    log.info("updated %-27s %d tables", path.name, len(tables))
