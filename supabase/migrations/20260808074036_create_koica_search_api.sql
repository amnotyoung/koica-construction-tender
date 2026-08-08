-- Private KOICA construction search read model.
create extension if not exists pgroonga with schema extensions;

create schema if not exists koica_search;

comment on schema koica_search is
  'Private read model synchronized from the KOICA construction source SQLite database.';

revoke all on schema koica_search from public;
revoke all on schema koica_search from anon, authenticated;
grant usage on schema koica_search to service_role;

create table koica_search.cases (
  case_id text primary key,
  project_no text,
  representative_bid_no text not null,
  display_name text not null,
  official_project_name text,
  country_ko text,
  facility_type text,
  work_type text,
  notice_date date,
  gross_floor_area_m2 numeric(14, 2),
  construction_cost_usd numeric(18, 2),
  amount_stage_code text,
  nominal_unit_usd_m2 numeric(14, 2),
  evidence_grade text,
  verification_level text,
  scope_note text,
  evidence_note text,
  allowed_use text,
  notice_count integer not null default 1,
  procurement_url text,
  search_text text not null,
  data_version text not null,
  audit_date date,
  is_published boolean not null default true,
  synced_at timestamptz not null default now(),
  constraint cases_case_id_format check (case_id ~ '^L[0-9]{4}-[0-9]{5}$'),
  constraint cases_representative_bid_no_not_blank check (btrim(representative_bid_no) <> ''),
  constraint cases_display_name_not_blank check (btrim(display_name) <> ''),
  constraint cases_area_positive check (
    gross_floor_area_m2 is null or gross_floor_area_m2 > 0
  ),
  constraint cases_cost_positive check (
    construction_cost_usd is null or construction_cost_usd > 0
  ),
  constraint cases_unit_cost_positive check (
    nominal_unit_usd_m2 is null or nominal_unit_usd_m2 > 0
  ),
  constraint cases_evidence_grade_valid check (
    evidence_grade is null or evidence_grade in ('A', 'B', 'C', 'C?', 'U', 'X')
  ),
  constraint cases_notice_count_positive check (notice_count > 0),
  constraint cases_procurement_url_valid check (
    procurement_url is null
    or procurement_url like 'https://nebid.koica.go.kr/%'
  ),
  constraint cases_search_text_not_blank check (btrim(search_text) <> '')
);

comment on table koica_search.cases is
  'One public search case per construction bid group; reannouncements are collapsed.';
comment on column koica_search.cases.nominal_unit_usd_m2 is
  'Nominal screening value only; it is not a future project estimate.';
comment on column koica_search.cases.evidence_grade is
  'Static source-evidence grade. Search priority is calculated per query.';

create table koica_search.related_notices (
  case_id text not null references koica_search.cases(case_id) on delete cascade,
  related_bid_base_no text not null,
  representative_bid_no text not null,
  relation_type text not null,
  display_name text not null,
  contract_type text,
  amount_usd numeric(18, 2),
  amount_stage_code text,
  notice_date date,
  procurement_url text,
  note text,
  is_published boolean not null default true,
  synced_at timestamptz not null default now(),
  primary key (case_id, related_bid_base_no),
  constraint related_notices_case_distinct check (case_id <> related_bid_base_no),
  constraint related_notices_representative_bid_not_blank check (
    btrim(representative_bid_no) <> ''
  ),
  constraint related_notices_display_name_not_blank check (btrim(display_name) <> ''),
  constraint related_notices_relation_type_valid check (
    relation_type in (
      'SUPERVISION',
      'PROJECT_MANAGEMENT',
      'DESIGN',
      'CONSTRUCTION_PACKAGE',
      'GOODS',
      'SERVICE',
      'RELATED_PROCUREMENT'
    )
  ),
  constraint related_notices_bid_base_format check (
    related_bid_base_no ~ '^L[0-9]{4}-[0-9]{5}$'
  ),
  constraint related_notices_amount_positive check (amount_usd is null or amount_usd > 0),
  constraint related_notices_url_valid check (
    procurement_url is null
    or procurement_url like 'https://nebid.koica.go.kr/%'
  )
);

comment on table koica_search.related_notices is
  'Other procurement notices sharing the same KOICA project number.';

create index cases_published_filters_idx
  on koica_search.cases (country_ko, facility_type, work_type, notice_date desc)
  where is_published;

create index cases_search_text_pgroonga_idx
  on koica_search.cases using pgroonga (search_text);

create index related_notices_case_published_idx
  on koica_search.related_notices (case_id, relation_type, notice_date desc)
  where is_published;

alter table koica_search.cases enable row level security;
alter table koica_search.related_notices enable row level security;

create policy "service role reads published cases"
  on koica_search.cases
  for select
  to service_role
  using (is_published);

create policy "service role reads published related notices"
  on koica_search.related_notices
  for select
  to service_role
  using (is_published);

revoke all on table koica_search.cases from public, anon, authenticated, service_role;
revoke all on table koica_search.related_notices from public, anon, authenticated, service_role;
grant select on table koica_search.cases to service_role;
grant select on table koica_search.related_notices to service_role;

