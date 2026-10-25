"""연금계좌 인출순서 분할 정답 테스트. 작성 Claude 2026-10-24 (docs/SPEC_gold_gaps6c.md)."""
import asyncio, json
from korean_tax_calc_mcp.server import mcp


def test_non_pension_part_follows_order():
    # 잔액 1억 = 과세제외 300만 + 이연퇴직 4,000만 + 그밖(6,000만 − 300만) 5,700만
    a = {"year": 2024, "birth_date": "1959-03-01", "join_date": "2012-01-15", "start_request_date": "2023-01-01",
         "balance_at_period_start": 100000000, "withdrawal": 45000000,
         "contributions_total": 60000000, "contributions_not_deducted": 3000000,
         "deferred_retirement_income": 40000000, "investment_income": 0}
    r = asyncio.run(mcp.call_tool("pension_account_withdrawal", a))
    r = json.loads((r.content[0] if hasattr(r, "content") else r[0][0]).text)
    lim = r["계산"]["연금수령한도"]
    assert lim == 30000000
    # 인출 4,500만 = 과세제외 300 + 이연퇴직 4,000 + 그밖 200 순. 앞 3,000만이 연금수령분
    assert r["결과"]["연금수령분"] == {"과세제외금액": 3000000, "이연퇴직소득": 27000000, "그밖": 0}
    assert r["결과"]["연금외수령분"] == {"과세제외금액": 0, "이연퇴직소득": 13000000, "그밖": 2000000}
    assert r["결과"]["이연퇴직_연금외수령"] == 13000000 and r["결과"]["기타소득_연금외수령"] == 2000000
