"""도구 공백 5건(새 도구 5개)의 정답 테스트. 작성 Claude 2026-10-24.
각 값은 손으로 푼 결과와 같다(docs/SPEC_gold_gaps2.md)."""
import asyncio, json
from korean_tax_calc_mcp.server import mcp


def c(tool, a):
    r = asyncio.run(mcp.call_tool(tool, a))
    return json.loads((r.content[0] if hasattr(r, "content") else r[0][0]).text)


# 1. 법인 임대보증금 간주익금
RENTALS = [{"구분": "비주택", "보증금": 50000000, "건설비": 100000000, "임대면적비율": 0.2},
           {"구분": "주택", "보증금": 200000000, "건설비": 300000000, "임대면적비율": 0.5}]


def test_deemed_rent_income_excludes_housing():
    r = c("corporate_deemed_rent_income", {"year": 2024, "rentals": RENTALS, "financial_income": 100000, "rate": 0.05})
    assert r["결과"]["간주익금"] == 1400000
    assert r["계산"]["제외_주택보증금"] == 200000000
    assert r["결과"]["세무조정"][0]["소득처분"] == "기타사외유출"


def test_deemed_rent_income_not_applicable_without_debt_condition():
    r = c("corporate_deemed_rent_income", {"year": 2024, "rentals": RENTALS, "rate": 0.05, "debt_over_2x": False})
    assert r["결과"]["간주익금"] == 0
    assert any("적용 대상 아님" in p["결론"] for p in r["판단"])


def test_deemed_rent_income_never_negative():
    r = c("corporate_deemed_rent_income", {"year": 2024, "rate": "5%", "financial_income": 100000,
                                           "rentals": [{"구분": "비주택", "보증금": 50000000, "건설비": 300000000, "임대면적비율": 0.2}]})
    assert r["결과"]["간주익금"] == 0


# 2. 추계 사업소득
REV = [{"구분": "매출", "금액": 170000000}, {"구분": "보조금", "금액": 20000000}, {"구분": "유형자산처분", "금액": 10000000}]
EXP = [{"구분": "매입", "금액": 30000000}, {"구분": "임차료", "금액": 10000000}, {"구분": "인건비", "금액": 40000000},
       {"구분": "기타", "금액": 2000000}, {"구분": "자산취득", "금액": 50000000}]


def test_estimated_income_base_rate_simple_bookkeeper():
    r = c("estimated_business_income", {"year": 2024, "industry_group": "나", "prior_year_revenue": 35000000,
                                        "revenues": REV, "expenses": EXP, "base_rate": 0.2, "simple_rate": 0.6})
    assert r["결과"]["사업소득금액"] == 72000000
    assert r["계산"]["수입금액"] == 190000000 and r["계산"]["주요경비"] == 80000000
    assert r["계산"]["장부구분"] == "간편장부대상자" and r["계산"]["적용방법"] == "기준경비율"


def test_estimated_income_double_entry_half_rate_and_disposal_included():
    r = c("estimated_business_income", {"year": 2024, "industry_group": "나", "prior_year_revenue": 200000000,
                                        "revenues": REV, "expenses": EXP, "base_rate": "20%", "simple_rate": "60%"})
    # 수입 200M, 200 − 80 − 200×10% = 100M, 한도 200×40%×3.4 = 272M
    assert r["계산"]["장부구분"] == "복식부기의무자" and r["계산"]["수입금액"] == 200000000
    assert r["결과"]["사업소득금액"] == 100000000


def test_estimated_income_simple_rate_when_small():
    r = c("estimated_business_income", {"year": 2024, "industry_group": "나", "prior_year_revenue": 30000000,
                                        "revenues": [{"구분": "매출", "금액": 100000000}], "expenses": [],
                                        "base_rate": 0.2, "simple_rate": 0.6})
    assert r["계산"]["적용방법"] == "단순경비율" and r["결과"]["사업소득금액"] == 40000000


