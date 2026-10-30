"""건물 기준시가 — 고시 제2025-39호(2026) 산식 손계산. 작성 Claude 2026-10-30."""
import asyncio, json
from korean_tax_calc_mcp.server import mcp


def c(a):
    r = asyncio.run(mcp.call_tool("building_standard_price", a))
    return json.loads((r.content[0] if hasattr(r, "content") else r[0][0]).text)


def test_office_2026_transfer_tax():
    # 860,000 × 1.00(철근콘크리트) × 1.15(사무소) × 1.40(공시지가 1,000만~1,500만) × 0.82(I그룹 10년) = 1,135,372 → 1,135,000 × 500㎡
    r = c({"year": 2026, "area_m2": 500, "structure": "철근콘크리트조", "use": "사무실", "land_price_per_m2": 10_000_000, "built_year": 2016})
    res = r["결과"]
    assert res["구조지수"] == 100 and res["용도지수"] == 115 and res["위치지수"] == 140 and res["잔가율"] == 0.82
    assert res["㎡당_원"] == 1_135_000 and res["기준시가_원"] == 567_500_000 and res["근사"] is False


def test_inheritance_adjustment_and_residual_floor():
    r = c({"year": 2026, "area_m2": 500, "structure": "철근콘크리트", "use": "사무실", "land_price_per_m2": 10_000_000, "built_year": 2016, "purpose": "상증세", "floors": 4})
    # 규모: 층수 4층 90 vs 연면적 500㎡ 90 → 90 → 1,135,372 × 0.9 = 1,021,834 → 1,021,000
    assert r["결과"]["조정률"] == 0.9 and r["결과"]["㎡당_원"] == 1_021_000
    r = c({"year": 2026, "area_m2": 100, "structure": "경량철골조", "use": "창고", "land_price_per_m2": 300_000, "built_year": 1990})
    # III그룹 36년 → 0.10 바닥; 860,000 × 0.79 × 0.75 × 0.93 × 0.10 = 47,386 → 47,000
    assert r["결과"]["잔가율"] == 0.1 and r["결과"]["㎡당_원"] == 47_000


def test_year_approximation_and_scope_errors():
    r = c({"year": 2024, "area_m2": 100, "structure": "철골조", "use": "공장", "land_price_per_m2": 500_000, "built_year": 2020})
    assert r["결과"]["근사"] is True and any("근사" in x["결론"] for x in r["판단"])   # 2024 기준액 830,000 × 0.95 × 0.78 × 0.97 × 0.91
    assert r["결과"]["㎡당_원"] == int(830_000 * 0.95 * 0.78 * 0.97 * 0.91 // 1000 * 1000)
    e = c({"year": 2026, "area_m2": 84, "structure": "철근콘크리트", "use": "아파트", "land_price_per_m2": 5_000_000, "built_year": 2010})
    assert e["error"] == "이 고시 대상 아님" and "공동주택가격" in e["안내"]
    e = c({"year": 2026, "area_m2": 84, "structure": "철근콘크리트", "use": "오피스텔", "land_price_per_m2": 5_000_000, "built_year": 2010})
    assert "고시" in e["안내"]
    e = c({"year": 2026, "area_m2": 84, "structure": "철근콘크리트", "use": "사무실", "built_year": 2010})
    assert "land_price_per_m2" in e["문제"][0]
