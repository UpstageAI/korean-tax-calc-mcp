"""연금계좌 날짜 순서 검증 정답 테스트. 작성 Claude 2026-10-24 (docs/SPEC_gold_gaps6b.md)."""
import asyncio, json
from korean_tax_calc_mcp.server import mcp


def c(tool, a):
    r = asyncio.run(mcp.call_tool(tool, a))
    return json.loads((r.content[0] if hasattr(r, "content") else r[0][0]).text)


BASE = {"year": 2025, "birth_date": "1960-01-01", "join_date": "2010-01-01", "start_request_date": "2024-01-01",
        "balance_at_period_start": 100000000, "withdrawal": 10000000, "contributions_total": 50000000, "contributions_not_deducted": 0}


def test_date_order_checked():
    for bad in ({"join_date": "2030-01-01"}, {"birth_date": "2015-01-01"}):
        r = c("pension_account_withdrawal", {**BASE, **bad})
        assert r.get("error", "").startswith("입력 확인 필요") and any("join_date" in p for p in r["문제"]), r
