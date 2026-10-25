"""법인 재해손실세액공제 — 법인세법 제58조, 시행령 제95조."""
from korean_tax_calc_mcp import server


def call(**kw):
    t = server.disaster_loss_credit
    return getattr(t, "fn", t)(**kw)


def test_basic_ratio_and_tax():
    # 상실 전 자산총액(토지 제외) 5억, 상실 2억 → 40%. 재해 사업연도 법인세: 산출 2,000만 − 다른 공제·감면 300만 = 1,700만
    r = call(year=2025, assets=[{"구분": "사업용", "장부가액": 500_000_000, "상실액": 200_000_000}], current_tax=20_000_000, other_credits=3_000_000)
    res = r["결과"]
    assert res["자산상실비율"] == 0.4
    assert res["공제대상 법인세"] == 17_000_000
    assert res["재해손실세액공제"] == 6_800_000


def test_below_20_percent():
    r = call(year=2025, assets=[{"구분": "사업용", "장부가액": 500_000_000, "상실액": 90_000_000}], current_tax=20_000_000)
    assert r["결과"]["재해손실세액공제"] == 0
    assert "20" in r["결과"]["판정"]


def test_unpaid_prior_tax_and_penalty():
    r = call(year=2025, assets=[{"구분": "사업용", "장부가액": 100_000_000, "상실액": 50_000_000}], current_tax=4_000_000,
             unpaid_prior_tax=2_000_000, penalty=400_000)
    assert r["결과"]["공제대상 법인세"] == 6_400_000      # 미납 법인세 + 당기 법인세 + 가산세(영 제95조③)
    assert r["결과"]["재해손실세액공제"] == 3_200_000


def test_cap_at_lost_assets():
    r = call(year=2025, assets=[{"구분": "사업용", "장부가액": 10_000_000, "상실액": 3_000_000}], current_tax=50_000_000)
    assert r["결과"]["재해손실세액공제"] == 3_000_000      # 상실 자산가액 한도
    assert "제58조" in str(r["근거"])


def test_land_excluded_input_guard():
    r = call(year=2025, assets=[{"구분": "사업용", "장부가액": 0, "상실액": 0}], current_tax=1_000_000)
    assert "error" in r
