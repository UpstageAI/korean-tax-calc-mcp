"""verify_workbook — 직접 만든 통합 문서의 금액 칸을 계산 도구 결과와 대조. 작성 Claude 2026-11-15.

- 칸 값(저장된 값, 없으면 다시 계산)과 계산 도구 결과를 견주어 일치·불일치(차이)·읽지 못함·도구 오류.
- 검증 범위: 일치한 칸, 그 칸이 가리키는 칸, 입력 숫자, 그런 칸들의 링크·합·차가 아닌 금액 칸은 '대조 안 한 금액'.
- 사본: 대조 결과 시트를 붙이고 모든 수식 칸에 값을 채움(원본은 그대로, 원본에 저장된 값은 보존).
- 사례 값은 모두 지어낸 값(특정 사례와 무관).
"""
import hashlib
import json
import shutil

import openpyxl
import pytest

from korean_tax_calc_mcp import server as S
from tests._helpers import call as c

DIV = dict(income_kind="배당", recipient_type="법인", residence_country="프랑스", year=2025, amount=40_000_000)
NW, PEN = "nonresident_withholding", "withholding_late_payment_penalty"
FILED = {**DIV, "treaty_rate": 0.15, "treaty_includes_local_tax": False}
PEN_ARGS = dict(unpaid_tax=2_000_000, due="2025-04-10", until="2025-09-30")
CHECKS = [{"cell": "배당!B6", "tool": NW, "args": DIV, "key": "원천징수세액"},
          {"cell": "배당!B7", "tool": NW, "args": DIV, "key": "지방소득세", "label": "지방소득세(직접 붙인 이름)"},
          {"cell": "'배당'!$C$6", "tool": NW, "args": FILED, "key": "원천징수세액"},
          {"cell": "가산세_칸", "tool": PEN, "args": PEN_ARGS, "key": "가산세"},
          {"cell": "배당!C7", "tool": NW, "args": FILED, "key": "지방소득세"}]


def _book(path, tax_formula="=ROUNDDOWN(B4*B5,-1)"):
    """손으로 짠 작은 통합 문서(수식만, 저장된 값 없음)."""
    wb = openpyxl.Workbook()
    i = wb.active
    i.title = "입력"
    for r, (k, v) in enumerate([("배당금", 40_000_000), ("국내세율", 0.2), ("제한세율", 0.15), ("이미 낸 세액", 6_000_000), ("일수", 173)], 1):
        i.cell(r, 1, k)
        i.cell(r, 2, v)
    ws = wb.create_sheet("배당")
    ws.append(["배당 원천징수"])
    ws.append([])
    ws.append(["항목", "맞는 금액", "신고한 대로"])
    ws.append(["배당금", "=입력!B1", "=입력!B1"])
    ws.append(["세율", "=입력!B2", "=입력!B3"])
    ws.append(["법인세", tax_formula, "=ROUNDDOWN(C4*C5,-1)"])
    ws.append(["지방소득세", "=ROUNDDOWN(B6*0.1,-1)", "=ROUNDDOWN(C6*0.1,-1)"])
    ws.append(["합계", "=B6+B7", "=SUM(C6:C7)"])
    ws.append(["부족분", "=B6-입력!B4"])
    ws.append(["가산세", "=MIN(ROUNDDOWN(B9*0.03,0)+ROUNDDOWN(B9*입력!B5*0.00022,0),ROUNDDOWN(B9*0.1,0))"])
    ws.append(["지방소득세 가산세(직접 식)", "=ROUNDDOWN(B7*0.03+B7*입력!B5*0.00022,0)"])
    ws.append(["과거 연도 추정", "=B8*2.5/3"])
    ws.append(["직접 적은 금액", 1_234_567])
    ws.append(["비율", "=B6/B4"])
    ws["B5"].number_format = ws["C5"].number_format = ws["B14"].number_format = "0.0%"
    s = wb.create_sheet("요약")
    s.append(["낼 세금", "=배당!B8"])
    s.append(["가산세 포함", "=배당!B8+배당!B10"])
    s.append(["추정", "=배당!B12"])
    from openpyxl.workbook.defined_name import DefinedName
    wb.defined_names["가산세_칸"] = DefinedName("가산세_칸", attr_text="'배당'!$B$10")
    wb.save(path)
    return str(path)


