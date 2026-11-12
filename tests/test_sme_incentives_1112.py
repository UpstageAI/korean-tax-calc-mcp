"""0.36.0 startup_tax_reduction·sme_special_tax_reduction·loss_carryback_refund 정답 테스트(2026-11-12, Claude 손계산).
근거: 조세특례제한법 제6조(2016~2026 각 시행본)·시행령 제5조·시행규칙 제4조의2, 제7조·시행령 제6조, 제127조④, 제132조①, 법인세법 제72조·시행령 제110조.
세율: 2016~2017 2억 이하 10%·초과 20%, 2018~2022 같음(3천억 초과 구간 제외), 2023~ 2억 이하 9%·초과 19%."""
from korean_tax_calc_mcp import server as S
from korean_tax_calc_mcp.engine import calc_cit as CC

M = 1_000_000
OEM = {"domestic_maker": True, "own_planning": True, "own_name": True, "own_sale": True}


def _f(name):
    t = getattr(S, name)
    return getattr(t, "fn", t)


def ST(**k):
    return _f("startup_tax_reduction")(**k)


def SP(**k):
    return _f("sme_special_tax_reduction")(**k)


def CB(**k):
    return _f("loss_carryback_refund")(**k)


def test_youth_oem_in_overconcentration_zone_50_percent():
    # 2021.3.2. 과밀억제권역 청년창업, 위탁제조 4요건 충족, 2022 최초 소득 → 2023은 2번째. 과세표준 8억: 1,800만 + 6억×19% = 1.32억 → 50% 6,600만. 최저한세 5,600만 → 전액 적용
    r = ST(founded_on="2021-03-02", region="수도권과밀억제권역", year=2023, first_income_year=2022, tax=132 * M, taxable_base=800 * M, youth=True, industry="위탁제조", oem=OEM)
    assert r["결과"] == {"감면세액": 66 * M, "적용": "제1항(창업중소기업)", "감면율": 0.5, "납부할_세액_감면_후": 66 * M}
    assert r["계산"]["감면기간"] == "2022~2026 과세연도" and r["계산"]["감면_연차"] == 2 and r["계산"]["최저한세"] == 56 * M


def test_non_youth_in_overconcentration_zone_not_eligible():
    r = ST(founded_on="2021-03-02", region="수도권과밀억제권역", year=2023, first_income_year=2022, tax=132 * M, taxable_base=800 * M, industry="위탁제조", oem=OEM)
    assert r["결과"] == {"감면세액": 0, "적용": "대상 아님"} and any("제1항에 감면율이 없음" in p for p in r["판단"])


def test_youth_outside_zone_full_exemption_no_minimum_tax():
    r = ST(founded_on="2021-03-02", region="수도권", year=2023, first_income_year=2022, tax=132 * M, taxable_base=800 * M, youth=True)
    assert r["결과"]["감면세액"] == 132 * M and r["결과"]["감면율"] == 1.0 and "최저한세" not in r["계산"]


def test_industry_gates():
    base = dict(region="수도권 밖", year=2023, first_income_year=2022, tax=132 * M, taxable_base=800 * M)
    assert ST(founded_on="2021-03-02", industry="도매업", **base)["결과"]["적용"] == "대상 아님"
    assert ST(founded_on="2017-06-01", industry="통신판매업", **base)["결과"]["적용"] == "대상 아님"      # 2018.5.29. 전 창업
    assert ST(founded_on="2019-06-01", industry="통신판매업", **base)["결과"]["감면세액"] == 66 * M
    r = ST(founded_on="2021-03-02", industry="위탁제조", oem=dict(OEM, domestic_maker=False), **base)      # 해외 제조업체 위탁
    assert r["결과"]["적용"] == "대상 아님" and any("위탁제조 요건 미충족" in p for p in r["판단"])
    assert "error" in ST(founded_on="2021-03-02", industry="위탁제조", **base)                             # 요건 미입력
    assert "error" in ST(founded_on="2018-03-01", industry="제조업", **base)                               # 대조 못 한 기간


