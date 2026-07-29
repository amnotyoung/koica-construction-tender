#!/usr/bin/env python3
"""Select the highest-priority available actual index and audit normalization.

The reviewed cases store nominal USD amounts whose local/imported currency mix is
usually unknown. Therefore this command does not calculate an adjusted USD unit
cost unless --assume-local-cost is explicitly supplied. The default output is an
audit showing which index would be selected and which cases remain blocked.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = (
    ROOT / "outputs" / "koica-construction-distribution"
    / "KOICA_건축사업_사례DB_2016-2025.sqlite"
)


def period_key(date_value: str, frequency: str) -> str:
    if frequency == "annual":
        return date_value[:4]
    if frequency == "quarterly":
        month = int(date_value[5:7])
        return f"{date_value[:4]}-Q{(month - 1) // 3 + 1}"
    if frequency == "monthly":
        return date_value[:7]
    raise ValueError(f"Unsupported frequency: {frequency}")


def select_source(
    connection: sqlite3.Connection,
    country: str,
    source_date: str,
    target_date: str,
) -> dict | None:
    sources = connection.execute(
        """SELECT source_id, priority, index_class, series_name, provider,
                  provider_url, frequency
           FROM price_index_sources
           WHERE country = ? AND priority IS NOT NULL
           ORDER BY priority, construction_specific DESC, source_id""",
        (country,),
    ).fetchall()
    for source in sources:
        source_period = period_key(source_date, source["frequency"])
        target_period = period_key(target_date, source["frequency"])
        values = dict(connection.execute(
            """SELECT period, value
               FROM price_index_values
               WHERE source_id = ? AND is_actual = 1
                 AND period IN (?,?)""",
            (source["source_id"], source_period, target_period),
        ).fetchall())
        if source_period in values and target_period in values:
            return {
                **dict(source),
                "source_period": source_period,
                "target_period": target_period,
                "index_source": values[source_period],
                "index_target": values[target_period],
            }
    return None


def fx_values(
    connection: sqlite3.Connection,
    iso3: str,
    source_date: str,
    target_date: str,
) -> tuple[float | None, float | None]:
    source_id = f"WB_PA.NUS.FCRF_{iso3}"
    source_period = source_date[:4]
    target_period = target_date[:4]
    values = dict(connection.execute(
        """SELECT period, value
           FROM price_index_values
           WHERE source_id = ? AND is_actual = 1
             AND period IN (?,?)""",
        (source_id, source_period, target_period),
    ).fetchall())
    return values.get(source_period), values.get(target_period)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--database", type=Path, default=DEFAULT_DB)
    parser.add_argument(
        "--assume-local-cost",
        action="store_true",
        help=(
            "명목 USD가 공고일 환율로 환산된 현지통화 비용이라고 가정한다. "
            "원문 확인 없이 확정값으로 사용 금지."
        ),
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="감사 결과를 normalization_runs에 기록",
    )
    args = parser.parse_args()

    connection = sqlite3.connect(args.database)
    connection.row_factory = sqlite3.Row
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cases = connection.execute(
        """SELECT bid_no, notice_date, country, unit_usd_m2_nominal
           FROM reviewed_cases
           WHERE notice_date <= ?
           ORDER BY notice_date, bid_no""",
        (args.target_date,),
    ).fetchall()
    iso_by_country = dict(connection.execute(
        "SELECT DISTINCT country, iso3 FROM price_index_sources"
    ).fetchall())

    results = []
    write_rows = []
    for case in cases:
        selected = select_source(
            connection, case["country"], case["notice_date"], args.target_date
        )
        if selected is None:
            results.append({
                "bid_no": case["bid_no"],
                "country": case["country"],
                "status": "실제지수 관측기간 부족",
            })
            continue
        index_factor = selected["index_target"] / selected["index_source"]
        fx_source, fx_target = fx_values(
            connection, iso_by_country[case["country"]],
            case["notice_date"], args.target_date,
        )
        fx_factor = (
            fx_source / fx_target
            if fx_source is not None and fx_target is not None
            else None
        )
        adjusted = None
        if args.assume_local_cost and fx_factor is not None:
            adjusted = case["unit_usd_m2_nominal"] * index_factor * fx_factor
            status = "대체지수 시나리오 산출"
            limitation = (
                "명목 USD 전액이 공고일 환율로 환산된 현지통화 비용이라는 "
                "가정값. 통화구성·수입재 비중 확인 후 재산정 필요."
            )
        else:
            status = "통화구성 확인필요"
            limitation = (
                "실제 지수비는 확보했으나 원금액의 현지통화·수입재 구성과 "
                "적용 환율이 확인되지 않아 USD 보정단가를 산출하지 않음."
            )
        result = {
            "bid_no": case["bid_no"],
            "country": case["country"],
            "notice_date": case["notice_date"],
            "target_date": args.target_date,
            "priority": selected["priority"],
            "index_class": selected["index_class"],
            "source_id": selected["source_id"],
            "source_period": selected["source_period"],
            "target_period": selected["target_period"],
            "index_factor": index_factor,
            "fx_factor": fx_factor,
            "adjusted_unit_usd_m2": adjusted,
            "status": status,
            "provider_url": selected["provider_url"],
            "limitation": limitation,
        }
        results.append(result)
        write_rows.append((
            case["bid_no"], selected["target_period"], selected["source_id"],
            selected["source_period"], selected["index_source"],
            selected["index_target"], index_factor, fx_source, fx_target,
            fx_factor, adjusted, status, limitation, now,
        ))

    if args.write:
        connection.executemany(
            """INSERT INTO normalization_runs
            (bid_no,target_period,source_id,source_period,index_source,index_target,
             index_factor,fx_source,fx_target,fx_factor,adjusted_unit_usd_m2,
             result_status,limitation_note,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            write_rows,
        )
        connection.commit()
    connection.close()

    summary = {
        "target_date": args.target_date,
        "case_count": len(cases),
        "selected_index_count": len(write_rows),
        "adjusted_value_count": sum(
            row.get("adjusted_unit_usd_m2") is not None for row in results
        ),
        "written": args.write,
        "assume_local_cost": args.assume_local_cost,
        "results": results,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
