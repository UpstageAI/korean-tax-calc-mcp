"""부가·증여·원천징수 도구의 법정서식 틀(export_workbook layout='forms').

calls는 실제 도구 호출 기록(tests/data/forms_vat_gift_wh_calls.json)을 그대로 쓴다. 서식 칸은 '입력·가정' 이름(호출N_…)을 가리키는
수식이고, 도구 값 대조 칸이 '일치'여야 한다(LibreOffice 재계산). 서식 라벨·번호는 국가법령정보센터 서식 PDF 원문:
부가가치세법 시행규칙 별지 제15호(2025.7.4.)·제19호(1)(2022.3.18.)·제21호(2025.7.4.)·제25호(2021.10.28.)서식,
상속세 및 증여세법 시행규칙 별지 제10호서식(2025.7.4.), 소득세법 시행규칙 별지 제23호서식(1)(2025.3.21.)·(5)(2024.12.31.)."""
import copy, json, pathlib, shutil, subprocess
import openpyxl
import pytest
from tests._helpers import call as c

DATA = json.loads((pathlib.Path(__file__).parent / "data" / "forms_vat_gift_wh_calls.json").read_text(encoding="utf-8"))
soffice = pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice 없음")

# 시트 이름
S_SUPPLY, S_CARD, S_PEN = "부가 신고서 간주공급(4)", "부가 신고서 카드발행공제(20)", "부가 신고서 가산세액명세(29)"
S_22, S_15, S_25 = "부가 별지22 공제받지못할매입세액", "부가 별지15 의제매입세액공제", "부가 별지25 부동산임대공급가액"
S_GIFT = "증여 별지10 신고및자진납부계산서"
S_NR5_P, S_NR5_C = "원천 별지23(5) 비거주자 지급명세", "원천 별지23(5) 외국법인 지급명세"
S_NR1_C, S_WH1 = "원천 별지23(1) 이자배당 외국법인", "원천 별지23(1) 이자배당 지급명세"

# 같은 기록의 둘째 증여 call은 사전 공제 구분 입력이 없어 도구가 '입력 확인 필요'로 멈춘다 — 공제 구분만 채운 call을 함께 확인
GIFT_SAME_DONOR = copy.deepcopy(DATA["gift_2"][2])
GIFT_SAME_DONOR["args"].pop("prior_deduction_used")
GIFT_SAME_DONOR["args"]["prior_deduction_same_donor"] = 50_000_000
GIFT_SAME_DONOR["label"] += "(같은 증여자 공제 구분)"
EXTRA = [
    GIFT_SAME_DONOR,
    {"label": "대손세액", "tool": "vat_bad_debt_credit", "args": {"bad_debt_incl_vat": 3_300_000}},
    {"label": "이자 원천징수", "tool": "withholding_tax", "args": {"kind": "이자", "amount": 1_234_567, "year": 2025}},
    {"label": "의제매입 예정신고", "tool": "vat_deemed_input_credit",
     "args": {"period": "2025-2", "industry": "음식점", "purchase": 54_000_000, "individual": True, "filing": "예정"}},
]


def res(call):
    return c(call["tool"], call["args"])["결과"]


def build(d, calls, name):
    r = c("export_workbook", {"title": name, "calls": calls, "output_dir": str(d), "company": "가상상사"})
    assert "결과" in r, r
    return r["결과"]["파일"]


def recalc(path, d):
    out = pathlib.Path(d) / "re"
    subprocess.run(["soffice", "--headless", "--calc", "--convert-to", "xlsx", "--outdir", str(out), path],
                   check=True, capture_output=True, timeout=180)
    return openpyxl.load_workbook(next(out.glob("*.xlsx")), data_only=True)


SETS = {"vat_1": DATA["vat_1"], "vat_2": DATA["vat_2"], "gift_1": DATA["gift_1"], "gift_2": DATA["gift_2"],
        "wh_1": DATA["wh_1"], "wh_2": DATA["wh_2"], "wh_late": DATA["wh_late"], "extra": EXTRA}


@pytest.fixture(scope="module")
def books(tmp_path_factory):
    out = {}
    for k, calls in SETS.items():
        d = tmp_path_factory.mktemp(k)
        p = build(d, calls, k)
        out[k] = (openpyxl.load_workbook(p), recalc(p, d) if shutil.which("soffice") else None)
    return out


def checks(ws):
    return [x.value for row in ws.iter_rows() for x in row if x.value in ("일치", "확인 필요")]


