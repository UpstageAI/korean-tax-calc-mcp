"""기준일(지출분·신고분·확정분·발급분) 정답 테스트 — 법인세·부가가치세·국제조세 (2026-11-14 점검 B 반영).

대조한 원문(국세법령정보시스템 응답 캐시·연혁본, 2026-11-14 조회):
  · 조세특례제한법 2026.6.2. 반영본 — 제136조제6항 현행 문언(2028.12.31. 이전, 전통시장·온누리상품권·지역사랑상품권, 100분의 20),
    법률 제19936호 부칙 제35조(이 법 시행 이후 과세표준을 신고하는 경우부터), 법률 제21223호(2026.1.1. 시행) 부칙 제31조(같은 문언),
    법률 제21612호(공포일 시행, 2026.5.12.) 부칙 제4조(시행일이 속하는 과세연도에 지출하는 분부터), 법률 제17759호(2021.1.1. 시행) 부칙 제35조(이월공제기간 — 신고분부터).
  · 부가가치세법 2026 시행본 — 제60조제3항제1호·제2호(4퍼센트), 법률 제21218호 부칙 제3조(시행 전 발급·발급받은 경우 종전), 법률 제18577호 부칙 제7조(제29조제9항제2호).
  · 법인세법 시행령 36738호 시행본 부칙 — 31443호 제9조·제19조(2021.1.1. 이후 접대비로 지출하는 분), 34266호 제7조(2024.1.1. 이후 업무용승용차 관련비용 지출분),
    34266호 제2조(제10조제1항제7호), 29529호 제7조(시행 이후 재판상 화해 등이 확정되는 분).
  · 법인세법 21217호 시행본 부칙 — 16008호 제4조(신고분), 16833호 제4조(제24조제2항·제5항·제6항, 신고분), 21217호 제3조(개시 사업연도 지출분).
  · 국제조세조정에 관한 법률 21215호 시행본 부칙 — 17651호 제5조①·제17조·제23조①·제28조, 19191호 제3조·제4조.
기대값은 위 문언으로 손으로 계산한 값이다.
"""
from tests._helpers import call

M = 1_000_000


def ok(r):
    assert "error" not in r, r
    return r


# ── P1 기업업무추진비 전통시장등 추가한도 — 신고일 기준(19936 부칙§35·21223 부칙§31) ──
# 수입금액 10억(0.3% → 300만), 중소 기본 3,600만 → 일반한도 3,900만. 전통시장 지출 5,000만.
ENT = dict(sme=True, general_revenue=1_000 * M, expensed=100 * M, market=50 * M)


def test_market_rate_by_filing_noncalendar_2024():
    # 2024.11.1.~2025.10.31. 사업연도, 신고기한 2026.1.31. → 20%: min(5,000만, 3,900만 × 20%) = 780만
    r = ok(call("entertainment_limit", dict(ENT, year=2024, fy_start="2024-11-01")))
    assert r["결과"]["전통시장한도"] == 7_800_000 and r["결과"]["한도"] == 46_800_000 and r["결과"]["한도초과(기타사외유출)"] == 53_200_000
    assert r["기준"]["신고일"].startswith("2026-01-31") and r["기준"]["전통시장등_대상"] == ["전통시장", "지역사랑상품권"]


def test_market_rate_by_filing_calendar_2024_and_short_2025():
    # 역년 2024 → 신고 2025.3.31. → 10% = 390만
    assert ok(call("entertainment_limit", dict(ENT, year=2024, fy_start="2024-01-01", fy_end="2024-12-31")))["결과"]["전통시장한도"] == 3_900_000
    # 2025.1.1.~6.30. 단기 사업연도 → 신고 2025.9.30.(2026.1.1. 전) → 10% = 390만(사업연도 표만 보면 20%)
    r = ok(call("entertainment_limit", dict(ENT, year=2025, fy_start="2025-01-01", fy_end="2025-06-30")))
    assert r["결과"]["전통시장한도"] == 3_900_000 and r["기준"]["전통시장등_대상"] == ["전통시장"]
    # 같은 사업연도라도 실제 신고일을 넣으면 그 날로
    assert ok(call("entertainment_limit", dict(ENT, year=2025, fy_start="2025-01-01", fy_end="2025-06-30", filing_date="2026-01-02")))["결과"]["전통시장한도"] == 7_800_000


