"""export_workbook이 저장한 통합 문서의 수식 칸 캐시 값(`<v>`). 작성 Claude 2026-11-15.

- 휴대폰 뷰어·메신저 미리보기·macOS 훑어보기는 수식을 다시 계산하지 않는다 — 수식 칸에 계산 값이 없으면 0·빈칸으로 보인다.
- LibreOffice 없이 도는 테스트: 모든 수식 칸에 값이 있음, 대표 값이 도구 결과와 같음, 수식·fullCalcOnLoad가 남아 있음, zip·XML이 유효함,
  계산하지 않는 수식(모르는 함수·순환 참조)은 값을 쓰지 않고 warnings로 알림.
- LibreOffice가 있으면: 캐시 값을 지운 사본을 LibreOffice로 다시 계산해 칸 단위로 전수 비교(없으면 건너뜀).
  LibreOffice는 캐시 값이 있으면 그 값을 믿고 다시 계산하지 않으므로, 비교할 때는 캐시 값을 지운 사본을 쓴다.
- 사례 값은 모두 지어낸 값.
"""
import datetime
import pathlib
import re
import shutil
import subprocess
import zipfile
from xml.etree import ElementTree as ET

import openpyxl
import pytest
from openpyxl.utils.datetime import to_excel
from openpyxl.workbook.defined_name import DefinedName

from korean_tax_calc_mcp import workbook_cache as wc
from tests._helpers import call as c
from tests.test_export_workbook_blend import CALLS, ISSUES, SCENARIOS, SOURCES

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
BLEND = {"scenarios": SCENARIOS, "sources": SOURCES, "issues": ISSUES}
CASES = {
    "compact_ko": {**BLEND},
    "compact_en": {**BLEND, "lang": "en"},
    "forms_ko": {**BLEND, "detail": "forms"},
    "forms_en": {**BLEND, "detail": "forms", "lang": "en"},
    "full_ko": {**BLEND, "detail": "full"},
    "full_en": {**BLEND, "detail": "full", "lang": "en"},
    "plain_forms": {},
    "plain_forms_en": {"lang": "en"},
    "plain_steps": {"layout": "steps"},
}


def _export(tmp_path, name, **kw):
    r = c("export_workbook", {"title": name, "calls": CALLS, "output_dir": str(tmp_path), **kw})
    assert "error" not in r, r
    return r


@pytest.fixture(scope="module")
def books(tmp_path_factory):
    d = tmp_path_factory.mktemp("cached")
    return {name: _export(d, name, **kw) for name, kw in CASES.items()}


def _formula_cells(path):
    """[(시트 XML 경로, 칸 주소, t 속성, <v> 글 또는 None)] — 수식 칸 전부."""
    out = []
    with zipfile.ZipFile(path) as z:
        for n in z.namelist():
            if not n.startswith("xl/worksheets/sheet"):
                continue
            for cell in ET.fromstring(z.read(n)).iter(NS + "c"):
                if cell.find(NS + "f") is not None:
                    v = cell.find(NS + "v")
                    out.append((n, cell.get("r"), cell.get("t"), None if v is None else (v.text or "")))
    return out


def _strip_cached(src, dst):
    """수식 칸의 캐시 값을 지운 사본(LibreOffice가 처음부터 다시 계산하게)."""
    pat = re.compile(rb'<c r="([A-Z]+[0-9]+)"((?: [A-Za-z:]+="[^"]*")*)>(<f(?: [^>]*)?(?:/>|>[^<]*</f>))<v>[^<]*</v></c>')

    def repl(m):
        return b'<c r="' + m.group(1) + b'"' + re.sub(rb' t="[^"]*"', b"", m.group(2)) + b">" + m.group(3) + b"<v></v></c>"

    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename.startswith("xl/worksheets/sheet"):
                data = pat.sub(repl, data)
            zout.writestr(info, data)


