-- Publish the sanitized, human-reviewed endline-evaluation evidence already
-- embedded in the source SQLite database. Raw PDFs, local paths, file hashes,
-- OCR digests, and internal review notes intentionally remain outside this
-- read model.

alter table koica_search.snapshot_metadata
  add column evaluation_snapshot_generated_at timestamptz,
  add column evaluation_synced_at timestamptz;

create table koica_search.evaluation_projects (
  project_no text primary key,
  country_ko text not null,
  project_name text not null,
  in_area_cost_review boolean not null,
  has_works_contract boolean not null,
  has_construction_candidate boolean not null,
  manual_construction_relevance boolean not null,
  match_status text not null,
  screening_note text not null,
  data_version text not null,
  is_published boolean not null default true,
  synced_at timestamptz not null default now(),
  constraint evaluation_projects_project_no_format check (
    project_no ~ '^[0-9]{4}-[0-9]{5}$'
  ),
  constraint evaluation_projects_country_not_blank check (
    btrim(country_ko) <> ''
  ),
  constraint evaluation_projects_name_not_blank check (
    btrim(project_name) <> ''
  ),
  constraint evaluation_projects_status_valid check (
    match_status in (
      'accepted_match',
      'candidate_reviewed_not_accepted',
      'no_accepted_same_project_report'
    )
  ),
  constraint evaluation_projects_note_not_blank check (
    btrim(screening_note) <> ''
  ),
  constraint evaluation_projects_version_not_blank check (
    btrim(data_version) <> ''
  )
);

comment on table koica_search.evaluation_projects is
  'Published screening status for every KOICA construction-project identifier checked against the curated endline-evaluation corpus.';
comment on column koica_search.evaluation_projects.match_status is
  'no_accepted_same_project_report means no same-project match was accepted from the reviewed corpus; it does not prove that no report exists.';

create table koica_search.evaluation_reports (
  report_id text primary key,
  source_kind text not null,
  source_collection text not null,
  report_title text not null,
  report_type text not null,
  project_period text not null,
  publication_date text not null,
  publication_date_precision text not null,
  source_page_url text,
  source_download_url text,
  page_count integer not null,
  extraction_status text not null,
  data_version text not null,
  is_published boolean not null default true,
  synced_at timestamptz not null default now(),
  constraint evaluation_reports_id_not_blank check (btrim(report_id) <> ''),
  constraint evaluation_reports_source_kind_valid check (
    source_kind in ('local_corpus', 'koica_official_site')
  ),
  constraint evaluation_reports_collection_not_blank check (
    btrim(source_collection) <> ''
  ),
  constraint evaluation_reports_title_not_blank check (
    btrim(report_title) <> ''
  ),
  constraint evaluation_reports_type_valid check (
    report_type = 'endline_evaluation'
  ),
  constraint evaluation_reports_period_not_blank check (
    btrim(project_period) <> ''
  ),
  constraint evaluation_reports_publication_date_valid check (
    publication_date ~ '^[0-9]{4}-[0-9]{2}(-[0-9]{2})?$'
  ),
  constraint evaluation_reports_date_precision_valid check (
    (publication_date_precision = 'month' and length(publication_date) = 7)
    or (publication_date_precision = 'day' and length(publication_date) = 10)
  ),
  constraint evaluation_reports_page_url_valid check (
    source_page_url is null or source_page_url ~ '^https://'
  ),
  constraint evaluation_reports_download_url_valid check (
    source_download_url is null or source_download_url ~ '^https://'
  ),
  constraint evaluation_reports_page_count_positive check (page_count > 0),
  constraint evaluation_reports_extraction_status_valid check (
    extraction_status in ('text', 'partial_text', 'ocr_text')
  ),
  constraint evaluation_reports_version_not_blank check (
    btrim(data_version) <> ''
  )
);

comment on table koica_search.evaluation_reports is
  'Sanitized metadata for accepted KOICA endline-evaluation reports; local paths, file hashes, and OCR digests are excluded.';

