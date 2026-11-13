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


def test_server_instructions_point_to_export_workbook():
    # 0.41.2: 같은 요청에서 모델이 서식 엑셀을 직접 그린 경우가 있어 서버 안내문에 export_workbook 사용을 적음
    ins = S.mcp.instructions
    assert "export_workbook" in ins and "직접 만들지 말고" in ins and "review_notes" in ins


def test_summary_sheet(tmp_path):
    # 0.42.0: 맨 앞 '요약' 시트 — 세액 요약, 세무조정 항목(근거·계산 시트), call별 주요 값, 검토·확인 필요 사항
    div = dict(received_on="2025-06-30", ownership_ratio=1.0, held_months=16, dividend=200 * M, foreign_withholding=10 * M)
    items = [{"항목": "법인세비용", "종류": "법인세비용", "금액": 190 * M}] + _fn(S.foreign_subsidiary_dividend)(**div)["세무조정"]
    calls = [{"label": "일본 배당", "tool": "foreign_subsidiary_dividend", "args": div},
             {"label": "집계", "tool": "income_adjustment_total", "args": {"net_income": 850 * M, "items": items}},
             {"label": "세액", "tool": "corporate_tax", "args": {"base": 860 * M, "year": 2025}}]
    notes = [{"항목": "관계사 매출 대사", "내용": "본사 장부와 현지법인 매입이 다름 — 수출신고필증과 대조"}, "판매장려금 전표 확인"]
    r = _fn(S.export_workbook)(title="t", calls=calls, output_dir=str(tmp_path), company="가상㈜", period="2025.01.01 ~ 2025.12.31", review_notes=notes)
    assert r["결과"]["오류_call"] == [] and r["결과"]["시트"][:2] == ["요약", "목록"]
    wb = openpyxl.load_workbook(r["결과"]["파일"])
    assert wb.sheetnames[0] == "요약"
    cells = [[c for c in row if c is not None] for row in wb["요약"].iter_rows(values_only=True)]
    flat = [c for row in cells for c in row]
    assert 860 * M in flat and 850 * M in flat                               # 각 사업연도 소득금액, 당기순이익
    tax = _fn(S.corporate_tax)(base=860 * M, year=2025)["결과"]["산출세액"]
    assert tax in flat
    row = next(x for x in cells if "외국자회사 수입배당금" in x)
    assert "익금불산입" in row and 190 * M in row and "기타" in row and any("제18조의4" in str(c) for c in row) and any(str(c).startswith("계산 1") for c in row)
    row = next(x for x in cells if "법인세비용" in x)
    assert any(str(c) == "계산 2" for c in row)                              # 금액이 같은 익금불산입(1.9억) 시트로 잘못 잇지 않음
    assert any("관계사 매출 대사" in x for x in cells) and any("판매장려금 전표 확인" in str(c) for c in flat)
    # 검토 의견을 주지 않으면 안내 한 줄, 소득금액 집계가 없어도 요약은 나옴
    r2 = _fn(S.export_workbook)(title="t2", calls=calls[:1], output_dir=str(tmp_path))
    f2 = [c for row in openpyxl.load_workbook(r2["결과"]["파일"])["요약"].iter_rows(values_only=True) for c in row if c is not None]
    assert any("입력된 검토 의견 없음" in str(c) for c in f2) and "세액 요약" not in f2 and "계산 결과 한눈에" in f2
    # steps 배치는 종전 그대로(자체 요약 시트)
    r3 = _fn(S.export_workbook)(title="t3", calls=calls[:1], output_dir=str(tmp_path), layout="steps")
    assert r3["결과"]["시트"].count("요약") == 1
