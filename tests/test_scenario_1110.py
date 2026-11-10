"""통합 시나리오(2026-11-10) 결함 6건 수정 검증 — 0.25.5 (Claude 보완, 뼈대 Solar Pro 4).

① simplified_vat_return 예정부과세액 공제·환급(부가가치세법 제67조②·제69조④)
② deemed_bonus_resettlement 표준세액공제(소득세법 제59조의4⑨·제137조③)
③ corporate_tax·minimum_tax 원 미만 절사(국고금 관리법 제47조 — 종전 반올림)
④ find_tool 별칭(소득처분·인정상여·재정산·업무무관 경비·부가가치세)
⑤ 납부지연가산세 until == due → 0, due가 토·일·공휴일이면 주의(국세기본법 제5조①)
⑥ vat_input_tax_deduction 영 제75조7호 — 수정신고·경정청구·결정·경정 조건 주의
"""
import pathlib
import shutil

import pytest

from _helpers import call as c
from korean_tax_calc_mcp.engine import calc_cit as C, calc_income as I

M = 1_000_000


# ── ① 간이과세자 원장형: 예정부과세액 공제·환급 ─────────────────────────────────────
_LEDGER_A = {"공급": [{"항목": "카드 매출", "금액": 50 * M}, {"항목": "현금 매출", "금액": 28 * M}],
             "매입": [{"항목": "세금계산서 수취 매입", "금액": 20 * M}, {"항목": "세금계산서 미수취 매입", "금액": 5 * M}]}
_ARGS_A = {"supply_incl_vat": 78 * M, "value_added_rate": 0.15, "invoice_purchase_incl_vat": 20 * M,
           "card_cash_receipt_supply_incl_vat": 50 * M, "no_invoice_purchase_incl_vat": 5 * M,
           "prior_year_supply_incl_vat": 60 * M, "prepaid_tax": 500_000, "year": 2025}


def test_simplified_vat_return_refund_matches_vat_simplified_taxpayer():
    """음식점업 2025(부가가치율 15%): 납부세액 78,000,000×15%×10% = 1,170,000(제63조②);
    세금계산서등수취세액공제 20,000,000×0.5% = 100,000(제63조③1호); 카드발급세액공제 50,000,000×1.3% = 650,000(제46조①3호);
    공제후 420,000; 미수취가산세 5,000,000×0.5% = 25,000(제68조의2②1호, 직전연도 6천만 ≥ 4,800만);
    차가감 = 420,000 + 25,000 − 예정부과 500,000 = −55,000 → 환급세액 55,000(제67조②). 종전은 max(0, …)으로 0이 나와 환급을 삼켰다."""
    r = c("simplified_vat_return", {"year": 2025, "business_type": "음식점업", "ledger": _LEDGER_A,
                                     "prepaid_assessed": 500_000, "prior_year_supplies": 60 * M})
    assert "error" not in r, r
    assert r["계산"]["공제후세액"] == 420_000 and r["계산"]["세금계산서미수취가산세"] == 25_000
    assert r["결과"]["납부의무면제"] is False
    assert (r["결과"]["예정부과세액_공제"], r["결과"]["차가감납부세액"], r["결과"]["환급세액"]) == (500_000, -55_000, 55_000)
    s = c("vat_simplified_taxpayer", _ARGS_A)["결과"]
    assert (s["예정부과세액_공제"], s["차가감_납부세액"], s["환급세액"]) == (500_000, -55_000, 55_000)
    assert s["납부의무_면제"] is False


def test_simplified_vat_return_exempt_refund_after_penalty():
    """공급대가 45,000,000 < 4,800만 → 납부의무 면제(제69조①): 납부세액 0, 공제 0이나 미수취가산세 25,000은 남음(제69조②는 제60조①만 배제);
    자진 납부한 예정부과세액 200,000은 가산세 충당 뒤 175,000 환급(제69조④): 차가감 = 0 + 25,000 − 200,000 = −175,000.
    종전은 차가감 0·환급 없음. vat_simplified_taxpayer(0.25.1)와 같은 값."""
    ledger = {"공급": [{"항목": "카드 매출", "금액": 30 * M}, {"항목": "현금 매출", "금액": 15 * M}],
              "매입": [{"항목": "세금계산서 미수취 매입", "금액": 5 * M}]}
    r = c("simplified_vat_return", {"year": 2025, "business_type": "음식점업", "ledger": ledger,
                                     "prepaid_assessed": 200_000, "prior_year_supplies": 60 * M})
    assert "error" not in r, r
    assert r["결과"]["납부의무면제"] is True and r["계산"]["납부세액"] == 0
    assert r["계산"]["세금계산서미수취가산세"] == 25_000
    assert (r["결과"]["예정부과세액_공제"], r["결과"]["차가감납부세액"], r["결과"]["환급세액"]) == (200_000, -175_000, 175_000)
    assert any(p["항목"] == "면제 사업자 예정부과세액 환급" and "제69조④" in p["근거"] for p in r["판단"])
    s = c("vat_simplified_taxpayer", {"supply_incl_vat": 45 * M, "value_added_rate": 0.15, "card_cash_receipt_supply_incl_vat": 30 * M,
                                      "no_invoice_purchase_incl_vat": 5 * M, "prior_year_supply_incl_vat": 60 * M,
                                      "prepaid_tax": 200_000, "year": 2025})["결과"]
    assert s["납부의무_면제"] is True and (s["가산세"], s["차가감_납부세액"], s["환급세액"]) == (25_000, -175_000, 175_000)


