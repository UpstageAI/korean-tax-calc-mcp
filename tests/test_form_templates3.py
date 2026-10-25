"""법정서식 3단계(부가·종소) 정답 테스트. 작성 Claude 2026-10-25 (docs/SPEC_form_templates3.md). 값은 가상 사례 손 검산."""
import copy, re, shutil
import openpyxl
import pytest
from test_form_templates import CALLS, build, recalc, c

V22, V63, V64, IDIV, IWAGE = ("부가 별지22 공제받지못할매입세액", "부가 계산근거 공통사용재화", "부가 계산근거 일괄양도",
                              "종소 배당·이자소득명세서", "종소 근로소득명세서")
soffice = pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice 없음")


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    d = tmp_path_factory.mktemp("tpl3")
    path = build(d, CALLS)
    return openpyxl.load_workbook(path), (recalc(path, d) if shutil.which("soffice") else None)


def test_all_demo_calls_have_forms(demo):
    raw, _ = demo
    n = raw.sheetnames
    assert n[8:13] == [V22, V63, V64, IDIV, IWAGE], n
    assert not any(re.fullmatch(r"계산 \d+", x) for x in n)
    assert n[-2:] == ["입력·가정", "판단·근거"]
    assert "2025년 제1기" in raw[V22]["A3"].value and "대표 갑 금융소득" in raw[IDIV]["A3"].value


@soffice
def test_vat_values(demo):
    _, calc = demo
    w = calc[V63]
    assert [[w.cell(r, col).value for col in range(2, 6)] for r in (11, 12)] == [[20000000, 0.5, 10000000, 1000000], [400000, 0.5, 400000, 40000]]
    assert (w["D21"].value, w["E21"].value) == (10400000, 1040000)
    assert [calc[V64].cell(r, 3).value for r in (10, 12, 13, 14)] == [400000000, 300000000, 30000000, 200000000]


@soffice
def test_income_values(demo):
    raw, calc = demo
    w = calc[IDIV]
    rows = [[w.cell(r, col).value for col in (1, 2, 3, 5)] for r in range(8, 12)]
    assert [(str(a), b, d) for a, b, _, d in rows] == [("21", 1, 10000000), ("21", 2, 7000000), ("21", 3, 8000000), ("28", 1, 6000000)]
    assert [w.cell(18, col).value for col in range(5, 9)] == [31000000, 5000000, 500000, 31500000]
    assert [calc[IWAGE].cell(8, col).value for col in range(5, 8)] == [138400000, 15518000, 122882000]
    checks = [x.value for s in (V22, V63, V64, IDIV, IWAGE) for r in calc[s].iter_rows() for x in r if x.value in ("일치", "확인 필요")]
    assert len(checks) == 10 and set(checks) == {"일치"}           # 같은 행 검증 2개도 각각(부가근거63 J·종소배당 M)


def test_items_breakdown_in_calc():
    fin = next(x for x in CALLS if x["tool"] == "financial_income_aggregate")
    r = c("financial_income_aggregate", fin["args"])
    got = [(i["항목"], i["금액"], i["구분"]) for i in r["계산"]["항목별"]]
    assert ("출자공동사업자배당", 6000000, "출자공동") in got and ("상장법인현금배당", 7000000, "GU대상") in got
    assert ("법원보증금이자", 2000000, "제외") in got


def test_separate_taxation_skips_dividend_sheet(tmp_path):
    calls = copy.deepcopy(CALLS)
    fin = next(x for x in calls if x["tool"] == "financial_income_aggregate")
    fin["args"]["items"] = [{"kind": "상장법인현금배당", "amount": 8000000}]
    raw = openpyxl.load_workbook(build(tmp_path, calls))
    assert IDIV not in raw.sheetnames
    txt = " ".join(str(x.value) for r in raw["목록"].iter_rows() for x in r if x.value)
    assert "배당소득명세서" in txt and "분리과세" in txt
