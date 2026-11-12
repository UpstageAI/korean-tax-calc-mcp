"""0.39.0 integrated_employment_credit 정답 테스트(2026-11-12, Claude 손계산).
근거: 조세특례제한법 제29조의8, 시행령 제26조의8(2023·2024·2025 연말·2026.11.12. 시행본), 시행령 제23조제10항·제11항·제13항."""
from korean_tax_calc_mcp import server as S

M = 1_000_000


def f(**k):
    return getattr(S.integrated_employment_credit, "fn", S.integrated_employment_credit)(**k)


H = lambda *rows: [{"year": y, "total": t, "youth": yo} for y, t, yo in rows]
STORY = H((2022, 20, 8), (2023, 45, 20), (2024, 80, 35), (2025, 110, 45))


def firsts(r):
    return {(x["최초_공제_과세연도"], x["차수"]): x for x in r["계산"]["최초_공제_과세연도별"]}


def test_sme_capital_area_three_years_with_carry_on_credits():
    # 2023: 전체 +25, 청년등 +12 × 1,450만 = 1.74억, 그 외 +13 × 850만 = 1.105억 → 2.845억
    r = f(year=2023, size="중소기업", headcounts=STORY)
    assert r["결과"]["공제_대상_세액"] == 284_500_000 and firsts(r)[(2023, 1)]["청년등_증가"] == 12 and firsts(r)[(2023, 1)]["청년등_외_증가"] == 13
    # 2024: 전체 +35, 청년등 +15 × 1,450만 = 2.175억, 그 외 +20 × 850만 = 1.7억 → 3.875억, 2023년분 2차 2.845억 → 6.72억
    r = f(year=2024, size="중소기업", headcounts=STORY)
    assert r["결과"]["기본공제"] == 672 * M and firsts(r)[(2024, 1)]["공제액"] == 387_500_000 and firsts(r)[(2023, 2)]["공제액"] == 284_500_000
    # 2025: 전체 +30, 청년등 +10 × 1,450만 = 1.45억, 그 외 +20 × 850만 = 1.7억 → 3.15억, 2024년분 2차 3.875억, 2023년분 3차 2.845억 → 9.87억
    r = f(year=2025, size="중소기업", headcounts=STORY)
    assert r["결과"]["기본공제"] == 987 * M and {k: v["공제액"] for k, v in firsts(r).items()} == {(2025, 1): 315 * M, (2024, 2): 387_500_000, (2023, 3): 284_500_000}


def test_amounts_by_size_and_region():
    hc = H((2023, 20, 8), (2024, 30, 12))      # 전체 +10, 청년등 +4, 그 외 +6
    assert f(year=2024, size="중소기업", headcounts=hc, outside_capital_area=True)["결과"]["기본공제"] == 4 * 15_500_000 + 6 * 9_500_000     # 1.19억
    assert f(year=2024, size="중견기업", headcounts=hc)["결과"]["기본공제"] == 4 * 8 * M + 6 * 4_500_000                                    # 5,900만
    assert f(year=2024, size="일반", headcounts=hc)["결과"]["기본공제"] == 16 * M                                                          # 청년등 외는 0


def test_carry_on_period_one_year_for_others_two_for_sme():
    hc = H((2022, 20, 8), (2023, 30, 12), (2024, 30, 12), (2025, 30, 12))
    assert f(year=2025, size="중소기업", headcounts=hc)["결과"]["기본공제"] == 4 * 14_500_000 + 6 * 8_500_000      # 2023년분 3차
    assert f(year=2024, size="일반", headcounts=hc)["결과"]["기본공제"] == 16 * M                                  # 2023년분 2차
    assert f(year=2025, size="일반", headcounts=hc)["결과"]["기본공제"] == 0                                       # 그 밖의 기업은 1년 더까지만


def test_increase_capped_by_total_increase():
    # 청년등 +5, 그 외 −2, 전체 +3 → 청년등 3명만
    assert f(year=2024, size="중소기업", headcounts=H((2023, 20, 8), (2024, 23, 13)))["결과"]["기본공제"] == 3 * 14_500_000
    # 청년등 −2, 그 외 +5, 전체 +3 → 그 외 3명만
    assert f(year=2024, size="중소기업", headcounts=H((2023, 20, 8), (2024, 23, 6)))["결과"]["기본공제"] == 3 * 8_500_000
    # 전체가 늘지 않으면 0
    r = f(year=2024, size="중소기업", headcounts=H((2023, 20, 8), (2024, 20, 12)))
    assert r["결과"]["기본공제"] == 0 and any("늘지 않아" in p for p in r["판단"])


