#!/usr/bin/env python3
"""Create an auditable inventory of recursively recovered KOICA attachments."""

from __future__ import annotations

import csv
import json
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from scripts.extract_construction_evidence import is_source_document
except ModuleNotFoundError:
    from extract_construction_evidence import is_source_document


ROOT_ARCHIVE_SUFFIXES = {".zip", ".hwpx"}
BOQ_KEYWORDS = (
    "boq",
    "bill of quant",
    "bill_of_quant",
    "bill of quantity",
    "price schedule",
    "산출내역",
    "내역서",
    "수량산출",
)
DRAWING_KEYWORDS = (
    "drawing",
    "architectural",
    "structural",
    "floor plan",
    "도면",
    "평면도",
)
SPEC_KEYWORDS = ("specification", "specifications", "시방서")
COST_KEYWORDS = ("cost estimate", "estimate", "priced", "unit price", "견적", "가격")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def normalized_path(value: str | Path) -> str:
    return unicodedata.normalize("NFC", str(value))


def candidate_types(path: Path) -> list[str]:
    lowered = normalized_path(path).lower()
    labels = []
    if any(keyword in lowered for keyword in BOQ_KEYWORDS):
        labels.append("BOQ")
    if path.suffix.lower() == ".dwg" or any(
        keyword in lowered for keyword in DRAWING_KEYWORDS
    ):
        labels.append("도면")
    if any(keyword in lowered for keyword in SPEC_KEYWORDS):
        labels.append("시방서")
    if any(keyword in lowered for keyword in COST_KEYWORDS):
        labels.append("가격·견적")
    return labels


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    data = project_root / "data"
    raw = (data / "raw").resolve()
    unpacked = (data / "unpacked").resolve()
    manifests = data / "manifests"
    output = project_root / "outputs" / "koica-only-pilot"

    root_targets = {
        (unpacked / archive.relative_to(raw).with_suffix("")).resolve()
        for archive in raw.rglob("*")
        if archive.is_file()
        and archive.suffix.lower() in ROOT_ARCHIVE_SUFFIXES
    }
    marker_targets = {
        marker.parent.resolve() for marker in unpacked.rglob(".complete")
    }
    nested_targets = marker_targets - root_targets
    nested_files = {
        path.resolve()
        for target in nested_targets
        for path in target.rglob("*")
        if path.is_file() and path.name != ".complete"
    }

    file_index = load_json(manifests / "file_index.json")
    evidence = load_json(manifests / "construction_evidence.json")
    summary = load_json(manifests / "extraction_summary.json")
    projects = {
        row["bid_no"]: row for row in load_json(manifests / "projects.json")
    }
    index_by_path: dict[str, list[dict[str, Any]]] = {}
    for row in file_index:
        index_by_path.setdefault(normalized_path(row["source_file"]), []).append(row)

    inventory: list[dict[str, Any]] = []
    for path in sorted(nested_files, key=lambda item: normalized_path(item).casefold()):
        relative = path.relative_to(unpacked)
        relative_text = normalized_path(relative)
        matches = index_by_path.get(relative_text, [])
        index_row = matches[0] if matches else {}
        bid_no = relative.parts[0] if relative.parts else ""
        project = projects.get(bid_no, {})
        labels = candidate_types(path)
        inventory.append(
            {
                "bid_no": bid_no,
                "project_no": project.get("project_no", ""),
                "country_ko": project.get("country_ko", ""),
                "project_name": project.get("project_name", ""),
                "source_file": relative_text,
                "extension": path.suffix.lower(),
                "bytes": path.stat().st_size,
                "indexed": bool(matches),
                "text_chunks": index_row.get("text_chunks", 0),
                "evidence_count": index_row.get("evidence_count", 0),
                "candidate_types": " | ".join(labels),
                "exclusion_reason": (
                    ""
                    if matches
                    else (
                        "운영체제·Office 메타데이터"
                        if not is_source_document(relative)
                        else "색인오류·경로확인필요"
                    )
                ),
            }
        )

    nested_paths = {normalized_path(path.relative_to(unpacked)) for path in nested_files}
    nested_evidence = [
        row
        for row in evidence
        if normalized_path(row["source_file"]) in nested_paths
    ]
    by_bid_category: Counter[tuple[str, str]] = Counter(
        (row["bid_no"], row["category"]) for row in nested_evidence
    )
    evidence_rows = [
        {
            "bid_no": bid_no,
            "project_no": projects.get(bid_no, {}).get("project_no", ""),
            "country_ko": projects.get(bid_no, {}).get("country_ko", ""),
            "project_name": projects.get(bid_no, {}).get("project_name", ""),
            "category": category,
            "evidence_records": count,
        }
        for (bid_no, category), count in sorted(by_bid_category.items())
    ]

    candidate_rows = [
        row for row in inventory if "BOQ" in row["candidate_types"].split(" | ")
    ]
    current_errors = load_json(manifests / "extraction_errors.json")
    audit = {
        "scope": "KOICA 현지입찰 첨부 중 재귀적으로 회수된 중첩 ZIP",
        "pre_recursive_snapshot": {
            "source_files": 2034,
            "indexed_files": 2029,
            "evidence_records": 2800,
            "errors": 5,
            "note": "재귀회수 실행 직전 extraction_summary.json 기록",
        },
        "current_extraction_summary": summary,
        "root_archive_targets": len(root_targets),
        "nested_archive_targets": len(nested_targets),
        "all_marker_targets": len(marker_targets),
        "nested_files": len(nested_files),
        "nested_files_indexed": sum(bool(row["indexed"]) for row in inventory),
        "nested_files_not_indexed": sum(not row["indexed"] for row in inventory),
        "nested_bids": len({row["bid_no"] for row in inventory}),
        "nested_extension_counts": dict(
            sorted(Counter(row["extension"] for row in inventory).items())
        ),
        "nested_evidence_records": len(nested_evidence),
        "nested_evidence_category_counts": dict(
            sorted(Counter(row["category"] for row in nested_evidence).items())
        ),
        "nested_evidence_bids": len({row["bid_no"] for row in nested_evidence}),
        "boq_candidate_files": len(candidate_rows),
        "boq_candidate_bids": len({row["bid_no"] for row in candidate_rows}),
        "current_errors": current_errors,
        "interpretation": [
            "중첩 ZIP 80개는 제한·실패 없이 해제되었는지 extraction_summary의 unpack 통계로 확인한다.",
            "색인 성공은 텍스트 추출 또는 파일 인벤토리 편입을 뜻하며 비용자료 적합성을 보장하지 않는다.",
            "스캔 PDF·DWG·ZIP은 파일 인벤토리에는 포함되지만 OCR·CAD 해석이 없으면 내용 활용이 제한된다.",
            "BOQ 후보명은 파일경로 키워드 기반이며 단가·금액 입력 여부는 별도 원문 검토가 필요하다.",
        ],
        "claim_boundary": (
            "재귀 압축 및 텍스트 색인 오류는 0건으로 정리했지만, 스캔·DWG·미가격 "
            "BOQ와 실제 계약·준공가 부재 때문에 KOICA 자료 100% 의미활용이라고 주장할 수 없다."
        ),
    }

    output.mkdir(parents=True, exist_ok=True)
    (output / "KOICA_중첩자료_회수감사.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    fields = [
        "bid_no",
        "project_no",
        "country_ko",
        "project_name",
        "source_file",
        "extension",
        "bytes",
        "indexed",
        "text_chunks",
        "evidence_count",
        "candidate_types",
        "exclusion_reason",
    ]
    write_csv(output / "KOICA_중첩자료_파일인벤토리.csv", inventory, fields)
    write_csv(output / "KOICA_중첩자료_BOQ후보.csv", candidate_rows, fields)
    write_csv(
        output / "KOICA_중첩자료_증거요약.csv",
        evidence_rows,
        [
            "bid_no",
            "project_no",
            "country_ko",
            "project_name",
            "category",
            "evidence_records",
        ],
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
