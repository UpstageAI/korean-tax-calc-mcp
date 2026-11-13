"""0.41.1 실무형 자료 점검에서 나온 것(2026-11-13, Claude).
- 연도별 세무조정 묶음이 임시유보·이전소득 배당을 받음(국조령 제22조~제25조 — 2021·2022·2023·2025·2026 시행본)
- 별지 제50호서식(을): 띄어쓰기가 다른 같은 과목을 한 줄로, 연도별 세무조정 묶음에 넣은 기초 유보를 ②기초잔액으로
- 업무무관 지급이자: 특수관계법인 대여금의 업무 관련성 해석 안내(법인세과-599, 법인세과-45, 조심2012서2206, 조심2016중1733, 서면인터넷방문상담2팀-1931 — 요지와 본문 대조, 조심2016중1733은 요지 기준)"""
import openpyxl
from korean_tax_calc_mcp import server as S

M = 1_000_000


def _fn(t):
    return getattr(t, "fn", t)


ADJ = [{"name": "정상가격 조정", "amount": 117_702_000, "kind": "익금산입", "disposition": "임시유보"},
       {"name": "포인트충당부채", "amount": 100 * M, "kind": "손금불산입", "disposition": "유보"},
       {"name": "포인트충당부채", "amount": 65 * M, "kind": "손금산입", "disposition": "유보"}]


def test_schedule_accepts_provisional_reserve():
    r = _fn(S.tax_adjustment_schedule)(years=[{"year": 2025, "book_income": 850 * M, "adjustments": ADJ}], opening_reserves=[{"name": "포인트충당부채", "amount": 67_500_000}])
    y = r["계산"]["연도별"][0]
    assert y["각사업연도소득"] == 850 * M + 117_702_000 + 100 * M - 65 * M
    assert y["임시유보"] == [{"항목": "정상가격 조정", "당기": 117_702_000}]
    assert y["유보_기말_합계"] == 102_500_000 and "출자의_증가" not in y          # 임시유보는 유보 표·출자의 증가에 넣지 않음
    assert any("임시유보" in p["항목"] and "90일" in p["결론"] for p in r["판단"])
    d = _fn(S.tax_adjustment_schedule)(years=[{"year": 2025, "book_income": 0, "adjustments": [{"name": "x", "amount": 5, "kind": "익금산입", "disposition": "이전소득 배당"}]}])
    assert d["계산"]["연도별"][0]["소득처분_사외유출"] == {"이전소득 배당": 5}
    old = _fn(S.tax_adjustment_schedule)(years=[{"year": 2020, "book_income": 0, "adjustments": [{"name": "x", "amount": 5, "kind": "익금산입", "disposition": "임시유보"}]}])
    assert "error" in old and "2021 사업연도부터" in old["문제"][0]
    bad = _fn(S.tax_adjustment_schedule)(years=[{"year": 2025, "book_income": 0, "adjustments": [{"name": "x", "amount": 5, "kind": "손금산입", "disposition": "임시유보"}]}])
    assert "error" in bad


def test_form50_groups_and_opening_balance(tmp_path):
    items = [{"항목": "포인트충당부채 설정", "조정": "손금불산입", "금액": 100 * M, "소득처분": "유보"}, {"항목": "포인트충당부채 사용", "조정": "손금산입", "금액": 65 * M, "소득처분": "△유보"},
             {"항목": "포인트충당부채 환입", "조정": "익금불산입", "금액": 10 * M, "소득처분": "△유보"}, {"항목": "특정외국법인 배당간주금액", "조정": "익금산입", "금액": 350 * M, "소득처분": "유보"}]
    calls = [{"label": "집계", "tool": "income_adjustment_total", "args": {"net_income": 850 * M, "items": items}},
             {"label": "묶음", "tool": "tax_adjustment_schedule", "args": {"years": [{"year": 2025, "book_income": 850 * M, "adjustments": ADJ}],
                                                                       "opening_reserves": [{"name": "포인트충당부채", "amount": 67_500_000}, {"name": "특정외국법인 배당간주금액", "amount": 900 * M}]}}]
    r = _fn(S.export_workbook)(title="t", calls=calls, output_dir=str(tmp_path))
    assert r["결과"]["오류_call"] == []
    ws = openpyxl.load_workbook(r["결과"]["파일"])[next(s for s in r["결과"]["시트"] if s.startswith("별지50"))]
    rows = {row[0]: row for row in ws.iter_rows(values_only=True) if row[0]}
    names = [n for n in rows if "포인트" in str(n)]
    assert names == ["포인트 충당부채"]                                   # 설정·사용·환입 한 줄
    assert 67_500_000 in rows["포인트 충당부채"] and 900 * M in rows["특정외국법인 배당간주금액"]   # ②기초잔액


def test_nonbusiness_advance_to_affiliate_warns():
    args = dict(loans=[S.Loan(interest=120 * M, principal=2_400 * M, days=365)], year=2025, fiscal_start="2025-01-01", fiscal_end="2025-12-31")
    r = _fn(S.nonbusiness_interest_disallowance)(**args, advances=[{"대상": "특수관계법인", "이름": "해외 자회사", "사유": "업무무관대여", "금액": 1_000 * M, "지급일": "2025-03-01"}])
    assert "error" not in r, r
    assert any("법인세과-599" in x and "조심2016중1733" in x and "판정하지 않음" in x for x in r["주의"])
    assert any("서면인터넷방문상담2팀-1931" in x for x in r["주의"])
    p = _fn(S.nonbusiness_interest_disallowance)(**args, advances=[{"대상": "대표이사", "이름": "대표", "사유": "업무무관대여", "금액": 100 * M, "지급일": "2025-03-01"}])
    assert "주의" not in p
