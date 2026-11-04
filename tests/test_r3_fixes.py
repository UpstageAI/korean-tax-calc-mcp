"""원 단위 반올림·'계산 N' 확인 칸·라벨 문자열·별지50(을) 기초잔액·부가 신고서 (4)·(8)란·별지19 회수분·
의제매입세액 한도액·특수관계 조문 인용·세무조정 근거·도구 설명·비상장주식 결과 형식·제척기간 원천징수 표기 회귀 테스트.

tests/data/r3_*_calls.json은 실제 사용 기록의 call 목록(label만 중립 문구로 바꿈)이다. 서식·계산 시트는 openpyxl로 다시 읽어
칸(수식 문자열)을 보고, LibreOffice(soffice)가 있으면 다시 계산해 값과 '확인' 칸도 본다.
"""
import asyncio
import copy
import json
import pathlib
import shutil
import subprocess

import openpyxl
import pytest

from korean_tax_calc_mcp import server as S
from korean_tax_calc_mcp.engine import calc as engine_calc
from korean_tax_calc_mcp.audit.agents import calc as agent_calc

DATA = pathlib.Path(__file__).parent / "data"
CORP = json.loads((DATA / "r3_corp_adjust_calls.json").read_text(encoding="utf-8"))
INCOME_VAT = json.loads((DATA / "r3_income_vat_calls.json").read_text(encoding="utf-8"))
VAT_RETURN = json.loads((DATA / "r3_vat_return_calls.json").read_text(encoding="utf-8"))
STOCK_GIFT = json.loads((DATA / "r3_stock_gift_calls.json").read_text(encoding="utf-8"))

# 회수분 call에 회수 구분 입력을 준 목록(기록에는 그 입력이 없던 도구로 부름)
INCOME_VAT_RECOVERED = copy.deepcopy(INCOME_VAT)
INCOME_VAT_RECOVERED[5]["args"]["recovered"] = True

soffice = pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice 없음")


def call(tool, args):
    r = asyncio.run(S.mcp.call_tool(tool, args))
    return json.loads((r.content[0] if hasattr(r, "content") else r[0][0]).text)


def build(d, calls, name):
    r = S.export_workbook(title=name, calls=calls, output_dir=str(d))
    assert "error" not in r, r
    return r["결과"]["파일"], r["결과"]["오류_call"]


def recalc(path, d):
    out = pathlib.Path(d) / "re"
    subprocess.run(["soffice", "--headless", "--calc", "--convert-to", "xlsx", "--outdir", str(out), path],
                   check=True, capture_output=True, timeout=240)
    return openpyxl.load_workbook(next(out.glob("*.xlsx")), data_only=True)


SETS = {"corp": CORP, "income_vat": INCOME_VAT_RECOVERED, "vat_return": VAT_RETURN, "stock_gift": STOCK_GIFT}


@pytest.fixture(scope="module")
def books(tmp_path_factory):
    out = {}
    for k, calls in SETS.items():
        d = tmp_path_factory.mktemp(k)
        p, errs = build(d, calls, k)
        out[k] = (p, openpyxl.load_workbook(p), d, errs)
    return out


@pytest.fixture(scope="module")
def recalced(books):
    if not shutil.which("soffice"):
        pytest.skip("LibreOffice 없음")
    return {k: recalc(p, d) for k, (p, _, d, _) in books.items()}


def test_no_error_calls(books):
    assert {k: v[3] for k, v in books.items()} == {k: [] for k in books}


def row_of(ws, text, col=1):
    for r in range(1, ws.max_row + 1):
        if ws.cell(r, col).value == text:
            return r
    return None


# ── 원 미만 반올림(0.5는 올림) ──────────────────────────────────────────
@pytest.mark.parametrize("fn", [engine_calc.won, agent_calc.won])
def test_won_rounds_half_up(fn):
    assert [fn(x) for x in (0.5, 1.5, 2.5, 50_000_000.5, 181_078_830.5, 2.4999, -2.5)] == \
        [1, 2, 3, 50_000_001, 181_078_831, 2, -3]


def test_donation_limit_half_won_rounds_up():
    a = S.donation_limit(year=2025, base_income=100_000_001, carried_loss=0, special=0, general=0, sme=True)
    assert a["결과"]["특례한도"] == 50_000_001
    b = S.donation_limit(year=2025, base_income=392_157_661, carried_loss=30_000_000, special=20_000_000, general=0, sme=True)
    assert b["결과"]["특례한도"] == 181_078_831


# ── '계산 N' 확인 칸: 같은 정의의 합계와 비교 ─────────────────────────────
def _check_cells(ws):
    return [(r, ws.cell(r, 1).value, ws.cell(r, 3).value) for r in range(1, ws.max_row + 1)
            if isinstance(ws.cell(r, 1).value, str) and ws.cell(r, 1).value.startswith("확인 (")]


