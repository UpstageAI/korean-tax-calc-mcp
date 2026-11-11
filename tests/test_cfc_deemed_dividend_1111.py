"""0.31.0 정답 테스트(수정 금지, Claude 작성) — cfc_deemed_dividend(특정외국법인 유보소득 배당간주액).
근거: 국제조세조정에 관한 법률 제27조~제31조, 시행령 제61조·제62조·제64조~제67조, 법인세법 제55조(최고세율 연도표). 조문은 2026 시행본(korean-tax-mcp)으로 확인.
손계산 사례는 가상 법인(홍콩 지주회사 등)."""
from _helpers import call as c

M = 1_000_000
RE = {"unappropriated_retained_earnings": 3_000 * M, "dividends": 500 * M, "mandatory_reserves": 100 * M,
      "previously_taxed_undistributed": 400 * M}          # 3,000 − 500 − 100 − 400 − 200(영 제66조①7호) = 1,800
BASE = {"year": 2026, "pretax_incomes": [1_000 * M, 800 * M, 1_200 * M], "taxes_paid": [100 * M, 80 * M, 120 * M],
        "ownership_chains": [[1.0]], "distributable": RE, "fy_end": "2026-12-31"}


def run(**kw):
    return c("cfc_deemed_dividend", {**BASE, **kw})


# ── 전부 적용 ───────────────────────────────────────────────────────────────
def test_full_inclusion_paper_company():
    r = run()
    assert "error" not in r, r
    g = r["결과"]
    assert g["특정외국법인_해당"] is True and g["배당간주_적용"] is True and g["적용방식"] == "전부"
    assert g["실제발생소득_연평균"] == 1_000 * M and g["실제부담세액_연평균"] == 100 * M
    assert g["기준세율_만분율"] == 1750 and g["실제부담세율_만분율"] == 1000
    assert g["배당가능_유보소득"] == 1_800 * M
    assert g["주식보유비율_만분율"] == 10000
    assert g["배당간주금액"] == 1_800 * M
    assert g["익금귀속_기준일"] == "2027-03-01" and g["익금귀속_과세연도"] == 2027      # 법 제31조: 종료일 다음 날부터 60일이 되는 날
    assert g["적용제외_사유"] is None
    assert "제27조" in r["근거"] and "제30조" in r["근거"] and "제66조" in r["근거"]
    assert isinstance(r["단계별_계산"], list) and len(r["단계별_계산"]) >= 3
    assert any("제67조" in s for s in r["주의"]) and any("제32조" in s for s in r["주의"])


def test_fy_end_june_60th_day():
    g = run(fy_end="2026-06-30")["결과"]
    assert g["익금귀속_기준일"] == "2026-08-29" and g["익금귀속_과세연도"] == 2026


# ── 저세율 기준: 법인세법 제55조 최고세율 × 70% 연도표 ─────────────────────────────
def test_threshold_2026_is_17_5_percent_inclusive():
    assert run(pretax_incomes=[1_000 * M], taxes_paid=[175 * M])["결과"]["특정외국법인_해당"] is True     # 이하
    r = run(pretax_incomes=[1_000 * M], taxes_paid=[175 * M + 1])
    assert r["결과"]["특정외국법인_해당"] is False and r["결과"]["배당간주금액"] == 0
    assert "실제부담세액" in r["결과"]["적용제외_사유"] and r["결과"]["적용방식"] == "없음"


def test_threshold_2023_2025_is_16_8_percent():
    for y in (2023, 2024, 2025):
        g = run(year=y, pretax_incomes=[1_000 * M], taxes_paid=[168 * M])["결과"]
        assert g["기준세율_만분율"] == 1680 and g["특정외국법인_해당"] is True
        assert run(year=y, pretax_incomes=[1_000 * M], taxes_paid=[170 * M])["결과"]["특정외국법인_해당"] is False


