"""0.31.9 연도 점검 남은 항목(2026-11-12): 출산 급여 전액 비과세, 경정청구 종전 3년 규정, 비거주자 원천징수 근거 호, 의제매입 근거 위치."""
from korean_tax_calc_mcp import server as S


def _fn(t):
    return getattr(t, "fn", t)


def _egp(year, facts, amount=10_000_000):
    r = _fn(S.earned_income_gross_pay)(year, [{"kind": "급여", "amount": 50_000_000},
                                               {"kind": "출산·보육수당", "amount": amount, "facts": facts}])
    assert "error" not in r, r
    return [x for x in r["항목별"] if x["kind"] == "출산·보육수당"][0]


def _nontax(x):
    return x.get("비과세액", x.get("비과세"))


def test_birth_pay_2024_child_born_2021_or_later_without_2y():
    # 2024년 지급분: 2021.1.1. 이후 출생 자녀면 2년이 지났어도 전액 비과세(제12조3호머목1) 괄호)
    x = _egp(2024, {"purpose": "출산", "within_2y_of_birth": False, "child_born_on": "2021-03-01", "payment_count": 1})
    assert _nontax(x) == 10_000_000
    # 2020년 출생이면 대상 아님 → 2024년은 종전 머목 월 한도(20만 × months)
    y = _egp(2024, {"purpose": "출산", "within_2y_of_birth": False, "child_born_on": "2020-12-31", "payment_count": 1, "months": 1})
    assert _nontax(y) == 200_000


def test_birth_pay_2025_special_rule_not_applied():
    # 2025년 지급분에는 2021년생 특례 없음 — 2년 이내가 아니면 전액 과세
    x = _egp(2025, {"purpose": "출산", "within_2y_of_birth": False, "child_born_on": "2021-03-01", "payment_count": 1, "months": 12})
    assert _nontax(x) == 0 and "전액 과세" in x["사유"]


def test_birth_pay_2025_related_party_or_third_payment_taxable():
    for facts in ({"purpose": "출산", "within_2y_of_birth": True, "payment_count": 1, "related_party": True, "months": 12},
                  {"purpose": "출산", "within_2y_of_birth": True, "payment_count": 3, "months": 12}):
        x = _egp(2026, facts)
        assert _nontax(x) == 0, x


def test_birth_pay_qualifying_cites_law_and_decree():
    x = _egp(2025, {"purpose": "출산", "within_2y_of_birth": True, "payment_count": 2})
    assert _nontax(x) == 10_000_000 and "머목1)" in x["사유"] and "제17조의2" in x["사유"] and "2호" not in x["사유"]


def test_birth_pay_2023_monthly_cap_unchanged():
    x = _egp(2023, {"purpose": "출산", "months": 12})
    assert _nontax(x) == 1_200_000


def test_refund_claim_old_three_year_rule_rejected():
    f = _fn(S.refund_claim_deadline)
    # 2010년 귀속 소득세: 법정신고기한 2011.5.31. → 종전 3년이 2014.6.2.에 끝남 → 5년 규정 아님
    r = f(kind="통상", tax="소득세", year=2010)
    assert "error" in r and "제7조제2항" in r["error"]
    r = f(kind="통상", due_date="2011-12-30")          # 금요일 — 종전 3년이 2014.12.30.에 끝남
    assert "error" in r
    # 법정신고기한 2011.12.31.(토) → 기한 특례로 2012.1.2. → 종전 3년이 2015.1.2.까지라 시행 당시 지나지 않음 → 5년
    for d in ("2011-12-31", "2012-01-02"):
        r = f(kind="통상", due_date=d)
        assert "error" not in r and r["결과"]["경정청구_기한"].startswith("2017-01-02")
    # 2011년 귀속 소득세(기한 2012.5.31.)는 5년 — 2017.5.31.
    r = f(kind="통상", tax="소득세", year=2011)
    assert "error" not in r and r["결과"]["경정청구_기한"].startswith("2017-05-31")


def test_nonresident_withholding_basis_by_year():
    f = _fn(S.nonresident_withholding)
    new = f("사용료", 100_000_000, "법인", "US", year=2019)
    old = f("사용료", 100_000_000, "법인", "US", year=2018)
    none = f("사용료", 100_000_000, "법인", "US")
    assert old["결과"]["원천징수세액"] == new["결과"]["원천징수세액"] == none["결과"]["원천징수세액"] == 20_000_000
    assert "제98조①6호" in str(new["근거"]) and "제98조①6호" in str(none["근거"])
    assert "제98조①3호" in str(old["근거"]) and "개정 전" in str(old["근거"])
    assert "제156조①2호" in str(f("인적용역", 1_000_000, "개인", "US", year=2017)["근거"])
    assert "제156조①4호" in str(f("인적용역", 1_000_000, "개인", "US", year=2026)["근거"])
    b = f("이자", 1_000_000, "개인", "US", bond_interest=True, year=2016)
    assert b["결과"]["원천징수세액"] == 140_000 and "3호 단서" in str(b["근거"])
    assert "1호가목" in str(f("이자", 1_000_000, "개인", "US", bond_interest=True, year=2020)["근거"])


def test_nonresident_withholding_year_out_of_range():
    r = _fn(S.nonresident_withholding)("배당", 1_000_000, "법인", "US", year=2015)
    assert "error" in r


def test_deemed_input_basis_location_by_period():
    f = _fn(S.vat_deemed_input_credit)
    old = f(period="2017-2", industry="음식점", purchase=50_000_000, base=200_000_000)
    new = f(period="2018-1", industry="음식점", purchase=50_000_000, base=200_000_000)
    for r in (old, new):
        assert "error" not in r, r
    def 근거(r, word):
        return [s["근거"] for s in r["결과"]["단계별_계산"] if word in s["항목"]]
    assert all("시행령 제84조① 표" in b for b in 근거(old, "공제율"))
    assert all(b == "부가가치세법 제42조① 표" for b in 근거(new, "공제율"))
    for r in (old, new):
        lim = [x["근거"] for x in r["결과"]["단계별_계산"] if x["항목"].startswith(("과세표준", "한도"))]
        assert lim and all("시행령 제84조②" in b for b in lim) and not any("제42조②" in b for b in lim)
    assert "제84조①" in str(old["근거"]) and "① 표" in str(new["근거"])


def test_ownership_ratio_description_mentions_old_article():
    import asyncio
    tools = asyncio.run(S.mcp.list_tools())
    d = [t for t in tools if t.name == "ownership_ratio"][0].description
    assert "제34조의3제2항" in d and "제34조의2제2항" in d
