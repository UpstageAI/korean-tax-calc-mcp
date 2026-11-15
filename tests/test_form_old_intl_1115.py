"""2016~2020 개시 사업연도의 국제거래명세서·정상가격 산출방법 신고서·해외현지법인 명세서·재무상황표 서식 판(2026-11-15, Claude).

원문(법제처 국가법령정보센터 — 시행본별 별지 서식 PDF와 부칙):
- 구 국제조세조정에 관한 법률 시행규칙 별지 제8호서식(갑): <개정 2016.4.6.>(기획재정부령 제559호 — ⑯ 합계 = ㉓+㉘+㉟, 제출현황 칸 없음),
  <개정 2017. 3. 17.>(제613호 — ⑦~⑨ 제출현황 신설, ⑲ 합계 = ㉖+㉛+㊳), <개정 2018. 3. 19.>(제663호 — 칸 배치 같음)
- 국제조세조정에 관한 법률 시행규칙 별지 제16호서식(갑) 2021.3.16. 전부개정본(제840호 — 칸 번호는 2017판과 같고 문구 일부 다름),
  <개정 2022. 3. 18.>(제901호 — 무형자산거래를 따로 떼어 칸 번호가 바뀜, 이 판 틀은 없음)
- 구 별지 제1호의3서식 <개정 2015.3.13.>·<개정 2020. 3. 13.>(제772호), 별지 제20호서식 2021.3.16. 전부개정본
- 구 법인세법 시행규칙 별지 제81호·제82호서식 <개정 2014.3.14>(2016.11.2.·2020.4.21. 시행본 같음), 국조칙 별지 제47호·제48호서식 2021.3.16. 전부개정본
- 부칙: 제613호 제2조·제717호 제3조·제772호 제2조①·제840호 제3조·제901호 제4조 — 시행 이후 제출하는 분부터. 제559호·제663호는 서식 적용례 없음(시행일부터로 봄)
- 법률 제17651호 부칙 제28조: 종전 제출기한이 2021.1.1. 전에 지난 해외현지법인 자료는 종전 규정(구 법인세법 제121조의2)
"""
from datetime import date

import openpyxl
import pytest
from test_form_26 import Evaluator
from test_form_templates import build
from tests._helpers import call as c

from korean_tax_calc_mcp.engine import calc_intl_statement as I
from korean_tax_calc_mcp.forms_workbook import load_templates

T, OST = "international_transaction_statement", "overseas_subsidiary_statement"
EX = [{"amount": 100, "days": 60}, {"amount": 200, "days": 180}]          # 서식 예시: 적수 42,000, 평균 115(365일)
A = {"name": "Alpha Inc.", "country": "미국", "local_id": "123", "tax_id": "T-1", "fiscal_year": "1.1.~12.31.", "industry_code": "515050",
     "established": "2010-03", "relationship": "지배", "address": "New York",
     "sales": {"inventory": 6_000_000_000, "other_tangible": 10, "intangible_sale": 20, "royalty": 30, "tangible_rental": 5,
               "other_services": 40, "guarantee": 50, "loans": EX, "interest": 7, "other": 3},
     "purchases": {"inventory": 100, "guarantee": 9, "interest": 11, "other": 4},
     "transfer_pricing": {"transaction": "제품 판매", "method": "거래순이익률방법", "reason": "비교가능성"}}
B = {"name": "Beta GmbH", "country": "독일", "relationship": "피지배", "purchases": {"inventory": 2_000_000_000}}
# 손 계산(Alpha): 재화 6,000,000,000+10+20+100 = 6,000,000,130 / 용역 40+50+(30+5)+9 = 134 / 대여·차입 115+7+11 = 133 / 그 밖 3+4 = 7
A_GOODS, A_SVC, A_LOAN, A_OTHER = 6_000_000_130, 134, 133, 7
A_TOTAL = A_GOODS + A_SVC + A_LOAN                                        # 합계에는 그 밖의 거래를 넣지 않음(서식 ⑲ = ㉖+㉛+㊳)


