"""별지15 소득처분 코드·부가 신고서 (4)란 같은 자산 중복·원천 별지23 세율 단위·배당소득명세서 행별 Gross-up·
기업업무추진비 한도 이름·결과 키 설명·상증 보충적 평가액·퇴직소득 연도 표기·경정청구 기한 설명·대손 전기말 채권 금액·
특수관계인 조문 원문 인용 회귀 테스트.

tests/data/r5_*_calls.json은 실제 사용 기록의 call 목록(label만 중립 문구로 바꿈)이다. 서식 시트는 openpyxl로 다시 읽어
칸을 보고, LibreOffice(soffice)가 있으면 다시 계산해 값을 본다.
tests/data/related_cite_articles.json은 법제처 국가법령정보 DRF에서 받은 시행령 조문 본문(키: 법령|조|기준일)이다.
"""
import asyncio
import json
import pathlib
import re
import shutil
import subprocess

import openpyxl
import pytest

from korean_tax_calc_mcp import server as S
from tests._helpers import call

DATA = pathlib.Path(__file__).parent / "data"
CORP = json.loads((DATA / "r5_corp_adjust_calls.json").read_text(encoding="utf-8"))
VAT_RETURN = json.loads((DATA / "r5_vat_return_calls.json").read_text(encoding="utf-8"))
NONRESIDENT = json.loads((DATA / "r5_nonresident_calls.json").read_text(encoding="utf-8"))
INCOME_VAT = json.loads((DATA / "r5_income_vat_calls.json").read_text(encoding="utf-8"))
CITE = json.loads((DATA / "related_cite_articles.json").read_text(encoding="utf-8"))

soffice = pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice 없음")


def tool_def(name):
    return next(t for t in asyncio.run(S.mcp.list_tools()) if t.name == name)


def build(d, calls, name):
    r = S.export_workbook(title=name, calls=calls, output_dir=str(d))
    assert "error" not in r, r
    return r["결과"]["파일"], r["결과"]["오류_call"]


def recalc(path, d):
    out = pathlib.Path(d) / "re"
    subprocess.run(["soffice", "--headless", "--calc", "--convert-to", "xlsx", "--outdir", str(out), path],
                   check=True, capture_output=True, timeout=240)
    return openpyxl.load_workbook(next(out.glob("*.xlsx")), data_only=True)


SETS = {"corp": CORP, "vat_return": VAT_RETURN, "nonresident": NONRESIDENT, "income_vat": INCOME_VAT}


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


# ── 별지15 소득처분 코드(법인세법 시행규칙 별지 제15호서식 작성방법) ──────────────
# 익금산입·손금불산입: 상여 100·배당 200·기타소득 300·유보 400·기타사외유출 500·기타 600
# 손금산입·익금불산입: 유보(△유보) 100·기타 200
ADD_CODE = {"상여": "100", "배당": "200", "기타소득": "300", "유보": "400", "기타사외유출": "500", "기타": "600"}
SUB_CODE = {"유보": "100", "△유보": "100", "기타": "200"}


def _form15_rows(ws):
    add, sub = [], []
    for r in range(8, ws.max_row + 1):
        if ws.cell(r, 1).value in (None, "합 계") and ws.cell(r, 5).value in (None, "합 계"):
            continue
        if ws.cell(r, 3).value:
            add.append((ws.cell(r, 1).value, ws.cell(r, 3).value, str(ws.cell(r, 4).value)))
        if ws.cell(r, 7).value:
            sub.append((ws.cell(r, 5).value, ws.cell(r, 7).value, str(ws.cell(r, 8).value)))
    return add, sub


def test_form15_disposal_codes_follow_form(books):
    ws = books["corp"][1]["별지15 소득금액조정합계표"]
    add, sub = _form15_rows(ws)
    assert any(p == "상여" for _, p, _ in add), add
    assert [(n, p, c) for n, p, c in add if ADD_CODE[p] != c] == []
    assert [(n, p, c) for n, p, c in sub if SUB_CODE[p] != c] == []
    by = {n: c for n, _, c in add}
    assert by["가지급금 인정이자"] == "100"
    assert by["채권자불분명 사채이자(원천징수세액 제외분)"] == "100"
    assert by["채권자불분명 사채이자(원천징수세액)"] == "500"


