import sqlite3
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = (
    ROOT
    / "outputs"
    / "koica-construction-distribution"
    / "KOICA_건축사업_사례DB_2016-2025.sqlite"
)


class KoicaOnlyDistributionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.connection = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)

    @classmethod
    def tearDownClass(cls):
        cls.connection.close()

    def test_schema_has_no_external_donor_objects(self):
        rows = self.connection.execute(
            """SELECT type, name
               FROM sqlite_master
               WHERE lower(name) LIKE '%external%'
                  OR lower(name) LIKE '%world_bank%'
                  OR lower(name) LIKE '%future_survey%'
                  OR lower(COALESCE(sql, '')) LIKE '%external_%'
                  OR lower(COALESCE(sql, '')) LIKE '%world bank%'"""
        ).fetchall()
        self.assertEqual(rows, [])

    def test_metadata_and_price_sources_have_no_world_bank_data(self):
        metadata = self.connection.execute(
            """SELECT key, value
               FROM metadata
               WHERE lower(key || ' ' || value) LIKE '%world bank%'
                  OR lower(key || ' ' || value) LIKE '%worldbank%'
                  OR lower(key || ' ' || value) LIKE '%external_%'"""
        ).fetchall()
        sources = self.connection.execute(
            """SELECT source_id, provider, provider_url
               FROM price_index_sources
               WHERE source_id GLOB 'WB_*'
                  OR lower(provider) LIKE '%world bank%'
                  OR lower(provider_url) LIKE '%worldbank%'"""
        ).fetchall()
        self.assertEqual(metadata, [])
        self.assertEqual(sources, [])
        self.assertEqual(
            self.connection.execute(
                "SELECT COALESCE(SUM(fallback_loaded), 0) "
                "FROM national_index_source_audit"
            ).fetchone()[0],
            0,
        )

    def test_koica_inventory_and_relations_are_preserved(self):
        expected = {
            "datasets": 2,
            "bids": 575,
            "details": 379,
            "projects": 379,
            "attachments": 1000,
            "documents": 3698,
            "evidence": 4402,
            "reviewed_cases": 66,
            "area_cost_notice_review": 170,
            "area_cost_bid_group_review": 154,
            "area_cost_project_review": 91,
            "area_cost_review_summary": 1,
            "fee_benchmarks": 7,
            "price_index_sources": 3,
            "price_index_values": 60,
        }
        actual = {
            table: self.connection.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]
            for table in expected
        }
        self.assertEqual(actual, expected)
        self.assertEqual(
            self.connection.execute("PRAGMA integrity_check").fetchone()[0],
            "ok",
        )
        self.assertEqual(
            self.connection.execute("PRAGMA foreign_key_check").fetchall(),
            [],
        )

    def test_area_cost_review_is_queryable_without_inheriting_legacy_grades(self):
        self.assertEqual(
            dict(
                self.connection.execute(
                    """SELECT compact_grade, COUNT(*)
                       FROM area_cost_project_review
                       GROUP BY compact_grade"""
                ).fetchall()
            ),
            {"A": 2, "B": 5, "C": 53, "C?": 7, "U": 7, "X": 17},
        )
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM v_area_cost_ready_projects"
            ).fetchone()[0],
            60,
        )
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM area_cost_project_review "
                "WHERE direct_future_estimate_ready = 1"
            ).fetchone()[0],
            1,
        )
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM area_cost_notice_review "
                "WHERE compact_grade IN ('U','X') "
                "AND screening_unit_usd_m2 IS NOT NULL"
            ).fetchone()[0],
            0,
        )

    def test_dataset_metadata_matches_child_rows(self):
        for dataset_id, bids, details, attachments, documents, evidence in (
            self.connection.execute(
                """SELECT dataset_id, bids_count, details_count,
                          attachments_count, documents_count, evidence_count
                   FROM datasets"""
            )
        ):
            recorded = (bids, details, attachments, documents, evidence)
            actual = tuple(
                self.connection.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE dataset_id = ?",
                    (dataset_id,),
                ).fetchone()[0]
                for table in (
                    "bids",
                    "details",
                    "attachments",
                    "documents",
                    "evidence",
                )
            )
            self.assertEqual(actual, recorded)


if __name__ == "__main__":
    unittest.main()
