"""다른 브랜치 도구 중복 등록 방지 정답 테스트. 작성 Claude 2026-10-24, 10-25 수정 (docs/SPEC_gold_gaps4c.md)."""
import pathlib, re
from korean_tax_calc_mcp.server import mcp

SRC = pathlib.Path(__file__).resolve().parents[1] / "korean_tax_calc_mcp" / "server.py"


def test_vat_tools_registered_and_no_duplicate_defs():
    names = set(mcp._tool_manager._tools)
    assert {"vat_input_tax_deduction", "vat_deemed_supply_items"} <= names
    src = SRC.read_text(encoding="utf-8")
    for fn in ("vat_input_tax_deduction", "vat_deemed_supply_items", "personal_deduction", "pension_income",
               "income_loss_offset", "disaster_loss_credit"):
        assert len(re.findall(rf"^def {fn}\(", src, re.M)) <= 1, fn   # 다른 브랜치 도구는 한 번만 정의(머지 후 중복 금지)
