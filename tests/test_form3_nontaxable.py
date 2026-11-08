"""별지3 110 비과세소득·111 소득공제 — 최저한세 조정 call 입력에서 받는다 (Claude 2026-11-08).

배경: 110·111은 받을 입력이 없어 항상 빈칸이었고, 109 이월결손금은 108 − 110 − 111 − 112로 거꾸로 구해
비과세소득·소득공제가 있으면 그 금액이 109에 섞였다. minimum_tax_adjustment call이 있으면 그 입력(nontaxable·income_deduction)을 쓴다.
"""
import openpyxl
from test_form_templates import build
from test_form_26 import Evaluator

S3 = "별지3 과세표준및세액조정계산서"
ADJ = {"net_income": 300_000_000, "items": [{"항목": "법인세비용", "종류": "법인세비용", "금액": 20_000_000}]}
# 108 = 320,000,000, 이월결손금 30,000,000·비과세 5,000,000·소득공제 3,000,000 → 112 = 282,000,000
MT = {"year": 2025, "sme": True, "net_income": 300_000_000, "income_add": 20_000_000, "income_deduct": 0,
      "loss_carryforward": 30_000_000, "nontaxable": 5_000_000, "income_deduction": 3_000_000}


def _calls(with_mt):
    calls = [{"label": "세무조정", "tool": "income_adjustment_total", "args": ADJ}]
    if with_mt:
        calls.append({"label": "최저한세", "tool": "minimum_tax_adjustment", "args": MT})
    calls.append({"label": "법인세", "tool": "corporate_tax", "args": {"base": 282_000_000, "year": 2025}})
    return calls


def test_nontaxable_and_deduction_from_minimum_tax_call(tmp_path):
    wb = openpyxl.load_workbook(build(tmp_path, _calls(True)))
    ws, ev = wb[S3], Evaluator(wb)
    assert ws["F14"].value == "=호출2_비과세소득" and ws["F15"].value == "=호출2_소득공제"
    g = lambda a: ev.v(S3, a)
    assert (g("F12"), g("F14"), g("F15"), g("F16")) == (320_000_000, 5_000_000, 3_000_000, 282_000_000)
    assert g("F13") == 30_000_000                       # 109 이월결손금 — 비과세·소득공제가 섞이지 않음


def test_blank_without_minimum_tax_call(tmp_path):
    wb = openpyxl.load_workbook(build(tmp_path, _calls(False)))
    ws = wb[S3]
    assert ws["F14"].value in (None, "") and ws["F15"].value in (None, "")
