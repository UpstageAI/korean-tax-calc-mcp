"""국조법 전부개정(2021.1.1. 시행) 전 사업연도(2016~2020 개시)의 정상가격 범위·대여금 정상이자·임시유보, 그 밖의 구 조문 번호.

대조한 원문(법제처 시행본 전문, 2026-11-15):
  · 구 국제조세조정에 관한 법률 2016.1.1.(법률 제13553호)~2020.6.9.(제17339호): 제3조②, 제4조, 제4조의2(법률 제16843호 신설, 부칙 제2조: 2020.1.1. 이후 개시 과세연도분부터),
    제9조①, 제20조의2, 제35조
  · 구 시행령 2016.2.5.(대통령령 제26958호)~2020.8.12.(제30934호): 제3조의2(2020.2.11.부터 제3조의3), 제5조, 제6조④⑤⑦, 제15조, 제15조의2, 제16조, 제37조, 제51조
    — 대통령령 제27837호(2017.2.7.) 부칙 제2조, 제30405호(2020.2.11.) 부칙 제2조, 제31448호(2021.2.17.) 부칙 제3조·제17조
  · 구 시행규칙 2015.12.2.(기획재정부령 제520호)~2020.3.13.(제772호): 제2조, 제2조의2(간주 정상이자율 ② 2017.3.17. 신설, 2019.3.20.부터 ③)
  · 법인세법 시행규칙 제43조②(당좌대출이자율 4.6%, 2016.3.7.부터)
  · 해외현지법인 명세서: 구 법인세법 제121조의2①·구 시행령 제164조의2①(2016~2020 각 연말 기준 시행본), 구 소득세법 제165조의2①·구 시행령 제217조의2①(2016·2020),
    구 법인세법 시행규칙 별지 제81호·제82호·제82호의2서식, 구 소득세법 시행규칙 별지 제93호~제95호서식, 국조법 부칙(법률 제17651호) 제28조
"""
from korean_tax_calc_mcp import server as S
from korean_tax_calc_mcp.engine import calc_batch0300 as B
from korean_tax_calc_mcp.engine import calc_foreign as F
from korean_tax_calc_mcp.engine import tp_era as E


def _fn(t):
    return getattr(t, "fn", t)


M = 1_000_000
COMPS = [0.02, 0.03, 0.04, 0.05, 0.06]


def _range(year):
    return _fn(S.arm_length_range)(comparables=COMPS, tested_value=0.01, base_amount=10_000 * M, tested_is_resident=True, year=year)


def test_era_boundaries():
    assert [E.era(y) for y in (2016, 2019, 2020, 2021, None)] == [E.ERA_OLD, E.ERA_OLD, E.ERA_2020, E.ERA_NEW, E.ERA_NEW]


def test_arm_length_range_opens_2016_to_2020():
    # 중위값 4% − 1% = 3%p × 100억 = 3억원 — 계산은 연도와 무관, 근거 조문만 바뀜
    for y in (2016, 2019, 2020, 2021):
        r = _range(y)
        assert "error" not in r and r["결과"]["조정액"] == 300 * M and r["세무조정"][0]["소득처분"] == "임시유보"
    r19, r20, r21 = _range(2019), _range(2020), _range(2021)
    assert "구 국제조세조정에 관한 법률 시행령 제6조④⑤" in r19["근거"] and "제4조의2" not in r19["근거"]
    assert "대통령령 제30405호" in r20["근거"] and "제4조의2" in r20["근거"]
    assert r21["근거"] == "국제조세조정에 관한 법률 시행령 제15조⑤⑥, 법 제6조·제7조"
    assert "과세당국의 처분" in r19["세무조정"][0]["근거"] and "수정신고" in r19["주의"][-1] and "근거 없음" in r19["주의"][-1]
    assert "과세당국 또는 내국법인" in r20["세무조정"][0]["근거"] and "제13조①" in r21["세무조정"][0]["근거"]
    assert any("과세당국의 과세조정 판정" in n for n in r19["주의"]) and not any("과세당국의 과세조정 판정" in n for n in r20["주의"])
    assert r19["비교대상_확인"][0]["근거"] == "구 시행령 제5조①1호" and r21["비교대상_확인"][0]["근거"] == "시행령 제14조①1호"
    assert "error" in _range(2015)


