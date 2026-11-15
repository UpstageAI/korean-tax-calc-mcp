"""export_workbook 통합 문서(scenarios·sources·issues) — 요약·입력·출처·시나리오 시트·쟁점 목록. 작성 Claude 2026-11-15.

- 선택 입력이 없으면 기존 출력 그대로(시트·칸·결과 키).
- 시나리오 시트의 수식을 LibreOffice로 다시 계산한 값이 계산 도구 결과와 원 단위로 같다
  (nonresident_withholding 총액·순액 역산·지방소득세 부담·조약 대상조세 포함, withholding_late_payment_penalty 종전·개정·이율 변경 구간).
- 대조한 원문: 국세기본법 제47조의5제1항(2026.10.2. 시행본 — 법률 제21212호로 제2호 '납부고지일(납부고지일 전에 납부한 경우에는 그 납부일)의
  전날까지', 2026.7.1. 시행; 2026.6.2. 시행본 제2호 '법정납부기한의 다음 날부터 납부일까지'), 법제처 국가법령정보 공동활용 조회.
- 뒤 시트는 detail로 고른다: compact(기본 — 앞 시트 + '계산 상세' 한 장), forms(+ 신고 서식), full(전부).
- 납부고지 후 가산세 틀: 국세기본법 제47조의5제1항제3호·제4호·제4항·제5항(법률 제21212호, 2026.7.1. 시행), 시행령 제27조의4제2항·제3항,
  종전 제2호(지정납부기한 후 일수분)와 부칙 제4조 — 숫자·근거는 도구(withholding_late_payment_penalty)가 쓰는 것 그대로이고 수식 재계산 값을 도구 결과와 대조.
- 사례 값은 모두 지어낸 값(특정 사례와 무관).
"""
import shutil
import subprocess

import openpyxl
import pytest

from korean_tax_calc_mcp import server as S
from tests._helpers import call as c
from tests.test_export_workbook_c import ENT

NAVY, BAND, BLUE, GREEN, YELLOW = "001F3864", "00D9E1F2", "000000FF", "00008000", "00FFFF00"

DIV = dict(income_kind="배당", recipient_type="법인", residence_country="일본", year=2025)          # 조약 대상조세에 지방소득세 포함
FEE = dict(income_kind="인적용역", recipient_type="개인", residence_country="독일", year=2024, service_location="국내")
INT = dict(income_kind="이자", recipient_type="법인", residence_country="싱가포르", year=2023)
CALLS = [
    {"label": "배당 총액", "tool": "nonresident_withholding", "args": {**DIV, "amount": 73_456_789, "treaty_rate": 0.10}},
    {"label": "배당 순액", "tool": "nonresident_withholding", "args": {**DIV, "amount": 73_456_789, "treaty_rate": 0.10, "net_of_tax": True}},
    {"label": "용역 순액+지방세", "tool": "nonresident_withholding", "args": {**FEE, "amount": 12_345_670, "payer_bears_local_tax": True}},
    {"label": "이자 조약없음", "tool": "nonresident_withholding", "args": {**INT, "amount": 5_550_001}},
    {"label": "이자 조약", "tool": "nonresident_withholding", "args": {**INT, "amount": 5_550_001, "treaty_rate": 0.12, "treaty_includes_local_tax": False,
                                                                 "net_of_tax": True, "payer_bears_local_tax": True}},
    {"label": "가산세 종전", "tool": "withholding_late_payment_penalty", "args": dict(unpaid_tax=1_110_000, due="2024-03-11", until="2024-05-20")},
    {"label": "가산세 개정", "tool": "withholding_late_payment_penalty", "args": dict(unpaid_tax=1_110_000, due="2026-08-10", until="2026-09-25")},
    {"label": "가산세 이율변경", "tool": "withholding_late_payment_penalty", "args": dict(unpaid_tax=987_650, due="2022-01-10", until="2022-03-31")},
    {"label": "가산세 한도", "tool": "withholding_late_payment_penalty", "args": dict(unpaid_tax=2_222_220, due="2023-02-10", until="2025-02-10")},
    {"label": "기업업무추진비", "tool": "entertainment_adjustment", "args": ENT},
    {"label": "간주임대료", "tool": "vat_deemed_rent", "args": dict(deposit=80_000_000, days=181, period="2025-1")},
]
SCENARIOS = [
    {"sheet": "배당", "title": "배당 원천징수", "subtitle": "두 약정 비교", "heading": "1. 약정별 세액",
     "columns": [{"call": "배당 총액", "heading": "A 총액 약정"}, {"call": 2, "heading": "B 순액 약정"}],
     "notes": {"원천징수세액": "관할 세무서 납부", "없는 줄": "x"}, "summary_note": "납부기한 한 줄"},
    {"sheet": "용역·이자", "heading": "용역", "columns": ["용역 순액+지방세"]},
    {"sheet": "용역·이자", "heading": "이자", "columns": [{"call": "이자 조약없음", "heading": "조약 없음"}, {"call": "이자 조약", "heading": "조약 12%"}]},
    {"sheet": "가산세", "heading": "납부지연", "columns": ["가산세 종전", "가산세 개정", "가산세 이율변경", "가산세 한도"]},
]
SOURCES = [
    {"call": "배당 총액", "arg": "amount", "source": "이사회 의사록 제7호"},
    {"call": "배당 순액", "arg": "amount", "source": "이사회 의사록 제7호"},
    {"call": "가산세 개정", "arg": "until", "source": "납부 예정일", "assumption": True},
]
ISSUES = [{"no": 1, "issue": "신청서 수령일", "finding": "지급일 뒤 수령", "risk": "High", "action": "수정신고"},
          {"번호": 2, "쟁점": "=증빙 누락", "발견": "거래명세서 없음", "위험도": "낮음", "조치": "보완"},
          {"issue": "기타", "finding": "", "risk": "", "action": ""}]


def _export(tmp_path, name="통합", **kw):
    args = {"title": name, "calls": CALLS, "output_dir": str(tmp_path), "scenarios": SCENARIOS, "sources": SOURCES, "issues": ISSUES, **kw}
    r = c("export_workbook", args)
    assert "error" not in r, r
    return r


def _dump(path):
    wb = openpyxl.load_workbook(path)
    return {ws.title: {cell.coordinate: (cell.value, cell.number_format, cell.font.b, cell.fill.fgColor.rgb if cell.fill.fill_type else None)
                       for row in ws.iter_rows() for cell in row if cell.value is not None} for ws in wb.worksheets}


