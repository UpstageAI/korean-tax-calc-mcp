"""0.57.0 — 계산 근거 엑셀은 직접 짜고 verify_workbook으로 대조: 호출_id, call 대조, key 생략, 자동 대조, 짧은 검산 시트. 작성 Claude 2026-11-15.

값은 모두 지어낸 것(배당 40,000,000원, 프랑스 법인). 통합 문서는 tests/test_verify_workbook_1115.py의 _book(입력·배당·요약 세 시트)을 쓴다.
세액 계산은 건드리지 않았으므로 여기서는 계산 값을 다시 검증하지 않고, 도구가 돌려준 값과 통합 문서 칸의 대조만 본다.
"""
import re

import openpyxl
import pytest

from korean_tax_calc_mcp import workbook_verify as V
from tests import _helpers
from tests._helpers import call as c


class _Live:
    """지금 등록돼 도는 서버 모듈 — 다른 테스트가 서버 모듈을 다시 읽어 들였어도 call()이 쓰는 것과 같은 모듈의 이름을 읽는다."""

    def __getattr__(self, name):
        return _helpers.mcp._tool_manager._tools["corporate_tax"].fn.__globals__[name]

    def __setattr__(self, name, value):
        _helpers.mcp._tool_manager._tools["corporate_tax"].fn.__globals__[name] = value


S = _Live()
from tests.test_verify_workbook_1115 import CHECKS, DIV, FILED, NW, PEN, PEN_ARGS, _book


@pytest.fixture()
def calls():
    """호출 기록을 비우고 세 번 호출 — (맞는 20%, 신고 15%, 가산세)의 호출_id."""
    S._reset_call_log()
    return c(NW, DIV)["호출_id"], c(NW, FILED)["호출_id"], c(PEN, PEN_ARGS)["호출_id"]


# ── 호출_id ────────────────────────────────────────────────────────────────
def test_every_calc_result_carries_a_call_id_and_the_tail_names_it():
    S._reset_call_log()
    a, b = c(NW, DIV), c(PEN, PEN_ARGS)
    assert (a["호출_id"], b["호출_id"]) == ("c1", "c2")
    assert list(a)[-2:] == ["호출_id", "엑셀"]
    assert '{cell: "시트!칸", call: "c1"}' in a["엑셀"] and '[{cell: "Sheet!B9", call: "c2"}]' in b["엑셀"]
    assert "계산 근거·보고용 Excel은 직접 짠다(구성은 자유 — 필요한 줄만)" in a["엑셀"] and len(a["엑셀"]) < 440      # 결과마다 붙으므로 0.56.1(436자)보다 길지 않게
    assert "build the workbook yourself" in a["엑셀"] and "Use export_workbook only for Korean statutory return forms" in a["엑셀"]
    assert c(NW, DIV)["호출_id"] == "c1"                                        # 같은 도구 + 같은 입력은 같은 번호
    assert c(NW, dict(reversed(list(DIV.items()))))["호출_id"] == "c1"          # 입력 순서가 달라도
    rec = S.call_record("c1")
    assert rec["tool"] == NW and {k: rec["args"][k] for k in DIV} == DIV and rec["data"]["결과"]["원천징수세액"] == a["결과"]["원천징수세액"]
    assert S.call_record("C1") is rec and S.call_record(1) is rec and S.call_record("c99") is None


def test_no_call_id_on_errors_or_on_the_workbook_and_finder_tools(tmp_path):
    S._reset_call_log()
    assert "호출_id" not in c(NW, {**DIV, "year": 1990})                         # 오류 결과에는 붙지 않음
    assert "호출_id" not in S.find_tool(query="법인세")
    made = c("export_workbook", {"title": "t", "calls": [{"label": "a", "tool": NW, "args": DIV}], "output_dir": str(tmp_path)})
    assert "호출_id" not in made and "엑셀" not in made
    wb = openpyxl.load_workbook(made["결과"]["파일"])                            # 호출 번호·안내 꼬리는 통합 문서에 찍히지 않음
    text = " ".join(str(x.value) for ws in wb.worksheets for row in ws.iter_rows() for x in row if x.value is not None)
    assert "호출_id" not in text and "verify_workbook" not in text


