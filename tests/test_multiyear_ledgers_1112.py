"""0.34.0 loss_carryforward_ledger·foreign_subsidiary_liquidation 정답 테스트(2026-11-12, Claude 손계산).
근거: 법인세법 제13조①(2016~2026 시행본), 시행령 제10조②, 법률 제17652호 부칙 제4조·제15조, 법인세법 제16조①4호, 해석 법인46012-442 등."""
from korean_tax_calc_mcp import server as S

M = 1_000_000


def L(**k):
    return getattr(S.loss_carryforward_ledger, "fn", S.loss_carryforward_ledger)(**k)


def Q(**k):
    return getattr(S.foreign_subsidiary_liquidation, "fn", S.foreign_subsidiary_liquidation)(**k)


def rows(r):
    return {x["year"]: x for x in r["계산"]["연도별"]}


def test_sme_losses_then_profit():
    # 2021 −3억, 2022 −2억, 2023 +8억(중소기업 100%) → 3억 + 2억 공제, 과세표준 3억. 2024 +30억은 공제할 결손금 없음
    r = L(years=[{"year": 2021, "income": -300 * M}, {"year": 2022, "income": -200 * M}, {"year": 2023, "income": 800 * M}, {"year": 2024, "income": 3_000 * M}])
    y = rows(r)
    assert y[2022]["결손금_잔액_합계"] == 500 * M
    assert y[2023]["공제"] == [{"발생연도": 2021, "금액": 300 * M}, {"발생연도": 2022, "금액": 200 * M}] and y[2023]["과세표준"] == 300 * M and y[2023]["한도율"] == 1.0
    assert y[2024]["공제액"] == 0 and y[2024]["과세표준"] == 3_000 * M
    assert r["결과"] == {"공제액": 500 * M, "과세표준": 3_300 * M, "소멸": 0, "기말_결손금_잔액": 0}


def test_non_sme_limit_80_percent():
    # 일반법인 2022 −10억, 2023 +5억 → 한도 4억, 2024 +5억 → 한도 4억, 잔액 2억
    r = L(years=[{"year": 2022, "income": -1_000 * M}, {"year": 2023, "income": 500 * M}, {"year": 2024, "income": 500 * M}], sme=False)
    y = rows(r)
    assert (y[2023]["공제한도"], y[2023]["공제액"], y[2023]["과세표준"], y[2023]["결손금_잔액_합계"]) == (400 * M, 400 * M, 100 * M, 600 * M)
    assert y[2024]["결손금_잔액_합계"] == 200 * M and any("80%" in p["결론"] for p in r["판단"])


def test_non_sme_limit_changes_by_year():
    # 일반법인 한도율: 2017년 80%, 2018년 70%, 2019~2022년 60%, 2023년 80%
    r = L(years=[{"year": y, "income": 100 * M} for y in range(2017, 2024)], sme=False, opening_losses=[{"year": 2016, "amount": 10_000 * M}])
    assert [x["한도율"] for x in r["계산"]["연도별"]] == [0.8, 0.7, 0.6, 0.6, 0.6, 0.6, 0.8]
    assert [x["공제액"] for x in r["계산"]["연도별"]] == [80 * M, 70 * M, 60 * M, 60 * M, 60 * M, 60 * M, 80 * M]


def test_oldest_loss_first_and_partial_use():
    r = L(years=[{"year": 2021, "income": -100 * M}, {"year": 2022, "income": -400 * M}, {"year": 2023, "income": 250 * M}])
    y = rows(r)[2023]
    assert y["공제"] == [{"발생연도": 2021, "금액": 100 * M}, {"발생연도": 2022, "금액": 150 * M}]
    assert y["결손금_잔액"] == [{"발생연도": 2022, "금액": 250 * M, "공제기한": "2037년 개시 사업연도까지"}]


