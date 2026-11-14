"""export_workbook lang='en' — 영문 표기(국문 병기)와 lang='ko' 회귀. 작성 Claude 2026-11-15.

- lang='ko'(기본)는 기존 출력과 같다: lang을 주지 않은 호출과 시트 이름·칸 값·결과 키가 같다.
- lang='en'은 시트 이름·요약 라벨·표 머리글·결과 키를 'English (국문)'으로 적는다. 번역표는 docs/glossary_ko_en.md의
  패키지 사본이고, 용어집에 없는 라벨은 국문 그대로 두어 요약 시트 'Untranslated labels (번역 없음)'과 결과 warnings에 모은다.
- 법정서식 틀 시트는 글자를 바꾸지 않는다. 숫자·수식은 같다.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import openpyxl
import pytest

from korean_tax_calc_mcp import workbook_i18n as i18n
from tests._helpers import call as c
from tests.test_export_workbook_c import ADJ, ENT

ROOT = Path(__file__).resolve().parents[1]
HANGUL = re.compile(r"[가-힣]")
CASES = {
    "nonresident_withholding": dict(income_kind="사용료", amount=100000000, recipient_type="법인", residence_country="미국",
                                    treaty_rate=0.15, year=2026),
    "foreign_worker_flat_tax": dict(year=2025, first_work_date="2023-03-01", taxable_pay=200000000, nontaxable_pay=3000000),
    "corporate_tax": dict(base=500000000, year=2025),
    "entertainment_limit": dict(year=2025, sme=False, general_revenue=10000000000, expensed=80000000),
}
# 도구별: '계산 1' 시트 A열에 있어야 하는 영문 라벨(국문 병기)
EXPECT = {
    "nonresident_withholding": ["Domestic tax rate (국내세율)", "Treaty tax rate (조약세율)", "Applicable tax rate (적용세율)",
                                "Withholding tax amount (원천징수세액)", "Local income tax (지방소득세)", "Total (합계)"],
    "foreign_worker_flat_tax": ["누진세율.Total salary (총급여)", "누진세율.Wage and salary income deduction (근로소득공제)",
                                "누진세율.Tax base (과세표준)", "누진세율.Calculated tax amount (산출세액)"],
    "corporate_tax": ["Calculated tax amount (산출세액)", "Tax base (과세표준)", "Business year (사업연도)", "Number of months (월수)"],
    "entertainment_limit": ["Number of months (월수)", "Limit (한도)", "Excess over limit (한도초과)"],
}


def _export(tmp_path, tool, lang=None, **kw):
    args = {"title": f"{tool}_{lang or 'default'}", "calls": [{"label": tool, "tool": tool, "args": CASES[tool]}],
            "output_dir": str(tmp_path), **kw}
    if lang:
        args["lang"] = lang
    r = c("export_workbook", args)
    assert "error" not in r, r
    return r


def _cells(ws):
    return {cell.coordinate: cell.value for row in ws.iter_rows() for cell in row if cell.value is not None}


def _col_a(ws):
    return [cell.value for cell in ws["A"] if isinstance(cell.value, str)]


# ── lang='ko' 회귀 ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("tool", list(CASES))
def test_ko_is_unchanged(tmp_path, tool):
    base, ko = _export(tmp_path, tool), _export(tmp_path, tool, "ko")
    assert set(base) == set(ko) == {"결과", "근거"}                       # 결과에 lang·warnings 같은 키를 더하지 않음
    assert set(ko["결과"]) == {"파일", "시트", "call_수", "오류_call"}
    assert base["결과"]["시트"] == ko["결과"]["시트"]
    assert {"요약", "목록", "입력·가정", "계산 1", "판단·근거"} <= set(ko["결과"]["시트"])
    wa, wb = openpyxl.load_workbook(base["결과"]["파일"]), openpyxl.load_workbook(ko["결과"]["파일"])
    assert wa.sheetnames == wb.sheetnames
    for name in wa.sheetnames:
        a, b = _cells(wa[name]), _cells(wb[name])
        # 요약 A1은 제목(호출마다 다르게 준 값)이라 뺀다
        if name == "요약":
            a.pop("A1"), b.pop("A1")
        assert a == b, name
    assert {n: d.attr_text for n, d in wa.defined_names.items()} == {n: d.attr_text for n, d in wb.defined_names.items()}


def test_ko_multi_call_forms_and_steps_unchanged(tmp_path):
    calls = [{"label": "기업업무추진비", "tool": "entertainment_adjustment", "args": ENT},
             {"label": "차가감", "tool": "income_adjustment_total", "args": ADJ},
             {"label": "법인세", "tool": "corporate_tax", "args": CASES["corporate_tax"]}]
    for layout in ("forms", "steps"):
        a = c("export_workbook", {"title": f"기본_{layout}", "calls": calls, "output_dir": str(tmp_path), "layout": layout})
        b = c("export_workbook", {"title": f"국문_{layout}", "calls": calls, "output_dir": str(tmp_path), "layout": layout, "lang": "ko"})
        wa, wb = openpyxl.load_workbook(a["결과"]["파일"]), openpyxl.load_workbook(b["결과"]["파일"])
        assert wa.sheetnames == wb.sheetnames and a["결과"]["시트"] == b["결과"]["시트"]
        for name in wa.sheetnames:
            x, y = _cells(wa[name]), _cells(wb[name])
            for k in ("A1", "B1"):       # 제목 칸(forms 요약 A1, steps 요약 B1)
                if name == "요약":
                    x.pop(k, None), y.pop(k, None)
            assert x == y, (layout, name)


def test_invalid_lang_is_rejected(tmp_path):
    try:
        r = c("export_workbook", {"title": "x", "calls": [{"label": "a", "tool": "corporate_tax", "args": CASES["corporate_tax"]}],
                                  "output_dir": str(tmp_path), "lang": "jp"})
    except Exception as e:                # 입력 스키마 검증에서 막힘(mcp 버전에 따라 예외 또는 오류 응답)
        assert "lang" in str(e)
        return
    assert "결과" not in r
    assert not list(tmp_path.glob("*.xlsx"))


# ── lang='en' ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize("tool", list(CASES))
def test_en_labels_with_korean_in_parentheses(tmp_path, tool):
    ko, en = _export(tmp_path, tool, "ko"), _export(tmp_path, tool, "en")
    res = en["결과"]
    assert res["lang"] == "en" and res["시트"][0] == "Summary (요약)"
    assert {"Summary (요약)", "Sheet list (목록)", "Inputs (입력·가정)", "Calc 1 (계산 1)", "Judgements (판단·근거)"} <= set(res["시트"])
    wb = openpyxl.load_workbook(res["파일"])                                # openpyxl로 다시 열림
    assert wb.sheetnames[0] == "Summary (요약)" and set(wb.sheetnames) == set(res["시트"])
    assert all(len(n) <= 31 for n in wb.sheetnames)
    calc = wb["Calc 1 (계산 1)"]
    col_a = _col_a(calc)
    for label in EXPECT[tool]:
        assert label in col_a, (label, col_a)
    headers = [cell.value for row in calc.iter_rows() for cell in row if isinstance(cell.value, str)]
    assert "Item (항목)" in headers or "Name (이름)" in headers
    # 요약 시트: 머리글·주요 값의 결과 키가 영문
    summ = wb["Summary (요약)"]
    texts = [v for v in _cells(summ).values() if isinstance(v, str)]
    assert "Results at a glance (계산 결과 한눈에)" in texts and "Key values (주요 값)" in texts
    assert summ["A1"].value.endswith("— Summary (요약)")
    # 숫자는 그대로: 시트마다 숫자 칸의 값이 국문 워크북과 같다
    kb = openpyxl.load_workbook(ko["결과"]["파일"])
    back = {"Summary (요약)": "요약", "Sheet list (목록)": "목록", "Inputs (입력·가정)": "입력·가정",
            "Calc 1 (계산 1)": "계산 1", "Judgements (판단·근거)": "판단·근거"}
    for name in wb.sheetnames:
        nums = sorted(v for v in _cells(wb[name]).values() if isinstance(v, (int, float)) and not isinstance(v, bool))
        ko_nums = sorted(v for v in _cells(kb[back.get(name, name)]).values() if isinstance(v, (int, float)) and not isinstance(v, bool))
        if name == "Summary (요약)":      # 영문 요약에는 시트 안내·번역 없음 목록의 순번이 더 있다
            assert all(n in nums for n in ko_nums)
        else:
            assert nums == ko_nums, name
    # 정의된 이름은 새 시트 이름을 가리킨다(옛 이름이 남지 않음)
    for d in wb.defined_names.values():
        assert "'입력·가정'" not in d.attr_text and "'계산 1'" not in d.attr_text
        sheet = re.match(r"'([^']+)'!", d.attr_text).group(1)
        assert sheet in wb.sheetnames


def test_en_untranslated_labels_are_kept_and_listed(tmp_path):
    en = _export(tmp_path, "entertainment_limit", "en")
    missing = en["결과"]["번역_없음"]
    assert "기본한도" in missing and "수입금액한도" in missing            # 용어집에 없는 라벨
    assert en["결과"]["번역_라벨_수"] > 0
    assert len(en["warnings"]) == 1 and en["warnings"][0].startswith(i18n.UNTRANSLATED_TITLE) and "기본한도" in en["warnings"][0]
    wb = openpyxl.load_workbook(en["결과"]["파일"])
    assert "기본한도" in _col_a(wb["Calc 1 (계산 1)"])                    # 국문 그대로(번역을 지어내지 않음)
    summ = wb["Summary (요약)"]
    rows = [[cell.value for cell in row] for row in summ.iter_rows()]
    start = next(i for i, r in enumerate(rows) if r[0] == i18n.UNTRANSLATED_TITLE)
    listed = [r[1] for r in rows[start + 1:] if isinstance(r[0], int)]
    assert listed == missing
    # 용어집에 다 있는 도구는 목록이 비고 warnings도 빈다
    ok = _export(tmp_path, "corporate_tax", "en")
    assert ok["결과"]["번역_없음"] == [] and ok["warnings"] == []
    s2 = openpyxl.load_workbook(ok["결과"]["파일"])["Summary (요약)"]
    assert any(isinstance(v, str) and v.startswith("None —") for v in _cells(s2).values())


def test_uncertain_glossary_rows_are_not_used():
    rows = json.loads((ROOT / "korean_tax_calc_mcp/data/glossary_ko_en.json").read_text(encoding="utf-8"))["terms"]
    uncertain = [r["ko"] for r in rows if "확인 필요" in r["note"]]
    assert "유보" in uncertain and "결정세액" in uncertain and "지점세" in uncertain
    t = i18n.Translator()
    for ko in uncertain:
        assert t.label(ko) == ko, ko                                       # '확인 필요' 행은 번역하지 않고 국문 그대로
    assert set(uncertain) <= set(t.missing)
    assert t.label("과세표준") == "Tax base (과세표준)"
    assert t.label("익금산입_손금불산입") == "Inclusion in gross income / non-deductible (익금산입_손금불산입)"
    assert t.label("한도 초과액") == "Excess over limit (한도 초과액)"          # 띄어쓰기 차이는 같은 용어
    assert t.label("amount") == "amount" and t.label("=SUM(A1)") == "=SUM(A1)"


def test_en_form_sheets_are_untouched(tmp_path):
    for tool, forms in (("entertainment_limit", ["별지23(갑) 기업업무추진비", "별지23(을) 기업업무추진비"]),
                        ("nonresident_withholding", ["원천 별지23(5) 외국법인 지급명세"])):
        ko, en = _export(tmp_path, tool, "ko"), _export(tmp_path, tool, "en")
        kb, eb = openpyxl.load_workbook(ko["결과"]["파일"]), openpyxl.load_workbook(en["결과"]["파일"])
        for name in forms:
            assert name in eb.sheetnames                                   # 시트 이름도 그대로
            a, b = _cells(kb[name]), _cells(eb[name])
            assert a.keys() == b.keys()
            for k in a:
                va, vb = a[k], b[k]
                if isinstance(va, str) and va.startswith("="):             # 수식은 다른 시트의 새 이름만 가리키게 바뀜
                    vb = vb.replace("'Inputs (입력·가정)'", "'입력·가정'").replace("'Calc 1 (계산 1)'", "'계산 1'")
                assert va == vb, (name, k)
            assert [str(m) for m in kb[name].merged_cells.ranges] == [str(m) for m in eb[name].merged_cells.ranges]
        # 요약 시트에 서식 시트마다 한 줄 영문 안내
        texts = [v for v in _cells(eb["Summary (요약)"]).values() if isinstance(v, str)]
        for name in forms:
            line = next(t for t in texts if t.startswith(f"Sheet '{name}' — statutory form"))
            assert line.endswith("(Korean filing format, kept in Korean)")
    assert any("under the Income Tax Act" in t for t in texts)


def test_en_free_text_stays_korean_under_notes_column(tmp_path):
    en = _export(tmp_path, "nonresident_withholding", "en",
                 review_notes=[{"항목": "Treaty rate", "내용": "Confirm the treaty article before filing."}])
    wb = openpyxl.load_workbook(en["결과"]["파일"])
    calc = wb["Calc 1 (계산 1)"]
    assert calc["C1"].value == i18n.NOTES_HEADER
    notes = [calc.cell(r, 3).value for r in range(2, calc.max_row + 1) if calc.cell(r, 3).value]
    assert notes and all(HANGUL.search(n) for n in notes)                  # 도구 문장은 번역하지 않고 국문 그대로
    assert all(calc.cell(r, 2).value is None for r in range(2, calc.max_row + 1) if calc.cell(r, 3).value)
    jud = wb["Judgements (판단·근거)"]
    heads = [cell.value for cell in jud[1]]
    assert sum(1 for h in heads if h.startswith(i18n.NOTES_HEADER)) == 3
    assert HANGUL.search(jud["C2"].value)
    texts = [v for v in _cells(wb["Summary (요약)"]).values() if isinstance(v, str)]
    assert "Confirm the treaty article before filing." in texts           # review_notes는 적은 그대로


def test_en_steps_layout_and_error_call(tmp_path):
    r = c("export_workbook", {"title": "steps_en", "layout": "steps", "lang": "en", "output_dir": str(tmp_path), "calls": [
        {"label": "CIT", "tool": "corporate_tax", "args": CASES["corporate_tax"]},
        {"label": "bad", "tool": "corporate_tax", "args": {"base": 1}}]})
    assert r["결과"]["시트"] == ["Summary (요약)", "Calc 1 (계산 1)", "Calc 2 (계산 2)", "Inputs (입력·가정)", "Judgements (판단·근거)"]
    assert r["결과"]["오류_call"] == ["bad"]
    wb = openpyxl.load_workbook(r["결과"]["파일"])
    s = wb["Summary (요약)"]
    assert s["A1"].value == "Title (제목)" and s["B1"].value == "steps_en"
    row5 = [cell.value for cell in s[5]]
    assert "Tax base (과세표준)" in row5 and 500000000 in row5
    assert _col_a(wb["Calc 2 (계산 2)"])[:3] == ["label", "Tool (도구)", "Error (오류)"]


def test_default_filename_is_the_same(tmp_path):
    en = _export(tmp_path, "corporate_tax", "en")
    assert Path(en["결과"]["파일"]).name == "corporate_tax_en.xlsx"         # 파일명 기본값은 제목 그대로


@pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice 없음")
def test_en_formulas_recalculate(tmp_path):
    calls = [{"label": "기업업무추진비", "tool": "entertainment_adjustment", "args": ENT},
             {"label": "차가감", "tool": "income_adjustment_total", "args": ADJ}]
    vals = {}
    for lang in ("ko", "en"):
        for layout in ("steps", "forms"):
            r = c("export_workbook", {"layout": layout, "title": f"recalc_{layout}_{lang}", "calls": calls,
                                      "output_dir": str(tmp_path), "lang": lang})
            out = tmp_path / f"recalc_{layout}_{lang}"
            subprocess.run(["soffice", "--headless", "--calc", "--convert-to", "xlsx", "--outdir", str(out), r["결과"]["파일"]],
                           check=True, capture_output=True, timeout=180)
            vals[(lang, layout)] = openpyxl.load_workbook(next(out.glob("*.xlsx")), data_only=True)
    for layout in ("steps", "forms"):
        wb = vals[("en", layout)]
        checks = [cell.value for s in ("Calc 1 (계산 1)", "Calc 2 (계산 2)") for row in wb[s].iter_rows() for cell in row
                  if cell.value in ("Match (일치)", "Check (확인 필요)", "일치", "확인 필요")]
        assert len(checks) >= 10 and set(checks) == {"Match (일치)"}, (layout, set(checks))
        # 수식이 낸 숫자는 국문 워크북과 같다(시트 이름을 바꿔도 참조가 끊기지 않음)
        ko = vals[("ko", layout)]
        for ke, kk in zip(wb.sheetnames, ko.sheetnames):
            ne = sorted(v for v in _cells(wb[ke]).values() if isinstance(v, (int, float)) and not isinstance(v, bool))
            nk = sorted(v for v in _cells(ko[kk]).values() if isinstance(v, (int, float)) and not isinstance(v, bool))
            if kk == "요약":
                assert all(n in ne for n in nk)
            else:
                assert ne == nk, (layout, ke)
            errs = [v for v in _cells(wb[ke]).values() if isinstance(v, str) and v.startswith(("#REF", "#NAME", "Err:"))]
            assert not errs, (layout, ke, errs)


# ── 용어집 사본·설명 ─────────────────────────────────────────────────────────
def test_packaged_glossary_matches_docs():
    md = i18n.parse_glossary_md((ROOT / "docs/glossary_ko_en.md").read_text(encoding="utf-8"))
    data = json.loads((ROOT / "korean_tax_calc_mcp/data/glossary_ko_en.json").read_text(encoding="utf-8"))
    assert data["terms"] == md and len(md) >= 220                         # 표를 고치면 사본도 다시 만든다
    kos = [r["ko"] for r in md]
    assert len(kos) == len(set(kos))                                      # 국문 용어 하나에 영문 하나


def test_docstring_and_schema_document_lang():
    import asyncio
    from korean_tax_calc_mcp.server import mcp
    tool = next(t for t in asyncio.run(mcp.list_tools()) if t.name == "export_workbook")
    schema = getattr(tool, "inputSchema", None) or tool.input_schema
    assert schema["properties"]["lang"]["enum"] == ["ko", "en"] and schema["properties"]["lang"]["default"] == "ko"
    assert tool.description.splitlines()[0].isascii() or tool.description.startswith("Excel export")
    for phrase in ("lang —", "Untranslated labels (번역 없음)", "Notes (Korean original)", "With lang='en', write review_notes in English"):
        assert phrase in tool.description, phrase