create or replace function public.search_koica_reference_cases(
  p_target_text text default null,
  p_target_country text default null,
  p_target_facility_type text default null,
  p_target_work_type text default null,
  p_target_area_m2 numeric default null,
  p_max_results integer default 10
)
returns table (
  priority bigint,
  case_id text,
  project_no text,
  display_name text,
  country_ko text,
  facility_type text,
  work_type text,
  notice_date date,
  gross_floor_area_m2 numeric,
  construction_cost_usd numeric,
  amount_stage_code text,
  amount_basis_label text,
  nominal_unit_usd_m2 numeric,
  evidence_grade text,
  verification_level text,
  match_score numeric,
  match_reason text,
  scope_note text,
  evidence_note text,
  allowed_use text,
  procurement_url text,
  related_notices jsonb,
  data_version text,
  audit_date date
)
language sql
stable
security invoker
set search_path = ''
as $$
  with params as (
    select
      nullif(btrim(p_target_text), '') as target_text,
      nullif(btrim(p_target_country), '') as target_country,
      nullif(btrim(p_target_facility_type), '') as target_facility_type,
      nullif(btrim(p_target_work_type), '') as target_work_type,
      case when p_target_area_m2 > 0 then p_target_area_m2 else null end as target_area_m2
  ),
  signals as (
    select
      c.*,
      p.*,
      (
        p.target_country is not null
        and lower(coalesce(c.country_ko, '')) = lower(p.target_country)
      ) as country_match,
      (
        p.target_facility_type is not null
        and (
          position(lower(p.target_facility_type) in lower(coalesce(c.facility_type, ''))) > 0
          or (
            c.facility_type is not null
            and position(lower(c.facility_type) in lower(p.target_facility_type)) > 0
          )
          or position(lower(p.target_facility_type) in lower(c.search_text)) > 0
        )
      ) as facility_match,
      (
        p.target_work_type is not null
        and (
          position(lower(p.target_work_type) in lower(coalesce(c.work_type, ''))) > 0
          or (
            c.work_type is not null
            and position(lower(c.work_type) in lower(p.target_work_type)) > 0
          )
          or position(lower(p.target_work_type) in lower(c.search_text)) > 0
        )
      ) as work_type_match,
      (
        p.target_text is not null
        and c.search_text operator(extensions.&@~) p.target_text
      ) as text_match
    from koica_search.cases as c
    cross join params as p
    where c.is_published
  ),
  scored as (
    select
      s.*,
      (
        case when s.country_match then 40 else 0 end
        + case when s.facility_match then 30 else 0 end
        + case when s.work_type_match then 10 else 0 end
        + case when s.text_match then 15 else 0 end
        + case
            when s.target_area_m2 is not null and s.gross_floor_area_m2 is not null
            then round(
              5 * greatest(
                0::numeric,
                1 - abs(s.gross_floor_area_m2 - s.target_area_m2) / s.target_area_m2
              ),
              2
            )
            else 0
          end
        + case s.evidence_grade
            when 'A' then 5
            when 'B' then 4
            when 'C' then 3
            when 'C?' then 2
            when 'U' then 1
            else 0
          end
      )::numeric as score,
      coalesce(
        nullif(
          concat_ws(
            '·',
            case when s.country_match then '동일 국가' end,
            case when s.facility_match then '동일·유사 시설기능' end,
            case when s.work_type_match then '동일 공종' end,
            case when s.text_match then '검색어 일치' end,
            case
              when s.target_area_m2 is not null
                and s.gross_floor_area_m2 is not null
                and abs(s.gross_floor_area_m2 - s.target_area_m2) / s.target_area_m2 <= 0.25
              then '연면적 ±25%'
            end
          ),
          ''
        ),
        '근거등급 기준'
      ) as reason
    from signals as s
  ),
  ranked as (
    select
      s.*,
      dense_rank() over (order by s.score desc) as result_priority
    from scored as s
  )
  select
    r.result_priority as priority,
    r.case_id,
    r.project_no,
    r.display_name,
    r.country_ko,
    r.facility_type,
    r.work_type,
    r.notice_date,
    r.gross_floor_area_m2,
    r.construction_cost_usd,
    r.amount_stage_code,
    case r.amount_stage_code
      when 'NOTICE_EXECUTION_CEILING' then '집행한도'
      when 'NOTICE_EXECUTION_CEILING_RAW' then '공고 집행한도(미검토)'
      when 'ADVERTISED_BUDGET_CAP' then '광고예산 기준'
      when 'ADVERTISED_ESTIMATED_BUDGET' then '광고 추정예산'
      when 'CONSTRUCTION_BUDGET' then '공사예산'
      when 'DESIGN_ESTIMATE' then '설계 추정금액'
      when 'BASIC_ESTIMATED_PRICE' then '기초 추정가격'
      when 'BID_LIMIT' then '입찰한도'
      when 'SERVICE_OR_GOODS_CEILING' then '용역·물품 한도'
      else r.amount_stage_code
    end as amount_basis_label,
    r.nominal_unit_usd_m2,
    r.evidence_grade,
    r.verification_level,
    r.score as match_score,
    r.reason as match_reason,
    r.scope_note,
    r.evidence_note,
    r.allowed_use,
    r.procurement_url,
    coalesce(
      (
        select jsonb_agg(
          jsonb_build_object(
            'related_bid_base_no', n.related_bid_base_no,
            'representative_bid_no', n.representative_bid_no,
            'relation_type', n.relation_type,
            'display_name', n.display_name,
            'contract_type', n.contract_type,
            'amount_usd', n.amount_usd,
            'amount_stage_code', n.amount_stage_code,
            'notice_date', n.notice_date,
            'procurement_url', n.procurement_url,
            'note', n.note
          )
          order by n.notice_date desc nulls last, n.related_bid_base_no
        )
        from koica_search.related_notices as n
        where n.case_id = r.case_id and n.is_published
      ),
      '[]'::jsonb
    ) as related_notices,
    r.data_version,
    r.audit_date
  from ranked as r
  order by r.score desc, r.notice_date desc nulls last, r.case_id
  limit least(greatest(coalesce(p_max_results, 10), 1), 50);
