#!/usr/bin/env python3
"""Build or verify a reproducible snapshot of the KOICA evaluation index."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import unicodedata
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    ROOT
    / "data"
    / "manifests"
    / "koica_evaluation_report_index_2026-08-09.json"
)
LIST_URL = "https://www.koica.go.kr/sites/evaluation_kr/article/list/15/1"
DIGEST_ALGORITHM = (
    "sha256(post_id NUL list_page NUL title_nfc LF; numeric post_id order)"
)
TITLE_PATTERN = re.compile(
    r'<a[^>]*class="tit btn goView"[^>]*data-langStr="kr"'
    r'[^>]*data-writeSn="([0-9]+)"[^>]*>(.*?)</a>',
    re.DOTALL,
)


def normalized_title(raw_html: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", "", raw_html))
    return unicodedata.normalize("NFC", re.sub(r"\s+", " ", text).strip())


def index_payload(posts: list[dict]) -> bytes:
    payload = bytearray()
    for row in sorted(posts, key=lambda item: int(item["post_id"])):
        payload.extend(str(row["post_id"]).encode("ascii"))
        payload.extend(b"\0")
        payload.extend(str(row["list_page"]).encode("ascii"))
        payload.extend(b"\0")
        payload.extend(
            unicodedata.normalize("NFC", row["title"]).encode("utf-8")
        )
        payload.extend(b"\n")
    return bytes(payload)


def validate_snapshot(snapshot: dict) -> dict:
    if snapshot.get("schema_version") != "1.0":
        raise ValueError("index snapshot schema_version must be 1.0")
    if snapshot.get("list_url") != LIST_URL:
        raise ValueError("index snapshot list_url differs from KOICA source")
    if snapshot.get("digest_algorithm") != DIGEST_ALGORITHM:
        raise ValueError("index snapshot digest algorithm is unsupported")
    page_count = int(snapshot.get("page_count", 0))
    posts = snapshot.get("posts")
    if page_count <= 0 or not isinstance(posts, list) or not posts:
        raise ValueError("index snapshot page/post inventory is missing")
    if snapshot.get("post_count") != len(posts):
        raise ValueError("index snapshot post count differs from inventory")
    if [int(row["post_id"]) for row in posts] != sorted(
        int(row["post_id"]) for row in posts
    ):
        raise ValueError("index snapshot posts must be in numeric post-id order")
    post_ids = []
    listed_pages = set()
    for row in posts:
        post_id = str(row.get("post_id", ""))
        list_page = row.get("list_page")
        title = row.get("title")
        if not post_id.isdigit() or not isinstance(list_page, int):
            raise ValueError("index snapshot post identity is invalid")
        if not 1 <= list_page <= page_count:
            raise ValueError(f"index snapshot page is invalid: {post_id}")
        if (
            not isinstance(title, str)
            or not title.strip()
            or title != unicodedata.normalize("NFC", title)
        ):
            raise ValueError(f"index snapshot title is invalid: {post_id}")
        post_ids.append(post_id)
        listed_pages.add(list_page)
    if len(post_ids) != len(set(post_ids)):
        raise ValueError("index snapshot contains duplicate post ids")
    if listed_pages != set(range(1, page_count + 1)):
        raise ValueError("index snapshot does not cover every list page")
    payload = index_payload(posts)
    digest = hashlib.sha256(payload).hexdigest()
    if snapshot.get("payload_bytes") != len(payload):
        raise ValueError("index snapshot payload byte count differs")
    if snapshot.get("digest") != digest:
        raise ValueError("index snapshot digest differs")
    return snapshot


def page_path(html_dir: Path, page: int) -> Path:
    candidate = html_dir / f"koica-eval-page-{page}.html"
    if page == 1 and not candidate.is_file():
        candidate = html_dir / "koica-evaluation-list.html"
    if not candidate.is_file():
        raise FileNotFoundError(candidate)
    return candidate


def build_snapshot(
    html_dir: Path, page_count: int, screened_at: str
) -> dict:
    posts = []
    for page in range(1, page_count + 1):
        source = page_path(html_dir, page).read_text(encoding="utf-8")
        matches = TITLE_PATTERN.findall(source)
        if not matches:
            raise ValueError(f"no KOICA evaluation posts found on page {page}")
        posts.extend(
            {
                "post_id": post_id,
                "list_page": page,
                "title": normalized_title(raw_title),
            }
            for post_id, raw_title in matches
        )
    posts.sort(key=lambda row: int(row["post_id"]))
    payload = index_payload(posts)
    snapshot = {
        "schema_version": "1.0",
        "list_url": LIST_URL,
        "screened_at": screened_at,
        "page_count": page_count,
        "post_count": len(posts),
        "digest_algorithm": DIGEST_ALGORITHM,
        "digest": hashlib.sha256(payload).hexdigest(),
        "payload_bytes": len(payload),
        "posts": posts,
    }
    return validate_snapshot(snapshot)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--html-dir", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--page-count", type=int, default=66)
    parser.add_argument("--screened-at", default="2026-08-09")
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the existing snapshot instead of rebuilding it",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.check:
        snapshot = validate_snapshot(
            json.loads(args.output.read_text(encoding="utf-8"))
        )
    else:
        if args.html_dir is None:
            raise ValueError("--html-dir is required when building a snapshot")
        snapshot = build_snapshot(
            args.html_dir, args.page_count, args.screened_at
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(args.output)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "page_count": snapshot["page_count"],
                "post_count": snapshot["post_count"],
                "payload_bytes": snapshot["payload_bytes"],
                "digest": snapshot["digest"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