def test_market_rate_2022_start_filed_2024():
    # 2022.12.1.~2023.11.30. → 신고기한 2024.2.29.(2024.1.1. 이후) → 10% = 390만. 사업연도 표(2022)에는 비율이 없어 날짜 없이는 0
    assert ok(call("entertainment_limit", dict(ENT, year=2022, fy_start="2022-12-01")))["결과"]["전통시장한도"] == 3_900_000
    assert ok(call("entertainment_limit", dict(ENT, year=2022)))["결과"]["전통시장한도"] == 0


def test_market_no_date_keeps_result_with_warning():
    r = ok(call("entertainment_limit", dict(ENT, year=2024)))
    assert r["결과"]["전통시장한도"] == 3_900_000 and "기준" not in r
    assert any("filing_date" in w for w in r["주의"])
    assert "주의" not in ok(call("entertainment_limit", dict(ENT, year=2019, market=0, general_revenue=0)))


# ── P1 온누리상품권 — 2026.5.12.이 속하는 사업연도 지출분(21612 부칙§4) ──
LEDGER = [{"항목": "거래처 접대", "금액": 50 * M, "증빙": "적격"},
          {"항목": "온누리상품권", "금액": 3 * M, "증빙": "적격", "성격": "온누리상품권"},
          {"항목": "지역사랑상품권", "금액": 2 * M, "증빙": "적격", "성격": "지역사랑상품권"}]
ADJ = dict(sme=True, ledger=LEDGER, revenue={"매출액": 1_000 * M})


def test_onnuri_included_for_fy_containing_2026_05_12():
    # 2025.7.1.~2026.6.30.(year=2025) — 시행일이 속하는 사업연도 → 온누리 포함: 전통시장등 500만 ≤ 780만 → 한도 4,400만, 초과 5,500만 − 4,400만 = 1,100만
    r = ok(call("entertainment_adjustment", dict(ADJ, year=2025, fy_start="2025-07-01")))
    assert r["결과"]["한도"] == 44 * M and r["결과"]["한도초과"] == 11 * M and r["계산"]["온누리상품권_지출"] == 3 * M


def test_onnuri_excluded_for_calendar_2025_and_included_2026():
    # 역년 2025(신고 2026.3.31.): 20%, 지역사랑 200만만 → 한도 4,100만, 초과 1,400만. 온누리는 대상 밖 판단
    for extra in ({}, {"fy_start": "2025-01-01", "fy_end": "2025-12-31"}):
        r = ok(call("entertainment_adjustment", dict(ADJ, year=2025, **extra)))
        assert r["결과"]["한도"] == 41 * M and r["결과"]["한도초과"] == 14 * M and r["계산"]["온누리상품권_지출"] == 0
        assert any(j["항목"] == "전통시장등 추가한도 대상 밖" for j in r["판단"])
    r = ok(call("entertainment_adjustment", dict(ADJ, year=2026, fy_start="2026-01-01")))
    assert r["결과"]["한도"] == 44 * M


def test_adjustment_short_fy_2025_filed_2025_no_local_voucher():
    # 2025.1.1.~6.30. → 신고 2025.9.30. → 10%, 전통시장만 → 지역사랑·온누리 모두 대상 밖 → 추가한도 0 → 한도 3,900만, 초과 1,600만
    r = ok(call("entertainment_adjustment", dict(ADJ, year=2025, fy_start="2025-01-01", fy_end="2025-06-30")))
    assert r["결과"]["한도"] == 39 * M and r["결과"]["한도초과"] == 16 * M


