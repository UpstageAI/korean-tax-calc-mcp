"""테스트 공용 — mcp.call_tool을 동기로 불러 본문 JSON을 dict로 돌려준다(픽스처는 conftest.call)."""
import asyncio
import json

from korean_tax_calc_mcp.result_en import COUNT_EN, KEY_EN, VALUE_EN
from korean_tax_calc_mcp.server import mcp

_WB_TOOLS = ("export_workbook", "verify_workbook")
_KEY_KO = {v: k for k, v in KEY_EN.items()} | {v: k for k, v in COUNT_EN.items()} | {"sheet": "시트", "sheets": "시트"}
_VALUE_KO = {v: k for k, v in VALUE_EN.items()}
_KEEP = ("대조_안_한_금액_시트별", "detail", "labels_적용", "번역_없음")


def legacy_keys(r, _parent=""):
    """lang='en' 결과(0.59.1부터 영문 키·고정 문구)를 종전 국문 키로 되돌린 사본 — 0.59.0까지 쓰던 기존 테스트의 단언을 그대로 쓰기 위함.
    영문 키 자체는 tests/test_rough_outputs_1116.py가 확인한다."""
    if isinstance(r, dict):
        if _parent in _KEEP:
            return r
        out = {}
        for k, v in r.items():
            kk = _KEY_KO.get(k, k)
            out[kk] = v if kk in _KEEP else legacy_keys(v, kk)
        return out
    if isinstance(r, list):
        return [legacy_keys(v, _parent) for v in r]
    if isinstance(r, str) and _parent in ("판정", "방식", "근거", "다음", "한계", "도구_오류", "알림"):
        if " / " in r and all(p in _VALUE_KO for p in r.split(" / ")):
            return " / ".join(_VALUE_KO[p] for p in r.split(" / "))
        return _VALUE_KO.get(r, r)
    return r


def call_raw(tool: str, args: dict) -> dict:
    r = asyncio.run(mcp.call_tool(tool, args))
    return json.loads((r.content[0] if hasattr(r, "content") else r[0][0]).text)


def call(tool: str, args: dict) -> dict:
    out = call_raw(tool, args)
    if tool in _WB_TOOLS and isinstance(args, dict) and args.get("lang") == "en":
        assert "결과" not in out and "근거" not in out, "lang='en' 결과 키는 영어여야 함(0.59.1)"
        out = legacy_keys(out)
    return out
