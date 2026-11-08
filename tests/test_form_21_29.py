"""별지 제21호서식 기부금조정명세서·제29호서식 업무용승용차 관련비용 명세서, 기업업무추진비 한도 도구의 별지 제23호 연결,
사회적기업 일반기부금 한도율 연도별 적용 (Claude 2026-11-08).

서식 원문: 법인세법 시행규칙 별지 제21호서식 <개정 2026. 3. 20.> 2쪽, 제29호서식 <개정 2026. 3. 20.> 3쪽 전부 대조.
조문: 법인세법 제24조③2호 — 2025. 12. 31. 시행본 "사회적기업은 20퍼센트", 2026. 1. 1. 시행본 "30퍼센트"
(법률 제21217호 2025. 12. 23. 부칙 제3조: 시행(2026. 1. 1.) 이후 개시하는 사업연도에 지출하는 기부금부터).
사회적기업 특례는 2018 사업연도부터(그 전 10%). 시행령 제50조의2(2026. 1. 2.)·제42조(2026. 2. 27.) 개정은 부처명·인용 조문만 바뀌어 금액 그대로.

손계산
[기부금 A] 2025, 중소, 기준소득 347,200,000, 일반 10,000,000:
  ① 347,200,000 ② 0 ③ 0 ④ 173,600,000 ⑤ 0 ⑥ 0 ⑦ 0 ⑧ 347,200,000 ⑨ 0 ⑩ 104,160,000 ⑪ 0 ⑫ 0
  ⑬ 10,000,000 ⑭ 34,720,000 ⑮ 0 ⑯ 10,000,000 ⑰ 0 ⑱ 10,000,000 ⑲ 10,000,000 ⑳ 0.
[기부금 B] 2025, 비중소(결손금 80% 한도), 기준소득 200,000,000, 결손금 300,000,000 → ② 160,000,000,
  특례 30,000,000·이월 5,000,000, 일반 10,000,000·이월 2,000,000(이월분 먼저):
  ④ 20,000,000 ⑤ 5,000,000 ⑥ 15,000,000 ⑦ 15,000,000 ⑧ 20,000,000 ⑩ 6,000,000 ⑭ 2,000,000 ⑮ 2,000,000 ⑯ 0 ⑰ 10,000,000
  ⑱ 40,000,000 ⑲ 15,000,000 ⑳ 25,000,000 / ㉓특례 5,000,000 ㉔ 5,000,000 ㉕ 0, ㉓일반 2,000,000 ㉔ 2,000,000 ㉕ 0
  / ㉖특례 30,000,000 ㉗ 15,000,000 ㉘ 15,000,000, ㉖일반 10,000,000 ㉗ 0 ㉘ 10,000,000 (차기이월 합계 25,000,000).
[기부금 C] 2018(당기분 먼저), 기준소득 100,000,000, 특례 40,000,000·이월 20,000,000:
  ④ 50,000,000 ⑥ 40,000,000 ⑤ 10,000,000 ⑧ 50,000,000 ⑭ 5,000,000 ㉕특례 10,000,000.
[사회적기업] 기준소득 100,000,000, 일반 50,000,000: 2017 ⑭ 10,000,000, 2025 ⑭ 20,000,000, 2026 ⑭ 30,000,000(한도초과 20,000,000).
[승용차 A] 2025, 운행기록 미작성, 취득가액 90,000,000, 세법상 감가상각비 18,000,000, 유지비 12,000,000:
  ⑨ = MIN(1, 15,000,000/30,000,000) = 50%, ⑯ 18,000,000, ⑲~㉓ 12,000,000, ㉔ 30,000,000, ㉙ 9,000,000 ㉚ 6,000,000 ㉛ 15,000,000
  ㉜ 9,000,000 ㉝ 6,000,000 ㉞ 15,000,000 ㉟ 1,000,000(9,000,000 − 8,000,000) ㊱ 16,000,000 ㊲ 14,000,000 ㊸·㊹·㊻ 1,000,000.
[승용차 B] 운행기록 80%, 보유 6개월, 감가상각비 9,000,000, 유지비 5,000,000:
  ㉔ 14,000,000 ㉙ 7,200,000 ㉚ 4,000,000 ㉜ 1,800,000 ㉝ 1,000,000 ㉟ 3,200,000(7,200,000 − 8,000,000×6/12) ㊱ 6,000,000 ㊲ 8,000,000.
[승용차 C] 부동산임대업 주업법인, 미작성, 감가상각비 10,000,000, 유지비 6,000,000:
  ⑨ = 5,000,000/16,000,000 = 31.25%, ㉙ 3,125,000 ㉚ 1,875,000 ㉜ 6,875,000 ㉝ 4,125,000 ㉟ 0(한도 4,000,000) ㊱ 11,000,000 ㊲ 5,000,000.
[기업업무추진비 한도] 2025, 중소, 수입금액 8,500,000,000, 지출 46,800,000 → 한도 61,500,000(3,600만 + 85억×0.3%), 초과 0.
  지출 80,000,000이면 한도초과 18,500,000.
"""
import openpyxl, pytest, shutil
from test_form_templates import build, c, recalc

