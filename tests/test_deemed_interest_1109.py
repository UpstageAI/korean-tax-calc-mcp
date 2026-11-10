"""인정이자 보강 정답 — 원 미만 절사, 동일인 가수금 연간 적수 상계, 가중평균차입이자율(대여 건별·선입선출·5년 초과·당좌선택)."""
import json

from tests._helpers import call


def R(d):
    return d.get("결과", d)


MV = [{"date": "2025-12-31", "amount": 300_000_000}, {"date": "2026-04-10", "amount": 100_000_000},
      {"date": "2026-09-30", "amount": -200_000_000}]
BASE = {"movements": MV, "year_end": "2026-12-31", "fiscal_start": "2026-01-01"}
DEP = [{"date": "2026-07-01", "amount": 50_000_000}, {"date": "2026-12-15", "amount": -50_000_000}]
BORROW = [
    {"borrowed_on": "2025-01-01", "amount": 1_000_000_000, "rate": 0.05},
    {"borrowed_on": "2026-03-01", "amount": 400_000_000, "rate": 0.03},
    {"borrowed_on": "2025-06-01", "amount": 500_000_000, "rate": 0.08, "related": True},
    {"borrowed_on": "2025-06-01", "amount": 100_000_000, "rate": 0.12, "unclear_creditor": True},
]


def test_truncation_both_paths():
    a = R(call("deemed_interest", {**BASE, "market_rate": 64 / 1400}))
    b = R(call("deemed_interest", {**BASE, "market_rate": 64 / 1400, "received_interest": 0}))
    assert a["시가이자"] == b["시가이자"] == 14_716_242
    assert a["익금산입"] == 14_716_242


def test_legacy_integer_case_unchanged():
    r = R(call("deemed_interest", {"movements": [{"date": "2025-01-01", "amount": 240_000_000}], "year_end": "2025-12-31"}))
    assert r["익금산입"] == 11_040_000


def test_deposits_offset_annual():
    r = R(call("deemed_interest", {**BASE, "market_rate": 64 / 1400, "deposits": DEP}))
    assert r["가지급금적수"] == 117_500_000_000
    assert r["가수금적수"] == 8_350_000_000
    assert r["적수"] == 109_150_000_000
    assert r["시가이자"] == 13_670_450


def test_deposits_exceed_no_interest():
    d = call("deemed_interest", {"movements": [{"date": "2026-01-01", "amount": 10_000_000}],
                                 "deposits": [{"date": "2026-01-01", "amount": 20_000_000}],
                                 "year_end": "2026-12-31", "fiscal_start": "2026-01-01"})
    assert R(d)["적수"] == 0 and R(d)["시가이자"] == 0 and R(d)["익금산입"] == 0
    assert "가수금" in json.dumps(d, ensure_ascii=False)


def test_deposits_blocked_not_offset():
    dep = [dict(x, offset_blocked=True) for x in DEP]
    d = call("deemed_interest", {**BASE, "market_rate": 64 / 1400, "deposits": dep})
    assert R(d)["적수"] == 117_500_000_000 and R(d)["시가이자"] == 14_716_242
    assert "상계" in json.dumps(d, ensure_ascii=False)


def test_weighted_average_per_tranche_fifo():
    d = call("deemed_interest", {**BASE, "rate_mode": "가중평균", "borrowings": BORROW})
    r = R(d)
    assert r["적수"] == 117_500_000_000
    assert r["시가이자"] == 15_679_452
    rows = (d.get("계산") or {}).get("대여건별") or r.get("대여건별")
    assert len(rows) == 2
    assert rows[0]["적수"] == 90_900_000_000 and abs(rows[0]["이자율"] - 0.05) < 1e-12
    assert rows[1]["적수"] == 26_600_000_000 and abs(rows[1]["이자율"] - 62 / 1400) < 1e-12


def test_weighted_average_with_deposits():
    r = R(call("deemed_interest", {**BASE, "rate_mode": "가중평균", "borrowings": BORROW, "deposits": DEP}))
    assert r["적수"] == 109_150_000_000 and r["시가이자"] == 14_565_210


