#!/usr/bin/env python3
"""Build the reviewed 2016–2025 distribution dataset and CSV."""

from __future__ import annotations

import csv
import json
import re
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RECENT = ROOT / "data" / "manifests"
HIST = ROOT / "data_2016_2020" / "manifests"
OUT = ROOT / "outputs" / "koica-construction-distribution"


HISTORICAL = [
    ("L2020-00023-1", 6906, "Iraq", "병원", "신축", "A", "문단 32", "총연면적", ""),
    ("L2020-00022-2", 4916, "Ethiopia", "병원", "신축", "A", "표 2 행 3", "총연면적", ""),
    ("L2020-00009-1", 7450, "Myanmar", "농산물 유통·가공센터", "신축", "B", "표 2 행 5", "2개 시설 연면적 합계", "농업·산업시설 복합"),
    ("L2020-00001-2", 4177.94, "Cambodia", "이비인후과 병원", "신축", "A", "문단 19", "총연면적", ""),
    ("L2019-00043-1", 3944.30, "Jordan", "학교", "신축", "A", "페이지 1", "총연면적", ""),
    ("L2019-00024-1", 12974, "Sri Lanka", "교원교육대학", "신축", "A", "표 2 행 3", "총연면적", ""),
    ("L2019-00021-1", 5455, "Uzbekistan", "직업훈련원", "신축", "A", "페이지 1", "총연면적", ""),
    ("L2019-00011-1", 5625, "Laos", "출입국관리청사", "신축", "A", "문단 3", "주동 연면적", "부속시설 포함 가능"),
    ("L2019-00010-1", 1549.83, "Nepal", "IT 교육동", "신축", "A", "문단 54", "총연면적", ""),
    ("L2018-00029-1", 2879.23, "Bolivia", "병원", "신축", "A", "문단 51", "총연면적", "지하층·외부공사 포함"),
    ("L2018-00020-1", 7599, "Jordan", "학교 2개소", "신축", "A", "표 1 행 4", "2개 학교 연면적 합계", ""),
    ("L2018-00014-1", 6428, "Paraguay", "노인 장기요양센터", "신축", "A", "문단 44", "총연면적", ""),
    ("L2018-00012-1", 6615, "Philippines", "농업복합시설", "설계·시공", "B", "문단 20", "3개 동 연면적 합계", "축사·농업시설 포함"),
    ("L2018-00011-1", 1987, "Paraguay", "보건시설", "신축", "A", "문단 26", "총연면적", ""),
    ("L2017-00011-1", 2250, "Turkmenistan", "가스산업 직업훈련원", "설계·시공", "B", "문단 11", "계획 연면적", "설계·시공 일괄입찰"),
    ("L2017-00007-1", 1562.68, "Laos", "청소년 IT센터", "신축", "B", "표 1 행 4", "본동+연결통로 합계", ""),
    ("L2017-00005-1", 2541.35, "Ecuador", "보건센터", "신축", "A", "표 1 행 3", "총연면적", ""),
    ("L2017-00001-1", 8694, "Senegal", "고등교육·농업훈련센터", "신축", "B", "문단 19", "2개 시설 연면적 합계", "서로 다른 지역의 2개 시설"),
]


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_usd(raw: str) -> float:
    match = re.search(r"[\d,.]+", raw or "")
    if not match:
        raise ValueError(f"Missing USD amount: {raw!r}")
    return float(match.group(0).replace(",", ""))


def decimal_year(value: str) -> float | None:
    try:
        current = date.fromisoformat(value[:10])
    except Exception:
        return None
    start = date(current.year, 1, 1)
    end = date(current.year + 1, 1, 1)
    return current.year + (current - start).days / (end - start).days


def find_evidence(rows: list[dict], bid: str, locator: str) -> dict:
    exact = [
        row for row in rows
        if row.get("bid_no") == bid
        and row.get("category") == "연면적·면적"
        and row.get("source_locator") == locator
    ]
    if exact:
        return exact[0]
    candidates = [
        row for row in rows
        if row.get("bid_no") == bid and row.get("category") == "연면적·면적"
    ]
    if not candidates:
        raise ValueError(f"Missing evidence: {bid} / {locator}")
    return candidates[0]


