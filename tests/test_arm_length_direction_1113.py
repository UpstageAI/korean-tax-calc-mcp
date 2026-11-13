"""정상가격 범위 — 분석대상 국내·국외 구분 필수와 방향 문장. Claude 작성(2026-11-13).

분석대상이 국외 판매법인인데 국내 법인으로 계산되면 조정 방향이 반대가 된다(거주자 소득 과다로 표시).
구분을 비우면 계산하지 않고, 이름으로 추측하지 않는다.
"""
import korean_tax_calc_mcp.server as S

f = getattr(S.arm_length_range, "fn", S.arm_length_range)
C8 = [0.012, 0.021, 0.025, 0.031, 0.038, 0.044, 0.052, 0.067]   # 사분위(INC) 2.4%~4.6%, 중위값 3.45%


def test_missing_resident_flag_is_error():
    r = f(comparables=C8, tested_value=0.075, base_amount=6_000_000_000)
    assert "error" in r
    assert any("tested_is_resident" in m for m in r["문제"])


def test_foreign_tested_party_above_range_means_domestic_income_low():
    # 미국 판매법인 영업이익률 7.5% > 상한 4.6% → 본사가 싸게 넘김 → 국내 법인 소득 과소, (3.45% − 7.5%) × 60억 = 2.43억
    r = f(comparables=C8, tested_value=0.075, base_amount=6_000_000_000, tested_is_resident=False)["결과"]
    assert r["거주자_소득"] == "과소"
    assert r["조정액"] == 243_000_000
    assert r["방향"].startswith("분석대상(국외 법인)") and "상한 초과" in r["방향"] and "증액 조정 대상" in r["방향"]


def test_domestic_tested_party_above_range_means_domestic_income_high():
    r = f(comparables=C8, tested_value=0.075, base_amount=6_000_000_000, tested_is_resident=True)["결과"]
    assert r["거주자_소득"] == "과다"
    assert r["방향"].startswith("분석대상(국내 법인)") and "경정청구" in r["방향"]


def test_inside_range_needs_flag_too_but_no_direction():
    assert "error" in f(comparables=C8, tested_value=0.03)
    r = f(comparables=C8, tested_value=0.03, tested_is_resident=False)["결과"]
    assert r["범위_안"] is True and "방향" not in r