def _same(cached, cell):
    """캐시 값(openpyxl data_only로 읽은 칸)과 LibreOffice가 다시 계산한 칸이 같은가.
    LibreOffice는 xlsx에 숫자를 유효숫자 15자리로 적고, 논리값을 1·0으로 적기도 한다."""
    a, b = cached.value, cell.value
    for x in (a, b):
        if isinstance(x, datetime.time) or isinstance(x, datetime.timedelta):
            return a == b
    if isinstance(a, (datetime.datetime, datetime.date)):
        a = to_excel(a)
    if isinstance(b, (datetime.datetime, datetime.date)):
        b = to_excel(b)
    if cached.data_type == "e" or cell.data_type == "e":
        return cached.data_type == cell.data_type and a == b
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b and not isinstance(a, str) and not isinstance(b, str)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b or abs(a - b) <= 1e-14 * max(abs(a), abs(b))
    return (a or "") == (b or "")


def compare_with_libreoffice(path, workdir):
    """(수식 칸 수, 불일치 목록) — 캐시 값 지운 사본을 LibreOffice로 다시 계산해 캐시 값과 칸 단위로 비교."""
    workdir = pathlib.Path(workdir)
    src = workdir / "src"
    out = workdir / "out"
    for d in (src, out):
        d.mkdir(parents=True, exist_ok=True)
    bare = src / "bare.xlsx"
    _strip_cached(path, bare)
    subprocess.run(["soffice", f"-env:UserInstallation=file://{workdir / 'lo_profile'}", "--headless", "--calc", "--convert-to", "xlsx",
                    "--outdir", str(out), str(bare)], check=True, capture_output=True, timeout=300)
    formulas = openpyxl.load_workbook(path)
    cached = openpyxl.load_workbook(path, data_only=True)
    recalculated = openpyxl.load_workbook(out / "bare.xlsx", data_only=True)
    n, bad = 0, []
    for ws in formulas.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if cell.data_type != "f":
                    continue
                n += 1
                a, b = cached[ws.title][cell.coordinate], recalculated[ws.title][cell.coordinate]
                if not _same(a, b):
                    bad.append((ws.title, cell.coordinate, cell.value, a.value, b.value))
    return n, bad


# ── LibreOffice 없이 ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("name", list(CASES))
def test_every_formula_cell_has_a_cached_value(books, name):
    r = books[name]
    cells = _formula_cells(r["결과"]["파일"])
    assert len(cells) > 20
    missing = [(n, ref) for n, ref, t, v in cells if v is None or (v == "" and t != "str")]
    assert missing == []
    assert not [w for w in r.get("warnings") or [] if "미리보기" in w or "previews" in w]


@pytest.mark.parametrize("name", list(CASES))
def test_formulas_stay_live_and_excel_recalculates_on_open(books, name):
    path = books[name]["결과"]["파일"]
    wb = openpyxl.load_workbook(path)
    formulas = [cell.value for ws in wb.worksheets for row in ws.iter_rows() for cell in row if cell.data_type == "f"]
    assert formulas and all(f.startswith("=") for f in formulas)
    assert len(formulas) == len(_formula_cells(path))
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        for n in z.namelist():
            if n.endswith(".xml") or n.endswith(".rels"):
                ET.fromstring(z.read(n))
        calc = ET.fromstring(z.read("xl/workbook.xml")).find(NS + "calcPr")
    assert calc is not None and calc.get("fullCalcOnLoad") == "1"