# ── P2 적격증빙 기준 1만→3만 원 — 지출일(영 31443 부칙§9) ──
def test_receipt_threshold_by_spending_date_adjustment():
    base = dict(sme=True, year=2020, fy_start="2020-07-01", revenue={"매출액": 0})
    after = ok(call("entertainment_adjustment", dict(base, ledger=[{"항목": "식대", "금액": 20_000, "증빙": "영수증 등", "지출일": "2021-03-01"}])))
    before = ok(call("entertainment_adjustment", dict(base, ledger=[{"항목": "식대", "금액": 20_000, "증빙": "영수증 등", "지출일": "2020-10-01"}])))
    nodate = ok(call("entertainment_adjustment", dict(base, ledger=[{"항목": "식대", "금액": 20_000, "증빙": "영수증 등"}])))
    assert after["결과"]["직부인_기타사외유출"] == 0 and after["결과"]["시부인_대상"] == 20_000
    assert before["결과"]["직부인_기타사외유출"] == 20_000
    assert nodate["결과"]["직부인_기타사외유출"] == 20_000 and any("지출일" in w for w in nodate["주의"])


def test_missing_receipt_by_spending_date():
    f = lambda **k: ok(call("missing_receipt_disallowance", k))          # noqa: E731
    assert f(year=2020, items=[{"amount": 20_000, "spent_on": "2021-03-01"}])["결과"]["손금불산입"] == 0
    assert f(year=2020, items=[{"amount": 20_000, "spent_on": "2020-12-31"}])["결과"]["손금불산입"] == 20_000
    r = f(year=2020, items=[{"amount": 20_000}], fy_start="2020-07-01")
    assert r["결과"]["손금불산입"] == 20_000 and "spent_on" in r["주의"][0]
    assert "주의" not in f(year=2020, items=[{"amount": 20_000}], fy_start="2020-01-01", fy_end="2020-12-31")
    assert "주의" not in f(year=2021, items=[{"amount": 20_000}]) and f(year=2021, items=[{"amount": 20_000}])["결과"]["손금불산입"] == 0
    assert f(year=2016, items=[{"amount": 200_001, "congratulatory": True}])["결과"]["손금불산입"] == 200_001


# ── P2 2020 수입금액 특례 일할(조특법 제136조④⑤) ──
def test_2020_revenue_special_prorated():
    # 2019.7.1.~2020.6.30.: 350만 × 182/366 + 200만(2019 개시 표 0.2%) × 184/366 = 2,745,902
    r = ok(call("entertainment_limit", dict(sme=True, year=2019, general_revenue=1_000 * M, expensed=0, fy_start="2019-07-01")))
    assert r["결과"]["수입금액한도"] == 2_745_902 and r["기준"]["2020년_일수"] == "182/366"
    # 2020.7.1.~2021.6.30.: 350만 × 184/365 + 300만 × 181/365 = 3,252,055
    assert ok(call("entertainment_limit", dict(sme=True, year=2020, general_revenue=1_000 * M, expensed=0, fy_start="2020-07-01")))["결과"]["수입금액한도"] == 3_252_055
    # 날짜 없음: 종전대로 2020 전액 특례 350만 + 주의
    r = ok(call("entertainment_limit", dict(sme=True, year=2020, general_revenue=1_000 * M, expensed=0)))
    assert r["결과"]["수입금액한도"] == 3_500_000 and any("일할" in w for w in r["주의"])


# ── P1 가공 세금계산서 — 발급·수취일(21218 부칙§3) ──
def test_fake_invoice_requires_issue_date():
    r = call("invoice_penalty", {"supply_amount": 100 * M, "kind": "가공"})
    assert "error" in r and "issued_on" in r["문제"][0]
    assert ok(call("invoice_penalty", {"supply_amount": 100 * M, "kind": "가공", "issued_on": "2025-12-31"}))["결과"]["가산세"] == 3 * M
    assert ok(call("invoice_penalty", {"supply_amount": 100 * M, "kind": "가공", "issued_on": "2026-01-01"}))["결과"]["가산세"] == 4 * M
    assert ok(call("invoice_penalty", {"supply_amount": 100 * M, "kind": "가공", "supplied_on": "2026-03-01"}))["결과"]["가산세"] == 4 * M
    assert ok(call("invoice_penalty", {"supply_amount": 100 * M, "kind": "가공", "issued_on": "2017-12-31"}))["결과"]["가산세"] == 2 * M
    b = call("invoice_penalty_bundle", {"items": [{"deal": "A", "kind": "가공", "supply_amount": 100 * M}]})
    assert "error" in b
    b = ok(call("invoice_penalty_bundle", {"items": [{"deal": "A", "kind": "가공", "supply_amount": 100 * M, "issued_on": "2026-02-01"},
                                                     {"deal": "A", "kind": "지연수취", "supply_amount": 100 * M, "supplied_on": "2026-02-01"}]}))
    assert b["결과"]["가산세_합계"] == 4 * M          # 지연수취는 같은 deal 가공으로 배제(제60조⑨)


