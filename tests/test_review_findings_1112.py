"""0.40.1 정답 테스트(2026-11-12, Claude 손계산) — 자동 코드 리뷰 지적을 다시 확인해 고친 것.
근거: 조세특례제한법 제29조의8·제29조의7 사후관리 항(최초 공제 과세연도 종료일부터 2년), 시행령 제26조의8④2호·제26조의7⑤2호, 제143조③."""
from korean_tax_calc_mcp import server as S

M = 1_000_000
fn = lambda t: getattr(t, "fn", t)
H = lambda *rows: [{"year": y, "total": t, "youth": yo} for y, t, yo in rows]


def test_other_company_recapture_in_second_year_after_first_credit():
    # 그 밖의 기업: 2023년 청년등 +4(× 400만 = 1,600만), 2024년 2차 공제. 2025년 전체 25·청년등 10 → 공제 기간은 끝났지만 사후관리 대상
    #   전체 −5, 청년등 −2, 그 외 −3 → (2 × 400만 + 3 × 0) × 공제받은 횟수 2 = 1,600만
    r = fn(S.integrated_employment_credit)(year=2025, size="일반", headcounts=H((2022, 20, 8), (2023, 30, 12), (2024, 30, 12), (2025, 25, 10)))
    row = r["계산"]["최초_공제_과세연도별"][0]
    assert r["결과"]["기본공제"] == 0 and r["결과"]["추가_납부세액"] == 16 * M and row["상태"] == "공제 기간 종료(사후관리)" and row["추가_납부"]["공제받은_횟수"] == 2
    assert any("공제 기간은 끝났지만" in p for p in r["판단"])
    # 줄지 않았으면 3년째에는 아무 줄도 나오지 않음
    r = fn(S.integrated_employment_credit)(year=2025, size="일반", headcounts=H((2022, 20, 8), (2023, 30, 12), (2024, 30, 12), (2025, 30, 12)))
    assert r["결과"]["기본공제"] == 0 and "추가_납부세액" not in r["결과"] and r["계산"]["최초_공제_과세연도별"] == []
    # 해당 과세연도의 직전 과세연도 인원은 여전히 필수
    assert "error" in fn(S.integrated_employment_credit)(year=2025, size="일반", headcounts=H((2022, 20, 8), (2023, 30, 12), (2025, 31, 12)))


def test_other_company_recapture_for_employment_increase_credit():
    # 고용증대, 그 밖의 기업: 2021년 청년등 +4 × 400만 = 1,600만. 2023년 전체 25·청년등 10 → (2 × 400만) × 2회 = 1,600만
    r = fn(S.employment_increase_credit)(year=2023, size="일반", headcounts=H((2020, 20, 8), (2021, 30, 12), (2022, 30, 12), (2023, 25, 10)), only_first_years=[2021])
    assert r["결과"]["공제_대상_세액"] == 0 and r["결과"]["추가_납부세액"] == 16 * M


def test_sme_results_unchanged():
    hc = H((2022, 20, 8), (2023, 45, 20), (2024, 80, 35), (2025, 110, 45))
    assert fn(S.integrated_employment_credit)(year=2025, size="중소기업", headcounts=hc)["결과"]["기본공제"] == 987 * M
    assert fn(S.employment_increase_credit)(year=2024, size="중소기업", headcounts=H((2021, 8, 4), (2022, 20, 8), (2023, 45, 20), (2024, 80, 35)), only_first_years=[2022])["결과"]["공제_대상_세액"] == 100 * M


def test_loss_allocation_remainder_goes_to_last_income_business():
    seg = lambda n, e, rev, dexp: {"name": n, "eligible": e, "revenue": rev, "direct_expenses": dexp}
    # 소득 10·10·10, 결손 10 → 3·3·4(나머지 1원은 마지막 소득 사업). 안분 합계 = 결손금
    r = fn(S.reduction_income_segments)(segments=[seg("A", True, 10, 0), seg("B", False, 10, 0), seg("C", False, 10, 0), seg("D", False, 0, 10)])
    cuts = [x["결손금_안분_공제"] for x in r["계산"]["사업별"]]
    assert cuts == [3, 3, 4, 0] and sum(cuts) == 10 and r["결과"]["감면_대상_소득"] == 7 and r["결과"]["각사업연도소득"] == 20
    # 결손이 소득 합계보다 크면 소득 사업 전부 0
    r = fn(S.reduction_income_segments)(segments=[seg("A", True, 10, 0), seg("D", False, 0, 30)])
    assert r["계산"]["사업별"][0]["공제_후_소득금액"] == 0 and r["결과"]["감면_대상_소득"] == 0


def test_employment_credits_point_to_requirements_guide():
    # 0.40.2: 요건은 조문 MCP의 요건 안내 도구로 확인하도록 주의 첫 줄에서 안내
    a = fn(S.integrated_employment_credit)(year=2025, size="중소기업", headcounts=H((2024, 80, 35), (2025, 110, 45)))
    b = fn(S.employment_increase_credit)(year=2024, size="중소기업", headcounts=H((2023, 45, 20), (2024, 80, 35)))
    assert "employment_credit_requirements_guide(year=과세연도, credit='통합고용'" in a["주의"][0] and "employment_credit_requirements_guide(year=과세연도, credit='고용증대'" in b["주의"][0]
