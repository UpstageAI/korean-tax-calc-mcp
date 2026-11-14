"""국세청 「2026 해외진출기업을 위한 세무 가이드북」 불일치 M3·M4·M5와 원 미만 처리 — 정답 테스트(Claude 작성 2026-11-14).

대조한 시행본(법제처 DRF, 2026-11-14 조회 — 원자료 통합테스트/고도화_1114/raw_guidefix/):
- M3 CFC 2억원 적용배제
  · 구 국제조세조정에 관한 법률 시행령 제34조의2 [2016.9.1.·2019.2.12. 시행본]: "제29조제1항부터 제3항까지의 규정에 따라 계산한 금액"
    (구 영 제29조 = 해당 법인의 법인세 차감 전 당기순이익) 2억원 이하, 1년 미만은 2억원 × 개월 수/12
  · 구 영 제32조제1항 [2020.8.12. 시행본]: "제29조에 따라 계산한 실제발생소득"(구 영 제29조 = 세전이익) 2억원 이하
  · 영 제64조제1항 [2021.12.30. 시행본]: "제61조에 따라 계산한 실제발생소득"(2021년 시행 제61조 = 세전이익 조정액, 단년)
  · 영 제61조제1항 [2022.2.15. 시행본·2026.2.27. 시행본]: 최근 3개 사업연도 합계의 연평균액(대통령령 제32423호 부칙 제2조:
    2022.1.1. 이후 개시하는 과세연도부터), 영 제64조제1항 [2026.2.27. 시행본]은 2021년 문언 그대로
  · 저세율 판정은 전 기간 최근 3개 사업연도 합계(구 영 제30조·영 제62조[2021.12.30.]) — 바꾸지 않음
- M4 법인세법 시행령 제19조제3호
  · 2016.11.29.·2019.9.16. 시행본: "3. 인건비"만
  · 2020.2.11. 시행본(대통령령 제30396호, 부칙 제2조 2020.1.1. 이후 개시 사업연도분)·2022.10.27. 시행본: 중소기업·중견기업이
    100% 직접·간접 출자한 해외현지법인 파견 임직원 인건비(내국법인 지급분이 합계의 100분의 50 미만인 경우로 한정) 포함
  · 2024.2.29. 시행본(대통령령 제34266호, 부칙 제5조 시행일이 속하는 사업연도부터)·2026.10.1. 시행본: 내국법인 일반으로 확대,
    소득세법 제127조제1항에 따라 근로소득세가 원천징수된 인건비
- M5 국제조세조정에 관한 법률 시행령 제98조제1항제3호가목 [2026.2.27. 시행본]: 거주자 단일 10억원·5년 누적 20억원
  (가이드 인쇄 37쪽 "거주자는 200억원"은 조문과 다름 — 도구 유지)
- 조세특례제한법 제23조의2제3항·시행령 제20조제2항: 차감금액 끝수 규정 없음 → 최종 익금불산입액만 원 미만 절사
"""
from _helpers import call as c

M = 1_000_000


# ── M3: CFC 2억원 적용배제 ─────────────────────────────────────────────
def cfc(**kw):
    a = {"pretax_incomes": [1_000 * M], "taxes_paid": [0], "ownership_chains": [[1]], "related_party": True,
         "distributable": {"unappropriated_retained_earnings": 1_000 * M}, **kw}
    if "taxes_paid" not in kw:
        a["taxes_paid"] = [0] * len(a["pretax_incomes"])
    r = c("cfc_deemed_dividend", a)
    assert "error" not in r, r
    return r


def test_2019_current_year_200m_excluded_even_if_average_higher():
    # 해당 사업연도(첫 값) 2억원 → 배제. 종전(3년 평균 666,666,666)이면 적용이었음
    r = cfc(year=2019, pretax_incomes=[200 * M, 900 * M, 900 * M])
    g = r["결과"]
    assert g["배당간주_적용"] is False and "제34조의2" in g["적용제외_사유"] and "해당 사업연도" in g["적용제외_사유"]
    assert g["적용배제_판정소득"] == 200 * M
    assert any("첫 값" in s for s in r["주의"])


