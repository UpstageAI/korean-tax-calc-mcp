"""조문 원문으로 손계산한 회귀 (부가령 제64조①, 소득세법 제95조③·영 제160조①, Claude 2026-11-02).

- 기계장치처럼 기준시가·감정가액이 없는 자산이 섞이면 영 제64조①2호 단서: 장부가액 안분 후
  기준시가가 있는 자산은 그 합계액을 기준시가로 재안분.
  240,000,000 × 50/60 = 200,000,000, 기계 40,000,000. 건물 200,000,000 × 15/100 = 30,000,000.
- 감정가액은 공급시기가 속하는 과세기간의 직전 과세기간 개시일부터 공급시기 과세기간 종료일까지의 것만 쓴다(1호 괄호).
  공급 2026-12-10이면 2026-01-01~2026-12-31. 2025-12-20 감정은 제외 → 기준시가.
  539,500,000(부가세 포함): 토지 150, 건물 과세 150, 건물 면세 100, 부가세 15 → 415 기준.
"""
import asyncio
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
