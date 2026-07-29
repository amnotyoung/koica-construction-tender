#!/usr/bin/env python3
"""Create the normalized SQLite source of truth for KOICA construction research."""

from __future__ import annotations

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

CREATE INDEX idx_bids_notice_date ON bids(notice_date);
CREATE INDEX idx_bids_contract_type ON bids(contract_type);
CREATE INDEX idx_projects_country ON projects(country_en);
CREATE INDEX idx_projects_project_no ON projects(project_no);
CREATE INDEX idx_attachments_sha256 ON attachments(sha256);
CREATE INDEX idx_documents_bid ON documents(bid_no);
CREATE INDEX idx_evidence_bid_category ON evidence(bid_no, category);
CREATE INDEX idx_reviewed_country_type ON reviewed_cases(country, facility_type, work_type);
CREATE INDEX idx_reviewed_notice_date ON reviewed_cases(notice_date);

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

CREATE VIEW v_duplicate_attachments AS
SELECT sha256, COUNT(*) AS copies, SUM(bytes) AS total_bytes
FROM attachments
WHERE sha256 IS NOT NULL AND sha256 <> ''
GROUP BY sha256
HAVING COUNT(*) > 1;
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


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    DB_PATH.unlink(missing_ok=True)
    connection = sqlite3.connect(DB_PATH)
    try:
        connection.executescript(SCHEMA)
        for spec in DATASETS:
            insert_dataset(connection, spec)
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
        connection.executemany(
            "INSERT INTO metadata VALUES (?,?)",
            [
                ("schema_version", "1.0"),
                ("coverage", "2016-01-01/2025-12-31"),
                ("source_of_truth", "SQLite"),
                ("price_treatment", "공고일 연속값; 명목 USD/㎡; 물가 미보정"),
                ("recommended_unit_rate_count", "0"),
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
