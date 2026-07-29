#!/usr/bin/env python3
"""Fetch country macro price-index fallbacks and FX from the World Bank API.

These series implement priority 4 (GDP deflator) and priority 5 (CPI) only.
They must not displace a usable national construction index, BOQ component
index, or construction-material PPI/WPI.
"""

from __future__ import annotations

import csv
import io
import json
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "manifests" / "price_indices_world_bank.json"
API = "https://api.worldbank.org/v2/country/{countries}/indicator/{indicator}"
DOWNLOAD_API = (
    "https://api.worldbank.org/v2/en/indicator/{indicator}?downloadformat=csv"
)

COUNTRIES = {
    "Bangladesh": "BGD",
    "Bolivia": "BOL",
    "Cambodia": "KHM",
    "Côte d’Ivoire": "CIV",
    "Dominican Republic": "DOM",
    "Ecuador": "ECU",
    "El Salvador": "SLV",
    "Ethiopia": "ETH",
    "Fiji": "FJI",
    "Ghana": "GHA",
    "Indonesia": "IDN",
    "Iraq": "IRQ",
    "Jordan": "JOR",
    "Kenya": "KEN",
    "Kyrgyzstan": "KGZ",
    "Laos": "LAO",
    "Mozambique": "MOZ",
    "Myanmar": "MMR",
    "Nepal": "NPL",
    "Pakistan": "PAK",
    "Paraguay": "PRY",
    "Philippines": "PHL",
    "Senegal": "SEN",
    "Sri Lanka": "LKA",
    "Timor-Leste": "TLS",
    "Turkmenistan": "TKM",
    "Uganda": "UGA",
    "Uzbekistan": "UZB"
}

SERIES = {
    "NY.GDP.DEFL.ZS": {
        "index_class": "gdp_deflator",
        "priority": 4,
        "series_name": "GDP deflator (base year varies by country)",
        "unit": "index"
    },
    "FP.CPI.TOTL": {
        "index_class": "consumer_price_index",
        "priority": 5,
        "series_name": "Consumer price index (2010 = 100)",
        "unit": "index"
    },
    "PA.NUS.FCRF": {
        "index_class": "official_exchange_rate",
        "priority": None,
        "series_name": "Official exchange rate (LCU per USD, period average)",
        "unit": "LCU per USD"
    }
}


def fetch(indicator: str) -> list[dict]:
    url = DOWNLOAD_API.format(indicator=indicator)
    result = subprocess.run(
        [
            "curl", "--fail", "--silent", "--show-error", "--location",
            "--retry", "5", "--retry-all-errors", "--retry-delay", "2",
            "--connect-timeout", "15", "--max-time", "120", url,
        ],
        check=True,
        capture_output=True,
    )
    with zipfile.ZipFile(io.BytesIO(result.stdout)) as archive:
        names = [
            name for name in archive.namelist()
            if name.startswith("API_") and name.endswith(".csv")
        ]
        if len(names) != 1:
            raise RuntimeError(f"Unexpected CSV members for {indicator}: {names}")
        text = archive.read(names[0]).decode("utf-8-sig")
    lines = text.splitlines()
    header_index = next(
        index for index, line in enumerate(lines)
        if line.startswith('"Country Name"')
    )
    rows = []
    wanted = set(COUNTRIES.values())
    for row in csv.DictReader(lines[header_index:]):
        iso3 = row["Country Code"]
        if iso3 not in wanted:
            continue
        for year in range(2015, 2027):
            raw = row.get(str(year), "")
            if not raw:
                continue
            rows.append({
                "countryiso3code": iso3,
                "date": str(year),
                "value": float(raw),
            })
    return rows


def main() -> None:
    iso_to_country = {iso: country for country, iso in COUNTRIES.items()}
    retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    sources = []
    values = []
    for indicator, metadata in SERIES.items():
        rows = fetch(indicator)
        for country, iso3 in COUNTRIES.items():
            source_id = f"WB_{indicator}_{iso3}"
            sources.append({
                "source_id": source_id,
                "country": country,
                "iso3": iso3,
                "priority": metadata["priority"],
                "index_class": metadata["index_class"],
                "series_name": metadata["series_name"],
                "provider": "World Bank, World Development Indicators",
                "provider_url": (
                    f"https://api.worldbank.org/v2/country/{iso3}/"
                    f"indicator/{indicator}"
                ),
                "indicator_code": indicator,
                "frequency": "annual",
                "unit": metadata["unit"],
                "construction_specific": False,
                "status": "actual_observation",
                "notes": (
                    "거시 대체자료. 우선순위 1~3의 건설 관련 지수가 있으면 "
                    "선택하지 않는다."
                )
            })
        for row in rows:
            iso3 = row.get("countryiso3code")
            value = row.get("value")
            if iso3 not in iso_to_country or value is None:
                continue
            values.append({
                "source_id": f"WB_{indicator}_{iso3}",
                "period": str(row["date"]),
                "value": value,
                "is_actual": True,
                "retrieved_at": retrieved_at
            })
    values.sort(key=lambda row: (row["source_id"], row["period"]))
    document = {
        "schema_version": "1.0",
        "retrieved_at": retrieved_at,
        "api_documentation": (
            "https://datahelpdesk.worldbank.org/knowledgebase/articles/"
            "889392-about-the-indicators-api-documentation"
        ),
        "coverage": "2015-2026 (공표된 실제 관측값만 저장)",
        "sources": sources,
        "values": values
    }
    OUTPUT.write_text(
        json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({
        "output": str(OUTPUT),
        "sources": len(sources),
        "values": len(values),
        "countries": len(COUNTRIES)
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
