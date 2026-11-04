"""2026-11-04 도구 점검(sweep)에서 나온 금액·숫자 처리 결함 회귀 테스트. #번호는 내부 점검 목록 번호."""
import json

import pytest

from korean_tax_calc_mcp import server as calc
from korean_tax_calc_mcp.engine import exact


def _mv(*pairs):
    return [calc.Movement(date=d, amount=a) for d, a in pairs]


def _err(r):
    return isinstance(r, dict) and "error" in r


# ── 정확 계산 보조 ──────────────────────────────────────────────

def test_exact_floor_won_keeps_decimal_rate():
    assert int(190_000_000 * 0.7) == 132_999_999          # 부동소수 절사가 실제로 생기는 값
    assert exact.floor_won(190_000_000, 0.7) == 133_000_000
    assert exact.floor_won(10_000_000, 570_000_000, div=1_000_000_000) == 5_700_000
    assert exact.floor_won(10, 1, div=3) == 3
    assert exact.floor_won(3_000_000, 1 / 3) == 1_000_000   # 나눗셈으로 만든 비율도 뜻한 분수로
    assert exact.floor_won(190_000_000 * 0.7) == 133_000_000  # 이미 곱한 float도 복원
    assert exact.round_won(5, div=2) == 3 and exact.round_won(-5, div=2) == -3


# ── #4 양도세 미등기 70% 등 세율 곱 ──────────────────────────────

def test_row4_capital_gains_tax_unregistered_70():
    r = calc.capital_gains_tax(base=190_000_000, asset_type='토지', acquisition_date='2018-01-01',
                               transfer_date='2025-01-01', registered=False)["결과"]
    assert r["산출세액"] == 133_000_000
    assert r["지방소득세"] == 13_300_000


def test_row4_capital_gains_tax_other_bases():
    r = calc.capital_gains_tax(base=23_000_000, asset_type='토지', acquisition_date='2018-01-01',
                               transfer_date='2025-01-01', registered=False)["결과"]
    assert r["산출세액"] == 16_100_000 and r["지방소득세"] == 1_610_000
    # 주택 1년 미만 70%(2021.6.1. 이후 양도)
    r = calc.capital_gains_tax(base=2_900_000, asset_type='주택', acquisition_date='2025-09-01',
                               transfer_date='2026-07-01', houses_count=2, adjusted_area=True)["결과"]
    assert r["세율_후보"][0]["세액"] == 2_030_000


def test_row4_capital_gains_income_unregistered():
    r = calc.capital_gains_income(asset_type='토지', acquisition_date='2018-01-01', transfer_date='2025-01-01',
                                  transfer_price=500_000_000, acquisition_price=300_000_000,
                                  transfer_expenses=10_000_000, registered=False, apply_basic_deduction=True)["결과"]
    assert r["산출세액"] == 133_000_000


# ── #5 근로소득공제(제47조①) 공통 엔진 ─────────────────────────

def test_row5_wage_income_tax_earned_deduction():
    r = calc.wage_income_tax(gross_pay=2_900_000, year=2025)["결과"]
    assert r["근로소득공제"] == 2_030_000
    assert r["근로소득금액"] == 870_000


def test_row5_deemed_bonus_resettlement():
    r = calc.deemed_bonus_resettlement(gross_pay=2_900_000, tax_base=40_000_000, bonus=10_000_000, year=2025)["결과"]
    # 50,000,000 − (공제(12,900,000) 6,660,000 − 공제(2,900,000) 2,030,000)
    assert r["재정산과세표준"] == 45_370_000


def test_row5_earned_income_gross_pay():
    r = calc.earned_income_gross_pay(year=2025, items=[
        {"kind": "급여", "amount": 2_900_000, "facts": {"service_year": 2025}},
        {"kind": "식사대", "amount": 2_400_000, "facts": {"months": 12, "meal_provided": False}}])
    assert r["결과"]["근로소득공제"] == 2_030_000


# ── #6 공통매입세액 안분 ────────────────────────────────────────

def test_row6_vat_common_input_allocation():
    r = calc.vat_common_input_allocation(common_tax=10_000_000, total_supply=1_000_000_000, exempt_supply=570_000_000)
    assert r["결과"]["불공제"] == 5_700_000


