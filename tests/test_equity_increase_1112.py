"""0.37.1 정답 테스트(2026-11-12, Claude 손계산). tax_adjustment_schedule의 '출자의 증가' 처분과 위탁제조 안내.
근거: 국제조세조정에 관한 법률 제13조①·시행령 제23조①1호(2021·2025 시행본), 구 법 제9조①·구 시행령 제16조①2호(2016·2020 시행본),
조심2023서10448(2024.2.16.), 조심2010중3890(2011.9.14.) 본문."""
from korean_tax_calc_mcp import server as S

M = 1_000_000


def f(tool, **k):
    return getattr(tool, "fn", tool)(**k)


A = lambda name, amount, kind, disp: {"name": name, "amount": amount, "kind": kind, "disposition": disp}
YEARS = [
    {"year": 2023, "book_income": 700 * M, "adjustments": [A("해외 자회사 대여 인정이자", 38_564_383, "익금산입", "출자의 증가"), A("포인트충당부채", 50 * M, "손금불산입", "유보")]},
    {"year": 2024, "book_income": 1_000 * M, "adjustments": [A("해외 자회사 대여 인정이자", 46 * M, "익금산입", "출자의 증가")]},
    {"year": 2025, "book_income": 1_000 * M, "adjustments": [A("해외 자회사 이전가격", 810 * M, "익금산입", "출자의 증가"), A("사주 인정이자", 6 * M, "익금산입", "상여")]},
]


def test_equity_increase_tracked_apart_from_reserve_and_outflow():
    r = f(S.tax_adjustment_schedule, years=YEARS)
    y = {x["year"]: x for x in r["계산"]["연도별"]}
    # 소득에는 그대로 더해짐: 7억 + 38,564,383 + 5,000만
    assert y[2023]["각사업연도소득"] == 788_564_383 and y[2025]["각사업연도소득"] == 1_816 * M
    # 유보·사외유출에는 들어가지 않음
    assert y[2023]["유보_기말_합계"] == 50 * M and y[2023]["소득처분_사외유출"] == {} and y[2025]["소득처분_사외유출"] == {"상여": 6 * M}
    assert y[2023]["출자의_증가"] == [{"항목": "해외 자회사 대여 인정이자", "당기": 38_564_383, "누계": 38_564_383}]
    assert y[2024]["출자의_증가_누계"] == 84_564_383
    assert y[2025]["출자의_증가"] == [{"항목": "해외 자회사 대여 인정이자", "당기": 0, "누계": 84_564_383}, {"항목": "해외 자회사 이전가격", "당기": 810 * M, "누계": 810 * M}]
    assert r["결과"]["기말_출자의_증가_누계"] == 894_564_383 and r["결과"]["기말_유보"] == 50 * M
    notes = [p for p in r["판단"] if "출자의 증가" in p["항목"]]
    assert len(notes) == 3 and all("제13조" in p["근거"] and "제23조" in p["근거"] for p in notes)
    assert any("해석 확인 필요" in s for s in r["주의"])


def test_equity_increase_basis_by_year_and_only_for_additions():
    r = f(S.tax_adjustment_schedule, years=[{"year": 2020, "book_income": 100 * M, "adjustments": [A("x", 10 * M, "익금산입", "출자의 증가")]},
                                             {"year": 2021, "book_income": 100 * M, "adjustments": [A("x", 10 * M, "익금산입", "출자의 증가")]}])
    basis = {p["항목"][:4]: p["근거"] for p in r["판단"] if "출자의 증가" in p["항목"]}
    assert "제9조" in basis["2020"] and "제16조" in basis["2020"] and "제13조" in basis["2021"]
    assert "error" in f(S.tax_adjustment_schedule, years=[{"year": 2025, "book_income": 1, "adjustments": [A("x", 1, "손금산입", "출자의 증가")]}])


def test_no_equity_keys_when_not_used():
    r = f(S.tax_adjustment_schedule, years=[{"year": 2025, "book_income": 100 * M, "adjustments": [A("x", 10 * M, "손금불산입", "유보")]}])
    assert "기말_출자의_증가_누계" not in r["결과"] and "출자의_증가" not in r["계산"]["연도별"][0] and len(r["주의"]) == 4


def test_consignment_manufacturing_notices():
    r = f(S.sme_special_tax_reduction, year=2024, size="소기업", hq_in_capital_area=True, industry_group="그 밖의 감면 업종", tax=550 * M, taxable_base=3_000 * M)
    assert r["결과"]["감면세액"] == 100 * M
    assert any("조심2023서10448" in s and "조심2010중3890" in s and "제4조의2" in s for s in r["주의"])
    r = f(S.sme_status, year=2025, industry_code="C20", revenue=50_000 * M, total_assets=25_000 * M)
    assert r["결과"]["구분"] == "중기업" and any("자기 계정으로 구입한 원재료" in s and "industry_code='G'" in s for s in r["주의"])