@pytest.mark.parametrize("sheet", ["계산 3", "계산 4", "계산 7", "계산 10"])
def test_calc_sheet_checks_compare_like_with_like(books, sheet):
    ws = books["corp"][1][sheet]
    add_row = row_of(ws, "가산 합계")
    sub_row = row_of(ws, "차감 합계")
    checks = _check_cells(ws)
    assert checks, sheet
    for r, label, f in checks:
        if "손금산입_익금불산입" in label:
            assert f"C{sub_row}" in f, (sheet, label, f)
        else:   # 손금불산입_합계·한도초과·익금산입_손금불산입 — 가산 쪽 합계
            assert f"C{add_row}" in f, (sheet, label, f)


def test_income_adjustment_donation_excess_outside_add_total(books):
    """기부금 한도초과(차가감소득금액 뒤 가산)는 '가산' 합계에 넣지 않는다 — 익금산입_손금불산입과 같은 정의."""
    ws = books["corp"][1]["계산 10"]
    r = row_of(ws, "기부금 한도초과")
    assert r is not None and ws.cell(r, 2).value != "가산"


@soffice
def test_calc_sheet_checks_read_match_after_recalc(recalced):
    for k, wb in recalced.items():
        for ws in wb.worksheets:
            if not ws.title.startswith("계산 "):
                continue
            bad = [(ws.title, c.coordinate) for row in ws.iter_rows() for c in row if c.value == "확인 필요"]
            assert not bad, (k, bad)


