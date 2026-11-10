"""해외직접투자 외국환 신고·사후보고·청산 판정 foreign_exchange_reporting — 정답 테스트(수정 금지, Claude 작성 2026-11-10).
근거: 외국환거래법 제18조, 시행령 제8조, 외국환거래규정(2026.11.2 시행) 제9-5조·제9-6조·제9-9조, 국조법 제58조, 법인46012-3838·법인46012-1986.
공개 검증 사례: 2026-11-10 5개년 시나리오(일본법인 설립 2024-03-01 자본금 2억, 대여 5억 2024-04-01, 증자 2025-10, 2026 배당·청산 가정).
"""
from _helpers import call as c


def test_new_subsidiary_prior_report_and_schedule():
    r = c("foreign_exchange_reporting", {"event": "신설출자", "ownership_ratio_after": 1.0, "amount_usd": 150_000, "event_date": "2024-03-01",
                                        "main_bank_type": "여신최다은행"})
    assert "error" not in r, r
    g = r["결과"]
    assert g["해외직접투자_해당"] is True
    assert g["신고"]["구분"] == "사전신고" and g["신고"]["기관"] == "여신최다은행"
    assert any("사업계획서" in s for s in g["신고"]["서류"]) and any("조세체납" in s for s in g["신고"]["서류"])
    sched = {x["보고서"]: x for x in g["사후관리"]}
    assert sched["외화증권취득보고서"]["기한"] == "2024-09-01"
    assert sched["송금보고서"]["기한"] == "즉시"
    assert sched["연간사업실적보고서"]["기한"] == "대상 아님"           # 누적 15만불 ≤ 300만불
    assert g["세무"]["해외직접투자명세_기한"] == "2025-06-30"
    assert "제9-5조" in r["근거"] and "제9-9조" in r["근거"] and "제58조" in r["근거"]


def test_loan_over_one_year_is_fdi_and_not_nonbusiness_advance():
    r = c("foreign_exchange_reporting", {"event": "금전대여", "ownership_ratio_after": 1.0, "loan_term_months": 24, "amount_usd": 370_000,
                                        "cumulative_usd": 520_000, "event_date": "2024-04-01"})
    g = r["결과"]
    assert g["해외직접투자_해당"] is True and g["신고"]["구분"] == "사전신고"
    assert {x["보고서"]: x for x in g["사후관리"]}["외화증권취득보고서"]["기한"] == "2024-10-01"
    assert any("가지급금" in s for s in g["세무"]["안내"])


def test_loan_under_one_year_is_not_fdi():
    r = c("foreign_exchange_reporting", {"event": "금전대여", "ownership_ratio_after": 1.0, "loan_term_months": 6, "amount_usd": 100_000, "event_date": "2025-01-01"})
    assert r["결과"]["해외직접투자_해당"] is False and r["결과"]["신고"]["구분"] == "해당없음"
    assert any("1년 미만" in str(j) for j in r["판단"])


def test_annual_report_required_over_3m_usd():
    r = c("foreign_exchange_reporting", {"event": "증액출자", "ownership_ratio_after": 1.0, "amount_usd": 3_500_000, "cumulative_usd": 3_700_000,
                                        "event_date": "2026-02-10"})
    sched = {x["보고서"]: x for x in r["결과"]["사후관리"]}
    assert sched["연간사업실적보고서"]["기한"] == "2027-05-31"           # 회계기간(2026.12.31) 종료 후 5월 이내
    assert sched["외화증권취득보고서"]["기한"] == "2026-08-10"


def test_retained_earnings_increase_allows_post_report():
    r = c("foreign_exchange_reporting", {"event": "유보금증자", "ownership_ratio_after": 1.0, "amount_usd": 200_000, "event_date": "2025-10-15"})
    assert r["결과"]["신고"]["구분"] == "사후보고" and r["결과"]["신고"]["기한"] == "2026-01-15"


def test_liquidation_report_and_tax_caution():
    r = c("foreign_exchange_reporting", {"event": "청산", "ownership_ratio_after": 1.0, "amount_usd": 0, "event_date": "2026-09-30", "recovered_usd": 0})
    g = r["결과"]
    sched = {x["보고서"]: x for x in g["사후관리"]}
    assert sched["청산보고서"]["기한"] == "즉시" and "제9-6조" in sched["청산보고서"]["근거"]
    assert any("손금" in s for s in g["세무"]["안내"]) and any("회수" in str(j) for j in r["판단"])


def test_share_sale_to_resident_three_months():
    r = c("foreign_exchange_reporting", {"event": "지분매각", "ownership_ratio_after": 0.0, "amount_usd": 500_000, "event_date": "2026-03-20", "counterparty_resident": True})
    sched = {x["보고서"]: x for x in r["결과"]["사후관리"]}
    assert sched["지분매각보고"]["기한"] == "2026-06-20"


def test_under_10pct_without_relationship_not_fdi_but_executive_dispatch_is():
    r = c("foreign_exchange_reporting", {"event": "신설출자", "ownership_ratio_after": 0.05, "amount_usd": 50_000, "event_date": "2026-01-10"})
    assert r["결과"]["해외직접투자_해당"] is False
    r2 = c("foreign_exchange_reporting", {"event": "임원파견", "ownership_ratio_after": 0.05, "amount_usd": 0, "event_date": "2026-01-10"})
    assert r2["결과"]["해외직접투자_해당"] is True


def test_month_end_rollover_and_financial_business_notice():
    r = c("foreign_exchange_reporting", {"event": "신설출자", "ownership_ratio_after": 1.0, "amount_usd": 10_000, "event_date": "2026-08-31"})
    assert {x["보고서"]: x for x in r["결과"]["사후관리"]}["외화증권취득보고서"]["기한"] == "2027-02-28"
    r2 = c("foreign_exchange_reporting", {"event": "신설출자", "ownership_ratio_after": 1.0, "amount_usd": 10_000, "event_date": "2026-08-31", "financial_business": True})
    assert any("제9-10조" in str(x) for x in r2.get("주의", []))


def test_errors():
    r = c("foreign_exchange_reporting", {"event": "합병", "amount_usd": 1, "event_date": "2026-01-01"})
    assert "error" in r and "허용값" in r
    assert "error" in c("foreign_exchange_reporting", {"event": "금전대여", "ownership_ratio_after": 1.0, "amount_usd": 1, "event_date": "2026-01-01"})
    assert "error" in c("foreign_exchange_reporting", {"event": "신설출자", "ownership_ratio_after": 1.0, "amount_usd": -1, "event_date": "2026-01-01"})
    assert "error" in c("foreign_exchange_reporting", {"event": "신설출자", "ownership_ratio_after": 1.0, "amount_usd": 1, "event_date": "2026/01/01"})


def test_find_tool_surfaces_tool():
    r = c("find_tool", {"query": "해외직접투자 외국환은행 신고 사후보고 청산보고", "n": 3})
    assert "foreign_exchange_reporting" in [x["도구"] for x in r["결과"]["후보"]], r