def _loan(**kw):
    return _fn(S.deemed_interest)(foreign_related=True, **kw)


def test_foreign_loan_deemed_rate_boundary_20170207():
    # 10억 × 4.6% × 365/365 = 46,000,000원
    r = _loan(movements=[S.Movement(date="2018-01-01", amount=1_000 * M)], year_end="2018-12-31", rate_mode="당좌선택")
    assert r["결과"]["익금산입"] == 46 * M and r["결과"]["부당행위"] is False
    assert "구 시행령 제6조⑦" in r["근거"] and "구 국제조세조정에 관한 법률 제4조" in r["세무조정"][0]["근거"]
    assert "어느 하나" in r["결과"]["판단"] and "제3조의2" in r["결과"]["판단"]
    # 2017.2.6. 대여 — 간주 이자율 없음 / 2017.2.7. 대여 — 가능(328일 × 4.6%)
    before = _loan(movements=[S.Movement(date="2017-02-06", amount=1_000 * M)], year_end="2017-12-31", rate_mode="당좌선택")
    assert "error" in before and "2017.2.7." in before["문제"][0]
    after = _loan(movements=[S.Movement(date="2017-02-07", amount=1_000 * M)], year_end="2017-12-31", rate_mode="당좌선택")
    assert after["결과"]["익금산입"] == 1_000 * M * 328 * 46 // (1000 * 365)
    assert any("2017.3.17." in n and "근거 없음" in n for n in after["주의"])           # 규칙 시행 전 거래분은 두 결과를 알림
    late = _loan(movements=[S.Movement(date="2017-03-17", amount=1_000 * M)], year_end="2017-12-31", rate_mode="당좌선택")
    assert not any("2017.3.17." in n for n in late["주의"])
    # 2017.2.7. 전 대여분은 2021년 이후 사업연도에도 간주 이자율 없음(대통령령 제31448호 부칙 제17조)
    carried = _loan(movements=[S.Movement(date="2016-06-01", amount=1_000 * M)], year_end="2025-12-31", rate_mode="당좌선택")
    assert "error" in carried
    # 입력 이자율: 10억 × 3% = 3천만원, 2016년도 계산
    r16 = _loan(movements=[S.Movement(date="2016-01-01", amount=1_000 * M)], year_end="2016-12-31", market_rate=0.03)
    assert r16["결과"]["익금산입"] == 30 * M * 366 // 366 and "수정신고" in r16["주의"][0]


def test_foreign_loan_era_by_fiscal_start():
    # 2020.7.1.~2021.6.30. 사업연도는 개시일 기준 구법(대통령령 제31448호 부칙 제3조)
    r = _loan(movements=[S.Movement(date="2020-07-01", amount=1_000 * M)], year_end="2021-06-30", fiscal_start="2020-07-01", rate_mode="당좌선택")
    assert r["결과"]["익금산입"] == 46 * M and "구 국제조세조정에 관한 법률 제3조②" in r["근거"] and "제3조의3" in r["결과"]["판단"]
    n = _loan(movements=[S.Movement(date="2021-01-01", amount=1_000 * M)], year_end="2021-12-31", rate_mode="당좌선택")
    assert n["근거"].startswith("국제조세조정에 관한 법률 제4조②") and "법 제8조① 단서" in n["결과"]["판단"]


def test_schedule_and_expat_disposition_old_years():
    for y, key in ((2019, "수정신고한 날"), (2020, "신고한 날(구 법 제4조의2)"), (2021, "신고한 날")):
        r = _fn(S.tax_adjustment_schedule)(years=[{"year": y, "book_income": 0, "adjustments": [{"name": "정상가격", "amount": 5 * M, "kind": "익금산입", "disposition": "임시유보"}]}])
        p = [x for x in r["판단"] if "임시유보" in x["항목"]][0]
        assert key in p["결론"] and ("구 " in p["근거"]) == (y <= 2020)
    item = {"이름": "A", "급여": 100 * M, "귀속": "현지법인", "마크업": 0.05, "청구액": 100 * M}
    for y in (2019, 2020, 2021):
        r = _fn(S.expat_cost_recharge)(year=y, items=[dict(item)])
        tp = [a for a in r["세무조정"] if a["소득처분"] == "임시유보"]
        assert len(tp) == 1 and tp[0]["금액"] == 5 * M and ("구 국제조세조정에 관한 법률 제4조" in tp[0]["근거"]) == (y <= 2020)


