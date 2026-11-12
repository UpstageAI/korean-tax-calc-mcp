"""0.35.0 tax_adjustment_schedule 정답 테스트(2026-11-12, Claude 손계산). 근거: 법인세법 제14조·제13조①·제55조·제67조(2016·2026 시행본)."""
from korean_tax_calc_mcp import server as S

M = 1_000_000


def f(**k):
    return getattr(S.tax_adjustment_schedule, "fn", S.tax_adjustment_schedule)(**k)


def rows(r):
    return {x["year"]: x for x in r["계산"]["연도별"]}


A = lambda name, amount, kind, disp: {"name": name, "amount": amount, "kind": kind, "disposition": disp}
STORY = [
    {"year": 2021, "book_income": -320 * M, "adjustments": [A("접대비 한도초과", 20 * M, "손금불산입", "기타사외유출")]},
    {"year": 2022, "book_income": -200 * M, "adjustments": []},
    {"year": 2023, "book_income": 700 * M, "adjustments": [
        A("포인트충당부채", 50 * M, "손금불산입", "유보"), A("포인트충당부채", 15 * M, "손금산입", "유보"),
        A("대여 인정이자", 38_564_383, "익금산입", "기타사외유출"), A("접대비 한도초과", 14 * M, "손금불산입", "기타사외유출"),
        A("법인세비용", 12_435_617, "손금불산입", "기타사외유출")]},
]


def test_three_years_losses_reserve_and_tax():
    r = f(years=STORY)
    y = rows(r)
    assert y[2021]["각사업연도소득"] == -300 * M and y[2022]["각사업연도소득"] == -200 * M and y[2022]["결손금_잔액"] == 500 * M
    # 2023: 7억 + (5,000만 + 38,564,383 + 1,400만 + 12,435,617) − 1,500만 = 8억 → 결손금 5억 공제 → 3억 → 2억×9% + 1억×19% = 3,700만
    assert y[2023]["익금산입_손금불산입"] == 115 * M and y[2023]["손금산입_익금불산입"] == 15 * M and y[2023]["각사업연도소득"] == 800 * M
    assert y[2023]["이월결손금_공제"] == 500 * M and y[2023]["과세표준"] == 300 * M and y[2023]["산출세액"] == 37 * M
    assert y[2023]["유보"] == [{"항목": "포인트충당부채", "기초": 0, "증가": 50 * M, "감소": 15 * M, "기말": 35 * M}]
    assert y[2023]["소득처분_사외유출"] == {"기타사외유출": 65 * M}
    assert r["결과"] == {"각사업연도소득": 300 * M, "과세표준": 300 * M, "산출세액": 37 * M, "기말_유보": 35 * M, "기말_결손금_잔액": 0}
    assert "제14조" in r["근거"] and "별지 제15호" in r["서식"]


def test_reserve_carries_into_next_year_and_reverses():
    yrs = [{"year": 2024, "book_income": 1_000 * M, "adjustments": [A("포인트충당부채", 100 * M, "손금불산입", "유보")]},
           {"year": 2025, "book_income": 1_000 * M, "adjustments": [A("포인트충당부채", 60 * M, "손금산입", "유보"), A("포인트충당부채", 20 * M, "익금불산입", "유보")]}]
    y = rows(f(years=yrs, opening_reserves=[{"name": "포인트충당부채", "amount": 35 * M}]))
    assert y[2024]["유보"][0] == {"항목": "포인트충당부채", "기초": 35 * M, "증가": 100 * M, "감소": 0, "기말": 135 * M}
    assert y[2025]["유보"][0] == {"항목": "포인트충당부채", "기초": 135 * M, "증가": 0, "감소": 80 * M, "기말": 55 * M}
    assert y[2025]["각사업연도소득"] == 920 * M and y[2025]["산출세액"] == 18 * M + int(720 * M * 0.19)


def test_over_reversal_is_flagged_and_negative_reserve_allowed():
    r = f(years=[{"year": 2025, "book_income": 100 * M, "adjustments": [A("재고평가", 30 * M, "손금산입", "유보")]}], opening_reserves=[{"name": "재고평가", "amount": 10 * M}])
    assert rows(r)[2025]["유보"][0]["기말"] == -20 * M and any("보다 많은" in p["결론"] for p in r["판단"])
    r = f(years=[{"year": 2025, "book_income": 100 * M, "adjustments": [A("감가상각 시인부족", 30 * M, "손금산입", "유보")]}])
    assert rows(r)[2025]["유보_기말_합계"] == -30 * M and not any("보다 많은" in p["결론"] for p in r["판단"])


def test_outflow_dispositions_and_notice():
    r = f(years=[{"year": 2025, "book_income": 500 * M, "adjustments": [A("가지급금 인정이자", 6_183_606, "익금산입", "상여"), A("대여금 면제", 200 * M, "손금불산입", "기타소득"),
                                                                       A("수입배당금", 190 * M, "익금불산입", "기타")]}])
    y = rows(r)[2025]
    assert y["소득처분_사외유출"] == {"상여": 6_183_606, "기타소득": 200 * M} and y["각사업연도소득"] == 500 * M + 206_183_606 - 190 * M
    assert y["유보"] == [] and any("원천징수" in p["결론"] for p in r["판단"])


def test_non_sme_limit_and_opening_losses():
    r = f(years=[{"year": 2023, "book_income": 500 * M, "adjustments": []}], sme=False, opening_losses=[{"year": 2020, "amount": 1_000 * M}])
    y = rows(r)[2023]
    assert y["이월결손금_공제"] == 400 * M and y["과세표준"] == 100 * M and y["산출세액"] == 9 * M and y["결손금_잔액"] == 600 * M


def test_tax_rate_tables_by_year():
    # 2022년 2억 이하 10%·초과 20%, 2023년부터 9%·19%
    y = rows(f(years=[{"year": 2022, "book_income": 300 * M, "adjustments": []}, {"year": 2023, "book_income": 300 * M, "adjustments": []}]))
    assert y[2022]["산출세액"] == 40 * M and y[2023]["산출세액"] == 37 * M


def test_input_errors():
    assert "error" in f(years=[])
    assert "error" in f(years=[{"year": 2025, "book_income": 1, "adjustments": [A("x", 1, "손금산입", "상여")]}])       # 차감 조정에 상여 처분
    assert "error" in f(years=[{"year": 2025, "book_income": 1, "adjustments": [A("x", 1, "가산", "유보")]}])
    assert "error" in f(years=[{"year": 2021, "book_income": 1, "adjustments": []}, {"year": 2023, "book_income": 1, "adjustments": []}])
    assert "error" in f(years=[{"year": 2015, "book_income": 1, "adjustments": []}])


def test_arm_length_range_comparable_notice():
    r = getattr(S.arm_length_range, "fn", S.arm_length_range)(comparables=[0.01, 0.02, 0.03], tested_value=0.02)
    items = {x["항목"]: x for x in r["비교대상_확인"]}
    assert set(items) == {"비교가능 거래의 뜻", "분석요소", "내부 비교가능 거래", "제외할 수 있는 거래", "이익률 자료의 한계", "과세당국의 재산정"}
    assert "제14조①1호" in items["비교가능 거래의 뜻"]["근거"] and "제7조①4호" in items["내부 비교가능 거래"]["근거"]
    assert "확인할 수 없음" in items["이익률 자료의 한계"]["내용"]
