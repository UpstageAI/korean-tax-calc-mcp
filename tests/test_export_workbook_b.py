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
    assert 106000000 in cells(wb["계산 1"])  # 100 + 8 − 2
    assert any(isinstance(v, str) and "no_such_tool" in v for v in cells(wb["요약"]))


# ── 수식을 직접 계산해 값까지 확인(엑셀 없이) ──
_REF = re.compile(r"^([A-Z]+)(\d+)$")


def _col(letters):
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n


def _range(ws, a):
    (c1, r1), (c2, r2) = [_REF.match(x).groups() for x in a.split(":")]
    return [ws.cell(r, c).value for r in range(int(r1), int(r2) + 1) for c in range(_col(c1), _col(c2) + 1)]


def _val(ws, ref):
    c, r = _REF.match(ref).groups()
    return _eval(ws, ws.cell(int(r), _col(c)).value)


def _eval(ws, v):
    if not (isinstance(v, str) and v.startswith("=")):
        return v
    f = v[1:]
    m = re.fullmatch(r"SUM\(([A-Z]+\d+:[A-Z]+\d+)\)", f, re.I)
    if m:
        return sum(x for x in _range(ws, m.group(1)) if isinstance(x, (int, float)))
    m = re.fullmatch(r'SUMIF\(([A-Z]+\d+:[A-Z]+\d+),"([^"]*)",([A-Z]+\d+:[A-Z]+\d+)\)', f, re.I)
    if m:
        crit, vals = _range(ws, m.group(1)), _range(ws, m.group(3))
        return sum(x for k, x in zip(crit, vals) if k == m.group(2) and isinstance(x, (int, float)))
    m = re.fullmatch(r"([A-Z]+\d+)-([A-Z]+\d+)", f)
    if m:
        return _val(ws, m.group(1)) - _val(ws, m.group(2))
    m = re.fullmatch(r'IF\(([A-Z]+\d+)=(-?[\d.]+),"([^"]*)","([^"]*)"\)', f, re.I)
    if m:
        return m.group(3) if _val(ws, m.group(1)) == float(m.group(2)) else m.group(4)
    raise AssertionError(f"해석 못 하는 수식: {v}")


def _labelled(ws):
    """A열 라벨 → 같은 행에서 처음 나오는 수식의 계산값."""
    out = {}
    for row in ws.iter_rows():
        lab = row[0].value
        f = next((c for c in row[1:] if isinstance(c.value, str) and c.value.startswith("=")), None)
        if isinstance(lab, str) and f is not None:
            out[lab] = _eval(ws, f.value)
    return out


def test_formulas_evaluate_to_tool_values(tmp_path):
    _, wb = build(tmp_path, [{"label": "접대비", "tool": "entertainment_adjustment", "args": ENT},
                             {"label": "차가감", "tool": "income_adjustment_total", "args": ADJ}])
    e, a = _labelled(wb["계산 1"]), _labelled(wb["계산 2"])
    assert a["가산 합계"] == 8000000 and a["차감 합계"] == 2000000 and a["순액"] == 6000000
    checks = [v for d in (e, a) for k, v in d.items() if k.startswith("확인")]
    assert len(checks) >= 3 and all(v == "일치" for v in checks)
    assert e["가산 합계"] == 13000000


