"""도구 입력 스키마 property 키 ASCII 검사 — Anthropic Messages API 제약 ^[a-zA-Z0-9_.-]{1,64}$."""
import re
from korean_tax_calc_mcp.server import mcp

_KEY_RE = re.compile(r"^[a-zA-Z0-9_.-]{1,64}$")


def _check_property_keys(properties_dict, base_path, problems):
    """properties dict의 키들이 ^[a-zA-Z0-9_.-]{1,64}$에 맞는지 검사하고, 각 값의 서브스키마를 재귀 탐색."""
    if not isinstance(properties_dict, dict):
        return
    for pk, pv in properties_dict.items():
        if not _KEY_RE.match(pk):
            problems.append(f"{base_path}.properties.{pk}")
        # 서브스키마 안에서 다시 properties / $defs 탐색
        _scan_schema(pv, f"{base_path}.properties.{pk}", problems)


def _scan_defs(defs_dict, base_path, problems):
    """$defs 각 정의의 이름 검사 + 정의 내부 스키마의 properties/$defs 재귀 탐색."""
    if not isinstance(defs_dict, dict):
        return
    for dk, dv in defs_dict.items():
        if not _KEY_RE.match(dk):
            problems.append(f"{base_path}.$defs.{dk}")
        _scan_schema(dv, f"{base_path}.$defs.{dk}", problems)


def _scan_schema(node, path, problems):
    """JSON Schema 노드 하나 안에서 properties / $defs만 추출해 검사."""
    if not isinstance(node, dict):
        return
    props = node.get("properties")
    if isinstance(props, dict):
        _check_property_keys(props, path, problems)
    defs = node.get("$defs")
    if isinstance(defs, dict):
        _scan_defs(defs, path, problems)
    # items 등 배열 서브스키마 처리
    items = node.get("items")
    if isinstance(items, dict):
        _scan_schema(items, f"{path}.items", problems)
    # additionalProperties가 스키마일 때
    ap = node.get("additionalProperties")
    if isinstance(ap, dict):
        _scan_schema(ap, f"{path}.additionalProperties", problems)
    # prefixItems
    pitems = node.get("prefixItems")
    if isinstance(pitems, list):
        for i, it in enumerate(pitems):
            if isinstance(it, dict):
                _scan_schema(it, f"{path}.prefixItems[{i}]", problems)
    # anyOf / oneOf / allOf 내부 검사
    for comb in ("anyOf", "oneOf", "allOf"):
        coll = node.get(comb)
        if isinstance(coll, list):
            for i, sub in enumerate(coll):
                if isinstance(sub, dict):
                    _scan_schema(sub, f"{path}.{comb}[{i}]", problems)


def _walk(d, path, problems):
    """최상위 inputSchema에서 properties / $defs를 찾아 검사."""
    _scan_schema(d, path, problems)


def test_all_tool_schema_property_keys_are_ascii_compliant():
    problems: list[str] = []
    tool_count = 0
    for tool in mcp._tool_manager.list_tools():
        tool_count += 1
        schema = tool.parameters or {}
        _walk(schema, f"tools.{tool.name}.inputSchema", problems)

    assert tool_count > 0, "등록된 도구가 하나도 없음 — 스키마 검사 의미 없음"
    assert not problems, (
        "Anthropic Messages API가 거부하는 비ASCII/비정규 property 키가 있음: "
        + "; ".join(problems)
    )
