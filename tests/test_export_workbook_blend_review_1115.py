"""export_workbook 통합 문서 — 독립 검토에서 재현된 결함 7건의 재현 입력과 고친 뒤 기대(2026-11-15, Claude).

 1. 전용 수식 틀에 맞지 않는 납부고지 가산세(제4항 5년 한도 등)는 도구 값을 옮긴다 — 요약의 가산세 = 도구 값.
    (도구의 `계산식`은 납부고지 전 부분이라, 그 마지막 단계 이름도 '납부고지_전_가산세'로 적는다.)
 2. `계산식`의 식이 엑셀 수식이 아닌 단계(숫자뿐·"None"·'결과.…')는 도구 값을 옮긴다 — 전 도구를 시나리오 블록으로 넣어 오류 칸 0, 값 = 도구 값.
 3. '='로 시작하는 호출자 글(제목·회사·머리글·메모·출처 등)은 글로 저장한다(수식 아님) — 통합 문서와 기존 경로 모두.
 4. 문자열로 온 args("85000000"·"0.15"·"false")는 도구와 같은 값으로 바꿔 틀을 만든다.
 5. 시트 이름은 대소문자만 다르면 같은 이름으로 보고, 31자로 자른 끝의 작은따옴표를 뗀다.
 6. sources의 from_call 순환·음수 less는 입력 오류, from_call 없는 less는 경고.
 7. 한 블록에 종전·개정 납부고지 건이 섞여도 줄 이름이 열마다 맞고, 날짜 입력에 from_call을 걸면 읽을 수 있는 경고.
사례 값은 모두 지어낸 값. 가산세 근거: 국세기본법 제47조의5제1항·제4항·제5항(도구 withholding_late_payment_penalty가 쓰는 것 그대로)."""
import json
import pathlib
import re
import shutil
import subprocess

import openpyxl
import pytest
from openpyxl.formula import Tokenizer

from korean_tax_calc_mcp.server import mcp
from tests._helpers import call as c

HAS_LO = pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice 없음")
DIV = dict(income_kind="배당", recipient_type="법인", residence_country="미국", amount=85_000_000, treaty_rate=0.15)
PEN = dict(unpaid_tax=1_110_000, due="2024-03-11", until="2024-05-20")
BASE = [{"label": "A", "tool": "nonresident_withholding", "args": DIV},
        {"label": "B", "tool": "nonresident_withholding", "args": dict(DIV)},
        {"label": "P", "tool": "withholding_late_payment_penalty", "args": PEN}]
FIVE_YEARS = dict(unpaid_tax=1_500_000, due="2021-03-28", until="2022-05-02", notice_due="2022-06-01", paid_on="2027-08-14")
ENT = dict(year=2025, sme=False, general_revenue=10_000_000_000, expensed=80_000_000)


def export(d, calls, name="검토", **kw):
    return c("export_workbook", {"title": name, "calls": calls, "output_dir": str(d), **kw})


def recalc(path, d):
    out = pathlib.Path(d) / "re"
    subprocess.run(["soffice", f"-env:UserInstallation=file://{pathlib.Path(d) / 'lo_profile'}", "--headless", "--calc", "--convert-to", "xlsx",
                    "--outdir", str(out), str(path)], check=True, capture_output=True, timeout=300)
    return openpyxl.load_workbook(next(out.glob("*.xlsx")), data_only=True)


def col(ws, j=2):
    return {ws.cell(r, 1).value: ws.cell(r, j).value for r in range(1, ws.max_row + 1) if ws.cell(r, 1).value}


def formula_cells(wb, sheets=None):
    return [(ws.title, x.coordinate, x.value) for ws in wb.worksheets if sheets is None or ws.title in sheets
            for row in ws.iter_rows() for x in row if x.data_type == "f"]


def error_cells(wb, sheets):
    return [(ws.title, x.coordinate, x.value) for ws in wb.worksheets if ws.title in sheets for row in ws.iter_rows() for x in row
            if isinstance(x.value, str) and (re.match(r"#[A-Z]", x.value) or x.value.startswith("Err:"))]


