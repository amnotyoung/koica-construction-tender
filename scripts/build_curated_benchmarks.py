#!/usr/bin/env python3
"""Build a conservative, citation-ready benchmark set from extracted evidence."""

from __future__ import annotations

import json
from pathlib import Path


def unit_record(
    bid_no: str,
    year: int,
    country: str,
    region: str,
    facility: str,
    work_type: str,
    area_m2: float | None,
    cost_usd: float | None,
    direct_unit_usd_m2: float | None,
    cost_basis: str,
    tax_note: str,
    source_file: str,
    source_locator: str,
    evidence: str,
    confidence: str = "높음",
    caution: str = "",
) -> dict:
    unit = direct_unit_usd_m2
    if unit is None and area_m2 and cost_usd:
        unit = cost_usd / area_m2
    return {
        "bid_no": bid_no,
        "year": year,
        "country": country,
        "region": region,
        "facility_type": facility,
        "work_type": work_type,
        "gross_floor_area_m2": area_m2,
        "construction_cost_usd": cost_usd,
        "direct_unit_usd_m2": direct_unit_usd_m2,
        "unit_cost_usd_m2": unit,
        "cost_basis": cost_basis,
        "tax_note": tax_note,
        "confidence": confidence,
        "caution": caution,
        "source_file": source_file,
        "source_locator": source_locator,
        "evidence_summary": evidence,
    }


