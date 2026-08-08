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

    def test_export_has_one_case_per_construction_bid_group(self):
        self.assertEqual(len(self.snapshot["cases"]), 156)
        self.assertEqual(len(self.cases), 156)

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
        }
        for row in self.snapshot["cases"] + self.snapshot["related_notices"]:
            self.assertTrue(forbidden.isdisjoint(row))


if __name__ == "__main__":
    unittest.main()
