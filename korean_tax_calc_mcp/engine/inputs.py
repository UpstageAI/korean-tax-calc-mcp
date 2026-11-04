"""입력 범위 점검 — 도구 설명에 적힌 범위 밖 값은 계산하지 않는다.

ValueError를 던지면 서버 _guard가 {"error": "입력 오류: …"}로 돌려준다(조용히 계산하지 않음).
"""
from __future__ import annotations

from datetime import date

YEAR_MIN, YEAR_MAX = 2016, 2026


def need(ok, msg: str) -> None:
    if not ok:
        raise ValueError(msg)


def int_range(name: str, v, lo: int, hi: int, what: str = "") -> None:
    """정수 v가 lo~hi 안인지. what은 값의 뜻(예: '사업연도 월수 ')."""
    need(isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi, f"{name}={v!r} — {what}{lo}~{hi}만 받음")


def nonneg(name: str, v) -> None:
    need(v is None or v >= 0, f"{name}={v!r} — 음수는 받지 않음")


def to_date(name: str, s) -> date:
    try:
        return date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        raise ValueError(f"{name}={s!r} — YYYY-MM-DD 형식의 실제 날짜가 필요") from None


def supported_year(name: str, value) -> None:
    """연도(int) 또는 날짜(YYYY-MM-DD)가 연도표 범위(2016~2026) 안인지."""
    y = value if isinstance(value, int) and not isinstance(value, bool) else to_date(name, value).year
    need(YEAR_MIN <= y <= YEAR_MAX, f"{name}={value} — {YEAR_MIN}~{YEAR_MAX}만 지원(연도표 없는 해는 계산하지 않음)")
