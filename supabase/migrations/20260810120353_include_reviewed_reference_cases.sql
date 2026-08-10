-- Publish reviewed design/supervision references without presenting them as
-- construction contracts, and expose the exact SQLite snapshot identity.

alter table koica_search.cases
  add column case_kind text not null default 'CONSTRUCTION_NOTICE',
  add column facility_family text not null default '기타·미분류',
  add constraint cases_case_kind_valid check (
    case_kind in ('CONSTRUCTION_NOTICE', 'DESIGN_SUPERVISION_REFERENCE')
  ),
  add constraint cases_facility_family_not_blank check (
    btrim(facility_family) <> ''
  );

comment on table koica_search.cases is
  'Published KOICA construction notices plus reviewed design/supervision reference cases; reannouncements are collapsed.';
comment on column koica_search.cases.case_kind is
  'CONSTRUCTION_NOTICE is a construction procurement group. DESIGN_SUPERVISION_REFERENCE is a reviewed project-level design or supervision reference, not a construction contract.';
comment on column koica_search.cases.facility_family is
  'Normalized broad facility family used to recover coarse source classifications.';

create index cases_published_family_filters_idx
  on koica_search.cases (
    country_ko,
    facility_family,
    work_type,
    notice_date desc
  )
  where is_published;

create table koica_search.snapshot_metadata (
  singleton boolean primary key default true,
  data_version text not null,
  source_schema_version text not null,
  source_db_sha256 text not null,
  snapshot_generated_at timestamptz not null,
  synced_at timestamptz not null default now(),
  constraint snapshot_metadata_singleton check (singleton),
  constraint snapshot_metadata_data_version_not_blank check (
    btrim(data_version) <> ''
  ),
  constraint snapshot_metadata_schema_version_not_blank check (
    btrim(source_schema_version) <> ''
  ),
  constraint snapshot_metadata_sha256_valid check (
    source_db_sha256 ~ '^[0-9a-f]{64}$'
  )
);

comment on table koica_search.snapshot_metadata is
  'Identity and generation time of the currently synchronized source SQLite snapshot.';

alter table koica_search.snapshot_metadata enable row level security;

create policy "service role reads snapshot metadata"
  on koica_search.snapshot_metadata
  for select
  to service_role
  using (true);

create policy "public reads snapshot metadata"
  on koica_search.snapshot_metadata
  for select
  to anon, authenticated
  using (true);

revoke all on table koica_search.snapshot_metadata
  from public, anon, authenticated, service_role;
grant select on table koica_search.snapshot_metadata
  to anon, authenticated, service_role;

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
  c.synced_at,
  c.case_kind,
  c.facility_family
from koica_search.cases as c
where c.is_published;

comment on view public.koica_construction_cases is
  'Public read-only projection for construction notices and explicitly labeled reviewed reference cases.';

create or replace function public.search_koica_construction_cases(
  p_target_text text default null,
  p_target_country text default null,
  p_target_facility_type text default null,
  p_target_work_type text default null,
  p_target_area_m2 numeric default null,
  p_max_results integer default 10
)
returns jsonb
language sql
stable
security invoker
set search_path = ''
as $$
  select coalesce(
    jsonb_agg(
      to_jsonb(search_result)
      || jsonb_build_object(
        'representative_bid_no', source_case.representative_bid_no,
        'case_kind', source_case.case_kind,
        'facility_family', source_case.facility_family
      )
      order by
        search_result.priority,
        search_result.match_score desc,
        search_result.notice_date desc nulls last,
        search_result.case_id
    ),
    '[]'::jsonb
  )
  from public.search_koica_reference_cases(
    p_target_text,
    p_target_country,
    p_target_facility_type,
    p_target_work_type,
    p_target_area_m2,
    p_max_results
  ) as search_result
  join koica_search.cases as source_case
    on source_case.case_id = search_result.case_id;
$$;

drop function public.get_koica_reference_case(text);