def lint(wb, sheets):
    """수식이 없는 시트·없는 이름·함수 아닌 낱말을 가리키면 그 칸을 돌려준다(LibreOffice 없이도 #NAME? 후보를 잡음)."""
    names, bad = set(wb.defined_names), []
    for sh, co, f in formula_cells(wb, sheets):
        for t in Tokenizer(f).items:
            if t.type != "OPERAND" or t.subtype != "RANGE":
                continue
            v = t.value
            if "!" in v:
                s = v.rpartition("!")[0]
                s = s[1:-1].replace("''", "'") if s.startswith("'") else s
                if s not in wb.sheetnames:
                    bad.append((sh, co, f))
            elif not re.fullmatch(r"\$?[A-Z]{1,3}\$?\d+(:\$?[A-Z]{1,3}\$?\d+)?", v) and v not in names and v.upper() not in ("TRUE", "FALSE"):
                bad.append((sh, co, f))
    return bad


# ── 1. 전용 틀에 맞지 않는 납부고지 가산세 ─────────────────────────────────────
def test_notice_penalty_outside_layout_copies_tool_values(tmp_path):
    tool = c("withholding_late_payment_penalty", FIVE_YEARS)["결과"]
    assert tool["가산세"] == 750_000 and tool["고지후_일수"] == 1826           # 제4항 5년 한도에 걸려 전용 틀이 없는 경우
    r = export(tmp_path, [{"label": "5년한도", "tool": "withholding_late_payment_penalty", "args": FIVE_YEARS}], issues=[{"issue": "x"}])
    wb = openpyxl.load_workbook(r["결과"]["파일"])
    ws = wb[r["결과"]["통합_시트"][2]]
    rows = {ws.cell(k, 1).value: ws.cell(k, 2) for k in range(1, ws.max_row + 1) if ws.cell(k, 1).value}
    assert rows["가산세"].value == 750_000 and rows["가산세"].data_type == "n"      # 수식이 아니라 도구 값
    assert rows["고지후분"].value == tool["고지후분"] and rows["한도_50%"].value == 750_000
    notes = col(ws, 3)
    assert notes["가산세"] == "도구 값(수식 틀 없음)"
    assert any(v == "이 도구는 수식 틀이 없어 결과 값을 옮김" for v in col(ws, 1))
    summary = wb[r["결과"]["통합_시트"][0]]
    link = next(summary.cell(k, 2).value for k in range(1, summary.max_row + 1) if str(summary.cell(k, 1).value).endswith("— 가산세"))
    assert link == f"='{ws.title}'!$B${rows['가산세'].row}"                       # 요약은 그 값 칸을 가리킴
    en = export(tmp_path, [{"label": "5y", "tool": "withholding_late_payment_penalty", "args": FIVE_YEARS}], "en", issues=[{"issue": "x"}], lang="en")
    w2 = openpyxl.load_workbook(en["결과"]["파일"])[en["결과"]["통합_시트"][2]]
    assert "Tool value (no formula layout)" in col(w2, 3).values()


@pytest.mark.parametrize("args", [
    FIVE_YEARS,
    dict(unpaid_tax=1_200_000, due="2021-05-10", until="2021-09-01", notice_due="2021-10-01", paid_on="2022-03-01"),      # 제5항 소액 기준 경과조치
    dict(unpaid_tax=1_499_999, due="2021-05-09", until="2021-05-09", notice_due="2021-06-09", paid_on="2021-07-10"),      # 고지일 = 법정납부기한
    dict(unpaid_tax=30_000_000, due="2024-03-11", until="2024-05-20", notice_due="2024-06-20", paid_on="2024-09-01"),     # 전용 틀이 있는 경우
])
def test_notice_penalty_steps_name_the_pre_notice_amount(args):
    """도구 결과에 서식 칸용으로 붙이는 `계산식` — 납부고지 후분이 있으면 마지막 단계는 '납부고지 전' 금액이고 값도 그 금액('계산 N' 대조 칸이 일치)."""
    from korean_tax_calc_mcp.forms_workbook import export_form_inputs
    data = c("withholding_late_payment_penalty", args)
    res = data["결과"]
    steps = {s["이름"]: s for s in export_form_inputs("withholding_late_payment_penalty", args, data)["계산식"]}
    pre = min(res["3%분"] + res["일수분"], res["한도_10%"])
    if res["가산세"] == steps.get("가산세", {}).get("값"):
        assert "납부고지_전_가산세" not in steps
    else:
        assert "가산세" not in steps and abs(steps["납부고지_전_가산세"]["값"] - pre) <= 1 and steps["납부고지_전_가산세"]["값"] < res["가산세"]
    assert steps["기본가산세"]["값"] == res["3%분"] and steps["기본가산세"]["식"] == "ROUNDDOWN(미납세액*3/100,0)"


