#!/usr/bin/env python3
"""Create the normalized SQLite source of truth for KOICA construction research."""

from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
import unicodedata
from pathlib import Path

try:
    from scripts.snapshot_koica_evaluation_index import (
        validate_snapshot as validate_official_index_snapshot,
    )
except ModuleNotFoundError:  # Direct execution via ``python scripts/...``.
    from snapshot_koica_evaluation_index import (
        validate_snapshot as validate_official_index_snapshot,
    )


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "outputs" / "koica-construction-distribution"
DB_PATH = OUTPUT / "KOICA_건축사업_사례DB_2016-2025.sqlite"

DATASETS = [
    {
        "id": "2016-2020",
        "root": ROOT / "data_2016_2020",
        "start_date": "2016-01-01",
        "end_date": "2020-12-31",
    },
    {
        "id": "2021-2025",
        "root": ROOT / "data",
        "start_date": "2021-01-01",
        "end_date": "2025-12-31",
    },
]


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_evaluation_curation(path: Path) -> dict:
    curation = load(path)
    include_files = curation.get("include_files", [])
    if not isinstance(include_files, list) or len(include_files) != len(
        set(include_files)
    ):
        raise RuntimeError("evaluation curation include_files are invalid")
    for filename in include_files:
        if not isinstance(filename, str) or Path(filename).name != filename:
            raise RuntimeError("evaluation curation include must be a basename")
        fragment = load(path.parent / filename)
        if fragment.get("fragment_schema_version") != "1.0":
            raise RuntimeError("evaluation curation fragment schema is invalid")
        for field in (
            "multi_project_report_ids", "reports", "matches", "findings"
        ):
            values = fragment.get(field, [])
            if not isinstance(values, list):
                raise RuntimeError("evaluation curation fragment list is invalid")
            curation.setdefault(field, []).extend(values)
        fragment_review = fragment.get("review", {})
        for field in ("excluded_candidates", "identity_conflicts"):
            values = fragment_review.get(field, [])
            if not isinstance(values, list):
                raise RuntimeError("evaluation curation review fragment is invalid")
            curation.setdefault("review", {}).setdefault(field, []).extend(values)
    official = curation.get("official_source") or {}
    snapshot_file = official.get("index_snapshot_file")
    if snapshot_file:
        if not isinstance(snapshot_file, str) or Path(snapshot_file).name != snapshot_file:
            raise RuntimeError("evaluation index snapshot must be a basename")
        official["index_snapshot"] = validate_official_index_snapshot(
            load(path.parent / snapshot_file)
        )
    return curation


def canonical_json_digest(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def nullable_float(value):
    if value in (None, ""):
        return None
    return float(value)


def nullable_int(value):
    if value in (None, ""):
        return None
    return int(value)


def portable_path(value: str) -> str:
    if not value:
        return ""
    path = Path(value)
    try:
        return str(path.resolve().relative_to(ROOT))
    except Exception:
        # Manifests may have been collected from another checkout/worktree of
        # this repository.  Preserve the repository-relative data tail rather
        # than re-publishing that checkout's absolute local path.
        parts = path.parts
        for marker in ("data_2016_2020", "data"):
            if marker in parts:
                return str(Path(*parts[parts.index(marker) :]))
        return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE metadata (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE datasets (
  dataset_id TEXT PRIMARY KEY,
  start_date TEXT NOT NULL,
  end_date TEXT NOT NULL,
  bids_count INTEGER NOT NULL,
  details_count INTEGER NOT NULL,
  attachments_count INTEGER NOT NULL,
  documents_count INTEGER NOT NULL,
  evidence_count INTEGER NOT NULL
);

CREATE TABLE bids (
  bid_no TEXT PRIMARY KEY,
  dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id),
  bid_base_no TEXT,
  order_no TEXT,
  list_number INTEGER,
  title TEXT,
  contract_type TEXT,
  contract_method TEXT,
  notice_date TEXT,
  manager TEXT,
  construction_candidate INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE details (
  bid_no TEXT PRIMARY KEY REFERENCES bids(bid_no),
  dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id),
  attachment_group_no TEXT,
  detail_url TEXT,
  collected_at TEXT,
  fields_json TEXT NOT NULL
);

CREATE TABLE projects (
  bid_no TEXT PRIMARY KEY REFERENCES bids(bid_no),
  dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id),
  project_no TEXT,
  country_ko TEXT,
  country_en TEXT,
  region TEXT,
  project_name TEXT,
  bid_title_ko TEXT,
  bid_title_en TEXT,
  facility_type TEXT,
  work_type TEXT,
  contract_type TEXT,
  contract_method TEXT,
  selection_method TEXT,
  ceiling_usd_raw TEXT,
  ceiling_krw_raw TEXT,
  notice_date TEXT,
  detail_url TEXT
);

CREATE TABLE attachments (
  dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id),
  bid_no TEXT NOT NULL REFERENCES bids(bid_no),
  attachment_sn TEXT NOT NULL,
  attachment_group_no TEXT,
  original_name TEXT,
  stored_name TEXT,
  mime_type TEXT,
  bytes INTEGER,
  registered_at TEXT,
  relative_path TEXT,
  sha256 TEXT,
  status TEXT,
  PRIMARY KEY (bid_no, attachment_sn)
);

CREATE TABLE documents (
  dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id),
  bid_no TEXT NOT NULL REFERENCES bids(bid_no),
  source_file TEXT NOT NULL,
  extension TEXT,
  bytes INTEGER,
  text_chunks INTEGER,
  evidence_count INTEGER,
  PRIMARY KEY (dataset_id, bid_no, source_file)
);

CREATE TABLE evidence (
  evidence_id INTEGER PRIMARY KEY AUTOINCREMENT,
  dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id),
  bid_no TEXT NOT NULL REFERENCES bids(bid_no),
  category TEXT,
  matched_keywords TEXT,
  area_mentions TEXT,
  currency_mentions TEXT,
  percentage_mentions TEXT,
  source_file TEXT,
  source_locator TEXT,
  evidence_text TEXT,
  review_status TEXT
);

CREATE TABLE reviewed_cases (
  bid_no TEXT PRIMARY KEY REFERENCES bids(bid_no),
  project_no TEXT,
  notice_date TEXT,
  price_year_decimal REAL,
  country TEXT,
  region TEXT,
  facility_type TEXT,
  work_type TEXT,
  gross_floor_area_m2 REAL,
  cost_usd_nominal REAL,
  direct_unit_usd_m2 REAL,
  unit_usd_m2_nominal REAL,
  evidence_grade TEXT CHECK (evidence_grade IN ('A','B','C')),
  area_basis TEXT,
  cost_stage TEXT,
  scope_caution TEXT,
  normalization_status TEXT,
  recommended_unit_rate TEXT CHECK (recommended_unit_rate IN ('예','아니오')),
  allowed_use TEXT,
  source_period TEXT,
  source_file TEXT,
  source_locator TEXT,
  source_url TEXT,
  evidence_summary TEXT
);

CREATE TABLE area_cost_notice_review (
  bid_no TEXT PRIMARY KEY REFERENCES bids(bid_no),
  project_no TEXT NOT NULL,
  bid_base_no TEXT,
  package_id TEXT,
  notice_date TEXT,
  country_ko TEXT,
  title TEXT,
  scope_role TEXT NOT NULL,
  record_cost_semantics TEXT NOT NULL,
  record_scope_status TEXT NOT NULL,
  same_scope_status TEXT NOT NULL,
  notice_ceiling_usd REAL,
  selected_construction_cost_usd REAL,
  amount_stage TEXT,
  selected_area_m2 REAL,
  area_semantics TEXT,
  area_aggregation TEXT,
  screening_unit_usd_m2 REAL,
  notice_ceiling_to_selected_gap_pct REAL,
  final_grade TEXT NOT NULL,
  compact_grade TEXT NOT NULL CHECK (compact_grade IN ('A','B','C','C?','U','X')),
  verification_level TEXT NOT NULL,
  unit_cost_allowed_use TEXT NOT NULL,
  direct_future_estimate_ready INTEGER NOT NULL CHECK (direct_future_estimate_ready IN (0,1)),
  sample_weight_notice INTEGER NOT NULL CHECK (sample_weight_notice IN (0,1)),
  is_bid_base_representative INTEGER NOT NULL CHECK (is_bid_base_representative IN (0,1)),
  is_project_display_representative INTEGER NOT NULL CHECK (is_project_display_representative IN (0,1)),
  legacy_reviewed_case INTEGER NOT NULL CHECK (legacy_reviewed_case IN (0,1)),
  strict_attachment_review INTEGER NOT NULL CHECK (strict_attachment_review IN (0,1)),
  indexed_attachment_count INTEGER NOT NULL,
  spreadsheet_count INTEGER NOT NULL,
  boq_named_file_count INTEGER NOT NULL,
  quantity_table_file_count INTEGER NOT NULL,
  priced_table_file_count INTEGER NOT NULL,
  grade_detail TEXT,
  manual_note TEXT,
  amount_source_file TEXT,
  amount_source_locator TEXT,
  area_source_file TEXT,
  area_source_locator TEXT,
  area_quote TEXT,
  source_url TEXT,
  grade_system_version TEXT NOT NULL,
  audit_date TEXT NOT NULL
);