def run(**kw):
    r = c(T, kw)
    assert "결과" in r, r
    return r


def wbook(tmp_path, tool, args, name="w"):
    d = tmp_path / name
    d.mkdir(parents=True, exist_ok=True)
    return openpyxl.load_workbook(build(d, [{"label": "호출", "tool": tool, "args": args}]))


def listed(wb):
    return {wb["목록"].cell(r, 1).value: wb["목록"].cell(r, 2).value for r in range(1, wb["목록"].max_row + 1)}


def inp(r, name):
    return next(x["값"] for x in r["계산식_입력"] if x["이름"] == name)


def test_edition_boundaries_by_date():
    e = lambda d: I._edition(I.STATEMENT_EDITIONS, date.fromisoformat(d))      # noqa: E731
    assert [e(d) for d in ("2016-04-06", "2017-03-16", "2017-03-17", "2018-03-18", "2018-03-19", "2021-03-15", "2021-03-16", "2022-03-17", "2022-03-18")] == \
        [20160406, 20160406, 20170317, 20170317, 20180319, 20180319, 20210316, 20210316, 20220318]
    t = lambda d: I._edition(I.TP_FORM_EDITIONS, date.fromisoformat(d))        # noqa: E731
    assert [t(d) for d in ("2020-03-12", "2020-03-13", "2021-03-15", "2021-03-16")] == [20150313, 20200313, 20200313, 20210316]


@pytest.mark.parametrize("year,fy,deadline,stmt,tp", [
    (2016, ("2016-01-01", "2016-11-30"), "2017-02-28", 20160406, 20150313),     # 기한이 2017.3.17. 전 → 2016판
    (2016, None, "2017-03-31", 20170317, 20150313),                             # 12월 결산 2016년분 → 2017판
    (2017, ("2017-01-01", "2017-11-30"), "2018-02-28", 20170317, 20150313),
    (2017, None, "2018-03-31", 20180319, 20150313),
    (2019, None, "2020-03-31", 20180319, 20200313),                             # 신고서는 2020.3.13.부터 2020판
    (2020, ("2020-01-01", "2020-09-30"), "2020-12-31", 20180319, 20200313),     # 종전 기한이 2021.1.1. 전 → 3개월, 구 서식
    (2020, None, "2021-06-30", 20210316, 20210316),                             # 6개월 기한 → 2021.3.16. 전부개정 서식
    (2020, ("2020-10-01", "2021-09-30"), "2022-03-31", 20220318, 20210316),
])
def test_edition_follows_deadline(year, fy, deadline, stmt, tp):
    kw = {"fy_start": fy[0], "fy_end": fy[1]} if fy else {}
    r = run(year=year, parties=[{"name": "A", "sales": {"inventory": 1}}], **kw)
    assert r["결과"]["제출기한"] == deadline and inp(r, "명세서_서식판") == stmt and inp(r, "신고서_서식판") == tp


def test_old_form_amounts_by_hand():
    x = run(year=2018, parties=[A, B])["결과"]["구서식"]
    assert x["p1"] == {"국외특수관계인": "Alpha Inc.", "재화소계": A_GOODS, "용역소계": A_SVC, "대차소계": A_LOAN, "기타소계": A_OTHER, "합계": A_TOTAL}
    assert x["p2"]["합계"] == 2_000_000_000 and x["장수"] == 2 and x["거래금액_총계"] == A_TOTAL + 2_000_000_000
    assert x["서식"] == "구 시행규칙 별지 제8호서식(갑) <개정 2018. 3. 19.>"
    assert "구서식" not in run(year=2021, parties=[A])["결과"]                  # 2021년부터는 기존 결과 그대로
    f = run(year=2018, parties=[dict(A, sales={"guarantee": 50})])["결과"]["함께_낼_서식"]
    assert f[0]["서식"].startswith("구 별지 제8호서식(을)") and "구 국제조세조정에 관한 법률 시행규칙 제6조①" in f[0]["근거"]
    f20 = run(year=2020, parties=[dict(A, sales={"guarantee": 50})])["결과"]["함께_낼_서식"]      # 기한 2021.6.30. → 새 번호
    assert f20[0]["서식"].startswith("별지 제16호서식(을)")