def _sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


@pytest.fixture(scope="module")
def made(tmp_path_factory):
    d = tmp_path_factory.mktemp("verify")
    path = _book(d / "직접.xlsx")
    before = _sha(path)
    r = c("verify_workbook", {"path": path, "checks": CHECKS})
    assert "error" not in r, r
    return d, path, before, r


def test_matches_and_scope(made):
    _, path, before, r = made
    res = r["결과"]
    assert res["요약"] == {"대조": 5, "일치": 5, "불일치": 0, "읽지_못함": 0, "도구_오류": 0, "자동_일치": 0, "자동_불일치": 0, "대조_안_한_금액": 2}
    assert _sha(path) == before                                                               # 원본은 고치지 않음
    rows = {x["칸"]: x for x in res["대조"]}
    tool = c(NW, DIV)["결과"]
    assert rows["배당!B6"]["통합_문서_값"] == rows["배당!B6"]["도구_값"] == tool["원천징수세액"] == 8_000_000 and rows["배당!B6"]["차이"] == 0
    assert rows["배당!B6"]["항목"] == "법인세" and rows["배당!B7"]["항목"] == "지방소득세(직접 붙인 이름)"        # 항목은 칸 왼쪽 글 또는 label
    assert rows["배당!C6"]["도구_값"] == 6_000_000 and rows["배당!B10"]["도구_값"] == c(PEN, PEN_ARGS)["결과"]["가산세"]   # 따옴표·$ 주소, 정의된 이름
    assert rows["배당!B6"]["근거"] and "법인세법" in rows["배당!B6"]["근거"]                          # 도구가 돌려준 근거 그대로
    # 대조 안 한 금액: 계산 도구를 거치지 않은 식(직접 적은 지방소득세 가산세, 추정). 대조된 칸의 합(요약!B2)·링크는 빠짐
    assert [(x["시트"], x["칸"], x["항목"]) for x in res["대조_안_한_금액"]] == [("배당", "B11", "지방소득세 가산세(직접 식)"), ("배당", "B12", "과거 연도 추정")]
    assert res["대조_안_한_금액"][0]["값"] == 54_448
    assert "대조 안 한 금액은" in res["다음"] and "checks에 더하거나" in res["다음"] and r["한계"]


def test_scope_rules(tmp_path):
    """합·차·링크는 대조된 칸에 딸려 가고, 곱셈·반올림이 든 식은 따로 대조해야 한다."""
    path = _book(tmp_path / "b.xlsx")
    r = c("verify_workbook", {"path": path, "checks": CHECKS[:1], "annotate": False})["결과"]
    names = {(x["시트"], x["칸"]) for x in r["대조_안_한_금액"]}
    # B6만 대조: B7(지방소득세 식)·B8(그 합)·B10·B11(가산세 식)·B12(추정)·C6~C8(다른 시나리오)와 그 값이 든 요약 합
    assert names == {("배당", "B7"), ("배당", "B8"), ("배당", "B10"), ("배당", "B11"), ("배당", "B12"), ("배당", "C6"), ("배당", "C7"), ("배당", "C8"), ("요약", "B2")}
    assert ("배당", "B9") not in names and ("배당", "B4") not in names and ("요약", "B1") not in names   # 대조된 칸 − 입력, 입력 링크, 링크는 가리키는 칸이 대상
    assert "사본" not in r
    r = c("verify_workbook", {"path": path, "checks": CHECKS, "annotate": False})["결과"]
    assert {(x["시트"], x["칸"]) for x in r["대조_안_한_금액"]} == {("배당", "B11"), ("배당", "B12")}      # 요약!B2 = 대조된 두 칸의 합


