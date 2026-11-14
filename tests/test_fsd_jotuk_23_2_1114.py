"""외국자회사 수입배당금 2026년 수령분 100% 익금불산입 특례 — 정답 테스트(Claude 작성 2026-11-14).
대조한 시행본: 조세특례제한법 [법률 제21549호(2026.4.21.) 반영, 시행 2026.9.18. 시행본] 제23조의2제1항~제3항,
  같은 법률 부칙 제1조(공포한 날부터 시행)·제2조(2026.1.1. 이후 외국자회사로부터 수입배당금액을 받는 경우부터 적용),
  조세특례제한법 시행령 [시행 2026.9.18. 시행본] 제20조(외국자회사 수입배당금의 익금불산입 특례) 제1항·제2항,
  법인세법 [시행 2026.7.1. 시행본] 제18조의4제1항(95%)·제4항제1호.
조문: 2026년 1월 1일부터 2026년 12월 31일까지 받은 수입배당금액의 100분의 100 익금불산입(제1항),
  배당간주금액 없는 특정외국법인 배당도 100%(제2항), 차입금 이자 × 외국자회사 주식 장부가액 일별 잔액 합계 ÷ 자산총액 일별 잔액 합계를 뺌(제3항·영 제20조제2항).
"""
from _helpers import call as c
from korean_tax_calc_mcp.engine import calc_cit as C

M = 1_000_000
B = {"ownership_ratio": 1.0, "held_months": 27, "dividend": 200 * M, "foreign_withholding": 10 * M}


def _g(day, **kw):
    r = c("foreign_subsidiary_dividend", {**B, "received_on": day, **kw})
    assert "error" not in r, r
    return r


def test_2025_12_31_is_95pct():
    g = _g("2025-12-31")["결과"]
    assert g["익금불산입액"] == 190 * M and g["익금산입액"] == 10 * M


def test_2026_01_01_is_100pct():
    r = _g("2026-01-01")
    g = r["결과"]
    assert g["제도"] == "익금불산입" and g["익금불산입액"] == 200 * M and g["익금산입액"] == 0
    assert g["외국세_손금불산입"] == 10 * M and g["공제대상_외국법인세액"] == 0
    assert "제23조의2" in r["근거"] and "21549" in r["근거"]
    assert any("제23조의2제3항" in s for s in r["주의"])          # 차입금 이자 입력 안내
    assert any(a["금액"] == 200 * M and "제23조의2" in a["근거"] for a in r["세무조정"])


def test_2026_12_31_is_100pct():
    assert _g("2026-12-31")["결과"]["익금불산입액"] == 200 * M


def test_2027_01_01_back_to_95pct_engine():
    # 특례 기간(조문 문언) 밖 — 법인세법 제18조의4제1항 95%. 도구는 2027을 연도표 밖으로 막으므로 엔진으로 확인.
    g = C.foreign_subsidiary_dividend({**B, "received_on": "2027-01-01"})["결과"]
    assert g["익금불산입액"] == 190 * M and g["익금산입액"] == 10 * M
    assert "error" in c("foreign_subsidiary_dividend", {**B, "received_on": "2027-01-01"})


def test_interest_deduction_2026():
    # 12,345,678 × 1,000,000,000 ÷ 3,000,000,000 = 4,115,226 → 200,000,000 − 4,115,226 = 195,884,774
    r = _g("2026-06-30", borrowing_interest=12_345_678, subsidiary_book_value_daily_sum=1_000_000_000,
           total_assets_daily_sum=3_000_000_000)
    g = r["결과"]
    assert g["익금불산입액"] == 195_884_774 and g["익금산입액"] == 4_115_226
    assert any("4,115,226" in str(j) for j in r["판단"])


def test_interest_deduction_floor_zero():
    g = _g("2026-06-30", dividend=1 * M, foreign_withholding=0, borrowing_interest=10 * M,
           subsidiary_book_value_daily_sum=5 * M, total_assets_daily_sum=5 * M)["결과"]
    assert g["익금불산입액"] == 0 and g["익금산입액"] == 1 * M


def test_interest_ignored_in_2025():
    g = _g("2025-06-30", borrowing_interest=12_345_678, subsidiary_book_value_daily_sum=1_000_000_000,
           total_assets_daily_sum=3_000_000_000)["결과"]
    assert g["익금불산입액"] == 190 * M


def test_interest_without_ratio_inputs_is_error():
    assert "error" in c("foreign_subsidiary_dividend", {**B, "received_on": "2026-06-30", "borrowing_interest": 1 * M})


def test_cfc_without_retained_income_2026_is_100pct():
    r = _g("2026-06-30", cfc_low_tax=True, cfc_no_retained_earnings=True)
    assert r["결과"]["익금불산입액"] == 200 * M and r["결과"]["익금산입액"] == 0
    assert any("제23조의2제2항" in str(j) for j in r["판단"])


def test_cfc_without_retained_income_2025_still_included():
    g = _g("2025-06-30", cfc_low_tax=True, cfc_no_retained_earnings=True)["결과"]
    assert g["익금불산입액"] == 0 and g["익금산입액"] == 200 * M


def test_cfc_low_tax_2026_without_flag_still_included():
    g = _g("2026-06-30", cfc_low_tax=True)["결과"]
    assert g["익금불산입액"] == 0 and g["익금산입액"] == 200 * M


def test_requirements_still_apply_in_2026():
    g = _g("2026-06-30", held_months=4)["결과"]
    assert g["제도"] == "외국납부세액공제" and g["익금불산입액"] == 0
