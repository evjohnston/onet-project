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
from onet_scraper import security  # noqa: E402
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


class TestSecurityMatrix(unittest.TestCase):
    """The efficiency / removal-risk / reconstitution matrix."""

    def _task(self, **kw):
        base = {"onet_soc_code": "15-0001.00", "task_id": 1, "importance": 50.0,
                "modest": "unchanged", "substantial": "unchanged",
                "extreme": "unchanged", "error_cost": 50.0,
                "accountability_requirement": 50.0,
                "judgment_under_uncertainty": 50.0,
                "interpersonal_demand": 50.0,
                "physical_embodiment_required": 50.0}
        base.update(kw)
        return base

    def test_efficiency_credits_automated_fully_and_augmented_partly(self):
        auto = [self._task(substantial="automated")]
        aug = [self._task(substantial="augmented")]
        none = [self._task(substantial="unchanged")]
        self.assertEqual(security.efficiency(auto, "substantial"), 100.0)
        self.assertEqual(security.efficiency(none, "substantial"), 0.0)
        self.assertEqual(security.efficiency(aug, "substantial"),
                         100.0 * security.AUGMENTED_CREDIT)

    def test_efficiency_is_importance_weighted_not_a_task_count(self):
        # One trivial automatable task plus one dominant task that stays human
        # is not an efficiency opportunity, even though it is 50% of the tasks.
        tasks = [self._task(task_id=1, importance=5.0, substantial="automated"),
                 self._task(task_id=2, importance=95.0, substantial="unchanged")]
        self.assertEqual(security.efficiency(tasks, "substantial"), 5.0)

    def test_efficiency_rises_with_scenario_severity(self):
        tasks = [self._task(task_id=1, modest="unchanged",
                            substantial="augmented", extreme="automated")]
        modest = security.efficiency(tasks, "modest")
        substantial = security.efficiency(tasks, "substantial")
        extreme = security.efficiency(tasks, "extreme")
        self.assertLess(modest, substantial)
        self.assertLess(substantial, extreme)

    def test_removal_risk_ignores_interpersonal_and_physical(self):
        """The central design claim: this is a risk index, not an
        anchoring index. Two tasks differing only in interpersonal demand and
        physical embodiment must score identically."""
        low = [self._task(interpersonal_demand=0.0, physical_embodiment_required=0.0)]
        high = [self._task(interpersonal_demand=100.0,
                           physical_embodiment_required=100.0)]
        self.assertEqual(security.removal_risk(low), security.removal_risk(high))

    def test_removal_risk_weights_error_cost_highest(self):
        base = self._task(error_cost=0.0, accountability_requirement=0.0,
                          judgment_under_uncertainty=0.0)
        bump_error = security.removal_risk([dict(base, error_cost=100.0)])
        bump_acct = security.removal_risk(
            [dict(base, accountability_requirement=100.0)])
        bump_judge = security.removal_risk(
            [dict(base, judgment_under_uncertainty=100.0)])
        self.assertGreater(bump_error, bump_acct)
        self.assertGreater(bump_acct, bump_judge)
        self.assertAlmostEqual(
            sum(security.RISK_WEIGHTS.values()), 1.0, places=6)

    def test_risk_at_stake_only_counts_handed_over_work(self):
        # The risky task stays human; the automated task is harmless. Overall
        # risk is high, but the risk actually being handed over is not.
        tasks = [self._task(task_id=1, importance=50.0, error_cost=100.0,
                            accountability_requirement=100.0,
                            judgment_under_uncertainty=100.0,
                            substantial="unchanged"),
                 self._task(task_id=2, importance=50.0, error_cost=0.0,
                            accountability_requirement=0.0,
                            judgment_under_uncertainty=0.0,
                            substantial="automated")]
        self.assertAlmostEqual(security.removal_risk(tasks), 50.0, places=1)
        self.assertEqual(security.risk_at_stake(tasks, "substantial"), 0.0)

    def test_risk_at_stake_is_zero_when_nothing_is_handed_over(self):
        tasks = [self._task(substantial="unchanged")]
        self.assertEqual(security.risk_at_stake(tasks, "substantial"), 0.0)

    def test_reconstitution_rises_with_training_depth(self):
        shallow = security.reconstitution(3, 10000, 0.3, 3.0, 6.0)
        deep = security.reconstitution(5, 10000, 0.3, 3.0, 6.0)
        self.assertLess(shallow["reconstitution"], deep["reconstitution"])
        self.assertEqual(deep["training_depth"], 100.0)

    def test_reconstitution_treats_small_cohorts_as_harder(self):
        tiny = security.reconstitution(4, 1_000, 0.3, 3.0, 6.0)
        huge = security.reconstitution(4, 1_000_000, 0.3, 3.0, 6.0)
        self.assertGreater(tiny["scarcity"], huge["scarcity"])
        self.assertGreater(tiny["reconstitution"], huge["reconstitution"])

    def test_scarcity_is_log_scaled(self):
        """A linear scale would call everything except the largest occupation
        scarce, because the corpus spans four orders of magnitude."""
        mid = security._scarcity(10**4.5, 3.0, 6.0)
        self.assertAlmostEqual(mid, 50.0, places=1)

    def test_isolation_is_the_inverse_of_shared_activity(self):
        shared = security.reconstitution(4, 10000, 0.9, 3.0, 6.0)
        isolated = security.reconstitution(4, 10000, 0.1, 3.0, 6.0)
        self.assertLess(shared["isolation"], isolated["isolation"])
        self.assertLess(shared["reconstitution"], isolated["reconstitution"])

    def test_missing_inputs_fall_back_to_the_midpoint(self):
        parts = security.reconstitution(None, None, None, 3.0, 6.0)
        self.assertEqual(parts["scarcity"], security.MIDPOINT)
        self.assertEqual(parts["isolation"], security.MIDPOINT)
        self.assertEqual(parts["reconstitution"], security.MIDPOINT)

    def test_all_eight_octants_are_reachable_and_named(self):
        seen = set()
        for eff in (10.0, 90.0):
            for risk in (10.0, 90.0):
                for recon in (10.0, 90.0):
                    seen.add(security.octant(eff, risk, recon)[0])
        self.assertEqual(len(seen), 8)
        self.assertEqual(len(security.OCTANTS), 8)
        self.assertEqual(len({n for n, _ in security.OCTANTS.values()}), 8)

    def test_octant_boundary_is_inclusive_at_the_midpoint(self):
        self.assertEqual(security.octant(50.0, 50.0, 50.0)[0], "Strategic trap")
        self.assertEqual(security.octant(49.9, 49.9, 49.9)[0], "Low stakes")

    def test_trap_score_is_a_product_so_one_low_axis_demotes(self):
        """A sum would rank overwhelming-efficiency-no-risk above
        dangerous-on-all-three, which inverts what a planner needs to read."""
        lopsided = security.trap_score(100.0, 5.0, 5.0)
        balanced = security.trap_score(60.0, 60.0, 60.0)
        self.assertGreater(balanced, lopsided)

    def test_field_map_prefers_a_leaf_discipline_over_a_role_type(self):
        cats = [{"stem_category_id": "1", "stem_category_name": "Role", "is_leaf": "0"},
                {"stem_category_id": "1-2", "stem_category_name": "Discipline",
                 "is_leaf": "1"}]
        members = [{"onet_soc_code": "X", "stem_category_id": "1"},
                   {"onet_soc_code": "X", "stem_category_id": "1-2"}]
        self.assertEqual(security.field_map(members, cats)["X"], "Discipline")
        # reversed input order must not change the answer
        self.assertEqual(
            security.field_map(list(reversed(members)), cats)["X"], "Discipline")

    def test_field_map_falls_back_to_role_type_when_no_discipline(self):
        cats = [{"stem_category_id": "4", "stem_category_name": "Managerial",
                 "is_leaf": "0"}]
        members = [{"onet_soc_code": "X", "stem_category_id": "4"}]
        self.assertEqual(security.field_map(members, cats)["X"], "Managerial")

    def test_field_map_is_deterministic_with_two_disciplines(self):
        cats = [{"stem_category_id": "1-2", "stem_category_name": "Comp",
                 "is_leaf": "1"},
                {"stem_category_id": "1-4", "stem_category_name": "Science",
                 "is_leaf": "1"}]
        members = [{"onet_soc_code": "X", "stem_category_id": "1-4"},
                   {"onet_soc_code": "X", "stem_category_id": "1-2"}]
        self.assertEqual(security.field_map(members, cats)["X"], "Comp")

    # -- the double-count regression -------------------------------------
    def _corpus(self):
        fates = [
            {"onet_soc_code": "29-1141.00", "task_id": 1, "importance": 90.0,
             "modest": "unchanged", "substantial": "automated",
             "extreme": "automated"},
            {"onet_soc_code": "29-1141.01", "task_id": 2, "importance": 90.0,
             "modest": "unchanged", "substantial": "automated",
             "extreme": "automated"},
        ]
        scores = [
            {"task_id": 1, "error_cost": 90.0, "accountability_requirement": 90.0,
             "judgment_under_uncertainty": 90.0},
            {"task_id": 2, "error_cost": 90.0, "accountability_requirement": 90.0,
             "judgment_under_uncertainty": 90.0},
        ]
        occs = [
            {"onet_soc_code": "29-1141.00", "title": "Nurses", "job_zone": 4,
             "stem_occupation_types": "Healthcare"},
            {"onet_soc_code": "29-1141.01", "title": "Acute Nurses", "job_zone": 4,
             "stem_occupation_types": "Healthcare"},
        ]
        # Both O*NET codes roll up to one SOC and each carries its full figure.
        emp = {"29-1141.00": 3_000_000.0, "29-1141.01": 3_000_000.0}
        soc_of = {"29-1141.00": "29-1141", "29-1141.01": "29-1141"}
        fields = {"29-1141.00": "Healthcare", "29-1141.01": "Healthcare"}
        return fates, scores, occs, emp, soc_of, fields

    def test_field_employment_collapses_to_soc_before_summing(self):
        """Both O*NET codes roll up to one SOC and each carries its full figure.
        Knowing the SOC map at build time is what prevents the double count -
        without it every occupation looks like its own SOC."""
        fates, scores, occs, emp, soc_of, fields = self._corpus()
        correct = security.by_field(
            security.build(fates, scores, occs, emp, fields=fields, soc_of=soc_of))
        naive = security.by_field(
            security.build(fates, scores, occs, emp, fields=fields))
        one = [r for r in correct if r["scenario"] == "substantial"][0]
        two = [r for r in naive if r["scenario"] == "substantial"][0]
        self.assertEqual(one["total_employment"], 3_000_000.0)
        self.assertEqual(two["total_employment"], 6_000_000.0)
        self.assertNotEqual(one["total_employment"], two["total_employment"])

    def test_summary_employment_collapses_to_soc(self):
        fates, scores, occs, emp, soc_of, fields = self._corpus()
        rows = security.build(fates, scores, occs, emp, fields=fields, soc_of=soc_of)
        report = security.summarise(rows, soc_of)
        self.assertEqual(
            report["scenarios"]["substantial"]["total_employment"], 3_000_000.0)
        shares = [c["share_employment"]
                  for c in report["scenarios"]["substantial"]["by_octant"].values()]
        self.assertAlmostEqual(sum(shares), 1.0, places=3)

    def test_build_emits_one_row_per_occupation_per_scenario(self):
        fates, scores, occs, emp, soc_of, fields = self._corpus()
        rows = security.build(fates, scores, occs, emp, fields=fields)
        self.assertEqual(len(rows), 6)
        self.assertEqual({r["scenario"] for r in rows},
                         {"modest", "substantial", "extreme"})
        self.assertEqual({r["field"] for r in rows}, {"Healthcare"})

    def test_build_skips_occupations_with_no_scored_tasks(self):
        fates, scores, occs, emp, soc_of, fields = self._corpus()
        occs.append({"onet_soc_code": "99-9999.00", "title": "Ghost",
                     "job_zone": 4, "stem_occupation_types": "Healthcare"})
        rows = security.build(fates, scores, occs, emp, fields=fields)
        self.assertNotIn("99-9999.00", {r["onet_soc_code"] for r in rows})

    def test_ranking_is_insensitive_to_the_augmented_credit(self):
        """AUGMENTED_CREDIT is a round number standing in for 'some'. The
        ordering it produces must not depend on the exact value."""
        tasks_a = [self._task(task_id=1, importance=80.0, substantial="augmented")]
        tasks_b = [self._task(task_id=2, importance=80.0, substantial="automated")]
        original = security.AUGMENTED_CREDIT
        try:
            for credit in (0.35, 0.5, 0.65):
                security.AUGMENTED_CREDIT = credit
                self.assertLess(security.efficiency(tasks_a, "substantial"),
                                security.efficiency(tasks_b, "substantial"))
        finally:
            security.AUGMENTED_CREDIT = original


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