def test_on_time_payment_steps_have_no_fixed_portion():
    from korean_tax_calc_mcp.forms_workbook import export_form_inputs
    args = dict(unpaid_tax=987_650, due="2026-08-10", until="2026-08-10")
    data = c("withholding_late_payment_penalty", args)
    steps = {s["이름"]: s for s in export_form_inputs("withholding_late_payment_penalty", args, data)["계산식"]}
    assert data["결과"]["가산세"] == 0 and steps["기본가산세"]["식"] == "ROUNDDOWN(0,0)" and steps["가산세"]["값"] == 0


@HAS_LO
def test_notice_penalty_summary_equals_tool_after_recalc(tmp_path):
    cases = {"5년한도": FIVE_YEARS,
             "소액경과": dict(unpaid_tax=1_200_000, due="2021-05-10", until="2021-09-01", notice_due="2021-10-01", paid_on="2022-03-01"),
             "틀있음": dict(unpaid_tax=30_000_000, due="2024-03-11", until="2024-05-20", notice_due="2024-06-20", paid_on="2024-09-01")}
    calls = [{"label": k, "tool": "withholding_late_payment_penalty", "args": a} for k, a in cases.items()]
    r = export(tmp_path, calls, scenarios=[{"sheet": k, "columns": [k]} for k in cases], detail="full")
    wb = recalc(r["결과"]["파일"], tmp_path)
    assert error_cells(wb, wb.sheetnames) == []
    for k, a in cases.items():
        assert col(wb[k])["가산세"] == c("withholding_late_payment_penalty", a)["결과"]["가산세"], k
    checks = [x.value for ws in wb.worksheets for row in ws.iter_rows() for x in row if x.value in ("일치", "확인 필요")]
    assert checks and set(checks) == {"일치"}                                     # '계산 N'의 대조 칸까지


# ── 2. 수식이 아닌 `계산식` 단계 ─────────────────────────────────────────────
@pytest.mark.parametrize("tool", ["entertainment_limit", "donation_limit", "business_car_expense"])
def test_non_formula_steps_are_copied_as_values(tmp_path, tool):
    args = ENT if tool == "entertainment_limit" else _sample_args(tool)
    data = c(tool, args)
    assert "결과" in data, data
    r = export(tmp_path, [{"label": "E", "tool": tool, "args": args}], issues=[{"issue": "x"}], detail="full")
    wb = openpyxl.load_workbook(r["결과"]["파일"])
    front = r["결과"]["통합_시트"]
    assert lint(wb, wb.sheetnames) == []
    fs = formula_cells(wb)
    assert not [f for f in fs if re.search(r"None|결과\.", f[2])]                 # '=None'·'=결과.…'이 없음(기존 '계산 N' 시트 포함)
    ws = wb[front[2]]
    for k in range(1, ws.max_row + 1):                                            # B열: 입력 링크 또는 값 — 숫자뿐인 식을 수식으로 적지 않음
        x = ws.cell(k, 2)
        assert x.data_type != "f" or x.value.startswith("='") or re.search(r"[A-Z]+\d", x.value), (k, x.value)


def test_step_formula_rules():
    from korean_tax_calc_mcp.workbook_blend import _step_formula as f
    names = {"미납세액", "일수1"}
    assert f("ROUNDDOWN(미납세액*3/100,0)", names) == "=ROUNDDOWN({미납세액}*3/100,0)"
    assert f("미납세액", names) == "={미납세액}"
    for bad in ("36000000", "None", "", None, "결과.시부인_대상", "미납세액+없는이름", "미납세액*{x}", 'IF(미납세액>0,"a","b")'):
        assert f(bad, names) is None, bad


