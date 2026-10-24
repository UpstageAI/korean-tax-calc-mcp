"""계산식 검수 반영 정답 테스트. 작성 Claude 2026-10-25 (docs/SPEC_export_workbook_g.md)."""
import copy, random, re
import pytest
from test_export_workbook_c import c, evaluate, ENT, ADJ
from test_export_workbook_f import DEMO

HANGUL = re.compile(r"^[가-힣][가-힣0-9_]*$")
KEYS = {"상각범위액": "상각범위액", "상각부인액": "상각부인액", "시인부족액": "시인부족액", "전기부인액_추인": "전기부인액_추인",
        "익금불산입액": "익금불산입액", "추가_매출세액": "추가_매출세액", "공제매입세액": "공제매입세액",
        "건물_공급가액": "건물_공급가액", "토지_가액": "토지_가액", "부가가치세": "부가가치세",
        "총급여액": "총급여액", "근로소득공제": "근로소득공제", "근로소득금액": "근로소득금액",
        "이자소득금액": "이자소득금액", "배당소득금액": "배당소득금액", "합산액": "합산액", "Gross-up": "GrossUp"}


def _random_cases(seed=20261025, n=40):
    rnd = random.Random(seed); R = rnd.randint; out = []
    for _ in range(n):
        d = copy.deepcopy(DEMO["depreciation_adjustment"])
        d.update(method=rnd.choice(["무신고", "정률법", "정액법"]), rate=rnd.choice([0.1, 0.2, 0.3, 0.451]),
                 booked_depreciation=R(0, 30) * 10**6, prior_disallowed=R(0, 10) * 10**6,
                 expensed_capex=R(0, 3) * 10**6, accumulated_dep_begin=R(0, 70) * 10**6)
        out.append(("depreciation_adjustment", d))
        d = copy.deepcopy(DEMO["dividend_received_deduction"])
        d["investees"] = [{"name": f"X{j}", "listed": rnd.random() < .5, "ratio": rnd.choice([0.05, 0.2, 0.3, 0.5, 0.8, 1.0]),
                           "dividend": R(1, 50) * 10**6, "book_value_jeoksu": R(1, 300) * 10**9} for j in range(R(1, 3))]
        d["interest_paid"] = R(0, 50) * 10**6; d["interest_excluded"] = R(0, min(10, d["interest_paid"] // 10**6)) * 10**6
        out.append(("dividend_received_deduction", d))
        out.append(("bundled_supply_split", {"total_price": R(100, 900) * 10**6, "vat_included": rnd.random() < .5,
                                             "standard_value": {"building": R(1, 500) * 10**6, "land": R(1, 500) * 10**6}}))
        out.append(("earned_income_gross_pay", {"year": rnd.choice([2019, 2022, 2024, 2025]),
                                                "items": [{"kind": "급여", "amount": R(1, 2000) * 500000, "facts": {}}]}))
        kinds = ["상장법인현금배당", "비상장법인현금배당", "출자공동사업자배당", "법원보증금이자", "예금이자"]
        out.append(("financial_income_aggregate", {"year": rnd.choice([2023, 2025]),
                                                   "items": [{"kind": rnd.choice(kinds), "amount": R(1, 30) * 10**6} for _ in range(R(1, 4))]}))
        d = copy.deepcopy(DEMO["common_input_tax"])
        d["supplies"] = {"확정": {"taxable": R(1, 100), "exempt": R(0, 100)}}
        d["prior_period_supplies"] = {"taxable": R(1, 100), "exempt": R(1, 100)}
        d["common_asset_sales"] = [{"sale_price": R(1, 40) * 100000 * rnd.choice([1, 10]), "input_tax": 0} for _ in range(R(1, 3))]
        out.append(("common_input_tax", d))
    return out


def _check(tool, args):
    r = c(tool, args)
    assert "계산식" in r, (tool, r.get("오류") or r)
    steps = evaluate(r)
    for k, name in KEYS.items():
        if k in r["결과"] and name in steps:
            assert abs(steps[name]["값"] - r["결과"][k]) < 1, (tool, name, steps[name]["값"], r["결과"][k], args)
    return r, steps


@pytest.mark.parametrize("tool, args", _random_cases(), ids=lambda x: x if isinstance(x, str) else "")
def test_random_inputs_formula_equals_tool(tool, args):
    _check(tool, args)


ALL = [("entertainment_adjustment", ENT), ("income_adjustment_total", ADJ)] + list(DEMO.items())


@pytest.mark.parametrize("tool, args", ALL, ids=[t for t, _ in ALL])
def test_names_are_korean_and_inputs_numeric(tool, args):
    r = c(tool, args)
    for x in r["계산식_입력"] + r["계산식"]:
        assert x["이름"] == "GrossUp" or HANGUL.match(x["이름"]), (tool, x["이름"])
    for i in r["계산식_입력"]:
        assert isinstance(i["값"], (int, float, bool)), (tool, i["이름"], i["값"])


@pytest.mark.parametrize("items, 분리, 배당, 합산", [
    ([{"kind": "비상장법인현금배당", "amount": 6000000}, {"kind": "상장법인현금배당", "amount": 14000000}], True, 0, 0),
    ([{"kind": "비상장법인현금배당", "amount": 6000001}, {"kind": "상장법인현금배당", "amount": 14000000}], False, None, None),
    ([{"kind": "출자공동사업자배당", "amount": 24000000}], True, 24000000, 24000000),
    ([{"kind": "상장법인현금배당", "amount": 13000000}, {"kind": "출자공동사업자배당", "amount": 20000000}], True, 20000000, 20000000),
])
def test_financial_income_boundaries(items, 분리, 배당, 합산):
    r, steps = _check("financial_income_aggregate", {"year": 2025, "items": items})
    assert r["결과"]["분리과세"] is 분리
    if 배당 is not None:
        assert r["결과"]["배당소득금액"] == 배당 and r["결과"]["합산액"] == 합산


def test_arithmetic_is_formula_not_input():
    r = c("depreciation_adjustment", DEMO["depreciation_adjustment"])
    ins = {i["이름"] for i in r["계산식_입력"]}; st = {s["이름"] for s in r["계산식"]}
    assert "정률법_기초미상각잔액" not in ins and "정률법_기초미상각잔액" in st
    r = c("dividend_received_deduction", DEMO["dividend_received_deduction"])
    ins = {i["이름"] for i in r["계산식_입력"]}; st = {s["이름"] for s in r["계산식"]}
    assert {"대상배당금1", "차입금이자"} <= st and not ({"대상배당금1", "차입금이자"} & ins)
