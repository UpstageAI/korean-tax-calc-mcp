"""조문 원문으로 손계산한 회귀 (부가령 제64조①, 소득세법 제95조③·영 제160조①, Claude 2026-11-02).

- 기계장치처럼 기준시가·감정가액이 없는 자산이 섞이면 영 제64조①2호 단서: 장부가액 안분 후
  기준시가가 있는 자산은 그 합계액을 기준시가로 재안분.
  240,000,000 × 50/60 = 200,000,000, 기계 40,000,000. 건물 200,000,000 × 15/100 = 30,000,000.
- 감정가액은 공급시기가 속하는 과세기간의 직전 과세기간 개시일부터 공급시기 과세기간 종료일까지의 것만 쓴다(1호 괄호).
  공급 2026-12-10이면 2026-01-01~2026-12-31. 2025-12-20 감정은 제외 → 기준시가.
  539,500,000(부가세 포함): 토지 150, 건물 과세 150, 건물 면세 100, 부가세 15 → 415 기준.
"""
import asyncio
import openpyxl
from test_form_templates import c
from korean_tax_calc_mcp.server import mcp


def test_other_asset_without_values_uses_book_then_standard():
    r = c("bundled_supply_split", {"total_price": 240_000_000, "vat_included": False,
          "appraisal": {"building": 20_000_000, "land": 180_000_000},
          "standard_value": {"building": 15_000_000, "land": 85_000_000},
          "book_value": {"building": 10_000_000, "land": 40_000_000},
          "other_assets": [{"name": "기계장치", "book_value": 10_000_000}]})
    R = r["결과"]
    assert R["건물_공급가액"] == 30_000_000 and R["토지_가액"] == 170_000_000
    assert R["기타자산"] == [{"name": "기계장치", "공급가액": 40_000_000}]
    assert R["과세표준_합계"] == 70_000_000 and R["부가가치세"] == 7_000_000
    assert "제64조①2호" in str(r["판단"])
    assert any(x["항목"] == "감정가액 미사용" and "기계장치" in x["결론"] for x in r["판단"])


def test_other_asset_with_appraisal_uses_appraisal():
    r = c("bundled_supply_split", {"total_price": 240_000_000, "vat_included": False,
          "appraisal": {"building": 20_000_000, "land": 180_000_000},
          "standard_value": {"building": 15_000_000, "land": 85_000_000},
          "other_assets": [{"name": "기계장치", "appraisal": 40_000_000}]})
    R = r["결과"]
    assert R["건물_공급가액"] == 20_000_000 and R["토지_가액"] == 180_000_000
    assert R["기타자산"] == [{"name": "기계장치", "공급가액": 40_000_000}]


def test_appraisal_outside_window_is_ignored_and_taxable_ratio_applies():
    r = c("bundled_supply_split", {"total_price": 539_500_000, "vat_included": True,
          "appraisal": {"building": 300_000_000, "land": 160_000_000},
          "appraisal_date": "2025-12-20", "supply_date": "2026-12-10",
          "standard_value": {"building": 250_000_000, "land": 150_000_000},
          "building_taxable_ratio": 0.6})
    R = r["결과"]
    assert R["건물_공급가액"] == 195_000_000 and R["건물_면세분"] == 130_000_000
    assert R["토지_가액"] == 195_000_000 and R["부가가치세"] == 19_500_000
    assert "2026-01-01" in str(r["판단"])


def test_appraisal_inside_window_is_used():
    r = c("bundled_supply_split", {"total_price": 1_000_000_000, "vat_included": False,
          "appraisal": {"building": 300_000_000, "land": 700_000_000},
          "appraisal_date": "2026-03-01", "supply_date": "2026-12-10",
          "standard_value": {"building": 500_000_000, "land": 500_000_000}})
    assert r["결과"]["건물_공급가액"] == 300_000_000


def test_expensive_house_names_taxable_gain_as_the_gain():
    r = c("capital_gains_income", {"asset_type": "주택", "acquisition_date": "2019-04-24", "transfer_date": "2026-05-23",
          "transfer_price": 2_400_000_000, "acquisition_price": 0, "acquisition_standard_price": 1_000_000_000,
          "transfer_standard_price": 2_000_000_000, "registered": True, "one_house": True, "exempt_met": True,
          "residence_years": 5, "apply_basic_deduction": True})
    assert r["결과"]["양도차익"] == 1_170_000_000 and r["결과"]["과세대상_양도차익"] == 585_000_000
    p = [x for x in r["판단"] if x["항목"] == "고가주택 양도차익"]
    assert p and "585,000,000" in p[0]["결론"] and "1,170,000,000" in p[0]["결론"] and "제160조" in p[0]["근거"]


def _desc(name):
    ts = asyncio.run(mcp.list_tools()); ts = getattr(ts, "tools", ts)
    return next(t.description for t in ts if t.name == name)


def test_simple_allocation_tool_points_to_settlement_tool():
    assert "common_input_tax" in _desc("vat_common_input_allocation")


def test_schema_key_check_sees_inside_anyof():
    from test_tool_schema_keys import _walk
    for s in ({"properties": {"a": {"anyOf": [{"properties": {"한글": {}}}, {"type": "null"}]}}},
              {"oneOf": [{"properties": {"한글": {}}}]}, {"allOf": [{"properties": {"한글": {}}}]}):
        p = []; _walk(s, "x", p); assert len(p) == 1


