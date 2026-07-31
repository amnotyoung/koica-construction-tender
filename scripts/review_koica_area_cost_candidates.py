#!/usr/bin/env python3
"""Re-audit the 170 KOICA notices that contain both area and amount signals.

The audit intentionally keeps three levels separate:

* notice: the 170 source notices selected from the KOICA-only SQLite database;
* notice group: 154 ``bid_base_no`` groups, retaining reannouncement history;
* project: 91 KOICA project numbers, which may contain several distinct packages.

The historical ``reviewed_cases.evidence_grade`` is never promoted into the new
estimating-readiness grade.  It is used only as manually curated area/amount
evidence.  Strict A/B evidence is imported from the separately audited
attachment corpus and only assigned to the exact evidence notice (or a manually
confirmed identical reannouncement).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from grade_koica_construction_candidates import (
    BLANK_FILE_RE,
    BOQ_FILE_RE,
    SPREADSHEET_EXTENSIONS,
    scan_spreadsheet,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = Path(
    "outputs/koica-construction-distribution/KOICA_건축사업_사례DB_2016-2025.sqlite"
)
DEFAULT_OUT = Path("outputs/koica-area-cost-review")

AUDIT_DATE = date(2026, 8, 1).isoformat()
GRADE_SYSTEM = "KOICA-AREA-COST-READINESS-2.0"


HISTORICAL_C_NOTICES = {
    "L2018-00026-1",
    "L2018-00029-1",
    "L2017-00011-1",
    "L2020-00022-1",
    "L2020-00022-2",
    "L2019-00024-1",
    "L2019-00010-1",
    "L2018-00011-1",
    "L2018-00014-1",
    "L2020-00023-1",
    "L2017-00007-1",
    "L2020-00009-1",
    "L2019-00011-1",
    "L2018-00020-1",
    "L2019-00043-1",
    "L2018-00019-1",
    "L2018-00012-1",
    "L2020-00003-1",  # stored as service, but the source is a works notice
    "L2019-00021-1",
    "L2020-00001-1",
    "L2020-00001-2",
    "L2017-00001-1",
    "L2017-00005-1",
}

HISTORICAL_SERVICE_X = {
    "L2018-00025-1",
    "L2018-00025-2",
    "L2019-00034-1",
    "L2019-00037-1",
    "L2018-00008-1",
    "L2019-00019-1",
    "L2018-00005-1",
    "L2020-00007-1",
    "L2018-00015-1",
    "L2020-00004-1",
}

HISTORICAL_NONBUILDING_X = {
    "L2019-00040-1",
    "L2019-00040-2",
    "L2019-00041-1",
    "L2019-00042-1",
    "L2020-00015-1",
}

HISTORICAL_NOTICE_NOTES = {
    "L2019-00040-1": "3.1416㎡는 식재 1주 주변 청소면적이며 GFA가 아님",
    "L2019-00040-2": "3.1416㎡는 식재 1주 주변 청소면적이며 GFA가 아님",
    "L2019-00041-1": "12㎡는 빗물집수장치 지붕면적이며 건물 GFA가 아님",
    "L2019-00042-1": "12㎡는 빗물집수장치 지붕면적이며 건물 GFA가 아님",
    "L2020-00015-1": "50mm² 전선 단면적을 면적으로 오인한 자동추출",
    "L2019-00044-1": "검출 4㎡는 기술규격의 도장 표면 문맥; 리모델링 GFA 미확인",
    "L2019-00046-1": (
        "신규 마감 외에 기존 사무소 원상복구·가구·이사·예비비가 포함되어 "
        "656/679㎡와 금액 범위가 일치하지 않음"
    ),
    "L2020-00003-1": "DB는 용역이나 원문은 NTIC 시공공고",
}

# Source-verified price-stage observations.  Both the notice execution ceiling
# and the bidding/basic amount remain in the output; neither overwrites the other.
BASIC_PRICE_EVIDENCE: dict[str, dict[str, Any]] = {
    "L2017-00001-1": {
        "amount": 5_664_262.66,
        "stage": "ADVERTISED_ESTIMATED_BUDGET",
        "tax": "VAT_EXCLUDED",
        "file": "L2017-00001-1/붙임2_입찰공고문(영문).docx",
        "locator": "문단 15",
        "quote": "Estimated Budget: Approx. USD 5,664,262.66 (VAT excluded)",
    },
    "L2017-00007-1": {
        "amount": 1_197_640,
        "stage": "ADVERTISED_BUDGET_CAP",
        "tax": "VAT_EXCLUDED",
        "file": "L2017-00007-1/청년동맹 IT 센터 Bid Announcement (20170911_신문공고).docx",
        "locator": "문단 27",
        "quote": "The budget for this Project is estimated as USD 1,197,640 (Excluding V.A.T)",
    },
    "L2018-00012-1": {
        "amount": 4_374_688,
        "stage": "ADVERTISED_ESTIMATED_BUDGET",
        "tax": "VAT_INCLUDED",
        "file": "L2018-00012-1/Bid Announcement (Quirino2)_final.docx",
        "locator": "표 1 행 7",
        "quote": "Estimated Budget USD 4,374,688.00 (Inclusive of VAT, provisional sum)",
        "contingency": "Provisional sum 8% included",
    },
    "L2018-00014-1": {
        "amount": 4_466_261,
        "stage": "BASIC_ESTIMATED_PRICE",
        "tax": "VAT_EXEMPT",
        "file": "L2018-00014-1/Bidding Guideline_Santo Domingo_180818.docx",
        "locator": "문단 64",
        "quote": "Basic Estimated Price: USD 4,466,261 (VAT exempted)",
    },
    "L2018-00020-1": {
        "amount": 5_354_000,
        "stage": "ADVERTISED_BUDGET_CAP",
        "tax": "SALES_TAX_INCLUDED",
        "file": "L2018-00020-1/붙임_ (입찰공고) Invitation for Bids_Bid Announcement_Rev3_최종.docx",
        "locator": "문단 27",
        "quote": "The available budget for this procurement assignment is USD 5,354,000 (sales tax included)",
    },
    "L2018-00029-1": {
        "amount": 4_114_500,
        "stage": "BID_LIMIT",
        "tax": "VAT_INCLUDED",
        "file": "L2018-00029-1/국문 재공고입찰계획서.hwp",
        "locator": "문단 95",
        "quote": "집행한도액 US $4,220,000 / 입찰한도액 US $4,114,500 (VAT 포함, -2.5%)",
    },
    "L2019-00024-1": {
        "amount": 7_161_000,
        "stage": "BASIC_ESTIMATED_PRICE",
        "tax": "UNKNOWN",
        "file": "L2019-00024-1/BIDDING NOTICE.docx",
        "locator": "표 2 행 6",
        "quote": "Basic/advertised construction amount USD 7,161,000; detail execution ceiling USD 7,300,000",
    },
    "L2020-00023-1": {
        "amount": 16_029_000,
        "stage": "BASIC_ESTIMATED_PRICE",
        "tax": "VAT_EXCLUDED",
        "file": "L2020-00023-1/[붙임1] 중환자 병원 입찰계획안.hwp",
        "locator": "문단 34",
        "quote": "기초금액 USD 16,029,000 (VAT 제외)",
    },
}


RECENT_SCOPE_PARTIAL = {
    "L2021-00017-1",
    "L2022-00001-1",
    "L2024-00068-1",
    "L2024-00068-2",
    "L2025-00016-1",
    "L2025-00016-2",
    "L2025-00051-1",
    "L2025-00051-2",
}

RECENT_SCOPE_NO_WORKS = {
    "L2023-00032-1",
    "L2025-00019-1",
    "L2025-00056-1",
}

RECENT_NOTICE_NOTES = {
    "L2021-00017-1": "두 센터 전체 GFA와 부분 개선공사 범위가 다름",
    "L2022-00001-1": "캠퍼스 전체 면적과 일부 칸막이·슬로프·실습실 공사 범위가 다름",
    "L2023-00032-1": "도로안전 공사 시방서의 책상·캐비닛 표면적을 GFA로 오인",
    "L2024-00048-1": "2·7㎡/person 공간계획 기준이며 대상 GFA가 아님",
    "L2024-00056-1": "2·7㎡/person 공간계획 기준이며 대상 GFA가 아님",
    "L2024-00056-2": "2·7㎡/person 공간계획 기준이며 대상 GFA가 아님",
    "L2023-00077-1": "BOQ 벽도장·철골 표면적이며 GFA가 아님",
    "L2024-00068-1": "방·벽·방수·도장 면적이 중첩되어 단일 GFA를 만들 수 없음",
    "L2024-00068-2": "방·벽·방수·도장 면적이 중첩되어 단일 GFA를 만들 수 없음",
    "L2024-00074-1": "기자재 조달용 바닥타일 면적이며 건축공사 GFA가 아님",
    "L2024-00076-1": "DB는 공사이나 실제 퇴비화 플랜트 설계용역; 대지·footprint만 확인",
    "L2025-00016-1": "캠퍼스 GFA 15,500㎡ 대비 공사는 조명·창살·경비실·지붕·화장실 일부 보수",
    "L2025-00016-2": "캠퍼스 GFA 15,500㎡ 대비 공사는 조명·창살·경비실·지붕·화장실 일부 보수",
    "L2025-00019-1": "도장 샘플 면적과 소화기 이동거리 OCR값이며 관개공사 GFA가 아님",
    "L2025-00051-1": "Internal Area 2,399㎡ 외 부속시설 면적이 도면 참조로 미완성",
    "L2025-00051-2": "Internal Area 2,399㎡ 외 부속시설 면적이 도면 참조로 미완성",
    "L2025-00056-1": "입찰업체 Company Profile의 타 사업 포트폴리오 면적",
    "L2022-00034-1": "DB는 용역이나 원문은 영양교육센터 신축공사",
}

RECENT_AREA_AMBIGUOUS = {
    "L2023-00032-1",
    "L2025-00019-1",
    "L2024-00048-1",
    "L2024-00056-1",
    "L2024-00056-2",
    "L2023-00077-1",
    "L2024-00074-1",
    "L2024-00068-1",
    "L2024-00068-2",
}

RECENT_AREA_SITE = {"L2024-00076-1"}
RECENT_AREA_QUALIFICATION = {"L2025-00056-1"}


STRICT_NOTICE_REVIEWS: dict[str, dict[str, str]] = {
    "L2025-00018-1": {
        "grade": "A",
        "scope": "FULL",
        "detail": "가격 있는 설계 BOQ 수량·단가·금액 수동검증",
    },
    "L2025-00085-1": {
        "grade": "A",
        "scope": "PARTIAL_BOUNDED",
        "detail": "건축 Bill No.01만 숨김 설계단가와 결합; 타 공종 제외",
    },
    "L2025-00012-1": {
        "grade": "B",
        "scope": "FULL",
        "detail": "건축·구조·전기·위생·조경 blank BOQ 수동검증",
    },
    "L2025-00012-2": {
        "grade": "B",
        "scope": "FULL",
        "detail": "재공고의 동일 차칼라 blank BOQ; 한 표본으로 처리",
    },
    "L2024-00078-1": {
        "grade": "B",
        "scope": "PARTIAL_BOUNDED",
        "detail": "몬테크리스티 직업훈련센터 899행 blank BOQ",
    },
    "L2023-00036-1": {
        "grade": "B",
        "scope": "FULL",
        "detail": "우르겐치 VTC·TTC 공종별 not-priced BOQ",
    },
    "L2025-00073-1": {
        "grade": "B",
        "scope": "FULL",
        "detail": "국립소아병원 공종별 blank BOQ",
    },
    "L2025-00051-1": {
        "grade": "B",
        "scope": "FULL",
        "detail": "피지 국립재활센터 공종별 blank BOQ",
    },
    "L2025-00051-2": {
        "grade": "B",
        "scope": "FULL",
        "detail": "재공고의 동일 피지 blank BOQ; 한 표본으로 처리",
    },
}

RELATED_OTHER_PACKAGE_EVIDENCE = {
    "2023-00087": {
        "grade": "B-부분(다른 패키지)",
        "bid_no": "L2025-00017-2",
        "detail": "자이툰 도서관 BOQ이며 현재 170집합의 학교·연수센터 용역 범위와 다름",
    }
}

COUNTRY_CORRECTIONS = {
    "2017-07115": "우즈베키스탄",
    "2014-00024": "투르크메니스탄",
    "2024-00105": "키르기스스탄",
    "2019-03655": "키르기스스탄",
}

# Values below resolve extraction contexts where a site figure and a GFA (or
# several building GFAs) occur in the same table/passage.  They are deliberately
# explicit so that the aggregation choice is auditable rather than hidden in a
# “take the largest number” heuristic.
AREA_MANUAL_OVERRIDES: dict[str, dict[str, Any]] = {
    "L2018-00019-1": {
        "value": 6_186.0,
        "semantic": "GFA_MIXED_NEW_AND_RENOVATION",
        "aggregation": "SUM_6_BUILDINGS",
        "file": "L2018-00019-1",
        "locator": "입찰개요 문단 3",
        "quote": "신축 1,230+700㎡ 및 기존건물 개보수 1,122+1,350+1,560+224㎡ 합계",
    },
    "L2020-00001-1": {
        "value": 4_177.94,
        "semantic": "GFA",
        "aggregation": "TOTAL",
        "file": "L2020-00001-1",
        "locator": "표 2 행 5",
        "quote": "Gross Floor Area approx. 4,177.94 m2; site/building footprint 별도",
    },
    "L2020-00003-1": {
        "value": 3_117.0,
        "semantic": "GFA",
        "aggregation": "TOTAL_4_FLOORS",
        "file": "L2020-00003-1",
        "locator": "표 1 행 4 / 문단 43",
        "quote": "Total Gross Floor Area 3,117㎡; site area 3,609.40㎡ 제외",
    },
    "L2020-00022-1": {
        "value": 4_916.0,
        "semantic": "GFA",
        "aggregation": "TOTAL",
        "file": "L2020-00022-1",
        "locator": "표 2 행 3",
        "quote": "Total floor area 4,916㎡; site 48,000㎡와 footprint 2,488㎡ 제외",
    },
    "L2021-00025-1": {
        "value": 1_325.32,
        "semantic": "GFA",
        "aggregation": "TOTAL_MULTI_FACILITY",
        "file": "L2021-00025-1",
        "locator": "페이지 7 / 문단 12",
        "quote": "Gross Floor Area approx. 1,325.32㎡; site area 66,209.28㎡ 제외",
    },
    "L2021-00037-1": {
        "value": 1_325.32,
        "semantic": "GFA",
        "aggregation": "TOTAL_MULTI_FACILITY",
        "file": "L2021-00037-1",
        "locator": "표 17·33 행 5",
        "quote": "Gross Floor Area approx. 1,325.32㎡; site area 66,209.28㎡ 제외",
    },
    "L2022-00032-1": {
        "value": 858.0,
        "semantic": "GFA",
        "aggregation": "TOTAL",
        "file": "L2022-00032-1",
        "locator": "문단 9·32",
        "quote": "Gross floor area 858㎡; 안전관리 일반기준 1,000㎡ 제외",
    },
    "L2022-00068-1": {
        "value": 2_443.0,
        "semantic": "RENOVATION_FLOOR_AREA",
        "aggregation": "SUM_2_FLOORS",
        "file": "L2022-00068-1/붙임 1. 입찰 계획서.hwp",
        "locator": "문단 115·117",
        "quote": "1층 1,246㎡ + 2층 1,197㎡; 안전관리 일반기준 1,000㎡ 제외",
    },
    "L2023-00004-1": {
        "value": 2_443.0,
        "semantic": "RENOVATION_FLOOR_AREA",
        "aggregation": "SUM_2_FLOORS",
        "file": "L2023-00004-1/붙임 1. 에티오피아 ICT 센터 입찰 계획.hwp",
        "locator": "문단 114·116",
        "quote": "1층 1,246㎡ + 2층 1,197㎡; 안전관리 일반기준 1,000㎡ 제외",
    },
    "L2023-00006-1": {
        "value": 826.8,
        "semantic": "GFA",
        "aggregation": "SUM_3_COLLECTION_STATIONS",
        "file": "L2023-00006-1",
        "locator": "입찰개요 페이지 5",
        "quote": "245.7+335.4+245.7㎡ 합계; 대지면적 1,983/2,738.6/3,172㎡ 제외",
    },
    "L2023-00019-1": {
        "value": 826.8,
        "semantic": "GFA",
        "aggregation": "SUM_3_COLLECTION_STATIONS",
        "file": "L2023-00019-1",
        "locator": "재공고 입찰개요",
        "quote": "3개 농산물 집하장 245.7+335.4+245.7㎡ 합계",
    },
    "L2023-00007-1": {
        "value": 6_963.0,
        "semantic": "GFA",
        "aggregation": "SUM_VTC_TTC",
        "file": "L2023-00007-1",
        "locator": "문단 203·204 / 표 1 행 5",
        "quote": "VTC 5,698㎡ + TTC 1,265㎡",
    },
    "L2023-00036-1": {
        "value": 6_963.0,
        "semantic": "GFA",
        "aggregation": "SUM_VTC_TTC",
        "file": "L2023-00036-1",
        "locator": "문단 203·204 / 표 1 행 5",
        "quote": "VTC 5,698㎡ + TTC 1,265㎡",
    },
    "L2023-00009-1": {
        "value": 835.67,
        "semantic": "GFA",
        "aggregation": "TOTAL_RESTORED_HWP_CONTEXT",
        "file": "L2023-00009-1",
        "locator": "HWP 문단 91·92",
        "quote": "건축면적(연면적) 835.67㎡; 앞 문단의 대지면적 6,070.35㎡와 분리",
    },
}


AREA_RE = re.compile(
    r"(?<![A-Za-z])(?P<value>\d[\d\s,.]{0,18}?)\s*"
    r"(?P<unit>㎡|m\s*[²2]|sq\.?\s*m(?:eters?)?|square\s+meters?)",
    re.IGNORECASE,
)
USD_RE = re.compile(r"(?:US\s*)?\$\s*([\d,]+(?:\.\d+)?)|USD\s*([\d,]+(?:\.\d+)?)", re.I)
NUMBER_RE = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?")

GFA_RE = re.compile(
    r"(?i)(gross\s*(?:floor|building)?\s*area|total\s*floor\s*area|\bGFA\b|"
    r"internal\s+area|floor\s+area|연\s*면적|연면적|건축연면적|building\s+size)"
)
SITE_RE = re.compile(r"(?i)(site\s+area|land\s+area|plot\s+area|대지면적|부지면적|site\s+size)")
BUILDING_AREA_RE = re.compile(r"(?i)(building\s+area|건축면적|construction\s+area)")
QUALIFICATION_RE = re.compile(
    r"(?i)(similar\s+(?:project|experience|performance)|experience\s+record|"
    r"at\s+least|minimum|qualification|bidder|입찰참가|유사\s*실적|실적합계|평가|이상)"
)
WORK_ITEM_RE = re.compile(
    r"(?i)(paint|painting|surface|waterproof|cleaning|radius|per\s+day|wire|cable|"
    r"tile|wall|식재|청소|도장|방수|전선|단면적|소화기|company\s+profile|portfolio)"
)

DESIGN_SERVICE_RE = re.compile(
    r"(?i)(설계.*(?:용역|입찰|업체|사\s*선정)|감리|설계감리|시공감리|저작권감리|control\s+office|"
    r"design\s+(?:and\s+)?supervision|consult(?:ant|ing)|supervision\s+service)"
)
WORKS_TITLE_RE = re.compile(
    r"(?i)(시공업체|시공사|신축공사|건축\s*공사|리모델링\s*공사|보수\s*공사|"
    r"마감공사|공사입찰|설계\s*[·및/]?\s*시공|construction\s+works|civil\s+works|"
    r"renovation\s+works|contractor)"
)


def clean(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def parse_amount(raw: str) -> float | None:
    text = clean(raw).replace("\xa0", " ")
    match = USD_RE.search(text)
    if match:
        return float((match.group(1) or match.group(2)).replace(",", ""))
    match = NUMBER_RE.search(text)
    return float(match.group().replace(",", "")) if match else None


def normalize_area_number(raw: str) -> float | None:
    text = re.sub(r"\s+", "", raw).strip(".,")
    if not text:
        return None
    if text.count(",") > 1:
        text = text.replace(",", "")
    elif "," in text and "." in text:
        text = text.replace(",", "")
    elif "," in text:
        right = text.rsplit(",", 1)[1]
        text = text.replace(",", ".") if len(right) in {1, 2} else text.replace(",", "")
    try:
        value = float(text)
    except ValueError:
        return None
    if not math.isfinite(value) or value <= 0:
        return None
    return value


def classify_area_context(context: str) -> tuple[str, int]:
    text = clean(context)
    if QUALIFICATION_RE.search(text) and not re.search(r"(?i)(project\s+summary|scope\s+of\s+work|공사개요)", text):
        return "QUALIFICATION", 10
    if WORK_ITEM_RE.search(text) and not GFA_RE.search(text):
        return "WORK_ITEM_AREA", 5
    if GFA_RE.search(text):
        score = 100 + (5 if re.search(r"(?i)(total|gross|연면적)", text) else 0)
        return "GFA", score
    if BUILDING_AREA_RE.search(text):
        return "BUILDING_OR_CONSTRUCTION_AREA", 75
    if SITE_RE.search(text):
        return "SITE_AREA", 20
    return "AMBIGUOUS_AREA", 40


def classify_area_match(source_text: str, match: re.Match[str]) -> tuple[str, int, str]:
    """Classify an area by the nearest preceding label, not the whole passage.

    Extracted table rows often contain `site / footprint / GFA` in one long
    string.  A passage-wide keyword test incorrectly assigns the site number to
    GFA.  The last label before the number is a safer deterministic proxy.
    """

    before = source_text[max(0, match.start() - 140):match.start()]
    after = source_text[match.end():min(len(source_text), match.end() + 70)]
    local = before + match.group(0) + after
    if QUALIFICATION_RE.search(local) and not re.search(
        r"(?i)(project\s+summary|scope\s+of\s+work|공사개요)", local
    ):
        return "QUALIFICATION", 10, local
    labels = (
        (GFA_RE, "GFA", 100),
        (SITE_RE, "SITE_AREA", 20),
        (BUILDING_AREA_RE, "BUILDING_OR_CONSTRUCTION_AREA", 75),
        (WORK_ITEM_RE, "WORK_ITEM_AREA", 5),
    )
    nearest: tuple[int, str, int] | None = None
    for pattern, semantic, score in labels:
        for label_match in pattern.finditer(before):
            candidate = (label_match.end(), semantic, score)
            if nearest is None or candidate[0] > nearest[0]:
                nearest = candidate
    if nearest and match.start() - max(0, match.start() - 140) - nearest[0] <= 70:
        semantic, score = nearest[1], nearest[2]
        if semantic == "GFA" and re.search(r"(?i)(total|gross|연면적)", before[nearest[0] - 30:]):
            score += 5
        return semantic, score, local
    semantic, score = classify_area_context(local)
    return semantic, score, local


def area_observations(evidence_rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for row in evidence_rows:
        text = clean(row["evidence_text"])
        matches = list(AREA_RE.finditer(text))
        if not matches:
            matches = list(AREA_RE.finditer(clean(row["area_mentions"])))
            source_text = clean(row["area_mentions"])
        else:
            source_text = text
        for match in matches:
            value = normalize_area_number(match.group("value"))
            if value is None:
                continue
            semantic, score, context = classify_area_match(source_text, match)
            if value < 20 and semantic not in {"GFA", "BUILDING_OR_CONSTRUCTION_AREA"}:
                semantic, score = "WORK_ITEM_AREA", min(score, 5)
            key = (value, semantic, row["source_file"], row["source_locator"])
            if key in seen:
                continue
            seen.add(key)
            observations.append(
                {
                    "value": value,
                    "semantic": semantic,
                    "score": score,
                    "source_file": clean(row["source_file"]),
                    "source_locator": clean(row["source_locator"]),
                    "quote": context[:300],
                }
            )
    observations.sort(key=lambda item: (item["score"], item["value"]), reverse=True)
    return observations


def normalize_cost_stage(value: str) -> str:
    text = clean(value)
    if "입찰 집행한도" in text:
        return "NOTICE_EXECUTION_CEILING"
    if "Construction Budget" in text or "Project Budget" in text:
        return "CONSTRUCTION_BUDGET"
    if any(term in text for term in ("추정공사비", "공사비 예산", "설계입찰 단계", "예비조사", "심층기획", "ToR")):
        return "DESIGN_ESTIMATE"
    if "추정예산" in text:
        return "ADVERTISED_ESTIMATED_BUDGET"
    if "직접 제시 계획단가" in text:
        return "DIRECT_UNIT_RATE_ONLY"
    return "OTHER_PLANNING_AMOUNT"


def classify_scope_role(bid_no: str, contract_type: str, title: str) -> str:
    if bid_no == "L2022-00034-1":
        return "WORKS"
    if bid_no == "L2024-00076-1":
        return "DESIGN_SERVICE"
    if bid_no in HISTORICAL_NONBUILDING_X or bid_no in RECENT_SCOPE_NO_WORKS - {"L2025-00056-1"}:
        return "NONBUILDING_OR_FALSE_AREA"
    if contract_type == "물품":
        return "GOODS"
    if bid_no in HISTORICAL_SERVICE_X:
        return "DESIGN_OR_SUPERVISION_SERVICE"
    if bid_no == "L2019-00046-1":
        return "MIXED_FITOUT_WORKS"
    if contract_type == "공사":
        if DESIGN_SERVICE_RE.search(title) and not WORKS_TITLE_RE.search(title):
            return "DESIGN_OR_SUPERVISION_SERVICE"
        if re.search(r"설계\s*[·및/]?\s*시공|설계시공", title):
            return "DESIGN_BUILD_WORKS"
        return "WORKS"
    if WORKS_TITLE_RE.search(title) and not DESIGN_SERVICE_RE.search(title):
        return "WORKS"
    if DESIGN_SERVICE_RE.search(title):
        return "DESIGN_OR_SUPERVISION_SERVICE"
    return "OTHER_SERVICE"


def is_cost_scope_usable(role: str) -> bool:
    return role in {"WORKS", "DESIGN_BUILD_WORKS"}


def source_file_path(root: Path, dataset_id: str, source_file: str) -> Path | None:
    base = root / ("data" if dataset_id == "2021-2025" else "data_2016_2020")
    for folder in ("unpacked", "raw"):
        path = base / folder / source_file
        if path.exists() and path.is_file():
            return path
    return None


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_manifest(root: Path, dataset_id: str, name: str) -> Any:
    base = root / ("data" if dataset_id == "2021-2025" else "data_2016_2020") / "manifests"
    return json.loads((base / name).read_text())


def candidate_query() -> str:
    return """
    WITH candidates AS (
      SELECT DISTINCT b.bid_no
      FROM bids b
      JOIN projects p ON p.bid_no=b.bid_no
      JOIN evidence e ON e.bid_no=b.bid_no
      WHERE b.construction_candidate=1
        AND e.category='연면적·면적'
        AND (
          trim(coalesce(p.ceiling_usd_raw,''))<>'' OR
          trim(coalesce(p.ceiling_krw_raw,''))<>''
        )
    )
    SELECT
      b.bid_no, b.bid_base_no, b.dataset_id, b.title, b.notice_date,
      b.contract_type, b.contract_method, b.order_no,
      p.project_no, p.country_ko, p.country_en, p.project_name,
      p.facility_type, p.work_type, p.ceiling_usd_raw, p.ceiling_krw_raw,
      p.detail_url
    FROM candidates c
    JOIN bids b ON b.bid_no=c.bid_no
    JOIN projects p ON p.bid_no=b.bid_no
    ORDER BY b.notice_date, b.bid_no
    """


def select_area(
    bid_no: str,
    dataset_id: str,
    reviewed: sqlite3.Row | None,
    evidence_rows: list[sqlite3.Row],
) -> dict[str, Any]:
    observations = area_observations(evidence_rows)
    best = observations[0] if observations else None
    override = AREA_MANUAL_OVERRIDES.get(bid_no)
    if override:
        return {
            "selected_area_m2": override["value"],
            "area_semantics": override["semantic"],
            "area_aggregation": override["aggregation"],
            "area_confidence": "MANUAL_CONTEXT_REVIEW",
            "area_source_file": override["file"],
            "area_source_locator": override["locator"],
            "area_quote": override["quote"],
            "area_candidates": ";".join(
                f"{item['value']:g}:{item['semantic']}" for item in observations[:12]
            ),
        }
    if reviewed is not None and reviewed["gross_floor_area_m2"]:
        basis = clean(reviewed["area_basis"])
        if any(term in basis for term in ("캠퍼스", "시설 면적", "동별 면적", "대상 시설")):
            semantic = "FACILITY_OR_CAMPUS_AREA"
        elif "연면적" in basis or "공간계획" in basis:
            semantic = "GFA"
        else:
            semantic = "GFA_OR_CURATED_AREA"
        return {
            "selected_area_m2": float(reviewed["gross_floor_area_m2"]),
            "area_semantics": semantic,
            "area_aggregation": "SUM_OR_MULTI" if any(term in basis for term in ("합계", "2개", "3개", "5개")) else "SINGLE_OR_TOTAL",
            "area_confidence": "MANUAL_CURATED",
            "area_source_file": clean(reviewed["source_file"]),
            "area_source_locator": clean(reviewed["source_locator"]),
            "area_quote": clean(reviewed["evidence_summary"])[:300],
            "area_candidates": ";".join(
                f"{item['value']:g}:{item['semantic']}" for item in observations[:12]
            ),
        }

    semantic_override = None
    if dataset_id == "2021-2025":
        if bid_no in RECENT_AREA_SITE:
            semantic_override = "SITE_OR_FOOTPRINT_ONLY"
        elif bid_no in RECENT_AREA_QUALIFICATION:
            semantic_override = "QUALIFICATION_OR_OTHER_PROJECT"
        elif bid_no in RECENT_AREA_AMBIGUOUS:
            semantic_override = "AMBIGUOUS_OR_WORK_ITEM"
    if bid_no in HISTORICAL_NONBUILDING_X or bid_no == "L2019-00044-1":
        semantic_override = "FALSE_POSITIVE_OR_WORK_ITEM"

    if semantic_override:
        return {
            "selected_area_m2": None,
            "area_semantics": semantic_override,
            "area_aggregation": "NOT_APPLICABLE",
            "area_confidence": "MANUAL_REJECTED",
            "area_source_file": best["source_file"] if best else "",
            "area_source_locator": best["source_locator"] if best else "",
            "area_quote": clean((HISTORICAL_NOTICE_NOTES | RECENT_NOTICE_NOTES).get(bid_no, best["quote"] if best else ""))[:300],
            "area_candidates": ";".join(
                f"{item['value']:g}:{item['semantic']}" for item in observations[:12]
            ),
        }

    if not best or best["semantic"] in {"SITE_AREA", "QUALIFICATION", "WORK_ITEM_AREA", "AMBIGUOUS_AREA"}:
        return {
            "selected_area_m2": None,
            "area_semantics": best["semantic"] if best else "NO_PARSEABLE_AREA",
            "area_aggregation": "UNKNOWN",
            "area_confidence": "LOW",
            "area_source_file": best["source_file"] if best else "",
            "area_source_locator": best["source_locator"] if best else "",
            "area_quote": best["quote"] if best else "",
            "area_candidates": ";".join(
                f"{item['value']:g}:{item['semantic']}" for item in observations[:12]
            ),
        }
    return {
        "selected_area_m2": best["value"],
        "area_semantics": best["semantic"],
        "area_aggregation": "AUTO_SELECTED_SINGLE_OR_TOTAL",
        "area_confidence": "AUTO_HIGH" if best["score"] >= 100 else "AUTO_MEDIUM",
        "area_source_file": best["source_file"],
        "area_source_locator": best["source_locator"],
        "area_quote": best["quote"][:300],
        "area_candidates": ";".join(
            f"{item['value']:g}:{item['semantic']}" for item in observations[:12]
        ),
    }


def select_cost(
    bid_no: str,
    role: str,
    notice_ceiling: float | None,
    reviewed: sqlite3.Row | None,
) -> dict[str, Any]:
    base = BASIC_PRICE_EVIDENCE.get(bid_no)
    if base:
        return {
            "selected_construction_cost_usd": base["amount"],
            "amount_stage": base["stage"],
            "amount_scope": "BUILDING_WORKS_OR_DESIGN_BUILD",
            "tax_basis": base.get("tax", "UNKNOWN"),
            "contingency_note": base.get("contingency", ""),
            "amount_source_file": base["file"],
            "amount_source_locator": base["locator"],
            "amount_quote": base["quote"],
            "amount_confidence": "MANUAL_SOURCE_VERIFIED",
        }

    if reviewed is not None and reviewed["cost_usd_nominal"] and reviewed["gross_floor_area_m2"]:
        stage = normalize_cost_stage(reviewed["cost_stage"])
        # A reviewed design/supervision notice may hold a source-verified
        # construction budget inside the attachment; its notice ceiling remains
        # separately visible and is not treated as construction cost.
        if is_cost_scope_usable(role) or stage in {
            "CONSTRUCTION_BUDGET",
            "DESIGN_ESTIMATE",
            "ADVERTISED_ESTIMATED_BUDGET",
        }:
            return {
                "selected_construction_cost_usd": float(reviewed["cost_usd_nominal"]),
                "amount_stage": stage,
                "amount_scope": "BUILDING_WORKS_OR_CURATED_CONSTRUCTION_BUDGET",
                "tax_basis": "SEE_SOURCE",
                "contingency_note": clean(reviewed["scope_caution"]),
                "amount_source_file": clean(reviewed["source_file"]),
                "amount_source_locator": clean(reviewed["source_locator"]),
                "amount_quote": clean(reviewed["evidence_summary"])[:300],
                "amount_confidence": "MANUAL_CURATED",
            }

    if is_cost_scope_usable(role) and notice_ceiling:
        return {
            "selected_construction_cost_usd": notice_ceiling,
            "amount_stage": "NOTICE_EXECUTION_CEILING",
            "amount_scope": "PROCUREMENT_CEILING_ASSUMED_WORKS",
            "tax_basis": "UNKNOWN",
            "contingency_note": "",
            "amount_source_file": "KOICA 입찰 상세페이지",
            "amount_source_locator": "집행한도금액(달러)",
            "amount_quote": "",
            "amount_confidence": "METADATA_PLUS_SCOPE_REVIEW",
        }

    return {
        "selected_construction_cost_usd": None,
        "amount_stage": "SERVICE_OR_GOODS_CEILING" if notice_ceiling else "NO_USABLE_CONSTRUCTION_AMOUNT",
        "amount_scope": role,
        "tax_basis": "NOT_APPLICABLE",
        "contingency_note": "",
        "amount_source_file": "KOICA 입찰 상세페이지" if notice_ceiling else "",
        "amount_source_locator": "집행한도금액(달러)" if notice_ceiling else "",
        "amount_quote": "",
        "amount_confidence": "SCOPE_REJECTED" if notice_ceiling else "NONE",
    }


def notice_scope_status(bid_no: str, dataset_id: str, role: str) -> str:
    if dataset_id == "2016-2020":
        if bid_no in HISTORICAL_C_NOTICES:
            return "MATCH"
        if bid_no == "L2019-00046-1":
            return "PARTIAL_MIXED_COST"
        return "NO_MATCH"
    if role in {"DESIGN_SERVICE", "DESIGN_OR_SUPERVISION_SERVICE", "OTHER_SERVICE", "GOODS"}:
        return "NO_MATCH"
    if bid_no in RECENT_SCOPE_PARTIAL:
        return "PARTIAL_SCOPE"
    if bid_no in RECENT_SCOPE_NO_WORKS:
        return "NO_MATCH"
    return "MATCH"


def evidence_scope_status(
    record_scope_status: str,
    role: str,
    area: dict[str, Any],
    cost: dict[str, Any],
    reviewed: sqlite3.Row | None,
) -> str:
    """Allow a service notice to contribute a separate construction budget.

    The notice contract ceiling remains a service fee (`record_scope_status` is
    NO_MATCH).  A manually curated design/CM attachment may nevertheless contain
    a project construction estimate that matches its GFA.  Keeping the two
    statuses separate prevents the service fee itself from being mislabeled.
    """

    if record_scope_status != "NO_MATCH":
        return record_scope_status
    if (
        role in {"DESIGN_SERVICE", "DESIGN_OR_SUPERVISION_SERVICE", "OTHER_SERVICE"}
        and reviewed is not None
        and area["selected_area_m2"]
        and cost["selected_construction_cost_usd"]
        and cost["amount_stage"] in {
            "CONSTRUCTION_BUDGET",
            "DESIGN_ESTIMATE",
            "ADVERTISED_ESTIMATED_BUDGET",
        }
    ):
        caution = clean(reviewed["scope_caution"])
        if any(term in caution for term in ("원문 재확인", "해석", "약식값", "다른 단계", "부분")):
            return "PARTIAL_ATTACHMENT_CONSTRUCTION_BUDGET"
        return "MATCH_ATTACHMENT_CONSTRUCTION_BUDGET"
    return record_scope_status


def final_notice_grade(
    bid_no: str,
    role: str,
    scope_status: str,
    area: dict[str, Any],
    cost: dict[str, Any],
    reviewed: sqlite3.Row | None,
) -> tuple[str, str, str]:
    strict = STRICT_NOTICE_REVIEWS.get(bid_no)
    if strict:
        display = strict["grade"] + ("-부분" if strict["scope"] != "FULL" else "")
        return display, "V3_ORIGINAL_MANUAL", strict["detail"]

    if role in {"GOODS", "NONBUILDING_OR_FALSE_AREA"}:
        return "X", "V3_SCOPE_REVIEW", "물품·비건축 또는 GFA 오탐으로 건축공사비 표본 제외"
    if role in {"DESIGN_SERVICE", "DESIGN_OR_SUPERVISION_SERVICE", "OTHER_SERVICE"} and not cost["selected_construction_cost_usd"]:
        return "X", "V3_SCOPE_REVIEW", "설계·감리·기타 용역 집행한도는 건축공사비가 아님"
    if scope_status.startswith("PARTIAL") and (
        not area["selected_area_m2"] or not cost["selected_construction_cost_usd"]
    ):
        return "U", "V3_SCOPE_REVIEW", "면적과 금액 범위가 부분·혼합되어 계산 금지"
    if scope_status == "NO_MATCH":
        if role in {"WORKS", "DESIGN_BUILD_WORKS", "MIXED_FITOUT_WORKS"}:
            return "U", "V3_SCOPE_REVIEW", "공사 후보이나 유효 GFA 또는 같은 범위 금액이 없음"
        return "X", "V3_SCOPE_REVIEW", "건축공사비 표본 범위 아님"
    if area["selected_area_m2"] and cost["selected_construction_cost_usd"]:
        partial = "-부분" if scope_status.startswith("PARTIAL") else ""
        if reviewed is not None:
            return f"C{partial}", "V3_CURATED_AREA_COST_RECHECK", "동일/제한 범위 공사금액÷면적 스크리닝 근거"
        return f"C?{partial}", "V2R_HUMAN_REVIEWED_EXTRACTION", "범위 일치 잠정확인; 원본 V3 확인 전 직접 사용 금지"
    return "U", "V2R_HUMAN_REVIEWED_EXTRACTION", "유효 면적과 공사금액 결합요건 미충족"


def grade_rank(value: str) -> int:
    if value.startswith("A"):
        return 6
    if value.startswith("B"):
        return 5
    if value.startswith("C") and "?" not in value:
        return 4
    if value.startswith("C?"):
        return 3
    if value.startswith("U"):
        return 2
    return 1


def compact_grade(value: str) -> str:
    if value.startswith("A"):
        return "A"
    if value.startswith("B"):
        return "B"
    if value.startswith("C?"):
        return "C?"
    if value.startswith("C"):
        return "C"
    if value.startswith("U"):
        return "U"
    return "X"


def attachment_audit(
    root: Path,
    candidate_rows: list[dict[str, Any]],
    output_dir: Path,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, int]], dict[str, Any]]:
    candidate_bids = {row["bid_no"] for row in candidate_rows}
    existing = read_csv(root / "outputs/koica-candidate-grading/KOICA_건축후보_첨부검사.csv")
    existing_by_key = {(row["bid_no"], row["source_file"]): row for row in existing}
    detail_by_bid = {row["bid_no"]: row for row in candidate_rows}

    indexed: list[dict[str, Any]] = []
    for dataset_id in ("2016-2020", "2021-2025"):
        for row in load_manifest(root, dataset_id, "file_index.json"):
            if row.get("bid_no") in candidate_bids:
                indexed.append({**row, "dataset_id": dataset_id})

    scan_rows: list[dict[str, Any]] = []
    scan_cache: dict[str, dict[str, Any]] = {}
    newly_scanned = 0
    reused_existing = 0
    for indexed_row in indexed:
        bid_no = indexed_row["bid_no"]
        source_file = indexed_row["source_file"]
        extension = indexed_row.get("extension", Path(source_file).suffix.lower())
        key = (bid_no, source_file)
        previous = existing_by_key.get(key)
        path = source_file_path(root, indexed_row["dataset_id"], source_file)
        digest = clean(previous.get("sha256")) if previous else ""
        if not digest and path:
            digest = sha256(path)
        scan = {
            "scan_error": "",
            "table_count": 0,
            "quantity_rows_max": 0,
            "priced_rows_max": 0,
            "strong_priced_table": 0,
            "best_sheet": "",
            "best_sheet_state": "",
            "best_header_row": "",
            "best_priced_ratio": 0.0,
        }
        if extension in SPREADSHEET_EXTENSIONS:
            if previous:
                reused_existing += 1
                for field in scan:
                    value: Any = previous.get(field, "")
                    if field in {"table_count", "quantity_rows_max", "priced_rows_max", "strong_priced_table", "best_header_row"}:
                        try:
                            value = int(float(value or 0))
                        except ValueError:
                            value = 0
                    elif field == "best_priced_ratio":
                        try:
                            value = float(value or 0)
                        except ValueError:
                            value = 0.0
                    scan[field] = value
            elif path:
                if digest not in scan_cache:
                    scan_cache[digest] = scan_spreadsheet(path)
                    newly_scanned += 1
                raw_scan = scan_cache[digest]
                scan.update({field: raw_scan.get(field, scan[field]) for field in scan})
            else:
                scan["scan_error"] = "파일경로 미확인"
        row = {
            "dataset_id": indexed_row["dataset_id"],
            "project_no": detail_by_bid[bid_no]["project_no"],
            "bid_no": bid_no,
            "scope_role": detail_by_bid[bid_no]["scope_role"],
            "source_file": source_file,
            "extension": extension,
            "bytes": indexed_row.get("bytes", 0),
            "sha256": digest,
            "boq_filename_candidate": int(bool(BOQ_FILE_RE.search(source_file))),
            "blank_or_unpriced_filename": int(bool(BLANK_FILE_RE.search(source_file))),
            **scan,
        }
        if row["strong_priced_table"]:
            row["provisional_file_signal"] = "A?"
        elif int(row["quantity_rows_max"] or 0) >= 3:
            row["provisional_file_signal"] = "B?"
        elif row["boq_filename_candidate"]:
            row["provisional_file_signal"] = "BOQ_NAME_ONLY"
        else:
            row["provisional_file_signal"] = "NONE"
        row["final_grade_rule"] = "자동 표 신호는 최종 A/B로 승격하지 않음"
        scan_rows.append(row)

    by_bid: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in scan_rows:
        stats = by_bid[row["bid_no"]]
        stats["indexed_attachment_count"] += 1
        stats["spreadsheet_count"] += int(row["extension"] in SPREADSHEET_EXTENSIONS)
        stats["boq_named_file_count"] += int(row["boq_filename_candidate"])
        stats["quantity_table_file_count"] += int(int(row["quantity_rows_max"] or 0) >= 3)
        stats["priced_table_file_count"] += int(bool(row["strong_priced_table"]))
        stats["scan_error_file_count"] += int(bool(row["scan_error"]))

    signal_rows = [
        row for row in scan_rows
        if row["extension"] in SPREADSHEET_EXTENSIONS or row["boq_filename_candidate"]
    ]
    write_csv(output_dir / "KOICA_170공고_첨부표탐색.csv", signal_rows)
    summary = {
        "indexed_attachment_rows": len(scan_rows),
        "candidate_bids_with_indexed_attachments": len({row["bid_no"] for row in scan_rows}),
        "spreadsheet_rows": sum(row["extension"] in SPREADSHEET_EXTENSIONS for row in scan_rows),
        "reused_previous_spreadsheet_scans": reused_existing,
        "new_unique_spreadsheet_scans": newly_scanned,
        "boq_named_file_rows": sum(row["boq_filename_candidate"] for row in scan_rows),
        "quantity_table_signal_rows": sum(int(row["quantity_rows_max"] or 0) >= 3 for row in scan_rows),
        "priced_table_signal_rows": sum(bool(row["strong_priced_table"]) for row in scan_rows),
        "warning": "자동 표 신호는 상품표·인력투입표 등을 포함할 수 있어 최종 A/B로 승격하지 않음",
    }
    return signal_rows, by_bid, summary


def run(root: Path, db_path: Path, output_dir: Path) -> dict[str, Any]:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    source_rows = list(connection.execute(candidate_query()))
    if len(source_rows) != 170:
        raise RuntimeError(f"expected 170 candidate notices, found {len(source_rows)}")
    if len({row["bid_no"] for row in source_rows}) != 170:
        raise RuntimeError("candidate bid numbers are not unique")
    if len({row["project_no"] for row in source_rows}) != 91:
        raise RuntimeError("expected 91 project numbers")

    evidence_by_bid: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in connection.execute(
        "SELECT * FROM evidence WHERE category='연면적·면적' ORDER BY bid_no, source_file, source_locator"
    ):
        evidence_by_bid[row["bid_no"]].append(row)
    reviewed_by_bid = {
        row["bid_no"]: row for row in connection.execute("SELECT * FROM reviewed_cases")
    }

    notice_rows: list[dict[str, Any]] = []
    for source in source_rows:
        bid_no = source["bid_no"]
        project_no = clean(source["project_no"])
        title = clean(source["title"])
        role = classify_scope_role(bid_no, clean(source["contract_type"]), title)
        reviewed = reviewed_by_bid.get(bid_no)
        notice_ceiling = parse_amount(source["ceiling_usd_raw"])
        area = select_area(
            bid_no,
            source["dataset_id"],
            reviewed,
            evidence_by_bid.get(bid_no, []),
        )
        cost = select_cost(bid_no, role, notice_ceiling, reviewed)
        record_scope_status = notice_scope_status(bid_no, source["dataset_id"], role)
        scope_status = evidence_scope_status(
            record_scope_status, role, area, cost, reviewed
        )
        grade, verification, detail = final_notice_grade(
            bid_no, role, scope_status, area, cost, reviewed
        )
        area_value = area["selected_area_m2"]
        cost_value = cost["selected_construction_cost_usd"]
        screening_unit = cost_value / area_value if cost_value and area_value else None
        price_stage_gap = (
            (notice_ceiling / cost_value - 1.0) * 100.0
            if notice_ceiling
            and cost_value
            and is_cost_scope_usable(role)
            and cost["amount_stage"] != "NOTICE_EXECUTION_CEILING"
            else None
        )
        note = clean(
            (HISTORICAL_NOTICE_NOTES | RECENT_NOTICE_NOTES).get(bid_no, "")
        )
        country = COUNTRY_CORRECTIONS.get(project_no, clean(source["country_ko"]))
        row = {
            "audit_no": len(notice_rows) + 1,
            "dataset_id": source["dataset_id"],
            "project_no": project_no,
            "bid_no": bid_no,
            "bid_base_no": clean(source["bid_base_no"]),
            "package_id": f"{project_no}::{clean(source['bid_base_no']) or bid_no}",
            "notice_date": clean(source["notice_date"]),
            "country_ko": country,
            "stored_country_ko": clean(source["country_ko"]),
            "title": title,
            "stored_contract_type": clean(source["contract_type"]),
            "scope_role": role,
            "facility_type": clean(source["facility_type"]),
            "work_type": clean(source["work_type"]),
            "notice_ceiling_usd": notice_ceiling,
            "notice_ceiling_krw_raw": clean(source["ceiling_krw_raw"]),
            "notice_ceiling_usd_raw": clean(source["ceiling_usd_raw"]),
            **area,
            **cost,
            "record_cost_semantics": (
                "WORKS_CEILING" if role in {"WORKS", "DESIGN_BUILD_WORKS", "NONBUILDING_OR_FALSE_AREA"}
                else "GOODS_CEILING" if role == "GOODS"
                else "SERVICE_FEE_OR_MIXED"
            ),
            "record_scope_status": record_scope_status,
            "same_scope_status": scope_status,
            "screening_unit_usd_m2": screening_unit,
            "notice_ceiling_to_selected_gap_pct": price_stage_gap,
            "realized_price_available": "NO",
            "final_grade": grade,
            "compact_grade": compact_grade(grade),
            "verification_level": verification,
            "grade_detail": detail,
            "manual_note": note,
            "legacy_reviewed_case": int(reviewed is not None),
            "legacy_evidence_grade": clean(reviewed["evidence_grade"]) if reviewed else "",
            "legacy_cost_stage": clean(reviewed["cost_stage"]) if reviewed else "",
            "legacy_grade_not_inherited": "YES" if reviewed else "",
            "strict_attachment_review": int(bid_no in STRICT_NOTICE_REVIEWS),
            "unit_cost_allowed_use": (
                "품목·검증범위 산정" if grade == "A" else
                "검증된 부분 Bill만" if grade.startswith("A-") else
                "현지단가 결합 수량모델" if grade.startswith("B") else
                "초기 스크리닝만" if grade.startswith("C") else
                "계산 금지"
            ),
            "direct_future_estimate_ready": int(grade == "A"),
            "sample_weight_notice": 0,
            "source_url": clean(source["detail_url"]),
            "grade_system_version": GRADE_SYSTEM,
            "audit_date": AUDIT_DATE,
        }
        notice_rows.append(row)

    output_dir.mkdir(parents=True, exist_ok=True)
    attachment_rows, attachment_by_bid, attachment_summary = attachment_audit(
        root, notice_rows, output_dir
    )
    for row in notice_rows:
        stats = attachment_by_bid.get(row["bid_no"], {})
        for field in (
            "indexed_attachment_count",
            "spreadsheet_count",
            "boq_named_file_count",
            "quantity_table_file_count",
            "priced_table_file_count",
            "scan_error_file_count",
        ):
            row[field] = int(stats.get(field, 0))

    by_base: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_project: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in notice_rows:
        by_base[row["bid_base_no"] or row["bid_no"]].append(row)
        by_project[row["project_no"]].append(row)
    if len(by_base) != 154:
        raise RuntimeError(f"expected 154 bid-base groups, found {len(by_base)}")

    group_rows: list[dict[str, Any]] = []
    representative_bids: set[str] = set()
    for base_no, rows in by_base.items():
        representative = max(
            rows,
            key=lambda row: (grade_rank(row["final_grade"]), row["notice_date"], row["bid_no"]),
        )
        representative_bids.add(representative["bid_no"])
        group_rows.append(
            {
                "bid_base_no": base_no,
                "project_no": representative["project_no"],
                "country_ko": representative["country_ko"],
                "notice_count": len(rows),
                "bid_nos": ";".join(row["bid_no"] for row in rows),
                "representative_bid_no": representative["bid_no"],
                "latest_notice_date": max(row["notice_date"] for row in rows),
                "representative_title": representative["title"],
                "best_grade": representative["final_grade"],
                "scope_role": representative["scope_role"],
                "same_scope_status": representative["same_scope_status"],
                "area_m2": representative["selected_area_m2"],
                "construction_cost_usd": representative["selected_construction_cost_usd"],
                "screening_unit_usd_m2": representative["screening_unit_usd_m2"],
                "duplicate_rule": "동일 bid_base_no는 재공고군; 다른 base의 의미중복은 project sheet에서 별도 주의",
            }
        )
    group_rows.sort(key=lambda row: (row["project_no"], row["bid_base_no"]))
    for row in notice_rows:
        row["is_bid_base_representative"] = int(row["bid_no"] in representative_bids)

    project_rows: list[dict[str, Any]] = []
    project_representatives: set[str] = set()
    for project_no, rows in by_project.items():
        representative = max(
            rows,
            key=lambda row: (
                grade_rank(row["final_grade"]),
                row["same_scope_status"] == "MATCH",
                row["verification_level"].startswith("V3"),
                row["notice_date"],
                row["bid_no"],
            ),
        )
        project_representatives.add(representative["bid_no"])
        valid_rows = [row for row in rows if compact_grade(row["final_grade"]) in {"A", "B", "C", "C?"}]
        related = RELATED_OTHER_PACKAGE_EVIDENCE.get(project_no, {})
        project_rows.append(
            {
                "project_no": project_no,
                "country_ko": representative["country_ko"],
                "project_name": max((row["title"] for row in rows), key=len, default=""),
                "notice_count": len(rows),
                "bid_base_group_count": len({row["bid_base_no"] or row["bid_no"] for row in rows}),
                "valid_area_cost_notice_count": len(valid_rows),
                "valid_bid_nos": ";".join(row["bid_no"] for row in valid_rows),
                "all_bid_nos": ";".join(row["bid_no"] for row in rows),
                "display_representative_bid": representative["bid_no"],
                "technical_evidence_bid": (
                    representative["bid_no"] if representative["final_grade"].startswith(("A", "B")) else ""
                ),
                "price_evidence_bid": representative["bid_no"] if representative["selected_construction_cost_usd"] else "",
                "best_grade": representative["final_grade"],
                "compact_grade": compact_grade(representative["final_grade"]),
                "verification_level": representative["verification_level"],
                "scope_status": representative["same_scope_status"],
                "representative_area_m2": representative["selected_area_m2"],
                "representative_construction_cost_usd": representative["selected_construction_cost_usd"],
                "representative_amount_stage": representative["amount_stage"],
                "screening_unit_usd_m2": representative["screening_unit_usd_m2"],
                "unit_cost_allowed_use": representative["unit_cost_allowed_use"],
                "direct_future_estimate_ready": representative["direct_future_estimate_ready"],
                "screening_sample_weight": int(bool(valid_rows)),
                "direct_estimate_sample_weight": int(representative["final_grade"] == "A"),
                "related_other_package_grade": related.get("grade", ""),
                "related_other_package_bid": related.get("bid_no", ""),
                "related_other_package_note": related.get("detail", ""),
                "duplicate_and_scope_warning": (
                    "project_no 안에 서로 다른 시설·Lot·설계·감리·공사 패키지가 있을 수 있어 1개 비용행으로 합산 금지"
                    if len(rows) > 1 else ""
                ),
                "grade_detail": representative["grade_detail"],
                "source_url": representative["source_url"],
                "grade_system_version": GRADE_SYSTEM,
                "audit_date": AUDIT_DATE,
            }
        )
    project_rows.sort(key=lambda row: (row["country_ko"], -grade_rank(row["best_grade"]), row["project_no"]))
    if len(project_rows) != 91:
        raise RuntimeError(f"expected 91 projects, found {len(project_rows)}")
    for row in notice_rows:
        row["is_project_display_representative"] = int(row["bid_no"] in project_representatives)
        row["sample_weight_notice"] = int(row["bid_no"] in project_representatives and compact_grade(row["final_grade"]) in {"A", "B", "C", "C?"})

    legacy_crosswalk: list[dict[str, Any]] = []
    notice_by_bid = {row["bid_no"]: row for row in notice_rows}
    project_by_no = {row["project_no"]: row for row in project_rows}
    for bid_no, legacy in sorted(reviewed_by_bid.items()):
        final = notice_by_bid.get(bid_no)
        if not final:
            continue
        legacy_crosswalk.append(
            {
                "bid_no": bid_no,
                "project_no": final["project_no"],
                "legacy_evidence_grade": clean(legacy["evidence_grade"]),
                "legacy_area_m2": legacy["gross_floor_area_m2"],
                "legacy_cost_usd": legacy["cost_usd_nominal"],
                "legacy_cost_stage": clean(legacy["cost_stage"]),
                "legacy_recommended_unit_rate": clean(legacy["recommended_unit_rate"]),
                "new_notice_grade": final["final_grade"],
                "new_project_grade": project_by_no[final["project_no"]]["best_grade"],
                "new_scope_status": final["same_scope_status"],
                "mapping_method": "exact_bid_no",
                "discrepancy_rule": "legacy A/B/C는 비교가능성 등급이라 새 A/B/C로 승계하지 않음",
            }
        )

    candidate127 = read_csv(root / "outputs/koica-candidate-grading/KOICA_건축후보_127건_등급.csv")
    crosswalk127: list[dict[str, Any]] = []
    for source in candidate127:
        project_no = clean(source.get("project_no_effective"))
        linked_bids = {bid for bid in clean(source.get("linked_bid_nos")).split(";") if bid}
        exact = sorted(linked_bids & set(notice_by_bid))
        final_project = project_by_no.get(project_no)
        crosswalk127.append(
            {
                "source_record_id": source.get("source_record_id", ""),
                "project_no_effective": project_no,
                "country_ko": source.get("country_ko", ""),
                "record_title": source.get("record_title", ""),
                "old_record_cost_status": source.get("record_cost_status", ""),
                "old_project_technical_status": source.get("project_technical_status", ""),
                "in_170_universe": int(bool(exact)),
                "exact_bid_overlap": ";".join(exact),
                "new_project_grade": final_project["best_grade"] if final_project else "",
                "mapping_method": "exact_bid_no_or_exact_project_no" if final_project else "not_mapped",
                "warning": "127 공식 원기록과 170 공고는 서로 다른 모집단",
            }
        )

    notice_rows.sort(key=lambda row: (row["notice_date"], row["bid_no"]))
    write_csv(output_dir / "KOICA_면적금액_170공고_재검토.csv", notice_rows)
    write_csv(output_dir / "KOICA_면적금액_154공고군_재검토.csv", group_rows)
    write_csv(output_dir / "KOICA_면적금액_91사업_재검토.csv", project_rows)
    write_csv(output_dir / "KOICA_기존66_새등급_교차검증.csv", legacy_crosswalk)
    write_csv(output_dir / "KOICA_기존127_새모집단_교차검증.csv", crosswalk127)

    notice_grade_counts = Counter(row["compact_grade"] for row in notice_rows)
    project_grade_counts = Counter(row["compact_grade"] for row in project_rows)
    scope_counts = Counter(row["same_scope_status"] for row in notice_rows)
    record_scope_counts = Counter(row["record_scope_status"] for row in notice_rows)
    recent_rows = [row for row in notice_rows if row["dataset_id"] == "2021-2025"]
    recent_role_counts = Counter(
        "works" if row["scope_role"] in {"WORKS", "DESIGN_BUILD_WORKS", "NONBUILDING_OR_FALSE_AREA"}
        else "goods" if row["scope_role"] == "GOODS"
        else "service_or_other"
        for row in recent_rows
    )
    summary = {
        "schema_version": "2.0.0",
        "grade_system_version": GRADE_SYSTEM,
        "audit_date": AUDIT_DATE,
        "universe": {
            "candidate_rule": "construction_candidate=1 AND area evidence exists AND USD/KRW ceiling raw exists",
            "notice_rows": len(notice_rows),
            "unique_bid_nos": len({row["bid_no"] for row in notice_rows}),
            "bid_base_groups": len(group_rows),
            "project_rows": len(project_rows),
            "historical_notices": sum(row["dataset_id"] == "2016-2020" for row in notice_rows),
            "recent_notices": len(recent_rows),
            "legacy_reviewed66_overlap": len(legacy_crosswalk),
            "warning": "91 project_no는 91개 독립 비용표본이 아니며 서로 다른 package/Lot을 포함할 수 있음",
        },
        "notice_grade_counts": dict(sorted(notice_grade_counts.items())),
        "project_grade_counts": dict(sorted(project_grade_counts.items())),
        "scope_status_counts_all_170": dict(sorted(scope_counts.items())),
        "record_scope_status_counts_all_170": dict(sorted(record_scope_counts.items())),
        "recent_2021_2025_role_counts": dict(sorted(recent_role_counts.items())),
        "recent_2021_2025_record_scope_counts": dict(sorted(Counter(row["record_scope_status"] for row in recent_rows).items())),
        "historical_2016_2020_manual_result": {
            "C_scope_matched_notices": len(HISTORICAL_C_NOTICES),
            "mixed_or_unresolved_notices": 2,
            "excluded_service_or_nonbuilding_notices": len(HISTORICAL_SERVICE_X | HISTORICAL_NONBUILDING_X),
        },
        "strict_attachment_readiness": {
            "exact_notice_A_or_A_partial": sum(row["compact_grade"] == "A" for row in notice_rows),
            "exact_notice_B_or_B_partial": sum(row["compact_grade"] == "B" for row in notice_rows),
            "direct_future_estimate_ready_projects": sum(row["direct_future_estimate_ready"] for row in project_rows),
            "related_other_package_B_not_promoted": len(RELATED_OTHER_PACKAGE_EVIDENCE),
        },
        "price_stage_finding": {
            "contract_or_award_or_final_cost_rows": 0,
            "manually_preserved_basic_or_advertised_price_rows": len(BASIC_PRICE_EVIDENCE),
            "finding": "집행한도와 기초·광고예산은 대체로 약 2~3% 차이가 있어 병렬 보존",
        },
        "attachment_audit": attachment_summary,
        "grade_definitions": {
            "A": "V3 검증된 실제 사업 BOQ의 수량과 양수 단가/금액; 부분범위는 A-부분",
            "B": "V3 검증된 실제 사업 BOQ 수량, usable 단가 없음; 부분범위는 B-부분",
            "C": "수동 재검토된 동일/제한 범위 공사금액+면적; 초기 스크리닝 전용",
            "C?": "추출자료를 사람이 검토한 잠정 범위일치; 원본 V3 확인 전 직접 사용 금지",
            "U": "건축공사 후보이나 면적·금액 범위 결합요건 미충족",
            "X": "설계·감리·물품·비건축 또는 면적 오탐으로 제외",
        },
        "non_inheritance_rule": "reviewed_cases.evidence_grade와 기존 127 project grade는 새 등급으로 승계하지 않음",
        "allowed_use": {
            "A_full": "검증된 가격범위의 직접 BOQ 산정",
            "A_partial": "검증된 부분 Bill만; 전체사업 환산 금지",
            "B": "현지 단가를 결합할 수 있는 수량모델",
            "C": "명목 공사금액÷면적 스크리닝; 물가·환율·세금·범위 보정 전 미래 견적 금지",
            "C_question": "원본 수동검증 대기",
            "U_X": "계산 금지",
        },
    }
    (output_dir / "KOICA_면적금액_170공고_91사업_재검토_요약.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2)
    )
    (output_dir / "KOICA_면적금액_170공고_91사업_구조화.json").write_text(
        json.dumps(
            {
                "summary": summary,
                "notices": notice_rows,
                "bid_base_groups": group_rows,
                "projects": project_rows,
                "attachment_signals": attachment_rows,
                "crosswalk_reviewed66": legacy_crosswalk,
                "crosswalk_candidate127": crosswalk127,
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    readme = f"""# KOICA 면적·금액 170공고·91사업 전수 재검토

