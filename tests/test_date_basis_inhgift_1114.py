"""기준일(부칙 적용례) 수정 정답 테스트 — 상증·국기·조특(2026-11-14, Claude 손계산).
대조한 원문(국세법령정보시스템 시행본·부칙, 응답 캐시와 raw_D 보관본):
  국세기본법 2016.7.1.·2019.1.1.·2020.1.1. 시행본 제47조의4제1항제1호, 최신 시행본(2026.7.1. 시행분 포함) 제47조의4제1항제1호,
    법률 제16097호 부칙 제1조·제11조, 법률 제16841호 부칙 제21조·제22조, 법률 제18586호 부칙 제7조, 법률 제21212호 부칙 제1조·제3조·제4조,
    2018 시행본 제48조제2항제1호(종전 50·20·10%).
  상속세 및 증여세법 2019·2020·2023·2025.3.14.·2026 시행본 제21조제1항·제53조제4호, 법률 제16846호 부칙 제5조, 법률 제20777호 부칙 제4조.
  상속세 및 증여세법 시행령 부칙(대통령령 제26960호, 2016.2.5.) 제9조(계산식 이미지 판독), 대통령령 제28638호 부칙 제8조.
  조세특례제한법 부칙 법률 제17759호 제4조제1항·제36조, 법률 제20617호 제5조제2항, 법률 제21223호(2025.12.23.) 제34조.
"""
from korean_tax_calc_mcp import server as S

M = 1_000_000


def call(tool, **k):
    t = getattr(S, tool)
    return getattr(t, "fn", t)(**k)


# ── late_payment_penalty: 납세고지일 포함 여부(성립일 기준) ─────────────────────────────

def test_late_payment_notice_day_excluded_for_2020_accrual():
    # 2023년 2기 부가세(성립 2023.12.31.), 법정납부기한 2024-01-25, 납세고지일 2025-03-10, 미납 1천만원
    # 2024-01-26 ~ 2025-03-10 = 410일, 고지일 제외 409일 × 10만분의 22 × 1천만 = 899,800
    r = call("late_payment_penalty", unpaid_tax=10 * M, due="2024-01-25", until="2025-03-10", notice=True, accrued_on="2023-12-31")
    assert r["결과"]["일수"] == 409 and r["결과"]["가산세"] == 899_800
    assert "고지일 전날" in r["판단"][0]["결론"]
    # 자진납부(notice=false)면 납부일까지 410일 → 902,000
    r = call("late_payment_penalty", unpaid_tax=10 * M, due="2024-01-25", until="2025-03-10", notice=False)
    assert r["결과"]["일수"] == 410 and r["결과"]["가산세"] == 902_000 and "주의" not in r


def test_late_payment_no_notice_input_flags():
    r = call("late_payment_penalty", unpaid_tax=10 * M, due="2024-01-25", until="2025-03-10")
    assert r["결과"]["일수"] == 410 and "notice=true" in r["판단"][0]["결론"] and "주의" not in r


def test_late_payment_pre2020_accrual_includes_notice_day():
    # 2019년 1기 부가세(성립 2019.6.30.), 기한 2019-07-25, 고지일 2020-03-10 → 2019-07-26 ~ 2020-03-10 포함 229일 × 10만분의 25
    r = call("late_payment_penalty", unpaid_tax=10 * M, due="2019-07-25", until="2020-03-10", notice=True)
    assert r["결과"]["일수"] == 229 and r["결과"]["가산세"] == 572_500
    assert "가산금" in str(r["주의"])


def test_late_payment_accrual_boundary_2020():
    # 기한 2020-01-27, 고지일 2020-03-10: 2020-01-28 ~ 03-10 = 43일
    old = call("late_payment_penalty", unpaid_tax=10 * M, due="2020-01-27", until="2020-03-10", notice=True, accrued_on="2019-12-31")
    new = call("late_payment_penalty", unpaid_tax=10 * M, due="2020-01-27", until="2020-03-10", notice=True, accrued_on="2020-01-01")
    assert (old["결과"]["일수"], old["결과"]["가산세"]) == (43, 107_500)
    assert (new["결과"]["일수"], new["결과"]["가산세"]) == (42, 105_000)
    # 성립일 미입력 + 2020년 기한 → 2020 성립으로 보고 계산하되 주의
    r = call("late_payment_penalty", unpaid_tax=10 * M, due="2020-01-27", until="2020-03-10", notice=True)
    assert r["결과"]["일수"] == 42 and "accrued_on" in str(r["주의"])