# ── 1차 구현 검수에서 나온 경우 (Claude 2026-11-02, 손계산) ──
def test_vat_included_other_asset_splits_supply_value_not_gross():
    # 장부 1:1:1, 기준시가 없음: x + x + x + 0.1×(건물 x + 기계 x) = 3.2x = 3,200,000
    r = c("bundled_supply_split", {"total_price": 3_200_000, "vat_included": True,
          "book_value": {"building": 100, "land": 100}, "other_assets": [{"name": "기계", "book_value": 100}]})
    R = r["결과"]
    assert R["건물_공급가액"] == 1_000_000 and R["토지_가액"] == 1_000_000 and R["부가가치세"] == 200_000
    assert R["기타자산"] == [{"name": "기계", "공급가액": 1_000_000}]


def test_vat_included_other_asset_with_standard_reallocation():
    # 토지·건물 합계 2x를 기준시가 30:70으로 재안분: 건물 0.6x, 토지 1.4x, 기계 x, 부가세 0.16x → 3.16x = 3,160,000
    r = c("bundled_supply_split", {"total_price": 3_160_000, "vat_included": True,
          "book_value": {"building": 100, "land": 100}, "standard_value": {"building": 30, "land": 70},
          "other_assets": [{"name": "기계", "book_value": 100}]})
    R = r["결과"]
    assert R["건물_공급가액"] == 600_000 and R["토지_가액"] == 1_400_000 and R["부가가치세"] == 160_000
    assert R["기타자산"] == [{"name": "기계", "공급가액": 1_000_000}]


def test_land_building_without_appraisal_use_book_not_standard_in_first_step():
    # 기계에만 감정가 → 감정 비례 불가, 2호 단서: 장부 10:40:10 → 기계 40,000,000, 토지·건물 200,000,000을 기준시가 15:85
    r = c("bundled_supply_split", {"total_price": 240_000_000, "vat_included": False,
          "book_value": {"building": 10_000_000, "land": 40_000_000},
          "standard_value": {"building": 15_000_000, "land": 85_000_000},
          "other_assets": [{"name": "기계장치", "book_value": 10_000_000, "appraisal": 40_000_000}]})
    R = r["결과"]
    assert R["건물_공급가액"] == 30_000_000 and R["토지_가액"] == 170_000_000
    assert R["기타자산"] == [{"name": "기계장치", "공급가액": 40_000_000}]


def test_all_assets_with_standard_value_use_standard_ratio():
    # 감정 없음, 모든 자산에 기준시가 → 1호 본문: 240,000,000 × 15/200, 85/200, 100/200
    r = c("bundled_supply_split", {"total_price": 240_000_000, "vat_included": False,
          "standard_value": {"building": 15_000_000, "land": 85_000_000},
          "other_assets": [{"name": "구축물", "standard_value": 100_000_000}]})
    R = r["결과"]
    assert R["건물_공급가액"] == 18_000_000 and R["토지_가액"] == 102_000_000
    assert R["기타자산"] == [{"name": "구축물", "공급가액": 120_000_000}]


def test_standard_reallocation_includes_other_asset_having_standard():
    # 장부 10:40:10:10 → 1단위 4,000,000(합계 280,000,000). 기준시가 있는 건물·토지·구축물 합계 240,000,000을 15:85:100
    r = c("bundled_supply_split", {"total_price": 280_000_000, "vat_included": False,
          "book_value": {"building": 10_000_000, "land": 40_000_000},
          "standard_value": {"building": 15_000_000, "land": 85_000_000},
          "other_assets": [{"name": "구축물", "book_value": 10_000_000, "standard_value": 100_000_000},
                           {"name": "기계장치", "book_value": 10_000_000}]})
    R = r["결과"]
    assert R["건물_공급가액"] == 18_000_000 and R["토지_가액"] == 102_000_000
    assert R["기타자산"] == [{"name": "구축물", "공급가액": 120_000_000}, {"name": "기계장치", "공급가액": 40_000_000}]


def test_taxable_ratio_out_of_range_is_refused():
    r = c("bundled_supply_split", {"total_price": 100_000, "vat_included": False,
          "standard_value": {"building": 1, "land": 1}, "building_taxable_ratio": 1.5})
    assert "error" in r


def test_appraisal_without_dates_warns_to_check_window():
    r = c("bundled_supply_split", {"total_price": 100_000_000, "vat_included": False,
          "appraisal": {"building": 3, "land": 7}})
    assert r["결과"]["건물_공급가액"] == 30_000_000
    assert "appraisal_date" in str(r["판단"])


def test_each_judgment_item_once():
    r = c("bundled_supply_split", {"total_price": 240_000_000, "vat_included": False,
          "book_value": {"building": 10_000_000, "land": 40_000_000},
          "standard_value": {"building": 15_000_000, "land": 85_000_000},
          "other_assets": [{"name": "기계장치", "book_value": 10_000_000}]})
    names = [p["항목"] for p in r["판단"]]
    assert len(names) == len(set(names)), names


def test_form_sheet_not_used_for_new_inputs(tmp_path):
    # 부가근거64 틀은 토지·건물 전부 과세만 수식으로 맞음 → 새 입력을 쓰면 그 틀을 쓰지 않음
    from test_form_templates import build
    wb = openpyxl.load_workbook(build(tmp_path, [{"tool": "bundled_supply_split", "args": {"total_price": 240_000_000, "vat_included": False,
          "book_value": {"building": 10_000_000, "land": 40_000_000}, "standard_value": {"building": 15_000_000, "land": 85_000_000},
          "other_assets": [{"name": "기계장치", "book_value": 10_000_000}]}}]))
    assert not [n for n in wb.sheetnames if "일괄양도" in n]
