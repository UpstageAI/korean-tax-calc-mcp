"""연도 의존 전수 점검(2026-11-11) 1순위 — 현행 연도에서 금액이 틀리던 6건(Claude 작성).
조문은 korean-tax-mcp로 해당 시점 시행본을 받아 확인: 상증법 제57조①(2016·2026), 소득세법 제59조의4②③·영 제118조의6①(2021~2026),
법인세법 제55조①2호·제60조의2①1호, 국조령 제36조(2022·2026)·제147조①(2024.12.31·2025.3.1·2026), 법인령 제12조①5호와 2024.2.29. 부칙 제4조."""
import pytest
from _helpers import call as c

M = 1_000_000


# ── 1. 증여세 세대생략 할증: 미성년자 40%는 증여재산가액 20억원 초과일 때만(상증법 제57조①) ─────────────
def _gift(value, minor=True, date="2026-05-01"):
    return c("gift_tax", {"gift_date": date, "gift_value": value, "relation": "직계존속", "recipient_minor": minor, "generation_skip": True})["결과"]

def test_generation_skip_surcharge_minor_below_2b_is_30_percent():
    g = _gift(130 * M)
    assert g["산출세액"] == 12 * M and g["할증세액"] == 3_600_000            # (1.3억 − 2천만) × 20% − 1천만 = 1,200만, × 30%

def test_generation_skip_surcharge_minor_over_2b_is_40_percent():
    over = _gift(2_100 * M); at = _gift(2_000 * M)
    assert over["할증세액"] * 10 == over["산출세액"] * 4                      # 20억 초과 → 40%
    assert at["할증세액"] * 10 == at["산출세액"] * 3                          # 정확히 20억은 "초과" 아님 → 30%

@pytest.mark.parametrize("date", ["2016-06-01", "2019-06-01", "2023-06-01", "2026-06-01"])
def test_generation_skip_threshold_same_every_year(date):
    g = _gift(500 * M, date=date)
    assert g["할증세액"] * 10 == g["산출세액"] * 3


# ── 2. 특별세액공제: 연도표 뒤 블록에서 빠졌던 항목 ───────────────────────────────────────
def _stc(year, persons, expenses, salary=50 * M):
    return c("special_tax_credit", {"year": year, "earner_type": "근로", "total_salary": salary, "wage_computed_tax": 5 * M,
                                    "persons": [{"name": "본인", "relation": "본인", "age": 45, "income_ok": True}, *persons], "expenses": expenses})

@pytest.mark.parametrize("year", [2018, 2021, 2022, 2023, 2024, 2026])
def test_severe_illness_medical_is_special_since_2018(year):
    """중증질환자 의료비는 700만원 한도가 없는 특정 의료비(법 제59조의4②2호 라목 → 2024년부터 마목)."""
    r = _stc(year, [{"name": "모", "relation": "직계존속", "age": 62, "income_ok": True, "severe_illness": True}],
             [{"kind": "의료비", "amount": 12 * M, "person": "모"}])
    assert "error" not in r, r
    assert r["결과"]["의료비_세액공제"] == 1_575_000                                     # (1,200만 − 5천만×3%) × 15%

def test_severe_illness_medical_general_in_2016_2017():
    for y in (2016, 2017):
        r = _stc(y, [{"name": "모", "relation": "직계존속", "age": 62, "income_ok": True, "severe_illness": True}],
                 [{"kind": "의료비", "amount": 12 * M, "person": "모"}])
        assert r["결과"]["의료비_세액공제"] == 1_050_000                                 # 일반 의료비 700만원 한도 × 15%

@pytest.mark.parametrize("year,expect", [(2016, 0), (2017, 45_000), (2022, 45_000), (2023, 45_000), (2025, 45_000), (2026, 45_000)])
def test_field_trip_cost_since_2017(year, expect):
    r = _stc(year, [{"name": "딸", "relation": "직계비속", "age": 16, "income_ok": True}], [{"kind": "체험학습", "amount": 300_000, "person": "딸"}])
    assert r["결과"]["교육비_세액공제"] == expect                                        # 영 제118조의6①6호, 1명당 30만원 × 15%

@pytest.mark.parametrize("year,expect", [(2016, 0), (2017, 300_000), (2022, 300_000), (2023, 300_000), (2026, 300_000)])
def test_student_loan_repayment_since_2017(year, expect):
    r = _stc(year, [], [{"kind": "학자금상환", "amount": 2 * M, "person": "본인"}])
    assert r["결과"]["교육비_세액공제"] == expect                                        # 법 제59조의4③2호 라목

@pytest.mark.parametrize("year,expect", [(2022, 0), (2023, 30_000), (2025, 30_000), (2026, 30_000)])
def test_college_application_fee_since_2023(year, expect):
    r = _stc(year, [{"name": "딸", "relation": "직계비속", "age": 18, "income_ok": True}], [{"kind": "대입전형료", "amount": 200_000, "person": "딸"}])
    assert r["결과"]["교육비_세액공제"] == expect                                        # 영 제118조의6①7호(2023년 신설)


# ── 3. 법인세: 성실신고확인대상 소규모 법인 세율(법 제55조①2호, 2025 사업연도부터) ────────────────────
def test_small_rental_corporation_rate_2025_2026():
    assert c("corporate_tax", {"base": 100 * M, "year": 2025, "small_rental_corp": True})["결과"]["산출세액"] == 19 * M
    assert c("corporate_tax", {"base": 100 * M, "year": 2026, "small_rental_corp": True})["결과"]["산출세액"] == 20 * M
    assert c("corporate_tax", {"base": 100 * M, "year": 2025})["결과"]["산출세액"] == 9 * M            # 일반 법인은 그대로
    assert c("corporate_tax", {"base": 30_000 * M, "year": 2025, "small_rental_corp": True})["결과"]["산출세액"] == 3_800 * M + 2_100 * M      # 200억 × 19% + 100억 × 21%

