"""연도 의존 전수 점검(2026-11-11) 남은 항목(Claude 작성).
조문 확인: 상증령 제49조①(20190211 전후 3개월 / 20190212 전 6개월·후 3개월), 법인령 제19조의2①10호(20190211 삭제 상태 / 20190212 신설)·대통령령 제29529호 부칙 제7조,
소득령 제81조⑤(20231231 5만원 / 20241231 8만원)·대통령령 제34265호 부칙 제18조, 조특법 제58조(20221231·20230101 삭제 / 20231231 고향사랑),
소득세법 제84조(20160630 / 20160701), 상증법 제53조4호(20250313 6촌·4촌 / 20250314 4촌·3촌)."""
import pytest
from _helpers import call as c

M = 1_000_000


# ── 증여재산 평가기간 ───────────────────────────────────────────────────────
def val(kind, vd, sale_on):
    r = c("inheritance_gift_valuation", {"kind": kind, "valuation_date": vd, "supplementary_value": 500 * M,
                                         "market_values": [{"대상": "해당재산", "종류": "매매", "가액": 700 * M, "날짜": sale_on}]})
    assert "error" not in r, r
    return r["결과"]

def test_gift_valuation_window_before_feb_2019():
    old = val("증여", "2019-02-11", "2018-10-01")      # 4개월여 전 매매 — 전후 3개월 밖 → 보충적 평가액
    new = val("증여", "2019-02-12", "2018-10-01")      # 전 6개월 안 → 매매가액(시가)
    assert old["평가액"] == 500 * M and new["평가액"] == 700 * M
    assert val("증여", "2019-02-11", "2018-12-01")["평가액"] == 700 * M     # 종전에도 3개월 안이면 시가

def test_inheritance_window_unchanged():
    assert val("상속", "2018-06-01", "2018-01-15")["평가액"] == 700 * M      # 상속은 전후 6개월 그대로


# ── 대손 10호(재판상 화해 등) ────────────────────────────────────────────────
def bd(year, **w):
    return c("bad_debt_adjustment", {"year": year, "sme": True, "book": {"opening": 0, "offset": 10 * M, "provision": 10 * M, "closing": 0},
                                     "receivables_prev_end_book": 1000 * M, "receivables_end_book": 1000 * M,
                                     "writeoffs": [{"kind": "화해·확정판결", "amount": 10 * M, "arose_in": "당기", **w}]})

def test_bad_debt_item10_only_from_2019_02_12():
    assert "10호 시행 전" in str(bd(2018))
    assert "인정(대손금, 결산조정)" in str(bd(2020))
    assert "error" in bd(2019)                                           # 확정일 필요
    assert "10호 시행 전" in str(bd(2019, date="2019-02-11"))
    assert "인정(대손금, 결산조정)" in str(bd(2019, date="2019-02-12"))


# ── 개인 기부금: 자원봉사 1일 가액, 고향사랑, 이월 문구 ────────────────────────────
def dn(year, **kw):
    return c("individual_donation_expense", {"year": year, "base_income": 100 * M, **kw})

@pytest.mark.parametrize("year,served,labor", [(2020, None, 100_000), (2023, None, 100_000), (2024, "2024-02-28", 100_000),
                                               (2024, "2024-02-29", 160_000), (2025, None, 160_000)])
def test_volunteer_per_day_by_year(year, served, labor):
    v = {"hours": 16}
    if served: v["served_on"] = served
    r = dn(year, volunteer=v)
    assert "error" not in r, r
    assert r["결과"]["특례기부금_산입"] == labor                      # 2일 × 5만원 또는 8만원

def test_volunteer_2024_needs_date_and_hometown_from_2023():
    assert "error" in dn(2024, volunteer={"hours": 8})
    assert "error" in dn(2022, hometown=300_000)
    assert "error" not in dn(2023, hometown=300_000)
    assert "5년" in str(dn(2017, general=50 * M)["판단"]) and "5년" not in str(dn(2020, general=50 * M)["판단"])


