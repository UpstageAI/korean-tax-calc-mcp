"""미확인 채우기(조세특례제한법 묶음) 정답값 — 조문 원문에서 손으로 계산. Claude 작성(2026-11-15).
대조한 원문(법제처 시행본·부칙·별표, 2026-11-15 조회 — 원자료는 통합테스트/고도화_1114/raw_wp5):
  조세특례제한법 제6조 2018.2.9.·2020.1.1.·2026.1.1. 시행본, 법률 제15227호 부칙 제4조·제39조, 제15623호 부칙 제4조, 제16835호 부칙 제4조·제17조, 제21223호 부칙 제2조·제34조
  조세특례제한법 제127조제4항 2016.10.4.·2017.9.12.·2018.2.9.·2018.12.24. 시행본, 제24조 2025.12.31.·2026.1.1. 시행본(문언 같음)
  조세특례제한법 제29조의7 2019.12.31.·2020.1.1.·2021.3.16. 시행본(제2항·제5항~제7항), 법률 제17926호 부칙 제2조, 시행령 제26조의7 2021.11.11.·현행 시행본
  조세특례제한법 제29조의8 2026.1.1. 시행본(법률 제21223호), 시행령 제26조의8제3항(2026.2.27. 신설: 중견 5명, 그 밖 10명)
  조세특례제한법 시행령 제2조·제6조제5항 2016.12.1.·2017.7.26. 시행본, 대통령령 제26959호 부칙 제22조, 제27848호 부칙 제2조·제3조, 제29116호 부칙 제2조, 시행규칙 제2조제1항(2016.8.13.)
  중소기업기본법 시행령 별표 1·별표 3 2016.4.28. 시행본(2015.6.30. 개정)·2017.10.17. 시행본
  농어촌특별세법 시행령 제4조 2019·2020·2021 연말 시행본, 부칙 제29528호·제30407호·제30610호·제31458호·제32431호·제33282호·제35360호
  해석: 서면-2017-소득-0523, 서면-2022-법규법인-3938, 서면-2022-법인-1042, 조심2023광8267"""
from korean_tax_calc_mcp import server as S
from korean_tax_calc_mcp.engine import calc_incentive as I

M = 1_000_000
E = 100 * M
H = lambda *rows: [{"year": y, "total": t, "youth": yo} for y, t, yo in rows]
OEM = {"domestic_maker": True, "own_planning": True, "own_name": True, "own_sale": True}
tool = lambda name: getattr(getattr(S, name), "fn", getattr(S, name))


# ── 창업감면: 2018.1.1.~5.28. 창업, 2016년 창업 위탁제조 ──
def test_startup_founded_between_2018_jan_and_may_28():
    base = dict(region="수도권 밖", tax=200 * M, taxable_base=1_000 * M)
    r = I.startup_tax_reduction("2018-05-28", year=2019, first_income_year=2019, youth=True, **base)      # 경계 앞: 청년 75%(1~3번째)
    assert r["계산"]["감면율"] == 0.75 and r["계산"]["한도_전_감면세액"] == 150 * M and r["결과"]["감면세액"] == 130 * M      # 최저한세 7,000만원
    assert I.startup_tax_reduction("2018-05-28", year=2022, first_income_year=2019, youth=True, **base)["계산"]["감면율"] == 0.5      # 4번째 과세연도
    r = I.startup_tax_reduction("2018-05-29", year=2019, first_income_year=2019, youth=True, **base)      # 경계 뒤: 청년 100%
    assert r["결과"]["감면세액"] == 200 * M
    assert I.startup_tax_reduction("2018-03-02", year=2019, first_income_year=2019, **base)["결과"]["감면세액"] == 100 * M      # 일반 50%
    r = I.startup_tax_reduction("2018-03-02", region="수도권과밀억제권역", year=2019, first_income_year=2019, youth=True, tax=200 * M, taxable_base=1_000 * M)
    assert r["결과"]["적용"] == "대상 아님"      # 2018.1.1. 시행본은 과밀억제권역 밖만(과밀억제권역 안 청년 50%는 2018.5.29. 창업부터)
    assert "15~29세" in " ".join(I.startup_tax_reduction("2018-05-28", year=2019, first_income_year=2019, youth=True, **base)["주의"])


