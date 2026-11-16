"""거친 출력 다듬기(0.59.1) — 전 도구 점검(0.57.2, 2026-11-16) (b)5~(b)10 중 0.58.1에서 남긴 것. Claude 작성.

항목별 재현 입력 → 기대(입력 오류·주의 문구·정수 표기·문장 끝·영문 키·조건부 확인 문구). 금액은 바꾸지 않는다(표기만).
원문 대조(조문 MCP 배포본 law_article, 2026-11-16 조회):
  법인세법 시행령 제4조제1항(2024.11.12. 시행본) — 내국법인 최초 사업연도 개시일은 설립등기일
  소득세법 시행령 제40조의2제3항제1호(2024.11.12. 시행본) — 55세 이후 연금수령 개시를 신청한 후 인출
  부가가치세법 제38조제2항(2025.12.31. 기준 시행본) — 매입세액은 공급받는 시기가 속하는 과세기간의 매출세액에서 공제
  부가가치세법 제48조제1항·제49조제1항(같은 시행본) — 예정신고기간·과세기간이 끝난 후 25일 이내 신고(폐업은 폐업일 기준)
  국제조세조정에 관한 법률 제53조제1항(2023.12.31. 기준 시행본) — 해외금융계좌정보는 다음 연도 6월 1일~30일 신고
"""
import json
import re

import openpyxl
import pytest

from korean_tax_calc_mcp import server as S
from korean_tax_calc_mcp.engine.rounding import num_text, pct_text, tidy_amounts
from tests._helpers import call_raw

EXP = re.compile(r"\d(?:\.\d+)?e[+-]?\d+", re.I)


def _err(r):
    return "error" in r, json.dumps(r, ensure_ascii=False)


def _text(r):
    return json.dumps(r, ensure_ascii=False)


# ── (b)5 범위 밖·앞뒤가 안 맞는 날짜 ──────────────────────────────────────────

def test_corporate_filing_established_after_fiscal_year_is_rejected():
    base = dict(year=2024, revenue=500_000_000, revenue_prev=90_000_000_000)
    r = S.corporate_filing_obligations(**base, established_on="2027-03-01")
    assert "error" in r and "설립일이 사업연도 종료일(2024-12-31" in r["error"]
    ok = S.corporate_filing_obligations(**base, established_on="2023-06-01")          # 설립 2년 이내 — 계산
    assert "error" not in ok and any("제4호" in x for x in ok["결과"]["외부세무조정"]["사유"])
    assert "error" in S.corporate_filing_obligations(**base, established_on="2024-02-30")   # 실제 날짜가 아님 — 종전엔 조용히 무시


def test_cfc_fy_end_before_start_year_is_rejected_and_long_year_is_noted():
    base = dict(pretax_incomes=[200_000_001, 0, 0], taxes_paid=[0, 0, 0], ownership_chains=[[1]], related_party=True,
                distributable={"unappropriated_retained_earnings": 1_000_000_000}, year=2023)
    r = S.cfc_deemed_dividend(**base, fy_end="2015-12-31")
    assert "error" in r and any("개시연도 year=2023보다 앞섬" in p for p in r["문제"])
    same = S.cfc_deemed_dividend(**base, fy_end="2024-06-30")       # 비역년 — 그대로
    assert "error" not in same and not any("1년을 넘는지" in n for n in same.get("주의", []))
    long_ = S.cfc_deemed_dividend(**base, fy_end="2025-06-30")
    assert "error" not in long_ and any("1년을 넘는지 확인" in n for n in long_["주의"])
    assert long_["결과"]["배당간주금액"] == same["결과"]["배당간주금액"]


@pytest.mark.parametrize("kw, msg", [
    (dict(start_request_date="2027-01-01"), "인출 연도 year=2026 뒤"),
    (dict(start_request_date="2026-12-31"), None),
])
def test_pension_withdrawal_inconsistent_dates(kw, msg):
    base = dict(year=2026, birth_date="1966-01-01", join_date="2019-01-01", start_request_date="2026-03-01",
                balance_at_period_start=80_000_000, withdrawal=12_000_000, contributions_total=60_000_000, contributions_not_deducted=3_000_000)
    assert "error" not in S.pension_account_withdrawal(**base)
    r = S.pension_account_withdrawal(**{**base, **kw})
    assert ("error" in r and msg in r["error"]) if msg else "error" not in r


def test_withholding_tax_paid_date_must_be_in_year():
    r = S.withholding_tax(kind="사업", amount=20_000, year=2024, paid_date="2027-06-30", continuous_personal_service=True)
    assert "error" in r and "지급연도 year=2024와 다름" in r["error"]
    ok = S.withholding_tax(kind="사업", amount=20_000, year=2024, paid_date="2024-08-30", continuous_personal_service=True)
    assert ok["결과"]["원천징수세액"] == 600


