"""branch_profits_tax · emigration_exit_tax — 손 계산 정답(2026-11-14, Claude 작성). 외부 호출 없음.
대조 시행본(법제처 DRF 연혁본):
  법인세법 제96조 2016(20160125)~2026(20260701) 연말 시행본, 제98조제1항 2016(20160125)·2018(20181101)·2019(20190101)·2026(20260701) 시행본,
  법인세법 시행령 제134조 2016(20161129)~2026(20261001) 연말 시행본,
  소득세법 제118조의9~제118조의18 2017(20170701)·2018(20180921)~2026(20260701) 연말 시행본과 부칙(2016.12.20. 제14389호, 2018.12.31. 제16104호, 2025.12.23. 제21221호),
  소득세법 시행령 제178조의8~제178조의12 2018(20181023)·2020(20201210)·2026(20261001) 시행본."""
import asyncio

from korean_tax_calc_mcp import server as S

M = 1_000_000
BASE = dict(pe_income=1000 * M, corporate_tax=170 * M, credits_reductions=10 * M, penalties_additional=5 * M,
            local_income_tax=16_500_000, capital_begin=2000 * M, capital_end=2100 * M, treaty_allows_branch_tax=True)


def bp(year, **kw):
    a = dict(BASE)
    a.update(kw)
    return S.branch_profits_tax(year, **a)


def test_branch_basic_treaty_rate():
    # 1호 = 170M − 10M + 5M = 165M, A = 1000M − 165M − 16.5M = 818.5M, 재투자(자본금상당액증가액) 100M → 718.5M × 5%
    r = bp(2025, treaty_branch_rate=0.05)
    assert r["결과"]["과세대상 금액"] == 718_500_000 and r["결과"]["지점세"] == 35_925_000
    assert r["계산"]["제2항제3호 재투자 등 공제 합계"] == 100 * M


def test_branch_statutory_rate_and_year_labels():
    # 조약 세율 생략 → 제98조 인용 세율 100분의 20. 인용 호: 2018 시행본까지 제3호, 2019부터 제2호
    r18, r19 = bp(2018), bp(2019)
    assert r18["결과"]["지점세"] == r19["결과"]["지점세"] == 143_700_000
    assert "제98조제1항제3호" in r18["결과"]["세율 근거"] and "제98조제1항제2호" in r19["결과"]["세율 근거"]
    # 과소자본 인용: 2020 시행본까지 국조법 제14조, 2021부터 제22조
    assert "제14조" in bp(2020)["연도별"]["과소자본 손금불산입"] and "제22조" in bp(2021)["연도별"]["과소자본 손금불산입"]


def test_branch_no_treaty_or_proviso():
    assert bp(2024, treaty_allows_branch_tax=False)["결과"]["지점세"] == 0
    r = bp(2024, residence_country_taxes_korean_branches=False)
    assert r["결과"]["지점세"] == 0 and "단서" in r["근거"]


def test_branch_capital_decrease_added_up_to_untaxed():
    # 감소액 100M, 직전 미과세누적유보소득 60M → 60M 합산: 818.5M + 60M = 878.5M × 5%
    r = bp(2024, capital_begin=2100 * M, capital_end=2000 * M, untaxed_retained_prior=60 * M, treaty_branch_rate=0.05)
    assert r["결과"]["과세대상 금액"] == 878_500_000 and r["결과"]["지점세"] == 43_925_000
    r = bp(2024, capital_begin=2100 * M, capital_end=2000 * M, untaxed_retained_prior=200 * M, treaty_branch_rate=0.05)
    assert r["결과"]["과세대상 금액"] == 918_500_000


def test_branch_negative_untaxed_and_limit():
    r = bp(2024, untaxed_retained_prior=-50 * M, treaty_branch_rate=0.05)
    assert r["결과"]["과세대상 금액"] == 668_500_000
    # 한도: A 178M − 증가액 150M = 28M까지만
    r = S.branch_profits_tax(2024, pe_income=200 * M, corporate_tax=20 * M, local_income_tax=2 * M, capital_begin=0, capital_end=150 * M,
                             untaxed_retained_prior=-50 * M, treaty_allows_branch_tax=True, treaty_branch_rate=0.05)
    assert r["계산"]["미과세누적유보소득(음수) 공제액"] == 28 * M and r["결과"]["과세대상 금액"] == 0


def test_branch_loss_year():
    # 결손 100M, 감소액 150M → 초과 50M, 미과세누적유보소득 30M 한도 → 30M × 10%
    r = S.branch_profits_tax(2023, pe_income=-100 * M, corporate_tax=0, capital_begin=500 * M, capital_end=350 * M,
                             untaxed_retained_prior=30 * M, treaty_allows_branch_tax=True, treaty_branch_rate=0.10)
    assert r["결과"]["과세대상 금액"] == 30 * M and r["결과"]["지점세"] == 3 * M
    r = S.branch_profits_tax(2023, pe_income=-200 * M, corporate_tax=0, capital_begin=500 * M, capital_end=350 * M,
                             untaxed_retained_prior=30 * M, treaty_allows_branch_tax=True, treaty_branch_rate=0.10)
    assert r["결과"]["지점세"] == 0


