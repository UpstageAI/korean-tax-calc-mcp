"""0.40.0 employment_increase_credit 정답 테스트(2026-11-12, Claude 손계산).
근거: 조세특례제한법 제29조의7(2018~2025 각 연말 시행본), 시행령 제26조의7, 제127조제11항, 법률 제16009호 부칙 제13조."""
from korean_tax_calc_mcp import server as S

M = 1_000_000


def f(**k):
    return getattr(S.employment_increase_credit, "fn", S.employment_increase_credit)(**k)


H = lambda *rows: [{"year": y, "total": t, "youth": yo} for y, t, yo in rows]
STORY = H((2020, 0, 0), (2021, 8, 4), (2022, 20, 8), (2023, 45, 20), (2024, 80, 35), (2025, 110, 45))


def firsts(r):
    return {(x["최초_공제_과세연도"], x["차수"]): x for x in r["계산"]["최초_공제_과세연도별"]}


def test_sme_capital_area_with_carry_on_years():
    # 2021(창업, 직전 0): 청년등 4 × 1,100만 + 그 외 4 × 700만 = 7,200만
    assert f(year=2021, size="중소기업", headcounts=STORY)["결과"]["공제_대상_세액"] == 72 * M
    # 2022: 전체 +12, 청년등 4 × 1,100만 + 그 외 8 × 700만 = 1억, 2021년분 2차 7,200만 → 1.72억
    r = f(year=2022, size="중소기업", headcounts=STORY)
    assert r["결과"]["공제_대상_세액"] == 172 * M and firsts(r)[(2022, 1)]["공제액"] == 100 * M and firsts(r)[(2021, 2)]["공제액"] == 72 * M


def test_choice_against_integrated_credit_from_2023():
    # 2023년부터 통합고용을 고른 회사: 고용증대는 2021·2022년분만 → 2023년 1.72억(2022년분 2차 + 2021년분 3차), 2024년 1억(2022년분 3차), 2025년 0
    one = lambda y: f(year=y, size="중소기업", headcounts=STORY, only_first_years=[2021, 2022])["결과"]["공제_대상_세액"]
    assert [one(y) for y in (2023, 2024, 2025)] == [172 * M, 100 * M, 0]
    # 고르지 않으면 2023년 새 증가분도 계산하고 선택 안내: 청년등 12 × 1,100만 + 그 외 13 × 700만 = 2.23억
    r = f(year=2023, size="중소기업", headcounts=STORY)
    assert firsts(r)[(2023, 1)]["공제액"] == 223 * M and r["결과"]["공제_대상_세액"] == 395 * M and any("제127조제11항" in p for p in r["판단"])


def test_amounts_by_size_region_and_year():
    hc = lambda y: H((y - 1, 20, 8), (y, 30, 12))      # 전체 +10, 청년등 +4, 그 외 +6
    one = lambda y, size, out=False: f(year=y, size=size, headcounts=hc(y), outside_capital_area=out)["결과"]["공제_대상_세액"]
    assert one(2019, "중소기업") == 4 * 11 * M + 6 * 7 * M                       # 8,600만
    assert one(2019, "중소기업", True) == 4 * 12 * M + 6 * 7_700_000             # 수도권 밖 1,200만·770만
    assert one(2021, "중소기업", True) == one(2022, "중소기업", True) == 4 * 13 * M + 6 * 7_700_000      # 2021·2022 수도권 밖 청년등 1,300만
    assert one(2023, "중소기업", True) == 4 * 12 * M + 6 * 7_700_000             # 2023년은 다시 1,200만
    assert one(2022, "중견기업") == 4 * 8 * M + 6 * 4_500_000 and one(2022, "중견기업", True) == 4 * 9 * M + 6 * 4_500_000
    assert one(2022, "일반") == 16 * M and one(2022, "일반", True) == 20 * M and one(2020, "일반", True) == 16 * M


