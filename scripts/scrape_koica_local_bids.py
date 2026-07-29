#!/usr/bin/env python3
"""Collect KOICA local-bid metadata and DEXT5 attachments.

The KOICA server is occasionally unreachable through ordinary DNS routing.
This collector therefore drives curl with --resolve while preserving a cookie
jar, Referer, retries, and atomic file writes.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import html
import json
import math
import re
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlencode

from bs4 import BeautifulSoup
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7


HOST = "nebid.koica.go.kr"
BASE_URL = f"https://{HOST}"
LIST_PATH = "/oep/lobi/localBidManageList.do"
DETAIL_PATH = "/oep/lobi/localBidManageDetail.do"
FILE_LIST_PATH = "/oep/com/atfi/atchFileListInqireByAtchFileGroupNo2.json"
DEXT_HANDLER_PATH = "/oep/dext5upload/handler/dext5handler.jsp"
DEFAULT_START = "2021-01-01"
DEFAULT_END = "2025-12-31"
STANDARD_B64_ALPHABET = (
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="
)
DEXT5_B64_ALPHABET = (
    "adebcfijghklopmnqruvstwyzxAHIJDBCEFLMNUVGKRSTOWXPQYZ0163847259+/="
)

CONSTRUCTION_KEYWORDS = (
    "건축",
    "건립",
    "신축",
    "증축",
    "개축",
    "개보수",
    "보수공사",
    "환경개선",
    "리모델링",
    "리노베이션",
    "시공",
    "공사",
    "설계",
    "감리",
    "시설물",
    "토목",
    "epc",
    "construction",
    "building",
    "renovation",
    "remodeling",
    "architect",
    "supervision",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        handle.write(text)
        temp_path = Path(handle.name)
    temp_path.replace(path)


def atomic_write_json(path: Path, value: Any) -> None:
    atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2))


def safe_filename(name: str) -> str:
    normalized = re.sub(r"[\x00-\x1f/\\:*?\"<>|]", "_", name).strip()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized[:220] or "unnamed_attachment"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def construction_candidate(row: dict[str, Any]) -> bool:
    if row.get("contract_type") == "공사":
        return True
    title = str(row.get("title", "")).lower()
    return any(keyword in title for keyword in CONSTRUCTION_KEYWORDS)


def decode_dext_failure(payload: bytes) -> str:
    if not payload.startswith(b"[FAIL]"):
        return ""
    encoded = payload[len(b"[FAIL]") :].strip()
    try:
        first = base64.b64decode(encoded).decode("utf-8", errors="replace")
        if first.startswith("R"):
            first = base64.b64decode(first[1:]).decode("utf-8", errors="replace")
        return first
    except Exception:
        return payload[:500].decode("utf-8", errors="replace")


def dext5_encrypt_download_params(file_path: str, original_name: str) -> str:
    """Reproduce DEXT5 encrypt_param=4 (d03) for a single-file download."""
    unit_delimiter = "\x0b"
    attribute_delimiter = "\x0c"
    request_guid = str(uuid.uuid4()).lower()
    plaintext = (
        f"d01{attribute_delimiter}downloadRequest{unit_delimiter}"
        f"d10{attribute_delimiter}_{unit_delimiter}"
        f"d25{attribute_delimiter}{file_path}{unit_delimiter}"
        f"d26{attribute_delimiter}{original_name}{unit_delimiter}"
        f"d07{attribute_delimiter}{request_guid}{unit_delimiter}"
    ).encode("utf-8")

    key_text = base64.b64encode(str(uuid.uuid4()).lower().encode("utf-8")).decode(
        "ascii"
    )[:15]
    # CryptoJS parses 15 UTF-8 bytes and then sets sigBytes=16. The unused
    # low byte in the final 32-bit word is therefore a zero byte.
    key = key_text.encode("ascii") + b"\x00"
    padder = PKCS7(128).padder()
    padded = padder.update(plaintext) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.CBC(key)).encryptor()
    encrypted = encryptor.update(padded) + encryptor.finalize()
    encoded = base64.b64encode(encrypted).decode("ascii")
    translated = encoded.translate(
        str.maketrans(STANDARD_B64_ALPHABET, DEXT5_B64_ALPHABET)
    )
    return key_text + translated


class CurlClient:
    def __init__(
        self,
        state_dir: Path,
        server_ip: str,
        retries: int = 2,
        connect_timeout: int = 8,
        max_time: int = 60,
    ) -> None:
        self.server_ip = server_ip
        self.retries = retries
        self.connect_timeout = connect_timeout
        self.max_time = max_time
        self.cookie_jar = state_dir / "cookies.txt"
        state_dir.mkdir(parents=True, exist_ok=True)

    def _base_args(self, referer: str | None = None) -> list[str]:
        args = [
            "curl",
            "-4",
            "--resolve",
            f"{HOST}:443:{self.server_ip}",
            "-A",
            "Mozilla/5.0 (compatible; KOICA-Construction-Research/1.0)",
            "-sS",
            "--fail-with-body",
            "--connect-timeout",
            str(self.connect_timeout),
            "--max-time",
            str(self.max_time),
            "--retry",
            str(self.retries),
            "--retry-delay",
            "2",
            "--retry-all-errors",
            "-c",
            str(self.cookie_jar),
            "-b",
            str(self.cookie_jar),
        ]
        if referer:
            args.extend(["-e", referer])
        return args

    def request_bytes(
        self,
        path: str,
        *,
        method: str = "GET",
        form: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
        query: dict[str, str] | None = None,
        referer: str | None = None,
    ) -> bytes:
        url = f"{BASE_URL}{path}"
        args = self._base_args(referer)
        if method != "GET":
            args.extend(["-X", method])
        if form:
            for key, value in form.items():
                args.extend(["--data-urlencode", f"{key}={value}"])
        if json_body is not None:
            args.extend(
                [
                    "-H",
                    "Content-Type: application/json;charset=UTF-8",
                    "--data",
                    json.dumps(json_body, ensure_ascii=False),
                ]
            )
        if query:
            args.append("--get")
            for key, value in query.items():
                args.extend(["--data-urlencode", f"{key}={value}"])
        args.append(url)
        result = subprocess.run(args, check=False, capture_output=True)
        if result.returncode:
            stderr = result.stderr.decode("utf-8", errors="replace").strip()
            body = result.stdout[:500].decode("utf-8", errors="replace")
            raise RuntimeError(
                f"curl failed ({result.returncode}) for {path}: {stderr}; {body}"
            )
        return result.stdout

    def download(
        self,
        path: str,
        destination: Path,
        *,
        file_path: str,
        original_name: str,
        referer: str,
    ) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as handle:
            temp_path = Path(handle.name)
        args = self._base_args(referer)
        args.extend(
            [
                "-X",
                "POST",
                "--data-urlencode",
                f"d03={dext5_encrypt_download_params(file_path, original_name)}",
                "--data-urlencode",
                "customValue=",
            ]
        )
        args.extend(["-o", str(temp_path), f"{BASE_URL}{path}"])
        result = subprocess.run(args, check=False, capture_output=True)
        if result.returncode:
            temp_path.unlink(missing_ok=True)
            stderr = result.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"download curl failed ({result.returncode}): {stderr}")
        failure = decode_dext_failure(temp_path.read_bytes()[:4096])
        if failure:
            temp_path.unlink(missing_ok=True)
            raise RuntimeError(f"DEXT5 download failure: {failure}")
        temp_path.replace(destination)


def resolve_server_ip(explicit_ip: str | None) -> str:
    if explicit_ip:
        return explicit_ip
    return socket.gethostbyname(HOST)


def parse_list_page(page_html: str) -> tuple[int, list[dict[str, Any]]]:
    soup = BeautifulSoup(page_html, "html.parser")
    total_node = soup.select_one("p.list_count span")
    if not total_node:
        raise ValueError("Could not find total result count")
    total = int(re.sub(r"\D", "", total_node.get_text()) or "0")
    rows: list[dict[str, Any]] = []
    for row in soup.select("table tbody tr.row"):
        cells = [" ".join(cell.stripped_strings) for cell in row.select("td")]
        onclick = row.get("onclick", "")
        match = re.search(
            r"localBidManageDetailInqire\('([^']+)','([^']+)'\)", onclick
        )
        if len(cells) < 7 or not match:
            continue
        base_no, order = match.groups()
        rows.append(
            {
                "number": int(cells[0]),
                "bid_base_no": base_no,
                "order": order,
                "bid_no": html.unescape(cells[1]),
                "title": html.unescape(cells[2]),
                "contract_type": cells[3],
                "contract_method": cells[4],
                "notice_date": cells[5],
                "manager": cells[6],
            }
        )
    return total, rows


def parse_detail_page(page_html: str) -> tuple[dict[str, str], str]:
    soup = BeautifulSoup(page_html, "html.parser")
    detail: dict[str, str] = {}
    info_table = soup.select_one("table")
    if info_table:
        for row in info_table.select("tr"):
            headers = row.select("th")
            cells = row.select("td")
            for index, header_cell in enumerate(headers):
                if index < len(cells):
                    key = " ".join(header_cell.stripped_strings)
                    value = " ".join(cells[index].stripped_strings)
                    detail[key] = value
    group_input = soup.select_one("#P_ATCHMNFL_GROUP_NO")
    group_no = group_input.get("value", "").strip() if group_input else ""
    return detail, group_no


def unique_destination(directory: Path, filename: str, attachment_sn: Any) -> Path:
    candidate = directory / safe_filename(filename)
    if not candidate.exists():
        return candidate
    stem, suffix = candidate.stem, candidate.suffix
    return directory / f"{stem}__{attachment_sn}{suffix}"


def write_bids_csv(path: Path, bids: Iterable[dict[str, Any]]) -> None:
    rows = list(bids)
    fields = [
        "number",
        "bid_base_no",
        "order",
        "bid_no",
        "title",
        "contract_type",
        "contract_method",
        "notice_date",
        "manager",
        "construction_candidate",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8-sig", newline="", dir=path.parent, delete=False
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})
        temp_path = Path(handle.name)
    temp_path.replace(path)


def select_bids(bids: list[dict[str, Any]], scope: str) -> list[dict[str, Any]]:
    if scope == "none":
        return []
    if scope == "construction":
        return [row for row in bids if row["construction_candidate"]]
    return bids


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", default=DEFAULT_START)
    parser.add_argument("--end-date", default=DEFAULT_END)
    parser.add_argument("--scope", choices=("all", "construction", "none"), default="all")
    parser.add_argument("--server-ip")
    parser.add_argument("--output", type=Path, default=Path("data"))
    parser.add_argument("--page-size", type=int, default=10)
    parser.add_argument("--max-details", type=int)
    parser.add_argument(
        "--only-bids",
        help="Comma-separated bid numbers to collect or retry",
    )
    parser.add_argument("--metadata-only", action="store_true")
    parser.add_argument(
        "--reuse-list",
        action="store_true",
        help="Reuse data/manifests/bids.json instead of querying all list pages",
    )
    parser.add_argument(
        "--skip-collected",
        action="store_true",
        help="Skip bids already present in data/manifests/details.json",
    )
    parser.add_argument("--delay", type=float, default=0.35)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--connect-timeout", type=int, default=8)
    parser.add_argument("--max-time", type=int, default=60)
    parser.add_argument("--max-consecutive-failures", type=int, default=3)
    args = parser.parse_args()

    output = args.output.resolve()
    state_dir = output / ".state"
    manifests_dir = output / "manifests"
    details_dir = output / "details"
    raw_dir = output / "raw"
    server_ip = resolve_server_ip(args.server_ip)
    client = CurlClient(
        state_dir,
        server_ip,
        retries=args.retries,
        connect_timeout=args.connect_timeout,
        max_time=args.max_time,
    )

    bids_path = manifests_dir / "bids.json"
    if args.reuse_list:
        if not bids_path.exists():
            raise FileNotFoundError(f"--reuse-list requested but missing: {bids_path}")
        bids = json.loads(bids_path.read_text(encoding="utf-8"))
        total = len(bids)
        print(f"Reusing {total} bids from {bids_path}", flush=True)
    else:
        list_form = {
            "P_PAGE_NO": "1",
            "P_PAGE_SIZE": str(args.page_size),
            "P_BID_KOREAN_NM_S": "",
            "P_PBLANC_BEGIN_DE_S": args.start_date,
            "P_PBLANC_END_DE_S": args.end_date,
        }
        initial = client.request_bytes(
            LIST_PATH, method="POST", form=list_form, referer=f"{BASE_URL}{LIST_PATH}"
        ).decode("utf-8", errors="replace")
        total, first_rows = parse_list_page(initial)
        pages = math.ceil(total / args.page_size)
        bids = first_rows
        print(f"Found {total} bids across {pages} pages", flush=True)

        for page in range(2, pages + 1):
            list_form["P_PAGE_NO"] = str(page)
            page_html = client.request_bytes(
                LIST_PATH,
                method="POST",
                form=list_form,
                referer=f"{BASE_URL}{LIST_PATH}",
            ).decode("utf-8", errors="replace")
            page_total, rows = parse_list_page(page_html)
            if page_total != total:
                raise RuntimeError(
                    f"Result count changed while paging: expected {total}, got {page_total}"
                )
            bids.extend(rows)
            if page % 5 == 0 or page == pages:
                print(f"  list pages: {page}/{pages} ({len(bids)} rows)", flush=True)
            time.sleep(args.delay)

        if len(bids) != total:
            raise RuntimeError(f"Expected {total} rows, parsed {len(bids)}")
        for row in bids:
            row["construction_candidate"] = construction_candidate(row)
        atomic_write_json(bids_path, bids)
        write_bids_csv(manifests_dir / "bids.csv", bids)

    selected = select_bids(bids, args.scope)
    if args.only_bids:
        requested = {value.strip() for value in args.only_bids.split(",") if value.strip()}
        selected = [row for row in selected if row["bid_no"] in requested]
    if args.max_details is not None:
        selected = selected[: args.max_details]
    details: dict[str, Any] = {}
    attachments_manifest: dict[str, Any] = {}
    failures: list[dict[str, Any]] = []
    existing_details = manifests_dir / "details.json"
    existing_attachments = manifests_dir / "attachments.json"
    if existing_details.exists():
        details = json.loads(existing_details.read_text(encoding="utf-8"))
    if existing_attachments.exists():
        attachments_manifest = json.loads(
            existing_attachments.read_text(encoding="utf-8")
        )
    if args.skip_collected:
        selected = [bid for bid in selected if bid["bid_no"] not in details]
    print(
        f"Selected {len(selected)} bids for detail/attachment collection "
        f"(scope={args.scope}, skip_collected={args.skip_collected})",
        flush=True,
    )

    consecutive_failures = 0
    for index, bid in enumerate(selected, 1):
        bid_no = bid["bid_no"]
        detail_query = {
            "P_LOAZ_BID_PBLANC_NO": bid["bid_base_no"],
            "P_PBLANC_ODR": bid["order"],
        }
        detail_url = f"{BASE_URL}{DETAIL_PATH}?{urlencode(detail_query)}"
        try:
            detail_bytes = client.request_bytes(
                DETAIL_PATH,
                query=detail_query,
                referer=f"{BASE_URL}{LIST_PATH}",
            )
            detail_html = detail_bytes.decode("utf-8", errors="replace")
            atomic_write_text(details_dir / f"{bid_no}.html", detail_html)
            fields, group_no = parse_detail_page(detail_html)
            detail_record = {
                **bid,
                "fields": fields,
                "attachment_group_no": group_no,
                "detail_url": detail_url,
                "collected_at": utc_now(),
            }
            details[bid_no] = detail_record

            files: list[dict[str, Any]] = []
            if group_no:
                payload = client.request_bytes(
                    FILE_LIST_PATH,
                    method="POST",
                    json_body={"P_ATCHMNFL_GROUP_NO": group_no},
                    referer=detail_url,
                )
                files = json.loads(payload.decode("utf-8"))["atchFileList"]

            bid_manifest = attachments_manifest.setdefault(
                bid_no, {"bid_no": bid_no, "files": []}
            )
            known = {
                str(item.get("ATCHMNFL_SN")): item for item in bid_manifest["files"]
            }
            for attachment in files:
                attachment_sn = str(attachment["ATCHMNFL_SN"])
                record = dict(attachment)
                record["bid_no"] = bid_no
                record["downloaded_at"] = None
                record["local_path"] = None
                record["sha256"] = None
                record["status"] = "metadata"
                prior = known.get(attachment_sn, {})
                record.update(
                    {
                        key: prior.get(key, record[key])
                        for key in ("downloaded_at", "local_path", "sha256", "status")
                    }
                )

                if not args.metadata_only:
                    target_dir = raw_dir / bid_no
                    expected_size = int(attachment.get("FILE_CPCTY") or 0)
                    natural_path = target_dir / safe_filename(attachment["ATCHMNFL_NM"])
                    existing_path = (
                        Path(record["local_path"])
                        if record.get("local_path")
                        else (
                            natural_path
                            if natural_path.exists()
                            and (
                                not expected_size
                                or natural_path.stat().st_size == expected_size
                            )
                            else unique_destination(
                                target_dir, attachment["ATCHMNFL_NM"], attachment_sn
                            )
                        )
                    )
                    if (
                        existing_path.exists()
                        and (not expected_size or existing_path.stat().st_size == expected_size)
                    ):
                        record["status"] = "downloaded"
                        record["local_path"] = str(existing_path)
                        record["sha256"] = sha256_file(existing_path)
                    else:
                        client.download(
                            DEXT_HANDLER_PATH,
                            existing_path,
                            file_path=attachment["filePath"],
                            original_name=attachment["ATCHMNFL_NM"],
                            referer=detail_url,
                        )
                        if expected_size and existing_path.stat().st_size != expected_size:
                            raise RuntimeError(
                                f"size mismatch for {bid_no}/{attachment_sn}: "
                                f"{existing_path.stat().st_size} != {expected_size}"
                            )
                        record["status"] = "downloaded"
                        record["local_path"] = str(existing_path)
                        record["sha256"] = sha256_file(existing_path)
                        record["downloaded_at"] = utc_now()
                known[attachment_sn] = record
            bid_manifest["files"] = list(known.values())
            bid_manifest["attachment_group_no"] = group_no
            bid_manifest["updated_at"] = utc_now()
            consecutive_failures = 0
        except Exception as exc:
            consecutive_failures += 1
            failure = {
                "bid_no": bid_no,
                "stage": "detail_or_attachment",
                "error": str(exc),
                "failed_at": utc_now(),
            }
            failures.append(failure)
            print(f"  FAILED {bid_no}: {exc}", file=sys.stderr, flush=True)

        atomic_write_json(manifests_dir / "details.json", details)
        atomic_write_json(manifests_dir / "attachments.json", attachments_manifest)
        atomic_write_json(manifests_dir / "failures.json", failures)
        if index % 10 == 0 or index == len(selected):
            print(f"  details: {index}/{len(selected)}", flush=True)
        if consecutive_failures >= args.max_consecutive_failures:
            print(
                "Stopping after "
                f"{consecutive_failures} consecutive failures; rerun with "
                "--skip-collected to resume.",
                file=sys.stderr,
                flush=True,
            )
            break
        time.sleep(args.delay)

    downloaded = sum(
        1
        for bid_record in attachments_manifest.values()
        for item in bid_record.get("files", [])
        if item.get("status") == "downloaded"
    )
    print(
        f"Complete: bids={len(bids)}, details={len(details)}, "
        f"downloaded_files={downloaded}, failures={len(failures)}"
    )
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
