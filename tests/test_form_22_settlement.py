"""별지 제22호서식 4. 공통매입세액의 정산 명세 ⑮~⑲ (Claude 2026-11-02).

서식 원문: 부가가치세법 시행규칙 별지 제22호서식 <개정 2026. 3. 20.> 2쪽 대조. 시행령 제82조 1·2호.
손계산(신축 건물, 예정사용면적 안분 후 사용면적 확정):
- ⑮ 60,000,000, 예정 면세면적 22% → ⑱ 13,200,000.
- 확정 면세면적 350/1,000 = 35% → ⑰ 21,000,000, ⑲ = 7,800,000(납부세액 가산).
- 제82조 2호 식으로 같은 값: 60,000,000 × (1 − 35%) − 이미 공제한 46,800,000 = −7,800,000(추가 공제 없음, 가산).
"""
import openpyxl, pytest, shutil
from test_form_templates import build, c, recalc

SHEET = "부가 별지22 공제받지못할매입세액"
BLDG = {"항목": "신축 건물", "총공통매입세액": 60_000_000, "면적": {"과세": 650, "면세": 350}, "기불공제": 13_200_000}
ARGS = {"year": 2026, "period": "2기", "filing": "확정", "supplies": {}, "ledger": [], "settlements": [BLDG]}


def test_hand_calculation_area():
    r = c("common_input_tax", ARGS)
    row = r["계산"]["정산_명세"][0]
    assert row["불공제총액"] == 21_000_000 and row["기불공제"] == 13_200_000 and row["가산또는공제"] == 7_800_000
    assert row["근거"] == "제82조 2호"
    assert r["결과"]["정산_가산또는공제"] == 7_800_000 and r["결과"]["공제매입세액"] == -7_800_000
    assert "납부세액에 가산" in str(r["판단"])


def test_already_deducted_is_same_as_prior_disallowed():
    s = {k: v for k, v in BLDG.items() if k != "기불공제"} | {"이미공제세액": 46_800_000}
    assert c("common_input_tax", dict(ARGS, settlements=[s]))["결과"]["정산_가산또는공제"] == 7_800_000


def test_decrease_is_negative_and_adds_deduction():
    s = dict(BLDG, 면적={"과세": 900, "면세": 100})
    r = c("common_input_tax", dict(ARGS, settlements=[s]))
    assert r["결과"]["정산_가산또는공제"] == 6_000_000 - 13_200_000 == -7_200_000
    assert r["결과"]["공제매입세액"] == 7_200_000 and "공제(공제매입세액 증가)" in str(r["판단"])


def test_supply_basis_uses_item_1_and_truncates():
    s = {"총공통매입세액": 10_000_000, "공급가액": {"과세": 200_000_000, "면세": 100_000_000}, "기불공제": 2_000_000}
    row = c("common_input_tax", dict(ARGS, settlements=[s]))["계산"]["정산_명세"][0]
    assert row["불공제총액"] == 3_333_333 and row["가산또는공제"] == 1_333_333 and row["근거"] == "제82조 1호"


def test_ratio_has_no_float_error():
    # 0.35 × 60,000,000을 부동소수로 곱해 끝수가 어긋나지 않게 분수로 계산
    s = {"총공통매입세액": 60_000_000, "면세비율": 0.35, "기불공제": 0}
    assert c("common_input_tax", dict(ARGS, settlements=[s]))["계산"]["정산_명세"][0]["불공제총액"] == 21_000_000


def test_settlement_adds_to_ordinary_allocation():
    plain = dict(year=2026, period="2기", filing="확정", supplies={"확정": {"taxable": 700, "exempt": 300}},
                 ledger=[{"항목": "임차료", "매입세액": 1_000_000, "사용처": "공통"}])
    base = c("common_input_tax", plain)["결과"]["공제매입세액"]
    assert base == 700_000
    assert c("common_input_tax", dict(plain, settlements=[BLDG]))["결과"]["공제매입세액"] == base - 7_800_000