def test_branch_remittance_basis():
    # 송금 500M, 직전 과세대상 400M → 400M + 초과 100M 중 미과세누적유보소득 60M = 460M × 5%
    r = bp(2022, treaty_basis="송금액", remitted_profit=500 * M, prior_year_taxable=400 * M, untaxed_retained_prior=60 * M, treaty_branch_rate=0.05)
    assert r["결과"]["과세대상 금액"] == 460 * M and r["결과"]["지점세"] == 23 * M
    assert "error" in bp(2022, treaty_basis="송금액")


def test_branch_pe_closed():
    # 의제사업연도: 종료일 자본금상당액 0 → 감소액 300M, 미과세누적유보소득 200M 합산. A = 100M − 9M − 0.9M = 90.1M
    r = S.branch_profits_tax(2024, pe_income=100 * M, corporate_tax=9 * M, local_income_tax=900_000, capital_begin=300 * M, capital_end=300 * M,
                             untaxed_retained_prior=200 * M, treaty_allows_branch_tax=True, treaty_branch_rate=0.05, pe_closed=True)
    assert r["결과"]["과세대상 금액"] == 290_100_000 and r["결과"]["지점세"] == 14_505_000


def H(mv, cost, sme=False):
    return [{"name": "A", "market_value": mv, "acquisition_cost": cost, "sme": sme}]


def ex(day, holdings, **kw):
    a = dict(residence_years_in_10=8, major_shareholder=True)
    a.update(kw)
    return S.emigration_exit_tax(day, holdings=holdings, **a)


def test_exit_rate_boundary_2018_2019():
    # 양도소득금액 600M − 250만 = 597.5M. 2018 출국 20% / 2019 출국 6천만 + 297.5M × 25%
    assert ex("2018-12-31", H(1000 * M, 400 * M))["결과"]["산출세액"] == 119_500_000
    assert ex("2019-01-01", H(1000 * M, 400 * M))["결과"]["산출세액"] == 134_375_000


def test_exit_sme_2019_vs_2020():
    assert ex("2019-12-31", H(1000 * M, 400 * M, sme=True))["결과"]["산출세액"] == 119_500_000
    assert ex("2020-01-01", H(1000 * M, 400 * M, sme=True))["결과"]["산출세액"] == 134_375_000


def test_exit_3eok_boundary():
    assert ex("2023-05-01", H(302_500_000, 0))["결과"]["산출세액"] == 60_000_000
    assert ex("2023-05-01", H(302_500_004, 0))["결과"]["산출세액"] == 60_000_001


def test_exit_requirements():
    assert ex("2023-05-01", H(1000 * M, 0), residence_years_in_10=4.9)["결과"]["납세의무"] == "없음"
    assert ex("2023-05-01", H(1000 * M, 0), residence_years_in_10=5)["결과"]["납세의무"] == "있음"
    assert ex("2023-05-01", H(1000 * M, 0), major_shareholder=False)["결과"]["납세의무"] == "없음"
    assert ex("2017-12-31", H(1000 * M, 0))["결과"]["납세의무"] == "없음"
    assert ex("2018-01-01", H(1000 * M, 0))["결과"]["납세의무"] == "있음"
    assert "error" in ex("2027-01-01", H(1000 * M, 0))


def test_exit_unreported_penalty():
    r = ex("2019-01-01", H(1000 * M, 400 * M), holdings_reported=False, unreported_face_value=50 * M)
    assert r["결과"]["보유현황 미신고 가산"] == 1 * M and r["결과"]["납부할 세액(감면·공제 전)"] == 135_375_000
    r = ex("2018-12-31", H(1000 * M, 400 * M), holdings_reported=False, unreported_face_value=50 * M)
    assert r["결과"]["보유현황 미신고 가산"] == 0


def test_exit_deadlines():
    r = ex("2024-01-31", H(1000 * M, 400 * M))
    assert "2024-04-30" in r["신고·납부"]["과세표준 신고·납부"] and "2024-01-30" in r["신고·납부"]["납세관리인·보유현황 신고"]


def test_exit_2019_mixed_sme():
    # 일반 100M − 250만 = 97.5M(20%) + 중소 50M(20%) = 29.5M
    hs = [{"market_value": 300 * M, "acquisition_cost": 200 * M}, {"market_value": 80 * M, "acquisition_cost": 30 * M, "sme": True}]
    assert ex("2019-07-01", hs)["결과"]["산출세액"] == 29_500_000
    # 일반 손실 20M은 중소 50M과 통산 → 30M − 250만 = 27.5M × 20%
    hs = [{"market_value": 180 * M, "acquisition_cost": 200 * M}, {"market_value": 80 * M, "acquisition_cost": 30 * M, "sme": True}]
    assert ex("2019-07-01", hs)["결과"]["산출세액"] == 5_500_000


def test_descriptions_first_line_english():
    tools = {t.name: t for t in asyncio.run(S.mcp.list_tools())}
    for n in ("branch_profits_tax", "emigration_exit_tax"):
        d = tools[n].description
        first = d.strip().splitlines()[0]
        assert first[0].isascii() and "(" in first and "언제:" in d and "입력:" in d