def test_cached_values_equal_tool_results(books):
    """시나리오 시트·요약 링크의 캐시 값이 계산 도구 값과 같다(재계산 없이 값만 읽음)."""
    wb = openpyxl.load_workbook(books["compact_ko"]["결과"]["파일"], data_only=True)
    tool = [c(x["tool"], x["args"]) for x in CALLS[:2]]
    ws = wb["배당"]
    row = next(r for r in range(1, ws.max_row + 1) if str(ws.cell(r, 1).value).startswith("원천징수세액"))
    assert [ws.cell(row, 2).value, ws.cell(row, 3).value] == [t["결과"]["원천징수세액"] for t in tool]
    assert ws.cell(row, 2).value > 0
    checks = [cell.value for w in wb.worksheets for r in w.iter_rows() for cell in r if cell.value in ("일치", "확인 필요")]
    assert checks and set(checks) == {"일치"}
    summary = wb.worksheets[0]
    numbers = [cell.value for r in summary.iter_rows() for cell in r if isinstance(cell.value, (int, float)) and not isinstance(cell.value, bool)]
    assert tool[0]["결과"]["원천징수세액"] in numbers and tool[0]["결과"]["합계"] in numbers and tool[1]["결과"]["합계"] in numbers      # 첫 열은 결과 줄, 다른 열은 합계 줄


def test_english_summary_links_show_numbers_without_recalculation(books):
    """영문 통합 문서 첫 시트(Summary)의 링크 칸 — 값만 읽어도 0이 아닌 숫자."""
    path = books["compact_en"]["결과"]["파일"]
    formulas = openpyxl.load_workbook(path).worksheets[0]
    values = openpyxl.load_workbook(path, data_only=True).worksheets[0]
    assert formulas.title == "Summary"
    links = [(cell.coordinate, values[cell.coordinate].value) for r in formulas.iter_rows() for cell in r if cell.data_type == "f"]
    assert len(links) >= 10
    assert all(v is not None for _, v in links)
    assert sum(1 for _, v in links if isinstance(v, (int, float)) and v > 0) >= 10


def _wb(cells, names=None):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "가 나"
    for ref, v in cells.items():
        ws[ref] = v
    for k, v in (names or {}).items():
        wb.defined_names[k] = DefinedName(k, attr_text=v)
    return wb


def _eval(formula, cells=None, names=None):
    wb = _wb({**(cells or {}), "Z1": formula}, names)
    values, skipped = wc.evaluate_workbook(wb)
    assert not [s for s in skipped if s[1] == "Z1"], skipped
    return values["가 나"]["Z1"]