SAMPLES = json.loads((pathlib.Path(__file__).parent / "data" / "blend_sweep_calls.json").read_text(encoding="utf-8"))
# 표본 호출이 없는 도구: 결과가 표 모양이 아니거나(안내·검색·PDF·시세 조회·관계 판정) export_workbook 자신
NO_SAMPLE = {"dominant_shareholder", "export_workbook", "verify_workbook", "extract_relations", "kinship_check", "official_property_price", "ownership_ratio",
             "precheck_schema", "related_judge", "return_precheck", "return_precheck_pdf", "stock_price_lookup",
             "tunnelling_from_pdf", "tunnelling_gift", "tunnelling_gift_nts",
             "kr_comparable_candidates"}   # OpenDART 키·네트워크가 필요한 도구


def _sample_args(tool):
    return json.loads(json.dumps(SAMPLES[tool]).replace("{TESTS}", str(pathlib.Path(__file__).parent)))


def test_every_tool_has_a_sample_call():
    registered = {t.name for t in mcp._tool_manager.list_tools()}
    assert registered - set(SAMPLES) == NO_SAMPLE and not set(SAMPLES) - registered      # 새 도구를 넣으면 표본 호출도 넣는다


@pytest.fixture(scope="module")
def sweep(tmp_path_factory):
    """전 도구(표본 124개)를 call마다 시나리오 블록 하나로 넣은 통합 문서 — 25개씩."""
    tools, out = sorted(SAMPLES), []
    for k in range(0, len(tools), 25):
        d = tmp_path_factory.mktemp(f"sweep{k}")
        calls = [{"label": f"t{k + i}", "tool": t, "args": _sample_args(t)} for i, t in enumerate(tools[k:k + 25])]
        r = export(d, calls, f"전도구{k}", scenarios=[{"sheet": x["label"], "columns": [x["label"]]} for x in calls], detail="compact")
        assert "error" not in r and r["결과"]["오류_call"] == [], r
        out.append((d, calls, r))
    return out


def test_every_tool_in_a_scenario_block_has_no_broken_formula(sweep):
    for _, calls, r in sweep:
        wb = openpyxl.load_workbook(r["결과"]["파일"])
        assert [x["label"] for x in calls] == r["결과"]["통합_시트"][2:2 + len(calls)]
        assert lint(wb, wb.sheetnames) == []
        assert not [f for f in formula_cells(wb) if re.search(r"=None|결과\.", f[2])]


@HAS_LO
def test_every_tool_in_a_scenario_block_recalculates_to_tool_values(sweep):
    compared = 0
    for d, calls, r in sweep:
        raw, wb = openpyxl.load_workbook(r["결과"]["파일"]), recalc(r["결과"]["파일"], d)
        front = r["결과"]["통합_시트"]
        assert error_cells(wb, wb.sheetnames) == []
        summary = col(wb[front[0]])
        for x in calls:
            res = c(x["tool"], x["args"]).get("결과") or {}
            ws, wr = wb[x["label"]], raw[x["label"]]
            for k in range(1, ws.max_row + 1):
                lab, v, src = ws.cell(k, 1).value, ws.cell(k, 2).value, wr.cell(k, 2)
                if src.data_type == "f" and str(src.value).startswith("='"):        # 입력 링크 줄(입력 이름이 결과 키와 같을 수 있음)
                    continue
                want = res.get(lab)
                if isinstance(want, (int, float)) and not isinstance(want, bool) and v is not None:
                    assert abs(v - want) < 1e-6, (x["tool"], lab, v, want, src.value)
                    compared += 1
        assert not [k for k, v in summary.items() if isinstance(v, str) and v.startswith("#")]
    assert compared > 400