def test_startup_contract_manufacturing_founded_2016():
    r = I.startup_tax_reduction("2016-05-02", "수도권 밖", 2018, 2017, 200 * M, 1_000 * M, industry="위탁제조", oem=OEM)
    assert r["결과"]["감면세액"] == 100 * M and any("서면-2017-소득-0523" in x for x in r["근거"])
    r = I.startup_tax_reduction("2016-05-02", "수도권 밖", 2018, 2017, 200 * M, 1_000 * M, industry="위탁제조", oem=dict(OEM, own_name=False))
    assert r["결과"]["적용"] == "대상 아님"
    text = " ".join(I.startup_tax_reduction("2021-03-02", "수도권 밖", 2023, 2022, 200 * M, 1_000 * M)["주의"])
    assert "대조하지 않음" not in text and "2016·2017 시행본 제127조제4항에는 이 단서가 없고" in text


# ── 중소기업 판정: 2016·2017 과세연도 ──
def test_sme_status_2016_table():
    f = lambda **k: I.sme_status(**{"year": 2016, "total_assets": 10 * E, **k})
    lim = lambda code, year=2016: (I._size_limit(code, year, "중소") // E, I._size_limit(code, year, "소") // E)
    assert [lim(c) for c in ("C14", "C20", "C11", "E", "D", "N", "L", "S", "G", "J", "I")] == [
        (1500, 120), (1000, 120), (800, 120), (800, 30), (1000, 120), (600, 30), (400, 30), (600, 10), (1000, 50), (800, 50), (400, 10)]
    assert f(industry_code="C20", revenue=1_000 * E)["결과"] == {"중소기업": True, "구분": "중기업"}        # 1,000억원 이하
    assert f(industry_code="C20", revenue=1_000 * E + 1)["결과"]["구분"] == "유예기간 중"
    assert f(industry_code="G", revenue=50 * E)["결과"]["구분"] == "소기업" and f(industry_code="G", revenue=50 * E + 1)["결과"]["구분"] == "중기업"
    for bad in ("E36", "C34", "N76"):      # 제10차 분류 기호는 2016 별표에 없음
        assert "error" in f(industry_code=bad, revenue=1)
    r = f(industry_code="C20", revenue=1, excluded_business=True)
    assert r["결과"]["중소기업"] is False and "열거" in r["판단"][0]
    assert "error" in I.sme_status(2015, "C20", 1, 1)


def test_sme_status_2017_and_small_business_transition():
    r = I.sme_status(2017, "C34", 600 * E, 10 * E)      # 2017.12.31. 현재 별표 = 2017.10.17. 개정본(C34 600억원, 소기업 10억원)
    assert r["결과"] == {"중소기업": True, "구분": "중기업"} and "2017.10.17." in r["근거"][1]
    assert I.sme_status(2017, "E36", 1_000 * E, 10 * E)["결과"]["중소기업"] is True
    r = I.sme_status(2017, "C20", 1_200 * E, 10 * E)
    assert r["계산"]["유예기간"] == "2017~2020 과세연도"
    assert "소비성서비스업" in I.sme_status(2017, "I", 1, 1, excluded_business=True)["판단"][0]
    # 소기업 경과조치(대통령령 제26959호 부칙 제22조): 2019 과세연도까지
    kw = dict(industry_code="G", revenue=60 * E, total_assets=10 * E)
    assert I.sme_status(2019, **kw)["결과"]["구분"] == "중기업"
    assert I.sme_status(2019, small_under_pre2016_rule=True, **kw)["결과"]["구분"] == "소기업"
    assert I.sme_status(2020, small_under_pre2016_rule=True, **kw)["결과"]["구분"] == "중기업"
    r = tool("sme_status")(year=2016, industry_code="G", revenue=60 * E, total_assets=10 * E, small_under_pre2016_rule=True)
    assert r["결과"]["구분"] == "소기업"


# ── 농어촌특별세: 개정 부칙 적용례 ──
def test_rural_special_tax_transition_rules():
    one = lambda y, a: I.rural_special_tax(y, [{"article": a, "amount": 10 * M}])["결과"]["농어촌특별세"]
    pairs = [("제104조의24", 2017, 2018), ("제99조의9", 2017, 2018), ("제19조제2항", 2018, 2019), ("제25조제1항", 2018, 2019), ("제18조의3", 2019, 2020),
             ("제99조의11", 2019, 2020), ("제104조의31", 2020, 2021), ("제16조의2", 2021, 2022), ("제92조", 2023, 2024)]
    for art, taxed, exempt in pairs:
        assert (one(taxed, art), one(exempt, art)) == (2 * M, 0), art
    assert one(2026, "제25조제1항") == 0 and (one(2019, "제11조"), one(2020, "제11조")) == (0, 2 * M)
    r = I.rural_special_tax(2019, [{"article": "제25조제1항", "amount": 10 * M}])
    assert "대통령령 제30407호 부칙 제2조" in r["계산"]["항목별"][0]["적용례"]
    assert not any("확인" in row for row in I.rural_special_tax(2022, [{"article": "제104조의31", "amount": M}])["계산"]["항목별"])


# ── 통합고용세액공제: 2026 과세연도 개정 계산식 ──
def test_integrated_employment_credit_2026_new_formula():
    f = lambda size, prev, cur, **k: I.integrated_employment_credit(2026, size, H((2025, *prev), (2026, *cur)), **k)
    assert f("중소기업", (10, 3), (14, 5))["결과"]["기본공제"] == 22 * M                                   # 청년등 2 × 700만 + 그 외 2 × 400만
    assert f("중소기업", (10, 3), (14, 5), outside_capital_area=True)["결과"]["기본공제"] == 34 * M        # 2 × 1,000만 + 2 × 700만
    assert f("중소기업", (10.5, 3.25), (12.75, 4.5))["결과"]["기본공제"] == 12_750_000                    # 1.25 × 700만 + 1 × 400만
    assert f("중소기업", (10, 5), (12, 9))["결과"]["기본공제"] == 14 * M                                   # 청년등 증가 4명은 전체 증가 2명 한도
    assert f("중소기업", (10, 3), (10, 5))["결과"]["기본공제"] == 0
    # 중견: 최소고용증가인원수 5명을 넘어야 하고 제3호 금액을 뺌
    assert f("중견기업", (100, 30), (105, 33))["결과"]["기본공제"] == 0                                    # 5명은 넘은 것이 아님
    assert f("중견기업", (100, 30), (108, 33))["결과"]["기본공제"] == 15 * M                               # 3 × 500만 + 5 × 300만 − 5 × 300만
    assert f("중견기업", (100, 30), (106, 35))["결과"]["기본공제"] == 5 * M                                # 5 × 500만 + 1 × 300만 − (1 × 300만 + 4 × 500만)
    # 그 밖: 10명 초과, 청년등 외 금액 없음
    assert f("일반", (100, 30), (110, 40))["결과"]["기본공제"] == 0
    assert f("일반", (100, 30), (115, 36))["결과"]["기본공제"] == 15 * M                                   # 6 × 300만 − (10 − 9) × 300만
    assert f("일반", (100, 30), (112, 30))["결과"]["기본공제"] == 0
    r = f("중견기업", (100, 30), (108, 33))
    assert "추가_납부세액" not in r["결과"] and r["계산"]["최초_공제_과세연도별"][0]["차감액_제3호"] == 15 * M


def test_integrated_employment_credit_2026_with_old_rule_carryover():
    g = I.integrated_employment_credit
    r = g(2026, "중소기업", H((2024, 8, 2), (2025, 10, 3), (2026, 14, 5)), returned_from_leave=1)
    # 2025 증가분 2차(종전): 1 × 1,450만 + 1 × 850만 = 2,300만 / 2026 증가분(개정): 2,200만 / 육아휴직 복귀 1,300만
    assert r["결과"]["기본공제"] == 45 * M and r["결과"]["육아휴직_복귀_공제"] == 13 * M and r["결과"]["공제_대상_세액"] == 58 * M
    assert "error" in g(2026, "중소기업", H((2025, 10, 3), (2026, 14, 5)), converted=1)      # 정규직 전환은 2024년 전환분까지
    assert "error" in g(2027, "중소기업", H((2026, 10, 3), (2027, 14, 5)))
    # 중소·중견이 아닌 기업의 2024 증가분: 2026 과세연도는 부칙 제34조의 종전 규정 기간 밖 — 추가 납부 없음
    r = g(2026, "일반", H((2023, 100, 20), (2024, 110, 25), (2025, 110, 25), (2026, 105, 25)))
    assert r["결과"]["기본공제"] == 0 and "추가_납부세액" not in r["결과"] and any("부칙 제34조" in p and "추가 납부는 없는" in p for p in r["판단"])
    text = " ".join(r["판단"] + r["주의"])
    assert "확인 필요라 계산하지 않음" not in text


def test_integrated_employment_credit_youth_only_decrease_shows_both_readings():
    r = I.integrated_employment_credit(2024, "중소기업", H((2022, 10, 2), (2023, 14, 5), (2024, 14, 4)))
    row = next(x for x in r["계산"]["최초_공제_과세연도별"] if x["최초_공제_과세연도"] == 2023)
    # 2023 증가: 청년등 3·그 외 1. 2024년 청년등 1명 감소 → 청년등 외 금액 4 × 850만 = 3,400만 / 다른 해석: 2 × 1,450만 + 1 × 850만 + 1 × 850만 = 4,600만
    assert row["공제액"] == 34 * M and row["다른_해석_공제액"] == 46 * M
    assert any("근거 없음" in p and "서면질의 필요" in p for p in r["판단"]) and not any("확인하지 못함" in p for p in r["판단"])


# ── 고용증대: 2020 사후관리 유예(제29조의7제5항~제7항) ──
def test_employment_increase_2020_deferral_first_year_2019():
    g = lambda year, *rows, **k: I.employment_increase_credit(year, "중소기업", H(*rows), **k)
    base = ((2018, 10, 4), (2019, 20, 8), (2020, 15, 8))      # 2019 증가: 청년등 4 × 1,100만 + 그 외 6 × 700만 = 8,600만
    r = g(2020, *base)
    assert r["결과"] == {"공제_대상_세액": 0} and any("제29조의7제5항" in p for p in r["판단"])      # 2020년: 공제 중단, 추가 납부 없음
    assert g(2021, *base, (2021, 20, 8))["결과"] == {"공제_대상_세액": 121 * M}                      # 회복: 8,600만 + 2021 증가분 5 × 700만
    assert g(2022, *base, (2021, 20, 8), (2022, 20, 8))["결과"] == {"공제_대상_세액": 121 * M}       # 제6항 공제는 2022년까지(중소 3년)
    r = g(2022, *base, (2021, 20, 8), (2022, 18, 8))      # 제7항: 2022년에 2명 감소 — 그 외 2 × 700만 × 공제 횟수 1(2021년) + 2021년분 1년 이내 2 × 700만
    assert r["결과"] == {"공제_대상_세액": 0, "추가_납부세액": 28 * M} and any("근거 없음" in p for p in r["판단"])
    r = g(2021, *base, (2021, 17, 8))                     # 2021년에도 감소: 2년 이내 산식 — 그 외 3 × 700만 × 공제 횟수 1(2020년은 중단) = 2,100만. 2021 증가분 2 × 700만
    assert r["결과"] == {"공제_대상_세액": 14 * M, "추가_납부세액": 21 * M}
    r = I.employment_increase_credit(2021, "일반", H(*base, (2021, 20, 8)))      # 중소·중견이 아니면 제6항 기간은 2년(2021년까지): 4 × 400만
    assert r["결과"] == {"공제_대상_세액": 16 * M}


def test_employment_increase_2020_deferral_first_year_2018():
    rows = ((2017, 10, 2), (2018, 15, 4), (2019, 15, 4), (2020, 13, 3))      # 2018 증가: 청년등 2 × 1,100만 + 그 외 3 × 700만 = 4,300만
    g = lambda year, *more, **k: I.employment_increase_credit(year, "중소기업", H(*rows, *more), **k)
    assert g(2020)["결과"] == {"공제_대상_세액": 0}
    assert g(2021, (2021, 15, 4))["결과"] == {"공제_대상_세액": 43 * M + 18 * M}      # 제6항(2021년까지) + 2021 증가분 1 × 1,100만 + 1 × 700만
    r = g(2021, (2021, 12, 3), credits_taken=[{"first_year": 2018, "year": 2018, "amount": 43 * M}, {"first_year": 2018, "year": 2019, "amount": 43 * M}])
    # 2020년 유예분: (1 × 1,100만 + 1 × 700만) × 2회 = 3,600만 / 2021년 감소 기준: (1 × 1,100만 + 2 × 700만) × 2회 = 5,000만 → 적은 금액(서면-2022-법규법인-3938)
    row = r["계산"]["최초_공제_과세연도별"][0]
    assert row["유예_계산"] == {"2020_유예된_금액": 36 * M, "2021_감소_기준_금액": 50 * M} and r["결과"]["추가_납부세액"] == 36 * M
    r = I.employment_increase_credit(2021, "일반", H(*rows, (2021, 15, 4)), only_first_years=[2018])
    assert r["결과"] == {"공제_대상_세액": 0}      # 중소·중견이 아니면 제6항 기간(2020년까지)이 지남
    # 유예와 무관한 경우(2020년에 줄지 않음)는 종전과 같음
    r = I.employment_increase_credit(2020, "중소기업", H((2017, 10, 2), (2018, 15, 4), (2019, 15, 4), (2020, 15, 4)))
    assert r["결과"] == {"공제_대상_세액": 43 * M}


def test_employment_increase_2020_youth_only_decrease_keeps_other_credit():
    # 서면-2022-법인-1042의 인원: 수도권 밖 중소기업, 2019 최초 공제, 2020년 전체 증가·청년등 감소 → 2020년에도 청년등 외 금액으로 공제
    r = I.employment_increase_credit(2020, "중소기업", H((2018, 14.08, 5.08), (2019, 27.50, 8.33), (2020, 32.58, 7.16)), outside_capital_area=True)
    row = next(x for x in r["계산"]["최초_공제_과세연도별"] if x["최초_공제_과세연도"] == 2019)
    assert row["공제액"] == 25_025_000 + 78_309_000 and row["상태"] == "청년등 외 금액으로 공제"      # 3.25 × 770만 + 10.17 × 770만
    assert r["결과"] == {"공제_대상_세액": 103_334_000 + 39_116_000}                                 # 2020 증가분 5.08 × 770만


# ── 통합투자: 졸업 기업의 임시 투자 세액공제 ──
def test_investment_credit_graduate_temp_rates():
    f = lambda **k: I.integrated_investment_credit(2025, "졸업 뒤 3년", [{"kind": "일반", "amount": 1_000 * M}], graduated_year=2025, **k)
    r = f()
    assert r["결과"]["공제_대상_세액"] == 75 * M and r["계산"]["임시_졸업_기업_지위별"] == {"중견기업": 70 * M, "일반": 10 * M}
    assert not any("확인 필요" in p for p in r["판단"])
    r = f(graduate_status="중견기업")
    assert r["결과"]["적용"] == "본칙" and r["결과"]["공제_대상_세액"] == 75 * M      # 7.5% > 임시 7%
    assert "error" in f(graduate_status="중소기업")
    assert "error" in I.integrated_investment_credit(2025, "중견기업", [{"kind": "일반", "amount": M}], graduate_status="일반")