@pytest.mark.parametrize("formula, expected", [
    ("=1+2*3-4/2", 5.0), ("=(1+2)*3", 9.0), ("=-2^2", 4.0), ("=10%+1", 1.1), ("=0.1+0.2-0.3", 0.0), ("=0.1+0.2=0.3", True),
    ("=ROUND(2.675,2)", 2.68), ("=ROUND(1.005,2)", 1.01), ("=ROUND(-2.5,0)", -3.0), ("=ROUND(1234.5678,-2)", 1200.0),
    ("=ROUNDDOWN(0.29*100,0)", 29.0), ("=INT(0.29*100)", 29.0), ("=INT(-3.5)", -4.0), ("=ROUNDUP(1.1*3,1)", 3.3), ("=ROUNDDOWN(-19.99,0)", -19.0),
    ("=ROUNDDOWN(ROUND(73456789*0.1/1.1,4),-1)", 6677880.0), ("=ABS(-3.5)", 3.5), ("=MIN(3,1,2)", 1.0), ("=MAX(0,MIN(5,7)-9)", 0.0),
    ('=IF(1>2,"a","b")', "b"), ("=IF(FALSE,1)", False), ("=IF(TRUE,,5)", 0.0), ("=AND(1=1,2>1)", True), ("=OR(1=2,2<1)", False),
    ('="a"="A"', True), ('="가"&1&"나"', "가1나"), ("=1/0", wc.XlError("#DIV/0!")), ("=1/0+1", wc.XlError("#DIV/0!")), ('="abc"+1', wc.XlError("#VALUE!")),
    ("=IFERROR(1/0,7)", 7.0), ("=A1", 0.0), ('=A1=""', True), ("=A1=0", True), ("=ISNUMBER(A1)", False), ("=N(A1)+N(B1)", 12.0),
    ('=IF(ISNUMBER(B1),B1,0)', 12.0), ("=SUM(B1:B4)", 42.5), ("=COUNT(B1:C4)", 3.0), ('=IF(COUNT(C1:C4)=0,"",SUM(C1:C4))', ""),
    ('=SUMIF(C1:C4,"가산",B1:B4)', 12.0), ('=SUMIF(D1:D4,"가산",B1:B4)', 32.0), ('=SUMIFS(B1:B4,D1:D4,"가산",B1:B4,">15")', 20.0),
    ("=SUMIF(B1:B4,\">11\")", 32.0), ("=rate*100", 15.0), ("=ROUND(RATE*B1,2)", 1.8), ("='가 나'!B1+'가 나'!$B$2", 32.0),
    ('=DATE(2026,12,31)-DATE(2026,1,1)+1', 365.0), ('=DATEDIF(DATE(2024,1,31)+1,DATE(2026,1,31),"m")', 23.0), ('=MIN(60,DATEDIF(E1,E2,"m"))', 60.0),
    ('=DATE(VALUE(LEFT(F1,4)),VALUE(MID(F1,6,2)),VALUE(RIGHT(F1,2)))-E1', 4017.0), ("=E2-E1", 4017.0), ('=LEFT("가나다")', "가"),
    ("=ISLOGICAL(1=1)", True), ('=ISLOGICAL("x")', False), ("=nosuch_name", wc.XlError("#NAME?")),
])
def test_evaluator_values(formula, expected):
    cells = {"B1": 12, "B2": 20, "B3": 10.5, "B4": "글", "C1": "가산", "C2": "차감", "D1": "가산", "D2": "가산", "D3": "차감",
             "E1": datetime.date(2020, 1, 1), "E2": datetime.date(2030, 12, 31), "F1": "2030-12-31"}
    got = _eval(formula, {**cells, "G1": 0.15}, {"rate": "'가 나'!$G$1"})
    assert got == expected and type(got) is type(expected)


def test_unknown_function_and_cycle_are_left_without_a_value(tmp_path):
    wb = _wb({"A1": 5, "A2": "=A1*2", "A3": "=NOSUCHFUNC(A1)", "A4": "=A3+1", "A5": '=IF(A1>0,"ok",A3)',
              "B1": "=B2+1", "B2": "=B1+1", "B3": "=B1*2", "B4": "=SUM(A1:A2)", "C1": '=TRUE&""', "C2": "=SUM(0.1,0.2,-0.3)"})
    path = tmp_path / "x.xlsx"
    wb.save(path)
    info = wc.fill_cached_values(wb, str(path))
    skipped = {ref: why for _, ref, why in info["못_쓴_칸"]}
    assert set(skipped) == {"A3", "A4", "B1", "B2", "B3", "C1", "C2"}
    assert "NOSUCHFUNC" in skipped["A3"] and "순환" in skipped["B1"]
    assert info["수식_칸"] == 10 and info["값_쓴_칸"] == 3
    got = {ref: (t, v) for _, ref, t, v in _formula_cells(path)}
    assert got["A2"] == (None, "10") and got["A5"] == ("str", "ok") and got["B4"] == (None, "15")
    assert all(got[ref][1] in (None, "") for ref in skipped)
    assert "미리보기에서 값이 안 보일 수 있는 칸 7개" in wc.uncached_warning(info)
    assert "7 formula cell(s)" in wc.uncached_warning(info, "en")
    assert wc.uncached_warning({"수식_칸": 3, "값_쓴_칸": 3, "못_쓴_칸": []}) is None
    reopened = openpyxl.load_workbook(path, data_only=True).active
    assert [reopened[k].value for k in ("A2", "A3", "A5", "B4")] == [10, None, "ok", 15]
    assert openpyxl.load_workbook(path).active["A3"].value == "=NOSUCHFUNC(A1)"