class TestHandoffFramework(unittest.TestCase):
    """Watson's two axes, six stages and four categories."""

    def _row(self, **kw):
        base = {d: 0 for d in (
            "automation_feasibility_today", "llm_exposure", "physical_embodiment_required",
            "interpersonal_demand", "judgment_under_uncertainty",
            "accountability_requirement", "error_cost")}
        base.update(kw)
        base.setdefault("onet_soc_code", "15-0001.00")
        return base

    def test_axes_separate_can_from_permitted(self):
        from onet_scraper.handoff import axes
        # Pure capability, nothing in the way.
        t, r = axes(self._row(llm_exposure=100))
        self.assertGreater(t, 90)
        self.assertEqual(r, 0.0)
        # Pure resistance: accountability and stakes, no capability.
        t, r = axes(self._row(accountability_requirement=100, error_cost=100,
                              interpersonal_demand=100))
        self.assertEqual(r, 100.0)

    def test_stage_is_the_lower_of_the_two_ceilings(self):
        from onet_scraper.handoff import stage
        # Full capability but total resistance -> nothing is permitted.
        self.assertEqual(stage(100, 100), 0)
        # Full capability, no resistance -> AI led, unreviewed.
        self.assertEqual(stage(100, 0), 5)
        # Capability is the binding constraint here, not permission.
        self.assertEqual(stage(20, 0), 1)

    def test_low_tractability_is_never_handed_off(self):
        """The bug the frontier curve alone produces: a constant-product curve
        puts 'low on both axes' on the same side as 'high T, low R'."""
        from onet_scraper.handoff import classify
        self.assertEqual(classify(33, 45, 10), "Human held")
        self.assertEqual(classify(49, 20, 10), "Human held")

    def test_handed_off_and_human_held_separate(self):
        from onet_scraper.handoff import classify
        self.assertEqual(classify(78, 30, 5), "Handed off")
        self.assertEqual(classify(55, 80, 5), "Human held")

    def test_watch_point_needs_all_three_conditions(self):
        from onet_scraper.handoff import classify
        self.assertEqual(classify(64, 70, 50), "Watch point")
        # capability present and resistance high, but no willingness gap
        self.assertNotEqual(classify(64, 70, 5), "Watch point")
        # wide gap but the work is not tractable
        self.assertEqual(classify(40, 70, 50), "Human held")

    def test_frontier_is_monotone_decreasing(self):
        from onet_scraper.handoff import frontier_resistance
        values = [frontier_resistance(t) for t in (40, 50, 60, 70, 80)]
        self.assertEqual(values, sorted(values, reverse=True))

    def test_build_reports_pending_crossings_and_weighty_ones(self):
        from onet_scraper.handoff import WEIGHTY_CROSSINGS, build
        rows = build([self._row(llm_exposure=80, automation_feasibility_today=20,
                                accountability_requirement=30, error_cost=30)])
        row = rows[0]
        self.assertGreater(row["stage_reachable"], row["stage_now"])
        self.assertEqual(row["pending_crossings"],
                         row["stage_reachable"] - row["stage_now"])
        self.assertEqual(row["willingness_gap"], 60.0)
        if row["stage_now"] in WEIGHTY_CROSSINGS:
            self.assertTrue(row["weighty_crossing"])

    def test_no_pending_crossing_means_no_weighty_label(self):
        from onet_scraper.handoff import build
        rows = build([self._row(llm_exposure=50, automation_feasibility_today=50)])
        self.assertEqual(rows[0]["pending_crossings"], 0)
        self.assertEqual(rows[0]["weighty_crossing"], "")

    def test_summarise_counts_employment_once(self):
        from onet_scraper.handoff import build, summarise
        rows = build(
            [self._row(onet_soc_code="29-1141.01", llm_exposure=70,
                       accountability_requirement=70, error_cost=70),
             self._row(onet_soc_code="29-1141.02", llm_exposure=70,
                       accountability_requirement=70, error_cost=70)],
            employment={"29-1141.01": 100.0, "29-1141.02": 100.0})
        s = summarise(rows)
        self.assertEqual(s["occupations"], 2)
        self.assertIn("by_classification", s)