def raw_checks(ws):
    """도구 값 대조 칸 수식 수(재계산 없이)."""
    return [x.value for row in ws.iter_rows() for x in row if isinstance(x.value, str) and x.value.startswith("=IF(ROUND(")]


# ── 서식 시트가 생기고 '서식 틀 없음' 안내가 사라짐 ──
@pytest.mark.parametrize("k, sheets", [
    ("vat_1", [S_SUPPLY, S_CARD, S_PEN, S_22, S_15, S_25]),
    ("vat_2", [S_SUPPLY, S_CARD, S_PEN, S_22, S_15, S_25]),
    ("gift_1", [S_GIFT]), ("gift_2", [S_GIFT]),
    ("wh_1", [S_NR5_P, S_NR5_C, S_NR1_C]), ("wh_2", [S_NR5_P, S_NR5_C, S_NR1_C]),
    ("extra", [S_GIFT, "부가 별지19 대손세액공제신고서", S_WH1, "부가 별지15 의제매입세액공제(예정)"]),
])
def test_form_sheets_exist(books, k, sheets):
    raw, _ = books[k]
    for sh in sheets:
        assert sh in raw.sheetnames, (sh, raw.sheetnames)
    lst = "\n".join(str(x.value) for row in raw["목록"].iter_rows() for x in row if x.value)
    for tool in ("vat_deemed_rent", "vat_deemed_supply_items", "vat_deemed_input_credit", "vat_card_sales_credit",
                 "invoice_penalty", "vat_input_tax_deduction", "gift_tax", "nonresident_withholding"):
        assert f"서식 틀 없음 — {tool}" not in lst, (k, tool)
    assert "law.go.kr" in lst                                         # 서식 원문 출처를 목록에 적음


def test_one_sheet_collects_all_calls(books):
    """부동산임대공급가액명세서·가산세액 명세: 같은 도구 call이 한 장의 행으로(시트 하나)."""
    raw, _ = books["vat_1"]
    assert sum(sh.startswith(S_25) for sh in raw.sheetnames) == 1
    assert sum(sh.startswith(S_PEN) for sh in raw.sheetnames) == 1
    ws = raw[S_25]
    assert ws["J13"].value == "=호출3_보증금" and ws["J14"].value == "=호출4_보증금"
    assert "호출3_이자율" in ws["M13"].value and "호출3_연일수" in ws["M13"].value
    p = raw[S_PEN]
    assert "호출10_공급가액" in p["G8"].value                         # (65) 지연발급 등
    assert "호출11_공급가액" in p["G10"].value                        # (67) 미발급 등
    assert p["D8"].value == "(65)" and p["D10"].value == "(67)" and p["D26"].value == "(83)"


def test_amount_cells_are_formulas_linked_to_inputs(books):
    raw, _ = books["vat_2"]
    assert raw[S_15]["F11"].value == "=호출7_매입가액"
    assert raw[S_15]["B25"].value.startswith("=ROUNDDOWN(") and "G20" in raw[S_15]["B25"].value
    assert raw[S_CARD]["E8"].value == "=호출8_발행금액" and "호출8_연간한도" in raw[S_CARD]["G8"].value
    assert raw[S_SUPPLY]["E10"].value == "=호출3_간주공급_과세표준"
    g, _ = books["gift_2"]
    ws = g[S_GIFT]
    assert ws["D8"].value == "=호출1_증여재산가액" and ws["D25"].value == "=MAX(0,D15-SUM(D16:D24))"
    w, _ = books["wh_2"]
    assert w[S_NR5_C]["F14"].value == "=호출1_지급액" and "호출1_조약지방세포함" in w[S_NR5_C]["K14"].value
    # 원천징수 납부지연가산세: 계산 시트에 산식이 수식으로
    late, _ = books["wh_late"]
    f = [x.value for row in late["계산 1"].iter_rows() for x in row if isinstance(x.value, str) and x.value.startswith("=ROUNDDOWN(MIN(")]
    assert f and "미납세액" in f[0]


