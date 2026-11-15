"""영문 모드 엑셀(verify_workbook·export_workbook lang='en')의 결과 키·근거 표기 — 0.56.1. 작성 Claude 2026-11-15.

- 결과 키: 용어집에 있으면 'Tax base (과세표준)', 없으면 국문 그대로 + 번역_없음. labels로 준 글이 먼저.
- 근거: 법령명·조문 번호는 규칙으로 영문 인용('Corporate Tax Act (법인세법) Art. 98(1)2'), 구절은 용어집에 통째로 있는 것만.
- 국문 모드 출력과 숫자·수식·대조 결과는 그대로.
- 사례 값은 모두 지어낸 값(특정 사례와 무관).
"""
import re

import openpyxl
import pytest

from korean_tax_calc_mcp import workbook_i18n as i18n
from tests._helpers import call as c
from tests.test_verify_workbook_1115 import CHECKS, DIV, FILED, NW, PEN, PEN_ARGS, _book

HANGUL = re.compile(r"[가-힣]")
GLOSS = re.compile(r"\([^()]*\)")


def _outside_gloss(s: str) -> str:
    """'English (국문)' 병기 괄호를 걷어 낸 글."""
    while True:
        t = GLOSS.sub(lambda m: "" if HANGUL.search(m.group(0)) else "<" + m.group(0)[1:-1] + ">", s)
        if t == s:
            return t
        s = t


def _rows(ws, first=5):
    """대조 표의 줄 — 0.57.0 틀: 머리 행 4행, 칸 / 항목 / 통합 문서 값 / 도구 값 / (차이) / 판정 / 근거 번호 · 결과 키."""
    out = []
    for r in range(first, ws.max_row + 1):
        if ws.cell(r, 1).value is None:
            break
        out.append([ws.cell(r, j).value for j in range(1, 8)])
    return out


def _notes(ws):
    """표 아래 근거 줄 — {번호: 글}."""
    out = {}
    for r in range(1, ws.max_row + 1):
        m = re.match(r"\[(\d+)\] (.*)$", str(ws.cell(r, 1).value or ""), re.S)
        if m:
            out[int(m.group(1))] = m.group(2)
    return out


@pytest.fixture(scope="module")
def pair(tmp_path_factory):
    d = tmp_path_factory.mktemp("cite")
    path = _book(d / "직접.xlsx")
    ko = c("verify_workbook", {"path": path, "checks": CHECKS, "filename": "ko"})
    en = c("verify_workbook", {"path": path, "checks": CHECKS, "filename": "en", "lang": "en"})
    assert "error" not in ko and "error" not in en, (ko, en)
    return d, path, ko, en


def test_verify_en_result_keys_use_the_glossary(pair):
    _, _, _, en = pair
    rows = _rows(openpyxl.load_workbook(en["결과"]["사본"])["Tool check"])
    keys = [r[5] for r in rows]
    assert keys[0] == "[1] Withholding tax amount (원천징수세액)"
    assert keys[1] == "[1] Local income tax (지방소득세)"
    assert keys[3].endswith("] Penalty tax (가산세)") and keys[3] != keys[0][:3] + " Penalty tax (가산세)"      # 다른 도구 — 다른 근거 번호
    assert all(not HANGUL.search(_outside_gloss(k)) for k in keys)


def test_verify_en_basis_is_an_english_citation(pair):
    _, _, ko, en = pair
    ws = openpyxl.load_workbook(en["결과"]["사본"])["Tool check"]
    rows, notes = _rows(ws), _notes(ws)
    raw = ko["결과"]["대조"][0]["근거"]
    assert raw.startswith("법인세법 제98조")                                  # 도구가 돌려준 글(국문)
    first = notes[int(rows[0][5][1:rows[0][5].index("]")])]
    assert first.startswith(f"{NW} (") and "— Corporate Tax Act (법인세법) Art. 98(1)" in first
    assert "제98조" not in first and "①" not in first
    pen = notes[int(rows[3][5][1:rows[3][5].index("]")])]
    assert "— Framework Act on National Taxes (국세기본법) Art. 47-5(1)" in pen and "Enforcement Decree Art. 27-4" in pen
    assert all(not re.search(r"제\d+조|[①-⑳]|\d호", t) for t in notes.values())        # 조문 번호가 국문 꼴로 남지 않음
    # 결과 JSON의 대조 줄은 도구가 돌려준 글 그대로(기계가 읽는 값)
    assert en["결과"]["대조"][0]["근거"] == raw and en["결과"]["대조"][0]["키"] == "원천징수세액"


