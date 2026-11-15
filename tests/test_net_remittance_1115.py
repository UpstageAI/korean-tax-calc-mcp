"""0.57.1 — nonresident_withholding 순액 약정의 수취인 송금액 = 약정 순액(과세표준 − 세액 아님), 끝수 차이는 따로. 작성 Claude 2026-11-15.

대조한 원문
  법인세법 기본통칙 98-0…2(2024년 고시본, 국세법령정보시스템): 계약조건이 "국내 세법에 의한 제세를 공제한 금액을 지급하도록" 약정되어 있는 때의
    과세표준금액 = 지급하기로 약정한 금액 ÷ (1 − 원천징수세율) → 수취인에게 지급하는 금액은 약정한 금액 그대로, 과세표준은 역산한 금액.
  국고금 관리법 제47조(2011.10.5.·2026.1.2. 시행본 같은 문언): 제1항 수입·지출 10원 미만 끝수 버림, 제2항 국세 과세표준 1원 미만 버림.
  지방세기본법 제59조: 지방자치단체 징수금 끝수에 국고금 관리법 제47조 준용.
기대값은 손으로 계산(아래 주석). 사례 값은 모두 지어낸 값."""
import shutil
import subprocess

import openpyxl
import pytest

from korean_tax_calc_mcp.engine.calc_income import nonresident_withholding as nw
from tests._helpers import call as c

M = 1_000_000
ROY = dict(income_kind="사용료", recipient_type="법인", residence_country="미국", treaty_rate=0.15)
HAS_LO = pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice 없음")


def _nw(amount, **kw):
    a = dict(ROY) | kw
    return nw(a.pop("income_kind"), amount, a.pop("recipient_type"), a.pop("residence_country"), **a)


# ── 도구 결과 ───────────────────────────────────────────────────────────────
def test_payer_bears_all_tax_remits_the_agreed_net_amount():
    """100,000,000 ÷ (1 − 0.165) = 119,760,479.04… → 과세표준 119,760,479
    법인세 119,760,479.04 × 15% = 17,964,071.8… → 17,964,070, 지방소득세 1,796,407 → 1,796,400, 합계 19,760,470
    과세표준 − 합계 = 100,000,009 — 송금액은 약정 순액 100,000,000, 끝수 9"""
    r = _nw(100 * M, payer_bears_local_tax=True)
    assert (r["과세표준"], r["원천징수세액"], r["지방소득세"], r["합계"]) == (119_760_479, 17_964_070, 1_796_400, 19_760_470)      # 계산은 그대로
    assert r["수취인_송금액"] == r["약정_순액"] == 100 * M
    assert r["끝수_차이"] == 9 == r["과세표준"] - r["합계"] - r["수취인_송금액"]
    assert "100,000,000원" in r["끝수_설명"] and "100,000,009원" in r["끝수_설명"] and "9원 다르다" in r["끝수_설명"]
    assert "국고금 관리법 제47조제2항" in r["끝수_설명"] and "119,760,470원" in r["끝수_설명"]      # 지급자가 실제 내는 돈 = 송금액 + 세액


def test_national_tax_only_net_clause_deducts_local_tax_from_the_recipient():
    """100,000,000 ÷ 0.85 = 117,647,058.82… → 과세표준 117,647,058, 법인세 17,647,058.8 → 17,647,050, 지방소득세 1,764,700(수취인 부담)
    송금액 = 100,000,000 − 1,764,700 = 98,235,300, 과세표준 − 합계 = 98,235,308 → 끝수 8"""
    r = _nw(100 * M, net_of_tax=True)
    assert (r["과세표준"], r["원천징수세액"], r["지방소득세"]) == (117_647_058, 17_647_050, 1_764_700)
    assert r["수취인_송금액"] == 98_235_300 and r["끝수_차이"] == 8
    assert "약정 순액 − 지방소득세" in r["끝수_설명"]


def test_no_fraction_when_the_gross_up_is_exact():
    """83,500,000 ÷ 0.835 = 100,000,000 — 법인세 15,000,000, 지방소득세 1,500,000, 과세표준 − 합계 = 83,500,000 → 끝수 0"""
    r = _nw(83_500_000, payer_bears_local_tax=True)
    assert (r["과세표준"], r["합계"], r["수취인_송금액"], r["끝수_차이"]) == (100 * M, 16_500_000, 83_500_000, 0)
    assert "끝수 없음" in r["끝수_설명"] and "다르다" not in r["끝수_설명"]


