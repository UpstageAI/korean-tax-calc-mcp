"""별지 제32호서식 퇴직급여충당금 조정명세서·제33호서식 퇴직연금부담금 조정명세서 (Claude 2026-11-06).

서식 원문: 법인세법 시행규칙 별지 제32호서식 <개정 2019. 3. 20.> 2쪽, 제33호서식 <개정 2014. 3. 14.> 1쪽 전부 대조.
손계산(ARGS, 2025 사업연도, 추계액 적립비율 0%):
- ⑰ 총급여 1,000,000,000 − 확정기여형 설정자 100,000,000 = 900,000,000, ⑱ 50,000,000, ⑲ = ① = 850,000,000, ③ = 42,500,000.
- ④ 300,000,000 − ⑤ 0 − ⑥ 0 − ⑦ 280,000,000 − ⑧ 40,000,000 = △20,000,000 → ⑨ 0, (△) 20,000,000 손금산입(부인액 추인).
- ⑩ 650,000,000 × 0% = 0, ⑪ 2,000,000, ⑫ 0, ⑬ = 0 − 0 + 2,000,000 + 0 = 2,000,000, ⑭ = 2,000,000, ⑮ 30,000,000, ⑯ 28,000,000.
- 별지33: ① 650,000,000, ② 290,000,000, ③ 0, ④ 280,000,000 + 28,000,000 − 20,000,000 = 288,000,000, ⑤ 2,000,000, ⑥ 648,000,000.
  ⑭ 400,000,000 − ⑮ 0 − ⑯ 20,000,000 = ⑰ 380,000,000 = ⑦, ⑧ 268,000,000, ⑬ 500,000,000, ⑱ = ⑨ 120,000,000,
  ⑩ 120,000,000, ⑪ 0, ⑫ 120,000,000(손금산입). ⑲ 450,000,000, ⑳ 20,000,000, ㉑ = 500,000,000 − 450,000,000 + 20,000,000 = 70,000,000.
DC 전환자 설정 전 충당금(⑤): ⑨ = ④ − ⑤ − ⑥ − ⑦ − ⑧이므로 그 몫은 다른 직원 퇴직금 지급과 한도 계산에 쓰지 않는다(서식 작성방법 2~4).
"""
import openpyxl, pytest, shutil
from test_form_templates import build, c, recalc

S32, S33 = "별지32 퇴직급여충당금", "별지33 퇴직연금부담금"
ARGS = {"year": 2025,
        "allowance": {"opening": 300_000_000, "provision": 30_000_000, "paid_cash": 40_000_000, "closing": 290_000_000},
        "prior_disallowed": 280_000_000, "estimate": {"lump_sum": 600_000_000, "actuarial": 650_000_000},
        "salary": {"total": 1_000_000_000, "dc_members": 100_000_000, "not_eligible": 50_000_000}, "conversion_fund": 2_000_000,
        "pension": {"asset_closing": 500_000_000, "prior_deducted": 400_000_000, "book_provision": 0, "book_paid": 20_000_000,
                    "asset_opening": 450_000_000}}
NO_PENSION = {k: v for k, v in ARGS.items() if k != "pension"}


def _inputs(r):
    return {x["이름"]: x["값"] for x in r["계산식_입력"]}


def test_existing_results_unchanged():
    r = c("retirement_allowance_adjustment", ARGS)
    k = r["계산"]
    assert (k["총급여기준_한도"], k["추계액기준_한도"], k["퇴직급여충당금_한도"], k["부인액_추인"]) == (42_500_000, 2_000_000, 2_000_000, 20_000_000)
    assert (k["퇴직급여충당금_유보_기말"], k["이미_손금산입한_부담금"], k["퇴직연금_손금산입범위액"]) == (288_000_000, 380_000_000, 120_000_000)
    adj = {x["구분"]: x["금액"] for x in r["결과"]["세무조정"]}
    assert adj == {"퇴직급여충당금 한도초과": 28_000_000, "퇴직급여충당금(부인액 추인)": 20_000_000, "퇴직연금충당금": 120_000_000}


def test_form_inputs_from_tool():
    i = _inputs(c("retirement_allowance_adjustment", ARGS))
    want = {"장부기초": 300_000_000, "DC설정전": 0, "기초부인누계": 280_000_000, "기중지급": 40_000_000, "퇴직금전환금": 2_000_000,
            "회사계상": 30_000_000, "장부기말": 290_000_000, "추계액_일시퇴직": 600_000_000, "추계액_보험수리": 650_000_000,
            "추계액_적립비율": 0, "퇴직연금여부": True, "연금충당금_기초": 400_000_000, "연금_수령": 20_000_000,
            "연금_회사계상": 0, "운용자산기말": 500_000_000, "운용자산기초": 450_000_000, "운용자산납입": 70_000_000}
    for name, v in want.items():
        assert i[name] == v, name


def test_pension_adjustment_amount_signed():
    k = c("retirement_allowance_adjustment", ARGS)["계산"]
    assert k["퇴직연금_조정금액"] == 120_000_000
    a = dict(ARGS, pension=dict(ARGS["pension"], book_provision=150_000_000))
    assert c("retirement_allowance_adjustment", a)["계산"]["퇴직연금_조정금액"] == -30_000_000


