"""2차 점검(실사용 재풀이)에서 나온 입력·안내 문제 회귀 테스트. 작성 Claude 2026-10-28."""
import asyncio, json
from korean_tax_calc_mcp.server import mcp


def c(tool, a):
    r = asyncio.run(mcp.call_tool(tool, a))
    return json.loads((r.content[0] if hasattr(r, "content") else r[0][0]).text)


def test_find_tool_says_none_when_nothing_fits_and_accepts_keyword():
    assert c("find_tool", {"query": "가상자산사업자 거래내역 자료 제출기한"})["결과"]["후보"] == []
    assert c("find_tool", {"keyword": "해산한 법인 청산소득"})["결과"]["후보"][0]["도구"] == "liquidation_income"


def test_entertainment_in_kind_amount_only():
    r = c("entertainment_adjustment", {"year": 2026, "sme": True, "부가세별도": False,
                                       "ledger": [{"항목": "현물접대", "금액": 15000000, "성격": "현물"}]})
    assert "error" not in r and r["결과"]["시부인_대상"] == 15000000


def test_income_adjustment_aliases_and_precise_labels():
    r = c("income_adjustment_total", {"net_income": 100000000, "items": [
        {"항목": "법인세", "종류": "법인세", "금액": 8000000}, {"항목": "환급금 이자", "종류": "국세환급가산금", "금액": 2000000}]})
    adj = {e["구분"]: (e["조정"], e["조정구분"]) for e in r["결과"]["세무조정"]}
    assert adj["법인세"] == ("익금산입", "손금불산입") and adj["환급금 이자"] == ("손금산입", "익금불산입")
    e = c("income_adjustment_total", {"net_income": 1, "items": [{"항목": "a", "종류": "없는1", "금액": 1}, {"항목": "b", "종류": "없는2", "금액": 1}]})
    assert "2건" in e["문제"][0] and "허용 종류" in e


def test_simplified_vat_prior_year_optional_without_unreceived_invoices():
    r = c("simplified_vat_return", {"year": 2026, "business_type": "음식점업",
          "ledger": {"공급": [{"항목": "신용카드매출전표 발행분", "금액": 50000000}],
                     "매입": [{"항목": "조미료(세금계산서)", "금액": 22000000}]}})
    assert "error" not in r


def test_bonus_share_nontaxable_citation():
    r = c("deemed_dividend_bonus_shares", {"year": 2025, "source": "주식발행초과금", "capitalized_amount": 16000000, "par_value": 5000,
          "shareholders": [{"name": "A", "shares": 1000}, {"name": "기타", "shares": 9000}], "self_stock_allotment": "미교부", "shareholder_type": "법인"})
    txt = json.dumps(r, ensure_ascii=False)
    assert "제16조①2호 단서 가목" in txt and "제16조①3호 단서" not in txt
