"""소득세·원천세 귀속연도별 연도표(2016~2026) 경계 테스트 — 조문 산식 손계산. knowledge/16 '소득세 연도표'."""

from korean_tax_calc_mcp.engine import calc_income as I


def test_income_tax_rates_by_year():  # 소득세법 제55조①
    assert [I.income_tax(600_000_000, y) for y in (2016, 2017, 2018)] == [208_600_000, 210_600_000, 216_600_000]
    assert (I.income_tax(1_200_000_000, 2020), I.income_tax(1_200_000_000, 2021)) == (468_600_000, 474_600_000)
    assert (I.income_tax(50_000_000, 2022), I.income_tax(50_000_000, 2023)) == (6_780_000, 6_240_000)
    assert I.income_tax(50_000_000, 2025) == I.income_tax(50_000_000)


def test_earned_deduction_cap():  # 제47조① 단서(2020~)
    assert (I.earned_deduction(400_000_000, 2019), I.earned_deduction(400_000_000, 2020)) == (20_750_000, 20_000_000)


def test_earned_tax_credit_cap():  # 제59조② 1억2천만 초과 구간(2023~)
    assert (I.earned_tax_credit(3_000_000, 150_000_000, year=2022), I.earned_tax_credit(3_000_000, 150_000_000, year=2023)) == (500_000, 200_000)


def test_daily_worker():  # 제47조② 10만 → 15만(2019)
    assert (I.daily_worker_tax(200_000, 2018), I.daily_worker_tax(200_000, 2019)) == (2_700, 1_350)


def test_withholding_rate_by_year():  # 제129조
    assert [I.withholding_tax("비실명", 10_000_000, y) for y in (2017, 2018, 2019, 2022, 2023)] == [3_800_000, 4_000_000, 4_200_000, 4_200_000, 4_500_000]
    assert (I.withholding_tax("외국인직업운동가", 10_000_000, 2018), I.withholding_tax("외국인직업운동가", 10_000_000, 2019)) == (300_000, 2_000_000)
    assert (I.withholding_tax("온투업이자", 1_000_000, 2019), I.withholding_tax("온투업이자", 1_000_000, 2020)) == (250_000, 140_000)


def test_payment_statement_penalty():  # 제81조① → 제81조의11
    P = I.payment_statement_penalty
    assert (P(100_000_000, due_date="2017-02-28"), P(100_000_000, due_date="2018-03-12")) == (2_000_000, 1_000_000)
    assert P(100_000_000, True, due_date="2017-02-28") == 1_000_000
    assert (P(100_000_000, daily_worker=True, paid_on="2021-06-30"), P(100_000_000, daily_worker=True, paid_on="2021-07-01")) == (1_000_000, 250_000)


def test_withholding_late_split():  # 국기법 제47조의5 + 국기령 제27조의4 안분
    assert I.withholding_late_penalty(1_000_000, 20, "2019-02-01") == 35_550
    assert I.withholding_late_penalty(1_000_000, 100) == 52_000


def test_no_year_table():
    try: I.income_tax(1, 2015); assert False
    except I.NoYearTable: pass


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"): f(); print("ok", k)