class TestWageProtection(unittest.TestCase):
    def _soc(self, code, emp, wage, expo, anch):
        return {"soc_code": code, "soc_title": code, "total_employment": emp,
                "annual_mean_wage": wage, "exposure": expo, "anchoring": anch,
                "susceptibility": 50 + (expo - anch) / 2, "quadrant": ""}

    def test_returns_the_same_shape_when_empty(self):
        """The success and failure paths must agree, or a caller's availability
        check silently skips the whole analysis."""
        from onet_scraper.wages import build
        empty, full = build([]), build([self._soc("a", 100, 50000, 60, 40)])
        self.assertEqual(set(empty), set(full))
        self.assertFalse(empty["available"])
        self.assertTrue(full["available"])

    def test_deciles_hold_workers_constant_not_occupations(self):
        """One occupation larger than a decile must be split across buckets,
        not dropped whole into one - otherwise the buckets are not deciles."""
        from onet_scraper.wages import build
        rows = [self._soc("big", 9000, 40000, 50, 50),
                self._soc("small", 1000, 200000, 90, 10)]
        d = build(rows)["deciles"]
        self.assertEqual(len(d), 10)
        sizes = [x["workers"] for x in d]
        self.assertLess(max(sizes) - min(sizes), 2, "every decile holds 1,000 workers")
        # the cheap occupation fills the first nine buckets
        self.assertEqual(sum(1 for x in d if x["mean_wage"] == 40000), 9)

    def test_protection_classes(self):
        from onet_scraper.wages import classify_protection
        self.assertEqual(classify_protection(80, 80, 60, 50),
                         "Accountability - AI could, a human must answer")
        self.assertEqual(classify_protection(80, 20, 60, 50),
                         "Unprotected - exposed and lightly anchored")
        self.assertEqual(classify_protection(20, 80, 60, 50),
                         "Capability - AI cannot do much of it")


