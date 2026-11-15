"""export_workbook의 자유 형식 시트(extra_sheets)·조치·기한(actions)·핵심 숫자(key_figures)와 새 요약 시트. 작성 Claude 2026-11-15.

- extra_sheets: 호출자가 준 표를 그대로 시트로(값·날짜·허용 수식·합계 행·출처 열·계산 도구 결과 링크), 수식 주입은 입력 오류, 수식 칸에 캐시 값.
- actions·key_figures: 요약 시트의 조치·기한 표와 핵심 숫자 표.
- 새 입력을 안 쓰면 기존 출력 그대로(scenarios 없는 출력은 칸 단위로 같음).
- 사례 값은 모두 지어낸 값(특정 사례와 무관).
"""
import json
import shutil

import openpyxl
import pytest

from korean_tax_calc_mcp import server as S
from tests._helpers import call as c

DIV = dict(income_kind="배당", recipient_type="법인", residence_country="프랑스", year=2025, amount=40_000_000)
CALLS = [{"label": "신고 15%", "tool": "nonresident_withholding", "args": {**DIV, "treaty_rate": 0.15}},
         {"label": "맞는 20%", "tool": "nonresident_withholding", "args": DIV},
         {"label": "부족분 가산세", "tool": "withholding_late_payment_penalty", "args": dict(unpaid_tax=2_000_000, due="2025-04-10", until="2025-09-30")}]
SCEN = [{"sheet": "배당", "heading": "신고한 대로 vs 맞는 금액", "summary_note": "메모 한 줄",
         "columns": [{"call": "신고 15%", "heading": "신고한 대로"}, {"call": "맞는 20%", "heading": "맞는 금액", "recommended": True}]},
        {"sheet": "가산세", "heading": "부족분", "columns": ["부족분 가산세"]}]
SRC = [{"call": "부족분 가산세", "arg": "unpaid_tax", "from_call": "맞는 20%", "from_row": "원천징수세액", "less": 6_000_000, "source": "맞는 세액 − 이미 낸 세액"}]
EXTRA = [{"sheet": "품목별 검산", "title": "품목별 매출 검산", "note": "장부에서 옮긴 표", "source": "매출 장부 3월분",
          "headers": ["품목", "1분기", "2분기", "대상", "출처"], "formats": ["", "amount", "amount", "text", "source"],
          "rows": [["가", 1_100_000, 2_200_000, "Y", "장부 1쪽"], ["나", 3_300_000, 4_400_000, "N", "=장부 2쪽"], "소계",
                   ["대상만", '=SUMIFS(B5:B6,D5:D6,"Y")', '=sumifs( C5:C6 , D5:D6 , "Y" )'],
                   ["수수료 3%", "=ROUNDDOWN(B8*0.03,-3)", "=ROUNDDOWN(C8*3%,-3)"],
                   ["맞는 세액", {"from_call": "맞는 20%", "from_row": "원천징수세액"}, "=B10-6000000"]],
          "total": {"label": "매출 합계", "columns": ["1분기"]}},
         {"sheet": "추정", "headers": ["연도", "금액", "율", "기준일"], "formats": {"율": "percent"},
          "rows": [[2023, 5_000_000, 0.165, "2023-12-31"], [2024, 7_000_000, 0.22, "2024-12-31"]], "total": True}]
ACTIONS = [{"action": "수정신고", "due": "2025-10-10", "owner": "재무팀", "basis": "국세기본법 제45조"},
           {"조치": "=영수증 교부", "기한": "납부 후 30일", "근거": "약정 제5조"}]
FIGS = [{"label": "이번에 낼 세금", "call": "맞는 20%", "row": "합계", "highlight": True, "note": "=메모"},
        {"call": 3, "row": "가산세"}, {"label": "검산 값", "sheet": "품목별 검산", "cell": "b9"}]


def _export(tmp_path, **kw):
    return c("export_workbook", {"title": "t", "calls": CALLS, "output_dir": str(tmp_path), **kw})


def _cells(path, data_only=False):
    wb = openpyxl.load_workbook(path, data_only=data_only)
    return {ws.title: {x.coordinate: x.value for row in ws.iter_rows() for x in row if x.value is not None} for ws in wb.worksheets}


