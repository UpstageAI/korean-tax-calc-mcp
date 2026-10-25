"""연금계좌 인출(연금수령한도·인출순서)·상증 재산평가(시가 우선순위·저당권 특례) 정답 테스트. 작성 Claude 2026-10-24.
값은 문항을 손으로 푼 결과와 조문 원문 대조(docs/SPEC_gold_gaps6.md)."""
import asyncio, json
from korean_tax_calc_mcp.server import mcp


def c(tool, a):
    r = asyncio.run(mcp.call_tool(tool, a))
    return json.loads((r.content[0] if hasattr(r, "content") else r[0][0]).text)


def err(r):
    return "입력 확인 필요" in json.dumps(r, ensure_ascii=False)


ACC = {"year": 2024, "birth_date": "1959-03-01", "join_date": "2012-01-15", "start_request_date": "2023-01-01",
       "balance_at_period_start": 100000000, "withdrawal": 45000000,
       "contributions_total": 60000000, "contributions_not_deducted": 3000000,
       "deferred_retirement_income": 10000000, "investment_income": 30000000}


def test_pension_account_limit_order_pre2013_account():
    r = c("pension_account_withdrawal", ACC)
    assert r["계산"]["연금수령연차"] == 7 and r["계산"]["연금수령한도"] == 30000000
    assert r["결과"]["연금수령분"] == {"과세제외금액": 3000000, "이연퇴직소득": 10000000, "그밖": 17000000}
    assert r["결과"]["연금외수령분"] == {"과세제외금액": 0, "이연퇴직소득": 0, "그밖": 15000000}
    assert r["결과"]["사적연금_총연금액"] == 17000000


def test_pension_account_first_year_post2013_account():
    r = c("pension_account_withdrawal", {**ACC, "birth_date": "1960-05-01", "join_date": "2015-03-01", "start_request_date": "2024-01-01", "withdrawal": 12000000})
    assert r["계산"]["연금수령연차"] == 1 and r["계산"]["연금수령한도"] == 12000000
    assert r["결과"]["연금외수령분"]["그밖"] == 0


def test_pension_account_no_limit_from_year_11():
    r = c("pension_account_withdrawal", {**ACC, "year": 2028})
    assert r["계산"]["연금수령연차"] == 11 and r["계산"]["연금수령한도"] is None
    assert sum(r["결과"]["연금외수령분"].values()) == 0


def test_pension_account_under_55_is_non_pension_withdrawal():
    r = c("pension_account_withdrawal", {**ACC, "birth_date": "1975-01-01"})
    assert sum(r["결과"]["연금수령분"].values()) == 0
    assert sum(r["결과"]["연금외수령분"].values()) == 45000000


def test_pension_account_inconsistent_inputs():
    assert err(c("pension_account_withdrawal", {**ACC, "contributions_not_deducted": 70000000}))


GIFT = {"kind": "증여", "valuation_date": "2023-07-01", "supplementary_value": 150000000,
        "market_values": [{"대상": "유사재산", "종류": "매매", "가액": 250000000, "날짜": "2023-05-01"},
                          {"대상": "해당재산", "종류": "감정", "가액": 200000000, "날짜": "2023-08-01"}],
        "secured_debt": {"채권최고액": 234000000, "채무액": 180000000}}


def test_valuation_own_appraisal_over_similar_sale_and_mortgage():
    r = c("inheritance_gift_valuation", GIFT)
    assert r["결과"]["평가액"] == 200000000
    assert r["계산"]["시가"] == 200000000 and r["계산"]["담보채권액"] == 180000000


def test_valuation_similar_sale_when_no_own_value():
    r = c("inheritance_gift_valuation", {**GIFT, "market_values": [GIFT["market_values"][0]], "secured_debt": None})
    assert r["결과"]["평가액"] == 250000000


def test_valuation_outside_window_falls_back():
    mv = [{"대상": "해당재산", "종류": "감정", "가액": 200000000, "날짜": "2023-10-15"}]
    r = c("inheritance_gift_valuation", {**GIFT, "market_values": mv, "secured_debt": None})
    assert r["결과"]["평가액"] == 150000000 and r["계산"]["시가"] is None


def test_valuation_inheritance_window_and_mortgage_floor():
    mv = [{"대상": "해당재산", "종류": "매매", "가액": 200000000, "날짜": "2023-12-20"}]
    r = c("inheritance_gift_valuation", {"kind": "상속", "valuation_date": "2023-07-01", "supplementary_value": 150000000,
                                 "market_values": mv, "secured_debt": {"채권최고액": 234000000, "채무액": 260000000}})
    assert r["계산"]["시가"] == 200000000 and r["결과"]["평가액"] == 234000000


def test_valuation_two_appraisals_averaged_and_closest_sale():
    mv = [{"대상": "해당재산", "종류": "감정", "가액": 200000000, "날짜": "2023-06-01"},
          {"대상": "해당재산", "종류": "감정", "가액": 220000000, "날짜": "2023-06-10"}]
    r = c("inheritance_gift_valuation", {**GIFT, "market_values": mv, "secured_debt": None})
    assert r["결과"]["평가액"] == 210000000