CREATE TABLE area_cost_bid_group_review (
  bid_base_no TEXT PRIMARY KEY,
  project_no TEXT NOT NULL,
  country_ko TEXT,
  notice_count INTEGER NOT NULL,
  bid_nos TEXT NOT NULL,
  representative_bid_no TEXT NOT NULL REFERENCES bids(bid_no),
  latest_notice_date TEXT,
  representative_title TEXT,
  best_grade TEXT NOT NULL,
  scope_role TEXT,
  same_scope_status TEXT,
  area_m2 REAL,
  construction_cost_usd REAL,
  screening_unit_usd_m2 REAL,
  duplicate_rule TEXT
);

CREATE TABLE area_cost_project_review (
  project_no TEXT PRIMARY KEY,
  country_ko TEXT,
  project_name TEXT,
  notice_count INTEGER NOT NULL,
  bid_base_group_count INTEGER NOT NULL,
  valid_area_cost_notice_count INTEGER NOT NULL,
  valid_bid_nos TEXT,
  all_bid_nos TEXT NOT NULL,
  display_representative_bid TEXT NOT NULL REFERENCES bids(bid_no),
  technical_evidence_bid TEXT,
  price_evidence_bid TEXT,
  best_grade TEXT NOT NULL,
  compact_grade TEXT NOT NULL CHECK (compact_grade IN ('A','B','C','C?','U','X')),
  verification_level TEXT NOT NULL,
  scope_status TEXT NOT NULL,
  representative_area_m2 REAL,
  representative_construction_cost_usd REAL,
  representative_amount_stage TEXT,
  screening_unit_usd_m2 REAL,
  unit_cost_allowed_use TEXT NOT NULL,
  direct_future_estimate_ready INTEGER NOT NULL CHECK (direct_future_estimate_ready IN (0,1)),
  screening_sample_weight INTEGER NOT NULL CHECK (screening_sample_weight IN (0,1)),
  direct_estimate_sample_weight INTEGER NOT NULL CHECK (direct_estimate_sample_weight IN (0,1)),
  related_other_package_grade TEXT,
  related_other_package_bid TEXT,
  related_other_package_note TEXT,
  duplicate_and_scope_warning TEXT,
  grade_detail TEXT,
  source_url TEXT,
  grade_system_version TEXT NOT NULL,
  audit_date TEXT NOT NULL
);

CREATE TABLE area_cost_review_summary (
  audit_date TEXT PRIMARY KEY,
  schema_version TEXT NOT NULL,
  grade_system_version TEXT NOT NULL,
  notice_rows INTEGER NOT NULL,
  bid_base_groups INTEGER NOT NULL,
  project_rows INTEGER NOT NULL,
  summary_json TEXT NOT NULL
);

CREATE TABLE evaluation_field_definitions (
  field_code TEXT PRIMARY KEY CHECK (length(trim(field_code)) > 0),
  category TEXT NOT NULL CHECK (category IN (
    'facility_scope','cost_procurement','schedule','quality_safety',
    'operations_maintenance','utilization_results','risk_issue',
    'lesson_recommendation'
  )),
  value_kind TEXT NOT NULL CHECK (value_kind IN ('text','numeric_optional')),
  allowed_units_json TEXT NOT NULL CHECK (json_valid(allowed_units_json)),
  description TEXT NOT NULL CHECK (length(trim(description)) > 0),
  UNIQUE (field_code, category)
);

CREATE TABLE evaluation_corpus_files (
  source_file TEXT PRIMARY KEY CHECK (length(trim(source_file)) > 0),
  source_collection TEXT NOT NULL CHECK (length(trim(source_collection)) > 0),
  sha256 TEXT NOT NULL CHECK (
    length(sha256) = 64 AND sha256 NOT GLOB '*[^0-9a-f]*'
  ),
  file_bytes INTEGER NOT NULL CHECK (
    typeof(file_bytes) = 'integer' AND file_bytes > 0
  ),
  page_count INTEGER NOT NULL CHECK (
    typeof(page_count) = 'integer' AND page_count > 0
  ),
  text_char_count INTEGER NOT NULL CHECK (
    typeof(text_char_count) = 'integer' AND text_char_count >= 0
  ),
  meaningful_text_char_count INTEGER NOT NULL CHECK (
    typeof(meaningful_text_char_count) = 'integer'
    AND meaningful_text_char_count >= 0
  ),
  text_page_coverage REAL NOT NULL CHECK (
    typeof(text_page_coverage) IN ('real','integer')
    AND text_page_coverage >= 0 AND text_page_coverage <= 1
  ),
  extraction_status TEXT NOT NULL CHECK (
    extraction_status IN ('text','partial_text','ocr_required')
  ),
  duplicate_of_source_file TEXT REFERENCES evaluation_corpus_files(source_file),
  CHECK (duplicate_of_source_file IS NULL OR duplicate_of_source_file <> source_file)
);

CREATE TABLE evaluation_reports (
  report_id TEXT PRIMARY KEY,
  source_kind TEXT NOT NULL CHECK (
    source_kind IN ('local_corpus','koica_official_site')
  ),
  source_collection TEXT NOT NULL CHECK (length(trim(source_collection)) > 0),
  source_document_id TEXT NOT NULL CHECK (length(trim(source_document_id)) > 0),
  source_file TEXT NOT NULL UNIQUE CHECK (length(trim(source_file)) > 0),
  source_page_url TEXT,
  source_download_url TEXT,
  source_post_id TEXT,
  source_attachment_id TEXT,
  sha256 TEXT NOT NULL CHECK (
    length(sha256) = 64 AND sha256 NOT GLOB '*[^0-9a-f]*'
  ),
  file_bytes INTEGER NOT NULL CHECK (
    typeof(file_bytes) = 'integer' AND file_bytes > 0
  ),
  page_count INTEGER NOT NULL CHECK (
    typeof(page_count) = 'integer' AND page_count > 0
  ),
  text_char_count INTEGER NOT NULL CHECK (
    typeof(text_char_count) = 'integer' AND text_char_count >= 0
  ),
  meaningful_text_char_count INTEGER NOT NULL CHECK (
    typeof(meaningful_text_char_count) = 'integer'
    AND meaningful_text_char_count >= 0
  ),
  text_page_coverage REAL NOT NULL CHECK (
    typeof(text_page_coverage) IN ('real','integer')
    AND text_page_coverage >= 0 AND text_page_coverage <= 1
  ),
  report_title TEXT NOT NULL CHECK (length(trim(report_title)) > 0),
  report_type TEXT NOT NULL CHECK (report_type = 'endline_evaluation'),
  project_period TEXT NOT NULL CHECK (length(trim(project_period)) > 0),
  publication_date TEXT NOT NULL CHECK (length(publication_date) IN (7,10)),
  publication_date_precision TEXT NOT NULL CHECK (
    publication_date_precision IN ('month','day')
    AND (publication_date_precision <> 'month' OR length(publication_date) = 7)
    AND (publication_date_precision <> 'day' OR length(publication_date) = 10)
  ),
  duplicate_of_report_id TEXT REFERENCES evaluation_reports(report_id),
  extraction_method TEXT NOT NULL CHECK (length(trim(extraction_method)) > 0),
  extraction_status TEXT NOT NULL
    CHECK (extraction_status IN ('text','partial_text','ocr_text')),
  ocr_text_digest TEXT CHECK (
    ocr_text_digest IS NULL OR (
      length(ocr_text_digest) = 64
      AND ocr_text_digest NOT GLOB '*[^0-9a-f]*'
    )
  ),
  ocr_text_page_count INTEGER CHECK (
    ocr_text_page_count IS NULL OR (
      typeof(ocr_text_page_count) = 'integer' AND ocr_text_page_count > 0
    )
  ),
  ocr_text_digest_algorithm TEXT,
  CHECK (duplicate_of_report_id IS NULL OR duplicate_of_report_id <> report_id),
  CHECK (
    (extraction_status = 'ocr_text'
      AND ocr_text_digest IS NOT NULL
      AND ocr_text_page_count = page_count
      AND length(trim(ocr_text_digest_algorithm)) > 0)
    OR
    (extraction_status <> 'ocr_text'
      AND ocr_text_digest IS NULL
      AND ocr_text_page_count IS NULL
      AND ocr_text_digest_algorithm IS NULL)
  ),
  CHECK (
    (source_kind = 'local_corpus'
      AND source_page_url IS NULL AND source_download_url IS NULL
      AND source_post_id IS NULL AND source_attachment_id IS NULL)
    OR
    (source_kind = 'koica_official_site'
      AND source_page_url LIKE
        'https://www.koica.go.kr/sites/evaluation_kr/article/view/%'
      AND source_download_url LIKE
        'https://www.koica.go.kr/sites/evaluation_kr/common/filedownload/%'
      AND length(trim(source_post_id)) > 0
      AND length(trim(source_attachment_id)) > 0)
  )
);

