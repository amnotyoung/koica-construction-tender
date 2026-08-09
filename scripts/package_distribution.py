#!/usr/bin/env python3
"""Create the lightweight KOICA construction data distribution ZIP."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path

try:
    from scripts.snapshot_koica_evaluation_index import (
        validate_snapshot as validate_official_index_snapshot,
    )
except ModuleNotFoundError:  # Direct execution via ``python scripts/...``.
    from snapshot_koica_evaluation_index import (
        validate_snapshot as validate_official_index_snapshot,
    )


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "koica-construction-distribution"
FILES = [
    "KOICA_건축사업_사례DB_2016-2025.sqlite",
    "KOICA_건축사업_사례라이브러리_2016-2025.xlsx",
    "KOICA_건축사업_검토사례_2016-2025.csv",
    "KOICA_국가별_가격지수_적용현황_28개국.csv",
    "reviewed_cases_2016_2025.json",
    "DEMO_네팔_직업교육시설_3000m2.md",
    "TEMPLATE_국가별_건축사업비_산정.md",
    "README.md",
]
EVALUATION_MANIFEST = (
    ROOT / "data" / "manifests" / "koica_endline_evaluation_reports.json"
)
EVALUATION_MANIFEST_ARCHIVE_NAME = (
    "data/manifests/koica_endline_evaluation_reports.json"
)
EVALUATION_INDEX_SNAPSHOT = (
    ROOT
    / "data"
    / "manifests"
    / "koica_evaluation_report_index_2026-08-09.json"
)
EVALUATION_INDEX_SNAPSHOT_ARCHIVE_NAME = (
    "data/manifests/koica_evaluation_report_index_2026-08-09.json"
)
ZIP_PATH = OUT / "KOICA_건축사업_사례데이터_배포패키지_2016-2025.zip"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(
    zip_path: Path = ZIP_PATH,
    manifest_path: Path = OUT / "MANIFEST.json",
) -> None:
    package_files = [(OUT / name, name) for name in FILES]
    package_files.append(
        (EVALUATION_MANIFEST, EVALUATION_MANIFEST_ARCHIVE_NAME)
    )
    package_files.append(
        (EVALUATION_INDEX_SNAPSHOT, EVALUATION_INDEX_SNAPSHOT_ARCHIVE_NAME)
    )
    records = []
    for path, archive_name in package_files:
        if not path.exists():
            raise FileNotFoundError(path)
        records.append({
            "name": archive_name,
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        })
    evaluation_manifest = json.loads(
        EVALUATION_MANIFEST.read_text(encoding="utf-8")
    )
    index_snapshot = validate_official_index_snapshot(
        json.loads(EVALUATION_INDEX_SNAPSHOT.read_text(encoding="utf-8"))
    )
    if evaluation_manifest.get("official_source", {}).get(
        "index_snapshot"
    ) != index_snapshot:
        raise RuntimeError(
            "packaged evaluation index differs from evaluation manifest"
        )
    database_path = OUT / "KOICA_건축사업_사례DB_2016-2025.sqlite"
    with sqlite3.connect(f"file:{database_path}?mode=ro", uri=True) as connection:
        schema_version = connection.execute(
            "SELECT value FROM metadata WHERE key = 'schema_version'"
        ).fetchone()[0]
        evaluation_counts = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "evaluation_field_definitions",
                "evaluation_reports",
                "evaluation_project_matches",
                "evaluation_findings",
                "evaluation_corpus_files",
                "evaluation_project_screening",
            )
        }
        recorded_evaluation_manifest_hash = connection.execute(
            "SELECT value FROM metadata "
            "WHERE key = 'evaluation_manifest_sha256'"
        ).fetchone()[0]
    if recorded_evaluation_manifest_hash != sha256(EVALUATION_MANIFEST):
        raise RuntimeError(
            "SQLite evaluation manifest hash differs from packaged manifest"
        )
    manifest = {
        "package": zip_path.name,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_of_truth": "KOICA_건축사업_사례DB_2016-2025.sqlite",
        "database_schema_version": schema_version,
        "raw_attachments_included": False,
        "raw_evaluation_reports_included": False,
        "evaluation_table_counts": evaluation_counts,
        "files": records,
    }
    temporary_manifest = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    temporary_zip = zip_path.with_suffix(zip_path.suffix + ".tmp")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_manifest.unlink(missing_ok=True)
    temporary_zip.unlink(missing_ok=True)
    try:
        temporary_manifest.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        with zipfile.ZipFile(
            temporary_zip, "w", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            for path, archive_name in package_files:
                archive.write(path, arcname=archive_name)
            archive.write(temporary_manifest, arcname="MANIFEST.json")
        with zipfile.ZipFile(temporary_zip) as archive:
            bad = archive.testzip()
            if bad:
                raise RuntimeError(f"Corrupt ZIP member: {bad}")
            embedded_manifest = json.loads(
                archive.read("MANIFEST.json").decode("utf-8")
            )
            for record in embedded_manifest["files"]:
                payload = archive.read(record["name"])
                if len(payload) != record["bytes"]:
                    raise RuntimeError(
                        f"ZIP member size mismatch: {record['name']}"
                    )
                if hashlib.sha256(payload).hexdigest() != record["sha256"]:
                    raise RuntimeError(
                        f"ZIP member hash mismatch: {record['name']}"
                    )
        temporary_manifest.replace(manifest_path)
        temporary_zip.replace(zip_path)
    finally:
        temporary_manifest.unlink(missing_ok=True)
        temporary_zip.unlink(missing_ok=True)
    print(json.dumps({
        "zip": str(zip_path),
        "bytes": zip_path.stat().st_size,
        "sha256": sha256(zip_path),
        "members": len(package_files) + 1,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