# ── P2 업무용승용차 번호판 — 2024.1.1. 이후 지출분(영 34266 부칙§7) ──
CAR = dict(upkeep=10 * M, depreciation=8 * M, booked_depreciation=8 * M, log_kept=True, business_ratio=1.0, plate_ok=False)


def test_plate_requirement_by_spending_date():
    # 2023.7.1.~2024.6.30.(366일), 2024년분 182일 → 업무사용비율 1 × (1 − 182/366): 유지비 손금불산입 1,000만 × 182/366 = 4,972,678
    r = ok(call("business_car_expense", dict(CAR, year=2023, fy_start="2023-07-01")))
    assert r["결과"]["유지비 손금불산입(상여)"] == 4_972_678 and r["결과"]["감가상각 사적사용 손금불산입(상여)"] == 3_978_142
    r = ok(call("business_car_expense", dict(CAR, year=2023, fy_start="2023-07-01", share_from_2024=0.5)))
    assert r["결과"]["유지비 손금불산입(상여)"] == 5 * M and r["결과"]["감가상각 사적사용 손금불산입(상여)"] == 4 * M
    assert ok(call("business_car_expense", dict(CAR, year=2023, fy_start="2023-01-01", fy_end="2023-12-31")))["결과"]["유지비 손금불산입(상여)"] == 0
    r = ok(call("business_car_expense", dict(CAR, year=2023)))          # 날짜 없음: 종전대로 미적용 + 주의
    assert r["결과"]["유지비 손금불산입(상여)"] == 0 and any("fy_start" in w for w in r["주의"])
    assert ok(call("business_car_expense", dict(CAR, year=2024)))["결과"]["유지비 손금불산입(상여)"] == 10 * M


# ── P2 기부금 이월분 먼저(16833 부칙§4)·사회적기업 20%(16008 부칙§4①) — 신고일 ──
DON = dict(base_income=100 * M, general=20 * M, general_carry=5 * M)


def test_donation_carry_first_by_filing():
    # 2018.12.1.~2019.11.30. → 신고 2020.2.29. → 이월분 먼저: 한도 1,000만 중 이월 500만 + 당기 500만, 한도초과 1,500만
    r = ok(call("donation_limit", dict(DON, year=2018, fy_start="2018-12-01")))
    assert r["결과"]["이월분 손금산입"] == 5 * M and r["결과"]["한도초과(기타사외유출)"] == 15 * M
    # 날짜 없는 2018(역년, 신고 2019.3.) → 당기분 먼저: 당기 1,000만, 이월 0, 한도초과 1,000만
    r = ok(call("donation_limit", dict(DON, year=2018)))
    assert r["결과"]["이월분 손금산입"] == 0 and r["결과"]["한도초과(기타사외유출)"] == 10 * M and r["주의"]
    # 2019.1.1.~6.30. 단기 → 신고 2019.9.30.(2020.1.1. 전) → 당기분 먼저(연도표 2019는 이월 먼저)
    assert ok(call("donation_limit", dict(DON, year=2019, fy_start="2019-01-01", fy_end="2019-06-30")))["결과"]["이월분 손금산입"] == 0
    assert ok(call("donation_limit", dict(DON, year=2019)))["결과"]["이월분 손금산입"] == 5 * M


