"""엑셀 정의 이름 규칙 — 정답 테스트. 작성 Claude 2026-10-26 (docs/SPEC_excel_defined_names.md)."""
import re, zipfile
import pytest
from test_export_workbook_c import c, ENT, ADJ
from test_export_workbook_f import DEMO

VALID = re.compile(r"^[가-힣A-Za-z_][가-힣A-Za-z0-9_.]*$")
CELL_A1 = re.compile(r"^[A-Za-z]{1,3}[0-9]+$")
CELL_R1C1 = re.compile(r"^[RrCc]$|^[Rr][0-9]*[Cc][0-9]*$")


def _calls():
    return ([{"label": "기업업무추진비", "tool": "entertainment_adjustment", "args": ENT}]
            + [{"label": t, "tool": t, "args": a} for t, a in DEMO.items()]
            + [{"label": "차가감", "tool": "income_adjustment_total", "args": ADJ}])


def _build(tmp_path, layout):
    r = c("export_workbook", {"layout": layout, "title": f"이름 {layout}", "calls": _calls(),
                              "output_dir": str(tmp_path), "company": "㈜가상", "period": "2025.01.01 ~ 2025.12.31"})
    return r["결과"]["파일"]


def _names(path):
    with zipfile.ZipFile(path) as z:
        wbxml = z.read("xl/workbook.xml").decode("utf-8")
        sheets = {n: z.read(n).decode("utf-8") for n in z.namelist() if n.startswith("xl/worksheets/sheet")}
    names = re.findall(r'<definedName\b([^>]*)>([^<]*)</definedName>', wbxml)
    out = []
    for attrs, ref in names:
        nm = re.search(r'name="([^"]+)"', attrs).group(1)
        scope = re.search(r'localSheetId="(\d+)"', attrs)
        out.append((nm, scope.group(1) if scope else None, ref))
    formulas = [f for xml in sheets.values() for f in re.findall(r"<f>([^<]*)</f>", xml)]
    return out, formulas


@pytest.mark.parametrize("layout", ["forms", "steps"])
def test_defined_names_are_excel_valid(tmp_path, layout):
    names, _ = _names(_build(tmp_path, layout))
    user = [(n, s) for n, s, _ in names if not n.startswith("_xlnm.")]
    assert user, "정의 이름이 하나도 없음"
    bad = [n for n, _ in user if not VALID.match(n) or CELL_A1.match(n) or CELL_R1C1.match(n) or len(n) > 255]
    assert not bad, bad[:10]


@pytest.mark.parametrize("layout", ["forms", "steps"])
def test_defined_names_unique_case_insensitive(tmp_path, layout):
    names, _ = _names(_build(tmp_path, layout))
    seen = {}
    for n, s, _ in names:
        key = (n.lower(), s)
        assert key not in seen, f"겹치는 이름: {n}"
        seen[key] = 1


@pytest.mark.parametrize("layout", ["forms", "steps"])
def test_formula_names_all_defined(tmp_path, layout):
    names, formulas = _names(_build(tmp_path, layout))
    defined = {n.lower() for n, _, _ in names}
    used = set()
    for f in formulas:
        f2 = re.sub(r'"[^"]*"', "", f)          # 문자열 상수 제외
        f2 = re.sub(r"'[^']*'!\$?[A-Z]+\$?\d+", "", f2)  # 시트 참조 제외
        for tok in re.findall(r"호출\d+_[가-힣A-Za-z0-9_.]+", f2):
            used.add(tok)
    assert used, "수식이 정의 이름을 하나도 안 씀"
    missing = sorted(t for t in used if t.lower() not in defined)
    assert not missing, missing[:10]


def test_checks_still_match_tool_values(tmp_path):
    """이름만 바뀌고 도구 값은 그대로: steps 레이아웃 계산 시트의 도구 값 열이 결과와 같은 개수로 채워진다."""
    import openpyxl
    wb = openpyxl.load_workbook(_build(tmp_path, "steps"))
    calc = [ws for ws in wb.worksheets if ws.title.startswith("계산 ")]
    assert len(calc) == len(_calls())
    for ws in calc:
        checks = [x.value for row in ws.iter_rows() for x in row if isinstance(x.value, str) and x.value.startswith("=IF(B")]
        assert checks, ws.title