def test_2019_current_year_over_200m_applies_even_if_average_lower():
    g = cfc(year=2019, pretax_incomes=[200 * M + 1, 0, 0])["결과"]
    assert g["배당간주_적용"] is True and g["배당간주금액"] == 800 * M        # 1,000,000,000 − 200,000,000
    g = cfc(year=2019, pretax_incomes=[200 * M + 1, 0, 0], current_year_income=200 * M)["결과"]
    assert g["배당간주_적용"] is False


def test_current_year_income_input_used_and_no_caution():
    r = cfc(year=2018, pretax_incomes=[900 * M], current_year_income=150 * M)
    assert r["결과"]["배당간주_적용"] is False
    assert not any("첫 값" in s for s in r["주의"])


def test_2020_2021_also_current_year():
    g = cfc(year=2020, pretax_incomes=[200 * M, 900 * M, 900 * M])["결과"]
    assert g["배당간주_적용"] is False and "제32조①" in g["적용제외_사유"]
    g = cfc(year=2021, pretax_incomes=[200 * M, 900 * M, 900 * M])["결과"]
    assert g["배당간주_적용"] is False and "제64조①" in g["적용제외_사유"]
    assert cfc(year=2021, pretax_incomes=[200 * M + 1, 0, 0])["결과"]["배당간주_적용"] is True


def test_2022_uses_three_year_average():
    r = cfc(year=2022, pretax_incomes=[200 * M, 900 * M, 900 * M], current_year_income=100 * M)
    g = r["결과"]
    assert g["배당간주_적용"] is True and g["적용배제_판정소득"] == 666_666_666
    assert any("current_year_income은 이 판정에 쓰지 않음" in s for s in r["주의"])
    assert cfc(year=2022, pretax_incomes=[200 * M + 1, 0, 0])["결과"]["배당간주_적용"] is False   # 연평균 66,666,667


def test_average_compared_without_truncation():
    # (200,000,000 + 200,000,000 + 200,000,002) ÷ 3 = 200,000,000.67 > 2억원 → 적용(평균을 먼저 자르면 2억원 이하로 잘못 배제)
    assert cfc(year=2026, pretax_incomes=[200 * M, 200 * M, 200 * M + 2])["결과"]["배당간주_적용"] is True
    assert cfc(year=2026, pretax_incomes=[200 * M, 200 * M, 200 * M])["결과"]["배당간주_적용"] is False
    assert cfc(year=2026, pretax_incomes=[200 * M, 200 * M, 200 * M + 2])["결과"]["실제발생소득_연평균"] == 200 * M   # 표시값은 종전대로 절사


def test_monthly_proration_both_sides():
    # 2억원 × 5/12 = 83,333,333.33…
    assert cfc(year=2019, months=5, pretax_incomes=[83_333_333])["결과"]["배당간주_적용"] is False
    assert cfc(year=2019, months=5, pretax_incomes=[83_333_334])["결과"]["배당간주_적용"] is True
    assert cfc(year=2024, months=5, pretax_incomes=[83_333_333])["결과"]["배당간주_적용"] is False
    g = cfc(year=2024, months=5, pretax_incomes=[83_333_334])["결과"]
    assert g["배당간주_적용"] is True and g["배당간주금액"] == 1_000 * M - 83_333_333


# ── M4: 해외현지법인 파견 인건비 손비 특례 ─────────────────────────────
def expat(year, sme=None, **item):
    it = {"이름": "파견A", "급여": 60 * M, "귀속": "현지법인", **item}
    a = {"year": year, "items": [it]}
    if sme is not None:
        a["sme_or_midsize"] = sme
    r = c("expat_cost_recharge", a)
    assert "error" not in r, r
    return r


def disallowed(r):
    return r["결과"]["합계"]["본사_손금불산입"]


def test_2024_special_rule_applies():
    r = expat(2024, 완전자회사=True, 현지법인_지급인건비=60 * M + 1, 근로소득_원천징수=True)
    assert disallowed(r) == 0 and r["결과"]["합계"]["본사_손금"] == 60 * M
    assert r["결과"]["항목별"][0]["파견인건비_손비특례"] is True
    assert not r.get("세무조정") and "34266" in r["근거"]