def test_donation_social_enterprise_by_filing():
    # 2017.12.1.~2018.11.30. → 신고 2019.2.28. → 20%: 한도 2,000만, 일반 3,000만 → 초과 1,000만. 날짜 없으면 10% → 초과 2,000만
    a = dict(base_income=100 * M, general=30 * M, social_enterprise=True)
    assert ok(call("donation_limit", dict(a, year=2017, fy_start="2017-12-01")))["결과"]["한도초과(기타사외유출)"] == 10 * M
    assert ok(call("donation_limit", dict(a, year=2017)))["결과"]["한도초과(기타사외유출)"] == 20 * M
    # 2026 개시 사업연도는 30%(개시 사업연도 기준) 그대로
    assert ok(call("donation_limit", dict(a, year=2026, fy_start="2026-01-01")))["결과"]["한도초과(기타사외유출)"] == 0


# ── P2 최저한세 미공제 이월기간 10년 — 2021.1.1. 이후 신고분(법률 제17759호 부칙 제35조) ──
MT = {"sme": True, "net_income": 400 * M, "income_add": 50 * M, "income_deduct": 50 * M,
      "reductions": [{"code": "112", "amount": 10 * M}],
      "credits": [{"code": "14Z", "current": 6 * M}, {"code": "13W", "current": 30 * M, "carryforward": []}]}


def _carry_text(r):
    return next(j["결론"] for j in r["판단"] if j["항목"] == "이월공제")


def test_min_tax_carry_period_by_filing():
    assert "10년" in _carry_text(ok(call("minimum_tax_adjustment", dict(MT, year=2020))))
    r = ok(call("minimum_tax_adjustment", dict(MT, year=2020, fy_start="2020-01-01", fy_end="2020-06-30")))   # 신고 2020.9.30.
    assert "5년" in _carry_text(r) and r["기준"]["이월공제기간_10년"] is False
    # 2019.12.1.~2020.11.30. → 신고 2021.2.28. → 10년. 2014 발생분(종전 5년 → 2019 개시 사업연도까지)은 아직 지나지 않아 공제 가능
    c14 = dict(MT, credits=[{"code": "13W", "current": 0, "carryforward": [{"year": 2014, "amount": 1 * M}]}])
    r = ok(call("minimum_tax_adjustment", dict(c14, year=2019, fy_start="2019-12-01")))
    assert r["기준"]["이월공제기간_10년"] is True
    ok(call("minimum_tax_adjustment", dict(c14, year=2019)))


# ── P2 화해 등 대손(영 제19조의2①10호) — 확정일(29529 부칙§7) ──
def _bd(year, **w):
    item = {"kind": "화해·확정판결", "amount": 10 * M, "arose_in": "당기", **{k: v for k, v in w.items() if k not in ("fy_start", "fy_end")}}
    return call("bad_debt_adjustment", {"year": year, "sme": True, "book": {"opening": 0, "offset": 10 * M, "provision": 0, "closing": 0},
                                        "receivables_prev_end_book": 1_000 * M, "receivables_end_book": 1_000 * M, "writeoffs": [item],
                                        **{k: v for k, v in w.items() if k in ("fy_start", "fy_end")}})


def test_settlement_bad_debt_by_confirmation_date():
    # 2018.7.1.~2019.6.30. 사업연도, 2019.3.15. 확정 → 10호 대손 인정
    r = ok(_bd(2018, date="2019-03-15", fy_start="2018-07-01"))
    assert "10호 시행 전" not in str(r["판단"]) and r["결과"]["손금불산입_합계"] == 0
    # 같은 사업연도, 2019.1.15. 확정 → 시행 전
    assert "10호 시행 전" in str(ok(_bd(2018, date="2019-01-15", fy_start="2018-07-01"))["판단"])
    # 역년 2018(날짜 없음) + 확정일 2019.3.1. → 사업연도 밖 → 시행 전 처리 + 주의
    r = ok(_bd(2018, date="2019-03-01"))
    assert "10호 시행 전" in str(r["판단"]) and r["주의"]
    # 비역년 2018 개시 사업연도가 2019.2.12.을 걸치는데 확정일이 없으면 계산하지 않음
    assert "error" in _bd(2018, fy_start="2018-07-01")