@pytest.fixture(scope="module")
def blend(tmp_path_factory):
    r = _export(tmp_path_factory.mktemp("blend"), scenarios=SCEN, sources=SRC, extra_sheets=EXTRA, actions=ACTIONS, key_figures=FIGS,
                issues=[{"issue": "세율", "finding": "15% 적용", "risk": "High", "action": "수정", "amount": {"from_call": 3, "from_row": "가산세"}},
                        {"issue": "증빙", "finding": "없음", "risk": "Low", "action": "보완", "amount": 1_234_000}, {"issue": "기타"}])
    assert "error" not in r, r
    return r


# ── 자유 형식 시트 ───────────────────────────────────────────────────────────
def test_extra_sheet_holds_the_table_as_given(blend):
    path = blend["결과"]["파일"]
    f, v = _cells(path)["품목별 검산"], _cells(path, True)["품목별 검산"]
    assert f["A1"] == "품목별 매출 검산" and f["A2"] == "장부에서 옮긴 표" and "계산 도구의 검증을 거치지 않음" in f["A3"] and "초록 칸" in f["A3"]
    assert [f[k] for k in ("A4", "B4", "C4", "D4", "E4")] == ["품목", "1분기", "2분기", "대상", "출처"]
    assert (f["A5"], f["B5"], f["D5"], f["E6"], f["A7"]) == ("가", 1_100_000, "Y", "=장부 2쪽", "소계")
    assert f["B8"] == '=SUMIFS(B5:B6,D5:D6,"Y")' and f["C8"] == '=SUMIFS(C5:C6,D5:D6,"Y")'       # 받은 수식 그대로(공백·소문자만 다듬음)
    assert f["B10"].startswith("='배당'!$C$") and f["C10"] == "=B10-6000000"                    # 계산 도구 결과는 링크, 그 칸을 다시 가리킴
    assert (f["A11"], f["B11"]) == ("매출 합계", "=SUM(B5:B10)") and "C11" not in f and f["A13"] == "출처: 매출 장부 3월분"
    assert (v["B8"], v["C8"], v["B9"], v["C9"], v["B10"], v["C10"]) == (1_100_000, 2_200_000, 33_000, 66_000, 8_000_000, 2_000_000)   # 캐시 값
    wb = openpyxl.load_workbook(path)
    ws = wb["품목별 검산"]
    assert ws["E6"].data_type == "s" and ws["B5"].number_format.startswith("#,##0") and ws["B10"].font.color.rgb == "00008000" and ws.freeze_panes == "A5"
    e = _cells(path)["추정"], _cells(path, True)["추정"]
    assert e[0]["D5"].date().isoformat() == "2023-12-31" and wb["추정"]["C5"].number_format.endswith("%")
    assert e[0]["B7"] == "=SUM(B5:B6)" and e[1]["B7"] == 12_000_000 and "C7" not in e[0] and "D7" not in e[0]        # 합계는 숫자 열만(율·날짜 제외)
    assert blend["결과"]["자유_시트"] == [{"시트": "품목별 검산", "머리_행": 4, "첫_행": 5, "끝_행": 10, "열": "A~E", "합계_행": 11},
                                    {"시트": "추정", "머리_행": 4, "첫_행": 5, "끝_행": 6, "열": "A~D", "합계_행": 7}]


def test_extra_sheets_sit_after_scenarios_and_are_not_counted_as_tool_sheets(blend):
    res = blend["결과"]
    assert res["시트"] == ["요약", "입력·출처", "배당", "가산세", "품목별 검산", "추정", "쟁점 목록", "계산 상세"]
    assert res["통합_시트"] == ["요약", "입력·출처", "배당", "가산세", "쟁점 목록"]
    assert len([n for n in res["시트"] if n not in {x["시트"] for x in res["자유_시트"]}]) <= 8          # compact 시트 수는 자유 시트를 빼고 센다
    assert openpyxl.load_workbook(res["파일"]).sheetnames == res["시트"]
    legend = [v for v in _cells(res["파일"])["요약"].values() if isinstance(v, str) and v.startswith("호출자가 넣은 표")]
    assert legend == ["호출자가 넣은 표(계산 도구의 검증을 거치지 않음): '품목별 검산', '추정'. 그 밖의 시트는 계산 도구 결과."]


