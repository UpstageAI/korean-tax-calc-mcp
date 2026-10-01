from korean_tax_calc_mcp.engine import calc_cit as C

"""2026 법인세 신고안내(2025 사업연도) 계산 예시 재현. 쪽 = 책 인쇄 쪽(PDF = 책 + 22). 플레이북 11 §6."""

M = 1_000_000

def test_T1_entertain_313():
    r = C.entertain(2025, True, 710 * 100 * M, 100 * 100 * M, expensed=172 * M, asset_part=57 * M, no_card_over=10 * M, culture=10 * M)
    assert (r["일반한도"], r["한도"], r["한도초과(기타사외유출)"], r["자산감액"]) == (152_600_000, 162_600_000, 56_400_000, 0)

def test_T6_interest_266():
    loan = C.jeoksu([("2025-04-20", 7 * M), ("2025-08-15", -5 * M)], "2025-12-31")
    land = C.jeoksu([("2025-01-01", 20 * M)], "2025-12-31")
    r = C.nonbusiness_interest([(7_800_000, 21_900 * M), (15 * M, 54_750 * M)], (5 * M, 9_125 * M, 1_375_000))(loan + land)
    assert (loan, land, r["손금불산입(기타사외유출)"]) == (1_097_000_000, 7_300_000_000, 2_497_737)

def test_T7_T8_depreciation_285_287():
    assert C.depreciation({"건물": (100000, 120000), "기계1": (10000, 12000), "기계2": (20000, 16000), "비품": (20000, 17000)})["손금불산입(유보)"] == 22000
    assert C.depreciation_recover(100, 500, 470) == {"추인(△유보)": 30, "차기이월": 70}

def test_T9_T11_car_325_327():
    a = C.business_car(2025, 20 * M, 40 * M, 0, True, 0.7)
    assert (a["유지비 손금불산입(상여)"], a["감가상각 사적사용 손금불산입(상여)"], a["감가상각 한도초과(유보)"]) == (6 * M, 12 * M, 20 * M)
    b = C.business_car(2025, 3 * M, 4 * M, 4 * M, False)
    assert b["유지비 손금불산입(상여)"] == b["감가상각 한도초과(유보)"] == 0
    c = C.business_car(2025, 20 * M, 40 * M, 0, False)
    assert (c["업무사용비율"], c["유지비 손금불산입(상여)"], c["감가상각 사적사용 손금불산입(상여)"], c["감가상각 한도초과(유보)"]) == (0.25, 15 * M, 30 * M, 2 * M)

def test_T12_donation_348():
    d = C.donation(279 * M, 135 * M, special=55 * M, general=43 * M, sme=False)
    assert (d["특례한도"], d["일반한도"], d["한도초과(기타사외유출)"], d["차기이월"]["일반"]) == (72 * M, 8_900_000, 34_100_000, 34_100_000)

def test_T14_pension_232():
    r = C.pension(100 * M, 30 * M, 0, 80 * M, 60 * M, 0, 15 * M, 35 * M)
    assert (r["손금산입범위"], r["조정"]) == (25 * M, -10 * M)

def test_T15_bad_debt_245():
    assert C.bad_debt_allowance(175_100_000, 0.009, 1_950_000)["한도초과(유보)"] == 199_000

def test_T19_short_year_396():
    assert C.corp_tax(110 * M, 2025, C.months_in("2025-07-07", "2025-12-31")) == 10_900_000

def test_T20_min_tax_430():
    base = 255 * M; tax = C.corp_tax(base, 2025)
    red = int(tax * 220 / 255 * 0.5)
    r = C.apply_min_tax(tax, red, 1 * M, C.min_tax(base, sme=True))
    assert (tax, red, r["배제"], r["결정세액"]) == (28_450_000, 12_272_549, 1_672_549, 16_850_000)

if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"): f(); print("ok", k)