def test_simplified_vat_return_no_prepaid_unchanged():
    """예정부과세액 0이면 종전과 같음: 차가감 = 420,000 + 25,000 = 445,000, 환급 0."""
    r = c("simplified_vat_return", {"year": 2025, "business_type": "음식점업", "ledger": _LEDGER_A,
                                     "prepaid_assessed": 0, "prior_year_supplies": 60 * M})
    assert (r["결과"]["예정부과세액_공제"], r["결과"]["차가감납부세액"], r["결과"]["환급세액"]) == (0, 445_000, 0)


# ── ② 인정상여 재정산: 표준세액공제 ─────────────────────────────────────────────
def test_deemed_bonus_resettlement_includes_standard_credit():
    """총급여 120,000,000·과세표준 103,350,000·상여 29,719,452(2025).
    당초: 산출세액 103,350,000×35% − 15,440,000 = 20,732,500(제55조①), 근로소득세액공제 500,000(제59조①, 총급여 7천만 초과 하한),
      표준세액공제 130,000(제59조의4⑨) → 결정세액 20,102,500 = wage_income_tax(gross_pay=120,000,000) 결정세액(참고).
    재정산: 총급여 149,719,452, 근로소득공제 14,750,000 + 49,719,452×2% = 15,744,389(제47조①), 당초 15,150,000 → 과세표준
      103,350,000 + 29,719,452 − 594,389 = 132,475,063; 산출세액 132,475,063×35% − 15,440,000 = 30,926,272; 근로소득세액공제 200,000
      (총급여 1.2억 초과 하한); 표준세액공제 130,000 → 30,596,272. 추가 원천징수 = 30,596,272 − 20,102,500 = 10,493,772(제137조③·영 제192조).
    종전은 표준세액공제를 빼지 않아 20,232,500 / 30,726,272 — 차액은 같았지만 wage_income_tax 결정세액을 prev_decided로 주면 +130,000 틀렸다."""
    base = {"gross_pay": 120 * M, "tax_base": 103_350_000, "bonus": 29_719_452, "year": 2025}
    r = c("deemed_bonus_resettlement", base)["결과"]
    assert (r["당초결정세액"], r["재정산결정세액"], r["추가원천징수세액"]) == (20_102_500, 30_596_272, 10_493_772)
    assert r["표준세액공제"] == {"재정산": 130_000, "당초": 130_000}
    w0 = c("wage_income_tax", {"gross_pay": 120 * M, "year": 2025})["결과"]
    w1 = c("wage_income_tax", {"gross_pay": 149_719_452, "year": 2025})["결과"]
    assert (w0["결정세액(참고)"], w1["결정세액(참고)"]) == (20_102_500, 30_596_272)
    # wage_income_tax 결정세액(표준세액공제 반영 후)을 prev_decided로 줘도 같은 추가 원천징수세액
    r2 = c("deemed_bonus_resettlement", base | {"prev_decided": 20_102_500})["결과"]
    assert (r2["당초결정세액"], r2["재정산결정세액"], r2["추가원천징수세액"]) == (20_102_500, 30_596_272, 10_493_772)
    # other_credits에 표준세액공제 13만 원을 직접 넣으면(택일) 같은 값 — 표준세액공제를 겹쳐 빼지 않음
    r3 = c("deemed_bonus_resettlement", base | {"other_credits": 130_000})["결과"]
    assert (r3["당초결정세액"], r3["재정산결정세액"], r3["추가원천징수세액"]) == (20_102_500, 30_596_272, 10_493_772)
    assert r3["표준세액공제"]["재정산"] == 0


def test_deemed_bonus_resettlement_engine_tc22_with_standard_credit():
    """TC-22(총급여 8천만·과세표준 61,250,000·상여 3천만, 2025): 종전 당초 8,440,000 / 재정산 15,577,500에서 표준세액공제 130,000씩(제59조의4⑨) 빠져
    8,310,000 / 15,447,500, 추가 원천징수 7,137,500은 그대로."""
    r = I.deemed_bonus_resettlement(80 * M, 61_250_000, 30 * M)
    assert (r["당초결정세액"], r["재정산과세표준"], r["재정산결정세액"], r["추가원천징수세액"]) == (8_310_000, 90_050_000, 15_447_500, 7_137_500)