def test_mismatch_gives_both_values_and_the_difference(tmp_path):
    path = _book(tmp_path / "틀림.xlsx", tax_formula="=ROUNDDOWN(B4*B5,-1)+70")
    r = c("verify_workbook", {"path": path, "checks": json.dumps(CHECKS), "lang": "en"})
    res = r["결과"]
    assert res["요약"]["불일치"] == 2 and res["요약"]["일치"] == 3                                    # 틀린 칸과 그 칸에 딸린 가산세
    bad = {x["칸"]: x for x in res["불일치"]}
    assert (bad["배당!B6"]["통합_문서_값"], bad["배당!B6"]["도구_값"], bad["배당!B6"]["차이"]) == (8_000_070, 8_000_000, 70)
    assert set(bad["배당!B6"]) == {"칸", "항목", "방식", "도구", "호출", "키", "통합_문서_값", "도구_값", "차이", "판정", "근거"}   # 원인 추측 없음 — 두 값과 차이, 근거만
    assert "불일치 칸을 고쳐" in res["다음"]
    ok = c("verify_workbook", {"path": path, "checks": [{**CHECKS[0], "tolerance": 100}], "annotate": False})["결과"]["요약"]
    assert ok["일치"] == 1
    ws = openpyxl.load_workbook(res["사본"])["Tool check"]
    assert ws["E4"].value == "Difference"                                                           # 차이 열은 불일치가 있을 때만
    verdicts = [ws.cell(k, 6).value for k in range(5, 10)]
    assert verdicts == ["Mismatch", "Match", "Match", "Mismatch", "Match"] and ws["E5"].value == 70 and ws["F5"].fill.fgColor.rgb == "00F8CBAD"


def test_copy_has_check_sheet_and_values_in_every_formula_cell(made):
    d, path, _, r = made
    copy = r["결과"]["사본"]
    assert copy.endswith("직접_verified.xlsx") and copy != path
    src, wb, wv = openpyxl.load_workbook(path), openpyxl.load_workbook(copy), openpyxl.load_workbook(copy, data_only=True)
    assert wb.sheetnames == src.sheetnames + ["검산"]
    for name in src.sheetnames:                                                                # 원래 시트의 값·수식·서식 그대로
        for row in src[name].iter_rows():
            for x in row:
                y = wb[name][x.coordinate]
                assert (x.value, x.number_format, x.data_type) == (y.value, y.number_format, y.data_type)
    formulas = [(ws.title, x.coordinate) for ws in wb.worksheets for row in ws.iter_rows() for x in row if x.data_type == "f"]
    assert len(formulas) == 18 and not [k for k in formulas if wv[k[0]][k[1]].value is None]          # 모든 수식 칸에 값
    assert r["결과"]["부가_점검"]["저장된_값_없는_수식_칸"] == 18                                       # 원본에는 값이 없었음
    ws = wb["검산"]
    assert [ws.cell(4, j).value for j in range(1, 8)] == ["칸", "항목", "통합 문서 값", "도구 값", "판정", "근거 번호 · 결과 키", None]      # 불일치가 없어 차이 열 없음
    assert [ws.cell(5, j).value for j in range(1, 7)] == ["배당!B6", "법인세", 8_000_000, 8_000_000, "일치", "[1] 원천징수세액"]
    assert not [x.coordinate for row in ws.iter_rows() for x in row if x.data_type == "f"]
    texts = [ws.cell(k, 1).value for k in range(1, ws.max_row + 1)]
    assert texts[1] == "대조 5 · 일치 5 · 불일치 0 · 대조 안 한 금액 2칸"                              # 맨 위 한 줄 요약
    assert "계산 도구 대조를 거치지 않은 금액 — 2" in texts and "배당" in texts and "부가 점검" in texts and "검증 범위" not in texts
    again = c("verify_workbook", {"path": copy, "checks": CHECKS, "annotate": False})["결과"]      # 사본을 다시 대조하면 저장된 값을 읽음
    assert again["요약"]["일치"] == 5 and again["부가_점검"]["저장된_값_없는_수식_칸"] == 0


def test_other_checks(made, tmp_path):
    extra = made[3]["결과"]["부가_점검"]
    assert extra["수식_열에_직접_적은_숫자"] == ["배당!B13"] and extra["원_미만_소수_금액_칸"] == ["배당!B12", "요약!B3"]
    assert extra["오류_칸"] == [] and extra["값을_계산하지_못한_수식_칸"] == [] and extra["저장된_값과_다시_계산한_값이_다른_칸"] == []
    wb = openpyxl.load_workbook(made[1])
    wb["배당"]["D4"] = "=B4/0"
    wb["배당"]["D5"] = "=VLOOKUP(1,B4:B5,1)"
    wb.save(tmp_path / "e.xlsx")
    r = c("verify_workbook", {"path": str(tmp_path / "e.xlsx"), "checks": CHECKS[:1] + [{"cell": "배당!D5", "tool": NW, "args": DIV, "key": "합계"}]})
    assert r["결과"]["부가_점검"]["오류_칸"] == ["배당!D4"] and r["결과"]["부가_점검"]["값을_계산하지_못한_수식_칸"] == ["배당!D5"]
    assert r["결과"]["요약"]["읽지_못함"] == 1 and "읽지 못한 칸" in r["결과"]["다음"]