def test_period_and_five_year_rule():
    base = dict(region="수도권 밖", tax=40 * M, taxable_base=300 * M)
    assert ST(founded_on="2018-06-01", first_income_year=2019, year=2024, **base)["결과"]["적용"] == "감면기간 아님"
    r = ST(founded_on="2018-06-01", first_income_year=2025, year=2023, **base)     # 5년이 되는 2023년까지 소득 없음 → 2023부터
    assert r["계산"]["감면기간"] == "2023~2027 과세연도" and r["계산"]["감면_연차"] == 1


def test_2017_youth_75_then_50_and_minimum_tax_cut():
    # 2017.3.1. 과밀억제권역 밖 청년, 최초 소득 2018. 2020(3번째): 과세표준 3억 → 2,000만 + 1억×20% = 4,000만 × 75% = 3,000만. 최저한세 2,100만 → 1,900만만 적용
    r = ST(founded_on="2017-03-01", region="수도권 밖", year=2020, first_income_year=2018, tax=40 * M, taxable_base=300 * M, youth=True)
    assert r["계산"]["한도_전_감면세액"] == 30 * M and r["결과"]["감면세액"] == 19 * M and r["결과"]["감면율"] == 0.75
    r = ST(founded_on="2017-03-01", region="수도권 밖", year=2021, first_income_year=2018, tax=40 * M, taxable_base=300 * M, youth=True)
    assert r["결과"]["감면율"] == 0.5 and r["결과"]["감면세액"] == 19 * M        # 2,000만이지만 최저한세로 1,900만