# 판 → (연도 인자, 시트 이름, 머리 문구, 합계 행, 합계 문구, 재화 소계 행 문구, 용역 문구(매출), 그 밖의 거래 문구)
LAYOUT = {
    2016: (dict(year=2016, fy_end="2016-11-30"), "구국조 별지8갑 2016판", "[별지 제8호서식(갑)] <개정 2016.4.6.>", 14,
           "⑯ 재화거래, 용역거래, 대여 및 차입거래 합계 (㉓ + ㉘ + ㉟)", "㉓ 소 계", "㉔ 「국제조세조정에 관한 법률 시행령」에 따른 용역거래", "라. 상기 ’가‘~’다‘ 및\n자본거래 외의 거래"),
    2017: (dict(year=2016), "구국조 별지8갑 2017판", "[별지 제8호서식(갑)] <개정 2017. 3. 17.>", 17,
           "⑲ 재화거래, 용역거래, 대여 및 차입거래 합계 (㉖ + ㉛ + ㊳)", "㉖ 소 계", "㉗ 「국제조세조정에 관한 법률 시행령」 제6조의2제1항에 따른 용역거래", "라. 가목부터 디목까지\n및 마목 이외의 거래"),
    2018: (dict(year=2019), "구국조 별지8갑 2018판", "[별지 제8호서식(갑)] <개정 2018. 3. 19.>", 17,
           "⑲ 재화거래, 용역거래, 대여 및 차입거래 합계 (㉖ + ㉛ + ㊳)", "㉖ 소 계", "㉗ 「국제조세조정에 관한 법률 시행령」 제6조의2제1항에 따른 용역거래", "라. 가목부터 디목까지\n및 마목 이외의 거래"),
    2021: (dict(year=2020), "국조 별지16갑 2021판", "[별지 제16호서식(갑)]", 17,
           "⑲ 재화거래, 용역거래, 대여 및 차입 거래 합계 (㉖ + ㉛ + ㊳)", "㉖ 소 계", "㉗ 「국제조세조정에 관한 법률 시행령」 제12조에 따른 용역거래", "라. 가목부터\n다목까지\n및 마목 외의 거래"),
}


@pytest.mark.parametrize("ed", list(LAYOUT))
def test_statement_sheet_per_party_in_that_edition(tmp_path, ed):
    kw, sheet, head, t, total, sub, svc, other = LAYOUT[ed]
    a = dict(A, sales=dict(A["sales"], loans=[{"amount": 100, "days": 60}, {"amount": 200, "days": 180}]))
    wb = wbook(tmp_path, T, dict(parties=[a, B], **kw))
    names = [n for n in wb.sheetnames if "별지8갑" in n or "별지16갑" in n]
    assert names == [f"{sheet} (1)", f"{sheet} (2)"], wb.sheetnames            # 국외특수관계인별 한 장, 현행 틀(국조 별지16갑 국제거래명세서)은 없음
    ws, ev = wb[f"{sheet} (1)"], Evaluator(wb)
    assert ws["A1"].value.endswith(head) and ws["A2"].value == "국제거래명세서"
    assert ws[f"A{t}"].value == total and ws[f"B{t + 7}"].value == sub and ws[f"C{t + 8}"].value == svc and ws[f"A{t + 22}"].value == other
    assert ws[f"A{t + 25}"].value.startswith("※") and ws[f"A{t + 26}"].value is None       # 그 밖의 거래 소계가 마지막 줄
    assert (ws["A7"].value == "2. 국제거래명세서 제출현황(총계)") == (ed in (2017, 2018))    # 제출현황 칸은 2017판부터(2021판은 문구가 '제출 현황')
    assert ws[f"B{t - 6}"].value == "Alpha Inc." and ws[f"D{t - 3}"].value == "지배" and wb[f"{sheet} (2)"][f"B{t - 6}"].value == "Beta GmbH"
    days = 366 if kw["year"] in (2016, 2020) and "fy_end" not in kw else (335 if "fy_end" in kw else 365)
    avg = 42_000 // days                                                       # 적수 42,000 ÷ 사업연도 일수, 원 미만 절사
    assert ws[f"F{t + 18}"].value == 42_000 and ev.v(f"{sheet} (1)", f"F{t + 19}") == avg
    goods, svc_v, loan = A_GOODS, A_SVC, avg + 7 + 11
    assert [ev.v(f"{sheet} (1)", f"F{r}") for r in (t + 7, t + 14, t + 21, t + 24, t)] == [goods, svc_v, loan, A_OTHER, goods + svc_v + loan]
    assert [ev.v(f"{sheet} (1)", f"I{r}") for r in (t, t + 7, t + 14, t + 21, t + 24)] == ["일치"] * 5       # 도구 값 대조
    assert ev.v(f"{sheet} (2)", f"F{t}") == 2_000_000_000
    if ed != 2016:                                                             # ⑧ 제출 국외특수관계인 수, ⑨ 거래금액 총계
        assert ev.v(f"{sheet} (1)", "C9") == 2 and ev.v(f"{sheet} (1)", "E9") == goods + svc_v + loan + 2_000_000_000