def test_threshold_2022_is_17_5_and_before_2022_is_15_percent():
    assert run(year=2022, pretax_incomes=[1_000 * M], taxes_paid=[175 * M])["결과"]["기준세율_만분율"] == 1750
    g = run(year=2021, pretax_incomes=[1_000 * M], taxes_paid=[150 * M])["결과"]
    assert g["기준세율_만분율"] == 1500 and g["특정외국법인_해당"] is True
    assert run(year=2021, pretax_incomes=[1_000 * M], taxes_paid=[151 * M])["결과"]["특정외국법인_해당"] is False
    assert run(year=2016, pretax_incomes=[1_000 * M], taxes_paid=[150 * M])["결과"]["기준세율_만분율"] == 1500


def test_loss_year_counts_as_zero_income():
    g = run(pretax_incomes=[-500 * M, 300 * M, 600 * M], taxes_paid=[0, 30 * M, 60 * M])["결과"]
    assert g["실제발생소득_연평균"] == 300 * M and g["실제부담세액_연평균"] == 30 * M      # (0+300+600)/3, 영 제61조①
    assert g["특정외국법인_해당"] is True and g["실제부담세율_만분율"] == 1000


# ── 적용 배제 ───────────────────────────────────────────────────────────────
def test_small_income_exclusion_200m_inclusive():
    r = run(pretax_incomes=[200 * M], taxes_paid=[0])
    assert r["결과"]["특정외국법인_해당"] is True and r["결과"]["배당간주_적용"] is False
    assert "2억원" in r["결과"]["적용제외_사유"] and r["결과"]["배당간주금액"] == 0
    assert run(pretax_incomes=[200 * M + 3], taxes_paid=[0])["결과"]["배당간주_적용"] is True


def test_small_income_exclusion_prorated_for_short_year():
    assert run(pretax_incomes=[100 * M], taxes_paid=[0], months=6)["결과"]["배당간주_적용"] is False      # 2억 × 6/12
    g = run(pretax_incomes=[150 * M], taxes_paid=[0], months=6)["결과"]
    assert g["배당간주_적용"] is True
    assert g["배당가능_유보소득"] == 1_900 * M          # 3,000 − 500 − 100 − 400 − 100(2억×6/12)


def test_holding_company_exemption():
    r = run(holding_company_exemption=True)
    assert r["결과"]["배당간주_적용"] is False and "제28조3호" in r["결과"]["적용제외_사유"]
    assert any("호출자" in s for s in r["주의"])


def test_no_related_party_and_below_10_percent():
    r = run(related_party=False)
    assert r["결과"]["특정외국법인_해당"] is False and "특수관계" in r["결과"]["적용제외_사유"]
    r2 = run(ownership_chains=[[0.08]])
    assert r2["결과"]["특정외국법인_해당"] is False and "10퍼센트" in r2["결과"]["적용제외_사유"]
    g3 = run(ownership_chains=[[0.08]], ownership_with_related_ratio=0.12)["결과"]      # 10% 판정은 특수관계인 직접 보유 포함(법 제27조②)
    assert g3["배당간주_적용"] is True and g3["배당간주금액"] == 144 * M                 # 1,800 × 8%
    assert run(ownership_chains=[[0.1]])["결과"]["배당간주금액"] == 180 * M              # 정확히 10%는 대상


# ── 주식 보유비율(영 제67조①) ─────────────────────────────────────────────────
def test_indirect_ownership_chains_multiply_then_add():
    g = run(ownership_chains=[[0.6, 0.5], [0.1]])["결과"]
    assert g["주식보유비율_만분율"] == 4000 and g["배당간주금액"] == 720 * M            # (0.6×0.5 + 0.1) × 1,800


def test_fraction_arithmetic_no_float_error():
    g = run(ownership_chains=[[0.1], [0.2]], distributable={"unappropriated_retained_earnings": 200 * M + 1_000_000_007})["결과"]
    assert g["주식보유비율_만분율"] == 3000 and g["배당간주금액"] == 300_000_002         # 1,000,000,007 × 3/10 = 300,000,002.1 → 절사


# ── 고정 시설을 둔 법인(법 제28조2호)과 예외적 적용(제29조) ───────────────────────────
def test_active_business_excluded():
    r = run(fixed_facility_active_business=True)
    assert r["결과"]["배당간주_적용"] is False and "제28조2호" in r["결과"]["적용제외_사유"]


