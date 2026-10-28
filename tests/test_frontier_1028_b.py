"""사업소득·결손금 연도별 규칙 회귀 테스트(소득세법 제45조·제19조, 영 제143조, 규칙 제67조, 제129조). 작성 Claude 2026-10-28."""
import asyncio, json
from korean_tax_calc_mcp.server import mcp


def c(tool, a):
    r = asyncio.run(mcp.call_tool(tool, a))
    return json.loads((r.content[0] if hasattr(r, "content") else r[0][0]).text)


def biz(x):
    return {"book_income": x, "adjustments": []}


# ── 제45조③: 이월결손금 소멸기한은 발생연도 기준(2019년 이전 발생 10년, 2020년 이후 발생 15년) ──

def test_history_keeps_origin_year_and_expires():
    # 2014년 결손 2,000만 → 2024년 근로 500만에서 공제, 1,500만 남음(2014년분)
    # 2025년: 2014 + 10 = 2024 < 2025 → 소멸. 종합소득금액 = 근로 3,000만 그대로
    r = c("income_loss_offset", {"year": 2025, "incomes": {"근로": 30_000_000}, "history": [
        {"year": 2014, "incomes": {}, "business": biz(-20_000_000)},
        {"year": 2024, "incomes": {"근로": 5_000_000}}]})
    res = r["결과"]
    assert res["종합소득금액"] == 30_000_000
    assert res["이력_계산"][1]["남은_결손금_발생연도별"] == [{"year": 2014, "kind": "사업", "amount": 15_000_000}]
    assert res["소멸"][0]["연도"] == 2014 and res["소멸"][0]["금액"] == 15_000_000


def test_history_separate_buckets_10y_and_15y():
    # 2014년 결손 1,000만(10년, 2024년까지), 2020년 결손 800만(15년, 2035년까지)
    # 2025년 근로 3,000만: 2014분 소멸, 2020분 800만 공제 → 2,200만
    r = c("income_loss_offset", {"year": 2025, "incomes": {"근로": 30_000_000}, "history": [
        {"year": 2014, "incomes": {}, "business": biz(-10_000_000)},
        {"year": 2020, "incomes": {}, "business": biz(-8_000_000)}]})
    res = r["결과"]
    assert res["종합소득금액"] == 22_000_000
    assert [(x["연도"], x["금액"]) for x in res["소멸"]] == [(2014, 10_000_000)]
    assert res["이월결손금(다음 연도로)"]["사업"] == 0


def test_by_origin_output_carries_current_loss():
    r = c("income_loss_offset", {"year": 2023, "incomes": {"근로": 2_000_000}, "business": biz(-5_000_000),
                                 "carryforwards": [{"year": 2021, "kind": "사업", "amount": 1_000_000}]})
    res = r["결과"]
    # 당기 결손 500만 → 근로 200만 공제, 300만 이월(2023년분). 2021분 100만은 공제할 소득 없음 → 그대로 이월
    assert res["이월결손금(다음 연도로)"]["사업"] == 4_000_000
    assert res["이월결손금_발생연도별"] == [{"year": 2021, "kind": "사업", "amount": 1_000_000},
                                       {"year": 2023, "kind": "사업", "amount": 3_000_000}]


# ── 제45조④: 추계 연도는 공제만 안 하고 이월결손금은 남음 ──

def test_estimated_year_keeps_carryforward():
    r = c("income_loss_offset", {"year": 2023, "incomes": {}, "business": biz(5_000_000), "estimated": True,
                                 "carryforwards": [{"year": 2022, "kind": "사업", "amount": 2_000_000}]})
    assert r["결과"]["종합소득금액"] == 5_000_000
    assert r["결과"]["이월결손금(다음 연도로)"]["사업"] == 2_000_000
    assert r["결과"]["추계_공제배제"][0]["금액"] == 2_000_000