def _find(ws, text, col=1):
    return next(r for r in range(1, ws.max_row + 1) if ws.cell(r, col).value == text)


# ── 선택 입력이 없으면 기존 출력 그대로 ───────────────────────────────────────
@pytest.mark.parametrize("layout", ["forms", "steps"])
@pytest.mark.parametrize("lang", ["ko", "en"])
def test_without_new_inputs_output_is_unchanged(tmp_path, layout, lang):
    base = {"calls": CALLS[:3] + CALLS[5:6] + CALLS[9:], "output_dir": str(tmp_path), "layout": layout, "lang": lang}
    a = c("export_workbook", {"title": "같은 제목", "filename": "a", **base})
    b = c("export_workbook", {"title": "같은 제목", "filename": "b", **base, "scenarios": [], "sources": None, "issues": ""})
    assert "통합_시트" not in a["결과"] and "통합_시트" not in b["결과"]
    assert a["결과"]["시트"] == b["결과"]["시트"] and ("warnings" in a) == (lang == "en")
    assert a["결과"]["시트"][0] == ("Summary (요약)" if lang == "en" else "요약")
    da, db = _dump(a["결과"]["파일"]), _dump(b["결과"]["파일"])
    assert da == db
    wb = openpyxl.load_workbook(a["결과"]["파일"])
    assert not any("완성된 .xlsx 생성" in str(cell.value) for ws in wb for row in ws.iter_rows() for cell in row)   # 공통 꼬리는 엑셀에 싣지 않음


# ── 시트 구성·서식 ────────────────────────────────────────────────────────
def test_sheets_order_and_result_keys(tmp_path):
    r = _export(tmp_path, detail="full")
    front = ["요약", "입력·출처", "배당", "용역·이자", "가산세", "기업업무추진비", "간주임대료", "쟁점 목록"]
    assert r["결과"]["통합_시트"] == front and r["결과"]["시트"][:len(front)] == front
    wb = openpyxl.load_workbook(r["결과"]["파일"])
    assert wb.sheetnames[:len(front)] == front and sorted(wb.sheetnames) == sorted(r["결과"]["시트"])
    assert "호출 요약" in wb.sheetnames and "입력·가정" in wb.sheetnames and "판단·근거" in wb.sheetnames
    assert any(n.startswith("원천 별지23") for n in wb.sheetnames)        # 서식 시트는 그대로 뒤에
    assert any("없는 줄" in w for w in r["warnings"])                     # 맞는 줄이 없는 notes는 알림


def test_scenario_sheet_side_by_side_with_basis_column(tmp_path):
    wb = openpyxl.load_workbook(_export(tmp_path)["결과"]["파일"])
    ws = wb["배당"]
    assert ws["A1"].value == "배당 원천징수" and ws["A1"].font.b and ws["A1"].font.sz == 14
    assert ws["A2"].value == "두 약정 비교" and ws["A2"].font.i
    assert ws.freeze_panes == "A4" and ws.sheet_view.showGridLines is False
    assert ws["A4"].value == "1. 약정별 세액" and ws["A4"].fill.fgColor.rgb == BAND
    assert [ws.cell(5, j).value for j in (2, 3, 4)] == ["A 총액 약정", "B 순액 약정", "근거 · 메모"]
    assert ws["B5"].fill.fgColor.rgb == NAVY and ws["B5"].font.color.rgb == "00FFFFFF"
    assert (ws.column_dimensions["A"].width, ws.column_dimensions["B"].width, ws.column_dimensions["D"].width) == (58, 22, 70)
    r_amt, r_tax, r_base = _find(ws, "지급액(순액 약정이면 약정 순액)"), _find(ws, "원천징수세액(법인세)"), _find(ws, "과세표준")
    # 입력은 '입력·출처' 칸을 가리키는 초록 링크, 계산 줄은 그 시트 칸을 가리키는 수식(숫자를 박지 않음)
    assert ws.cell(r_amt, 2).value.startswith("='입력·출처'!$B$") and ws.cell(r_amt, 2).font.color.rgb == GREEN
    assert ws.cell(r_amt, 2).value == ws.cell(r_amt, 3).value          # 같은 값·같은 출처는 입력 한 칸을 함께 씀
    assert ws.cell(r_base, 2).value == f"=B{r_amt}" and "ROUNDDOWN" in ws.cell(r_base, 3).value
    for j in (2, 3):
        f = ws.cell(r_tax, j).value
        assert f.startswith("=ROUNDDOWN(") and "73456789" not in f and ws.cell(r_tax, j).fill.fgColor.rgb == YELLOW
    assert ws.cell(r_tax, 4).value.startswith("관할 세무서 납부 — ") and ws.cell(r_tax, 4).font.i
    r_app = _find(ws, "적용세율")
    assert "법인세법 제98조" in ws.cell(r_app, 4).value and "MIN(" in ws.cell(r_app, 2).value   # 근거 조문은 도구 문구 그대로
    r_chk = _find(ws, "도구 값 대조(수식 = 계산 도구 결과)")
    assert all(ws.cell(r_chk, j).value.startswith("=IF(AND(ROUND(") and '"일치"' in ws.cell(r_chk, j).value for j in (2, 3))
    # 같은 sheet 이름의 블록은 한 시트에 차례로
    ws2 = wb["용역·이자"]
    assert _find(ws2, "용역") < _find(ws2, "이자")


def test_inputs_sheet_sources_and_colour_rules(tmp_path):
    wb = openpyxl.load_workbook(_export(tmp_path)["결과"]["파일"])
    ws = wb["입력·출처"]
    assert ws["A1"].value == "입력과 출처" and "파랑 = 입력값" in ws["A2"].value
    assert [ws.cell(4, j).value for j in (1, 2, 3)] == ["항목", "값", "출처"] and ws.freeze_panes == "A5"
    assert ws["A5"].value == "법정 세율·이율"
    rows = {ws.cell(r, 1).value: r for r in range(1, ws.max_row + 1) if ws.cell(r, 1).value}
    r_rate = rows["원천징수 납부지연가산세 — 미납세액의 3%"]
    assert ws.cell(r_rate, 2).value == 0.03 and ws.cell(r_rate, 3).value == "국세기본법 제47조의5제1항제1호"
    assert ws.cell(rows["국내 원천징수세율 — 배당"], 3).value.startswith("법인세법 제98조")
    amt = [r for r in range(1, ws.max_row + 1) if ws.cell(r, 2).value == 73_456_789]
    assert len(amt) == 1 and ws.cell(amt[0], 3).value == "이사회 의사록 제7호" and ws.cell(amt[0], 2).font.color.rgb == BLUE
    assume = next(r for r in range(1, ws.max_row + 1) if ws.cell(r, 3).value == "납부 예정일")
    assert ws.cell(assume, 2).fill.fgColor.rgb == YELLOW and ws.cell(assume, 2).number_format == "yyyy-mm-dd"
    assert ws.cell(assume, 2).value.date().isoformat() == "2026-09-25"
    # 열마다 값이 다른 입력은 열 이름을 붙여 따로
    assert "미납·과소납부 세액 — 가산세 종전" in rows and "미납·과소납부 세액 — 가산세 이율변경" in rows


