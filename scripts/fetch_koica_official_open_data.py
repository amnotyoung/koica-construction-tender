#!/usr/bin/env python3
"""Download and normalize three KOICA official open-data files.

The source pages are the Korean Public Data Portal records published by KOICA.
The portal's attachment identifiers change when a file is refreshed, so this
collector resolves the current ``contentUrl`` from each official dataset page
instead of hard-coding a stale attachment URL.

Raw bytes are kept under ``data/koica_official/raw``.  They are intentionally
ignored by Git in the same way as the existing tender attachments.  A
reproducibility manifest is written to ``data/manifests`` and UTF-8 normalized
CSV files are written to ``outputs/koica-official-open-data``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "koica_official" / "raw"
OUTPUT_DIR = ROOT / "outputs" / "koica-official-open-data"
MANIFEST_PATH = ROOT / "data" / "manifests" / "koica_official_open_data.json"
DB_PATH = (
    ROOT
    / "outputs"
    / "koica-construction-distribution"
    / "KOICA_건축사업_사례DB_2016-2025.sqlite"
)

USER_AGENT = (
    "Mozilla/5.0 (compatible; KOICA-construction-research/1.0; "
    "+https://www.data.go.kr/)"
)
PROJECT_NO_RE = re.compile(r"(?<![A-Z0-9])((?:19|20)\d{2}-\d{5})(?!\d)")
BID_NO_RE = re.compile(r"(?<![A-Z0-9])(L(?:19|20)\d{2}-\d{5}(?:-\d+)?)(?!\d)", re.I)
AREA_RE = re.compile(
    r"(?P<value>\d[\d,]*(?:\.\d+)?)\s*(?:m2|m²|㎡|제곱미터)",
    re.I,
)

STRONG_BUILDING_KEYWORDS = (
    "건축공사",
    "신축",
    "증축",
    "개축",
    "재건축",
    "리모델링",
    "리노베이션",
    "보수공사",
    "건립",
    "공간계획",
    "space program",
    "building construction",
    "renovation",
)
WEAK_CONSTRUCTION_KEYWORDS = (
    "시공",
    "공사",
    "토목공사",
    "구조공사",
    "전기공사",
    "기계공사",
    "construction",
)
BUILDING_ASSET_KEYWORDS = (
    "건물",
    "청사",
    "센터",
    "연수원",
    "훈련원",
    "교육원",
    "학교",
    "대학",
    "병원",
    "보건소",
    "실험실",
    "연구소",
    "연구센터",
    "기숙사",
    "강의동",
    "사무동",
    "도서관",
    "복지관",
    "공장",
    "공항",
    "시설",
    "laboratory",
    "hospital",
    "school",
    "building",
)
BUILDING_SERVICE_KEYWORDS = (
    "기본설계",
    "실시설계",
    "설계",
    "감리",
    "건설사업관리",
    "cm용역",
    "cm 용역",
    "설계검토",
    "architectural",
    "supervision",
)


@dataclass(frozen=True)
class Source:
    slug: str
    public_data_id: str
    dataset_name: str
    page_url: str
    required_columns: tuple[str, ...]
    normalized_filename: str


SOURCES = (
    Source(
        slug="annual_procurement_plan",
        public_data_id="15085055",
        dataset_name="한국국제협력단_대외무상원조사업 연간발주계획",
        page_url="https://www.data.go.kr/data/15085055/fileData.do",
        required_columns=(
            "번호",
            "사업담당부서",
            "수원국",
            "발주명",
            "분야",
            "입찰구분",
            "입찰범위",
            "입찰한도액(원)",
            "계약방법",
            "낙찰자선정방식",
            "발주예정시기",
        ),
        normalized_filename="KOICA_연간발주계획_정규화.csv",
    ),
    Source(
        slug="aid_procurement_contracts",
        public_data_id="15073135",
        dataset_name="한국국제협력단_원조조달사업 계약목록",
        page_url="https://www.data.go.kr/data/15073135/fileData.do",
        required_columns=(
            "번호",
            "계약번호",
            "차수",
            "신규여부",
            "계약명",
            "조달사업구분",
            "조달구분",
            "조달계약종류",
            "계약방법",
            "계약일자",
            "통화구분",
            "계약금액",
            "계약범위",
            "금액변경 여부",
            "기간변경 여부",
            "과업변경 여부",
            "계약기간시작일자",
            "계약기간종료일자",
            "의뢰부서",
            "계약업체",
            "예정가격",
            "비고",
        ),
        normalized_filename="KOICA_원조조달계약_정규화.csv",
    ),
    Source(
        slug="country_project_reports",
        public_data_id="15052832",
        dataset_name="한국국제협력단_국별사업 보고서 목록",
        page_url="https://www.data.go.kr/data/15052832/fileData.do",
        required_columns=(
            "사업번호",
            "사업명",
            "시작연도",
            "종료연도",
            "사업개요서링크",
        ),
        normalized_filename="KOICA_국별사업보고서_정규화.csv",
    ),
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT.resolve()))


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def atomic_write_text(path: Path, text: str) -> None:
    atomic_write_bytes(path, text.encode("utf-8"))


def fetch_bytes(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=120) as response:
        return response.read()


def strip_tags(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", value))).strip()


def parse_source_page(page_bytes: bytes, source: Source) -> dict[str, Any]:
    page = page_bytes.decode("utf-8", errors="replace")
    content_url_match = re.search(r'"contentUrl"\s*:\s*"([^"]+)"', page)
    if not content_url_match:
        raise RuntimeError(f"Current CSV contentUrl not found: {source.page_url}")

    filename_match = re.search(
        r"파일데이터명</th>\s*<td[^>]*>(.*?)</td>",
        page,
        flags=re.S,
    )
    row_count_match = re.search(
        r"전체\s*행</th>\s*<td[^>]*>\s*([\d,]+)\s*</td>",
        page,
        flags=re.S,
    )
    modified_match = re.search(
        r'id="updtDt"[^>]*value="([^"]+)"',
        page,
    )
    source_filename = (
        strip_tags(filename_match.group(1))
        if filename_match
        else f"{source.dataset_name}_unknown"
    )
    version_match = re.search(r"_(20\d{6})(?:\D|$)", source_filename)
    version_date = version_match.group(1) if version_match else "unknown"
    return {
        "resolved_download_url": html.unescape(content_url_match.group(1)),
        "source_filename": source_filename,
        "source_version_date": version_date,
        "portal_row_count": (
            int(row_count_match.group(1).replace(",", "")) if row_count_match else None
        ),
        "portal_modified_at": modified_match.group(1) if modified_match else "",
        "source_page_sha256": sha256_bytes(page_bytes),
    }


def decode_csv(data: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError:
            continue
        if "\ufffd" not in text:
            return text, encoding
    raise UnicodeError("CSV is not valid UTF-8, CP949, or EUC-KR")


def parse_csv(data: bytes, source: Source) -> tuple[list[dict[str, str]], str]:
    text, encoding = decode_csv(data)
    reader = csv.DictReader(io.StringIO(text, newline=""))
    fieldnames = [str(name or "").lstrip("\ufeff").strip() for name in reader.fieldnames or []]
    missing = [column for column in source.required_columns if column not in fieldnames]
    if missing:
        raise RuntimeError(
            f"{source.slug}: required columns missing: {', '.join(missing)}; "
            f"found={fieldnames}"
        )
    rows = []
    for raw in reader:
        row = {
            str(key or "").lstrip("\ufeff").strip(): html.unescape(
                str(value or "").strip()
            )
            for key, value in raw.items()
        }
        rows.append(row)
    return rows, encoding


def csv_text(rows: list[dict[str, Any]], fieldnames: list[str]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field, "") for field in fieldnames})
    return buffer.getvalue()


def parse_int(value: str) -> int | None:
    cleaned = re.sub(r"[^\d-]", "", str(value or ""))
    if cleaned in ("", "-"):
        return None
    return int(cleaned)


def normalize_project_no(value: str) -> str:
    match = PROJECT_NO_RE.search(unicodedata.normalize("NFKC", str(value or "")).upper())
    return match.group(1) if match else ""


def normalize_bid_no(value: str) -> str:
    match = BID_NO_RE.search(unicodedata.normalize("NFKC", str(value or "")).upper())
    if not match:
        return ""
    bid_no = match.group(1).upper()
    return bid_no if bid_no.count("-") == 2 else bid_no


def bid_base_no(bid_no: str) -> str:
    if not bid_no:
        return ""
    return re.sub(r"-\d+$", "", bid_no) if bid_no.count("-") == 2 else bid_no


def normalize_title(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).lower()
    text = text.replace("…", "...").replace("`", "'").replace("’", "'").replace("‘", "'")
    # Procurement titles usually append a period/budget expression such as
    # ('23-'28/1,220만불).  It is not part of the project identity.
    text = re.sub(
        r"[\(\[][^)\]]*(?:만불|백만불|억불|usd|달러)[^)\]]*[\)\]]?",
        " ",
        text,
        flags=re.I,
    )
    text = re.sub(r"\.{2,}.*$", " ", text)
    return re.sub(r"[^0-9a-z가-힣]+", "", text)


def title_score(left: str, right: str) -> float:
    left_norm = normalize_title(left)
    right_norm = normalize_title(right)
    if not left_norm or not right_norm:
        return 0.0
    shorter, longer = sorted((left_norm, right_norm), key=len)
    if len(shorter) >= 12 and shorter in longer:
        return 0.99
    return SequenceMatcher(None, left_norm, right_norm).ratio()


def classify_construction(text: str, procurement_category: str = "") -> dict[str, Any]:
    normalized = unicodedata.normalize("NFKC", str(text or "")).lower()
    strong = sorted(
        {keyword for keyword in STRONG_BUILDING_KEYWORDS if keyword.lower() in normalized}
    )
    weak = sorted(
        {keyword for keyword in WEAK_CONSTRUCTION_KEYWORDS if keyword.lower() in normalized}
    )
    assets = sorted(
        {keyword for keyword in BUILDING_ASSET_KEYWORDS if keyword.lower() in normalized}
    )
    services = sorted(
        {keyword for keyword in BUILDING_SERVICE_KEYWORDS if keyword.lower() in normalized}
    )
    category_is_works = procurement_category.strip() == "공사"
    candidate = (
        bool(strong)
        or (bool(assets) and bool(services))
        or (bool(assets) and bool(weak))
        or (category_is_works and bool(assets))
    )
    reasons = []
    if category_is_works and assets:
        reasons.append("입찰구분=공사+시설어")
    if strong:
        reasons.append("강한건축어")
    if assets and weak:
        reasons.append("시설어+공사어")
    if assets and services:
        reasons.append("시설어+설계감리어")
    return {
        "construction_related": int(candidate),
        "construction_reason": ";".join(reasons),
        "construction_keywords": ";".join(strong + weak + assets + services),
    }


def extract_area_values(text: str) -> list[float]:
    values = []
    for match in AREA_RE.finditer(unicodedata.normalize("NFKC", str(text or ""))):
        values.append(float(match.group("value").replace(",", "")))
    return values


def extract_gfa(text: str) -> tuple[float | None, str]:
    normalized = unicodedata.normalize("NFKC", str(text or ""))
    explicit_pattern = re.compile(
        r"(?:건축\s*)?연면적\s*(?:[:：]\s*)?(?:약\s*)?"
        r"(?P<value>\d[\d,]*(?:\.\d+)?)\s*(?:m2|m²|㎡|제곱미터)",
        re.I,
    )
    explicit = [
        float(match.group("value").replace(",", ""))
        for match in explicit_pattern.finditer(normalized)
    ]
    if len(explicit) == 1:
        return explicit[0], "explicit_gross_floor_area"
    if len(explicit) > 1:
        return None, "multiple_explicit_gross_floor_areas"

    matches = list(AREA_RE.finditer(normalized))
    if len(matches) == 1:
        prefix = normalized[max(0, matches[0].start() - 18) : matches[0].start()]
        if not re.search(r"(?:대지|부지|건축)\s*면적", prefix):
            return (
                float(matches[0].group("value").replace(",", "")),
                "single_unlabelled_area",
            )
    return None, ""


def extract_program_budget_usd(title: str) -> int | None:
    normalized = unicodedata.normalize("NFKC", str(title or "")).replace(" ", "")
    patterns = (
        (r"([\d,]+(?:\.\d+)?)만불", 10_000),
        (r"([\d,]+(?:\.\d+)?)백만불", 1_000_000),
        (r"([\d,]+(?:\.\d+)?)억불", 100_000_000),
    )
    for pattern, multiplier in patterns:
        match = re.search(pattern, normalized)
        if match:
            return round(float(match.group(1).replace(",", "")) * multiplier)
    return None


def country_tokens(value: str) -> list[str]:
    return [
        token.strip()
        for token in re.split(r"[,/·ㆍ]|(?:\s+및\s+)", str(value or ""))
        if token.strip()
    ]


def infer_countries(text: str, known_countries: Iterable[str]) -> list[str]:
    normalized = unicodedata.normalize("NFKC", str(text or ""))
    return [
        country
        for country in sorted(set(known_countries), key=lambda item: (-len(item), item))
        if country and country in normalized
    ]


def load_existing_db(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "project_rows": [],
            "project_nos": set(),
            "bids_by_project": {},
            "country_names": set(),
        }
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        project_rows = [
            dict(row)
            for row in connection.execute(
                """
                SELECT bid_no, project_no, country_ko, project_name, bid_title_ko
                FROM projects
                WHERE COALESCE(project_no, '') <> ''
                """
            )
        ]
    finally:
        connection.close()
    bids_by_project: dict[str, list[str]] = {}
    for row in project_rows:
        bids_by_project.setdefault(row["project_no"], []).append(row["bid_no"])
    return {
        "project_rows": project_rows,
        "project_nos": {row["project_no"] for row in project_rows},
        "bids_by_project": {
            project_no: sorted(set(bid_nos))
            for project_no, bid_nos in bids_by_project.items()
        },
        "country_names": {
            row["country_ko"] for row in project_rows if row.get("country_ko")
        },
    }


def unique_project_candidates(rows: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    candidates: dict[str, dict[str, str]] = {}
    for row in rows:
        project_no = row.get("project_no_linked", "")
        if project_no:
            candidates.setdefault(
                project_no,
                {
                    "project_no": project_no,
                    "project_title": row.get("project_title", ""),
                    "country_ko": row.get("country_ko", ""),
                },
            )
    return list(candidates.values())


def link_project_by_title(
    title: str,
    countries: list[str],
    candidates: list[dict[str, str]],
) -> tuple[str, str, float]:
    scored: list[tuple[float, dict[str, str]]] = []
    for candidate in candidates:
        candidate_country = candidate.get("country_ko", "")
        if countries and candidate_country and candidate_country not in countries:
            continue
        score = title_score(title, candidate.get("project_title", ""))
        if score:
            scored.append((score, candidate))
    if not scored:
        return "", "", 0.0
    scored.sort(key=lambda item: (-item[0], item[1].get("project_no", "")))
    best_score, best = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0
    if best_score >= 0.98:
        same_top = {
            item[1].get("project_no", "")
            for item in scored
            if item[0] >= best_score - 0.005
        }
        if len(same_top) == 1:
            return best["project_no"], "official_report_title_containment", best_score
    if best_score >= 0.86 and best_score - second_score >= 0.04:
        return best["project_no"], "official_report_title_fuzzy", best_score
    return "", "", best_score


def link_project_from_existing_db(
    title: str,
    countries: list[str],
    project_rows: list[dict[str, str]],
) -> tuple[str, str, float]:
    candidates: dict[str, dict[str, str]] = {}
    for row in project_rows:
        if countries and row.get("country_ko") and row["country_ko"] not in countries:
            continue
        project_no = row.get("project_no", "")
        score = max(
            title_score(title, row.get("project_name", "")),
            title_score(title, row.get("bid_title_ko", "")),
        )
        current = candidates.get(project_no)
        if project_no and (current is None or score > float(current["score"])):
            candidates[project_no] = {"project_no": project_no, "score": str(score)}
    ranked = sorted(
        ((float(row["score"]), row["project_no"]) for row in candidates.values()),
        reverse=True,
    )
    if not ranked:
        return "", "", 0.0
    best_score, best_project_no = ranked[0]
    second_score = ranked[1][0] if len(ranked) > 1 else 0.0
    if best_score >= 0.98 and best_score - second_score >= 0.005:
        return best_project_no, "existing_db_title_containment", best_score
    if best_score >= 0.88 and best_score - second_score >= 0.05:
        return best_project_no, "existing_db_title_fuzzy", best_score
    return "", "", best_score


def project_link_fields(
    direct_project_no: str,
    title: str,
    countries: list[str],
    official_projects: list[dict[str, str]],
    existing: dict[str, Any],
) -> dict[str, Any]:
    if direct_project_no:
        linked_project_no = direct_project_no
        method = "source_direct"
        score = 1.0
    else:
        linked_project_no, method, score = link_project_by_title(
            title, countries, official_projects
        )
        if not linked_project_no:
            linked_project_no, method, db_score = link_project_from_existing_db(
                title, countries, existing["project_rows"]
            )
            score = max(score, db_score)
    bid_nos = existing["bids_by_project"].get(linked_project_no, [])
    return {
        "project_no_source": direct_project_no,
        "project_no_linked": linked_project_no,
        "project_link_method": method,
        "project_link_score": f"{score:.3f}" if score else "",
        "existing_db_project_match": int(
            linked_project_no in existing["project_nos"]
        ),
        "existing_db_project_bid_nos": ";".join(bid_nos),
    }


def normalize_report_rows(
    source: Source,
    raw_rows: list[dict[str, str]],
    known_countries: set[str],
    existing: dict[str, Any],
) -> list[dict[str, Any]]:
    normalized = []
    for index, row in enumerate(raw_rows, 1):
        title = row["사업명"]
        direct_project_no = normalize_project_no(row["사업번호"])
        countries = infer_countries(title, known_countries)
        country = ";".join(countries)
        classification = classify_construction(title)
        linked = project_link_fields(
            direct_project_no,
            title,
            countries,
            [],
            existing,
        )
        budget = extract_program_budget_usd(title)
        normalized.append(
            {
                "source_record_id": f"{source.public_data_id}:{index}",
                "source_row_number": index,
                "public_data_id": source.public_data_id,
                "source_page_url": source.page_url,
                **linked,
                "bid_no_source": normalize_bid_no(" ".join(row.values())),
                "bid_base_no_source": bid_base_no(
                    normalize_bid_no(" ".join(row.values()))
                ),
                "country_ko": country,
                "is_uganda": int("우간다" in title),
                "project_title": title,
                "start_year": parse_int(row["시작연도"]),
                "end_year": parse_int(row["종료연도"]),
                "project_summary_url": row["사업개요서링크"],
                "program_budget_usd_from_title": budget,
                "amount_boundary": (
                    "사업명에 표시된 KOICA 전체 사업예산; 건축공사비 아님"
                    if budget is not None
                    else ""
                ),
                **classification,
                "area_values_m2": "",
                "gross_floor_area_m2": "",
                "gfa_extraction_method": "",
                "raw_ceiling_per_gfa_krw": "",
                "unit_cost_potential": 0,
            }
        )
    return normalized


def normalize_plan_rows(
    source: Source,
    raw_rows: list[dict[str, str]],
    known_countries: set[str],
    official_projects: list[dict[str, str]],
    existing: dict[str, Any],
) -> list[dict[str, Any]]:
    normalized = []
    for index, row in enumerate(raw_rows, 1):
        countries = country_tokens(row["수원국"])
        if not countries:
            countries = infer_countries(
                " ".join((row["발주명"], row["입찰범위"])),
                known_countries,
            )
        text = " ".join((row["발주명"], row["입찰범위"]))
        classification = classify_construction(text, row["입찰구분"])
        areas = extract_area_values(text)
        gross_floor_area_m2, gfa_method = extract_gfa(text)
        ceiling_krw = parse_int(row["입찰한도액(원)"])
        direct_project_no = normalize_project_no(text)
        linked = project_link_fields(
            direct_project_no,
            row["발주명"],
            countries,
            official_projects,
            existing,
        )
        direct_bid_no = normalize_bid_no(text)
        unit_cost_potential = bool(
            classification["construction_related"]
            and row["입찰구분"] == "공사"
            and ceiling_krw
            and gross_floor_area_m2
        )
        normalized.append(
            {
                "source_record_id": f"{source.public_data_id}:{index}",
                "source_row_number": index,
                "public_data_id": source.public_data_id,
                "source_page_url": source.page_url,
                **linked,
                "bid_no_source": direct_bid_no,
                "bid_base_no_source": bid_base_no(direct_bid_no),
                "department": row["사업담당부서"],
                "country_ko": ";".join(countries),
                "is_uganda": int(
                    "우간다" in row["수원국"] or "우간다" in text
                ),
                "procurement_title": row["발주명"],
                "sector": row["분야"],
                "procurement_category": row["입찰구분"],
                "scope": row["입찰범위"],
                "ceiling_krw": ceiling_krw,
                "amount_boundary": "발주계획 입찰한도액; 계획 변경 가능",
                "contract_method": row["계약방법"],
                "selection_method": row["낙찰자선정방식"],
                "planned_issue_date": row["발주예정시기"],
                **classification,
                "area_values_m2": ";".join(f"{value:g}" for value in areas),
                "gross_floor_area_m2": (
                    f"{gross_floor_area_m2:g}" if gross_floor_area_m2 else ""
                ),
                "gfa_extraction_method": gfa_method,
                "raw_ceiling_per_gfa_krw": (
                    round(ceiling_krw / gross_floor_area_m2)
                    if unit_cost_potential
                    else ""
                ),
                "unit_cost_potential": int(unit_cost_potential),
            }
        )
    return normalized


def normalize_contract_rows(
    source: Source,
    raw_rows: list[dict[str, str]],
    known_countries: set[str],
    official_projects: list[dict[str, str]],
    existing: dict[str, Any],
) -> list[dict[str, Any]]:
    normalized = []
    for index, row in enumerate(raw_rows, 1):
        text = " ".join((row["계약명"], row["계약범위"], row["비고"]))
        countries = infer_countries(text, known_countries)
        classification = classify_construction(text, row["조달구분"])
        areas = extract_area_values(text)
        gross_floor_area_m2, gfa_method = extract_gfa(text)
        direct_project_no = normalize_project_no(text)
        linked = project_link_fields(
            direct_project_no,
            row["계약명"],
            countries,
            official_projects,
            existing,
        )
        direct_bid_no = normalize_bid_no(text)
        normalized.append(
            {
                "source_record_id": f"{source.public_data_id}:{index}",
                "source_row_number": index,
                "public_data_id": source.public_data_id,
                "source_page_url": source.page_url,
                **linked,
                "bid_no_source": direct_bid_no,
                "bid_base_no_source": bid_base_no(direct_bid_no),
                "contract_no": row["계약번호"].strip().upper(),
                "amendment_sequence": parse_int(row["차수"]),
                "new_or_amended": row["신규여부"],
                "country_ko": ";".join(countries),
                "is_uganda": int("우간다" in text),
                "contract_title": row["계약명"],
                "procurement_program": row["조달사업구분"],
                "procurement_category": row["조달구분"],
                "contract_type": row["조달계약종류"],
                "contract_method": row["계약방법"],
                "contract_date": row["계약일자"],
                "currency": row["통화구분"],
                "contract_amount": parse_int(row["계약금액"]),
                "scope": row["계약범위"],
                "amount_changed": row["금액변경 여부"],
                "period_changed": row["기간변경 여부"],
                "scope_changed": row["과업변경 여부"],
                "contract_start_date": row["계약기간시작일자"],
                "contract_end_date": row["계약기간종료일자"],
                "requesting_department": row["의뢰부서"],
                "contractors": row["계약업체"],
                "estimated_price": parse_int(row["예정가격"]),
                "note": row["비고"],
                "amount_boundary": "KOICA 원조조달 계약금액; 변경계약은 차수별 스냅샷",
                **classification,
                "area_values_m2": ";".join(f"{value:g}" for value in areas),
                "gross_floor_area_m2": (
                    f"{gross_floor_area_m2:g}" if gross_floor_area_m2 else ""
                ),
                "gfa_extraction_method": gfa_method,
                "raw_ceiling_per_gfa_krw": "",
                # This source has no local construction contracts in the
                # current file.  Design/PMC amounts must not be divided by GFA.
                "unit_cost_potential": 0,
            }
        )
    return normalized


REPORT_FIELDS = [
    "source_record_id",
    "source_row_number",
    "public_data_id",
    "source_page_url",
    "project_no_source",
    "project_no_linked",
    "project_link_method",
    "project_link_score",
    "existing_db_project_match",
    "existing_db_project_bid_nos",
    "bid_no_source",
    "bid_base_no_source",
    "country_ko",
    "is_uganda",
    "project_title",
    "start_year",
    "end_year",
    "project_summary_url",
    "program_budget_usd_from_title",
    "amount_boundary",
    "construction_related",
    "construction_reason",
    "construction_keywords",
    "area_values_m2",
    "gross_floor_area_m2",
    "gfa_extraction_method",
    "raw_ceiling_per_gfa_krw",
    "unit_cost_potential",
]

PLAN_FIELDS = [
    "source_record_id",
    "source_row_number",
    "public_data_id",
    "source_page_url",
    "project_no_source",
    "project_no_linked",
    "project_link_method",
    "project_link_score",
    "existing_db_project_match",
    "existing_db_project_bid_nos",
    "bid_no_source",
    "bid_base_no_source",
    "department",
    "country_ko",
    "is_uganda",
    "procurement_title",
    "sector",
    "procurement_category",
    "scope",
    "ceiling_krw",
    "amount_boundary",
    "contract_method",
    "selection_method",
    "planned_issue_date",
    "construction_related",
    "construction_reason",
    "construction_keywords",
    "area_values_m2",
    "gross_floor_area_m2",
    "gfa_extraction_method",
    "raw_ceiling_per_gfa_krw",
    "unit_cost_potential",
]

CONTRACT_FIELDS = [
    "source_record_id",
    "source_row_number",
    "public_data_id",
    "source_page_url",
    "project_no_source",
    "project_no_linked",
    "project_link_method",
    "project_link_score",
    "existing_db_project_match",
    "existing_db_project_bid_nos",
    "bid_no_source",
    "bid_base_no_source",
    "contract_no",
    "amendment_sequence",
    "new_or_amended",
    "country_ko",
    "is_uganda",
    "contract_title",
    "procurement_program",
    "procurement_category",
    "contract_type",
    "contract_method",
    "contract_date",
    "currency",
    "contract_amount",
    "scope",
    "amount_changed",
    "period_changed",
    "scope_changed",
    "contract_start_date",
    "contract_end_date",
    "requesting_department",
    "contractors",
    "estimated_price",
    "note",
    "amount_boundary",
    "construction_related",
    "construction_reason",
    "construction_keywords",
    "area_values_m2",
    "gross_floor_area_m2",
    "gfa_extraction_method",
    "raw_ceiling_per_gfa_krw",
    "unit_cost_potential",
]

COMBINED_FIELDS = [
    "source_dataset",
    "source_record_id",
    "project_no_linked",
    "project_link_method",
    "project_link_score",
    "existing_db_project_match",
    "existing_db_project_bid_nos",
    "bid_no_source",
    "contract_no",
    "country_ko",
    "is_uganda",
    "record_title",
    "record_scope",
    "procurement_category",
    "amount_currency",
    "amount_value",
    "amount_role",
    "amount_boundary",
    "area_values_m2",
    "gross_floor_area_m2",
    "gfa_extraction_method",
    "raw_ceiling_per_gfa_krw",
    "unit_cost_potential",
    "construction_reason",
    "construction_keywords",
    "official_record_url",
]


def combined_construction_rows(
    reports: list[dict[str, Any]],
    plans: list[dict[str, Any]],
    contracts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    combined = []
    for row in plans:
        if row["construction_related"]:
            combined.append(
                {
                    **{field: row.get(field, "") for field in COMBINED_FIELDS},
                    "source_dataset": "annual_procurement_plan",
                    "record_title": row["procurement_title"],
                    "record_scope": row["scope"],
                    "amount_currency": "KRW",
                    "amount_value": row["ceiling_krw"],
                    "amount_role": "planned_bid_ceiling",
                    "official_record_url": row["source_page_url"],
                }
            )
    for row in contracts:
        if row["construction_related"]:
            combined.append(
                {
                    **{field: row.get(field, "") for field in COMBINED_FIELDS},
                    "source_dataset": "aid_procurement_contracts",
                    "record_title": row["contract_title"],
                    "record_scope": row["scope"],
                    "amount_currency": row["currency"],
                    "amount_value": row["contract_amount"],
                    "amount_role": "contract_amount",
                    "official_record_url": row["source_page_url"],
                }
            )
    for row in reports:
        if row["construction_related"]:
            combined.append(
                {
                    **{field: row.get(field, "") for field in COMBINED_FIELDS},
                    "source_dataset": "country_project_reports",
                    "record_title": row["project_title"],
                    "record_scope": "",
                    "procurement_category": "",
                    "amount_currency": "USD" if row["program_budget_usd_from_title"] else "",
                    "amount_value": row["program_budget_usd_from_title"],
                    "amount_role": (
                        "whole_program_budget_from_title"
                        if row["program_budget_usd_from_title"]
                        else ""
                    ),
                    "official_record_url": row["project_summary_url"],
                }
            )
    combined.sort(
        key=lambda row: (
            -int(row.get("is_uganda") or 0),
            row["source_dataset"],
            str(row.get("country_ko") or ""),
            str(row.get("record_title") or ""),
        )
    )
    return combined


def source_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "normalized_row_count": len(rows),
        "construction_related_count": sum(
            int(row.get("construction_related") or 0) for row in rows
        ),
        "uganda_row_count": sum(int(row.get("is_uganda") or 0) for row in rows),
        "uganda_construction_related_count": sum(
            int(row.get("is_uganda") or 0)
            and int(row.get("construction_related") or 0)
            for row in rows
        ),
        "linked_project_no_count": sum(bool(row.get("project_no_linked")) for row in rows),
        "existing_db_project_match_count": sum(
            int(row.get("existing_db_project_match") or 0) for row in rows
        ),
        "unit_cost_potential_count": sum(
            int(row.get("unit_cost_potential") or 0) for row in rows
        ),
    }


def load_previous_manifest() -> dict[str, Any]:
    if not MANIFEST_PATH.exists():
        return {}
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def offline_source(source: Source, previous_manifest: dict[str, Any]) -> tuple[bytes, dict[str, Any]]:
    previous_sources = {
        item["slug"]: item for item in previous_manifest.get("sources", [])
    }
    previous = previous_sources.get(source.slug, {})
    path_value = previous.get("raw_relative_path")
    if path_value and (ROOT / path_value).exists():
        raw_path = ROOT / path_value
    else:
        candidates = sorted(RAW_DIR.glob(f"{source.slug}_*.csv"))
        if not candidates:
            raise FileNotFoundError(
                f"--offline requested but no raw file exists for {source.slug}"
            )
        raw_path = candidates[-1]
    metadata = {
        "resolved_download_url": previous.get("resolved_download_url", ""),
        "source_filename": previous.get("source_filename", raw_path.name),
        "source_version_date": previous.get(
            "source_version_date",
            raw_path.stem.rsplit("_", 1)[-1],
        ),
        "portal_row_count": previous.get("portal_row_count"),
        "portal_modified_at": previous.get("portal_modified_at", ""),
        "source_page_sha256": previous.get("source_page_sha256", ""),
        "raw_path": raw_path,
    }
    return raw_path.read_bytes(), metadata


def acquire_source(
    source: Source,
    offline: bool,
    previous_manifest: dict[str, Any],
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    if offline:
        raw_bytes, metadata = offline_source(source, previous_manifest)
        raw_path = metadata.pop("raw_path")
    else:
        page_bytes = fetch_bytes(source.page_url)
        metadata = parse_source_page(page_bytes, source)
        raw_bytes = fetch_bytes(metadata["resolved_download_url"])
        raw_path = RAW_DIR / f"{source.slug}_{metadata['source_version_date']}.csv"
        atomic_write_bytes(raw_path, raw_bytes)
    rows, encoding = parse_csv(raw_bytes, source)
    portal_count = metadata.get("portal_row_count")
    if portal_count is not None and len(rows) != portal_count:
        raise RuntimeError(
            f"{source.slug}: downloaded rows {len(rows)} != portal rows {portal_count}"
        )
    metadata.update(
        {
            "raw_relative_path": relative(raw_path),
            "raw_sha256": sha256_bytes(raw_bytes),
            "raw_encoding": encoding,
            "downloaded_row_count": len(rows),
        }
    )
    return rows, metadata


def validate_normalized(rows: list[dict[str, Any]], source: Source) -> None:
    record_ids = [row["source_record_id"] for row in rows]
    if len(record_ids) != len(set(record_ids)):
        raise RuntimeError(f"{source.slug}: duplicate source_record_id")
    for row in rows:
        project_no = str(row.get("project_no_linked") or "")
        if project_no and not PROJECT_NO_RE.fullmatch(project_no):
            raise RuntimeError(f"{source.slug}: invalid project number {project_no!r}")
        bid_no = str(row.get("bid_no_source") or "")
        if bid_no and not BID_NO_RE.fullmatch(bid_no):
            raise RuntimeError(f"{source.slug}: invalid bid number {bid_no!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Rebuild normalized outputs from the most recently downloaded raw files.",
    )
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    previous_manifest = load_previous_manifest()
    existing = load_existing_db(DB_PATH)

    raw: dict[str, list[dict[str, str]]] = {}
    metadata: dict[str, dict[str, Any]] = {}
    for source in SOURCES:
        rows, source_metadata = acquire_source(source, args.offline, previous_manifest)
        raw[source.slug] = rows
        metadata[source.slug] = source_metadata

    known_countries = set(existing["country_names"])
    for row in raw["annual_procurement_plan"]:
        known_countries.update(country_tokens(row["수원국"]))
    known_countries.add("우간다")

    report_source = next(item for item in SOURCES if item.slug == "country_project_reports")
    report_rows = normalize_report_rows(
        report_source,
        raw["country_project_reports"],
        known_countries,
        existing,
    )
    official_projects = unique_project_candidates(report_rows)

    plan_source = next(item for item in SOURCES if item.slug == "annual_procurement_plan")
    plan_rows = normalize_plan_rows(
        plan_source,
        raw["annual_procurement_plan"],
        known_countries,
        official_projects,
        existing,
    )
    contract_source = next(
        item for item in SOURCES if item.slug == "aid_procurement_contracts"
    )
    contract_rows = normalize_contract_rows(
        contract_source,
        raw["aid_procurement_contracts"],
        known_countries,
        official_projects,
        existing,
    )

    normalized_by_slug = {
        "annual_procurement_plan": (plan_rows, PLAN_FIELDS),
        "aid_procurement_contracts": (contract_rows, CONTRACT_FIELDS),
        "country_project_reports": (report_rows, REPORT_FIELDS),
    }
    manifest_sources = []
    for source in SOURCES:
        rows, fields = normalized_by_slug[source.slug]
        validate_normalized(rows, source)
        normalized_path = OUTPUT_DIR / source.normalized_filename
        atomic_write_text(normalized_path, csv_text(rows, fields))
        manifest_sources.append(
            {
                "slug": source.slug,
                "public_data_id": source.public_data_id,
                "dataset_name": source.dataset_name,
                "source_page_url": source.page_url,
                **metadata[source.slug],
                "normalized_relative_path": relative(normalized_path),
                "normalized_sha256": sha256_path(normalized_path),
                **source_stats(rows),
            }
        )

    combined_rows = combined_construction_rows(report_rows, plan_rows, contract_rows)
    combined_path = OUTPUT_DIR / "KOICA_공식데이터_건축관련후보.csv"
    atomic_write_text(combined_path, csv_text(combined_rows, COMBINED_FIELDS))

    manifest = {
        "schema_version": "1.0",
        "provider": "한국국제협력단(KOICA)",
        "distribution_platform": "공공데이터포털",
        "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "offline_rebuild": bool(args.offline),
        "existing_db_relative_path": relative(DB_PATH) if DB_PATH.exists() else "",
        "join_policy": {
            "direct": "국별사업 보고서 목록의 사업번호 또는 원문 텍스트의 정규식 식별자",
            "inferred": (
                "국가 제한 후 공식 국별사업 제목 포함관계 또는 보수적 유사도 "
                "기준으로 연결; project_link_method/score에 구분"
            ),
            "bid_number": (
                "원문에 LYYYY-NNNNN[-차수]가 실제 표기된 경우만 bid_no_source로 기록"
            ),
            "existing_db_match": (
                "project_no_linked를 기존 SQLite projects.project_no와 일치시킨 결과"
            ),
        },
        "cost_boundary_policy": {
            "annual_procurement_plan": "발주계획 입찰한도액(KRW), 변경 가능한 계획값",
            "aid_procurement_contracts": (
                "원조조달 계약금액(KRW), 변경계약은 차수별 스냅샷"
            ),
            "country_project_reports": (
                "사업명에서 추출한 전체 사업예산(USD), 건축공사비로 사용 금지"
            ),
        },
        "construction_screening_note": (
            "construction_related는 공사 구분·직접 건축어·시설어와 설계감리어의 "
            "조합으로 만든 문서추적 후보이며 검토 완료 단가사례가 아니다."
        ),
        "sources": manifest_sources,
        "combined_construction_candidates": {
            "relative_path": relative(combined_path),
            "sha256": sha256_path(combined_path),
            "row_count": len(combined_rows),
            "uganda_row_count": sum(
                int(row.get("is_uganda") or 0) for row in combined_rows
            ),
            "unit_cost_potential_count": sum(
                int(row.get("unit_cost_potential") or 0) for row in combined_rows
            ),
        },
    }
    atomic_write_text(
        MANIFEST_PATH,
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    )

    print(
        json.dumps(
            {
                "manifest": relative(MANIFEST_PATH),
                "combined": manifest["combined_construction_candidates"],
                "sources": {
                    item["slug"]: {
                        key: item[key]
                        for key in (
                            "normalized_row_count",
                            "construction_related_count",
                            "uganda_row_count",
                            "uganda_construction_related_count",
                            "linked_project_no_count",
                            "existing_db_project_match_count",
                            "unit_cost_potential_count",
                        )
                    }
                    for item in manifest_sources
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