def test_row6_common_input_tax():
    r = calc.common_input_tax(
        year=2024, period="1기", filing="확정",
        supplies={"예정": {"taxable": 400_000_000, "exempt": 600_000_000}, "확정": {"taxable": 200_000_000, "exempt": 800_000_000}},
        prior_nondeductible=600_000, prior_common_input_tax=190_000_000,
        ledger=[{"항목": "과세사업 전용", "매입세액": 700_000, "사용처": "과세"},
                {"항목": "면세사업 전용", "매입세액": 800_000, "사용처": "면세"},
                {"항목": "실지귀속1", "매입세액": 100_000, "사용처": "실지귀속", "과세비율": 0.7},
                {"항목": "공통매입", "매입세액": 1_200_000, "사용처": "공통"}])
    assert r["계산"]["불공제_과세기간합계"] == 133_840_000   # (190,000,000 + 1,200,000) × 70%


# ── #7 의제매입세액 운반비 제외 계수 ─────────────────────────────

def test_row7_vat_deemed_input_credit_freight():
    r = calc.vat_deemed_input_credit(period='2026-1', industry='제조', purchase_total=100_000_000, freight_included=6_000_000,
                                     used_taxable=70_000_000, used_exempt=15_000_000, ending_inventory_common=10_000_000,
                                     taxable_supply=280_000_000, exempt_supply=120_000_000, individual=False, sme=False)["결과"]
    assert r["운반비율_적용"]["과세_사용분_조정"] == 65_800_000
    assert r["공제대상_매입가액"] == 72_380_000


# ── #8 납부지연가산세 이자율 2019.2.12. 경계 ───────────────────────

def test_row8_late_payment_penalty_before_2019_02_12():
    r = calc.late_payment_penalty(unpaid_tax=1_000_000, due='2018-03-31', until='2019-03-31')["결과"]
    # 2018.4.1.~2019.2.11. 317일 × 3/10,000 + 2019.2.12.~3.31. 48일 × 25/100,000
    assert r["일수"] == 365
    assert r["0.03%일수"] == 317 and r["0.025%일수"] == 48
    assert r["가산세"] == 107_100


def test_row8_late_payment_penalty_three_rates():
    r = calc.late_payment_penalty(unpaid_tax=10_000_000, due='2019-01-31', until='2022-03-01')["결과"]
    assert (r["0.03%일수"], r["0.025%일수"], r["0.022%일수"]) == (11, 1099, 15)
    assert r["가산세"] == 10_000_000 * 11 * 3 // 10_000 + 10_000_000 * 1099 * 25 // 100_000 + 10_000_000 * 15 * 22 // 100_000


def test_row8_late_payment_penalty_unchanged_after_2022():
    r = calc.late_payment_penalty(unpaid_tax=1_000_000, due='2024-03-31', until='2024-04-30')["결과"]
    assert r["0.022%일수"] == 30 and r["가산세"] == 6_600 and "0.03%일수" not in r


def test_row8_late_payment_penalty_until_before_due():
    assert _err(calc.late_payment_penalty(unpaid_tax=1_000_000, due='2025-03-31', until='2024-03-31'))


# ── #9 증여세 지원 연도 밖 ───────────────────────────────────────

@pytest.mark.parametrize("d", ["2015-05-01", "2027-05-01"])
def test_row9_gift_tax_outside_years(d):
    r = calc.gift_tax(gift_date=d, gift_value=200_000_000, relation='직계존속')
    assert _err(r) and "2016~2026" in json.dumps(r, ensure_ascii=False)


def test_row9_gift_tax_2016_rate_unchanged():
    assert calc.gift_tax(gift_date='2016-05-01', gift_value=200_000_000, relation='직계존속')["계산"]["신고세액공제율"] == 0.1


# ── #10 퇴직소득세 근속연수 범위 ─────────────────────────────────

@pytest.mark.parametrize("n", [0, -1, 61])
def test_row10_retirement_years_of_service_range(n):
    assert _err(calc.retirement_income_tax(income=100_000_000, years_of_service=n, retire_year=2025))


def test_row10_retirement_years_one_ok():
    assert calc.retirement_income_tax(income=100_000_000, years_of_service=1, retire_year=2025)["결과"]["퇴직소득세"] == 22_397_500


# ── #15·#16 범위·형식 밖 입력 ───────────────────────────────────

@pytest.mark.parametrize("m", [0, 13, -1])
def test_row15_16_corporate_tax_months(m):
    r = calc.corporate_tax(base=300_000_000, year=2025, months=m)
    assert _err(r) and "months" in json.dumps(r, ensure_ascii=False)