# ── 3. '='로 시작하는 글 ───────────────────────────────────────────────────
def test_user_text_starting_with_equals_is_stored_as_text(tmp_path):
    calls = BASE[:1] + [{"label": "B", "tool": "nonresident_withholding", "args": {**DIV, "net_of_tax": True}}, BASE[2]]
    sc = [{"sheet": "S", "title": "=1+1", "subtitle": "=2+2", "heading": '=HYPERLINK("http://x","h")',
           "columns": [{"call": "A", "heading": "=3+3"}, {"call": "B", "heading": "+4"}], "notes": {"합계": "=가정: 환율 1,300"}, "summary_note": "=5+5"}]
    so = [{"call": "A", "arg": "amount", "source": "=이사회 의사록", "label": "=라벨"},
          {"call": "P", "arg": "unpaid_tax", "from_call": "A", "from_row": "원천징수세액", "less": 11_640_000, "less_label": "=차감", "less_source": "=출처"}]
    for lang in ("ko", "en"):
        r = export(tmp_path, calls, "=제목", scenarios=sc, sources=so, issues=[{"issue": "=x", "risk": "-y", "action": "@z"}], company="=회사",
                   period="=기간", lang=lang, filename=f"inj_{lang}")
        wb = openpyxl.load_workbook(r["결과"]["파일"])
        user = ("=제목", "=회사", "=기간", "=1+1", "=2+2", "=HYPERLINK", "=3+3", "=가정", "=5+5", "=이사회", "=라벨", "=차감", "=출처", "=x")
        assert not [f for f in formula_cells(wb) if f[2].startswith(user)], lang
        texts = {x.value for ws in wb.worksheets for row in ws.iter_rows() for x in row if x.data_type == "s"}
        assert {"=1+1", "=2+2", "=3+3", "=5+5", "=이사회 의사록", "=차감", "=출처", "=x"} <= texts
        assert any(t.startswith("=제목 — ") for t in texts) and any(t.startswith("=회사 | =기간") for t in texts)
        assert wb["S"]["A1"].quotePrefix and wb["S"]["A1"].value == "=1+1"
        linked = next(x for row in wb[r["결과"]["통합_시트"][1]].iter_rows() for x in row if x.data_type == "f")      # from_call 연결 수식은 그대로
        assert linked.value.startswith("='S'!$B$") and linked.value.endswith(f"-$B${linked.row - 1}")


@pytest.mark.parametrize("kw", [dict(), dict(lang="en"), dict(layout="steps"), dict(layout="steps", lang="en")])
def test_user_text_on_the_plain_path_is_stored_as_text(tmp_path, kw):
    r = export(tmp_path, [{"label": "=1+7", "tool": "nonresident_withholding", "args": DIV}], "=1+1", company="=2+2", period="=3+3", biz_no="=4+4",
               review_notes=["=5+5"], filename="plain", **kw)
    wb = openpyxl.load_workbook(r["결과"]["파일"])
    assert not [f for f in formula_cells(wb) if re.match(r"=\d\+\d", f[2])]
    assert any(x.value == "=1+7" and x.data_type == "s" for ws in wb.worksheets for row in ws.iter_rows() for x in row)


# ── 4. 문자열로 온 args ────────────────────────────────────────────────────
def test_string_typed_args_build_the_same_layout(tmp_path):
    s_args = {**DIV, "amount": "85000000", "treaty_rate": "0.15", "net_of_tax": "false"}
    p_args = dict(unpaid_tax="1110000", due="2024-03-11", until="2024-05-20")
    calls = lambda a, p: [{"label": "S", "tool": "nonresident_withholding", "args": a}, {"label": "D", "tool": "withholding_late_payment_penalty", "args": p}]
    (tmp_path / "s").mkdir()
    (tmp_path / "n").mkdir()
    got = export(tmp_path / "s", calls(s_args, p_args), issues=[{"issue": "x"}], detail="full")
    want = export(tmp_path / "n", calls(DIV, PEN), issues=[{"issue": "x"}], detail="full")
    a, b = openpyxl.load_workbook(got["결과"]["파일"]), openpyxl.load_workbook(want["결과"]["파일"])
    for name in got["결과"]["통합_시트"]:
        assert {x.coordinate: x.value for row in a[name].iter_rows() for x in row} == {x.coordinate: x.value for row in b[name].iter_rows() for x in row}, name
    inputs = col(a[got["결과"]["통합_시트"][1]])
    assert inputs["지급액(순액 약정이면 약정 순액)"] == 85_000_000 and inputs["조세조약 제한세율"] == 0.15 and inputs["미납·과소납부 세액"] == 1_110_000
    assert col(a["S"])["세금 부담"].startswith("수취인 부담") and a["S"]["B" + str(next(k for k in range(1, 40) if a["S"].cell(k, 1).value == "과세표준"))].value.count("ROUND") == 0


