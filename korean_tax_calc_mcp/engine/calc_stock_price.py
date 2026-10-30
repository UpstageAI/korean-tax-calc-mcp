"""상장주식 시세 조회 — 직전 사업연도 종료일 최종시세가액(소득세법 시행령 제157조④1호)과 상증법 시가(평가기준일 전후 2개월 종가 평균, 법 제63조①1호가목).
시세는 pykrx(KRX 정보데이터시스템, 키 없음)로 가져온다. 선택 설치: pip install 'korean-tax-calc-mcp[stock]'. 외부로 나가는 건 종목코드·날짜뿐.
작성 Claude 2026-10-30."""
from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from typing import Any, Callable

Fetcher = Callable[[str, str, str], list[tuple[str, int]]]   # (ticker, start YYYYMMDD, end YYYYMMDD) -> [(YYYY-MM-DD, close)]


def _d(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _add_months(d: date, n: int) -> date:
    y, m = d.year, d.month + n
    while m > 12:
        y, m = y + 1, m - 12
    while m < 1:
        y, m = y - 1, m + 12
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def pykrx_fetcher(ticker: str, start: str, end: str) -> list[tuple[str, int]]:
    try:
        from pykrx import stock   # 선택 의존성
    except ImportError as e:
        raise RuntimeError("pykrx가 설치돼 있지 않음 — pip install 'korean-tax-calc-mcp[stock]' (또는 pip install pykrx) 뒤 다시, 아니면 종가를 직접 넣으세요") from e
    df = stock.get_market_ohlcv(start, end, ticker)   # 종가는 KRX 로그인 없이 조회됨 — pykrx가 'KRX 로그인 실패(KRX_ID·KRX_PW 미설정)' 경고를 찍어도 무시
    out = []
    for idx, row in df.iterrows():
        out.append((idx.strftime("%Y-%m-%d"), int(row["종가"])))
    return out


def pykrx_name(ticker: str) -> str | None:
    try:
        from pykrx import stock
        return stock.get_market_ticker_name(ticker)
    except Exception:
        return None


def last_close_on_or_before(ticker: str, day: str, fetch: Fetcher) -> dict[str, Any]:
    """그날 최종시세가액, 없으면(휴장) 직전 거래일 — 영 제157조④1호 단서."""
    d = _d(day)
    rows = fetch(ticker, (d - timedelta(days=31)).strftime("%Y%m%d"), d.strftime("%Y%m%d"))   # 긴 연휴·거래정지를 넘길 수 있게 31일 창
    rows = [r for r in rows if r[0] <= day]
    if not rows:
        return {"error": f"{day} 전후 거래 자료 없음 — 종목코드·날짜 확인(상장 전이거나 거래정지일 수 있음)"}
    dt, close = rows[-1]
    return {"기준일": day, "거래일": dt, "종가": close, "직전거래일_사용": dt != day}


def two_month_average(ticker: str, base_day: str, fetch: Fetcher) -> dict[str, Any]:
    """평가기준일 이전·이후 각 2개월 동안 공표된 매일의 최종시세가액 평균(상증법 제63조①1호가목) — 소수점은 원 단위 올림 없이 반올림하지 않고 그대로."""
    d = _d(base_day)
    start, end = _add_months(d, -2), _add_months(d, 2)
    rows = fetch(ticker, start.strftime("%Y%m%d"), end.strftime("%Y%m%d"))
    rows = [r for r in rows if start.isoformat() <= r[0] <= end.isoformat()]
    if not rows:
        return {"error": f"{start}~{end} 거래 자료 없음"}
    closes = [c for _, c in rows]
    avg = sum(closes) / len(closes)
    return {"평가기준일": base_day, "기간": f"{start.isoformat()} ~ {end.isoformat()}", "거래일수": len(rows), "종가합계": sum(closes), "평균": avg,
            "첫거래일": rows[0][0], "끝거래일": rows[-1][0]}


def stock_price(ticker: str, day: str, mode: str = "close", fetch: Fetcher | None = None, name_lookup=None) -> dict[str, Any]:
    fetch = fetch or pykrx_fetcher
    ticker = (ticker or "").strip().upper()
    if not (ticker.isdigit() and len(ticker) == 6):
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": [f"ticker='{ticker}' — 6자리 종목코드(예: 005930)만 받음. 종목명만 알면 KRX·포털에서 코드를 확인해 넣으세요"]}
    try:
        _d(day)
    except ValueError:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": [f"day='{day}' — YYYY-MM-DD"]}
    name = (name_lookup or pykrx_name)(ticker) if fetch is pykrx_fetcher or name_lookup else None
    try:
        if mode == "close":
            r = last_close_on_or_before(ticker, day, fetch)
            if "error" in r:
                return r
            res = {"종목": ticker, "종목명": name, **r}
            판단 = [{"항목": "용도", "결론": f"{day} 최종시세가액 {r['종가']:,}원" + (f" — 그날 거래가 없어 직전거래일 {r['거래일']} 종가" if r["직전거래일_사용"] else "") + ". 양도세 대주주 시가총액은 직전 사업연도 종료일 기준이니 그 날짜를 넣었는지 확인", "근거": "소득세법 시행령 제157조④1호(최종시세가액, 없으면 직전거래일)"}]
            return {"결과": res, "판단": 판단, "근거": "소득세법 시행령 제157조④1호", "출처": "KRX 정보데이터시스템(pykrx) — 외부로 나간 정보: 종목코드·날짜"}
        if mode == "avg_2m":
            r = two_month_average(ticker, day, fetch)
            if "error" in r:
                return r
            res = {"종목": ticker, "종목명": name, **r}
            판단 = [{"항목": "용도", "결론": f"상속·증여 평가 시가 = 평가기준일 전후 각 2개월 종가 평균 {r['평균']:,.2f}원(거래일 {r['거래일수']}일)", "근거": "상속세 및 증여세법 제63조①1호가목"},
                  {"항목": "확인 필요", "결론": "기간 중 증자·합병 등으로 주가가 바뀐 사유가 있으면 평균 기간을 조정(영 제52조의2) — 이 도구는 조정하지 않음. 평가기준일 전후 2개월 안의 거래정지·관리종목 기간도 그대로 포함됨", "근거": "상속세 및 증여세법 시행령 제52조의2"}]
            return {"결과": res, "판단": 판단, "근거": "상속세 및 증여세법 제63조①1호가목, 시행령 제52조의2", "출처": "KRX 정보데이터시스템(pykrx) — 외부로 나간 정보: 종목코드·날짜"}
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": [f"mode='{mode}' — close(그날 종가) | avg_2m(전후 2개월 평균)"]}
    except RuntimeError as e:
        return {"error": str(e), "대안": "종가를 알면 stock_major_shareholder의 price(1주당 가액)나 own_mcap에 직접 넣으세요"}