def test_late_payment_from_2026_07_01_day_before():
    # 2025 사업연도 법인세 기한 2026-03-31, 2026-07-10 자진납부 → 2026-04-01 ~ 07-09 = 100일 × 10만분의 22
    r = call("late_payment_penalty", unpaid_tax=10 * M, due="2026-03-31", until="2026-07-10", notice=False)
    assert r["결과"]["일수"] == 100 and r["결과"]["가산세"] == 220_000


# ── withholding_late_payment_penalty: 제5항 소액 기준 2022.1.1. 기간 분할 ──────────────────

WH = dict(unpaid_tax=1_100_000, due="2021-09-10", until="2021-11-15", notice_due="2021-11-30", paid_on="2022-03-31", accrued_on="2021-08-31")


def test_withholding_small_notice_split_at_2022():
    # 고지 전: 3% 33,000 + 65일 × 10만분의 25 × 110만 = 17,875 → 50,875
    # 고지세액 120만원(100만 이상 150만 미만): 2021-12-01 ~ 12-31 31일만 종전 → 110만 × 31 × 10만분의 25 = 8,525 → 합계 59,400
    r = call("withholding_late_payment_penalty", notice_amount=1_200_000, **WH)
    assert r["결과"]["일수"] == 65 and r["결과"]["고지후_일수"] == 31 and r["결과"]["고지후분"] == 8_525 and r["결과"]["가산세"] == 59_400
    assert any("제18586호" in p["근거"] for p in r["판단"])


def test_withholding_notice_150man_or_more_full_period():
    # 150만원 이상: 2021-12-01 ~ 2022-03-31 121일 — 2022-02-14까지 76일 × 10만분의 25, 그 뒤 45일 × 10만분의 22
    # 110만 × (76 × 0.00025 + 45 × 0.00022) = 31,790 → 50,875 + 31,790 = 82,665
    r = call("withholding_late_payment_penalty", notice_amount=1_600_000, **WH)
    assert r["결과"]["고지후_일수"] == 121 and r["결과"]["고지후분"] == 31_790 and r["결과"]["가산세"] == 82_665


def test_withholding_notice_under_100man_none():
    r = call("withholding_late_payment_penalty", notice_amount=900_000, **WH)
    assert r["결과"]["고지후분"] == 0 and r["결과"]["가산세"] == 50_875


# ── inheritance_tax: 기한후신고 시 인적공제와 일괄공제 선택(법률 제16846호 부칙 제5조) ─────────

INH = dict(estate_value=2_000 * M, children=4, seniors=2, minors=[10])


def test_inheritance_late_filing_after_2020_chooses_larger():
    # 인적: 기초 2억 + 자녀 4 × 5천만 + 연로 2 × 5천만 + 미성년 10년 × 1천만 = 6억 > 5억
    # 과세가액 20억 − 장례비용 하한 500만 = 19.95억, 과세표준 13.95억 → 1천만 + 8천만 + 1.5억 + 3.95억 × 40% = 3.98억, 신고세액공제 없음
    r = call("inheritance_tax", year=2024, filed=False, late_filed_on="2024-11-15", **INH)
    assert r["계산"]["인적공제_적용액"] == 600 * M and r["결과"]["과세표준"] == 1_395 * M and r["결과"]["산출세액"] == 398 * M
    assert r["결과"]["신고세액공제"] == 0 and r["결과"]["납부할세액"] == 398 * M
    assert "제16846호" in r["판단"]["일괄공제_선택"]["근거"]


def test_inheritance_no_filing_forces_500m():
    r = call("inheritance_tax", year=2024, filed=False, **INH)
    assert r["계산"]["인적공제_적용액"] == 500 * M and r["결과"]["산출세액"] == 438 * M
    assert "late_filed_on" in r["판단"]["일괄공제_선택"]["결론"]