def test_summary_links_to_scenario_cells(tmp_path):
    wb = openpyxl.load_workbook(_export(tmp_path)["결과"]["파일"])
    ws = wb["요약"]
    # 0.56.0: 요약은 핵심 숫자 표 한 장 — 블록마다 권고 열(없으면 첫 열)의 결과 줄, 그 아래 나머지 열의 합계 줄. 시나리오 블록을 되풀이하지 않음
    assert ws["A1"].value == "통합 — 요약" and ws.freeze_panes == "A5"
    assert [ws.cell(4, j).value for j in (1, 2, 3, 4)] == ["핵심 숫자", "금액(원)", "계산 위치", "메모"]
    r_tot = _find(ws, "배당 — 1. 약정별 세액 — 합계 (A 총액 약정)")
    assert ws.cell(r_tot, 2).value.startswith("='배당'!$B$") and ws.cell(r_tot, 2).font.color.rgb == GREEN
    assert ws.cell(r_tot, 1).font.b and ws.cell(r_tot, 2).font.b and ws.cell(r_tot, 2).fill.fgColor.rgb == YELLOW      # 합계 줄 강조
    assert ws.cell(r_tot, 3).value == "배당" and ws.cell(r_tot, 3).hyperlink.location == "'배당'!" + ws.cell(r_tot, 2).value.split("!")[1].replace("$", "")
    r_b = _find(ws, "배당 — 1. 약정별 세액 — 합계 (B 순액 약정)")
    assert r_b > r_tot and ws.cell(r_b, 2).value.startswith("='배당'!$C$") and not ws.cell(r_b, 1).font.b
    r_first = _find(ws, "배당 — 1. 약정별 세액 — 과세표준 (A 총액 약정)")
    assert ws.cell(r_first, 4).value == "납부기한 한 줄" and ws.cell(r_first, 4).font.i
    assert ws.max_row <= 40 and ws.page_setup.fitToHeight == 1 and ws.print_area      # 블록 5개·call 11개(같은 입력의 0.55.1 요약은 52줄)
    texts = [ws.cell(k, 1).value for k in range(1, ws.max_row + 1) if ws.cell(k, 1).value]
    assert "쟁점 3건 — '쟁점 목록' 시트" in texts and "High 1 · 낮음 1" in texts
    assert any(t.startswith("색 규칙: 파랑 = 입력, 초록 = 다른 시트 링크, 검정 = 수식, 노랑 = 핵심 결과·가정") for t in texts)
    assert not any(isinstance(cell.value, (int, float)) for row in ws.iter_rows() for cell in row)     # 숫자는 모두 링크


def test_issues_log_shows_rows_as_given(tmp_path):
    wb = openpyxl.load_workbook(_export(tmp_path)["결과"]["파일"])
    ws = wb["쟁점 목록"]
    assert [ws.cell(4, j).value for j in range(1, 6)] == ["#", "쟁점", "발견", "위험도", "조치"] and ws.freeze_panes == "A5"
    assert [[ws.cell(r, j).value for j in range(1, 6)] for r in (5, 6, 7)] == [
        [1, "신청서 수령일", "지급일 뒤 수령", "High", "수정신고"], [2, "=증빙 누락", "거래명세서 없음", "낮음", "보완"], [3, "기타", None, None, None]]
    assert ws.max_row == 7 and ws["B6"].data_type == "s"                 # 받은 글만, '='로 시작해도 글자 그대로
    assert ws["D5"].fill.fgColor.rgb == "00F8CBAD" and ws["D6"].fill.fgColor.rgb == "00E2EFDA" and ws["D7"].fill.fill_type is None
    assert [ws.column_dimensions[k].width for k in "ABCDE"] == [5, 34, 66, 12, 60]


def test_english_view(tmp_path):
    r = _export(tmp_path, name="Workings", lang="en", detail="full")
    assert r["결과"]["통합_시트"] == ["Summary", "Inputs", "배당", "용역·이자", "가산세", "기업업무추진비", "간주임대료", "Issues Log"]
    wb = openpyxl.load_workbook(r["결과"]["파일"])
    assert {"Call summary (호출 요약)", "Call inputs (입력·가정)", "Judgements (판단·근거)", "Calc 1 (계산 1)"} <= set(wb.sheetnames)
    ws = wb["배당"]
    labels = [ws.cell(k, 1).value for k in range(1, ws.max_row + 1) if ws.cell(k, 1).value]
    for want in ("Withholding tax base", "Corporate tax to withhold", "Local income tax to withhold", "Total Korean tax",
                 "Check: formulas agree with the calculation tool"):
        assert want in labels, want
    assert ws["D5"].value == "Basis / note"
    assert wb["Summary"]["A1"].value == "Workings — summary" and wb["Inputs"]["A1"].value == "Inputs and sources"
    assert [wb["Issues Log"].cell(4, j).value for j in range(1, 6)] == ["#", "Issue", "Finding", "Risk", "Action"]
    # 결과에 계산식이 있는 도구는 용어집 표기(English (국문))
    assert "Excess over limit (한도초과)" in [wb["기업업무추진비"].cell(k, 1).value for k in range(1, 60)]
    # 이름이 바뀐 '입력·가정' 시트를 가리키는 정의된 이름이 끊기지 않음
    assert all("Call inputs (입력·가정)" in dn.attr_text or "Calc " in dn.attr_text for dn in wb.defined_names.values())
    # 'Call summary'의 영문 시트 안내 표가 앞에 더한 시트까지 순서대로 나열
    ws = wb["Call summary (호출 요약)"]
    k = _find(ws, "Sheets in this workbook") + 2
    listed = [ws.cell(j, 2).value for j in range(k, k + len(wb.sheetnames))]
    assert listed == wb.sheetnames
    assert "key figures linked from the scenario sheets" in ws.cell(k, 3).value and "source column" in ws.cell(k + 1, 3).value
    assert "calls side by side" in ws.cell(k + 2, 3).value and "issues log" in ws.cell(k + 7, 3).value