@pytest.mark.parametrize("kw", [dict(days=200, period='2025-1'), dict(days=0, period='2025-1'), dict(days=181, period='2025'),
                                dict(days=181, period='2025-9'), dict(days=181, period='2030-1')])
def test_row15_16_vat_deemed_rent_inputs(kw):
    r = calc.vat_deemed_rent(deposit=500_000_000, **kw)
    assert _err(r)
    assert "list index" not in json.dumps(r, ensure_ascii=False)


def test_row16_vat_deemed_rent_valid_unchanged():
    assert calc.vat_deemed_rent(deposit=500_000_000, days=181, period='2025-1')["결과"]["간주임대료"] > 0


@pytest.mark.parametrize("g", [-3, 6])
def test_row16_minimum_tax_grace_year(g):
    assert _err(calc.minimum_tax(base_before_incentives=500_000_000, year=2025, sme=False, grace_year=g))


@pytest.mark.parametrize("m", [0, 13])
def test_row16_entertainment_limit_months(m):
    assert _err(calc.entertainment_limit(year=2025, sme=False, general_revenue=10_000_000_000, expensed=100_000_000, months=m))


def test_row15_deemed_dividend_bonus_shares_par_zero():
    r = calc.deemed_dividend_bonus_shares(year=2025, source="이익잉여금", capitalized_amount=10_000_000, par_value=0,
                                          shareholders=[{"name": "갑", "shares": 1000}], self_stock_allotment="미교부",
                                          shareholder_type="법인")
    assert _err(r) and "division" not in json.dumps(r, ensure_ascii=False)


# ── #17 인정이자 사업연도·잔액 ──────────────────────────────────

def test_row17_deemed_interest_movement_after_year_end():
    r = calc.deemed_interest(movements=_mv(("2025-01-01", 100_000_000)), year_end="2015-12-31")
    assert _err(r)


def test_row17_deemed_interest_negative_balance():
    r = calc.deemed_interest(movements=_mv(("2025-01-01", -100_000_000)), year_end="2025-12-31")
    assert _err(r)


def test_row17_deemed_interest_year_outside_range():
    r = calc.deemed_interest(movements=_mv(("2027-01-01", 100_000_000)), year_end="2027-12-31")
    assert _err(r)


def test_row17_deemed_interest_normal_unchanged():
    r = calc.deemed_interest(movements=_mv(("2025-01-01", 100_000_000), ("2025-07-01", -50_000_000)),
                             year_end="2025-12-31")["결과"]
    assert r["적수"] == 100_000_000 * 181 + 50_000_000 * 184


# ── #18 날짜 기반 도구의 지원 연도(2016~2026) ─────────────────────

def test_row18_stock_basis_income_tax_2015():
    r = calc.stock_basis_income_tax(transfer_date='2015-05-01', shares=100000, prior_year_income=50_000_000, book_net_asset=700_000_000)
    assert _err(r) and "2016~2026" in json.dumps(r, ensure_ascii=False)


@pytest.mark.parametrize("d", ["2014-06-30", "2027-06-30"])
def test_row18_unlisted_stock_valuation_years(d):
    r = calc.unlisted_stock_valuation(valuation_date=d, shares=10000, net_asset=1_000_000_000,
                                      incomes=[{"사업연도": 2013, "순손익액": 100_000_000}, {"사업연도": 2012, "순손익액": 100_000_000},
                                               {"사업연도": 2011, "순손익액": 100_000_000}])
    assert _err(r)


def test_row18_inheritance_gift_valuation_2014():
    assert _err(calc.inheritance_gift_valuation(kind="상속", valuation_date="2014-05-01", supplementary_value=100_000_000))


def test_row18_pension_account_withdrawal_2015():
    r = calc.pension_account_withdrawal(year=2015, birth_date="1955-01-01", join_date="2005-01-01", start_request_date="2015-01-02",
                                        balance_at_period_start=100_000_000, withdrawal=10_000_000, contributions_total=50_000_000,
                                        contributions_not_deducted=0)
    assert _err(r)


def test_row18_vat_exempt_use_deemed_supply_2027():
    r = calc.vat_exempt_use_deemed_supply(use_date="2027-03-01", mode="전부",
                                          assets=[{"구분": "건물", "취득일": "2020-01-10", "취득가액": 100_000_000, "매입세액공제": True}])
    assert _err(r)