def test_inheritance_basis_is_late_filing_date_not_death():
    # 2019 상속개시: 2019.12.31.까지 기한후신고면 5억 강제, 2020.1.2. 기한후신고면 선택
    before = call("inheritance_tax", year=2019, filed=False, late_filed_on="2019-12-31", **INH)
    after = call("inheritance_tax", year=2019, filed=False, late_filed_on="2020-01-02", **INH)
    assert before["계산"]["인적공제_적용액"] == 500 * M and before["결과"]["산출세액"] == 438 * M
    assert after["계산"]["인적공제_적용액"] == 600 * M and after["결과"]["산출세액"] == 398 * M


def test_inheritance_late_filed_on_input_checks():
    assert "error" in call("inheritance_tax", year=2024, filed=True, late_filed_on="2024-11-15", **INH)
    assert "error" in call("inheritance_tax", year=2024, filed=False, late_filed_on="2023-11-15", **INH)
    # 기한 안 신고는 그대로: 6억, 신고세액공제 3% 11,940,000
    r = call("inheritance_tax", year=2024, **INH)
    assert r["계산"]["인적공제_적용액"] == 600 * M and r["결과"]["신고세액공제"] == 11_940_000


# ── gift_tax: 기타친족 범위(법률 제20777호 부칙 제4조) ─────────────────────────────

def test_gift_other_relative_range_after_2025_03_14():
    # 5촌 혈족 5천만원: 2025.6.1. 증여 → 공제 0, 과세표준 5천만 × 10% = 500만, 신고세액공제 3% 15만 → 485만
    r = call("gift_tax", gift_date="2025-06-01", gift_value=50 * M, relation="기타친족", kin_type="혈족", kin_degree=5)
    assert r["결과"]["증여재산공제"] == 0 and r["결과"]["산출세액"] == 5 * M and r["결과"]["납부할세액"] == 4_850_000
    assert "제20777호" in r["판단"]["기타친족_촌수"]["근거"]
    # 2025.3.13. 증여는 종전(6촌 혈족) → 1천만 공제, 4천만 × 10% = 400만, 388만
    r = call("gift_tax", gift_date="2025-03-13", gift_value=50 * M, relation="기타친족", kin_type="혈족", kin_degree=5)
    assert r["결과"]["증여재산공제"] == 10 * M and r["결과"]["납부할세액"] == 3_880_000
    # 4촌 인척은 2025.3.14.부터 범위 밖
    assert call("gift_tax", gift_date="2025-03-14", gift_value=50 * M, relation="기타친족", kin_type="인척", kin_degree=4)["결과"]["증여재산공제"] == 0
    assert call("gift_tax", gift_date="2025-03-13", gift_value=50 * M, relation="기타친족", kin_type="인척", kin_degree=4)["결과"]["증여재산공제"] == 10 * M


def test_gift_other_relative_alias_and_no_degree():
    r = call("gift_tax", gift_date="2025-06-01", gift_value=50 * M, relation="사촌")       # 혈족 4촌 → 범위 안
    assert r["결과"]["증여재산공제"] == 10 * M and "혈족 4촌" in r["입력 해석"]
    r = call("gift_tax", gift_date="2025-06-01", gift_value=50 * M, relation="기타친족")    # 촌수 미입력 → 공제하되 확인 필요
    assert r["결과"]["증여재산공제"] == 10 * M and r["판단"]["기타친족_촌수"].get("확인필요")
    r = call("gift_tax", gift_date="2024-06-01", gift_value=50 * M, relation="기타친족")
    assert "기타친족_촌수" not in r["판단"]
    assert "error" in call("gift_tax", gift_date="2025-06-01", gift_value=50 * M, relation="직계존속", kin_type="혈족", kin_degree=1)


def test_gift_allowed_values_wording_by_date():
    after = call("gift_tax", gift_date="2025-06-01", gift_value=50 * M, relation="이웃사촌형")
    before = call("gift_tax", gift_date="2024-06-01", gift_value=50 * M, relation="이웃사촌형")
    assert after["허용값"]["기타친족"].startswith("4촌 이내 혈족·3촌 이내 인척")
    assert before["허용값"]["기타친족"].startswith("6촌 이내 혈족·4촌 이내 인척")