def test_input_linked_to_another_calls_result(tmp_path):
    need = c("nonresident_withholding", CALLS[3]["args"])["결과"]["원천징수세액"]
    paid = 300_000
    calls = [CALLS[3], {"label": "부족분 가산세", "tool": "withholding_late_payment_penalty",
                        "args": dict(unpaid_tax=need - paid, due="2023-11-10", until="2024-01-31")}]
    src = [{"call": "부족분 가산세", "arg": "unpaid_tax", "source": "정당 세액 − 기납부", "from_call": 1, "from_row": "원천징수세액",
            "less": paid, "less_label": "기납부 세액", "less_source": "납부서"}]
    r = c("export_workbook", {"title": "링크", "calls": calls, "output_dir": str(tmp_path), "sources": src})
    ws = openpyxl.load_workbook(r["결과"]["파일"])["입력·출처"]
    row = next(k for k in range(1, ws.max_row + 1) if ws.cell(k, 3).value == "정당 세액 − 기납부")
    assert ws.cell(row - 1, 1).value == "기납부 세액" and ws.cell(row - 1, 2).value == paid and ws.cell(row - 1, 3).value == "납부서"
    assert ws.cell(row, 2).value.startswith("='계산'!$B$") and ws.cell(row, 2).value.endswith(f"-$B${row - 1}")
    assert "warnings" not in r
    # 도구에 넣은 값과 다르면 잇지 않고 알림
    src[0]["less"] = paid + 1
    r2 = c("export_workbook", {"title": "링크2", "calls": calls, "output_dir": str(tmp_path), "sources": src})
    ws2 = openpyxl.load_workbook(r2["결과"]["파일"])["입력·출처"]
    assert ws2.cell(row, 2).value == need - paid and any("연결하지 않음" in w for w in r2["warnings"])


def test_form_inputs_follow_the_new_cells(tmp_path):
    wb = openpyxl.load_workbook(_export(tmp_path, detail="full")["결과"]["파일"])
    ws = wb["입력·가정"]
    linked = [cell.value for row in ws.iter_rows() for cell in row if isinstance(cell.value, str) and cell.value.startswith("='배당'!")]
    assert len(linked) == 4                                              # 두 call의 지급액·적용세율 → 서식 칸이 새 칸을 따라감
    assert wb.defined_names["호출1_지급액"].attr_text.startswith("'입력·가정'!")


def test_notice_path_and_error_call_do_not_break(tmp_path):
    calls = [{"label": "고지 후", "tool": "withholding_late_payment_penalty",
              "args": dict(unpaid_tax=3_000_000, due="2024-02-13", until="2024-06-03", notice_due="2024-06-30", paid_on="2024-08-01")},
             {"label": "오류", "tool": "corporate_tax", "args": dict(base=1, year=1990)}]
    r = c("export_workbook", {"title": "예외", "calls": calls, "output_dir": str(tmp_path),
                              "scenarios": [{"sheet": "예외", "columns": ["고지 후"]}, {"sheet": "예외", "heading": "오류 call", "columns": ["오류"]}]})
    assert r["결과"]["오류_call"] == ["오류"] and r["결과"]["통합_시트"] == ["요약", "입력·출처", "예외"]
    ws = openpyxl.load_workbook(r["결과"]["파일"])["예외"]
    assert any(isinstance(ws.cell(k, 2).value, str) and ws.cell(k, 2).value.startswith("=") for k in range(1, ws.max_row + 1))


@pytest.mark.parametrize("kw,msg", [
    ({"scenarios": [{"columns": ["없는 call"]}]}, "찾지 못함"),
    ({"scenarios": [{"columns": ["배당 총액", "기업업무추진비"]}]}, "같은 도구"),
    ({"scenarios": [{"columns": ["배당 총액"]}, {"columns": [1]}]}, "두 번"),
    ({"scenarios": "[{broken"}, "JSON"),
    ({"sources": [{"call": "배당 총액"}]}, "sources[1]"),
    ({"sources": [{"call": 99, "arg": "amount"}]}, "찾지 못함"),
    ({"issues": ["글"]}, "issues[1]"),
])
def test_bad_optional_inputs_are_reported(tmp_path, kw, msg):
    r = c("export_workbook", {"title": "x", "calls": CALLS, "output_dir": str(tmp_path), **kw})
    assert msg in r["error"] and not list(tmp_path.glob("*.xlsx"))


def test_json_string_inputs(tmp_path):
    import json
    r = c("export_workbook", {"title": "문자열", "calls": CALLS, "output_dir": str(tmp_path), "scenarios": json.dumps(SCENARIOS, ensure_ascii=False),
                              "sources": json.dumps(SOURCES, ensure_ascii=False), "issues": json.dumps(ISSUES, ensure_ascii=False)})
    assert r["결과"]["통합_시트"][:3] == ["요약", "입력·출처", "배당"]


# ── 수식 재계산 = 도구 결과(원 단위) ──────────────────────────────────────────
def _recalc(path, out):
    prof = out.parent / f"lo_{out.name}"          # 실행마다 빈 프로필 — 동시에 도는 LibreOffice와 부딪히지 않게
    subprocess.run(["soffice", f"-env:UserInstallation=file://{prof}", "--headless", "--calc", "--convert-to", "xlsx", "--outdir", str(out), str(path)],
                   check=True, capture_output=True, timeout=180)
    return openpyxl.load_workbook(next(out.glob("*.xlsx")), data_only=True)


def _col_values(ws, col):
    return {ws.cell(r, 1).value: ws.cell(r, col).value for r in range(1, ws.max_row + 1) if ws.cell(r, 1).value}


@pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice 없음")
@pytest.mark.parametrize("lang", ["ko", "en"])
def test_scenario_formulas_recalculate_to_tool_values(tmp_path, lang):
    r = _export(tmp_path, name=f"recalc_{lang}", lang=lang, detail="full")
    wb = _recalc(r["결과"]["파일"], tmp_path / f"out_{lang}")
    ok, ng = ("Match (일치)", "Check (확인 필요)") if lang == "en" else ("일치", "확인 필요")
    front = r["결과"]["통합_시트"]
    checks = [cell.value for n in front for row in wb[n].iter_rows() for cell in row if cell.value in (ok, ng)]
    assert len(checks) == 10 and set(checks) == {ok}                       # 원천징수 5열 + 가산세 4열 + 기업업무추진비 1열
    errs = [(n, cell.coordinate, cell.value) for n in wb.sheetnames for row in wb[n].iter_rows() for cell in row
            if isinstance(cell.value, str) and (cell.value.startswith("#") and len(cell.value) > 1 or cell.value.startswith("Err:"))]
    assert not errs, errs
    tax, loc, tot, base = (("Corporate tax to withhold", "Local income tax to withhold", "Total Korean tax", "Withholding tax base") if lang == "en"
                           else ("원천징수세액(법인세)", "지방소득세(특별징수)", "합계", "과세표준"))
    res = [c(x["tool"], x["args"])["결과"] for x in CALLS]
    for sheet, col, i in (("배당", 2, 0), ("배당", 3, 1), ("용역·이자", 2, 3), ("용역·이자", 3, 4)):
        ws = wb[sheet]
        rows = [k for k in range(1, ws.max_row + 1) if ws.cell(k, 1).value == tot]
        k = rows[-1] if (sheet, col) in (("용역·이자", 2), ("용역·이자", 3)) else rows[0]
        got = {ws.cell(j, 1).value: ws.cell(j, col).value for j in range(k - 6, k + 1)}
        assert (got[tax], got[loc], got[tot]) == (res[i]["원천징수세액"], res[i]["지방소득세"], res[i]["합계"]), (sheet, col)
        if "과세표준" in res[i]:
            assert got[base] == res[i]["과세표준"]
    # 개인 수취인(소득세) 블록 — 순액 + 지방소득세 부담
    ws = wb["용역·이자"]
    v = _col_values(ws, 2)
    assert v["Income tax to withhold" if lang == "en" else "원천징수세액(소득세)"] == res[2]["원천징수세액"]
    # 가산세 4열: 종전(납부일까지)·개정(납부일 전날까지)·이율 변경 구간·10% 한도
    ws = wb["가산세"]
    pen = "Penalty" if lang == "en" else "가산세"
    k = max(j for j in range(1, ws.max_row + 1) if ws.cell(j, 1).value == pen)
    assert [ws.cell(k, j).value for j in (2, 3, 4, 5)] == [res[i]["가산세"] for i in (5, 6, 7, 8)]
    to_day, before = (("Days (day after the statutory due date to the payment date)", "Days (day after the statutory due date to the day before payment)")
                      if lang == "en" else ("일수(법정납부기한 다음 날부터 납부일까지)", "일수(법정납부기한 다음 날부터 납부일의 전날까지)"))
    assert ws.cell(_find(ws, to_day), 2).value == res[5]["일수"] == 70          # 종전: 2024.3.12.~5.20.
    assert ws.cell(_find(ws, before), 3).value == res[6]["일수"] == 45          # 개정: 2026.8.11.~9.24.(납부일 9.25.의 전날)
    assert ws.cell(_find(ws, to_day), 5).value == res[8]["일수"] == 731 and res[8]["한도_적용"] is True and res[7]["일수"] == 80
    # 요약 링크·서식 칸도 같은 값
    summ = wb[front[0]]
    assert res[1]["합계"] in [cell.value for row in summ.iter_rows() for cell in row]
    form_checks = [cell.value for n in wb.sheetnames if n.startswith("원천 별지23") for row in wb[n].iter_rows() for cell in row
                   if cell.value in ("일치", "확인 필요")]
    assert form_checks and set(form_checks) == {"일치"}
    assert [cell.value for row in wb["기업업무추진비"].iter_rows() for cell in row if cell.value == res[9]["한도초과"]]


@pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice 없음")
def test_changing_an_input_cell_recalculates_like_the_tool(tmp_path):
    """입력·출처 칸의 값을 바꾸면 시나리오 시트·요약이 따라 바뀌고, 그 값은 바꾼 입력으로 도구를 다시 부른 결과와 같다."""
    r = _export(tmp_path, name="live")
    wb = openpyxl.load_workbook(r["결과"]["파일"])
    ws = wb["입력·출처"]
    new_amt, new_until = 91_234_560, "2026-10-30"
    for row in ws.iter_rows(min_col=2, max_col=2):
        cell = row[0]
        if cell.value == 73_456_789:
            cell.value = new_amt
        elif cell.number_format == "yyyy-mm-dd" and cell.value.date().isoformat() == "2026-09-25":
            cell.value = cell.value.replace(month=10, day=30)
    edited = tmp_path / "edited.xlsx"
    wb.save(edited)
    out = _recalc(edited, tmp_path / "out")
    a = c("nonresident_withholding", {**CALLS[0]["args"], "amount": new_amt})["결과"]
    b = c("nonresident_withholding", {**CALLS[1]["args"], "amount": new_amt})["결과"]
    p = c("withholding_late_payment_penalty", {**CALLS[6]["args"], "until": new_until})["결과"]
    ws = out["배당"]
    k = next(j for j in range(1, ws.max_row + 1) if ws.cell(j, 1).value == "합계")
    assert (ws.cell(k, 2).value, ws.cell(k, 3).value) == (a["합계"], b["합계"])
    assert ws.cell(_find(ws, "과세표준"), 3).value == b["과세표준"]
    ws = out["가산세"]
    k = max(j for j in range(1, ws.max_row + 1) if ws.cell(j, 1).value == "가산세")
    assert ws.cell(k, 3).value == p["가산세"]
    assert a["합계"] in [cell.value for row in out["요약"].iter_rows() for cell in row]
    # 바꾼 값은 도구 값과 달라졌으므로 대조 줄이 알려 준다
    assert ws.cell(_find(ws, "도구 값 대조(수식 = 계산 도구 결과)"), 3).value == "확인 필요"


# ── 쓰이게 만들기: 설명 첫 문장·서버 안내문·공통 꼬리·검색어 ─────────────────────
def test_description_first_sentence_says_statutory_forms_and_where():
    tool = next(t for t in S.mcp._tool_manager.list_tools() if t.name == "export_workbook")
    first = tool.description.splitlines()[0]
    assert first.startswith("Builds Korean statutory return forms (법정서식 · 별지 서식) as an Excel (.xlsx) file")      # 0.57.0: 법정서식 전용
    for phrase in ("output_dir", "absolute path", "verify_workbook", "Not needed for a general workings workbook"):
        assert phrase in first, phrase
    assert "언제:" in tool.description and "입력:" in tool.description
    for name in ("scenarios", "sources", "issues", "extra_sheets", "actions", "key_figures"):
        assert name in tool.parameters["properties"] and f"{name}" in tool.description
    assert len(S.mcp._tool_manager.list_tools()) == 140