def test_missing_receipt_spent_on_range_and_outside_fiscal_year():
    r = call_raw("missing_receipt_disallowance", {"year": 2020, "items": [{"amount": 50_000, "spent_on": "2027-12-31"}]})
    assert "error" in r and "2016~2026만 지원" in r["error"]
    w = call_raw("missing_receipt_disallowance", {"year": 2020, "items": [{"amount": 50_000, "spent_on": "2022-03-02"}]})
    assert w["결과"]["손금불산입"] == 50_000 and any("사업연도(2020-01-01~2020-12-31) 밖" in n for n in w["주의"])
    assert "주의" not in call_raw("missing_receipt_disallowance", {"year": 2021, "items": [{"amount": 50_000, "spent_on": "2021-03-02"}]})


def test_vat_bad_debt_period_and_supply_after_reason():
    base = dict(bad_debt_incl_vat=11_000_000, reason="부도", reason_date="2026-08-20", supply_date="2024-06-20", receivable="외상매출금", sme=True)
    assert S.vat_bad_debt_credit(**base, period="2027-1")["결과"]["대손세액"] == 1_000_000      # 2026 사유 → 2027-1 확정: 그대로
    assert "error" in S.vat_bad_debt_credit(**base, period="2015-1")
    r = S.vat_bad_debt_credit(**{**base, "supply_date": "2027-06-20"}, period="2026-2")
    assert "error" in r and "공급일이 대손 사유 발생일" in r["error"]


def test_vat_input_tax_supply_after_period_is_rejected():
    item = {"항목": "매입", "성격": "일반", "공급가액": 100_000_000, "증빙": "세금계산서", "공급시기": "2027-02-10"}
    r = S.vat_input_tax_deduction(period="2026-2", filing="확정", items=[item])
    assert "error" in r and any("부가가치세법 제38조제2항" in p for p in r["문제"])
    ok = S.vat_input_tax_deduction(period="2026-2", filing="확정", items=[{**item, "공급시기": "2026-12-10"}])
    assert ok["결과"]["공제매입세액"] == 10_000_000


def test_vat_exempt_use_asset_acquired_after_use_is_rejected():
    assets = [{"구분": "토지", "취득일": "2027-10-05", "취득가액": 50_000_000}, {"구분": "건물", "취득일": "2022-10-05", "취득가액": 40_000_000}]
    r = S.vat_exempt_use_deemed_supply(use_date="2024-10-01", mode="전부", assets=assets)
    assert "error" in r and "전용일 use_date=2024-10-01보다 뒤" in r["문제"][0]
    assert S.vat_exempt_use_deemed_supply(use_date="2024-10-01", mode="전부", assets=assets[1:])["결과"]["과세표준"] == 32_000_000


def test_overseas_account_correction_inside_reporting_year_is_rejected():
    months = [100_000_000, 120_000_000, 300_000_000, 480_000_000, 500_000_000, 520_000_000, 410_000_000, 200_000_000, 100_000_000, 90_000_000, 80_000_000, 70_000_000]
    r = S.overseas_account_reporting(year=2022, month_end_totals_krw=months, corrected_on="2015-07-01")
    assert "error" in r and "2023년 이후" in r["error"]
    assert "error" not in S.overseas_account_reporting(year=2022, month_end_totals_krw=months, corrected_on="2023-07-01")


def test_housing_registration_after_tax_year_is_rejected():
    hs = [{"이름": "A", "기준시가": 300_000_000, "월세": 10_000_000, "등록임대": True, "임대유형": "단기", "아파트": True, "등록신청일": "2027-08-01"},
          {"이름": "B", "기준시가": 300_000_000, "월세": 0}]
    r = S.housing_rental_income(year=2019, houses=hs, other_income_amount=0)
    assert "error" in r and "과세연도 2019년 뒤" in r["문제"][0]


def test_vat_return_filed_on_before_period():
    base = dict(year=2025, period="2", sales_invoice=100_000_000, e_filing=True)
    assert "error" in S.vat_return_general(**base, filed_on="2019-01-01")
    early = S.vat_return_general(**base, filed_on="2025-11-01")
    normal = S.vat_return_general(**base, filed_on="2026-01-25")
    assert any("끝나기 전 날짜" in n for n in early["주의"]) and "주의" not in normal
    assert early["결과"]["차가감_납부세액"] == normal["결과"]["차가감_납부세액"]


