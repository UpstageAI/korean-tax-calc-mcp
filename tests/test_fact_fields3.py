"""항목형 입력 3차 — 전기 자료를 그대로 받아 당기 기초값을 도구가 계산, 입력 관용(비율 %, Gross-up 포함 여부 기본값, 과세 가공식품 사전). 작성 Claude 2026-10-22.
근거: 정답 인자 대조에서 모델이 가장 많이 틀린 필드가 감가상각의 prior_book_value(44회)·prior_disallowed(26회)·accumulated_dep_begin — 전기 상각·추인을 거쳐 당기 기초값을 못 구한다."""
import asyncio, json
from korean_tax_calc_mcp.server import mcp


def c(tool, a):
    r = asyncio.run(mcp.call_tool(tool, a))
    return json.loads((r.content[0] if hasattr(r, "content") else r[0][0]).text)


def test_prior_year_block_derives_current_begin_values():
    # 22기: 기초 누계 60M, 기초 부인누계 5M, 회사 상각 12.5M, 범위액 13.5M → 시인부족 1M 추인 → 23기 기초 부인 4M, 기초 누계 72.5M, 장부가액 27.5M
    r = c("depreciation_adjustment", {"year": 2023, "method": "무신고", "asset_class": "건축물외_유형자산", "rate": 0.3,
                                      "acquisition_cost": 100000000, "booked_depreciation": 15000000, "expensed_capex": 1000000,
                                      "prior_year": {"accumulated_dep_begin": 60000000, "disallowed_begin": 5000000,
                                                     "booked_depreciation": 12500000, "limit": 13500000}})
    assert "error" not in r
    assert r["결과"]["상각부인액"] == 5550000
    assert r["계산"]["기초 감가상각누계액"] == 72500000
    assert r["계산"]["전기_계산"]["기초_상각부인누계액"] == 4000000
    assert r["계산"]["전기_계산"]["직전_장부가액"] == 27500000
    assert any("추인" in str(p) for p in r["판단"])


def test_prior_year_block_first_year_tax_exempt_month_prorated():
    # 창업중소기업 감면 법인, 기계 2021.7.1 취득, 2기 회사 상각 25M, 범위액 500M×0.259×6/12=64.75M → 의제상각 △39.75M, 3기 미상각잔액 322,520,250
    r = c("depreciation_adjustment", {"year": 2022, "method": "무신고", "asset_class": "건축물외_유형자산", "rate": 0.259, "useful_life": 10,
                                      "acquisition_cost": 500000000, "booked_depreciation": 50000000, "accumulated_dep_end": 75000000,
                                      "expensed_capex": 22000000, "tax_exempt": True,
                                      "prior_year": {"accumulated_dep_begin": 0, "disallowed_begin": 0, "booked_depreciation": 25000000,
                                                     "in_service_date": "2021-07-01", "tax_exempt": True}})
    assert "error" not in r
    assert r["계산"]["전기_계산"]["전기_상각범위액"] == 64750000
    assert r["계산"]["전기_계산"]["기초_상각부인누계액"] == -39750000
    assert r["결과"]["세무상_미상각잔액"] == 322520250


def test_prior_year_block_conflicting_with_explicit_values_is_rejected():
    r = c("depreciation_adjustment", {"year": 2023, "method": "무신고", "asset_class": "건축물외_유형자산", "rate": 0.3,
                                      "acquisition_cost": 100000000, "booked_depreciation": 15000000,
                                      "prior_disallowed": 5000000,
                                      "prior_year": {"accumulated_dep_begin": 60000000, "disallowed_begin": 5000000,
                                                     "booked_depreciation": 12500000, "limit": 13500000}})
    assert "error" in r and "prior_year" in json.dumps(r, ensure_ascii=False)


def test_dividend_ratio_given_as_percent_is_accepted():
    r = c("dividend_received_deduction", {"year": 2021, "investees": [{"name": "B", "listed": False, "ratio": 10, "dividend": 340000}]})
    assert r["결과"]["익금불산입액"] == 102000
    assert r["결과"]["피출자법인별"][0]["출자비율"] == 0.1
    assert any("%" in str(p) or "퍼센트" in str(p) or "백분율" in str(p) for p in r["판단"])


def test_foreign_tax_credit_grossup_flag_optional_defaults_to_included():
    r = c("foreign_tax_credit", {"year": 2022, "base": 400000000, "method": "세액공제",
                                 "countries": [{"country": "B국", "foreign_income": 100000000, "direct_tax": 0,
                                                "subsidiaries": [{"name": "B자회사", "dividend": 100000000, "withholding_tax": 10000000, "received_on": "2022-03-31",
                                                                  "ownership": 0.4, "holding_months": 12, "resource_dev": False, "sub_income": 270000000, "sub_tax": 20000000}]}]})
    assert "error" not in r and r["결과"]["외국납부세액공제액"] == 16200000
    assert any("포함" in str(p) and "가정" in str(p) for p in r.get("판단", [])) or "가정" in json.dumps(r, ensure_ascii=False)


def test_deemed_input_processed_food_dictionary():
    # 치즈는 과세 가공식품 — taxable_goods 표시 없이도 도구가 사전으로 제외
    r = c("vat_deemed_input_credit", {"period": "2021-1", "industry": "제조", "individual": False, "sme": True,
                                      "items": [{"name": "돼지고기", "purchase_price": 26000000, "usage": {"제조": 60, "재판매": 30, "재고": 10}},
                                                {"name": "밀가루", "purchase_price": 22100000, "imported": True, "customs_value": 20800000, "customs_duty": 1300000, "usage": {"제조": 100}},
                                                {"name": "소금", "purchase_price": 10920000, "freight_included": 520000, "usage": {"제조": 100}},
                                                {"name": "치즈", "purchase_price": 5200000, "usage": {"제조": 100}},
                                                {"name": "김치", "purchase_price": 3900000, "usage": {"종업원제공": 100}}]})
    assert r["결과"]["의제매입세액"] == 1900000
    cheese = [p for p in r["계산"]["품목별"] if p["name"] == "치즈"][0]
    assert cheese["공제대상"] == 0 and "과세" in cheese["판단"]