def test_active_business_but_listed_industry_with_related_parties():
    g = run(fixed_facility_active_business=True, listed_industry="도매업", listed_industry_share=0.8, listed_industry_related_share=0.6)["결과"]
    assert g["적용방식"] == "전부" and g["배당간주금액"] == 1_800 * M                    # 법 제29조①1호
    g2 = run(fixed_facility_active_business=True, listed_industry="도매업", listed_industry_share=0.8, listed_industry_related_share=0.5)["결과"]
    assert g2["배당간주_적용"] is False                                                # 50% "초과"가 아님


def test_wholesale_same_country_unrelated_sales_exception():
    g = run(fixed_facility_active_business=True, listed_industry="도매업", listed_industry_share=0.8, listed_industry_related_share=0.6,
            same_country_unrelated_sales_share=0.55)["결과"]
    assert g["배당간주_적용"] is False                                                 # 법 제29조① 단서
    g2 = run(fixed_facility_active_business=True, listed_industry="부동산업", listed_industry_share=0.8, listed_industry_related_share=0.6,
             same_country_unrelated_sales_share=0.55)["결과"]
    assert g2["적용방식"] == "전부"                                                    # 단서는 도매업만


def test_passive_main_business():
    assert run(fixed_facility_active_business=True, passive_main_business=True)["결과"]["적용방식"] == "전부"      # 법 제29조①2호


def test_passive_income_partial_inclusion():
    g = run(fixed_facility_active_business=True, passive_income=80 * M, passive_excluded_dividends=20 * M, total_revenue=1_000 * M)["결과"]
    assert g["적용방식"] == "수동소득" and g["배당간주금액"] == 108 * M                  # 1,800 × 100% × (80−20)/1,000, 법 제30조②
    g2 = run(fixed_facility_active_business=True, passive_income=80 * M, passive_excluded_dividends=40 * M, total_revenue=1_000 * M)["결과"]
    assert g2["배당간주_적용"] is False                                                # (80−40)/1,000 = 4% ≤ 5%
    g3 = run(fixed_facility_active_business=True, passive_income=50 * M, total_revenue=1_000 * M)["결과"]
    assert g3["배당간주_적용"] is False                                                # 정확히 5%는 "초과" 아님


# ── 유보소득 ────────────────────────────────────────────────────────────────
def test_distributable_floor_zero_and_all_deductions():
    g = run(distributable={"unappropriated_retained_earnings": 300 * M, "dividends": 200 * M})["결과"]
    assert g["배당가능_유보소득"] == 0 and g["배당간주금액"] == 0 and g["배당간주_적용"] is True
    full = {"unappropriated_retained_earnings": 5_000 * M, "dividends": 500 * M, "bonuses_and_outflows": 100 * M, "mandatory_reserves": 200 * M,
            "previously_taxed_undistributed": 300 * M, "pre_cfc_earnings_undistributed": 400 * M, "unrealized_stock_gains": 500 * M}
    assert run(distributable=full)["결과"]["배당가능_유보소득"] == 2_800 * M             # 5,000 − 2,000 − 200


# ── 입력 오류 ───────────────────────────────────────────────────────────────
def test_input_errors():
    for bad in ({"year": 2015}, {"pretax_incomes": []}, {"pretax_incomes": [1, 2, 3, 4], "taxes_paid": [0, 0, 0, 0]},
                {"taxes_paid": [100 * M]}, {"taxes_paid": [-1, 0, 0]}, {"ownership_chains": []}, {"ownership_chains": [[1.2]]},
                {"ownership_chains": [[0.7], [0.5]]}, {"months": 13}, {"listed_industry": "제조업"},
                {"distributable": {"unappropriated_retained_earnings": -1}}, {"listed_industry": "도매업", "listed_industry_share": 1.5}):
        r = run(**bad)
        assert "error" in r, (bad, r)


def test_find_tool_surfaces_cfc():
    for q in ("특정외국법인 유보소득 배당간주 계산", "홍콩 지주회사 유보소득 배당 안 해도 과세"):
        names = [x["도구"] for x in c("find_tool", {"query": q, "n": 4})["결과"]["후보"]]
        assert "cfc_deemed_dividend" in names, (q, names)
