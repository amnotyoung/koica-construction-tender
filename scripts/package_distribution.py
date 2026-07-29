#!/usr/bin/env python3
"""Create the lightweight KOICA construction data distribution ZIP."""

from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "koica-construction-distribution"
FILES = [
    "KOICA_건축사업_사례DB_2016-2025.sqlite",
    "KOICA_건축사업_사례라이브러리_2016-2025.xlsx",
    "KOICA_건축사업_검토사례_2016-2025.csv",
    "KOICA_국가별_가격지수_적용현황_28개국.csv",
    "reviewed_cases_2016_2025.json",
    "DEMO_네팔_직업교육시설_3000m2.md",
    "README.md",
]
ZIP_PATH = OUT / "KOICA_건축사업_사례데이터_배포패키지_2016-2025.zip"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    records = []
    for name in FILES:
        path = OUT / name
        if not path.exists():
            raise FileNotFoundError(path)
        records.append({
            "name": name,
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        })
    manifest = {
        "package": ZIP_PATH.name,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_of_truth": "KOICA_건축사업_사례DB_2016-2025.sqlite",
        "raw_attachments_included": False,
        "files": records,
    }
    manifest_path = OUT / "MANIFEST.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in FILES:
            archive.write(OUT / name, arcname=name)
        archive.write(manifest_path, arcname="MANIFEST.json")
    with zipfile.ZipFile(ZIP_PATH) as archive:
        bad = archive.testzip()
        if bad:
            raise RuntimeError(f"Corrupt ZIP member: {bad}")
    print(json.dumps({
        "zip": str(ZIP_PATH),
        "bytes": ZIP_PATH.stat().st_size,
        "sha256": sha256(ZIP_PATH),
        "members": len(FILES) + 1,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
