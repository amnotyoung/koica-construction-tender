from __future__ import annotations

import unittest

from scripts.extract_koica_uganda_boq import (
    DEFAULT_SOURCE,
    compare_versions,
    default_primary_source,
    extract_boq,
    normalize_unit,
)


class KoicaUgandaBoqExtractionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.primary_source = default_primary_source()
        cls.primary = extract_boq(cls.primary_source)
        cls.comparison = extract_boq(DEFAULT_SOURCE)

    def test_unit_normalization(self) -> None:
        self.assertEqual(normalize_unit("SM"), "m²")
        self.assertEqual(normalize_unit("CM"), "m³")
        self.assertEqual(normalize_unit("METERS"), "m")
        self.assertEqual(normalize_unit("PIECES"), "no.")

    def test_expected_unpriced_boq_inventory(self) -> None:
        summary = self.primary["summary"]
        self.assertEqual(summary["bid_no"], "L2023-00009-1")
        self.assertEqual(summary["detail_sheets"], 11)
        self.assertEqual(summary["item_rows"], 540)
        self.assertEqual(summary["quantified_items"], 501)
        self.assertEqual(summary["positive_quantity_items"], 462)
        self.assertEqual(summary["zero_quantity_items"], 39)
        self.assertEqual(summary["unquantified_items"], 39)
        self.assertEqual(summary["priced_items"], 0)

    def test_market_scope_conflict_is_preserved(self) -> None:
        market = next(
            row
            for row in self.primary["summary"]["sheet_stats"]
            if row["sheet"] == "MARKET SHED."
        )
        self.assertEqual(market["scope_multiplier_scenario_low"], 5)
        self.assertEqual(market["scope_multiplier_scenario_high"], 6)

    def test_rebid_changes_labels_not_item_quantities(self) -> None:
        comparison = compare_versions(
            self.primary_source,
            self.primary,
            DEFAULT_SOURCE,
            self.comparison,
        )
        self.assertEqual(comparison["primary_rows"], 891)
        self.assertEqual(comparison["comparison_rows"], 891)
        self.assertEqual(comparison["description_rows_changed"], 5)
        self.assertEqual(comparison["item_quantity_rows_changed"], 0)


if __name__ == "__main__":
    unittest.main()
