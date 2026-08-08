-- Public, read-only access to the sanitized KOICA construction search snapshot.
--
-- The storage schema stays outside PostgREST's exposed-schema list. Public Data
-- API clients read the two security-invoker views below or call the bounded RPCs.
-- Snapshot synchronization remains service-role only.

grant usage on schema koica_search to anon, authenticated;

drop policy if exists "public reads published cases" on koica_search.cases;
create policy "public reads published cases"
  on koica_search.cases
  for select
  to anon, authenticated
  using (is_published);

drop policy if exists "public reads published related notices"
  on koica_search.related_notices;
create policy "public reads published related notices"
  on koica_search.related_notices
  for select
  to anon, authenticated
  using (is_published);

grant select on table koica_search.cases to anon, authenticated;
grant select on table koica_search.related_notices to anon, authenticated;

create or replace view public.koica_construction_cases
with (security_invoker = true, security_barrier = true)
as
select
  c.case_id,
  c.project_no,
  c.representative_bid_no,
  c.display_name,
  c.official_project_name,
  c.country_ko,
  c.facility_type,
  c.work_type,
  c.notice_date,
  c.gross_floor_area_m2,
  c.construction_cost_usd,
  c.amount_stage_code,
  c.nominal_unit_usd_m2,
  c.evidence_grade,
  c.verification_level,
  c.scope_note,
  c.evidence_note,
  c.allowed_use,
  c.notice_count,
  c.procurement_url,
  c.data_version,
  c.audit_date,
  c.synced_at
from koica_search.cases as c
where c.is_published;

comment on view public.koica_construction_cases is
  'Public read-only projection for published KOICA construction cases.';

create or replace view public.koica_construction_related_notices
with (security_invoker = true, security_barrier = true)
as
select
  n.case_id,
  n.related_bid_base_no,
  n.representative_bid_no,
  n.relation_type,
  n.display_name,
  n.contract_type,
  n.amount_usd,
  n.amount_stage_code,
  n.notice_date,
  n.procurement_url,
  n.note
from koica_search.related_notices as n
where n.is_published;

comment on view public.koica_construction_related_notices is
  'Public read-only projection for published notices related to KOICA construction cases.';

revoke all on table public.koica_construction_cases
  from public, anon, authenticated, service_role;
revoke all on table public.koica_construction_related_notices
  from public, anon, authenticated, service_role;

grant select on table public.koica_construction_cases
  to anon, authenticated, service_role;
grant select on table public.koica_construction_related_notices
  to anon, authenticated, service_role;

-- These are the three bounded public read operations used by the MCP tools.
-- search_koica_reference_cases is an invoker-rights dependency of the stable
-- search projection and returns the same published search scope.
revoke all on function public.get_koica_search_status()
  from public, anon, authenticated;
revoke all on function public.search_koica_reference_cases(
  text,
  text,
  text,
  text,
  numeric,
  integer
) from public, anon, authenticated;
revoke all on function public.search_koica_construction_cases(
  text,
  text,
  text,
  text,
  numeric,
  integer
) from public, anon, authenticated;
revoke all on function public.get_koica_reference_case(text)
  from public, anon, authenticated;

grant execute on function public.get_koica_search_status()
  to anon, authenticated;
grant execute on function public.search_koica_reference_cases(
  text,
  text,
  text,
  text,
  numeric,
  integer
) to anon, authenticated;
grant execute on function public.search_koica_construction_cases(
  text,
  text,
  text,
  text,
  numeric,
  integer
) to anon, authenticated;
grant execute on function public.get_koica_reference_case(text)
  to anon, authenticated;