def test_2026_founding_rates():
    # 2026.2.1. 수도권(과밀억제권역 밖) 일반 25%: 과세표준 2억, 세액 × 25%, 최저한세 1,400만
    t = CC.corp_tax(200 * M, 2026)
    r = ST(founded_on="2026-02-01", region="수도권", year=2026, first_income_year=2026, tax=t, taxable_base=200 * M)
    assert r["결과"]["감면율"] == 0.25 and r["결과"]["감면세액"] == min(t // 4, t - 14 * M)
    assert ST(founded_on="2026-02-01", region="수도권", year=2026, first_income_year=2026, tax=t, taxable_base=200 * M, youth=True)["결과"]["감면율"] == 0.75
    assert ST(founded_on="2026-02-01", region="수도권과밀억제권역", year=2026, first_income_year=2026, tax=t, taxable_base=200 * M)["결과"]["적용"] == "대상 아님"
    assert ST(founded_on="2026-02-01", region="수도권 인구감소지역", year=2026, first_income_year=2026, tax=t, taxable_base=200 * M, youth=True)["결과"]["감면율"] == 1.0


def test_venture_route_and_cap():
    # 과밀억제권역 일반 창업(제1항 없음) → 2023.1.10. 벤처 확인(창업 후 3년 안). 2024 과세표준 10억: 1,800만 + 8억×19% = 1.7억 × 50% = 8,500만
    r = ST(founded_on="2021-03-02", region="수도권과밀억제권역", year=2024, first_income_year=2023, tax=170 * M, taxable_base=1_000 * M, venture_confirmed_on="2023-01-10")
    assert r["결과"]["적용"] == "제2항(창업벤처중소기업)" and r["결과"]["감면세액"] == 85 * M and r["계산"]["감면기간"] == "2023~2027 과세연도"
    assert ST(founded_on="2021-03-02", region="수도권과밀억제권역", year=2025, first_income_year=2025, tax=170 * M, taxable_base=1_000 * M, venture_confirmed_on="2024-06-01")["결과"]["적용"] == "대상 아님"
    t = CC.corp_tax(5_000 * M, 2026)                                              # 2025.2.1. 창업 100% → 5억 한도
    r = ST(founded_on="2025-02-01", region="수도권 밖", year=2026, first_income_year=2026, tax=t, taxable_base=5_000 * M, youth=True)
    assert t > 500 * M and r["결과"]["감면세액"] == 500 * M


def test_special_reduction_rates_cap_and_minimum_tax():
    # 2025 과세표준 5억: 1,800만 + 3억×19% = 7,500만
    assert SP(year=2025, size="소기업", hq_in_capital_area=True, industry_group="그 밖의 감면 업종", tax=75 * M, taxable_base=500 * M)["결과"]["감면세액"] == 15 * M
    assert SP(year=2025, size="소기업", hq_in_capital_area=True, industry_group="도매업등", tax=75 * M, taxable_base=500 * M)["결과"]["감면세액"] == 7_500_000
    assert SP(year=2025, size="중기업", hq_in_capital_area=True, industry_group="그 밖의 감면 업종", tax=75 * M, taxable_base=500 * M)["결과"]["감면세액"] == 0
    assert SP(year=2025, size="중기업", hq_in_capital_area=False, industry_group="도매업등", tax=75 * M, taxable_base=500 * M)["결과"]["감면율"] == 0.05
    # 과세표준 30억: 1,800만 + 28억×19% = 5.5억 × 30% = 1.65억 → 한도 1억, 3명 감소면 8,500만
    k = dict(year=2025, size="소기업", hq_in_capital_area=False, industry_group="그 밖의 감면 업종", tax=550 * M, taxable_base=3_000 * M)
    assert SP(**k)["결과"]["감면세액"] == 100 * M
    assert SP(employees_prev=20, employees_now=17, **k)["결과"]["감면세액"] == 85 * M
    # 2017: 한도 없음. 2,000만 + 28억×20% = 5.8억 × 30% = 1.74억
    assert SP(year=2017, size="소기업", hq_in_capital_area=False, industry_group="그 밖의 감면 업종", tax=580 * M, taxable_base=3_000 * M)["결과"]["감면세액"] == 174 * M
    # 최저한세: 과세표준 2억(2025) 세액 1,800만 × 30% = 540만, 최저한세 1,400만 → 400만
    assert SP(year=2025, size="소기업", hq_in_capital_area=False, industry_group="그 밖의 감면 업종", tax=18 * M, taxable_base=200 * M)["결과"]["감면세액"] == 4 * M


def test_carryback_refund():
    # 2023 결손 3억, 2022 과세표준 5억(2,000만 + 3억×20% = 8,000만) → 2억에 대한 세액 2,000만 → 환급 6,000만
    r = CB(year=2023, loss=300 * M, prior_base=500 * M)
    assert r["결과"] == {"환급세액": 60 * M, "소급공제_결손금": 300 * M, "이월할_결손금": 0}
    r = CB(year=2023, loss=800 * M, prior_base=500 * M)
    assert r["결과"] == {"환급세액": 80 * M, "소급공제_결손금": 500 * M, "이월할_결손금": 300 * M}
    # 직전 감면 5,000만 → 한도 3,000만. 3,000만을 돌려받는 최소 소급공제액: 세액 5,000만이 되는 과세표준 3.5억 → 1.5억(원 미만 절사 때문에 4원 적은 149,999,996원이 최소)
    r = CB(year=2023, loss=300 * M, prior_base=500 * M, prior_credits=50 * M)
    assert r["결과"]["환급세액"] == 30 * M and r["계산"]["한도만큼_환급받는_최소_소급공제액"] == 150 * M - 4
    assert CB(year=2023, loss=300 * M, prior_base=500 * M, prior_credits=80 * M)["결과"] == {"환급세액": 0, "소급공제_결손금": 0, "이월할_결손금": 300 * M}
    assert "error" in CB(year=2016, loss=300 * M, prior_base=500 * M)
    assert "error" in CB(year=2023, loss=300 * M, prior_base=500 * M, carryback=400 * M)
    assert any("제8조의4" in x for x in CB(year=2021, loss=300 * M, prior_base=500 * M)["주의"])