def test_salary_row_for_form():
    r = c("retirement_allowance_adjustment", ARGS)
    assert r["서식_표"]["32_총급여"] == [{"계정명": "총급여", "총급여_인원": "", "총급여": 900_000_000, "지급대상외_인원": "",
                                         "지급대상외": 50_000_000, "지급대상_인원": ""}]


def test_deposit_derived_from_opening_or_opening_from_deposit():
    p = dict(ARGS["pension"]); p.pop("asset_opening"); p["deposited"] = 70_000_000
    i = _inputs(c("retirement_allowance_adjustment", dict(ARGS, pension=p)))
    assert i["운용자산기초"] == 450_000_000 and i["운용자산납입"] == 70_000_000
    p.pop("deposited")
    i = _inputs(c("retirement_allowance_adjustment", dict(ARGS, pension=p)))
    assert "운용자산기초" not in i and "운용자산납입" not in i


def test_no_pension_inputs():
    i = _inputs(c("retirement_allowance_adjustment", NO_PENSION))
    assert i["퇴직연금여부"] is False and i["DC설정전"] == 0


def test_dc_transferred_kept_apart_from_payment_and_limit():
    # ⑨ = 100,000,000 − 20,000,000 − 0 − 10,000,000 − 75,000,000 = △5,000,000 → 부인액 추인 5,000,000
    a = {"year": 2025, "allowance": {"opening": 100_000_000, "provision": 10_000_000, "paid_cash": 75_000_000, "closing": 35_000_000},
         "prior_disallowed": 10_000_000, "estimate": {"lump_sum": 300_000_000}, "salary": {"total": 500_000_000},
         "pension": {"asset_closing": 50_000_000, "prior_deducted": 0, "book_provision": 0, "dc_transferred_allowance": 20_000_000}}
    k = c("retirement_allowance_adjustment", a)["계산"]
    assert k["부인액_추인"] == 5_000_000 and k["세무상_설정전잔액"] == 0
    assert k["퇴직급여충당금_유보_기말"] == 15_000_000          # 10,000,000 + 한도초과 10,000,000 − 추인 5,000,000
    assert k["세무상_퇴직급여충당금_기말"] == 20_000_000        # DC 전환자 몫은 세무상 잔액에 그대로 남음
    assert k["추계액기준_연금한도"] == 300_000_000              # 300,000,000 − (20,000,000 − 20,000,000) − 0


@pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice 없음")
def test_form_sheet_values_and_checks(tmp_path):
    path = build(tmp_path, [{"tool": "retirement_allowance_adjustment", "args": ARGS}])
    wb = recalc(path, tmp_path)
    w32, w33 = wb[S32], wb[S33]
    want32 = {"B6": 850_000_000, "I6": 42_500_000, "B8": 300_000_000, "D8": 0, "F8": 0, "G8": 280_000_000, "I8": 40_000_000,
              "K8": 0, "L8": 20_000_000, "B10": 0, "E10": 2_000_000, "G10": 0, "J10": 2_000_000, "B12": 2_000_000,
              "F12": 30_000_000, "J12": 28_000_000, "C16": 900_000_000, "E16": 50_000_000, "G16": 850_000_000,
              "C20": 900_000_000, "E20": 50_000_000, "G20": 850_000_000, "I16": 600_000_000, "I18": 650_000_000, "I20": 650_000_000}
    want33 = {"A7": 650_000_000, "C7": 290_000_000, "E7": 0, "G7": 288_000_000, "I7": 2_000_000, "K7": 648_000_000,
              "A9": 380_000_000, "C9": 268_000_000, "E9": 120_000_000, "G9": 120_000_000, "I9": 0, "K9": 120_000_000,
              "A13": 500_000_000, "C13": 400_000_000, "E13": 0, "G13": 20_000_000, "I13": 380_000_000, "K13": 120_000_000,
              "A16": 450_000_000, "D16": 20_000_000, "G16": 70_000_000, "J16": 500_000_000}
    for ws, want in ((w32, want32), (w33, want33)):
        for addr, v in want.items():
            assert ws[addr].value == v, (ws.title, addr)
        checks = [x.value for row in ws.iter_rows() for x in row if x.value in ("일치", "확인 필요")]
        assert checks and set(checks) == {"일치"}, ws.title
    assert w32["A16"].value == "총급여" and w32["F6"].value == 0.05


def test_form_sheet_layout(tmp_path):
    wb = openpyxl.load_workbook(build(tmp_path, [{"tool": "retirement_allowance_adjustment", "args": ARGS}]))
    assert S32 in wb.sheetnames and S33 in wb.sheetnames
    assert wb.sheetnames.index(S33) == wb.sheetnames.index(S32) + 1
    w32, w33 = wb[S32], wb[S33]
    assert w32["D2"].value == "퇴직급여충당금 조정명세서" and w33["D2"].value == "퇴직연금부담금 조정명세서"
    assert w32["J12"].value.startswith("=") and w33["K9"].value.startswith("=") and S32 in w33["A7"].value
    assert {"B6:E6", "J10:L10", "I20:L20"} <= {str(m) for m in w32.merged_cells.ranges}


def test_no_pension_no_form_33(tmp_path):
    wb = openpyxl.load_workbook(build(tmp_path, [{"tool": "retirement_allowance_adjustment", "args": NO_PENSION}]))
    assert S32 in wb.sheetnames and S33 not in wb.sheetnames
