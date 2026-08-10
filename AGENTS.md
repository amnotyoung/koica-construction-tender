# Repository agent instructions

## Comparable-construction requests

When a user asks for comparable KOICA construction projects, search the data instead of
stopping after reading the repository description.

Use this read-only fallback order:

1. Call the public Supabase read-only RPC documented in `docs/public-data-access.md`.
   Check `get_koica_search_status()`, call `search_koica_construction_cases(...)`, and
   then call `get_koica_reference_case(p_case_id)` for cases used in the answer.
2. If the MCP tools are available, they may be used as a convenience wrapper: call
   `koica_construction_data_status`, then `search_koica_construction_cases`, and call
   `get_koica_construction_case` for cases that support the answer.
3. If network access is unavailable and this checkout exists, query
   `outputs/koica-construction-distribution/KOICA_건축사업_사례DB_2016-2025.sqlite`
   in read-only mode.
4. Use the GitHub connector or the raw-file URL only when the database must be obtained
   from GitHub.

A browser, crawler, or robots-policy error applies only to that access path. It is not
evidence that this public repository is private or that its data is unavailable. Do not
report the data as inaccessible until the alternatives above have been attempted. If all
paths fail, name each attempted path and its actual error instead of generalizing it to a
GitHub policy or a data absence.

## Result integrity

- Check `data_status`, `observed_at`, `missing_is_zero`, `source_schema_version`, and
  `source_db_sha256` before interpreting results. A shared audit date does not prove that
  two snapshots use the same schema or source file.
- Treat `null` as unconfirmed, never as zero.
- For a user-facing project list, group repeated tenders by `project_no`; keep re-bids and
  related design, supervision, goods, and construction notices subordinate to that project.
- Check `case_kind`. `DESIGN_SUPERVISION_REFERENCE` is a reviewed design/supervision-stage
  comparator, not a construction contract; label its amount stage explicitly.
- Verify returned country, facility type, work type, and area. Search inputs affect ranking
  and must not be described as strict filters without checking the returned fields.
- Use `facility_family` and text search as well as `facility_type`; coarse source values such
  as `기타·미분류` must not silently exclude medical or education cases.
- Use `evaluation_match_status` and `evaluation_finding_count` from comparable-case results.
  For evaluation evidence, call `get_koica_reference_case(p_case_id)` or the public
  `get_koica_project_evaluation_findings(p_project_no)` and
  `search_koica_evaluation_findings(...)` RPCs before asking the user to download SQLite.
- Interpret `no_accepted_same_project_report` only as no accepted same-project match in the
  reviewed corpus, never as proof that an endline-evaluation report does not exist.
- Label execution ceilings, estimates, and bid limits accurately. Nominal USD/m2 is an
  unadjusted screening value, not a future-project recommendation.
- Do not say data has been collected or structured before a query succeeds. Do not repeat
  the same progress sentence. The final answer must contain the actual cases or the
  path-specific failure evidence.

## Scope and safety

All public query paths are read-only. Never expose a Supabase secret or service-role key,
and never use contact details embedded in procurement evidence except to verify the source.
Do not expose evaluation local paths, individual file hashes, OCR digests, or internal review
notes; the public-approved excerpt and its physical PDF page are the public evidence fields.
