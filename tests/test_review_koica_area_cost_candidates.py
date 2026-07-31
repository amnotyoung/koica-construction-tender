from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/review_koica_area_cost_candidates.py"
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("area_cost_review", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_candidate_universe_is_exactly_170_notices_and_91_projects() -> None:
    database = ROOT / MODULE.DEFAULT_DB
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    rows = list(connection.execute(MODULE.candidate_query()))
    connection.close()
    assert len(rows) == 170
    assert len({row["bid_no"] for row in rows}) == 170
    assert len({row["bid_base_no"] for row in rows}) == 154
    assert len({row["project_no"] for row in rows}) == 91


def test_amount_and_area_number_parsers() -> None:
    assert MODULE.parse_amount("$ 5,497,600 (환율 : 1150)") == 5_497_600
    assert MODULE.parse_amount("USD 4,374,688.00") == 4_374_688
    assert MODULE.normalize_area_number("1, 706") == 1706
    assert MODULE.normalize_area_number("255,52") == 255.52
    assert MODULE.normalize_area_number("1,0 8 0") == 1080


def test_known_contract_type_corrections() -> None:
    assert MODULE.classify_scope_role(
        "L2022-00034-1", "용역", "영양교육센터 신축공사 공사입찰설명서"
    ) == "WORKS"
    assert MODULE.classify_scope_role(
        "L2024-00076-1", "공사", "퇴비화 시범 플랜트 설계용역"
    ) == "DESIGN_SERVICE"
    assert MODULE.classify_scope_role(
        "L2025-00078-1", "용역", "모성보건센터 공사 설계사 선정"
    ) == "DESIGN_OR_SUPERVISION_SERVICE"


def test_historical_manual_partition_is_complete() -> None:
    classified = (
        MODULE.HISTORICAL_C_NOTICES
        | MODULE.HISTORICAL_SERVICE_X
        | MODULE.HISTORICAL_NONBUILDING_X
        | {"L2019-00044-1", "L2019-00046-1"}
    )
    assert len(classified) == 40
    assert not (MODULE.HISTORICAL_C_NOTICES & MODULE.HISTORICAL_SERVICE_X)
    assert not (MODULE.HISTORICAL_C_NOTICES & MODULE.HISTORICAL_NONBUILDING_X)


def test_known_area_context_overrides_exclude_site_and_qualification_values() -> None:
    assert MODULE.AREA_MANUAL_OVERRIDES["L2020-00003-1"]["value"] == 3117
    assert MODULE.AREA_MANUAL_OVERRIDES["L2021-00025-1"]["value"] == 1325.32
    assert MODULE.AREA_MANUAL_OVERRIDES["L2023-00009-1"]["value"] == 835.67
    assert "L2025-00056-1" in MODULE.RECENT_AREA_QUALIFICATION


def test_strict_grades_are_not_inferred_from_automatic_table_signals() -> None:
    assert {row["grade"] for row in MODULE.STRICT_NOTICE_REVIEWS.values()} == {"A", "B"}
    assert len([row for row in MODULE.STRICT_NOTICE_REVIEWS.values() if row["grade"] == "A"]) == 2
    assert MODULE.RELATED_OTHER_PACKAGE_EVIDENCE["2023-00087"]["grade"].startswith("B")