class TestTransitions(unittest.TestCase):
    def _setup(self):
        occ = [{"onet_soc_code": "A", "title": "A", "susceptibility": 80},
               {"onet_soc_code": "B", "title": "B", "susceptibility": 40},
               {"onet_soc_code": "C", "title": "C", "susceptibility": 78}]
        edges = [{"source": "A", "target": "B", "cosine": 0.5},
                 {"source": "A", "target": "C", "cosine": 0.9}]
        occ_dwa = {"A": {"d1", "d2"}, "B": {"d1", "d3"}, "C": {"d1", "d2"}}
        dwa_susc = {"d1": 90.0, "d2": 85.0, "d3": 20.0}
        return edges, occ, occ_dwa, dwa_susc, {}

    def test_similar_but_equally_exposed_is_not_a_destination(self):
        from onet_scraper.transitions import build
        moves, stranded, s = build(*self._setup())
        a = next(m for m in moves if m["onet_soc_code"] == "A")
        # C is the closest neighbour but offers no relief; B must win
        self.assertEqual(a["destination_code"], "B")

    def test_stranded_when_every_neighbour_is_exposed(self):
        from onet_scraper.transitions import build
        edges, occ, occ_dwa, dwa_susc, emp = self._setup()
        edges = [{"source": "A", "target": "C", "cosine": 0.9}]
        moves, stranded, s = build(edges, occ, occ_dwa, dwa_susc, emp)
        self.assertIn("A", [r["onet_soc_code"] for r in stranded])
        self.assertEqual(s["stranded_share"], round(len(stranded)/3, 3))

    def test_sweep_reports_threshold_dependence(self):
        from onet_scraper.transitions import sweep
        out = sweep(*self._setup())
        self.assertEqual(len(out), 9)
        self.assertTrue(all("stranded" in r for r in out))


