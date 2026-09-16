"""Tests for the network projection, index building and score propagation.

The scoring stage's API call cannot run offline, but everything around it can:
these exercise the maths that turns 963 rated subtasks into task- and
occupation-level measures.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from onet_scraper.descriptors import build_indices, build_related_occupations  # noqa: E402
from onet_scraper.network import (  # noqa: E402
    build_incidence,
    occupation_edges,
    occupation_nodes,
    subtask_network,
    validate_against_related,
    write_graphml,
)
from onet_scraper.score import estimate_cost, propagate, subtask_catalogue  # noqa: E402

TASKS = [
    {"onet_soc_code": "15-0001.00", "occupation_title": "A", "task_id": 1,
     "task": "t1", "task_category": "Core", "importance": 90.0},
    {"onet_soc_code": "15-0001.00", "occupation_title": "A", "task_id": 2,
     "task": "t2", "task_category": "Supplemental", "importance": 10.0},
    {"onet_soc_code": "29-0002.00", "occupation_title": "B", "task_id": 3,
     "task": "t3", "task_category": "Core", "importance": 50.0},
]
LINKS = [
    {"onet_soc_code": "15-0001.00", "task_id": 1, "dwa_id": "d1", "dwa_title": "D one"},
    {"onet_soc_code": "15-0001.00", "task_id": 1, "dwa_id": "d2", "dwa_title": "D two"},
    {"onet_soc_code": "15-0001.00", "task_id": 2, "dwa_id": "d3", "dwa_title": "D three"},
    {"onet_soc_code": "29-0002.00", "task_id": 3, "dwa_id": "d1", "dwa_title": "D one"},
    {"onet_soc_code": "29-0002.00", "task_id": 3, "dwa_id": "d2", "dwa_title": "D two"},
    {"onet_soc_code": "29-0002.00", "task_id": 3, "dwa_id": "d3", "dwa_title": "D three"},
]
OCCUPATIONS = [
    {"onet_soc_code": "15-0001.00", "title": "A", "stem_occupation_types": "x", "job_zone": 4},
    {"onet_soc_code": "29-0002.00", "title": "B", "stem_occupation_types": "y", "job_zone": 5},
]
HIERARCHY = [
    {"dwa_id": "d1", "dwa_title": "D one", "iwa_id": "i1", "iwa_title": "I one",
     "gwa_id": "g1", "gwa_title": "G one"},
]


class TestIncidence(unittest.TestCase):
    def test_importance_flows_to_subtasks(self):
        occ_dwa, weights, dwa_occ = build_incidence(LINKS, TASKS)
        self.assertEqual(occ_dwa["15-0001.00"], {"d1", "d2", "d3"})
        self.assertEqual(dwa_occ["d1"], {"15-0001.00", "29-0002.00"})
        # d1 comes from task 1 (importance 90), d3 from task 2 (importance 10)
        self.assertEqual(weights["15-0001.00"]["d1"], 90.0)
        self.assertEqual(weights["15-0001.00"]["d3"], 10.0)

    def test_exclude_soc_prefix(self):
        occ_dwa, _, _ = build_incidence(LINKS, TASKS, exclude_soc=("29",))
        self.assertEqual(set(occ_dwa), {"15-0001.00"})


class TestOccupationNetwork(unittest.TestCase):
    def setUp(self):
        self.occ_dwa, self.weights, self.dwa_occ = build_incidence(LINKS, TASKS)
        self.occs = {o["onet_soc_code"]: o for o in OCCUPATIONS}

    def test_identical_subtask_sets_give_cosine_one(self):
        edges = occupation_edges(self.occ_dwa, self.weights, self.occs, min_shared=3)
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["shared_subtasks"], 3)
        self.assertAlmostEqual(edges[0]["cosine"], 1.0)
        self.assertAlmostEqual(edges[0]["jaccard"], 1.0)
        self.assertEqual(edges[0]["same_soc_major_group"], 0)

    def test_weighted_cosine_differs_from_unweighted(self):
        edges = occupation_edges(self.occ_dwa, self.weights, self.occs, min_shared=3)
        self.assertLess(edges[0]["weighted_cosine"], edges[0]["cosine"],
                        "importance weighting must distinguish these two occupations")

    def test_min_shared_filters(self):
        self.assertEqual(occupation_edges(self.occ_dwa, self.weights, self.occs,
                                          min_shared=4), [])

    def test_nodes_carry_degree(self):
        edges = occupation_edges(self.occ_dwa, self.weights, self.occs, min_shared=3)
        nodes = occupation_nodes(self.occ_dwa, self.weights, edges, self.occs)
        self.assertEqual({n["degree"] for n in nodes}, {1})
        self.assertEqual(nodes[0]["n_subtasks"], 3)

    def test_graphml_roundtrips_through_xml(self):
        import xml.etree.ElementTree as ET
        edges = occupation_edges(self.occ_dwa, self.weights, self.occs, min_shared=3)
        nodes = occupation_nodes(self.occ_dwa, self.weights, edges, self.occs)
        out = Path(__file__).parent / "_tmp.graphml"
        try:
            write_graphml(out, nodes, edges, "onet_soc_code", "cosine")
            root = ET.parse(out).getroot()
            ns = "{http://graphml.graphdrawing.org/xmlns}"
            self.assertEqual(len(root.findall(f"{ns}graph/{ns}node")), 2)
            self.assertEqual(len(root.findall(f"{ns}graph/{ns}edge")), 1)
        finally:
            out.unlink(missing_ok=True)


class TestSubtaskNetwork(unittest.TestCase):
    def test_co_occurrence(self):
        _, _, dwa_occ = build_incidence(LINKS, TASKS)
        edges, nodes = subtask_network(dwa_occ, HIERARCHY, LINKS, min_shared=2)
        self.assertEqual(len(edges), 3, "d1-d2, d1-d3, d2-d3 all co-occur in both jobs")
        self.assertEqual({n["dwa_id"] for n in nodes}, {"d1", "d2", "d3"})
        self.assertEqual(next(n for n in nodes if n["dwa_id"] == "d1")["gwa_title"], "G one")


class TestRelatednessValidation(unittest.TestCase):
    def test_recall_against_onet(self):
        occ_dwa, weights, _ = build_incidence(LINKS, TASKS)
        edges = occupation_edges(occ_dwa, weights, {}, min_shared=3)
        related = [{"onet_soc_code": "15-0001.00", "related_onet_soc_code": "29-0002.00",
                    "related_is_stem": 1}]
        result = validate_against_related(edges, related, top_k=5)
        self.assertTrue(result["available"])
        self.assertEqual(result["recall_at_k"], 1.0)

    def test_no_baseline_is_reported_not_crashed(self):
        self.assertEqual(validate_against_related([], []), {"available": False})


class TestScorePropagation(unittest.TestCase):
    def setUp(self):
        dims = {
            "automation_feasibility_today": 0, "llm_exposure": 0,
            "physical_embodiment_required": 0, "interpersonal_demand": 0,
            "judgment_under_uncertainty": 0, "accountability_requirement": 0,
            "error_cost": 0,
        }
        self.scores = [
            {**dims, "dwa_id": "d1", "llm_exposure": 100, "verdict": "largely_automatable"},
            {**dims, "dwa_id": "d2", "llm_exposure": 0, "verdict": "human_anchored"},
            {**dims, "dwa_id": "d3", "llm_exposure": 50, "verdict": "augmentable"},
        ]

    def test_task_score_is_mean_of_its_subtasks(self):
        task_rows, _ = propagate(self.scores, TASKS, LINKS, OCCUPATIONS)
        t1 = next(r for r in task_rows if r["task_id"] == 1)
        self.assertEqual(t1["n_subtasks_scored"], 2)
        self.assertEqual(t1["llm_exposure"], 50.0)  # mean of 100 and 0

    def test_occupation_score_is_importance_weighted(self):
        _, occ_rows = propagate(self.scores, TASKS, LINKS, OCCUPATIONS)
        a = next(r for r in occ_rows if r["onet_soc_code"] == "15-0001.00")
        # task1 (llm 50, importance 90) and task2 (llm 50, importance 10) -> 50
        self.assertEqual(a["llm_exposure"], 50.0)
        b = next(r for r in occ_rows if r["onet_soc_code"] == "29-0002.00")
        self.assertEqual(b["llm_exposure"], 50.0)  # mean of 100, 0, 50
        self.assertEqual(b["task_coverage"], 1.0)

    def test_weighting_actually_bites(self):
        """A high-importance automatable task should dominate a trivial one."""
        tasks = [
            {"onet_soc_code": "15-0001.00", "occupation_title": "A", "task_id": 1,
             "task": "t1", "task_category": "Core", "importance": 99.0},
            {"onet_soc_code": "15-0001.00", "occupation_title": "A", "task_id": 2,
             "task": "t2", "task_category": "Core", "importance": 1.0},
        ]
        links = [
            {"onet_soc_code": "15-0001.00", "task_id": 1, "dwa_id": "d1", "dwa_title": ""},
            {"onet_soc_code": "15-0001.00", "task_id": 2, "dwa_id": "d2", "dwa_title": ""},
        ]
        _, occ = propagate(self.scores, tasks, links, OCCUPATIONS[:1])
        self.assertGreater(occ[0]["llm_exposure"], 95.0,
                           "the importance-99 task must dominate the importance-1 one")

    def test_unscored_subtasks_are_skipped_not_zeroed(self):
        task_rows, _ = propagate([self.scores[0]], TASKS, LINKS, OCCUPATIONS)
        t2 = [r for r in task_rows if r["task_id"] == 2]
        self.assertEqual(t2, [], "a task with no scored subtask must be absent, not 0")


class TestCatalogueAndCost(unittest.TestCase):
    def test_catalogue_is_deduplicated(self):
        catalogue = subtask_catalogue(LINKS, HIERARCHY)
        self.assertEqual(len(catalogue), 3)
        d1 = next(c for c in catalogue if c["dwa_id"] == "d1")
        self.assertEqual(d1["n_occupations"], 2)
        self.assertEqual(d1["gwa_title"], "G one")

    def test_cost_scales_with_chunk_size(self):
        small = estimate_cost([{"dwa_id": str(i)} for i in range(100)], 5, "claude-opus-5")
        large = estimate_cost([{"dwa_id": str(i)} for i in range(100)], 25, "claude-opus-5")
        self.assertEqual(small["requests"], 20)
        self.assertEqual(large["requests"], 4)
        self.assertLess(large["est_cost_usd"], small["est_cost_usd"])


class TestIndices(unittest.TestCase):
    def test_missing_element_is_reported(self):
        tables = {"work_context.csv": [
            {"onet_soc_code": "15-0001.00", "element_name": "Contact With Others",
             "scale_id": "CX", "data_value": 5.0},
            {"onet_soc_code": "29-0002.00", "element_name": "Contact With Others",
             "scale_id": "CX", "data_value": 1.0},
        ]}
        rows, missing = build_indices(tables, OCCUPATIONS)
        self.assertTrue(any("Work With or Contribute" in m for m in missing),
                        "an element absent from the data must be reported, not silently zero")
        a = next(r for r in rows if r["onet_soc_code"] == "15-0001.00")
        self.assertEqual(a["collaboration"], 100.0)  # rescaled max of the observed range
        self.assertIsNone(a["bottleneck_creative_intelligence"])

    def test_related_occupations_flags_stem(self):
        rows = build_related_occupations(
            [{"O*NET-SOC Code": "15-0001.00", "Related O*NET-SOC Code": "29-0002.00",
              "Related Title": "B", "Relatedness Tier": "Primary-Short", "Index": "1"}],
            {"15-0001.00", "29-0002.00"})
        self.assertEqual(rows[0]["related_is_stem"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestSusceptibilityIndex(unittest.TestCase):
    """The index must not double-count the two near-collinear dimension pairs."""

    def _row(self, **kw):
        base = {d: 0 for d in (
            "automation_feasibility_today", "llm_exposure", "physical_embodiment_required",
            "interpersonal_demand", "judgment_under_uncertainty",
            "accountability_requirement", "error_cost")}
        base.update(kw)
        return base

    def test_stakes_pair_collapses_to_one_factor(self):
        from onet_scraper.susceptibility import add_axes
        # accountability and error_cost correlate at r=0.90; together they must carry
        # the weight of one anchoring component, not two.
        both = add_axes(self._row(accountability_requirement=100, error_cost=100))
        one = add_axes(self._row(interpersonal_demand=100))
        self.assertEqual(both["anchoring"], one["anchoring"],
                         "the stakes pair must weigh the same as any single component")

    def test_physical_not_counted_twice(self):
        from onet_scraper.susceptibility import add_axes
        # physical_embodiment is llm_exposure's mirror (r=-0.89); it belongs to
        # anchoring only, and must not also be subtracted from exposure.
        r = add_axes(self._row(llm_exposure=80, physical_embodiment_required=100))
        self.assertEqual(r["exposure"], 80.0)

    def test_susceptibility_direction_and_clamp(self):
        from onet_scraper.susceptibility import add_axes
        hi = add_axes(self._row(llm_exposure=100))
        lo = add_axes(self._row(llm_exposure=0, interpersonal_demand=100,
                                accountability_requirement=100, error_cost=100,
                                judgment_under_uncertainty=100,
                                physical_embodiment_required=100))
        self.assertGreater(hi["susceptibility"], lo["susceptibility"])
        for r in (hi, lo):
            self.assertGreaterEqual(r["susceptibility"], 0)
            self.assertLessEqual(r["susceptibility"], 100)

    def test_deployment_gap(self):
        from onet_scraper.susceptibility import add_axes
        r = add_axes(self._row(llm_exposure=90, automation_feasibility_today=20))
        self.assertEqual(r["deployment_gap"], 70.0)

    def test_quadrant_naming(self):
        from onet_scraper.susceptibility import quadrant
        self.assertEqual(quadrant(80, 20, 50, 50), "Displaceable")
        self.assertEqual(quadrant(80, 80, 50, 50), "Contested")
        self.assertEqual(quadrant(20, 80, 50, 50), "Human-anchored")
        self.assertEqual(quadrant(20, 20, 50, 50), "Insulated")

    def test_convergent_validity_flags_non_monotonic(self):
        from onet_scraper.susceptibility import convergent_validity
        bad = [{"verdict": "largely_automatable", "susceptibility": 10.0},
               {"verdict": "human_anchored", "susceptibility": 90.0}]
        self.assertFalse(convergent_validity(bad)["monotonic"])
        good = [{"verdict": "largely_automatable", "susceptibility": 90.0},
                {"verdict": "human_anchored", "susceptibility": 10.0}]
        self.assertTrue(convergent_validity(good)["monotonic"])


class TestEmploymentJoin(unittest.TestCase):
    """The SOC join is where a naive implementation silently multi-counts."""

    OEWS = {
        "29-1141": {"soc_code": "29-1141", "soc_title": "Registered Nurses",
                    "total_employment": 3_000_000.0, "annual_mean_wage": 90_000.0,
                    "annual_median_wage": 86_000.0},
        "29-2010": {"soc_code": "29-2010", "soc_title": "Clinical Lab Techs",
                    "total_employment": 300_000.0, "annual_mean_wage": 60_000.0,
                    "annual_median_wage": 58_000.0},
        "15-2051": {"soc_code": "15-2051", "soc_title": "Data Scientists",
                    "total_employment": 200_000.0, "annual_mean_wage": 120_000.0,
                    "annual_median_wage": 110_000.0},
    }

    def _occ(self, code, susc, quad="Displaceable"):
        return {"onet_soc_code": code, "title": code, "susceptibility": susc,
                "exposure": susc, "anchoring": 100 - susc, "deployment_gap": 10,
                "quadrant": quad, "stem_occupation_types": "x"}

    def test_five_onet_nurses_count_three_million_workers_once(self):
        from onet_scraper.employment import build_soc_table
        occ = [self._occ(f"29-1141.0{i}", 50, "Human-anchored") for i in range(5)]
        rows, diag = build_soc_table(occ, self.OEWS)
        self.assertEqual(len(rows), 1, "five O*NET nurse occupations = one SOC row")
        self.assertEqual(rows[0]["total_employment"], 3_000_000.0)
        self.assertEqual(rows[0]["n_onet_occupations"], 5)
        self.assertEqual(diag["employment_covered"], 3_000_000.0,
                         "employment must be counted once, not five times")

    def test_broad_code_fallback_does_not_double_count(self):
        from onet_scraper.employment import build_soc_table
        # 29-2011 and 29-2012 are both published by BLS as 29-2010.
        occ = [self._occ("29-2011.00", 60), self._occ("29-2012.00", 40)]
        rows, diag = build_soc_table(occ, self.OEWS)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["soc_code"], "29-2010")
        self.assertEqual(diag["employment_covered"], 300_000.0)
        self.assertEqual(rows[0]["susceptibility"], 50.0, "mean of 60 and 40")

    def test_within_soc_disagreement_is_reported(self):
        from onet_scraper.employment import build_soc_table
        rows, _ = build_soc_table(
            [self._occ("29-1141.01", 20), self._occ("29-1141.02", 80)], self.OEWS)
        self.assertGreater(rows[0]["susceptibility_sd_within_soc"], 40,
                           "a hidden split inside one SOC must be visible")

    def test_unmatched_codes_are_reported_not_dropped_silently(self):
        from onet_scraper.employment import build_soc_table
        rows, diag = build_soc_table([self._occ("99-9999.00", 50)], self.OEWS)
        self.assertEqual(rows, [])
        self.assertEqual(diag["unmatched_onet_codes"], ["99-9999.00"])

    def test_resolve_soc(self):
        from onet_scraper.employment import resolve_soc
        avail = set(self.OEWS)
        self.assertEqual(resolve_soc("15-2051.00", avail), "15-2051")
        self.assertEqual(resolve_soc("29-2011.00", avail), "29-2010")
        self.assertIsNone(resolve_soc("99-9999.00", avail))

    def test_bls_sentinels_are_not_parsed_as_numbers(self):
        from onet_scraper.employment import _num
        for marker in ("*", "**", "#", "~", ""):
            self.assertIsNone(_num(marker), f"{marker!r} is a suppression flag, not a value")
        self.assertEqual(_num("1,234"), 1234.0)
        self.assertEqual(_num(56.7), 56.7)

    def test_headline_weighting(self):
        from onet_scraper.employment import build_soc_table, headline_stats
        occ = [self._occ("29-1141.00", 20, "Human-anchored"),
               self._occ("15-2051.00", 90, "Displaceable")]
        rows, _ = build_soc_table(occ, self.OEWS)
        stats = headline_stats(rows)
        # 3.0M at 20 and 0.2M at 90 -> weighted mean must sit near 20, not 55.
        self.assertLess(stats["employment_weighted_susceptibility"], 30)
        self.assertEqual(stats["unweighted_susceptibility"], 55.0)
        self.assertLess(stats["weighting_shifts_result_by"], -20)
        self.assertEqual(stats["by_quadrant"]["Human-anchored"]["employment"], 3_000_000.0)


class TestExternalValidation(unittest.TestCase):
    def test_pearson_and_spearman(self):
        from onet_scraper.external import pearson, spearman
        a = [1, 2, 3, 4, 5]
        self.assertAlmostEqual(pearson(a, [2, 4, 6, 8, 10]), 1.0)
        self.assertAlmostEqual(pearson(a, [10, 8, 6, 4, 2]), -1.0)
        # Spearman is rank-based, so a monotone non-linear map is still 1.0
        self.assertAlmostEqual(spearman(a, [1, 4, 9, 16, 25]), 1.0)
        self.assertLess(pearson(a, [1, 4, 9, 16, 25]), 1.0)

    def test_spearman_handles_ties(self):
        from onet_scraper.external import spearman
        self.assertAlmostEqual(spearman([1, 1, 2, 2], [1, 1, 2, 2]), 1.0)

    def test_join_keeps_soc_level_measures(self):
        from onet_scraper.external import join
        ours = [{"onet_soc_code": "15-2021.00", "title": "Mathematicians",
                 "susceptibility": 77.4, "exposure": 80.0, "anchoring": 25.0}]
        bench = {"occ": {"15-2021.00": {"human_rating_beta": "0.8",
                                        "dv_rating_beta": "0.75"}},
                 "auto": {"15-2021": {"freyOsborne": "0.047", "mSML": "3.1",
                                      "felten_raj_seamans": "4.2"}}}
        rows, cov = join(ours, bench)
        self.assertEqual(cov["matched"], 1)
        self.assertEqual(rows[0]["human_beta"], 0.8)
        self.assertEqual(rows[0]["frey_osborne"], 0.047,
                         "SOC-level measures must join on the 6-digit code")

    def test_unmatched_reported(self):
        from onet_scraper.external import join
        rows, cov = join([{"onet_soc_code": "99-9999.00", "susceptibility": 50}],
                         {"occ": {}, "auto": {}})
        self.assertEqual(rows, [])
        self.assertEqual(cov["unmatched"], ["99-9999.00"])

    def test_correlate_skips_thin_overlap(self):
        from onet_scraper.external import correlate
        rows = [{"our_susceptibility": i, "human_beta": i} for i in range(5)]
        result = {c["measure"]: c for c in correlate(rows)}
        self.assertIsNone(result["human_beta"]["pearson"],
                          "fewer than 10 pairs must not produce a correlation")