def test_2024_exactly_half_not_less_than_50pct():
    # 내국 60,000,000 / 합계 120,000,000 = 50% → "50 미만" 아님
    assert disallowed(expat(2024, 완전자회사=True, 현지법인_지급인건비=60 * M, 근로소득_원천징수=True)) == 60 * M


def test_2024_requires_withholding_and_full_ownership():
    assert disallowed(expat(2024, 완전자회사=True, 현지법인_지급인건비=100 * M, 근로소득_원천징수=False)) == 60 * M
    assert disallowed(expat(2024, 완전자회사=False, 현지법인_지급인건비=100 * M, 근로소득_원천징수=True)) == 60 * M
    # 2024부터는 중소·중견이 아니어도 적용
    assert disallowed(expat(2024, sme=False, 완전자회사=True, 현지법인_지급인건비=100 * M, 근로소득_원천징수=True)) == 0


def test_2020_2023_sme_only_no_withholding_requirement():
    assert disallowed(expat(2020, sme=True, 완전자회사=True, 현지법인_지급인건비=60 * M + 1)) == 0
    assert disallowed(expat(2023, sme=True, 완전자회사=True, 현지법인_지급인건비=60 * M + 1, 근로소득_원천징수=False)) == 0
    assert disallowed(expat(2023, sme=False, 완전자회사=True, 현지법인_지급인건비=100 * M)) == 60 * M
    r = expat(2023, 완전자회사=True, 현지법인_지급인건비=100 * M)          # 중소·중견 여부 미입력
    assert disallowed(r) == 60 * M and any("sme_or_midsize" in s for s in r["주의"])
    assert any("2024.2.29." in s for s in r["주의"])


def test_2019_no_special_rule():
    r = expat(2019, sme=True, 완전자회사=True, 현지법인_지급인건비=100 * M, 근로소득_원천징수=True)
    assert disallowed(r) == 60 * M and "제19조제3호" not in r["근거"]


def test_backward_compatible_and_caution():
    r = expat(2024)
    assert disallowed(r) == 60 * M and any("제19조제3호" in s for s in r["주의"])


def test_partial_charge_keeps_transfer_pricing():
    # 정상청구액 63,000,000 − 청구 30,000,000 = 33,000,000 정상가격 조정은 그대로, 손금불산입 없음
    r = expat(2024, 청구액=30 * M, 완전자회사=True, 현지법인_지급인건비=100 * M, 근로소득_원천징수=True)
    assert disallowed(r) == 0 and r["결과"]["합계"]["정상가격_조정_익금산입"] == 33 * M


# ── 원 미만 처리: 조특법 제23조의2 차입금 이자 차감 ─────────────────────
def test_interest_deduction_truncates_only_final_amount():
    # 10,000,000 × 1,000,000,000 ÷ 3,000,000,000 = 3,333,333.33… → 200,000,000 − 3,333,333.33… = 196,666,666.67 → 196,666,666
    r = c("foreign_subsidiary_dividend", {"received_on": "2026-06-30", "ownership_ratio": 1.0, "held_months": 27, "dividend": 200 * M,
                                          "borrowing_interest": 10 * M, "subsidiary_book_value_daily_sum": 1_000 * M,
                                          "total_assets_daily_sum": 3_000 * M})
    g = r["결과"]
    assert g["익금불산입액"] == 196_666_666 and g["익금산입액"] == 3_333_334
    assert "원 미만 처리 규정 없음 — 최종 금액에서 절사" in r["주의"]


# ── M5: 거주자 손실거래명세서 5년 누적 20억원(조문) ─────────────────────
def test_resident_cumulative_loss_threshold_is_2bn():
    loss = lambda v: c("overseas_subsidiary_statement", {"year": 2025, "filer": "개인", "ownership_direct": 0.5, "related_party": True,
                                                         "loss_cumulative_5y": v})["결과"]["손실거래명세서_제출대상"]
    assert loss(2_000 * M) is True and loss(2_000 * M - 1) is False
