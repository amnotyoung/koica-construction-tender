import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "export_koica_search_data.py"
DB_PATH = (
    ROOT
    / "outputs"
    / "koica-construction-distribution"
    / "KOICA_건축사업_사례DB_2016-2025.sqlite"
)

SPEC = importlib.util.spec_from_file_location("export_koica_search_data", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class KoicaSearchExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = MODULE.build_snapshot(DB_PATH)
        cls.cases = {row["case_id"]: row for row in cls.snapshot["cases"]}

    def test_export_has_construction_groups_and_reviewed_design_references(self):
        self.assertEqual(len(self.snapshot["cases"]), 161)
        self.assertEqual(len(self.cases), 161)
        self.assertEqual(
            sum(
                row["case_kind"] == MODULE.DESIGN_SUPERVISION_REFERENCE
                for row in self.snapshot["cases"]
            ),
            5,
        )

    def test_dangkao_design_reference_is_published_without_becoming_a_contract(self):
        dangkao = self.cases["L2025-00036"]
        self.assertEqual(dangkao["case_kind"], MODULE.DESIGN_SUPERVISION_REFERENCE)
        self.assertEqual(dangkao["project_no"], "2024-00015")
        self.assertEqual(dangkao["facility_family"], "보건·의료시설")
        self.assertEqual(dangkao["gross_floor_area_m2"], 3700.0)
        self.assertEqual(dangkao["construction_cost_usd"], 6600000.0)
        self.assertEqual(dangkao["amount_stage_code"], "DESIGN_ESTIMATE")
        self.assertEqual(dangkao["evidence_grade"], "C")

    def test_medical_family_recovers_coarse_source_classifications(self):
        self.assertEqual(self.cases["L2021-00016"]["facility_type"], "기타·미분류")
        self.assertEqual(
            self.cases["L2021-00016"]["facility_family"], "보건·의료시설"
        )
        self.assertIn("병원", self.cases["L2021-00016"]["search_text"])
        self.assertEqual(
            self.cases["L2024-00031"]["facility_family"], "보건·의료시설"
        )

    def test_snapshot_identifies_exact_source_database(self):
        self.assertEqual(self.snapshot["source_schema_version"], "1.9")
        self.assertRegex(self.snapshot["source_db_sha256"], r"^[0-9a-f]{64}$")

    def test_evaluation_snapshot_has_reviewed_public_counts(self):
        self.assertEqual(len(self.snapshot["evaluation_projects"]), 175)
        self.assertEqual(len(self.snapshot["evaluation_reports"]), 42)
        self.assertEqual(len(self.snapshot["evaluation_matches"]), 46)
        self.assertEqual(len(self.snapshot["evaluation_findings"]), 158)
        self.assertEqual(
            sum(
                row["match_status"] == "accepted_match"
                for row in self.snapshot["evaluation_projects"]
            ),
            45,
        )

    def test_evaluation_findings_keep_public_page_evidence(self):
        findings = {
            row["finding_id"]: row
            for row in self.snapshot["evaluation_findings"]
        }
        finding = findings["f-017729-area"]
        self.assertEqual(finding["match_id"], "match-2016-00043-017729")
        self.assertEqual(finding["field_code"], "facility_area")
        self.assertEqual(finding["value_numeric"], 950.0)
        self.assertEqual(finding["unit"], "m2")
        self.assertEqual(finding["pdf_page_start"], 42)
        self.assertIn("약 950", finding["evidence_excerpt"])
        self.assertIn("나이지리아", finding["search_text"])

    def test_current_review_overrides_legacy_amount_and_country(self):
        jordan = self.cases["L2018-00020"]
        self.assertEqual(jordan["country_ko"], "요르단")
        self.assertEqual(jordan["gross_floor_area_m2"], 7599.0)
        self.assertEqual(jordan["construction_cost_usd"], 5354000.0)
        self.assertEqual(jordan["nominal_unit_usd_m2"], 704.57)
        self.assertEqual(jordan["evidence_grade"], "C")

        uzbekistan = self.cases["L2019-00021"]
        self.assertEqual(uzbekistan["country_ko"], "우즈베키스탄")

    def test_unreviewed_construction_keeps_area_null_and_parses_ceiling(self):
        zarqa = self.cases["L2019-00016"]
        self.assertIsNone(zarqa["gross_floor_area_m2"])
        self.assertEqual(zarqa["construction_cost_usd"], 5425100.0)
        self.assertIsNone(zarqa["nominal_unit_usd_m2"])
        self.assertEqual(zarqa["amount_stage_code"], "NOTICE_EXECUTION_CEILING_RAW")

    def test_related_supervision_notice_is_available(self):
        supervision = [
            row
            for row in self.snapshot["related_notices"]
            if row["case_id"] == "L2019-00016"
            and row["related_bid_base_no"] == "L2019-00015"
        ]
        self.assertEqual(len(supervision), 1)
        self.assertEqual(supervision[0]["relation_type"], "SUPERVISION")
        self.assertEqual(supervision[0]["amount_usd"], 186000.0)

    def test_public_snapshot_excludes_internal_evidence_paths(self):
        forbidden = {
            "source_file",
            "source_locator",
            "relative_path",
            "sha256",
            "evidence_text",
            "ocr_text_digest",
            "review_note",
            "extraction_method",
        }
        public_rows = []
        for collection in (
            "cases",
            "related_notices",
            "evaluation_projects",
            "evaluation_reports",
            "evaluation_matches",
            "evaluation_findings",
        ):
            public_rows.extend(self.snapshot[collection])
        for row in public_rows:
            self.assertTrue(forbidden.isdisjoint(row))


if __name__ == "__main__":
    unittest.main()
