"""0.37.0 sme_status 정답 테스트(2026-11-12, Claude 손계산).
근거: 조세특례제한법 시행령 제2조(2016~2026 시행본)·2024.11.12. 개정 부칙 제2조, 중소기업기본법 시행령 별표 1·2·3(2017.10.17. 개정본, 2025.9.1. 개정본)."""
from korean_tax_calc_mcp import server as S

E = 100_000_000


def F(**k):
    return getattr(S.sme_status, "fn", S.sme_status)(**k)


def test_cosmetics_maker_grows_from_small_to_medium():
    # 화학제품 제조업(C20): 소기업 120억, 중소기업 1,000억(2024까지)·1,200억(2025~)
    assert F(year=2022, industry_code="C20", revenue=60 * E, total_assets=40 * E)["결과"] == {"중소기업": True, "구분": "소기업"}
    assert F(year=2023, industry_code="C20", revenue=150 * E, total_assets=90 * E)["결과"] == {"중소기업": True, "구분": "중기업"}
    r = F(year=2025, industry_code="C20", revenue=500 * E, total_assets=250 * E)
    assert r["결과"] == {"중소기업": True, "구분": "중기업"} and r["계산"]["중소기업_매출_기준"] == 1_200 * E


def test_wholesale_thresholds_by_year():
    # 도매 및 소매업(G): 소기업 50억(2024까지)·60억(2025~)
    assert F(year=2024, industry_code="G", revenue=55 * E, total_assets=30 * E)["결과"]["구분"] == "중기업"
    assert F(year=2025, industry_code="G", revenue=55 * E, total_assets=30 * E)["결과"]["구분"] == "소기업"
    assert F(year=2024, industry_code="G", revenue=1_100 * E, total_assets=500 * E)["결과"]["구분"] == "유예기간 중"       # 1,000억 초과
    assert F(year=2025, industry_code="G", revenue=1_100 * E, total_assets=500 * E)["결과"]["구분"] == "중기업"           # 2025부터 1,200억


def test_grace_period_three_then_five_years():
    # 2022에 처음 초과 → 2022~2025 유예(3개 과세연도), 2026은 아님
    k = dict(industry_code="C20", revenue=1_300 * E, total_assets=900 * E, first_exceeded_year=2022)
    assert F(year=2025, **k)["결과"] == {"중소기업": True, "구분": "유예기간 중"}
    assert F(year=2026, **k)["결과"] == {"중소기업": False, "구분": "중소기업 아님"}
    # 2024에 처음 초과 → 5개 과세연도(2029까지)
    r = F(year=2026, industry_code="C20", revenue=1_300 * E, total_assets=900 * E, first_exceeded_year=2024)
    assert r["결과"]["구분"] == "유예기간 중" and r["계산"]["유예기간"] == "2024~2029 과세연도"


def test_no_grace_when_exceeded_within_two_years_of_founding():
    r = F(year=2023, industry_code="G", revenue=1_100 * E, total_assets=300 * E, founded_on="2021-03-02")
    assert r["결과"] == {"중소기업": False, "구분": "중소기업 아님"}
    assert F(year=2024, industry_code="G", revenue=1_100 * E, total_assets=300 * E, founded_on="2021-03-02")["결과"]["구분"] == "유예기간 중"


def test_domestic_affiliates_are_combined():
    # 본사 900억 + 60% 자회사 200억(전액) + 40% 자회사 100억(40억) = 1,140억 > 1,000억(2024)
    r = F(year=2024, industry_code="C20", revenue=900 * E, total_assets=600 * E, domestic_affiliates=[{"revenue": 200 * E, "ownership": 0.6}, {"revenue": 100 * E, "ownership": 0.4}])
    assert r["계산"]["관계기업_합산_매출액"] == 1_140 * E and r["결과"]["구분"] == "유예기간 중"
    assert "error" in F(year=2024, industry_code="C20", revenue=900 * E, total_assets=600 * E, domestic_affiliates=[{"revenue": 200 * E, "ownership": 0.2}])


def test_independence_and_assets():
    assert F(year=2025, industry_code="C20", revenue=500 * E, total_assets=250 * E, large_corp_owner=True)["결과"] == {"중소기업": False, "구분": "중소기업 아님"}
    assert F(year=2025, industry_code="C20", revenue=500 * E, total_assets=5_000 * E)["결과"]["구분"] == "유예기간 중"
    assert F(year=2025, industry_code="L", revenue=10 * E, total_assets=50 * E, excluded_business=True)["결과"]["중소기업"] is False


def test_input_errors():
    assert "error" in F(year=2017, industry_code="C20", revenue=1, total_assets=1)
    assert "error" in F(year=2025, industry_code="화장품", revenue=1, total_assets=1)
    assert F(year=2025, industry_code="n76", revenue=30 * E, total_assets=10 * E)["결과"]["구분"] == "소기업"      # 별표 3은 N 30억