# ── ③ 산출세액 원 미만 절사 ────────────────────────────────────────────────────
def test_corporate_tax_truncates_won():
    """과세표준 353,719,452(2025, 제55조①: 2억 이하 9%·초과 19%): 18,000,000 + 153,719,452×19% = 47,206,695.88 → 47,206,695(원 미만 절사,
    국고금 관리법 제47조 끝수 계산). 종전 반올림은 47,206,696."""
    r = c("corporate_tax", {"base": 353_719_452, "year": 2025})["결과"]
    assert r["산출세액"] == 47_206_695
    assert C.corp_tax(353_719_452, 2025) == 47_206_695
    # 1년 미만 사업연도(연 환산 경로)도 절사: 62,586,115·11개월 → ×12/11 → 9% → ×11/12 = 62,586,115×9% = 5,632,750.35 → 5,632,750
    assert C.corp_tax(62_586_115, 2025, 11) == 5_632_750
    # 정수로 떨어지는 값은 그대로(2억 × 9% = 18,000,000)
    assert C.corp_tax(200 * M, 2025) == 18 * M


def test_minimum_tax_truncates_won():
    """감면 전 과세표준 353,719,452 × 중소기업 7%(조특법 제132조①) = 24,760,361.64 → 24,760,361(원 미만 절사, 국고금 관리법 제47조). 종전 24,760,362."""
    assert c("minimum_tax", {"base_before_incentives": 353_719_452, "year": 2025, "sme": True})["결과"]["최저한세"] == 24_760_361
    assert C.min_tax(353_719_452, sme=True, year=2025) == 24_760_361
    # 일반기업 구간표도 절사: 353,719,452 × 10% = 35,371,945.2 → 35,371,945
    assert C.min_tax(353_719_452, sme=False, year=2025) == 35_371_945


@pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice 없음")
def test_byeolji3_formula_rounddown_matches_tool(tmp_path):
    """별지3 115 산출세액 칸의 서식 수식이 ROUNDDOWN(…,0)으로 도구 값(원 미만 절사) 47,206,695와 같아야 한다 — LibreOffice 재계산."""
    import openpyxl
    from test_form_templates import build, recalc
    calls = [{"label": "각사업연도소득", "tool": "income_adjustment_total",
              "args": {"net_income": 289_369_452, "items": [{"항목": "가산 합계", "종류": "기타", "금액": 69_350_000, "방향": "가산", "소득처분": "기타"},
                                                           {"항목": "차감 합계", "종류": "기타", "금액": 5_000_000, "방향": "차감", "소득처분": "기타"}]}},
             {"label": "법인세 산출세액", "tool": "corporate_tax", "args": {"base": 353_719_452, "year": 2025}}]
    path = build(tmp_path, calls)
    raw = openpyxl.load_workbook(path)
    s3 = next(n for n in raw.sheetnames if n.startswith("별지3"))
    assert raw[s3]["F20"].value.startswith("=ROUNDDOWN((MAX(0,")
    wb = recalc(path, tmp_path)
    assert wb[s3]["F20"].value == 47_206_695


# ── ④ find_tool 별칭 ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("query, expected", [
    ("법인세 세무조정 접대비 가지급금 인정이자 소득처분 상여 연말정산 재정산", {"deemed_bonus_resettlement", "income_adjustment_total"}),
    ("인정상여 재정산 추가 원천징수", {"deemed_bonus_resettlement"}),
    ("대표이사 개인 경비 법인 지출", {"income_adjustment_total", "deemed_bonus_resettlement"}),
    ("부가가치세", {"vat_simplified_taxpayer", "common_input_tax", "vat_bad_debt_credit", "vat_input_tax_deduction"}),
    ("지연수취", {"vat_input_tax_deduction"}),
])
def test_find_tool_scenario_queries_top5(query, expected):
    """통합 시나리오에서 find_tool 상위 5에 안 나오던 다섯 질의 — 별칭(소득처분·인정상여·재정산·개인 경비·부가가치세·지연수취) 추가 뒤 상위 5 안."""
    r = c("find_tool", {"query": query, "n": 5})
    names = [x["도구"] for x in r["결과"]["후보"]]
    assert expected <= set(names), (query, names)


def test_find_tool_first_query_top_is_resettlement_family():
    """첫 질의는 소득처분 → 재정산 흐름이라 income_adjustment_total·deemed_bonus_resettlement가 1·2위."""
    r = c("find_tool", {"query": "법인세 세무조정 접대비 가지급금 인정이자 소득처분 상여 연말정산 재정산", "n": 5})
    assert [x["도구"] for x in r["결과"]["후보"]][:2] == ["income_adjustment_total", "deemed_bonus_resettlement"]


