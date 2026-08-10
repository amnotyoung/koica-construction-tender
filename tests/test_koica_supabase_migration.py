import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = next((ROOT / "supabase" / "migrations").glob("*_create_koica_search_api.sql"))
SQL = MIGRATION.read_text(encoding="utf-8")
PROJECTION_MIGRATION = next(
    (ROOT / "supabase" / "migrations").glob(
        "*_add_koica_construction_search_projection.sql"
    )
)
PROJECTION_SQL = PROJECTION_MIGRATION.read_text(encoding="utf-8")
PUBLIC_READ_MIGRATION = next(
    (ROOT / "supabase" / "migrations").glob(
        "*_expose_koica_construction_reads_to_public.sql"
    )
)
PUBLIC_READ_SQL = PUBLIC_READ_MIGRATION.read_text(encoding="utf-8")
REVIEWED_REFERENCE_MIGRATION = next(
    (ROOT / "supabase" / "migrations").glob(
        "*_include_reviewed_reference_cases.sql"
    )
)
REVIEWED_REFERENCE_SQL = REVIEWED_REFERENCE_MIGRATION.read_text(encoding="utf-8")
CONFIG = (ROOT / "supabase" / "config.toml").read_text(encoding="utf-8")


class KoicaSupabaseMigrationTests(unittest.TestCase):
    def test_public_read_model_tables_have_rls(self):
        self.assertIn("alter table koica_search.cases enable row level security", SQL)
        self.assertIn("alter table koica_search.related_notices enable row level security", SQL)
        self.assertIn("to service_role\n  using (is_published)", SQL)

    def test_base_migration_starts_service_role_only(self):
        self.assertNotRegex(SQL, r"grant (?:select|execute).*?to (?:anon|authenticated)")
        self.assertIn("grant usage on schema koica_search to service_role", SQL)
        for function_signature in (
            "search_koica_reference_cases(text, text, text, text, numeric, integer)",
            "get_koica_reference_case(text)",
            "get_koica_related_notices(text)",
            "get_koica_search_status()",
        ):
            self.assertIn(
                f"grant execute on function public.{function_signature}\n  to service_role",
                SQL,
            )

    def test_read_functions_are_invoker_and_sync_is_service_role_only(self):
        for function_name in (
            "search_koica_reference_cases",
            "get_koica_reference_case",
            "get_koica_related_notices",
            "get_koica_search_status",
        ):
            match = re.search(
                rf"create or replace function public\.{function_name}.*?as \$\$",
                SQL,
                flags=re.DOTALL,
            )
            self.assertIsNotNone(match)
            self.assertIn("security invoker", match.group(0))

        sync_function = re.search(
            r"create or replace function public\.sync_koica_search_snapshot.*?as \$\$",
            SQL,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(sync_function)
        self.assertIn("security definer", sync_function.group(0))
        self.assertIn(
            "grant execute on function public.sync_koica_search_snapshot(jsonb, jsonb, text)\n"
            "  to service_role",
            SQL,
        )

    def test_pgroonga_extension_is_not_version_pinned(self):
        self.assertIn("create extension if not exists pgroonga with schema extensions", SQL)
        self.assertNotRegex(SQL, r"create extension[^;]+version")

    def test_empty_case_snapshot_is_rejected(self):
        self.assertIn("p_cases must be a non-empty JSON array", SQL)

    def test_mcp_projection_is_service_role_only_and_includes_bid_number(self):
        signature = (
            "public.search_koica_construction_cases(\n"
            "  text,\n"
            "  text,\n"
            "  text,\n"
            "  text,\n"
            "  numeric,\n"
            "  integer\n"
            ")"
        )
        self.assertIn("security invoker", PROJECTION_SQL)
        self.assertIn("'representative_bid_no'", PROJECTION_SQL)
        self.assertIn(
            f"revoke all on function {signature} from public, anon, authenticated, service_role",
            PROJECTION_SQL,
        )
        self.assertIn(
            f"grant execute on function {signature} to service_role",
            PROJECTION_SQL,
        )

    def test_public_read_policies_only_expose_published_rows(self):
        for table_name in ("cases", "related_notices"):
            policy = re.search(
                rf'create policy "public reads published [^"]+"'
                rf".*?on koica_search\.{table_name}"
                r".*?for select"
                r".*?to anon, authenticated"
                r".*?using \(is_published\)",
                PUBLIC_READ_SQL,
                flags=re.DOTALL,
            )
            self.assertIsNotNone(policy)
            self.assertIn(
                f"grant select on table koica_search.{table_name} to anon, authenticated",
                PUBLIC_READ_SQL,
            )

    def test_public_views_are_invoker_only_and_omit_search_internals(self):
        for view_name in (
            "koica_construction_cases",
            "koica_construction_related_notices",
        ):
            view = re.search(
                rf"create or replace view public\.{view_name}.*?;",
                PUBLIC_READ_SQL,
                flags=re.DOTALL,
            )
            self.assertIsNotNone(view)
            self.assertIn("security_invoker = true", view.group(0))
            self.assertIn("security_barrier = true", view.group(0))
            self.assertNotIn("security definer", view.group(0))

        cases_projection = re.search(
            r"create or replace view public\.koica_construction_cases.*?"
            r"\bas\s+select(?P<columns>.*?)"
            r"\bfrom koica_search\.cases",
            PUBLIC_READ_SQL,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(cases_projection)
        self.assertNotIn("search_text", cases_projection.group("columns"))
        self.assertNotIn("is_published", cases_projection.group("columns"))

    def test_public_roles_get_only_select_and_bounded_read_rpcs(self):
        self.assertNotRegex(
            PUBLIC_READ_SQL,
            r"grant\s+(?:all|insert|update|delete|truncate|references|trigger)\b",
        )
        self.assertIn(
            "grant execute on function public.get_koica_search_status()\n"
            "  to anon, authenticated",
            PUBLIC_READ_SQL,
        )
        self.assertIn(
            "grant execute on function public.get_koica_reference_case(text)\n"
            "  to anon, authenticated",
            PUBLIC_READ_SQL,
        )
        self.assertRegex(
            PUBLIC_READ_SQL,
            r"(?s)grant execute on function public\.search_koica_construction_cases\("
            r".*?\) to anon, authenticated",
        )
        self.assertNotRegex(
            PUBLIC_READ_SQL,
            r"grant execute on function public\.(?:get_koica_related_notices|"
            r"sync_koica_search_snapshot)",
        )

    def test_storage_schema_stays_outside_data_api(self):
        self.assertIn('schemas = ["public", "graphql_public"]', CONFIG)
        self.assertIn("auto_expose_new_tables = false", CONFIG)

    def test_reviewed_references_are_labeled_separately_from_contracts(self):
        self.assertIn("add column case_kind text not null", REVIEWED_REFERENCE_SQL)
        self.assertIn("'CONSTRUCTION_NOTICE'", REVIEWED_REFERENCE_SQL)
        self.assertIn("'DESIGN_SUPERVISION_REFERENCE'", REVIEWED_REFERENCE_SQL)
        self.assertIn("add column facility_family text not null", REVIEWED_REFERENCE_SQL)
        self.assertIn("cases_case_kind_valid", REVIEWED_REFERENCE_SQL)
        self.assertIn("cases_facility_family_not_blank", REVIEWED_REFERENCE_SQL)

    def test_updated_public_projection_is_invoker_only_and_exposes_labels(self):
        view = re.search(
            r"create or replace view public\.koica_construction_cases.*?;",
            REVIEWED_REFERENCE_SQL,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(view)
        self.assertIn("security_invoker = true", view.group(0))
        self.assertIn("security_barrier = true", view.group(0))
        self.assertIn("c.case_kind", view.group(0))
        self.assertIn("c.facility_family", view.group(0))
        self.assertNotIn("c.search_text", view.group(0))

        projection = re.search(
            r"create or replace function public\.search_koica_construction_cases"
            r".*?\$\$;",
            REVIEWED_REFERENCE_SQL,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(projection)
        self.assertIn("security invoker", projection.group(0))
        self.assertIn("'case_kind'", projection.group(0))
        self.assertIn("'facility_family'", projection.group(0))

    def test_snapshot_identity_is_publicly_auditable_but_read_only(self):
        self.assertIn(
            "alter table koica_search.snapshot_metadata enable row level security",
            REVIEWED_REFERENCE_SQL,
        )
        self.assertRegex(
            REVIEWED_REFERENCE_SQL,
            r'(?s)create policy "public reads snapshot metadata".*?'
            r"for select.*?to anon, authenticated.*?using \(true\)",
        )
        self.assertIn(
            "grant select on table koica_search.snapshot_metadata\n"
            "  to anon, authenticated, service_role",
            REVIEWED_REFERENCE_SQL,
        )
        for field in (
            "source_schema_version",
            "source_db_sha256",
            "snapshot_generated_at",
            "construction_notice_count",
            "reviewed_reference_count",
        ):
            self.assertIn(field, REVIEWED_REFERENCE_SQL)
        self.assertNotRegex(
            REVIEWED_REFERENCE_SQL,
            r"grant\s+(?:all|insert|update|delete|truncate|references|trigger)\b",
        )

    def test_replacement_sync_rpc_remains_service_role_only(self):
        sync_function = re.search(
            r"create function public\.sync_koica_search_snapshot.*?as \$\$",
            REVIEWED_REFERENCE_SQL,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(sync_function)
        self.assertIn("security definer", sync_function.group(0))
        self.assertIn("set search_path = ''", sync_function.group(0))
        self.assertIn("p_source_db_sha256", sync_function.group(0))
        self.assertRegex(
            REVIEWED_REFERENCE_SQL,
            r"(?s)grant execute on function public\.sync_koica_search_snapshot\("
            r".*?\) to service_role",
        )
        self.assertNotRegex(
            REVIEWED_REFERENCE_SQL,
            r"(?s)grant execute on function public\.sync_koica_search_snapshot\("
            r".*?\) to (?:anon|authenticated)",
        )


if __name__ == "__main__":
    unittest.main()
