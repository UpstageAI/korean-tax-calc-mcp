"""남은 산술 입력을 식으로 — 정답 테스트. 작성 Claude 2026-10-25 (docs/SPEC_export_workbook_h.md)."""
import copy
from test_export_workbook_c import c, evaluate
from test_export_workbook_f import DEMO


def _io(tool, args):
    r = c(tool, args)
    evaluate(r)
    return {i["이름"] for i in r["계산식_입력"]}, {s["이름"] for s in r["계산식"]}, r


def test_bundled_ratios_are_steps():
    for vat in (False, True):
        ins, st, _ = _io("bundled_supply_split", {**DEMO["bundled_supply_split"], "vat_included": vat})
        assert not ({"기준총계", "건물비율", "토지건물비율"} & ins), ins
        assert {"기준총계", "건물비율"} <= st


def test_common_prior_ratio_is_step():
    ins, st, r = _io("common_input_tax", DEMO["common_input_tax"])
    assert not any(n.startswith("직전과세비율") for n in ins), ins
    assert "직전과세비율" in st
    step = next(s for s in r["계산식"] if s["이름"] == "직전과세비율")
    assert "직전과세공급가액" in step["식"] and "직전면세공급가액" in step["식"]


def test_depreciation_booked_is_step():
    a = copy.deepcopy(DEMO["depreciation_adjustment"]); a["expensed_capex"] = 2000000
    ins, st, r = _io("depreciation_adjustment", a)
    assert "회사계상액" in st and "회사계상액" not in ins and "장부상각비" in ins
    assert "월수12" not in ins