class TestChurn(unittest.TestCase):
    def test_picks_the_real_task_file_not_the_green_subset(self):
        """A suffix match also catches 'Green Task Statements.txt', which is a
        small subset that parses cleanly and silently replaces the real file."""
        import io, zipfile
        from unittest.mock import Mock
        from onet_scraper.churn import fetch_release
        buf = io.BytesIO()
        hdr = "O*NET-SOC Code\tTitle\tTask ID\tTask\n"
        with zipfile.ZipFile(buf, "w") as z:
            # green file first, exactly as the real archives order them
            z.writestr("db/Green Task Statements.txt", hdr + "11-0000.00\tG\t1\tgreen task\n")
            z.writestr("db/Task Statements.txt",
                       hdr + "11-0000.00\tR\t2\treal task\n15-0000.00\tR\t3\tanother\n")
        client = Mock()
        client.get.return_value = Mock(content=buf.getvalue())
        out = fetch_release(client, "24_0")
        self.assertEqual(len(out), 2, "must read the full file, not the green subset")
        self.assertEqual(out["11-0000.00"][0]["task"], "real task")

    def test_reworded_task_counts_as_surviving(self):
        from onet_scraper.churn import diff, normalise
        before = {"A": [{"id": "1", "task": "Analyze data.", "key": normalise("Analyze data.")}]}
        after = {"A": [{"id": "9", "task": "Analyze  data!", "key": normalise("Analyze  data!")}]}
        d = diff(before, after, ["A"])
        self.assertEqual(d["added"], 0, "punctuation and spacing are not a new task")
        self.assertEqual(d["survived"], 1)

    def test_missing_occupation_is_skipped_not_counted_as_churn(self):
        from onet_scraper.churn import diff, normalise
        before = {"A": [{"id": "1", "task": "x", "key": "x"}]}
        after = {}
        d = diff(before, after, ["A"])
        self.assertEqual(d["occupations_skipped"], 1)
        self.assertEqual(d["retired"], 0, "a taxonomy change is not a retired task")