@pytest.mark.parametrize("k, sheet, cells", [
    ("vat_1", S_25, {"P12": "간주임대료"}),
    ("vat_1", S_15, {"J25": "의제매입세액"}),
    ("vat_1", S_CARD, {"I8": "공제액"}),
    ("vat_1", S_SUPPLY, {"I10": "과세표준"}),
])
def test_tool_values_in_check_cells(books, k, sheet, cells):
    """도구 값 칸에 그 call의 도구 값(재계산 없이)."""
    raw, _ = books[k]
    calls = SETS[k]
    by_tool = {}
    for call in calls:
        r = c(call["tool"], call["args"])
        if "결과" in r:
            by_tool.setdefault(call["tool"], []).append(r["결과"])
    tool = {S_25: "vat_deemed_rent", S_15: "vat_deemed_input_credit", S_CARD: "vat_card_sales_credit",
            S_SUPPLY: "vat_deemed_supply_items"}[sheet]
    for cell, key in cells.items():
        want = sum(x[key] for x in by_tool[tool]) if sheet == S_25 else by_tool[tool][-1][key]
        assert raw[sheet][cell].value == want, (cell, raw[sheet][cell].value, want)


# ── LibreOffice 재계산: 서식 칸 = 도구 값, 확인 칸 전부 '일치' ──
@soffice
@pytest.mark.parametrize("k", ["vat_1", "vat_2"])
def test_vat_forms_recalc_match_tool(books, k):
    _, wb = books[k]
    calls = SETS[k]
    by = {}
    for call in calls:
        r = c(call["tool"], call["args"])
        if "결과" in r:
            by.setdefault(call["tool"], []).append(r["결과"])
    assert wb[S_25]["M12"].value == sum(x["간주임대료"] for x in by["vat_deemed_rent"])
    assert [wb[S_25][f"M{r}"].value for r in (13, 14)] == [x["간주임대료"] for x in by["vat_deemed_rent"]]
    assert wb[S_15]["B25"].value == by["vat_deemed_input_credit"][-1]["의제매입세액"]
    assert wb[S_15]["G20"].value == min(250_000_000 * 0.6, by["vat_deemed_input_credit"][-1]["공제대상_매입가액"])
    assert wb[S_CARD]["G8"].value == by["vat_card_sales_credit"][-1]["공제액"]
    assert wb[S_SUPPLY]["E10"].value == by["vat_deemed_supply_items"][-1]["과세표준"]
    assert wb[S_PEN]["G26"].value == sum(x["가산세"] for x in by["invoice_penalty"])
    assert (wb[S_PEN]["G8"].value, wb[S_PEN]["G10"].value) == tuple(x["가산세"] for x in by["invoice_penalty"])
    assert wb[S_22]["F20"].value == by["vat_input_tax_deduction"][-1]["불공제매입세액"]
    for sh in (S_SUPPLY, S_CARD, S_PEN, S_22, S_15, S_25):
        got = checks(wb[sh])
        assert got and set(got) == {"일치"}, (sh, got)


@soffice
@pytest.mark.parametrize("k", ["gift_1", "gift_2", "extra"])
def test_gift_form_recalc_match_tool(books, k):
    _, wb = books[k]
    call = next(x for x in SETS[k] if x["tool"] == "gift_tax" and "결과" in c(x["tool"], x["args"]))
    want = res(call)
    ws = wb[S_GIFT]
    assert (ws["D15"].value, ws["D25"].value, ws["D27"].value, ws["D28"].value) == (
        want["과세가액"], want["과세표준"], want["산출세액"], want["할증세액"])
    assert (ws["I10"].value, ws["I12"].value, ws["I18"].value) == (want["기납부세액공제"], want["신고세액공제"], want["납부할세액"])
    assert sum(ws[f"D{r}"].value for r in range(16, 20)) == want["증여재산공제"]
    got = checks(ws)
    assert len(got) >= 7 and set(got) == {"일치"}, got


@soffice
def test_gift_same_donor_combined_values(books):
    """10년 내 같은 증여자 합산·인수채무·기납부세액: ㉒ 채무 3억, ㉓ 가산 1억, ㉖ 직계존속 5천만원, ㊷ 5백만원."""
    _, wb = books["extra"]
    ws = wb[S_GIFT]
    assert (ws["D13"].value, ws["D14"].value, ws["D17"].value, ws["I10"].value) == (300_000_000, 100_000_000, 50_000_000, 5_000_000)
    assert ws["D16"].value == ws["D18"].value == ws["D19"].value == 0