def test_estimated_income_capped_by_simple_rate_multiple():
    r = c("estimated_business_income", {"year": 2024, "industry_group": "나", "prior_year_revenue": 40000000,
                                        "revenues": [{"구분": "매출", "금액": 100000000}], "expenses": [],
                                        "base_rate": 0.1, "simple_rate": 0.9})
    # 기준 100 − 0 − 10 = 90M, 한도 100×10%×2.8 = 28M
    assert r["계산"]["적용방법"] == "기준경비율" and r["결과"]["사업소득금액"] == 28000000


# 3. 면세전용 간주공급
ASSETS = [{"구분": "토지", "취득일": "2022-10-05", "취득가액": 50000000},
          {"구분": "건물", "취득일": "2022-10-05", "취득가액": 40000000},
          {"구분": "기타", "취득일": "2023-12-09", "취득가액": 10000000}]


def test_exempt_use_partial_prorated_by_exempt_ratio():
    r = c("vat_exempt_use_deemed_supply", {"use_date": "2024-10-01", "mode": "일부", "assets": ASSETS,
                                           "supplies": {"taxable": 180000000, "exempt": 60000000}})
    assert r["결과"]["과세표준"] == 9250000
    by = {a["구분"]: a for a in r["계산"]["자산별"]}
    assert by["건물"]["경과과세기간수"] == 4 and by["건물"]["간주시가"] == 32000000
    assert by["기타"]["경과과세기간수"] == 2 and by["기타"]["간주시가"] == 5000000
    assert "제외사유" in by["토지"]


def test_exempt_use_full_and_fully_depreciated():
    r = c("vat_exempt_use_deemed_supply", {"use_date": "2024-10-01", "mode": "전부",
                                           "assets": ASSETS + [{"구분": "기타", "취득일": "2021-03-01", "취득가액": 7000000}]})
    assert r["결과"]["과세표준"] == 37000000


def test_exempt_use_below_5_percent_is_not_supply():
    r = c("vat_exempt_use_deemed_supply", {"use_date": "2024-10-01", "mode": "일부", "assets": ASSETS,
                                           "supplies": {"taxable": 960000000, "exempt": 40000000}})
    assert r["결과"]["과세표준"] == 0


# 4. 청산소득
LIQ = {"assets_realized": 510000000, "liabilities_paid": 150000000, "capital": 100000000, "surplus": 150000000}


def test_liquidation_income_with_capitalized_surplus_and_loss_limit():
    r = c("liquidation_income", {**LIQ, "carryforward_loss": 180000000, "capitalized_surplus_2y": 20000000})
    assert r["계산"]["잔여재산가액"] == 360000000
    assert r["계산"]["결손금_상계"] == 170000000 and r["계산"]["자기자본총액"] == 80000000
    assert r["결과"]["청산소득금액"] == 280000000


def test_liquidation_income_loss_limited_to_surplus():
    r = c("liquidation_income", {**LIQ, "carryforward_loss": 180000000})
    assert r["계산"]["결손금_상계"] == 150000000 and r["결과"]["청산소득금액"] == 260000000


def test_liquidation_income_small_loss():
    r = c("liquidation_income", {**LIQ, "carryforward_loss": 100000000, "assets_realized": [{"항목": "토지", "금액": 300000000}, {"항목": "기타", "금액": 210000000}]})
    assert r["결과"]["청산소득금액"] == 210000000


# 5. 차가감소득금액
ITEMS = [{"항목": "공장건물 재산세", "종류": "사업용 재산세", "금액": 7000000},
         {"항목": "특례기부금 한도초과", "종류": "기부금 한도초과", "금액": 15000000},
         {"항목": "법인세", "종류": "법인세비용", "금액": 8000000},
         {"항목": "국세 환급금 이자", "종류": "환급금이자", "금액": 2000000},
         {"항목": "자기주식처분이익", "종류": "자기주식처분이익(자본잉여금)", "금액": 9000000},
         {"항목": "정기예금 미수이자", "종류": "미수이자(원천징수대상)", "금액": 4000000},
         {"항목": "대표이사 종친회 기부금", "종류": "비지정기부금", "금액": 5000000}]