def test_recipient_bears_tax_is_payment_less_tax_and_other_values_unchanged():
    """수취인 부담: 100,000,000 × 15% = 15,000,000, 지방소득세 1,500,000 → 송금액 83,500,000. 종전 키의 값은 그대로이고 끝수 키는 없음."""
    r = _nw(100 * M)
    assert (r["국내세율"], r["조약세율"], r["적용세율"], r["원천징수세액"], r["지방소득세"], r["합계"]) == (0.2, 0.15, 0.15, 15 * M, 1_500_000, 16_500_000)
    assert r["수취인_송금액"] == 83_500_000
    assert not {"끝수_차이", "끝수_설명", "약정_순액", "과세표준", "역산"} & set(r)
    odd = _nw(33_333_333, treaty_rate=None)                # 33,333,333 × 20% = 6,666,666.6 → 6,666,660, 지방 666,666 → 666,660
    assert (odd["원천징수세액"], odd["지방소득세"], odd["수취인_송금액"]) == (6_666_660, 666_660, 33_333_333 - 7_333_320)


def test_treaty_covering_local_tax_and_individual_recipient():
    """조약 대상조세에 지방소득세 포함(일본 10%): 85,000,000 ÷ 0.9 = 94,444,444.4 → 과세표준 94,444,444
    국세분 94,444,444.4 × 10%/1.1 = 8,585,858.5 → 8,585,850, 지방 858,585 → 858,580, 합계 9,444,430 → 과세표준 − 합계 = 85,000,014 → 끝수 14"""
    r = _nw(85 * M, residence_country="일본", treaty_rate=0.10, payer_bears_local_tax=True)
    assert (r["과세표준"], r["원천징수세액"], r["지방소득세"]) == (94_444_444, 8_585_850, 858_580)
    assert r["수취인_송금액"] == 85 * M and r["끝수_차이"] == 14
    p = _nw(100 * M, recipient_type="개인", payer_bears_local_tax=True)      # 개인도 같은 산식(유추) — 송금액은 약정 순액
    assert p["수취인_송금액"] == 100 * M and p["끝수_차이"] == 9


@pytest.mark.parametrize("amount", [1, 9, 999, 12_345_678, 987_654_321, 10 * M + 1])
@pytest.mark.parametrize("kw", [dict(net_of_tax=True), dict(payer_bears_local_tax=True)])
@pytest.mark.parametrize("rate", [None, 0.05, 0.1, 0.12, 0.15])
def test_fraction_is_never_negative_and_stays_small(amount, kw, rate):
    r = _nw(amount, treaty_rate=rate, **kw)
    assert 0 <= r["끝수_차이"] < 20                          # 과세표준 1원 미만 + 국세 10원 미만 + 지방세 10원 미만(+ 국세 끝수의 10%)
    assert r["과세표준"] - r["합계"] == r["수취인_송금액"] + r["끝수_차이"]
    assert r["수취인_송금액"] == amount - (0 if kw.get("payer_bears_local_tax") else r["지방소득세"])


def test_tool_result_keys_through_the_server():
    out = c("nonresident_withholding", dict(ROY, amount=100 * M, payer_bears_local_tax=True))["결과"]
    assert (out["수취인_송금액"], out["끝수_차이"]) == (100 * M, 9) and out["끝수_설명"].startswith("수취인 송금액은 약정 순액 100,000,000원")
    plain = c("nonresident_withholding", dict(ROY, amount=100 * M))["결과"]
    assert plain["수취인_송금액"] == 83_500_000 and "끝수_차이" not in plain


# ── export_workbook 시나리오 틀 ─────────────────────────────────────────────
CALLS = [{"label": "총액", "tool": "nonresident_withholding", "args": dict(ROY, amount=100 * M)},
         {"label": "국세만 부담", "tool": "nonresident_withholding", "args": dict(ROY, amount=100 * M, net_of_tax=True)},
         {"label": "전부 부담", "tool": "nonresident_withholding", "args": dict(ROY, amount=100 * M, payer_bears_local_tax=True)}]
SCEN = [{"sheet": "사용료", "columns": ["총액", "국세만 부담", "전부 부담"]}]


def _export(d, lang="ko", **kw):
    r = c("export_workbook", {"title": "순액 약정", "calls": CALLS, "scenarios": SCEN, "output_dir": str(d), "lang": lang, "filename": f"net_{lang}", **kw})
    assert "error" not in r, r
    return r["결과"]["파일"]


def _rows(ws):
    return {ws.cell(r, 1).value: r for r in range(1, ws.max_row + 1) if ws.cell(r, 1).value}


def _sheet(wb):
    return next(ws for ws in wb.worksheets if ws.title.startswith("사용료"))