def test_instructions_tell_to_build_then_verify_for_workings():
    ins = S.mcp.instructions
    assert "엑셀·스프레드시트·계산 근거·workings를 원하면" in ins and "verify_workbook" in ins and "extra_sheets" not in ins
    assert "저장한 뒤 verify_workbook으로 금액 칸을 대조한다" in ins and "then run verify_workbook" in ins      # 0.57.0: 직접 짜고 대조가 기본 길
    for gone in ("직접 만들지", "do not write your own", "instead of writing"):      # 0.56.0: 금지 문구는 지움 — 직접 짜도 되고 대조로 받침
        assert gone not in ins, gone


def test_calc_results_carry_excel_tail_but_not_export_or_find():
    r = S.corporate_tax(base=123_000_000, year=2024)
    assert list(r)[-2:] == ["호출_id", "엑셀"] and f'call: "{r["호출_id"]}"' in r["엑셀"] and "법정서식(별지 서식) 엑셀이 필요할 때만 export_workbook" in r["엑셀"]
    assert "엑셀" not in S.find_tool(query="법인세") and "엑셀" not in S.corporate_tax(base=1, year=1990)


def test_export_result_has_no_tail(tmp_path):
    r = c("export_workbook", {"title": "t", "calls": CALLS[10:], "output_dir": str(tmp_path)})
    assert "엑셀" not in r and r["결과"]["파일"].endswith(".xlsx")


@pytest.mark.parametrize("query", ["Excel workings", "xlsx", "spreadsheet", "workings file", "엑셀", "계산 근거", "엑셀로 계산 근거 정리"])
def test_find_tool_reaches_the_workbook_tools(query):
    got = [x["도구"] for x in S.find_tool(query=query)["결과"]["후보"]]
    assert got[0] == "verify_workbook" and "export_workbook" in got[:2]      # 0.57.0: 계산 근거 엑셀은 직접 짠 뒤 대조가 먼저


@pytest.mark.parametrize("query", ["법정서식 엑셀", "별지 서식", "신고 서식 엑셀로", "statutory form workbook"])
def test_find_tool_reaches_export_workbook_for_statutory_forms(query):
    assert S.find_tool(query=query)["결과"]["후보"][0]["도구"] == "export_workbook"


def test_llms_txt_has_search_words():
    from pathlib import Path
    text = (Path(__file__).resolve().parents[1] / "llms.txt").read_text(encoding="utf-8")
    line = next(ln for ln in text.splitlines() if "xlsx" in ln and "verify_workbook" in ln)
    for w in ("Excel", "xlsx", "spreadsheet", "workings", "엑셀", "계산 근거"):
        assert w in line, w


# ── 검산: 원천징수 납부지연가산세 일수의 끝날(국세기본법 제47조의5제1항제2호) ───────────
@pytest.mark.parametrize("due,until,days", [
    ("2026-05-11", "2026-06-30", 50),      # 종전: 다음 날(5.12.)부터 납부일(6.30.)까지
    ("2026-05-11", "2026-07-01", 50),      # 개정(2026.7.1. 시행): 납부일의 전날(6.30.)까지 — 하루 늦게 내도 일수 같음
    ("2026-07-10", "2026-07-11", 0),       # 기한 다음 날 납부: 전날까지 0일, 3%분만
    ("2026-07-10", "2026-07-10", 0),       # 기한 당일 납부: 가산세 없음
])
def test_withholding_penalty_day_count_boundary(due, until, days):
    r = S.withholding_late_payment_penalty(unpaid_tax=1_000_000, due=due, until=until)["결과"]
    assert r["일수"] == days and r["일수분"] == 1_000_000 * days * 22 // 100_000
    assert r["3%분"] == (0 if due == until else 30_000) and r["가산세"] == r["3%분"] + r["일수분"]


# ── detail: 뒤 시트 줄이기 ────────────────────────────────────────────────────
def _dangling(wb):
    """없는 시트를 가리키는 수식·정의된 이름."""
    import re
    names = set(wb.sheetnames)
    bad = [(n, dn.attr_text) for n, dn in wb.defined_names.items() if not any(dn.attr_text.startswith(f"'{x}'!") or dn.attr_text.startswith(f"{x}!") for x in names)]
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if cell.data_type == "f" and isinstance(cell.value, str):
                    bad += [(ws.title, cell.coordinate, m) for m in re.findall(r"'((?:[^']|'')+)'!", cell.value) if m.replace("''", "'") not in names]
                    bad += [(ws.title, cell.coordinate, m) for m in re.findall(r"호출\d+_[가-힣A-Za-z0-9_.]+", cell.value) if m not in wb.defined_names]
    return bad


def test_default_is_compact_one_detail_sheet(tmp_path):
    r = _export(tmp_path)
    front = ["요약", "입력·출처", "배당", "용역·이자", "가산세", "그 밖의 계산", "쟁점 목록"]
    assert r["결과"]["통합_시트"] == front and r["결과"]["시트"] == front + ["계산 상세"] and len(r["결과"]["시트"]) <= 8
    assert r["결과"]["detail"] == "compact" and "detail='forms'" in r["결과"]["서식_안내"]
    wb = openpyxl.load_workbook(r["결과"]["파일"])
    assert wb.sheetnames == r["결과"]["시트"] and not _dangling(wb)
    ws = wb["계산 상세"]
    col_a = [ws.cell(k, 1).value for k in range(1, ws.max_row + 1)]
    for n, call in enumerate(CALLS, 1):                                  # call마다 띠 한 줄, 순서대로
        assert f"{n}. {call['label']} — {call['tool']}" in col_a
    assert col_a.index("1. 배당 총액 — nonresident_withholding") < col_a.index("11. 간주임대료 — vat_deemed_rent")
    text = " ".join(str(cell.value) for row in ws.iter_rows() for cell in row if cell.value is not None)
    assert "결론" in text and "korean-tax-mcp" in text                    # 판단·근거가 call 아래에 실림
    assert any(isinstance(cell.value, str) and cell.value.startswith("=") for row in ws.iter_rows() for cell in row)   # 계산식 단계의 수식·대조 칸이 살아 있음
    # 0.57.0: 뒤 시트 안내와 서식 안내는 호출자에게 하는 말 — 요약 시트에는 찍지 않고 결과로만 돌려준다
    summ = [str(wb["요약"].cell(k, 1).value) for k in range(1, wb["요약"].max_row + 1)]
    assert not any("detail=" in x or x.startswith("뒤 시트") for x in summ) and any(x.startswith("색 규칙") for x in summ)
    assert "'계산 상세' 한 장" in r["결과"]["시트_안내"] and "신고 서식" in r["결과"]["서식_안내"]
    # scenarios에 넣지 않은 call 둘은 한 시트에 차례로
    rest = [wb["그 밖의 계산"].cell(k, 1).value for k in range(1, wb["그 밖의 계산"].max_row + 1)]
    assert "기업업무추진비" in rest and "간주임대료" in rest