class TestScenarios(unittest.TestCase):
    def _t(self, e, a, code="15-0001.00"):
        return {"onet_soc_code": code, "occupation_title": "X", "task_id": 1,
                "task": "t", "importance": 50, "exposure": e, "anchoring": a}

    def test_accountability_is_what_the_scenario_moves(self):
        """Capability is fixed; the scenarios differ in how much accountability
        they are willing to hand over, so a high-exposure high-anchoring task
        should only automate at the extreme setting."""
        from onet_scraper.scenarios import fate
        t = self._t(75, 60)
        self.assertEqual(fate(t, "modest"), "augmented")
        self.assertEqual(fate(t, "substantial"), "augmented")
        self.assertEqual(fate(t, "extreme"), "automated")

    def test_low_exposure_never_moves(self):
        from onet_scraper.scenarios import SCENARIOS, fate
        t = self._t(20, 20)
        for name in SCENARIOS:
            self.assertEqual(fate(t, name), "unchanged", name)

    def test_scenarios_are_ordered_by_severity(self):
        from onet_scraper.scenarios import SCENARIOS, task_fates
        import collections
        tasks = [self._t(e, a) for e in range(30, 100, 5) for a in range(20, 80, 10)]
        counts = {}
        for name in SCENARIOS:
            f = task_fates(tasks)
            counts[name] = sum(1 for r in f if r[name] == "automated")
        self.assertLess(counts["modest"], counts["substantial"])
        self.assertLess(counts["substantial"], counts["extreme"])

    def test_employment_is_counted_once_per_soc(self):
        """Several O*NET occupations share one SOC and carry the same employment
        figure; summing across the O*NET rows turns 21.5M into 49.3M."""
        from onet_scraper.scenarios import by_occupation, flows
        tasks = [self._t(90, 10, "29-1141.01"), self._t(90, 10, "29-1141.02")]
        fates = __import__("onet_scraper.scenarios", fromlist=["x"]).task_fates(tasks)
        occ = by_occupation(fates, [], {"29-1141.01": "A", "29-1141.02": "B"},
                           {"29-1141.01": 3_000_000.0, "29-1141.02": 3_000_000.0},
                           set())
        naive = flows(occ)                       # no SOC map: double counts
        correct = flows(occ, {"29-1141.01": "29-1141", "29-1141.02": "29-1141"})
        self.assertEqual(naive["substantial"]["workers"], 6_000_000)
        self.assertEqual(correct["substantial"]["workers"], 3_000_000)
        self.assertEqual(correct["substantial"]["soc_codes"], 1)

    def test_new_tasks_are_observed_not_derived(self):
        from onet_scraper.scenarios import by_occupation, task_fates
        occ = by_occupation(task_fates([self._t(50, 50)]),
                            [{"onet_soc_code": "15-0001.00", "task": "new thing"}],
                            {"15-0001.00": "X"}, {}, set())
        self.assertTrue(all(r["new_tasks"] == 1 for r in occ))


class TestSecuritySeverity(unittest.TestCase):
    def test_every_octant_has_a_severity(self):
        names = {n for n, _ in security.OCTANTS.values()}
        self.assertEqual(names, set(security.SEVERITY))

    def test_severity_tiers_are_in_range(self):
        self.assertTrue(all(0 <= v < len(security.SEVERITY_LABELS)
                            for v in security.SEVERITY.values()))
        self.assertEqual(len(security.SEVERITY_LABELS), 4)

    def test_strategic_trap_is_the_only_critical_cell(self):
        top = max(security.SEVERITY.values())
        critical = [n for n, v in security.SEVERITY.items() if v == top]
        self.assertEqual(critical, ["Strategic trap"])

    def test_irreversible_outranks_reversible_at_equal_risk(self):
        """Quiet attrition and Hold the line both sit at low efficiency; the
        first is irreversible, the second is not, and that must show up."""
        self.assertGreater(security.severity("Quiet attrition"),
                           security.severity("Hold the line"))

    def test_unknown_octant_is_lowest_not_an_error(self):
        self.assertEqual(security.severity("nonsense"), 0)