def test_call_log_keeps_only_the_latest(monkeypatch):
    S._reset_call_log()
    monkeypatch.setitem(_helpers.mcp._tool_manager._tools["corporate_tax"].fn.__globals__, "CALL_LOG_MAX", 3)
    ids = [S.corporate_tax(base=100_000_000 + k, year=2024)["호출_id"] for k in range(5)]
    assert ids == ["c1", "c2", "c3", "c4", "c5"]
    assert [k for k, _ in S.call_records()] == ["c3", "c4", "c5"]                 # 오래된 것부터 버림
    assert S.call_record("c1") is None and S.call_record("c5")["args"] == {"base": 100_000_004, "year": 2024}
    assert S.corporate_tax(base=100_000_000, year=2024)["호출_id"] == "c6"        # 버려진 호출을 다시 부르면 새 번호
    S._reset_call_log()


# ── call 대조 ──────────────────────────────────────────────────────────────
def test_check_by_call_id_alone(tmp_path, calls):
    ok, filed, pen = calls
    path = _book(tmp_path / "a.xlsx")
    checks = [{"cell": "배당!B6", "call": ok, "key": "원천징수세액"}, {"cell": "배당!B7", "call": ok, "key": "지방소득세"},
              {"cell": "배당!C6", "call": filed, "key": "원천징수세액"}, {"cell": "가산세_칸", "call": pen, "key": "가산세"}, {"cell": "배당!C7", "call": filed, "key": "지방소득세"}]
    by_call = c("verify_workbook", {"path": path, "checks": checks, "annotate": False})["결과"]
    by_args = c("verify_workbook", {"path": path, "checks": CHECKS, "annotate": False})["결과"]
    assert by_call["요약"] == by_args["요약"] == {"대조": 5, "일치": 5, "불일치": 0, "읽지_못함": 0, "도구_오류": 0, "자동_일치": 0, "자동_불일치": 0, "대조_안_한_금액": 2}
    strip = lambda rows: [{k: v for k, v in r.items() if k not in ("항목", "호출")} for r in rows]
    assert strip(by_call["대조"]) == strip(by_args["대조"])                       # 두 방식의 줄이 같다(값·키·판정·근거)
    assert all(r.get("호출") for r in by_args["대조"])                            # tool+args로 대조한 줄에도 호출 번호가 붙는다
    assert [r["호출"] for r in by_call["대조"]] == [ok, ok, filed, pen, filed] and {r["방식"] for r in by_call["대조"]} == {"명시"}


def test_unknown_call_id_is_reported_on_that_check_only(tmp_path, calls):
    ok, _, _ = calls
    path = _book(tmp_path / "a.xlsx")
    res = c("verify_workbook", {"path": path, "annotate": False, "checks": [
        {"cell": "배당!B6", "call": "c77", "key": "원천징수세액"}, {"cell": "배당!B7", "call": ok, "key": "지방소득세"},
        {"cell": "배당!C6", "call": "c78", "tool": NW, "args": FILED, "key": "원천징수세액"}]})["결과"]     # 기록이 없어도 tool+args가 있으면 그쪽으로
    assert res["요약"]["도구_오류"] == 1 and res["요약"]["일치"] == 2
    bad = res["읽지_못함·도구_오류"][0]
    assert bad["칸"] == "배당!B6" and "도구 호출 기록 없음" in bad["도구_오류"] and "tool+args로 다시" in bad["도구_오류"]
    assert "call(또는 tool+args)" in res["다음"]