def test_detail_forms_adds_form_sheets_only(tmp_path):
    r = _export(tmp_path, detail="forms")
    wb = openpyxl.load_workbook(r["결과"]["파일"])
    back = r["결과"]["시트"][len(r["결과"]["통합_시트"]):]
    assert back[0] == "계산 상세" and len(back) > 1 and r["결과"]["detail"] == "forms" and "서식_안내" not in r["결과"]
    assert not any(n.startswith("계산 ") and n != "계산 상세" or n in ("호출 요약", "목록", "입력·가정", "판단·근거") for n in wb.sheetnames)
    assert any(n.startswith("원천 별지23") for n in back) and not _dangling(wb)
    assert wb.defined_names["호출1_지급액"].attr_text.startswith("'계산 상세'!")       # 서식 칸이 가리키는 호출 입력은 '계산 상세' 아래로
    assert "서식 연결 칸 — 서식 시트의 수식이 가리키는 호출 입력" in [wb["계산 상세"].cell(k, 1).value for k in range(1, wb["계산 상세"].max_row + 1)]
    full = _export(tmp_path, name="전부", detail="full")
    forms_full = [n for n in full["결과"]["시트"] if n in back]
    assert forms_full == back[1:]                                         # 서식 시트는 full과 같은 것, 같은 순서


def test_detail_english_and_steps_layout(tmp_path):
    r = _export(tmp_path, name="en", lang="en", layout="steps")
    assert r["결과"]["시트"] == r["결과"]["통합_시트"] + ["Calc detail"] and "서식_안내" not in r["결과"]      # steps에는 서식 시트가 없음
    wb = openpyxl.load_workbook(r["결과"]["파일"])
    assert wb["Calc detail"]["A1"].value.startswith("Calculation detail") and not _dangling(wb)
    assert "Other workings" in wb.sheetnames


def test_detail_only_applies_to_blend_and_is_checked(tmp_path):
    base = {"title": "x", "calls": CALLS[:2], "output_dir": str(tmp_path)}
    a, b = c("export_workbook", {**base, "filename": "a"}), c("export_workbook", {**base, "filename": "b", "detail": "compact"})
    assert a["결과"]["시트"] == b["결과"]["시트"] and "detail" not in b["결과"] and _dump(a["결과"]["파일"]) == _dump(b["결과"]["파일"])
    with pytest.raises(Exception):                                       # 입력 스키마(Literal)가 막음
        c("export_workbook", {**base, "detail": "tiny"})
    from korean_tax_calc_mcp.tools_export import export_workbook_impl
    assert "detail" in export_workbook_impl("x", CALLS[:1], str(tmp_path), detail="tiny")["error"]


@pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice 없음")
@pytest.mark.parametrize("detail,lang", [("compact", "ko"), ("compact", "en"), ("forms", "ko")])
def test_compact_and_forms_recalculate_to_tool_values(tmp_path, detail, lang):
    r = _export(tmp_path, name=f"{detail}_{lang}", lang=lang, detail=detail)
    src = openpyxl.load_workbook(r["결과"]["파일"])
    wb = _recalc(r["결과"]["파일"], tmp_path / "out")
    assert wb.sheetnames == r["결과"]["시트"]
    errs = [(n, cell.coordinate, cell.value) for n in wb.sheetnames for row in wb[n].iter_rows() for cell in row
            if isinstance(cell.value, str) and (cell.value.startswith("#") and len(cell.value) > 1 or cell.value.startswith("Err:"))]
    assert not errs, errs
    checks = [(n, cell.coordinate, cell.value) for n in wb.sheetnames for row in wb[n].iter_rows() for cell in row
              if src[n][cell.coordinate].data_type == "f" and isinstance(cell.value, str) and ("일치" in cell.value or "확인 필요" in cell.value)]
    assert len(checks) >= 10 and not [x for x in checks if "확인 필요" in x[2]], checks
    if detail == "forms":
        assert [x for x in checks if x[0].startswith("원천 별지23")]            # 서식 시트의 대조 칸도 일치
    res = [c(x["tool"], x["args"])["결과"] for x in CALLS]
    summ = [cell.value for row in wb[r["결과"]["통합_시트"][0]].iter_rows() for cell in row]
    for i in (0, 1, 2, 3, 4):
        assert res[i]["합계"] in summ                         # 열마다 합계 줄
    for i in (0, 2, 3):
        assert res[i]["원천징수세액"] in summ                  # 블록의 첫 열은 결과 줄 전부
    for i in (5, 6, 7, 8):
        assert res[i]["가산세"] in summ


# ── 납부고지 후 가산세 수식 틀 ────────────────────────────────────────────────
NOTICE = [
    # 손 계산(개정 3호·4호): 고지 전 2026.8.11.~9.9. 30일 → 3% 90,000 + 3,000,000 × 30 × 22/100,000 = 19,800 → 109,800(10% 한도 300,000 안),
    # 고지 후 2026.10.1.~12.4. 경과 2개월 × 0.67% = 40,200, 독촉비용 3,000 → 153,000(50% 한도 1,500,000 안)
    ("개정 3호·4호", dict(unpaid_tax=3_000_000, due="2026-08-10", until="2026-09-10", notice_due="2026-09-30", paid_on="2026-12-05", dunning_fee=3_000), 153_000),
    # 손 계산(종전): 고지 전 2024.2.14.~6.2. 110일 → 90,000 + 3,000,000 × 110 × 22/100,000 = 72,600 → 162,600, 고지 후 2024.7.1.~8.1. 32일 × 22/100,000 = 21,120 → 183,720
    ("종전 일수분", dict(unpaid_tax=3_000_000, due="2024-02-13", until="2024-06-03", notice_due="2024-06-30", paid_on="2024-08-01"), 183_720),
    ("소액 제외", dict(unpaid_tax=1_200_000, due="2026-08-10", until="2026-09-10", notice_due="2026-09-30", paid_on="2026-12-05"), None),
    ("기한 안 납부", dict(unpaid_tax=3_000_000, due="2026-08-10", until="2026-09-10", notice_due="2026-09-30", paid_on="2026-09-28"), None),
    ("고지세액 입력", dict(unpaid_tax=1_200_000, due="2026-08-10", until="2026-09-10", notice_due="2026-09-30", paid_on="2027-03-15", notice_amount=2_000_000), None),
    ("기산일 말일", dict(unpaid_tax=5_000_000, due="2026-08-10", until="2026-09-10", notice_due="2026-10-30", paid_on="2027-03-01"), None),
    ("이율 변경", dict(unpaid_tax=4_000_000, due="2021-11-10", until="2022-03-02", notice_due="2022-03-31", paid_on="2022-06-30"), None),
    ("종전 장기", dict(unpaid_tax=2_000_000, due="2020-03-10", until="2020-05-11", notice_due="2020-05-31", paid_on="2025-05-20"), None),
    ("50% 한도", dict(unpaid_tax=2_000_000, due="2025-08-11", until="2026-08-10", notice_due="2026-08-31", paid_on="2031-10-15"), None),
]


