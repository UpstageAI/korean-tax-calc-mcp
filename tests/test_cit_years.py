from korean_tax_calc_mcp.engine import calc_cit as C

"""사업연도별 법령표(calc_cit.YEAR 2016~2025) 경계 테스트. 기대값은 조문 산식 손계산. 근거: knowledge/16 '법인 연도표'."""

M = 1_000_000

억 = 100 * M

def test_table_covers_2016_2025():
    assert sorted(C.YEAR) == list(range(2016, 2026))
    for y in range(2016, 2026):
        C.require_year(y)
    try:
        C.require_year(2015); raise AssertionError("2015는 표 없음")
    except C.NoYearTable:
        pass

def test_corp_tax_rates_by_year():
    # 3억: 2016~2022 2천만 + 1억×20% = 4천만 / 2023~ 1,800만 + 1억×19% = 3,700만
    assert [C.corp_tax(3 * 억, y) for y in (2016, 2019, 2020, 2021, 2022)] == [40 * M] * 5
    assert [C.corp_tax(3 * 억, y) for y in (2023, 2024, 2025)] == [37 * M] * 3
    # 3,500억: 2017 39.8억 + 3,300억×22% = 765.8억 / 2018 655.8억 + 500억×25% = 780.8억 / 2023 625.8억 + 500억×24% = 745.8억
    assert C.corp_tax(3500 * 억, 2017) == 76_580 * M
    assert C.corp_tax(3500 * 억, 2018) == 78_080 * M
    assert C.corp_tax(3500 * 억, 2023) == 74_580 * M
    # 소규모 임대법인 세율은 2025부터: 3억 × 19% = 5,700만, 2024엔 일반 세율
    assert C.corp_tax(3 * 억, 2025, small_rental=True) == 57 * M
    assert C.corp_tax(3 * 억, 2024, small_rental=True) == 37 * M

def _ent(y, rev, **kw):
    return C.entertain(y, True, rev, 0, expensed=10 * 억, **kw)

def test_entertain_base_and_revenue_tables():
    # 중소, 수입 100억: 2019 2,400만 + 0.2% 2,000만 / 2020 3,600만 + 0.35%(조특§136④) 3,500만 / 2021 3,600만 + 0.3% 3,000만
    assert [_ent(y, 100 * 억)["일반한도"] for y in (2016, 2017, 2018, 2019)] == [44 * M] * 4
    assert _ent(2020, 100 * 억)["일반한도"] == 71 * M
    assert _ent(2021, 100 * 억)["일반한도"] == 66 * M
    # 수입 200억: 2019 2천만 + 100억×0.1% = 3천만 / 2020 3,500만 + 100억×0.25% = 6천만 / 2021 3천만 + 100억×0.2% = 5천만
    assert _ent(2019, 200 * 억)["일반한도"] - 24 * M == 30 * M
    assert _ent(2020, 200 * 억)["일반한도"] - 36 * M == 60 * M
    assert _ent(2021, 200 * 억)["일반한도"] - 36 * M == 50 * M
    # 수입 600억: 2019 6천만 + 100억×0.03% = 6,300만 / 2020 1.35억 + 100억×0.06% = 1.41억
    assert _ent(2019, 600 * 억)["일반한도"] - 24 * M == 63 * M
    assert _ent(2020, 600 * 억)["일반한도"] - 36 * M == 141 * M
    # 일반법인 기본 1,200만은 전 연도 동일
    assert C.entertain(2016, False, 0, 0, 10 * 억)["일반한도"] == C.entertain(2025, False, 0, 0, 10 * 억)["일반한도"] == 12 * M

def test_entertain_2020_split_fiscal_year():
    # 조특§136⑤: 2020.7.1.~2021.6.30. 사업연도(2020년 184일/365일), 수입 100억
    r = _ent(2020, 100 * 억, days_2020=(184, 365))
    assert r["일반한도"] == round(36 * M + (35 * M * 184 + 30 * M * 181) / 365)

def test_entertain_rental_half_from_2017():
    assert _ent(2016, 100 * 억, rental_corp=True)["일반한도"] == 44 * M      # 2016: 50% 규정 없음
    assert _ent(2017, 100 * 억, rental_corp=True)["일반한도"] == 22 * M