def main() -> None:
    recent_rows: list[dict] = read_json(RECENT / "curated_unit_costs_expanded.json")
    recent_projects = {
        row["bid_no"]: row for row in read_json(RECENT / "projects.json")
    }
    historical_projects = {
        row["bid_no"]: row for row in read_json(HIST / "projects.json")
    }
    historical_evidence: list[dict] = read_json(HIST / "construction_evidence.json")

    combined: list[dict] = []
    for row in recent_rows:
        meta = recent_projects.get(row["bid_no"], {})
        notice_date = meta.get("notice_date") or f"{row['year']}-01-01"
        combined.append({
            "bid_no": row["bid_no"],
            "project_no": row.get("project_no", ""),
            "notice_date": notice_date,
            "price_year_decimal": decimal_year(notice_date),
            "country": row["country"],
            "region": row.get("region", ""),
            "facility_type": row["facility_type"],
            "work_type": row["work_type"],
            "gross_floor_area_m2": row.get("gross_floor_area_m2"),
            "cost_usd_nominal": row.get("construction_cost_usd"),
            "direct_unit_usd_m2": row.get("direct_unit_usd_m2"),
            "unit_usd_m2_nominal": row.get("unit_cost_usd_m2"),
            "evidence_grade": row.get("benchmark_grade", ""),
            "area_basis": row.get("area_basis", ""),
            "cost_stage": row.get("cost_stage", row.get("cost_basis", "")),
            "scope_caution": row.get("cost_scope_note", row.get("caution", "")),
            "normalization_status": "미보정",
            "recommended_unit_rate": "아니오",
            "allowed_use": "유사사례·현지견적 교차검증",
            "source_period": "2021-2025 수집분",
            "source_file": row.get("source_file", ""),
            "source_locator": row.get("source_locator", ""),
            "source_url": row.get("cost_source_url", meta.get("detail_url", "")),
            "evidence_summary": row.get("evidence_summary", ""),
        })

    for (
        bid, area, country, facility, work, grade, locator, area_basis, caution
    ) in HISTORICAL:
        meta = historical_projects[bid]
        evidence = find_evidence(historical_evidence, bid, locator)
        cost = parse_usd(meta.get("ceiling_usd_raw", ""))
        notice_date = meta.get("notice_date", "")
        combined.append({
            "bid_no": bid,
            "project_no": meta.get("project_no", ""),
            "notice_date": notice_date,
            "price_year_decimal": decimal_year(notice_date),
            "country": country,
            "region": "",
            "facility_type": facility,
            "work_type": work,
            "gross_floor_area_m2": area,
            "cost_usd_nominal": cost,
            "direct_unit_usd_m2": None,
            "unit_usd_m2_nominal": cost / area,
            "evidence_grade": grade,
            "area_basis": area_basis,
            "cost_stage": "공사 입찰 집행한도",
            "scope_caution": caution,
            "normalization_status": "미보정",
            "recommended_unit_rate": "아니오",
            "allowed_use": "유사사례·현지견적 교차검증",
            "source_period": "2016-2020 수집분",
            "source_file": evidence.get("source_file", ""),
            "source_locator": evidence.get("source_locator", locator),
            "source_url": meta.get("detail_url", ""),
            "evidence_summary": (
                f"{area_basis} {area:,.2f}㎡; 집행한도 USD {cost:,.0f}; "
                f"명목단가 USD {cost / area:,.0f}/㎡."
            ),
        })

    combined.sort(key=lambda row: (row["notice_date"], row["bid_no"]), reverse=True)
    if len({row["bid_no"] for row in combined}) != len(combined):
        raise ValueError("Duplicate bid numbers in distribution dataset")

    OUT.mkdir(parents=True, exist_ok=True)
    json_path = OUT / "reviewed_cases_2016_2025.json"
    csv_path = OUT / "KOICA_건축사업_검토사례_2016-2025.csv"
    json_path.write_text(
        json.dumps(combined, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    fields = list(combined[0])
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(combined)

    print(json.dumps({
        "rows": len(combined),
        "historical_added": len(HISTORICAL),
        "years": sorted({row["notice_date"][:4] for row in combined}),
        "countries": len({row["country"] for row in combined}),
        "recommended_unit_rates": sum(
            row["recommended_unit_rate"] == "예" for row in combined
        ),
        "json": str(json_path),
        "csv": str(csv_path),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
