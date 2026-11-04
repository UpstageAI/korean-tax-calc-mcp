"""기한·기간 계산 — 국세기본법 제4조(기간 계산, 민법 준용)·제5조제1항(기한의 특례)·제45조의2(경정 등의 청구).

공휴일은 data/kr_holidays.json(2016~2027)에서 꺼낸다. 표 밖의 해는 토·일과 날짜가 고정된 공휴일만 보고,
설·추석·부처님 오신 날·대체공휴일·선거일·임시공휴일은 확인하지 못했다고 결과에 밝힌다.
"""
import calendar
import json
import os
from datetime import date, timedelta

_WD = "월화수목금토일"
_HOL: dict | None = None


def _table() -> dict:
    global _HOL
    if _HOL is None:
        p = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "kr_holidays.json")
        with open(p, encoding="utf-8") as f:
            raw = json.load(f)
        days = {}
        for rows in raw["공휴일"].values():
            for e in rows:
                days[date.fromisoformat(e["날짜"])] = (e["이름"], e["구분"])
        _HOL = {"범위": tuple(raw["범위"]), "days": days}
    return _HOL


def table_range() -> tuple[int, int]:
    return _table()["범위"]


def in_table(d: date) -> bool:
    lo, hi = table_range()
    return lo <= d.year <= hi


def fmt(d: date) -> str:
    return f"{d.isoformat()}({_WD[d.weekday()]})"


def labor_day_name(d: date) -> str:
    # 국세기본법 제5조제1항제3호: 2025.11.11. 개정 전 「근로자의 날 제정에 관한 법률」의 근로자의 날, 이후 「노동절 제정에 관한 법률」의 노동절
    return "노동절" if d >= date(2025, 11, 11) else "근로자의 날"


def _fixed_holidays(y: int) -> dict:
    """표 밖의 해 — 「공휴일에 관한 법률」의 날짜 고정 공휴일만(음력·대체·선거·임시 제외)."""
    fx = {(1, 1): "1월 1일", (3, 1): "3·1절", (5, 5): "어린이날", (6, 6): "현충일", (8, 15): "광복절",
          (10, 3): "개천절", (10, 9): "한글날", (12, 25): "기독탄신일"}
    if y >= 2026:
        fx[(5, 1)] = "노동절"
        fx[(7, 17)] = "제헌절"
    return fx


def nonbusiness(d: date, labor_day: bool = True) -> str | None:
    """d가 기한 특례 대상 날이면 그 사유, 아니면 None.
    labor_day=True: 국세기본법 제5조제1항(토·일, 공휴일·대체공휴일, 근로자의 날·노동절).
    labor_day=False: 민법 제161조(토요일·공휴일 — 근로자의 날은 공휴일이 아님, 2026.5.1.부터 노동절은 공휴일)."""
    if d.weekday() == 5:
        return "토요일"
    if d.weekday() == 6:
        return "일요일"
    if in_table(d):
        h = _table()["days"].get(d)
        if h:
            return f"{h[0]}({h[1]})"
    else:
        n = _fixed_holidays(d.year).get((d.month, d.day))
        if n:
            return f"{n}(공휴일)"
    if labor_day and (d.month, d.day) == (5, 1):
        return labor_day_name(d)
    return None


def roll(d: date, labor_day: bool = True) -> dict:
    """기한 특례 — 기한이 특례 대상 날이면 그 다음 날(반복). 결과: 적용일·건너뛴 날·표 밖 여부."""
    skipped, cur, outside = [], d, []
    while True:
        if not in_table(cur):
            outside.append(cur.year)
        why = nonbusiness(cur, labor_day)
        if not why:
            break
        skipped.append({"날짜": fmt(cur), "사유": why})
        cur += timedelta(days=1)
    return {"날짜": cur, "건너뜀": skipped, "표_밖_연도": sorted(set(outside))}


def add_months(d: date, months: int) -> date:
    """민법 제160조 — 초일 불산입(제157조)으로 d 다음 날부터 기산한 n개월의 말일 = d의 n개월 뒤 같은 날(없으면 그 달 말일)."""
    m = d.month - 1 + months
    y, m = d.year + m // 12, m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def month_end_plus(d: date, months: int) -> date:
    """'d가 속하는 달의 말일부터 n개월 이내' — 그 기간의 마지막 날(n개월 뒤 달의 말일)."""
    m = d.month - 1 + months
    y, m = d.year + m // 12, m % 12 + 1
    return date(y, m, calendar.monthrange(y, m)[1])


def outside_note(years: list[int]) -> str:
    lo, hi = table_range()
    return (f"{', '.join(map(str, years))}년은 내장 공휴일표({lo}~{hi}) 밖 — 토·일과 날짜가 고정된 공휴일만 반영했고 "
            "설·추석·부처님 오신 날·대체공휴일·선거일·임시공휴일은 확인하지 못함. 그해 공휴일을 확인해 다시 보세요")
