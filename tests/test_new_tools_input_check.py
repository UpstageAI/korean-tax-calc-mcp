"""새 계산 도구 입력 검증 — 모르는 최상위 인자 거부, 목록 안 금액 칸 bool·문자열 거부."""
import asyncio, json

import pytest

from korean_tax_calc_mcp.server import mcp

M = 1_000_000
NEW = ["inheritance_tax", "gift_tax", "dividend_received_deduction",
       "inventory_valuation_adjustment", "special_tax_credit", "asset_grant_reserve"]


def c(tool, a):
    r = asyncio.run(mcp.call_tool(tool, a))
    return json.loads((r.content[0] if hasattr(r, "content") else r[0][0]).text)


def rejected(tool, a):
    try:
        r = c(tool, a)
    except Exception:
        return True
    return isinstance(r, dict) and "error" in r


@pytest.mark.parametrize("name", NEW)
def test_new_tools_forbid_extra_top_level(name):
    model = mcp._tool_manager._tools[name].fn_metadata.arg_model
    assert model.model_config.get("extra") == "forbid"


INV = {"category": "원재료", "reported_method": "무신고", "used_method": "총평균법",
       "book_value": 4_250_000, "valuations": {"선입선출법": 4_500_000, "총평균법": 4_250_000}}


def test_inventory_top_level_prior_adjustment_rejected():
    assert rejected("inventory_valuation_adjustment",
                    {"year": 2021, "items": [INV], "prior_adjustment": "100000"})


# 전기 유보 100,000 추인(손금산입 △유보) + 당기 선입선출 4.5M − 4.25M = 익금산입 250,000 → 순 150,000
def test_inventory_item_prior_adjustment_applied():
    r = c("inventory_valuation_adjustment", {"year": 2021, "items": [{**INV, "prior_adjustment": 100_000}]})
    assert r["결과"]["순조정액"] == 150_000


BLD = {"asset": "건물", "cost": 100 * M, "depreciable": True, "depreciation_this_year": 10 * M}


@pytest.mark.parametrize("bad", [True, False, "50000000"])
def test_grant_reserve_used_must_be_amount(bad):
    r = c("asset_grant_reserve", {"year": 2021, "kind": "국고보조금", "received": 50 * M,
                                  "assets": [{**BLD, "used": bad}]})
    assert "error" in r
    assert "used" in json.dumps(r, ensure_ascii=False)


# 법 제36조·영 제64조: 설정 50M(손금산입 △유보), 상계 10M × 50/100 = 5M(익금산입 유보) → 순영향 −45M
def test_grant_reserve_correct_amount():
    r = c("asset_grant_reserve", {"year": 2021, "kind": "국고보조금", "received": 50 * M,
                                  "assets": [{**BLD, "used": 50 * M}]})
    assert r["결과"]["소득금액_순영향"] == -45 * M


def test_inventory_book_value_bool_rejected():
    assert rejected("inventory_valuation_adjustment", {"year": 2021, "items": [{**INV, "book_value": True}]})
