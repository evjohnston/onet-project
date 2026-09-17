"""Parser contract tests.

Fixtures reproduce O*NET's real markup (attribute names, nesting, the collapsed
rows and the "N displayed" counter) in miniature, so a change in the live site's
structure fails here rather than silently emptying a column.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from onet_scraper.parse import (  # noqa: E402
    ParseError,
    parse_dwas,
    parse_occupation,
    parse_stem_index,
    parse_tasks,
    soup_of,
)

INDEX_HTML = """
<html><body>
<h2 id="f1">Technologists and Technicians &mdash; Computer and Mathematical</h2>
<table class="table tablesorter">
  <thead><tr><th>Code</th><th>Occupation</th><th>Occupation Types</th></tr></thead>
  <tbody>
    <tr>
      <td data-title="Code">15-2011.00</td>
      <td data-title="Occupation">
        <a href="https://www.onetonline.org/link/summary/15-2011.00">Actuaries</a>
        <a href="/help/bright/15-2011.00"><i class="fakd fa-bright-outlook bright-outlook-icon"></i>
        <small>Bright Outlook</small></a>
      </td>
      <td data-title="Occupation Types">Research, Development, Design, and Practitioners</td>
    </tr>
    <tr>
      <td data-title="Code">17-2051.00</td>
      <td data-title="Occupation"><a href="/link/summary/17-2051.00">Civil Engineers</a></td>
      <td data-title="Occupation Types">Managerial</td>
    </tr>
    <tr><td data-title="Code">&nbsp;</td><td data-title="Occupation">spacer</td></tr>
  </tbody>
</table>
</body></html>
"""

DETAILS_HTML = """
<html><body>
<div id="content">
  <h1><span class="main">Actuaries</span>
      <span class="sub"><div>15-2011.00</div>
      <a>Bright Outlook</a><a>Updated 2026</a></span></h1>
  <p>Analyze statistical data and construct probability tables.</p>
  <p><b>Sample of reported job titles:</b> Actuarial Analyst, Consulting Actuary, Health Actuary</p>

  <div id="Tasks" class="reportsection">
    <h2 class="report">Tasks</h2>
    <div><button>10 of All 2 displayed</button></div>
    <table class="table tablesorter">
      <thead><tr><th>Importance</th><th>Category</th><th>Task</th></tr></thead>
      <tbody>
        <tr>
          <td data-title="Importance" data-text="94"><span>94</span></td>
          <td data-title="Category">Core</td>
          <td data-title="Task" data-text="Analyze data to determine premium rates.">
            <div class="order-2">Analyze data to determine premium rates.</div>
            <a href="/link/moreinfo/task/24015?r=details&amp;j=15-2011.00">more</a>
          </td>
        </tr>
        <tr class="long_Tasks collapse">
          <td data-title="Importance" data-text="67"><span>67</span></td>
          <td data-title="Category">Supplemental</td>
          <td data-title="Task" data-text="Construct probability tables.">
            <div class="order-2">Construct probability tables.</div>
            <a href="/link/moreinfo/task/24016?r=details">more</a>
          </td>
        </tr>
      </tbody>
    </table>
  </div>

  <div id="DetailedWorkActivities" class="reportsection">
    <h2 class="report">Detailed Work Activities</h2>
    <div><button>10 of All 2 displayed</button></div>
    <ul class="list-unstyled m-0">
      <li><div class="d-flex"><div class="order-2">Manage financial activities of the organization.</div>
        <a href="/link/moreinfo/dwa/4.A.4.b.4.h.6?r=details">more</a></div></li>
      <li><div class="d-flex"><div class="order-2">Analyze data to inform operational decisions.</div>
        <a href="/link/moreinfo/dwa/4.A.2.a.4.g.12?r=details">more</a></div></li>
    </ul>
  </div>

  <div id="JobZone" class="reportsection">
    <table><tr><td>Title</td><td>Job Zone Four: Considerable Preparation Needed</td></tr></table>
  </div>
