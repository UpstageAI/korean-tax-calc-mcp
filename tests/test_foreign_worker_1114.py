"""외국인근로자 단일세율(조특법 제18조의2)·외국인기술자 감면(조특법 제18조) — 원문에서 손으로 계산한 값.

대조한 시행본(법제처 DRF eflaw, 2026-11-14 조회):
  조세특례제한법 연말 시행본 2016.10.04.·2017.09.12.·2018.12.24.·2019.12.31.·2020.12.10.·2021.12.30.·
    2022.12.08.·2023.12.21.·2024.07.10.·2025.11.11.·2026.09.18.
  부칙: 법률 제12173호 제59조, 제12853호 제8조·제61조, 제14390호 제10조, 제16009호 제7조·제40조,
    제16835호 제11조, 제19199호 제9조·제10조, 제19936호 제6조
  조세특례제한법 시행령 제16조·제16조의2(2016.12.01.~2026.09.18. 시행본), 지방세특례제한법 제106조의2(2026.06.02. 시행본),
  소득세법 제59조의5(2026.01.01. 시행본), 기획재정부 소득세제과-135(2023.2.21.)
"""
import pytest

from korean_tax_calc_mcp import server as S
from korean_tax_calc_mcp.engine import calc_foreign_worker as FW


def flat(**k):
    base = dict(first_work_date="2015-03-01", taxable_pay=50_000_000)
    base.update(k)
    return S.foreign_worker_flat_tax(**base)


def expert(**k):
    base = dict(category="연구원", category_requirements_met=True)
    base.update(k)
    return S.foreign_expert_income_reduction(**base)


# ── 제18조의2 ──────────────────────────────────────────────────────────────
def test_rate_17_in_2016_19_from_2017():
    # 2016 시행본 17%, 법률 제14390호 19%(부칙 제10조제3항: 2017.1.1. 전 발생 소득 17%)
    a = flat(year=2016, nontaxable_pay=2_000_000)["결과"]
    b = flat(year=2017, nontaxable_pay=2_000_000)["결과"]
    assert a["단일세율"]["과세대상근로소득"] == 52_000_000      # 비과세도 과세대상(제18조의2제3항)
    assert a["단일세율"]["소득세"] == 8_840_000 and a["단일세율"]["지방소득세"] == 884_000
    assert b["단일세율"]["소득세"] == 9_880_000 and b["단일세율"]["지방소득세"] == 988_000


def test_five_year_end_then_twenty_year_revival():
    # 최초 근로 2015.3.1.: 5년 이내 끝나는 과세기간 = 2019 귀속까지
    assert flat(year=2019)["결과"]["단일세율_적용가능"] is True
    r20 = flat(year=2020)["결과"]
    assert r20["단일세율_적용가능"] is False and r20["더_적은_쪽"].startswith("누진세율")
    assert flat(year=2022)["결과"]["단일세율_적용가능"] is False
    # 법률 제19199호 부칙 제10조: 2023.1.1. 현재 20년이 지나지 않았으면 다시 적용, 20년 → 2034 귀속까지
    r23 = flat(year=2023)["결과"]
    assert r23["단일세율_적용가능"] is True and r23["적용_마지막_귀속연도"] == 2034


def test_pre2014_worker():
    kw = dict(first_work_date="2010-01-01")
    r16 = flat(year=2016, **kw)["결과"]
    assert r16["단일세율_적용가능"] is True and r16["단일세율"]["세율"] == 17
    r18 = flat(year=2018, **kw)["결과"]
    assert r18["단일세율_적용가능"] is True and r18["단일세율"]["세율"] == 19     # 부칙 제14390호 제10조①
    assert flat(year=2019, **kw)["결과"]["단일세율_적용가능"] is False          # 2018.12.31.까지만
    r23 = flat(year=2023, **kw)["결과"]
    assert r23["단일세율_적용가능"] is True and r23["기산일"] == "2014-01-01"      # 기획재정부 소득세제과-135
    assert r23["적용_마지막_귀속연도"] == 2033
    r23b = flat(year=2023, reentry_date="2016-07-01", **kw)["결과"]
    assert r23b["기산일"] == "2016-07-01" and r23b["적용_마지막_귀속연도"] == 2035


