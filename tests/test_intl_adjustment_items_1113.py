"""0.41.0 국제거래 도구가 세무조정 항목을 내고, 집계·서식이 국조법 처분을 받는지(2026-11-13, Claude).
조문: 국제조세조정에 관한 법률 제13조①, 시행령 제22조~제25조(2021·2022·2023·2025·2026 시행본), 법인세법 시행령 제106조①,
법인세법 시행규칙 별지 제15호서식 작성방법 3.(2025.10.31. 시행본 — 임시유보 700, 이전소득 배당 810, 출자의 증가 820, 손금 쪽 출자의 증가 300)."""
import openpyxl
from korean_tax_calc_mcp import server as S

M = 1_000_000


def _fn(t):
    return getattr(t, "fn", t)


RANGE = dict(comparables=[0.012, 0.021, 0.025, 0.031, 0.038, 0.044, 0.052, 0.067], tested_value=0.075, base_amount=6_000 * M, tested_is_resident=False, year=2025)
LOAN = dict(movements=[S.Movement(date="2025-03-01", amount=1_000 * M)], year_end="2025-12-31", rate_mode="당좌선택", foreign_related=True)
EXPAT = dict(year=2025, items=[
    {"이름": "파견 팀장", "급여": 90 * M, "사회보험": 8 * M, "체재비": 20 * M, "귀속": "현지법인", "청구액": 0, "국외근로_개월": 12},
    {"이름": "겸직 MD", "급여": 60 * M, "사회보험": 5 * M, "귀속": "공통", "공통비율": 0.4, "청구액": 20 * M, "국외근로_개월": 0}])
PROV = dict(grants=[{"year": 2025, "amount": 200 * M}], valid_years=2, usage_pattern=[0.3, 0.4, 0.1], expected_usage_rate=1.0, cost_ratio=0.5)
DIV = dict(received_on="2025-06-30", ownership_ratio=1.0, held_months=16, dividend=200 * M, foreign_withholding=10 * M)
CFC = dict(year=2025, pretax_incomes=[1_000 * M], taxes_paid=[82_500_000], ownership_chains=[[1.0]], distributable={"unappropriated_retained_earnings": 1_000 * M},
           listed_industry="도매업", listed_industry_share=1.0, listed_industry_related_share=0.9, same_country_unrelated_sales_share=0.05, fixed_facility_active_business=True)


def _items(r):
    return [(a["조정"], a["금액"], a["소득처분"]) for a in r["세무조정"]]


def test_transfer_pricing_items_are_provisional_reserve():
    r = _fn(S.arm_length_range)(**RANGE)
    assert _items(r) == [("익금산입", 243_000_000, "임시유보")] and "제24조①" in r["세무조정"][0]["근거"]
    assert any("제25조①4호" in x and "90일" in x for x in r["주의"])
    d = _fn(S.deemed_interest)(**LOAN)
    assert _items(d) == [("익금산입", 38_564_383, "임시유보")]
    inside = _fn(S.arm_length_range)(**{**RANGE, "tested_value": 0.03})
    assert inside["세무조정"] == []
    # 거주자 소득이 많은 쪽(감액)은 항목을 내지 않는다
    over = _fn(S.arm_length_range)(**{**RANGE, "tested_value": 0.005})
    assert over["세무조정"] == [] and any("감액" in x for x in over["주의"])
    # 국내 가지급금은 종전 그대로(귀속자에 따라 처분이 달라 항목을 내지 않음)
    dom = _fn(S.deemed_interest)(movements=LOAN["movements"], year_end="2025-12-31", rate_mode="당좌선택")
    assert "세무조정" not in dom


def test_expat_items_and_old_years():
    r = _fn(S.expat_cost_recharge)(**EXPAT)
    assert _items(r) == [("손금불산입", 118_000_000, "기타소득"), ("익금산입", 7_300_000, "임시유보")]
    old = _fn(S.expat_cost_recharge)(**{**EXPAT, "year": 2020})
    assert [a["소득처분"] for a in old["세무조정"]] == ["기타소득"] and any("2020 사업연도까지" in x for x in old["주의"])


