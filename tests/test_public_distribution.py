import hashlib
import re
import sqlite3
import unittest
from contextlib import closing
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATABASE = (
    ROOT
    / "outputs"
    / "koica-construction-distribution"
    / "KOICA_건축사업_사례DB_2016-2025.sqlite"
)
README = (ROOT / "README.md").read_text(encoding="utf-8")
PUBLIC_ACCESS_DOC = (ROOT / "docs" / "public-data-access.md").read_text(
    encoding="utf-8"
)
SEARCH_SERVICE_DOC = (ROOT / "docs" / "koica-search-service.md").read_text(
    encoding="utf-8"
)
AGENT_GUIDE = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
EXPECTED_SHA256 = "9546ff7f35ebbb42c5b3f7a068a42e2059e507b4a77cc5bb331dc9c2284a538d"


class PublicDistributionTests(unittest.TestCase):
    def test_sqlite_integrity_hash_and_scope(self):
        self.assertEqual(DATABASE.stat().st_size, 8_290_304)
        self.assertEqual(
            hashlib.sha256(DATABASE.read_bytes()).hexdigest(), EXPECTED_SHA256
        )

        uri = f"{DATABASE.resolve().as_uri()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            self.assertEqual(
                connection.execute("PRAGMA integrity_check").fetchone()[0], "ok"
            )
            counts = connection.execute(
                """
                SELECT
                  (SELECT COUNT(*) FROM bids),
                  (SELECT COUNT(*) FROM projects),
                  (SELECT COUNT(*) FROM attachments),
                  (SELECT COUNT(*) FROM documents),
                  (SELECT COUNT(*) FROM evidence),
                  (SELECT COUNT(*) FROM area_cost_project_review),
                  (SELECT COUNT(*) FROM evaluation_corpus_files),
                  (SELECT COUNT(*) FROM evaluation_reports),
                  (SELECT COUNT(*) FROM evaluation_project_matches),
                  (SELECT COUNT(*) FROM evaluation_project_screening),
                  (SELECT COUNT(*) FROM evaluation_findings)
                """
            ).fetchone()
            self.assertEqual(
                counts,
                (575, 379, 1000, 3698, 4402, 91, 333, 42, 46, 175, 158),
            )
            self.assertEqual(
                connection.execute(
                    "SELECT value FROM metadata WHERE key = 'schema_version'"
                ).fetchone()[0],
                "1.9",
            )
            absolute_paths = connection.execute(
                """
                SELECT COUNT(*)
                FROM attachments
                WHERE relative_path GLOB '/*'
                   OR relative_path GLOB '[A-Za-z]:*'
                """
            ).fetchone()[0]
            self.assertEqual(absolute_paths, 0)

    def test_public_docs_cover_all_four_access_methods(self):
        for heading in (
            "1. Supabase",
            "2. SQLite DB",
            "3. MCP",
            "4. 플러그인",
        ):
            self.assertIn(heading, README)
            self.assertIn(heading, PUBLIC_ACCESS_DOC)
        self.assertIn("Supabase 공개 DB에 접근해 조회 (권장)", README)
        self.assertIn("SQLite DB를 내려받아 직접 조회 (선택)", README)
        for document in (README, PUBLIC_ACCESS_DOC, SEARCH_SERVICE_DOC, AGENT_GUIDE):
            self.assertNotIn("To be continued", document)
        for tool_name in (
            "koica_construction_data_status",
            "search_koica_construction_cases",
            "get_koica_construction_case",
        ):
            self.assertIn(tool_name, README)
            self.assertIn(tool_name, PUBLIC_ACCESS_DOC)
            self.assertIn(tool_name, AGENT_GUIDE)
        self.assertIn("robots", README)
        self.assertIn("robots", PUBLIC_ACCESS_DOC)
        self.assertIn("robots-policy", AGENT_GUIDE)
        self.assertIn("public Supabase read-only RPC", AGENT_GUIDE)
        self.assertIn("query", AGENT_GUIDE)
        self.assertIn("Do not repeat", AGENT_GUIDE)
        self.assertIn("DESIGN_SUPERVISION_REFERENCE", README)
        self.assertIn("DESIGN_SUPERVISION_REFERENCE", PUBLIC_ACCESS_DOC)
        self.assertIn("source_db_sha256", SEARCH_SERVICE_DOC)
        self.assertIn("source_db_sha256", AGENT_GUIDE)
        self.assertIn("공사 공고군 156건", README)
        self.assertRegex(README, r"설계·감리 참고사례\s+5건")
        for rpc_name in (
            "search_koica_evaluation_findings",
            "get_koica_project_evaluation_findings",
        ):
            self.assertIn(rpc_name, PUBLIC_ACCESS_DOC)
            self.assertIn(rpc_name, SEARCH_SERVICE_DOC)
            self.assertIn(rpc_name, AGENT_GUIDE)
        self.assertIn("공개 승인된 건축 근거 158건", README)
        self.assertIn("koica_evaluation_findings", PUBLIC_ACCESS_DOC)
        self.assertNotIn(
            "종료평가 관련 테이블과 페이지 근거는 현재 SQLite 배포에만 제공",
            PUBLIC_ACCESS_DOC,
        )
        self.assertIn(EXPECTED_SHA256, README)
        self.assertIn(EXPECTED_SHA256, PUBLIC_ACCESS_DOC)

    def test_docs_publish_only_the_supabase_publishable_key(self):
        publishable_keys = re.findall(
            r"sb_publishable_[A-Za-z0-9_-]+", PUBLIC_ACCESS_DOC
        )
        self.assertTrue(publishable_keys)
        self.assertEqual(len(set(publishable_keys)), 1)
        self.assertNotRegex(PUBLIC_ACCESS_DOC, r"sb_secret_[A-Za-z0-9_-]{12,}")
        self.assertNotRegex(PUBLIC_ACCESS_DOC, r"eyJ[A-Za-z0-9_-]{20,}\.")

    def test_database_binary_contains_no_known_secret_markers(self):
        payload = DATABASE.read_bytes()
        for marker in (
            b"sb_secret_",
            b"-----BEGIN PRIVATE KEY-----",
            b"-----BEGIN RSA PRIVATE KEY-----",
            b"AKIA",
        ):
            self.assertNotIn(marker, payload)


if __name__ == "__main__":
    unittest.main()