# ── 기타소득 과세최저한(2016.7.1. 전후) ───────────────────────────────────────
def oi(year, item):
    return c("other_income_aggregate", {"year": year, "items": [item]})

def sep(year, item):
    r = oi(year, item)
    assert "error" not in r, r
    return r["결과"]["분리과세_기타소득금액"]

def test_slot_machine_threshold_2016():
    assert "error" in oi(2016, {"kind": "슬롯머신당첨금", "amount": 3 * M})
    assert sep(2016, {"kind": "슬롯머신당첨금", "amount": 3 * M, "occurred_on": "2016-06-30"}) == 0          # 500만원 미만 → 과세최저한
    assert sep(2016, {"kind": "슬롯머신당첨금", "amount": 3 * M, "occurred_on": "2016-07-01"}) == 3 * M      # 200만원 초과 → 과세
    assert sep(2016, {"kind": "슬롯머신당첨금", "amount": 5 * M, "occurred_on": "2016-06-30"}) == 5 * M      # 500만원 '미만'이 아님
    assert sep(2020, {"kind": "슬롯머신당첨금", "amount": 3 * M}) == 3 * M
    assert sep(2020, {"kind": "슬롯머신당첨금", "amount": 2 * M}) == 0

def test_horse_racing_threshold_2016():
    item = {"kind": "승마투표권환급금", "amount": 5 * M, "unit_bet": 100_000, "per_bet_refund": 5 * M, "ticket_total": 100_000}
    assert "error" in oi(2016, item)
    assert sep(2016, {**item, "occurred_on": "2016-06-30"}) == 0             # 100배 이하(50배) — 종전은 200만원 상한 없음
    assert sep(2016, {**item, "occurred_on": "2016-07-01"}) == 4_900_000     # 개별 환급금 200만원 초과 → 과세(환급금 − 단위투표금액)


# ── 증여재산공제 기타친족 범위 ────────────────────────────────────────────────
@pytest.mark.parametrize("on,scope", [("2025-03-13", "6촌 혈족·4촌 인척"), ("2025-03-14", "4촌 혈족·3촌 인척"), ("2020-05-01", "6촌 혈족·4촌 인척")])
def test_gift_relative_scope_by_gift_date(on, scope):
    r = c("gift_tax", {"gift_value": 50 * M, "relation": "기타친족", "gift_date": on})
    assert "error" not in r, r
    assert scope in str(r)


# ── 범위 밖 날짜·연도 거절 ────────────────────────────────────────────────────
@pytest.mark.parametrize("tool,args", [
    ("invoice_penalty", {"supply_amount": 10 * M, "kind": "지연발급", "supplied_on": "2015-05-01"}),
    ("invoice_penalty_bundle", {"items": [{"deal": "A", "kind": "지연발급", "supply_amount": 10 * M, "supplied_on": "2027-05-01"}]}),
    ("vat_reverse_charge", {"year": 2015, "items": []}),
    ("bundled_supply_split", {"total_price": 100 * M, "vat_included": False, "standard_value": {"building": 40 * M, "land": 60 * M}, "supply_date": "2015-03-01"}),
])
def test_out_of_range_dates_are_refused(tool, args):
    r = c(tool, args)
    assert "error" in r and ("2016" in str(r) or "지원" in str(r)), r


def test_review_findings_0318():
    """자동 리뷰 지적 확인: ① 2016.6.30. 이전 발생분도 권면 합계 10만원 초과면 과세 ② 2018 사업연도는 확정일과 관계없이 10호 시행 전."""
    item = {"kind": "승마투표권환급금", "amount": 5 * M, "unit_bet": 100_000, "per_bet_refund": 5 * M, "ticket_total": 200_000, "occurred_on": "2016-06-30"}
    assert sep(2016, item) == 4_900_000
    assert "10호 시행 전" in str(bd(2018, date="2019-03-01"))