def test_form15_codes_for_dividend_other_income_and_other(tmp_path):
    calls = [{"tool": "income_adjustment_total", "label": "소득금액 집계", "args": {
        "net_income": 100_000_000,
        "items": [
            {"항목": "주주 가지급금 인정이자", "조정": "익금산입", "금액": 1_000_000, "소득처분": "배당"},
            {"항목": "외부인 귀속 사외유출", "조정": "손금불산입", "금액": 2_000_000, "소득처분": "기타소득"},
            {"항목": "자기주식처분이익", "조정": "익금산입", "금액": 3_000_000, "소득처분": "기타"},
            {"항목": "임원 상여 한도초과", "조정": "손금불산입", "금액": 4_000_000, "소득처분": "상여"},
            {"항목": "국세환급가산금", "조정": "익금불산입", "금액": 500_000, "소득처분": "기타"},
            {"항목": "전기 감가상각 부인액 추인", "조정": "손금산입", "금액": 600_000, "소득처분": "△유보"},
        ]}}]
    p, errs = build(tmp_path, calls, "codes")
    assert errs == []
    add, sub = _form15_rows(openpyxl.load_workbook(p)["별지15 소득금액조정합계표"])
    assert {n: c for n, _, c in add} == {"주주 가지급금 인정이자": "200", "외부인 귀속 사외유출": "300",
                                          "자기주식처분이익": "600", "임원 상여 한도초과": "100"}
    assert {n: c for n, _, c in sub} == {"국세환급가산금": "200", "전기 감가상각 부인액 추인": "100"}


# ── 부가 신고서 (4)란: 면세전용 call과 간주공급 항목별 call에 같은 자산이면 한 번만 ──────
def test_deemed_supply_line4_counts_same_asset_once(books):
    ws = books["vat_return"][1]["부가 신고서 간주공급(4)"]
    r = next(r for r in range(1, ws.max_row + 1) if ws.cell(r, 4).value == "(4)")
    f = str(ws.cell(r, 5).value)
    assert "호출4_간주공급_과세표준" in f and "호출3_간주공급_과세표준" not in f, f
    assert ws.cell(r, 9).value == 4_980_000          # 도구 값(확인 칸 비교 대상)
    text = " ".join(str(c.value) for row in ws.iter_rows() for c in row if isinstance(c.value, str))
    assert "호출 3" in text and "중복" in text, text


@soffice
def test_deemed_supply_line4_value_after_recalc(recalced):
    ws = recalced["vat_return"]["부가 신고서 간주공급(4)"]
    r = next(r for r in range(1, ws.max_row + 1) if ws.cell(r, 4).value == "(4)")
    assert ws.cell(r, 5).value == 4_980_000
    assert ws.cell(r, 7).value == 498_000
    assert ws.cell(r, 10).value == "일치"


def test_deemed_supply_line4_different_assets_still_add(tmp_path):
    """다른 자산이면 두 call을 그대로 더한다(면세전용 자산의 취득가액이 다름)."""
    calls = json.loads(json.dumps(VAT_RETURN[2:4]))
    calls[0]["args"]["assets"][0]["취득가액"] = 6_000_000
    p, errs = build(tmp_path, calls, "two_assets")
    assert errs == []
    ws = openpyxl.load_workbook(p)["부가 신고서 간주공급(4)"]
    r = next(r for r in range(1, ws.max_row + 1) if ws.cell(r, 4).value == "(4)")
    f = str(ws.cell(r, 5).value)
    assert "호출1_간주공급_과세표준" in f and "호출2_간주공급_과세표준" in f, f


# ── 원천 별지23: 같은 통합문서 안 세율 칸은 같은 단위(%) ──────────────────────────
def _rate_cells(wb):
    out = []
    for ws in wb.worksheets:
        if ws.title.startswith("원천 별지23(1)"):
            out.append((ws.title, ws["O17"].value, ws["N17"].value, (ws["P17"].value or 0) + (ws["Q17"].value or 0)))
        elif ws.title.startswith("원천 별지23(5)"):
            out.append((ws.title, ws["I14"].value, ws["F14"].value, (ws["J14"].value or 0) + (ws["K14"].value or 0)))
    return out


@soffice
def test_withholding_rate_cells_same_unit_percent(recalced):
    cells = _rate_cells(recalced["nonresident"])
    assert len(cells) == 5, cells
    for title, rate, paid, tax in cells:
        assert isinstance(rate, (int, float)) and 1 < rate < 100, (title, rate)
        assert abs(paid * rate / 100 - tax) < 10, (title, rate, paid, tax)    # 세액은 원 단위 10원 미만 절사


