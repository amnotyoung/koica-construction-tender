import importlib.util
import base64
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "sync_koica_search_to_supabase.py"
SPEC = importlib.util.spec_from_file_location("sync_koica_search_to_supabase", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class KoicaSearchSyncTests(unittest.TestCase):
    def test_rejects_forbidden_internal_fields(self):
        snapshot = {
            "data_version": "test",
            "cases": [{"case_id": "L2025-00001", "source_file": "private.pdf"}],
            "related_notices": [],
        }
        with self.assertRaisesRegex(ValueError, "forbidden keys"):
            MODULE.validate_snapshot(snapshot)

    def test_rejects_related_notice_for_unknown_case(self):
        snapshot = {
            "data_version": "test",
            "cases": [{"case_id": "L2025-00001"}],
            "related_notices": [
                {
                    "case_id": "L2025-99999",
                    "related_bid_base_no": "L2024-00001",
                }
            ],
        }
        with self.assertRaisesRegex(ValueError, "unknown case"):
            MODULE.validate_snapshot(snapshot)

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