def test_verify_en_reports_untranslated_and_ko_is_unchanged(pair):
    _, _, ko, en = pair
    assert en["결과"]["lang"] == "en" and isinstance(en["결과"]["번역_없음"], list)
    ws_en = openpyxl.load_workbook(en["결과"]["사본"])["Tool check"]
    sheet_text = " ".join([str(r[5]) for r in _rows(ws_en)] + list(_notes(ws_en).values()))
    for miss in en["결과"]["번역_없음"]:
        assert miss in sheet_text                                              # 국문 그대로 시트에 남은 것만 올린다
    if en["결과"]["번역_없음"]:
        assert "labels" in en["결과"]["번역_없음_안내"]
    # 국문 모드: 결과 키도 시트도 그대로
    assert not {"lang", "번역_없음", "번역_없음_안내", "labels_적용"} & set(ko["결과"])
    ws_ko = openpyxl.load_workbook(ko["결과"]["사본"])["검산"]
    rows = _rows(ws_ko)
    assert rows[0][5] == "[1] 원천징수세액" and _notes(ws_ko)[1].endswith("— " + ko["결과"]["대조"][0]["근거"])
    # 대조 결과·숫자는 언어와 무관
    assert en["결과"]["요약"] == ko["결과"]["요약"]
    strip = lambda rs: [{k: v for k, v in r.items()} for r in rs]
    assert strip(en["결과"]["대조"]) == strip(ko["결과"]["대조"])


def test_verify_values_and_formulas_same_in_both_languages(pair):
    _, _, ko, en = pair
    a, b = openpyxl.load_workbook(ko["결과"]["사본"]), openpyxl.load_workbook(en["결과"]["사본"])
    av, bv = openpyxl.load_workbook(ko["결과"]["사본"], data_only=True), openpyxl.load_workbook(en["결과"]["사본"], data_only=True)
    for name in ("입력", "배당", "요약"):
        for row in a[name].iter_rows():
            for cell in row:
                assert b[name][cell.coordinate].value == cell.value                       # 수식·글
                assert bv[name][cell.coordinate].value == av[name][cell.coordinate].value  # 저장된 값
    num = lambda ws: [[v for v in r[2:4]] for r in _rows(ws)]
    assert num(a["검산"]) == num(b["Tool check"])


def test_verify_labels_apply_to_keys_and_phrases(tmp_path):
    path = _book(tmp_path / "직접.xlsx")
    gross = {**DIV, "net_of_tax": True}
    checks = [{"cell": "배당!B6", "tool": NW, "args": gross, "key": "역산.역산에_쓴_세율"}]
    first = c("verify_workbook", {"path": path, "checks": checks, "lang": "en", "filename": "a"})
    assert "역산" in first["결과"]["번역_없음"] and "역산에_쓴_세율" in first["결과"]["번역_없음"]
    again = c("verify_workbook", {"path": path, "checks": checks, "lang": "en", "filename": "b",
                                  "labels": {"역산": "Gross-up", "역산에_쓴_세율": "Gross-up rate", "없는_키": "Nothing"}})
    row = _rows(openpyxl.load_workbook(again["결과"]["사본"])["Tool check"])[0]
    assert row[6] == "[1] Gross-up (역산).Gross-up rate (역산에_쓴_세율)"      # 세율 칸이 아니라 불일치 — 차이 열이 있어 한 칸 뒤
    assert again["결과"]["labels_적용"] == ["역산", "역산에_쓴_세율"]
    assert "역산" not in again["결과"]["번역_없음"]
    assert any("없는_키" in w for w in again["warnings"])
    # 국문 모드에서도 labels는 표에 있는 글을 그대로 적는다
    ko = c("verify_workbook", {"path": path, "checks": checks, "filename": "c", "labels": '{"역산에_쓴_세율": "역산 세율"}'})
    assert _rows(openpyxl.load_workbook(ko["결과"]["사본"])["검산"])[0][6] == "[1] 역산.역산 세율"
    bad = c("verify_workbook", {"path": path, "checks": checks, "labels": {"역산": "=1+1"}})
    assert "error" in bad and "labels" in bad["error"]


