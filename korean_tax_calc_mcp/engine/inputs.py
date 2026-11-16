"""입력 범위 점검 — 도구 설명에 적힌 범위 밖 값은 계산하지 않는다.

ValueError를 던지면 서버 _guard가 {"error": "입력 오류: …"}로 돌려준다(조용히 계산하지 않음).
"""
from __future__ import annotations

import re
from datetime import date

YEAR_MIN, YEAR_MAX = 2016, 2026


def need(ok, msg: str) -> None:
    if not ok:
        raise ValueError(msg)


def int_range(name: str, v, lo: int, hi: int, what: str = "") -> None:
    """정수 v가 lo~hi 안인지. what은 값의 뜻(예: '사업연도 월수 ')."""
    need(isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi, f"{name}={v!r} — {what}{lo}~{hi}만 받음")


_ISO_HEAD = re.compile(r"\d{4}-\d{2}-\d{2}")


def to_date(name: str, s) -> date:
    """YYYY-MM-DD(뒤에 시각이 붙어도 앞 10자) → date. YYYYMMDD 등 다른 꼴은 도구 입구(normalize_dates)에서 바꿔 들어온다.
    date.fromisoformat은 파이썬 3.11부터 '20250101'도 받으므로, 판마다 결과가 달라지지 않게 꼴을 먼저 본다."""
    head = str(s)[:10]
    try:
        if not _ISO_HEAD.fullmatch(head):
            raise ValueError
        return date.fromisoformat(head)
    except (TypeError, ValueError):
        raise ValueError(f"{name}={s!r} — YYYY-MM-DD 형식의 실제 날짜가 필요(예: 2025-03-31)") from None


# ── 날짜 문자열 정규화(도구 입구) ──
# 엔진은 날짜 문자열을 그대로 비교하거나(s >= "2021-07-01") 잘라 쓴다(s[5:7]). 그래서 YYYYMMDD·YYYY.MM.DD 같은 꼴이 들어오면
# 검증은 지나가도 값이 조용히 틀린다. 서버 _guard가 모든 도구 인자를 계산 전에 이 함수로 YYYY-MM-DD로 바꾼다.
# 날짜 자리는 이름으로 알아본다 — 인자·키 이름이 날짜를 뜻하는 것(…date·…_on·…_start·…_end·due·until·day, …일·…시기·…기한·…일자·날짜)이고
# 값이 아래 꼴과 정확히 맞을 때만 바꾼다. 연도-기수('2025-1')·연월('2025-06')·코드·금액은 꼴이 맞지 않아 그대로 둔다.
DATE_KEY = re.compile(r"(date|_on$|^on$|_start$|_end$|(^|_)due($|_)|until|^day$|일$|시기$|기한$|일자$|날짜$)", re.IGNORECASE)
_DATE_FORMS = (
    re.compile(r"(\d{4})(\d{2})(\d{2})"),                                        # 20250131
    re.compile(r"(\d{4})\s*([./-])\s*(\d{1,2})\s*\2\s*(\d{1,2})\s*\.?"),           # 2025-1-31 · 2025.01.31 · 2025. 1. 31. · 2025/01/31
    re.compile(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일"),                  # 2025년 1월 31일
)


def normalize_date_str(name: str, s: str) -> str:
    """날짜 자리의 문자열 하나를 YYYY-MM-DD로. 꼴이 맞지 않으면 그대로 돌려준다(엔진의 기존 검증이 처리).
    꼴은 맞는데 실제 날짜가 아니면(20250230) 고칠 방법을 말하는 ValueError."""
    if _ISO_HEAD.fullmatch(s):
        return s                      # 이미 YYYY-MM-DD — 실제 날짜인지는 엔진의 기존 검증이 본다(오류 문구를 바꾸지 않음)
    t = s.strip()
    for i, rx in enumerate(_DATE_FORMS):
        m = rx.fullmatch(t)
        if not m:
            continue
        g = m.groups()
        y, mo, d = (g[0], g[2], g[3]) if i == 1 else g
        try:
            return date(int(y), int(mo), int(d)).isoformat()
        except ValueError:
            raise ValueError(f"{name}={s!r} — 실제 날짜가 아님. YYYY-MM-DD 형식의 실제 날짜로 넣으세요(예: 2025-03-31)") from None
    return s


def normalize_dates(value, name: str = "", in_date: bool = False):
    """인자 값 하나를 훑어 날짜 자리의 문자열을 YYYY-MM-DD로 바꾼 사본을 돌려준다(바뀐 것이 없으면 원래 객체).
    dict는 키 이름, 목록은 바깥 이름을 이어받는다. Pydantic 모델은 필드 이름으로 본다."""
    if isinstance(value, str):
        return normalize_date_str(name, value) if in_date else value
    if isinstance(value, dict):
        out, changed = {}, False
        for k, v in value.items():
            nv = normalize_dates(v, f"{name}.{k}" if name else str(k), bool(DATE_KEY.search(str(k))))
            changed |= nv is not v
            out[k] = nv
        return out if changed else value
    if isinstance(value, (list, tuple)):
        items = [normalize_dates(v, f"{name}[{i}]", in_date) for i, v in enumerate(value)]
        if all(a is b for a, b in zip(items, value)):
            return value
        return type(value)(items) if isinstance(value, tuple) else items
    fields = getattr(type(value), "model_fields", None)
    if fields is not None and hasattr(value, "model_copy"):
        upd = {}
        for f in fields:
            v = getattr(value, f, None)
            nv = normalize_dates(v, f"{name}.{f}" if name else f, bool(DATE_KEY.search(f)))
            if nv is not v:
                upd[f] = nv
        return value.model_copy(update=upd) if upd else value
    return value


def normalize_date_args(args: dict) -> dict:
    """도구 인자 {이름: 값} 전체를 정규화한 새 dict."""
    return {k: normalize_dates(v, k, bool(DATE_KEY.search(k))) for k, v in args.items()}


def supported_year(name: str, value) -> None:
    """연도(int) 또는 날짜(YYYY-MM-DD)가 연도표 범위(2016~2026) 안인지."""
    y = value if isinstance(value, int) and not isinstance(value, bool) else to_date(name, value).year
    need(YEAR_MIN <= y <= YEAR_MAX, f"{name}={value} — {YEAR_MIN}~{YEAR_MAX}만 지원(연도표 없는 해는 계산하지 않음)")