def test_2017_and_2018_editions_share_layout():
    t = load_templates()
    a, b = t["국조명세서_2017_1"], t["국조명세서_2018_1"]
    assert [x for x in a["cells"][1:]] == [x for x in b["cells"][1:]] and a["cells"][0] != b["cells"][0]     # 머리의 개정 표기만 다름
    assert sorted(k for k in t if k.startswith("국조명세서_")) == [f"국조명세서_{y}_{k}" for y in (2016, 2017, 2018, 2021) for k in range(1, 6)]


def test_amount_on_line_missing_from_that_form_skips_sheet(tmp_path):
    # 가상자산 칸은 2023.3.20. 개정에서 생김 — 그 전 서식에 없는 칸에 금액이 있으면 시트를 만들지 않고 목록에 사유
    wb = wbook(tmp_path, T, dict(year=2019, parties=[dict(B, sales={"virtual_assets": 5})]))
    assert not any("별지8갑" in n or "별지16갑" in n for n in wb.sheetnames)
    assert "가상자산 칸이 없어" in listed(wb)["국제거래명세서(구 서식)"]
    # 제출기한이 2022.3.18. 이후인 2020년 개시 사업연도 — 2022판 틀은 없음
    wb = wbook(tmp_path, T, dict(year=2020, fy_start="2020-10-01", fy_end="2021-09-30", parties=[B]), "late")
    assert not any("별지8갑" in n or "별지16갑" in n for n in wb.sheetnames)
    assert "<개정 2022. 3. 18.>" in listed(wb)["국제거래명세서(2022판)"]


def test_more_than_five_parties_draws_first_five(tmp_path):
    ps = [{"name": f"P{i}", "sales": {"inventory": i}} for i in range(1, 8)]
    r = run(year=2018, parties=ps)
    assert r["결과"]["구서식"]["장수"] == 7 and any("앞의 5명만" in m for m in r["주의"])
    wb = wbook(tmp_path, T, dict(year=2018, parties=ps))
    assert [n for n in wb.sheetnames if "별지8갑" in n] == [f"구국조 별지8갑 2018판 ({k})" for k in range(1, 6)]


