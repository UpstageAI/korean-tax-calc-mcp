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
