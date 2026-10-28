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