@pytest.mark.parametrize("lang", ["ko", "en"])
def test_scenario_sheet_remittance_row_points_at_the_agreed_net_amount(tmp_path, lang):
    path = _export(tmp_path, lang)
    ws, vals = _sheet(openpyxl.load_workbook(path)), _sheet(openpyxl.load_workbook(path, data_only=True))
    rows = _rows(ws)
    remit, gap, amount, ok = (("Net amount remitted to the recipient", "Difference from fractional numbers (tax base − total tax − net amount remitted)",
                               "Payment amount (agreed net amount under a net-of-tax clause)", "Match (일치)") if lang == "en" else
                              ("수취인 송금액", "끝수 차이(과세표준 − 합계 − 송금액)", "지급액(순액 약정이면 약정 순액)", "일치"))
    assert not [k for k in rows if "tax base − total tax)" in str(k) or "(과세표준 − 합계)" in str(k)]      # 옛 줄 이름 없음
    r, g, a = rows[remit], rows[gap], rows[amount]
    # 저장된 값(캐시 값): 송금액은 한 줄에 나란히 — 총액 83,500,000 / 국세만 부담 98,235,300 / 전부 부담 100,000,000
    assert [vals.cell(r, j).value for j in (2, 3, 4)] == [83_500_000, 98_235_300, 100 * M]
    assert [vals.cell(g, j).value for j in (2, 3, 4)] == [None, 8, 9]
    # 수식: 전부 부담 열은 입력 칸(약정 순액)만, 국세만 부담 열은 약정 순액 − 지방소득세, 총액 열은 종전대로 과세표준 − 합계
    assert ws.cell(r, 4).value == f"=D{a}" and ws.cell(r, 3).value.startswith(f"=C{a}-C") and ws.cell(r, 2).value.count("-") == 1
    assert ws.cell(g, 4).value.endswith(f"-D{r}") and ws.cell(g, 2).value is None
    # 대조 칸: 송금액·끝수 차이도 도구 값과 견준다 — 수식에 값이 들어 있고 저장된 판정은 일치
    check = next(k for k in range(1, ws.max_row + 1) if str(ws.cell(k, 4).value).startswith("=IF(AND("))
    assert f"ROUND(D{r},0)=100000000" in ws.cell(check, 4).value and f"ROUND(D{g},0)=9" in ws.cell(check, 4).value
    assert [vals.cell(check, j).value for j in (2, 3, 4)] == [ok] * 3


def test_old_row_names_still_resolve_for_links(tmp_path):
    """종전 줄 이름으로 건 링크(extra_sheets의 from_row)는 그대로 통한다 — 값은 약정 순액."""
    extra = [{"sheet": "메모", "headers": ["항목", "금액"], "rows": [["송금", {"from_call": "전부 부담", "from_row": "수취인 송금액(과세표준 − 합계)"}],
                                                               ["송금(키)", {"from_call": "전부 부담", "from_row": "수취인_송금액"}]]}]
    path = _export(tmp_path, extra_sheets=extra)
    ws = openpyxl.load_workbook(path, data_only=True)["메모"]
    assert [ws.cell(k, 2).value for k in (5, 6)] == [100 * M, 100 * M]


@HAS_LO
def test_scenario_sheet_recalculates_to_tool_values(tmp_path):
    path = _export(tmp_path, "en")
    out = tmp_path / "re"
    subprocess.run(["soffice", f"-env:UserInstallation=file://{tmp_path / 'lo_profile'}", "--headless", "--calc", "--convert-to", "xlsx",
                    "--outdir", str(out), str(path)], check=True, capture_output=True, timeout=300)
    ws = _sheet(openpyxl.load_workbook(next(out.glob("*.xlsx")), data_only=True))
    rows = _rows(ws)
    r, g = rows["Net amount remitted to the recipient"], rows["Difference from fractional numbers (tax base − total tax − net amount remitted)"]
    assert [ws.cell(r, j).value for j in (2, 3, 4)] == [83_500_000, 98_235_300, 100 * M] and [ws.cell(g, j).value for j in (3, 4)] == [8, 9]
    checks = [x.value for row in ws.iter_rows() for x in row if x.value in ("Match (일치)", "Check (확인 필요)")]
    assert checks == ["Match (일치)"] * 3


# ── 영문 표기 ───────────────────────────────────────────────────────────────
def test_glossary_has_the_new_result_keys():
    from korean_tax_calc_mcp import workbook_i18n as W
    import json
    import pathlib
    terms = {t["ko"]: t for t in json.loads((pathlib.Path(W.__file__).parent / "data" / "glossary_ko_en.json").read_text(encoding="utf-8"))["terms"]}
    assert terms["수취인_송금액"]["en"] == "net amount remitted to the recipient"
    assert terms["끝수_차이"]["en"] == "difference from fractional numbers" and "국고금 관리법 제47조" in terms["끝수_차이"]["note"]