def test_withholding_23_5_rate_formula_is_percent(books):
    wb = books["nonresident"][1]
    for ws in wb.worksheets:
        if ws.title.startswith("원천 별지23(5)"):
            f = str(ws["I14"].value).replace(" ", "")
            assert f.endswith("*100"), (ws.title, f)


# ── 종합소득세 배당소득명세서: Gross-up 대상 행마다 ⑥대상금액·⑦가산액 ───────────────
@soffice
def test_dividend_statement_rows_have_grossup(recalced):
    ws = recalced["income_vat"]["종소 배당·이자소득명세서"]
    rows = {ws.cell(r, 3).value: r for r in range(8, 18) if ws.cell(r, 3).value}
    r1, r2 = rows["비상장법인현금배당"], rows["상장법인현금배당"]
    assert (ws.cell(r1, 6).value, ws.cell(r1, 7).value, ws.cell(r1, 8).value) == (12_000_000, 1_200_000, 13_200_000)
    assert (ws.cell(r2, 6).value, ws.cell(r2, 7).value, ws.cell(r2, 8).value) == (6_000_000, 600_000, 6_600_000)
    for name in ("투자신탁환매이익", "외국법인배당"):
        r = rows[name]
        assert ws.cell(r, 6).value in (None, 0) and ws.cell(r, 7).value in (None, 0), name
        assert ws.cell(r, 8).value == ws.cell(r, 5).value
    assert (ws["F18"].value, ws["G18"].value, ws["H18"].value) == (18_000_000, 1_800_000, 26_800_000)
    assert ws["L18"].value == "일치" and ws["N18"].value == "일치"


def test_dividend_statement_rows_written(books):
    ws = books["income_vat"][1]["종소 배당·이자소득명세서"]
    rows = {ws.cell(r, 3).value: r for r in range(8, 18) if ws.cell(r, 3).value}
    for name in ("비상장법인현금배당", "상장법인현금배당"):
        assert ws.cell(rows[name], 6).value not in (None, "", 0), name
        assert ws.cell(rows[name], 7).value not in (None, ""), name


# ── 기업업무추진비: 기본한도·수입금액한도·일반한도를 각각의 이름으로 ────────────────
def test_entertainment_limit_names():
    r = call("entertainment_adjustment", CORP[0]["args"])
    c = r["계산"]
    assert c["기본한도"] == 36_000_000           # 법인세법 제25조④1호 중소기업 3,600만 원 × 12/12
    assert c["수입금액한도"] == 31_400_000       # 제25조④2호(일반 100억 이하 0.3% + 초과 0.2%, 특수관계 10%)
    assert c["일반한도"] == 67_400_000
    assert c["문화한도"] == 6_000_000 and c["전통시장한도"] == 4_000_000


def test_entertainment_form_general_limit_still_checked(books):
    ws = books["corp"][1]["별지23(갑) 기업업무추진비"]
    r = next(r for r in range(1, ws.max_row + 1) if str(ws.cell(r, 2).value or "").startswith("⑧"))
    assert ws.cell(r, 6).value == 67_400_000


# ── 결과 키 설명·이름 ─────────────────────────────────────────────────────
def test_bad_debt_reversal_key_explained():
    r = call("bad_debt_adjustment", CORP[4]["args"])
    assert r["결과"]["과소환입_과다환입"] == -6_000_000
    desc = r["키_설명"]["과소환입_과다환입"]
    assert "환입할 금액" in desc and "과다환입" in desc, desc


def test_capital_gains_period_keys_explained():
    args = {"asset_type": "주택", "acquisition_date": "2012-03-15", "transfer_date": "2025-09-30",
            "transfer_price": 2_000_000_000, "acquisition_price": 700_000_000, "acquisition_tax": 23_000_000,
            "capital_expenditure": 30_000_000, "transfer_expenses": 10_000_000, "registered": True, "one_house": True,
            "exempt_met": True, "residence_start": "2017-02-01", "residence_end": "2025-09-30", "apply_basic_deduction": True}
    r = call("capital_gains_income", args)
    if "error" in r:
        pytest.fail(r)
    keys = [k for k in r["계산"] if re.search(r"_(이상|미만)$", k)]
    assert keys, r["계산"]
    for k in keys:
        assert r["키_설명"].get(k), (k, r.get("키_설명"))


