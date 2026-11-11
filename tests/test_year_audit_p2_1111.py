"""연도 의존 전수 점검(2026-11-11) 2순위 가운데 국세기본법 계열·인정이자·원천징수세율(Claude 작성).
조문 확인: 국세기본법 제47조의5(2019.12.31.·2020.1.1.·2021.12.31.·2022.12.31. 시행본)와 법률 제16841호 부칙 제21조·제18586호 부칙 제7조,
제26조의2(2018.12.31.·2019.1.1.)와 법률 제16097호 부칙 제10조, 제47조의4(2026.6.30.·2026.7.1.),
법인세법 시행규칙 제43조②(2015.12.31. 1,000분의 69 → 2016.3.7. 1,000분의 46), 소득세법 제129조①3호(2019~2024 "계약기간 3년 이하")."""
import pytest
from _helpers import call as c

M = 1_000_000


# ── 1. 원천징수 등 납부지연가산세 ────────────────────────────────────────────────
def wl(**kw):
    return c("withholding_late_payment_penalty", kw)

def test_pre2020_obligation_uses_old_rule_10_percent_cap_only():
    """2018년 지급분: 3% + 납부기한 다음 날부터 납세고지일까지 일수분, 10% 한도. 고지 후분·50% 한도 없음."""
    r = wl(unpaid_tax=100 * M, due="2018-07-10", until="2019-03-01", notice_due="2019-03-31", paid_on="2019-12-31")
    assert "error" not in r, r
    g = r["결과"]
    # 2018.7.11.~2019.2.11. 216일 × 3/10,000 = 6,480,000, 2019.2.12.~3.1. 18일 × 25/100,000 = 450,000, 3% 3,000,000
    assert g["일수"] == 234 and g["3%분"] == 3 * M and g["일수분"] == 6_930_000
    assert g["가산세"] == 9_930_000 and g["고지후분"] == 0 and g["50%한도_적용"] is False
    assert "부칙 제21조" in r["근거"]
    assert "가산금" in str(r["주의"])

def test_pre2020_cap_at_10_percent():
    g = wl(unpaid_tax=100 * M, due="2017-03-10", until="2019-06-30")["결과"]
    assert g["가산세"] == 10 * M and g["한도_적용"] is True

def test_boundary_between_2019_and_2020_obligation():
    old = wl(unpaid_tax=10 * M, due="2020-01-10", until="2020-03-10")                    # 12월 지급분 — 2019년 성립으로 봄
    assert "2019" in old["결과"]["적용_규정"]["고지 전"] and "accrued_on" in str(old["주의"])
    new = wl(unpaid_tax=10 * M, due="2020-02-10", until="2020-03-10")
    assert new["결과"]["적용_규정"]["고지 전"] == "종전"                                    # 2026.7.1. 개정 전이라는 뜻의 '종전'(2020년 이후 규정)
    half = wl(unpaid_tax=10 * M, due="2020-01-10", until="2020-03-10", accrued_on="2019-07-15")   # 반기 납부: 7월 지급
    assert "2019" in half["결과"]["적용_규정"]["고지 전"] and "accrued_on" not in str(half.get("주의", ""))
    assert "error" in wl(unpaid_tax=10 * M, due="2020-02-10", until="2020-03-10", accrued_on="2020-03-01")

@pytest.mark.parametrize("due,until,notice_due,paid_on,excluded", [
    ("2021-01-10", "2021-03-01", "2021-03-31", "2021-09-30", False),      # 지정납부기한 2021년: 100만원 기준 → 120만원은 고지 후분 있음
    ("2022-01-10", "2022-03-01", "2022-03-31", "2022-09-30", True)])      # 2022년부터 150만원 기준 → 고지 후분 없음
def test_small_amount_threshold_by_year(due, until, notice_due, paid_on, excluded):
    g = wl(unpaid_tax=1_200_000, due=due, until=until, notice_due=notice_due, paid_on=paid_on)["결과"]
    assert (g["고지후분"] == 0) is excluded


# ── 2. 부과제척기간: 역외거래 7년·10년은 2019.1.1. 이후 성립분부터 ─────────────────────────
def al(**kw):
    return c("assessment_limitation", kw)