DEMO_CALLS = json.loads('[{"label": "기업업무추진비", "tool": "entertainment_adjustment", "args": {"year": 2025, "sme": true, "ledger": [{"항목": "일반 접대비", "금액": 52000000, "증빙": "적격"}, {"항목": "체육활동 입장권", "금액": 20000000, "증빙": "적격", "성격": "문화"}, {"항목": "직원단체(법인) 복리시설비", "금액": 4000000, "증빙": "적격", "성격": "직원단체_법인"}, {"항목": "거래처 증정 제품", "금액": 9000000, "증빙": "적격", "성격": "현물", "시가": 10000000, "장부가액": 8000000}], "revenue": {"매출액": 15000000000, "특수관계매출": 3000000000}}}, {"label": "기계장치 감가상각", "tool": "depreciation_adjustment", "args": {"year": 2025, "method": "무신고", "asset_class": "건축물외_유형자산", "acquisition_cost": 100000000, "booked_depreciation": 15000000, "accumulated_dep_begin": 72500000, "rate": 0.3, "expensed_capex": 1000000, "prior_book_value": 27500000, "prior_disallowed": 4000000}}, {"label": "수입배당금", "tool": "dividend_received_deduction", "args": {"year": 2025, "investees": [{"name": "B", "listed": false, "ratio": 0.4, "dividend": 15000000, "book_value_jeoksu": 219000000000}], "interest_paid": 30000000, "interest_excluded": 10000000, "total_assets_jeoksu": 730000000000}}, {"label": "차가감소득금액", "tool": "income_adjustment_total", "args": {"net_income": 300000000, "items": [{"항목": "법인세비용", "종류": "법인세비용", "금액": 20000000}, {"항목": "기업업무추진비 한도초과", "종류": "기업업무추진비 한도초과", "금액": 2280000}, {"항목": "기계장치 감가상각비 한도초과", "종류": "감가상각비 한도초과", "금액": 5550000}, {"항목": "㈜B 수입배당금 익금불산입", "종류": "수입배당금 익금불산입", "금액": 7200000}]}}, {"label": "부가세 공통사용재화", "tool": "common_input_tax", "args": {"year": 2025, "period": "1기", "filing": "확정", "supplies": {"확정": {"taxable": 60, "exempt": 40}}, "prior_period_supplies": {"taxable": 50, "exempt": 50}, "common_asset_sales": [{"sale_price": 20000000, "input_tax": 0}, {"sale_price": 400000, "input_tax": 0}], "ledger": [{"항목": "당기 매입 없음", "매입세액": 0, "사용처": "과세"}]}}, {"label": "부가세 토지·건물 일괄양도", "tool": "bundled_supply_split", "args": {"total_price": 500000000, "vat_included": false, "standard_value": {"building": 240000000, "land": 160000000}, "book_value": {"building": 200000000, "land": 200000000}}}, {"label": "대표 갑 총급여", "tool": "earned_income_gross_pay", "args": {"year": 2025, "items": [{"kind": "급여", "amount": 100000000, "facts": {}}, {"kind": "사회보험료_사용자부담분", "amount": 3000000, "facts": {"insurance": "건강보험"}}, {"kind": "인정상여", "amount": 5000000, "facts": {"work_year": 2025, "settlement_date": "2026-03-30"}}, {"kind": "자가운전보조금", "amount": 2400000, "facts": {"months": 12, "vehicle": "기타", "business_use": false, "actual_travel_reimbursed": false}}, {"kind": "실비변상여비", "amount": 4000000, "facts": {"actual_cost": false}}, {"kind": "직무발명보상금", "amount": 7000000, "facts": {"retired": false, "related_party": true}}, {"kind": "사택제공이익", "amount": 20000000, "facts": {"position": "지배주주인 대표자"}}]}}, {"label": "대표 갑 금융소득", "tool": "financial_income_aggregate", "args": {"year": 2025, "items": [{"kind": "출자공동사업자배당", "amount": 6000000}, {"kind": "의제배당_잉여금자본전입", "amount": 10000000, "source": "이익잉여금"}, {"kind": "상장법인현금배당", "amount": 7000000}, {"kind": "비상장법인현금배당", "amount": 8000000}, {"kind": "직장공제회초과반환금", "amount": 1000000}, {"kind": "법원보증금이자", "amount": 2000000}]}}]')


def test_demo_case_exports_all_calls(tmp_path):
    r, wb = build(tmp_path, DEMO_CALLS)
    assert r["결과"]["오류_call"] == [] and r["결과"]["call_수"] == 8
    summ = cells(wb["요약"])
    assert any(isinstance(v, str) and "부가가치세법 제40조" in v for v in summ)
    assert not any(isinstance(v, str) and v.startswith("[[") for s in wb.sheetnames for v in cells(wb[s]))
    calc = [s for s in wb.sheetnames if s.startswith("계산")]
    assert len(calc) == 8
    assert any(320630000 in cells(wb[s]) for s in calc)
    checks = [v for s in calc for k, v in _labelled(wb[s]).items() if k.startswith("확인")]
    assert checks and all(v == "일치" for v in checks)


def test_basis_lines_keep_positions(tmp_path):
    _, wb = build(tmp_path, DEMO_CALLS)
    lines = [ln for v in cells(wb["요약"]) if isinstance(v, str) for ln in v.split("\n")]
    assert "부가가치세법 제40조 — 실지귀속 우선, 공통매입세액은 안분기준으로 안분" in lines
    assert any(ln.startswith("부가가치세법 시행령 제81조① — ") for ln in lines)
    for s in [s for s in wb.sheetnames if s.startswith("계산")]:
        labels = [r[0] for r in wb[s].iter_rows(values_only=True)]
        assert labels.count("합계") == 0 or "금액 합계(방향 무관)" not in labels