def test_follow_up_stops_on_decrease():
    # 전체 감소: 2023년 45명 → 2024년 40명 → 2023년분 중단, 2024년 새 공제도 없음
    r = f(year=2024, size="중소기업", headcounts=H((2022, 20, 8), (2023, 45, 20), (2024, 40, 20)))
    assert r["결과"]["기본공제"] == 0 and firsts(r)[(2023, 2)]["상태"] == "중단" and any("추가 납부" in p for p in r["판단"])
    # 청년등만 감소: 2024년 전체 50·청년등 15 → 2023년분은 그 외 13명 × 850만 = 1.105억만, 2024년 새 공제는 그 외 min(10, 5) × 850만 = 4,250만
    r = f(year=2024, size="중소기업", headcounts=H((2022, 20, 8), (2023, 45, 20), (2024, 50, 15)))
    assert firsts(r)[(2023, 2)]["공제액"] == 110_500_000 and firsts(r)[(2023, 2)]["상태"] == "청년등 공제 중단"
    assert firsts(r)[(2024, 1)]["공제액"] == 42_500_000 and r["결과"]["기본공제"] == 153 * M and any("해석 확인 필요" in p for p in r["판단"])


def test_headcount_truncated_to_hundredths():
    # 10.559 → 10.55, 20.999 → 20.99: 전체 +10.44, 청년등 0 → 10.44 × 850만 = 88,740,000
    r = f(year=2024, size="중소기업", headcounts=[{"year": 2023, "total": 10.559, "youth": 0}, {"year": 2024, "total": 20.999, "youth": 0}])
    assert r["결과"]["기본공제"] == 88_740_000 and r["계산"]["상시근로자"][2023]["전체"] == 10.55


def test_conversion_and_childcare_return():
    hc = H((2023, 20, 8), (2024, 30, 12))
    r = f(year=2024, size="중소기업", headcounts=hc, converted=2, returned_from_leave=1)
    assert r["결과"]["정규직_전환_공제"] == 26 * M and r["결과"]["육아휴직_복귀_공제"] == 13 * M and r["결과"]["공제_대상_세액"] == 4 * 14_500_000 + 6 * 8_500_000 + 39 * M
    assert f(year=2024, size="중견기업", headcounts=hc, converted=2)["결과"]["정규직_전환_공제"] == 18 * M
    r = f(year=2024, size="중소기업", headcounts=H((2023, 20, 8), (2024, 19, 8)), returned_from_leave=1)      # 인원이 줄면 적용하지 않음
    assert r["결과"]["육아휴직_복귀_공제"] == 0 and any("줄어" in p for p in r["판단"])
    assert "error" in f(year=2025, size="중소기업", headcounts=H((2024, 20, 8), (2025, 30, 12)), converted=1)     # 2025년 전환분 규정 없음
    assert "error" in f(year=2024, size="일반", headcounts=hc, converted=1)


def test_out_of_scope_years_and_input_errors():
    assert "2026" in f(year=2026, size="중소기업", headcounts=H((2025, 20, 8), (2026, 30, 12)))["문제"][0]
    assert "제29조의7" in f(year=2022, size="중소기업", headcounts=H((2021, 20, 8), (2022, 30, 12)))["문제"][0]
    assert "error" in f(year=2024, size="중소기업", headcounts=H((2024, 30, 12)))                       # 직전 과세연도 없음
    assert "error" in f(year=2024, size="중소기업", headcounts=H((2023, 20, 25), (2024, 30, 12)))       # 청년등 > 전체
    assert "error" in f(year=2024, size="소기업", headcounts=H((2023, 20, 8), (2024, 30, 12)))
    assert "error" in f(year=2025, size="중소기업", headcounts=H((2022, 20, 8), (2023, 45, 20), (2025, 60, 25), (2024 - 10, 1, 1)))   # 2025·2024 가운데 2024 없음
