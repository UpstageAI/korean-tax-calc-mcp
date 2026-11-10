"""경정청구 기한(refund_claim_deadline)·기한 특례(국세기본법 제5조제1항)·도구 설명 원문자 금지.

조문(국세기본법, 2025.12.31. 기준 law_article로 대조):
- 제45조의2제1항 본문: 법정신고기한이 지난 후 5년 이내.
- 제45조의2제1항 단서: 결정·경정으로 증가된 세액은 처분이 있음을 안 날(통지를 받은 날)부터 3개월 이내(법정신고기한이 지난 후 5년 이내로 한정).
  2024.12.31. 개정(법률 제20611호, 2025.1.1. 시행) 전에는 90일. 부칙 제6조제1항: 시행 당시 안 날부터 3개월이 지나지 않았으면 3개월.
- 제45조의2제2항: 후발적 사유가 발생한 것을 안 날부터 3개월 이내.
- 제5조제1항: 신고·청구 등의 기한이 토요일·일요일, 공휴일·대체공휴일, 근로자의 날(노동절)이면 그 다음 날.
- 제4조: 기간 계산은 민법(초일 불산입, 역에 의한 계산, 말일에 해당일이 없으면 그 달 말일).
"""
import asyncio
import json
import re

from korean_tax_calc_mcp import server as S
from tests._helpers import call as run


def res(r):
    assert "결과" in r, r
    return r["결과"]


# ── 필수 사례: 2023 사업연도 법인세(12월 결산) 통상 경정청구 ──
def test_corporate_2023_ordinary_claim_required_case():
    r = run("refund_claim_deadline", {"kind": "통상", "tax": "법인세", "year": 2023})
    x = res(r)
    assert x["법정신고기한"]["법령상"].startswith("2024-03-31")
    assert x["법정신고기한"]["적용"] == "2024-04-01(월)"
    assert x["기간_말일"].startswith("2029-04-01")
    assert x["경정청구_기한"] == "2029-04-02"
    assert x["요일"] == "월"
    s = json.dumps(r, ensure_ascii=False)
    assert "제45조의2제1항" in s and "제5조제1항" in s


def test_same_case_by_fiscal_year_end_and_by_due_date():
    a = res(run("refund_claim_deadline", {"kind": "통상", "tax": "법인세", "fiscal_year_end": "2023-12-31"}))
    b = res(run("refund_claim_deadline", {"kind": "통상", "due_date": "2024-03-31"}))
    assert a["경정청구_기한"] == b["경정청구_기한"] == "2029-04-02"


def test_outside_holiday_table_is_flagged():
    r = run("refund_claim_deadline", {"kind": "통상", "tax": "법인세", "year": 2023})
    s = json.dumps(r, ensure_ascii=False)
    assert "공휴일표" in s and "2029" in s and "확인하지 못함" in s


def test_inside_table_no_flag():
    # 2020 귀속 종합소득세: 2021-05-31(월) → 5년 2026-05-31(일) → 2026-06-01(월). 2026년은 표 안
    r = run("refund_claim_deadline", {"kind": "통상", "tax": "소득세", "year": 2020})
    x = res(r)
    assert x["법정신고기한"]["적용"] == "2021-05-31(월)"
    assert x["경정청구_기한"] == "2026-06-01"
    assert "확인하지 못함" not in json.dumps(r, ensure_ascii=False)


def test_corporate_fiscal_year_june_and_sincere_filing():
    # 6월 결산: 사업연도 종료일이 속하는 달의 말일부터 3개월 → 9.30.
    x = res(run("refund_claim_deadline", {"kind": "통상", "tax": "법인세", "fiscal_year_end": "2024-06-30"}))
    assert x["법정신고기한"]["법령상"].startswith("2024-09-30")
    # 성실신고확인서 제출 법인 4개월(법인세법 제60조제1항 괄호) — 2024-04-30(화)
    y = res(run("refund_claim_deadline", {"kind": "통상", "tax": "법인세", "year": 2023, "sincere_filing": True}))
    assert y["법정신고기한"]["법령상"].startswith("2024-04-30")
    assert y["경정청구_기한"] == "2029-04-30"


def test_vat_due_date_rolls_over_lunar_new_year_and_temporary_holiday():
    # 2024년 제2기 확정신고기한 2025-01-25(토) → 26(일) → 27(임시공휴일) → 28~30(설) → 2025-01-31(금)
    x = res(run("refund_claim_deadline", {"kind": "통상", "tax": "부가가치세", "period": "2024-2"}))
    assert x["법정신고기한"]["법령상"].startswith("2025-01-25")
    assert x["법정신고기한"]["적용"] == "2025-01-31(금)"
    assert len(x["법정신고기한"]["건너뛴 날"]) == 6
    assert x["경정청구_기한"] == "2030-01-31"


