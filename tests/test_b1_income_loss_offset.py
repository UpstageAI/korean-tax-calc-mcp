"""결손금·이월결손금 공제 후 종합소득금액 — 소득세법 제45조."""
from korean_tax_calc_mcp import server


def call(**kw):
    t = server.income_loss_offset
    return getattr(t, "fn", t)(**kw)


def test_current_business_loss_order():
    # 사업 결손 −2,500만 → 근로 1,000만 → 연금 500만 → 기타 300만 → 이자 400만 → 배당 600만 순서
    r = call(year=2023, business={"book_income": -25_000_000, "adjustments": []}, incomes={"근로": 10_000_000, "연금": 5_000_000, "기타": 3_000_000, "이자": 4_000_000, "배당": 6_000_000})
    res = r["결과"]
    assert res["종합소득금액"] == 3_000_000
    after = res["공제 후 소득금액"]
    assert after["근로"] == 0 and after["연금"] == 0 and after["기타"] == 0 and after["이자"] == 0 and after["배당"] == 3_000_000


def test_rental_loss_not_offset_and_carried():
    r = call(year=2023, incomes={"부동산임대": -8_000_000, "근로": 20_000_000})
    assert r["결과"]["종합소득금액"] == 20_000_000
    assert r["결과"]["이월결손금(다음 연도로)"]["부동산임대"] == 8_000_000


def test_general_loss_nets_rental_income_first():
    r = call(year=2023, business={"book_income": -5_000_000, "adjustments": []}, incomes={"부동산임대": 3_000_000, "근로": 10_000_000})
    after = r["결과"]["공제 후 소득금액"]
    assert after["부동산임대"] == 0 and after["근로"] == 8_000_000
    assert r["결과"]["종합소득금액"] == 8_000_000


def test_carryforward_order_and_current_loss_first():
    r = call(year=2023, business={"book_income": 6_000_000, "adjustments": []}, incomes={"근로": 10_000_000},
             carryforwards=[{"year": 2021, "kind": "사업", "amount": 4_000_000}, {"year": 2019, "kind": "사업", "amount": 3_000_000}])
    res = r["결과"]
    # 2019분 먼저 300만(사업), 2021분 400만 → 사업 600만에서 300만 남음 → 다음 근로에서 100만
    assert res["공제 후 소득금액"]["사업"] == 0
    assert res["공제 후 소득금액"]["근로"] == 9_000_000
    assert res["종합소득금액"] == 9_000_000


def test_rental_carryforward_only_rental():
    r = call(year=2023, incomes={"부동산임대": 2_000_000, "근로": 10_000_000},
             carryforwards=[{"year": 2022, "kind": "부동산임대", "amount": 5_000_000}])
    res = r["결과"]
    assert res["공제 후 소득금액"]["부동산임대"] == 0 and res["공제 후 소득금액"]["근로"] == 10_000_000
    assert res["이월결손금(다음 연도로)"]["부동산임대"] == 3_000_000


def test_expired_and_estimated():
    r = call(year=2023, business={"book_income": 5_000_000, "adjustments": []}, incomes={},
             carryforwards=[{"year": 2012, "kind": "사업", "amount": 2_000_000}])   # 2019 이전 발생분 10년 → 2022까지
    assert r["결과"]["종합소득금액"] == 5_000_000
    r2 = call(year=2023, business={"book_income": 5_000_000, "adjustments": []}, incomes={}, estimated=True,
              carryforwards=[{"year": 2022, "kind": "사업", "amount": 2_000_000}])   # 추계 → 이월결손금 공제 안 함
    assert r2["결과"]["종합소득금액"] == 5_000_000


def test_flat_rate_financial_excluded():
    r = call(year=2023, business={"book_income": -10_000_000, "adjustments": []}, incomes={"이자": 6_000_000}, financial_flat_rate=4_000_000)
    # 이자 600만 중 원천징수세율 적용분 400만은 공제 대상 아님 → 200만만 공제
    assert r["결과"]["공제 후 소득금액"]["이자"] == 4_000_000
    assert r["결과"]["이월결손금(다음 연도로)"]["사업"] == 8_000_000
    assert "제45조" in str(r["근거"])