# ── key 생략 ───────────────────────────────────────────────────────────────
def test_key_can_be_left_out(tmp_path, calls):
    ok, filed, pen = calls
    path = _book(tmp_path / "a.xlsx")
    res = c("verify_workbook", {"path": path, "annotate": False, "checks": [
        {"cell": "배당!B6", "call": ok}, {"cell": "배당!B7", "call": ok}, {"cell": "배당!C6", "call": filed}, {"cell": "배당!B10", "call": pen},
        {"cell": "배당!B8", "tool": NW, "args": DIV}]})["결과"]                                           # tool+args에서도 key 생략
    assert res["요약"]["일치"] == 5 and res["요약"]["대조"] == 5 and res["요약"]["자동_일치"] == 0          # call을 적었으니 명시 대조
    keys = [r["키"] for r in res["대조"]]
    assert keys[0].split(" · ")[0] == "원천징수세액" and keys[1].split(" · ")[0] == "지방소득세" and keys[3].split(" · ")[0] == "가산세"
    assert keys[4].split(" · ")[0] == "합계"
    tool = c(NW, DIV)["결과"]
    same = [k for k, v in V._leaves({"결과": tool}) if v == tool["원천징수세액"]]
    if len(same) > 1:                                                                                   # 같은 값의 키가 여럿이면 모두 적는다
        assert res["대조"][0]["같은_값_키"] == same and res["대조"][0]["키"] == " · ".join(same)


def test_key_left_out_and_no_equal_value_is_a_mismatch_with_the_nearest_key(tmp_path, calls):
    ok, _, _ = calls
    path = _book(tmp_path / "틀림.xlsx", tax_formula="=ROUNDDOWN(B4*B5,-1)+70")
    res = c("verify_workbook", {"path": path, "annotate": False, "checks": [{"cell": "배당!B6", "call": ok}, {"cell": "배당!B5", "call": ok}]})["결과"]
    bad = res["불일치"][0]
    assert res["요약"]["불일치"] == 1 and (bad["칸"], bad["키"], bad["통합_문서_값"], bad["도구_값"], bad["차이"]) == ("배당!B6", "원천징수세액", 8_000_070, 8_000_000, 70)
    assert "가장 가까운 키" in bad["알림"]
    assert res["대조"][1]["판정"] == "일치" and res["대조"][1]["도구_값"] == 0.2                           # 세율 칸도 값으로 찾음
    text = c("verify_workbook", {"path": path, "annotate": False, "checks": [{"cell": "배당!A6", "call": ok}]})["결과"]["읽지_못함·도구_오류"][0]
    assert "숫자가 아님" in text["도구_오류"]                                                              # 글 칸은 key가 필요


# ── 자동 대조 ──────────────────────────────────────────────────────────────
def test_cell_only_check_searches_every_recorded_call(tmp_path, calls):
    ok, filed, pen = calls
    path = _book(tmp_path / "a.xlsx")
    res = c("verify_workbook", {"path": path, "annotate": False, "checks": [{"cell": "배당!B6"}, {"cell": "배당!C6"}, {"cell": "배당!B10"},
                                                                         {"cell": "배당!B7", "call": ok, "key": "지방소득세"}]})["결과"]
    q = res["요약"]
    assert (q["대조"], q["일치"], q["자동_일치"], q["자동_불일치"]) == (1, 1, 3, 0)                         # 명시 대조와 자동 대조를 따로 센다
    rows = {r["칸"]: r for r in res["대조"]}
    assert rows["배당!B6"]["방식"] == "자동(값 일치)" and rows["배당!B6"]["호출"] == ok and rows["배당!B6"]["키"].startswith("원천징수세액")
    assert rows["배당!C6"]["호출"] == filed and rows["배당!B10"]["호출"] == pen and rows["배당!B7"]["방식"] == "명시"
    assert "우연히" in res["자동_대조_안내"] and "자동(값 일치)으로 맞춘 칸" in res["다음"]


def test_cell_only_check_without_a_match_or_without_records(tmp_path, calls):
    path = _book(tmp_path / "틀림.xlsx", tax_formula="=ROUNDDOWN(B4*B5,-1)+70")
    res = c("verify_workbook", {"path": path, "annotate": False, "checks": [{"cell": "배당!B6"}]})["결과"]
    bad = res["불일치"][0]
    assert res["요약"]["자동_불일치"] == 1 and res["요약"]["불일치"] == 0 and bad["차이"] == 70 and "가장 가까운 값" in bad["알림"]
    S._reset_call_log()
    res = c("verify_workbook", {"path": path, "annotate": False, "checks": [{"cell": "배당!B6"}]})["결과"]
    assert res["요약"]["도구_오류"] == 1 and "보관된 도구 호출 기록 없음" in res["읽지_못함·도구_오류"][0]["도구_오류"]