# ── gift_tax: 2016.1.1. 전 조부모 증여 합산 시 할증(상증령 부칙 제26960호 제9조) ──────────────

GS = dict(gift_date="2025-05-01", gift_value=1_500 * M, relation="직계존속", recipient_minor=True, prior_gifts_same_donor=1_000 * M, generation_skip=True)


def test_gift_generation_skip_pre2016_formula():
    # 합산 25억 − 공제 2천만 = 과세표준 24.8억 → 산출세액 1천만 + 8천만 + 1.5억 + 14.8억 × 40% = 8.32억
    # 2016년 전분: 8.32억 × 10/25 × 30% − 종전 할증 5천만 = 99,840,000 − 50,000,000 = 49,840,000
    # 나머지: 8.32억 × 15/25 × 40% = 199,680,000 → 할증 249,520,000
    r = call("gift_tax", prior_gifts_before_2016=1_000 * M, prior_surcharge_before_2016=50 * M, **GS)
    assert r["결과"]["산출세액"] == 832 * M and r["결과"]["할증세액"] == 249_520_000
    assert r["계산"]["세대생략할증_2016년전_분할"]["2016년_전분_할증"] == 49_840_000


def test_gift_generation_skip_pre2016_absent_flags():
    r = call("gift_tax", **GS)
    assert r["결과"]["할증세액"] == 332_800_000 and r["판단"]["세대생략할증_2016년전_증여"].get("확인필요")
    # 2016년 이후 증여만 합산(0 입력)이면 전체 40%, 확인 표시 없음
    r = call("gift_tax", prior_gifts_before_2016=0, **GS)
    assert r["결과"]["할증세액"] == 332_800_000 and "세대생략할증_2016년전_증여" not in r["판단"]
    # 2026년 증여는 10년 안에 2016년 전 증여가 없음
    assert "error" in call("gift_tax", **{**GS, "gift_date": "2026-01-02"}, prior_gifts_before_2016=100 * M)


# ── integrated_investment_credit ─────────────────────────────────────────

def test_investment_graduation_year_basis():
    G = [{"kind": "일반", "amount": 1_000 * M}]
    # FY2026: 2024 과세연도에 처음 졸업 → 졸업 뒤 3년 율 아님, 중견 5% = 5천만 / 2025 졸업 → 7.5% = 7,500만
    old = call("integrated_investment_credit", year=2026, size="졸업 뒤 3년", investments=G, graduated_year=2024)
    new = call("integrated_investment_credit", year=2026, size="졸업 뒤 3년", investments=G, graduated_year=2025)
    assert old["결과"]["기본공제"] == 50 * M and any("제20617호 부칙 제5조제2항" in p for p in old["판단"])
    assert new["결과"]["기본공제"] == 75 * M
    # 미입력: 7.5%로 계산하되 판단에 표시
    r = call("integrated_investment_credit", year=2026, size="졸업 뒤 3년", investments=G)
    assert r["결과"]["기본공제"] == 75 * M and any("graduated_year" in p for p in r["판단"])
    # FY2025 2024 졸업: 본칙 중견 5% = 5천만(임시 중견 7%와 비교)
    r = call("integrated_investment_credit", year=2025, size="졸업 뒤 3년", investments=G, graduated_year=2024)
    assert r["계산"]["본칙"]["기본공제"] == 50 * M and r["계산"]["임시"]["기본공제"] == 70 * M
    assert "error" in call("integrated_investment_credit", year=2026, size="중견기업", investments=G, graduated_year=2024)


def test_investment_fy2020_accepted():
    # FY2020 중소기업 일반시설 10억 → 2021 율표 10% = 1억
    r = call("integrated_investment_credit", year=2020, size="중소기업", investments=[{"kind": "일반", "amount": 1_000 * M}])
    assert r["결과"]["기본공제"] == 100 * M and any("제17759호 부칙 제4조제1항" in p for p in r["판단"])
    assert "error" in call("integrated_investment_credit", year=2020, size="중소기업", investments=[{"kind": "국가전략", "amount": 1_000 * M}])
    assert "error" in call("integrated_investment_credit", year=2019, size="중소기업", investments=[{"kind": "일반", "amount": 1_000 * M}])


# ── integrated_employment_credit: 2026 과세연도 2024·2025 증가분(법률 제21223호 부칙 제34조) ─────