class TestSecurityEmploymentPartition(unittest.TestCase):
    """Employment must partition exactly, however the matrix is sliced."""

    SOC_OF = {"19-1029.00": "19-1029", "19-1029.01": "19-1029",
              "19-1029.02": "19-1029", "29-1141.00": "29-1141"}
    EMP = {"19-1029.00": 55_850.0, "19-1029.01": 55_850.0,
           "19-1029.02": 55_850.0, "29-1141.00": 3_000_000.0}

    def test_share_splits_a_soc_evenly_and_preserves_the_total(self):
        shares = security.employment_shares(
            list(self.SOC_OF), self.EMP, self.SOC_OF)
        self.assertAlmostEqual(shares["19-1029.00"], 55_850.0 / 3, places=4)
        self.assertEqual(shares["29-1141.00"], 3_000_000.0)
        self.assertAlmostEqual(sum(shares.values()), 55_850.0 + 3_000_000.0, places=3)

    def test_naive_soc_dedup_overcounts_a_straddling_soc(self):
        """The bug this exists to prevent: three occupations of one SOC landing
        in three different cells, each cell claiming the whole SOC."""
        shares = security.employment_shares(
            list(self.SOC_OF), self.EMP, self.SOC_OF)
        cells = [["19-1029.00"], ["19-1029.01"], ["19-1029.02"]]
        by_share = sum(sum(shares[c] for c in cell) for cell in cells)
        by_soc_dedup = sum(self.EMP[cell[0]] for cell in cells)
        self.assertAlmostEqual(by_share, 55_850.0, places=3)
        self.assertEqual(by_soc_dedup, 55_850.0 * 3)
        self.assertNotEqual(round(by_share), by_soc_dedup)

    def test_occupation_with_no_employment_gets_no_share(self):
        shares = security.employment_shares(["X.00"], {}, {"X.00": "X"})
        self.assertNotIn("X.00", shares)

    def test_cell_shares_sum_to_one(self):
        fates, scores, occs, emp, soc_of, fields = \
            TestSecurityMatrix._corpus(TestSecurityMatrix())
        rows = security.build(fates, scores, occs, emp, fields=fields, soc_of=soc_of)
        report = security.summarise(rows, soc_of)
        for scenario, s in report["scenarios"].items():
            shares = [c["share_employment"] for c in s["by_octant"].values()]
            self.assertAlmostEqual(sum(shares), 1.0, places=3, msg=scenario)
            self.assertEqual(s["total_employment"], 3_000_000.0)

    def test_field_totals_sum_to_the_corpus_total(self):
        fates, scores, occs, emp, soc_of, fields = \
            TestSecurityMatrix._corpus(TestSecurityMatrix())
        rows = security.build(fates, scores, occs, emp, fields=fields, soc_of=soc_of)
        for scenario in ("modest", "substantial", "extreme"):
            fl = [f for f in security.by_field(rows, soc_of)
                  if f["scenario"] == scenario]
            self.assertAlmostEqual(sum(f["total_employment"] for f in fl),
                                   3_000_000.0, places=3)