@pytest.mark.parametrize("due,case,years", [("2018-05-31", "일반", 5), ("2018-05-31", "무신고", 7), ("2018-05-31", "부정행위", 15),
                                            ("2020-06-01", "일반", 7), ("2020-06-01", "무신고", 10), ("2016-05-31", "일반", 5)])
def test_offshore_period_by_accrual(due, case, years):
    r = al(due_date=due, case=case, offshore=True)
    assert "error" not in r, r
    assert r["결과"]["제척기간(년)"] == years

def test_offshore_2019_due_date_needs_accrual_date():
    assert "error" in al(due_date="2019-05-31", case="일반", offshore=True)
    assert al(due_date="2019-05-31", case="일반", offshore=True, accrued_on="2018-12-31")["결과"]["제척기간(년)"] == 5     # 2018년 귀속 소득세
    assert al(due_date="2019-07-25", case="일반", offshore=True, accrued_on="2019-06-30")["결과"]["제척기간(년)"] == 7     # 2019년 1기 부가가치세
    assert al(due_date="2019-05-31", case="부정행위", offshore=True)["결과"]["제척기간(년)"] == 15                         # 부정행위는 전후 같음
    assert al(due_date="2019-05-31", case="일반")["결과"]["제척기간(년)"] == 5                                            # 역외가 아니면 성립일 불필요
    old = al(due_date="2018-05-31", case="일반", offshore=True)
    assert any("부칙 제10조" in str(x) for x in old.get("판단", []))

def test_assessment_limitation_rejects_before_2016():
    assert "error" in al(due_date="2005-05-31")


# ── 3. 가지급금 인정이자: 당좌대출이자율 2016.3.6.까지 6.9%, 이후 4.6% ─────────────────────────
def di(year_end, **kw):
    return c("deemed_interest", {"movements": [{"date": f"{int(year_end[:4])}-01-01", "amount": 1_000 * M}], "year_end": year_end,
                                 "rate_mode": "당좌선택", **kw})

def test_overdraft_rate_split_in_2016():
    r = di("2016-12-31")
    assert "error" not in r, r
    assert r["결과"]["시가이자"] == 50_147_540          # 10억 × (66일 × 6.9% + 300일 × 4.6%) ÷ 366
    assert "2016.3.6" in r["결과"]["판단"]

@pytest.mark.parametrize("year_end,expect", [("2017-12-31", 46 * M), ("2023-12-31", 46 * M), ("2024-12-31", 46 * M)])
def test_overdraft_rate_after_2016(year_end, expect):
    assert di(year_end)["결과"]["시가이자"] == expect

def test_overdraft_split_with_deposits_is_refused():
    r = di("2016-12-31", deposits=[{"date": "2016-02-01", "amount": 100 * M}])
    assert "error" in r and "6.9%" in str(r["문제"])


# ── 4. 납부지연가산세: 2026.7.1.부터 "전날까지" ─────────────────────────────────────────
def test_late_payment_day_count_changes_on_20260701():
    old = c("late_payment_penalty", {"unpaid_tax": 100 * M, "due": "2026-05-31", "until": "2026-06-30"})["결과"]
    new = c("late_payment_penalty", {"unpaid_tax": 100 * M, "due": "2026-07-27", "until": "2026-08-26"})["결과"]
    assert old["일수"] == 30 and old["가산세"] == 660_000
    assert new["일수"] == 29 and new["가산세"] == 638_000

def test_late_payment_rejects_before_2016():
    assert "error" in c("late_payment_penalty", {"unpaid_tax": 1 * M, "due": "2010-03-31", "until": "2010-06-30"})


# ── 5. 원천징수세율: 외국인 직업운동가 ──────────────────────────────────────────────
@pytest.mark.parametrize("year,over3,rate", [(2018, False, 0.03), (2019, False, 0.20), (2022, True, 0.03), (2024, True, 0.03),
                                             (2024, False, 0.20), (2025, True, 0.20), (2026, True, 0.20)])
def test_foreign_athlete_rate_by_year_and_contract(year, over3, rate):
    r = c("withholding_tax", {"kind": "외국인직업운동가", "amount": 100 * M, "year": year, "contract_over_3_years": over3})
    assert r["결과"]["세율"] == rate and r["결과"]["원천징수세액"] == int(100 * M * rate)
