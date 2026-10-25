"""인적공제 소득금액 계산 오류 정답 테스트. 작성 Claude 2026-10-24 (docs/SPEC_gold_gaps3c.md)."""
import asyncio, json
from korean_tax_calc_mcp.server import mcp

T = {"sex": "남", "birth_year": 1980, "has_spouse": False, "comprehensive_income": 40000000}


def person(items, name="부친"):
    r = asyncio.run(mcp.call_tool("personal_deduction", {"year": 2023, "taxpayer": T, "persons": [
        {"name": name, "relation": "직계존속", "birth_year": 1950, "income_items": items}]}))
    r = json.loads((r.content[0] if hasattr(r, "content") else r[0][0]).text)
    return next(p for p in r["사람별"] if p["name"] == name)


def test_interest_items_use_own_amount():
    p = person([{"kind": "이자", "amount": 15000000}, {"kind": "이자", "amount": 10000000}])
    assert sorted(x["반영금액"] for x in p["소득처리내역"]) == [10000000, 15000000]


def test_wage_income_is_gross_minus_deduction():
    # 총급여 250만 → 근로소득공제 175만(70%) → 근로소득금액 75만 + 기타소득금액 20만 = 95만 ≤ 100만
    p = person([{"kind": "근로_총급여", "amount": 2500000}, {"kind": "기타소득금액", "amount": 200000}])
    wage = next(x for x in p["소득처리내역"] if x["kind"] == "근로_총급여")
    assert wage["반영금액"] == 750000
    assert p["기본공제"] is True


def test_wage_only_ignores_zero_effect_items():
    # 총급여 400만(근로소득금액 120만 > 100만)이지만 근로소득만 있고 총급여 500만 이하 → 대상. 공적연금 과세제외분은 소득 아님
    p = person([{"kind": "근로_총급여", "amount": 4000000}, {"kind": "공적연금_과세제외", "amount": 30000000}], name="모친")
    assert p["기본공제"] is True
