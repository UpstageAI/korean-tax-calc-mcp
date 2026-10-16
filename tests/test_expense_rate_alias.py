"""기타소득 필요경비율 연도별 기준·대손 별칭 — 정답은 법제처 원문으로 확인 (Claude 10-15)."""
from korean_tax_calc_mcp import server as s


def _f(name):
    t = getattr(s, name)
    return getattr(t, "fn", t)


def test_other_income_expense_rate_by_year():
    # 소득세법 시행령 제87조: 2018.3.31까지 1호(100분의 80), 2018.4.1부터 1호의2(100분의 70), 2019년부터 100분의 60
    f = _f("other_income_aggregate")
    for year, income in ((2017, 600_000), (2018, 900_000), (2019, 1_200_000)):
        r = f(year=year, items=[{"kind": "일시적인적용역", "amount": 3_000_000}])
        assert r["항목별"][0]["소득금액"] == income, year
    r = f(year=2018, items=[{"kind": "일시적인적용역", "amount": 3_000_000}])
    assert any("2018.3.31" in x for x in r["산식"])


def test_bad_debt_alias_bankruptcy():
    # '파산'은 회수불능의 별칭 — 결산조정 대손금으로 인정 (법인세법 시행령 제19조의2①8호)
    r = _f("bad_debt_adjustment")(year=2019, sme=True,
                                  book={"opening": 1_000_000, "offset": 500_000, "provision": 800_000, "closing": 1_300_000},
                                  receivables_prev_end_book=50_000_000, receivables_end_book=60_000_000,
                                  writeoffs=[{"kind": "파산", "amount": 500_000, "arose_in": "당기"}])
    assert r["판단"][0]["결론"].startswith("인정")