def test_market_10pct_from_2023_filing():
    # 조특§136⑥ 부칙(법률 19936)§35: 2024.1.1. 이후 신고분 → 2023 사업연도부터. 한도 = 일반한도 × 10%
    assert _ent(2022, 100 * 억, market=50 * M)["전통시장한도"] == 0
    assert _ent(2023, 100 * 억, market=50 * M)["전통시장한도"] == round(66 * M * 0.1)
    assert _ent(2025, 100 * 억, market=1 * M)["전통시장한도"] == 1 * M

def test_culture_20pct_all_years():
    assert _ent(2016, 100 * 억, culture=50 * M)["문화한도"] == round(44 * M * 0.2)
    assert _ent(2022, 100 * 억, culture=50 * M)["문화한도"] == round(66 * M * 0.2)

def test_receipt_threshold_1man_to_3man():
    items = [(20_000, False, False), (50_000, False, False), (9_000, False, False), (150_000, False, True), (250_000, False, True),
             (100_000, True, False)]
    assert C.receipt_disallowed(2020, items) == 20_000 + 50_000 + 250_000   # 1만원 초과, 경조금 20만원 초과
    assert C.receipt_disallowed(2021, items) == 50_000 + 250_000            # 3만원 초과(2021.1.1. 이후 지출분)

def test_business_car_log_threshold_1000_to_1500():
    # 운행기록 미작성, 유지비 1천만 + 감가상각 1천만 = 2천만
    a = C.business_car(2019, 10 * M, 10 * M, 10 * M, False)                 # 1,000만 / 2,000만 = 50%
    b = C.business_car(2020, 10 * M, 10 * M, 10 * M, False)                 # 1,500만 / 2,000만 = 75%
    assert (a["유지비 손금불산입(상여)"], a["감가상각 사적사용 손금불산입(상여)"]) == (5 * M, 5 * M)
    assert (b["유지비 손금불산입(상여)"], b["감가상각 사적사용 손금불산입(상여)"]) == (2_500_000, 2_500_000)
    # 임대법인(영§50조의2⑮, 2017~): 500만 / 2,000만 = 25%. 2016은 특례 없음 → 1,000만 기준
    c = C.business_car(2020, 10 * M, 10 * M, 10 * M, False, rental_corp=True)
    assert c["유지비 손금불산입(상여)"] == 7_500_000
    d = C.business_car(2016, 10 * M, 10 * M, 10 * M, False, rental_corp=True)
    assert d["유지비 손금불산입(상여)"] == 5 * M

def test_business_car_depreciation_cap_rental_from_2017():
    # 운행기록 작성 100%, 감가상각 1천만: 한도 800만(초과 200만), 임대법인 2017~ 400만(초과 600만)
    assert C.business_car(2016, 0, 10 * M, 10 * M, True, 1.0, rental_corp=True)["감가상각 한도초과(유보)"] == 2 * M
    assert C.business_car(2017, 0, 10 * M, 10 * M, True, 1.0, rental_corp=True)["감가상각 한도초과(유보)"] == 6 * M

def test_business_car_plate_from_2024():
    r = C.business_car(2024, 10 * M, 10 * M, 10 * M, True, 1.0, plate_ok=False)
    assert (r["유지비 손금불산입(상여)"], r["감가상각 사적사용 손금불산입(상여)"], r["감가상각 한도초과(유보)"]) == (10 * M, 10 * M, 0)
    r = C.business_car(2023, 10 * M, 10 * M, 10 * M, True, 1.0, plate_ok=False)   # 2023: 요건 없음
    assert (r["유지비 손금불산입(상여)"], r["감가상각 한도초과(유보)"]) == (0, 2 * M)

def test_loss_limit_ratio_all_years():
    assert [C.loss_limit_ratio(y, False) for y in range(2016, 2026)] == [0.8, 0.8, 0.7, 0.6, 0.6, 0.6, 0.6, 0.8, 0.8, 0.8]
    assert all(C.loss_limit_ratio(y, True) == 1.0 for y in range(2016, 2026))

def test_min_tax_year_arg():
    for y in (2016, 2020, 2025):
        assert C.min_tax(10 * 억, True, year=y) == 70 * M
        assert C.min_tax(10 * 억, False, grace_year=2, year=y) == 80 * M
        assert C.min_tax(10 * 억, False, grace_year=5, year=y) == 90 * M
        assert C.min_tax(200 * 억, False, year=y) == 10 * 억 + 12 * 억      # 100억×10% + 100억×12%
    assert C.min_tax(10 * 억, True) == 70 * M                                # 연도 인자 없는 종전 호출
    try:
        C.min_tax(10 * 억, True, year=2015); raise AssertionError
    except C.NoYearTable:
        pass

