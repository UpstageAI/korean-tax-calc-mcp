"""2025 귀속 소득세·원천세 예시 재현(플레이북 14 §13)."""

from korean_tax_calc_mcp.engine import calc_income as I


def test_earned_deduction():
    assert (I.earned_deduction(33_800_000), I.earned_deduction(65_400_000), I.earned_deduction(36_000_000)) == (10_320_000, 13_020_000, 10_650_000)


def test_income_tax():
    assert (I.income_tax(36_285_000), I.income_tax(20_150_000)) == (4_182_750, 1_762_500)


def test_earned_tax_credit():
    assert I.earned_tax_credit(900_000, 30_000_000) == 495_000
    assert I.earned_tax_credit(2_000_000, 60_000_000) == 660_000
    assert I.earned_tax_credit(4_182_750, 65_400_000) == 660_000


def test_sme_youth_reduction():
    r = I.sme_youth_reduction(3_802_500, 50_000_000, 20_000_000)
    assert (r, I.earned_tax_credit(3_802_500, 50_000_000, r)) == (1_368_900, 422_400)
    r = I.sme_youth_reduction(3_802_500, 50_000_000, 50_000_000)
    assert (r, I.earned_tax_credit(3_802_500, 50_000_000, r)) == (2_000_000, 312_859)


def test_withholding():
    assert (I.daily_worker_tax(200_000), I.daily_worker_tax(187_000)) == (1_350, 0)
    assert I.withholding_late_penalty(1_000_000, 100) == 52_000
    assert (I.payment_statement_penalty(100_000_000), I.payment_statement_penalty(100_000_000, True)) == (1_000_000, 500_000)


def test_retirement_tax():  # 소법§48①·§55② 손계산
    # 1억, 10년: 근속공제 1,500만 → 환산 1.02억 → 환산공제 6,170만+200만×45% = 6,260만 → 과표 3,940만
    #   → 84만 + 2,540만×15% = 465만 → ÷12×10 = 3,875,000
    assert I.retirement_service_deduction(10) == 15_000_000 and I.converted_pay_deduction(102_000_000) == 62_600_000
    assert I.retirement_tax(100_000_000, 10) == 3_875_000
    # 5천만, 5년: 공제 500만 → 환산 1.08억 → 공제 6,530만 → 과표 4,270만 → 514.5만 ÷12×5 = 2,143,750
    assert I.retirement_tax(50_000_000, 5) == 2_143_750
    assert I.retirement_tax(3_000_000, 5) == 0 and I.retirement_service_deduction(25) == 55_000_000


def test_withholding_rates():  # 소법§129① — TC-23·24
    assert I.withholding_tax("배당", 10_000_000) == 1_400_000 and I.withholding_tax("기타", 10_000_000) == 2_000_000
    assert I.withholding_tax("이자", 1_000_000) == 140_000 and I.withholding_tax("비영업대금", 1_000_000) == 250_000
    assert I.withholding_tax("사업", 3_333_333) == 99_990


def test_deemed_bonus_resettlement():  # TC-22
    r = I.deemed_bonus_resettlement(80_000_000, 61_250_000, 30_000_000)
    assert (r["당초결정세액"], r["재정산과세표준"], r["재정산결정세액"], r["추가원천징수세액"]) == (8_440_000, 90_050_000, 15_577_500, 7_137_500)


def test_exec_retirement_limit():  # 소법§22③ 손계산(TC-33)
    assert I.exec_retirement_limit(100_000_000, 96, 150_000_000, 72) == 420_000_000
    assert I.exec_retirement_excess(600_000_000, 24, 96, 72, 100_000_000, 150_000_000) == 105_000_000
    assert I.exec_retirement_excess(600_000_000, 24, 96, 72, 100_000_000, 150_000_000, amount_2011=100_000_000) == 80_000_000

if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"): f(); print("ok", k)