def test_expiry_10_years_for_pre_2020_losses():
    # 2014년 발생 결손금은 2024년 개시 사업연도까지 공제, 2025년에는 소멸
    r = L(years=[{"year": 2024, "income": 10 * M}, {"year": 2025, "income": 500 * M}], opening_losses=[{"year": 2014, "amount": 300 * M}])
    y = rows(r)
    assert y[2024]["공제액"] == 10 * M and y[2024]["결손금_잔액"][0]["공제기한"] == "2024년 개시 사업연도까지"
    assert y[2025]["소멸"] == [{"발생연도": 2014, "금액": 290 * M, "공제기간": "10년"}] and y[2025]["공제액"] == 0 and y[2025]["과세표준"] == 500 * M
    assert r["결과"]["소멸"] == 290 * M


def test_15_years_for_losses_from_2020():
    r = L(years=[{"year": 2020, "income": -100 * M}, {"year": 2021, "income": 0}])
    assert rows(r)[2021]["결손금_잔액"][0]["공제기한"] == "2035년 개시 사업연도까지"
    r = L(years=[{"year": 2020, "income": 0}], opening_losses=[{"year": 2019, "amount": 100 * M}])
    assert rows(r)[2020]["결손금_잔액"][0]["공제기한"] == "2029년 개시 사업연도까지"


def test_per_year_sme_flag_and_input_errors():
    r = L(years=[{"year": 2022, "income": -1_000 * M}, {"year": 2023, "income": 500 * M, "sme": False}, {"year": 2024, "income": 500 * M}])
    y = rows(r)
    assert y[2023]["공제액"] == 400 * M and y[2024]["공제액"] == 500 * M      # 2024년은 중소기업 100%
    assert "error" in L(years=[{"year": 2021, "income": -1}, {"year": 2023, "income": 1}])      # 빠진 해
    assert "error" in L(years=[{"year": 2015, "income": 1}])
    assert "error" in L(years=[{"year": 2020, "income": 1}], opening_losses=[{"year": 2008, "amount": 1}])
    assert "error" in L(years=[])


def test_liquidation_loss_and_year_of_deduction():
    # 취득가액 3.9억, 분배 2,600만 → 청산손실 3.64억, 2024.9.30. 완료 → 2024 사업연도 손금
    r = Q(tax_basis=390 * M, distribution=26 * M, completed_on="2024-09-30")
    assert r["결과"]["구분"] == "청산손실" and r["결과"]["청산손실"] == 364 * M and r["결과"]["의제배당"] == 0
    assert r["결과"]["손금_귀속"] == {"사업연도_종료일": "2024-12-31", "기준일": "2024-09-30"}
    assert any("법인46012-442" in p["근거"] for p in r["판단"])
    # 3월 결산 법인: 2024.9.30. 완료 → 2025.3.31. 종료 사업연도
    assert Q(tax_basis=390 * M, distribution=0, completed_on="2024-09-30", fy_end="2024-03-31")["결과"]["손금_귀속"]["사업연도_종료일"] == "2025-03-31"


def test_liquidation_not_completed_no_deduction_year():
    r = Q(tax_basis=390 * M, distribution=26 * M)
    assert r["결과"]["청산손실"] == 364 * M and r["결과"]["손금_귀속"] is None
    assert any("확정되기 전" in p["결론"] for p in r["판단"])


def test_liquidation_deemed_dividend():
    r = Q(tax_basis=390 * M, distribution=500 * M, completed_on="2025-06-30")
    assert r["결과"]["구분"] == "의제배당" and r["결과"]["의제배당"] == 110 * M and r["결과"]["청산손실"] == 0
    assert "제16조①4호" in r["판단"][0]["근거"]
    assert Q(tax_basis=100 * M, distribution=100 * M)["결과"]["구분"] == "손익 없음"


def test_liquidation_book_value_gap_and_errors():
    r = Q(tax_basis=390 * M, distribution=0, completed_on="2024-09-30", book_value=100 * M)
    assert r["결과"]["유보_정리"] == 290 * M and any(p["항목"] == "유보" for p in r["판단"])
    assert "error" in Q(tax_basis=-1, distribution=0)
    assert "error" in Q(tax_basis=1, distribution=0, completed_on="2015-01-01")
    assert any("대손" in s for s in Q(tax_basis=1, distribution=0)["주의"])