def test_resaved_export_gets_its_values_back(tmp_path):
    """export_workbook이 만든 파일을 openpyxl로 다시 저장하면 저장된 값이 지워진다 — verify_workbook을 거친 사본에는 다시 채워진다."""
    calls = [{"label": "배당", "tool": NW, "args": DIV}]
    made = c("export_workbook", {"title": "t", "calls": calls, "output_dir": str(tmp_path), "scenarios": [{"sheet": "배당", "columns": ["배당"]}]})
    path = made["결과"]["파일"]
    ws = openpyxl.load_workbook(path)["배당"]
    row = next(k for k in range(1, ws.max_row + 1) if str(ws.cell(k, 1).value).startswith("원천징수세액"))
    check = [{"cell": f"배당!B{row}", "tool": NW, "args": DIV, "key": "원천징수세액"}]
    first = c("verify_workbook", {"path": path, "checks": check, "annotate": False})["결과"]
    assert first["요약"]["일치"] == 1 and first["부가_점검"]["저장된_값_없는_수식_칸"] == 0
    resaved = str(tmp_path / "resaved.xlsx")
    openpyxl.load_workbook(path).save(resaved)
    r = c("verify_workbook", {"path": resaved, "checks": check})["결과"]
    assert r["요약"]["일치"] == 1 and r["부가_점검"]["저장된_값_없는_수식_칸"] > 10
    wb, wv = openpyxl.load_workbook(r["사본"]), openpyxl.load_workbook(r["사본"], data_only=True)
    assert not [1 for w in wb.worksheets for rr in w.iter_rows() for x in rr if x.data_type == "f" and wv[w.title][x.coordinate].value is None]
    assert "verify_workbook" in made["결과"]["파일_안내"]