def test_bad_debt_and_advance_dates_after_fiscal_year_are_noted():
    r = S.bad_debt_adjustment(year=2025, sme=True, book={"opening": 0, "offset": 0, "provision": 0, "closing": 0},
                              receivables_prev_end_book=0, receivables_end_book=0,
                              writeoffs=[{"kind": "소멸시효완성", "amount": 100_000_000, "arose_in": "전기", "booked": "손비", "date": "2027-03-01"}])
    assert any("사업연도(2025-01-01~2025-12-31) 뒤" in n for n in r["주의"])
    n = S.nonbusiness_interest_disallowance(loans=[{"interest": 10_000_000, "jeoksu": 36_500_000_000}], year=2025,
                                            advances=[{"대상": "대표이사", "사유": "업무무관대여", "금액": 100_000_000, "지급일": "2027-02-01"}])
    assert n["결과"]["손금불산입_합계"] == 0 and any("사업연도(2025-01-01~2025-12-31) 뒤 날짜" in x for x in n["주의"])


# ── (b)9 금액 float·지수 표기 ─────────────────────────────────────────────────

def test_stock_major_shareholder_no_exponent_and_integer_mcap():
    r = S.stock_major_shareholder(transfer_date="2025-06-01", market="코스피", total_shares=10 ** 13, own_shares=19_000, price=1000)
    t = _text(r)
    assert not EXP.search(t) and "0.0001% 미만" in r["결과"]["이유"]
    assert r["계산"]["본인_시가총액"] == 19_000_000 and isinstance(r["계산"]["본인_시가총액"], int)
    big = S.stock_major_shareholder(transfer_date="2025-06-01", market="코스피", total_shares=10 ** 13, own_shares=10 ** 13, price=1000.0016)
    assert isinstance(big["계산"]["본인_시가총액"], int) and not EXP.search(_text(big))
    small = S.stock_major_shareholder(transfer_date="2025-06-01", market="코스피", own_ratio=0.013000000000000001, own_mcap=6e9)
    assert small["계산"]["본인_지분율"] == 0.013 and small["계산"]["본인_시가총액"] == 6_000_000_000


def test_amounts_are_integers_where_tools_passed_floats():
    tg = S.tunnelling_gift(beneficiary="수혜", size="중견", sales_total=100_000_000_000, sales_by_corp={"특관": 40_000_000_000},
                           after_tax_op_profit=10_000_000_000, people={"갑": {"구분": "개인"}, "수혜": {"구분": "법인"}, "특관": {"구분": "법인"}},
                           family=[], stakes=[["갑", "수혜", 0.2], ["갑", "특관", 0.6]], fiscal_year_end="2025-12-31")
    assert isinstance(tg["특수관계법인매출"]["특관"], int)
    dd = S.deemed_dividend_capital_reduction(shareholder_type="개인", event="감자", resolution_date="2025-10-01",
                                             acquisitions=[{"date": "2023-01-01", "shares": 2000, "kind": "유상취득", "unit_cost": 5000}],
                                             cash_received=3_000_000, cancelled_shares=500, par_value=500)
    assert all(isinstance(v, int) for k, v in dd["결과"].items() if k in ("평균단가", "소각후_1주당_장부가액"))


def test_sme_reduction_headcount_text_has_no_exponent():
    r = S.sme_special_tax_reduction(year=2025, size="소기업", hq_in_capital_area=True, industry_group="도매업등", tax=75_000_000,
                                    taxable_base=500_000_000, employees_prev=10 ** 13, employees_now=0)
    assert "10,000,000,000,000명 감소" in _text(r) and not EXP.search(_text(r))
    r2 = S.sme_special_tax_reduction(year=2025, size="소기업", hq_in_capital_area=True, industry_group="도매업등", tax=75_000_000,
                                     taxable_base=500_000_000, employees_prev=10.5, employees_now=8)
    assert "2.5명 감소" in _text(r2)


def test_treaty_rate_error_has_no_exponent():
    r = S.nonresident_withholding(income_kind="배당", amount=10_000_000, recipient_type="법인", residence_country="일본", year=2025, treaty_rate=10 ** 13)
    assert "error" in r and not EXP.search(_text(r)) and "10,000,000,000,000" in _text(r)