def test_income_tax_due_date_saturday():
    # 2024 귀속 종합소득세 2025-05-31(토) → 2025-06-02(월)
    x = res(run("refund_claim_deadline", {"kind": "통상", "tax": "소득세", "year": 2024}))
    assert x["법정신고기한"]["적용"] == "2025-06-02(월)"


def test_gift_and_inheritance_due_dates():
    g = res(run("refund_claim_deadline", {"kind": "통상", "tax": "증여세", "tax_base_date": "2024-01-15"}))
    assert g["법정신고기한"]["법령상"].startswith("2024-04-30")
    h = res(run("refund_claim_deadline", {"kind": "통상", "tax": "상속세", "tax_base_date": "2024-01-15"}))
    assert h["법정신고기한"]["법령상"].startswith("2024-07-31")
    h9 = res(run("refund_claim_deadline", {"kind": "통상", "tax": "상속세", "tax_base_date": "2024-01-15", "abroad": True}))
    assert h9["법정신고기한"]["법령상"].startswith("2024-10-31")


# ── 후발적 경정청구(제45조의2제2항): 안 날부터 3개월 ──
def test_subsequent_claim_three_months_sunday():
    # 2025-03-15에 안 날 → 2025-06-15(일) → 2025-06-16(월)
    x = res(run("refund_claim_deadline", {"kind": "후발적", "event_date": "2025-03-15"}))
    assert x["기간_말일"].startswith("2025-06-15")
    assert x["경정청구_기한"] == "2025-06-16"


def test_subsequent_claim_chuseok_chain():
    # 2025-07-05 → 2025-10-05(일·추석 전날) → 6·7 추석 → 8 대체공휴일 → 9 한글날 → 2025-10-10(금)
    x = res(run("refund_claim_deadline", {"kind": "후발적", "event_date": "2025-07-05"}))
    assert x["경정청구_기한"] == "2025-10-10"
    reasons = " ".join(d["사유"] for d in x["건너뛴 날"])
    assert "추석" in reasons and "대체공휴일" in reasons and "한글날" in reasons


def test_subsequent_claim_month_end_clamp():
    # 2023-11-30 → 3개월 뒤 같은 날 없음 → 2024-02-29(목, 윤년 말일)
    x = res(run("refund_claim_deadline", {"kind": "후발적", "event_date": "2023-11-30"}))
    assert x["경정청구_기한"] == "2024-02-29"


def test_subsequent_claim_shows_ordinary_too_when_due_given():
    r = run("refund_claim_deadline", {"kind": "후발적", "event_date": "2025-03-15", "tax": "법인세", "year": 2023})
    x = res(r)
    assert x["경정청구_기한"] == "2025-06-16"
    assert x["통상_경정청구_기한"] == "2029-04-02"


def test_subsequent_claim_needs_event_date():
    r = run("refund_claim_deadline", {"kind": "후발적"})
    assert "error" in r and "event_date" in json.dumps(r, ensure_ascii=False)


# ── 증액 결정·경정분(제45조의2제1항 단서) ──
def test_increase_notice_three_months_after_2025():
    # 2025-02-10 통지 → 2025-05-10(토) → 11(일) → 2025-05-12(월)
    x = res(run("refund_claim_deadline", {"kind": "증액경정", "event_date": "2025-02-10", "tax": "법인세", "year": 2023}))
    assert x["경정청구_기한"] == "2025-05-12"
    assert x["적용_기간"] == "3개월"


def test_increase_notice_capped_by_five_years():
    # 2019 귀속 소득세: 2020-05-31(일) → 2020-06-01(월) → 5년 2025-06-01(일) → 2025-06-02(월). 통지 2025-04-01 + 3개월 = 2025-07-01 → 5년 한도로 2025-06-02
    x = res(run("refund_claim_deadline", {"kind": "증액경정", "event_date": "2025-04-01", "tax": "소득세", "year": 2019}))
    assert x["경정청구_기한"] == "2025-06-02"
    assert "5년" in x["판정"]


def test_increase_notice_old_90_days_and_labor_day():
    # 2024-02-01 통지 → 3개월이 2024-05-01로 2025.1.1. 전에 지남 → 종전 90일 → 2024-05-01(근로자의 날) → 2024-05-02(목)
    x = res(run("refund_claim_deadline", {"kind": "증액경정", "event_date": "2024-02-01", "tax": "법인세", "year": 2022}))
    assert x["적용_기간"] == "90일"
    assert x["경정청구_기한"] == "2024-05-02"
    assert any("근로자의 날" in d["사유"] for d in x["건너뛴 날"])