## 결론

- 모집단은 공고 170건, `bid_base_no` 공고군 154개, KOICA 사업번호 91개다.
- 91개 사업은 독립 비용표본 91개가 아니다. 한 사업에 설계·감리·공사, 여러 시설·Lot, 재공고가 함께 있을 수 있다.
- 과거 `reviewed_cases` 66건의 A/B/C는 새 산정준비도 등급으로 승계하지 않았다.
- 계약가·낙찰가·준공정산가는 현재 0건이다. 대부분 집행한도·기초금액·설계예산이므로 미래 견적에 직접 투입하면 안 된다.

## 등급

- **A**: 가격 있는 실제 사업 BOQ를 V3 수동검증. `A-부분`은 해당 Bill만 사용.
- **B**: 수량 있는 blank/unpriced BOQ를 V3 수동검증. 현지단가 결합 필요.
- **C**: 수동 재검토된 동일 또는 제한 범위의 공사금액+면적. 초기 스크리닝 전용.
- **C?**: 추출자료 기반 잠정 범위일치. 원본 V3 확인 전 직접 계산에 사용 금지.
- **U**: 건축 후보이나 면적·금액 범위 결합 불충분.
- **X**: 설계·감리·물품·비건축 또는 면적 오탐.

## 파일

- `KOICA_면적금액_170공고_재검토.csv`: 모든 공고, 면적·금액 단계·범위·등급·근거.
- `KOICA_면적금액_154공고군_재검토.csv`: 동일 `bid_base_no` 재공고군.
- `KOICA_면적금액_91사업_재검토.csv`: 사업별 대표 근거와 중복·패키지 경고.
- `KOICA_170공고_첨부표탐색.csv`: 첨부 1:N 표 신호. 자동 A?/B?는 최종 등급이 아니다.
- `KOICA_기존66_새등급_교차검증.csv`: 과거 등급 비승계 교차표.
- `KOICA_기존127_새모집단_교차검증.csv`: 서로 다른 두 모집단의 교차표.

## 핵심 안전장치

1. 공고 상세페이지 집행한도와 원문 기초·광고예산을 별도 필드로 보존한다.
2. 분자 금액과 분모 면적이 같은 시설·패키지·단계인지 `same_scope_status`로 확인한다.
3. 재공고는 `bid_base_no` 단위로 묶되, 다른 base라도 동일 패키지일 수 있으므로 사업 원문을 유지한다.
4. C 원단위는 명목 스크리닝일 뿐이며 현지단가·물가·환율·세금·외부공사 범위 보정 전 미래사업 견적값이 아니다.
5. 자동 표 검출은 상품표·감리 인력표를 BOQ로 오인할 수 있어 최종 A/B로 승격하지 않는다.
"""
    (output_dir / "README.md").write_text(readme)
    connection.close()
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    root = args.project_root.resolve()
    db_path = args.db if args.db.is_absolute() else root / args.db
    output_dir = args.output_dir if args.output_dir.is_absolute() else root / args.output_dir
    summary = run(root, db_path, output_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
