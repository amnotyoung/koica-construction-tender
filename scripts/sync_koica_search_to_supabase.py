#!/usr/bin/env python3
"""Synchronize a generated KOICA search snapshot through a protected Supabase RPC."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SNAPSHOT = ROOT / "outputs" / "koica-search" / "koica_search_snapshot.json"
FORBIDDEN_PUBLIC_KEYS = {
    "source_file",
    "source_locator",
    "relative_path",
    "sha256",
    "evidence_text",
    "stored_name",
}
PUBLISHABLE_CASE_KINDS = {
    "CONSTRUCTION_NOTICE",
    "DESIGN_SUPERVISION_REFERENCE",
}


def normalize_supabase_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value.strip())
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError("Supabase URL must be a path-free HTTPS origin")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def assert_server_secret_key(value: str) -> str:
    key = value.strip()
    if key.startswith("sb_secret_") and len(key) >= 24:
        return key
    if key.startswith("eyJ"):
        try:
            encoded_payload = key.split(".")[1]
            padding = "=" * (-len(encoded_payload) % 4)
            payload = json.loads(
                base64.urlsafe_b64decode(encoded_payload + padding).decode("utf-8")
            )
        except (IndexError, UnicodeDecodeError, ValueError, json.JSONDecodeError):
            payload = None
        if isinstance(payload, dict) and payload.get("role") == "service_role":
            return key
    raise ValueError("a server-only Supabase secret/service-role key is required")


def validate_snapshot(snapshot: dict[str, Any]) -> None:
    if not isinstance(snapshot.get("cases"), list) or not snapshot["cases"]:
        raise ValueError("snapshot cases must be a non-empty list")
    if not isinstance(snapshot.get("related_notices"), list):
        raise ValueError("snapshot related_notices must be a list")
    if not str(snapshot.get("data_version") or "").strip():
        raise ValueError("snapshot data_version must not be blank")
    if not str(snapshot.get("source_schema_version") or "").strip():
        raise ValueError("snapshot source_schema_version must not be blank")
    source_db_sha256 = str(snapshot.get("source_db_sha256") or "").strip()
    if not re.fullmatch(r"[0-9a-f]{64}", source_db_sha256):
        raise ValueError("snapshot source_db_sha256 must be a lowercase SHA-256 digest")
    generated_at = str(snapshot.get("generated_at") or "").strip()
    try:
        parsed_generated_at = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("snapshot generated_at must be an ISO-8601 timestamp") from error
    if parsed_generated_at.tzinfo is None:
        raise ValueError("snapshot generated_at must include a timezone")

    case_ids: set[str] = set()
    for row in snapshot["cases"]:
        if not isinstance(row, dict):
            raise ValueError("each case must be an object")
        case_id = row.get("case_id")
        if not case_id or case_id in case_ids:
            raise ValueError(f"missing or duplicate case_id: {case_id!r}")
        case_ids.add(case_id)
        if row.get("case_kind") not in PUBLISHABLE_CASE_KINDS:
            raise ValueError(f"case {case_id} has invalid case_kind: {row.get('case_kind')!r}")
        if not str(row.get("facility_family") or "").strip():
            raise ValueError(f"case {case_id} has a blank facility_family")
        forbidden = FORBIDDEN_PUBLIC_KEYS.intersection(row)
        if forbidden:
            raise ValueError(f"case {case_id} contains forbidden keys: {sorted(forbidden)}")

    related_keys: set[tuple[str, str]] = set()
    for row in snapshot["related_notices"]:
        if not isinstance(row, dict):
            raise ValueError("each related notice must be an object")
        key = (row.get("case_id"), row.get("related_bid_base_no"))
        if not all(key) or key in related_keys:
            raise ValueError(f"missing or duplicate related notice key: {key!r}")
        if row["case_id"] not in case_ids:
            raise ValueError(f"related notice references unknown case: {row['case_id']}")
        related_keys.add(key)
        forbidden = FORBIDDEN_PUBLIC_KEYS.intersection(row)
        if forbidden:
            raise ValueError(f"related notice {key} contains forbidden keys: {sorted(forbidden)}")


def rpc_headers(api_key: str) -> dict[str, str]:
    headers = {
        "apikey": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "koica-search-sync/1.0",
    }
    # Legacy service-role keys are JWTs. Modern sb_secret_* keys belong only in apikey.
    if api_key.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def sync_snapshot(
    snapshot: dict[str, Any],
    supabase_url: str,
    service_role_key: str,
    timeout_seconds: float = 60,
) -> dict[str, Any]:
    validate_snapshot(snapshot)
    base_url = normalize_supabase_url(supabase_url)
    api_key = assert_server_secret_key(service_role_key)
    endpoint = f"{base_url}/rest/v1/rpc/sync_koica_search_snapshot"
    payload = json.dumps(
        {
            "p_cases": snapshot["cases"],
            "p_related_notices": snapshot["related_notices"],
            "p_data_version": snapshot["data_version"],
            "p_source_schema_version": snapshot["source_schema_version"],
            "p_source_db_sha256": snapshot["source_db_sha256"],
            "p_snapshot_generated_at": snapshot["generated_at"],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=payload,
        headers=rpc_headers(api_key),
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            response_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        response_body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Supabase sync failed (HTTP {error.code}): {response_body}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Supabase sync failed: {error.reason}") from error
    return json.loads(response_body)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Perform the remote mutation. Without this flag only validation runs.",
    )
    args = parser.parse_args()

    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    validate_snapshot(snapshot)
    print(
        f"Validated {len(snapshot['cases'])} cases and "
        f"{len(snapshot['related_notices'])} related notices "
        f"({snapshot['data_version']})."
    )
    if not args.apply:
        print("Dry run only. Pass --apply to synchronize Supabase.")
        return

    supabase_url = os.environ.get("KOICA_CONSTRUCTION_SUPABASE_URL", "").strip()
    service_role_key = os.environ.get(
        "KOICA_CONSTRUCTION_SUPABASE_SECRET_KEY", ""
    ).strip()
    if not supabase_url or not service_role_key:
        print(
            "KOICA_CONSTRUCTION_SUPABASE_URL and "
            "KOICA_CONSTRUCTION_SUPABASE_SECRET_KEY are required for --apply.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    result = sync_snapshot(snapshot, supabase_url, service_role_key)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
