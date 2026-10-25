"""나머지 6개 도구 살아 있는 수식 정답 테스트. 작성 Claude 2026-10-25 (docs/SPEC_export_workbook_f.md)."""
import copy, shutil, subprocess
import openpyxl
import pytest
from test_export_workbook_c import c, evaluate, ENT, ADJ

DEMO = {'depreciation_adjustment': {'year': 2025,
                             'method': '무신고',
                             'asset_class': '건축물외_유형자산',
                             'acquisition_cost': 100000000,
                             'booked_depreciation': 15000000,
                             'accumulated_dep_begin': 72500000,
                             'rate': 0.3,
                             'expensed_capex': 1000000,
                             'prior_book_value': 27500000,
                             'prior_disallowed': 4000000},
 'dividend_received_deduction': {'year': 2025,
                                 'investees': [{'name': 'B',
                                                'listed': False,
                                                'ratio': 0.4,
                                                'dividend': 15000000,
                                                'book_value_jeoksu': 219000000000}],
                                 'interest_paid': 30000000,
                                 'interest_excluded': 10000000,
                                 'total_assets_jeoksu': 730000000000},
 'common_input_tax': {'year': 2025,
                      'period': '1기',
                      'filing': '확정',
                      'supplies': {'확정': {'taxable': 60, 'exempt': 40}},
                      'prior_period_supplies': {'taxable': 50, 'exempt': 50},
                      'common_asset_sales': [{'sale_price': 20000000, 'input_tax': 0}, {'sale_price': 400000, 'input_tax': 0}],
                      'ledger': [{'항목': '당기 매입 없음', '매입세액': 0, '사용처': '과세'}]},
 'bundled_supply_split': {'total_price': 500000000,
                          'vat_included': False,
                          'standard_value': {'building': 240000000, 'land': 160000000},
                          'book_value': {'building': 200000000, 'land': 200000000}},
 'earned_income_gross_pay': {'year': 2025,
                             'items': [{'kind': '급여', 'amount': 100000000, 'facts': {}},
                                       {'kind': '사회보험료_사용자부담분', 'amount': 3000000, 'facts': {'insurance': '건강보험'}},
                                       {'kind': '인정상여', 'amount': 5000000, 'facts': {'work_year': 2025, 'settlement_date': '2026-03-30'}},
                                       {'kind': '자가운전보조금',
                                        'amount': 2400000,
                                        'facts': {'months': 12, 'vehicle': '기타', 'business_use': False, 'actual_travel_reimbursed': False}},
                                       {'kind': '실비변상여비', 'amount': 4000000, 'facts': {'actual_cost': False}},
                                       {'kind': '직무발명보상금', 'amount': 7000000, 'facts': {'retired': False, 'related_party': True}},
                                       {'kind': '사택제공이익', 'amount': 20000000, 'facts': {'position': '지배주주인 대표자'}}]},
 'financial_income_aggregate': {'year': 2025,
                                'items': [{'kind': '출자공동사업자배당', 'amount': 6000000},
                                          {'kind': '의제배당_잉여금자본전입', 'amount': 10000000, 'source': '이익잉여금'},
                                          {'kind': '상장법인현금배당', 'amount': 7000000},
                                          {'kind': '비상장법인현금배당', 'amount': 8000000},
                                          {'kind': '직장공제회초과반환금', 'amount': 1000000},
                                          {'kind': '법원보증금이자', 'amount': 2000000}]}}


def v(tool, **kw):
    a = copy.deepcopy(DEMO[tool]); a.update(kw); return a


