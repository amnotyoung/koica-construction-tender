#!/usr/bin/env python3
"""Create the normalized SQLite source of truth for KOICA construction research."""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path


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
        return value


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


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    DB_PATH.unlink(missing_ok=True)
    connection = sqlite3.connect(DB_PATH)
    try:
        connection.executescript(SCHEMA)
        for spec in DATASETS:
            insert_dataset(connection, spec)
        insert_area_cost_review(connection)
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
                ("schema_version", "1.6"),
                ("coverage", "2016-01-01/2025-12-31"),
                ("data_scope", "KOICA procurement and official national indices only"),
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
                ("usage_warning", "현지 견적·BOQ·물가보정 없이 미래 사업 단가로 직접 사용 금지"),
            ],
        )
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(f"Foreign key violations: {violations[:10]}")
        connection.commit()
        connection.execute("VACUUM")
    finally:
        connection.close()

    check = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        counts = {
            table: check.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "bids", "details", "projects", "attachments", "documents",
                "evidence", "reviewed_cases", "fee_benchmarks",
                "area_cost_notice_review", "area_cost_bid_group_review",
                "area_cost_project_review", "area_cost_review_summary",
                "price_index_policy", "price_index_sources",
                "price_index_values", "national_index_source_audit",
                "normalization_runs",
            )
        }
        integrity = check.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        check.close()
    print(json.dumps({
        "database": str(DB_PATH),
        "bytes": DB_PATH.stat().st_size,
        "integrity_check": integrity,
        "counts": counts,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
