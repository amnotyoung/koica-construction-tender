import unittest
from pathlib import Path

from scripts.extract_koica_ikhcc_hidden_rates import extract


class IkhccHiddenRateExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.project_root = Path(__file__).resolve().parents[1]
        cls.summary = extract(cls.project_root)

    def test_recovers_all_architectural_boq_items(self) -> None:
        self.assertEqual(self.summary["boq_item_rows"], 561)
        self.assertEqual(self.summary["unique_boq_item_codes"], 355)
        self.assertEqual(self.summary["recovered_item_rows"], 561)
        self.assertEqual(self.summary["recovery_rate"], 1.0)
        section_codes = {
            row["section_code"]
            for row in __import__("json").loads(
                (
                    self.project_root
                    / "outputs"
                    / "koica-only-pilot"
                    / "KOICA_IKHCC_숨김단가_구조화.json"
                ).read_text(encoding="utf-8")
            )["section_rows"]
        }
        self.assertTrue(section_codes)
        self.assertTrue(all(code.isdigit() and 6 <= len(code) <= 8 for code in section_codes))

    def test_rate_library_is_positive_and_consistent(self) -> None:
        self.assertEqual(self.summary["rate_library_rows"], 644)
        self.assertEqual(self.summary["assembly_rate_rows"], 298)
        self.assertEqual(self.summary["direct_resource_rate_rows"], 346)
        self.assertEqual(self.summary["positive_rate_rows"], 644)
        self.assertTrue(
            all(
                row["same_as_hospital"]
                for row in self.summary["library_consistency_checks"]
            )
        )

    def test_recovered_total_and_source_boundary(self) -> None:
        self.assertAlmostEqual(
            self.summary["recovered_architectural_bill_usd"],
            8_372_712.42,
            places=2,
        )
        self.assertEqual(self.summary["visible_component_prices_blank_rows"], 561)
        self.assertEqual(self.summary["currency"], "USD")
        self.assertEqual(self.summary["gross_floor_area_m2"], 5486)

    def test_reannouncement_files_are_identical(self) -> None:
        hashes_by_facility: dict[str, set[str]] = {}
        for row in self.summary["version_lineage"]:
            hashes_by_facility.setdefault(row["facility_en"], set()).add(
                row["sha256"]
            )
        self.assertEqual(set(hashes_by_facility), {"HOSPITAL", "MEP BUILDING", "BRIDGE"})
        self.assertTrue(all(len(values) == 1 for values in hashes_by_facility.values()))


if __name__ == "__main__":
    unittest.main()