def test_provision_dividend_cfc_items():
    p = _fn(S.provision_reserve_ledger)(**PROV, year=2025)
    assert _items(p) == [("손금불산입", 100 * M, "유보"), ("손금산입", 30 * M, "△유보")] and p["세무조정_사업연도"] == 2025
    assert "세무조정" not in _fn(S.provision_reserve_ledger)(**PROV)
    assert "error" in _fn(S.provision_reserve_ledger)(**PROV, year=2030)
    d = _fn(S.foreign_subsidiary_dividend)(**DIV)
    assert _items(d) == [("익금불산입", 190 * M, "기타"), ("손금불산입", 10 * M, "기타사외유출")]
    c = _fn(S.cfc_deemed_dividend)(**CFC)
    assert _items(c) == [("익금산입", 800 * M, "유보")] and any("제106조①2호" in x for x in c["주의"])
    none = _fn(S.cfc_deemed_dividend)(**{**CFC, "taxes_paid": [210 * M]})
    assert none["세무조정"] == []


def _all_items():
    out = [{"항목": "법인세비용", "종류": "법인세비용", "금액": 190 * M}]
    for f, a in ((S.arm_length_range, RANGE), (S.deemed_interest, LOAN), (S.expat_cost_recharge, EXPAT), (S.provision_reserve_ledger, {**PROV, "year": 2025}),
                 (S.foreign_subsidiary_dividend, DIV), (S.cfc_deemed_dividend, CFC)):
        out += _fn(f)(**a)["세무조정"]
    return out


def test_total_accepts_items_as_is():
    r = _fn(S.income_adjustment_total)(net_income=850 * M, items=_all_items())
    add = 190 * M + 243 * M + 38_564_383 + 118 * M + 7_300_000 + 100 * M + 10 * M + 800 * M
    sub = 30 * M + 190 * M
    assert r["결과"]["익금산입_손금불산입"] == add and r["결과"]["손금산입_익금불산입"] == sub
    assert r["결과"]["각사업연도소득금액"] == 850 * M + add - sub
    assert [a["소득처분"] for a in r["결과"]["세무조정"]].count("임시유보") == 3
    # 근거는 앞 도구가 준 것을 그대로
    assert any("제24조①" in p["근거"] for p in r["판단"])
    bad = _fn(S.income_adjustment_total)(net_income=0, items=[{"항목": "x", "조정": "손금산입", "금액": 1, "소득처분": "임시유보"}])
    assert "error" in bad and "익금산입·손금불산입에만" in bad["문제"][0]
    ok = _fn(S.income_adjustment_total)(net_income=0, items=[{"항목": "x", "조정": "익금산입", "금액": 5, "소득처분": "출자의증가"}, {"항목": "y", "조정": "손금산입", "금액": 2, "소득처분": "출자의 증가"}])
    assert [a["소득처분"] for a in ok["결과"]["세무조정"]] == ["출자의 증가", "출자의 증가"]


def test_form15_codes(tmp_path):
    items = _all_items() + [{"항목": "이전소득 배당 예", "조정": "익금산입", "금액": 1, "소득처분": "이전소득 배당"},
                            {"항목": "출자 증가 예", "조정": "익금산입", "금액": 2, "소득처분": "출자의 증가"}, {"항목": "출자 감소 예", "조정": "손금산입", "금액": 3, "소득처분": "출자의 증가"}]
    r = _fn(S.export_workbook)(title="t", calls=[{"label": "집계", "tool": "income_adjustment_total", "args": {"net_income": 850 * M, "items": items}}], output_dir=str(tmp_path))
    assert r["결과"]["오류_call"] == []
    ws = openpyxl.load_workbook(r["결과"]["파일"])[next(s for s in r["결과"]["시트"] if s.startswith("별지15"))]
    rows = [[c for c in row if c is not None] for row in ws.iter_rows(values_only=True)]
    def code(name):
        row = next(x for x in rows if name in x)
        i = row.index(name)
        return [str(v) for v in row[i + 1:i + 4]]
    assert "700" in code("정상가격 조정(국외특수관계인 거래)") and "임시유보" in code("정상가격 조정(국외특수관계인 거래)")
    assert "810" in code("이전소득 배당 예") and "820" in code("출자 증가 예") and "300" in code("출자 감소 예")
    assert "400" in code("특정외국법인 배당간주금액")
    # 별지 제50호서식(을): 충당부채 설정·사용은 한 과목으로, 임시유보는 유보 표에 넣지 않음
    ws50 = openpyxl.load_workbook(r["결과"]["파일"])[next(s for s in r["결과"]["시트"] if s.startswith("별지50"))]
    names = [row[0] for row in ws50.iter_rows(values_only=True) if row[0]]
    assert names.count("포인트 충당부채") == 1 and not any("설정" in str(n) or "정상가격" in str(n) for n in names)