def test_donation_loss_cap_by_year():
    # 비중소, 기준소득 10억, 결손금 9억, 특례(법정) 3억
    # 2020: 결손금 전액 차감 → (10−9)×50% = 5천만 / 2021: 60% 한도 6억 → 2억 / 2023: 80% 한도 8억 → 1억
    f = lambda y: C.donation(10 * 억, 9 * 억, 3 * 억, 0, sme=False, year=y)
    assert (f(2020)["특례한도"], f(2020)["한도초과(기타사외유출)"]) == (50 * M, 250 * M)
    assert (f(2021)["특례한도"], f(2021)["한도초과(기타사외유출)"]) == (200 * M, 100 * M)
    assert (f(2023)["특례한도"], f(2023)["한도초과(기타사외유출)"]) == (100 * M, 200 * M)
    assert C.donation(10 * 억, 9 * 억, 3 * 억, 0, sme=False)["특례한도"] == 100 * M   # year 없는 종전 호출(80%) 유지

def test_donation_carry_order_2018_vs_2019():
    # 기준소득 1억, 특례 당기 4천만 + 이월 3천만, 한도 5천만
    a = C.donation(1 * 억, 0, 40 * M, 0, special_carry=30 * M, year=2018)    # 당기분 먼저 4천만, 이월 1천만
    b = C.donation(1 * 억, 0, 40 * M, 0, special_carry=30 * M, year=2019)    # 이월 3천만 먼저, 당기 2천만
    assert (a["이월분 손금산입"], a["한도초과(기타사외유출)"], a["차기이월"]["특례"]) == (10 * M, 0, 20 * M)
    assert (b["이월분 손금산입"], b["한도초과(기타사외유출)"], b["차기이월"]["특례"]) == (30 * M, 20 * M, 20 * M)

def test_donation_social_enterprise_from_2018():
    assert C.donation(1 * 억, 0, 0, 20 * M, social_enterprise=True, year=2017)["일반한도"] == 10 * M
    assert C.donation(1 * 억, 0, 0, 20 * M, social_enterprise=True, year=2018)["일반한도"] == 20 * M

def test_names_by_year():
    assert [C.YEAR[y]["접대비_명칭"] for y in (2023, 2024)] == ["접대비", "기업업무추진비"]
    assert [C.YEAR[y]["기부금_명칭"] for y in (2022, 2023)] == [("법정", "지정"), ("특례", "일반")]
    assert [C.YEAR[y]["기부금_이월기간"] for y in (2017, 2018)] == [5, 10]

def test_receipt_check_by_expense_date():
    """적격증빙 건별(영 §41): 지출일로 1만원/3만원, 법인명의·가맹점·원천징수영수증·예외"""
    r = C.receipt_check([
        {"지출일": "2020-12-31", "금액": 20_000, "증빙": "간이영수증"},                 # 2020 기준 1만원 초과 → 부인
        {"지출일": "2021-01-01", "금액": 20_000, "증빙": "간이영수증"},                 # 2021 기준 3만원 이하 → 인정
        {"지출일": "2025-03-01", "금액": 50_000, "증빙": "신용카드", "법인명의": False},  # 개인카드 → 부인
        {"지출일": "2025-03-01", "금액": 50_000, "증빙": "신용카드", "가맹점일치": False},  # 위장가맹점 → 부인
        {"지출일": "2025-03-01", "금액": 150_000, "증빙": "없음", "경조금": True},      # 경조금 20만 이하 → 인정
        {"지출일": "2025-03-01", "금액": 500_000, "증빙": "없음", "국외현금불가피": True},
        {"지출일": "2025-03-01", "금액": 100_000, "증빙": "원천징수영수증"},            # 사업자 용역 → 부인
    ])
    assert [x["판정"] for x in r["건별"]] == ["부인", "인정", "부인", "부인", "인정", "인정", "부인"]
    assert r["부인합계"] == 20_000 + 50_000 + 50_000 + 100_000

if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"): f(); print("ok", k)