def test_tool_args_conversion():
    from korean_tax_calc_mcp.workbook_blend import _tool_args
    got = _tool_args("nonresident_withholding", {**DIV, "amount": "85000000", "treaty_rate": "0.15", "net_of_tax": "false", "payer_bears_local_tax": "true"})
    assert got["amount"] == 85_000_000 and got["treaty_rate"] == 0.15 and got["net_of_tax"] is False and got["payer_bears_local_tax"] is True
    assert set(got) == set(DIV) | {"net_of_tax", "payer_bears_local_tax"}          # 넣지 않은 입력은 더하지 않음
    assert _tool_args("없는_도구", {"a": "1"}) == {"a": "1"} and _tool_args("nonresident_withholding", {"amount": "많이"}) == {"amount": "많이"}


# ── 5. 시트 이름 ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("lang", ["ko", "en"])
def test_sheet_names_case_and_trailing_quote(tmp_path, lang):
    long_q = "a" * 30 + "'bbb"                                                    # 31자로 자르면 끝이 작은따옴표
    sc = [{"sheet": "summary", "columns": ["A"]}, {"sheet": "INPUTS", "columns": ["B"]}, {"sheet": long_q, "columns": ["P"]}]
    r = export(tmp_path, BASE, scenarios=sc, lang=lang)
    assert "error" not in r, r
    names = r["결과"]["시트"]
    assert len({n.casefold() for n in names}) == len(names) and all(len(n) <= 31 and not n.startswith("'") and not n.endswith("'") for n in names)
    assert "a" * 30 in names
    if lang == "en":
        assert names[:5] == ["Summary", "Inputs", "summary (2)", "INPUTS (2)", "a" * 30]
    wb = openpyxl.load_workbook(r["결과"]["파일"])
    assert lint(wb, wb.sheetnames) == []


def test_sheet_name_helper():
    from korean_tax_calc_mcp.workbook_blend import _sheet_name
    wb = openpyxl.Workbook()
    wb.active.title = "Summary"
    taken: set = set()
    assert _sheet_name(wb, "summary", taken) == "summary (2)" and _sheet_name(wb, "SUMMARY", taken) == "SUMMARY (3)"
    assert _sheet_name(wb, "x" * 30 + "'y", taken) == "x" * 30 and _sheet_name(wb, "'q'", taken) == "q" and _sheet_name(wb, "[]:*?/\\", taken) == "Sheet"
    assert _sheet_name(wb, "x" * 40, taken) == "x" * 31 and _sheet_name(wb, "x" * 40, taken) == "x" * 27 + " (2)"


# ── 6. from_call 순환·less ─────────────────────────────────────────────────
@pytest.mark.parametrize("sources,msg", [
    ([{"call": "A", "arg": "amount", "from_call": "B", "from_row": "과세표준"}, {"call": "B", "arg": "amount", "from_call": "A", "from_row": "과세표준"}], "순환"),
    ([{"call": "A", "arg": "amount", "from_call": "B", "from_row": "합계"}, {"call": "B", "arg": "amount", "from_call": "P", "from_row": "가산세"},
      {"call": "P", "arg": "unpaid_tax", "from_call": "A", "from_row": "합계"}], "순환"),
    ([{"call": "P", "arg": "unpaid_tax", "from_call": "A", "from_row": "원천징수세액", "less": -1}], "0 이상의 숫자"),
    ([{"call": "P", "arg": "unpaid_tax", "from_call": "A", "from_row": "원천징수세액", "less": "11640000"}], "0 이상의 숫자"),
])
def test_from_call_cycle_and_negative_less_are_input_errors(tmp_path, sources, msg):
    r = export(tmp_path, BASE, sources=sources)
    assert "error" in r and msg in r["error"], r


def test_less_without_from_call_warns_and_chain_without_cycle_works(tmp_path):
    r = export(tmp_path, BASE, sources=[{"call": "P", "arg": "unpaid_tax", "less": 5, "source": "s"}])
    assert "error" not in r and any("less는 from_call" in w for w in r["warnings"])
    ok = export(tmp_path, BASE, sources=[{"call": "P", "arg": "unpaid_tax", "from_call": "A", "from_row": "원천징수세액", "less": 11_640_000}], filename="ok")
    assert "error" not in ok and not ok.get("warnings")


