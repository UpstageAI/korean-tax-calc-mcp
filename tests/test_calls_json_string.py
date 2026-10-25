"""export_workbook: calls·args를 JSON 문자열로 줘도 목록으로 준 것과 같은 결과."""
import asyncio
import json
from pathlib import Path

from korean_tax_calc_mcp import server as S

CALLS = json.loads((Path(__file__).parent / "data" / "workbook_forms_calls.json").read_text())


def _sheets(r):
    return r["결과"]["시트"]


def test_calls_as_json_string_same_as_list(tmp_path):
    a = S.export_workbook(title="목록", calls=CALLS, output_dir=str(tmp_path))
    b = S.export_workbook(title="문자열", calls=json.dumps(CALLS, ensure_ascii=False), output_dir=str(tmp_path))
    assert "error" not in b, b
    assert _sheets(a) == _sheets(b)
    assert b["결과"]["call_수"] == len(CALLS)
    assert Path(b["결과"]["파일"]).exists()


def test_args_as_json_string(tmp_path):
    calls = [dict(c, args=json.dumps(c["args"], ensure_ascii=False)) for c in CALLS]
    r = S.export_workbook(title="args문자열", calls=calls, output_dir=str(tmp_path))
    assert "error" not in r, r
    assert r["결과"]["오류_call"] == []


def test_bad_json_string_returns_error(tmp_path):
    r = S.export_workbook(title="깨짐", calls="[{label: 1", output_dir=str(tmp_path))
    assert "error" in r and "calls" in r["error"]


def test_json_string_not_list_returns_error(tmp_path):
    r = S.export_workbook(title="객체", calls='{"label": "x"}', output_dir=str(tmp_path))
    assert "error" in r and "calls" in r["error"]


def test_bad_args_string_only_that_call_fails(tmp_path):
    calls = [dict(CALLS[0], label="깨진 args", args="{not json")] + CALLS[1:]
    r = S.export_workbook(title="일부", calls=calls, output_dir=str(tmp_path))
    assert "error" not in r, r
    assert r["결과"]["오류_call"] == ["깨진 args"]


def test_schema_accepts_string():
    tools = asyncio.run(S.mcp.list_tools())
    t = next(t for t in tools if t.name == "export_workbook")
    sch = json.dumps(t.input_schema["properties"]["calls"], ensure_ascii=False)
    assert '"string"' in sch and '"array"' in sch
