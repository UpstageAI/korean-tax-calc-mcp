"""export_workbook — 실제 사용 입력에서 나온 서식 엑셀 문제 회귀 테스트.

openpyxl로 만든 파일을 다시 읽어 칸을 확인한다(수식은 문자열, 도구 값은 숫자).
- 정액법 감가상각 → 별지 제20호서식(2)
- 서식 칸·표는 그 값을 만든 call에서(calls 자리 번호로 가정하지 않음), 두 도구 값이 다르면 알림
- 같은 도구를 두 번 부르면 신고서 한 부에 한 장인 서식(별지3·별지15 등)은 마지막 call이 본 시트
- 별지3 확인 값은 서식 아래 표로, 109~115·119·120은 법인세 산출세액 call로
- '계산 N' 시트 수 = call 수
- 부가 별지22 2.(불공제 사유별)·5.(재계산)
- period 없음 → '~ 귀속' 대신 연도/미입력, 신고기한 뒤 개정 서식은 개정일 표기 생략
- 공통사용재화 공급이 없으면 그 시트를 만들지 않음
- 라벨 글자 깨짐(자모 분리·대체 문자) 없음
"""
import asyncio
import json
import re
import unicodedata

import openpyxl
import pytest

from korean_tax_calc_mcp import server


def run(tool, args):
    r = asyncio.run(server.mcp.call_tool(tool, args))
    raw = r.content[0].text if hasattr(r, "content") else r[0][0].text
    return json.loads(raw)


def build(tmp_path, calls, **kw):
    r = server.export_workbook(title="wb", calls=calls, output_dir=str(tmp_path), **kw)
    assert "error" not in r, r
    return r, openpyxl.load_workbook(r["결과"]["파일"])


def strings(ws):
    return [c.value for row in ws.iter_rows() for c in row if isinstance(c.value, str)]


# ── 법인세: 정액법·정률법 감가상각, 서로 입력이 다른 대손 두 call, 세무조정 합계 두 call, 산출세액 ──
DEP_SL = {"year": 2025, "method": "정액법", "useful_life": 40, "acquisition_cost": 500_000_000,
          "booked_depreciation": 10_000_000, "accumulated_dep_begin": 50_000_000, "expensed_capex": 30_000_000,
          "prior_book_value": 450_000_000, "prior_disallowed": 0}
DEP_DB = {"year": 2025, "method": "정률법", "useful_life": 8, "acquisition_cost": 100_000_000,
          "booked_depreciation": 10_000_000, "accumulated_dep_begin": 40_000_000, "expensed_capex": 0,
          "prior_book_value": 60_000_000, "prior_disallowed": 3_000_000}
BAD_DEBT = {"year": 2025, "sme": True, "prior_excess": 2_000_000,
            "book": {"opening": 10_000_000, "offset": 3_000_000, "provision": 20_000_000, "closing": 27_000_000},
            "receivables_prev_end_book": 900_000_000, "receivables_end_book": 1_000_000_000,
            "writeoffs": [{"kind": "파산", "amount": 3_000_000, "arose_in": "당기", "booked": "상계",
                           "account": "외상매출금", "detail": "거래처 A 파산"}]}
# 같은 대손충당금 한도를 다른 입력(채권잔액·실적률)으로 따로 계산한 call
BAD_DEBT_ALLOW = {"receivables": 1_200_000_000, "loss_rate": 0.012, "set_amount": 27_000_000, "prior_disallowed": 2_000_000}
ADJ_ITEMS = {"net_income": 200_000_000, "items": [
    {"항목": "법인세비용", "종류": "법인세비용", "금액": 30_000_000},
    {"항목": "건물 상각부인액", "종류": "감가상각비 한도초과", "금액": 26_750_000, "방향": "가산", "소득처분": "유보"},
    {"항목": "대손충당금 한도초과", "종류": "기타", "금액": 12_600_000, "방향": "가산", "소득처분": "유보"},
    {"항목": "전기 대손충당금 한도초과 추인", "종류": "기타", "금액": 2_000_000, "방향": "차감", "소득처분": "△유보"},
    {"항목": "기계장치 전기 상각부인액 추인", "종류": "기타", "금액": 3_000_000, "방향": "차감", "소득처분": "△유보"}]}
