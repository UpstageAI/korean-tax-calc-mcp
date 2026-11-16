"""모든 도구에 읽기 전용·외부 호출 표시가 있고, 파일을 저장하는 도구는 읽기 전용이 아니어야 한다."""
import asyncio

from korean_tax_calc_mcp.server import mcp

WRITES_FILE = {"export_workbook", "verify_workbook"}
OPEN_WORLD = {
    "stock_price_lookup", "official_property_price",          # 시세·공시가격 조회
    "related_judge", "related_provision_at",                  # LAW_OC가 있으면 법제처 조회
    "extract_relations", "tunnelling_from_pdf", "return_precheck_pdf",  # UPSTAGE_API_KEY가 있으면 문서 추출 API
    "kr_comparable_candidates",                               # OpenDART 공시(본인 키) + 선택 Upstage 분류
}


def _tools():
    return asyncio.run(mcp.list_tools())


def _hint(a, snake, camel):
    """mcp 버전에 따라 속성 이름이 다르다(read_only_hint / readOnlyHint)."""
    return getattr(a, snake) if hasattr(a, snake) else getattr(a, camel)


def _ro(a):
    return _hint(a, "read_only_hint", "readOnlyHint")


def _open(a):
    return _hint(a, "open_world_hint", "openWorldHint")


def _destructive(a):
    return _hint(a, "destructive_hint", "destructiveHint")


def test_every_tool_has_annotations():
    missing = [t.name for t in _tools() if t.annotations is None or _ro(t.annotations) is None
               or _open(t.annotations) is None]
    assert missing == []


def test_file_writing_tools_are_not_read_only():
    by = {t.name: t.annotations for t in _tools()}
    for name in WRITES_FILE:
        assert _ro(by[name]) is False, name
        assert _destructive(by[name]) is False, name
    others = [n for n, a in by.items() if n not in WRITES_FILE and _ro(a) is not True]
    assert others == []


def test_open_world_tools():
    got = {t.name for t in _tools() if _open(t.annotations)}
    assert got == OPEN_WORLD