$$;

create or replace function public.get_koica_reference_case(p_case_id text)
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
  audit_date date
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
    c.audit_date
  from koica_search.cases as c
  where c.case_id = p_case_id and c.is_published;
$$;

create or replace function public.get_koica_related_notices(p_case_id text)
returns table (
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
  note text
)
language sql
stable
security invoker
set search_path = ''
as $$
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
  where n.case_id = p_case_id and n.is_published
  order by n.notice_date desc nulls last, n.related_bid_base_no;
$$;

create or replace function public.get_koica_search_status()
returns table (
  data_version text,
  audit_date date,
  synced_at timestamptz,
  case_count bigint,
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
    max(c.data_version) as data_version,
    max(c.audit_date) as audit_date,
    max(c.synced_at) as synced_at,
    count(*) as case_count,
    (
      select count(*)
      from koica_search.related_notices as n
      where n.is_published
    ) as related_notice_count,
    min(c.notice_date) as notice_date_start,
    max(c.notice_date) as notice_date_end
  from koica_search.cases as c
  where c.is_published;
$$;

create or replace function public.sync_koica_search_snapshot(
  p_cases jsonb,
  p_related_notices jsonb,
  p_data_version text
)
returns jsonb
language plpgsql
volatile
security definer
set search_path = ''
as $$
declare
  v_case_count integer;
  v_related_count integer;
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
  if nullif(btrim(p_data_version), '') is null then
    raise exception 'p_data_version must not be blank';
  end if;

  insert into koica_search.cases (
    case_id,
    project_no,
    representative_bid_no,
    display_name,
    official_project_name,
    country_ko,
    facility_type,
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
    x.project_no,
    x.representative_bid_no,
    x.display_name,
    x.official_project_name,
    x.country_ko,
    x.facility_type,
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
    now()
  from jsonb_to_recordset(p_cases) as x(
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
    search_text text,
    data_version text,
    audit_date date,
    is_published boolean
  )
  on conflict (case_id) do update set
    project_no = excluded.project_no,
    representative_bid_no = excluded.representative_bid_no,
    display_name = excluded.display_name,
    official_project_name = excluded.official_project_name,
    country_ko = excluded.country_ko,
    facility_type = excluded.facility_type,
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
    now()
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

  select count(*) into v_case_count from koica_search.cases;
  select count(*) into v_related_count from koica_search.related_notices;

  return jsonb_build_object(
    'data_version', p_data_version,
    'cases', v_case_count,
    'related_notices', v_related_count,
    'synced_at', now()
  );
end;
$$;

revoke all on function public.search_koica_reference_cases(text, text, text, text, numeric, integer)
  from public, anon, authenticated, service_role;
revoke all on function public.get_koica_reference_case(text)
  from public, anon, authenticated, service_role;
revoke all on function public.get_koica_related_notices(text)
  from public, anon, authenticated, service_role;
revoke all on function public.get_koica_search_status()
  from public, anon, authenticated, service_role;
revoke all on function public.sync_koica_search_snapshot(jsonb, jsonb, text)
  from public, anon, authenticated, service_role;

grant execute on function public.search_koica_reference_cases(text, text, text, text, numeric, integer)
  to service_role;
grant execute on function public.get_koica_reference_case(text)
  to service_role;
grant execute on function public.get_koica_related_notices(text)
  to service_role;
grant execute on function public.get_koica_search_status()
  to service_role;
grant execute on function public.sync_koica_search_snapshot(jsonb, jsonb, text)
  to service_role;

alter default privileges in schema koica_search revoke all on tables from public, anon, authenticated;
alter default privileges in schema koica_search revoke all on sequences from public, anon, authenticated;
alter default privileges in schema koica_search revoke execute on functions from public, anon, authenticated;