ADJ_SUMMARY = {"net_income": 200_000_000, "donation_excess": 4_000_000, "donation_carryover_deduction": 1_000_000,
               "items": [{"항목": "가산 합계", "종류": "기타", "금액": 69_350_000, "방향": "가산", "소득처분": "기타"},
                         {"항목": "차감 합계", "종류": "기타", "금액": 5_000_000, "방향": "차감", "소득처분": "기타"}]}
CORP = [
    {"label": "건물 감가상각", "tool": "depreciation_adjustment", "args": DEP_SL},                 # 1
    {"label": "기계장치 감가상각", "tool": "depreciation_adjustment", "args": DEP_DB},             # 2
    {"label": "이월결손금 한도율", "tool": "loss_carryforward_limit", "args": {"year": 2025, "sme": True}},  # 3
    {"label": "대손금·대손충당금", "tool": "bad_debt_adjustment", "args": BAD_DEBT},               # 4 (calls[3])
    {"label": "대손충당금 한도", "tool": "bad_debt_allowance", "args": BAD_DEBT_ALLOW},            # 5
    {"label": "항목별 세무조정", "tool": "income_adjustment_total", "args": ADJ_ITEMS},             # 6
    {"label": "각사업연도소득", "tool": "income_adjustment_total", "args": ADJ_SUMMARY},           # 7
    {"label": "산출세액", "tool": "corporate_tax", "args": {"base": 250_000_000, "year": 2025}},     # 8
]
S3, S15, S34, S50 = ("별지3 과세표준및세액조정계산서", "별지15 소득금액조정합계표", "별지34 대손충당금·대손금",
                     "별지50(을) 자본금과적립금")
SL, DB = "별지20(2) 감가상각비(정액법)", "별지20(1) 감가상각비(정률법)"


@pytest.fixture(scope="module")
def corp(tmp_path_factory):
    return build(tmp_path_factory.mktemp("corp"), CORP)


def test_straight_line_depreciation_gets_form_20_2(corp):
    """정액법 call은 별지 제20호서식(2)로 — 정률법 서식만 있던 문제."""
    _, wb = corp
    assert SL in wb.sheetnames and DB in wb.sheetnames
    ws, res = wb[SL], run("depreciation_adjustment", DEP_SL)["결과"]
    assert "별지 제20호서식(2)" in ws["A1"].value and "정액법" in ws["C2"].value
    assert ws["E7"].value == "건물 감가상각"
    assert ws["E10"].value == "=호출1_취득가액"                       # ⑤
    assert ws["E19"].value == "=E12+E15+E18"                          # ⑭ 취득가액(⑦+⑩+⑬)
    assert ws["E28"].value == "=MAX(0,E26)+E27"                       # ㉓ 상각부인액
    assert ws["I24"].value == res["상각범위액"] and ws["I28"].value == res["상각부인액"] == 26_750_000
    assert wb[DB]["E7"].value == "기계장치 감가상각"                    # 정률법 call은 그대로 (1)
    # 별지50(을)은 감가상각 시트마다 한 행, 그 시트 칸을 가리킴
    a = [wb[S50].cell(r, 1).value for r in range(8, 28)]
    assert "감가상각비 한도초과(건물 감가상각)" in a and "감가상각비 한도초과(기계장치 감가상각)" in a
    r = 8 + a.index("감가상각비 한도초과(건물 감가상각)")
    assert wb[S50][f"D{r}"].value == f"='{SL}'!E28"


