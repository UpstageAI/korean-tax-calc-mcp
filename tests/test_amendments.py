"""조문 개정·미구현 규정 반영 — 원천징수 등 납부지연가산세 2026.7.1. 개정(법률 제21212호)과 납부고지 후 기간,
증여세 납부세액공제 한도(상증법 제58조②), 대손금 채무보증 구상채권 예외(법인세법 시행령 제19조의2⑥)·전기 유보 정리.
기대값은 조문을 손으로 계산한 값."""
import json

from korean_tax_calc_mcp import server as S
from tests._helpers import call as c

M = 1_000_000


def wl(**a):
    return c("withholding_late_payment_penalty", a)


# ── 1. 원천징수 등 납부지연가산세(국세기본법 제47조의5) ──────────────────────────
# 개정(2025.12.23. 법률 제21212호, 2026.7.1. 시행): 2호 일수 '납부고지일(납부일)의 전날까지', 3호 지정납부기한 후 월 1만분의 67(영 제27조의4②),
# 4호 독촉비용, ⑤ 150만원 미만은 3호·4호 제외. 부칙 제4조: 2026.6.30. 이전에 지정납부기한이 지난 경우는 종전 규정.

def test_old_rule_before_2026_07_unchanged():
    # 고지 전 납부 2026.6.30. — 종전: 3% 150,000 + 5,000,000 × 355일 × 22/100,000 = 390,500 → 10% 한도 500,000
    assert wl(unpaid_tax=5 * M, due="2025-07-10", until="2026-06-30")["결과"]["가산세"] == 500_000
    assert wl(unpaid_tax=5 * M, due="2025-07-10", until="2025-08-09")["결과"]["가산세"] == 183_000


def test_new_rule_self_payment_counts_to_day_before():
    # 개정 2호: 2026.6.11.~7.19.(납부일 전날) 39일 → 1,000,000 × 39 × 22/100,000 = 8,580, + 3% 30,000 = 38,580
    # (종전대로 납부일까지 40일이면 38,800)
    r = wl(unpaid_tax=1 * M, due="2026-06-10", until="2026-07-20")
    assert "error" not in r, r
    assert r["결과"]["가산세"] == 38_580
    assert r["결과"]["일수"] == 39
    assert "제21212호" in json.dumps(r, ensure_ascii=False)


def test_new_rule_after_notice_monthly():
    # 법정납부기한 2026.3.10., 고지 2026.7.1., 지정납부기한 2026.7.31., 납부 2026.10.15.
    # 1호 300,000 / 2호 3.11.~6.30.(고지일 전날) 112일 × 22/100,000 × 1천만 = 246,400 (합 546,400 ≤ 10% 1,000,000)
    # 3호 8.1.~10.14. 경과 개월 2(8월·9월) × 67/10,000 × 1천만 = 134,000 → 680,400 (50% 한도 5,000,000)
    r = wl(unpaid_tax=10 * M, due="2026-03-10", until="2026-07-01", notice_due="2026-07-31", paid_on="2026-10-15")
    assert "error" not in r, r
    assert r["결과"]["가산세"] == 680_400
    assert r["결과"]["고지후분"] == 134_000
    assert r["결과"]["경과_개월"] == 2
    r = wl(unpaid_tax=10 * M, due="2026-03-10", until="2026-07-01", notice_due="2026-07-31", paid_on="2026-10-15",
           dunning_fee=2_000)
    assert r["결과"]["가산세"] == 682_400      # 4호 독촉비용 더함


def test_transition_old_rule_when_designated_due_passed_by_june():
    # 부칙 제4조: 지정납부기한(2026.5.31.)이 2026.6.30. 이전에 지남 → 납부가 7.1. 이후라도 종전 규정
    # 1호 300,000 / 2호 고지 전 1.11.~4.30.(고지일 제외) 110일 = 242,000 / 고지 후 6.1.~8.31. 92일 = 202,400 → 744,400
    r = wl(unpaid_tax=10 * M, due="2026-01-10", until="2026-05-01", notice_due="2026-05-31", paid_on="2026-08-31")
    assert "error" not in r, r
    assert r["결과"]["가산세"] == 744_400
    assert "부칙 제4조" in json.dumps(r, ensure_ascii=False)
    # 종전 규정엔 4호가 없음
    assert "error" in wl(unpaid_tax=10 * M, due="2026-01-10", until="2026-05-01", notice_due="2026-05-31",
                         paid_on="2026-08-31", dunning_fee=2_000)