def test_increase_notice_transition_addendum():
    # 2024-10-15 통지 → 3개월 2025-01-15 — 2025.1.1. 당시 3개월이 지나지 않음 → 개정 3개월(부칙 제6조제1항)
    r = run("refund_claim_deadline", {"kind": "증액경정", "event_date": "2024-10-15", "tax": "법인세", "year": 2022})
    x = res(r)
    assert x["적용_기간"] == "3개월"
    assert x["경정청구_기한"] == "2025-01-15"
    assert "부칙 제6조제1항" in json.dumps(r, ensure_ascii=False)


def test_increase_notice_needs_due_date():
    r = run("refund_claim_deadline", {"kind": "증액경정", "event_date": "2025-02-10"})
    assert "error" in r


# ── 입력 오류 ──
def test_bad_inputs():
    assert "error" in run("refund_claim_deadline", {"kind": "통상", "due_date": "2024-02-30"})
    assert "error" in run("refund_claim_deadline", {"kind": "통상"})
    assert "error" in run("refund_claim_deadline", {"kind": "통상", "tax": "부가가치세", "period": "2024-3"})
    assert "error" in run("refund_claim_deadline", {"kind": "후발적", "event_date": "2015-06-01"})


def test_withholding_and_comprehensive_real_estate():
    w = res(run("refund_claim_deadline", {"kind": "통상", "tax": "원천징수", "year": 2023}))
    assert w["법정신고기한"]["법령상"].startswith("2024-03-10")    # 연말정산분 납부기한 3.10.(일) → 3.11.(월)
    assert w["법정신고기한"]["적용"] == "2024-03-11(월)"
    c = res(run("refund_claim_deadline", {"kind": "통상", "tax": "종합부동산세", "year": 2023}))
    assert c["법정신고기한"]["법령상"].startswith("2023-12-15")


# ── find_tool 경로 ──
def test_find_tool_routes_claim_deadline_queries():
    for q in ("경정청구기간 계산", "경정청구 기한", "후발적 경정청구 언제까지"):
        r = run("find_tool", {"query": q})
        names = [c["도구"] for c in r["결과"]["후보"]]
        assert names and names[0] == "refund_claim_deadline", (q, names)


# ── assessment_limitation도 기한 특례를 같은 방식으로 ──
def test_assessment_limitation_applies_deadline_rule_to_due_date():
    r = run("assessment_limitation", {"due_date": "2024-03-31"})
    x = res(r)
    assert x["법정신고기한(적용)"] == "2024-04-01(월)"
    assert x["만료일"] == "2029-04-02"          # 2024-04-01 + 5년 = 2029-04-01(일) → 다음 날
    assert x["만료일(역법)"].startswith("2029-04-01")
    s = json.dumps(r, ensure_ascii=False)
    assert "제26조의2제6항" in s and "refund_claim_deadline" in s


def test_assessment_limitation_weekday_due_unchanged():
    x = res(run("assessment_limitation", {"due_date": "2024-01-10", "offshore": True, "withholding": True}))
    assert x["만료일"] == "2031-01-10"
    assert x["법정납부기한(적용)"] == "2024-01-10(수)"   # 원천징수분은 법정납부기한


# ── 도구 설명에 원문자(①②…) 금지 — 일부 클라이언트에서 '124'로 풀려 조문 번호와 붙어 읽힘 ──
_CIRCLED = re.compile("[①-⓿❶-➓㉑-㉟㊱-㊿]")


def test_no_circled_numbers_in_tool_descriptions():
    bad = []
    for t in asyncio.run(S.mcp.list_tools()):
        text = (t.description or "") + json.dumps(t.input_schema, ensure_ascii=False)
        if _CIRCLED.search(text):
            bad.append((t.name, sorted(set(_CIRCLED.findall(text)))))
    assert not bad, bad


def test_assessment_limitation_description_reads_as_text():
    t = next(t for t in asyncio.run(S.mcp.list_tools()) if t.name == "assessment_limitation")
    assert "제26조의2제1항·제2항·제4항" in t.description


def test_readme_tool_count_matches():
    n = len(asyncio.run(S.mcp.list_tools()))
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    assert f"## 도구 ({n}개)" in (root / "README.md").read_text(encoding="utf-8")
    assert f"## Tools ({n})" in (root / "README-EN.md").read_text(encoding="utf-8")
    assert f"{n} tools" in (root / "server.json").read_text(encoding="utf-8")
    assert "`refund_claim_deadline`" in (root / "README.md").read_text(encoding="utf-8")