def test_over_five_years_overdraft():
    d = call("deemed_interest", {"movements": [{"date": "2020-03-01", "amount": 100_000_000}], "year_end": "2026-12-31",
                                 "fiscal_start": "2026-01-01", "rate_mode": "가중평균",
                                 "borrowings": [{"borrowed_on": "2019-01-01", "amount": 1_000_000_000, "rate": 0.05}]})
    assert R(d)["시가이자"] == 4_600_000
    assert "5년" in json.dumps(d, ensure_ascii=False)


def test_no_eligible_borrowing_overdraft():
    d = call("deemed_interest", {**BASE, "rate_mode": "가중평균",
                                 "borrowings": [{"borrowed_on": "2025-01-01", "amount": 1_000_000_000, "rate": 0.05, "related": True}]})
    assert R(d)["시가이자"] == 14_808_219


def test_overdraft_election():
    d = call("deemed_interest", {**BASE, "rate_mode": "당좌선택"})
    assert R(d)["시가이자"] == 14_808_219
    assert "2개 사업연도" in json.dumps(d, ensure_ascii=False)


def test_nonbusiness_pointer_includes_deposits():
    d = call("nonbusiness_interest_disallowance", {
        "loans": [{"interest": 50_000_000, "principal": 1_000_000_000, "days": 365}],
        "advances": [{"대상": "대표이사", "이름": "김대표", "사유": "업무무관대여", "movements": [
            {"일자": "2025-12-31", "증감": 300_000_000}, {"일자": "2026-09-30", "증감": -200_000_000}]}],
        "deposits": [{"이름": "김대표", "금액": 50_000_000, "일자": "2026-07-01", "반환일": "2026-12-15"}],
        "year": 2026})
    ptr = d["인정이자_연결"]
    assert "김대표" in json.dumps(ptr.get("deposits_사람별", ptr), ensure_ascii=False)
    assert "deposits" in json.dumps(ptr, ensure_ascii=False)


# ── 검수 추가 ──
def test_weighted_recovery_before_fiscal_start_reduces_tranche():
    """개시일 전 회수도 선입선출로 대여 건 잔액을 줄인다 — 2024 대여 1억, 2025 회수 6천만 → 2026 잔액 4천만."""
    mv = [{"date": "2024-01-02", "amount": 100_000_000}, {"date": "2025-06-01", "amount": -60_000_000}]
    d = call("deemed_interest", {"movements": mv, "year_end": "2026-12-31", "fiscal_start": "2026-01-01",
                                 "rate_mode": "가중평균", "borrowings": [{"borrowed_on": "2023-01-01", "amount": 1_000_000_000, "rate": 0.05}]})
    assert R(d)["적수"] == 40_000_000 * 365
    assert R(d)["시가이자"] == 2_000_000


def test_weighted_fifo_unsorted_input():
    mv = [{"date": "2026-04-10", "amount": 100_000_000}, {"date": "2026-09-30", "amount": -200_000_000},
          {"date": "2025-12-31", "amount": 300_000_000}]
    r = R(call("deemed_interest", {"movements": mv, "year_end": "2026-12-31", "fiscal_start": "2026-01-01",
                                   "rate_mode": "가중평균", "borrowings": BORROW}))
    assert r["시가이자"] == 15_679_452


def test_five_years_civil_boundary():
    """대여일 2021-12-31 → 2026-12-31은 정확히 5년(초과 아님) → 가중평균, 2021-12-30이면 5년 초과 → 당좌."""
    b = [{"borrowed_on": "2019-01-01", "amount": 1_000_000_000, "rate": 0.05}]
    a = R(call("deemed_interest", {"movements": [{"date": "2021-12-31", "amount": 100_000_000}], "year_end": "2026-12-31",
                                   "fiscal_start": "2026-01-01", "rate_mode": "가중평균", "borrowings": b}))
    c = R(call("deemed_interest", {"movements": [{"date": "2021-12-30", "amount": 100_000_000}], "year_end": "2026-12-31",
                                   "fiscal_start": "2026-01-01", "rate_mode": "가중평균", "borrowings": b}))
    assert a["시가이자"] == 5_000_000 and c["시가이자"] == 4_600_000


def test_rate_mode_invalid_rejected():
    d = None
    try:
        d = call("deemed_interest", {**BASE, "rate_mode": "가중 평균"})
    except Exception:
        return
    assert "error" in d
