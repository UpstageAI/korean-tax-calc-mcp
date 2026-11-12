"""0.31.11 해외 자회사 시나리오에서 나온 결함 3건(2026-11-12, Claude)."""
from korean_tax_calc_mcp import server as S


def _fn(t):
    return getattr(t, "fn", t)


def test_dividend_without_subsidiary_figures():
    # 자회사 세액·소득 없이 배당만: 익금불산입 95%(제18조의4), 외국 원천세는 손금불산입
    r = _fn(S.foreign_subsidiary_dividend)(received_on="2026-06-30", ownership_ratio=1.0, held_months=28,
                                           dividend=200_000_000, foreign_withholding=10_000_000)
    assert "error" not in r, r
    assert r["결과"]["제도"] == "익금불산입" and r["결과"]["익금불산입액"] == 190_000_000
    assert r["결과"]["익금산입액"] == 10_000_000 and r["결과"]["외국세_손금불산입"] == 10_000_000


def test_dividend_credit_path_without_subsidiary_figures_notes_zero_indirect():
    r = _fn(S.foreign_subsidiary_dividend)(received_on="2026-06-30", ownership_ratio=1.0, held_months=4,
                                           dividend=200_000_000, foreign_withholding=10_000_000)
    assert "error" not in r and r["결과"]["제도"] == "외국납부세액공제"
    assert r["결과"]["간접외국납부세액"] == 0 and r["결과"]["공제대상_외국법인세액"] == 10_000_000
    assert any(p["항목"] == "간접외국납부세액" for p in r["판단"])


def test_dividend_still_rejects_income_not_above_tax_when_both_given():
    r = _fn(S.foreign_subsidiary_dividend)(received_on="2026-06-30", ownership_ratio=1.0, held_months=4, dividend=200_000_000,
                                           subsidiary_tax=60_000_000, subsidiary_income=50_000_000)
    assert "error" in r
    ok = _fn(S.foreign_subsidiary_dividend)(received_on="2026-06-30", ownership_ratio=1.0, held_months=4, dividend=200_000_000,
                                            foreign_withholding=10_000_000, subsidiary_tax=60_000_000, subsidiary_income=300_000_000)
    assert ok["결과"]["간접외국납부세액"] == 50_000_000


def test_liquidation_is_not_judged_by_ownership_ratio():
    r = _fn(S.foreign_exchange_reporting)(event="청산", amount_usd=300_000, recovered_usd=20_000, event_date="2026-05-20")
    assert "error" not in r, r
    res = r["결과"]
    assert "미만" not in res["사유"] and "청산" in res["사유"]
    assert res["신고"]["구분"] == "해당없음" and "청산보고서" in res["신고"]["비고"]
    assert any(x["보고서"] == "청산보고서" for x in res["사후관리"])
    assert res["세무"]["해외직접투자명세_기한"] == ""
    # 지분 10% 미만 출자 문구
    low = _fn(S.foreign_exchange_reporting)(event="증액출자", amount_usd=10_000, ownership_ratio_after=0.05, event_date="2026-05-20")
    assert "5% — 10% 미만" in low["결과"]["사유"]


def _loan(**k):
    return _fn(S.deemed_interest)(movements=[S.Movement(date="2025-03-01", amount=1_000_000_000)], year_end="2025-12-31", **k)


def test_foreign_related_loan_uses_transfer_pricing_rule():
    dom = _loan(rate_mode="당좌선택")
    frn = _loan(rate_mode="당좌선택", foreign_related=True)
    assert dom["결과"]["시가이자"] == frn["결과"]["시가이자"] == 38_564_383      # 10억 × 4.6% × 306/365
    assert "법인세법 제52조" in dom["근거"] and dom["결과"]["부당행위"] is True
    assert "국제조세조정에 관한 법률" in frn["근거"] and "제7조" in frn["근거"]
    assert frn["결과"]["부당행위"] is False and frn["결과"]["정상가격_조정"] is True and frn["결과"]["익금산입"] == 38_564_383
    assert "이후 2개 사업연도" not in frn["결과"]["판단"]


def test_foreign_related_loan_has_no_5_percent_threshold():
    # 4.5%를 받으면 차액 0.1%p(시가이자의 약 2.2%) — 국내 특수관계인은 5% 미만이라 부인 안 함, 국외특수관계인은 차액 전부 조정
    dom = _loan(rate_mode="당좌선택", charged_rate=0.045)
    frn = _loan(rate_mode="당좌선택", charged_rate=0.045, foreign_related=True)
    assert dom["결과"]["익금산입"] == 0
    assert frn["결과"]["익금산입"] == frn["결과"]["차액"] > 0
    full = _loan(rate_mode="당좌선택", charged_rate=0.046, foreign_related=True)
    assert full["결과"]["익금산입"] == 0 and full["결과"]["정상가격_조정"] is False


def test_foreign_related_loan_rejections():
    r = _fn(S.deemed_interest)(movements=[S.Movement(date="2020-03-01", amount=1_000_000_000)], year_end="2020-12-31",
                               rate_mode="당좌선택", foreign_related=True)
    assert "error" in r and "2021" in r["문제"][0]
    r = _loan(rate_mode="가중평균", foreign_related=True, borrowings=[])
    assert "error" in r and "가중평균" in r["문제"][0]
