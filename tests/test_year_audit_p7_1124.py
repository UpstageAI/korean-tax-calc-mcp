"""연도 점검 미확인 항목 정리(2026-11-24) — 계산이 틀리던 7건과 범위 밖 거절 3건.
근거 원문: 통합테스트/연도점검_1124 보고_h1~h4(조문 MCP 0.30.0 law_article·article_addenda as_of 대조)."""
from tests._helpers import call_raw


# ── 1. 개인 외국납부세액공제: 러시아 조약 초과분(영 제117조① 단서 후단)은 2023.8.8. 이후 납부분부터(대통령령 제34265호 부칙 제9조)
_FTC = dict(calculated_tax=5_000_000, total_income=50_000_000)
_RU = dict(country="러시아", foreign_income=10_000_000, foreign_tax=1_500_000, treaty_rate=0.10,
           gross_amount=10_000_000, russia_override=True)


def _ftc_recognized(year, **extra):
    r = call_raw("individual_foreign_tax_credit", dict(_FTC, year=year, countries=[dict(_RU, **extra)]))
    rows = [v for v in r["결과"].values() if isinstance(v, list) and v and isinstance(v[0], dict) and "인정_외국소득세액" in v[0]]
    return rows[0][0]["인정_외국소득세액"], r


def test_russia_override_before_rule_uses_treaty_cap():
    amt, r = _ftc_recognized(2020)
    assert amt == 1_000_000
    assert any("부칙 제9조" in x for x in r.get("주의", []))


def test_russia_override_needs_paid_date_in_2022_2023():
    r = call_raw("individual_foreign_tax_credit", dict(_FTC, year=2023, countries=[dict(_RU)]))
    assert "tax_paid_on" in str(r)
    assert "결과" not in r


def test_russia_override_by_paid_date():
    assert _ftc_recognized(2023, tax_paid_on="2023-05-01")[0] == 1_000_000
    assert _ftc_recognized(2023, tax_paid_on="2023-09-01")[0] == 1_500_000
    assert _ftc_recognized(2025)[0] == 1_500_000


# ── 2. 소득 이월결손금: 2008년 이전 발생분은 5년(구 소득세법 제45조②, 법률 제9270호 부칙 제4조)
def _offset(cf_year):
    return call_raw("income_loss_offset", {"year": 2016, "incomes": {"근로": 30_000_000},
                                           "carryforwards": [{"year": cf_year, "kind": "사업", "amount": 10_000_000}]})["결과"]


def test_loss_before_2009_expires_after_5_years():
    r = _offset(2008)
    assert r["종합소득금액"] == 30_000_000
    assert r["소멸"] and "5년 경과" in r["소멸"][0]["사유"] and "제9270호" in r["소멸"][0]["사유"]


def test_loss_from_2009_still_10_years():
    assert _offset(2010)["종합소득금액"] == 20_000_000


# ── 3. 비상장주식 기준시가: 2023.2.27.까지 양도분 '3년 연속 결손'이면 순자산가치만(구 영 제165조④3호다목)
def _stock(transfer_date, status):
    return call_raw("stock_basis_income_tax", {"transfer_date": transfer_date, "shares": 1000, "prior_year_income": -5_000_000,
                                               "book_net_asset": 10_000_000, "status": status})


def test_three_year_loss_before_2023_net_asset_only():
    assert _stock("2017-06-30", "3년연속결손")["결과"]["1주당_기준시가"] == 10_000
    assert _stock("2020-06-30", "3년연속결손")["결과"]["1주당_기준시가"] == 10_000


def test_three_year_loss_after_2023_not_a_reason():
    assert _stock("2024-06-30", "3년연속결손")["결과"]["1주당_기준시가"] == 8_000


def test_unknown_status_rejected():
    r = _stock("2020-06-30", "적자")
    assert "error" in r


# ── 4·5. 최저한세: 적용대상 감면의 연도별 차이(조특법 제132조①4호), 2019년 이전 배제 순서(영 제126조⑤2호)
_MT = dict(sme=False, income_add=0, income_deduct=0)


def _mt(year, code, amount=150_000_000):
    return call_raw("minimum_tax_adjustment", dict(_MT, year=year, net_income=1_000_000_000,
                                                   reductions=[{"code": code, "amount": amount}]))["결과"]


def test_jeju_reduction_not_subject_before_2020():
    r = _mt(2018, "13P")
    assert r["배제_내역"] == [] and r["적용제외_차감후세액"] == 30_000_000
    assert "연도별_적용대상_변경" in r
    r = _mt(2020, "13P")
    assert sum(b["배제액"] for b in r["배제_내역"]) == 70_000_000


