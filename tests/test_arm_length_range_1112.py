"""0.33.0 arm_length_range 정답 테스트(2026-11-12, Claude 손계산). 근거: 국조령 제15조⑤⑥(2021.12.31.·2026.11.1. 시행본)."""
from korean_tax_calc_mcp import server as S

C8 = [0.012, 0.021, 0.025, 0.031, 0.038, 0.044, 0.052, 0.067]


def f(**k):
    return getattr(S.arm_length_range, "fn", S.arm_length_range)(**k)


def test_quartiles_inclusive():
    # n=8: Q1 위치 1.75 → 0.021 + 0.75×0.004 = 0.024, 중위값 (0.031+0.038)/2 = 0.0345, Q3 위치 5.25 → 0.044 + 0.25×0.008 = 0.046
    r = f(comparables=C8, tested_value=0.03, tested_is_resident=True)["결과"]
    assert (r["제1사분위"], r["중위값"], r["제3사분위"]) == (0.024, 0.0345, 0.046)
    assert r["평균값"] == 0.03625 and r["범위_안"] is True and r["조정_필요"] is False and r["조정액"] == 0


def test_foreign_tested_party_below_range():
    # 해외 판매법인 이익률 0.8% < 하한 2.4% → 중위값 3.45%까지, 차이 2.65%p × 매출 100억 = 2.65억. 해외법인 소득이 적다 = 거주자 소득 과다
    r = f(comparables=C8, tested_value=0.008, base_amount=10_000_000_000, tested_is_resident=False)
    res = r["결과"]
    assert res["조정_필요"] is True and res["조정액"] == 265_000_000 and res["거주자_소득"] == "과다"
    assert any("제6조" in p["결론"] for p in r["판단"])


def test_foreign_tested_party_above_range_means_resident_income_low():
    # 해외 판매법인 이익률 8% > 상한 4.6% → 거주자(본사) 소득 과소, (8% − 3.45%) × 100억 = 4.55억
    r = f(comparables=C8, tested_value=0.08, base_amount=10_000_000_000, tested_is_resident=False)
    assert r["결과"]["거주자_소득"] == "과소" and r["결과"]["조정액"] == 455_000_000
    assert any("제7조" in p["결론"] for p in r["판단"])


def test_resident_tested_party_and_direction_flag():
    assert f(comparables=C8, tested_value=0.008, base_amount=1_000_000_000, tested_is_resident=True)["결과"]["거주자_소득"] == "과소"
    # 분석대상(거주자)이 지급하는 수수료율처럼 높을수록 소득이 줄어드는 지표
    r = f(comparables=C8, tested_value=0.08, higher_is_more_income=False, tested_is_resident=True)
    assert r["결과"]["거주자_소득"] == "과소"


def test_full_range_and_mean_point():
    r = f(comparables=C8, tested_value=0.05, range_type="전체", tested_is_resident=True)["결과"]
    assert r["범위"] == {"종류": "전체", "하한": 0.012, "상한": 0.067} and r["범위_안"] is True
    assert f(comparables=C8, tested_value=0.05, tested_is_resident=True)["결과"]["범위_안"] is False          # 사분위 상한 4.6% 초과
    r = f(comparables=C8, tested_value=0.07, range_type="전체", point="평균값", base_amount=1_000_000_000, tested_is_resident=True)["결과"]
    assert r["기준점"] == {"종류": "평균값", "값": 0.03625} and r["조정액"] == 33_750_000


def test_custom_point_must_be_inside_range():
    ok = f(comparables=C8, tested_value=0.008, point="직접입력", point_value=0.024, base_amount=1_000_000_000, tested_is_resident=True)
    assert ok["결과"]["조정액"] == 16_000_000
    bad = f(comparables=C8, tested_value=0.008, point="직접입력", point_value=0.05, tested_is_resident=True)
    assert "error" in bad and "범위" in bad["문제"][0]


def test_quartile_exclusive_and_odd_count():
    # n=5 [1,2,3,4,5]%: inclusive Q1=2%, Q3=4% / exclusive Q1 위치 0.5 → 1.5%, Q3 위치 3.5 → 4.5%
    c = [0.01, 0.02, 0.03, 0.04, 0.05]
    a = f(comparables=c, tested_value=0.03, tested_is_resident=True)["결과"]
    b = f(comparables=c, tested_value=0.03, quartile_method="exclusive", tested_is_resident=True)["결과"]
    assert (a["제1사분위"], a["제3사분위"]) == (0.02, 0.04) and (b["제1사분위"], b["제3사분위"]) == (0.015, 0.045) and a["중위값"] == b["중위값"] == 0.03


def test_named_comparables_and_notes():
    r = f(comparables=[{"이름": "가", "값": 0.05}, {"이름": "나", "값": 0.02}, {"이름": "다", "값": 0.03}], tested_value=0.01, tested_is_resident=True)
    assert [x["이름"] for x in r["계산"]["비교대상_정렬"]] == ["나", "다", "가"]
    assert "제15조⑤⑥" in r["근거"] and any("판단하지 않음" in s for s in r["주의"]) and any("3.57" in p["근거"] for p in r["판단"])


def test_input_errors():
    assert "error" in f(comparables=[0.03], tested_value=0.02, tested_is_resident=True)
    assert "error" in f(comparables=[0.03, "x"], tested_value=0.02, tested_is_resident=True)
    assert "error" in f(comparables=C8, tested_value=0.02, year=2020, tested_is_resident=True)
    assert "error" in f(comparables=[0.01, 0.02], tested_value=0.02, quartile_method="exclusive", tested_is_resident=True)
    assert "error" in f(comparables=C8, tested_value=0.008, point="직접입력", tested_is_resident=True)
    assert "error" not in f(comparables=C8, tested_value=0.02, year=2025, tested_is_resident=True)
