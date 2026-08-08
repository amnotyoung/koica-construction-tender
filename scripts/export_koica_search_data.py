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
    "project_no",
    "representative_bid_no",
    "display_name",
    "official_project_name",
    "country_ko",
    "facility_type",
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
    for case_id in sorted(construction_groups):
        raw_latest = latest_row(construction_groups[case_id])
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
            else group_review.get("area_m2")
        )
        cost = as_float(
            notice_review.get("selected_construction_cost_usd")
            if notice_review.get("selected_construction_cost_usd") is not None
            else group_review.get("construction_cost_usd")
        )
        amount_stage = clean_text(notice_review.get("amount_stage"))
        if cost is None:
            cost = parse_usd_ceiling(representative.get("ceiling_usd_raw"))
            if cost is not None:
                amount_stage = "NOTICE_EXECUTION_CEILING_RAW"
        unit_cost = round(cost / area, 2) if cost and area else None
        evidence_grade = compact_grade(
            notice_review.get("compact_grade") or group_review.get("best_grade")
        )
        audit_date = clean_text(notice_review.get("audit_date")) or global_audit_date

        scope_note = join_notes(
            notice_review.get("scope_role"),
            notice_review.get("record_scope_status"),
            notice_review.get("same_scope_status"),
            group_review.get("duplicate_rule"),
        )
        evidence_note = join_notes(
            notice_review.get("grade_detail"),
            notice_review.get("manual_note"),
            notice_review.get("area_quote"),
        )
        facility_type = clean_text(representative.get("facility_type"))
        work_type = clean_text(representative.get("work_type"))
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
                "project_no": project_no,
                "representative_bid_no": representative_bid_no,
                "display_name": display_name,
                "official_project_name": official_project_name,
                "country_ko": country_ko,
                "facility_type": facility_type,
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
                "verification_level": clean_text(notice_review.get("verification_level")),
                "scope_note": scope_note,
                "evidence_note": evidence_note,
                "allowed_use": clean_text(notice_review.get("unit_cost_allowed_use")),
                "notice_count": int(group_review.get("notice_count") or len(construction_groups[case_id])),
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

    return {
        "data_version": data_version,
        "source_db_sha256": source_sha256(database),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cases": cases,
        "related_notices": related_notices,
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
        f"{len(snapshot['related_notices'])} related notices to {args.output_dir}"
    )


if __name__ == "__main__":
    main()