def test_rounding_helpers():
    assert tidy_amounts({"연도별": {"2022": {"매출": 25_000_000.0, "지표%": 1.5}}, "공제율": 1.0, "점수": 5.0, "매출액": 0.5}) == \
        {"연도별": {"2022": {"매출": 25_000_000, "지표%": 1.5}}, "공제율": 1.0, "점수": 5.0, "매출액": 0.5}
    assert isinstance(tidy_amounts({"금액": 3.0})["금액"], int) and isinstance(tidy_amounts({"공제율": 1.0})["공제율"], float)
    assert pct_text(0.015) == "1.5%" and pct_text(1.9e-9) == "0.0001% 미만" and pct_text(0.013000000000000001) == "1.3%"
    assert num_text(1e13) == "10,000,000,000,000" and num_text(2.5) == "2.5" and num_text(3e-7) == "0.01 미만"


# ── (b)7 문장 잘림 ─────────────────────────────────────────────────────────────

def _unclosed(s):
    for o, c in ("()", "[]"):
        d = 0
        for ch in s:
            if ch == o:
                d += 1
            elif ch == c and d:
                d -= 1
        if d:
            return True
    return False


@pytest.mark.parametrize("q", ["해외금융계좌", "주식 양도세", "비상장주식 평가", "엑셀 서식", "금융소득", "여러 해 세무조정", "부당행위 양도",
                               "국제거래명세서", "대주주", "검산", "법인세"])
def test_find_tool_descriptions_end_at_sentence_or_comma(q):
    for c in S.find_tool(q)["결과"]["후보"]:
        for k in ("설명", "국문 설명", "언제"):
            s = c[k]
            assert not _unclosed(s), (c["도구"], k, s)
            assert len(s) <= 202
            if len(s) > 150:          # 길이 제한에 걸린 것은 문장 끝(.) 또는 쉼표·가운뎃점 경계에서 '…'로 끝남
                assert s.endswith((".", "…", ")", "다.", "함.")), (c["도구"], k, s)
        assert "언제:" not in c["국문 설명"]


def test_clip_text_keeps_parentheses_whole():
    from korean_tax_calc_mcp.server import _clip_text
    s = "가나다 계산(소득세법 제1조·제2조·제3조, 시행령 제4조(1항·2항)·제5조)과 그 밖의 긴 설명이 이어지는 문장, 그리고 또 다른 구절이 계속됨"
    out = _clip_text(s, 40)
    assert not _unclosed(out) and out.endswith("…")
    assert _clip_text("짧은 문장.", 40) == "짧은 문장."


def test_integrated_investment_graduated_sentence_is_complete():
    r = S.integrated_investment_credit(year=2025, size="졸업 뒤 3년", graduated_year=2023, investments=[{"kind": "일반", "amount": 1_000_000_000}])
    assert any(p.endswith("size='일반'으로 다시 계산하세요") for p in r["판단"] if isinstance(p, str))


def test_docstrings_have_balanced_parentheses():
    cat = S._tool_catalog()
    for name in ("overseas_account_reporting", "capital_gains_unfair_transaction"):
        assert not _unclosed(cat[name].splitlines()[2]), name


# ── (b)8 개발자 표기 오류 안내 ─────────────────────────────────────────────────

@pytest.mark.parametrize("tool, args, want", [
    ("expat_cost_recharge", dict(year=2024, items=[{"이름": "파견A", "급여": -1, "귀속": "현지법인"}]), "급여 — 0 이상의 원 단위 정수로 넣으세요"),
    ("expat_cost_recharge", dict(year=2024, items=[{"이름": "파견A", "급여": 1, "귀속": "현지법인", "마크업": -0.1}]), "마크업 — 0 이상의 소수로 넣으세요(예: 5%면 0.05)"),
    ("foreign_subsidiary_dividend", dict(ownership_ratio=1.0, held_months=4, dividend=0, received_on="2026-06-30"), "dividend — 0보다 큰 원 단위 정수로"),
    ("corporate_filing_obligations", dict(year=2024, liabilities=-5), "liabilities — 0 이상의 원 단위 정수로"),
])
def test_error_messages_are_plain(tool, args, want):
    r = call_raw(tool, args)
    t = _text(r)
    assert want in t, t
    assert not re.search(r"int ?[≥>]|소수≥|\bbool\b|dict 아님", t)


def test_no_type_notation_left_in_error_strings_in_source():
    import pathlib
    root = pathlib.Path(S.__file__).parent
    bad = []
    for f in list(root.glob("*.py")) + list(root.glob("engine/*.py")) + list(root.glob("audit/**/*.py")):
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"(error|문제|problems|raise|필요입력|필요 입력).*([은는] (원 )?int\b|int[≥>]|소수≥0|=int 필요|=dict 필요|dict 아님|\"bool\"|\"bool\()", line):
                bad.append(f"{f.name}:{i}")
    assert not bad, bad


# ── (b)6 영문 모드 결과 JSON 키 ─────────────────────────────────────────────────