def test_stored_values_from_the_original_are_kept(tmp_path):
    """원본에 저장돼 있던 값은 사본에 그대로 옮긴다(다른 프로그램이 계산한 값 보존) — 다시 계산한 값과 다르면 부가 점검에 나타남."""
    import zipfile
    from korean_tax_calc_mcp.workbook_cache import fill_cached_values
    path = _book(tmp_path / "v.xlsx")
    fill_cached_values(openpyxl.load_workbook(path), path)
    stale = str(tmp_path / "stale.xlsx")
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(stale, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename == "xl/worksheets/sheet2.xml":
                assert b"<v>8000000</v>" in data
                data = data.replace(b"<v>8000000</v>", b"<v>7999990</v>", 1)
            zout.writestr(info, data)
    r = c("verify_workbook", {"path": stale, "checks": CHECKS[:1]})["결과"]
    assert r["불일치"][0]["통합_문서_값"] == 7_999_990 and r["부가_점검"]["저장된_값과_다시_계산한_값이_다른_칸"] == ["배당!B6"]
    assert openpyxl.load_workbook(r["사본"], data_only=True)["배당"]["B6"].value == 7_999_990


@pytest.mark.parametrize("kw, phrase", [
    (dict(path="/없는/파일.xlsx"), "xlsx 파일이 아님"), (dict(checks=[]), "비어 있음"), (dict(checks="{"), "JSON"),
    (dict(checks=[{"tool": NW, "args": DIV}]), "{cell, call 또는 tool+args, key}"), (dict(checks=[{"cell": "없는시트!B6", "tool": NW, "args": DIV, "key": "합계"}]), "시트: 입력, 배당, 요약"),
    (dict(checks=[{"cell": "배당!B6:B7", "tool": NW, "args": DIV, "key": "합계"}]), "찾지 못함"),
    (dict(checks=[{"cell": "배당!B6", "tool": "export_workbook", "args": {}, "key": "파일"}]), "대조에 쓸 수 없음"),
    (dict(checks=[{"cell": "배당!B6", "tool": NW, "args": DIV, "key": "합계", "tolerance": -1}]), "tolerance"), (dict(output_dir="/없는/폴더"), "output_dir")])
def test_bad_inputs(made, kw, phrase):
    r = c("verify_workbook", {"path": made[1], "checks": CHECKS, **kw})
    assert "error" in r and phrase in r["error"], r


def test_tool_errors_are_reported_per_check(made):
    checks = [{"cell": "배당!B6", "tool": NW, "args": DIV, "key": "없는_키"}, {"cell": "배당!B6", "tool": "없는_도구", "args": {}, "key": "x"},
              {"cell": "배당!B6", "tool": NW, "args": {**DIV, "year": 1990}, "key": "합계"}, {"cell": "배당!B6", "tool": NW, "args": DIV, "key": "역산.과세표준"}]
    res = c("verify_workbook", {"path": made[1], "checks": checks, "annotate": False})["결과"]
    assert res["요약"]["도구_오류"] == 4 and res["요약"]["일치"] == 0
    assert "숫자 키: " in res["읽지_못함·도구_오류"][0]["도구_오류"] and "원천징수세액" in res["읽지_못함·도구_오류"][0]["도구_오류"]


def test_dotted_key_and_same_call_runs_once(made, monkeypatch):
    args = {**DIV, "net_of_tax": True}
    tool = c(NW, args)["결과"]
    n = {"n": 0}
    import sys
    mcp = sys.modules["korean_tax_calc_mcp.server"].mcp          # 다른 테스트가 서버 모듈을 다시 읽어 들였어도 지금 쓰이는 것을 센다
    real = mcp.call_tool

    async def counting(name, a):
        n["n"] += 1
        return await real(name, a)
    monkeypatch.setattr(mcp, "call_tool", counting)
    from korean_tax_calc_mcp.workbook_verify import verify_workbook_impl
    r = verify_workbook_impl(made[1], [{"cell": "배당!B5", "tool": NW, "args": args, "key": "역산.역산에_쓴_세율"}, {"cell": "배당!B6", "tool": NW, "args": args, "key": "원천징수세액"},
                                       {"cell": "배당!B7", "tool": NW, "args": dict(reversed(list(args.items()))), "key": "지방소득세"}], annotate=False)
    assert n["n"] == 1 and r["결과"]["대조"][0]["도구_값"] == tool["역산"]["역산에_쓴_세율"] == 0.2 and r["결과"]["대조"][0]["판정"] == "일치"


def test_description_and_registration():
    tools = {t.name: t for t in S.mcp._tool_manager.list_tools()}
    assert len(tools) == 144
    d = tools["verify_workbook"].description
    first = d.splitlines()[0]
    assert first.startswith("After saving an Excel workbook (.xlsx file or spreadsheet — workings or a report) you built yourself, call this tool (직접 만든 엑셀 검산)") and "언제:" in d and "입력:" in d
    assert d.splitlines()[1].strip().startswith("직접 만든 Excel을 저장한 뒤 이 도구를 부른다 — 금액 칸을 계산 도구 결과와 대조해 검산 시트 한 장을 붙인다.")
    for p in tools["verify_workbook"].parameters["properties"]:
        assert p in d, p
    assert "엑셀" not in c("verify_workbook", {"path": "x", "checks": []})                           # 공통 꼬리는 붙지 않음
    assert S.find_tool(query="직접 만든 엑셀 검산")["결과"]["후보"][0]["도구"] == "verify_workbook"
    assert S.find_tool(query="verify my workbook against the calculators")["결과"]["후보"][0]["도구"] == "verify_workbook"
    ins = S.mcp.instructions
    assert "저장한 뒤 verify_workbook으로 금액 칸을 대조한다" in ins and "대조하지 않은 금액은 사용자에게 밝힌다" in ins


@pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice 없음")
def test_copy_values_match_libreoffice(made, tmp_path):
    from tests.test_workbook_cached_values import compare_with_libreoffice
    n, bad = compare_with_libreoffice(made[3]["결과"]["사본"], tmp_path)
    assert n == 18 and bad == []