@pytest.mark.parametrize("year,sheet,head,rel,decl", [
    (2018, "구국조 별지1의3 2015판", "[별지 제1호의3서식] <개정 2015.3.13.>", "[ ] 피지배  [√] 지배", "「국제조세조정에 관한 법률 시행령」 제7조제1항에 따라"),
    (2019, "구국조 별지1의3 2020판", "[별지 제1호의3서식] <개정 2020. 3. 13.>", "[ ] 피지배  [√] 지배", "「국제조세조정에 관한 법률 시행령」 제7조제1항에 따라"),
    (2020, "국조 별지20 2021판", "[별지 제20호서식]", "[√] 지배  [ ] 피지배", "「국제조세조정에 관한 법률」 제16조제2항제3호에 따라"),
])
def test_pricing_method_report_editions(tmp_path, year, sheet, head, rel, decl):
    wb = wbook(tmp_path, T, dict(year=year, parties=[A, B]))                   # 재화 80억(전체 50억 초과, Alpha 60억) → 신고서 제출 대상
    assert sheet in wb.sheetnames and "국조 별지20 정상가격산출방법" not in wb.sheetnames
    ws = wb[sheet]
    assert ws["A1"].value.endswith(head) and ws["C9"].value.startswith(rel) and ws["A14"].value.startswith(decl)
    assert ws["C7"].value == "Alpha Inc." and ws["B12"].value == "거래순이익률방법"


# ── 해외현지법인 명세서·재무상황표 ──
FIN = {"01": 10_000, "14": 4_000, "21": 6_000, "27": 9_000, "30": 6_000, "56": 3_000}
OS = dict(subsidiary={"name": "Garam Vietnam Co., Ltd.", "country": "베트남", "local_id": "123456789"}, ownership_direct=0.6,
          equity_investment=3_000_000_000, loan_investment=500_000_000, related_party=True, financials=FIN)
S81, S82, S47N, S48N = "법인 별지81 해외현지법인명세", "법인 별지82 재무상황표", "국조 별지47 2021판", "국조 별지48 2021판"
S47, S48 = "국조 별지47 해외현지법인명세", "국조 별지48 재무상황표"


def os_sheets(wb):
    return [n for n in wb.sheetnames if "별지81" in n or "별지82" in n or "별지47" in n or "별지48" in n]


def test_overseas_old_rule_uses_corporate_tax_forms(tmp_path):
    # 2019.12.31. 종료 법인: 종전 기한 2020.3.31.이 2021.1.1. 전 → 구 법인세법 시행규칙 별지 제81호·제82호서식
    wb = wbook(tmp_path, OST, dict(OS, year=2019))
    assert os_sheets(wb) == [S81, S82]
    w81, w82, ev = wb[S81], wb[S82], Evaluator(wb)
    assert w81["A1"].value == "■ 법인세법 시행규칙 [별지 제81호서식] <개정 2014.3.14>" and w81["A2"].value == "① 모법인명"
    assert w81["A10"].value == "⑪ 해외현지법인명" and w81["B10"].value == "Garam Vietnam Co., Ltd." and w81["B16"].value == "㉑ 출자금액"
    assert w81["A30"].value == "㊲ 주거래은행 신고 여부" and w81["A31"].value.startswith("「법인세법」 제121조의2")
    assert "[√] 국내모법인의 자회사" in w81["A9"].value and ev.v(S81, "B17") == 3_000_000_000 and ev.v(S81, "D17") == 60.0
    assert w81["F39"].value == "2020-03-31"
    assert w82["A1"].value == "■ 법인세법 시행규칙 [별지 제82호서식] <개정 2014.3.14>" and w82["A9"].value.startswith("1. 해외현지법인 요약대차대조표")
    assert w82["A24"].value == "11. 위 분류과목 이외 자산" and w82["A53"].value.startswith("「법인세법」 제121조의2")
    assert ev.v(S82, "C10") == 10_000 and ev.v(S82, "F16") == 3_000
    # 재무상황표 대상이 아니면 82 시트 없이 목록에 사유(구 조문)
    wb = wbook(tmp_path, OST, dict(OS, year=2019, ownership_direct=0.05, related_party=False), "small")
    assert os_sheets(wb) == [S81] and "구 법인세법 시행령 제164조의2제1항제2호" in listed(wb)["구 법인세법 시행규칙 별지 제82호서식"]