def test_cached_value_types_in_xml(tmp_path):
    wb = _wb({"A1": 3, "A2": "=A1/3", "A3": "=A1>1", "A4": '="<&>"&A1', "A5": "=1/0", "A6": '=""', "A7": "=A1/7", "A8": "=A99"})
    path = tmp_path / "t.xlsx"
    wb.save(path)
    wc.fill_cached_values(wb, str(path))
    got = {ref: (t, v) for _, ref, t, v in _formula_cells(path)}
    assert got == {"A2": (None, "1"), "A3": ("b", "1"), "A4": ("str", "<&>3"), "A5": ("e", "#DIV/0!"), "A6": ("str", ""),
                   "A7": (None, repr(3 / 7)), "A8": (None, "0")}
    ws = openpyxl.load_workbook(path, data_only=True).active
    assert ws["A3"].value is True and ws["A4"].value == "<&>3" and ws["A5"].value == "#DIV/0!" and ws["A7"].value == 3 / 7


def test_empty_string_cell_counts_as_blank_like_the_saved_file(tmp_path):
    """값이 ""인 칸은 파일에 빈 칸으로 저장된다 — 더하면 0, 비교하면 빈 칸."""
    wb = _wb({"A1": "", "A2": 7, "A3": "=A1+A2", "A4": "=SUM(A1:A2)", "A5": '=IF(A1="","빈칸","값")', "A6": "=ISBLANK(A1)"})
    values, skipped = wc.evaluate_workbook(wb)
    assert skipped == [] and values["가 나"] == {"A3": 7.0, "A4": 7.0, "A5": "빈칸", "A6": True}


def test_long_reference_chain_does_not_hit_recursion_limit(tmp_path):
    cells = {"A1": 1, **{f"A{r}": f"=A{r - 1}+1" for r in range(2, 3001)}, "B3000": 1, **{f"B{r}": f"=B{r + 1}+1" for r in range(1, 3000)}}
    values, skipped = wc.evaluate_workbook(_wb(cells))
    assert skipped == [] and values["가 나"]["A3000"] == 3000.0 and values["가 나"]["B1"] == 3000.0


def test_functions_cover_everything_the_exporter_writes(books):
    """내보내는 수식에 쓰인 함수가 모두 계산 대상 목록에 있다."""
    used = set()
    for r in books.values():
        wb = openpyxl.load_workbook(r["결과"]["파일"])
        for ws in wb.worksheets:
            for row in ws.iter_rows():
                for cell in row:
                    if cell.data_type == "f":
                        used |= set(re.findall(r"([A-Z][A-Z0-9.]*)\(", re.sub(r'"[^"]*"', "", cell.value)))
    assert used and used <= set(wc.FUNCTIONS)


# ── LibreOffice로 전수 비교 ───────────────────────────────────────────────────
@pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice 없음")
@pytest.mark.parametrize("name", list(CASES))
def test_cached_values_match_libreoffice_recalculation(books, name, tmp_path):
    n, bad = compare_with_libreoffice(books[name]["결과"]["파일"], tmp_path)
    assert n > 20
    assert bad == []


@pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice 없음")
def test_evaluator_matches_libreoffice_on_rounding_and_text_cases(tmp_path):
    """끝수·날짜·조건 합계·글 함수의 경계 값 — 계산한 칸은 LibreOffice와 같고, 갈릴 수 있는 칸은 값을 쓰지 않는다."""
    import random
    rnd = random.Random(20261115)
    cells = {}
    row = 0

    def add(f):
        nonlocal row
        row += 1
        cells[f"A{row}"] = f

    for i in range(1, 31):
        cells[f"C{i}"] = rnd.choice([rnd.randint(-500, 5000), round(rnd.uniform(-10, 10), 2), None])
        cells[f"D{i}"] = rnd.choice(["가산", "차감", "abc", "Abc", None])
        cells[f"E{i}"] = rnd.randint(1, 5)
    rates = [0.1, 0.11, 0.22, 0.15, 0.055, 0.0275, 0.2, 0.033, 0.154, 1.1, 0.00022, 0.03]
    for _ in range(400):
        a = rnd.choice([rnd.randint(1, 10 ** rnd.randint(2, 11)), round(rnd.uniform(0, 1e6), rnd.randint(0, 3))])
        expr = rnd.choice(["{a}*{r}", "{a}*{r}/{d}", "{a}/{d}", "-{a}*{r}", "{a}/(1-{r})*{r}"]).format(a=a, r=rnd.choice(rates), d=rnd.choice([1.1, 3, 7, 12, 365, 366, 100]))
        add(f"={rnd.choice(['ROUND', 'ROUNDDOWN', 'TRUNC'])}({expr},{rnd.choice([-3, -1, 0, 0, 2, 4])})")
        add(f"=ROUNDDOWN(ROUND({expr},4),-1)")
        add(f"=INT({expr})")
    for _ in range(100):
        base, n = rnd.randint(0, 99999), rnd.choice([0, 1, 2, -1])
        x = (base * 10 + 5) / 10 ** (n + 1)
        add(f"=ROUND({x!r},{n})")
        add(f"=ROUND(-{x!r},{n})")
        add(f"=ROUNDDOWN({base / 100!r}*100,0)")
        a, b = round(rnd.uniform(0, 1000), 3), round(rnd.uniform(0, 1000), 3)
        add(f"={a}+{b}-{round(a + b, 3)}")
        add(f"={a}+{b}={round(a + b, 3)}")
        add(f"=SUM({a},{b},{a})")
        d1 = datetime.date(2019, 1, 1) + datetime.timedelta(days=rnd.randint(0, 2500))
        d2 = d1 + datetime.timedelta(days=rnd.choice([0, 1, 28, 29, 30, 31, 365, 366, rnd.randint(0, 2500)]))
        add(f'=DATEDIF(DATE({d1.year},{d1.month},{d1.day})+1,DATE({d2.year},{d2.month},{d2.day})+1,"m")')
        add(f"=DATE({d2.year},{d2.month},{d2.day})-DATE({d1.year},{d1.month},{d1.day})+1")
    for f in ["=SUM(C1:C30)", "=MIN(C1:C30)", "=MAX(C1:C30)", "=COUNT(C1:D30)", '=SUMIF(D1:D30,"가산",C1:C30)', '=SUMIF(D1:D30,"abc",C1:C30)',
              '=SUMIF(D1:D30,"<>abc",C1:C30)', "=SUMIF(E1:E30,3,C1:C30)", '=SUMIF(E1:E30,">2",C1:C30)', '=SUMIFS(C1:C30,D1:D30,"차감",E1:E30,"<=3")',
              '=COUNTIF(D1:D30,"가산")', "=N(D1)", "=N(C99)", '=IF(C99="","blank","x")', "=C99", '=LEFT("2026-12-31",4)&MID("2026-12-31",6,2)',
              '=VALUE("12.50")', '=VALUE("abc")', "=DATE(2026,13,1)", "=DATE(2026,2,30)", "=1/0", "=IFERROR(1/0,0)", '="a"="A"', '=1="1"', '="12"*2',
              "=MOD(-10,3)", "=AVERAGE(C1:C30)", "=COUNTA(D1:D30)", "=NOT(1=2)", "=2^10", '=LEN("가나다abc")', "=ROUND(1.5)", "=1E+20+1"]:
        add(f)
    wb = _wb(cells)
    path = tmp_path / "edge.xlsx"
    wb.save(path)
    info = wc.fill_cached_values(wb, str(path))
    assert info["값_쓴_칸"] > 0.9 * info["수식_칸"]
    n, bad = compare_with_libreoffice(str(path), tmp_path / "lo")
    written = {ref for _, ref, t, v in _formula_cells(path) if v is not None and not (v == "" and t != "str")}
    assert [b for b in bad if b[1] in written] == []