def test_housing_benefit_kept_nontaxable_from_2024():
    # 법률 제19936호 제18조의2제3항 괄호·부칙 제6조, 시행령 제16조의2제5항
    kw = dict(first_work_date="2021-01-01", taxable_pay=60_000_000, nontaxable_pay=4_000_000, housing_benefit_nontaxable=3_000_000)
    a = S.foreign_worker_flat_tax(year=2023, **kw)["결과"]["단일세율"]
    b = S.foreign_worker_flat_tax(year=2024, **kw)["결과"]["단일세율"]
    assert a["과세대상근로소득"] == 64_000_000 and a["소득세"] == 12_160_000
    assert b["과세대상근로소득"] == 61_000_000 and b["소득세"] == 11_590_000 and b["지방소득세"] == 1_159_000


def test_exclusions():
    assert flat(year=2025, related_party_employer=True)["결과"]["단일세율_적용가능"] is False
    assert flat(year=2025, first_work_date="2022-01-01", related_party_employer=True, fie_excepted=True)["결과"]["단일세율_적용가능"] is True
    assert flat(year=2025, daily_worker=True)["결과"]["단일세율_적용가능"] is False
    assert flat(year=2025, korean_national=True)["결과"]["단일세율_적용가능"] is False


def test_progressive_matches_wage_income_tax_and_lower_side():
    r = flat(year=2025, first_work_date="2022-01-01", taxable_pay=100_000_000)["결과"]
    w = S.wage_income_tax(gross_pay=100_000_000, year=2025)["결과"]
    assert r["누진세율"]["결정세액"] == w["결정세액(참고)"] == 13_710_000
    # 단일 19,000,000 + 1,900,000 > 누진 13,710,000 + 1,371,000
    assert r["단일세율"]["합계"] == 20_900_000 and r["더_적은_쪽"] == "누진세율"
    hi = flat(year=2025, first_work_date="2022-01-01", taxable_pay=1_000_000_000)["결과"]
    assert hi["더_적은_쪽"] == "단일세율"
    assert hi["차이(누진−단일, 지방소득세 포함)"] == hi["누진세율"]["합계"] - hi["단일세율"]["합계"] > 0


def test_withholding_monthly():
    assert flat(year=2016, monthly_pay=5_000_000)["결과"]["월_원천징수_단일세율"] == 850_000
    assert flat(year=2017, monthly_pay=5_000_000)["결과"]["월_원천징수_단일세율"] == 950_000


def test_flat_tool_has_citations_and_limits():
    r = flat(year=2024)
    assert "제18조의2제2항" in r["근거"] and "지방세특례제한법 제106조의2" in r["근거"]
    assert any("확인 필요" in x for x in r["한계"])


def test_input_errors():
    assert "error" in flat(year=2016, first_work_date="2017-01-01")
    assert "error" in flat(year=2025, nontaxable_pay=1, housing_benefit_nontaxable=2)


# ── 제18조 ────────────────────────────────────────────────────────────────
def test_two_year_window_pre2019_partial_year():
    # 최초 근로 2018.6.15.: 2년이 되는 날(2020.6.14.)이 속하는 달 = 2020.6. → 2020 귀속 6개월
    r = expert(year=2020, first_work_date="2018-06-15", gross_pay=60_000_000)["결과"]
    assert r["그해_달수"]["50%달수"] == 6 and r["감면대상_총급여_50%"] == 30_000_000
    # 근로소득공제 1,275만 → 근로소득금액 4,725만, 과세표준 4,575만, 2020 산출세액 72만 + 3,375만×15% = 5,782,500
    assert r["산출세액"] == 5_782_500
    assert r["감면세액"] == 1_445_625                          # 5,782,500 × 30/60 × 50%
    assert expert(year=2021, first_work_date="2018-06-15", gross_pay=60_000_000)["결과"]["감면세액"] == 0


def test_19199_addendum9_boundary():
    # 2023.1.1. 현재 최초 근로일부터 5년이 지나지 아니한 사람만(부칙 제9조): 2018.1.1. 시작 → 2022.12.31.로 5년 끝
    a = expert(year=2023, first_work_date="2018-01-01", gross_pay=60_000_000)["결과"]
    b = expert(year=2023, first_work_date="2018-01-02", gross_pay=60_000_000)["결과"]
    assert a["감면세액"] == 0
    assert b["그해_달수"]["50%달수"] == 12 and b["감면세액"] == b["산출세액"] // 2