# ── P2 국제거래명세서·해외현지법인 자료 6개월 기한 — 종전 기한 미도과분(17651 부칙§5①·§17) ──
def test_six_month_deadline_for_unexpired_old_deadline():
    # 2019.11.1.~2020.10.31. → 종전 기한 2021.1.31.(2021.1.1. 현재 미도과) → 6개월: 2021.4.30.
    r = ok(call("corporate_filing_obligations", {"year": 2019, "foreign_direct_investment": True, "related_goods": 1, "fy_start": "2019-11-01"}))
    assert r["결과"]["해외직접투자명세"]["기한"] == "2021-04-30" and r["결과"]["제출기한"].startswith("2021-04-30")
    # 2019.10.1.~2020.9.30. → 종전 기한 2020.12.31.(이미 지남) → 종전 기한
    r = ok(call("corporate_filing_obligations", {"year": 2019, "foreign_direct_investment": True, "related_goods": 1, "fy_start": "2019-10-01"}))
    assert r["결과"]["해외직접투자명세"]["기한"] == "2020-12-31" and r["결과"]["제출기한"].startswith("2020-12-31")
    # 날짜 없음(역년 2019·2020): 종전 결과 그대로 + 주의
    r = ok(call("corporate_filing_obligations", {"year": 2019, "foreign_direct_investment": True}))
    assert r["결과"]["해외직접투자명세"]["기한"] == "2020-03-31" and r["주의"]
    assert ok(call("corporate_filing_obligations", {"year": 2020, "foreign_direct_investment": True}))["결과"]["해외직접투자명세"]["기한"] == "2021-06-30"


def test_intl_statement_deadline_noncalendar():
    p = [{"name": "A", "sales": {"inventory": 600 * M}}]
    r = ok(call("international_transaction_statement", {"year": 2019, "parties": p, "fy_start": "2019-11-01", "fy_end": "2020-10-31"}))
    assert any(j["항목"] == "제출기한" and j["결론"].startswith("2021-04-30") for j in r["판단"])
    r = ok(call("international_transaction_statement", {"year": 2019, "parties": p, "fy_start": "2019-10-01", "fy_end": "2020-09-30"}))
    assert any(j["항목"] == "제출기한" and j["결론"].startswith("2020-12-31") for j in r["판단"])


# ── P2 외부감사 신기준 — 2019.11.1. 이후 시작 사업연도(대통령령 제29269호 부칙 제2조, 코드 근거) ──
def test_external_audit_new_criteria_by_fy_start():
    a = {"year": 2019, "revenue_prev": 60_000 * M}              # 매출 600억 — 신기준(매출 500억)만 해당
    assert ok(call("corporate_filing_obligations", dict(a, fy_start="2019-11-01")))["결과"]["외부감사"]["대상"] is True
    assert ok(call("corporate_filing_obligations", dict(a, fy_start="2019-10-01")))["결과"]["외부감사"]["대상"] is False
    assert ok(call("corporate_filing_obligations", a))["결과"]["외부감사"]["대상"] is False


# ── P3 문구·어휘 ──
def test_wording_items():
    from korean_tax_calc_mcp import vocab
    assert vocab.rule("간이과세자_납부의무면제", 2018)["기준"] == 30 * M                 # 16101 부칙§6: 2019.1.1. 이후 신고분 → 2018 과세기간
    r = call("simplified_vat_return", {"year": 2021, "business_type": "소매업", "ledger": {"공급": [{"항목": "카드매출", "금액": 1}], "매입": []}})
    assert "error" in r and "17653" in r["error"]
    assert "주의" in ok(call("loss_carryforward_limit", {"year": 2024, "sme": False}))
    r = ok(call("bundled_supply_split", {"total_price": 100 * M, "vat_included": False, "standard_value": {"building": 40 * M, "land": 60 * M}, "supply_date": "2021-03-01"}))
    assert "2호 사유 없음" in r["범위"]
