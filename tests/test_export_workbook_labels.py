"""export_workbook의 labels(라벨 치환 표)와 '파일을 다시 저장하지 말 것' 안내. 작성 Claude 2026-11-15.

- 영문 통합 문서에 국문 그대로 남은 라벨을 고치려고 저장된 파일을 openpyxl 등으로 다시 저장하면 수식 칸의 계산 값이 지워져
  휴대폰·미리보기에서 다시 0으로 보인다. 그래서 표기는 입력(labels)으로 받는다 — 도구는 글을 지어내지 않고 준 글만 쓴다.
- labels를 주지 않으면 출력은 그대로, 줘도 수식·정의된 이름·대조 칸은 그대로.
- 사례 값은 모두 지어낸 값.
"""
import json
import shutil

import openpyxl
import pytest

from korean_tax_calc_mcp import server as S
from tests._helpers import call as c
from tests.test_export_workbook_blend import CALLS, ISSUES, SCENARIOS, SOURCES
from tests.test_workbook_cached_values import _formula_cells, compare_with_libreoffice

BLEND = {"scenarios": SCENARIOS, "sources": SOURCES, "issues": ISSUES}
LABELS = {"약정_순액": "Agreed net amount", "역산": "Gross-up", "세율_구성": "Rate components", "지방소득세_근거": "Local income tax basis",
          "원천징수세액(법인세)": "CIT withheld", "과세표준": "Base amount", "시트에_없는_키": "Nothing"}


def _export(tmp_path, name, **kw):
    r = c("export_workbook", {"title": name, "calls": CALLS, "output_dir": str(tmp_path), **kw})
    assert "error" not in r, r
    return r


def _texts(path):
    wb = openpyxl.load_workbook(path)
    return {(ws.title, cell.coordinate): cell.value for ws in wb.worksheets for row in ws.iter_rows() for cell in row if cell.value is not None}


def _column_a(path, sheet):
    return [v for (s, ref), v in _texts(path).items() if s == sheet and ref.startswith("A") and isinstance(v, str)]


@pytest.fixture(scope="module")
def made(tmp_path_factory):
    d = tmp_path_factory.mktemp("labels")
    out = {}
    for lang in ("en", "ko"):
        out[lang, "plain"] = _export(d, f"plain_{lang}", lang=lang, **BLEND)
        out[lang, "labels"] = _export(d, f"labels_{lang}", lang=lang, labels=LABELS, **BLEND)
    return out


def test_english_labels_keep_the_original_key_in_parentheses(made):
    r = made["en", "labels"]
    path = r["결과"]["파일"]
    detail = _column_a(path, "Calc detail")
    assert "Agreed net amount (약정_순액)" in detail and "Local income tax basis (지방소득세_근거)" in detail
    assert "Gross-up (역산).Rate components (세율_구성)" in detail            # 경로는 마디마다
    assert "약정_순액" not in detail and "지방소득세_근거" not in detail
    scenario = _column_a(path, "배당")
    assert "CIT withheld (원천징수세액(법인세))" in scenario and "Base amount (과세표준)" in scenario
    assert any("CIT withheld (원천징수세액(법인세))" in t for t in _column_a(path, "Summary"))
    before, after = made["en", "plain"]["결과"]["번역_없음"], r["결과"]["번역_없음"]
    assert {"약정_순액", "지방소득세_근거"} <= set(before) and not {"약정_순액", "지방소득세_근거", "역산", "세율_구성"} & set(after)
    assert set(r["결과"]["labels_적용"]) == set(LABELS) - {"시트에_없는_키"}


def test_korean_labels_show_the_given_text(made):
    r = made["ko", "labels"]
    path = r["결과"]["파일"]
    detail = _column_a(path, "계산 상세")
    assert "Agreed net amount" in detail and "Gross-up.Rate components" in detail and "약정_순액" not in detail
    assert "CIT withheld" in _column_a(path, "배당") and any("— CIT withheld (" in t for t in _column_a(path, "요약"))
    assert set(r["결과"]["labels_적용"]) == set(LABELS) - {"시트에_없는_키"}


@pytest.mark.parametrize("lang, phrase", [("en", "labels: no label with this name"), ("ko", "labels: 시트에서 이 이름의 라벨을 찾지 못해")])
def test_unknown_label_key_is_reported(made, lang, phrase):
    warn = [w for w in made[lang, "labels"]["warnings"] if w.startswith("labels:")]
    assert len(warn) == 1 and phrase in warn[0] and warn[0].endswith("시트에_없는_키")
    assert not [w for w in made[lang, "plain"].get("warnings") or [] if w.startswith("labels:")]