def test_forms_take_values_from_the_call_that_made_them(corp):
    """별지15·별지50(을) 행은 income_adjustment_total에서 — calls[3](여기서는 대손 call)이 아니라."""
    _, wb = corp
    w15 = wb[S15]
    assert w15["A8"].value == "가산 합계" and w15["B8"].value == 69_350_000   # 본 별지15 = 마지막 세무조정 call
    w15a = wb[f"{S15} (호출 6)"]
    assert [w15a.cell(r, 1).value for r in range(8, 12)] == ["법인세비용", "건물 상각부인액", "대손충당금 한도초과", None]
    assert w15a["B9"].value == f"='{SL}'!E28"                              # 같은 금액이면 그 서식 칸을 가리킴
    # 별지50(을): 대손충당금 한도초과는 세무조정 call 금액(12,600,000) — 대손 call의 한도초과가 아님
    w50 = wb[S50]
    rows = {w50.cell(r, 1).value: (w50.cell(r, 3).value, w50.cell(r, 4).value) for r in range(8, 28)}
    # 같은 과목(대손충당금)의 유보·△유보는 한 줄 — △유보(전기 한도초과 추인)는 감소, 유보는 증가
    assert rows["대손충당금 한도초과"] == (2_000_000, 12_600_000)
    r50 = next(r for r in range(8, 28) if w50.cell(r, 1).value == "대손충당금 한도초과")
    assert w50.cell(r50, 2).value == 2_000_000                               # ②기초 = 대손 call의 전기 한도초과(prior_excess)
    assert "전기 대손충당금 한도초과 추인" not in rows
    assert "한도초과" not in rows                                            # 대손 call 세무조정의 '종류' 이름으로 섞이지 않음
    assert "기계장치 전기 상각부인액 추인" not in rows                         # 정률법 시트 행(㉗)과 겹치는 추인은 한 번만
    # 별지34는 대손 call 값 그대로, 다른 call(대손충당금 한도)과 다르면 알림
    bd = run("bad_debt_adjustment", BAD_DEBT)["결과"]["한도초과"]
    ba = run("bad_debt_allowance", BAD_DEBT_ALLOW)["결과"]["한도초과(유보)"]
    assert bd != ba and wb[S34]["N7"].value == bd
    notes = [s for s in strings(wb[S34]) if s.startswith("확인 필요")]
    assert len(notes) == 1 and f"{bd:,}" in notes[0] and f"{ba:,}" in notes[0] and "호출 5" in notes[0]
    assert any("확인 필요" in s for s in strings(wb["목록"]))


def test_same_tool_twice_main_sheet_is_last_call(corp):
    """같은 도구 두 번: 본 별지3은 마지막 call, 앞 call은 '(호출 N)' 시트."""
    r, wb = corp
    names = wb.sheetnames
    assert S3 in names and f"{S3} (호출 6)" in names and f"{S3} (2)" not in names
    ws = wb[S3]
    assert ws["F5"].value == "=호출7_당기순이익" and ws["F9"].value == "=호출7_기부금한도초과"
    assert ws["F6"].value == f"='{S15}'!B31"                                # 본 별지15(같은 call)
    last = run("income_adjustment_total", ADJ_SUMMARY)["결과"]
    vals = {ws[f"D{r}"].value: ws[f"F{r}"].value for r in range(42, 50)}
    assert vals["107 각 사업연도소득금액 (F11)"] == last["각사업연도소득금액"]
    assert wb[f"{S3} (호출 6)"]["F5"].value == "=호출6_당기순이익"
    assert any("마지막 call이 본 시트" in s for s in strings(wb["목록"]))


def test_byeolji3_checks_below_form_and_tax_lines_filled(corp):
    """확인 값이 136·139 줄 옆(N열)에 찍히지 않고, 109·112·113·115가 채워짐."""
    _, wb = corp
    ws = wb[S3]
    assert ws["N8"].value is None and ws["N11"].value is None and ws["N7"].value is None
    assert ws["A40"].value.startswith("도구 확인")
    labels = [ws[f"D{r}"].value for r in range(42, 46)]
    assert labels == ["104 차가감소득금액 (F8)", "107 각 사업연도소득금액 (F11)",
                      "112 과세표준 (법인세 산출세액 call) (F16)", "115 산출세액 (법인세 산출세액 call) (F20)"]
    ct = run("corporate_tax", {"base": 250_000_000, "year": 2025})["결과"]
    assert ws["F16"].value == "=250000000" and ws["F20"].value == f"={ct['산출세액']}"
    assert ws["F13"].value == "=F12-F14-F15-F16"                            # 109 = 108 − 110 − 111 − 112
    assert ws["F18"].value == "=F16+F17" and ws["F24"].value == "=F20+F23" and ws["F25"].value == "=F24"
    assert ws["J44"].value.startswith("=IF(ROUND(F16,0)")
    # 앞 call 시트에는 다른 call 값(과세표준)을 채우지 않음
    assert wb[f"{S3} (호출 6)"]["F16"].value is None


