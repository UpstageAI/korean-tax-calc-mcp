"""테스트 공용 — mcp.call_tool을 동기로 불러 본문 JSON을 dict로 돌려준다(픽스처는 conftest.call)."""
import asyncio
import json

from korean_tax_calc_mcp.server import mcp


def call(tool: str, args: dict) -> dict:
    r = asyncio.run(mcp.call_tool(tool, args))
    return json.loads((r.content[0] if hasattr(r, "content") else r[0][0]).text)