create table koica_search.evaluation_matches (
  match_id text primary key,
  report_id text not null references koica_search.evaluation_reports(report_id)
    on delete cascade,
  project_no text not null references koica_search.evaluation_projects(project_no)
    on delete cascade,
  report_project_name text not null,
  match_method text not null,
  relation_scope text not null,
  match_score numeric(4, 3) not null,
  match_basis text not null,
  reviewed_at date not null,
  data_version text not null,
  is_published boolean not null default true,
  synced_at timestamptz not null default now(),
  constraint evaluation_matches_id_not_blank check (btrim(match_id) <> ''),
  constraint evaluation_matches_report_project_name_not_blank check (
    btrim(report_project_name) <> ''
  ),
  constraint evaluation_matches_method_valid check (
    match_method in ('exact_official_title', 'exact_component_title')
  ),
  constraint evaluation_matches_scope_valid check (
    relation_scope in ('same_project', 'same_project_component')
  ),
  constraint evaluation_matches_score_valid check (
    match_score between 0.85 and 1
  ),
  constraint evaluation_matches_basis_not_blank check (
    btrim(match_basis) <> ''
  ),
  constraint evaluation_matches_version_not_blank check (
    btrim(data_version) <> ''
  ),
  unique (report_id, project_no)
);

comment on table koica_search.evaluation_matches is
  'Human-reviewed accepted links between a KOICA project identifier and an endline-evaluation report.';

create table koica_search.evaluation_findings (
  finding_id text primary key,
  match_id text not null references koica_search.evaluation_matches(match_id)
    on delete cascade,
  category text not null,
  field_code text not null,
  field_description text not null,
  summary_text text not null,
  value_text text,
  value_numeric numeric,
  unit text,
  value_context text,
  pdf_page_start integer not null,
  pdf_page_end integer not null,
  printed_page_label text,
  evidence_excerpt text not null,
  conflict_group text,
  confidence text not null,
  search_text text not null,
  data_version text not null,
  is_published boolean not null default true,
  synced_at timestamptz not null default now(),
  constraint evaluation_findings_id_not_blank check (btrim(finding_id) <> ''),
  constraint evaluation_findings_category_valid check (
    category in (
      'facility_scope',
      'cost_procurement',
      'schedule',
      'quality_safety',
      'operations_maintenance',
      'utilization_results',
      'risk_issue',
      'lesson_recommendation'
    )
  ),
  constraint evaluation_findings_field_code_not_blank check (
    btrim(field_code) <> ''
  ),
  constraint evaluation_findings_field_description_not_blank check (
    btrim(field_description) <> ''
  ),
  constraint evaluation_findings_summary_length check (
    char_length(btrim(summary_text)) between 15 and 600
  ),
  constraint evaluation_findings_numeric_unit_pair check (
    (value_numeric is null and unit is null)
    or (value_numeric is not null and unit is not null)
  ),
  constraint evaluation_findings_pages_valid check (
    pdf_page_start > 0 and pdf_page_end >= pdf_page_start
  ),
  constraint evaluation_findings_excerpt_length check (
    char_length(btrim(evidence_excerpt)) between 20 and 400
  ),
  constraint evaluation_findings_confidence_valid check (
    confidence in ('high', 'medium')
  ),
  constraint evaluation_findings_search_text_not_blank check (
    btrim(search_text) <> ''
  ),
  constraint evaluation_findings_version_not_blank check (
    btrim(data_version) <> ''
  )
);

comment on table koica_search.evaluation_findings is
  'Public-approved structured construction findings with physical PDF page references and short evidence excerpts.';

create index evaluation_projects_published_filters_idx
  on koica_search.evaluation_projects (country_ko, match_status, project_no)
  where is_published;
create index evaluation_reports_published_date_idx
  on koica_search.evaluation_reports (publication_date desc, report_id)
  where is_published;
create index evaluation_matches_project_published_idx
  on koica_search.evaluation_matches (project_no, report_id)
  where is_published;
create index evaluation_matches_report_published_idx
  on koica_search.evaluation_matches (report_id, project_no)
  where is_published;
create index evaluation_findings_match_category_published_idx
  on koica_search.evaluation_findings (match_id, category, field_code)
  where is_published;
create index evaluation_findings_search_text_pgroonga_idx
  on koica_search.evaluation_findings using pgroonga (search_text);

alter table koica_search.evaluation_projects enable row level security;
alter table koica_search.evaluation_reports enable row level security;
alter table koica_search.evaluation_matches enable row level security;
alter table koica_search.evaluation_findings enable row level security;

create policy "service role reads published evaluation projects"
  on koica_search.evaluation_projects for select to service_role
  using (is_published);
create policy "public reads published evaluation projects"
  on koica_search.evaluation_projects for select to anon, authenticated
  using (is_published);
create policy "service role reads published evaluation reports"
  on koica_search.evaluation_reports for select to service_role
  using (is_published);
create policy "public reads published evaluation reports"
  on koica_search.evaluation_reports for select to anon, authenticated
  using (is_published);
