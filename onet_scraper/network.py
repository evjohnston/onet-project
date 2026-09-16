"""Occupation and subtask networks from the task -> subtask edge.

The base object is a bipartite graph of occupations and detailed work activities.
Projecting it one way gives "which jobs do similar work"; the other way gives
"which activities co-occur". Both are written as edge lists and GraphML.

Two things this does NOT claim: an edge is *similarity of work*, not evidence
that two occupations interact; and the subtask vocabulary is analyst-assigned,
so the structure partly reflects O*NET's coding choices.
"""

from __future__ import annotations

import collections
import itertools
import logging
import math
from pathlib import Path
from typing import Any, Iterable, Sequence
from xml.sax.saxutils import escape

log = logging.getLogger(__name__)

OCC_EDGE_COLUMNS = ("source", "target", "source_title", "target_title",
                    "shared_subtasks", "cosine", "jaccard", "weighted_cosine",
                    "same_soc_major_group")
OCC_NODE_COLUMNS = ("onet_soc_code", "title", "stem_occupation_types", "job_zone",
                    "bright_outlook", "n_tasks", "n_subtasks", "degree",
                    "weighted_degree", "mean_similarity")
DWA_EDGE_COLUMNS = ("source", "target", "source_title", "target_title",
                    "co_occurring_occupations", "cosine")
DWA_NODE_COLUMNS = ("dwa_id", "dwa_title", "iwa_title", "gwa_title",
                    "n_occupations", "n_tasks", "degree")


def _cosine(a: set[str], b: set[str]) -> float:
    inter = len(a & b)
    return inter / math.sqrt(len(a) * len(b)) if inter else 0.0


def _jaccard(a: set[str], b: set[str]) -> float:
    union = len(a | b)
    return len(a & b) / union if union else 0.0


def build_incidence(
    task_subtasks: Sequence[dict[str, Any]],
    tasks: Sequence[dict[str, Any]],
    exclude_soc: Sequence[str] = (),
) -> tuple[dict[str, set[str]], dict[str, dict[str, float]], dict[str, set[str]]]:
    """occupation -> subtasks, occupation -> subtask importance weights, subtask -> occupations."""
    importance = {
        (t["onet_soc_code"], t["task_id"]): float(t["importance"])
        for t in tasks
        if t.get("importance") not in (None, "")
    }
    occ_dwa: dict[str, set[str]] = collections.defaultdict(set)
    weights: dict[str, dict[str, float]] = collections.defaultdict(dict)
    dwa_occ: dict[str, set[str]] = collections.defaultdict(set)

    for link in task_subtasks:
        code, dwa = link["onet_soc_code"], link["dwa_id"]
        if not dwa or any(code.startswith(p) for p in exclude_soc):
            continue
        occ_dwa[code].add(dwa)
        dwa_occ[dwa].add(code)
        # A subtask inherits the importance of the most important task feeding it.
        score = importance.get((code, link["task_id"]))
        if score is not None:
            weights[code][dwa] = max(weights[code].get(dwa, 0.0), score)

    return dict(occ_dwa), dict(weights), dict(dwa_occ)


def occupation_edges(
    occ_dwa: dict[str, set[str]],
    weights: dict[str, dict[str, float]],
    occupations: dict[str, dict[str, Any]],
    min_shared: int = 3,
) -> list[dict[str, Any]]:
    edges = []
    for a, b in itertools.combinations(sorted(occ_dwa), 2):
        sa, sb = occ_dwa[a], occ_dwa[b]
        shared = sa & sb
        if len(shared) < min_shared:
            continue
        wa, wb = weights.get(a, {}), weights.get(b, {})
        num = sum(wa.get(d, 0.0) * wb.get(d, 0.0) for d in shared)
        na = math.sqrt(sum(v * v for v in wa.values())) or 1.0
        nb = math.sqrt(sum(v * v for v in wb.values())) or 1.0
        edges.append(
            {
                "source": a,
                "target": b,
                "source_title": occupations.get(a, {}).get("title", ""),
                "target_title": occupations.get(b, {}).get("title", ""),
                "shared_subtasks": len(shared),
                "cosine": round(_cosine(sa, sb), 4),
                "jaccard": round(_jaccard(sa, sb), 4),
                "weighted_cosine": round(num / (na * nb), 4),
                "same_soc_major_group": int(a[:2] == b[:2]),
            }
        )
    return sorted(edges, key=lambda e: -e["cosine"])


