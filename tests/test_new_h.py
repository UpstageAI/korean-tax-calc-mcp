"""종교인소득 religious_income — 소득세법 제21조①26호(2018.1.1. 시행), 제12조5호아목, 시행령 제19조·제87조3호, 제14조③8호가목."""
import asyncio, json

import pytest

from korean_tax_calc_mcp.server import mcp

M = 1_000_000


def c(tool, a):
    r = asyncio.run(mcp.call_tool(tool, a))
    return json.loads((r.content[0] if hasattr(r, "content") else r[0][0]).text)


def ri(**a):
    return c("religious_income", a)


def test_table_band_2_2023_with_nontaxable():
    # 비과세: 학자금 200만 + 식사대 min(240만, 20만×12) 240만(시행령 제19조②2호, 2023~ 20만)
    #   + 자가운전 min(300만, 20만×12) 240만 + 보육 min(180만, 10만×12) 120만(제12조5호아목4, 2023은 10만) = 800만
    # 과세대상 4,200만 → 표 2,600만 + 200만×30% = 2,660만 → 소득금액 1,540만
    r = ri(year=2023, amount=50 * M, scholarship=2 * M, meal_allowance=2_400_000, meal_months=12, meal_provided=False,
           vehicle_allowance=3 * M, vehicle_months=12, vehicle="본인소유",
           childcare_allowance=1_800_000, childcare_months=12, childcare_children=1)
    R = r["결과"]
    assert R["비과세_합계"] == 8 * M
    assert R["과세대상_받은금액"] == 42 * M
    assert R["필요경비"] == 26_600_000
    assert R["기타소득금액"] == 15_400_000
    assert R["선택적_분리과세_가능"] is False


def test_table_band_1_2018():
    # 1,800만 × 80% = 1,440만 → 360만
    R = ri(year=2018, amount=18 * M)["결과"]
    assert (R["필요경비"], R["기타소득금액"]) == (14_400_000, 3_600_000)


def test_table_band_4_actual_expense_larger():
    # 7,000만: 표 3,200만 + 1,000만×20% = 3,400만, 실제 4,000만이 더 크면 실제(시행령 제87조3호 단서)
    R = ri(year=2021, amount=70 * M, actual_expense=40 * M)["결과"]
    assert R["필요경비_표금액"] == 34 * M
    assert R["필요경비"] == 40 * M and R["기타소득금액"] == 30 * M


def test_table_band_3():
    # 5,000만: 2,600만 + 1,000만×30% = 2,900만
    assert ri(year=2026, amount=50 * M)["결과"]["필요경비"] == 29 * M


def test_optional_separate_taxation_needs_withholding():
    # 300만 × 20% = 60만 ≤ 300만 — 26호는 제14조③8호가목 열거(2018~), 원천징수된 소득이면 선택 가능
    assert ri(year=2019, amount=3 * M, withheld=True)["결과"]["선택적_분리과세_가능"] is True
    assert ri(year=2019, amount=3 * M, withheld=False)["결과"]["선택적_분리과세_가능"] is False
    assert ri(year=2019, amount=3 * M)["결과"]["선택적_분리과세_가능"] is None


def test_childcare_per_child_2026_vs_2025():
    # 2026~ 자녀 1명당 월 20만(제12조5호아목4 개정 2025.12.23), 2024~2025 1인당 월 20만
    a = dict(amount=30 * M, childcare_allowance=4_800_000, childcare_months=12, childcare_children=2)
    assert ri(year=2026, **a)["결과"]["비과세_합계"] == 4_800_000
    assert ri(year=2025, **a)["결과"]["비과세_합계"] == 2_400_000
    assert ri(year=2023, **a)["결과"]["비과세_합계"] == 1_200_000
    assert ri(year=2026, amount=30 * M, childcare_allowance=1 * M, childcare_months=12, childcare_children=0)["결과"]["비과세_합계"] == 0


def test_leased_vehicle_from_2025():
    # 본인 명의 임차 차량: 시행령 제19조③2호 개정 2025.2.28, 부칙 제4조 — 2025 과세기간 지급분부터
    a = dict(amount=30 * M, vehicle_allowance=3 * M, vehicle_months=12, vehicle="본인명의임차")
    assert ri(year=2024, **a)["결과"]["비과세_합계"] == 0
    assert ri(year=2025, **a)["결과"]["비과세_합계"] == 2_400_000


def test_meal_allowance_limit_and_provided():
    a = dict(amount=30 * M, meal_allowance=2_400_000, meal_months=12)
    assert ri(year=2022, meal_provided=False, **a)["결과"]["비과세_합계"] == 1_200_000
    assert ri(year=2023, meal_provided=True, **a)["결과"]["비과세_합계"] == 0


def test_activity_fund_and_reimbursement_fully_exempt():
    R = ri(year=2020, amount=25 * M, religious_activity_fund=3 * M, expense_reimbursement=1 * M, housing_benefit=1 * M)["결과"]
    # 과세대상 2,000만 × 80% = 1,600만 → 400만
    assert R["비과세_합계"] == 5 * M and R["기타소득금액"] == 4 * M


@pytest.mark.parametrize("year", [2016, 2017])
def test_before_2018_rejected(year):
    r = ri(year=year, amount=10 * M)
    assert "error" in r and "2018.1.1" in r["문제"][0]


def test_wage_route_points_to_wage_tools():
    r = ri(year=2022, amount=10 * M, route="근로소득")
    assert "error" in r and "earned_income_gross_pay" in r["문제"][0] and "제21조④" in r["문제"][0]
    assert "제21조③" in ri(year=2019, amount=10 * M, route="근로소득")["문제"][0]


def test_missing_facts_and_overflow_rejected():
    assert "error" in ri(year=2022, amount=10 * M, meal_allowance=1 * M)
    assert "error" in ri(year=2022, amount=10 * M, childcare_allowance=1 * M, childcare_months=12)
    assert "error" in ri(year=2022, amount=1 * M, scholarship=2 * M)


def _rejected(a):
    try:
        r = ri(**a)
    except Exception:
        return True
    return "error" in r


def test_bool_and_string_amount_rejected():
    assert _rejected({"year": 2022, "amount": True})
    assert _rejected({"year": 2022, "amount": "1000000"})
    assert _rejected({"year": 2022, "amount": 1000, "scholarship": False})


def test_find_tool_and_description():
    r = c("find_tool", {"query": "목사 사례비 종교인소득"})
    assert r["결과"]["후보"][0]["도구"] == "religious_income"
    d = mcp._tool_manager._tools["religious_income"].description
    assert "언제:" in d and "입력:" in d and "지원하지 않음" in d
