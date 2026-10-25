"""수식 이름 치환·차가감 식 정답 테스트. 작성 Claude 2026-10-25 (docs/SPEC_export_workbook_e.md)."""
import asyncio, json, pathlib, re, shutil, subprocess
import pytest
from korean_tax_calc_mcp.server import mcp, _이름_치환

SRC = pathlib.Path(__file__).resolve().parents[1] / "korean_tax_calc_mcp" / "server.py"
M = {"항목1": "호출1_항목1", "항목2": "호출1_항목2", "EBIT": "호출1_EBIT"}


def c(tool, a):
    r = asyncio.run(mcp.call_tool(tool, a))
    return json.loads((r.content[0] if hasattr(r, "content") else r[0][0]).text)


@pytest.mark.parametrize("식, 기대", [
    ("2-EBIT", "2-호출1_EBIT"),
    ("12-항목1", "12-호출1_항목1"),
    ("0.1*항목2", "0.1*호출1_항목2"),
    ("1.5E+2-항목1", "1.5E+2-호출1_항목1"),
    ("2e-3+EBIT", "2e-3+호출1_EBIT"),
    ("MIN(항목1,3-EBIT)", "MIN(호출1_항목1,3-호출1_EBIT)"),
    ("0-0", "0-0"),
])
def test_number_tokens_stop_before_operators(식, 기대):
    assert _이름_치환(식, M) == 기대


def test_exponent_without_digits_is_a_name():
    assert _이름_치환("3*E", {"E": "호출1_E"}) == "3*호출1_E"
    assert _이름_치환("3-E", {"E": "호출1_E"}) == "3-호출1_E"


BASE = {"net_income": 300000000, "items": [
    {"항목": "법인세비용", "종류": "법인세비용", "금액": 20000000},
    {"항목": "㈜B 수입배당금 익금불산입", "종류": "수입배당금 익금불산입", "금액": 7200000},
    {"항목": "기업업무추진비 한도초과", "종류": "기업업무추진비 한도초과", "금액": 2280000}]}


def _step(r, name):
    return next(s for s in r["계산식"] if s["이름"] == name)


@pytest.mark.parametrize("extra, 기대식", [
    ({}, "차가감소득금액"),
    ({"donation_excess": 1000000}, "차가감소득금액+기부금한도초과"),
    ({"donation_carryover_deduction": 500000}, "차가감소득금액-기부금이월공제"),
    ({"donation_excess": 1000000, "donation_carryover_deduction": 500000}, "차가감소득금액+기부금한도초과-기부금이월공제"),
])
def test_each_year_income_formula_has_no_zero_terms(extra, 기대식):
    r = c("income_adjustment_total", {**BASE, **extra})
    s = _step(r, "각사업연도소득금액")
    assert s["식"] == 기대식
    assert "+0" not in s["식"] and "-0" not in s["식"]
    assert s["값"] == r["결과"]["각사업연도소득금액"]


def test_item_names_are_contiguous():
    r = c("income_adjustment_total", {**BASE, "donation_excess": 1000000, "donation_carryover_deduction": 500000})
    items = [i["이름"] for i in r["계산식_입력"] if re.fullmatch(r"항목\d+", i["이름"])]
    assert items == ["항목1", "항목2", "항목3"]
    assert _step(r, "익금산입_손금불산입")["식"] == "항목1+항목2"
    assert _step(r, "손금산입_익금불산입")["식"] == "항목3"


def _old_pythons():
    return [p for p in (shutil.which("python3.10"), shutil.which("python3.11"),
                        str(pathlib.Path.home() / ".local/bin/python3.11")) if p and pathlib.Path(p).exists()]


def test_server_compiles_on_python310_311():
    pys = _old_pythons()
    if not pys:
        pytest.skip("python3.10/3.11 없음")
    for py in pys:
        r = subprocess.run([py, "-c", "import ast,sys; ast.parse(open(sys.argv[1], encoding='utf-8').read())", str(SRC)],
                           capture_output=True, text=True)
        assert r.returncode == 0, f"{py}: {r.stderr[-400:]}"