def test_one_calc_sheet_per_call(corp):
    """'계산 N' 시트 수 = call 수, N = calls 안 순번, 목록에 대응표."""
    _, wb = corp
    calc = [s for s in wb.sheetnames if re.fullmatch(r"계산 \d+", s)]
    assert calc == [f"계산 {i}" for i in range(1, len(CORP) + 1)]
    lst = wb["목록"]
    hdr = next(r for r in range(1, lst.max_row + 1) if lst.cell(r, 1).value == "call")
    assert [lst.cell(hdr, c).value for c in range(1, 5)] == ["call", "label", "계산 시트", "서식 시트"]
    assert lst.cell(hdr + 1, 3).value == "계산 1" and lst.cell(hdr + 1, 4).value == SL
    assert lst.cell(hdr + 8, 2).value == "산출세액" and lst.cell(hdr + 8, 3).value == "계산 8"


def test_error_call_also_gets_its_calc_sheet(tmp_path):
    _, wb = build(tmp_path, [{"label": "없음", "tool": "no_such_tool", "args": {}}, CORP[7]])
    assert [s for s in wb.sheetnames if s.startswith("계산 ")] == ["계산 1", "계산 2"]
    assert "오류" in strings(wb["계산 1"])


# ── 부가·종소: period 없이, 불공제 사유·공통매입세액·재계산·금융소득 ──
VAT_DED = {"period": "2025-2", "filing": "확정", "items": [
    {"항목": "원재료", "증빙": "세금계산서", "공급가액": 50_000_000, "성격": "일반"},
    {"항목": "면세사업 자재", "증빙": "세금계산서", "공급가액": 20_000_000, "성격": "면세사업"},
    {"항목": "거래처 선물", "증빙": "세금계산서", "공급가액": 1_000_000, "성격": "접대"},
    {"항목": "업무용 승용차", "증빙": "세금계산서", "공급가액": 25_000_000, "성격": "비영업용승용차"},
    {"항목": "사무용품", "증빙": "영수증", "공급가액": 500_000, "성격": "일반"}]}
COMMON = {"year": 2025, "period": "2기", "filing": "확정",
          "supplies": {"예정": {"taxable": 300_000_000, "exempt": 200_000_000},
                       "확정": {"taxable": 350_000_000, "exempt": 150_000_000}},
          "ledger": [{"항목": "공통 비품", "매입세액": 5_000_000, "사용처": "공통"}],
          "prior_common_input_tax": 3_000_000, "prior_nondeductible": 1_200_000}
RECALC = {"asset_type": "기타감가상각자산", "acquired": {"year": 2024, "period": 2}, "input_tax": 10_000_000,
          "ratios": [{"year": 2024, "period": 2, "exempt_ratio": 0.2}, {"year": 2025, "period": 1, "exempt_ratio": 0.22},
                     {"year": 2025, "period": 2, "exempt_ratio": 0.3}]}
FIN = {"year": 2025, "items": [{"kind": "예금이자", "amount": 9_000_000}, {"kind": "비상장법인현금배당", "amount": 15_000_000},
                               {"kind": "상장법인현금배당", "amount": 5_000_000}]}
VAT = [
    {"label": "금융소득", "tool": "financial_income_aggregate", "args": FIN},
    {"label": "매입세액 불공제", "tool": "vat_input_tax_deduction", "args": VAT_DED},
    {"label": "공통매입세액", "tool": "common_input_tax", "args": COMMON},
    {"label": "납부세액 재계산", "tool": "input_tax_recalculation", "args": RECALC},
]
V22, V63, IDIV = "부가 별지22 공제받지못할매입세액", "부가 계산근거 공통사용재화", "종소 배당·이자소득명세서"


@pytest.fixture(scope="module")
def vat(tmp_path_factory):
    return build(tmp_path_factory.mktemp("vat"), VAT)