</div>
</body></html>
"""

# Occupations with no incumbent ratings render Tasks as a <ul>, not a table
# (e.g. 19-4044.00 Hydrologic Technicians). Same section id, different shape.
UNRATED_TASKS_HTML = """
<html><body><div id="content">
  <h1><span class="main">Hydrologic Technicians</span>
      <span class="sub"><div>19-4044.00</div></span></h1>
  <div id="Tasks" class="reportsection">
    <h2 class="report">Tasks</h2>
    <div><button>10 of All 2 displayed</button></div>
    <ul class="list-unstyled m-0">
      <li><div class="d-flex"><div class="order-2">Analyze ecological data about pollution.</div>
        <a href="/link/moreinfo/task/22292?r=details&amp;j=19-4044.00">more</a></div></li>
      <li><div class="d-flex"><div class="order-2">Answer technical questions from hydrologists.</div>
        <a href="/link/moreinfo/task/22293?r=details">more</a></div></li>
    </ul>
  </div>
</div></body></html>
"""


# Tasks O*NET has not yet rated show "Not available" with a negative data-text
# sort sentinel (-2). That is missing data, not a score of -2.
UNAVAILABLE_SCORE_HTML = DETAILS_HTML.replace(
    '''<td data-title="Importance" data-text="67"><span>67</span></td>
          <td data-title="Category">Supplemental</td>''',
    '''<td data-title="Importance" data-text="-2">Not available</td>
          <td data-title="Category">New</td>''',
)


class TestStemIndex(unittest.TestCase):
    def test_sections_rows_and_anchor(self):
        sections = parse_stem_index(INDEX_HTML)
        self.assertEqual(len(sections), 1)
        section = sections[0]
        self.assertEqual(section["anchor"], "f1")
        self.assertEqual(len(section["rows"]), 2, "the spacer row must be dropped")
        first = section["rows"][0]
        self.assertEqual(first["onet_soc_code"], "15-2011.00")
        self.assertEqual(first["title"], "Actuaries")
        self.assertTrue(first["bright_outlook"])
        self.assertFalse(section["rows"][1]["bright_outlook"])

    def test_missing_table_raises(self):
        with self.assertRaises(ParseError):
            parse_stem_index("<html><body><p>nothing here</p></body></html>")


class TestTasks(unittest.TestCase):
    def setUp(self):
        self.soup = soup_of(DETAILS_HTML)

    def test_collapsed_rows_are_included(self):
        tasks, declared = parse_tasks(self.soup)
        self.assertEqual(len(tasks), 2)
        self.assertEqual(declared, 2, "must read the page's own row count for cross-checking")

    def test_fields(self):
        tasks, _ = parse_tasks(self.soup)
        self.assertEqual(tasks[0]["task_id"], 24015)
        self.assertEqual(tasks[0]["importance"], 94.0)
        self.assertEqual(tasks[0]["task_category"], "Core")
        self.assertEqual(tasks[0]["task"], "Analyze data to determine premium rates.")
        self.assertEqual(tasks[1]["task_category"], "Supplemental")
        self.assertIsNone(tasks[0]["relevance"])

    def test_column_order_is_irrelevant(self):
        swapped = DETAILS_HTML.replace(
            '<th>Importance</th><th>Category</th><th>Task</th>',
            '<th>Task</th><th>Category</th><th>Importance</th>',
        )
        tasks, _ = parse_tasks(soup_of(swapped))
        self.assertEqual(tasks[0]["importance"], 94.0)
        self.assertEqual(tasks[0]["task_id"], 24015)

    def test_missing_section_is_empty_not_fatal(self):
        tasks, declared = parse_tasks(soup_of("<html><body></body></html>"))
        self.assertEqual(tasks, [])
        self.assertIsNone(declared)


class TestDwas(unittest.TestCase):
    def test_ids_and_titles(self):
        dwas, declared = parse_dwas(soup_of(DETAILS_HTML))
        self.assertEqual(declared, 2)
        self.assertEqual(
            [d["dwa_id"] for d in dwas],
            ["4.A.4.b.4.h.6", "4.A.2.a.4.g.12"],
        )
        self.assertEqual(dwas[0]["dwa_title"], "Manage financial activities of the organization.")


class TestOccupation(unittest.TestCase):
    def test_full_record(self):
        record = parse_occupation(DETAILS_HTML, expected_code="15-2011.00")
        self.assertEqual(record["title"], "Actuaries")
        self.assertEqual(record["onet_soc_code"], "15-2011.00")
        self.assertEqual(record["updated_year"], 2026)
        self.assertTrue(record["bright_outlook"])
        self.assertEqual(record["job_zone"], 4)
        self.assertIn("probability tables", record["description"])
        self.assertEqual(record["reported_job_titles"][0], "Actuarial Analyst")
        self.assertEqual(record["counts"],
                         {"tasks_parsed": 2, "tasks_declared": 2,
                          "dwas_parsed": 2, "dwas_declared": 2})

    def test_wrong_code_raises(self):
        with self.assertRaises(ParseError):
            parse_occupation(DETAILS_HTML, expected_code="11-1011.00")


class TestUnratedTaskList(unittest.TestCase):
    """The list layout must yield the same records, minus the ratings."""

    def test_tasks_parsed_from_list(self):
        tasks, declared = parse_tasks(soup_of(UNRATED_TASKS_HTML))
        self.assertEqual(declared, 2)
        self.assertEqual(len(tasks), 2, "list-layout tasks must not be dropped")
        self.assertEqual(tasks[0]["task_id"], 22292)
        self.assertEqual(tasks[0]["task"], "Analyze ecological data about pollution.")
        self.assertIsNone(tasks[0]["importance"])
        self.assertIsNone(tasks[0]["task_category"])
        self.assertEqual(tasks[1]["display_rank"], 2)

    def test_counts_reconcile(self):
        record = parse_occupation(UNRATED_TASKS_HTML, expected_code="19-4044.00")
        counts = record["counts"]
        self.assertEqual(counts["tasks_parsed"], counts["tasks_declared"])


class TestUnavailableScores(unittest.TestCase):
    def test_sentinel_becomes_none(self):
        tasks, _ = parse_tasks(soup_of(UNAVAILABLE_SCORE_HTML))
        self.assertEqual(tasks[1]["task_category"], "New")
        self.assertIsNone(tasks[1]["importance"],
                          "the -2 sort sentinel must not leak in as a rating")
        self.assertEqual(tasks[0]["importance"], 94.0, "real scores still parse")


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestMarkdownTableAlignment(unittest.TestCase):
    """Numeric table columns must be right-aligned or they cannot be read down."""

    def _render(self, md):
        from onet_scraper.markdown import render
        return render(md)

    def test_numeric_column_is_detected_and_right_aligned(self):
        html = self._render("| Thing | Count |\n| --- | --- |\n"
                            "| a | 287 |\n| b | 5,717 |\n")
        self.assertIn('<th class="num">Count</th>', html)
        self.assertIn('<td class="num">287</td>', html)
        self.assertIn("<td>a</td>", html)

    def test_explicit_right_alignment_is_honoured(self):
        """The separator row is read from its own line - an earlier version read
        it after the parser had advanced past the body, so `---:` was ignored."""
        html = self._render("| Cell | Modest |\n| --- | ---: |\n"
                            "| trap | 37 / 10.1% |\n| protect | 130 / 50.4% |\n")
        self.assertIn('<th class="num">Modest</th>', html)
        self.assertIn('<td class="num">37 / 10.1%</td>', html)

    def test_explicit_centre_alignment(self):
        html = self._render("| A | B |\n| --- | :---: |\n| x | y |\n| p | q |\n")
        self.assertIn('<th class="mid">B</th>', html)

    def test_explicit_left_beats_numeric_detection(self):
        html = self._render("| Year | Note |\n| :--- | --- |\n"
                            "| 2019 | a |\n| 2024 | b |\n")
        self.assertIn("<th>Year</th>", html)
        self.assertNotIn('<th class="num">Year</th>', html)

    def test_mixed_column_stays_left(self):
        """A version column holding '31.0' and a comma-separated list is not a
        figure column, and right-aligning it would be wrong."""
        html = self._render("| Source | Version |\n| --- | --- |\n"
                            "| a | 31.0 |\n| b | 20.1, 22.0, 24.0 |\n")
        self.assertIn("<th>Version</th>", html)
        self.assertNotIn('class="num">20.1, 22.0, 24.0', html)

    def test_single_row_table_is_not_right_aligned_on_coincidence(self):
        html = self._render("| Label | Value |\n| --- | --- |\n| only | 7 |\n")
        self.assertIn("<th>Value</th>", html)

    def test_percentages_and_negatives_count_as_numeric(self):
        html = self._render("| K | V |\n| --- | --- |\n"
                            "| a | 30% |\n| b | -2.5 |\n| c | 1,024 |\n")
        self.assertIn('<th class="num">V</th>', html)

    def test_short_row_does_not_raise(self):
        html = self._render("| A | B | C |\n| --- | --- | --- |\n| 1 | 2 |\n")
        self.assertIn("<table>", html)


class TestSmokeAssertions(unittest.TestCase):
    """The page checks themselves, which had their own version of the bug."""

    TWO_TABLES = """
    <table><thead><tr><th>Occupation</th><th>Workers</th></tr></thead><tbody>
      <tr><td>a</td><td>n/a</td></tr>
      <tr><td>b</td><td>n/a</td></tr>
      <tr><td>c</td><td>n/a</td></tr>
    </tbody></table>
    <table><thead><tr><th>Task</th><th>Score</th></tr></thead><tbody>
      <tr><td>t1</td><td>91</td></tr>
      <tr><td>t2</td><td>84</td></tr>
    </tbody></table>"""

    def test_extraction_is_scoped_to_the_table_declaring_the_header(self):
        """The bug: the column index from one table's header was applied to
        every <tr> in the document, so rows borrowed from a second table masked
        a column that had come through entirely empty."""
        from onet_scraper.smoke import _cells
        vals = _cells("Workers")(self.TWO_TABLES)
        self.assertEqual(vals, ["n/a", "n/a", "n/a"])
        self.assertNotIn("91", vals)

    def test_a_wholly_placeholder_column_fails(self):
        from onet_scraper.smoke import _mostly_populated
        self.assertFalse(_mostly_populated("Workers")(self.TWO_TABLES))

    def test_a_populated_column_passes(self):
        from onet_scraper.smoke import _mostly_populated
        self.assertTrue(_mostly_populated("Score")(self.TWO_TABLES))

    def test_partial_gaps_are_tolerated(self):
        """Some occupations genuinely have no BLS employment match, so the test
        is a fraction, not a demand that every cell be filled."""
        from onet_scraper.smoke import _mostly_populated
        dom = ("<table><thead><tr><th>Workers</th></tr></thead><tbody>"
               + "<tr><td>1,000</td></tr>" * 7 + "<tr><td>n/a</td></tr>" * 3
               + "</tbody></table>")
        self.assertTrue(_mostly_populated("Workers")(dom))

    def test_a_missing_column_fails_rather_than_passing_vacuously(self):
        from onet_scraper.smoke import _mostly_populated
        self.assertFalse(_mostly_populated("Nonexistent")(self.TWO_TABLES))

    def test_em_dash_counts_as_a_placeholder(self):
        from onet_scraper.smoke import PLACEHOLDERS
        self.assertIn("—", PLACEHOLDERS)

    def test_every_published_page_has_assertions(self):
        from onet_scraper.smoke import PAGES
        for page in ("index.html", "story.html", "dashboard.html",
                     "methodology.html", "security_matrix.html"):
            self.assertIn(page, PAGES)
            self.assertTrue(PAGES[page], f"{page} has no assertions")