CREATE TABLE evaluation_project_matches (
  match_id TEXT PRIMARY KEY,
  report_id TEXT NOT NULL REFERENCES evaluation_reports(report_id),
  project_no TEXT NOT NULL REFERENCES evaluation_project_screening(project_no),
  db_country TEXT NOT NULL CHECK (length(trim(db_country)) > 0),
  db_project_name TEXT NOT NULL CHECK (length(trim(db_project_name)) > 0),
  report_project_name TEXT NOT NULL CHECK (length(trim(report_project_name)) > 0),
  match_method TEXT NOT NULL CHECK (
    match_method IN ('exact_official_title','exact_component_title')
  ),
  relation_scope TEXT NOT NULL CHECK (
    relation_scope IN ('same_project','same_project_component')
  ),
  match_score REAL NOT NULL CHECK (
    typeof(match_score) IN ('real','integer')
    AND match_score >= 0.85 AND match_score <= 1
  ),
  match_basis TEXT NOT NULL CHECK (length(trim(match_basis)) > 0),
  review_status TEXT NOT NULL CHECK (review_status IN ('accepted')),
  reviewed_at TEXT NOT NULL CHECK (length(reviewed_at) = 10),
  UNIQUE (report_id, project_no)
);

CREATE TABLE evaluation_project_screening (
  project_no TEXT PRIMARY KEY,
  country_ko TEXT NOT NULL CHECK (length(trim(country_ko)) > 0),
  project_name TEXT NOT NULL CHECK (length(trim(project_name)) > 0),
  in_area_cost_review INTEGER NOT NULL CHECK (in_area_cost_review IN (0,1)),
  has_works_contract INTEGER NOT NULL CHECK (has_works_contract IN (0,1)),
  has_construction_candidate INTEGER NOT NULL
    CHECK (has_construction_candidate IN (0,1)),
  manual_construction_relevance INTEGER NOT NULL
    CHECK (manual_construction_relevance IN (0,1)),
  status TEXT NOT NULL CHECK (
    status IN (
      'accepted_match','candidate_reviewed_not_accepted',
      'no_accepted_same_project_report'
    )
  ),
  report_ids_json TEXT NOT NULL CHECK (json_valid(report_ids_json)),
  note TEXT NOT NULL CHECK (length(trim(note)) > 0)
);

CREATE TABLE evaluation_findings (
  finding_id TEXT PRIMARY KEY,
  match_id TEXT NOT NULL REFERENCES evaluation_project_matches(match_id),
  category TEXT NOT NULL CHECK (category IN (
    'facility_scope','cost_procurement','schedule','quality_safety',
    'operations_maintenance','utilization_results','risk_issue',
    'lesson_recommendation'
  )),
  field_code TEXT NOT NULL,
  summary_text TEXT NOT NULL CHECK (
    length(trim(summary_text)) BETWEEN 15 AND 600
  ),
  value_text TEXT,
  value_numeric REAL CHECK (
    value_numeric IS NULL OR typeof(value_numeric) IN ('real','integer')
  ),
  unit TEXT,
  value_context TEXT,
  pdf_page_start INTEGER NOT NULL CHECK (pdf_page_start > 0),
  pdf_page_end INTEGER NOT NULL CHECK (pdf_page_end >= pdf_page_start),
  printed_page_label TEXT,
  evidence_excerpt TEXT NOT NULL CHECK (
    length(trim(evidence_excerpt)) BETWEEN 20 AND 400
  ),
  conflict_group TEXT,
  review_note TEXT,
  confidence TEXT NOT NULL CHECK (confidence IN ('high','medium')),
  review_status TEXT NOT NULL CHECK (review_status IN ('accepted')),
  public_excerpt_approved INTEGER NOT NULL CHECK (public_excerpt_approved = 1),
  FOREIGN KEY (field_code, category)
    REFERENCES evaluation_field_definitions(field_code, category),
  CHECK ((value_numeric IS NULL AND unit IS NULL)
      OR (value_numeric IS NOT NULL AND unit IS NOT NULL))
);

CREATE TABLE fee_benchmarks (
  fee_id INTEGER PRIMARY KEY AUTOINCREMENT,
  bid_no TEXT,
  country TEXT,
  facility_type TEXT,
  gross_floor_area_m2 REAL,
  construction_cost_usd REAL,
  design_fee_usd REAL,
  supervision_fee_usd REAL,
  combined_fee_usd REAL,
  design_rate REAL,
  supervision_rate REAL,
  combined_rate REAL,
  tax_note TEXT,
  source_file TEXT,
  source_locator TEXT,
  evidence_summary TEXT
);

CREATE TABLE price_index_policy (
  priority INTEGER PRIMARY KEY,
  index_class TEXT NOT NULL UNIQUE,
  label TEXT NOT NULL,
  intended_use TEXT NOT NULL,
  requirements TEXT NOT NULL
);

CREATE TABLE price_index_sources (
  source_id TEXT PRIMARY KEY,
  country TEXT NOT NULL,
  iso3 TEXT NOT NULL,
  priority INTEGER REFERENCES price_index_policy(priority),
  index_class TEXT NOT NULL,
  series_name TEXT NOT NULL,
  provider TEXT NOT NULL,
  provider_url TEXT NOT NULL,
  indicator_code TEXT,
  frequency TEXT NOT NULL,
  unit TEXT NOT NULL,
  construction_specific INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL,
  notes TEXT
);

CREATE TABLE price_index_values (
  source_id TEXT NOT NULL REFERENCES price_index_sources(source_id),
  period TEXT NOT NULL,
  native_period TEXT,
  value REAL NOT NULL CHECK (value > 0),
  is_actual INTEGER NOT NULL CHECK (is_actual IN (0,1)),
  observation_status TEXT NOT NULL,
  release_url TEXT,
  retrieved_at TEXT NOT NULL,
  PRIMARY KEY (source_id, period)
);

CREATE TABLE national_index_source_audit (
  country TEXT PRIMARY KEY,
  iso3 TEXT NOT NULL,
  candidate_priority INTEGER,
  candidate_name TEXT,
  provider TEXT NOT NULL,
  source_url TEXT NOT NULL,
  status TEXT NOT NULL,
  fallback_loaded INTEGER NOT NULL CHECK (fallback_loaded IN (0,1)),
  audited_at TEXT NOT NULL
);