def test_small_rental_corporation_before_2025_uses_general_rate_with_note():
    r = c("corporate_tax", {"base": 100 * M, "year": 2024, "small_rental_corp": True})
    assert r["결과"]["산출세액"] == 9 * M and any("2025" in s for s in r["주의"])


# ── 4. 정상가격 산출방법 신고서 면제: 전체 재화 50억·용역 10억·무형 10억 이하(국조령 제36조3호가목) ───────
def _filing(**kw):
    return c("corporate_filing_obligations", {"year": 2026, **kw})["결과"]

def test_tp_method_report_exempt_when_total_services_under_1b():
    g = _filing(related_services=500 * M, party_max_services=500 * M)            # 전체 용역 5억 ≤ 10억 → 면제
    assert g["정상가격산출방법신고서"] is False
    g2 = _filing(related_services=1_100 * M, party_max_services=500 * M)         # 전체 11억 > 10억, 상대별 5억 > 2억 → 제출
    assert g2["정상가격산출방법신고서"] is True
    g3 = _filing(related_intangibles=800 * M, party_max_intangibles=800 * M)     # 무형 8억 ≤ 10억 → 면제
    assert g3["정상가격산출방법신고서"] is False


# ── 5. 해외금융계좌 과태료: 2025.2.28. 영 개정 기준은 보유연도가 아니라 "2025.2.28. 이후 부과하는 분부터" ───────
#    (기획재정부 국제조세제도과-80, 2026.2.11.; 기준-2025-법규국조-0110 — 2020~2023년 미신고분을 2025.6.에 부과하는 사례)
BAL = [600 * M] * 12
def _oar(year, **kw):
    return c("overseas_account_reporting", {"year": year, "month_end_totals_krw": BAL, **kw})

def test_unexplained_penalty_rate_follows_assessment_date_not_holding_year():
    for y in (2018, 2022, 2025):                                               # 지금 부과하면 보유연도와 무관하게 10%
        assert _oar(y, unexplained_amount_krw=1_000 * M)["결과"]["소명불이행_과태료"] == 100 * M
    assert _oar(2022, unexplained_amount_krw=1_000 * M, assessed_on="2025-02-28")["결과"]["소명불이행_과태료"] == 100 * M
    assert _oar(2022, unexplained_amount_krw=1_000 * M, assessed_on="2025-02-27")["결과"]["소명불이행_과태료"] == 200 * M
    r = _oar(2022, unexplained_amount_krw=1_000 * M)
    assert any("국제조세제도과-80" in s for s in r["주의"])

def test_main_penalty_progressive_table_before_20250228():
    big = {"month_end_totals_krw": [6_000 * M] * 12}                           # 미신고 60억
    now = c("overseas_account_reporting", {"year": 2022, **big})["결과"]
    old = c("overseas_account_reporting", {"year": 2022, **big, "assessed_on": "2024-06-01"})["결과"]
    assert now["과태료"] == 600 * M                                             # 60억 × 10%, 10억 한도 안
    assert old["과태료"] == 850 * M                                             # 6.5억 + (60억 − 50억) × 20%
    mid = c("overseas_account_reporting", {"year": 2022, "month_end_totals_krw": [3_000 * M] * 12, "assessed_on": "2024-06-01"})["결과"]
    assert mid["과태료"] == 350 * M                                             # 2억 + (30억 − 20억) × 15%
    cap_old = c("overseas_account_reporting", {"year": 2022, "month_end_totals_krw": [20_000 * M] * 12, "assessed_on": "2024-06-01"})["결과"]
    cap_new = c("overseas_account_reporting", {"year": 2022, "month_end_totals_krw": [20_000 * M] * 12})["결과"]
    assert cap_old["과태료"] == 2_000 * M and cap_new["과태료"] == 1_000 * M      # 종전 20억 한도, 개정 10억 한도

def test_assessed_on_validation():
    assert "error" in _oar(2022, assessed_on="2020-12-31") and "error" in _oar(2022, assessed_on="2025/03/01")


# ── 6. 무상증자 의제배당: 상환주식 주식발행초과금은 2024.2.29. 이후 전입분만 과세(법인령 제12조①5호, 부칙 제4조) ──
def _bonus(year, **kw):
    return c("deemed_dividend_bonus_shares", {"year": year, "source": "상환주식_주식발행초과금", "capitalized_amount": 100 * M, "par_value": 5_000,
                                               "shareholders": [{"name": "갑", "shares": 10_000}], "self_stock_allotment": "미교부", "shareholder_type": "법인", **kw})

def test_redeemable_share_premium_not_taxed_before_2024():
    for y in (2016, 2022, 2023):
        r = _bonus(y)
        assert "error" not in r, r
        assert r["결과"]["과세대상합계"] == 0
    assert _bonus(2025)["결과"]["과세대상합계"] == 100 * M and _bonus(2026)["결과"]["과세대상합계"] == 100 * M

def test_redeemable_share_premium_2024_needs_capitalization_date():
    assert "error" in _bonus(2024)                                              # 2024년은 전입일이 있어야 판정
    assert _bonus(2024, capitalized_on="2024-02-28")["결과"]["과세대상합계"] == 0
    assert _bonus(2024, capitalized_on="2024-02-29")["결과"]["과세대상합계"] == 100 * M