create function public.get_koica_reference_case(p_case_id text)
returns table (
  case_id text,
  project_no text,
  representative_bid_no text,
  display_name text,
  official_project_name text,
  country_ko text,
  facility_type text,
  work_type text,
  notice_date date,
  gross_floor_area_m2 numeric,
  construction_cost_usd numeric,
  amount_stage_code text,
  nominal_unit_usd_m2 numeric,
  evidence_grade text,
  verification_level text,
  scope_note text,
  evidence_note text,
  allowed_use text,
  notice_count integer,
  procurement_url text,
  related_notices jsonb,
  data_version text,
  audit_date date,
  case_kind text,
  facility_family text
)
language sql
stable
security invoker
set search_path = ''
as $$
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
    coalesce(
      (
        select jsonb_agg(
          (to_jsonb(n) - 'case_id' - 'is_published' - 'synced_at')
          order by n.notice_date desc nulls last, n.related_bid_base_no
        )
        from koica_search.related_notices as n
        where n.case_id = c.case_id and n.is_published
      ),
      '[]'::jsonb
    ) as related_notices,
    c.data_version,
    c.audit_date,
    c.case_kind,
    c.facility_family
  from koica_search.cases as c
  where c.case_id = p_case_id and c.is_published;
$$;

drop function public.get_koica_search_status();

create function public.get_koica_search_status()
returns table (
  data_version text,
  source_schema_version text,
  source_db_sha256 text,
  snapshot_generated_at timestamptz,
  audit_date date,
  synced_at timestamptz,
  case_count bigint,
  construction_notice_count bigint,
  reviewed_reference_count bigint,
  related_notice_count bigint,
  notice_date_start date,
  notice_date_end date
)
language sql
stable
security invoker
set search_path = ''
as $$
  select
    coalesce(m.data_version, max(c.data_version)) as data_version,
    m.source_schema_version,
    m.source_db_sha256,
    m.snapshot_generated_at,
    max(c.audit_date) as audit_date,
    coalesce(m.synced_at, max(c.synced_at)) as synced_at,
    count(*) as case_count,
    count(*) filter (where c.case_kind = 'CONSTRUCTION_NOTICE')
      as construction_notice_count,
    count(*) filter (where c.case_kind = 'DESIGN_SUPERVISION_REFERENCE')
      as reviewed_reference_count,
    (
      select count(*)
      from koica_search.related_notices as n
      where n.is_published
    ) as related_notice_count,
    min(c.notice_date) as notice_date_start,
    max(c.notice_date) as notice_date_end
  from koica_search.cases as c
  left join koica_search.snapshot_metadata as m on m.singleton
  where c.is_published
  group by
    m.data_version,
    m.source_schema_version,
    m.source_db_sha256,
    m.snapshot_generated_at,
    m.synced_at;
$$;

drop function public.sync_koica_search_snapshot(jsonb, jsonb, text);

create function public.sync_koica_search_snapshot(
  p_cases jsonb,
  p_related_notices jsonb,
  p_data_version text,
  p_source_schema_version text,
  p_source_db_sha256 text,
  p_snapshot_generated_at timestamptz
)
returns jsonb
language plpgsql
volatile
security definer
set search_path = ''
as $$
declare
  v_case_count integer;
  v_construction_notice_count integer;
  v_reviewed_reference_count integer;
  v_related_count integer;
  v_synced_at timestamptz := now();
