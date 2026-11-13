"""0.43.0 부가가치세 신고서 본표(별지 제21호서식 제1쪽 ① 신고내용) 서식 틀(2026-11-13, Claude).
원문: 부가가치세법 시행규칙 별지 제21호서식 <개정 2025. 7. 4.>(2026.1.2. 시행본 PDF 제1쪽)·<개정 2026. 3. 20.> 제1쪽 — (1)~(30) 칸 배치 같음."""
import pathlib, shutil, subprocess
import openpyxl, pytest
from korean_tax_calc_mcp import server as S

M = 1_000_000
SHEET = "부가 별지21 신고서"
ARGS = dict(year=2025, period="2", kind="확정", sales_invoice=114 * M, sales_card_cash=225 * M, deemed_supply=5 * M, sales_zero_other=5_060_690_000,
            purchase_invoice=2_018 * M, purchase_card_cash=30_300_000, nondeductible=970_000, bad_debt_credit=300_000, e_filing=True,
            penalties=[{"kind": "세금계산서 지연발급", "amount": 120_000}])


def _fn(t):
    return getattr(t, "fn", t)


@pytest.fixture(scope="module")
def book(tmp_path_factory):
    d = tmp_path_factory.mktemp("vat21")
    r = _fn(S.export_workbook)(title="v", calls=[{"label": "신고서", "tool": "vat_return_general", "args": ARGS}], output_dir=str(d), company="가상㈜")
    assert r["결과"]["오류_call"] == [] and SHEET in r["결과"]["시트"], r
    path = r["결과"]["파일"]
    re = None
    if shutil.which("soffice"):
        out = pathlib.Path(d) / "re"
        subprocess.run(["soffice", "--headless", "--calc", "--convert-to", "xlsx", "--outdir", str(out), path], check=True, capture_output=True, timeout=180)
        re = openpyxl.load_workbook(next(out.glob("*.xlsx")), data_only=True)
    return openpyxl.load_workbook(path), re, _fn(S.vat_return_general)(**ARGS)


def test_form_layout_follows_original(book):
    raw, _, _ = book
    ws = raw[SHEET]
    # 2025년 2기 신고기한(2026.1.26.)은 2026.3.20. 개정 전 — 머리의 개정일 표기는 빼고 목록에 사유
    assert "별지 제21호서식" in ws["A1"].value and "2026. 3. 20." not in ws["A1"].value and "2025년 제2기" in ws["A3"].value
    for cell, no, name in (("D7", "(1)", "세금계산서 발급분"), ("D10", "(4)", "기타(정규영수증 외 매출분)"), ("D15", "(9)", "합계"), ("D16", "(10)", "일반매입"),
                           ("D21", "(15)", "그 밖의 공제매입세액"), ("D24", "(18)", "차감계 (16)-(17)"), ("D28", "(21)", "합계"), ("D36", "(29)", "가산세액 계")):
        assert ws[cell].value == no
        assert name in [ws.cell(ws[cell].row, c).value for c in (1, 2, 3)]
    assert ws["F37"].value == "(30)" and ws["F25"].value == "㉰"
    assert ws["E7"].value == "=호출1_과세_세금계산서_발급분" and ws["G7"].value == "=INT(E7*10/100)"       # 금액은 입력 이름, 세액은 수식
    assert ws["G37"].value == "=G25-G28-G29-G30-G31-G32-G33-G34-G35+G36"


def test_inputs_named(book):
    _, _, r = book
    names = {x["이름"]: x["값"] for x in r["계산식_입력"]}
    assert names["과세_세금계산서_발급분"] == 114 * M and names["과세_기타"] == 5 * M and names["영세율_기타"] == 5_060_690_000
    assert names["일반매입_세액"] == 201_800_000 and names["그밖의_공제매입세액"] == 3_030_000 and names["공제받지못할_매입세액"] == 970_000
    assert names["가산세액_계"] == 120_000 and names["과세연도"] == 2025


@pytest.mark.skipif(not shutil.which("soffice"), reason="수식 재계산에 LibreOffice 필요")
def test_recalculated_values_match_tool(book):
    _, re, r = book
    ws, f = re[SHEET], r["서식"]
    assert ws["G15"].value == f["(9) 합계"] and ws["G22"].value == f["(16) 합계"] and ws["G24"].value == f["(18) 차감계"]
    assert ws["G25"].value == f["납부(환급)세액"] and ws["G28"].value == f["(21) 합계"]
    assert ws["G37"].value == f["(30) 차감ㆍ가감하여 납부할 세액(환급받을 세액)"] == r["결과"]["차가감_납부세액"]
    checks = [ws.cell(row, 10).value for row in range(7, 38) if ws.cell(row, 10).value]
    assert checks and set(checks) == {"일치"}, checks


def test_old_years_have_no_form_sheet(tmp_path):
    r = _fn(S.export_workbook)(title="o", calls=[{"label": "신고서", "tool": "vat_return_general", "args": {**ARGS, "year": 2023, "penalties": []}}], output_dir=str(tmp_path))
    assert r["결과"]["오류_call"] == [] and SHEET not in r["결과"]["시트"]
    wb = openpyxl.load_workbook(r["결과"]["파일"])
    assert any("2024년 이전" in str(c) for row in wb["목록"].iter_rows(values_only=True) for c in row if c)


def test_negative_amounts_are_rejected_by_tool():
    # 금액 칸은 음수를 받지 않음(환입은 차감한 금액으로 입력) — 서식 세액 수식(INT)과 도구 내림(//)이 갈릴 입력이 없음
    r = _fn(S.vat_return_general)(**{**ARGS, "sales_invoice": -1_000_005, "penalties": []})
    assert "error" in r


def test_2026_period_keeps_revision_mark(tmp_path):
    r = _fn(S.export_workbook)(title="y", calls=[{"label": "신고서", "tool": "vat_return_general", "args": {**ARGS, "year": 2026, "period": "1", "penalties": []}}], output_dir=str(tmp_path))
    ws = openpyxl.load_workbook(r["결과"]["파일"])[SHEET]
    assert "<개정 2026. 3. 20.>" in ws["A1"].value and "2026년 제1기" in ws["A3"].value