create policy "service role reads published evaluation matches"
  on koica_search.evaluation_matches for select to service_role
  using (is_published);
create policy "public reads published evaluation matches"
  on koica_search.evaluation_matches for select to anon, authenticated
  using (is_published);
create policy "service role reads published evaluation findings"
  on koica_search.evaluation_findings for select to service_role
  using (is_published);
create policy "public reads published evaluation findings"
  on koica_search.evaluation_findings for select to anon, authenticated
  using (is_published);

grant usage on schema koica_search to anon, authenticated, service_role;

revoke all on table koica_search.evaluation_projects
  from public, anon, authenticated, service_role;
revoke all on table koica_search.evaluation_reports
  from public, anon, authenticated, service_role;
revoke all on table koica_search.evaluation_matches
  from public, anon, authenticated, service_role;
revoke all on table koica_search.evaluation_findings
  from public, anon, authenticated, service_role;

grant select on table koica_search.evaluation_projects
  to anon, authenticated, service_role;
grant select on table koica_search.evaluation_reports
  to anon, authenticated, service_role;
grant select on table koica_search.evaluation_matches
  to anon, authenticated, service_role;
grant select on table koica_search.evaluation_findings
  to anon, authenticated, service_role;

create view public.koica_evaluation_projects
with (security_invoker = true, security_barrier = true)
as
select
  p.project_no,
  p.country_ko,
  p.project_name,
  p.in_area_cost_review,
  p.has_works_contract,
  p.has_construction_candidate,
  p.manual_construction_relevance,
  p.match_status,
  p.screening_note,
  p.data_version,
  p.synced_at
from koica_search.evaluation_projects as p
where p.is_published;

comment on view public.koica_evaluation_projects is
  'Public read-only endline-evaluation screening status for all 175 reviewed KOICA project identifiers.';

create view public.koica_evaluation_reports
with (security_invoker = true, security_barrier = true)
as
select
  r.report_id,
  r.source_kind,
  r.source_collection,
  r.report_title,
  r.report_type,
  r.project_period,
  r.publication_date,
  r.publication_date_precision,
  r.source_page_url,
  r.source_download_url,
  r.page_count,
  r.extraction_status,
  r.data_version,
  r.synced_at
from koica_search.evaluation_reports as r
where r.is_published;

comment on view public.koica_evaluation_reports is
  'Public read-only sanitized metadata for accepted KOICA endline-evaluation reports.';

create view public.koica_evaluation_findings
with (security_invoker = true, security_barrier = true)
as
select
  f.finding_id,
  m.match_id,
  p.project_no,
  p.country_ko,
  p.project_name,
  p.match_status,
  r.report_id,
  r.report_title,
  r.report_type,
  r.project_period,
  r.publication_date,
  r.publication_date_precision,
  r.source_kind,
  r.source_page_url,
  r.source_download_url,
  r.page_count,
  m.report_project_name,
  m.match_method,
  m.relation_scope,
  m.match_score,
  m.match_basis,
  m.reviewed_at,
  f.category,
  f.field_code,
  f.field_description,
  f.summary_text,
  f.value_text,
  f.value_numeric,
  f.unit,
  f.value_context,
  f.pdf_page_start,
  f.pdf_page_end,
  f.printed_page_label,
  f.evidence_excerpt,
  f.conflict_group,
  f.confidence,
  f.data_version,
  f.synced_at
from koica_search.evaluation_findings as f
join koica_search.evaluation_matches as m
  on m.match_id = f.match_id and m.is_published
join koica_search.evaluation_projects as p
  on p.project_no = m.project_no and p.is_published
join koica_search.evaluation_reports as r
  on r.report_id = m.report_id and r.is_published
where f.is_published;

comment on view public.koica_evaluation_findings is
  'Public read-only structured endline-evaluation evidence joined to accepted KOICA projects and sanitized report metadata.';

revoke all on table public.koica_evaluation_projects
  from public, anon, authenticated, service_role;
revoke all on table public.koica_evaluation_reports
  from public, anon, authenticated, service_role;
revoke all on table public.koica_evaluation_findings
  from public, anon, authenticated, service_role;

grant select on table public.koica_evaluation_projects
  to anon, authenticated, service_role;
grant select on table public.koica_evaluation_reports
  to anon, authenticated, service_role;
grant select on table public.koica_evaluation_findings
  to anon, authenticated, service_role;

