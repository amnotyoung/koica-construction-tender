#!/usr/bin/env python3
"""Export the 28-country price-index audit and current automatic selection."""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "koica-construction-distribution"
DB_PATH = OUT / "KOICA_건축사업_사례DB_2016-2025.sqlite"
CSV_PATH = OUT / "KOICA_국가별_가격지수_적용현황_28개국.csv"


QUERY = """
WITH reviewed AS (
  SELECT country, COUNT(*) AS reviewed_case_count
  FROM reviewed_cases
  GROUP BY country
)
SELECT
  a.country,
  a.iso3,
  COALESCE(r.reviewed_case_count, 0) AS reviewed_case_count,
  a.candidate_priority,
  a.candidate_name,
  a.provider AS candidate_provider,
  a.status AS audit_status,
  a.source_url AS candidate_source_url,
  b.priority AS selected_priority,
  b.index_class AS selected_index_class,
  b.series_name AS selected_series_name,
  b.provider AS selected_provider,
  b.frequency,
  b.actual_observation_count,
  b.earliest_period,
  b.latest_period,
  b.latest_observation_status,
  b.latest_retrieved_at,
  b.provider_url AS selected_source_url,
  CASE
    WHEN b.priority <= 3 THEN
      '공식 상위지수 실제값 적재; 대상일 관측값 존재 여부를 실행 시 재확인'
    ELSE
      '상위지수 미적재 또는 기간 미충족 시 거시지표 대체; 보고서에 한계 명시'
  END AS automatic_use_note
FROM national_index_source_audit a
LEFT JOIN reviewed r ON r.country = a.country
LEFT JOIN v_best_available_price_index b ON b.country = a.country
ORDER BY a.country
"""


HEADERS = [
    "국가",
    "ISO3",
    "검토사례수",
    "공식후보_우선순위",
    "공식후보_지수명",
    "공식후보_제공기관",
    "감사상태",
    "공식후보_URL",
    "현재선택_우선순위",
    "현재선택_지수분류",
    "현재선택_지수명",
    "현재선택_제공기관",
    "주기",
    "실제관측값수",
    "최초기간",
    "최근기간",
    "최근값상태",
    "최근조회시각",
    "현재선택_URL",
    "자동사용_주의사항",
]


def main() -> None:
    with sqlite3.connect(DB_PATH) as connection:
        rows = connection.execute(QUERY).fetchall()
    if len(rows) != 28:
        raise RuntimeError(f"Expected 28 audited countries, got {len(rows)}")
    with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADERS)
        writer.writerows(rows)
    print(f"{CSV_PATH}: {len(rows)} countries")


if __name__ == "__main__":
    main()
