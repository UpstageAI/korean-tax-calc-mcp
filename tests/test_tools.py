import asyncio, json
from korean_tax_calc_mcp.server import mcp


def c(n, a): return json.loads(asyncio.run(mcp.call_tool(n, a)).content[0].text)


def test_tools_and_values():
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert {"corporate_tax", "deemed_interest", "invoice_penalty", "assessment_limitation", "withholding_tax"} <= names
    assert c("corporate_tax", {"base": 500_000_000, "year": 2025})["결과"]["산출세액"] == 75_000_000
    assert c("deemed_interest", {"movements": [{"date": "2025-01-01", "amount": 240_000_000}], "year_end": "2025-12-31"})["결과"]["익금산입"] == 11_040_000
    assert c("invoice_penalty", {"supply_amount": 40_000_000, "kind": "가공", "supplied_on": "2025-12-15"})["결과"]["가산세"] == 1_200_000
    r = c("assessment_limitation", {"due_date": "2024-03-31", "case": "부정행위", "offshore": True})["결과"]
    assert r["제척기간(년)"] == 15 and r["만료일"] == "2039-03-31"
    assert c("assessment_limitation", {"due_date": "2024-03-31", "case": "무신고"})["결과"]["제척기간(년)"] == 7
    assert c("underreporting_penalty", {"additional_tax": 10_000_000, "fraud": True})["결과"]["가산세"] == 4_000_000


def test_no_year_table_stops():
    assert "error" in c("corporate_tax", {"base": 1, "year": 2026}) or "결과" in c("corporate_tax", {"base": 1, "year": 2026})


def test_v02_tools():
    assert c("nonbusiness_interest_disallowance", {"loans": [{"interest": 30_000_000, "jeoksu": 3_650_000_000}], "nonbusiness_jeoksu": 876_000_000})["결과"]["손금불산입(기타사외유출)"] == 7_200_000
    r = c("business_car_expense", {"year": 2025, "upkeep": 20_000_000, "depreciation": 8_000_000, "booked_depreciation": 8_000_000, "log_kept": False})["결과"]
    assert round(r["업무사용비율"], 4) == round(15_000_000 / 28_000_000, 4)
    assert c("donation_limit", {"year": 2025, "base_income": 500_000_000, "special": 10_000_000, "general": 80_000_000})["결과"]["한도초과(기타사외유출)"] == 31_000_000
    assert c("vat_deemed_input_credit", {"purchase": 50_000_000, "base": 300_000_000, "period": "2025-1", "industry": "음식점", "individual": False})["결과"]["의제매입세액"] == 2_830_188
    items = [{"amount": 50_000}, {"amount": 20_000}, {"amount": 300_000, "congratulatory": True}, {"amount": 100_000, "qualified": True}]
    assert c("missing_receipt_disallowance", {"year": 2025, "items": items})["결과"]["손금불산입"] == 350_000
    assert c("vat_common_input_allocation", {"common_tax": 10_000_000, "total_supply": 1_000_000_000, "exempt_supply": 300_000_000})["결과"]["불공제"] == 3_000_000
    assert c("daily_worker_withholding", {"daily_wage": 200_000})["결과"]["원천징수세액"] == 1_350