# ── '='로 시작하는 결과 문구는 문자열 칸 ─────────────────────────────────
def _tool_strings(obj, out):
    if isinstance(obj, str):
        if obj.startswith("="):
            out.add(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            _tool_strings(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _tool_strings(v, out)
    return out


def test_label_strings_are_not_formulas(books):
    labels = set()
    for calls in SETS.values():
        for c in calls:
            _tool_strings(call(c["tool"], c["args"]), labels)
    assert "= 순손익액" in labels
    for k, (_, wb, _, _) in books.items():
        for ws in wb.worksheets:
            for row in ws.iter_rows():
                for c in row:
                    if isinstance(c.value, str) and c.value.startswith("="):
                        if c.value in labels or c.value.startswith("= "):
                            assert c.data_type == "s", (k, ws.title, c.coordinate, c.value)


def test_no_label_formula_in_stock_calc_sheet(books):
    ws = books["stock_gift"][1]["계산 1"]
    texts = [c for row in ws.iter_rows() for c in row if c.value in ("= 순손익액", "= 순자산가액(자산 − 부채)")]
    assert len(texts) == 4 and all(c.data_type == "s" for c in texts)


@soffice
def test_no_error_values_after_recalc(recalced):
    errs = ("#NAME?", "#N/A", "#VALUE!", "#REF!", "#DIV/0!")
    for k, wb in recalced.items():
        bad = [(ws.title, c.coordinate) for ws in wb.worksheets for row in ws.iter_rows() for c in row if c.value in errs]
        assert not bad, (k, bad)


# ── 별지50(을): 전기 유보를 기초잔액으로, 없으면 빈칸 ─────────────────────
S50 = "별지50(을) 자본금과적립금"


def _rows50(ws):
    rows = {}
    for r in range(8, 28):
        a = ws.cell(r, 1).value
        if a:
            rows[a] = r
    return rows


def test_form50_opening_balances_from_calls(books):
    ws = books["corp"][1][S50]
    rows = _rows50(ws)
    want = {"대손충당금": 6_000_000, "대손금": 20_000_000, "퇴직급여충당금": 70_000_000, "퇴직연금충당금": -300_000_000}
    for name, v in want.items():
        r = next((rr for a, rr in rows.items() if a.startswith(name)), None)
        assert r is not None, (name, list(rows))
        assert ws.cell(r, 2).value == v, (name, ws.cell(r, 2).value)


def test_form50_missing_opening_left_blank_with_note(books):
    ws = books["corp"][1][S50]
    rows = _rows50(ws)
    r = next(rr for a, rr in rows.items() if "미지급기부금" in a)
    assert ws.cell(r, 2).value in (None, "")          # ②기초잔액 빈칸(0 아님)
    assert ws.cell(r, 5).value in (None, "")          # ⑤기말도 빈칸 — 기초 없이 감소만 빼서 음수가 되지 않게
    assert "기초" in str(ws.cell(r, 6).value or "")   # 비고에 안내


@soffice
def test_form50_closing_balances_after_recalc(recalced):
    ws = recalced["corp"][S50]
    vals = {ws.cell(r, 1).value: ws.cell(r, 5).value for r in range(8, 28) if ws.cell(r, 1).value}
    got = {k.split("(")[0].split(" ")[0]: v for k, v in vals.items()}
    assert got["대손충당금"] == 12_332_000
    assert got["대손금"] == 4_000_000
    assert got["퇴직급여충당금"] == 94_000_000
    assert got["퇴직연금충당금"] == -394_000_000
    # 기초를 모르는 줄 말고는 음수 기말 없음(퇴직연금충당금은 △유보 잔액)
    for k, v in vals.items():
        if isinstance(v, (int, float)) and v < 0:
            assert k.startswith("퇴직연금충당금"), (k, v)


# ── 부가 신고서 (4)란: 같은 파일의 간주공급 과세표준 전부 ─────────────────
S4 = "부가 신고서 간주공급(4)"


def test_vat_line4_includes_exempt_use(books):
    ws = books["vat_return"][1][S4]
    f = ws["E10"].value
    assert "호출4_" in f and "호출5_" in f, f


@soffice
def test_vat_line4_total_after_recalc(recalced):
    ws = recalced["vat_return"][S4]
    assert ws["E10"].value == 4_980_000
    assert [c.value for row in ws.iter_rows() for c in row if c.value in ("일치", "확인 필요")] == ["일치"]


# ── 대손세액: 회수(가산)는 공제와 구분 ─────────────────────────────────
def test_bad_debt_recovered_is_addition():
    r = S.vat_bad_debt_credit(bad_debt_incl_vat=5_500_000, recovered=True)
    assert r["결과"]["대손세액"] == 500_000 and r["결과"]["회수"] is True
    assert "가산" in r["결과"]["구분"] and "단서" in r["근거"]
    d = S.vat_bad_debt_credit(bad_debt_incl_vat=22_000_000)
    assert d["결과"]["회수"] is False and "공제" in d["결과"]["구분"]


def test_form19_has_only_deduction_and_line8_has_both(books):
    wb = books["income_vat"][1]
    s19 = [n for n in wb.sheetnames if n.startswith("부가 별지19")]
    assert s19 == ["부가 별지19 대손세액공제신고서"], s19       # 회수 call은 공제 신고서에 넣지 않음
    assert "호출5_" in wb[s19[0]]["C12"].value
    s8 = [n for n in wb.sheetnames if "대손세액가감(8)" in n]
    assert len(s8) == 1, wb.sheetnames
    f = wb[s8[0]]["G7"].value
    assert "호출5_" in f and "호출6_" in f, f


@soffice
def test_line8_signed_total_after_recalc(recalced):
    ws = next(recalced["income_vat"][n] for n in recalced["income_vat"].sheetnames if "대손세액가감(8)" in n)
    assert ws["G7"].value == -2_000_000 + 500_000
    assert [c.value for row in ws.iter_rows() for c in row if c.value in ("일치", "확인 필요")] == ["일치"]


def test_export_doc_describes_numbered_sheets():
    doc = S.export_workbook.__doc__ if S.export_workbook.__doc__ else ""
    assert "(2)" in doc and "(호출 N)" in doc


# ── 의제매입세액: 한도액 표시, 쓰지 않은 단계는 빼기 ──────────────────────
def test_deemed_input_shows_limit_amount():
    r = S.vat_deemed_input_credit(period="2025-2", industry="음식점", purchase=168_000_000, base=250_000_000, individual=True)
    res = r["결과"]
    assert res["한도액"] == 150_000_000
    assert res["의제매입세액"] == 11_111_111
    steps = res["단계별_계산"]
    names = [s["항목"] for s in steps]
    assert not any(n.startswith(("총 구입액", "채취 운반비", "과세 공급가액", "면세 공급가액", "운반비 제외")) for n in names), names
    assert any("한도액" in n and s.get("금액") == 150_000_000 for n, s in zip(names, steps))
    assert all(s.get("금액") != 0 for s in steps if "금액" in s), steps


# ── 특수관계 판정 적용조문: 개정 연혁 없이 문장 단위 인용 ─────────────────
def test_related_cite_quotes_clean_sentence(monkeypatch):
    from korean_tax_calc_mcp.audit.agents import related, law as law_api
    text = ("제2조(정의) ① 생략\n⑧ 법 제2조제12호에서 \"경제적 연관관계 또는 경영지배관계 등 대통령령으로 정하는 관계에 있는 자\"란 "
            "다음 각 호의 어느 하나에 해당하는 관계에 있는 자를 말한다. <신설 2019. 2. 12., 2023. 2. 28., 2024. 2. 29.>\n"
            "1. 임원의 임면권의 행사 ...")
    monkeypatch.setattr(law_api, "article", lambda name, jo, as_of="": text if jo == "제2조" else "")
    related._CITE_CACHE.clear()
    try:
        name, jo, quote = related.cite_at("법인", "2025-09-30")
    finally:
        related._CITE_CACHE.clear()
    assert jo == "제2조⑧"
    assert "<" not in quote and "신설" not in quote
    assert quote.rstrip().endswith("말한다.")


def test_related_cite_quote_long_sentence_marks_cut(monkeypatch):
    from korean_tax_calc_mcp.audit.agents import related, law as law_api
    head = "제1조의2(특수관계인의 범위) ① " + "가" * 400 + " <개정 2023. 2. 28.>"
    monkeypatch.setattr(law_api, "article", lambda name, jo, as_of="": head)
    related._CITE_CACHE.clear()
    try:
        _, _, quote = related.cite_at("국기", "2025-09-30")
    finally:
        related._CITE_CACHE.clear()
    assert quote.endswith("…") and "<" not in quote


# ── 세무조정 합계: 근거 자리표시 대신 실제 조문 또는 안내 ─────────────────
def test_income_adjustment_basis_no_placeholder():
    r = S.income_adjustment_total(**CORP[9]["args"])
    by = {j["항목"]: j["근거"] for j in r["판단"]}
    assert not any("앞 도구의 근거" in g for g in by.values()), by
    assert "제28조" in by["채권자불분명 사채이자(원천세)"]
    assert "제25조" in by["기업업무추진비 적격증빙 미수취"]
    assert "제36조" in by["미지급기부금(당기 어음)"]


def test_income_adjustment_item_basis_passthrough():
    r = S.income_adjustment_total(net_income=0, items=[{"항목": "무언가", "종류": "한도초과", "금액": 1_000, "소득처분": "기타사외유출",
                                                       "근거": "법인세법 제99조"}])
    assert r["판단"][0]["근거"] == "법인세법 제99조"
    r2 = S.income_adjustment_total(net_income=0, items=[{"항목": "무언가", "종류": "한도초과", "금액": 1_000, "소득처분": "기타사외유출"}])
    assert "근거 미지정" in r2["판단"][0]["근거"]


# ── 도구 설명·결과 문구가 실제 동작과 맞음 ──────────────────────────────
def test_financial_income_excluded_total_names_actual_items():
    r = call("financial_income_aggregate", INCOME_VAT[0]["args"])
    d = next(x["설명"] for x in r["계산식_입력"] if x["이름"] == "제외합계")
    assert "비실명이자" in d and "법원보증금이자" not in d and "직장공제회" not in d


def test_personal_deduction_example_uses_allowed_relation():
    tools = asyncio.run(S.mcp.list_tools())
    t = next(x for x in tools if x.name == "personal_deduction")
    text = json.dumps(t.model_dump(), ensure_ascii=False)
    assert "직계존속" in text
    assert '\\"relation\\":\\"부친\\"' not in text and '"relation":"부친"' not in text


# ── 비상장주식 평가: null 키 없음, 원 단위 정수 ───────────────────────────
def test_unlisted_stock_result_ints_no_nulls():
    r = S.unlisted_stock_valuation(**STOCK_GIFT[0]["args"])
    res = r["결과"]
    assert None not in res.values(), res
    for k in ("1주당_평가액", "1주당_할증전", "순손익가치", "순자산가치", "가중평균"):
        assert isinstance(res[k], int), (k, res[k])
    assert res["1주당_평가액"] == 48_000
    for blk in r["계산"]["순손익액 산출"]:
        for line in blk["산출"]:
            assert isinstance(line["금액"], int), line


# ── 제척기간: 원천징수분은 법정납부기한·그 근거 ───────────────────────────
def test_assessment_limitation_withholding_labels():
    r = S.assessment_limitation(due_date="2025-07-10", offshore=True, withholding=True)
    res = r["결과"]
    assert "법정납부기한(적용)" in res and "법정신고기한(적용)" not in res
    assert "제12조의3②1호" in r["근거"]
    assert "제5조" not in r["근거"]                       # 기한이 미뤄지지 않았으면 기한 특례 근거 없음
    assert "제4조" in r["근거"]                           # 만료일이 토요일 → 다음 월요일
    plain = S.assessment_limitation(due_date="2024-03-31")
    assert "법정신고기한(적용)" in plain["결과"] and "제5조제1항" in plain["근거"]


def test_donation_limit_and_excess_add_up_to_spending():
    """한도는 원 단위로 확정한 뒤 한도초과를 계산 — 한도 + 한도초과 = 지출(이월 포함)."""
    from korean_tax_calc_mcp import server as s
    r = s.donation_limit(year=2025, base_income=392157935, carried_loss=30000000, special=20000000,
                         general=39000000, general_carry=6000000, sme=True)
    res = r.get("결과", r)
    assert res["일반한도"] == 34215794 and res["한도초과(기타사외유출)"] == 10784206
    assert res["일반한도"] + res["한도초과(기타사외유출)"] == 39000000 + 6000000