def test_startup_full_reduction_subject_before_2019():
    assert sum(b["배제액"] for b in _mt(2017, "11O")["배제_내역"]) == 70_000_000
    assert _mt(2019, "11O")["배제_내역"] == []


def test_reserve_excluded_first_before_2020():
    def order(year):
        r = call_raw("minimum_tax_adjustment", dict(_MT, year=year, net_income=300_000_000, income_deduct=100_000_000,
                                                    reserve=50_000_000, special_depreciation=50_000_000))["결과"]
        return [b["코드"] for b in r["배제_내역"]]
    assert order(2018)[0] == "105"
    assert order(2021)[0] == "106"


# ── 6. 업무용승용차 번호판: 2024.1.1. 이후 등록·임차 차량부터(국토교통부 고시 제2023-954호 부칙 제2조)
_CAR = dict(year=2025, upkeep=10_000_000, depreciation=8_000_000, booked_depreciation=8_000_000, log_kept=True,
            business_ratio=0.9, acquisition_cost=100_000_000, plate_ok=False)


def test_plate_rule_skips_cars_registered_before_2024():
    r = call_raw("business_car_expense", dict(_CAR, registered_on="2023-06-01"))
    assert r["결과"]["업무사용비율"] == 0.9


def test_plate_rule_applies_to_cars_registered_from_2024():
    assert call_raw("business_car_expense", dict(_CAR, registered_on="2024-03-01"))["결과"]["업무사용비율"] == 0


def test_plate_rule_without_date_warns():
    r = call_raw("business_car_expense", dict(_CAR))
    assert r["결과"]["업무사용비율"] == 0
    assert any("registered_on" in x for x in r.get("주의", []))


# ── 7. 일감몰아주기 일반기업 1천억원 요건: 2018년 개시 사업연도부터(영 제28638호 부칙 제4조)
def _tunnel(fs, fe):
    r = call_raw("tunnelling_gift_nts", dict(size="일반", fiscal_year_start=fs, fiscal_year_end=fe, sales_total=400_000_000_000,
                                                sales_by_corp={"A": 110_000_000_000}, relations={"직접": 0.3},
                                                op_income=10_000_000_000, taxable_income=10_000_000_000, tax=2_000_000_000))
    assert "error" not in r, r
    return r.get("결과", r)


def test_tunnelling_1000eok_route_not_for_2017_start_year():
    r = _tunnel("2017-04-01", "2018-03-31")
    assert r["과세 대상"] is False and r["합계"] == 0


def test_tunnelling_1000eok_route_from_2018_start_year():
    r = _tunnel("2018-04-01", "2019-03-31")
    assert r["과세 대상"] is True and r["합계"] == 540_000_000


# ── 8~10. 범위 밖 거절
def test_out_of_range_rejected():
    assert "error" in call_raw("nonprofit_reserve_limit", {"year": 2010, "interest_income": 0, "dividend_income": 0, "other_income": 100_000_000})
    assert "error" in call_raw("related_judge", {"a": "김갑", "b": "김을", "on": "2010-01-01",
                                                  "people": {"김갑": {"구분": "개인"}, "김을": {"구분": "개인"}},
                                                  "family": [["김갑", "김을", "부모자녀"]], "stakes": []})
    assert "error" in call_raw("capital_gains_unfair_transaction", {"mode": "증여후양도", "gift_date": "2008-01-01",
                                                                     "transfer_date": "2012-01-01", "donee_relation": "직계존비속"})


def test_gift_before_2016_with_transfer_in_range_still_computed():
    r = call_raw("capital_gains_unfair_transaction", {"mode": "증여후양도", "gift_date": "2014-01-01", "transfer_date": "2017-01-01",
                                                      "donee_relation": "기타특수관계인", "donee_gift_tax": 1,
                                                      "donee_capital_gains_tax": 1, "donor_direct_capital_gains_tax": 5})
    assert r["결과"]["증여자_직접양도_간주"] is True


# ── 해석 근거·공백 표시(2026-11-24 연도 점검 마무리)
def test_treaty_cap_before_2019_points_to_law_mcp():
    _, r = _ftc_recognized(2017, russia_override=False)
    assert any("2019년 과세기간부터" in x and "search_tax_rulings" in x for x in r.get("주의", []))


def test_2015_carryforward_marked_as_interpretation_gap():
    r = call_raw("individual_foreign_tax_credit", dict(_FTC, year=2022, countries=[dict(country="미국", foreign_income=10_000_000, foreign_tax=0)],
                                                       carryforward=[{"country": "미국", "year": 2015, "amount": 300_000}]))
    assert any(x.startswith("해석 공백 — 2015년 발생분") for x in r.get("주의", []))
