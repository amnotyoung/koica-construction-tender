#!/usr/bin/env python3
"""Repair attachment manifest paths after macOS shortens long Unicode filenames."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, value: object) -> None:
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        temp = Path(handle.name)
    temp.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    args = parser.parse_args()
    data = args.data.resolve()
    manifest_path = data / "manifests" / "attachments.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    repaired = 0
    unresolved: list[tuple[str, str]] = []

    for bid_no, bid in manifest.items():
        directory = data / "raw" / bid_no
        disk_files = [path for path in directory.iterdir()] if directory.exists() else []
        hash_cache: dict[Path, str] = {}
        for item in bid.get("files", []):
            current = Path(item.get("local_path") or "")
            if current.exists():
                continue
            expected_size = int(item.get("FILE_CPCTY") or 0)
            expected_hash = item.get("sha256") or ""
            candidates = [
                path for path in disk_files
                if path.is_file() and (not expected_size or path.stat().st_size == expected_size)
            ]
            matched = None
            for candidate in candidates:
                if candidate not in hash_cache:
                    hash_cache[candidate] = sha256(candidate)
                if expected_hash and hash_cache[candidate] == expected_hash:
                    matched = candidate
                    break
            if matched is None:
                unresolved.append((bid_no, str(item.get("ATCHMNFL_SN", ""))))
                continue
            item["local_path"] = str(matched.resolve())
            repaired += 1

    atomic_json(manifest_path, manifest)
    print(json.dumps({
        "manifest": str(manifest_path),
        "repaired": repaired,
        "unresolved": unresolved,
    }, ensure_ascii=False))
    if unresolved:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
