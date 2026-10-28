"""10/28 프론티어 모델 점검에서 나온 수정의 회귀 테스트. 작성 Claude 2026-10-28."""
import asyncio, json, os, tempfile
import openpyxl
from korean_tax_calc_mcp.server import mcp


def c(tool, a):
    r = asyncio.run(mcp.call_tool(tool, a))
    return json.loads((r.content[0] if hasattr(r, "content") else r[0][0]).text)


def test_residential_rental_loss_offsets_other_income():
    r = c("income_loss_offset", {"year": 2026, "incomes": {"부동산임대": -5000000, "주거용임대": -20000000, "근로": 30000000,
                                                          "기타": 5000000, "이자": 15000000, "배당": 10000000},
                                 "business": {"book_income": 10000000, "adjustments": []}})
    assert r["결과"]["종합소득금액"] == 50000000
    assert r["결과"]["이월결손금(다음 연도로)"]["부동산임대"] == 5000000


def test_unwithheld_financial_income_taxed_below_threshold():
    r = c("financial_income_aggregate", {"year": 2025, "items": [
        {"kind": "외국법인배당", "amount": 3000000, "withheld": False},
        {"kind": "비영업대금이익", "amount": 2000000, "withheld": False},
        {"kind": "상장법인현금배당", "amount": 1000000}]})
    assert r["결과"]["합산액"] == 5000000
    assert r["결과"]["이자소득금액"] == 2000000 and r["결과"]["배당소득금액"] == 3000000


def test_withheld_default_keeps_separate_taxation():
    r = c("financial_income_aggregate", {"year": 2025, "items": [{"kind": "예금이자", "amount": 5000000}]})
    assert r["결과"]["합산액"] == 0


def test_form_keeps_traditional_market_ratio_with_zero_spending():
    with tempfile.TemporaryDirectory() as d:
        r = c("export_workbook", {"title": "t", "output_dir": d, "calls": [{"label": "x", "tool": "entertainment_adjustment",
              "args": {"year": 2025, "sme": True, "revenue": {"매출액": 15000000000}, "ledger": [{"항목": "카드", "금액": 93000000}]}}]})
        ws = openpyxl.load_workbook(r["결과"]["파일"])["별지23(갑) 기업업무추진비"]
        assert "전통시장등비율" in str(ws["D25"].value)


def test_deemed_input_preliminary_return_skips_limit():
    base = {"period": "2026-1", "industry": "제조", "individual": False, "sme": False, "purchase": 100000000, "base": 40000000}
    final = c("vat_deemed_input_credit", base)
    pre = c("vat_deemed_input_credit", {**base, "filing": "예정"})
    assert pre["결과"]["의제매입세액"] > final["결과"]["의제매입세액"] if "결과" in pre else pre["의제매입세액"] > final["의제매입세액"]
    assert "Infinity" not in json.dumps(pre)


def test_simplified_vat_wording_consistent_above_threshold():
    r = c("simplified_vat_return", {"year": 2026, "business_type": "음식점업", "prior_year_supplies": 75000000,
          "ledger": {"공급": [{"항목": "신용카드매출전표 발행분", "금액": 50000000}],
                     "매입": [{"항목": "조미료(세금계산서)", "금액": 22000000}]}})
    txt = json.dumps(r, ensure_ascii=False)
    assert "< 영수증발급기준" not in txt


def _top(q, n=3):
    return [x["도구"] for x in c("find_tool", {"query": q, "n": n})["결과"]["후보"]]


def test_find_tool_surfaces_tools_models_missed():
    assert _top("해산한 법인 청산소득")[0] == "liquidation_income"
    assert _top("보험차익으로 대체 취득한 기계 일시상각충당금")[0] == "asset_grant_reserve"
    assert _top("당기순이익에서 차가감소득금액")[0] == "income_adjustment_total"
    assert "capital_gains_income" in _top("아파트 팔았을 때 양도세")
    assert _top("업무무관 가지급금 지급이자")[0] == "nonbusiness_interest_disallowance"
    assert "deemed_interest" in _top("unfair transaction deemed interest")
