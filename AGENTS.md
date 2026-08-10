# Repository agent instructions

## Comparable-construction requests

When a user asks for comparable KOICA construction projects, search the data instead of
stopping after reading the repository description.

Use this read-only fallback order:

1. If the MCP tools are available, call `koica_construction_data_status`, then
   `search_koica_construction_cases`, and call `get_koica_construction_case` for cases
   that support the answer.
2. If those tools are unavailable, call the public Supabase read-only RPC documented in
   `docs/public-data-access.md`.
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

- Check `data_status`, `observed_at`, and `missing_is_zero` before interpreting results.
- Treat `null` as unconfirmed, never as zero.
- For a user-facing project list, group repeated tenders by `project_no`; keep re-bids and
  related design, supervision, goods, and construction notices subordinate to that project.
- Verify returned country, facility type, work type, and area. Search inputs affect ranking
  and must not be described as strict filters without checking the returned fields.
- Label execution ceilings, estimates, and bid limits accurately. Nominal USD/m2 is an
  unadjusted screening value, not a future-project recommendation.
- Do not say data has been collected or structured before a query succeeds. Do not repeat
  the same progress sentence. The final answer must contain the actual cases or the
  path-specific failure evidence.

## Scope and safety

All public query paths are read-only. Never expose a Supabase secret or service-role key,
and never use contact details embedded in procurement evidence except to verify the source.
