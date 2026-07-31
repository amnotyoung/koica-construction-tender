from __future__ import annotations

import unittest

from scripts.grade_koica_construction_candidates import (
    construction_bid_relevant,
    find_table_signals,
    grade_project,
    project_key,
)


class CandidateGradingTests(unittest.TestCase):
    def test_priced_boq_signal_requires_line_quantities_and_prices(self):
        matrix = [
            ["Description", "Unit", "Quantity", "Unit Rate", "Amount"],
            ["Excavation", "m3", 10, 5, 50],
            ["Concrete", "m3", 8, 20, 160],
            ["Rebar", "kg", 100, 2, 200],
            ["TOTAL", "", None, None, 410],
        ]
        signals = find_table_signals(matrix, "BOQ")
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].quantity_rows, 3)
        self.assertEqual(signals[0].priced_rows, 3)
        self.assertEqual(signals[0].priced_ratio, 1.0)

    def test_unpriced_boq_signal_preserves_quantity_rows(self):
        matrix = [
            ["Description", "Unit", "Qty", "Unit Price", "Total Amount"],
            ["Excavation", "m3", 10, None, None],
            ["Concrete", "m3", 8, 0, 0],
            ["Rebar", "kg", 100, "", ""],
        ]
        signals = find_table_signals(matrix, "Blank BOQ")
        self.assertEqual(signals[0].quantity_rows, 3)
        self.assertEqual(signals[0].priced_rows, 0)

    def test_goods_price_table_cannot_upgrade_construction_grade(self):
        candidates = [
            {
                "source_record_id": "x:1",
                "project_no_linked": "2099-00001",
                "country_ko": "테스트국",
                "record_title": "센터 건립사업",
                "procurement_category": "",
                "existing_db_project_bid_nos": "L2099-00001-1",
                "unit_cost_potential": "0",
                "gross_floor_area_m2": "",
                "amount_value": "",
            }
        ]
        files = [
            {
                "source_file": "IT equipment.xlsx",
                "sha256": "a",
                "bid_no": "L2099-00001-1",
                "construction_bid_cost_relevant": 0,
                "strong_priced_table": 1,
                "quantity_rows_max": 10,
                "priced_rows_max": 10,
                "boq_filename_candidate": 1,
                "scan_error": "",
                "extension": ".xlsx",
            }
        ]
        project = grade_project("2099-00001", candidates, files)
        self.assertEqual(project["grade"], "C")
        self.assertEqual(project["technical_status"], "U")

    def test_bid_and_alias_boundaries(self):
        self.assertTrue(
            construction_bid_relevant(
                {"contract_type": "공사", "title": "학교 신축공사"}
            )
        )
        self.assertFalse(
            construction_bid_relevant(
                {"contract_type": "물품", "title": "컴퓨터 공급 및 설치"}
            )
        )
        self.assertEqual(
            project_key(
                {
                    "source_record_id": "15085055:325",
                    "project_no_linked": "",
                }
            ),
            "2020-00070",
        )


if __name__ == "__main__":
    unittest.main()
