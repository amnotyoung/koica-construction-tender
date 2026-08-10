import importlib.util
import base64
import json
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "sync_koica_search_to_supabase.py"
SPEC = importlib.util.spec_from_file_location("sync_koica_search_to_supabase", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class KoicaSearchSyncTests(unittest.TestCase):
    @staticmethod
    def snapshot(**overrides):
        snapshot = {
            "data_version": "sqlite-1.9-test",
            "source_schema_version": "1.9",
            "source_db_sha256": "a" * 64,
            "generated_at": "2026-08-10T12:00:00+00:00",
            "cases": [
                {
                    "case_id": "L2025-00001",
                    "case_kind": "CONSTRUCTION_NOTICE",
                    "facility_family": "보건·의료시설",
                }
            ],
            "related_notices": [],
            "evaluation_projects": [
                {
                    "project_no": "2025-00001",
                    "match_status": "accepted_match",
                    "is_published": True,
                }
            ],
            "evaluation_reports": [
                {
                    "report_id": "koica-eval-test-01",
                    "is_published": True,
                }
            ],
            "evaluation_matches": [
                {
                    "match_id": "match-test-01",
                    "report_id": "koica-eval-test-01",
                    "project_no": "2025-00001",
                    "is_published": True,
                }
            ],
            "evaluation_findings": [
                {
                    "finding_id": "finding-test-01",
                    "match_id": "match-test-01",
                    "search_text": "병원 시설 범위",
                    "is_published": True,
                }
            ],
        }
        snapshot.update(overrides)
        return snapshot

    def test_rejects_forbidden_internal_fields(self):
        snapshot = self.snapshot()
        snapshot["cases"][0]["source_file"] = "private.pdf"
        with self.assertRaisesRegex(ValueError, "forbidden keys"):
            MODULE.validate_snapshot(snapshot)

    def test_rejects_related_notice_for_unknown_case(self):
        snapshot = self.snapshot(
            related_notices=[
                {
                    "case_id": "L2025-99999",
                    "related_bid_base_no": "L2024-00001",
                }
            ]
        )
        with self.assertRaisesRegex(ValueError, "unknown case"):
            MODULE.validate_snapshot(snapshot)

    def test_rejects_missing_source_identity_and_invalid_case_kind(self):
        for field, value, message in (
            ("source_schema_version", "", "source_schema_version"),
            ("source_db_sha256", "not-a-hash", "source_db_sha256"),
            ("generated_at", "2026-08-10", "timezone"),
        ):
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, message):
                    MODULE.validate_snapshot(self.snapshot(**{field: value}))

        invalid_case_snapshot = self.snapshot()
        invalid_case_snapshot["cases"][0]["case_kind"] = "CONTRACT"
        with self.assertRaisesRegex(ValueError, "invalid case_kind"):
            MODULE.validate_snapshot(invalid_case_snapshot)

    def test_rejects_private_evaluation_fields_and_unknown_links(self):
        private_snapshot = self.snapshot()
        private_snapshot["evaluation_reports"][0]["ocr_text_digest"] = "a" * 64
        with self.assertRaisesRegex(ValueError, "forbidden keys"):
            MODULE.validate_snapshot(private_snapshot)

        unknown_match_snapshot = self.snapshot()
        unknown_match_snapshot["evaluation_findings"][0]["match_id"] = "unknown"
        with self.assertRaisesRegex(ValueError, "unknown match"):
            MODULE.validate_snapshot(unknown_match_snapshot)

    def test_sync_payload_carries_source_identity(self):
        snapshot = self.snapshot()

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            @staticmethod
            def read():
                return b'{"cases":1}'

        captured = []

        def fake_urlopen(request, timeout):
            captured.append((request, timeout))
            return Response()

        with mock.patch.object(MODULE.urllib.request, "urlopen", fake_urlopen):
            MODULE.sync_snapshot(
                snapshot,
                "https://project-ref.supabase.co",
                "sb_secret_test-placeholder-0123456789",
                timeout_seconds=12,
            )

        self.assertEqual(len(captured), 2)
        construction_request, construction_timeout = captured[0]
        evaluation_request, evaluation_timeout = captured[1]
        construction_payload = json.loads(construction_request.data)
        evaluation_payload = json.loads(evaluation_request.data)
        for payload in (construction_payload, evaluation_payload):
            self.assertEqual(payload["p_source_schema_version"], "1.9")
            self.assertEqual(payload["p_source_db_sha256"], "a" * 64)
            self.assertEqual(
                payload["p_snapshot_generated_at"],
                "2026-08-10T12:00:00+00:00",
            )
        self.assertIn(
            "/rpc/sync_koica_search_snapshot",
            construction_request.full_url,
        )
        self.assertIn(
            "/rpc/sync_koica_evaluation_snapshot",
            evaluation_request.full_url,
        )
        self.assertEqual(
            evaluation_payload["p_findings"],
            snapshot["evaluation_findings"],
        )
        self.assertEqual(construction_timeout, 12)
        self.assertEqual(evaluation_timeout, 12)

    def test_modern_secret_is_not_used_as_bearer_token(self):
        headers = MODULE.rpc_headers("sb_secret_example")
        self.assertEqual(headers["apikey"], "sb_secret_example")
        self.assertNotIn("Authorization", headers)

    def test_legacy_jwt_is_used_as_bearer_token(self):
        headers = MODULE.rpc_headers("eyJexample")
        self.assertEqual(headers["Authorization"], "Bearer eyJexample")

    def test_remote_target_must_be_path_free_https(self):
        self.assertEqual(
            MODULE.normalize_supabase_url("https://project-ref.supabase.co/"),
            "https://project-ref.supabase.co",
        )
        for value in (
            "http://project-ref.supabase.co",
            "https://project-ref.supabase.co/rest/v1",
            "https://user:password@project-ref.supabase.co",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                MODULE.normalize_supabase_url(value)

    def test_only_server_secret_or_service_role_jwt_is_accepted(self):
        modern = "sb_" + "secret_" + "test-placeholder-0123456789"
        self.assertEqual(MODULE.assert_server_secret_key(modern), modern)
        payload = base64.urlsafe_b64encode(
            json.dumps({"role": "service_role"}).encode("utf-8")
        ).decode("ascii").rstrip("=")
        legacy = f"eyJheader.{payload}.signature"
        self.assertEqual(MODULE.assert_server_secret_key(legacy), legacy)
        for value in ("sb_publishable_example", "eyJbroken", ""):
            with self.subTest(value=value), self.assertRaises(ValueError):
                MODULE.assert_server_secret_key(value)


if __name__ == "__main__":
    unittest.main()