def test_estimated_history_year_then_deduct_later():
    # 2021 결손 1,000만 → 2022 추계(공제 안 함, 이월 유지) → 2023 사업 600만에서 공제, 400만 남음
    r = c("income_loss_offset", {"year": 2023, "incomes": {}, "business": biz(6_000_000), "history": [
        {"year": 2021, "incomes": {}, "business": biz(-10_000_000)},
        {"year": 2022, "incomes": {}, "business": biz(5_000_000), "estimated": True}]})
    res = r["결과"]
    assert res["이력_계산"][1]["종합소득금액"] == 5_000_000
    assert res["종합소득금액"] == 0
    assert res["이월결손금_발생연도별"] == [{"year": 2021, "kind": "사업", "amount": 4_000_000}]


# ── 영 제143조④: 단순경비율 대상의 해당 과세기간 수입금액 요건은 2019년 귀속부터(2018.2.13. 개정) ──

_A = {"industry_group": "나", "prior_year_revenue": 30_000_000,
      "revenues": [{"구분": "매출", "금액": 200_000_000}], "expenses": [{"구분": "매입", "금액": 50_000_000}],
      "base_rate": 0.2, "simple_rate": 0.6}


def test_simple_rate_eligibility_2018_continuing_business():
    # 직전 3,000만 < 3,600만 → 2018년 귀속까지는 당해 수입(2억)과 무관하게 단순경비율: 2억 × 0.4 = 8,000만
    r = c("estimated_business_income", {**_A, "year": 2018})
    assert r["결과"]["사업소득금액"] == 80_000_000
    assert r["계산"]["적용방법"] == "단순경비율"


def test_simple_rate_eligibility_2024_needs_current_revenue():
    # 2019년 귀속부터 당해 수입 2억 ≥ 1억5천만 → 기준경비율: 2억 − 5천만 − 2억×0.2 = 1억1천만(한도 8천만×2.8 = 2억2,400만)
    r = c("estimated_business_income", {**_A, "year": 2024})
    assert r["결과"]["사업소득금액"] == 110_000_000
    assert r["계산"]["적용방법"] == "기준경비율"


# ── 규칙 제67조: 배율 2.6/3.2(2020.3.12.까지), 2.8/3.4(2020.3.13.부터) ──

_B = {"industry_group": "나", "prior_year_revenue": 40_000_000,
      "revenues": [{"구분": "매출", "금액": 100_000_000}], "expenses": [],
      "base_rate": 0.1, "simple_rate": 0.9}   # 기준경비율 소득 9,000만, 단순경비율 소득 1,000만


def test_multiplier_by_year():
    assert c("estimated_business_income", {**_B, "year": 2017})["결과"]["사업소득금액"] == 26_000_000   # × 2.6
    assert c("estimated_business_income", {**_B, "year": 2020})["결과"]["사업소득금액"] == 28_000_000   # × 2.8
    r = c("estimated_business_income", {**_B, "year": 2019})
    assert "error" in r and "multiplier" in r["문제"][0]
    assert c("estimated_business_income", {**_B, "year": 2019, "multiplier": 2.6})["결과"]["사업소득금액"] == 26_000_000


# ── 법 제19조①20호: 복식부기의무자 사업용 유형자산 처분액은 2018년 귀속부터 수입금액 ──

_C = {"industry_group": "나", "prior_year_revenue": 200_000_000,
      "revenues": [{"구분": "매출", "금액": 100_000_000}, {"구분": "유형자산처분", "금액": 20_000_000}],
      "expenses": [], "base_rate": 0.2, "simple_rate": 0.7}


def test_asset_disposal_revenue_from_2018():
    # 2017: 수입 1억, 1억 − 1억×0.1(복식 ½) = 9,000만, 한도 3,000만×3.2 = 9,600만 → 9,000만
    r17 = c("estimated_business_income", {**_C, "year": 2017})
    assert r17["계산"]["수입금액"] == 100_000_000 and r17["결과"]["사업소득금액"] == 90_000_000
    # 2018: 수입 1억2천만, 1억2천만 − 1,200만 = 1억800만, 한도 3,600만×3.2 = 1억1,520만 → 1억800만
    r18 = c("estimated_business_income", {**_C, "year": 2018})
    assert r18["계산"]["수입금액"] == 120_000_000 and r18["결과"]["사업소득금액"] == 108_000_000