def test_auto_matches_every_amount_cell_and_counts_them_apart(tmp_path, calls):
    ok, filed, pen = calls
    path = _book(tmp_path / "a.xlsx")
    res = c("verify_workbook", {"path": path, "auto": True, "annotate": False})["결과"]            # checks 없이
    q = res["요약"]
    assert q["대조"] == 0 and q["일치"] == 0 and q["자동_일치"] >= 6 and q["자동_불일치"] == 0
    rows = {r["칸"]: r for r in res["대조"]}
    assert {r["방식"] for r in res["대조"]} == {"자동(값 일치)"}
    for cell, cid in (("배당!B6", ok), ("배당!B7", ok), ("배당!B8", ok), ("배당!C6", filed), ("배당!B10", pen)):
        assert rows[cell]["판정"] == "일치" and rows[cell]["호출"] == cid, cell
    assert "배당!B4" not in rows and "입력!B1" not in rows                                         # 입력을 그대로 되돌려준 값(지급액)은 자동 대조에서 뺌
    assert "요약!B1" not in rows                                                                   # 다른 칸을 그대로 가리키는 링크는 가리키는 칸이 대상
    assert {(x["시트"], x["칸"]) for x in res["대조_안_한_금액"]} >= {("배당", "B11"), ("배당", "B12")}   # 도구 값과 같지 않은 금액은 그대로 '대조 안 한 금액'
    # 명시한 칸은 자동으로 다시 맞추지 않는다
    both = c("verify_workbook", {"path": path, "auto": True, "annotate": False, "checks": [{"cell": "배당!B6", "call": ok, "key": "원천징수세액"}]})["결과"]
    assert both["요약"]["대조"] == 1 and both["요약"]["일치"] == 1 and both["요약"]["자동_일치"] == q["자동_일치"] - 1
    assert [r["방식"] for r in both["대조"] if r["칸"] == "배당!B6"] == ["명시"]


def test_auto_match_can_be_a_coincidence_and_is_marked(tmp_path):
    """같은 숫자가 우연히 일치 — 도구 결과와 무관한 칸이 같은 값이면 '자동(값 일치)'으로 잡히되 명시 대조 수에는 들어가지 않고, 후보가 여럿이면 나열한다."""
    S._reset_call_log()
    a, b = c(NW, DIV), c(NW, {**DIV, "residence_country": "독일"})                                  # 값이 같은 호출 둘(지어낸 값)
    assert a["결과"]["원천징수세액"] == b["결과"]["원천징수세액"] and a["호출_id"] != b["호출_id"]
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "메모"
    ws.append(["창고 임차료(세금과 무관)", a["결과"]["원천징수세액"]])                                 # 세금이 아닌데 숫자가 같다
    ws.append(["합", "=B1+1000"])
    path = str(tmp_path / "우연.xlsx")
    wb.save(path)
    res = c("verify_workbook", {"path": path, "auto": True, "annotate": False})["결과"]
    row = res["대조"][0]
    assert (row["칸"], row["방식"], row["판정"]) == ("메모!B1", "자동(값 일치)", "일치")
    assert res["요약"]["대조"] == 0 and res["요약"]["일치"] == 0 and res["요약"]["자동_일치"] == 1         # 명시 대조로 세지 않음
    assert len(row["후보"]) == 2 and {x.split(" ")[0] for x in row["후보"]} == {a["호출_id"], b["호출_id"]}   # 값이 같은 호출이 여럿 — 후보로
    assert any("우연히" in x for x in V.LIMITS)