def test_new_rule_small_notice_skips_monthly():
    # ⑤ 납부고지서별·세목별 세액 150만원 미만(1,000,000 + 고지 전 가산세 41,220) → 3호 적용 안 함
    # 1호 30,000 + 2호 6.11.~7.31. 51일 × 22/100,000 × 1백만 = 11,220 → 41,220
    r = wl(unpaid_tax=1 * M, due="2026-06-10", until="2026-08-01", notice_due="2026-08-31", paid_on="2026-12-15")
    assert "error" not in r, r
    assert r["결과"]["가산세"] == 41_220
    assert r["결과"]["고지후분"] == 0


def test_old_rule_five_year_and_half_cap():
    # 2026-11-11 정정: 법정납부기한을 2020년으로 — 2020.1.1. 전 성립분은 구 제47조의5(10% 한도뿐, 법률 제16841호 부칙 제21조)라 50% 한도 확인에 쓸 수 없음
    # 종전(2026.7.1. 개정 전): 고지 전 2020.3.11.~2021.1.1. 297일 × 25/100,000 = 742,500 + 3% 300,000 → 10% 한도 1,000,000
    # 고지 후 2021.2.1.부터 5년(④, 1,826일): 2022.2.14.까지 379일 × 25/100,000 = 947,500, 이후 1,447일 × 22/100,000 = 3,183,400
    # 합 5,130,900 → 50% 한도 5,000,000
    r = wl(unpaid_tax=10 * M, due="2020-03-10", until="2021-01-02", notice_due="2021-01-31", paid_on="2026-06-15")
    assert "error" not in r, r
    assert r["결과"]["가산세"] == 5_000_000
    assert r["결과"]["한도_50%"] == 5_000_000


def test_notice_inputs_checked():
    assert "error" in wl(unpaid_tax=10 * M, due="2026-03-10", until="2026-07-01", notice_due="2026-07-31")
    assert "error" in wl(unpaid_tax=10 * M, due="2026-03-10", until="2026-07-01", paid_on="2026-10-15")
    assert "error" in wl(unpaid_tax=10 * M, due="2026-03-10", until="2026-08-10", notice_due="2026-07-31", paid_on="2026-10-15")


# ── 2. 증여세 납부세액공제 한도(상증법 제58조②) ────────────────────────────────
# 한도 = 산출세액(제56조) × 가산한 증여재산의 과세표준 ÷ 합친 금액의 과세표준

def test_gift_credit_limit_binds():
    # 자녀→부모 2015년 증여 2.3억(그때 직계비속 공제 3천만 → 과세표준 2억, 산출 3천만), 2025.11.20. 1천만 추가
    # 합산 2.4억 − 공제 5천만 = 과세표준 1.9억 → 산출 1천만 + 9천만 × 20% = 28,000,000
    # 한도 = 28,000,000 × 2억 ÷ 1.9억 = 29,473,684(원 미만 절사) < 기납부 30,000,000, 산출세액에서 공제하므로 28,000,000까지
    r = c("gift_tax", {"gift_date": "2025-11-20", "gift_value": 10 * M, "relation": "직계비속",
                       "prior_gifts_same_donor": 230 * M, "prior_deduction_same_donor": 30 * M,
                       "prior_gift_tax_paid": 30 * M})
    assert "error" not in r, r
    assert r["결과"]["산출세액"] == 28 * M
    assert r["계산"]["납부세액공제_한도"] == 29_473_684
    assert r["결과"]["기납부세액공제"] == 28 * M
    assert r["결과"]["납부할세액"] == 0
    assert "제58조②" in json.dumps(r, ensure_ascii=False)


def test_gift_credit_limit_not_binding_shown():
    # 합산 과세표준 6.5억, 산출 1.35억, 가산분 과세표준 1억 − 5천만 = 5천만 → 한도 135,000,000 × 5천만/6.5억 = 10,384,615 ≥ 5,000,000
    r = c("gift_tax", {"gift_date": "2025-11-20", "gift_value": 900 * M, "relation": "직계존속", "assumed_debt": 300 * M,
                       "prior_gifts_same_donor": 100 * M, "prior_deduction_same_donor": 50 * M,
                       "prior_gift_tax_paid": 5 * M, "filed": True})
    assert r["결과"]["기납부세액공제"] == 5 * M
    assert r["계산"]["납부세액공제_한도"] == 10_384_615
    assert r["결과"]["납부할세액"] == 126_100_000


def test_gift_credit_needs_aggregated_prior():
    # 제58조①: 제47조②로 가산한 증여재산에 대한 세액만 — 합산할 사전증여가 없으면 공제할 것이 없음
    r = c("gift_tax", {"gift_date": "2025-11-20", "gift_value": 100 * M, "relation": "직계존속", "prior_gift_tax_paid": 5 * M})
    assert "error" in r


