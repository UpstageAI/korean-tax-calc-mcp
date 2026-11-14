"""부가가치세 신고서(별지 제21호서식 제1쪽 신고내용) 2016~2024 과세기간 서식 판(2026-11-15, Claude).
원문(국가법령정보센터 별표·서식 PDF, 부가가치세법 시행규칙 시행본):
  <개정 2016.3.9.>(기획재정부령 제546호)·<개정 2017. 3. 10.>(제598호)·<개정 2018. 3. 19.>(제662호) — (1)~(26), (25) 가산세액계
  <개정 2019. 3. 20.>(제718호) — (25) 신용카드업자의 대리납부 기납부세액 신설, (26) 가산세액계, (27)
  <개정 2020. 4. 21.>(제793호) — (20-1) 소규모 개인사업자 부가가치세 감면세액 신설
  <개정 2021. 3. 16.>(제846호)·<개정 2022. 3. 18.>(제906호)·<개정 2023. 3. 20.>(제973호) — (23)~(25) 문구만 바뀜
  서식 개정규정은 시행 이후 신고하는 분부터(각 규칙 부칙 '서식에 관한 적용례')."""
import pathlib, shutil, subprocess
import openpyxl, pytest
from korean_tax_calc_mcp import server as S

M = 1_000_000
SHEET = "부가 별지21 신고서"
BASE = dict(period="2", kind="확정", sales_invoice=114 * M, sales_card_cash=225 * M, deemed_supply=5 * M, sales_zero_other=60 * M,
            purchase_invoice=218 * M, purchase_invoice_fixed=40 * M, import_vat_deferred=1_200_000, purchase_card_cash=30_300_000,
            nondeductible=970_000, bad_debt_credit=300_000, other_credit=10_000, card_sales_credit=2_925_000,
            prepaid_refund_pending=150_000, prepaid_assessed=700_000, prepaid_by_transferee=30_000, prepaid_buyer_special=20_000,
            penalties=[{"kind": "세금계산서 지연발급", "amount": 120_000}])
# 연도 → (머리 개정 표기, 마지막 줄 행, 마지막 줄 번호, 가산세액 계 번호, 서식에 있는 선택 칸 입력)
YEARS = {2016: ("<개정 2016.3.9.>", 34, "(26)", "(25)", {}),
         2018: ("<개정 2018. 3. 19.>", 34, "(26)", "(25)", {}),
         2019: ("<개정 2019. 3. 20.>", 35, "(27)", "(26)", {"prepaid_by_card_company": 40_000}),
         2020: ("<개정 2020. 4. 21.>", 36, "(27)", "(26)", {"prepaid_by_card_company": 40_000, "small_biz_reduction": 50_000}),
         2021: ("<개정 2021. 3. 16.>", 36, "(27)", "(26)", {"prepaid_by_card_company": 40_000, "small_biz_reduction": 50_000}),
         2024: ("<개정 2023. 3. 20.>", 36, "(27)", "(26)", {"prepaid_by_card_company": 40_000, "small_biz_reduction": 50_000})}


def _sheet(y):
    return f"{SHEET} {min(y, 2023)}판"      # 2023·2024년은 <개정 2023. 3. 20.> 판 한 틀


def _fn(t):
    return getattr(t, "fn", t)


def _export(d, args, title="v"):
    r = _fn(S.export_workbook)(title=title, calls=[{"label": "신고서", "tool": "vat_return_general", "args": args}], output_dir=str(d), company="가상㈜")
    assert r["결과"]["오류_call"] == [], r
    return r


@pytest.fixture(scope="module")
def books(tmp_path_factory):
    out = {}
    for y, (_, _, _, _, extra) in YEARS.items():
        d = tmp_path_factory.mktemp(f"vat21_{y}")
        args = {**BASE, **extra, "year": y}
        r = _export(d, args)
        assert _sheet(y) in r["결과"]["시트"] and SHEET not in r["결과"]["시트"], (y, r["결과"]["시트"])
        path = r["결과"]["파일"]
        re = None
        if shutil.which("soffice"):
            o = pathlib.Path(d) / "re"
            # 다른 LibreOffice 실행과 프로필이 겹치지 않게 이 실행만의 프로필을 쓴다
            subprocess.run(["soffice", f"-env:UserInstallation=file://{pathlib.Path(d) / 'lo_profile'}", "--headless", "--calc", "--convert-to", "xlsx",
                            "--outdir", str(o), path], check=True, capture_output=True, timeout=180)
            re = openpyxl.load_workbook(next(o.glob("*.xlsx")), data_only=True)
        out[y] = (openpyxl.load_workbook(path), re, _fn(S.vat_return_general)(**args))
    return out


