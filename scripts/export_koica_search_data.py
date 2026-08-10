#!/usr/bin/env python3
"""Build the public KOICA construction search snapshot from the source SQLite DB.

The SQLite file remains the source of truth.  This script emits only the small,
review-oriented read model that can be synchronized to Supabase.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = (
    ROOT
    / "outputs"
    / "koica-construction-distribution"
    / "KOICA_건축사업_사례DB_2016-2025.sqlite"
)
DEFAULT_OUTPUT_DIR = ROOT / "outputs" / "koica-search"

CASE_FIELDS = [
    "case_id",
    "case_kind",
    "project_no",
    "representative_bid_no",
    "display_name",
    "official_project_name",
    "country_ko",
    "facility_type",
    "facility_family",
    "work_type",
    "notice_date",
    "gross_floor_area_m2",
    "construction_cost_usd",
    "amount_stage_code",
    "nominal_unit_usd_m2",
    "evidence_grade",
    "verification_level",
    "scope_note",
    "evidence_note",
    "allowed_use",
    "notice_count",
    "procurement_url",
    "search_text",
    "data_version",
    "audit_date",
    "is_published",
]

CONSTRUCTION_NOTICE = "CONSTRUCTION_NOTICE"
DESIGN_SUPERVISION_REFERENCE = "DESIGN_SUPERVISION_REFERENCE"
PUBLISHABLE_REFERENCE_GRADES = {"A", "B", "C"}
PUBLISHABLE_REFERENCE_AMOUNT_STAGES = {"DESIGN_ESTIMATE", "CONSTRUCTION_BUDGET"}

FACILITY_FAMILY_ALIASES = {
    "보건·의료시설": "병원 의료 보건 보건의료 의료인프라 모자보건 병동 진료",
    "교육·훈련시설": "학교 교육 훈련 대학 직업교육 TVET",
    "농업·생산시설": "농업 농촌 생산 가공 저장",
    "연구·실험시설": "연구 실험 실험실 연구소",
    "행정·공공시설": "정부 행정 공공 청사",
    "환경·기반시설": "상하수 환경 위생 기반시설",
    "기타·미분류": "",
}

RELATED_NOTICE_FIELDS = [
    "case_id",
    "related_bid_base_no",
    "representative_bid_no",
    "relation_type",
    "display_name",
    "contract_type",
    "amount_usd",
    "amount_stage_code",
    "notice_date",
    "procurement_url",
    "note",
    "is_published",
]

EVALUATION_PROJECT_FIELDS = [
    "project_no",
    "country_ko",
    "project_name",
    "in_area_cost_review",
    "has_works_contract",
    "has_construction_candidate",
    "manual_construction_relevance",
    "match_status",
    "screening_note",
    "data_version",
    "is_published",
]

EVALUATION_REPORT_FIELDS = [
    "report_id",
    "source_kind",
    "source_collection",
    "report_title",
    "report_type",
    "project_period",
    "publication_date",
    "publication_date_precision",
    "source_page_url",
    "source_download_url",
    "page_count",
    "extraction_status",
    "data_version",
    "is_published",
]

EVALUATION_MATCH_FIELDS = [
    "match_id",
    "report_id",
    "project_no",
    "report_project_name",
    "match_method",
    "relation_scope",
    "match_score",
    "match_basis",
    "reviewed_at",
    "data_version",
    "is_published",
]

EVALUATION_FINDING_FIELDS = [
    "finding_id",
    "match_id",
    "category",
    "field_code",
    "field_description",
    "summary_text",
    "value_text",
    "value_numeric",
    "unit",
    "value_context",
    "pdf_page_start",
    "pdf_page_end",
    "printed_page_label",
    "evidence_excerpt",
    "conflict_group",
    "confidence",
    "search_text",
    "data_version",
    "is_published",
]


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value).replace("\u00a0", " ")).strip()
    return text or None


def as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    number = float(value)
    return round(number, 2)


def parse_usd_ceiling(value: Any) -> float | None:
    """Parse one explicit USD amount; do not infer from KRW or exchange rates."""
    text = clean_text(value)
    if not text:
        return None
    match = re.search(
        r"(?:US\s*\$|USD|\$)\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?)",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    return round(float(match.group(1).replace(",", "")), 2)


def join_notes(*values: Any) -> str | None:
    notes: list[str] = []
    for value in values:
        text = clean_text(value)
        if text and text not in notes:
            notes.append(text)
    return " | ".join(notes) if notes else None


def facility_family(*values: Any) -> str:
    text = " ".join(filter(None, (clean_text(value) for value in values))).lower()
    if re.search(
        r"병원|의료|보건|의과|간호|진료|병동|hospital|medical|health|clinic|matern",
        text,
    ):
        return "보건·의료시설"
    if re.search(
        r"학교|교육|훈련|대학|직업|tvet|school|education|training|university|college",
        text,
    ):
        return "교육·훈련시설"
    if re.search(r"농업|농촌|영농|축산|수산|가공|저장|agri|farm", text):
        return "농업·생산시설"
    if re.search(r"연구|실험|laborator|research", text):
        return "연구·실험시설"
    if re.search(r"정부|행정|공공|청사|government|administr", text):
        return "행정·공공시설"
    if re.search(r"상하수|환경|위생|폐기물|water|sanitation|environment", text):
        return "환경·기반시설"
    return "기타·미분류"


def compact_grade(value: Any) -> str | None:
    grade = clean_text(value)
    if not grade:
        return None
    if grade in {"A", "B", "C", "C?", "U", "X"}:
        return grade
    if grade.startswith("A"):
        return "A"
    if grade.startswith("B"):
        return "B"
    if grade.startswith("C?"):
        return "C?"
    if grade.startswith("C"):
        return "C"
    if grade.startswith("U"):
        return "U"
    if grade.startswith("X"):
        return "X"
    return None


def relation_type(title: Any, contract_type: Any) -> str:
    normalized = (clean_text(title) or "").lower()
    if "감리" in normalized or "supervision" in normalized:
        return "SUPERVISION"
    if "사업관리" in normalized or re.search(r"\bpmc?\b", normalized):
        return "PROJECT_MANAGEMENT"
    if "설계" in normalized or "design" in normalized:
        return "DESIGN"
    contract = clean_text(contract_type) or ""
    if contract == "공사":
        return "CONSTRUCTION_PACKAGE"
    if contract == "물품":
        return "GOODS"
    if contract == "용역":
        return "SERVICE"
    return "RELATED_PROCUREMENT"


def row_dicts(connection: sqlite3.Connection, query: str) -> list[dict[str, Any]]:
    return [dict(row) for row in connection.execute(query)]


def latest_row(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    return max(
        rows,
        key=lambda row: (
            clean_text(row.get("notice_date")) or "",
            clean_text(row.get("bid_no")) or "",
        ),
    )


def source_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_snapshot(database: Path) -> dict[str, Any]:
    uri = f"{database.resolve().as_uri()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        metadata = {
            row["key"]: row["value"]
            for row in connection.execute("SELECT key, value FROM metadata")
        }
        project_rows = row_dicts(
            connection,
            """
            SELECT
              p.*,
              b.bid_base_no,
              b.order_no,
              b.title AS source_bid_title,
              b.contract_type AS source_contract_type
            FROM projects AS p
            JOIN bids AS b USING (bid_no)
            WHERE NULLIF(b.bid_base_no, '') IS NOT NULL
            """,
        )
        notice_reviews = {
            row["bid_no"]: row
            for row in row_dicts(connection, "SELECT * FROM area_cost_notice_review")
        }
        group_reviews = {
            row["bid_base_no"]: row
            for row in row_dicts(connection, "SELECT * FROM area_cost_bid_group_review")
        }
        project_reviews = {
            row["project_no"]: row
            for row in row_dicts(connection, "SELECT * FROM area_cost_project_review")
        }
        evaluation_project_rows = row_dicts(
            connection,
            """
            SELECT
              project_no,
              country_ko,
              project_name,
              in_area_cost_review,
              has_works_contract,
              has_construction_candidate,
              manual_construction_relevance,
              status AS match_status,
              note AS screening_note
            FROM evaluation_project_screening
            ORDER BY project_no
            """,
        )
        evaluation_report_rows = row_dicts(
            connection,
            """
            SELECT
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
              extraction_status
            FROM evaluation_reports
            ORDER BY report_id
            """,
        )
        evaluation_match_rows = row_dicts(
            connection,
            """
            SELECT
              match_id,
              report_id,
              project_no,
              report_project_name,
              match_method,
              relation_scope,
              match_score,
              match_basis,
              reviewed_at
            FROM evaluation_project_matches
            WHERE review_status = 'accepted'
            ORDER BY match_id
            """,
        )
        evaluation_finding_rows = row_dicts(
            connection,
            """
            SELECT
              f.finding_id,
              f.match_id,
              f.category,
              f.field_code,
              d.description AS field_description,
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
              s.country_ko,
              s.project_name,
              r.report_title
            FROM evaluation_findings AS f
            JOIN evaluation_project_matches AS m USING (match_id)
            JOIN evaluation_project_screening AS s USING (project_no)
            JOIN evaluation_reports AS r USING (report_id)
            JOIN evaluation_field_definitions AS d
              USING (field_code, category)
            WHERE
              f.review_status = 'accepted'
              AND f.public_excerpt_approved = 1
              AND m.review_status = 'accepted'
            ORDER BY f.finding_id
            """,
        )

    by_bid = {row["bid_no"]: row for row in project_rows}
    by_base: dict[str, list[dict[str, Any]]] = {}
    by_project: dict[str, list[dict[str, Any]]] = {}
    for row in project_rows:
        by_base.setdefault(row["bid_base_no"], []).append(row)
        project_no = clean_text(row.get("project_no"))
        if project_no:
            by_project.setdefault(project_no, []).append(row)

    construction_groups = {
        base_no: rows
        for base_no, rows in by_base.items()
        if any(
            (clean_text(row.get("contract_type")) or clean_text(row.get("source_contract_type")))
            == "공사"
            for row in rows
        )
    }
    construction_project_nos = {
        project_no
        for rows in construction_groups.values()
        for row in rows
        if (project_no := clean_text(row.get("project_no")))
    }
    published_groups = dict(construction_groups)
    case_kinds = {base_no: CONSTRUCTION_NOTICE for base_no in construction_groups}
    for project_no, project_review in project_reviews.items():
        if project_no in construction_project_nos:
            continue
        if clean_text(project_review.get("compact_grade")) not in PUBLISHABLE_REFERENCE_GRADES:
            continue
        if (
            clean_text(project_review.get("representative_amount_stage"))
            not in PUBLISHABLE_REFERENCE_AMOUNT_STAGES
        ):
            continue
        if not project_review.get("representative_area_m2") or not project_review.get(
            "representative_construction_cost_usd"
        ):
            continue
        representative_bid_no = clean_text(project_review.get("display_representative_bid"))
        representative = by_bid.get(representative_bid_no or "")
        if not representative:
            continue
        representative_relation = relation_type(
            representative.get("bid_title_ko") or representative.get("source_bid_title"),
            representative.get("contract_type") or representative.get("source_contract_type"),
        )
        if representative_relation not in {"DESIGN", "SUPERVISION"}:
            continue
        case_id = clean_text(representative.get("bid_base_no"))
        if not case_id or case_id not in by_base:
            continue
        published_groups[case_id] = by_base[case_id]
        case_kinds[case_id] = DESIGN_SUPERVISION_REFERENCE
    global_audit_date = max(
        (
            clean_text(row.get("audit_date")) or ""
            for row in notice_reviews.values()
        ),
        default="",
    ) or None
    schema_version = metadata.get("schema_version", "unknown")
    data_version = f"sqlite-{schema_version}-area-review-{global_audit_date or 'unreviewed'}"

    cases: list[dict[str, Any]] = []
    for case_id in sorted(published_groups):
        raw_latest = latest_row(published_groups[case_id])
        group_review = group_reviews.get(case_id, {})
        representative_bid_no = (
            clean_text(group_review.get("representative_bid_no")) or raw_latest["bid_no"]
        )
        representative = by_bid.get(representative_bid_no, raw_latest)
        notice_review = notice_reviews.get(representative_bid_no, {})
        project_no = (
            clean_text(notice_review.get("project_no"))
            or clean_text(group_review.get("project_no"))
            or clean_text(representative.get("project_no"))
        )
        project_review = project_reviews.get(project_no or "", {})

        display_name = (
            clean_text(notice_review.get("title"))
            or clean_text(group_review.get("representative_title"))
            or clean_text(representative.get("bid_title_ko"))
            or clean_text(representative.get("source_bid_title"))
            or clean_text(representative.get("project_name"))
            or case_id
        )
        official_project_name = (
            clean_text(project_review.get("project_name"))
            or clean_text(representative.get("project_name"))
        )
        country_ko = (
            clean_text(notice_review.get("country_ko"))
            or clean_text(group_review.get("country_ko"))
            or clean_text(project_review.get("country_ko"))
            or clean_text(representative.get("country_ko"))
        )
        area = as_float(
            notice_review.get("selected_area_m2")
            if notice_review.get("selected_area_m2") is not None
            else (
                group_review.get("area_m2")
                if group_review.get("area_m2") is not None
                else project_review.get("representative_area_m2")
            )
        )
        cost = as_float(
            notice_review.get("selected_construction_cost_usd")
            if notice_review.get("selected_construction_cost_usd") is not None
            else (
                group_review.get("construction_cost_usd")
                if group_review.get("construction_cost_usd") is not None
                else project_review.get("representative_construction_cost_usd")
            )
        )
        amount_stage = clean_text(
            notice_review.get("amount_stage")
            or project_review.get("representative_amount_stage")
        )
        if cost is None:
            cost = parse_usd_ceiling(representative.get("ceiling_usd_raw"))
            if cost is not None:
                amount_stage = "NOTICE_EXECUTION_CEILING_RAW"
        unit_cost = round(cost / area, 2) if cost and area else None
        evidence_grade = compact_grade(
            notice_review.get("compact_grade")
            or group_review.get("best_grade")
            or project_review.get("compact_grade")
        )
        audit_date = clean_text(notice_review.get("audit_date")) or global_audit_date

        scope_note = join_notes(
            notice_review.get("scope_role"),
            notice_review.get("record_scope_status"),
            notice_review.get("same_scope_status"),
            group_review.get("duplicate_rule"),
            project_review.get("duplicate_and_scope_warning"),
        )
        evidence_note = join_notes(
            notice_review.get("grade_detail"),
            notice_review.get("manual_note"),
            notice_review.get("area_quote"),
            project_review.get("grade_detail"),
        )
        facility_type = clean_text(representative.get("facility_type"))
        work_type = clean_text(representative.get("work_type"))
        normalized_facility_family = facility_family(
            facility_type,
            display_name,
            official_project_name,
        )
        procurement_url = (
            clean_text(notice_review.get("source_url"))
            or clean_text(representative.get("detail_url"))
        )
        search_text = " ".join(
            value
            for value in [
                display_name,
                official_project_name,
                country_ko,
                facility_type,
                normalized_facility_family,
                FACILITY_FAMILY_ALIASES[normalized_facility_family],
                work_type,
                scope_note,
                evidence_note,
                project_no,
                case_id,
            ]
            if value
        )
        cases.append(
            {
                "case_id": case_id,
                "case_kind": case_kinds[case_id],
                "project_no": project_no,
                "representative_bid_no": representative_bid_no,
                "display_name": display_name,
                "official_project_name": official_project_name,
                "country_ko": country_ko,
                "facility_type": facility_type,
                "facility_family": normalized_facility_family,
                "work_type": work_type,
                "notice_date": (
                    clean_text(notice_review.get("notice_date"))
                    or clean_text(group_review.get("latest_notice_date"))
                    or clean_text(representative.get("notice_date"))
                ),
                "gross_floor_area_m2": area,
                "construction_cost_usd": cost,
                "amount_stage_code": amount_stage,
                "nominal_unit_usd_m2": unit_cost,
                "evidence_grade": evidence_grade,
                "verification_level": clean_text(
                    notice_review.get("verification_level")
                    or project_review.get("verification_level")
                ),
                "scope_note": scope_note,
                "evidence_note": evidence_note,
                "allowed_use": clean_text(
                    notice_review.get("unit_cost_allowed_use")
                    or project_review.get("unit_cost_allowed_use")
                ),
                "notice_count": int(
                    group_review.get("notice_count") or len(published_groups[case_id])
                ),
                "procurement_url": procurement_url,
                "search_text": search_text,
                "data_version": data_version,
                "audit_date": audit_date,
                "is_published": True,
            }
        )

    related_notices: list[dict[str, Any]] = []
    for case in cases:
        project_no = case["project_no"]
        if not project_no:
            continue
        related_by_base: dict[str, list[dict[str, Any]]] = {}
        for row in by_project.get(project_no, []):
            if row["bid_base_no"] != case["case_id"]:
                related_by_base.setdefault(row["bid_base_no"], []).append(row)
        for related_base_no in sorted(related_by_base):
            representative = latest_row(related_by_base[related_base_no])
            title = (
                clean_text(representative.get("bid_title_ko"))
                or clean_text(representative.get("source_bid_title"))
                or clean_text(representative.get("project_name"))
                or related_base_no
            )
            contract_type = (
                clean_text(representative.get("contract_type"))
                or clean_text(representative.get("source_contract_type"))
            )
            amount = parse_usd_ceiling(representative.get("ceiling_usd_raw"))
            related_notices.append(
                {
                    "case_id": case["case_id"],
                    "related_bid_base_no": related_base_no,
                    "representative_bid_no": representative["bid_no"],
                    "relation_type": relation_type(title, contract_type),
                    "display_name": title,
                    "contract_type": contract_type,
                    "amount_usd": amount,
                    "amount_stage_code": "NOTICE_EXECUTION_CEILING_RAW" if amount else None,
                    "notice_date": clean_text(representative.get("notice_date")),
                    "procurement_url": clean_text(representative.get("detail_url")),
                    "note": "동일 KOICA 사업번호의 관련 공고이며 재공고는 공고군 단위로 통합",
                    "is_published": True,
                }
            )

    evaluation_projects = [
        {
            **row,
            "in_area_cost_review": bool(row["in_area_cost_review"]),
            "has_works_contract": bool(row["has_works_contract"]),
            "has_construction_candidate": bool(row["has_construction_candidate"]),
            "manual_construction_relevance": bool(
                row["manual_construction_relevance"]
            ),
            "data_version": data_version,
            "is_published": True,
        }
        for row in evaluation_project_rows
    ]
    evaluation_reports = [
        {
            **row,
            "data_version": data_version,
            "is_published": True,
        }
        for row in evaluation_report_rows
    ]
    evaluation_matches = [
        {
            **row,
            "match_score": float(row["match_score"]),
            "data_version": data_version,
            "is_published": True,
        }
        for row in evaluation_match_rows
    ]
    evaluation_findings: list[dict[str, Any]] = []
    for row in evaluation_finding_rows:
        public_row = {
            field: row.get(field)
            for field in EVALUATION_FINDING_FIELDS
            if field not in {"search_text", "data_version", "is_published"}
        }
        public_row.update(
            {
                "search_text": " ".join(
                    filter(
                        None,
                        (
                            clean_text(row.get("country_ko")),
                            clean_text(row.get("project_name")),
                            clean_text(row.get("report_title")),
                            clean_text(row.get("category")),
                            clean_text(row.get("field_code")),
                            clean_text(row.get("field_description")),
                            clean_text(row.get("summary_text")),
                            clean_text(row.get("value_text")),
                            clean_text(row.get("value_context")),
                            clean_text(row.get("evidence_excerpt")),
                        ),
                    )
                ),
                "data_version": data_version,
                "is_published": True,
            }
        )
        evaluation_findings.append(public_row)

    return {
        "data_version": data_version,
        "source_schema_version": schema_version,
        "source_db_sha256": source_sha256(database),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cases": cases,
        "related_notices": related_notices,
        "evaluation_projects": evaluation_projects,
        "evaluation_reports": evaluation_reports,
        "evaluation_matches": evaluation_matches,
        "evaluation_findings": evaluation_findings,
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_snapshot(snapshot: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "koica_search_cases.csv", snapshot["cases"], CASE_FIELDS)
    write_csv(
        output_dir / "koica_search_related_notices.csv",
        snapshot["related_notices"],
        RELATED_NOTICE_FIELDS,
    )
    write_csv(
        output_dir / "koica_evaluation_projects.csv",
        snapshot["evaluation_projects"],
        EVALUATION_PROJECT_FIELDS,
    )
    write_csv(
        output_dir / "koica_evaluation_reports.csv",
        snapshot["evaluation_reports"],
        EVALUATION_REPORT_FIELDS,
    )
    write_csv(
        output_dir / "koica_evaluation_matches.csv",
        snapshot["evaluation_matches"],
        EVALUATION_MATCH_FIELDS,
    )
    write_csv(
        output_dir / "koica_evaluation_findings.csv",
        snapshot["evaluation_findings"],
        EVALUATION_FINDING_FIELDS,
    )
    (output_dir / "koica_search_snapshot.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    if not args.database.is_file():
        parser.error(f"SQLite database not found: {args.database}")
    snapshot = build_snapshot(args.database)
    write_snapshot(snapshot, args.output_dir)
    print(
        f"Exported {len(snapshot['cases'])} cases and "
        f"{len(snapshot['related_notices'])} related notices; "
        f"{len(snapshot['evaluation_projects'])} evaluation project screenings, "
        f"{len(snapshot['evaluation_reports'])} reports, "
        f"{len(snapshot['evaluation_matches'])} matches, and "
        f"{len(snapshot['evaluation_findings'])} findings to {args.output_dir}"
    )


if __name__ == "__main__":
    main()