def test_inheritance_valuation_supplementary_matches_input():
    args = {"kind": "증여", "valuation_date": "2025-11-20", "supplementary_value": 800_000_000,
            "lease": {"월임대료": 6_000_000, "임대보증금": 300_000_000},
            "secured_debt": [{"채권최고액": 1_200_000_000, "채무액": 400_000_000}]}
    r = call("inheritance_gift_valuation", args)
    assert r["결과"]["평가액"] == 900_000_000
    assert r["계산"]["보충적_평가액"] == 800_000_000          # 입력 supplementary_value와 같은 이름 → 같은 값
    assert r["계산"]["임대료_환산가액"] == 900_000_000         # 72,000,000 ÷ 12% + 300,000,000
    assert r["계산"]["제61조_평가액"] == 900_000_000           # 상증법 제61조제5항: 둘 중 큰 금액


# ── 퇴직소득세 연도 표기: 인자 설명·스키마·도구 설명이 같은 범위 ─────────────────────
def test_retirement_year_range_consistent():
    t = tool_def("retirement_income_tax")
    p = t.input_schema["properties"]["retire_year"]
    assert (p.get("minimum"), p.get("maximum")) == (2016, 2026)
    for text in (p.get("description", ""), t.description):
        assert "2020~2026" in text and "2016~2019" in text, text
    assert "error" in call("retirement_income_tax", {"income": 50_000_000, "years_of_service": 10, "retire_year": 2019})
    assert "error" not in call("retirement_income_tax", {"income": 50_000_000, "years_of_service": 10, "retire_year": 2020})


# ── 경정청구 기한: 도구 설명과 결과 근거의 민법 조문이 같음 ───────────────────────
def test_refund_claim_description_matches_result_basis():
    t = tool_def("refund_claim_deadline")
    r = call("refund_claim_deadline", {"kind": "통상", "tax": "법인세", "year": 2023})
    assert r["결과"]["경정청구_기한"].startswith("2029-04-02")
    basis = json.dumps(r["근거"], ensure_ascii=False)

    def civil(s):
        return {tuple(re.findall(r"제(\d+)조", m)) for m in re.findall(r"민법 (제\d+조(?:·제\d+조)*)", s)}
    assert civil(t.description) == civil(basis) == {("157", "159", "160")}, (civil(t.description), civil(basis))


# ── 도구 설명: 영어 단어 없이(도구·인자 이름과 PDF·Gross-up 같은 용어는 허용) ───────────
def test_when_sentences_have_no_stray_english():
    tools = asyncio.run(S.mcp.list_tools())
    names = {t.name for t in tools} | {a for t in tools for a in t.input_schema.get("properties", {})}
    allowed = names | {"PDF", "Gross", "up", "True", "False", "data", "tax", "price"}
    bad = []
    for t in tools:
        m = re.search(r"언제:([^\n]*)", t.description or "")
        if not m:
            continue
        stray = [w for w in re.findall(r"[A-Za-z][A-Za-z_]+", m.group(1)) if w not in allowed]
        if stray:
            bad.append((t.name, stray))
    assert not bad, bad
    assert "prices" not in tool_def("unfair_transaction").description


# ── 대손충당금: '세법상 전기말 채권' 판단 금액 = 결론 값 ─────────────────────────
def test_bad_debt_prior_receivable_judgment_amount():
    args = {"year": 2025, "sme": False,
            "writeoffs": [
                {"amount": 100_000_000, "arose_in": "전기", "booked": "손비", "date": "2023-05-31",
                 "instrument": "외상매출금", "kind": "소멸시효완성"},
                {"amount": 500_000_000, "arose_in": "당기", "booked": "손비", "date": "2025-11-30", "kind": "파산",
                 "instrument": "기타", "excluded_reason": "특수관계인업무무관가지급금", "lent_on": "2021-03-02",
                 "recipient": "법인", "related_at_event": True, "related_at_lending": False}],
            "book": {"closing": 0, "offset": 0, "opening": 0, "provision": 0},
            "receivables_end_book": 0, "receivables_prev_end_book": 0}
    r = call("bad_debt_adjustment", args)
    j = next(x for x in r["판단"] if x["항목"] == "세법상 전기말 채권")
    assert j["금액"] == r["계산"]["세법상 전기말 채권"] == 0, (j, r["계산"])


# ── 특수관계인 적용조문: 세 세법 모두 기준일 시행본 원문 인용 ─────────────────────
@pytest.fixture
def cite_text(monkeypatch):
    from korean_tax_calc_mcp.audit.agents import related, law as law_api

    def fake(name, jo, as_of=""):
        return CITE.get(f"{name}|{jo}|{as_of}", "조문 없음 — 조번호 확인")
    monkeypatch.setattr(law_api, "article", fake)
    related._CITE_CACHE.clear()
    yield related
    related._CITE_CACHE.clear()