# ── 7. 표기 ────────────────────────────────────────────────────────────────
OLD_N = dict(unpaid_tax=30_000_000, due="2024-03-11", until="2024-05-20", notice_due="2024-06-20", paid_on="2024-09-01")
NEW_N = dict(unpaid_tax=30_000_000, due="2026-08-10", until="2026-09-25", notice_due="2026-10-25", paid_on="2027-03-01", dunning_fee=2830)
MIXED = [{"label": "n1", "tool": "withholding_late_payment_penalty", "args": OLD_N},
         {"label": "n2", "tool": "withholding_late_payment_penalty", "args": {**OLD_N, "notice_amount": 1_200_000}},
         {"label": "n3", "tool": "withholding_late_payment_penalty", "args": NEW_N},
         {"label": "n4", "tool": "withholding_late_payment_penalty", "args": {**NEW_N, "notice_amount": 50_000_000}}]


def test_mixed_old_and_new_notice_columns_keep_their_own_row_names(tmp_path):
    r = export(tmp_path, MIXED, scenarios=[{"sheet": "S", "heading": "h", "columns": ["n1", "n2", "n3", "n4"]}])
    wb = openpyxl.load_workbook(r["결과"]["파일"])
    ws = wb["S"]
    row = {ws.cell(k, 1).value: [ws.cell(k, j).value is not None for j in range(2, 6)] for k in range(1, ws.max_row + 1) if ws.cell(k, 1).value}
    assert row["납부고지 후분(종전 2호 일수분)"] == [True, True, False, False] and row["납부고지 후분(3호)"] == [False, False, True, True]
    assert row["납부고지서별·세목별 세액"] == [False, True, False, True]                                    # 입력한 고지세액은 입력 줄에
    assert row["납부고지서별·세목별 세액(미납세액 + 납부고지 전 가산세로 봄)"] == [True, False, True, False]
    summary = wb[r["결과"]["통합_시트"][0]]
    names = [str(summary.cell(k, 1).value) for k in range(5, summary.max_row + 1) if str(summary.cell(k, 2).value).startswith("=")]
    # 0.56.0: 요약은 첫 열(n1)의 결과 줄 + 나머지 열의 합계(가산세) 줄 — 첫 열에 없는 줄 이름(3호)은 올리지 않음
    assert any("납부고지 후분(종전 2호 일수분) (n1)" in t for t in names) and not any("납부고지 후분(3호)" in t for t in names)
    assert [t.rsplit(" — ", 1)[1] for t in names if " — 가산세 (" in t] == [f"가산세 ({n})" for n in ("n1", "n2", "n3", "n4")]
    assert lint(wb, wb.sheetnames) == []


@HAS_LO
def test_mixed_notice_columns_recalculate_to_tool_values(tmp_path):
    r = export(tmp_path, MIXED, scenarios=[{"sheet": "S", "heading": "h", "columns": ["n1", "n2", "n3", "n4"]}])
    wb = recalc(r["결과"]["파일"], tmp_path)
    ws = wb["S"]
    k = next(k for k in range(1, ws.max_row + 1) if ws.cell(k, 1).value == "가산세")
    assert [ws.cell(k, j).value for j in range(2, 6)] == [c("withholding_late_payment_penalty", x["args"])["결과"]["가산세"] for x in MIXED]
    assert [ws.cell(k + 1, j).value for j in range(2, 6)] == ["일치"] * 4 and error_cells(wb, wb.sheetnames) == []


def test_from_call_on_a_date_input_gives_a_readable_warning(tmp_path):
    r = export(tmp_path, BASE, sources=[{"call": "P", "arg": "due", "from_call": "A", "from_row": "합계"}])
    assert "error" not in r
    w = [x for x in r["warnings"] if "from_call" in x]
    assert w == ["sources: call 3의 입력 'due'는 숫자가 아니라(날짜·글) from_call로 연결하지 않음(값은 입력 그대로)"]