def test_auto_match_does_not_extend_to_the_cells_behind_it(tmp_path, calls):
    """명시 대조로 일치한 칸은 그 칸이 가리키는 칸까지 대조된 것으로 보지만, 자동(값 일치)은 그 칸만."""
    ok, _, _ = calls
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "배당"
    ws.append(["지급액", 40_000_000])
    ws.append(["중간 계산", "=B1*0.25"])                # 10,000,000 — 도구 결과에 없는 금액
    ws.append(["법인세", "=B2*0.8"])                    # 8,000,000 = 도구의 원천징수세액
    path = str(tmp_path / "뒤.xlsx")
    wb.save(path)
    un = lambda r: {(x["시트"], x["칸"]) for x in r["대조_안_한_금액"]}
    explicit = c("verify_workbook", {"path": path, "annotate": False, "checks": [{"cell": "배당!B3", "call": ok}]})["결과"]
    auto = c("verify_workbook", {"path": path, "annotate": False, "auto": True})["결과"]
    assert explicit["요약"]["일치"] == 1 and un(explicit) == set()
    assert auto["요약"]["자동_일치"] == 1 and un(auto) == {("배당", "B2")}


# ── 검산 시트: 한 장, 짧게 ─────────────────────────────────────────────────
def _col_a(ws):
    return [ws.cell(k, 1).value for k in range(1, ws.max_row + 1)]


def test_check_sheet_is_short_basis_once_and_unchecked_grouped_by_sheet(tmp_path, calls):
    ok, filed, pen = calls
    path = _book(tmp_path / "a.xlsx")
    src = openpyxl.load_workbook(path)
    extra = src.create_sheet("과거연도")
    for k in range(1, 13):                                  # 대조할 수 없는 추정 12칸(지어낸 값)
        extra.append([f"추정 {k}", 1_000_000 * k, f"=B{k}*0.3"])
    src.save(path)
    checks = [{"cell": "배당!B6", "call": ok}, {"cell": "배당!B7", "call": ok}, {"cell": "배당!B8", "call": ok}, {"cell": "배당!C6", "call": filed},
              {"cell": "배당!B10", "call": pen}]
    r = c("verify_workbook", {"path": path, "checks": checks})
    res = r["결과"]
    ws = openpyxl.load_workbook(res["사본"])["검산"]
    a = _col_a(ws)
    assert a[1] == f"대조 5 · 일치 5 · 불일치 0 · 대조 안 한 금액 {res['요약']['대조_안_한_금액']}칸"            # 맨 위 한 줄 요약
    assert [ws.cell(4, j).value for j in range(1, 7)] == ["칸", "항목", "통합 문서 값", "도구 값", "판정", "근거 번호 · 결과 키"]
    assert ws.cell(4, 7).value is None                                                                   # 차이 열 없음(불일치가 없으므로)
    # 근거: 표에는 번호만, 글은 표 아래에 번호마다 한 번
    refs = [ws.cell(k, 6).value for k in range(5, 10)]
    assert [x[:3] for x in refs] == ["[1]", "[1]", "[1]", "[2]", "[3]"]
    basis = res["대조"][0]["근거"]
    cells = [str(x.value) for row in ws.iter_rows() for x in row if x.value is not None]
    assert sum(1 for x in cells if x.endswith("— " + basis)) == 1 and sum(1 for x in cells if x.endswith("— " + res["대조"][4]["근거"])) == 1
    notes = [x for x in a if re.match(r"\[\d+\] ", str(x))]
    assert len(notes) == 3 and notes[0].startswith(f"[1] {NW} ({ok}) — ") and notes[2].startswith(f"[3] {PEN} ({pen}) — ")
    # 대조 안 한 금액: 칸마다 한 줄이 아니라 시트마다 한 줄 + 대표 3칸. 전체 목록은 반환값에
    assert res["대조_안_한_금액_시트별"] == {"배당": 4, "과거연도": 12} and len(res["대조_안_한_금액"]) == 16
    k = a.index("과거연도")
    assert ws.cell(k + 1, 2).value == "12칸 — 예: C1 추정 1 300,000; C2 추정 2 600,000; C3 추정 3 900,000 …"
    assert a[a.index("배당")] == "배당" and "C12" not in " ".join(cells) and "배당!B12" not in a
    assert "검증 범위" not in a and ws.max_row <= 25                                                       # 화면 한 장 안팎
    # 부가 점검: 문제가 있는 것만 한 줄씩
    k = a.index("부가 점검")
    lines = [x for x in a[k + 1:] if x]
    assert all(re.search(r": \d+", x) for x in lines) and not any(": 0" in x for x in lines)
    assert any(x.startswith("원 미만 소수가 남은 금액 칸: ") for x in lines) and not any(x.startswith("오류 값 칸") for x in lines)