def test_every_formula_cell_has_a_cached_value(blend):
    path = blend["결과"]["파일"]
    f, v = _cells(path), _cells(path, True)
    formulas = [(s, k) for s, cells in f.items() for k, x in cells.items() if isinstance(x, str) and x.startswith("=") and
                openpyxl.load_workbook(path)[s][k].data_type == "f"]
    assert len(formulas) > 40 and not [x for x in formulas if v[x[0]].get(x[1]) is None]
    assert not any("미리보기" in w for w in blend.get("warnings") or [])


@pytest.mark.parametrize("formula, why", [
    ("=Sheet2!A1", "쓸 수 없음"), ("='입력·출처'!B5", "쓸 수 없음"), ("=[1]Sheet1!A1", "쓸 수 없음"), ("=cmd|' /C calc'!A0", "읽지 못함"),
    ("=HYPERLINK(\"http://x\",\"y\")", "함수 HYPERLINK"), ("=WEBSERVICE(\"http://x\")", "함수 WEBSERVICE"), ("=INDIRECT(\"B5\")", "함수 INDIRECT"),
    ("=B5+호출1_지급액", "쓸 수 없음"), ("=B:B", "쓸 수 없음"), ("=B5+B99", "표 밖"), ("=Z5", "표 밖"), ("=B4", "표 밖"), ("={1,2}", "쓸 수 없음"),
    ("=B5+", None), ("=C5", "순환"), ("=B5/0", "오류 값"), ("=B5+A5", "오류 값"), ("=" + "B5+" * 200 + "1", "넘음")])
def test_formula_outside_the_allowed_set_is_an_input_error(tmp_path, formula, why):
    r = _export(tmp_path, extra_sheets=[{"sheet": "표", "headers": ["항목", "값", "식"], "rows": [["가", 100, formula]]}])
    assert "error" in r and "extra_sheets" in r["error"] and not list(tmp_path.iterdir()), r      # 파일을 만들지 않음
    if why:
        assert why in r["error"], r["error"]


@pytest.mark.parametrize("formula, value", [
    ("=B5*2", 200), ("=SUM(B5:B5)+ROUND(B5/3,0)", 133), ("=IF(B5>50,MAX(B5,1),MIN(B5,1))", 100), ("=ROUNDUP(B5*1.5%,0)", 2),
    ("=TRUNC(B5/7,1)", 14.2), ("=$B$5-1", 99), ("=-B5", -100), ("=IF(A5=\"가\",1,0)", 1), ("=B5^2", 10_000), ("=LEN(A5)&\"자\"", "1자")])
def test_allowed_formulas_are_kept_live_with_cached_values(tmp_path, formula, value):
    r = _export(tmp_path, extra_sheets=[{"sheet": "표", "headers": ["항목", "값", "식"], "rows": [["가", 100, formula]]}])
    assert "error" not in r, r
    wb, wv = openpyxl.load_workbook(r["결과"]["파일"]), openpyxl.load_workbook(r["결과"]["파일"], data_only=True)
    assert wb["표"]["C5"].data_type == "f" and wv["표"]["C5"].value == value


def test_text_that_looks_like_a_formula_stays_text(tmp_path):
    r = _export(tmp_path, extra_sheets=[{"sheet": "=주입", "title": "=1+1", "note": "=cmd|'/c calc'!A0", "source": "=출처", "headers": ["=머리", "값", "메모"],
                                         "formats": ["text", "", "source"], "rows": [["=HYPERLINK(\"http://x\")", 5, "=WEBSERVICE(\"x\")"], "=띠"]}])
    assert "error" not in r, r
    wb = openpyxl.load_workbook(r["결과"]["파일"])
    ws = wb[r["결과"]["자유_시트"][0]["시트"]]
    assert not [x.coordinate for row in ws.iter_rows() for x in row if x.data_type == "f"]          # 수식 칸 없음 — 전부 글
    assert ws["A1"].value == "=1+1" and ws["A5"].value == "=HYPERLINK(\"http://x\")" and ws["C5"].value == "=WEBSERVICE(\"x\")" and ws["A6"].value == "=띠"