begin
  if p_cases is null
    or jsonb_typeof(p_cases) <> 'array'
    or jsonb_array_length(p_cases) = 0
  then
    raise exception 'p_cases must be a non-empty JSON array';
  end if;
  if jsonb_array_length(p_cases) > 10000 then
    raise exception 'p_cases exceeds the 10000 row safety limit';
  end if;
  if p_related_notices is null or jsonb_typeof(p_related_notices) <> 'array' then
    raise exception 'p_related_notices must be a JSON array';
  end if;
  if jsonb_array_length(p_related_notices) > 50000 then
    raise exception 'p_related_notices exceeds the 50000 row safety limit';
  end if;
  if nullif(btrim(p_data_version), '') is null then
    raise exception 'p_data_version must not be blank';
  end if;
  if nullif(btrim(p_source_schema_version), '') is null then
    raise exception 'p_source_schema_version must not be blank';
  end if;
  if p_source_db_sha256 is null
    or p_source_db_sha256 !~ '^[0-9a-f]{64}$'
  then
    raise exception 'p_source_db_sha256 must be a lowercase SHA-256 digest';
  end if;
  if p_snapshot_generated_at is null then
    raise exception 'p_snapshot_generated_at must not be null';
  end if;

  insert into koica_search.cases (
    case_id,
    case_kind,
    project_no,
    representative_bid_no,
    display_name,
    official_project_name,
    country_ko,
    facility_type,
    facility_family,
    work_type,
    notice_date,
    gross_floor_area_m2,
    construction_cost_usd,
    amount_stage_code,
    nominal_unit_usd_m2,
    evidence_grade,
    verification_level,
    scope_note,
    evidence_note,
    allowed_use,
    notice_count,
    procurement_url,
    search_text,
    data_version,
    audit_date,
    is_published,
    synced_at
  )
  select
    x.case_id,
    x.case_kind,
    x.project_no,
    x.representative_bid_no,
    x.display_name,
    x.official_project_name,
    x.country_ko,
    x.facility_type,
    x.facility_family,
    x.work_type,
    x.notice_date,
    x.gross_floor_area_m2,
    x.construction_cost_usd,
    x.amount_stage_code,
    x.nominal_unit_usd_m2,
    x.evidence_grade,
    x.verification_level,
    x.scope_note,
    x.evidence_note,
    x.allowed_use,
    coalesce(x.notice_count, 1),
    x.procurement_url,
    x.search_text,
    p_data_version,
    x.audit_date,
    coalesce(x.is_published, true),
    v_synced_at
  from jsonb_to_recordset(p_cases) as x(
    case_id text,
    case_kind text,
    project_no text,
    representative_bid_no text,
    display_name text,
    official_project_name text,
    country_ko text,
    facility_type text,
    facility_family text,
    work_type text,
    notice_date date,
    gross_floor_area_m2 numeric,
    construction_cost_usd numeric,
    amount_stage_code text,
    nominal_unit_usd_m2 numeric,
    evidence_grade text,
    verification_level text,
    scope_note text,
    evidence_note text,
    allowed_use text,
    notice_count integer,
    procurement_url text,
    search_text text,
    data_version text,
    audit_date date,
    is_published boolean
  )
  on conflict (case_id) do update set
    case_kind = excluded.case_kind,
    project_no = excluded.project_no,
    representative_bid_no = excluded.representative_bid_no,
    display_name = excluded.display_name,
    official_project_name = excluded.official_project_name,
    country_ko = excluded.country_ko,
    facility_type = excluded.facility_type,
    facility_family = excluded.facility_family,
    work_type = excluded.work_type,
    notice_date = excluded.notice_date,
    gross_floor_area_m2 = excluded.gross_floor_area_m2,
    construction_cost_usd = excluded.construction_cost_usd,
    amount_stage_code = excluded.amount_stage_code,
    nominal_unit_usd_m2 = excluded.nominal_unit_usd_m2,
    evidence_grade = excluded.evidence_grade,
    verification_level = excluded.verification_level,
    scope_note = excluded.scope_note,
    evidence_note = excluded.evidence_note,
    allowed_use = excluded.allowed_use,
    notice_count = excluded.notice_count,
    procurement_url = excluded.procurement_url,
    search_text = excluded.search_text,
    data_version = excluded.data_version,
    audit_date = excluded.audit_date,
    is_published = excluded.is_published,
    synced_at = excluded.synced_at;

  insert into koica_search.related_notices (
    case_id,
    related_bid_base_no,
    representative_bid_no,
    relation_type,
    display_name,
    contract_type,
    amount_usd,
    amount_stage_code,
    notice_date,
    procurement_url,
    note,
    is_published,
    synced_at
  )
  select
    x.case_id,
    x.related_bid_base_no,
    x.representative_bid_no,
    x.relation_type,
    x.display_name,
    x.contract_type,
    x.amount_usd,
    x.amount_stage_code,
    x.notice_date,
    x.procurement_url,
    x.note,
    coalesce(x.is_published, true),
    v_synced_at
  from jsonb_to_recordset(p_related_notices) as x(
    case_id text,
    related_bid_base_no text,
    representative_bid_no text,
    relation_type text,
    display_name text,
    contract_type text,
    amount_usd numeric,
    amount_stage_code text,
    notice_date date,
    procurement_url text,
    note text,
    is_published boolean
  )
  on conflict (case_id, related_bid_base_no) do update set
    representative_bid_no = excluded.representative_bid_no,
    relation_type = excluded.relation_type,
    display_name = excluded.display_name,
    contract_type = excluded.contract_type,
    amount_usd = excluded.amount_usd,
    amount_stage_code = excluded.amount_stage_code,
    notice_date = excluded.notice_date,
    procurement_url = excluded.procurement_url,
    note = excluded.note,
    is_published = excluded.is_published,
    synced_at = excluded.synced_at;

  delete from koica_search.related_notices as n
  where not exists (
    select 1
    from jsonb_to_recordset(p_related_notices) as x(
      case_id text,
      related_bid_base_no text
    )
    where x.case_id = n.case_id
      and x.related_bid_base_no = n.related_bid_base_no
  );

  delete from koica_search.cases as c
  where not exists (
    select 1
    from jsonb_to_recordset(p_cases) as x(case_id text)
    where x.case_id = c.case_id
  );

  insert into koica_search.snapshot_metadata (
    singleton,
    data_version,
    source_schema_version,
    source_db_sha256,
    snapshot_generated_at,
    synced_at
  )
  values (
    true,
    p_data_version,
    p_source_schema_version,
    p_source_db_sha256,
    p_snapshot_generated_at,
    v_synced_at
  )
  on conflict (singleton) do update set
    data_version = excluded.data_version,
    source_schema_version = excluded.source_schema_version,
    source_db_sha256 = excluded.source_db_sha256,
    snapshot_generated_at = excluded.snapshot_generated_at,
    synced_at = excluded.synced_at;

  select
    count(*),
    count(*) filter (where case_kind = 'CONSTRUCTION_NOTICE'),
    count(*) filter (where case_kind = 'DESIGN_SUPERVISION_REFERENCE')
  into
    v_case_count,
    v_construction_notice_count,
    v_reviewed_reference_count
  from koica_search.cases
  where is_published;
  select count(*) into v_related_count
  from koica_search.related_notices
  where is_published;

  return jsonb_build_object(
    'data_version', p_data_version,
    'source_schema_version', p_source_schema_version,
    'source_db_sha256', p_source_db_sha256,
    'snapshot_generated_at', p_snapshot_generated_at,
    'cases', v_case_count,
    'construction_notices', v_construction_notice_count,
    'reviewed_references', v_reviewed_reference_count,
    'related_notices', v_related_count,
    'synced_at', v_synced_at
  );
end;
$$;

revoke all on function public.search_koica_construction_cases(
  text,
  text,
  text,
  text,
  numeric,
  integer
) from public, anon, authenticated, service_role;
revoke all on function public.get_koica_reference_case(text)
  from public, anon, authenticated, service_role;
revoke all on function public.get_koica_search_status()
  from public, anon, authenticated, service_role;
revoke all on function public.sync_koica_search_snapshot(
  jsonb,
  jsonb,
  text,
  text,
  text,
  timestamptz
) from public, anon, authenticated, service_role;

grant execute on function public.search_koica_construction_cases(
  text,
  text,
  text,
  text,
  numeric,
  integer
) to anon, authenticated, service_role;
grant execute on function public.get_koica_reference_case(text)
  to anon, authenticated, service_role;
grant execute on function public.get_koica_search_status()
  to anon, authenticated, service_role;
grant execute on function public.sync_koica_search_snapshot(
  jsonb,
  jsonb,
  text,
  text,
  text,
  timestamptz
) to service_role;

notify pgrst, 'reload schema';