def test_check_sheet_difference_column_only_when_there_is_a_mismatch(tmp_path, calls):
    ok, _, _ = calls
    path = _book(tmp_path / "틀림.xlsx", tax_formula="=ROUNDDOWN(B4*B5,-1)+70")
    res = c("verify_workbook", {"path": path, "checks": [{"cell": "배당!B6", "call": ok}, {"cell": "배당!B5", "call": ok}], "lang": "en"})["결과"]
    ws = openpyxl.load_workbook(res["사본"])["Tool check"]
    assert [ws.cell(4, j).value for j in range(1, 8)] == ["Cell", "Item", "Workbook value", "Tool value", "Difference", "Result", "Basis no. · result key"]
    assert (ws["E5"].value, ws["F5"].value) == (70, "Mismatch") and ws["G5"].value.endswith("— nearest value")
    assert ws["A2"].value.startswith("Checked 2 · match 1 · mismatch 1 · amounts not checked ")


def test_check_sheet_marks_auto_rows_and_english_mode_keeps_the_0561_wording(tmp_path, calls):
    ok, _, pen = calls
    path = _book(tmp_path / "a.xlsx")
    res = c("verify_workbook", {"path": path, "auto": True, "lang": "en", "checks": [{"cell": "배당!B6", "call": ok, "key": "원천징수세액"}]})["결과"]
    ws = openpyxl.load_workbook(res["사본"])["Tool check"]
    a = _col_a(ws)
    assert re.fullmatch(r"Checked 1 · match 1 · mismatch 0 · amounts not checked \d+ · auto \(same value\) \d+", a[1])
    rows = {ws.cell(k, 1).value: [ws.cell(k, j).value for j in range(1, 7)] for k in range(5, 5 + len(res["대조"]))}
    assert rows["배당!B6"][4] == "Match" and rows["배당!B6"][5] == "[1] Withholding tax amount (원천징수세액)"      # 결과 키: 'English (국문)'
    assert rows["배당!B7"][4] == "Match (auto)" and rows["배당!B10"][4] == "Match (auto)"                      # 자동 줄은 구분 표시
    note = next(x for x in a if str(x).startswith("[1] "))
    assert "— Corporate Tax Act (법인세법) Art. 98(1)" in note and "제98조" not in note                         # 근거: 영문 인용
    assert res["lang"] == "en" and isinstance(res["번역_없음"], list)


def test_no_unchecked_amounts_shows_none_and_no_other_checks_band(tmp_path, calls):
    ok, _, _ = calls
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "배당"
    ws.append(["지급액", 40_000_000])
    ws.append(["세율", 0.2])
    ws.append(["법인세", "=ROUNDDOWN(B1*B2,-1)"])
    path = str(tmp_path / "깨끗.xlsx")
    wb.save(path)
    openpyxl.load_workbook(path).save(path)
    first = c("verify_workbook", {"path": path, "checks": [{"cell": "배당!B3", "call": ok}], "filename": "first"})["결과"]
    res = c("verify_workbook", {"path": first["사본"], "checks": [{"cell": "배당!B3", "call": ok}], "filename": "second"})["결과"]   # 값이 채워진 사본을 다시
    sheet = openpyxl.load_workbook(res["사본"])
    a = _col_a(sheet[sheet.sheetnames[-1]])
    assert "계산 도구 대조를 거치지 않은 금액 — 없음" in a and "부가 점검" not in a and len(a) <= 12


