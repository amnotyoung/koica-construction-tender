#!/usr/bin/env python3
"""Extract auditable construction evidence from downloaded KOICA attachments."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import struct
import subprocess
import tempfile
import unicodedata
import zipfile
import zlib
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import olefile
from docx import Document
from openpyxl import load_workbook
from pptx import Presentation
import xlrd


COUNTRIES = {
    "가나": "Ghana", "과테말라": "Guatemala", "네팔": "Nepal",
    "도미니카": "Dominican Republic", "라오스": "Laos", "르완다": "Rwanda",
    "모로코": "Morocco", "몽골": "Mongolia", "미얀마": "Myanmar",
    "방글라데시": "Bangladesh", "베트남": "Vietnam", "볼리비아": "Bolivia",
    "세네갈": "Senegal", "스리랑카": "Sri Lanka", "알제리": "Algeria",
    "에콰도르": "Ecuador", "에티오피아": "Ethiopia", "엘살바도르": "El Salvador",
    "요르단": "Jordan", "우간다": "Uganda", "우즈베키스탄": "Uzbekistan",
    "이라크": "Iraq", "인도네시아": "Indonesia", "잠비아": "Zambia",
    "캄보디아": "Cambodia", "케냐": "Kenya", "콜롬비아": "Colombia",
    "키르기즈": "Kyrgyzstan", "타지키스탄": "Tajikistan", "탄자니아": "Tanzania",
    "튀니지": "Tunisia", "파라과이": "Paraguay", "파키스탄": "Pakistan",
    "팔레스타인": "Palestine", "페루": "Peru", "필리핀": "Philippines",
    "온두라스": "Honduras", "코트디부아르": "Côte d’Ivoire",
    "카메룬": "Cameroon", "모잠비크": "Mozambique", "말라위": "Malawi",
    "짐바브웨": "Zimbabwe", "동티모르": "Timor-Leste", "피지": "Fiji",
    "솔로몬": "Solomon Islands", "부탄": "Bhutan", "조지아": "Georgia",
}

FACILITIES = {
    "병원": ("병원", "의료원", "보건소", "health center", "hospital", "clinic"),
    "학교·교육시설": ("학교", "교실", "교육센터", "school", "classroom", "training center"),
    "실험실·연구시설": ("실험실", "연구소", "laboratory", "lab "),
    "정부·행정시설": ("청사", "경찰", "행정", "government", "police"),
    "농업시설": ("농장", "농업", "관개", "farm", "agricultur", "irrigation"),
    "상하수·환경시설": ("정수", "하수", "폐기물", "water treatment", "waste"),
    "산업·직업훈련시설": ("직업훈련", "기술교육", "산업", "vocational", "technical center"),
}

CATEGORY_KEYWORDS = {
    "연면적·면적": (
        "연면적", "건축면적", "대지면적", "floor area", "gross area",
        "built-up area", "building area", "square meter", "m²", "㎡",
    ),
    "공사비": (
        "공사비", "건축비", "시공비", "construction cost", "works cost",
        "contract amount", "contract price", "bill of quantities", "boq",
    ),
    "설계비": ("설계비", "design fee", "design cost", "consultancy fee"),
    "감리·CM비": (
        "감리비", "감리용역", "supervision fee", "supervision cost",
        "construction management", "cm fee", "bureau de control",
    ),
    "총사업비·예산": (
        "총사업비", "사업비", "예산", "집행한도", "estimated cost",
        "project budget", "total budget", "ceiling amount",
    ),
    "부가세·예비비": (
        "부가가치세", "vat", "tax", "예비비", "contingency", "reserve",
    ),
    "기간": (
        "공사기간", "용역기간", "construction period", "completion period",
        "duration", "calendar days", "months",
    ),
}

AREA_RE = re.compile(
    r"(?<![\w.])(\d[\d,. ]{0,18})\s*(m(?:2|²)|sq\.?\s*m|square\s*met(?:er|re)s?|㎡)",
    re.I,
)
CURRENCY_RE = re.compile(
    r"(?:(USD|US\$|\$|EUR|€|KRW|원|KES|UGX|RWF|XOF|XAF|PKR|PEN|"
    r"IDR|VND|MNT|IQD|DZD|ETB|GHS|TZS|ZMW|MAD|JOD|NPR|BDT)\s*)"
    r"(\d[\d,.\s]{1,22})(?:\s*(million|billion|백만|천))?"
    r"|(\d[\d,.\s]{1,22})\s*"
    r"(USD|US\$|\$|EUR|€|KRW|원|KES|UGX|RWF|XOF|XAF|PKR|PEN|"
    r"IDR|VND|MNT|IQD|DZD|ETB|GHS|TZS|ZMW|MAD|JOD|NPR|BDT)",
    re.I,
)
PERCENT_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*%")


def clean_text(value: Any) -> str:
    text = unicodedata.normalize("NFC", str(value or ""))
    text = text.replace("\x00", " ")
    return re.sub(r"\s+", " ", text).strip()


def safe_member_path(name: str) -> Path | None:
    path = Path(unicodedata.normalize("NFC", name.replace("\\", "/")))
    if path.is_absolute() or ".." in path.parts:
        return None
    return path


def unpack_archives(raw_dir: Path, unpacked_dir: Path) -> dict[str, int]:
    stats = Counter()
    for archive in raw_dir.rglob("*"):
        if not archive.is_file() or archive.suffix.lower() not in {".zip", ".hwpx"}:
            continue
        rel = archive.relative_to(raw_dir)
        target = unpacked_dir / rel.with_suffix("")
        marker = target / ".complete"
        if marker.exists():
            stats["reused"] += 1
            continue
        try:
            with zipfile.ZipFile(archive) as zf:
                members = zf.infolist()
                if len(members) > 5000:
                    raise ValueError("archive has more than 5,000 members")
                total = sum(item.file_size for item in members)
                if total > 2_000_000_000:
                    raise ValueError("archive expands beyond 2 GB")
                target.mkdir(parents=True, exist_ok=True)
                for item in members:
                    member = safe_member_path(item.filename)
                    if member is None or item.is_dir():
                        continue
                    destination = target / member
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(item) as src, destination.open("wb") as dst:
                        shutil.copyfileobj(src, dst)
            marker.touch()
            stats["unpacked"] += 1
        except Exception:
            stats["failed"] += 1
    return dict(stats)


def hwp_chunks(path: Path) -> list[tuple[str, str]]:
    chunks: list[tuple[str, str]] = []
    with olefile.OleFileIO(path) as ole:
        header = ole.openstream("FileHeader").read()
        compressed = bool(struct.unpack("<I", header[36:40])[0] & 1)
        sections = sorted(
            name for name in ole.listdir() if name and name[0] == "BodyText"
        )
        para_no = 0
        for stream_name in sections:
            data = ole.openstream(stream_name).read()
            if compressed:
                data = zlib.decompress(data, -15)
            offset = 0
            while offset + 4 <= len(data):
                record = struct.unpack("<I", data[offset : offset + 4])[0]
                offset += 4
                tag_id = record & 0x3FF
                size = (record >> 20) & 0xFFF
                if size == 0xFFF:
                    size = struct.unpack("<I", data[offset : offset + 4])[0]
                    offset += 4
                payload = data[offset : offset + size]
                offset += size
                if tag_id == 67:
                    para_no += 1
                    text = clean_text(payload.decode("utf-16le", errors="ignore"))
                    if text:
                        chunks.append((f"문단 {para_no}", text))
    return chunks


def pdf_chunks(path: Path) -> list[tuple[str, str]]:
    result = subprocess.run(
        ["pdftotext", "-layout", str(path), "-"],
        check=False,
        capture_output=True,
        timeout=180,
    )
    text = result.stdout.decode("utf-8", errors="replace")
    return [
        (f"페이지 {index}", clean_text(page))
        for index, page in enumerate(text.split("\f"), 1)
        if clean_text(page)
    ]


def docx_chunks(path: Path) -> list[tuple[str, str]]:
    doc = Document(path)
    chunks = [
        (f"문단 {i}", clean_text(p.text))
        for i, p in enumerate(doc.paragraphs, 1)
        if clean_text(p.text)
    ]
    for table_no, table in enumerate(doc.tables, 1):
        for row_no, row in enumerate(table.rows, 1):
            value = clean_text(" | ".join(cell.text for cell in row.cells))
            if value:
                chunks.append((f"표 {table_no} 행 {row_no}", value))
    return chunks


def xlsx_chunks(path: Path) -> list[tuple[str, str]]:
    workbook = load_workbook(path, read_only=True, data_only=False)
    chunks: list[tuple[str, str]] = []
    try:
        for sheet in workbook.worksheets:
            for row_number, row in enumerate(sheet.iter_rows(), 1):
                values = [
                    f"{cell.coordinate}={clean_text(cell.value)}"
                    for cell in row
                    if cell.value not in (None, "")
                ]
                if values:
                    chunks.append((f"{sheet.title}!{row_number}", " | ".join(values)))
    finally:
        workbook.close()
    return chunks


def xls_chunks(path: Path) -> list[tuple[str, str]]:
    workbook = xlrd.open_workbook(path, on_demand=True)
    chunks: list[tuple[str, str]] = []
    try:
        for sheet in workbook.sheets():
            for row_number in range(sheet.nrows):
                values = []
                for column_number in range(sheet.ncols):
                    value = clean_text(sheet.cell_value(row_number, column_number))
                    if value:
                        values.append(f"R{row_number + 1}C{column_number + 1}={value}")
                if values:
                    chunks.append((f"{sheet.name}!{row_number + 1}", " | ".join(values)))
    finally:
        workbook.release_resources()
    return chunks


def pptx_chunks(path: Path) -> list[tuple[str, str]]:
    presentation = Presentation(path)
    chunks: list[tuple[str, str]] = []
    for slide_number, slide in enumerate(presentation.slides, 1):
        values = []
        for shape in slide.shapes:
            if hasattr(shape, "text") and clean_text(shape.text):
                values.append(clean_text(shape.text))
            if getattr(shape, "has_table", False):
                for row in shape.table.rows:
                    values.append(clean_text(" | ".join(cell.text for cell in row.cells)))
        if values:
            chunks.append((f"슬라이드 {slide_number}", " | ".join(values)))
    return chunks


def legacy_doc_chunks(path: Path) -> list[tuple[str, str]]:
    with tempfile.TemporaryDirectory(prefix="koica-doc-") as temp:
        output = Path(temp) / "converted.txt"
        result = subprocess.run(
            ["textutil", "-convert", "txt", "-output", str(output), str(path)],
            check=False,
            capture_output=True,
            timeout=180,
        )
        if result.returncode or not output.exists():
            raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))
        text = output.read_text(encoding="utf-8", errors="replace")
    return [
        (f"문단 {index}", clean_text(paragraph))
        for index, paragraph in enumerate(re.split(r"\n\s*\n", text), 1)
        if clean_text(paragraph)
    ]


def xml_chunks(path: Path) -> list[tuple[str, str]]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    text = clean_text(re.sub(r"<[^>]+>", " ", raw))
    return [("본문", text)] if text else []


def extract_chunks(path: Path) -> list[tuple[str, str]]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return pdf_chunks(path)
    if suffix == ".docx":
        return docx_chunks(path)
    if suffix in {".xlsx", ".xlsm"}:
        return xlsx_chunks(path)
    if suffix == ".xls":
        return xls_chunks(path)
    if suffix == ".pptx":
        return pptx_chunks(path)
    if suffix == ".doc":
        return legacy_doc_chunks(path)
    if suffix == ".hwp":
        return hwp_chunks(path)
    if suffix in {".txt", ".csv", ".xml", ".html", ".htm"}:
        return xml_chunks(path)
    return []


def find_country(text: str) -> tuple[str, str]:
    lowered = text.lower()
    for korean, english in COUNTRIES.items():
        if korean in text or english.lower() in lowered:
            return korean, english
    return "", ""


def classify_facility(text: str) -> str:
    lowered = text.lower()
    for label, keywords in FACILITIES.items():
        if any(keyword in lowered for keyword in keywords):
            return label
    return "기타·미분류"


def classify_work(text: str) -> str:
    lowered = text.lower()
    if any(k in lowered for k in ("리모델링", "개보수", "보수", "renovation", "rehabilitation")):
        return "리모델링·개보수"
    if any(k in lowered for k in ("증축", "extension", "expansion")):
        return "증축"
    if any(k in lowered for k in ("신축", "건립", "new construction", "construction of")):
        return "신축"
    return "미분류"


def numeric_tokens(text: str) -> dict[str, list[str]]:
    return {
        "areas": [clean_text(" ".join(m.groups(default=""))) for m in AREA_RE.finditer(text)],
        "currencies": [
            clean_text(" ".join(m.groups(default=""))) for m in CURRENCY_RE.finditer(text)
        ],
        "percentages": [m.group(0) for m in PERCENT_RE.finditer(text)],
    }


def evidence_from_chunks(
    bid_no: str, source_path: Path, chunks: Iterable[tuple[str, str]], root: Path
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    relative = str(source_path.relative_to(root))
    for locator, text in chunks:
        lowered = text.lower()
        tokens = numeric_tokens(text)
        if not any(tokens.values()):
            continue
        for category, keywords in CATEGORY_KEYWORDS.items():
            matched = [keyword for keyword in keywords if keyword in lowered]
            if not matched:
                continue
            if category == "연면적·면적" and not tokens["areas"]:
                continue
            if category in {"공사비", "설계비", "감리·CM비", "총사업비·예산"} and not tokens["currencies"]:
                continue
            records.append(
                {
                    "bid_no": bid_no,
                    "category": category,
                    "matched_keywords": ", ".join(matched[:5]),
                    "area_mentions": " | ".join(tokens["areas"][:8]),
                    "currency_mentions": " | ".join(tokens["currencies"][:8]),
                    "percentage_mentions": " | ".join(tokens["percentages"][:8]),
                    "source_file": relative,
                    "source_locator": locator,
                    "evidence_text": text[:1200],
                    "review_status": "자동추출·검토필요",
                }
            )
    return records


def project_rows(details: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for bid_no, detail in sorted(details.items(), reverse=True):
        fields = detail.get("fields", {})
        combined = " ".join(
            (
                fields.get("사업명", ""),
                fields.get("입찰명(국문)", ""),
                fields.get("입찰명(영문)", ""),
            )
        )
        country_ko, country_en = find_country(combined)
        rows.append(
            {
                "bid_no": bid_no,
                "project_no": fields.get("사업번호", ""),
                "country_ko": country_ko,
                "country_en": country_en,
                "region": "",
                "project_name": fields.get("사업명", ""),
                "bid_title_ko": fields.get("입찰명(국문)", ""),
                "bid_title_en": fields.get("입찰명(영문)", ""),
                "facility_type": classify_facility(combined),
                "work_type": classify_work(combined),
                "contract_type": fields.get("계약구분", ""),
                "contract_method": fields.get("계약방법", ""),
                "selection_method": fields.get("낙찰자 선정방식", ""),
                "ceiling_usd_raw": fields.get("집행한도금액(달러)", ""),
                "ceiling_krw_raw": fields.get("집행한도금액(원)", ""),
                "notice_date": fields.get("공고일자", ""),
                "detail_url": detail.get("detail_url", ""),
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--max-files", type=int)
    args = parser.parse_args()
    data = args.data.resolve()
    raw = data / "raw"
    unpacked = data / "unpacked"
    manifests = data / "manifests"
    unpack_stats = unpack_archives(raw, unpacked)
    details = json.loads((manifests / "details.json").read_text(encoding="utf-8"))

    sources: list[tuple[str, Path, Path]] = []
    for root in (raw, unpacked):
        for path in root.rglob("*"):
            if not path.is_file() or path.name == ".complete":
                continue
            rel = path.relative_to(root)
            if not rel.parts:
                continue
            # Office lock files and hidden metadata are not source documents.
            if any(part.startswith(".") or part.startswith("~$") for part in rel.parts):
                continue
            sources.append((rel.parts[0], path, root))
    if args.max_files:
        sources = sources[: args.max_files]

    evidence: list[dict[str, Any]] = []
    file_index: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for index, (bid_no, path, root) in enumerate(sources, 1):
        try:
            chunks = extract_chunks(path)
            found = evidence_from_chunks(bid_no, path, chunks, root)
            evidence.extend(found)
            file_index.append(
                {
                    "bid_no": bid_no,
                    "source_file": str(path.relative_to(root)),
                    "extension": path.suffix.lower(),
                    "bytes": path.stat().st_size,
                    "text_chunks": len(chunks),
                    "evidence_count": len(found),
                }
            )
        except Exception as exc:
            errors.append(
                {
                    "bid_no": bid_no,
                    "source_file": str(path.relative_to(root)),
                    "error": str(exc),
                }
            )
        if index % 100 == 0:
            print(f"files {index}/{len(sources)} evidence={len(evidence)}", flush=True)

    outputs = {
        "projects.json": project_rows(details),
        "construction_evidence.json": evidence,
        "file_index.json": file_index,
        "extraction_errors.json": errors,
        "extraction_summary.json": {
            "unpack": unpack_stats,
            "source_files": len(sources),
            "indexed_files": len(file_index),
            "evidence_records": len(evidence),
            "errors": len(errors),
        },
    }
    for name, value in outputs.items():
        (manifests / name).write_text(
            json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(json.dumps(outputs["extraction_summary.json"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
