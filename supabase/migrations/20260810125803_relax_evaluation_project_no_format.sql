-- KOICA source identifiers are not uniformly YYYY-NNNNN. Preserve official
-- identifiers such as 201601, EC2016001, IDKOICA2016001, and L2017-0004.

alter table koica_search.evaluation_projects
  drop constraint evaluation_projects_project_no_format,
  add constraint evaluation_projects_project_no_not_blank check (
    btrim(project_no) <> ''
  );

comment on column koica_search.evaluation_projects.project_no is
  'KOICA source project identifier preserved verbatim; historical formats are heterogeneous.';
