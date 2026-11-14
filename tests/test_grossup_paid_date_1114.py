"""Gross-up 가산율 지급일 기준 — 소득세법 제17조③, 법률 제19933호 부칙(2024.1.1. 이후 지급분 10%), 법률 제21221호 부칙(2027.1.1. 이후 지급분 11%). Claude 작성(2026-11-14)."""
from korean_tax_calc_mcp import server as S

M = 10_000_000


def fia(year, items):
    r = S.financial_income_aggregate(year, items)
    assert "error" not in r, r
    return r


def test_default_year_rate_unchanged():
    assert fia(2023, [{"kind": "상장법인현금배당", "amount": 5 * M}])["결과"]["Gross-up"] == 3_300_000      # (5천만−2천만)×11%
    assert fia(2024, [{"kind": "상장법인현금배당", "amount": 5 * M}])["결과"]["Gross-up"] == 3_000_000


def test_2023_income_paid_in_2024_uses_10pct():
    r = fia(2023, [{"kind": "상장법인현금배당", "amount": 5 * M, "paid_date": "2024-01-15"}])
    assert r["결과"]["Gross-up"] == 3_000_000 and any("지급일 2024-01-15" in n for n in r["주의"])
    r = fia(2023, [{"kind": "상장법인현금배당", "amount": 5 * M, "paid_date": "2023-12-29"}])
    assert r["결과"]["Gross-up"] == 3_300_000 and "주의" not in r


def test_2026_income_paid_in_2027_uses_11pct():
    assert fia(2026, [{"kind": "비상장법인현금배당", "amount": 5 * M, "paid_date": "2027-01-10"}])["결과"]["Gross-up"] == 3_300_000


def test_mixed_rates_split_by_amount():
    r = fia(2023, [{"kind": "상장법인현금배당", "amount": 3 * M, "paid_date": "2023-06-30"},
                   {"kind": "상장법인현금배당", "amount": 3 * M, "paid_date": "2024-01-10"}])
    # 기준액 4천만 → 2천만×11% + 2천만×10%
    assert r["결과"]["Gross-up"] == 2_200_000 + 2_000_000
    assert any("섞임" in n for n in r["주의"])


def test_hint_when_no_paid_date_in_boundary_year():
    assert "가산율_안내" in fia(2023, [{"kind": "상장법인현금배당", "amount": 5 * M}])
    assert "가산율_안내" not in fia(2025, [{"kind": "상장법인현금배당", "amount": 5 * M}])


def test_bad_paid_date():
    r = S.financial_income_aggregate(2023, [{"kind": "상장법인현금배당", "amount": 5 * M, "paid_date": "2024/01/15"}])
    assert "error" in r


def test_dividend_tax_credit_follows():
    a = S.dividend_tax_credit(2023, items=[{"kind": "상장법인현금배당", "amount": 5 * M, "paid_date": "2024-01-15"}], other_base=50 * M)
    assert a["결과"]["Gross-up"] == 3_000_000 and a["결과"]["배당세액공제액"] == 3_000_000