def test_sheet_names_follow_the_existing_rules(tmp_path):
    long = "가" * 40
    r = _export(tmp_path, scenarios=SCEN, extra_sheets=[{"sheet": "배당", "headers": ["a", "b"], "rows": [["x", 1]]}, {"sheet": "요약", "headers": ["a"], "rows": [["x"]]},
                                                         {"sheet": "A/B:C*?[1]", "headers": ["a"], "rows": [["x"]]}, {"sheet": long, "headers": ["a"], "rows": [["x"]]},
                                                         {"sheet": "a/b:c*?[1]", "headers": ["a"], "rows": [["x"]]}])
    names = [x["시트"] for x in r["결과"]["자유_시트"]]
    assert names == ["배당 (2)", "요약 (2)", "A B C   1", "가" * 31, "a b c   1 (2)"]                   # 중복·금지 문자·31자·대소문자
    assert openpyxl.load_workbook(r["결과"]["파일"]).sheetnames == r["결과"]["시트"]


@pytest.mark.parametrize("bad, phrase", [
    ("not json", "JSON"), ([{"sheet": "x", "rows": [[1]]}], "headers"), ([{"sheet": "x", "headers": ["a"]}], "rows"),
    ([{"sheet": "x", "headers": ["a"], "rows": [[1, 2]]}], "많음"), ([{"sheet": "x", "headers": ["a", "b"], "rows": [["x", 1]], "formats": ["", "won"]}], "서식"),
    ([{"sheet": "x", "headers": ["a", "b"], "rows": [["x", "y"]], "total": True}], "합계"), ([{"sheet": "x", "headers": ["a", "b"], "rows": [["x", [1]]]}], "목록"),
    ([{"sheet": "x", "headers": ["a", "b"], "rows": [["x", {"from_call": 1}]]}], "from_row"),
    ([{"sheet": "x", "headers": ["a", "b"], "rows": [["x", {"from_call": 9, "from_row": "합계"}]]}], "from_call"),
    ([{"sheet": "x", "headers": ["a", "b"], "rows": [["x", {"from_call": 1, "from_row": "없는 줄"}]]}], "쓸 수 있는 줄")])
def test_bad_extra_sheets_are_input_errors(tmp_path, bad, phrase):
    r = _export(tmp_path, extra_sheets=bad)
    assert "error" in r and phrase in r["error"] and not list(tmp_path.iterdir()), r


def test_extra_sheets_work_without_scenarios_and_in_english(tmp_path):
    for kw in (dict(), dict(layout="steps"), dict(lang="en")):
        base = _export(tmp_path, **kw)
        r = _export(tmp_path, extra_sheets=json.dumps(EXTRA), **kw)                               # JSON 문자열도 받음
        assert "error" not in r and "통합_시트" not in r["결과"], r
        assert r["결과"]["시트"] == base["결과"]["시트"][:1] + ["품목별 검산", "추정"] + base["결과"]["시트"][1:]
        a, b = _cells(base["결과"]["파일"]), _cells(r["결과"]["파일"])
        first = base["결과"]["시트"][0]
        legend = [k for k, v in b[first].items() if isinstance(v, str) and ("호출자가 넣은 표" in v or "Preparer's own tables" in v)]
        assert len(legend) == 1 and {k: v for k, v in b[first].items() if k not in legend} == a[first]     # 기존 시트는 범례 한 줄만 더함
        assert all(a[n] == b[n] for n in base["결과"]["시트"][1:])
        v = _cells(r["결과"]["파일"], True)["품목별 검산"]
        assert b["품목별 검산"]["B10"] == 8_000_000 and v["C10"] == 2_000_000                       # 가리킬 칸이 없으면 도구 값
        assert any("도구 값을 옮김" in w or "tool value copied" in w for w in r["warnings"])


def test_output_is_unchanged_when_new_inputs_are_not_given(tmp_path):
    for kw in (dict(), dict(layout="steps"), dict(lang="en")):
        a, b = _export(tmp_path, **kw), _export(tmp_path, extra_sheets=None, actions=[], key_figures="", **kw)
        assert set(a["결과"]) == set(b["결과"]) and a["결과"]["시트"] == b["결과"]["시트"]
        x, y = _cells(a["결과"]["파일"]), _cells(b["결과"]["파일"])
        strip = lambda d: {s: {k: v for k, v in cells.items() if not (isinstance(v, str) and v.startswith("t"))} for s, cells in d.items()}
        assert strip(x) == strip(y)
        assert "자유_시트" not in a["결과"] and "통합_시트" not in a["결과"]