def occupation_nodes(
    occ_dwa: dict[str, set[str]],
    weights: dict[str, dict[str, float]],
    edges: Sequence[dict[str, Any]],
    occupations: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    degree: dict[str, int] = collections.Counter()
    strength: dict[str, float] = collections.Counter()
    for edge in edges:
        for end in ("source", "target"):
            degree[edge[end]] += 1
            strength[edge[end]] += edge["cosine"]
    nodes = []
    for code in sorted(occ_dwa):
        occ = occupations.get(code, {})
        deg = degree.get(code, 0)
        nodes.append(
            {
                "onet_soc_code": code,
                "title": occ.get("title", ""),
                "stem_occupation_types": occ.get("stem_occupation_types", ""),
                "job_zone": occ.get("job_zone"),
                "bright_outlook": occ.get("bright_outlook"),
                "n_tasks": occ.get("n_tasks"),
                "n_subtasks": len(occ_dwa[code]),
                "degree": deg,
                "weighted_degree": round(strength.get(code, 0.0), 3),
                "mean_similarity": round(strength.get(code, 0.0) / deg, 4) if deg else 0.0,
            }
        )
    return nodes


def subtask_network(
    dwa_occ: dict[str, set[str]],
    hierarchy: Sequence[dict[str, Any]],
    task_subtasks: Sequence[dict[str, Any]],
    min_shared: int = 5,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    hier = {h["dwa_id"]: h for h in hierarchy}
    titles = {l["dwa_id"]: l["dwa_title"] for l in task_subtasks}
    task_counts = collections.Counter(l["dwa_id"] for l in task_subtasks)

    edges = []
    for a, b in itertools.combinations(sorted(dwa_occ), 2):
        shared = dwa_occ[a] & dwa_occ[b]
        if len(shared) < min_shared:
            continue
        edges.append(
            {
                "source": a,
                "target": b,
                "source_title": titles.get(a, ""),
                "target_title": titles.get(b, ""),
                "co_occurring_occupations": len(shared),
                "cosine": round(_cosine(dwa_occ[a], dwa_occ[b]), 4),
            }
        )
    edges.sort(key=lambda e: -e["co_occurring_occupations"])

    degree = collections.Counter()
    for edge in edges:
        degree[edge["source"]] += 1
        degree[edge["target"]] += 1
    nodes = [
        {
            "dwa_id": dwa,
            "dwa_title": titles.get(dwa, ""),
            "iwa_title": hier.get(dwa, {}).get("iwa_title", ""),
            "gwa_title": hier.get(dwa, {}).get("gwa_title", ""),
            "n_occupations": len(occs),
            "n_tasks": task_counts[dwa],
            "degree": degree.get(dwa, 0),
        }
        for dwa, occs in sorted(dwa_occ.items())
    ]
    return edges, nodes


# --------------------------------------------------------------------------- #
# Validation against O*NET's own relatedness list                              #
# --------------------------------------------------------------------------- #
def validate_against_related(
    edges: Sequence[dict[str, Any]],
    related: Sequence[dict[str, Any]],
    top_k: int = 10,
) -> dict[str, Any]:
    """What share of O*NET's related occupations land in our top-k neighbours."""
    if not related:
        return {"available": False}

    neighbours: dict[str, list[tuple[float, str]]] = collections.defaultdict(list)
    for edge in edges:
        neighbours[edge["source"]].append((edge["cosine"], edge["target"]))
        neighbours[edge["target"]].append((edge["cosine"], edge["source"]))

    truth: dict[str, set[str]] = collections.defaultdict(set)
    for row in related:
        if row.get("related_is_stem"):
            truth[row["onet_soc_code"]].add(row["related_onet_soc_code"])

    hits = total = covered = ceiling = 0
    for code, expected in truth.items():
        if code not in neighbours or not expected:
            continue
        top = {c for _, c in sorted(neighbours[code], reverse=True)[:top_k]}
        hits += len(top & expected)
        total += len(expected)
        # A top-k list cannot recall more than k items, so an occupation with 17
        # related jobs caps at 10/17 at k=10. Report recall against that ceiling
        # too, or a structurally capped number reads as a bad network.
        ceiling += min(top_k, len(expected))
        covered += 1
    recall = hits / total if total else 0.0
    return {
        "available": True,
        "occupations_compared": covered,
        "recall_at_k": round(recall, 4),
        "max_achievable_recall_at_k": round(ceiling / total, 4) if total else 0.0,
        "recall_vs_ceiling": round(hits / ceiling, 4) if ceiling else 0.0,
        "k": top_k,
        "note": "O*NET relatedness uses skills, knowledge and abilities as well as "
                "activities, so perfect agreement is not expected or desirable",
    }


# --------------------------------------------------------------------------- #
# GraphML                                                                       #
# --------------------------------------------------------------------------- #
def write_graphml(
    path: Path,
    nodes: Sequence[dict[str, Any]],
    edges: Sequence[dict[str, Any]],
    node_id: str,
    edge_weight: str,
) -> None:
    node_keys = [k for k in nodes[0] if k != node_id] if nodes else []
    edge_keys = [k for k in (edges[0] if edges else {}) if k not in ("source", "target")]

    def typeof(value: Any) -> str:
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, int):
            return "int"
        if isinstance(value, float):
            return "double"
        return "string"

    node_types = {k: typeof(next((n[k] for n in nodes if n.get(k) is not None), "")) for k in node_keys}
    edge_types = {k: typeof(next((e[k] for e in edges if e.get(k) is not None), "")) for k in edge_keys}

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">',
    ]
    for key in node_keys:
        lines.append(f'  <key id="n_{key}" for="node" attr.name="{key}" attr.type="{node_types[key]}"/>')
    for key in edge_keys:
        lines.append(f'  <key id="e_{key}" for="edge" attr.name="{key}" attr.type="{edge_types[key]}"/>')
    lines.append('  <graph edgedefault="undirected">')

    for node in nodes:
        lines.append(f'    <node id="{escape(str(node[node_id]))}">')
        for key in node_keys:
            value = node.get(key)
            if value not in (None, ""):
                lines.append(f'      <data key="n_{key}">{escape(str(value))}</data>')
        lines.append("    </node>")

    for i, edge in enumerate(edges):
        lines.append(f'    <edge id="e{i}" source="{escape(edge["source"])}" '
                     f'target="{escape(edge["target"])}">')
        for key in edge_keys:
            value = edge.get(key)
            if value not in (None, ""):
                lines.append(f'      <data key="e_{key}">{escape(str(value))}</data>')
        lines.append("    </edge>")

    lines += ["  </graph>", "</graphml>"]
    path.write_text("\n".join(lines))
    log.info("wrote %-28s %d nodes, %d edges (weight: %s)",
             path.name, len(nodes), len(edges), edge_weight)
