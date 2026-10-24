"""착오 기재 항목 결론·불공제 정답 테스트. 작성 Claude 2026-10-24 (docs/SPEC_gold_gaps4d.md)."""
import asyncio, json
from korean_tax_calc_mcp.server import mcp


def c(items):
    r = asyncio.run(mcp.call_tool("vat_input_tax_deduction", {"period": "2023-2", "filing": "확정", "items": items}))
    return json.loads((r.content[0] if hasattr(r, "content") else r[0][0]).text)


def test_misstated_amount_is_deducted_conclusion():
    r = c([{"항목": "원재료", "증빙": "세금계산서", "공급가액": 110000000, "실제공급가액": 100000000, "성격": "일반"}])
    item = r["계산"]["항목별"][0]
    assert item["공제세액"] == 10000000 and not item["불공제사유"]
    j = [x for x in r["판단"] if x["항목"] == "원재료"]
    assert j and j[0]["결론"].startswith("공제")


def test_misstated_amount_with_other_disallowance():
    r = c([{"항목": "대표 개인 물품", "증빙": "세금계산서", "공급가액": 11000000, "실제공급가액": 10000000, "성격": "사업무관"}])
    item = r["계산"]["항목별"][0]
    assert item["공제세액"] == 0 and item["불공제사유"]
    assert r["결과"]["공제매입세액"] == 0