@soffice
@pytest.mark.parametrize("k", ["wh_1", "wh_2"])
def test_nonresident_forms_recalc_match_tool(books, k):
    raw, wb = books[k]
    calls = SETS[k]
    for i, call in enumerate(calls, 1):
        want = res(call)
        corp = call["args"]["recipient_type"] == "법인"
        div = call["args"]["income_kind"] in ("이자", "배당")
        # 이 call이 만든 시트(같은 틀 둘째부터 ' (2)'): 지급액 칸이 '=호출i_지급액'인 시트
        cell = "N17" if div else "F14"
        sh = next(s for s in raw.sheetnames if s.startswith("원천 ") and raw[s][cell].value == f"=호출{i}_지급액")
        ws = wb[sh]
        if div:
            tax, local, total = ws["Q17" if corp else "P17"].value, ws["R17"].value, ws["T17"].value
        else:
            tax, local, total = ws["K14" if corp else "J14"].value, ws["L14"].value, ws["N14"].value
        assert (tax, local, total) == (want["원천징수세액"], want["지방소득세"], want["합계"]), (sh, call["label"])
        got = checks(ws)
        assert len(got) == 3 and set(got) == {"일치"}, (sh, got)


@soffice
def test_withholding_late_penalty_calc_sheet_recalc(books):
    raw, wb = books["wh_late"]
    for i, call in enumerate(SETS["wh_late"], 1):
        got = checks(wb[f"계산 {i}"])
        assert len(got) == 4 and set(got) == {"일치"}, (call["label"], got)
        want = res(call)["가산세"]
        rows = {wb[f"계산 {i}"][f"A{r}"].value: wb[f"계산 {i}"][f"B{r}"].value for r in range(1, 30)}
        assert rows["가산세"] == want


@soffice
def test_extra_forms_recalc(books):
    _, wb = books["extra"]
    assert wb["부가 별지19 대손세액공제신고서"]["E12"].value == 300_000
    assert wb[S_WH1]["P17"].value == res(EXTRA[2])["원천징수세액"]
    assert wb["부가 별지15 의제매입세액공제(예정)"]["H11"].value == res(EXTRA[3])["의제매입세액"]
    for sh in ("부가 별지19 대손세액공제신고서", S_WH1, "부가 별지15 의제매입세액공제(예정)"):
        got = checks(wb[sh])
        assert got and set(got) == {"일치"}, (sh, got)


def test_check_formulas_present_without_recalc(books):
    """재계산 없이도 대조 칸 수식이 서식 시트마다 있음."""
    for k, sheets in (("vat_1", [S_SUPPLY, S_CARD, S_PEN, S_22, S_15, S_25]), ("gift_2", [S_GIFT]),
                      ("wh_2", [S_NR5_P, S_NR5_C, S_NR1_C])):
        raw, _ = books[k]
        for sh in sheets:
            assert raw_checks(raw[sh]), (k, sh)


def test_form_header_revision_and_labels(books):
    """서식 머리 번호·개정일과 줄 번호는 원문 그대로."""
    raw, _ = books["vat_1"]
    assert raw[S_15]["A1"].value == "[별지 제15호서식] <개정 2025. 7. 4.>"
    assert raw[S_25]["A1"].value == "■ 부가가치세법 시행규칙 [별지 제25호서식] <개정 2021. 10. 28.>"
    assert raw[S_PEN]["A1"].value == "■ 부가가치세법 시행규칙 [별지 제21호서식] <개정 2025. 7. 4.>"
    assert raw[S_15]["G23"].value.startswith("㉖ 공제(납부)할 세액") and raw[S_15]["B24"].value == "㉒ 공제대상세액"
    assert raw[S_PEN]["C8"].value == "지연발급 등" and raw[S_PEN]["C10"].value == "미발급 등"
    assert raw[S_25]["M10"].value.startswith("⑰") and "이자(계)" in raw[S_25]["M10"].value
    assert "2025년 제2기" in raw[S_25]["A3"].value
    g, _ = books["gift_2"]
    assert g[S_GIFT]["A1"].value == "■ 상속세 및 증여세법 시행규칙 [별지 제10호서식] <개정 2025. 7. 4.>"
    assert g[S_GIFT]["A25"].value.startswith("㉞ 과세표준") and g[S_GIFT]["F18"].value.startswith("㊿ 자진납부할 세액")
    w, _ = books["wh_2"]
    assert w[S_NR5_C]["A1"].value == "■ 소득세법 시행규칙 [별지 제23호서식(5)] <개정 2024. 12. 31.>"
    assert w[S_NR5_C]["D11"].value == "61"                            # ⑨ 소득구분코드 — 사용료소득
    assert w[S_NR1_C]["A1"].value == "■ 소득세법 시행규칙 [별지 제23호서식(1)] <개정 2025. 3. 21.>"