# ── export_workbook(lang='en') ─────────────────────────────────────────────
CALLS = [{"label": "As filed", "tool": NW, "args": FILED}, {"label": "Required", "tool": NW, "args": DIV},
         {"label": "Penalty", "tool": PEN, "args": PEN_ARGS}]


def test_export_en_calc_sheet_basis_is_converted_and_ko_is_not(tmp_path):
    en = c("export_workbook", {"title": "cite_en", "calls": CALLS, "output_dir": str(tmp_path), "lang": "en"})
    ko = c("export_workbook", {"title": "cite_ko", "calls": CALLS, "output_dir": str(tmp_path)})
    assert "error" not in en and "error" not in ko, (en, ko)
    ws = openpyxl.load_workbook(en["결과"]["파일"])["Calc 1 (계산 1)"]
    basis = next(ws.cell(r, 3).value for r in range(1, ws.max_row + 1) if ws.cell(r, 1).value == "Basis (근거)")
    assert basis.startswith("Corporate Tax Act (법인세법) Art. 98(1)") and "제98조" not in basis
    local = next(ws.cell(r, 3).value for r in range(1, ws.max_row + 1) if ws.cell(r, 1).value == "지방소득세_근거")
    assert "Local Tax Act (지방세법) Art. 103-52(1)" in local
    jud = openpyxl.load_workbook(en["결과"]["파일"])["Judgements (판단·근거)"]
    assert jud.cell(1, 5).value == "Basis (근거)"
    cited = [jud.cell(r, 5).value for r in range(2, jud.max_row + 1) if isinstance(jud.cell(r, 5).value, str)]
    assert cited and all(not re.search(r"제\d+조", v) for v in cited)
    assert any("Art. " in v for v in cited)
    # 결론·이유는 국문 그대로(문장을 번역하지 않음)
    assert any(HANGUL.search(str(jud.cell(r, 3).value or "")) for r in range(2, jud.max_row + 1))
    # 국문 모드는 도구가 돌려준 글 그대로
    wk = openpyxl.load_workbook(ko["결과"]["파일"])["계산 1"]
    raw = next(wk.cell(r, 2).value for r in range(1, wk.max_row + 1) if wk.cell(r, 1).value == "근거")
    assert raw.startswith("법인세법 제98조") and "Corporate Tax Act" not in raw
    assert "번역_없음" not in ko["결과"]