create function public.search_koica_evaluation_findings(
  p_query text default null,
  p_project_no text default null,
  p_country text default null,
  p_category text default null,
  p_max_results integer default 20
)
returns jsonb
language sql
stable
security invoker
set search_path = ''
as $$
  with matched as (
    select
      f.finding_id,
      m.match_id,
      p.project_no,
      p.country_ko,
      p.project_name,
      p.match_status,
      r.report_id,
      r.report_title,
      r.report_type,
      r.project_period,
      r.publication_date,
      r.publication_date_precision,
      r.source_kind,
      r.source_page_url,
      r.source_download_url,
      r.page_count,
      m.report_project_name,
      m.match_method,
      m.relation_scope,
      m.match_score,
      m.match_basis,
      m.reviewed_at,
      f.category,
      f.field_code,
      f.field_description,
      f.summary_text,
      f.value_text,
      f.value_numeric,
      f.unit,
      f.value_context,
      f.pdf_page_start,
      f.pdf_page_end,
      f.printed_page_label,
      f.evidence_excerpt,
      f.conflict_group,
      f.confidence,
      f.data_version
    from koica_search.evaluation_findings as f
    join koica_search.evaluation_matches as m
      on m.match_id = f.match_id and m.is_published
    join koica_search.evaluation_projects as p
      on p.project_no = m.project_no and p.is_published
    join koica_search.evaluation_reports as r
      on r.report_id = m.report_id and r.is_published
    where
      f.is_published
      and (
        nullif(btrim(p_query), '') is null
        or f.search_text operator(extensions.&@~) btrim(p_query)
      )
      and (
        nullif(btrim(p_project_no), '') is null
        or p.project_no = btrim(p_project_no)
      )
      and (
        nullif(btrim(p_country), '') is null
        or position(lower(btrim(p_country)) in lower(p.country_ko)) > 0
      )
      and (
        nullif(btrim(p_category), '') is null
        or f.category = lower(btrim(p_category))
      )
    order by
      r.publication_date desc,
      p.project_no,
      f.pdf_page_start,
      f.finding_id
    limit least(greatest(coalesce(p_max_results, 20), 1), 100)
  )
  select coalesce(
    jsonb_agg(to_jsonb(matched)),
    '[]'::jsonb
  )
  from matched;
$$;

comment on function public.search_koica_evaluation_findings(
  text, text, text, text, integer
) is
  'Bounded full-text and field-filter search over public-approved KOICA endline-evaluation construction findings.';

create function public.get_koica_project_evaluation_findings(p_project_no text)
returns jsonb
language sql
stable
security invoker
set search_path = ''
as $$
  select jsonb_build_object(
    'project_no', p.project_no,
    'country_ko', p.country_ko,
    'project_name', p.project_name,
    'in_area_cost_review', p.in_area_cost_review,
    'has_works_contract', p.has_works_contract,
    'has_construction_candidate', p.has_construction_candidate,
    'manual_construction_relevance', p.manual_construction_relevance,
    'match_status', p.match_status,
    'screening_note', p.screening_note,
    'report_count', (
      select count(distinct m.report_id)
      from koica_search.evaluation_matches as m
      join koica_search.evaluation_reports as r
        on r.report_id = m.report_id and r.is_published
      where m.project_no = p.project_no and m.is_published
    ),
    'finding_count', (
      select count(*)
      from koica_search.evaluation_matches as m
      join koica_search.evaluation_findings as f
        on f.match_id = m.match_id and f.is_published
      where m.project_no = p.project_no and m.is_published
    ),
    'reports', coalesce(
      (
        select jsonb_agg(to_jsonb(report_match) order by report_match.publication_date desc, report_match.report_id)
        from (
          select
            r.report_id,
            r.report_title,
            r.report_type,
            r.project_period,
            r.publication_date,
            r.publication_date_precision,
            r.source_kind,
            r.source_collection,
            r.source_page_url,
            r.source_download_url,
            r.page_count,
            r.extraction_status,
            m.match_id,
            m.report_project_name,
            m.match_method,
            m.relation_scope,
            m.match_score,
            m.match_basis,
            m.reviewed_at
          from koica_search.evaluation_matches as m
          join koica_search.evaluation_reports as r
            on r.report_id = m.report_id and r.is_published
          where m.project_no = p.project_no and m.is_published
        ) as report_match
      ),
      '[]'::jsonb
    ),
    'findings', coalesce(
      (
        select jsonb_agg(to_jsonb(project_finding) order by project_finding.publication_date desc, project_finding.pdf_page_start, project_finding.finding_id)
        from (
          select
            f.finding_id,
            m.match_id,
            r.report_id,
            r.report_title,
            r.publication_date,
            r.source_kind,
            r.source_page_url,
            r.source_download_url,
            m.relation_scope,
            f.category,
            f.field_code,
            f.field_description,
            f.summary_text,
            f.value_text,
            f.value_numeric,
            f.unit,
            f.value_context,
            f.pdf_page_start,
            f.pdf_page_end,
            f.printed_page_label,
            f.evidence_excerpt,
            f.conflict_group,
            f.confidence
          from koica_search.evaluation_matches as m
          join koica_search.evaluation_reports as r
            on r.report_id = m.report_id and r.is_published
          join koica_search.evaluation_findings as f
            on f.match_id = m.match_id and f.is_published
          where m.project_no = p.project_no and m.is_published
        ) as project_finding
      ),
      '[]'::jsonb
    ),
    'data_version', p.data_version
  )
  from koica_search.evaluation_projects as p
  where p.project_no = btrim(p_project_no) and p.is_published;
