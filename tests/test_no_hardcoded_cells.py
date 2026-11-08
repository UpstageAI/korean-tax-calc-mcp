"""서식 시트 금액 칸에 계산 결과를 숫자로 박지 않는다 (Claude 2026-11-08).

배경: 0.21.0 엑셀에서 별지3 112 과세표준·115 산출세액이 `=337200000`처럼 도구 값으로 들어가
'서식 산식 그대로의 수식'이 끊겨 있었다. 0.21.0 테스트가 만든 엑셀 호출 33묶음 + 데모 1묶음(data/workbook_all_forms_calls.json)으로
서식 시트(목록·입력·가정·판단·근거·요약·계산 N 제외)의 인쇄 영역을 전수 조사했다.

정답(data/hardcoded_cells_golden.json, 102칸)은 0.21.0이 그 칸에 넣던 값이다. 수식으로 바뀌어도 값은 같아야 한다.
- '상수수식': `=숫자`(절댓값 100 이상) — 다른 칸 참조 또는 '입력·가정' 이름(호출N_…) 참조 수식으로 바꾼다.
  입력 사실(감면세액·당기발생액·전통시장 지출 등)은 '입력·가정' 시트의 이름 칸을 가리키게 한다.
- '계산값 숫자': 수식이 아닌 숫자로 들어간 계산 칸 — 별지26(을) 경과일수, 별지26(갑) ⑪ 적수·⑬, 별지50(을) ③감소·④증가,
  별지34 부도어음 비망가액 나눔(㉛·㉜). 원장 금액·지분율·기초잔액 같은 입력 사실 숫자는 대상 아님.
"""
import json, pathlib, re, shutil
import openpyxl, pytest
from openpyxl.utils import range_boundaries
from test_form_templates import build, recalc

D = pathlib.Path(__file__).parent / "data"
SETS = json.loads((D / "workbook_all_forms_calls.json").read_text("utf-8"))
GOLD = json.loads((D / "hardcoded_cells_golden.json").read_text("utf-8"))
SKIP = ("목록", "입력·가정", "판단·근거", "요약")
CONST = re.compile(r"^=\s*-?\d[\d,]*(\.\d+)?\s*$")


def _form_sheets(wb):
    for ws in wb.worksheets:
        if ws.title in SKIP or ws.title.startswith("계산"):
            continue
        pa = ws.print_area
        pa = (pa if isinstance(pa, str) else pa[0]).split("!")[-1].replace("$", "") if pa else None
        yield ws, (range_boundaries(pa) if pa else (1, 1, ws.max_column, ws.max_row))


@pytest.fixture(scope="module")
def books(tmp_path_factory):
    d = tmp_path_factory.mktemp("hc")
    out = {}
    for i, e in enumerate(SETS):
        sub = d / f"{i:03d}"; sub.mkdir()
        out[i] = build(sub, e["calls"], **e.get("kw", {}))
    return out


def test_no_constant_formulas(books):
    bad = []
    for i, p in books.items():
        for ws, (c1, r1, c2, r2) in _form_sheets(openpyxl.load_workbook(p)):
            for row in ws.iter_rows(min_row=r1, max_row=r2, min_col=c1, max_col=c2):
                for c in row:
                    v = c.value
                    if isinstance(v, str) and CONST.match(v) and abs(float(v[1:].replace(",", ""))) >= 100:
                        bad.append((i, ws.title, c.coordinate, v))
    assert not bad, bad[:20]


def test_target_cells_are_formulas(books):
    bad = []
    for g in GOLD:
        v = openpyxl.load_workbook(books[g["set"]])[g["sheet"]][g["cell"]].value
        if not (isinstance(v, str) and v.startswith("=") and not CONST.match(v)):
            bad.append((g["set"], g["sheet"], g["cell"], v))
    assert not bad, bad[:20]


@pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice 없음")
def test_target_values_unchanged(books, tmp_path):
    by_set = {}
    for g in GOLD:
        by_set.setdefault(g["set"], []).append(g)
    bad = []
    for i, gs in by_set.items():
        wb = recalc(books[i], tmp_path / f"r{i:03d}")
        for g in gs:
            v = wb[g["sheet"]][g["cell"]].value
            if v != pytest.approx(g["value"]):
                bad.append((i, g["sheet"], g["cell"], v, g["value"]))
    assert not bad, bad[:20]


@pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice 없음")
def test_check_cells_still_match(books, tmp_path):
    bad = []
    for i, p in books.items():
        wb = recalc(p, tmp_path / f"c{i:03d}")
        for ws in wb.worksheets:
            for row in ws.iter_rows():
                for c in row:
                    if c.value == "확인 필요":
                        bad.append((i, ws.title, c.coordinate))
    assert not bad, bad[:20]