# ── 요약 시트: 핵심 숫자 표·조치·기한 ────────────────────────────────────────
def test_summary_has_key_figures_actions_and_issue_line(blend):
    wb = openpyxl.load_workbook(blend["결과"]["파일"])
    ws, wv = wb["요약"], openpyxl.load_workbook(blend["결과"]["파일"], data_only=True)["요약"]
    assert [ws.cell(4, j).value for j in range(1, 5)] == ["핵심 숫자", "금액(원)", "계산 위치", "메모"]
    rows = [[ws.cell(r, j).value for j in range(1, 5)] for r in (5, 6, 7)]
    assert rows[0][0] == "이번에 낼 세금" and rows[0][1].startswith("='배당'!$C$") and rows[0][2] == "배당" and rows[0][3] == "=메모"
    assert rows[1][0] == "가산세 (부족분 가산세)" and rows[1][1].startswith("='가산세'!$B$")                    # label을 비우면 줄 이름 + 열 제목
    assert rows[2][:3] == ["검산 값", "='품목별 검산'!$B$9", "품목별 검산"]
    assert [wv.cell(r, 2).value for r in (5, 6, 7)] == [8_800_000, c("withholding_late_payment_penalty", CALLS[2]["args"])["결과"]["가산세"], 33_000]
    assert ws["A5"].font.b and ws["B5"].fill.fgColor.rgb == "00FFFF00" and not ws["A6"].font.b and ws["D5"].data_type == "s"
    assert ws["C7"].hyperlink.location == "'품목별 검산'!B9"
    r0 = next(r for r in range(1, ws.max_row + 1) if ws.cell(r, 1).value == "조치·기한 2건")
    assert [ws.cell(r0 + 1, j).value for j in range(1, 5)] == ["조치", "기한", "담당", "근거"]
    assert [[ws.cell(r0 + k, j).value for j in range(1, 5)] for k in (2, 3)] == [
        ["수정신고", "2025-10-10", "재무팀", "국세기본법 제45조"], ["=영수증 교부", "납부 후 30일", None, "약정 제5조"]]
    assert ws.cell(r0 + 3, 1).data_type == "s"                                                    # 받은 글 그대로 — '='로 시작해도 글
    texts = [ws.cell(r, 1).value for r in range(1, ws.max_row + 1)]
    assert "쟁점 3건 — '쟁점 목록' 시트" in texts and texts.index("쟁점 3건 — '쟁점 목록' 시트") > r0 and ws.max_row <= 25
    iss = wb["쟁점 목록"]
    assert iss["F4"].value == "금액" and iss["F5"].value.startswith("='가산세'!$B$") and iss["F6"].value == 1_234_000 and iss["F7"].value is None


def test_default_key_figures_use_the_recommended_column(tmp_path):
    r = _export(tmp_path, scenarios=SCEN, actions=[{"action": "신고", "due": "2025-10-10"}])
    ws = openpyxl.load_workbook(r["결과"]["파일"])["요약"]
    a = [ws.cell(k, 1).value for k in range(5, ws.max_row + 1)]
    main = [t for t in a if t and t.endswith("(맞는 금액)")]
    assert len(main) == 5 and a[:5] == main and a[5] == "배당 — 신고한 대로 vs 맞는 금액 — 합계 (신고한 대로)"   # 권고 열의 결과 줄, 그 아래 나머지 열의 합계 줄
    bold = [t for k, t in enumerate(a, 5) if t and ws.cell(k, 1).font.b and ws.cell(k, 2).fill.fgColor.rgb == "00FFFF00"]
    assert bold == ["배당 — 신고한 대로 vs 맞는 금액 — 합계 (맞는 금액)", "가산세 — 부족분 — 가산세"]                  # 블록마다 합계 줄만 강조
    assert ws.cell(5, 4).value == "메모 한 줄"
    r0 = next(k for k in range(1, ws.max_row + 1) if ws.cell(k, 1).value == "조치·기한 1건")
    assert [ws.cell(r0 + 1, j).value for j in (1, 2, 3)] == ["조치", "기한", "근거"]                    # 담당을 안 적으면 그 열 없이