# ── 3. 대손금: 영 제19조의2⑥ 채무보증 구상채권 예외, 전기 유보 정리 ─────────────────
BOOK = {"opening": 20_000_000, "offset": 0, "provision": 10_000_000, "closing": 30_000_000}


def _bd(writeoffs, **kw):
    args = dict(year=2025, sme=True, book=BOOK, receivables_prev_end_book=1_000_000_000,
                receivables_end_book=1_200_000_000, writeoffs=writeoffs)
    args.update(kw)
    return S.bad_debt_adjustment(**args)


GUAR = {"kind": "회수불능", "amount": 500_000_000, "arose_in": "당기", "booked": "손비",
        "excluded_reason": "채무보증구상채권", "recipient": "법인"}


def test_guarantee_exception_item_recognized():
    # 영 제19조의2⑥2호(금융회사 등이 행한 채무보증) 구상채권은 법 제19조의2②1호 괄호로 제외 대상이 아님 → 일반 대손 요건(①8호)
    r = _bd([dict(GUAR, guarantee_item=2)])
    assert "error" not in r, r
    assert r["계산"]["세법상 당기 대손금"] == 500_000_000
    assert not [s for s in r["세무조정"] if "19조의2②" in s["구분"]]
    assert "제19조의2⑥2호" in json.dumps(r["판단"], ensure_ascii=False)


def test_guarantee_exception_by_effective_date():
    # 6호(해외자원개발)는 2023.2.28. 신설(부칙 제5조: 시행 이후 회수할 수 없게 되는 경우) — 그 전 회수불능은 여전히 제외
    before = _bd([dict(GUAR, guarantee_item=6, date="2022-12-20")], year=2022)
    assert before["계산"]["세법상 당기 대손금"] == 0
    after = _bd([dict(GUAR, guarantee_item=6, date="2023-05-02")], year=2023)
    assert after["계산"]["세법상 당기 대손금"] == 500_000_000
    # 5호 전기통신업은 2018.2.13. 개정(부칙 제5조: 시행 이후 손금 산입분) — 2017년은 건설업만
    tel = _bd([dict(GUAR, guarantee_item=5, guarantor_business="전기통신업", date="2017-12-01")], year=2017)
    assert tel["계산"]["세법상 당기 대손금"] == 0
    con = _bd([dict(GUAR, guarantee_item=5, guarantor_business="건설업", date="2017-12-01")], year=2017)
    assert con["계산"]["세법상 당기 대손금"] == 500_000_000
    # 8호(핵심자원)는 2026.2.27. 신설
    assert _bd([dict(GUAR, guarantee_item=8, date="2026-02-20")], year=2026)["계산"]["세법상 당기 대손금"] == 0
    assert _bd([dict(GUAR, guarantee_item=8, date="2026-03-15")], year=2026)["계산"]["세법상 당기 대손금"] == 500_000_000


def test_guarantee_item_validated():
    assert "error" in _bd([dict(GUAR, guarantee_item=9)])
    no_excl = {k: v for k, v in GUAR.items() if k != "excluded_reason"}
    assert "error" in _bd([dict(no_excl, guarantee_item=2)])


def test_prior_yubo_excluded_receivable_cleared_on_event():
    # 전기에 장부 대손·세무 부인(유보)된 특수관계인 업무무관 가지급금 3억 — 당기 회수불능 확정:
    # 유보 정리 손금산입(△유보) 3억 + 손금불산입 3억(귀속자 임원 → 상여, 영 제106조①1호). 대손금·설정대상 채권에는 넣지 않음
    w = {"kind": "회수불능", "amount": 300_000_000, "arose_in": "당기", "booked": "전기부인",
         "excluded_reason": "특수관계인업무무관가지급금", "recipient": "임원", "lent_on": "2022-01-10"}
    r = _bd([w])
    assert "error" not in r, r
    assert r["계산"]["세법상 당기 대손금"] == 0
    assert r["계산"]["세법상 전기말 채권"] == 1_000_000_000
    adj = [(s["조정"], s["금액"], s["소득처분"]) for s in r["세무조정"] if "19조의2②" in s["구분"]]
    assert ("손금산입", 300_000_000, "△유보") in adj
    assert ("손금불산입", 300_000_000, "상여") in adj
    # 대손 요건 전(부도 3개월)이면 유보 그대로
    r2 = _bd([dict(w, kind="부도6개월", instrument="받을어음", months_since_default=3)])
    assert not [s for s in r2["세무조정"] if "19조의2②" in s["구분"]]
