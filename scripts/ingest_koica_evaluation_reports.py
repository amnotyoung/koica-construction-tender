#!/usr/bin/env python3
"""Validate KOICA endline-evaluation curation and build a portable manifest.

The raw PDF corpus stays outside the repository.  The generated manifest keeps
an inventory of every physical PDF, deterministic corpus integrity metadata,
accepted same-project matches, and short page-verified construction excerpts.
Reports may come either from the frozen local corpus or from a separately
cached, hash-audited download from KOICA's official evaluation platform.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import sqlite3
import subprocess
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from scripts.snapshot_koica_evaluation_index import (
        validate_snapshot as validate_official_index_snapshot,
    )
except ModuleNotFoundError:  # Direct execution via ``python scripts/...``.
    from snapshot_koica_evaluation_index import (
        validate_snapshot as validate_official_index_snapshot,
    )


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = (
    ROOT
    / "outputs"
    / "koica-construction-distribution"
    / "KOICA_건축사업_사례DB_2016-2025.sqlite"
)
DEFAULT_CURATION = (
    ROOT / "data" / "manifests" / "koica_endline_evaluation_curation.json"
)
DEFAULT_OUTPUT = (
    ROOT / "data" / "manifests" / "koica_endline_evaluation_reports.json"
)

LOCAL_REPORT_ID_PATTERN = re.compile(r"^koica-eval-(\d{12})-(\d{2})$")
OFFICIAL_REPORT_ID_PATTERN = re.compile(r"^koica-official-eval-(\d+)$")
SOURCE_FILE_PATTERN = re.compile(
    r"^(\d{12})_(\d{2})(?: \((\d+)\))?\.pdf$", re.IGNORECASE
)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}(?:-\d{2})?$")

FIELD_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "facility_scope_summary": {
        "category": "facility_scope", "value_kind": "text",
        "description": "평가보고서가 확인한 시설·공종·산출물 범위",
    },
    "facility_area": {
        "category": "facility_scope", "value_kind": "numeric_optional",
        "units": ["m2"], "description": "시설 면적",
    },
    "facility_count": {
        "category": "facility_scope", "value_kind": "numeric_optional",
        "units": ["building", "site", "room", "unit"],
        "description": "건물·대상지·실·시설 개수",
    },
    "project_budget": {
        "category": "cost_procurement", "value_kind": "numeric_optional",
        "units": ["USD", "KRW"], "description": "전체 사업 예산",
    },
    "construction_budget": {
        "category": "cost_procurement", "value_kind": "numeric_optional",
        "units": ["USD", "KRW"], "description": "건축·인프라 예산 또는 계약액",
    },
    "procurement_issue": {
        "category": "cost_procurement", "value_kind": "text",
        "description": "조달·계약·비용 집행 관련 이슈",
    },
    "implementation_period": {
        "category": "schedule", "value_kind": "numeric_optional",
        "units": ["day", "month", "year"], "description": "사업·공사 기간",
    },
    "schedule_delay": {
        "category": "schedule", "value_kind": "numeric_optional",
        "units": ["day", "month", "year"], "description": "지연 기간과 원인",
    },
    "handover_status": {
        "category": "schedule", "value_kind": "text",
        "description": "준공·인계·개소 상태",
    },
    "construction_quality": {
        "category": "quality_safety", "value_kind": "text",
        "description": "시공 품질·하자·설계 적합성",
    },
    "safety_issue": {
        "category": "quality_safety", "value_kind": "text",
        "description": "시설 안전·산업안전 이슈",
    },
    "equipment_compatibility": {
        "category": "quality_safety", "value_kind": "text",
        "description": "시설과 기자재의 규격·환경 적합성",
    },
    "maintenance_arrangement": {
        "category": "operations_maintenance", "value_kind": "numeric_optional",
        "units": ["day", "month", "year"],
        "description": "시설 운영·유지관리 책임과 체계",
    },
    "maintenance_budget": {
        "category": "operations_maintenance", "value_kind": "numeric_optional",
        "units": ["USD", "KRW", "percent"],
        "description": "유지관리 예산·재원",
    },
    "facility_utilization": {
        "category": "utilization_results", "value_kind": "numeric_optional",
        "units": ["percent", "person", "day", "month", "year"],
        "description": "시설 이용률·이용자·가동 수준",
    },
    "facility_performance": {
        "category": "utilization_results", "value_kind": "text",
        "description": "시설이 기여한 산출·성과",
    },
    "infrastructure_risk": {
        "category": "risk_issue", "value_kind": "text",
        "description": "건축·인프라 지속가능성 위험",
    },
    "construction_lesson": {
        "category": "lesson_recommendation", "value_kind": "text",
        "description": "유사 건축사업 설계·집행 교훈",
    },
    "construction_recommendation": {
        "category": "lesson_recommendation", "value_kind": "text",
        "description": "평가보고서의 시설·인프라 관련 권고",
    },
}

ALLOWED_CONFIDENCE = {"high", "medium"}
ALLOWED_MATCH_METHODS = {"exact_official_title", "exact_component_title"}
ALLOWED_RELATION_SCOPES = {"same_project", "same_project_component"}
MIN_ACCEPTED_MATCH_SCORE = 0.85
LOCAL_SOURCE_KIND = "local_corpus"
OFFICIAL_SOURCE_KIND = "koica_official_site"
OCR_TEXT_DIGEST_ALGORITHM = (
    "sha256(filename_nfc NUL sha256 NUL bytes LF)"
)
OFFICIAL_PAGE_PREFIX = (
    "https://www.koica.go.kr/sites/evaluation_kr/article/view/"
)
OFFICIAL_DOWNLOAD_PREFIX = (
    "https://www.koica.go.kr/sites/evaluation_kr/common/filedownload/"
)


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_curation(path: Path) -> Dict[str, Any]:
    """Load the reviewed base curation and its bounded JSON fragments."""
    curation = load_json(path)
    include_files = curation.get("include_files", [])
    if not isinstance(include_files, list) or len(include_files) != len(
        set(include_files)
    ):
        raise ValueError("curation include_files must be a unique list")
    for filename in include_files:
        if not isinstance(filename, str) or Path(filename).name != filename:
            raise ValueError(f"curation include must be a basename: {filename}")
        fragment = load_json(path.parent / filename)
        if fragment.get("fragment_schema_version") != "1.0":
            raise ValueError(f"unsupported curation fragment: {filename}")
        for field in (
            "multi_project_report_ids", "reports", "matches", "findings"
        ):
            values = fragment.get(field, [])
            if not isinstance(values, list):
                raise ValueError(f"fragment field must be a list: {filename}.{field}")
            curation.setdefault(field, []).extend(values)
        fragment_review = fragment.get("review", {})
        if not isinstance(fragment_review, dict):
            raise ValueError(f"fragment review must be an object: {filename}")
        for field in ("excluded_candidates", "identity_conflicts"):
            values = fragment_review.get(field, [])
            if not isinstance(values, list):
                raise ValueError(
                    f"fragment review field must be a list: {filename}.{field}"
                )
            curation.setdefault("review", {}).setdefault(field, []).extend(values)
    official = curation.get("official_source") or {}
    snapshot_file = official.get("index_snapshot_file")
    if snapshot_file:
        if not isinstance(snapshot_file, str) or Path(snapshot_file).name != snapshot_file:
            raise ValueError("official index snapshot must be a basename")
        official["index_snapshot"] = validate_official_index_snapshot(
            load_json(path.parent / snapshot_file)
        )
    return curation


def canonical_json_digest(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_text(value: Any) -> str:
    return re.sub(
        r"\s+", " ", unicodedata.normalize("NFKC", str(value or ""))
    ).strip()


def compact_text(value: Any) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]+", "", normalize_text(value)).lower()


def require_nonempty(value: Any, label: str, minimum: int = 1) -> str:
    text = normalize_text(value)
    if len(text) < minimum:
        raise ValueError(f"{label} must be non-empty")
    return text


def validate_partial_date(value: Any, label: str) -> Optional[str]:
    if value in (None, ""):
        return None
    text = str(value)
    if not DATE_PATTERN.fullmatch(text):
        raise ValueError(f"{label} must be YYYY-MM or YYYY-MM-DD: {text}")
    year, month, *day = [int(part) for part in text.split("-")]
    if not 1 <= month <= 12 or (day and not 1 <= day[0] <= 31):
        raise ValueError(f"invalid {label}: {text}")
    return text


def pdf_page_count(path: Path) -> int:
    completed = subprocess.run(
        ["pdfinfo", str(path)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    match = re.search(r"^Pages:\s+(\d+)\s*$", completed.stdout, re.MULTILINE)
    if not match:
        raise RuntimeError(f"pdfinfo did not return a page count: {path.name}")
    return int(match.group(1))


def extract_pdf_pages(path: Path) -> Tuple[List[str], int]:
    completed = subprocess.run(
        ["pdftotext", "-layout", "-enc", "UTF-8", str(path), "-"],
        check=True,
        capture_output=True,
    )
    text = completed.stdout.decode("utf-8", errors="replace")
    pages = text.split("\f")
    if pages and pages[-1] == "":
        pages.pop()
    return pages, len(text)


def meaningful_character_count(page: str) -> int:
    text = normalize_text(page)
    text = re.sub(r"www\s*\.\s*koica\s*\.\s*go\s*\.\s*kr", "", text, flags=re.I)
    text = re.sub(r"(?:^|\s)-?\s*\d{1,4}\s*-?(?:\s|$)", " ", text)
    return len(re.sub(r"[^0-9A-Za-z가-힣]", "", text))


def extraction_metrics(pages: List[str]) -> Tuple[int, float, str]:
    meaningful = [meaningful_character_count(page) for page in pages]
    total = sum(meaningful)
    covered = sum(count >= 50 for count in meaningful)
    coverage = covered / max(len(pages), 1)
    average = total / max(len(pages), 1)
    if coverage >= 0.75 and average >= 100:
        status = "text"
    elif coverage >= 0.20 and average >= 40:
        status = "partial_text"
    else:
        status = "ocr_required"
    return total, round(coverage, 6), status


def validate_tools() -> None:
    missing = [name for name in ("pdfinfo", "pdftotext") if not shutil.which(name)]
    if missing:
        raise RuntimeError(f"missing PDF tools: {', '.join(missing)}")


def corpus_digest(inventory: List[Dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for row in sorted(inventory, key=lambda item: unicodedata.normalize("NFC", item["source_file"])):
        digest.update(unicodedata.normalize("NFC", row["source_file"]).encode("utf-8"))
        digest.update(b"\0")
        digest.update(row["sha256"].encode("ascii"))
        digest.update(b"\0")
        digest.update(str(row["file_bytes"]).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def load_ocr_pages(directory: Path, expected_page_count: int) -> Tuple[List[str], str]:
    """Load a page-addressable OCR sidecar and return its audited digest."""
    if not directory.is_dir():
        raise FileNotFoundError(directory)
    paths = sorted(directory.glob("page-*.txt"))
    expected_names = [f"page-{page:03d}.txt" for page in range(1, expected_page_count + 1)]
    if [path.name for path in paths] != expected_names:
        raise ValueError(
            f"OCR sidecar pages differ: expected {expected_page_count}, "
            f"found {len(paths)} in {directory.name}"
        )
    inventory = []
    pages = []
    for path in paths:
        payload = path.read_bytes()
        try:
            pages.append(payload.decode("utf-8"))
        except UnicodeDecodeError as error:
            raise ValueError(f"OCR sidecar is not UTF-8: {path.name}") from error
        inventory.append({
            "source_file": path.name,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "file_bytes": len(payload),
        })
    return pages, corpus_digest(inventory)


def build_corpus_inventory(
    report_dir: Path, selected_files: Set[str]
) -> Tuple[List[Dict[str, Any]], Dict[str, List[str]], str]:
    pdf_files = sorted(
        (path for path in report_dir.iterdir() if path.is_file() and path.suffix.lower() == ".pdf"),
        key=lambda path: unicodedata.normalize("NFC", path.name),
    )
    inventory: List[Dict[str, Any]] = []
    selected_pages: Dict[str, List[str]] = {}
    for path in pdf_files:
        page_count = pdf_page_count(path)
        pages, text_char_count = extract_pdf_pages(path)
        if len(pages) != page_count:
            raise ValueError(
                f"pdftotext page split mismatch for {path.name}: "
                f"{len(pages)} != {page_count}"
            )
        meaningful_count, page_coverage, status = extraction_metrics(pages)
        row = {
            "source_file": path.name,
            "sha256": sha256(path),
            "file_bytes": path.stat().st_size,
            "page_count": page_count,
            "text_char_count": text_char_count,
            "meaningful_text_char_count": meaningful_count,
            "text_page_coverage": page_coverage,
            "extraction_status": status,
            "duplicate_of_source_file": None,
        }
        inventory.append(row)
        if path.name in selected_files:
            selected_pages[path.name] = pages

    by_hash: Dict[str, List[Dict[str, Any]]] = {}
    for row in inventory:
        by_hash.setdefault(row["sha256"], []).append(row)
    for rows in by_hash.values():
        if len(rows) > 1:
            canonical = min(
                rows,
                key=lambda item: (
                    SOURCE_FILE_PATTERN.fullmatch(item["source_file"]).group(3)
                    is not None,
                    unicodedata.normalize("NFC", item["source_file"]),
                ),
            )["source_file"]
            for row in rows:
                if row["source_file"] != canonical:
                    row["duplicate_of_source_file"] = canonical
    return inventory, selected_pages, corpus_digest(inventory)


COUNTRY_NAME_PREFIXES = tuple(sorted({
    "가나", "과테말라", "나이지리아", "네팔", "도미니카", "동티모르",
    "라오스", "모잠비크", "몽골", "미얀마", "방글라데시", "베트남",
    "볼리비아", "세네갈", "스리랑카", "알제리", "에콰도르",
    "에티오피아", "엘살바도르", "요르단", "우간다", "우즈베키스탄",
    "우크라이나", "이라크", "이집트", "인도네시아", "카메룬",
    "캄보디아", "케냐", "코트디부아르", "키르기스스탄", "키르기즈",
    "타지키스탄", "탄자니아", "튀니지", "투르크메니스탄", "파라과이",
    "파키스탄", "페루", "피지", "필리핀",
}, key=len, reverse=True))


def inferred_country(country: Any, project_name: Any) -> str:
    explicit = normalize_text(country)
    if explicit:
        return explicit
    name = normalize_text(project_name)
    for candidate in COUNTRY_NAME_PREFIXES:
        if name.startswith(candidate):
            return candidate
    return "미상"


def canonical_projects(database: Path) -> Dict[str, Dict[str, str]]:
    uri = f"{database.resolve().as_uri()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        rows = connection.execute(
            """SELECT p.project_no, p.country_ko, p.project_name, p.bid_no,
                      p.contract_type, b.construction_candidate
               FROM projects p
               JOIN bids b ON b.bid_no = p.bid_no
               WHERE project_no IS NOT NULL AND trim(project_no) <> ''"""
        ).fetchall()
        reviewed = {
            row[0]: row[1:]
            for row in connection.execute(
                """SELECT project_no, country_ko, project_name
                   FROM area_cost_project_review"""
            )
        }
    candidates: Dict[str, List[Tuple[str, str, str, str, int]]] = {}
    for (
        project_no, country, project_name, bid_no, contract_type,
        construction_candidate,
    ) in rows:
        candidates.setdefault(project_no, []).append(
            (
                normalize_text(country), normalize_text(project_name),
                normalize_text(bid_no), normalize_text(contract_type),
                int(bool(construction_candidate)),
            )
        )
    projects: Dict[str, Dict[str, str]] = {}
    for project_no, options in candidates.items():
        representative = max(
            options,
            key=lambda row: (
                bool(row[0]), bool(row[1]), len(row[1]), row[2]
            ),
        )
        country, project_name = representative[:2]
        if project_no in reviewed:
            country, project_name = reviewed[project_no]
        project_name = normalize_text(project_name)
        projects[project_no] = {
            "project_no": project_no,
            "country_ko": inferred_country(country, project_name),
            "project_name": project_name,
            "in_area_cost_review": int(project_no in reviewed),
            "has_works_contract": int(
                any(row[3] == "공사" for row in options)
            ),
            "has_construction_candidate": int(
                any(row[4] for row in options)
            ),
        }
    return projects


def validate_curation_shape(curation: Dict[str, Any]) -> None:
    if curation.get("schema_version") != "1.2":
        raise ValueError("curation schema_version must be 1.2")
    target = curation.get("target_universe") or {}
    if target.get("table") != "projects":
        raise ValueError("target_universe.table must be projects")
    if target.get("selector") != "distinct_nonempty_project_no":
        raise ValueError(
            "target_universe.selector must be distinct_nonempty_project_no"
        )
    if int(target.get("expected_count", 0)) <= 0:
        raise ValueError("target_universe.expected_count is required")
    corpus = curation.get("corpus") or {}
    if not corpus.get("logical_name") or int(corpus.get("expected_pdf_count", 0)) <= 0:
        raise ValueError("corpus logical_name and expected_pdf_count are required")
    if not SHA256_PATTERN.fullmatch(str(corpus.get("expected_digest", ""))):
        raise ValueError("corpus.expected_digest must be a SHA-256 digest")
    review = curation.get("review") or {}
    require_nonempty(review.get("method"), "review.method", 10)
    validate_partial_date(review.get("screening_completed_at"), "screening_completed_at")
    for key in ("reports", "matches", "findings"):
        if not isinstance(curation.get(key), list):
            raise ValueError(f"curation {key} must be a list")
    official = curation.get("official_source") or {}
    if any(
        row.get("source_kind", LOCAL_SOURCE_KIND) == OFFICIAL_SOURCE_KIND
        for row in curation["reports"]
    ):
        require_nonempty(official.get("logical_name"), "official_source.logical_name")
        if official.get("list_url") != (
            "https://www.koica.go.kr/sites/evaluation_kr/article/list/15/1"
        ):
            raise ValueError("official_source.list_url is not the KOICA evaluation list")
        if int(official.get("screened_post_count", 0)) <= 0:
            raise ValueError("official_source.screened_post_count is required")
        if int(official.get("screened_page_count", 0)) <= 0:
            raise ValueError("official_source.screened_page_count is required")
        if not SHA256_PATTERN.fullmatch(
            str(official.get("screened_index_digest", ""))
        ):
            raise ValueError(
                "official_source.screened_index_digest must be SHA-256"
            )
        require_nonempty(
            official.get("screened_index_digest_algorithm"),
            "official_source.screened_index_digest_algorithm",
        )
        if int(official.get("screened_index_payload_bytes", 0)) <= 0:
            raise ValueError(
                "official_source.screened_index_payload_bytes is required"
            )
        validate_partial_date(
            official.get("screened_at"), "official_source.screened_at"
        )
        snapshot_file = require_nonempty(
            official.get("index_snapshot_file"),
            "official_source.index_snapshot_file",
        )
        if Path(snapshot_file).name != snapshot_file:
            raise ValueError("official index snapshot must be a basename")
        snapshot = validate_official_index_snapshot(
            official.get("index_snapshot") or {}
        )
        snapshot_pairs = (
            ("list_url", "list_url"),
            ("screened_at", "screened_at"),
            ("screened_page_count", "page_count"),
            ("screened_post_count", "post_count"),
            ("screened_index_digest_algorithm", "digest_algorithm"),
            ("screened_index_digest", "digest"),
            ("screened_index_payload_bytes", "payload_bytes"),
        )
        for official_field, snapshot_field in snapshot_pairs:
            if official.get(official_field) != snapshot.get(snapshot_field):
                raise ValueError(
                    "official index snapshot differs: " + official_field
                )
        snapshot_post_ids = {row["post_id"] for row in snapshot["posts"]}
        for report in curation["reports"]:
            if (
                report.get("source_kind", LOCAL_SOURCE_KIND)
                == OFFICIAL_SOURCE_KIND
                and str(report.get("source_post_id")) not in snapshot_post_ids
            ):
                raise ValueError(
                    "official report post is absent from index snapshot: "
                    + str(report.get("report_id"))
                )


def validate_duplicate_reports(reports: List[Dict[str, Any]]) -> None:
    by_id = {row["report_id"]: row for row in reports}
    for row in reports:
        parent = row.get("duplicate_of_report_id")
        if not parent:
            continue
        if parent == row["report_id"] or parent not in by_id:
            raise ValueError(f"invalid duplicate_of_report_id for {row['report_id']}")
        if by_id[parent]["sha256"] != row["sha256"]:
            raise ValueError(f"duplicate reports must have identical SHA-256: {row['report_id']}")
        seen = {row["report_id"]}
        cursor = parent
        while cursor:
            if cursor in seen:
                raise ValueError(f"duplicate report cycle: {row['report_id']}")
            seen.add(cursor)
            cursor = by_id[cursor].get("duplicate_of_report_id")


def numeric_token_present(value_numeric: float, value_text: str) -> bool:
    candidates = {
        str(int(value_numeric)) if float(value_numeric).is_integer() else str(value_numeric),
        f"{value_numeric:,.0f}" if float(value_numeric).is_integer() else f"{value_numeric:,}",
    }
    compact_value = value_text.replace(",", "")
    return any(candidate.replace(",", "") in compact_value for candidate in candidates)


def build_manifest(
    report_dir: Path,
    database: Path,
    curation: Dict[str, Any],
    official_cache_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    validate_tools()
    validate_curation_shape(curation)
    if not report_dir.is_dir():
        raise FileNotFoundError(report_dir)
    if not database.is_file():
        raise FileNotFoundError(database)

    curated_reports = curation["reports"]
    source_files = {row["source_file"] for row in curated_reports}
    if len(source_files) != len(curated_reports):
        raise ValueError("duplicate source_file in curation reports")
    local_curated_reports = [
        row for row in curated_reports
        if row.get("source_kind", LOCAL_SOURCE_KIND) == LOCAL_SOURCE_KIND
    ]
    selected_files = {row["source_file"] for row in local_curated_reports}
    inventory, report_pages, actual_digest = build_corpus_inventory(
        report_dir, selected_files
    )
    expected_count = int(curation["corpus"]["expected_pdf_count"])
    if len(inventory) != expected_count:
        raise ValueError(
            f"corpus count changed: expected {expected_count}, found {len(inventory)}"
        )
    if actual_digest != curation["corpus"]["expected_digest"]:
        raise ValueError(
            "corpus digest changed: "
            f"expected {curation['corpus']['expected_digest']}, found {actual_digest}"
        )
    inventory_by_file = {row["source_file"]: row for row in inventory}
    missing_selected = selected_files - set(report_pages)
    if missing_selected:
        raise FileNotFoundError(f"curated report files missing: {sorted(missing_selected)}")

    project_universe = canonical_projects(database)
    expected_universe_count = int(curation["target_universe"]["expected_count"])
    if len(project_universe) != expected_universe_count:
        raise ValueError(
            f"target universe changed: expected {expected_universe_count}, "
            f"found {len(project_universe)}"
        )

    report_ids: Set[str] = set()
    output_reports: List[Dict[str, Any]] = []
    report_full_text: Dict[str, str] = {}
    report_pages_by_id: Dict[str, List[str]] = {}
    for curated in curated_reports:
        report_id = curated.get("report_id", "")
        source_kind = curated.get("source_kind", LOCAL_SOURCE_KIND)
        local_match = LOCAL_REPORT_ID_PATTERN.fullmatch(report_id)
        official_match = OFFICIAL_REPORT_ID_PATTERN.fullmatch(report_id)
        if source_kind not in {LOCAL_SOURCE_KIND, OFFICIAL_SOURCE_KIND}:
            raise ValueError(f"unsupported source_kind: {source_kind}")
        if (
            (source_kind == LOCAL_SOURCE_KIND and not local_match)
            or (source_kind == OFFICIAL_SOURCE_KIND and not official_match)
            or report_id in report_ids
        ):
            raise ValueError(f"invalid or duplicate report_id: {report_id}")
        report_ids.add(report_id)
        source_file = curated["source_file"]
        if source_kind == LOCAL_SOURCE_KIND:
            source_match = SOURCE_FILE_PATTERN.fullmatch(source_file)
            if not source_match:
                raise ValueError(f"unsupported curated source filename: {source_file}")
            assert local_match is not None
            if (local_match.group(1), local_match.group(2)) != (
                source_match.group(1), source_match.group(2)
            ):
                raise ValueError(
                    f"report_id/source_file mismatch: {report_id} vs {source_file}"
                )
            inventory_row = inventory_by_file[source_file]
            pages = report_pages[source_file]
            source_collection = curation["corpus"]["logical_name"]
            source_document_id = source_match.group(1)
            source_page_url = None
            source_download_url = None
            source_post_id = None
            source_attachment_id = None
            extraction_method = "pdftotext -layout -enc UTF-8"
        else:
            if official_cache_dir is None:
                raise ValueError(
                    "--official-cache-dir is required for official KOICA reports"
                )
            assert official_match is not None
            attachment_id = require_nonempty(
                curated.get("source_attachment_id"),
                f"source_attachment_id:{report_id}",
            )
            post_id = require_nonempty(
                curated.get("source_post_id"), f"source_post_id:{report_id}"
            )
            if official_match.group(1) != attachment_id:
                raise ValueError(f"official report/attachment id mismatch: {report_id}")
            source_page_url = require_nonempty(
                curated.get("source_page_url"), f"source_page_url:{report_id}"
            )
            source_download_url = require_nonempty(
                curated.get("source_download_url"),
                f"source_download_url:{report_id}",
            )
            if source_page_url != OFFICIAL_PAGE_PREFIX + post_id:
                raise ValueError(f"invalid KOICA source page URL: {report_id}")
            if source_download_url != OFFICIAL_DOWNLOAD_PREFIX + attachment_id:
                raise ValueError(f"invalid KOICA download URL: {report_id}")
            cache_file = require_nonempty(
                curated.get("cache_file"), f"cache_file:{report_id}"
            )
            if Path(cache_file).name != cache_file:
                raise ValueError(f"official cache_file must be a basename: {report_id}")
            cache_path = official_cache_dir / cache_file
            if not cache_path.is_file():
                raise FileNotFoundError(cache_path)
            expected_sha256 = str(curated.get("expected_sha256", ""))
            expected_file_bytes = int(curated.get("expected_file_bytes", 0))
            expected_page_count = int(curated.get("expected_page_count", 0))
            if (
                not SHA256_PATTERN.fullmatch(expected_sha256)
                or expected_file_bytes <= 0
                or expected_page_count <= 0
            ):
                raise ValueError(
                    f"official expected file audit is incomplete: {report_id}"
                )
            actual_sha256 = sha256(cache_path)
            actual_file_bytes = cache_path.stat().st_size
            page_count = pdf_page_count(cache_path)
            if (
                actual_sha256 != expected_sha256
                or actual_file_bytes != expected_file_bytes
                or page_count != expected_page_count
            ):
                raise ValueError(
                    "official PDF differs from curated audit: "
                    f"{report_id} expected "
                    f"({expected_sha256}, {expected_file_bytes}, "
                    f"{expected_page_count}) found "
                    f"({actual_sha256}, {actual_file_bytes}, {page_count})"
                )
            pages, text_char_count = extract_pdf_pages(cache_path)
            if len(pages) != page_count:
                raise ValueError(
                    f"pdftotext page split mismatch for {cache_file}: "
                    f"{len(pages)} != {page_count}"
                )
            meaningful_count, page_coverage, extraction_status = (
                extraction_metrics(pages)
            )
            ocr_text_digest = None
            ocr_text_page_count = None
            ocr_text_digest_algorithm = None
            if extraction_status == "ocr_required":
                ocr_cache_dir = require_nonempty(
                    curated.get("ocr_cache_dir"),
                    f"ocr_cache_dir:{report_id}",
                )
                if Path(ocr_cache_dir).name != ocr_cache_dir:
                    raise ValueError(
                        f"official ocr_cache_dir must be a basename: {report_id}"
                    )
                pages, ocr_text_digest = load_ocr_pages(
                    official_cache_dir / ocr_cache_dir, page_count
                )
                expected_ocr_digest = str(
                    curated.get("expected_ocr_text_digest", "")
                )
                if (
                    not SHA256_PATTERN.fullmatch(expected_ocr_digest)
                    or ocr_text_digest != expected_ocr_digest
                ):
                    raise ValueError(
                        f"OCR sidecar differs from curated audit: {report_id}"
                    )
                if int(curated.get("expected_ocr_text_page_count", 0)) != page_count:
                    raise ValueError(
                        f"OCR sidecar page audit differs: {report_id}"
                    )
                text_char_count = sum(len(page) for page in pages)
                meaningful_count, page_coverage, _ = extraction_metrics(pages)
                extraction_status = "ocr_text"
                extraction_method = require_nonempty(
                    curated.get("ocr_extraction_method"),
                    f"ocr_extraction_method:{report_id}",
                    10,
                )
                ocr_text_page_count = len(pages)
                ocr_text_digest_algorithm = OCR_TEXT_DIGEST_ALGORITHM
            inventory_row = {
                "sha256": actual_sha256,
                "file_bytes": actual_file_bytes,
                "page_count": page_count,
                "text_char_count": text_char_count,
                "meaningful_text_char_count": meaningful_count,
                "text_page_coverage": page_coverage,
                "extraction_status": extraction_status,
                "ocr_text_digest": ocr_text_digest,
                "ocr_text_page_count": ocr_text_page_count,
                "ocr_text_digest_algorithm": ocr_text_digest_algorithm,
            }
            source_collection = curation["official_source"]["logical_name"]
            source_document_id = attachment_id
            source_post_id = post_id
            source_attachment_id = attachment_id
            if extraction_status != "ocr_text":
                extraction_method = "pdftotext -layout -enc UTF-8"
        if inventory_row["extraction_status"] == "ocr_required":
            raise ValueError(f"accepted report requires OCR before curation: {source_file}")
        report_title = require_nonempty(curated.get("report_title"), "report_title", 10)
        if "종료평가" not in report_title:
            raise ValueError(f"report title is not an endline evaluation: {report_id}")
        full_text = normalize_text(" ".join(pages))
        if compact_text(report_title) not in compact_text(full_text):
            raise ValueError(f"report_title not found in PDF: {report_id}")
        if curated.get("report_type") != "endline_evaluation":
            raise ValueError(f"report_type must be endline_evaluation: {report_id}")
        publication_date = validate_partial_date(
            curated.get("publication_date"), f"publication_date:{report_id}"
        )
        precision = curated.get("publication_date_precision")
        expected_precision = "day" if publication_date and len(publication_date) == 10 else "month"
        if not publication_date or precision != expected_precision:
            raise ValueError(f"publication date precision mismatch: {report_id}")
        output = {
            "report_id": report_id,
            "source_kind": source_kind,
            "source_collection": source_collection,
            "source_document_id": source_document_id,
            "source_file": source_file,
            "source_page_url": source_page_url,
            "source_download_url": source_download_url,
            "source_post_id": source_post_id,
            "source_attachment_id": source_attachment_id,
            **{key: inventory_row[key] for key in (
                "sha256", "file_bytes", "page_count", "text_char_count",
                "meaningful_text_char_count", "text_page_coverage", "extraction_status",
            )},
            "report_title": report_title,
            "report_type": "endline_evaluation",
            "project_period": require_nonempty(
                curated.get("project_period"), f"project_period:{report_id}", 4
            ),
            "publication_date": publication_date,
            "publication_date_precision": precision,
            "duplicate_of_report_id": curated.get("duplicate_of_report_id"),
            "extraction_method": extraction_method,
            "ocr_text_digest": inventory_row.get("ocr_text_digest"),
            "ocr_text_page_count": inventory_row.get("ocr_text_page_count"),
            "ocr_text_digest_algorithm": inventory_row.get(
                "ocr_text_digest_algorithm"
            ),
        }
        output_reports.append(output)
        report_full_text[report_id] = full_text
        report_pages_by_id[report_id] = pages
    validate_duplicate_reports(output_reports)

    match_ids: Set[str] = set()
    report_match_counts = {report_id: 0 for report_id in report_ids}
    output_matches: List[Dict[str, Any]] = []
    multi_project_reports = set(curation.get("multi_project_report_ids", []))
    for curated in curation["matches"]:
        match_id = require_nonempty(curated.get("match_id"), "match_id", 5)
        if match_id in match_ids:
            raise ValueError(f"duplicate match_id: {match_id}")
        match_ids.add(match_id)
        report_id = curated.get("report_id")
        if report_id not in report_ids:
            raise ValueError(f"unknown report_id in match: {report_id}")
        project_no = curated.get("project_no")
        if project_no not in project_universe:
            raise ValueError(f"project outside target universe: {project_no}")
        canonical = project_universe[project_no]
        if curated.get("db_country") != canonical["country_ko"]:
            raise ValueError(f"db_country differs from canonical review row: {project_no}")
        if curated.get("db_project_name") != canonical["project_name"]:
            raise ValueError(f"db_project_name differs from canonical review row: {project_no}")
        report_project_name = require_nonempty(
            curated.get("report_project_name"), "report_project_name", 8
        )
        if compact_text(report_project_name) not in compact_text(report_full_text[report_id]):
            raise ValueError(f"report_project_name not found in PDF: {match_id}")
        match_method = curated.get("match_method")
        relation_scope = curated.get("relation_scope")
        if match_method not in ALLOWED_MATCH_METHODS:
            raise ValueError(f"invalid match_method: {match_id}")
        if relation_scope not in ALLOWED_RELATION_SCOPES:
            raise ValueError(f"invalid relation_scope: {match_id}")
        score = float(curated.get("match_score", -1))
        if not math.isfinite(score) or not MIN_ACCEPTED_MATCH_SCORE <= score <= 1:
            raise ValueError(f"accepted match_score below threshold: {match_id}")
        if curated.get("review_status") != "accepted":
            raise ValueError(f"only accepted matches may be ingested: {match_id}")
        reviewed_at = validate_partial_date(
            curated.get("reviewed_at"), f"reviewed_at:{match_id}"
        )
        if not reviewed_at or len(reviewed_at) != 10:
            raise ValueError(f"reviewed_at must be a full date: {match_id}")
        output = dict(curated)
        output["match_score"] = score
        output["match_basis"] = require_nonempty(
            curated.get("match_basis"), f"match_basis:{match_id}", 20
        )
        output_matches.append(output)
        report_match_counts[report_id] += 1
        if report_match_counts[report_id] > 1 and report_id not in multi_project_reports:
            raise ValueError(f"report matched more than once without override: {report_id}")
    unused_reports = sorted(report_id for report_id, count in report_match_counts.items() if count == 0)
    if unused_reports:
        raise ValueError(f"curated reports without accepted matches: {unused_reports}")

    match_by_id = {row["match_id"]: row for row in output_matches}
    finding_ids: Set[str] = set()
    findings_per_match = {match_id: 0 for match_id in match_ids}
    semantic_keys: Set[Tuple[Any, ...]] = set()
    output_findings: List[Dict[str, Any]] = []
    for curated in curation["findings"]:
        finding_id = require_nonempty(curated.get("finding_id"), "finding_id", 5)
        if finding_id in finding_ids:
            raise ValueError(f"duplicate finding_id: {finding_id}")
        finding_ids.add(finding_id)
        match_id = curated.get("match_id")
        if match_id not in match_by_id:
            raise ValueError(f"unknown match_id in finding: {match_id}")
        field_code = curated.get("field_code")
        definition = FIELD_DEFINITIONS.get(field_code)
        if not definition or curated.get("category") != definition["category"]:
            raise ValueError(f"field/category mismatch: {finding_id}")
        summary = require_nonempty(curated.get("summary_text"), "summary_text", 15)
        if len(summary) > 600:
            raise ValueError(f"summary_text too long: {finding_id}")
        match_row = match_by_id[match_id]
        report_id = match_row["report_id"]
        report_row = next(row for row in output_reports if row["report_id"] == report_id)
        page_start = int(curated.get("pdf_page_start", 0))
        page_end = int(curated.get("pdf_page_end", page_start))
        if not 1 <= page_start <= page_end <= report_row["page_count"]:
            raise ValueError(f"finding page outside report: {finding_id}")
        excerpt = normalize_text(curated.get("evidence_excerpt"))
        if not 20 <= len(excerpt) <= 400:
            raise ValueError(f"evidence excerpt length invalid: {finding_id}")
        page_text = normalize_text(
            " ".join(report_pages_by_id[report_id][page_start - 1 : page_end])
        )
        if excerpt not in page_text:
            raise ValueError(f"evidence excerpt not found on PDF page(s): {finding_id}")
        value_text = normalize_text(curated.get("value_text")) or None
        if value_text and value_text not in excerpt:
            raise ValueError(f"value_text not found in evidence excerpt: {finding_id}")
        value_numeric = curated.get("value_numeric")
        unit = curated.get("unit")
        if value_numeric is not None:
            if isinstance(value_numeric, bool) or not isinstance(value_numeric, (int, float)):
                raise ValueError(f"value_numeric must be a real number: {finding_id}")
            value_numeric = float(value_numeric)
            if not math.isfinite(value_numeric) or not value_text:
                raise ValueError(f"invalid numeric evidence: {finding_id}")
            if not numeric_token_present(value_numeric, value_text):
                raise ValueError(f"numeric value not represented in value_text: {finding_id}")
        allowed_units = set(definition.get("units", []))
        if unit is not None and unit not in allowed_units:
            raise ValueError(f"invalid unit for {field_code}: {finding_id}")
        if (value_numeric is None) != (unit is None):
            raise ValueError(f"numeric value and unit must be provided together: {finding_id}")
        if curated.get("confidence") not in ALLOWED_CONFIDENCE:
            raise ValueError(f"invalid confidence: {finding_id}")
        if curated.get("review_status") != "accepted":
            raise ValueError(f"finding must be accepted: {finding_id}")
        if curated.get("public_excerpt_approved") is not True:
            raise ValueError(f"public excerpt approval required: {finding_id}")
        semantic_key = (match_id, field_code, page_start, page_end, summary)
        if semantic_key in semantic_keys:
            raise ValueError(f"semantic duplicate finding: {finding_id}")
        semantic_keys.add(semantic_key)
        output = dict(curated)
        output.update(
            {
                "summary_text": summary,
                "value_text": value_text,
                "value_numeric": value_numeric,
                "pdf_page_start": page_start,
                "pdf_page_end": page_end,
                "evidence_excerpt": excerpt,
            }
        )
        output_findings.append(output)
        findings_per_match[match_id] += 1
    empty_matches = sorted(match_id for match_id, count in findings_per_match.items() if count == 0)
    if empty_matches:
        raise ValueError(f"accepted matches without findings: {empty_matches}")

    matched_project_reports: Dict[str, List[str]] = {}
    for row in output_matches:
        matched_project_reports.setdefault(row["project_no"], []).append(row["report_id"])
    excluded_notes: Dict[str, List[str]] = {}
    for decision in curation["review"].get("excluded_candidates", []):
        project_no = normalize_text(decision.get("candidate_project_no"))
        reason = normalize_text(decision.get("reason"))
        if project_no in project_universe and reason:
            excluded_notes.setdefault(project_no, []).append(reason)
    screening = []
    for project_no, project in sorted(project_universe.items()):
        report_ids_for_project = sorted(matched_project_reports.get(project_no, []))
        if report_ids_for_project:
            screening_status = "accepted_match"
        elif project_no in excluded_notes:
            screening_status = "candidate_reviewed_not_accepted"
        else:
            screening_status = "no_accepted_same_project_report"
        screening.append(
            {
                **project,
                "manual_construction_relevance": int(bool(report_ids_for_project)),
                "status": screening_status,
                "report_ids": report_ids_for_project,
                "note": (
                    "동일 사업 종료평가 매칭을 채택함"
                    if report_ids_for_project
                    else (
                        "종료평가 후보를 검토했으나 미채택: "
                        + " | ".join(excluded_notes[project_no])
                        if project_no in excluded_notes
                        else "이 코퍼스와 공식 목록에서 동일 사업 종료평가 매칭을 채택하지 않음; 보고서 부재를 의미하지 않음"
                    )
                ),
            }
        )

    duplicate_file_count = sum(bool(row["duplicate_of_source_file"]) for row in inventory)
    manifest = {
        "schema_version": "1.2",
        "curation_digest_algorithm": "sha256(canonical merged JSON)",
        "curation_digest": canonical_json_digest(curation),
        "target_universe": {
            **curation["target_universe"],
            "actual_count": len(project_universe),
            "in_area_cost_review_count": sum(
                row["in_area_cost_review"] for row in project_universe.values()
            ),
            "has_works_contract_count": sum(
                row["has_works_contract"] for row in project_universe.values()
            ),
            "has_construction_candidate_count": sum(
                row["has_construction_candidate"]
                for row in project_universe.values()
            ),
        },
        "corpus": {
            "logical_name": curation["corpus"]["logical_name"],
            "pdf_count": len(inventory),
            "digest_algorithm": "sha256(filename_nfc NUL sha256 NUL bytes LF)",
            "digest": actual_digest,
            "raw_pdfs_included": False,
            "duplicate_physical_file_count": duplicate_file_count,
            "ocr_required_file_count": sum(
                row["extraction_status"] == "ocr_required" for row in inventory
            ),
            "selected_report_count": len(output_reports),
            "selected_local_report_count": sum(
                row["source_kind"] == LOCAL_SOURCE_KIND for row in output_reports
            ),
            "selected_official_report_count": sum(
                row["source_kind"] == OFFICIAL_SOURCE_KIND for row in output_reports
            ),
            "accepted_match_count": len(output_matches),
            "matched_project_count": len(matched_project_reports),
            "no_accepted_match_project_count": len(project_universe) - len(matched_project_reports),
            "inventory": inventory,
        },
        "official_source": {
            **curation.get("official_source", {}),
            "raw_pdfs_included": False,
            "selected_report_count": sum(
                row["source_kind"] == OFFICIAL_SOURCE_KIND for row in output_reports
            ),
        },
        "review": curation["review"],
        "field_definitions": [
            {"field_code": code, **definition}
            for code, definition in sorted(FIELD_DEFINITIONS.items())
        ],
        "project_screening": screening,
        "reports": output_reports,
        "matches": output_matches,
        "findings": output_findings,
        "counts": {
            "field_definitions": len(FIELD_DEFINITIONS),
            "reports": len(output_reports),
            "matches": len(output_matches),
            "findings": len(output_findings),
        },
    }
    payload = json.dumps(manifest, ensure_ascii=False, sort_keys=True)
    if str(report_dir) in payload or re.search(r'"source_file":\s*"/', payload):
        raise ValueError("absolute source path leaked into manifest")
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--curation", type=Path, default=DEFAULT_CURATION)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--official-cache-dir", type=Path,
        help="directory containing hash-audited KOICA official PDF downloads",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="validate the corpus and curation without writing the manifest",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    curation = load_curation(args.curation)
    manifest = build_manifest(
        args.report_dir, args.database, curation, args.official_cache_dir
    )
    if not args.check:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(args.output)
    print(
        json.dumps(
            {
                "output": None if args.check else str(args.output),
                "corpus_pdf_count": manifest["corpus"]["pdf_count"],
                "corpus_digest": manifest["corpus"]["digest"],
                "matched_project_count": manifest["corpus"]["matched_project_count"],
                **manifest["counts"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