def test_income_adjustment_total():
    r = c("income_adjustment_total", {"net_income": 100000000, "items": ITEMS})
    assert r["결과"]["차가감소득금액"] == 116000000
    assert r["결과"]["각사업연도소득금액"] == 131000000
    assert r["결과"]["익금산입_손금불산입"] == 22000000 and r["결과"]["손금산입_익금불산입"] == 6000000
    처분 = {a["구분"]: a["소득처분"] for a in r["결과"]["세무조정"]}
    assert 처분.get("정기예금 미수이자") == "△유보"
    assert not any("재산세" in a["구분"] for a in r["결과"]["세무조정"])


def test_income_adjustment_explicit_direction_and_unknown_kind():
    r = c("income_adjustment_total", {"net_income": 10000000, "items": [{"항목": "가", "종류": "사전에 없는 것", "금액": 1000000, "방향": "차감"}]})
    assert r["결과"]["차가감소득금액"] == 9000000
    r = c("income_adjustment_total", {"net_income": 10000000, "items": [{"항목": "나", "종류": "사전에 없는 것", "금액": 1000000}]})
    assert "입력 확인 필요" in json.dumps(r, ensure_ascii=False)


# 검수 반영(SPEC_gold_gaps2b)
def test_exempt_use_non_depreciable_uses_market_value():
    r = c("vat_exempt_use_deemed_supply", {"use_date": "2024-10-01", "mode": "전부",
                                           "assets": [{"구분": "비상각", "취득일": "2024-01-10", "취득가액": 1000000, "시가": 3000000}]})
    assert r["결과"]["과세표준"] == 3000000


def test_exempt_use_rejects_unknown_kind_and_use_before_acquisition():
    r = c("vat_exempt_use_deemed_supply", {"use_date": "2024-10-01", "mode": "전부",
                                           "assets": [{"구분": "차량", "취득일": "2023-01-10", "취득가액": 1000000}]})
    assert "입력 확인 필요" in json.dumps(r, ensure_ascii=False)
    r = c("vat_exempt_use_deemed_supply", {"use_date": "2023-03-01", "mode": "전부",
                                           "assets": [{"구분": "건물", "취득일": "2024-01-10", "취득가액": 1000000}]})
    assert "입력 확인 필요" in json.dumps(r, ensure_ascii=False)


def test_estimated_income_explicit_multiplier_not_scaled():
    a = {"year": 2024, "industry_group": "나", "prior_year_revenue": 40000000,
         "revenues": [{"구분": "매출", "금액": 100000000}], "expenses": [], "base_rate": 0.1, "simple_rate": 0.9}
    assert c("estimated_business_income", {**a, "multiplier": 2.8})["결과"]["사업소득금액"] == 28000000


def test_estimated_income_rejects_unknown_item_kind():
    r = c("estimated_business_income", {"year": 2024, "industry_group": "나", "prior_year_revenue": 40000000,
                                        "revenues": [{"구분": "매출액", "금액": 100000000}], "expenses": [],
                                        "base_rate": 0.1, "simple_rate": 0.9})
    assert "입력 확인 필요" in json.dumps(r, ensure_ascii=False)


def test_deemed_rent_area_ratio_accepts_percent():
    rentals = [{"구분": "비주택", "보증금": 50000000, "건설비": 100000000, "임대면적비율": 20}]
    r = c("corporate_deemed_rent_income", {"year": 2024, "rentals": rentals, "financial_income": 100000, "rate": 0.05})
    assert r["결과"]["간주익금"] == 1400000


def test_income_adjustment_rejects_unknown_direction():
    r = c("income_adjustment_total", {"net_income": 10000000, "items": [{"항목": "가", "종류": "법인세비용", "금액": 1000000, "방향": "더하기"}]})
    assert "입력 확인 필요" in json.dumps(r, ensure_ascii=False)
