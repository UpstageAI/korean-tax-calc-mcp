"""엑셀 내보내기 검수 반영 정답 테스트. 작성 Claude 2026-10-24 (docs/SPEC_export_workbook_b.md)."""
import asyncio, json, re
import openpyxl
from korean_tax_calc_mcp.server import mcp


def c(tool, a):
    r = asyncio.run(mcp.call_tool(tool, a))
    return json.loads((r.content[0] if hasattr(r, "content") else r[0][0]).text)


ENT = {"year": 2025, "sme": True, "ledger": [{"항목": "일반", "금액": 95000000, "증빙": "적격"}],
       "revenue": {"매출액": 18000000000}}
ADJ = {"net_income": 100000000, "items": [{"항목": "법인세", "종류": "법인세비용", "금액": 8000000},
                                          {"항목": "환급금 이자", "종류": "환급금이자", "금액": 2000000}]}


def rows(ws):
    return [[v for v in r] for r in ws.iter_rows(values_only=True)]


def cells(ws):
    return [v for r in ws.iter_rows(values_only=True) for v in r if v is not None]


def build(tmp_path, calls):
    r = c("export_workbook", {"title": "검수", "calls": calls, "output_dir": str(tmp_path)})
    return r, openpyxl.load_workbook(r["결과"]["파일"])


def test_each_calc_sheet_uses_its_own_calc_dict(tmp_path):
    _, wb = build(tmp_path, [{"label": "접대비", "tool": "entertainment_adjustment", "args": ENT},
                             {"label": "차가감", "tool": "income_adjustment_total", "args": ADJ}])
    s1 = cells(wb["계산 1"])
    assert "기본한도" in s1 and "시부인 대상" in s1  # 접대비 call의 계산 dict


def test_direction_column_and_sumif_by_direction(tmp_path):
    adj = c("income_adjustment_total", ADJ)["결과"]["세무조정"]
    assert {e["구분"]: e["조정"] for e in adj} == {"법인세": "익금산입", "환급금 이자": "손금산입"}
    _, wb = build(tmp_path, [{"label": "차가감", "tool": "income_adjustment_total", "args": ADJ}])
    rs = rows(wb["계산 1"])
    hdr = next(r for r in rs if "구분" in r and "조정" in r)
    i_c, i_j = hdr.index("구분"), hdr.index("조정")
    dirs = {r[i_c]: r[i_j] for r in rs if r[i_c] in ("법인세", "환급금 이자")}
    assert dirs == {"법인세": "가산", "환급금 이자": "차감"}
    fs = [v for v in cells(wb["계산 1"]) if isinstance(v, str) and v.startswith("=")]
    assert any("SUMIF(" in f.upper() and '"가산"' in f for f in fs)
    assert any("SUMIF(" in f.upper() and '"차감"' in f for f in fs)


def test_check_cells_compare_numbers_not_strings(tmp_path):
    _, wb = build(tmp_path, [{"label": "접대비", "tool": "entertainment_adjustment", "args": ENT},
                             {"label": "차가감", "tool": "income_adjustment_total", "args": ADJ}])
    fs = [v for s in ("계산 1", "계산 2") for v in cells(wb[s]) if isinstance(v, str) and v.upper().startswith("=IF(")]
    assert fs and not any(re.search(r'="\d', f) for f in fs)
    assert any(re.search(r"=13000000\b", f) for f in fs)   # 접대비 손금불산입_합계
    assert any(re.search(r"=8000000\b", f) for f in fs) and any(re.search(r"=2000000\b", f) for f in fs)


def test_unknown_tool_is_recorded_and_others_continue(tmp_path):
    r, wb = build(tmp_path, [{"label": "없는도구", "tool": "no_such_tool", "args": {}},
                             {"label": "차가감", "tool": "income_adjustment_total", "args": ADJ}])
    assert r["결과"]["오류_call"] == ["없는도구"]
    assert any(s.startswith("계산") for s in wb.sheetnames)
    assert 108000000 in cells(wb["계산 1"])
    assert any(isinstance(v, str) and "no_such_tool" in v for v in cells(wb["요약"]))