def test_notice_penalty_hand_values():
    for label, args, want in NOTICE:
        if want is not None:
            assert c("withholding_late_payment_penalty", args)["결과"]["가산세"] == want, label


def test_notice_penalty_layout_has_formulas_and_statutory_sources(tmp_path):
    calls = [{"label": lab, "tool": "withholding_late_payment_penalty", "args": a} for lab, a, _ in NOTICE]
    r = c("export_workbook", {"title": "고지 후", "calls": calls, "output_dir": str(tmp_path),
                              "scenarios": [{"sheet": "고지 후", "columns": [x["label"] for x in calls]}]})
    wb = openpyxl.load_workbook(r["결과"]["파일"])
    ws, wi = wb["고지 후"], wb["입력·출처"]
    k = max(j for j in range(1, ws.max_row + 1) if ws.cell(j, 1).value == "가산세")
    assert all(str(ws.cell(k, j).value).startswith("=ROUNDDOWN(ROUND(MIN(MIN(") for j in range(2, 2 + len(calls)))      # 모든 열이 수식
    src = {wi.cell(j, 1).value: (wi.cell(j, 2).value, wi.cell(j, 3).value) for j in range(1, wi.max_row + 1) if wi.cell(j, 1).value}
    assert src["납부고지 후 — 경과 개월마다의 이율(월 1만분의 67)"] == (0.0067, "국세기본법 제47조의5제1항제3호 · 시행령 제27조의4제2항")
    assert src["전체 한도(미납세액의 50%)"] == (0.5, "국세기본법 제47조의5제1항(전체 50% 한도)")
    small = [wi.cell(j, 2).value for j in range(1, wi.max_row + 1) if str(wi.cell(j, 1).value).startswith("소액 기준")]
    assert small == [1_500_000, 1_000_000]                                # 지정납부기한 2022.1.1. 이후 150만원, 2021.12.31.까지 100만원(도구와 같은 기준)
    assert src["독촉비용(4호)"][0] == 3_000
    months = _find(ws, "경과 개월 수(지정납부기한 다음 날부터 납부일 전날까지)")
    assert ws.cell(months, 2).value.startswith("=MIN(60,DATEDIF(")


@pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice 없음")
def test_notice_penalty_formulas_recalculate_to_tool_values(tmp_path):
    calls = [{"label": lab, "tool": "withholding_late_payment_penalty", "args": a} for lab, a, _ in NOTICE]
    r = c("export_workbook", {"title": "고지 후 재계산", "calls": calls, "output_dir": str(tmp_path),
                              "scenarios": [{"sheet": "고지 후", "columns": [x["label"] for x in calls]}]})
    res = [c("withholding_late_payment_penalty", a)["결과"] for _, a, _ in NOTICE]
    assert res[2]["고지후분"] == 0 and res[3]["고지후분"] == 0 and res[4]["고지후분"] > 0 and res[8]["50%한도_적용"] is True and res[8]["경과_개월"] == 60
    wb = _recalc(r["결과"]["파일"], tmp_path / "out")
    ws = wb["고지 후"]
    k = max(j for j in range(1, ws.max_row + 1) if ws.cell(j, 1).value == "가산세")
    assert [ws.cell(k, j).value for j in range(2, 2 + len(calls))] == [x["가산세"] for x in res]
    chk = _find(ws, "도구 값 대조(수식 = 계산 도구 결과)")
    assert [ws.cell(chk, j).value for j in range(2, 2 + len(calls))] == ["일치"] * len(calls)
    # 입력을 바꾸면(독촉비용·납부일) 도구를 다시 부른 값과 같다
    src = openpyxl.load_workbook(r["결과"]["파일"])
    wi = src["입력·출처"]
    for row in wi.iter_rows(min_col=2, max_col=2):
        cell = row[0]
        if cell.value == 3_000:
            cell.value = 4_500
        elif cell.number_format == "yyyy-mm-dd" and cell.value.date().isoformat() == "2026-12-05" and "개정 3호·4호" in str(wi.cell(cell.row, 1).value):
            cell.value = cell.value.replace(year=2027, month=2, day=20)
    edited = tmp_path / "edited.xlsx"
    src.save(edited)
    out = _recalc(edited, tmp_path / "out2")["고지 후"]
    again = c("withholding_late_payment_penalty", {**NOTICE[0][1], "paid_on": "2027-02-20", "dunning_fee": 4_500})["결과"]
    assert out.cell(k, 2).value == again["가산세"] and again["경과_개월"] == 4


# ── find_tool: 메모·Word 요청은 조문 MCP로 ────────────────────────────────────
@pytest.mark.parametrize("query", ["세무 메모 써줘", "tax memo for head office", "Word 문서로 정리", "docx 의견서", "원천징수 계산하고 의견서로"])
def test_find_tool_points_memo_requests_to_law_mcp(query):
    r = c("find_tool", {"query": query})["결과"]
    assert "tax_memo_guide" in r["메모 문서"] and "build_tax_memo" in r["메모 문서"] and "korean-tax-mcp" in r["메모 문서"]


@pytest.mark.parametrize("query", ["접대비 한도", "keyword search for password", "양도소득세"])
def test_find_tool_has_no_memo_line_otherwise(query):
    assert "메모 문서" not in c("find_tool", {"query": query})["결과"]
