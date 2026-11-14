"""법인세 도구의 기준일 판정 — 사업연도 개시일·종료일·신고일로 개정 부칙의 적용례(지출분·신고분·확정분·개시 사업연도분)를 고른다.

법인세 도구의 year는 '사업연도 개시일이 속하는 해'다. 부칙이 "개시하는 사업연도분"이면 year로 충분하지만,
"지출하는 분"·"과세표준을 신고하는 분"·"확정되는 분"이면 사업연도가 역년과 다른 법인에서 어긋난다.
fy_start·fy_end·filing_date를 받으면 이 모듈로 날짜를 정하고, 받지 않으면 종전처럼 역년(year-01-01~year-12-31)으로 본다.
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta

from .inputs import need, to_date


def month_end_plus(d: date, months: int) -> date:
    """d가 속하는 달의 말일부터 months개월이 되는 날(그 달의 말일)."""
    y, m = d.year, d.month + months
    while m > 12:
        y, m = y + 1, m - 12
    return date(y, m, calendar.monthrange(y, m)[1])


def corp_filing_due(fy_end: date) -> date:
    """법인세 과세표준 신고기한 — 사업연도 종료일이 속하는 달의 말일부터 3개월(법인세법 제60조제1항).
    외부감사 미종결 연장(제60조제7항)·성실신고확인서 제출 법인 1개월 연장(제60조의2)은 반영하지 않는다(filing_date로 직접 넣음)."""
    return month_end_plus(fy_end, 3)


def fiscal_year(year: int, fy_start: str | None, fy_end: str | None) -> tuple[date, date, bool]:
    """(개시일, 종료일, 날짜를 받았는지). 둘 다 없으면 역년. 하나만 있으면 1년 사업연도로 나머지를 채움.
    개시일은 year 안에 있어야 하고(year = 개시일이 속하는 해), 사업연도는 1년을 넘지 못한다(법인세법 제6조제1항)."""
    if fy_start is None and fy_end is None:
        return date(year, 1, 1), date(year, 12, 31), False
    if fy_start is not None:
        s = to_date("fy_start", fy_start)
    if fy_end is not None:
        e = to_date("fy_end", fy_end)
    if fy_start is None:
        try:
            s = e.replace(year=e.year - 1) + timedelta(days=1)
        except ValueError:                                     # 2월 29일
            s = e.replace(year=e.year - 1, day=28) + timedelta(days=1)
    if fy_end is None:
        try:
            e = s.replace(year=s.year + 1) - timedelta(days=1)
        except ValueError:
            e = s.replace(year=s.year + 1, day=28)
    need(s <= e, f"fy_start={s.isoformat()}가 fy_end={e.isoformat()}보다 뒤")
    try:
        one_year = s.replace(year=s.year + 1)
    except ValueError:
        one_year = s.replace(year=s.year + 1, day=28) + timedelta(days=1)
    need(e < one_year, f"사업연도 {s.isoformat()}~{e.isoformat()} — 1년을 넘을 수 없음(법인세법 제6조제1항)")
    need(s.year == year, f"fy_start={s.isoformat()} — year={year}는 사업연도 개시일이 속하는 해여야 함")
    return s, e, True


def filing_day(fy_end: date, filing_date: str | None) -> tuple[date, bool]:
    """(신고일, 추정 여부). filing_date가 없으면 신고기한(종료일이 속하는 달의 말일부터 3개월)에 신고했다고 본다."""
    if filing_date:
        f = to_date("filing_date", filing_date)
        need(f > fy_end, f"filing_date={f.isoformat()} — 사업연도 종료일({fy_end.isoformat()}) 뒤여야 함")
        return f, False
    return corp_filing_due(fy_end), True


def spans(fs: date, fe: date, boundary: date) -> bool:
    """사업연도가 boundary 전날과 boundary를 함께 품는지(개시 < boundary ≤ 종료)."""
    return fs < boundary <= fe


def days_overlap(fs: date, fe: date, a: date, b: date) -> int:
    """사업연도 [fs, fe]와 [a, b]가 겹치는 일수(양 끝 포함)."""
    lo, hi = max(fs, a), min(fe, b)
    return max(0, (hi - lo).days + 1)


def ymd(d: date) -> int:
    """date → YYYYMMDD 정수(vocab.rule_on 키)."""
    return d.year * 10_000 + d.month * 100 + d.day