@pytest.mark.parametrize("bad,word", [
    ({"총공통매입세액": 1, "기불공제": 0}, "하나만"),
    ({"총공통매입세액": 1, "면세비율": 0.5, "면적": {"과세": 1, "면세": 1}, "기불공제": 0}, "하나만"),
    ({"총공통매입세액": 1, "면세비율": 1.5, "기불공제": 0}, "0~1"),
    ({"총공통매입세액": 1, "면세비율": 0.5}, "기불공제"),
    ({"총공통매입세액": 1, "면세비율": 0.5, "기불공제": 0, "이미공제세액": 1}, "기불공제"),
    ({"총공통매입세액": 1, "면적": {"과세": 0, "면세": 0}, "기불공제": 0}, "합계"),
    ({"면세비율": 0.5, "기불공제": 0}, "총공통매입세액"),
    ({"총공통매입세액": 1, "면세비율": 0.5, "기불공제": 0, "모름": 1}, "모르는 키"),
])
def test_bad_input_is_refused(bad, word):
    r = c("common_input_tax", dict(ARGS, settlements=[bad]))
    assert "error" in r and word in r["error"]


def test_only_final_return():
    assert "확정신고" in c("common_input_tax", dict(ARGS, filing="예정"))["error"]


def test_common_tax_without_supply_still_refused():
    a = dict(ARGS, ledger=[{"항목": "임차료", "매입세액": 1_000_000, "사용처": "공통"}])
    assert "안분 불가" in c("common_input_tax", a)["error"]


def test_no_settlements_keeps_result_shape():
    r = c("common_input_tax", dict(year=2026, period="2기", filing="확정", supplies={"확정": {"taxable": 700, "exempt": 300}},
                                   ledger=[{"항목": "임차료", "매입세액": 1_000_000, "사용처": "공통"}]))
    assert "서식_표" not in r and "정산_가산또는공제" not in r["결과"] and "정산_명세" not in r["계산"]


def _sheet(tmp_path, settlements):
    path = build(tmp_path, [{"tool": "common_input_tax", "args": dict(ARGS, settlements=settlements)}])
    return path, openpyxl.load_workbook(path)[SHEET]


def test_form_cells(tmp_path):
    other = {"항목": "구축물", "총공통매입세액": 10_000_000, "면세비율": 0.1, "기불공제": 2_000_000}
    _, ws = _sheet(tmp_path, [BLDG, other])
    assert ws["B34"].value == 60_000_000 and ws["F34"].value == 13_200_000 and ws["C34"].number_format == "0.00%"
    assert ws["D34"].value == "=ROUNDDOWN(ROUND(B34*C34,6),0)" and ws["G34"].value == "=D34-F34"
    assert ws["G36"].value == "=SUM(G34:G35)"


@pytest.mark.skipif(shutil.which("soffice") is None, reason="LibreOffice 필요")
def test_form_recalculates_to_tool_values(tmp_path):
    other = {"항목": "구축물", "총공통매입세액": 10_000_000, "공급가액": {"과세": 2, "면세": 1}, "기불공제": 2_000_000}
    path, _ = _sheet(tmp_path, [BLDG, other])
    ws = recalc(path, tmp_path)[SHEET]
    assert ws["D34"].value == 21_000_000 and ws["G34"].value == 7_800_000
    assert ws["D35"].value == 3_333_333 and ws["G35"].value == 1_333_333
    assert ws["B36"].value == 70_000_000 and ws["D36"].value == 24_333_333 and ws["F36"].value == 15_200_000
    assert ws["G36"].value == 9_133_333 and ws["J36"].value == "일치"


def test_more_rows_than_form_are_told_not_dropped(tmp_path):
    # 서식 정산 칸은 2행. 3건이면 조용히 빼지 않고 알림
    r = c("export_workbook", {"title": "서식", "calls": [{"tool": "common_input_tax", "args": dict(ARGS, settlements=[BLDG, BLDG, BLDG])}],
                              "output_dir": str(tmp_path)})
    assert "error" in r and "칸보다 행이 많" in r["error"] and "max_rows 2" in r["error"]


def test_no_settlement_adds_no_check_row(tmp_path):
    a = dict(year=2026, period="2기", filing="확정", supplies={"확정": {"taxable": 700, "exempt": 300}},
             ledger=[{"항목": "임차료", "매입세액": 1_000_000, "사용처": "공통"}])
    ws = openpyxl.load_workbook(build(tmp_path, [{"tool": "common_input_tax", "args": a}]))[SHEET]
    assert ws["J36"].value is None and ws["B34"].value is None and ws["G36"].value == "=SUM(G34:G35)"