def main() -> None:
    manifests = Path("data/manifests")
    units = [
        unit_record(
            "L2021-00016-1", 2021, "Cambodia", "Ratanakiri·Mondulkiri",
            "모자보건 의료시설(5개소)", "신축", 1325.32, 1022588, None,
            "입찰공고 추정예산", "VAT 제외",
            "L2021-00016-1/캄보디아 동북부 소외지역 모자보건 프로그램 시공업체 선정 입찰 공고문.pdf",
            "페이지 1", "GFA 약 1,325.32㎡, 추정예산 약 USD 1,022,588.",
        ),
        unit_record(
            "L2021-00029-1", 2021, "Nepal", "Tanahun·Bhotekoshi",
            "농촌 Outreach Center 2개소", "신축", 1120.30, 929600, None,
            "입찰 Construction Budget", "VAT 제외",
            "L2021-00029-1/네팔 ORC시공업체선정 영문 RFP.pdf",
            "페이지 3", "2개소 총 GFA 1,120.30㎡, 공사예산 USD 929,600.",
        ),
        unit_record(
            "L2021-00004-1", 2021, "Nepal", "Tanahun·Bhotekoshi",
            "농촌 Outreach Center 2개소", "신축", 1048, 936074, None,
            "설계·감리 입찰 단계 추정공사비", "문서 내 별도 확인",
            "L2021-00004-1/1. 설계 및 감리사 선정 영문 RFP.pdf",
            "페이지 2 및 문단 23",
            "Putter 769㎡ + Hindi 279㎡; Estimated construction cost USD 936,074.",
            "중간",
            "같은 사업의 후속 시공입찰(L2021-00029-1)에서 면적·예산이 조정됨.",
        ),
        unit_record(
            "L2022-00027-1", 2022, "Ecuador", "Quito",
            "혁신센터", "신축", 3100, 2670000, None,
            "CM 보고서 기반 추정공사비", "문서 내 별도 확인",
            "L2022-00027-1/2. 입찰서류(영문)_키토혁신센터 설계_220531/1. Ecuador Bidding Guideline 20220531.docx",
            "문단 57", "GFA 3,100㎡, 추정공사비 USD 2,670,000; 설계비율 6%.",
        ),
        unit_record(
            "L2023-00021-1", 2023, "Paraguay", "미상",
            "멀티미디어 교육지원센터", "신축", None, None, 1100,
            "사무소 협의 적용단가", "문서 내 별도 확인",
            "L2023-00021-1/붙임1. 파라과이 멀티미디어 센터 설계용역 입찰설명서(국문본)_최종_230130_기평팀.hwp",
            "문단 567", "건축 공사비 단가 USD 1,100/㎡ 적용, 설계비 8% 적용.",
            "높음",
            "면적·총공사비가 아닌 직접 제시된 계획단가.",
        ),
        unit_record(
            "L2023-00038-1", 2023, "Fiji", "Tamavua·Suva",
            "국립재활센터", "신축", 2700, 5627206, None,
            "설계입찰 단계 공사비 예산", "문서 내 별도 확인",
            "L2023-00038-1/1. 입찰계획서(피지국립재활센터 건립사업 설계 및 감리 용역)-김우영-230713.hwp",
            "문단 68 및 문단 70", "연면적 약 2,700㎡, 공사비 예산 USD 5,627,206.",
            "중간", "면적이 약식값이며 상세 공간계획 합계는 2,686.4㎡.",
        ),
        unit_record(
            "L2024-00066-1", 2024, "Fiji", "Fiji National University",
            "의과대학 시뮬레이션센터", "신축", 1060, 2406346, None,
            "ToR 공사비 예산", "문서 내 별도 확인",
            "L2024-00066-1/Section 5 - Terms of Reference (ToR) R1.doc",
            "문단 46", "3층, 총연면적 약 1,060㎡, 공사비 예산 약 USD 2,406,346.",
        ),
        unit_record(
            "L2024-00075-1", 2024, "Laos", "Paksong·Champasak",
            "남부 농업훈련센터", "신축", 700, 624034, None,
            "BDS Project Budget", "VAT 및 간접세 제외",
            "L2024-00075-1/Section 2 - Bid Data Sheet_1120.pdf",
            "페이지 5", "GFA 700㎡, Project Budget USD 624,034; 예정가격 USD 608,433.",
        ),
        unit_record(
            "L2025-00036-1", 2025, "Cambodia", "Phnom Penh",
            "Dangkao 후송병원(70병상)", "신축", 3700, 6600000, None,
            "심층기획조사 결과 추정공사비", "문서 내 별도 확인",
            "L2025-00036-1/붙임2. 입찰서류 영문본 일체/Section 6 - Related Project Information of RFP.pdf",
            "페이지 3", "3층, GFA 3,700㎡, Construction Cost USD 6.6 million.",
        ),
        unit_record(
            "L2025-00078-1", 2025, "Bolivia", "El Alto",
            "모성보건시설 2개소", "신축", 1600, 3226604, None,
            "예비조사 추정 건축공사비", "문서 내 별도 확인",
            "L2025-00078-1/1. 국문 입찰계획서.hwp",
            "문단 14·16·80",
            "두 시설 연면적 1,080㎡와 520㎡, 추정 건축공사비 USD 3,226,604.",
            "중간", "공사비가 두 시설 합계라는 해석에 기반하므로 원문 재확인 필요.",
        ),
        unit_record(
            "L2025-00097-1", 2025, "Kyrgyzstan", "Bishkek",
            "ICT 교육센터", "신축", 1179, 1704050, None,
            "설계 ToR 공사예산 한도", "문서 내 별도 확인",
            "L2025-00097-1/붙임1. 공고내역 (KG-2025-10)/ENG - final/Section 2 - Bid Data Sheet (BDS).docx",
            "표 5 행 3", "2층 GFA 1,179㎡, 공사예산 한도 USD 1,704,050(비상발전기 포함).",
        ),
    ]

    fees = [
        {
            "bid_no": "L2022-00027-1", "country": "Ecuador",
            "facility_type": "혁신센터", "gross_floor_area_m2": 3100,
            "construction_cost_usd": 2670000, "design_fee_usd": 160200,
            "supervision_fee_usd": None, "design_rate": 0.06,
            "supervision_rate": None, "combined_fee_usd": 160200,
            "combined_rate": 0.06, "tax_note": "문서 내 별도 확인",
            "source_file": units[3]["source_file"], "source_locator": "문단 57",
            "evidence_summary": "추정공사비의 6%로 설계비 설정.",
        },
        {
            "bid_no": "L2023-00021-1", "country": "Paraguay",
            "facility_type": "멀티미디어 교육지원센터",
            "gross_floor_area_m2": None, "construction_cost_usd": None,
            "design_fee_usd": None, "supervision_fee_usd": None,
            "design_rate": 0.08, "supervision_rate": None,
            "combined_fee_usd": None, "combined_rate": 0.08,
            "tax_note": "문서 내 별도 확인", "source_file": units[4]["source_file"],
            "source_locator": "문단 567",
            "evidence_summary": "공사비 단가 USD 1,100/㎡ 및 설계비 8% 적용.",
        },
        {
            "bid_no": "L2022-00003-1", "country": "Uzbekistan",
            "facility_type": "직업훈련원·교사연수센터",
            "gross_floor_area_m2": 7021, "construction_cost_usd": None,
            "design_fee_usd": 147535, "supervision_fee_usd": 100800,
            "design_rate": None, "supervision_rate": None,
            "combined_fee_usd": 248335, "combined_rate": None,
            "tax_note": "VAT 미포함",
            "source_file": "L2022-00003-1/코이카사무소_우르겐치직훈원 입찰공고문(홈페이지게시).pdf",
            "source_locator": "페이지 1",
            "evidence_summary": "GFA 7,021㎡; 설계 USD 147,535, 감리 USD 100,800.",
        },
        {
            "bid_no": "L2025-00036-1", "country": "Cambodia",
            "facility_type": "Dangkao 후송병원", "gross_floor_area_m2": 3700,
            "construction_cost_usd": 6600000, "design_fee_usd": None,
            "supervision_fee_usd": None, "combined_fee_usd": 500000,
            "design_rate": None, "supervision_rate": None,
            "combined_rate": 500000 / 6600000, "tax_note": "문서 내 별도 확인",
            "source_file": "L2025-00036-1/붙임2. 입찰서류 영문본 일체/Section 5 - Terms of Reference (ToR).doc",
            "source_locator": "문단 45",
            "evidence_summary": "GFA 3,700㎡, 설계·시공감리 합산예산 약 USD 500,000.",
        },
        {
            "bid_no": "L2025-00097-1", "country": "Kyrgyzstan",
            "facility_type": "ICT 교육센터", "gross_floor_area_m2": 1179,
            "construction_cost_usd": 1704050, "design_fee_usd": 99600,
            "supervision_fee_usd": 11163, "combined_fee_usd": 110763,
            "design_rate": 99600 / 1704050, "supervision_rate": 11163 / 1704050,
            "combined_rate": 110763 / 1704050, "tax_note": "VAT 및 기타 비용 제외",
            "source_file": units[10]["source_file"], "source_locator": "표 5 행 5",
            "evidence_summary": "설계 USD 99,600, 저작권감리 USD 11,163.",
        },
        {
            "bid_no": "L2025-00045-1", "country": "Iraq",
            "facility_type": "난민통합교육 학교", "gross_floor_area_m2": None,
            "construction_cost_usd": None, "design_fee_usd": 205500,
            "supervision_fee_usd": 205500, "combined_fee_usd": 411000,
            "design_rate": None, "supervision_rate": None, "combined_rate": None,
            "tax_note": "VAT 및 기타 비용 제외",
            "source_file": "L2025-00045-1/붙임3. 입찰서류(영문) 일체/Section 2 - Bid Data Sheet (BDS).docx",
            "source_locator": "표 5 행 5",
            "evidence_summary": "설계 USD 205,500 + 시공감리 USD 205,500.",
        },
        {
            "bid_no": "L2024-00052-1", "country": "Indonesia",
            "facility_type": "공공시설(설계·감리)", "gross_floor_area_m2": None,
            "construction_cost_usd": None, "design_fee_usd": 150000,
            "supervision_fee_usd": 50000, "combined_fee_usd": 200000,
            "design_rate": None, "supervision_rate": None, "combined_rate": None,
            "tax_note": "VAT 및 기타 비용 제외",
            "source_file": "L2024-00052-1/입찰관련서류/Section 2 - Bid Data Sheet (BDS)_└╘┬√░°░φ┐δ ├╓┴╛.docx",
            "source_locator": "표 5 행 5",
            "evidence_summary": "설계 USD 150,000, Construction Supervision USD 50,000.",
        },
    ]

    checklist = [
        ["연면적", "총 연면적과 동별·시설별 면적을 구분", "단가 산식의 분모"],
        ["공사비 범위", "건축·토목·설비·외부공사·장비 포함 여부", "사업 간 비교 가능성"],
        ["세금", "VAT·관세·간접세 포함/제외/면제", "명목단가 왜곡 방지"],
        ["예비비", "신축 5%, 증축·리모델링 10%를 참고하되 현지 위험 반영", "제공 양식 기준"],
        ["설계비", "공사비 대비 비율과 인허가비 포함 여부", "과거 사례 6~8% 등"],
        ["CM·감리", "CM 7~10%, 현지감리 4~5% 참고 및 과업범위 대조", "제공 양식 기준"],
        ["물가·환율", "기준일·환율·물가상승률을 별도 기록", "연도 간 단가 환산"],
        ["사업유형", "신축·증축·리모델링 구분", "예비비·난이도 차이"],
        ["지역조건", "수도/지방, 물류, 치안, 우기, 기반시설", "지역 가산요인"],
        ["근거성", "파일·페이지/문단/시트 셀을 반드시 기록", "재검증 가능성"],
    ]

    for name, value in (
        ("curated_unit_costs.json", units),
        ("curated_fee_benchmarks.json", fees),
        ("survey_checklist.json", checklist),
    ):
        (manifests / name).write_text(
            json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(f"unit_costs={len(units)} fee_benchmarks={len(fees)}")


if __name__ == "__main__":
    main()
