import hashlib
import json
import sqlite3
import tempfile
import unittest
import zipfile
from contextlib import closing
from pathlib import Path
from unittest import mock

from scripts import package_distribution
from scripts.build_sqlite_distribution import (
    evaluation_corpus_digest,
    load_evaluation_manifest,
)
from scripts.ingest_koica_evaluation_reports import load_curation
from scripts.snapshot_koica_evaluation_index import validate_snapshot


ROOT = Path(__file__).resolve().parents[1]
DATABASE = (
    ROOT
    / "outputs"
    / "koica-construction-distribution"
    / "KOICA_건축사업_사례DB_2016-2025.sqlite"
)
MANIFEST = (
    ROOT / "data" / "manifests" / "koica_endline_evaluation_reports.json"
)
CURATION = (
    ROOT / "data" / "manifests" / "koica_endline_evaluation_curation.json"
)
INDEX_SNAPSHOT = (
    ROOT
    / "data"
    / "manifests"
    / "koica_evaluation_report_index_2026-08-09.json"
)
PACKAGE = (
    ROOT
    / "outputs"
    / "koica-construction-distribution"
    / "KOICA_건축사업_사례데이터_배포패키지_2016-2025.zip"
)


class EvaluationManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_manifest_covers_corpus_and_review_universe(self):
        manifest = self.manifest
        corpus = manifest["corpus"]
        self.assertEqual(manifest["schema_version"], "1.2")
        self.assertEqual(manifest["target_universe"]["actual_count"], 175)
        self.assertEqual(
            {
                key: manifest["target_universe"][key]
                for key in (
                    "in_area_cost_review_count",
                    "has_works_contract_count",
                    "has_construction_candidate_count",
                )
            },
            {
                "in_area_cost_review_count": 91,
                "has_works_contract_count": 109,
                "has_construction_candidate_count": 149,
            },
        )
        self.assertEqual(len(corpus["inventory"]), 333)
        self.assertEqual(corpus["digest"], evaluation_corpus_digest(corpus["inventory"]))
        self.assertFalse(corpus["raw_pdfs_included"])
        self.assertEqual(corpus["ocr_required_file_count"], 3)
        self.assertEqual(corpus["duplicate_physical_file_count"], 1)
        self.assertEqual(manifest["counts"], {
            "field_definitions": 19,
            "reports": 42,
            "matches": 46,
            "findings": 158,
        })
        self.assertEqual(corpus["selected_local_report_count"], 22)
        self.assertEqual(corpus["selected_official_report_count"], 20)
        self.assertEqual(manifest["official_source"]["screened_post_count"], 586)
        index_snapshot = validate_snapshot(
            manifest["official_source"]["index_snapshot"]
        )
        self.assertEqual(index_snapshot["post_count"], 586)
        self.assertEqual(index_snapshot["page_count"], 66)
        self.assertEqual(
            index_snapshot,
            validate_snapshot(
                json.loads(INDEX_SNAPSHOT.read_text(encoding="utf-8"))
            ),
        )
        self.assertEqual(len(manifest["project_screening"]), 175)
        self.assertEqual(
            sum(row["status"] == "accepted_match" for row in manifest["project_screening"]),
            45,
        )
        self.assertEqual(
            sum(
                row["status"] == "candidate_reviewed_not_accepted"
                for row in manifest["project_screening"]
            ),
            6,
        )

    def test_duplicate_and_ocr_audit_are_explicit(self):
        inventory = self.manifest["corpus"]["inventory"]
        duplicates = [row for row in inventory if row["duplicate_of_source_file"]]
        self.assertEqual(len(duplicates), 1)
        self.assertEqual(duplicates[0]["source_file"], "000000017804_01 (1).pdf")
        self.assertEqual(
            duplicates[0]["duplicate_of_source_file"], "000000017804_01.pdf"
        )
        ocr_files = {
            row["source_file"]
            for row in inventory
            if row["extraction_status"] == "ocr_required"
        }
        self.assertEqual(ocr_files, {
            "000000014611_01.pdf",
            "000000017919_01.pdf",
            "000000018160_01.pdf",
        })

    def test_official_reports_keep_page_and_download_provenance(self):
        official = [
            row for row in self.manifest["reports"]
            if row["source_kind"] == "koica_official_site"
        ]
        self.assertEqual(len(official), 20)
        self.assertEqual(len({row["source_post_id"] for row in official}), 20)
        self.assertTrue(all(
            row["source_page_url"].endswith("/" + row["source_post_id"])
            and row["source_download_url"].endswith(
                "/" + row["source_attachment_id"]
            )
            for row in official
        ))
        curation = load_curation(CURATION)
        curated_audit = {
            row["report_id"]: (
                row["expected_sha256"],
                row["expected_file_bytes"],
                row["expected_page_count"],
            )
            for row in curation["reports"]
            if row.get("source_kind") == "koica_official_site"
        }
        self.assertEqual(
            curated_audit,
            {
                row["report_id"]: (
                    row["sha256"], row["file_bytes"], row["page_count"]
                )
                for row in official
            },
        )
        ocr_reports = [
            row for row in official if row["extraction_status"] == "ocr_text"
        ]
        self.assertEqual(len(ocr_reports), 1)
        self.assertEqual(ocr_reports[0]["report_id"], "koica-official-eval-372")
        self.assertEqual(ocr_reports[0]["ocr_text_page_count"], 115)
        self.assertEqual(len(ocr_reports[0]["ocr_text_digest"]), 64)

    def test_manifest_is_portable_and_prevalidation_rejects_tampering(self):
        payload = MANIFEST.read_text(encoding="utf-8")
        self.assertNotIn("/Users/", payload)
        before_hash = hashlib.sha256(DATABASE.read_bytes()).hexdigest()
        tampered = json.loads(payload)
        tampered["counts"]["reports"] += 1
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tampered.json"
            path.write_text(
                json.dumps(tampered, ensure_ascii=False), encoding="utf-8"
            )
            with self.assertRaises(RuntimeError):
                load_evaluation_manifest(path)
        self.assertEqual(
            hashlib.sha256(DATABASE.read_bytes()).hexdigest(), before_hash
        )

        official_tamper = json.loads(payload)
        official = next(
            row for row in official_tamper["reports"]
            if row["source_kind"] == "koica_official_site"
        )
        official["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "official-tamper.json"
            path.write_text(
                json.dumps(official_tamper, ensure_ascii=False), encoding="utf-8"
            )
            with self.assertRaises(RuntimeError):
                load_evaluation_manifest(path)

        index_tamper = json.loads(payload)
        index_tamper["official_source"]["index_snapshot"]["posts"][0][
            "title"
        ] += " tampered"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "index-tamper.json"
            path.write_text(
                json.dumps(index_tamper, ensure_ascii=False), encoding="utf-8"
            )
            with self.assertRaises((RuntimeError, ValueError)):
                load_evaluation_manifest(path)


class EvaluationDatabaseTests(unittest.TestCase):
    def test_evaluation_tables_are_integral_and_auditable(self):
        uri = f"{DATABASE.resolve().as_uri()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            counts = connection.execute(
                """SELECT
                     (SELECT COUNT(*) FROM evaluation_field_definitions),
                     (SELECT COUNT(*) FROM evaluation_corpus_files),
                     (SELECT COUNT(*) FROM evaluation_reports),
                     (SELECT COUNT(*) FROM evaluation_project_matches),
                     (SELECT COUNT(*) FROM evaluation_project_screening),
                     (SELECT COUNT(*) FROM evaluation_findings),
                     (SELECT COUNT(*) FROM v_project_evaluation_findings)"""
            ).fetchone()
            self.assertEqual(counts, (19, 333, 42, 46, 175, 158, 158))
            self.assertEqual(
                connection.execute(
                    """SELECT COUNT(*) FROM evaluation_findings
                       WHERE review_status <> 'accepted'
                          OR public_excerpt_approved <> 1
                          OR length(trim(evidence_excerpt)) < 20"""
                ).fetchone()[0],
                0,
            )
            self.assertEqual(
                connection.execute(
                    """SELECT COUNT(*)
                       FROM evaluation_project_matches m
                       JOIN evaluation_project_screening p
                         ON p.project_no = m.project_no
                       WHERE m.match_score < 0.85
                          OR m.db_country <> p.country_ko
                          OR m.db_project_name <> p.project_name"""
                ).fetchone()[0],
                0,
            )
            self.assertEqual(
                connection.execute(
                    """SELECT COUNT(*)
                       FROM evaluation_findings f
                       JOIN evaluation_project_matches m ON m.match_id = f.match_id
                       JOIN evaluation_reports r ON r.report_id = m.report_id
                       WHERE f.pdf_page_start < 1
                          OR f.pdf_page_end < f.pdf_page_start
                          OR f.pdf_page_end > r.page_count"""
                ).fetchone()[0],
                0,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT status, COUNT(*) FROM evaluation_project_screening "
                    "GROUP BY status ORDER BY status"
                ).fetchall(),
                [
                    ("accepted_match", 45),
                    ("candidate_reviewed_not_accepted", 6),
                    ("no_accepted_same_project_report", 124),
                ],
            )

    def test_database_records_exact_portable_manifest(self):
        expected_hash = hashlib.sha256(MANIFEST.read_bytes()).hexdigest()
        uri = f"{DATABASE.resolve().as_uri()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            recorded_hash = connection.execute(
                "SELECT value FROM metadata "
                "WHERE key = 'evaluation_manifest_sha256'"
            ).fetchone()[0]
            self.assertEqual(recorded_hash, expected_hash)
            self.assertEqual(
                connection.execute(
                    "SELECT value FROM metadata WHERE key = 'schema_version'"
                ).fetchone()[0],
                "1.9",
            )

    def test_distribution_zip_contains_manifest_but_no_raw_pdfs(self):
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory) / PACKAGE.name
            package_distribution.main(
                zip_path=package,
                manifest_path=Path(directory) / "MANIFEST.json",
            )
            with zipfile.ZipFile(package) as archive:
                names = archive.namelist()
                self.assertIn(
                    "data/manifests/koica_endline_evaluation_reports.json", names
                )
                self.assertIn(
                    "data/manifests/koica_evaluation_report_index_2026-08-09.json",
                    names,
                )
                self.assertFalse(
                    any(name.lower().endswith(".pdf") for name in names)
                )
                package_manifest = json.loads(
                    archive.read("MANIFEST.json").decode("utf-8")
                )
                for record in package_manifest["files"]:
                    payload = archive.read(record["name"])
                    self.assertEqual(len(payload), record["bytes"])
                    self.assertEqual(
                        hashlib.sha256(payload).hexdigest(), record["sha256"]
                    )
        self.assertFalse(package_manifest["raw_evaluation_reports_included"])
        self.assertEqual(
            package_manifest["evaluation_table_counts"]["evaluation_findings"],
            158,
        )

    def test_package_failure_preserves_last_known_good_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory) / PACKAGE.name
            manifest_path = Path(directory) / "MANIFEST.json"
            package_distribution.main(
                zip_path=package, manifest_path=manifest_path
            )
            before_zip = hashlib.sha256(package.read_bytes()).hexdigest()
            before_manifest = hashlib.sha256(
                manifest_path.read_bytes()
            ).hexdigest()
            with mock.patch.object(
                package_distribution.zipfile.ZipFile,
                "write",
                side_effect=RuntimeError("injected archive failure"),
            ):
                with self.assertRaises(RuntimeError):
                    package_distribution.main(
                        zip_path=package, manifest_path=manifest_path
                    )
            self.assertEqual(
                hashlib.sha256(package.read_bytes()).hexdigest(), before_zip
            )
            self.assertEqual(
                hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                before_manifest,
            )
            self.assertFalse(
                package.with_suffix(package.suffix + ".tmp").exists()
            )
            self.assertFalse(
                manifest_path.with_suffix(manifest_path.suffix + ".tmp").exists()
            )

    def test_package_rejects_tampered_official_index_snapshot(self):
        snapshot = json.loads(INDEX_SNAPSHOT.read_text(encoding="utf-8"))
        snapshot["posts"][0]["title"] += " tampered"
        with tempfile.TemporaryDirectory() as directory:
            tampered = Path(directory) / INDEX_SNAPSHOT.name
            tampered.write_text(
                json.dumps(snapshot, ensure_ascii=False), encoding="utf-8"
            )
            package = Path(directory) / PACKAGE.name
            with mock.patch.object(
                package_distribution, "EVALUATION_INDEX_SNAPSHOT", tampered
            ):
                with self.assertRaises(ValueError):
                    package_distribution.main(
                        zip_path=package,
                        manifest_path=Path(directory) / "MANIFEST.json",
                    )
            self.assertFalse(package.exists())


if __name__ == "__main__":
    unittest.main()