# ── #13 날짜 형식 오류 ──────────────────────────────────────────

def test_row13_assessment_limitation_bad_date():
    r = calc.assessment_limitation(due_date='2025-02-30')
    assert _err(r) and "due_date" in r["error"]


# ── #31 공통매입세액 안분 — 면세공급가액 > 총공급가액 ──────────────

def test_row31_exempt_over_total():
    r = calc.vat_common_input_allocation(common_tax=1_000_000, total_supply=100, exempt_supply=200)
    s = json.dumps(r, ensure_ascii=False)
    assert _err(r) and "한쪽이 없음" not in s


# ── #63 재계산 경과과세기간수(영 제83조②·⑤, 제66조②) ──────────────

def test_row63_elapsed_periods_int_period():
    r = calc.input_tax_recalculation(asset_type='기타감가상각자산', acquired={'year': 2024, 'period': 2}, input_tax=20_000_000,
                                     ratios=[{'year': 2024, 'period': 2, 'exempt_ratio': 0.3}, {'year': 2025, 'period': 1, 'exempt_ratio': 0.33},
                                             {'year': 2025, 'period': 2, 'exempt_ratio': 0.4}])
    n = {(h["year"], h["period"]): h["경과과세기간수"] for h in r["이력"]}
    assert n == {(2024, 2): 0, (2025, 1): 1, (2025, 2): 2}
    assert r["결과"]["당기_납부세액_가산"] == 1_000_000      # 20,000,000 × (1 − 25% × 2) × 10%


def test_row14_recalculation_needs_input_tax():
    r = calc.input_tax_recalculation(asset_type='건물·구축물', acquired={'year': 2022, 'period': '2기'},
                                     ratios=[{'year': 2022, 'period': '2기', 'exempt_ratio': 0.5}, {'year': 2023, 'period': '1기', 'exempt_ratio': 0.56}])
    assert _err(r) and "input_tax" in json.dumps(r, ensure_ascii=False) and "NoneType" not in json.dumps(r, ensure_ascii=False)


def test_row63_elapsed_periods_label_forms_agree():
    a = calc.input_tax_recalculation(asset_type='건물·구축물', acquired={'year': 2024, 'period': '1기'}, input_tax=10_000_000,
                                     ratios=[{'year': 2024, 'period': '1기', 'exempt_ratio': 0.2}, {'year': 2025, 'period': '1기', 'exempt_ratio': 0.3}])
    b = calc.input_tax_recalculation(asset_type='건물·구축물', acquired={'year': 2024, 'period': 1}, input_tax=10_000_000,
                                     ratios=[{'year': 2024, 'period': 1, 'exempt_ratio': 0.2}, {'year': 2025, 'period': 1, 'exempt_ratio': 0.3}])
    assert a["이력"][-1]["경과과세기간수"] == b["이력"][-1]["경과과세기간수"] == 2
    assert a["결과"]["당기_납부세액_가산"] == b["결과"]["당기_납부세액_가산"] == 900_000   # 10,000,000 × 90% × 10%


# ── 대손충당금 한도·실적률 절사(같은 부동소수 원인, sweep 확장 점검) ─────────

def test_bad_debt_limit_exact():
    r = calc.bad_debt_adjustment(year=2025, sme=False, book={"opening": 5_000_000, "offset": 0, "provision": 1_000_000, "closing": 6_000_000},
                                 receivables_prev_end_book=1_000_000_000, receivables_end_book=23_000_000,
                                 writeoffs=[{"kind": "화해·확정판결", "amount": 11_000_000, "arose_in": "당기"}])
    assert r["계산"]["대손실적률"] == 0.011
    assert r["결과"]["한도"] == 253_000      # 23,000,000 × 1.1%


def test_bad_debt_loss_rate_floor_digits4():
    r = calc.bad_debt_adjustment(year=2025, sme=False, book={"opening": 5_000_000, "offset": 0, "provision": 1_000_000, "closing": 6_000_000},
                                 receivables_prev_end_book=1_000_000_000, receivables_end_book=23_000_000,
                                 writeoffs=[{"kind": "화해·확정판결", "amount": 300_000, "arose_in": "당기"}], loss_rate_digits=4)
    assert r["계산"]["대손실적률"] == 0.0003
