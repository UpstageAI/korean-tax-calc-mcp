"""기존 도구 확장 — 2025 전통시장 추가한도, 기타·금융소득 항목 추가, 부담부증여, 의제배당 재원 추가의 정답 테스트. 작성 Claude 2026-10-24.
값은 문항을 손으로 푼 결과(docs/SPEC_gold_gaps5.md)."""
import asyncio, json
import pytest
from korean_tax_calc_mcp.server import mcp


def c(tool, a):
    r = asyncio.run(mcp.call_tool(tool, a))
    return json.loads((r.content[0] if hasattr(r, "content") else r[0][0]).text)


def err(r):
    return "입력 확인 필요" in json.dumps(r, ensure_ascii=False)


ENT = [{"항목": "일반 기업업무추진비", "금액": 95000000, "증빙": "적격"},
       {"항목": "임직원 단합대회", "금액": 10000000, "증빙": "적격", "성격": "직원단체_비법인"},
       {"항목": "관광공연장 입장권", "금액": 6000000, "증빙": "적격", "성격": "문화"},
       {"항목": "전통시장 과일", "금액": 9000000, "증빙": "적격", "성격": "전통시장"}]
REV = {"매출액": 18000000000, "특수관계매출": 2000000000}


def test_entertainment_traditional_market_extra_limit_2025():
    # 2025 사업연도(2026.1.1 이후 신고): 법률 제21223호 부칙 제31조 → 한도액의 20%, 전통시장·지역사랑상품권 (Claude 10-25 수정)
    r = c("entertainment_adjustment", {"year": 2025, "sme": True, "ledger": ENT, "revenue": REV})
    assert r["계산"]["전통시장한도"] == 9000000          # min(9,000,000, 78,400,000 × 20%)
    assert r["결과"]["한도초과"] == 16600000            # 110,000,000 − (36,000,000 + 42,400,000 + 6,000,000 + 9,000,000)


@pytest.mark.parametrize("year", [2023, 2024])
def test_entertainment_traditional_market_10pct_2023_2024(year):
    # 법률 제19936호 부칙 제35조: 2024.1.1 이후 신고분부터 → 2023·2024 사업연도 10%
    r = c("entertainment_adjustment", {"year": year, "sme": True, "ledger": ENT, "revenue": REV})
    assert r["계산"]["전통시장한도"] == 7840000
    assert r["결과"]["한도초과"] == 17760000


def test_entertainment_traditional_market_not_before_2023():
    r = c("entertainment_adjustment", {"year": 2022, "sme": True, "ledger": ENT, "revenue": REV})
    assert r["계산"].get("전통시장한도", 0) == 0
    assert any("전통시장" in p["항목"] and "2024.1.1" in p["결론"] for p in r["판단"])


VOUCHER = [{"항목": "일반 기업업무추진비", "금액": 95000000, "증빙": "적격"},
           {"항목": "지역사랑상품권 선물", "금액": 4000000, "증빙": "적격", "성격": "지역사랑상품권"},
           {"항목": "온누리상품권 선물", "금액": 3000000, "증빙": "적격", "성격": "온누리상품권"}]


@pytest.mark.parametrize("year, 대상", [(2024, 0), (2025, 4000000), (2026, 7000000)])
def test_entertainment_vouchers_by_year(year, 대상):
    # 지역사랑상품권: 2025 사업연도부터(제21223호), 온누리상품권: 2026 사업연도 지출분부터(제21612호 부칙 제4조)
    r = c("entertainment_adjustment", {"year": year, "sme": True, "ledger": VOUCHER, "revenue": REV})
    assert r["계산"].get("전통시장한도", 0) == 대상


def test_other_income_horse_betting_refund_and_slot_machine():
    r = c("other_income_aggregate", {"year": 2025, "items": [
        {"kind": "승마투표권환급금", "amount": 2010000, "unit_bet": 10000},
        {"kind": "위약금·배상금", "amount": 1000000, "deposit_substituted": 1000000},
        {"kind": "주택입주지체상금", "amount": 1500000}]})
    assert sum(x["원천징수세액"] for x in r["항목별"]) == 460000
    horse = [x for x in r["항목별"] if x.get("kind") == "승마투표권환급금" or "승마" in str(x)][0]
    assert horse["소득금액"] == 2000000 and horse["원천징수세액"] == 400000


def test_other_income_slot_machine_below_threshold_not_withheld():
    r = c("other_income_aggregate", {"year": 2022, "items": [
        {"kind": "위약금·배상금", "amount": 4000000, "deposit_substituted": 4000000},
        {"kind": "일시적인적용역", "amount": 3000000}, {"kind": "배임수재", "amount": 6000000},
        {"kind": "산업재산권대여", "amount": 1000000}, {"kind": "주택입주지체상금", "amount": 2000000},
        {"kind": "슬롯머신당첨금", "amount": 1500000}]})
    assert sum(x["소득금액"] for x in r["항목별"] if x["원천징수세액"] > 0) == 2000000
    r = c("other_income_aggregate", {"year": 2022, "items": [{"kind": "슬롯머신당첨금", "amount": 3000000}]})
    assert sum(x["원천징수세액"] for x in r["항목별"]) == 600000


def test_financial_income_damages_interest_and_public_trust_excluded():
    r = c("financial_income_aggregate", {"year": 2022, "items": [
        {"kind": "환매조건부매매차익", "amount": 5000000},
        {"kind": "저축성보험차익", "premium": 8000000, "payout": 11000000, "contract_year": 2018},
        {"kind": "비영업대금이익", "amount": 2000000},
        {"kind": "손해배상법정이자", "amount": 500000},
        {"kind": "공익신탁이익", "amount": 1200000}]})
    assert r["계산"]["이자"] == 10000000
    j = json.dumps(r["판단"], ensure_ascii=False)
    assert "기타소득" in j and "비과세" in j


def test_capital_gains_burdened_gift_standard_price():
    r = c("capital_gains_income", {"asset_type": "토지", "acquisition_date": "2015-02-01", "transfer_date": "2025-12-01",
                                   "burdened_gift": {"증여가액": 500000000, "채무액": 200000000, "평가": "기준시가", "취득_기준시가": 300000000}})
    assert r["결과"]["양도소득금액"] == 61120000


def test_capital_gains_burdened_gift_conflicts_with_prices():
    r = c("capital_gains_income", {"asset_type": "토지", "acquisition_date": "2015-02-01", "transfer_date": "2025-12-01", "transfer_price": 1,
                                   "burdened_gift": {"증여가액": 500000000, "채무액": 200000000, "평가": "기준시가", "취득_기준시가": 300000000}})
    assert err(r)


SH = {"year": 2025, "par_value": 5000, "shareholders": [{"name": "A", "shares": 100}, {"name": "기타", "shares": 900}],
      "self_stock_allotment": "미교부", "shareholder_type": "법인"}


def test_bonus_shares_new_sources():
    assert c("deemed_dividend_bonus_shares", {**SH, "source": "상환주식_주식발행초과금", "capitalized_amount": 8000000})["결과"]["주주별_의제배당"]["A"] == 800000
    assert c("deemed_dividend_bonus_shares", {**SH, "source": "자기주식소각이익_2년내", "capitalized_amount": 6000000})["결과"]["주주별_의제배당"]["A"] == 600000
    assert c("deemed_dividend_bonus_shares", {**SH, "source": "자기주식소각이익", "capitalized_amount": 4000000})["결과"]["주주별_의제배당"]["A"] == 0
