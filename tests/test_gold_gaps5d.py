"""전통시장 추가한도 + 엑셀 계산식 합치기 정답 테스트. 작성 Claude 2026-10-25 (docs/SPEC_gold_gaps5d.md)."""
import pytest
from test_export_workbook_c import c, evaluate, ENT as ENT_C
from test_gold_gaps5 import ENT, REV


def test_market_limit_in_formula_2025():
    r = c("entertainment_adjustment", {"year": 2025, "sme": True, "ledger": ENT, "revenue": REV})
    steps = evaluate(r)
    assert steps["전통시장한도"]["값"] == r["계산"]["전통시장한도"] == 7840000
    assert "전통시장한도" in steps["한도"]["식"]
    assert steps["한도초과"]["값"] == r["결과"]["한도초과"] == 17760000


@pytest.mark.parametrize("year", [2024, 2023])
def test_no_market_step_before_2025(year):
    r = c("entertainment_adjustment", {"year": year, "sme": True, "ledger": ENT, "revenue": REV})
    steps = evaluate(r)
    assert "전통시장한도" not in steps
    assert steps["한도초과"]["값"] == r["결과"]["한도초과"]


def test_no_market_spend_no_step():
    r = c("entertainment_adjustment", ENT_C)
    steps = evaluate(r)
    assert "전통시장한도" not in steps and steps["한도초과"]["값"] == r["결과"]["한도초과"] == 2280000