H = lambda *rows: [{"year": y, "total": t, "youth": yo} for y, t, yo in rows]


def test_employment_2026_prior_increases_old_rule():
    hc = H((2023, 45, 20), (2024, 80, 35), (2025, 110, 45), (2026, 120, 50))
    # 2024분 3차: 청년 15 × 1,450만 + 그 외 20 × 850만 = 3.875억 / 2025분 2차: 청년 10 × 1,450만 + 그 외 20 × 850만 = 3.15억
    r = call("integrated_employment_credit", year=2026, size="중소기업", headcounts=hc)
    rows = {(x["최초_공제_과세연도"], x["차수"]): x["공제액"] for x in r["계산"]["최초_공제_과세연도별"]}
    assert rows == {(2024, 3): 387_500_000, (2025, 2): 315 * M} and r["결과"]["기본공제"] == 702_500_000
    assert any("제21223호 부칙 제34조" in p for p in r["판단"])
    # 감사 사례: 2025년 청년 2명 증가(중소·수도권) → 2026 2차 2,900만
    r = call("integrated_employment_credit", year=2026, size="중소기업", headcounts=H((2024, 10, 3), (2025, 12, 5), (2026, 12, 5)))
    assert r["결과"]["기본공제"] == 29 * M


def test_employment_2026_general_and_rejections():
    hc = H((2023, 45, 20), (2024, 80, 35), (2025, 110, 45), (2026, 120, 50))
    r = call("integrated_employment_credit", year=2026, size="일반", headcounts=hc)      # 2025분 2차만: 청년 10 × 400만
    assert r["결과"]["기본공제"] == 40 * M
    assert "error" in call("integrated_employment_credit", year=2026, size="중소기업", headcounts=hc, returned_from_leave=1)
    assert "error" in call("integrated_employment_credit", year=2027, size="중소기업", headcounts=H((2026, 20, 8), (2027, 30, 12)))
    # 2025 과세연도 결과는 그대로
    assert call("integrated_employment_credit", year=2025, size="중소기업", headcounts=hc)["결과"]["기본공제"] == 315 * M + 387_500_000   # 2025분 1차 + 2024분 2차


# ── underreporting_penalty: 2020 전 수정신고분의 재수정(법률 제16841호 부칙 제22조 후단) ─────────

def test_underreporting_re_amendment_keeps_old_rate():
    base = dict(additional_tax=10 * M, reduction="수정신고", due="2019-03-31", amended_on="2020-02-15")
    # 기한 후 10.5개월: 신 30%(감면 30만 → 70만), 2019.10.1. 1차 수정신고분의 재수정이면 종전 20%(감면 20만 → 80만)
    assert call("underreporting_penalty", **base)["결과"]["가산세"] == 700_000
    r = call("underreporting_penalty", prior_amended_on="2019-10-01", **base)
    assert r["결과"]["가산세"] == 800_000 and r["결과"]["감면율"] == 0.2 and "제22조 후단" in r["근거"]
    assert call("underreporting_penalty", prior_amended_on="2020-01-05", **base)["결과"]["가산세"] == 700_000
    assert "error" in call("underreporting_penalty", additional_tax=10 * M, prior_amended_on="2019-10-01")


# ── unlisted_stock_valuation: 2018.2.13. 순자산가치 사유(부칙 제8조) — 결과는 바꾸지 않고 주의 ──────

def test_unlisted_2018_rule_note():
    inc = [{"사업연도": 2016, "순손익액": -10 * M}, {"사업연도": 2015, "순손익액": -10 * M}, {"사업연도": 2014, "순손익액": -10 * M}]
    old = call("unlisted_stock_valuation", valuation_date="2017-11-30", shares=10_000, net_asset=1_000 * M, incomes=inc)
    assert "부칙 제8조" in str(old["판단"]) and "3년연속결손" in old["결과"]["평가방법"]
    new = call("unlisted_stock_valuation", valuation_date="2018-03-01", shares=10_000, net_asset=1_000 * M,
               incomes=[{**x, "사업연도": x["사업연도"] + 1} for x in inc])
    assert "제28638호 부칙 제8조" not in str(new["판단"])
