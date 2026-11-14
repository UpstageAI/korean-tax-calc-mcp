"""international_transaction_statement — 국조칙 별지 제16호서식(갑) 칸 집계·제출 의무, 국조16갑·국조20 서식 틀 (Claude 2026-11-14).

대조한 시행본(국세법령정보시스템):
- 별지 제16호서식(갑) <개정 2024. 3. 22.>(2026.3.20. 시행 시행규칙 HWP) 작성방법 5·9·10 — ⑨는 ⑩~㉑ 합계(⑰ 제외),
  ⑰ 예시 (100원×60일)+(200원×180일) = 42,000원, ⑱ 예시 42,000원 ÷ 365일 = 115원
- 국제조세조정에 관한 법률 시행령 2026.2.27. 시행본 제36조제1호(재화 5억·용역 1억·무형자산 1억 모두 이하면 국제거래명세서 면제),
  대통령령 제33272호 부칙 제2조(2023.1.1. 이후 개시 과세연도) — 2022년까지 면제 없음(corporate_filing_obligations와 같은 판정)
- 시행규칙 2024.3.22. 시행본 제27조①(지급보증 → 별지 제16호서식(을) 함께), ③(용역 18호·무형 19호·그 밖 20호)
"""
import openpyxl
from test_form_templates import build
from test_form_26 import Evaluator
from tests._helpers import call as c

T = "international_transaction_statement"
SH16, SH20 = "국조 별지16갑 국제거래명세서", "국조 별지20 정상가격산출방법"
EX_LOANS = [{"amount": 100, "days": 60}, {"amount": 200, "days": 180}]


def run(**kw):
    r = c(T, kw)
    assert "결과" in r, r
    return r


def test_form_example_loans_and_total_excludes_jeoksu():
    r = run(year=2025, parties=[{"name": "A", "sales": {"inventory": 1_000, "loans": EX_LOANS, "interest": 7}}])
    x = r["결과"]
    assert x["매출_대여금적수"] == 42_000 and x["매출_평균대여금"] == 115         # 서식 예시 그대로
    assert x["매출_계"] == 1_000 + 115 + 7                                        # ⑨ = ⑩~㉑(⑰ 제외)
    assert r["계산"]["매출거래"][0]["⑰ 대여금 적수"] == 42_000
    # 2024 사업연도는 366일 — 42,000 ÷ 366 = 114.75 → 114(원 미만 절사로 계산)
    r = run(year=2024, parties=[{"name": "A", "purchases": {"loans": EX_LOANS}}])
    assert r["결과"]["사업연도_일수"] == 366 and r["결과"]["매입_평균차입금"] == 114 and r["결과"]["매입_계"] == 114


def test_exemption_boundaries_2022_vs_2023():
    at = {"inventory": 500_000_000, "guarantee": 100_000_000, "royalty": 100_000_000}
    r23 = run(year=2023, parties=[{"name": "A", "sales": at}])["결과"]
    assert r23["국제거래명세서_제출"] is False and r23["제출기한"] is None          # 모두 '이하' → 면제(영 제36조제1호)
    over = run(year=2023, parties=[{"name": "A", "sales": dict(at, inventory=300_000_000), "purchases": {"other_tangible": 200_000_001}}])["결과"]
    assert over["재화거래_합계"] == 500_000_001 and over["국제거래명세서_제출"] is True   # 매출·매입 합계로 판정
    r22 = run(year=2022, parties=[{"name": "A", "sales": {"inventory": 400_000_000, "other_services": 100_000_000}}])["결과"]
    assert r22["국제거래명세서_제출"] is True and r22["제출기한"] == "2023-06-30"   # 2022년까지는 거래가 있으면 제출
    r25 = run(year=2025, parties=[{"name": "A", "sales": {"inventory": 400_000_000, "other_services": 100_000_000}}])["결과"]
    assert r25["국제거래명세서_제출"] is False
    # 금전대차만 큰 경우 — 면제 기준(재화·용역·무형)에 넣지 않음
    loan = run(year=2025, parties=[{"name": "A", "sales": {"loans": [{"amount": 10_000_000_000, "days": 365}], "interest": 300_000_000}}])["결과"]
    assert loan["국제거래명세서_제출"] is False


def test_same_as_corporate_filing_obligations():
    p = [{"name": "A", "sales": {"inventory": 3_000_000_000}, "purchases": {"royalty": 150_000_000}},
         {"name": "B", "purchases": {"other_services": 300_000_000}}]
    r = run(year=2025, parties=p)["결과"]
    o = c("corporate_filing_obligations", {"year": 2025, "related_goods": 3_000_000_000, "related_services": 300_000_000,
                                           "related_intangibles": 150_000_000, "party_max_goods": 3_000_000_000,
                                           "party_max_services": 300_000_000, "party_max_intangibles": 150_000_000})["결과"]
    assert (r["국제거래명세서_제출"], r["요약손익계산서_제출"], r["정상가격산출방법신고서_제출"]) == \
           (o["국제거래명세서"], o["요약손익계산서"], o["정상가격산출방법신고서"]) == (True, True, False)


def test_accompanying_forms_and_deadline():
    p = [{"name": "A", "relationship": "지배", "sales": {"inventory": 6_000_000_000, "guarantee": 50_000_000, "royalty": 300_000_000,
                                                      "other_services": 1_100_000_000},
          "transfer_pricing": {"method": "거래순이익률방법", "reason": "비교가능 제3자 거래 없음"}}]
    r = run(year=2024, fy_start="2024-04-01", fy_end="2025-03-31", parties=p)
    x = r["결과"]
    assert x["제출기한"] == "2025-09-30"                          # 종료일이 속하는 달의 말일부터 6개월
    names = [f["서식"].split(" ")[1] for f in x["함께_낼_서식"]]
    assert names == ["제16호서식(을)", "제17호서식", "제18호서식", "제19호서식", "제20호서식"]
    inp = {i["이름"]: i["값"] for i in r["계산식_입력"]}
    assert inp["산출방법"] == "거래순이익률방법" and inp["국외_관계표시"].startswith("[√] 지배")
    assert "재고자산 매출 6,000,000,000원" in inp["대상거래"]