S21, S29 = "별지21 기부금조정명세서", "별지29 업무용승용차"
GAP, EUL = "별지23(갑) 기업업무추진비", "별지23(을) 기업업무추진비"
DON_A = {"year": 2025, "base_income": 347_200_000, "general": 10_000_000}
DON_B = {"year": 2025, "sme": False, "base_income": 200_000_000, "carried_loss": 300_000_000, "special": 30_000_000,
         "special_carry": 5_000_000, "general": 10_000_000, "general_carry": 2_000_000}
DON_C = {"year": 2018, "base_income": 100_000_000, "special": 40_000_000, "special_carry": 20_000_000}
CAR_A = {"year": 2025, "upkeep": 12_000_000, "depreciation": 18_000_000, "booked_depreciation": 18_000_000, "log_kept": False,
         "acquisition_cost": 90_000_000}
CAR_B = {"year": 2025, "upkeep": 5_000_000, "depreciation": 9_000_000, "booked_depreciation": 9_000_000, "log_kept": True,
         "business_ratio": 0.8, "months": 6}
CAR_C = {"year": 2025, "upkeep": 6_000_000, "depreciation": 10_000_000, "booked_depreciation": 10_000_000, "log_kept": False,
         "rental_corp": True}
ENT = {"year": 2025, "sme": True, "general_revenue": 8_500_000_000, "expensed": 46_800_000}


# ── 1. 사회적기업 일반기부금 한도율은 연도별(법 제24조③2호, 부칙 2025.12.23 제3조) ──
@pytest.mark.parametrize("year,limit", [(2017, 10_000_000), (2018, 20_000_000), (2025, 20_000_000), (2026, 30_000_000)])
def test_social_enterprise_rate_by_year(year, limit):
    r = c("donation_limit", {"year": year, "base_income": 100_000_000, "general": 50_000_000, "social_enterprise": True})["결과"]
    assert r["일반한도"] == limit
    assert r["한도초과(기타사외유출)"] == 50_000_000 - limit


def test_non_social_enterprise_unchanged_2026():
    r = c("donation_limit", {"year": 2026, "base_income": 100_000_000, "general": 50_000_000})["결과"]
    assert r["일반한도"] == 10_000_000


def test_existing_donation_results_unchanged():
    a = c("donation_limit", DON_A)["결과"]
    assert (a["특례한도"], a["일반한도"], a["한도초과(기타사외유출)"]) == (173_600_000, 34_720_000, 0)
    b = c("donation_limit", DON_B)["결과"]
    assert (b["특례한도"], b["일반한도"], b["이월분 손금산입"], b["한도초과(기타사외유출)"]) == (20_000_000, 2_000_000, 7_000_000, 25_000_000)
    assert b["차기이월"] == {"특례": 15_000_000, "일반": 10_000_000}