CREATE TABLE normalization_runs (
  run_id INTEGER PRIMARY KEY AUTOINCREMENT,
  bid_no TEXT NOT NULL REFERENCES reviewed_cases(bid_no),
  target_period TEXT NOT NULL,
  source_id TEXT NOT NULL REFERENCES price_index_sources(source_id),
  source_period TEXT NOT NULL,
  index_source REAL NOT NULL,
  index_target REAL NOT NULL,
  index_factor REAL NOT NULL,
  fx_source REAL,
  fx_target REAL,
  fx_factor REAL,
  adjusted_unit_usd_m2 REAL,
  result_status TEXT NOT NULL,
  limitation_note TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE INDEX idx_bids_notice_date ON bids(notice_date);
CREATE INDEX idx_bids_contract_type ON bids(contract_type);
CREATE INDEX idx_projects_country ON projects(country_en);
CREATE INDEX idx_projects_project_no ON projects(project_no);
CREATE INDEX idx_attachments_sha256 ON attachments(sha256);
CREATE INDEX idx_documents_bid ON documents(bid_no);
CREATE INDEX idx_evidence_bid_category ON evidence(bid_no, category);
CREATE INDEX idx_reviewed_country_type ON reviewed_cases(country, facility_type, work_type);
CREATE INDEX idx_reviewed_notice_date ON reviewed_cases(notice_date);
CREATE INDEX idx_area_cost_notice_project_grade
  ON area_cost_notice_review(project_no, compact_grade);
CREATE INDEX idx_area_cost_notice_country_role
  ON area_cost_notice_review(country_ko, scope_role);
CREATE INDEX idx_area_cost_project_country_grade
  ON area_cost_project_review(country_ko, compact_grade);
CREATE INDEX idx_evaluation_corpus_sha256
  ON evaluation_corpus_files(sha256);
CREATE INDEX idx_evaluation_corpus_status
  ON evaluation_corpus_files(extraction_status);
CREATE INDEX idx_evaluation_reports_sha256
  ON evaluation_reports(sha256);
CREATE INDEX idx_evaluation_matches_project_status
  ON evaluation_project_matches(project_no, review_status);
CREATE INDEX idx_evaluation_findings_match_category
  ON evaluation_findings(match_id, category, field_code);
CREATE INDEX idx_price_source_country_priority
  ON price_index_sources(country, priority);
CREATE INDEX idx_price_values_period ON price_index_values(period);
CREATE INDEX idx_normalization_bid_target
  ON normalization_runs(bid_no, target_period);
CREATE VIEW v_sample_coverage AS
SELECT
  country,
  facility_type,
  work_type,
  COUNT(*) AS reviewed_case_count,
  SUM(CASE WHEN evidence_grade = 'A' THEN 1 ELSE 0 END) AS grade_a_count,
  MIN(notice_date) AS earliest_notice_date,
  MAX(notice_date) AS latest_notice_date,
  MIN(unit_usd_m2_nominal) AS nominal_unit_min,
  MAX(unit_usd_m2_nominal) AS nominal_unit_max,
  '권고단가 아님: 가격·범위 보정 후 현지견적과 교차검증' AS use_warning
FROM reviewed_cases
GROUP BY country, facility_type, work_type;

CREATE VIEW v_yearly_inventory AS
SELECT
  substr(notice_date, 1, 4) AS notice_year,
  COUNT(*) AS reviewed_case_count,
  SUM(CASE WHEN evidence_grade = 'A' THEN 1 ELSE 0 END) AS grade_a_count,
  SUM(CASE WHEN normalization_status = '미보정' THEN 1 ELSE 0 END) AS unnormalized_count
FROM reviewed_cases
GROUP BY substr(notice_date, 1, 4);

CREATE VIEW v_area_cost_ready_projects AS
SELECT
  project_no,
  country_ko,
  project_name,
  best_grade,
  verification_level,
  scope_status,
  representative_area_m2,
  representative_construction_cost_usd,
  representative_amount_stage,
  screening_unit_usd_m2,
  unit_cost_allowed_use,
  display_representative_bid,
  direct_future_estimate_ready,
  screening_sample_weight,
  'A/B는 BOQ 준비도, C는 초기 스크리닝; 현지단가·물가·환율·범위 보정 필요' AS use_warning
FROM area_cost_project_review
WHERE compact_grade IN ('A','B','C');

CREATE VIEW v_area_cost_followup_queue AS
SELECT
  project_no,
  country_ko,
  project_name,
  best_grade,
  verification_level,
  scope_status,
  display_representative_bid,
  duplicate_and_scope_warning,
  grade_detail
FROM area_cost_project_review
WHERE compact_grade IN ('C?','U');

CREATE VIEW v_project_evaluation_findings AS
SELECT
  m.project_no,
  m.db_country AS country_ko,
  m.db_project_name AS project_name,
  s.in_area_cost_review,
  s.has_works_contract,
  s.has_construction_candidate,
  s.manual_construction_relevance,
  r.report_id,
  r.source_kind,
  r.source_collection,
  r.source_file,
  r.source_page_url,
  r.source_download_url,
  r.sha256 AS report_sha256,
  r.report_title,
  r.publication_date,
  r.extraction_method,
  r.extraction_status,
  r.ocr_text_digest,
  m.match_method,
  m.relation_scope,
  m.match_score,
  m.match_basis,
  m.reviewed_at,
  f.finding_id,
  f.category,
  f.field_code,
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
  f.review_note,
  f.confidence,
  f.public_excerpt_approved
FROM evaluation_project_matches m
JOIN evaluation_project_screening s ON s.project_no = m.project_no
JOIN evaluation_reports r ON r.report_id = m.report_id
JOIN evaluation_findings f ON f.match_id = m.match_id
WHERE m.review_status = 'accepted' AND f.review_status = 'accepted';

CREATE VIEW v_duplicate_attachments AS
SELECT sha256, COUNT(*) AS copies, SUM(bytes) AS total_bytes
FROM attachments
WHERE sha256 IS NOT NULL AND sha256 <> ''
GROUP BY sha256
HAVING COUNT(*) > 1;

CREATE VIEW v_price_index_coverage AS
SELECT
  s.country,
  s.iso3,
  s.priority,
  s.index_class,
  s.series_name,
  s.provider,
  s.frequency,
  COUNT(v.period) AS actual_observation_count,
  MIN(v.period) AS earliest_period,
  MAX(v.period) AS latest_period,
  (
    SELECT v2.observation_status
    FROM price_index_values v2
    WHERE v2.source_id = s.source_id AND v2.is_actual = 1
    ORDER BY v2.period DESC
    LIMIT 1
  ) AS latest_observation_status,
  MAX(v.retrieved_at) AS latest_retrieved_at,
  s.provider_url
FROM price_index_sources s
LEFT JOIN price_index_values v
  ON v.source_id = s.source_id AND v.is_actual = 1
WHERE s.priority IS NOT NULL
GROUP BY
  s.source_id, s.country, s.iso3, s.priority, s.index_class,
  s.series_name, s.provider, s.frequency, s.provider_url;

CREATE VIEW v_best_available_price_index AS
SELECT c.*
FROM v_price_index_coverage c
WHERE c.actual_observation_count >= 2
  AND c.priority = (
    SELECT MIN(c2.priority)
    FROM v_price_index_coverage c2
    WHERE c2.country = c.country
      AND c2.actual_observation_count >= 2
  );

"""


def insert_dataset(connection: sqlite3.Connection, spec: dict) -> None:
    root: Path = spec["root"]
    manifests = root / "manifests"
    bids = load(manifests / "bids.json")
    known_bid_numbers = {row["bid_no"] for row in bids}
    details = load(manifests / "details.json")
    projects = load(manifests / "projects.json")
    attachments = load(manifests / "attachments.json")
    documents = load(manifests / "file_index.json")
    evidence = load(manifests / "construction_evidence.json")
    attachment_count = sum(len(item.get("files", [])) for item in attachments.values())

    connection.execute(
        "INSERT INTO datasets VALUES (?,?,?,?,?,?,?,?)",
        (
            spec["id"], spec["start_date"], spec["end_date"], len(bids),
            len(details), attachment_count, len(documents), len(evidence),
        ),
    )
    connection.executemany(
        """INSERT INTO bids VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        [
            (
                row["bid_no"], spec["id"], row.get("bid_base_no", ""),
                str(row.get("order", "")), row.get("number"), row.get("title", ""),
                row.get("contract_type", ""), row.get("contract_method", ""),
                row.get("notice_date", ""), row.get("manager", ""),
                int(bool(row.get("construction_candidate"))),
            )
            for row in bids
        ],
    )
    connection.executemany(
        """INSERT INTO details VALUES (?,?,?,?,?,?)""",
        [
            (
                bid_no, spec["id"], row.get("attachment_group_no", ""),
                row.get("detail_url", ""), row.get("collected_at", ""),
                json.dumps(row.get("fields", {}), ensure_ascii=False),
            )
            for bid_no, row in details.items()
        ],
    )
    connection.executemany(
        """INSERT INTO projects VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        [
            (
                row["bid_no"], spec["id"], row.get("project_no", ""),
                row.get("country_ko", ""), row.get("country_en", ""),
                row.get("region", ""), row.get("project_name", ""),
                row.get("bid_title_ko", ""), row.get("bid_title_en", ""),
                row.get("facility_type", ""), row.get("work_type", ""),
                row.get("contract_type", ""), row.get("contract_method", ""),
                row.get("selection_method", ""), row.get("ceiling_usd_raw", ""),
                row.get("ceiling_krw_raw", ""), row.get("notice_date", ""),
                row.get("detail_url", ""),
            )
            for row in projects
        ],
    )
    attachment_rows = []
    for bid_no, bid in attachments.items():
        for item in bid.get("files", []):
            attachment_rows.append(
                (
                    spec["id"], bid_no, str(item.get("ATCHMNFL_SN", "")),
                    str(item.get("ATCHMNFL_GROUP_NO", "")),
                    item.get("ATCHMNFL_NM", ""), item.get("STRE_FILE_NM", ""),
                    item.get("ATCHMNFL_EXTSN_NM", ""), int(item.get("FILE_CPCTY") or 0),
                    str(item.get("REGIST_DT", "")), portable_path(item.get("local_path", "")),
                    item.get("sha256", ""), item.get("status", ""),
                )
            )
    connection.executemany(
        """INSERT INTO attachments VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        attachment_rows,
    )
    connection.executemany(
        """INSERT INTO documents VALUES (?,?,?,?,?,?,?)""",
        [
            (
                spec["id"], row["bid_no"], row.get("source_file", ""),
                row.get("extension", ""), int(row.get("bytes") or 0),
                int(row.get("text_chunks") or 0), int(row.get("evidence_count") or 0),
            )
            for row in documents
            if row.get("bid_no") in known_bid_numbers
        ],
    )
    connection.executemany(
        """INSERT INTO evidence
        (dataset_id,bid_no,category,matched_keywords,area_mentions,currency_mentions,
         percentage_mentions,source_file,source_locator,evidence_text,review_status)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        [
            (
                spec["id"], row["bid_no"], row.get("category", ""),
                row.get("matched_keywords", ""), row.get("area_mentions", ""),
                row.get("currency_mentions", ""), row.get("percentage_mentions", ""),
                row.get("source_file", ""), row.get("source_locator", ""),
                row.get("evidence_text", ""), row.get("review_status", ""),
            )
            for row in evidence
            if row.get("bid_no") in known_bid_numbers
        ],
    )


def insert_area_cost_review(connection: sqlite3.Connection) -> None:
    review_root = ROOT / "outputs" / "koica-area-cost-review"
    notice_rows = load_csv(review_root / "KOICA_면적금액_170공고_재검토.csv")
    group_rows = load_csv(review_root / "KOICA_면적금액_154공고군_재검토.csv")
    project_rows = load_csv(review_root / "KOICA_면적금액_91사업_재검토.csv")
    summary = load(review_root / "KOICA_면적금액_170공고_91사업_재검토_요약.json")
    if (len(notice_rows), len(group_rows), len(project_rows)) != (170, 154, 91):
        raise RuntimeError(
            "area-cost review universe must be 170 notices / 154 bid groups / 91 projects"
        )

    notice_fields = [
        "bid_no", "project_no", "bid_base_no", "package_id", "notice_date",
        "country_ko", "title", "scope_role", "record_cost_semantics",
        "record_scope_status", "same_scope_status", "notice_ceiling_usd",
        "selected_construction_cost_usd", "amount_stage", "selected_area_m2",
        "area_semantics", "area_aggregation", "screening_unit_usd_m2",
        "notice_ceiling_to_selected_gap_pct", "final_grade", "compact_grade",
        "verification_level", "unit_cost_allowed_use",
        "direct_future_estimate_ready", "sample_weight_notice",
        "is_bid_base_representative", "is_project_display_representative",
        "legacy_reviewed_case", "strict_attachment_review",
        "indexed_attachment_count", "spreadsheet_count", "boq_named_file_count",
        "quantity_table_file_count", "priced_table_file_count", "grade_detail",
        "manual_note", "amount_source_file", "amount_source_locator",
        "area_source_file", "area_source_locator", "area_quote", "source_url",
        "grade_system_version", "audit_date",
    ]
    notice_float_fields = {
        "notice_ceiling_usd", "selected_construction_cost_usd",
        "selected_area_m2", "screening_unit_usd_m2",
        "notice_ceiling_to_selected_gap_pct",
    }
    notice_int_fields = {
        "direct_future_estimate_ready", "sample_weight_notice",
        "is_bid_base_representative", "is_project_display_representative",
        "legacy_reviewed_case", "strict_attachment_review",
        "indexed_attachment_count", "spreadsheet_count", "boq_named_file_count",
        "quantity_table_file_count", "priced_table_file_count",
    }
    connection.executemany(
        f"INSERT INTO area_cost_notice_review ({','.join(notice_fields)}) "
        f"VALUES ({','.join('?' for _ in notice_fields)})",
        [
            tuple(
                nullable_float(row[field]) if field in notice_float_fields
                else nullable_int(row[field]) if field in notice_int_fields
                else row[field]
                for field in notice_fields
            )
            for row in notice_rows
        ],
    )

    group_fields = [
        "bid_base_no", "project_no", "country_ko", "notice_count", "bid_nos",
        "representative_bid_no", "latest_notice_date", "representative_title",
        "best_grade", "scope_role", "same_scope_status", "area_m2",
        "construction_cost_usd", "screening_unit_usd_m2", "duplicate_rule",
    ]
    group_float_fields = {
        "area_m2", "construction_cost_usd", "screening_unit_usd_m2",
    }
    connection.executemany(
        f"INSERT INTO area_cost_bid_group_review ({','.join(group_fields)}) "
        f"VALUES ({','.join('?' for _ in group_fields)})",
        [
            tuple(
                nullable_float(row[field]) if field in group_float_fields
                else nullable_int(row[field]) if field == "notice_count"
                else row[field]
                for field in group_fields
            )
            for row in group_rows
        ],
    )

    project_fields = [
        "project_no", "country_ko", "project_name", "notice_count",
        "bid_base_group_count", "valid_area_cost_notice_count", "valid_bid_nos",
        "all_bid_nos", "display_representative_bid", "technical_evidence_bid",
        "price_evidence_bid", "best_grade", "compact_grade", "verification_level",
        "scope_status", "representative_area_m2",
        "representative_construction_cost_usd", "representative_amount_stage",
        "screening_unit_usd_m2", "unit_cost_allowed_use",
        "direct_future_estimate_ready", "screening_sample_weight",
        "direct_estimate_sample_weight", "related_other_package_grade",
        "related_other_package_bid", "related_other_package_note",
        "duplicate_and_scope_warning", "grade_detail", "source_url",
        "grade_system_version", "audit_date",
    ]
    project_float_fields = {
        "representative_area_m2", "representative_construction_cost_usd",
        "screening_unit_usd_m2",
    }
    project_int_fields = {
        "notice_count", "bid_base_group_count", "valid_area_cost_notice_count",
        "direct_future_estimate_ready", "screening_sample_weight",
        "direct_estimate_sample_weight",
    }
    connection.executemany(
        f"INSERT INTO area_cost_project_review ({','.join(project_fields)}) "
        f"VALUES ({','.join('?' for _ in project_fields)})",
        [
            tuple(
                nullable_float(row[field]) if field in project_float_fields
                else nullable_int(row[field]) if field in project_int_fields
                else row[field]
                for field in project_fields
            )
            for row in project_rows
        ],
    )

    universe = summary["universe"]
    connection.execute(
        """INSERT INTO area_cost_review_summary
        (audit_date,schema_version,grade_system_version,notice_rows,
         bid_base_groups,project_rows,summary_json)
        VALUES (?,?,?,?,?,?,?)""",
        (
            summary["audit_date"], summary["schema_version"],
            summary["grade_system_version"], universe["notice_rows"],
            universe["bid_base_groups"], universe["project_rows"],
            json.dumps(summary, ensure_ascii=False, sort_keys=True),
        ),
    )


EVALUATION_MANIFEST_PATH = (
    ROOT / "data" / "manifests" / "koica_endline_evaluation_reports.json"
)
EVALUATION_CURATION_PATH = (
    ROOT / "data" / "manifests" / "koica_endline_evaluation_curation.json"
)


def evaluation_corpus_digest(rows: list[dict]) -> str:
    digest = hashlib.sha256()
    for row in sorted(
        rows, key=lambda item: unicodedata.normalize("NFC", item["source_file"])
    ):
        digest.update(
            unicodedata.normalize("NFC", row["source_file"]).encode("utf-8")
        )
        digest.update(b"\0")
        digest.update(row["sha256"].encode("ascii"))
        digest.update(b"\0")
        digest.update(str(row["file_bytes"]).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def load_evaluation_manifest(
    manifest_path: Path = EVALUATION_MANIFEST_PATH,
    curation_path: Path = EVALUATION_CURATION_PATH,
) -> dict:
    """Load and structurally validate the portable evaluation manifest.

    This runs before a temporary database is created so a missing or tampered
    manifest can never replace the last known-good SQLite distribution.
    """
    manifest = load(manifest_path)
    if manifest.get("schema_version") != "1.2":
        raise RuntimeError("evaluation manifest schema_version must be 1.2")
    target = manifest.get("target_universe") or {}
    if target.get("table") != "projects":
        raise RuntimeError("evaluation target table must be projects")
    if target.get("selector") != "distinct_nonempty_project_no":
        raise RuntimeError("evaluation target selector is invalid")
    if target.get("expected_count") != 175 or target.get("actual_count") != 175:
        raise RuntimeError("evaluation target universe must contain 175 projects")
    expected_profile = {
        "in_area_cost_review_count": 91,
        "has_works_contract_count": 109,
        "has_construction_candidate_count": 149,
    }
    if any(target.get(key) != value for key, value in expected_profile.items()):
        raise RuntimeError("evaluation target-universe profile changed")

    collection = manifest.get("corpus") or {}
    inventory = collection.get("inventory") or []
    reports = manifest.get("reports") or []
    matches = manifest.get("matches") or []
    findings = manifest.get("findings") or []
    definitions = manifest.get("field_definitions") or []
    screening = manifest.get("project_screening") or []
    actual_counts = {
        "field_definitions": len(definitions),
        "reports": len(reports),
        "matches": len(matches),
        "findings": len(findings),
    }
    if manifest.get("counts") != actual_counts:
        raise RuntimeError(
            f"evaluation manifest count mismatch: {manifest.get('counts')} "
            f"!= {actual_counts}"
        )
    if collection.get("pdf_count") != len(inventory):
        raise RuntimeError("evaluation corpus inventory count mismatch")
    if collection.get("digest") != evaluation_corpus_digest(inventory):
        raise RuntimeError("evaluation corpus digest mismatch")
    if collection.get("raw_pdfs_included") is not False:
        raise RuntimeError("raw evaluation PDFs must not be embedded in the manifest")
    if collection.get("selected_report_count") != len(reports):
        raise RuntimeError("selected evaluation report count mismatch")
    local_reports = [
        row for row in reports if row.get("source_kind") == "local_corpus"
    ]
    official_reports = [
        row for row in reports
        if row.get("source_kind") == "koica_official_site"
    ]
    if len(local_reports) + len(official_reports) != len(reports):
        raise RuntimeError("unsupported evaluation report source_kind")
    if collection.get("selected_local_report_count") != len(local_reports):
        raise RuntimeError("selected local evaluation report count mismatch")
    if collection.get("selected_official_report_count") != len(official_reports):
        raise RuntimeError("selected official evaluation report count mismatch")
    official_source = manifest.get("official_source") or {}
    if official_source.get("selected_report_count") != len(official_reports):
        raise RuntimeError("official evaluation source count mismatch")
    if official_source.get("raw_pdfs_included") is not False:
        raise RuntimeError("official raw evaluation PDFs must not be embedded")
    official_index = validate_official_index_snapshot(
        official_source.get("index_snapshot") or {}
    )
    official_index_pairs = (
        ("list_url", "list_url"),
        ("screened_at", "screened_at"),
        ("screened_page_count", "page_count"),
        ("screened_post_count", "post_count"),
        ("screened_index_digest_algorithm", "digest_algorithm"),
        ("screened_index_digest", "digest"),
        ("screened_index_payload_bytes", "payload_bytes"),
    )
    for source_field, index_field in official_index_pairs:
        if official_source.get(source_field) != official_index.get(index_field):
            raise RuntimeError(
                "official evaluation index snapshot differs: " + source_field
            )
    indexed_post_ids = {row["post_id"] for row in official_index["posts"]}
    if any(str(row.get("source_post_id")) not in indexed_post_ids for row in official_reports):
        raise RuntimeError("official evaluation selection is absent from index snapshot")
    curation = load_evaluation_curation(curation_path)
    if curation.get("schema_version") != "1.2":
        raise RuntimeError("evaluation curation schema_version must be 1.2")
    if manifest.get("curation_digest_algorithm") != (
        "sha256(canonical merged JSON)"
    ) or manifest.get("curation_digest") != canonical_json_digest(curation):
        raise RuntimeError("evaluation curation digest mismatch")
    curated_official = {
        row["report_id"]: row
        for row in curation.get("reports", [])
        if row.get("source_kind") == "koica_official_site"
    }
    manifested_official = {row["report_id"]: row for row in official_reports}
    if set(curated_official) != set(manifested_official):
        raise RuntimeError("official evaluation selection differs from curation")
    curation_official_source = curation.get("official_source") or {}
    for field in (
        "logical_name", "list_url", "index_snapshot_file", "index_snapshot",
        "screened_page_count",
        "screened_post_count", "screened_at",
        "screened_index_digest_algorithm", "screened_index_digest",
        "screened_index_payload_bytes", "screening_note",
    ):
        if official_source.get(field) != curation_official_source.get(field):
            raise RuntimeError(
                f"official evaluation source metadata differs: {field}"
            )
    official_field_pairs = {
        "source_file": "source_file",
        "source_post_id": "source_post_id",
        "source_attachment_id": "source_attachment_id",
        "source_page_url": "source_page_url",
        "source_download_url": "source_download_url",
        "sha256": "expected_sha256",
        "file_bytes": "expected_file_bytes",
        "page_count": "expected_page_count",
        "report_title": "report_title",
        "project_period": "project_period",
        "publication_date": "publication_date",
        "publication_date_precision": "publication_date_precision",
        "ocr_text_digest": "expected_ocr_text_digest",
        "ocr_text_page_count": "expected_ocr_text_page_count",
    }
    for report_id, report in manifested_official.items():
        curated = curated_official[report_id]
        for manifest_field, curation_field in official_field_pairs.items():
            if report.get(manifest_field) != curated.get(curation_field):
                raise RuntimeError(
                    "official evaluation report differs from curation: "
                    f"{report_id}.{manifest_field}"
                )
        if report.get("extraction_status") == "ocr_text":
            if report.get("extraction_method") != curated.get(
                "ocr_extraction_method"
            ):
                raise RuntimeError(
                    "official OCR method differs from curation: " + report_id
                )
            if report.get("ocr_text_digest_algorithm") != (
                "sha256(filename_nfc NUL sha256 NUL bytes LF)"
            ):
                raise RuntimeError(
                    "official OCR digest algorithm is invalid: " + report_id
                )
    if collection.get("accepted_match_count") != len(matches):
        raise RuntimeError("accepted evaluation match count mismatch")
    matched_projects = {row["project_no"] for row in matches}
    if collection.get("matched_project_count") != len(matched_projects):
        raise RuntimeError("matched evaluation project count mismatch")
    expected_project_count = target["expected_count"]
    if collection.get("no_accepted_match_project_count") != (
        expected_project_count - len(matched_projects)
    ):
        raise RuntimeError("unmatched evaluation project count mismatch")
    if len(screening) != expected_project_count:
        raise RuntimeError(
            "evaluation project screening must cover all target projects"
        )
    if collection.get("ocr_required_file_count") != sum(
        row.get("extraction_status") == "ocr_required" for row in inventory
    ):
        raise RuntimeError("evaluation OCR queue count mismatch")
    if collection.get("duplicate_physical_file_count") != sum(
        bool(row.get("duplicate_of_source_file")) for row in inventory
    ):
        raise RuntimeError("evaluation duplicate-file count mismatch")

    def unique(rows: list[dict], field: str) -> None:
        values = [row.get(field) for row in rows]
        if None in values or len(values) != len(set(values)):
            raise RuntimeError(f"evaluation manifest has invalid {field} values")

    for rows, field in (
        (inventory, "source_file"),
        (definitions, "field_code"),
        (reports, "report_id"),
        (reports, "source_file"),
        (matches, "match_id"),
        (findings, "finding_id"),
        (screening, "project_no"),
    ):
        unique(rows, field)
    inventory_by_file = {row["source_file"]: row for row in inventory}
    report_ids = {row["report_id"] for row in reports}
    match_ids = {row["match_id"] for row in matches}
    for match in matches:
        if match.get("report_id") not in report_ids:
            raise RuntimeError(f"evaluation match references unknown report: {match}")
    for finding in findings:
        if finding.get("match_id") not in match_ids:
            raise RuntimeError(f"evaluation finding references unknown match: {finding}")
    expected_screening: dict[str, list[str]] = {}
    for match in matches:
        expected_screening.setdefault(match["project_no"], []).append(
            match["report_id"]
        )
    for row in screening:
        expected_report_ids = sorted(expected_screening.get(row["project_no"], []))
        if expected_report_ids:
            expected_status = "accepted_match"
        elif str(row.get("note", "")).startswith(
            "종료평가 후보를 검토했으나 미채택:"
        ):
            expected_status = "candidate_reviewed_not_accepted"
        else:
            expected_status = "no_accepted_same_project_report"
        if sorted(row.get("report_ids", [])) != expected_report_ids:
            raise RuntimeError(
                f"evaluation screening report_ids mismatch: {row['project_no']}"
            )
        if row.get("status") != expected_status:
            raise RuntimeError(
                f"evaluation screening status mismatch: {row['project_no']}"
            )
        for flag in (
            "in_area_cost_review", "has_works_contract",
            "has_construction_candidate", "manual_construction_relevance",
        ):
            if row.get(flag) not in (0, 1):
                raise RuntimeError(
                    f"evaluation screening flag invalid: {row['project_no']}.{flag}"
                )
        if row["manual_construction_relevance"] != int(
            expected_status == "accepted_match"
        ):
            raise RuntimeError(
                "manual construction relevance differs from accepted match: "
                f"{row['project_no']}"
            )
    for flag, count_key in (
        ("in_area_cost_review", "in_area_cost_review_count"),
        ("has_works_contract", "has_works_contract_count"),
        ("has_construction_candidate", "has_construction_candidate_count"),
    ):
        if sum(row[flag] for row in screening) != target[count_key]:
            raise RuntimeError(f"evaluation screening profile mismatch: {flag}")
    corpus_fields = (
        "sha256", "file_bytes", "page_count", "text_char_count",
        "meaningful_text_char_count", "text_page_coverage", "extraction_status",
    )
    for report in reports:
        if report.get("source_kind") == "local_corpus":
            corpus_row = inventory_by_file.get(report["source_file"])
            if corpus_row is None:
                raise RuntimeError(
                    f"selected report absent from corpus: {report['report_id']}"
                )
            if any(
                report.get(field) != corpus_row.get(field)
                for field in corpus_fields
            ):
                raise RuntimeError(
                    f"selected report audit fields differ: {report['report_id']}"
                )
            if report.get("source_collection") != collection.get("logical_name"):
                raise RuntimeError(
                    f"selected report collection differs: {report['report_id']}"
                )
        else:
            post_id = str(report.get("source_post_id") or "")
            attachment_id = str(report.get("source_attachment_id") or "")
            if report.get("source_page_url") != (
                "https://www.koica.go.kr/sites/evaluation_kr/article/view/"
                + post_id
            ):
                raise RuntimeError(
                    f"invalid official evaluation page URL: {report['report_id']}"
                )
            if report.get("source_download_url") != (
                "https://www.koica.go.kr/sites/evaluation_kr/common/filedownload/"
                + attachment_id
            ):
                raise RuntimeError(
                    f"invalid official evaluation download URL: {report['report_id']}"
                )
            if report.get("source_document_id") != attachment_id:
                raise RuntimeError(
                    f"official source document id differs: {report['report_id']}"
                )
            if report.get("source_collection") != official_source.get("logical_name"):
                raise RuntimeError(
                    f"official report collection differs: {report['report_id']}"
                )
    payload = json.dumps(manifest, ensure_ascii=False, sort_keys=True)
    if '"source_file": "/' in payload or '"source_file":"/' in payload:
        raise RuntimeError("absolute evaluation source path in manifest")
    return manifest


def insert_evaluation_reports(
    connection: sqlite3.Connection, manifest: dict
) -> None:
    definition_fields = [
        "field_code", "category", "value_kind", "allowed_units_json",
        "description",
    ]
    definitions = []
    for row in manifest["field_definitions"]:
        definitions.append({
            **row,
            "allowed_units_json": json.dumps(
                row.get("units", []), ensure_ascii=False, sort_keys=True
            ),
        })
    connection.executemany(
        f"INSERT INTO evaluation_field_definitions "
        f"({','.join(definition_fields)}) "
        f"VALUES ({','.join('?' for _ in definition_fields)})",
        [tuple(row.get(field) for field in definition_fields) for row in definitions],
    )

    corpus_fields = [
        "source_file", "source_collection", "sha256", "file_bytes",
        "page_count", "text_char_count", "meaningful_text_char_count",
        "text_page_coverage", "extraction_status", "duplicate_of_source_file",
    ]
    corpus_rows = [
        {**row, "source_collection": manifest["corpus"]["logical_name"]}
        for row in manifest["corpus"]["inventory"]
    ]
    corpus_rows.sort(
        key=lambda row: (
            row.get("duplicate_of_source_file") is not None, row["source_file"]
        )
    )
    connection.executemany(
        f"INSERT INTO evaluation_corpus_files ({','.join(corpus_fields)}) "
        f"VALUES ({','.join('?' for _ in corpus_fields)})",
        [tuple(row.get(field) for field in corpus_fields) for row in corpus_rows],
    )

    report_fields = [
        "report_id", "source_kind", "source_collection", "source_document_id",
        "source_file", "source_page_url", "source_download_url",
        "source_post_id", "source_attachment_id",
        "sha256", "file_bytes", "page_count", "text_char_count",
        "meaningful_text_char_count", "text_page_coverage",
        "report_title", "report_type", "project_period", "publication_date",
        "publication_date_precision", "duplicate_of_report_id",
        "extraction_method", "extraction_status", "ocr_text_digest",
        "ocr_text_page_count", "ocr_text_digest_algorithm",
    ]
    reports = sorted(
        manifest["reports"],
        key=lambda row: (row.get("duplicate_of_report_id") is not None, row["report_id"]),
    )
    connection.executemany(
        f"INSERT INTO evaluation_reports ({','.join(report_fields)}) "
        f"VALUES ({','.join('?' for _ in report_fields)})",
        [tuple(row.get(field) for field in report_fields) for row in reports],
    )

    screening_fields = [
        "project_no", "country_ko", "project_name", "in_area_cost_review",
        "has_works_contract", "has_construction_candidate",
        "manual_construction_relevance", "status", "report_ids_json", "note",
    ]
    screening_rows = [
        {
            **row,
            "report_ids_json": json.dumps(
                row.get("report_ids", []), ensure_ascii=False, sort_keys=True
            ),
        }
        for row in manifest["project_screening"]
    ]
    connection.executemany(
        f"INSERT INTO evaluation_project_screening "
        f"({','.join(screening_fields)}) "
        f"VALUES ({','.join('?' for _ in screening_fields)})",
        [tuple(row.get(field) for field in screening_fields) for row in screening_rows],
    )

    match_fields = [
        "match_id", "report_id", "project_no", "db_country",
        "db_project_name", "report_project_name", "match_method",
        "relation_scope", "match_score", "match_basis", "review_status",
        "reviewed_at",
    ]
    connection.executemany(
        f"INSERT INTO evaluation_project_matches ({','.join(match_fields)}) "
        f"VALUES ({','.join('?' for _ in match_fields)})",
        [
            tuple(row.get(field) for field in match_fields)
            for row in manifest["matches"]
        ],
    )

    finding_fields = [
        "finding_id", "match_id", "category", "field_code", "summary_text",
        "value_text", "value_numeric", "unit", "value_context",
        "pdf_page_start", "pdf_page_end", "printed_page_label",
        "evidence_excerpt", "conflict_group", "review_note", "confidence",
        "review_status", "public_excerpt_approved",
    ]
    connection.executemany(
        f"INSERT INTO evaluation_findings ({','.join(finding_fields)}) "
        f"VALUES ({','.join('?' for _ in finding_fields)})",
        [
            tuple(row.get(field) for field in finding_fields)
            for row in manifest["findings"]
        ],
    )

    invalid_pages = connection.execute(
        """SELECT f.finding_id, f.pdf_page_start, f.pdf_page_end, r.page_count
           FROM evaluation_findings f
           JOIN evaluation_project_matches m ON m.match_id = f.match_id
           JOIN evaluation_reports r ON r.report_id = m.report_id
           WHERE f.pdf_page_start < 1
              OR f.pdf_page_end < f.pdf_page_start
              OR f.pdf_page_end > r.page_count"""
    ).fetchall()
    if invalid_pages:
        raise RuntimeError(f"evaluation finding page violations: {invalid_pages[:10]}")
    unmatched_findings = connection.execute(
        """SELECT m.match_id
           FROM evaluation_project_matches m
           LEFT JOIN evaluation_findings f ON f.match_id = m.match_id
           WHERE m.review_status = 'accepted'
           GROUP BY m.match_id
           HAVING COUNT(f.finding_id) = 0"""
    ).fetchall()
    if unmatched_findings:
        raise RuntimeError(
            f"accepted evaluation matches without findings: {unmatched_findings}"
        )

    identity_mismatch = connection.execute(
        """SELECT m.match_id
           FROM evaluation_project_matches m
           JOIN evaluation_project_screening s ON s.project_no = m.project_no
           WHERE m.db_country <> s.country_ko
              OR m.db_project_name <> s.project_name"""
    ).fetchall()
    if identity_mismatch:
        raise RuntimeError(
            "evaluation project identity differs from screening rows: "
            f"{identity_mismatch[:5]}"
        )


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    evaluation_manifest = load_evaluation_manifest()
    temporary_db = DB_PATH.with_suffix(DB_PATH.suffix + ".tmp")
    temporary_db.unlink(missing_ok=True)
    connection = sqlite3.connect(temporary_db)
    try:
        connection.executescript(SCHEMA)
        for spec in DATASETS:
            insert_dataset(connection, spec)
        insert_area_cost_review(connection)
        insert_evaluation_reports(connection, evaluation_manifest)
        reviewed = load(OUTPUT / "reviewed_cases_2016_2025.json")
        fields = list(reviewed[0])
        connection.executemany(
            f"INSERT INTO reviewed_cases ({','.join(fields)}) "
            f"VALUES ({','.join('?' for _ in fields)})",
            [tuple(row[field] for field in fields) for row in reviewed],
        )
        fees = load(ROOT / "data" / "manifests" / "curated_fee_benchmarks.json")
        fee_fields = [
            "bid_no", "country", "facility_type", "gross_floor_area_m2",
            "construction_cost_usd", "design_fee_usd", "supervision_fee_usd",
            "combined_fee_usd", "design_rate", "supervision_rate", "combined_rate",
            "tax_note", "source_file", "source_locator", "evidence_summary",
        ]
        connection.executemany(
            f"INSERT INTO fee_benchmarks ({','.join(fee_fields)}) "
            f"VALUES ({','.join('?' for _ in fee_fields)})",
            [tuple(row.get(field) for field in fee_fields) for row in fees],
        )
        policy = load(ROOT / "data" / "manifests" / "price_index_policy.json")
        connection.executemany(
            """INSERT INTO price_index_policy
            (priority,index_class,label,intended_use,requirements)
            VALUES (?,?,?,?,?)""",
            [
                (
                    tier["priority"], tier["index_class"], tier["label"],
                    tier["use"], tier["requirements"],
                )
                for tier in policy["tiers"]
            ],
        )
        index_documents = []
        for name in (
            "price_indices_national.json",
        ):
            path = ROOT / "data" / "manifests" / name
            if path.exists():
                index_documents.append(load(path))
        for index_document in index_documents:
            connection.executemany(
                """INSERT INTO price_index_sources
                (source_id,country,iso3,priority,index_class,series_name,provider,
                 provider_url,indicator_code,frequency,unit,construction_specific,
                 status,notes)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                [
                    (
                        row["source_id"], row["country"], row["iso3"],
                        row.get("priority"), row["index_class"], row["series_name"],
                        row["provider"], row["provider_url"],
                        row.get("indicator_code", ""), row["frequency"], row["unit"],
                        int(bool(row.get("construction_specific"))),
                        row["status"], row.get("notes", ""),
                    )
                    for row in index_document["sources"]
                ],
            )
            connection.executemany(
                """INSERT INTO price_index_values
                (source_id,period,native_period,value,is_actual,
                 observation_status,release_url,retrieved_at)
                VALUES (?,?,?,?,?,?,?,?)""",
                [
                    (
                        row["source_id"], row["period"],
                        row.get("native_period", row["period"]), row["value"],
                        int(bool(row["is_actual"])),
                        row.get(
                            "observation_status",
                            "published" if row["is_actual"] else "forecast",
                        ),
                        row.get("release_url", ""),
                        row["retrieved_at"],
                    )
                    for row in index_document["values"]
                ],
            )
        audit = load(
            ROOT / "data" / "manifests" / "national_index_source_audit.json"
        )
        connection.executemany(
            """INSERT INTO national_index_source_audit
            (country,iso3,candidate_priority,candidate_name,provider,source_url,
             status,fallback_loaded,audited_at)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            [
                (
                    row["country"], row["iso3"], row.get("candidate_priority"),
                    row.get("candidate_name", ""), row["provider"],
                    row["source_url"], row["status"],
                    0, audit["audited_at"],
                )
                for row in audit["countries"]
            ],
        )
        connection.executemany(
            "INSERT INTO metadata VALUES (?,?)",
            [
                ("schema_version", "1.9"),
                ("coverage", "2016-01-01/2025-12-31"),
                (
                    "data_scope",
                    "KOICA procurement, KOICA endline evaluations, and official national indices only",
                ),
                ("source_of_truth", "SQLite"),
                (
                    "price_treatment",
                    "명목 USD/㎡; 국가별 실제 지수 우선순위 1~5; "
                    "보정 실행 전 원금액의 통화구성 확인",
                ),
                (
                    "price_index_priority",
                    "국가 건설지수 > BOQ 구성요소 가중합 > 건설자재 PPI/WPI "
                    "> GDP 디플레이터 > CPI",
                ),
                ("recommended_unit_rate_count", "0"),
                ("area_cost_review_notice_count", "170"),
                ("area_cost_review_project_count", "91"),
                (
                    "area_cost_review_boundary",
                    "170공고/154공고군/91사업; A/B는 BOQ 준비도, C는 스크리닝, C?는 원본확인 대기",
                ),
                (
                    "evaluation_target_universe",
                    json.dumps(
                        evaluation_manifest["target_universe"],
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                ),
                (
                    "evaluation_target_project_count",
                    str(evaluation_manifest["target_universe"]["actual_count"]),
                ),
                (
                    "evaluation_target_area_cost_review_count",
                    str(
                        evaluation_manifest["target_universe"][
                            "in_area_cost_review_count"
                        ]
                    ),
                ),
                (
                    "evaluation_target_works_contract_count",
                    str(
                        evaluation_manifest["target_universe"][
                            "has_works_contract_count"
                        ]
                    ),
                ),
                (
                    "evaluation_target_construction_candidate_count",
                    str(
                        evaluation_manifest["target_universe"][
                            "has_construction_candidate_count"
                        ]
                    ),
                ),
                (
                    "evaluation_corpus_digest",
                    evaluation_manifest["corpus"]["digest"],
                ),
                (
                    "evaluation_corpus_pdf_count",
                    str(evaluation_manifest["corpus"]["pdf_count"]),
                ),
                (
                    "evaluation_report_count",
                    str(evaluation_manifest["counts"]["reports"]),
                ),
                (
                    "evaluation_local_report_count",
                    str(
                        evaluation_manifest["corpus"][
                            "selected_local_report_count"
                        ]
                    ),
                ),
                (
                    "evaluation_official_report_count",
                    str(
                        evaluation_manifest["corpus"][
                            "selected_official_report_count"
                        ]
                    ),
                ),
                (
                    "evaluation_official_screened_post_count",
                    str(
                        evaluation_manifest["official_source"][
                            "screened_post_count"
                        ]
                    ),
                ),
                (
                    "evaluation_official_index_digest",
                    evaluation_manifest["official_source"][
                        "screened_index_digest"
                    ],
                ),
                (
                    "evaluation_matched_project_count",
                    str(evaluation_manifest["corpus"]["matched_project_count"]),
                ),
                (
                    "evaluation_finding_count",
                    str(evaluation_manifest["counts"]["findings"]),
                ),
                (
                    "evaluation_manifest_sha256",
                    sha256(EVALUATION_MANIFEST_PATH),
                ),
                (
                    "evaluation_review_json",
                    json.dumps(
                        evaluation_manifest["review"],
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                ),
                ("usage_warning", "현지 견적·BOQ·물가보정 없이 미래 사업 단가로 직접 사용 금지"),
            ],
        )
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(f"Foreign key violations: {violations[:10]}")
        connection.commit()
        connection.execute("VACUUM")
    except Exception:
        temporary_db.unlink(missing_ok=True)
        raise
    finally:
        connection.close()

    try:
        check = sqlite3.connect(f"file:{temporary_db}?mode=ro", uri=True)
        try:
            counts = {
                table: check.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in (
                    "bids", "details", "projects", "attachments", "documents",
                    "evidence", "reviewed_cases", "fee_benchmarks",
                    "area_cost_notice_review", "area_cost_bid_group_review",
                    "area_cost_project_review", "area_cost_review_summary",
                    "evaluation_field_definitions", "evaluation_corpus_files",
                    "evaluation_reports", "evaluation_project_matches",
                    "evaluation_project_screening", "evaluation_findings",
                    "price_index_policy", "price_index_sources",
                    "price_index_values", "national_index_source_audit",
                    "normalization_runs",
                )
            }
            integrity = check.execute("PRAGMA integrity_check").fetchone()[0]
            foreign_key_violations = check.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()
        finally:
            check.close()
    except Exception:
        temporary_db.unlink(missing_ok=True)
        raise
    if integrity != "ok" or foreign_key_violations:
        temporary_db.unlink(missing_ok=True)
        raise RuntimeError(
            f"temporary distribution validation failed: integrity={integrity}, "
            f"foreign_keys={foreign_key_violations[:10]}"
        )
    temporary_db.replace(DB_PATH)
    print(json.dumps({
        "database": str(DB_PATH),
        "bytes": DB_PATH.stat().st_size,
        "integrity_check": integrity,
        "counts": counts,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
