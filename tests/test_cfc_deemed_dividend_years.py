"""cfc_deemed_dividend 연도별 대조 테스트(Claude 작성, 2026-11-11).
2016~2026 각 연말 시행본을 korean-tax-mcp로 받아 대조한 결과: 조문 번호가 세 시기로 나뉘고(2016~2019 / 2020 / 2021~),
저세율 기준·수동소득 범위가 연도마다 다르다. 2억원·10%·50%·5%·60일은 전 기간 같다."""
import pytest
from _helpers import call as c

M = 1_000_000
RE = {"unappropriated_retained_earnings": 3_000 * M, "dividends": 500 * M, "mandatory_reserves": 100 * M, "previously_taxed_undistributed": 400 * M}
BASE = {"pretax_incomes": [1_000 * M, 800 * M, 1_200 * M], "taxes_paid": [100 * M, 80 * M, 120 * M],
        "ownership_chains": [[1.0]], "distributable": RE, "fy_end": "2026-12-31"}


def run(year, **kw):
    return c("cfc_deemed_dividend", {**BASE, "year": year, **kw})


@pytest.mark.parametrize("year,rate", [(2016, 1500), (2017, 1500), (2018, 1500), (2019, 1500), (2020, 1500), (2021, 1500),
                                       (2022, 1750), (2023, 1680), (2024, 1680), (2025, 1680), (2026, 1750)])
def test_threshold_every_supported_year(year, rate):
    g = run(year, pretax_incomes=[10_000 * M], taxes_paid=[rate * M])["결과"]          # 세액 = 소득 × 기준세율 → "이하"라 대상
    assert g["기준세율_만분율"] == rate and g["특정외국법인_해당"] is True
    assert run(year, pretax_incomes=[10_000 * M], taxes_paid=[rate * M + 1])["결과"]["특정외국법인_해당"] is False


@pytest.mark.parametrize("year", range(2016, 2027))
def test_same_amount_every_year_when_inputs_same(year):
    """2억원 차감·보유비율 산식은 전 기간 같다 — 연도만 바꿔도 금액은 1,800."""
    assert run(year)["결과"]["배당간주금액"] == 1_800 * M


def test_basis_article_numbers_by_era():
    for y in (2016, 2019):
        b = run(y)["근거"]
        assert "제17조" in b and "제18조의2" in b and "제36조의3" in b and "제27조" not in b
    b20 = run(2020)["근거"]
    assert "제17조의2" in b20 and "제17조의3" in b20 and "제27조" not in b20 and "제18조의2" not in b20
    b21 = run(2021)["근거"]
    assert "제27조" in b21 and "15퍼센트" in b21 and "제55조" not in b21
    for y in (2022, 2026):
        b = run(y)["근거"]
        assert "제27조" in b and "제55조" in b and "제17조" not in b


def test_exclusion_reason_cites_era_article():
    assert "제17조③" in run(2018, pretax_incomes=[200 * M], taxes_paid=[0])["결과"]["적용제외_사유"]
    assert "제17조의2" in run(2020, pretax_incomes=[200 * M], taxes_paid=[0])["결과"]["적용제외_사유"]
    assert "제28조1호" in run(2024, pretax_incomes=[200 * M], taxes_paid=[0])["결과"]["적용제외_사유"]
    assert "제18조의2" in run(2017, holding_company_exemption=True)["결과"]["적용제외_사유"]
    assert "제18조①" in run(2017, fixed_facility_active_business=True)["결과"]["적용제외_사유"]


def test_passive_income_scope_note_by_year():
    old = " ".join(run(2019)["주의"]); new = " ".join(run(2023)["주의"])
    assert "매각손익" in old and "2021년 이후" in old            # 2020년까지는 매각손익 제외
    assert "매각손익도 넣는다" in new
    assert "전부" in " ".join(run(2016)["주의"]) and "2017.2.7" in " ".join(run(2016)["주의"])
    assert "제61조②" in " ".join(run(2022)["주의"]) and "제61조②" not in " ".join(run(2021)["주의"])


def test_wholesale_exception_still_checks_passive_income():
    """도매업 단서로 빠져도 수동소득이 5%를 넘으면 그 부분은 적용(법 제29조② '제1항 각 호 외의 부분 단서에 따라 … 경우에도')."""
    kw = dict(fixed_facility_active_business=True, listed_industry="도매업", listed_industry_share=0.8, listed_industry_related_share=0.6,
              same_country_unrelated_sales_share=0.55)
    g = run(2026, **kw, passive_income=80 * M, passive_excluded_dividends=20 * M, total_revenue=1_000 * M)["결과"]
    assert g["적용방식"] == "수동소득" and g["배당간주금액"] == 108 * M
    assert run(2026, **kw)["결과"]["배당간주_적용"] is False


def test_fy_end_year_uses_60th_day_even_when_not_cfc():
    g = run(2026, related_party=False)["결과"]
    assert g["익금귀속_기준일"] == "2027-03-01" and g["익금귀속_과세연도"] == 2027


def test_validation_exact_and_rejects_bad_inputs():
    assert "error" not in run(2026, ownership_chains=[[0.1], [0.2], [0.7]])          # 합 정확히 1 — float 오차로 거절하면 안 됨
    for bad in ({"fy_end": "2026-13-01"}, {"distributable": {"unknown_key": 1}}, {"ownership_chains": [[0.5], []]}):
        assert "error" in run(2026, **bad), bad
    assert "error" in run(2027) and "error" in run(2015)
    step = " ".join(run(2026, ownership_chains=[[0.6, 0.5], [0.1]])["단계별_계산"])
    assert "60% × 50% + 10%" in step and "2/5" in step
