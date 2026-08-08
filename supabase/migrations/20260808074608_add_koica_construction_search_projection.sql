-- Stable MCP-facing projection. The underlying table-returning RPC predates
-- representative_bid_no, so this wrapper enriches each row without changing
-- the already-deployed function signature.
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
        'representative_bid_no', source_case.representative_bid_no
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

revoke all on function public.search_koica_construction_cases(
  text,
  text,
  text,
  text,
  numeric,
  integer
) from public, anon, authenticated, service_role;

grant execute on function public.search_koica_construction_cases(
  text,
  text,
  text,
  text,
  numeric,
  integer
) to service_role;