@pytest.mark.parametrize("y", list(YEARS))
def test_layout_follows_that_years_form(books, y):
    rev, last, fin, pen, _ = YEARS[y]
    ws = books[y][0][_sheet(y)]
    assert rev in ws["A1"].value and f"{y}년 제2기" in ws["A3"].value
    # 매입세액 칸 번호: 그 해 서식은 (10-1) 납부유예, (15) 합계, (17) 차감계
    assert [ws[f"D{r}"].value for r in (16, 17, 18, 22, 24, 28)] == ["(10)", "(10-1)", "(11)", "(15)", "(17)", "(20)"]
    assert ws["B22"].value == "합계 (10)-(10-1)+(11)+(12)+(13)+(14)"
    assert ws[f"F{last}"].value == fin and ws[f"D{last - 1}"].value == pen and ws[f"A{last - 1}"].value == "가산세액 계"
    assert ws[f"A{last + 1}"].value is None


def test_boundary_2018_2019_card_company_line(books):
    # 2018까지: (24) 매입자 납부특례 다음이 (25) 가산세액계 / 2019부터: (25) 신용카드업자의 대리납부 기납부세액
    w18, w19 = books[2018][0][_sheet(2018)], books[2019][0][_sheet(2019)]
    assert w18["A32"].value == "매입자 납부특례 기납부세액" and w18["A33"].value == "가산세액 계"
    assert w19["A33"].value == "신용카드업자의 대리납부 기납부세액" and w19["D33"].value == "(25)"
    assert w18["G34"].value == "=G25-G28-G29-G30-G31-G32+G33" and w19["G35"].value == "=G25-G28-G29-G30-G31-G32-G33+G34"


def test_boundary_2019_2020_small_business_line(books):
    # 2019: (20) 합계 다음이 (21) 예정신고 미환급 세액 / 2020부터: (20-1) 소규모 개인사업자 부가가치세 감면세액
    w19, w20 = books[2019][0][_sheet(2019)], books[2020][0][_sheet(2020)]
    assert w19["D29"].value == "(21)" and w20["D29"].value == "(20-1)" and w20["A29"].value == "소규모 개인사업자 부가가치세 감면세액"
    assert w20["G36"].value == "=G25-G28-G29-G30-G31-G32-G33-G34+G35"


def test_boundary_2020_2021_wording(books):
    assert books[2020][0][_sheet(2020)]["A32"].value == "사업양수자의 대리납부 기납부세액"
    assert books[2021][0][_sheet(2021)]["A32"].value == "사업양수자가 대리납부한 세액"


@pytest.mark.skipif(not shutil.which("soffice"), reason="수식 재계산에 LibreOffice 필요")
@pytest.mark.parametrize("y", list(YEARS))
def test_recalculated_values_match_tool(books, y):
    _, last, _, _, _ = YEARS[y]
    _, re, r = books[y]
    ws, f = re[_sheet(y)], r["서식"]
    assert ws["G15"].value == f["(9) 합계"] and ws["G22"].value == f["(16) 합계"] and ws["G24"].value == f["(18) 차감계"]
    assert ws["G25"].value == f["납부(환급)세액"] and ws["G28"].value == f["(21) 합계"]
    assert ws[f"G{last}"].value == r["결과"]["차가감_납부세액"]
    checks = [ws.cell(row, 10).value for row in range(7, last + 1) if ws.cell(row, 10).value]
    assert checks and set(checks) == {"일치"}, checks


@pytest.mark.parametrize("y,arg,word", [(2018, "prepaid_by_card_company", "신용카드업자"), (2019, "small_biz_reduction", "소규모"), (2024, "occasional_assessed", "수시부과")])
def test_amount_on_line_missing_from_that_form_skips_sheet(tmp_path, y, arg, word):
    # 그 해 서식에 없는 칸에 금액이 있으면 서식 시트를 만들지 않고 목록에 사유
    r = _export(tmp_path, {**BASE, "year": y, arg: 10_000})
    assert not any(SHEET in n for n in r["결과"]["시트"])
    wb = openpyxl.load_workbook(r["결과"]["파일"])
    assert any(word in str(c) and "칸이 없는데" in str(c) for row in wb["목록"].iter_rows(values_only=True) for c in row if c)


def test_no_unverified_note_left():
    from korean_tax_calc_mcp.forms_workbook import load_templates
    t = load_templates()
    assert "목록_생략" not in t["부가21"]
    assert sorted(k for k in t if k.startswith("부가21_")) == [f"부가21_{y}" for y in range(2016, 2024)]


def test_mixed_years_in_one_workbook_get_separate_sheets(tmp_path):
    a = dict(period="1", kind="예정", sales_invoice=100 * M, purchase_invoice=50 * M)
    r = _fn(S.export_workbook)(title="m", output_dir=str(tmp_path), calls=[{"label": "2022", "tool": "vat_return_general", "args": {**a, "year": 2022}},
                                                                            {"label": "2025", "tool": "vat_return_general", "args": {**a, "year": 2025}}])
    assert r["결과"]["오류_call"] == [] and {SHEET, _sheet(2022)} <= set(r["결과"]["시트"])
    wb = openpyxl.load_workbook(r["결과"]["파일"])
    assert wb[_sheet(2022)]["F36"].value == "(27)" and wb[SHEET]["F37"].value == "(30)"
