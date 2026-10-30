"""시세 조회 — 가짜 fetcher로 종가·직전거래일·2개월 평균 계산 검사(네트워크 없음). 작성 Claude 2026-10-30."""
from korean_tax_calc_mcp.engine.calc_stock_price import stock_price, _add_months
from datetime import date


def fake(ticker, start, end):
    # 2025-12-22 ~ 2026-03-06 매 평일 종가 = 1000 + 일 번호, 12/31은 휴장
    rows = []
    d = date(2025, 10, 20); n = 0
    while d <= date(2026, 3, 10):
        if d.weekday() < 5 and d != date(2025, 12, 31):
            n += 1; rows.append((d.isoformat(), 1000 + n))
        d = d.fromordinal(d.toordinal() + 1)
    s = f"{start[:4]}-{start[4:6]}-{start[6:]}"; e = f"{end[:4]}-{end[4:6]}-{end[6:]}"
    return [r for r in rows if s <= r[0] <= e]


def test_close_uses_previous_trading_day_on_holiday():
    r = stock_price("005930", "2025-12-31", mode="close", fetch=fake, name_lookup=lambda t: "삼성전자")
    assert r["결과"]["거래일"] == "2025-12-30" and r["결과"]["직전거래일_사용"] is True and r["결과"]["종목명"] == "삼성전자"
    r2 = stock_price("005930", "2025-12-30", mode="close", fetch=fake, name_lookup=lambda t: None)
    assert r2["결과"]["직전거래일_사용"] is False and r2["결과"]["종가"] == r["결과"]["종가"]


def test_two_month_average_window():
    r = stock_price("005930", "2026-01-05", mode="avg_2m", fetch=fake, name_lookup=lambda t: None)
    res = r["결과"]
    assert res["기간"] == "2025-11-05 ~ 2026-03-05"
    rows = fake("005930", "20251105", "20260305")
    assert res["거래일수"] == len(rows) and abs(res["평균"] - sum(c for _, c in rows) / len(rows)) < 1e-9
    assert any("제52조의2" in x["근거"] for x in r["판단"])


def test_bad_inputs_and_missing_pykrx_message():
    assert stock_price("삼성전자", "2025-12-30", fetch=fake)["error"].startswith("입력 확인 필요")
    assert stock_price("005930", "2025/12/30", fetch=fake)["error"].startswith("입력 확인 필요")
    def boom(t, s, e):
        raise RuntimeError("pykrx가 설치돼 있지 않음 — 안내")
    r = stock_price("005930", "2025-12-30", fetch=boom, name_lookup=lambda t: None)
    assert "pykrx" in r["error"] and "대안" in r


def test_add_months_edges():
    assert _add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert _add_months(date(2026, 3, 31), -1) == date(2026, 2, 28)