# ── ⑤ 납부지연가산세: until == due, 기한일 토·일·공휴일 주의 ─────────────────────────
def test_withholding_late_penalty_paid_on_due_date_is_zero():
    """법정납부기한 당일 납부(until == due)는 미납이 아니므로 가산세 0(국세기본법 제47조의5① — 1호 3%·2호 일수분 모두 없음). 종전은 '뒤 날짜' error."""
    r = c("withholding_late_payment_penalty", {"unpaid_tax": 5 * M, "due": "2025-03-10", "until": "2025-03-10"})
    assert "error" not in r, r
    assert r["결과"]["가산세"] == 0 and r["결과"]["3%분"] == 0 and r["결과"]["일수분"] == 0 and r["결과"]["일수"] == 0
    assert "주의" not in r  # 2025-03-10은 월요일
    # until < due는 여전히 입력 확인
    e = c("withholding_late_payment_penalty", {"unpaid_tax": 5 * M, "due": "2025-03-10", "until": "2025-03-09"})
    assert "error" in e and "앞 날짜" in e["문제"][0]
    # 하루 늦으면 종전대로: 3% 150,000 + 1일 × 10만분의 22 = 1,100 → 151,100(10% 한도 500,000 안)
    r1 = c("withholding_late_payment_penalty", {"unpaid_tax": 5 * M, "due": "2025-03-10", "until": "2025-03-11"})["결과"]
    assert (r1["3%분"], r1["일수분"], r1["가산세"]) == (150_000, 1_100, 151_100)


def test_late_penalty_due_on_holiday_warns_without_shifting():
    """2025-05-05(월, 어린이날·부처님 오신 날)·2025-03-09(일)가 법정납부기한이면 주의에 국세기본법 제5조① 연장 안내 — 계산 날짜는 옮기지 않음.
    late_payment_penalty: until == due → 일수 0·가산세 0. withholding: 2025-03-09 → 2025-03-20 = 11일분(종전 규정, 납부일까지) 5,000,000×11×22/100,000 = 12,100 + 3% 150,000 = 162,100."""
    r = c("late_payment_penalty", {"unpaid_tax": 5 * M, "due": "2025-05-05", "until": "2025-05-05"})
    assert r["결과"]["가산세"] == 0 and r["결과"]["일수"] == 0
    assert "국세기본법 제5조①" in r["주의"] and "어린이날" in r["주의"]
    w = c("withholding_late_payment_penalty", {"unpaid_tax": 5 * M, "due": "2025-03-09", "until": "2025-03-20"})
    assert "일요일" in w["주의"] and "제5조①" in w["주의"]
    assert (w["결과"]["일수"], w["결과"]["일수분"], w["결과"]["가산세"]) == (11, 12_100, 162_100)
    # 평일 기한에는 주의 없음
    assert "주의" not in c("late_payment_penalty", {"unpaid_tax": 5 * M, "due": "2025-03-31", "until": "2025-04-10"})


# ── ⑥ 영 제75조7호 조건 주의 ──────────────────────────────────────────────────
def test_vat_input_tax_deduction_art75_7_requires_amended_return():
    """공급시기 2026-03-10(2026-1기, 확정신고기한 2026-07-25), 발급일 2026-08-10 — 확정신고기한 뒤 1년 안(영 제75조7호):
    공제 1,000,000(10,000,000×10%)으로 세되 수정신고·경정청구 또는 결정·경정이 있는 경우에 한한다는 주의, 지연수취 가산세 10,000,000×0.5% = 50,000(법 제60조⑦)."""
    item = {"항목": "원재료", "증빙": "세금계산서", "공급가액": 10 * M, "성격": "일반", "공급시기": "2026-03-10", "발급일": "2026-08-10"}
    r = c("vat_input_tax_deduction", {"period": "2026-2", "filing": "확정", "items": [item]})
    assert (r["결과"]["공제매입세액"], r["결과"]["지연수취_가산세"]) == (1 * M, 50_000)
    assert "수정신고·경정청구 또는 결정·경정이 있는 경우에 한함(영 제75조7호)" in r["판단"][0]["결론"]
    assert len(r["주의"]) == 1 and "영 제75조7호" in r["주의"][0] and "원재료" in r["주의"][0]
    # 확정신고기한 안 지연수취(영 제75조3호)는 조건 없이 공제 — 주의 없음
    r3 = c("vat_input_tax_deduction", {"period": "2026-1", "filing": "확정", "items": [item | {"발급일": "2026-05-10"}]})
    assert r3["결과"]["공제매입세액"] == 1 * M and "주의" not in r3 and "영 제75조3호" in r3["판단"][0]["결론"]
