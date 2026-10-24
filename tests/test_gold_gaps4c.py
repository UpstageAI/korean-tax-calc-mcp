"""다른 브랜치 도구 등록 제거 정답 테스트. 작성 Claude 2026-10-24 (docs/SPEC_gold_gaps4c.md)."""
from korean_tax_calc_mcp.server import mcp


def test_only_vat_tools_added_here():
    names = set(mcp._tool_manager._tools)
    assert {"vat_input_tax_deduction", "vat_deemed_supply_items"} <= names
    assert not names & {"personal_deduction", "pension_income", "income_loss_offset", "disaster_loss_credit"}