# ── export_workbook: 호출자에게 하는 말은 시트에 찍지 않는다 ────────────────
@pytest.mark.parametrize("lang", ["ko", "en"])
@pytest.mark.parametrize("detail", [None, "forms", "full"])
def test_export_summary_has_no_caller_guidance_lines(tmp_path, lang, detail):
    kw = {"title": "t", "output_dir": str(tmp_path), "lang": lang, "calls": [{"label": "a", "tool": NW, "args": DIV}, {"label": "b", "tool": NW, "args": FILED}],
          "scenarios": [{"sheet": "배당", "heading": "비교", "columns": ["a", "b"]}],
          "extra_sheets": [{"sheet": "자체 표", "headers": ["항목", "금액"], "rows": [["가", 1000], ["나", 2000]], "total": True}]}
    if detail:
        kw["detail"] = detail
    r = c("export_workbook", kw)
    assert "error" not in r, r
    wb = openpyxl.load_workbook(r["결과"]["파일"])
    ws = wb[wb.sheetnames[0]]
    lines = [str(ws.cell(k, 1).value) for k in range(1, ws.max_row + 1) if ws.cell(k, 1).value is not None]
    for gone in ("detail=", "Supporting tab", "뒤 시트:", "are available with", "받을 수 있음"):
        assert not any(gone in x for x in lines), (gone, lines)
    # 읽는 사람에게 하는 말은 남는다: 색 범례, 작성자가 넣은 표 표시
    assert any(x.startswith("Colour key:" if lang == "en" else "색 규칙:") for x in lines)
    assert any("not verified by the calculation tools" in x if lang == "en" else "계산 도구의 검증을 거치지 않음" in x for x in lines)
    # 안내는 반환값으로만
    assert r["결과"]["시트_안내"] and ("서식_안내" in r["결과"]) == (detail is None and "detail='forms'" in str(r["결과"].get("서식_안내")))


# ── 설명 문구 ──────────────────────────────────────────────────────────────
def test_wording_puts_build_then_verify_first_everywhere():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    tools = S.mcp._tool_manager._tools
    exp, ver, ins = tools["export_workbook"].description, tools["verify_workbook"].description, S.mcp.instructions
    assert ver.splitlines()[1].strip().startswith("직접 만든 Excel을 저장한 뒤 이 도구를 부른다 — 금액 칸을 계산 도구 결과와 대조해 검산 시트 한 장을 붙인다.")
    assert "언제:" in ver and "입력:" in ver and "auto" in tools["verify_workbook"].parameters["properties"]
    assert exp.splitlines()[1].strip().startswith("한국 법정서식(별지 서식) 엑셀을 만든다 — 칸 번호·문구가 정해진 신고 서식. 일반 계산 근거 통합 문서에는 쓰지 않아도 된다")
    assert exp.splitlines()[0].startswith("Builds Korean statutory return forms")
    basic = "계산 근거·보고용 Excel은 직접 짠다(구성·시트·이름은 자유 — 읽는 사람의 질문 단위로, 필요한 줄만)"
    assert basic in ins and "저장한 뒤 verify_workbook으로 금액 칸을 대조한다" in ins and "대조하지 않은 금액은 사용자에게 밝힌다" in ins
    assert ins.index(basic) < ins.index("export_workbook은 한국 법정서식(별지 서식) 엑셀을 만든다")              # 순서: 직접 짠다 → 대조 → 법정서식
    hint = S.find_tool(query="엑셀로 계산 근거")["결과"]["엑셀 문서"]
    files = {n: (root / n).read_text(encoding="utf-8") for n in ("README.md", "README-EN.md", "llms.txt")}
    for name, text in {"instructions": ins, "export": exp, "verify": ver, "hint": hint, "tail": S._EXCEL_TAIL, **files}.items():
        for gone in ("길은 둘", "두 길", "two ways", "Two ways", "either pass this call", "one of two ways"):
            assert gone not in text, (name, gone)
        assert name == "verify" or "verify_workbook" in text, name
    assert "직접 짭니다" in files["README.md"] and "built by the AI itself" in files["README-EN.md"] and "`호출_id`" in files["llms.txt"]