def test_integrated_report_filer_2022_vs_2024():
    p = [{"name": "A", "sales": {"inventory": 60_000_000_000}}]
    assert run(year=2022, revenue=200_000_000_000, parties=p)["결과"]["국제거래명세서_제출"] is False   # 법 제16조② 괄호 — 제외
    assert run(year=2024, revenue=200_000_000_000, parties=p)["결과"]["국제거래명세서_제출"] is True    # 괄호 삭제(법률 제19928호)


def test_input_errors_and_old_years():
    r = c(T, {"year": 2025, "parties": [{"name": "A", "sales": {"loans": [{"amount": 1, "days": 400}]}}]})
    assert "error" in r and any("days" in m for m in r["문제"])
    r = c(T, {"year": 2025, "parties": [{"name": "A", "relationship": "모회사"}]})
    assert "error" in r
    old = run(year=2019, parties=[{"name": "A", "sales": {"inventory": 1}}])
    assert any("구 서식" in m and "미확인" in m for m in old["주의"])


def _wbook(tmp_path, args):
    tmp_path.mkdir(parents=True, exist_ok=True)
    y = args["year"]
    return openpyxl.load_workbook(build(tmp_path, [{"label": "국제거래", "tool": T, "args": args}], period=f"{y}.01.01 ~ {y}.12.31"))


def test_workbook_16gap_totals_match_tool(tmp_path):
    args = dict(year=2025, parties=[
        {"name": "Alpha Inc.", "country": "US", "relationship": "지배",
         "sales": {"inventory": 1_200_000_000, "loans": EX_LOANS, "interest": 3_000}, "purchases": {"royalty": 80_000_000}},
        {"name": "Beta GmbH", "country": "DE", "relationship": "자매",
         "sales": {"other_services": 40_000_000}, "purchases": {"inventory": 500_000_000, "loans": [{"amount": 1_000_000, "days": 365}], "interest": 50_000}}])
    tool = run(**args)["결과"]
    wb = _wbook(tmp_path, args)
    assert SH16 in wb.sheetnames
    ws, ev = wb[SH16], Evaluator(wb)
    assert ws["A7"].value == "Alpha Inc." and ws["A8"].value == "Beta GmbH" and ws["A16"].value == "Alpha Inc."
    assert ws["Q7"].value == "=100*60+200*180" and ev.v(SH16, "R7") == 115
    assert ev.v(SH16, "I12") == tool["매출_계"] == 1_200_000_000 + 115 + 3_000 + 40_000_000
    assert ev.v(SH16, "Q12") == tool["매출_대여금적수"] and ev.v(SH16, "R12") == tool["매출_평균대여금"]
    assert ev.v(SH16, "I21") == tool["매입_계"] == 80_000_000 + 500_000_000 + 1_000_000 + 50_000
    assert ev.v(SH16, "Q21") == tool["매입_차입금적수"] == 365_000_000 and ev.v(SH16, "R21") == 1_000_000
    assert "<개정 2024. 3. 22.>" in ws["A1"].value                         # 2025 사업연도 기한(2026.6.30.)은 개정 뒤
    assert [ev.v(SH16, f"G{r}") for r in range(26, 34)] == ["일치"] * 8      # 서식 아래 도구 확인 표(계·적수·평균·이자 × 매출·매입)
    # 정상가격 신고서 면제(전체 재화 50억 이하) → 별지20 시트 없음
    assert SH20 not in wb.sheetnames


def test_workbook_form20_and_skips(tmp_path):
    args = dict(year=2025, filer={"representative": "홍길동"}, parties=[
        {"name": "Alpha Inc.", "country": "US", "relationship": "피지배", "sales": {"inventory": 6_000_000_000},
         "transfer_pricing": {"transaction": "제품 수출", "method": "재판매가격방법", "reason": "재판매 기능만 수행"}}])
    wb = _wbook(tmp_path, args)
    assert SH16 in wb.sheetnames and SH20 in wb.sheetnames
    ws = wb[SH20]
    assert ws["C7"].value == "Alpha Inc." and ws["B11"].value == "제품 수출" and ws["B12"].value == "재판매가격방법"
    assert ws["C4"].value == "홍길동" and ws["C9"].value.startswith("[ ] 지배  [√] 피지배")
    # 2022 사업연도: 기한(2023.6.30.)이 서식 개정(2024.3.22.) 전이라 머리의 개정일 표기를 뺌
    wb = _wbook(tmp_path / "y22", dict(year=2022, parties=[{"name": "A", "sales": {"inventory": 1_000_000}}]))
    assert SH16 in wb.sheetnames and "<개정" not in wb[SH16]["A1"].value
    # 면제(2025, 재화 1백만) → 시트 없음, 2020 → 구 서식 미확인이라 시트 없음
    assert SH16 not in _wbook(tmp_path / "ex", dict(year=2025, parties=[{"name": "A", "sales": {"inventory": 1_000_000}}])).sheetnames
    assert SH16 not in _wbook(tmp_path / "y20", dict(year=2020, parties=[{"name": "A", "sales": {"inventory": 1_000_000}}])).sheetnames