def test_vat_22_sections_2_and_5_filled(vat):
    """2.(불공제 사유별)은 매입세액 불공제 call, 5.(재계산)은 재계산 call로."""
    _, wb = vat
    ws = wb[V22]
    assert [ws[f"{c}14"].value for c in "DEF"] == [1, 25_000_000, 2_500_000]   # ③ 승용차
    assert [ws[f"{c}15"].value for c in "DEF"] == [1, 1_000_000, 100_000]      # ④ 기업업무추진비
    assert [ws[f"{c}16"].value for c in "DEF"] == [1, 20_000_000, 2_000_000]   # ⑤ 면세사업
    assert ws["G14"].value == "업무용 승용차"
    assert ws["D12"].value in (None, "")                                        # 영수증은 세금계산서 명세가 아님
    assert ws["F20"].value == "=SUM(F12:F19)"
    rc = run("input_tax_recalculation", RECALC)
    assert ws["B40"].value == 10_000_000 and ws["D40"].value == 0.5 and ws["E40"].value == pytest.approx(0.1)
    assert ws["G40"].value == "=ROUNDDOWN(ROUND(B40*D40*E40,6),0)" and ws["G42"].value == "=SUM(G40:G41)"
    assert rc["결과"]["당기_납부세액_가산"] == 500_000
    # 4.(정산)은 영 제81조④ 정산만(작성방법 3) — 예정→확정 정산은 빈칸 두고 서식 아래 메모
    assert ws["B34"].value is None
    assert any(s.startswith("참고 — 예정신고분 확정 정산") for s in strings(ws))


def test_period_empty_header_not_blank_tilde(vat, corp):
    """period 없음 → ' ~ 귀속' 대신 'YYYY년 귀속', 법인 서식은 '사업연도 미입력'."""
    _, wb = vat
    a3 = wb[IDIV]["A3"].value
    assert a3 == "2025년 귀속 · 소득자 금융소득" and "~" not in a3
    assert corp[1][S3]["C2"].value == "사업연도 미입력" and corp[1][SL]["B2"].value == "사업연도 미입력"


def test_period_given_still_shown(tmp_path):
    _, wb = build(tmp_path, [CORP[0]], period="2025.01.01 ~ 2025.12.31")
    assert wb[SL]["B2"].value == "2025.01.01\n~\n2025.12.31"


def test_unused_common_goods_sheet_not_created(vat, tmp_path):
    """공통사용재화 공급이 없으면 '부가 계산근거 공통사용재화' 시트를 만들지 않음."""
    _, wb = vat
    assert V63 not in wb.sheetnames
    args = dict(COMMON, prior_period_supplies={"taxable": 60, "exempt": 40},
                common_asset_sales=[{"sale_price": 10_000_000, "input_tax": 0}])
    _, wb2 = build(tmp_path, [{"label": "공통사용재화", "tool": "common_input_tax", "args": args}])
    assert V63 in wb2.sheetnames


def test_revision_date_after_filing_deadline_dropped(vat, corp):
    """2025년 제2기(신고기한 2026.1.25.)에 2026.3.20. 개정 표기를 찍지 않음. 기한 전 개정은 그대로."""
    _, wb = vat
    a1 = wb[V22]["A1"].value
    assert "별지 제22호서식" in a1 and "개정" not in a1
    assert any("개정일 표기 생략" in s for s in strings(wb["목록"]))
    # 2025 사업연도 법인세(신고기한 2026.3.31.): 별지20(1) 2026.1.2.·별지20(2) 2026.3.20. 개정은 유지
    cw = corp[1]
    assert "<개정 2026. 1. 2.>" in cw[DB]["A1"].value and "<개정 2026. 3. 20.>" in cw[SL]["A1"].value


def test_labels_have_no_broken_hangul(corp, vat):
    """라벨 글자가 다른 글자로 깨져 보였다는 보고는 로컬에서 재현 안 됨 — 라벨 칸이 입력 그대로이고 자모 분리·대체 문자가 없음을 고정."""
    for _, wb in (corp, vat):
        for ws in wb:
            for s in strings(ws):
                assert "�" not in s, (ws.title, s)
                assert not re.search("[ᄀ-ᇿ]", s), (ws.title, s)        # 첫가끝 자모(분리된 한글)
                assert unicodedata.normalize("NFC", s) == s, (ws.title, s)
    cw = corp[1]
    assert cw[DB]["E7"].value == "기계장치 감가상각" and cw[SL]["E7"].value == "건물 감가상각"
    lst = cw["목록"]
    labels = [lst.cell(r, 2).value for r in range(1, lst.max_row + 1)]
    assert all(c["label"] in labels for c in CORP)