def test_related_party_law_old_article_numbers():
    f = lambda y: F.related_party_law(True, "자본거래", y)
    assert "구 시행령 제3조의2" in f(2019)["근거"] and "구 시행령 제3조의3" in f(2020)["근거"] and "시행령 제4조" in f(2021)["근거"]
    assert all("주의" not in f(y) for y in (2018, 2019, 2020, 2021))


def test_overseas_account_penalty_before_20210217():
    # 위반금액 150억: 6.5억 + (150억 − 50억) × 20% = 26.5억 — 2021.2.17. 전 부과분은 20억원 한도 없음(구 시행령 제51조), 이후는 20억원
    kw = dict(year=2018, month_end_totals_krw=[15_000 * M] * 12, reported_amount_krw=0)
    old = B.overseas_account_reporting(assessed_on="2021-02-16", **kw)
    new = B.overseas_account_reporting(assessed_on="2021-02-17", **kw)
    assert old["결과"]["과태료"] == 2_650 * M and new["결과"]["과태료"] == 2_000 * M
    assert any("2,650,000,000원" in n for n in new["주의"])
    small = B.overseas_account_reporting(assessed_on="2019-09-01", year=2018, month_end_totals_krw=[3_000 * M] * 12, reported_amount_krw=0)
    assert small["결과"]["과태료"] == 200 * M + 150 * M      # 2억 + (30억 − 20억) × 15%
    assert "error" in B.overseas_account_reporting(assessed_on="2015-12-31", **kw)


def test_overseas_subsidiary_statement_old_years():
    from korean_tax_calc_mcp.engine import calc_overseas_sub as O
    kw = dict(ownership_direct=0.6, equity_investment=500 * M, related_party=True, loss_single_year=6_000 * M)
    # 2019.12.31. 종료 법인: 종전 기한 2020.3.31.(3개월)이 2021.1.1. 전 — 종전 규정
    r = O.statement(2019, "법인", "2019-12-31", **kw)
    assert r["결과"]["적용_규정"] == "종전" and r["결과"]["제출기한"] == "2020-03-31"
    assert r["결과"]["재무상황표_제출대상"] is True and r["결과"]["손실거래명세서_제출대상"] is True
    assert "구 법인세법 제121조의2제1항" in r["근거"] and "별지 제82호서식" in r["판단"][1]
    # 2020.12.31. 종료 법인: 종전 기한 2021.3.31.이 2021.1.1. 전에 지나지 않음 — 현행 6개월(부칙 제28조)
    n = O.statement(2020, "법인", "2020-12-31", **kw)
    assert n["결과"]["적용_규정"] == "현행" and n["결과"]["제출기한"] == "2021-06-30" and "제58조제1항" in n["근거"]
    # 2020.9.30. 종료 법인: 종전 기한 2020.12.31. — 종전 규정
    b = O.statement(2020, "법인", "2020-09-30", **kw)
    assert b["결과"]["적용_규정"] == "종전" and b["결과"]["제출기한"] == "2020-12-31"
    # 개인 2019년: 다음 연도 5.31., 손실거래 10억원 기준
    p = O.statement(2019, "개인", None, ownership_direct=0.6, equity_investment=500 * M, related_party=True, loss_single_year=1_000 * M)
    assert p["결과"]["제출기한"] == "2020-05-31" and p["결과"]["손실거래명세서_제출대상"] is True and "구 소득세법 제165조의2제1항" in p["근거"]
    p20 = O.statement(2020, "개인", None, ownership_direct=0.6, equity_investment=500 * M)
    assert p20["결과"]["적용_규정"] == "현행" and p20["결과"]["제출기한"] == "2021-06-30"
    assert "error" in O.statement(2015, "법인", "2015-12-31", **kw)