@pytest.mark.parametrize("law, on, jo, phrase", [
    ("국기", "2025-11-20", "제1조의2①", "법 제2조제20호가목에서"),
    ("국기", "2013-01-01", "제1조의2①", "법 제2조제20호가목에서"),
    ("상증", "2025-11-20", "제2조의2①", "법 제2조제10호에서"),
    ("상증", "2015-01-01", "제12조의2①", "대통령령으로 정하는 특수관계인"),
    ("법인", "2025-11-20", "제2조⑧", "법 제2조제12호에서"),
])
def test_related_cite_quotes_article_text(cite_text, law, on, jo, phrase):
    name, got_jo, quote = cite_text.cite_at(law, on)
    assert got_jo == jo, (got_jo, quote)
    assert "조문 이동 기록" not in quote and "law_article로" not in quote, quote
    assert quote.startswith(f"{name} {jo}(기준일 {on} 시행본) — "), quote
    body = quote.split(" — ", 1)[1]
    assert body[0] in "①②③④⑤⑥⑦⑧⑨⑩", quote                     # 조 제목 없이 항 원문부터
    assert phrase in body and "<" not in body and "특수관계인의 범위)" not in body, quote


def test_related_cite_falls_back_when_article_moved(cite_text):
    """그 시점 제1조의2가 다른 조문이면(2010년) 원문 대신 위치 안내."""
    _, jo, quote = cite_text.cite_at("국기", "2010-01-01")
    assert jo == "제1조의2①" and "law_article" in quote


def test_related_judge_three_laws_same_format(cite_text):
    r = S.related_judge(a="갑", b="을", on="2025-11-20", people={"갑": {"구분": "개인"}, "을": {"구분": "개인"}},
                        family=[["갑", "을", "부모자녀"]], stakes=[])
    quotes = (r.get("결과") or r)["적용조문"]
    for law in ("국기", "법인", "상증"):
        q = quotes[law] if isinstance(quotes[law], str) else json.dumps(quotes[law], ensure_ascii=False)
        assert "시행본) — " in q and "조문 이동 기록" not in q, (law, q)


def _line4(tmp_path, calls, name):
    p, errs = build(tmp_path, calls, name)
    assert errs == []
    ws = openpyxl.load_workbook(p)["부가 신고서 간주공급(4)"]
    r = next(r for r in range(1, ws.max_row + 1) if ws.cell(r, 4).value == "(4)")
    text = " ".join(str(c.value) for row in ws.iter_rows() for c in row if isinstance(c.value, str))
    return str(ws.cell(r, 5).value), ws.cell(r, 9).value, text


def test_deemed_supply_line4_match_found_in_later_items_call(tmp_path):
    """면세전용 항목이 없는 간주공급 항목별 call이 앞에 있어도, 뒤 call의 같은 자산을 찾아 한 번만 더한다."""
    first = {"label": "개인적공급만", "tool": "vat_deemed_supply_items",
             "args": {"period": "2025-2", "items": [{"항목": "텀블러 고객 증정", "거래": "사업상증여", "매입세액공제": True, "시가": 2_000_000}]}}
    calls = [first] + json.loads(json.dumps(VAT_RETURN[2:4]))
    f, tool_value, text = _line4(tmp_path, calls, "later")
    assert "호출1_간주공급_과세표준" in f and "호출3_간주공급_과세표준" in f and "호출2_간주공급_과세표준" not in f, f
    assert "호출 2" in text and "중복" in text, text


def test_deemed_supply_line4_partial_match_keeps_sum_and_warns(tmp_path):
    """면세전용 call 자산 둘 중 하나만 항목별 call에 있으면 그대로 더하고 확인을 요청한다."""
    calls = json.loads(json.dumps(VAT_RETURN[2:4]))
    calls[0]["args"]["assets"].append({"구분": "기타", "취득일": "2024-06-01", "취득가액": 3_000_000, "매입세액공제": True, "시가": 2_000_000})
    f, _, text = _line4(tmp_path, calls, "partial")
    assert "호출1_간주공급_과세표준" in f and "호출2_간주공급_과세표준" in f, f
    assert re.search(r"호출 1[^\n]{0,80}(일부|같은 자산)", text), text