def test_existing_car_results_unchanged():
    r = c("business_car_expense", CAR_A)["결과"]
    assert (r["업무사용비율"], r["유지비 손금불산입(상여)"], r["감가상각 사적사용 손금불산입(상여)"], r["감가상각 한도초과(유보)"]) == (0.5, 6_000_000, 9_000_000, 1_000_000)


# ── 2. 목록에 '서식 틀 없음'이 남지 않는다 ──
def test_no_missing_template_rows(tmp_path):
    wb = openpyxl.load_workbook(build(tmp_path, [{"tool": "donation_limit", "args": DON_A}, {"tool": "business_car_expense", "args": CAR_A},
                                                 {"tool": "entertainment_limit", "args": ENT}]))
    texts = [str(x.value) for row in wb["목록"].iter_rows() for x in row if x.value]
    assert not any("서식 틀 없음" in t for t in texts), texts
    for s in (S21, S29, GAP, EUL):
        assert s in wb.sheetnames, (s, wb.sheetnames)


def test_layout(tmp_path):
    wb = openpyxl.load_workbook(build(tmp_path, [{"tool": "donation_limit", "args": DON_B}, {"tool": "business_car_expense", "args": CAR_A}]))
    w21, w29 = wb[S21], wb[S29]
    assert w21["C2"].value == "기부금조정명세서" and w29["E2"].value == "업무용승용차 관련비용 명세서"
    assert "별지 제21호서식" in w21["A1"].value and "별지 제29호서식" in w29["A1"].value
    assert w21["E18"].value.startswith("=") and w29["N12"].value.startswith("=") and w29["W7"].value.startswith("=")
    assert {"E18:G18", "F5:G5", "C25:D25"} <= {str(m) for m in w21.merged_cells.ranges}
    assert {"R7:V7", "N12:P12", "T12:W12"} <= {str(m) for m in w29.merged_cells.ranges}
    assert w29["F7"].value == "부" and w29["E7"].value in ("부착", "")
    assert "[√]해당" not in w29["A4"].value


def _vals(tmp_path, calls, sheet):
    path = build(tmp_path, calls)
    wb = recalc(path, tmp_path)
    ws = wb[sheet]
    checks = [x.value for row in ws.iter_rows() for x in row if x.value in ("일치", "확인 필요")]
    return ws, checks


# ── 3. 서식 칸 값(LibreOffice 재계산)과 확인 칸 ──
@pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice 없음")
@pytest.mark.parametrize("args,want", [
    (DON_A, {"C5": 347_200_000, "C6": 0, "C7": 0, "C8": 173_600_000, "F5": 0, "F6": 0, "F7": 0, "F8": 347_200_000,
             "C10": 0, "C11": 104_160_000, "F10": 0, "F11": 0, "C13": 10_000_000, "C14": 34_720_000, "C15": 0,
             "F13": 10_000_000, "F14": 0, "A18": 10_000_000, "C18": 10_000_000, "E18": 0}),
    (DON_B, {"C5": 200_000_000, "C6": 160_000_000, "C7": 30_000_000, "C8": 20_000_000, "F5": 5_000_000, "F6": 15_000_000,
             "F7": 15_000_000, "F8": 20_000_000, "C11": 6_000_000, "C13": 10_000_000, "C14": 2_000_000, "C15": 2_000_000,
             "F13": 0, "F14": 10_000_000, "A18": 40_000_000, "C18": 15_000_000, "E18": 25_000_000,
             "E21": 5_000_000, "F21": 5_000_000, "G21": 0, "E22": 2_000_000, "F22": 2_000_000, "G22": 0,
             "C25": 30_000_000, "E25": 15_000_000, "G25": 15_000_000, "C26": 10_000_000, "E26": 0, "G26": 10_000_000}),
    (DON_C, {"C8": 50_000_000, "F6": 40_000_000, "F5": 10_000_000, "F8": 50_000_000, "C14": 5_000_000, "G21": 10_000_000}),
])
def test_form21_values(tmp_path, args, want):
    ws, checks = _vals(tmp_path, [{"tool": "donation_limit", "args": args}], S21)
    for addr, v in want.items():
        assert ws[addr].value == v, (addr, ws[addr].value, v)
    assert checks and set(checks) == {"일치"}


@pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice 없음")
def test_form21_social_enterprise_2026(tmp_path):
    ws, checks = _vals(tmp_path, [{"tool": "donation_limit", "args": {"year": 2026, "base_income": 100_000_000, "general": 50_000_000,
                                                                      "social_enterprise": True}}], S21)
    assert ws["C14"].value == 30_000_000 and ws["F14"].value == 20_000_000 and ws["E18"].value == 20_000_000
    assert checks and set(checks) == {"일치"}


@pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice 없음")
@pytest.mark.parametrize("args,want", [
    (CAR_A, {"I7": 0.5, "M7": 90_000_000, "N7": 12, "O7": 18_000_000, "R7": 12_000_000, "W7": 30_000_000,
             "B12": 9_000_000, "D12": 6_000_000, "F12": 15_000_000, "H12": 9_000_000, "J12": 6_000_000, "L12": 15_000_000,
             "N12": 1_000_000, "Q12": 16_000_000, "T12": 14_000_000, "W8": 30_000_000, "T13": 14_000_000,
             "I16": 1_000_000, "L16": 1_000_000, "T16": 1_000_000}),
    (CAR_B, {"I7": 0.8, "N7": 6, "W7": 14_000_000, "B12": 7_200_000, "D12": 4_000_000, "H12": 1_800_000, "J12": 1_000_000,
             "N12": 3_200_000, "Q12": 6_000_000, "T12": 8_000_000}),
    (CAR_C, {"I7": 0.3125, "B12": 3_125_000, "D12": 1_875_000, "H12": 6_875_000, "J12": 4_125_000, "N12": 0,
             "Q12": 11_000_000, "T12": 5_000_000}),
])
def test_form29_values(tmp_path, args, want):
    ws, checks = _vals(tmp_path, [{"tool": "business_car_expense", "args": args}], S29)
    for addr, v in want.items():
        assert ws[addr].value == pytest.approx(v), (addr, ws[addr].value, v)
    assert checks and set(checks) == {"일치"}


@pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice 없음")
def test_form29_rental_corp_mark(tmp_path):
    ws, _ = _vals(tmp_path, [{"tool": "business_car_expense", "args": CAR_C}], S29)
    assert "[√]해당" in ws["A4"].value


@pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice 없음")
@pytest.mark.parametrize("expensed,over", [(46_800_000, 0), (80_000_000, 18_500_000)])
def test_form23_from_entertainment_limit(tmp_path, expensed, over):
    path = build(tmp_path, [{"tool": "entertainment_limit", "args": dict(ENT, expensed=expensed)}])
    wb = recalc(path, tmp_path)
    g = wb[GAP]
    assert g["D8"].value == expensed and g["D9"].value == 36_000_000 and g["D19"].value == 61_500_000
    assert g["D26"].value == 61_500_000 and g["D27"].value == over
    assert wb[EUL]["C7"].value == 8_500_000_000
    for ws in (g, wb[EUL]):
        checks = [x.value for row in ws.iter_rows() for x in row if x.value in ("일치", "확인 필요")]
        assert not checks or set(checks) == {"일치"}, ws.title


def test_entertainment_adjustment_forms_unchanged(tmp_path):
    """기존 entertainment_adjustment 연결은 그대로(틀 tool 목록에 두 도구)."""
    import json, pathlib
    d = pathlib.Path(__file__).resolve().parent.parent / "korean_tax_calc_mcp" / "data" / "form_templates"
    for k in ("별지23갑", "별지23을"):
        t = json.loads((d / f"{k}.json").read_text("utf-8"))
        tools = t.get("tools") or [t.get("tool")]
        assert "entertainment_adjustment" in tools and "entertainment_limit" in tools