class TestSharedTheme(unittest.TestCase):
    """Every emitted page draws type and colour from one place.

    The dashboard and the security matrix originally shipped their own
    `-apple-system` stack and their own surface colours, which is what made the
    site read as assembled rather than designed.
    """

    def _heads(self):
        from onet_scraper import dashboard, matrix3d, theme
        return {
            "dashboard": dashboard.TEMPLATE_HEAD,
            "matrix": theme.head("t", matrix3d.CSS, root_class="m3-root",
                                 extra_tokens=matrix3d.SEV_TOKENS,
                                 extra_tokens_dark=matrix3d.SEV_TOKENS_DARK),
        }

    def test_every_page_loads_the_same_three_families(self):
        for name, head in self._heads().items():
            for family in ("Manrope", "DM Serif Display", "IBM Plex Mono"):
                self.assertIn(family, head, f"{name} is missing {family}")

    def test_no_page_falls_back_to_a_system_ui_stack(self):
        for name, head in self._heads().items():
            self.assertNotIn("-apple-system", head, name)
            self.assertNotIn("BlinkMacSystemFont", head, name)

    def test_pages_share_the_paper_and_ink_surfaces(self):
        from onet_scraper import theme
        for name, head in self._heads().items():
            self.assertIn("#faf9f5", head, f"{name} lost the paper surface")
            self.assertIn("#1c1c18", head, f"{name} lost the ink colour")
        # the near-white surface the two pages used before
        for name, head in self._heads().items():
            self.assertNotIn("#fcfcfb", head, name)

    def test_uppercase_labels_carry_tracking(self):
        """Uppercase set at its natural letter-spacing is the defect the user
        saw as bad kerning; the label class must declare tracking."""
        from onet_scraper import theme
        self.assertIn("text-transform: uppercase", theme.BASE)
        self.assertRegex(theme.BASE, r"letter-spacing:\s*\.0[6-9]em|letter-spacing:\s*\.1em")

    def test_figures_use_tabular_numerals(self):
        from onet_scraper import theme
        self.assertIn("font-variant-numeric: tabular-nums", theme.BASE)

    def test_display_serif_is_not_negatively_tracked(self):
        """DM Serif Display is already tightly fitted; the dashboard's
        -0.01/-0.02em collided the terminals at display sizes."""
        from onet_scraper import theme
        self.assertNotIn("letter-spacing: -0.0", theme.BASE)
        self.assertNotIn("letter-spacing:-0.0", theme.BASE)

    def test_extra_tokens_reach_all_three_selectors(self):
        from onet_scraper import theme
        head = theme.head("t", extra_tokens="  --x: red;\n",
                          extra_tokens_dark="  --x: blue;\n")
        self.assertEqual(head.count("--x: red"), 1)      # light root
        self.assertEqual(head.count("--x: blue"), 2)     # media query + data-theme

    def test_dashboard_reads_data_not_window_data(self):
        """const at script scope does not become a window property, so
        window.DATA left the handoff columns blank."""
        from onet_scraper import dashboard
        import inspect
        src = inspect.getsource(dashboard)
        self.assertNotIn("window.DATA?.hand", src)
        self.assertIn("new Map((DATA.hand || [])", src)


class TestSecurityWeighting(unittest.TestCase):
    """No task may be silently dropped from its own occupation's score."""

    def _t(self, **kw):
        base = {"importance": 50.0, "substantial": "unchanged", "error_cost": 50.0,
                "accountability_requirement": 50.0, "judgment_under_uncertainty": 50.0}
        base.update(kw)
        return base

    def test_unrated_task_takes_the_occupations_mean(self):
        tasks = [self._t(importance=80.0), self._t(importance=40.0),
                 self._t(importance="")]
        self.assertEqual(security.weights(tasks), [80.0, 40.0, 60.0])

    def test_wholly_unrated_occupation_falls_back_to_equal_weights(self):
        tasks = [self._t(importance=""), self._t(importance=""), self._t(importance="")]
        self.assertEqual(security.weights(tasks), [1.0, 1.0, 1.0])

    def test_a_surgeon_with_no_importance_ratings_is_not_scored_zero(self):
        """The bug: O*NET rates no task importance for Cardiologists, Pediatric
        and Orthopedic Surgeons or EMTs, the weighted mean divided by zero, and
        they were returned as risk 0.0 and filed under 'Quiet attrition'."""
        tasks = [self._t(importance="", error_cost=95.0,
                         accountability_requirement=95.0,
                         judgment_under_uncertainty=90.0) for _ in range(5)]
        risk = security.removal_risk(tasks)
        self.assertGreater(risk, 80.0)
        self.assertNotEqual(risk, 0.0)
        name, _ = security.octant(20.0, risk, 85.0)
        self.assertEqual(name, "Protect")

    def test_efficiency_is_not_zero_for_a_wholly_unrated_occupation(self):
        tasks = [self._t(importance="", substantial="automated") for _ in range(4)]
        self.assertEqual(security.efficiency(tasks, "substantial"), 100.0)

    def test_partially_rated_occupation_still_counts_every_task(self):
        """Radiologists had 13 of 30 tasks unrated; dropping them changed the
        occupation's cell, so the unrated ones have to carry weight."""
        rated_only = [self._t(importance=90.0, substantial="unchanged")]
        with_unrated = rated_only + [self._t(importance="", substantial="automated")]
        self.assertEqual(security.efficiency(rated_only, "substantial"), 0.0)
        self.assertGreater(security.efficiency(with_unrated, "substantial"), 0.0)

    def test_weights_length_always_matches_task_count(self):
        for n in (0, 1, 5):
            tasks = [self._t() for _ in range(n)]
            self.assertEqual(len(security.weights(tasks)), n)

    def test_negative_and_zero_importance_are_treated_as_missing(self):
        """O*NET's sort sentinel puts -2.0 behind 'Not available'."""
        tasks = [self._t(importance=60.0), self._t(importance=-2.0),
                 self._t(importance=0.0)]
        self.assertEqual(security.weights(tasks), [60.0, 60.0, 60.0])
