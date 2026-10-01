"""부가가치세 과세기간별 연도표(2016년 제1기~2026년) 경계 테스트 — 같은 입력, 다른 과세기간 → 조문 산식 손계산 값. knowledge/16 '부가가치세 연도표'."""

from korean_tax_calc_mcp.engine import calc_vat as V, calc


def test_deemed_rent_rate_by_year():  # 부가규칙 제47조: 365,000,000 × 이율 × 181/365
    assert V.deemed_rent(365_000_000, 181, period="2016-1") == 3_258_000   # 1.8%
    assert V.deemed_rent(365_000_000, 181, period="2019-2") == 3_801_000   # 2.1%
    assert V.deemed_rent(365_000_000, 181, period="2021-1") == 2_172_000   # 1.2%
    assert V.deemed_rent(365_000_000, 181, period="2024-1") == 6_335_000   # 3.5%
    assert V.deemed_rent(365_000_000, 181, period="2025-06-30") == V.deemed_rent(365_000_000, 181) == 5_611_000  # 3.1%
    assert [V.DEEMED_RENT_RATE[y] for y in (2017, 2018, 2020, 2022, 2023)] == [0.016, 0.018, 0.018, 0.012, 0.029]


def test_invoice_penalty_by_supply_date():  # 부가법 제60조, 공급가액 10,000,000
    P = V.invoice_penalties
    assert (P(10_000_000, "지연전송", "2018-12-31"), P(10_000_000, "지연전송", "2019-01-01")) == (50_000, 30_000)
    assert (P(10_000_000, "미전송", "2018-12-31"), P(10_000_000, "미전송", "2019-01-01")) == (100_000, 50_000)
    assert P(10_000_000, "지연전송", "2016-05-01", designated_individual=True) == 10_000
    assert (P(10_000_000, "지연수취", "2016-12-31"), P(10_000_000, "지연수취", "2017-01-01")) == (100_000, 50_000)
    assert (P(10_000_000, "매출처별합계표_미제출", "2016-12-31"), P(10_000_000, "매출처별합계표_미제출", "2017-01-01")) == (100_000, 50_000)
    assert (P(10_000_000, "신용카드매입공제", "2018-12-31"), P(10_000_000, "신용카드매입공제", "2019-01-01")) == (100_000, 50_000)
    assert P(10_000_000, "미발급", "2016-01-01") == P(10_000_000, "미발급") == 200_000


def test_fake_invoice_rate_by_date():  # 부가법 제60조③: 2% → 3%(2018) → 4%(2026)
    assert [calc.penalty_fake_invoice(10_000_000, d) for d in ("2017-12-31", "2018-01-01", "2025-12-31", "2026-01-01")] == [200_000, 300_000, 300_000, 400_000]


def test_deemed_input_by_period():  # 음식점 개인, 과세표준 1.5억, 면세 매입 1억
    f = lambda p: V.deemed_input(100_000_000, 150_000_000, period=p, industry="음식점")
    assert f("2017-2") == 6_111_111    # 한도 55% → 8,250만 × 8/108
    assert f("2018-2") == 7_431_192    # 한도 60% → 9,000만 × 9/109(2억 이하 특례)
    assert f("2022-1") == 8_256_880    # 한도 70% → 1억(매입) × 9/109
    assert V.deemed_input_rate("유흥", "2019-2") == (4, 104) and V.deemed_input_rate("유흥", "2020-1") == (2, 102)
    assert V.deemed_input_rate("제조_떡방앗간등", "2018-2") == (4, 104) and V.deemed_input_rate("제조_떡방앗간등", "2019-1") == (6, 106)
    assert [V.deemed_input_limit_ratio(p, False, False, 1) for p in ("2018-1", "2018-2", "2021-2", "2022-1")] == [0.35, 0.40, 0.40, 0.50]
    assert V.deemed_input(21_800_000, 100_000_000, 9, 109, 0.75) == 1_800_000  # 기존 호출 유지


def test_simplified_by_period():  # 음식점 간이, 공급대가 5,500만, 세금계산서 수취 공급대가 2,200만
    assert V.simplified_tax(55_000_000, V.value_added_rate("음식점업", "2021-1"), 22_000_000, "2021-1") == 350_000  # 55만 − 200만×10%
    assert V.simplified_tax(55_000_000, V.value_added_rate("음식점업", "2021-2"), 22_000_000, "2021-2") == 715_000  # 82.5만 − 11만
    assert V.value_added_rate("전기·가스·증기 및 수도 사업", "2020-2") == 0.05
    assert [V.simplified_threshold(d) for d in ("2021-06-30", "2021-07-01", "2024-06-30", "2024-07-01")] == [48_000_000, 80_000_000, 80_000_000, 104_000_000]
    assert [V.simplified_exempt_threshold(y) for y in (2017, 2018, 2020, 2021)] == [24_000_000, 30_000_000, 30_000_000, 48_000_000]


def test_card_credit_by_date():
    assert V.card_sales_credit(10_000_000, "2021-06-30", True) == 260_000 and V.card_sales_credit(10_000_000, "2021-07-01", True) == 130_000
    assert V.card_sales_credit(1_000_000_000, "2017-12-01") == 5_000_000 and V.card_sales_credit(1_000_000_000, "2019-03-01") == 10_000_000


def test_late_payment_split():  # 국기령 제27조의4 경과조치 기간 안분
    assert V.late_payment(1_000_000, 20, "2019-02-01") == 5_550   # 11일×0.03% + 9일×0.025%
    assert V.late_payment(1_000_000, 10, "2022-02-10") == 2_350   # 5일×0.025% + 5일×0.022%
    assert V.late_payment(1_000_000, 30) == 6_600


def test_bad_debt_period():  # 부가령 제87조② 5년 → 10년
    assert V.bad_debt_eligible("2014-03-01", "2019-2")["공제가능"] is False
    assert V.bad_debt_eligible("2014-03-01", "2020-1")["공제가능"] is True


def test_no_year_table():
    for p in ("2015-2", "2027-1"):
        try: V.deemed_rent(1, 1, period=p); assert False
        except V.NoYearTable: pass


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"): f(); print("ok", k)
