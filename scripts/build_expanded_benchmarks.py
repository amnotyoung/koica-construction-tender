#!/usr/bin/env python3
"""Expand the curated KOICA unit-cost benchmarks with reviewed bid ceilings and GFA."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = ROOT / "data" / "manifests"


# bid, area, country, region, facility, work, grade, summary, area-source bid,
# area locator, area basis, scope caution
ADDITIONS = [
    ("L2025-00099-1", 255.52, "Kyrgyzstan", "Chuy", "학교 위생시설", "리모델링·개보수", "B", True, None, "표 4 행 8", "대상 시설 합계", "소규모 실내 개보수"),
    ("L2025-00084-1", 4040, "Uganda", "Kampala", "Makerere대 원격교육센터", "신축", "A", True, None, "표 4 행 9", "총연면적", ""),
    ("L2025-00073-1", 9053, "Cambodia", "Phnom Penh", "국립소아병원", "신축", "A", True, None, "페이지 5", "총연면적", ""),
    ("L2025-00071-1", 5486, "Iraq", "Baghdad", "어린이 심장병원", "신축", "A", True, None, "표 2 행 7", "총연면적", ""),
    ("L2025-00062-1", 2378.8, "Uganda", "미상", "농업 시범농장 시설", "신축·토목", "C", False, None, "표 4 행 8", "동별 면적 합계", "관개·외부공사 포함 패키지"),
    ("L2025-00051-2", 2686.4, "Fiji", "Tamavua·Suva", "국립재활센터", "신축", "A", True, "L2023-00038-1", "표 1 행 3", "상세 공간계획 합계", "동일 사업 설계단계 사례와 중복"),
    ("L2025-00018-1", 2684.36, "Ghana", "미상", "대학교 교육센터", "신축", "A", True, None, "표 4 행 8", "총연면적", ""),
    ("L2025-00016-2", 15500, "Mozambique", "Matola", "학교 캠퍼스", "개보수", "C", False, None, "표 4 행 8", "대상 캠퍼스 면적", "부분 보수 총액으로 신축단가와 비교 불가"),
    ("L2025-00012-2", 87.22, "Bolivia", "Chacala", "소규모 공공시설", "신축", "B", True, None, "표 3 행 7", "총연면적", "소규모 공사의 고정비 영향"),
    ("L2025-00008-1", 404.94, "Kenya", "미상", "모자보건시설", "신축", "A", True, None, "표 4 행 8", "총연면적", ""),
    ("L2025-00002-1", 2457.53, "Indonesia", "미상", "사이버보안 교육센터", "신축", "A", True, None, "표 4 행 8", "총연면적", ""),
    ("L2024-00079-1", 4996.62, "Nepal", "미상", "재활용 산업 플랫폼", "신축", "A", True, None, "표 5 행 8", "총연면적", "산업시설 성격"),
    ("L2024-00078-1", 936.2, "Dominican Republic", "미상", "직업훈련센터", "신축", "A", True, None, "표 2 행 7", "총연면적", ""),
    ("L2024-00050-1", 4032, "Uganda", "미상", "훈련복합시설", "신축", "B", True, None, "표 4 행 8", "동별 면적 합계", "외부공사 포함 가능"),
    ("L2024-00049-2", 788.12, "El Salvador", "미상", "ITCA 교육시설", "신축", "A", True, None, "문단 15", "총연면적", ""),
    ("L2024-00039-1", 8217, "Iraq", "미상", "직업훈련원", "리모델링·개보수", "C", False, None, "표 4 행 8", "대상 연면적", "부분 리모델링 범위"),
    ("L2024-00031-1", 5898.25, "Nepal", "Bhaktapur", "보건·의료시설", "신축", "A", True, None, "표 5 행 8", "총연면적", ""),
    ("L2023-00068-1", 3500, "Cambodia", "미상", "안과병원", "리모델링·개보수", "C", False, None, "표 5 행 8", "대상 연면적", "부분 보수 공사"),
    ("L2023-00067-1", 420, "Kyrgyzstan", "Bishkek", "G-Cloud 시설", "리모델링·개보수", "B", True, None, "표 3 행 8", "대상 연면적", ""),
    ("L2023-00060-1", 2983, "El Salvador", "미상", "보건교육센터", "신축", "A", True, None, "문단 24", "총연면적", ""),
    ("L2023-00053-1", 6963, "Uzbekistan", "미상", "직업훈련원", "신축", "A", True, None, "문단 10", "총연면적", ""),
    ("L2023-00045-1", 453, "Senegal", "미상", "메이커스페이스", "리모델링·개보수", "B", True, None, "문단 8", "대상 연면적", ""),
    ("L2023-00035-1", 1739.82, "Kyrgyzstan", "미상", "공공서비스센터", "리모델링·개보수", "C", False, None, "표 3 행 8", "대상 연면적", "재활·보수 범위"),
    ("L2023-00022-1", 826.8, "Timor-Leste", "미상", "농업 인프라 시설", "신축·토목", "C", False, None, "표 1 행 8", "동별 면적 합계", "도로·급수 등 토목 포함"),
    ("L2023-00018-1", 6149, "Indonesia", "미상", "청소년 재활시설", "리모델링·개보수", "C", False, None, "문단 67", "대상 연면적", "개보수 패키지"),
    ("L2023-00011-1", 6456, "Uganda", "미상", "온실·창고", "신축·토목", "C", False, None, "표 5 행 8", "시설 면적 합계", "온실 중심 비표준 시설"),
    ("L2023-00009-1", 827.4, "Uganda", "미상", "옥수수 가공·시장시설", "신축", "B", True, None, "표 5 행 8", "시설 면적 합계", "산업·시장시설"),
    ("L2022-00055-1", 449.72, "Kyrgyzstan", "미상", "약초 건조시설", "신축", "B", True, None, "문단 103", "총연면적", "산업시설"),
    ("L2022-00046-1", 858, "Dominican Republic", "미상", "보건센터", "신축", "A", True, None, "문단 57", "총연면적", ""),
    ("L2022-00043-1", 2194, "Bangladesh", "미상", "사이버수사 교육시설", "신축", "A", True, None, "문단 3", "총연면적", ""),
    ("L2022-00029-1", 5640.1, "Nepal", "미상", "모델 폴리테크닉", "신축", "A", True, None, "표 1 행 4", "총연면적", ""),
    ("L2022-00007-2", 1458, "Indonesia", "미상", "경찰 교육시설", "리모델링·개보수", "C", False, None, "문단 64", "대상 연면적", "개보수 패키지"),
    ("L2021-00045-1", 2866.41, "Paraguay", "미상", "항공훈련센터", "신축", "A", True, None, "문단 92", "총연면적", ""),
    ("L2021-00030-1", 945, "Paraguay", "미상", "항공훈련 격납고", "신축", "B", True, None, "문단 92", "총연면적", "동일 사업의 별도 공사 패키지"),
    ("L2021-00015-1", 2299.26, "Cambodia", "미상", "창업보육센터", "신축", "A", True, None, "문단 18", "총연면적", ""),
    ("L2025-00047-1", 1980, "Pakistan", "미상", "섬유산업 교육센터", "신축", "B", True, "L2025-00014-1", "표 4 행 7", "동일 사업 감리공고 연면적", "다른 단계 공고 간 연결"),
    ("L2025-00052-1", 1500, "Côte d’Ivoire", "미상", "PETROCI 교육시설", "리모델링·개보수", "B", True, "L2024-00056-2", "표 1 행 4", "동일 사업 선행공고 연면적", "다른 단계 공고 간 연결"),
    ("L2021-00031-1", 2349.2, "Pakistan", "미상", "태양광 연구실", "신축", "A", True, None, "표 2 행 7", "총연면적", ""),
]


def parse_usd(raw: str) -> float | None:
    numbers = re.findall(r"[\d,.]+", raw or "")
    if not numbers:
        return None
    # The field may append a parenthetical KRW/USD exchange rate. The first
    # number is the USD ceiling displayed immediately after the dollar sign.
    return float(numbers[0].replace(",", ""))


def pick_evidence(evidence: list[dict], bid: str, locator: str, area: float) -> dict:
    candidates = [
        row for row in evidence
        if row.get("bid_no") == bid
        and row.get("category") == "연면적·면적"
        and row.get("source_locator") == locator
    ]
    if not candidates:
        candidates = [
            row for row in evidence
            if row.get("bid_no") == bid and row.get("category") == "연면적·면적"
        ]
    if not candidates:
        raise ValueError(f"No area evidence: {bid} / {locator}")

    forms = {
        f"{area:g}",
        f"{area:,.1f}",
        f"{area:,.2f}",
        f"{area:,.0f}",
    }

    def score(row: dict) -> tuple[int, int]:
        text = " ".join(str(row.get(k, "")) for k in ("area_mentions", "evidence_text"))
        numeric_match = max((len(form) for form in forms if form in text), default=0)
        locator_match = int(row.get("source_locator") == locator)
        return locator_match, numeric_match

    return max(candidates, key=score)


def main() -> None:
    projects = json.loads((MANIFESTS / "projects.json").read_text(encoding="utf-8"))
    evidence = json.loads((MANIFESTS / "construction_evidence.json").read_text(encoding="utf-8"))
    base = json.loads((MANIFESTS / "curated_unit_costs.json").read_text(encoding="utf-8"))
    project_by_bid = {row["bid_no"]: row for row in projects}

    # Keep the original reviewed rows, but remove the superseded Nepal design-stage
    # duplicate. Fiji's design-stage row remains as a documented escalation pair.
    expanded = []
    for row in base:
        if row["bid_no"] == "L2021-00004-1":
            continue
        item = dict(row)
        meta = project_by_bid.get(item["bid_no"], {})
        item.update({
            "project_no": meta.get("project_no", ""),
            "benchmark_grade": "A" if item.get("confidence") == "높음" else "B",
            "summary_include": item["bid_no"] != "L2023-00038-1",
            "area_basis": "문서 명시 연면적" if item.get("gross_floor_area_m2") else "직접 제시 계획단가",
            "cost_stage": item.get("cost_basis", ""),
            "cost_scope_note": item.get("caution", ""),
            "cost_source_url": meta.get("detail_url", ""),
        })
        expanded.append(item)

    for (
        bid, area, country, region, facility, work, grade, include,
        area_bid, locator, area_basis, caution,
    ) in ADDITIONS:
        meta = project_by_bid.get(bid)
        if not meta:
            raise ValueError(f"Missing project metadata: {bid}")
        cost = parse_usd(meta.get("ceiling_usd_raw", ""))
        if not cost:
            raise ValueError(f"Missing USD ceiling: {bid}")
        source_bid = area_bid or bid
        ev = pick_evidence(evidence, source_bid, locator, area)
        expanded.append({
            "bid_no": bid,
            "project_no": meta.get("project_no", ""),
            "year": int(bid[1:5]),
            "country": country,
            "region": region,
            "facility_type": facility,
            "work_type": work,
            "gross_floor_area_m2": area,
            "construction_cost_usd": cost,
            "direct_unit_usd_m2": None,
            "unit_cost_usd_m2": cost / area,
            "cost_basis": "현지입찰 상세 집행한도금액(달러)",
            "tax_note": "세금·관세 포함 여부 원문 재확인",
            "confidence": {"A": "높음", "B": "중간", "C": "참고"}[grade],
            "benchmark_grade": grade,
            "summary_include": include,
            "area_basis": area_basis,
            "cost_stage": "공사 입찰 집행한도",
            "cost_scope_note": caution,
            "caution": caution,
            "source_file": ev.get("source_file", ""),
            "source_locator": ev.get("source_locator", locator),
            "cost_source_url": meta.get("detail_url", ""),
            "evidence_summary": (
                f"{area_basis} {area:,.2f}㎡; 상세페이지 집행한도 "
                f"USD {cost:,.0f}; 산출단가 USD {cost / area:,.0f}/㎡."
            ),
        })

    seen = set()
    for row in expanded:
        if row["bid_no"] in seen:
            raise ValueError(f"Duplicate benchmark bid: {row['bid_no']}")
        seen.add(row["bid_no"])
    expanded.sort(key=lambda row: row["bid_no"], reverse=True)
    out = MANIFESTS / "curated_unit_costs_expanded.json"
    out.write_text(json.dumps(expanded, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "output": str(out),
        "rows": len(expanded),
        "summary_rows": sum(bool(row["summary_include"]) for row in expanded),
        "grades": {
            grade: sum(row["benchmark_grade"] == grade for row in expanded)
            for grade in ("A", "B", "C")
        },
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