def test_export_en_blend_notes_and_sources_are_converted(tmp_path):
    scen = [{"sheet": "Dividend", "heading": "As filed vs required", "columns": [{"call": 1, "heading": "As filed"}, {"call": 2, "heading": "Required"}],
             "notes": {"원천징수세액": "Preparer's note"}},
            {"sheet": "Dividend", "heading": "Penalty", "columns": [{"call": 3, "heading": "Required"}]}]
    src = [{"call": 1, "arg": "amount", "source": "Board minutes (caller's text 제1조)"}]
    args = {"title": "blend", "calls": CALLS, "output_dir": str(tmp_path), "scenarios": scen, "sources": src}
    en = c("export_workbook", {**args, "lang": "en", "filename": "en"})
    ko = c("export_workbook", {**args, "filename": "ko"})
    assert "error" not in en and "error" not in ko, (en, ko)
    wb = openpyxl.load_workbook(en["결과"]["파일"])
    texts = lambda ws: [cell.value for row in ws.iter_rows() for cell in row if isinstance(cell.value, str) and cell.data_type != "f"]
    notes = texts(wb["Dividend"])
    assert any(t.startswith("Basis returned by the tool: Corporate Tax Act (법인세법) Art. 98(1)") for t in notes)
    assert any("Local income tax on the tax withheld: Corporate Tax Act (법인세법) Art. 98-7(1)1" in t for t in notes)
    assert any(t.startswith("Preparer's note") for t in notes)                           # 호출자가 준 메모는 그대로
    inputs = texts(wb["Inputs"])
    assert "Statutory rate: Corporate Tax Act (법인세법) Art. 98(1)2" in inputs
    assert "Framework Act on National Taxes (국세기본법) Art. 47-5(1)1" in inputs
    assert "Board minutes (caller's text 제1조)" in inputs                               # 호출자가 준 출처는 건드리지 않음
    for t in notes + inputs:
        assert not re.search(r"\(법인세법 제\d+조|\(국세기본법 제\d+조", t), t                 # 근거가 괄호 속 국문 문장으로 남지 않음
    detail = texts(wb["Calc detail"])
    assert any(t.startswith("Corporate Tax Act (법인세법) Art. 98(1)") for t in detail)
    assert isinstance(en["결과"]["번역_없음"], list)
    assert len(en["warnings"]) >= 1 and en["warnings"][0].startswith(i18n.UNTRANSLATED_TITLE)
    # 국문 통합 문서는 그대로 — 근거는 도구가 돌려준 국문
    kb = openpyxl.load_workbook(ko["결과"]["파일"])
    assert any(t.startswith("법인세법 제98조") for t in texts(kb["Dividend"]))
    assert not any("Corporate Tax Act" in t for ws in kb.worksheets for t in texts(ws))
    # 숫자(저장된 값)는 언어와 무관
    ev, kv = openpyxl.load_workbook(en["결과"]["파일"], data_only=True), openpyxl.load_workbook(ko["결과"]["파일"], data_only=True)
    nums = lambda w, n: [cell.value for row in w[n].iter_rows() for cell in row if isinstance(cell.value, (int, float)) and not isinstance(cell.value, bool)]
    assert nums(ev, "Dividend") == nums(kv, "Dividend") and len(nums(ev, "Dividend")) > 10


def test_export_en_labels_cover_basis_phrases(tmp_path):
    """labels에 근거 구절을 넣으면 용어집보다 먼저 그 글을 쓴다(쓰인 키는 labels_적용에)."""
    calls = [{"label": "Net of tax", "tool": NW, "args": {**DIV, "net_of_tax": True}}]
    first = c("export_workbook", {"title": "p1", "calls": calls, "output_dir": str(tmp_path), "lang": "en"})
    ws = openpyxl.load_workbook(first["결과"]["파일"])["Calc 1 (계산 1)"]
    basis = next(ws.cell(r, 3).value for r in range(1, ws.max_row + 1) if ws.cell(r, 1).value == "Basis (근거)")
    assert "gross-up under a net-of-tax clause" in basis and "순액 약정 역산" not in basis      # 용어집의 근거 구절
    again = c("export_workbook", {"title": "p2", "calls": calls, "output_dir": str(tmp_path), "lang": "en", "labels": {"순액 약정 역산": "CALLER PHRASE"}})
    assert "순액 약정 역산" in again["결과"]["labels_적용"]
    ws = openpyxl.load_workbook(again["결과"]["파일"])["Calc 1 (계산 1)"]
    basis = next(ws.cell(r, 3).value for r in range(1, ws.max_row + 1) if ws.cell(r, 1).value == "Basis (근거)")
    assert "CALLER PHRASE" in basis and "gross-up under a net-of-tax clause" not in basis