def test_period_and_expiry():
    hc = H((2023, 20, 8), (2024, 30, 12), (2025, 30, 12), (2026, 30, 12))
    assert f(year=2026, size="중소기업", headcounts=hc)["결과"]["공제_대상_세액"] == 86 * M        # 2024년분 3차
    assert f(year=2025, size="일반", headcounts=hc)["결과"]["공제_대상_세액"] == 16 * M            # 2024년분 2차
    assert f(year=2026, size="일반", headcounts=hc)["결과"]["공제_대상_세액"] == 0
    # 2025년에 늘어난 인원은 대상이 아님
    r = f(year=2025, size="중소기업", headcounts=H((2024, 20, 8), (2025, 30, 12)))
    assert r["결과"]["공제_대상_세액"] == 0 and any("2025 과세연도부터" in p for p in r["판단"])


def test_follow_up_and_recapture():
    # 2021년분(청년등 +4, 그 외 +4). 2022년 전체 6·청년등 2: 전체 −2, 청년등 −2(≥ 전체 감소) → [min(2, 4) − 2] × 400만 + 2 × 1,100만 = 2,200만
    r = f(year=2022, size="중소기업", headcounts=H((2020, 0, 0), (2021, 8, 4), (2022, 6, 2)))
    assert r["결과"]["공제_대상_세액"] == 0 and firsts(r)[(2021, 2)]["상태"] == "중단" and r["결과"]["추가_납부세액"] == 22 * M
    # 공제받은 세액 500만이 한도, 나머지 1,700만은 이월액에서 차감
    r = f(year=2022, size="중소기업", headcounts=H((2020, 0, 0), (2021, 8, 4), (2022, 6, 2)), credits_taken=[{"first_year": 2021, "year": 2021, "amount": 5 * M}], carryforward_left=[{"first_year": 2021, "amount": 67 * M}])
    assert firsts(r)[(2021, 2)]["추가_납부"]["납부액"] == 5 * M and firsts(r)[(2021, 2)]["추가_납부"]["이월액_차감"] == 17 * M
    # 청년등만 감소(전체 유지): 8명 전부 청년등 외 금액 700만 = 5,600만, 추가 납부 min(2, 4) × 400만 = 800만
    r = f(year=2022, size="중소기업", headcounts=H((2020, 0, 0), (2021, 8, 4), (2022, 8, 2)))
    assert firsts(r)[(2021, 2)]["공제액"] == 56 * M and firsts(r)[(2021, 2)]["상태"] == "청년등 외 금액으로 공제" and r["결과"]["추가_납부세액"] == 8 * M
    assert any("조세특례제도과-215" in p for p in r["판단"])


def test_2020_grace_rule_is_refused():
    r = f(year=2021, size="중소기업", headcounts=H((2018, 10, 4), (2019, 20, 8), (2020, 15, 8), (2021, 20, 8)))
    assert "error" in r and "제29조의7제5항" in r["문제"][0]
    # 2020년에 줄지 않았으면 그대로 계산: 2019년분 3차(청년등 4 × 1,100만 + 그 외 6 × 700만 = 8,600만)
    r = f(year=2021, size="중소기업", headcounts=H((2018, 10, 4), (2019, 20, 8), (2020, 20, 8), (2021, 20, 8)))
    assert r["결과"]["공제_대상_세액"] == 86 * M


def test_notices():
    r = f(year=2022, size="중소기업", headcounts=STORY)
    assert "korean-tax-mcp" in r["주의"][0] and any("29세" in s for s in r["주의"]) and any("18F" in s for s in r["주의"])


def test_input_errors():
    assert "error" in f(year=2017, size="중소기업", headcounts=H((2016, 1, 0), (2017, 2, 0)))
    assert "error" in f(year=2022, size="중소기업", headcounts=H((2022, 20, 8)))
    assert "error" in f(year=2022, size="중소기업", headcounts=H((2021, 8, 9), (2022, 20, 8)))
    assert "error" in f(year=2022, size="소기업", headcounts=STORY)
    assert "error" in f(year=2023, size="중소기업", headcounts=STORY, only_first_years="2021")