def test_overseas_boundary_20210101_and_20220318(tmp_path):
    # 2020.9.30. 종료: 종전 기한 2020.12.31. → 구 서식 / 2020.12.31. 종료: 종전 기한 2021.3.31. → 현행 규정, 기한 2021.6.30. → 2021.3.16. 전부개정 서식
    assert os_sheets(wbook(tmp_path, OST, dict(OS, year=2020, fy_end="2020-09-30"), "a")) == [S81, S82]
    wb = wbook(tmp_path, OST, dict(OS, year=2020), "b")
    assert os_sheets(wb) == [S47N, S48N]
    assert wb[S47N]["A1"].value == "■ 국제조세조정에 관한 법률 시행규칙 [별지 제47호서식]" and wb[S47N]["A10"].value == "⑪ 해외현지법인명"
    assert wb[S47N]["A2"].value == "① 성명/모법인명" and wb[S47N]["F39"].value == "2021-06-30"
    assert wb[S48N]["A1"].value == "■ 국제조세조정에 관한 법률 시행규칙 [별지 제48호서식]" and wb[S48N]["A9"].value.startswith("1. 해외현지법인 요약대차대조표")
    # 2021.8.31. 종료(2020.9.1. 개시): 기한 2022.2.28. → 재무상황표 2021판 / 2021.9.30. 종료: 기한 2022.3.31. → <개정 2022. 3. 18.>판(요약재무상태표)
    assert os_sheets(wbook(tmp_path, OST, dict(OS, year=2020, fy_end="2021-08-31"), "c")) == [S47N, S48N]
    wb = wbook(tmp_path, OST, dict(OS, year=2020, fy_end="2021-09-30"), "d")
    assert sorted(os_sheets(wb)) == sorted([S47N, S48]) and wb[S48]["A9"].value.startswith("1. 해외현지법인 요약재무상태표")
    # 2021년 개시분은 기존 틀 그대로
    assert os_sheets(wbook(tmp_path, OST, dict(OS, year=2021), "e")) == [S47, S48]


def test_overseas_individual_old_rule_has_no_sheet(tmp_path):
    wb = wbook(tmp_path, OST, dict(OS, year=2019, filer="개인"))
    assert os_sheets(wb) == [] and "별지 제93호" in listed(wb)["구 소득세법 시행규칙 별지 제93호·제94호서식"]


@pytest.mark.skipif(not __import__("shutil").which("soffice"), reason="수식 재계산에 LibreOffice 필요")
def test_recalculated_sheets_match_tool(tmp_path):
    """엑셀을 실제로 다시 계산해 평균(적수 ÷ 일수)·소계·합계가 도구 값과 같은지 — 구 서식 한 장과 현행 별지 제16호서식(갑)."""
    import pathlib
    import subprocess
    loans = {"loans": [{"amount": 100, "days": 60}, {"amount": 200, "days": 180}], "interest": 7}
    path = build(tmp_path, [{"label": "구", "tool": T, "args": dict(year=2018, parties=[A, B])},
                            {"label": "현행", "tool": T, "args": dict(year=2025, parties=[{"name": "A", "sales": dict(loans, inventory=600_000_000)}])}])
    out = pathlib.Path(tmp_path) / "re"
    subprocess.run(["soffice", f"-env:UserInstallation=file://{pathlib.Path(tmp_path) / 'lo_profile'}", "--headless", "--calc", "--convert-to", "xlsx",
                    "--outdir", str(out), path], check=True, capture_output=True, timeout=180)
    wb = openpyxl.load_workbook(next(out.glob("*.xlsx")), data_only=True)
    old = wb["구국조 별지8갑 2018판 (1)"]
    assert old["F35"].value == 42_000 and old["F36"].value == 115 and old["F38"].value == A_LOAN and old["F17"].value == A_TOTAL
    assert [old[f"I{r}"].value for r in (17, 24, 31, 38, 41)] == ["일치"] * 5
    cur = wb["국조 별지16갑 국제거래명세서"]
    assert cur["Q7"].value == 42_000 and cur["R7"].value == 115 and cur["I12"].value == 600_000_000 + 115 + 7
    assert [cur.cell(r, 7).value for r in range(26, 34)] == ["일치"] * 8