$$;

comment on function public.get_koica_project_evaluation_findings(text) is
  'Return one reviewed KOICA project screening result with accepted report links and all public-approved structured findings.';

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
        'facility_family', source_case.facility_family,
        'evaluation_match_status', evaluation_project.match_status,
        'evaluation_finding_count', (
          select count(*)
          from koica_search.evaluation_matches as evaluation_match
          join koica_search.evaluation_findings as evaluation_finding
            on evaluation_finding.match_id = evaluation_match.match_id
            and evaluation_finding.is_published
          where
            evaluation_match.project_no = source_case.project_no
            and evaluation_match.is_published
        )
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
    on source_case.case_id = search_result.case_id
  left join koica_search.evaluation_projects as evaluation_project
    on evaluation_project.project_no = source_case.project_no
    and evaluation_project.is_published;
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
  facility_family text,
  evaluation_match_status text,
  evaluation_report_count bigint,
  evaluation_finding_count bigint,
  evaluation_findings jsonb
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
    c.facility_family,
    evaluation_project.match_status,
    (
      select count(distinct evaluation_match.report_id)
      from koica_search.evaluation_matches as evaluation_match
      where
        evaluation_match.project_no = c.project_no
        and evaluation_match.is_published
    ) as evaluation_report_count,
    (
      select count(*)
      from koica_search.evaluation_matches as evaluation_match
      join koica_search.evaluation_findings as evaluation_finding
        on evaluation_finding.match_id = evaluation_match.match_id
        and evaluation_finding.is_published
      where
        evaluation_match.project_no = c.project_no
        and evaluation_match.is_published
    ) as evaluation_finding_count,
    coalesce(
      (
        select jsonb_agg(
          jsonb_build_object(
            'finding_id', evaluation_finding.finding_id,
            'report_id', evaluation_report.report_id,
            'report_title', evaluation_report.report_title,
            'source_page_url', evaluation_report.source_page_url,
            'source_download_url', evaluation_report.source_download_url,
            'category', evaluation_finding.category,
            'field_code', evaluation_finding.field_code,
            'field_description', evaluation_finding.field_description,
            'summary_text', evaluation_finding.summary_text,
            'value_text', evaluation_finding.value_text,
            'value_numeric', evaluation_finding.value_numeric,
            'unit', evaluation_finding.unit,
            'value_context', evaluation_finding.value_context,
            'pdf_page_start', evaluation_finding.pdf_page_start,
            'pdf_page_end', evaluation_finding.pdf_page_end,
            'printed_page_label', evaluation_finding.printed_page_label,
            'evidence_excerpt', evaluation_finding.evidence_excerpt,
            'conflict_group', evaluation_finding.conflict_group,
            'confidence', evaluation_finding.confidence
          )
          order by
            evaluation_report.publication_date desc,
            evaluation_finding.pdf_page_start,
            evaluation_finding.finding_id
        )
        from koica_search.evaluation_matches as evaluation_match
        join koica_search.evaluation_reports as evaluation_report
          on evaluation_report.report_id = evaluation_match.report_id
          and evaluation_report.is_published
        join koica_search.evaluation_findings as evaluation_finding
          on evaluation_finding.match_id = evaluation_match.match_id
          and evaluation_finding.is_published
        where
          evaluation_match.project_no = c.project_no
          and evaluation_match.is_published
      ),
      '[]'::jsonb
    ) as evaluation_findings
  from koica_search.cases as c
  left join koica_search.evaluation_projects as evaluation_project
    on evaluation_project.project_no = c.project_no
    and evaluation_project.is_published
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
  notice_date_end date,
  evaluation_snapshot_generated_at timestamptz,
  evaluation_synced_at timestamptz,
  evaluation_project_count bigint,
  evaluation_accepted_project_count bigint,
  evaluation_report_count bigint,
  evaluation_match_count bigint,
  evaluation_finding_count bigint
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
    max(c.notice_date) as notice_date_end,
    m.evaluation_snapshot_generated_at,
    m.evaluation_synced_at,
    (
      select count(*)
      from koica_search.evaluation_projects as p
      where p.is_published
    ) as evaluation_project_count,
    (
      select count(*)
      from koica_search.evaluation_projects as p
      where p.is_published and p.match_status = 'accepted_match'
    ) as evaluation_accepted_project_count,
    (
      select count(*)
      from koica_search.evaluation_reports as r
      where r.is_published
    ) as evaluation_report_count,
    (
      select count(*)
      from koica_search.evaluation_matches as em
      where em.is_published
    ) as evaluation_match_count,
    (
      select count(*)
      from koica_search.evaluation_findings as f
      where f.is_published
    ) as evaluation_finding_count
  from koica_search.cases as c
  left join koica_search.snapshot_metadata as m on m.singleton
  where c.is_published
  group by
    m.data_version,
    m.source_schema_version,
    m.source_db_sha256,
    m.snapshot_generated_at,
    m.synced_at,
    m.evaluation_snapshot_generated_at,
    m.evaluation_synced_at;
