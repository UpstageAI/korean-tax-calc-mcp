"""국조 별지 제30호서식(갑) 틀 — cfc_deemed_dividend 결과로 ㉒·㉓·㉕ 칸이 도구 값과 같은지 (Claude 2026-11-14)."""
import openpyxl
from test_form_templates import build
from test_form_26 import Evaluator

SH = "국조 별지30갑 유보소득계산"
BASE = dict(year=2025, pretax_incomes=[1_000_000_000], taxes_paid=[50_000_000], ownership_chains=[[0.6], [0.5, 0.4]], related_party=True,
            fy_end="2025-12-31", distributable={"unappropriated_retained_earnings": 900_000_000, "dividends": 100_000_000, "bonuses_and_outflows": 20_000_000,
                                                "mandatory_reserves": 30_000_000, "previously_taxed_undistributed": 40_000_000,
                                                "pre_cfc_earnings_undistributed": 50_000_000, "unrealized_stock_gains": 10_000_000})


def test_full_inclusion_matches_tool(tmp_path):
    wb = openpyxl.load_workbook(build(tmp_path, [{"label": "CFC", "tool": "cfc_deemed_dividend", "args": BASE}]))
    assert SH in wb.sheetnames
    ev = Evaluator(wb)
    g = lambda a: ev.v(SH, a)
    # 유보 = 900 − 50 − (100+20+30+40+10) − 200 = 450백만, 보유비율 0.6 + 0.2 = 0.8 → 360백만
    assert g("F13") == 850_000_000 and g("F24") == 200_000_000 and g("F27") == 450_000_000
    assert abs(g("E8") - 0.8) < 1e-12 and g("F28") == 360_000_000 and g("F30") == 0


def test_passive_and_not_applied(tmp_path):
    args = dict(BASE, fixed_facility_active_business=True, passive_income=300_000_000, passive_excluded_dividends=0, total_revenue=2_000_000_000)
    wb = openpyxl.load_workbook(build(tmp_path, [{"label": "CFC", "tool": "cfc_deemed_dividend", "args": args}]))
    ev = Evaluator(wb)
    assert ev.v(SH, "F28") == 0 and ev.v(SH, "F30") == 54_000_000          # 450 × 0.15 × 0.8
    # 2억원 이하로 배당간주 미적용 → 시트 없음
    small = dict(BASE, pretax_incomes=[150_000_000], taxes_paid=[5_000_000])
    wb = openpyxl.load_workbook(build(tmp_path, [{"label": "CFC", "tool": "cfc_deemed_dividend", "args": small}]))
    assert SH not in wb.sheetnames
    # 2020 사업연도 → 구 서식 미확인이라 시트 없음
    wb = openpyxl.load_workbook(build(tmp_path, [{"label": "CFC", "tool": "cfc_deemed_dividend", "args": dict(BASE, year=2020, fy_end="2020-12-31")}]))
    assert SH not in wb.sheetnames