def test_export_workbook_en_result_keys_are_english(tmp_path):
    r = call_raw("export_workbook", {"title": "en keys", "lang": "en", "output_dir": str(tmp_path),
                                     "calls": [{"label": "법인세", "tool": "corporate_tax", "args": {"base": 300_000_000, "year": 2025}}]})
    res = r["result"]
    assert {"file", "sheets", "call_count", "failed_calls", "file_note"} <= set(res) and r["basis"].startswith("Summary of calculation tool results")
    assert not any(re.search(r"[가-힣]", k) for k in res)
    assert res["file_note"].startswith("Re-saving this file")
    ko = call_raw("export_workbook", {"title": "ko keys", "output_dir": str(tmp_path),
                                      "calls": [{"label": "법인세", "tool": "corporate_tax", "args": {"base": 300_000_000, "year": 2025}}]})
    assert "결과" in ko and "파일" in ko["결과"]          # 국문 모드는 그대로


def test_verify_workbook_en_result_keys_are_english(tmp_path):
    p = tmp_path / "w.xlsx"
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "계산"; ws["A2"] = "산출세액"; ws["B2"] = 37_000_000; wb.save(p)
    r = call_raw("verify_workbook", {"path": str(p), "lang": "en", "checks": [{"cell": "계산!B2", "tool": "corporate_tax", "args": {"base": 300_000_000, "year": 2025}}]})
    res = r["result"]
    assert {"summary", "checks", "mismatches", "unchecked_amounts", "next_step", "copy"} <= set(res)
    assert {"checked", "matched", "mismatched", "unreadable", "tool_errors"} <= set(res["summary"])
    row = res["checks"][0]
    assert {"cell", "item", "method", "verdict", "workbook_value", "tool_value"} <= set(row) and row["verdict"] == "match" and row["method"] == "explicit"
    assert r["limits"] and not any(re.search(r"[가-힣]", s) for s in r["limits"])
    assert res["summary"]["matched"] == 1


# ── (b)10 고정 '확인 필요' 문구 ──────────────────────────────────────────────────

def test_nonresident_issues_have_checklists_not_fixed_judgement():
    base = dict(income_kind="사용료", amount=200_000_000, recipient_type="개인", residence_country="US")
    with_rate = S.nonresident_withholding(**base, treaty_rate=0.15)["쟁점"]
    without = S.nonresident_withholding(**base)["쟁점"]
    assert all("판단" not in it and it["확인할 자료"] for it in with_rate + without)
    relief = lambda iss: next(it for it in iss if it.get("구분") == "조약 적용 절차")["확인할 자료"]
    assert not any("treaty_rate" in x for x in relief(with_rate)) and any("treaty_rate" in x for x in relief(without))


def test_thin_cap_issue_depends_on_loans():
    plain = S.thin_capitalization(equity=2_000_000_000, borrowings=5_000_000_000, total_interest=300_000_000, ratio=2)["쟁점"]
    assert "보증·간접차입" in plain[0]["쟁점"] and "판단" not in plain[0]
    loans = S.thin_capitalization(equity=1_000_000_000, ratio=2, year=2025,
                                  loans=[{"kind": "직접", "rate": 0.05, "balance": 3_000_000_000}])["쟁점"]
    assert "loans 입력대로" in loans[0]["쟁점"] and "보증·간접차입" not in loans[0]["쟁점"]


def test_capital_gains_withholding_limit_only_with_acquisition_cost():
    base = dict(seller_type="개인", asset_kind="주식", year=2018, gross_price=10_000_000)
    assert not any("양도차익은" in x for x in S.nonresident_capital_gains_withholding(**base)["한계"])
    assert any(x.startswith("양도차익은") and "확인할 것" in x for x in S.nonresident_capital_gains_withholding(**base, acquisition_cost=4_000_000)["한계"])


def test_unlisted_valuation_items_are_checklists_and_ftc_has_no_empty_check():
    r = S.unlisted_stock_valuation(valuation_date="2017-10-01", shares=100_000, net_asset=800_000_000,
                                   incomes=[{"사업연도": 2016, "순손익액": 6_000_000}, {"사업연도": 2015, "순손익액": 6_000_000}, {"사업연도": 2014, "순손익액": 6_000_000}])
    assert not any(j["항목"] == "확인 필요" for j in r["판단"]) and any(j["항목"] == "확인할 것" for j in r["판단"])
    f = S.foreign_tax_credit(year=2025, base=100_000_000, base_includes_grossup=False, method="세액공제",
                             countries=[{"country": "미국", "foreign_income": 30_000_000, "direct_tax": 2_000_000}], months=6)
    assert "확인 필요" not in f["결과"]