$$;

create function public.sync_koica_evaluation_snapshot(
  p_projects jsonb,
  p_reports jsonb,
  p_matches jsonb,
  p_findings jsonb,
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
  v_project_count integer;
  v_accepted_project_count integer;
  v_report_count integer;
  v_match_count integer;
  v_finding_count integer;
  v_synced_at timestamptz := now();
begin
  if p_projects is null
    or jsonb_typeof(p_projects) <> 'array'
    or jsonb_array_length(p_projects) = 0
  then
    raise exception 'p_projects must be a non-empty JSON array';
  end if;
  if jsonb_array_length(p_projects) > 10000 then
    raise exception 'p_projects exceeds the 10000 row safety limit';
  end if;
  if p_reports is null
    or jsonb_typeof(p_reports) <> 'array'
    or jsonb_array_length(p_reports) = 0
  then
    raise exception 'p_reports must be a non-empty JSON array';
  end if;
  if jsonb_array_length(p_reports) > 10000 then
    raise exception 'p_reports exceeds the 10000 row safety limit';
  end if;
  if p_matches is null
    or jsonb_typeof(p_matches) <> 'array'
    or jsonb_array_length(p_matches) = 0
  then
    raise exception 'p_matches must be a non-empty JSON array';
  end if;
  if jsonb_array_length(p_matches) > 20000 then
    raise exception 'p_matches exceeds the 20000 row safety limit';
  end if;
  if p_findings is null
    or jsonb_typeof(p_findings) <> 'array'
    or jsonb_array_length(p_findings) = 0
  then
    raise exception 'p_findings must be a non-empty JSON array';
  end if;
  if jsonb_array_length(p_findings) > 100000 then
    raise exception 'p_findings exceeds the 100000 row safety limit';
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
  if not exists (
    select 1
    from koica_search.snapshot_metadata as metadata
    where
      metadata.singleton
      and metadata.data_version = p_data_version
      and metadata.source_schema_version = p_source_schema_version
      and metadata.source_db_sha256 = p_source_db_sha256
      and metadata.snapshot_generated_at = p_snapshot_generated_at
  ) then
    raise exception 'evaluation snapshot identity must match the current construction snapshot';
  end if;

  insert into koica_search.evaluation_projects (
    project_no,
    country_ko,
    project_name,
    in_area_cost_review,
    has_works_contract,
    has_construction_candidate,
    manual_construction_relevance,
    match_status,
    screening_note,
    data_version,
    is_published,
    synced_at
  )
  select
    x.project_no,
    x.country_ko,
    x.project_name,
    x.in_area_cost_review,
    x.has_works_contract,
    x.has_construction_candidate,
    x.manual_construction_relevance,
    x.match_status,
    x.screening_note,
    p_data_version,
    coalesce(x.is_published, true),
    v_synced_at
  from jsonb_to_recordset(p_projects) as x(
    project_no text,
    country_ko text,
    project_name text,
    in_area_cost_review boolean,
    has_works_contract boolean,
    has_construction_candidate boolean,
    manual_construction_relevance boolean,
    match_status text,
    screening_note text,
    data_version text,
    is_published boolean
  )
  on conflict (project_no) do update set
    country_ko = excluded.country_ko,
    project_name = excluded.project_name,
    in_area_cost_review = excluded.in_area_cost_review,
    has_works_contract = excluded.has_works_contract,
    has_construction_candidate = excluded.has_construction_candidate,
    manual_construction_relevance = excluded.manual_construction_relevance,
    match_status = excluded.match_status,
    screening_note = excluded.screening_note,
    data_version = excluded.data_version,
    is_published = excluded.is_published,
    synced_at = excluded.synced_at;

  insert into koica_search.evaluation_reports (
    report_id,
    source_kind,
    source_collection,
    report_title,
    report_type,
    project_period,
    publication_date,
    publication_date_precision,
    source_page_url,
    source_download_url,
    page_count,
    extraction_status,
    data_version,
    is_published,
    synced_at
  )
  select
    x.report_id,
    x.source_kind,
    x.source_collection,
    x.report_title,
    x.report_type,
    x.project_period,
    x.publication_date,
    x.publication_date_precision,
    x.source_page_url,
    x.source_download_url,
    x.page_count,
    x.extraction_status,
    p_data_version,
    coalesce(x.is_published, true),
    v_synced_at
  from jsonb_to_recordset(p_reports) as x(
    report_id text,
    source_kind text,
    source_collection text,
    report_title text,
    report_type text,
    project_period text,
    publication_date text,
    publication_date_precision text,
    source_page_url text,
    source_download_url text,
    page_count integer,
    extraction_status text,
    data_version text,
    is_published boolean
  )
  on conflict (report_id) do update set
    source_kind = excluded.source_kind,
    source_collection = excluded.source_collection,
    report_title = excluded.report_title,
    report_type = excluded.report_type,
    project_period = excluded.project_period,
    publication_date = excluded.publication_date,
    publication_date_precision = excluded.publication_date_precision,
    source_page_url = excluded.source_page_url,
    source_download_url = excluded.source_download_url,
    page_count = excluded.page_count,
    extraction_status = excluded.extraction_status,
    data_version = excluded.data_version,
    is_published = excluded.is_published,
    synced_at = excluded.synced_at;

  insert into koica_search.evaluation_matches (
    match_id,
    report_id,
    project_no,
    report_project_name,
    match_method,
    relation_scope,
    match_score,
    match_basis,
    reviewed_at,
    data_version,
    is_published,
    synced_at
  )
  select
    x.match_id,
    x.report_id,
    x.project_no,
    x.report_project_name,
    x.match_method,
    x.relation_scope,
    x.match_score,
    x.match_basis,
    x.reviewed_at,
    p_data_version,
    coalesce(x.is_published, true),
    v_synced_at
  from jsonb_to_recordset(p_matches) as x(
    match_id text,
    report_id text,
    project_no text,
    report_project_name text,
    match_method text,
    relation_scope text,
    match_score numeric,
    match_basis text,
    reviewed_at date,
    data_version text,
    is_published boolean
  )
  on conflict (match_id) do update set
    report_id = excluded.report_id,
    project_no = excluded.project_no,
    report_project_name = excluded.report_project_name,
    match_method = excluded.match_method,
    relation_scope = excluded.relation_scope,
    match_score = excluded.match_score,
    match_basis = excluded.match_basis,
    reviewed_at = excluded.reviewed_at,
    data_version = excluded.data_version,
    is_published = excluded.is_published,
    synced_at = excluded.synced_at;

  insert into koica_search.evaluation_findings (
    finding_id,
    match_id,
    category,
    field_code,
    field_description,
    summary_text,
    value_text,
    value_numeric,
    unit,
    value_context,
    pdf_page_start,
    pdf_page_end,
    printed_page_label,
    evidence_excerpt,
    conflict_group,
    confidence,
    search_text,
    data_version,
    is_published,
    synced_at
  )
  select
    x.finding_id,
    x.match_id,
    x.category,
    x.field_code,
    x.field_description,
    x.summary_text,
    x.value_text,
    x.value_numeric,
    x.unit,
    x.value_context,
    x.pdf_page_start,
    x.pdf_page_end,
    x.printed_page_label,
    x.evidence_excerpt,
    x.conflict_group,
    x.confidence,
    x.search_text,
    p_data_version,
    coalesce(x.is_published, true),
    v_synced_at
  from jsonb_to_recordset(p_findings) as x(
    finding_id text,
    match_id text,
    category text,
    field_code text,
    field_description text,
    summary_text text,
    value_text text,
    value_numeric numeric,
    unit text,
    value_context text,
    pdf_page_start integer,
    pdf_page_end integer,
    printed_page_label text,
    evidence_excerpt text,
    conflict_group text,
    confidence text,
    search_text text,
    data_version text,
    is_published boolean
  )
  on conflict (finding_id) do update set
    match_id = excluded.match_id,
    category = excluded.category,
    field_code = excluded.field_code,
    field_description = excluded.field_description,
    summary_text = excluded.summary_text,
    value_text = excluded.value_text,
    value_numeric = excluded.value_numeric,
    unit = excluded.unit,
    value_context = excluded.value_context,
    pdf_page_start = excluded.pdf_page_start,
    pdf_page_end = excluded.pdf_page_end,
    printed_page_label = excluded.printed_page_label,
    evidence_excerpt = excluded.evidence_excerpt,
    conflict_group = excluded.conflict_group,
    confidence = excluded.confidence,
    search_text = excluded.search_text,
    data_version = excluded.data_version,
    is_published = excluded.is_published,
    synced_at = excluded.synced_at;

  delete from koica_search.evaluation_findings as f
  where not exists (
    select 1
    from jsonb_to_recordset(p_findings) as x(finding_id text)
    where x.finding_id = f.finding_id
  );

  delete from koica_search.evaluation_matches as m
  where not exists (
    select 1
    from jsonb_to_recordset(p_matches) as x(match_id text)
    where x.match_id = m.match_id
  );

  delete from koica_search.evaluation_reports as r
  where not exists (
    select 1
    from jsonb_to_recordset(p_reports) as x(report_id text)
    where x.report_id = r.report_id
  );

  delete from koica_search.evaluation_projects as p
  where not exists (
    select 1
    from jsonb_to_recordset(p_projects) as x(project_no text)
    where x.project_no = p.project_no
  );

  update koica_search.snapshot_metadata
  set
    evaluation_snapshot_generated_at = p_snapshot_generated_at,
    evaluation_synced_at = v_synced_at
  where singleton;

  select
    count(*),
    count(*) filter (where match_status = 'accepted_match')
  into v_project_count, v_accepted_project_count
  from koica_search.evaluation_projects
  where is_published;

  select count(*) into v_report_count
  from koica_search.evaluation_reports
  where is_published;
  select count(*) into v_match_count
  from koica_search.evaluation_matches
  where is_published;
  select count(*) into v_finding_count
  from koica_search.evaluation_findings
  where is_published;

  return jsonb_build_object(
    'data_version', p_data_version,
    'source_schema_version', p_source_schema_version,
    'source_db_sha256', p_source_db_sha256,
    'snapshot_generated_at', p_snapshot_generated_at,
    'evaluation_projects', v_project_count,
    'evaluation_accepted_projects', v_accepted_project_count,
    'evaluation_reports', v_report_count,
    'evaluation_matches', v_match_count,
    'evaluation_findings', v_finding_count,
    'synced_at', v_synced_at
  );
end;
$$;

revoke all on function public.search_koica_evaluation_findings(
  text, text, text, text, integer
) from public, anon, authenticated, service_role;
revoke all on function public.get_koica_project_evaluation_findings(text)
  from public, anon, authenticated, service_role;
revoke all on function public.search_koica_construction_cases(
  text, text, text, text, numeric, integer
) from public, anon, authenticated, service_role;
revoke all on function public.get_koica_reference_case(text)
  from public, anon, authenticated, service_role;
revoke all on function public.get_koica_search_status()
  from public, anon, authenticated, service_role;
revoke all on function public.sync_koica_evaluation_snapshot(
  jsonb, jsonb, jsonb, jsonb, text, text, text, timestamptz
) from public, anon, authenticated, service_role;

grant execute on function public.search_koica_evaluation_findings(
  text, text, text, text, integer
) to anon, authenticated, service_role;
grant execute on function public.get_koica_project_evaluation_findings(text)
  to anon, authenticated, service_role;
grant execute on function public.search_koica_construction_cases(
  text, text, text, text, numeric, integer
) to anon, authenticated, service_role;
grant execute on function public.get_koica_reference_case(text)
  to anon, authenticated, service_role;
grant execute on function public.get_koica_search_status()
  to anon, authenticated, service_role;
grant execute on function public.sync_koica_evaluation_snapshot(
  jsonb, jsonb, jsonb, jsonb, text, text, text, timestamptz
) to service_role;

notify pgrst, 'reload schema';
