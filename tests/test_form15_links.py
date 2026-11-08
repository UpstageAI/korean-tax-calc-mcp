"""별지15 가산 행 금액 = 그 조정을 계산한 서식 칸 참조 (Claude 2026-11-08, 0.22.1).

배경: 과목 이름을 자유롭게 적은 세무조정 항목(예: "업무용승용차 업무외사용금액(유지비)")은 slot adjustment 이름과 달라
별지15에 숫자로 박혔다. 같은 계정 묶음의 adjustment 칸 중 도구 값이 금액과 같은 칸이 하나뿐이면 그 칸을 가리킨다.
기업업무추진비 적격증빙 미수취는 별지23(갑) ②를 가리킨다. 입력 사실(법인세비용·비지정기부금)은 숫자 그대로.
"""
import shutil
import openpyxl, pytest
from test_form_templates import build, recalc

S15, S23, S29 = "별지15 소득금액조정합계표", "별지23(갑) 기업업무추진비", "별지29 업무용승용차"
LEDGER = [{"항목": "법인카드 사용분", "금액": 46_447_000, "증빙": "적격"},
          {"항목": "경조금", "금액": 300_000, "증빙": "영수증 등", "성격": "경조금", "건당기준초과": False},
          {"항목": "간이영수증 3건", "금액": 1_200_000, "증빙": "영수증 등", "건당기준초과": True},
          {"항목": "간이영수증 소액", "금액": 53_000, "증빙": "영수증 등", "건당기준초과": False}]
CALLS = [
    {"label": "기업업무추진비", "tool": "entertainment_adjustment",
     "args": {"year": 2025, "sme": True, "ledger": LEDGER, "revenue": {"매출액": 8_500_000_000}}},
    {"label": "승용차", "tool": "business_car_expense",
     "args": {"year": 2025, "upkeep": 12_000_000, "depreciation": 18_000_000, "booked_depreciation": 18_000_000,
              "log_kept": False, "acquisition_cost": 90_000_000}},
    {"label": "소득금액 집계", "tool": "income_adjustment_total",
     "args": {"net_income": 320_000_000, "items": [
         {"항목": "법인세비용", "종류": "법인세비용", "금액": 40_000_000},
         {"항목": "기업업무추진비 적격증빙 미수취(간이영수증 3건)", "종류": "기업업무추진비 적격증빙 미수취", "금액": 1_200_000},
         {"항목": "업무용승용차 업무외사용금액(유지비)", "금액": 6_000_000, "조정": "손금불산입", "소득처분": "상여"},
         {"항목": "업무용승용차 업무외사용금액(감가상각비)", "금액": 9_000_000, "조정": "손금불산입", "소득처분": "상여"},
         {"항목": "업무용승용차 감가상각비 800만원 한도초과", "금액": 1_000_000, "조정": "손금불산입", "소득처분": "유보"},
         {"항목": "비지정기부금(향우회 찬조금)", "종류": "비지정기부금", "금액": 500_000}]}},
]


@pytest.fixture(scope="module")
def book(tmp_path_factory):
    d = tmp_path_factory.mktemp("f15")
    return build(d, CALLS), d


def test_rows_point_to_form_cells(book):
    path, _ = book
    ws = openpyxl.load_workbook(path)[S15]
    rows = {ws.cell(r, 1).value: ws.cell(r, 2).value for r in range(8, 15) if ws.cell(r, 1).value}
    assert rows["법인세비용"] == 40_000_000 and rows["비지정기부금(향우회 찬조금)"] == 500_000   # 입력 사실
    assert str(rows["기업업무추진비 적격증빙 미수취(간이영수증 3건)"]).startswith(f"='{S23}'!")
    for k in ("업무용승용차 업무외사용금액(유지비)", "업무용승용차 업무외사용금액(감가상각비)", "업무용승용차 감가상각비 800만원 한도초과"):
        assert str(rows[k]).startswith(f"='{S29}'!"), (k, rows[k])
    linked = [v for v in rows.values() if isinstance(v, str)]
    assert len(set(linked)) == len(linked)                                       # 한 칸을 두 행이 가리키지 않음


@pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice 없음")
def test_linked_values_unchanged(book):
    path, d = book
    ws = recalc(path, d)[S15]
    vals = {ws.cell(r, 1).value: ws.cell(r, 2).value for r in range(8, 15) if ws.cell(r, 1).value}
    assert vals == {"법인세비용": 40_000_000, "기업업무추진비 적격증빙 미수취(간이영수증 3건)": 1_200_000,
                    "업무용승용차 업무외사용금액(유지비)": 6_000_000, "업무용승용차 업무외사용금액(감가상각비)": 9_000_000,
                    "업무용승용차 감가상각비 800만원 한도초과": 1_000_000, "비지정기부금(향우회 찬조금)": 500_000}
    assert ws["B31"].value == 57_700_000
