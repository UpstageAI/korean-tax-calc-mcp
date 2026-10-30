"""소득세 종합문제형 세 도구 — 개인 기부금 필요경비·통합발행채권 할인액·연금수령한도. 작성 Claude 2026-10-30."""
import asyncio, json
from korean_tax_calc_mcp.server import mcp


def c(tool, a):
    r = asyncio.run(mcp.call_tool(tool, a))
    return json.loads((r.content[0] if hasattr(r, "content") else r[0][0]).text)


def test_individual_donation_full_case():
    # 기준소득 60,000,000, 정치 300,000·고향 2,000,000, 특례(사립학교 장학금 20,000,000 + 이재민 구호 2,000,000), 종교 10,000,000, 사회복지 6,000,000,
    # 자원봉사 74시간(10일×80,000=800,000)+유류비 350,000(이동 100,000 제외)+재료비 150,000 = 1,200,000, 현물(의료법인 일반) 장부 2,000,000·시가 3,000,000
    r = c("individual_donation_expense", {"year": 2025, "base_income": 60_000_000, "political": 300_000, "hometown": 2_000_000, "special": 22_000_000, "general": 6_000_000, "religious": 10_000_000,
                                           "volunteer": {"hours": 74, "fuel": 350_000, "transport_fuel": 100_000, "materials": 150_000}, "in_kind": [{"kind": "일반", "book": 2_000_000, "market": 3_000_000}]})
    res = r["결과"]
    assert r["계산"]["자원봉사용역"]["가액"] == 1_200_000 and r["계산"]["특례기부금_당기(현물·자원봉사 포함)"] == 23_200_000
    assert res["정치·고향_초과분_산입"] == 2_100_000 and res["특례기부금_산입"] == 23_200_000
    assert r["계산"]["일반_한도"] == 10_410_000 and res["일반기부금_산입"] == 10_410_000 and res["일반_한도초과_이월"] == 8_590_000
    assert res["필요경비_산입_합계"] == 35_710_000 and res["기부금_산입_후_사업소득금액"] == 24_290_000 and res["정치·고향_세액공제_대상(10만원_이하)"] == 200_000


def test_individual_donation_no_religion_and_carry():
    r = c("individual_donation_expense", {"year": 2025, "base_income": 100_000_000, "carried_loss": 10_000_000, "special": 95_000_000, "general": 20_000_000, "carried_general": 5_000_000})
    res = r["결과"]
    assert res["특례기부금_산입"] == 90_000_000 and res["특례_한도초과_이월"] == 5_000_000   # 한도 = 100M − 10M
    assert r["계산"]["일반_한도"] == 0 and res["일반기부금_산입"] == 0 and res["일반_한도초과_이월"] == 20_000_000


def test_integrated_issue_bond_discount_excluded():
    r = c("financial_income_aggregate", {"year": 2025, "items": [{"kind": "예금이자", "amount": 24_000_000, "withheld": 3_360_000}, {"kind": "통합발행채권할인액", "amount": 5_000_000}]})
    assert r["결과"]["이자소득금액"] == 24_000_000
    assert any(h["항목"] == "통합발행채권할인액" and "제외" in h["결론"] for h in r["판단"])


def test_pension_withdrawal_year_count_from_first_eligible_year():
    r = c("pension_account_withdrawal", {"year": 2025, "birth_date": "1968-03-01", "join_date": "2015-01-01", "start_request_date": "2025-01-01", "balance_at_period_start": 70_000_000, "withdrawal": 12_000_000,
                                         "contributions_total": 56_000_000, "contributions_not_deducted": 2_000_000, "deferred_retirement_income": 6_000_000, "investment_income": 8_000_000})
    assert r["계산"]["연금수령연차"] == 3 and r["계산"]["연금수령한도"] == 10_500_000 and r["결과"]["기타소득_연금외수령"] == 1_500_000