@pytest.mark.parametrize("lang", ["en", "ko"])
def test_labels_change_label_text_only(made, lang):
    """수식·숫자·정의된 이름은 그대로 — 달라지는 칸은 글 칸뿐이고, 모든 수식 칸에 계산 값이 있다."""
    a, b = made[lang, "plain"]["결과"]["파일"], made[lang, "labels"]["결과"]["파일"]
    ta, tb = _texts(a), _texts(b)
    assert set(ta) == set(tb)
    changed = {k for k in ta if ta[k] != tb[k]}
    assert len(changed) >= 10
    assert all(isinstance(ta[k], str) and isinstance(tb[k], str) and not ta[k].startswith("=") and not tb[k].startswith("=") for k in changed)
    wa, wb = openpyxl.load_workbook(a), openpyxl.load_workbook(b)
    assert {k: d.attr_text for k, d in wa.defined_names.items()} == {k: d.attr_text for k, d in wb.defined_names.items()}
    cells = _formula_cells(b)
    assert len(cells) > 50 and not [x for x in cells if x[3] is None or (x[3] == "" and x[2] != "str")]
    va, vb = openpyxl.load_workbook(a, data_only=True), openpyxl.load_workbook(b, data_only=True)
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if cell.data_type == "f":
                    assert va[ws.title][cell.coordinate].value == vb[ws.title][cell.coordinate].value
    checks = [cell.value for ws in vb.worksheets for row in ws.iter_rows() for cell in row
              if cell.value in ("일치", "확인 필요", "Match (일치)", "Check (확인 필요)", "Match", "Check")]
    assert checks and not [x for x in checks if "확인 필요" in x or x == "Check"]
    tool = c(CALLS[0]["tool"], CALLS[0]["args"])["결과"]["원천징수세액"]
    assert tool in [cell.value for row in vb.worksheets[0].iter_rows() for cell in row]


@pytest.mark.parametrize("lang", ["en", "ko"])
@pytest.mark.parametrize("kw", [{}, BLEND, {**BLEND, "detail": "full"}], ids=["plain", "compact", "full"])
def test_without_labels_the_text_is_unchanged(tmp_path, lang, kw):
    """labels를 주지 않거나 빈 표를 주면 글·수식이 같다."""
    a = _export(tmp_path, "a", lang=lang, **kw)
    b = _export(tmp_path, "b", lang=lang, labels={}, **kw)
    ta, tb = _texts(a["결과"]["파일"]), _texts(b["결과"]["파일"])
    title = {k for k in ta if isinstance(ta[k], str) and ta[k].startswith("a")}       # 제목 칸만 다름
    assert {k: v for k, v in ta.items() if k not in title} == {k: v for k, v in tb.items() if k not in title}
    assert "labels_적용" not in a["결과"] and "labels_적용" not in b["결과"]


def test_labels_reach_per_call_sheets_and_accept_json(tmp_path):
    ko = _export(tmp_path, "k", labels=json.dumps({"약정_순액": "약정한 순액", "지방소득세_근거": "지방소득세 근거"}, ensure_ascii=False))
    assert "약정한 순액" in _column_a(ko["결과"]["파일"], "계산 2") and "지방소득세 근거" in _column_a(ko["결과"]["파일"], "계산 1")
    assert ko["결과"]["labels_적용"] == ["약정_순액", "지방소득세_근거"]
    en = _export(tmp_path, "e", lang="en", labels={"약정_순액": "Agreed net amount"}, detail="full", **BLEND)
    assert "Agreed net amount (약정_순액)" in _column_a(en["결과"]["파일"], "Calc 2 (계산 2)")
    cells = _formula_cells(en["결과"]["파일"])
    assert cells and not [x for x in cells if x[3] is None or (x[3] == "" and x[2] != "str")]


@pytest.mark.parametrize("bad", [{"약정_순액": 3}, {"": "x"}, "not json", {"약정_순액": "=1+1"}])
def test_bad_labels_are_rejected(tmp_path, bad):
    r = c("export_workbook", {"title": "x", "calls": CALLS[:1], "output_dir": str(tmp_path), "labels": bad})
    assert "labels" in r["error"] and not list(tmp_path.iterdir())


def test_result_and_description_say_not_to_resave(made):
    en, ko = made["en", "plain"]["결과"], made["ko", "plain"]["결과"]
    for r in (en, ko):
        assert "다시 저장하면" in r["파일_안내"] and "labels" in r["파일_안내"] and "Re-saving this file" in r["파일_안내"] and "verify_workbook" in r["파일_안내"]
    assert en["번역_없음"] and "labels" in en["번역_없음_안내"] and "번역_없음_안내" not in ko
    assert "`labels`" in next(w for w in made["en", "plain"]["warnings"] if w.startswith("Untranslated labels"))
    doc = S.mcp._tool_manager._tools["export_workbook"].description
    head = doc[:1500]
    head = doc[:2200]      # 0.56.0: 사실 안내(다시 저장하면 계산값이 지워짐) + 다시 채우는 길(verify_workbook)
    assert "다시 저장하면" in head and "Re-saving the file" in head and "verify_workbook" in head and "언제:" in doc and "입력:" in doc and "labels —" in doc
    assert "다시 저장하면" in S.mcp.instructions and "Re-saving a file made by export_workbook" in S.mcp.instructions


@pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice 없음")
@pytest.mark.parametrize("lang", ["en", "ko"])
def test_labelled_workbook_matches_libreoffice_recalculation(made, lang, tmp_path):
    n, bad = compare_with_libreoffice(made[lang, "labels"]["결과"]["파일"], tmp_path)
    assert n > 50 and bad == []