def test_actions_or_key_figures_alone_make_the_summary(tmp_path):
    r = _export(tmp_path, actions=["지급명세서 제출"])
    assert r["결과"]["통합_시트"][0] == "요약" and "조치·기한 1건" in _cells(r["결과"]["파일"])["요약"].values()
    r = _export(tmp_path, key_figures=[{"call": 1, "row": "amount", "label": "지급액"}])
    assert _cells(r["결과"]["파일"], True)["요약"]["B5"] == 40_000_000


@pytest.mark.parametrize("kw, phrase", [
    (dict(key_figures=[{"call": 1, "row": "없는 줄"}]), "쓸 수 있는 줄: "), (dict(key_figures=[{"call": "없는 호출", "row": "합계"}]), "calls에서 찾지 못함"),
    (dict(key_figures=[{"sheet": "없는 시트", "cell": "B5"}], extra_sheets=EXTRA), "쓸 수 있는 이름: 품목별 검산, 추정"),
    (dict(key_figures=[{"sheet": "추정", "cell": "B9"}], extra_sheets=EXTRA), "표 밖"), (dict(key_figures=[{"sheet": "추정", "cell": "D5"}], extra_sheets=EXTRA), "숫자·수식 칸이 아님"),
    (dict(key_figures=[{"sheet": "품목별 검산", "cell": "D5"}], extra_sheets=EXTRA), "숫자·수식 칸이 아님"),
    (dict(key_figures=[{"label": "x"}]), "한 가지로"), (dict(actions=[{"due": "내일"}]), "action"), (dict(actions="{"), "JSON"),
    (dict(scenarios=SCEN, issues=[{"issue": "x", "amount": {"from_call": 1, "from_row": "없는 줄"}}]), "쓸 수 있는 줄")])
def test_bad_key_figures_and_actions_name_what_is_available(tmp_path, kw, phrase):
    r = _export(tmp_path, **kw)
    assert "error" in r and phrase in r["error"] and not list(tmp_path.iterdir()), r


# ── LibreOffice 재계산과 비교 ────────────────────────────────────────────────
@pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice 없음")
def test_cached_values_match_libreoffice(blend, tmp_path):
    from tests.test_workbook_cached_values import compare_with_libreoffice
    n, bad = compare_with_libreoffice(blend["결과"]["파일"], tmp_path)
    assert n > 40 and bad == []


# ── 설명·안내: 두 길(만들기 / 직접 짠 뒤 대조) ────────────────────────────────
def test_description_and_guidance_point_to_both_ways():
    doc = S.mcp._tool_manager._tools["export_workbook"].description
    lines = doc.splitlines()
    assert "verify_workbook" in lines[0] and "extra_sheets" in lines[0] and "as-filed vs correct" in lines[0]
    assert "신고한 대로 vs 맞는 금액" in doc[:1200] and "extra_sheets" in doc[:1200] and "시나리오마다 한 번씩" in doc[:1200]
    assert "예(지어낸 값)" in doc and "from_call" in doc and "less:6000000" in doc.replace(" ", "")
    for name in ("extra_sheets —", "actions —", "key_figures —"):
        assert name in doc
    tail = S.corporate_tax(base=123_000_000, year=2024)["엑셀"]
    assert "사용자가 엑셀(Excel)을 요청했다면" in tail and "verify_workbook" in tail and "시나리오마다 한 번씩" in tail
    hint = S.find_tool(query="excel workings")["결과"]["엑셀 문서"]
    assert "export_workbook" in hint and "verify_workbook" in hint and "extra_sheets" in hint
    for text in (doc, tail, hint, S.mcp.instructions, S.mcp._tool_manager._tools["verify_workbook"].description):
        for gone in ("직접 만들지", "do not write your own", "instead of writing", "do not build"):
            assert gone not in text, gone


def test_description_example_runs_as_written(tmp_path):
    """설명에 실은 예(지어낸 값)가 그대로 돌아가고 부족분 칸이 수식으로 이어진다."""
    r = _export(tmp_path, scenarios=SCEN, sources=SRC)
    assert "error" not in r and not [w for w in r.get("warnings") or [] if "연결하지 않음" in w]
    f = _cells(r["결과"]["파일"])["입력·출처"]
    link = next(v for v in f.values() if isinstance(v, str) and v.startswith("='배당'!$C$") and "-" in v)
    assert link.split("-")[1].startswith("$B$")