def test_ten_year_window_from_2019_start():
    w = FW.expert_windows(FW.date(2019, 3, 10))["구간"]
    assert len(w) == 1 and w[0][1] == 2029 * 12 + 2       # 2029년 3월까지
    r = expert(year=2026, first_work_date="2019-03-10", gross_pay=50_000_000)["결과"]
    assert r["그해_달수"]["50%달수"] == 12


def test_two_year_end_month_2016_start():
    r = expert(year=2018, first_work_date="2016-05-20", gross_pay=36_000_000)["결과"]
    assert r["그해_달수"]["50%달수"] == 5 and r["감면대상_총급여_50%"] == 15_000_000


def test_sobujang_70_then_50():
    # 2020.3.10. 최초 근로: 70% ~2023.3.(3년이 되는 날 2023.3.9.), 50% 2023.4.~2025.3.
    r = expert(year=2023, first_work_date="2020-03-10", gross_pay=120_000_000, sobujang=True)["결과"]
    assert r["그해_달수"] == {"근무달수": 12, "70%달수": 3, "50%달수": 9}
    assert r["감면대상_총급여_70%"] == 30_000_000 and r["감면대상_총급여_50%"] == 90_000_000
    # 근로소득공제 1,515만 → 근로소득금액 10,485만 → 과세표준 10,335만, 2023 산출세액 1,536만 + 1,535만×35% = 20,732,500
    assert r["산출세액"] == 20_732_500
    assert r["감면세액"] == 11_402_875                         # 20,732,500 × (0.7×3천만 + 0.5×9천만) / 1억2천만
    r25 = expert(year=2025, first_work_date="2020-03-10", gross_pay=120_000_000, sobujang=True)["결과"]
    assert r25["그해_달수"]["70%달수"] == 0 and r25["그해_달수"]["50%달수"] == 3
    r26 = expert(year=2026, first_work_date="2020-03-10", gross_pay=120_000_000, sobujang=True)["결과"]
    assert r26["감면세액"] == 0
    # 단서 기한 밖(2023 시작)이면 본문 50%
    r2 = expert(year=2024, first_work_date="2023-02-01", gross_pay=120_000_000, sobujang=True)["결과"]
    assert r2["그해_달수"]["70%달수"] == 0 and r2["그해_달수"]["50%달수"] == 12


def test_flat_elected_blocks_reduction_and_categories_by_year():
    r = expert(year=2024, first_work_date="2022-01-01", gross_pay=60_000_000, flat_rate_elected=True)["결과"]
    assert r["감면_적용가능"] is False and r["감면세액"] == 0
    a = expert(year=2024, first_work_date="2024-01-01", gross_pay=60_000_000, category="우수해외인재")["결과"]
    b = expert(year=2025, first_work_date="2024-01-01", gross_pay=60_000_000, category="우수해외인재")["결과"]
    assert a["감면_적용가능"] is False and b["감면_적용가능"] is True
    assert expert(year=2021, first_work_date="2020-01-01", gross_pay=60_000_000, related_party_employer=True)["결과"]["감면_적용가능"] is False
    assert expert(year=2020, first_work_date="2020-01-01", gross_pay=60_000_000, related_party_employer=True)["결과"]["감면_적용가능"] is True


def test_given_tax_with_other_income():
    # 소득세법 제59조의5: 산출세액 × 감면대상 근로소득금액 / 종합소득금액 × 50%
    r = expert(year=2025, first_work_date="2022-01-01", gross_pay=60_000_000, computed_tax=6_000_000,
               other_income_amount=12_750_000)["결과"]
    # 근로소득금액 = 6천만 − 1,275만 = 4,725만, 종합소득금액 6천만 → 6,000,000 × 4,725/6,000 × 50% = 2,362,500
    assert r["근로소득금액"] == 47_250_000 and r["감면세액"] == 2_362_500


def test_expert_pre2015_rejected():
    assert "error" in expert(year=2016, first_work_date="2014-12-31", gross_pay=10_000_000)


def test_docstrings_first_line_english():
    import asyncio
    tools = {t.name: t for t in asyncio.run(S.mcp.list_tools())}
    for n in ("foreign_worker_flat_tax", "foreign_expert_income_reduction"):
        d = tools[n].description
        first = d.splitlines()[0]
        assert first.isascii() is False and first[0].isascii() and "(" in first
        assert "언제:" in d and "입력:" in d
