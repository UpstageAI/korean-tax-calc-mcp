"""부가세 판정 도구 입력 검증 보강 정답 테스트. 작성 Claude 2026-10-24 (docs/SPEC_gold_gaps4b.md)."""
import asyncio, json
import pytest
from korean_tax_calc_mcp.server import mcp


def c(tool, a):
    r = asyncio.run(mcp.call_tool(tool, a))
    return json.loads((r.content[0] if hasattr(r, "content") else r[0][0]).text)


ITEM = {"항목": "a", "증빙": "세금계산서", "공급가액": 100, "성격": "일반"}


@pytest.mark.parametrize("period", ["2025-3", "abc", "25-1"])
def test_period_format(period):
    for tool, args in (("vat_input_tax_deduction", {"filing": "확정", "items": [ITEM]}),
                       ("vat_deemed_supply_items", {"items": [{"항목": "x", "거래": "판매", "매입세액공제": True, "시가": 100}]})):
        r = c(tool, {"period": period, **args})
        assert r.get("error", "").startswith("입력 확인 필요") and any("period" in p for p in r["문제"]), (tool, r)


def test_negative_supply_value_rejected():
    r = c("vat_input_tax_deduction", {"period": "2025-1", "filing": "확정", "items": [{**ITEM, "공급가액": -100}]})
    assert r.get("error", "").startswith("입력 확인 필요") and any("공급가액" in p for p in r["문제"])


def test_negative_deemed_value_rejected():
    r = c("vat_deemed_supply_items", {"period": "2025-1", "items": [{"항목": "x", "거래": "개인적공급", "매입세액공제": True, "시가": -5}]})
    assert r.get("error", "").startswith("입력 확인 필요") and any("시가" in p for p in r["문제"])
