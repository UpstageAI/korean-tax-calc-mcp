"""끝수 규칙 한 곳(engine/rounding.py) — 경계 정답 테스트(2026-11-15, Claude 작성). 외부 호출 없음. 손 계산 값.

대조한 원문(법제처·국세법령정보시스템, 2026-11-15 조회):
  국고금 관리법 제47조 2011.10.5.·2026.1.2. 시행본(제1항 수입·지출 10원 미만 끝수, 제2항 과세표준 1원 미만), 시행령 제109조의2제1항(2026.1.2.)
  지방세기본법 제75조(2016.11.30. 시행본)·제59조(2017.3.28. 전부개정 법률 제14474호, 현행) — 국고금 관리법 제47조 준용
  소득세법 제86조 2016.9.1.·2026.7.1. 시행본(소액 부징수 1천원 미만)
  원천세과-240(2012.5.2. 등록), 법인22601-2481(1989.7.6. 등록) — 소득자별·지급분 합계를 납부하는 때에 10원 미만을 버림
"""
import pytest

from korean_tax_calc_mcp import server as S
from korean_tax_calc_mcp.engine import calc_branch_exit as BX
from korean_tax_calc_mcp.engine import rounding as R

M = 1_000_000
PAY = "납부할 금액(10원 미만 버림)"


def _fn(t):
    return getattr(t, "fn", t)


def test_pay_amount_boundaries():
    # 제47조제1항: 10원 미만 끝수는 계산하지 않고, 전액이 10원 미만이면 전액을 계산하지 않음
    assert [R.pay_amount(x) for x in (0, 9, 10, 19, 1_234_567)] == [0, 0, 10, 10, 1_234_560]
    # 지출(환급)도 같은 규칙 — 절댓값에서 버림
    assert [R.pay_amount(x) for x in (-9, -10, -19)] == [0, -10, -10]
    assert BX.pay_amount is R.pay_amount and BX.ROUNDING_BASIS == R.ROUNDING_BASIS


def test_withholding_single_payment_is_10won_unit():
    # 사업소득 1,234,567 × 3% = 37,037.01 → 한 번 지급분을 납부하는 금액 37,030
    r = S.withholding_tax("사업", 1_234_567, 2025)
    assert r["결과"]["원천징수세액"] == 37_030
    assert "국고금 관리법 제47조제1항" in r["끝수"] and "원천세과-240" in r["끝수"]


def test_nonresident_withholding_note_cites_basis():
    r = S.nonresident_withholding("사용료", 123_456_789, "법인", "US", 0.15)
    # 123,456,789 × 15% = 18,518,518.35 → 18,518,510 / 지방소득세 1,851,851 → 1,851,850
    assert r["결과"]["원천징수세액"] == 18_518_510 and r["결과"]["지방소득세"] == 1_851_850
    note = " ".join(r["한계"])
    assert "국고금 관리법 제47조제1항" in note and "확인하지 못함" not in note


def test_nonresident_capital_gains_withholding_keeps_won_and_adds_pay_amount():
    # 333,333,337 × 10% = 33,333,333.7 → 계산값 33,333,333(원 미만 버림), 납부할 금액 33,333,330. 지방소득세 3,333,333 → 3,333,330
    r = S.nonresident_capital_gains_withholding("법인", "주식", 2026, 333_333_337)
    assert r["결과"]["원천징수세액"] == 33_333_333 and r["결과"]["지방소득세"] == 3_333_333
    assert r["결과"][PAY] == {"원천징수세액": 33_333_330, "지방소득세": 3_333_330}
    assert "지방세기본법 제59조" in r["끝수"]


@pytest.mark.parametrize("wage, tax, pay", [
    (190_000, 1_080, 1_080),   # (190,000 − 150,000) × 6% × 45% = 1,080
    (190_300, 1_088, 1_080),   # 40,300 × 2.7% = 1,088.1 → 1,088 → 납부 1,080
    (190_370, 1_089, 1_080),   # 40,370 × 2.7% = 1,089.99 → 1,089 → 납부 1,080
    (190_371, 1_090, 1_090),   # 40,371 × 2.7% = 1,090.017 → 1,090
])
def test_daily_worker_pay_amount(wage, tax, pay):
    r = S.daily_worker_withholding(wage, 2025)
    assert r["결과"]["원천징수세액"] == tax and r["결과"][PAY] == pay
    assert "원천세과-240" in r["끝수"]


def test_rural_special_tax_pay_amount():
    # 통합투자세액공제 1,234,567 × 20% = 246,913.4 → 246,913 → 납부 246,910
    f = _fn(S.rural_special_tax)
    r = f(year=2024, items=[{"article": "제24조", "amount": 1_234_567}])
    assert r["결과"]["농어촌특별세"] == 246_913 and r["결과"][PAY] == 246_910


def test_loss_carryback_refund_amount():
    # 2022 과세표준 5억 → 2,000만 + 3억 × 20% = 8,000만. 결손 100,000,005 소급 → 399,999,995 → 2,000만 + 199,999,995 × 20% = 59,999,999
    # 환급세액 = 80,000,000 − 59,999,999 = 20,000,001 → 돌려받을 금액 20,000,000(지출도 10원 미만 버림)
    f = _fn(S.loss_carryback_refund)
    r = f(year=2023, loss=100_000_005, prior_base=500 * M)
    assert r["결과"]["환급세액"] == 20_000_001 and r["결과"]["환급받을 금액(10원 미만 버림)"] == 20_000_000
    assert PAY not in r["결과"]


def test_gift_tax_pay_amount():
    # 성년 자녀, 직계존속 증여 150,000,055: 과세표준 100,000,055 → 1,000만 + 55 × 20% = 10,000,011 → 신고세액공제 3% 300,000(300,000.33) → 9,700,011
    f = _fn(S.gift_tax)
    r = f(gift_date="2025-03-01", gift_value=150_000_055, relation="직계존속")
    assert r["결과"]["산출세액"] == 10_000_011 and r["결과"]["납부할세액"] == 9_700_011
    assert r["결과"][PAY] == 9_700_010


def test_registered_keys_exist_and_values_unchanged():
    # 등록된 도구는 계산값을 바꾸지 않고 키만 더함 — 등록되지 않은 도구(산출세액·가산세 등 계산값)는 그대로
    r = S.income_tax(123_456_789, 2025)
    assert PAY not in r["결과"] and "끝수" not in r
    for tool in R.PAYABLE_KEYS:
        assert hasattr(S, tool), tool