# (도구, args, {결과 키: 단계 이름}, 기대값 일부) — 기대값은 손 검산 (명세 f 표)
CASES = [
    ("depreciation_adjustment", DEMO["depreciation_adjustment"], {"상각범위액": 9450000, "상각부인액": 5550000, "시인부족액": 0, "전기부인액_추인": 0}),
    ("depreciation_adjustment", v("depreciation_adjustment", booked_depreciation=5000000), {"상각범위액": 9450000, "상각부인액": 0, "시인부족액": 4450000, "전기부인액_추인": 4000000}),
    ("depreciation_adjustment", v("depreciation_adjustment", method="정액법", rate=0.1, booked_depreciation=12000000, prior_disallowed=0, expensed_capex=0),
     {"상각범위액": 10000000, "상각부인액": 2000000, "시인부족액": 0, "전기부인액_추인": 0}),
    ("dividend_received_deduction", DEMO["dividend_received_deduction"], {"익금불산입액": 7200000}),
    ("dividend_received_deduction", v("dividend_received_deduction", investees=[{**DEMO["dividend_received_deduction"]["investees"][0], "ratio": 0.6}]), {"익금불산입액": 9000000}),
    ("dividend_received_deduction", v("dividend_received_deduction", investees=DEMO["dividend_received_deduction"]["investees"] + [
        {"name": "C", "listed": True, "ratio": 0.1, "dividend": 4000000, "book_value_jeoksu": 36500000000}]), {"익금불산입액": 8100000}),
    ("common_input_tax", DEMO["common_input_tax"], {"추가_매출세액": 1040000, "공제매입세액": 0}),
    ("bundled_supply_split", DEMO["bundled_supply_split"], {"건물_공급가액": 300000000, "토지_가액": 200000000, "부가가치세": 30000000}),
    ("bundled_supply_split", v("bundled_supply_split", vat_included=True), {"건물_공급가액": 283018867, "토지_가액": 188679247, "부가가치세": 28301886}),
    ("earned_income_gross_pay", DEMO["earned_income_gross_pay"], {"총급여액": 138400000, "근로소득공제": 15518000, "근로소득금액": 122882000}),
    ("earned_income_gross_pay", v("earned_income_gross_pay", items=[{"kind": "급여", "amount": 30000000, "facts": {}}]), {"총급여액": 30000000, "근로소득공제": 9750000, "근로소득금액": 20250000}),
    ("financial_income_aggregate", DEMO["financial_income_aggregate"], {"배당소득금액": 31500000, "합산액": 31500000, "Gross-up": 500000}),
    ("financial_income_aggregate", v("financial_income_aggregate", items=[{"kind": "상장법인현금배당", "amount": 8000000}, {"kind": "법원보증금이자", "amount": 2000000}]),
     {"배당소득금액": 0, "합산액": 0, "Gross-up": 0}),
]
STEP = {"Gross-up": "GrossUp"}   # 이름 규칙상 `-` 불가


@pytest.mark.parametrize("tool, args, expect", CASES, ids=[f"{t}-{i}" for i, (t, _, _) in enumerate(CASES)])
def test_formula_steps_match_tool_results(tool, args, expect):
    r = c(tool, args)
    steps = evaluate(r)                       # 모든 단계 식을 입력값으로 직접 계산해 값과 대조
    for key, want in expect.items():
        assert r["결과"][key] == want, (key, r["결과"][key])       # 기존 결과 값은 그대로
        name = STEP.get(key, key)
        assert name in steps, f"{tool}: 단계 {name} 없음"
        assert steps[name]["값"] == want, (name, steps[name])


def test_depreciation_formula_refers_to_inputs():
    steps = evaluate(c("depreciation_adjustment", DEMO["depreciation_adjustment"]))
    assert "상각범위액" in steps["상각부인액"]["식"] and "회사계상액" in steps["상각부인액"]["식"]


def test_dividend_formula_per_investee():
    r = c("dividend_received_deduction", CASES[5][1])
    steps = evaluate(r)
    assert {"대상액1", "차감액1", "대상액2", "차감액2"} <= set(steps)
    assert "차입금이자" in steps["차감액1"]["식"]


@pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice 없음")
def test_demo_workbook_all_checks_match(tmp_path):
    calls = [{"label": "기업업무추진비", "tool": "entertainment_adjustment", "args": ENT}] + [
        {"label": t, "tool": t, "args": a} for t, a in DEMO.items()] + [{"label": "차가감", "tool": "income_adjustment_total", "args": ADJ}]
    path = c("export_workbook", {"title": "수식 전체", "calls": calls, "output_dir": str(tmp_path)})["결과"]["파일"]
    out = tmp_path / "recalc"
    subprocess.run(["soffice", "--headless", "--calc", "--convert-to", "xlsx", "--outdir", str(out), path], check=True, capture_output=True, timeout=180)
    wb = openpyxl.load_workbook(next(out.glob("*.xlsx")), data_only=True)
    for i in range(1, len(calls) + 1):
        checks = [x.value for row in wb[f"계산 {i}"].iter_rows() for x in row if x.value in ("일치", "확인 필요")]
        assert checks and set(checks) == {"일치"}, (i, calls[i - 1]["tool"], checks)
