"""적격합병 자산조정계정 세무조정(법인세법 시행령 제80조의4①) — 손계산 사례.

토지: 피합병법인 세무상 장부가액 120,000,000, 시가 250,000,000, 합병법인 계상액 300,000,000
  → 자산조정계정 손금산입 130,000,000(△유보) + 시가 초과 계상 손금산입 50,000,000(△유보) = 180,000,000, 익금산입 없음.
건물(감가상각자산): 세무상 장부가액 47,500,000, 시가 40,000,000, 계상액 40,000,000 → 자산조정계정 익금산입 7,500,000(유보).
"""
from test_form_templates import c

LAND = {"자산": "토지", "세무상장부가액": 120_000_000, "시가": 250_000_000, "계상액": 300_000_000}
BLDG = {"자산": "건물", "세무상장부가액": 47_500_000, "시가": 40_000_000, "계상액": 40_000_000, "감가상각자산": True}


def test_land_booked_above_fair_value():
    r = c("qualified_merger_asset_adjustment", {"assets": [LAND]})
    adj = r["결과"]["세무조정"]
    assert [(a["구분"], a["금액"], a["소득처분"]) for a in adj] == [("손금산입", 130_000_000, "△유보"), ("손금산입", 50_000_000, "△유보")]
    assert r["결과"]["손금산입_합계"] == 180_000_000 and r["결과"]["익금산입_합계"] == 0
    assert "처분하는 사업연도" in r["계산"]["자산별"][0]["자산조정계정_후속처리"]
    assert any("따로 익금산입 줄을 내지 않았음" in w for w in r["주의"])


def test_depreciable_asset_below_tax_basis():
    r = c("qualified_merger_asset_adjustment", {"assets": [BLDG]})
    adj = r["결과"]["세무조정"]
    assert [(a["구분"], a["금액"], a["소득처분"]) for a in adj] == [("익금산입", 7_500_000, "유보")]
    assert "감가상각비" in r["계산"]["자산별"][0]["자산조정계정_후속처리"]


def test_no_difference_and_default_booked_is_fair_value():
    r = c("qualified_merger_asset_adjustment", {"assets": [{"자산": "기타자산", "세무상장부가액": 114_000_000, "시가": 114_000_000}]})
    assert r["결과"]["세무조정"] == [] and r["계산"]["자산별"][0]["계상액"] == 114_000_000


def test_booked_below_fair_value_and_input_errors():
    r = c("qualified_merger_asset_adjustment", {"assets": [dict(LAND, 계상액=120_000_000)]})
    assert [(a["구분"], a["금액"]) for a in r["결과"]["세무조정"]] == [("손금산입", 130_000_000), ("익금산입", 130_000_000)]
    assert "error" in c("qualified_merger_asset_adjustment", {"assets": [{"자산": "토지", "시가": 1}]})
    assert "error" in c("qualified_merger_asset_adjustment", {"assets": []})
