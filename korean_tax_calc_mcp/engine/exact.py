"""원 단위 정확 계산 — 금액 × 비율의 원 미만 처리를 부동소수 없이.

int(190_000_000 * 0.7)은 132,999,999가 된다(0.7을 2진 부동소수로 담으면 0.6999…라 곱이 132,999,999.999…).
여기 함수는 비율을 뜻한 분수(0.7 → 7/10)로 바꿔 분수끼리 곱한 뒤 원 미만을 처리한다.
비율이 나눗셈 결과(면세공급가액/총공급가액 등)이면 되도록 분자·분모를 그대로 넘겨(div=) 나눗셈까지 정확히 한다.
"""

from __future__ import annotations

import math
from decimal import Decimal
from fractions import Fraction

# float를 분수로 읽을 때: 분모 10^7 이하 분수 중 가장 가까운 것이 부동소수 오차(상대 10^-15) 안에 있으면 그 분수
# (0.7 → 7/10, 0.00022 → 11/50000, 1/3로 나눈 값 → 1/3), 아니면 float가 담은 2진 값 그대로.
# 큰 수끼리 나눈 일반 비율을 엉뚱한 간단한 분수로 바꾸지 않기 위한 조건이다.
_MAX_DEN = 10 ** 7
_REL_TOL = Fraction(1, 10 ** 15)


def exact(x) -> Fraction:
    """수를 분수로. float는 뜻한 간단한 분수로 읽는다(0.7 → 7/10, 0.00022 → 11/50000, 1/3로 나눈 값 → 1/3)."""
    if isinstance(x, Fraction):
        return x
    if isinstance(x, bool):
        return Fraction(int(x))
    if isinstance(x, int):
        return Fraction(x)
    if isinstance(x, float):
        if not math.isfinite(x):
            raise ValueError(f"유한한 수가 아님: {x}")
        b = Fraction(x)
        f = b.limit_denominator(_MAX_DEN)
        return f if abs(f - b) <= abs(b) * _REL_TOL else b
    if isinstance(x, Decimal):
        return Fraction(x)
    if x is None:
        raise ValueError("값이 없음(None) — 숫자가 필요")
    return Fraction(str(x))


def product(*factors, div=1) -> Fraction:
    p = Fraction(1)
    for f in factors:
        p *= exact(f)
    return p / exact(div)


def floor_won(*factors, div=1) -> int:
    """곱(÷div)의 원 미만 버림(⌊x⌋). 법령이 '원 미만 버림'이거나 별도 규정이 없어 절사하던 자리."""
    return math.floor(product(*factors, div=div))


def trunc_won(*factors, div=1) -> int:
    """곱(÷div)의 0 쪽 절사 — 음수도 int()와 같은 방향(−1.5 → −1)."""
    return math.trunc(product(*factors, div=div))


def round_won(*factors, div=1) -> int:
    """곱(÷div)의 원 미만 반올림(0.5는 올림, 음수는 절댓값 기준)."""
    p = product(*factors, div=div)
    n = math.floor(abs(p) + Fraction(1, 2))
    return n if p >= 0 else -n
