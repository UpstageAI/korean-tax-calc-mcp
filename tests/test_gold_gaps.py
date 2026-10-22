"""정답 인자 세트 대조에서 나온 도구 공백 5건의 정답 테스트. 작성 Claude 2026-10-22.
각 값은 문항을 손으로 푼 결과와 같다(docs/SPEC_gold_gaps.md)."""
import asyncio, json
from korean_tax_calc_mcp.server import mcp


def c(tool, a):
    r = asyncio.run(mcp.call_tool(tool, a))
    return json.loads((r.content[0] if hasattr(r, "content") else r[0][0]).text)


def test_common_asset_sale_input_tax_prorated_by_prior_period_ratio():
    r = c("common_input_tax", {"year": 2021, "period": "1기", "filing": "확정",
                               "supplies": {"확정": {"taxable": 80, "exempt": 20}},
                               "prior_period_supplies": {"taxable": 70, "exempt": 30},
                               "common_asset_sales": [{"sale_price": 15000000, "input_tax": 2000000}],
                               "ledger": [{"항목": "원재료 과세", "매입세액": 50000000, "사용처": "과세"},
                                          {"항목": "비품 과세", "매입세액": 10000000, "사용처": "과세"},
                                          {"항목": "기계장치 공통", "매입세액": 10000000, "사용처": "공통"}]})
    assert r["계산"]["공통사용재화_매입세액_공제"] == 1400000
    assert r["결과"]["공제매입세액"] == 69400000
    assert any("직전" in p["결론"] and "81조④" in p["근거"] for p in r["판단"])


def test_dividend_excluded_within_3m_is_not_charged_interest():
    r = c("dividend_received_deduction", {"year": 2022, "company_type": "지주회사", "interest_paid": 50000000, "total_assets_jeoksu": 1825000000000,
                                           "investees": [{"name": "B", "listed": False, "ratio": 0.7, "dividend": 35000000, "book_value_jeoksu": 127750000000},
                                                         {"name": "C", "listed": False, "ratio": 0.45, "dividend": 5000000, "within_3m_dividend": 5000000, "book_value_jeoksu": 219000000000}]})
    C = r["결과"]["피출자법인별"][1]
    assert C["제외_배당금"] == 5000000 and C["차감액"] == 0 and C["익금불산입액"] == 0
    assert r["결과"]["익금불산입액"] == 28350000


def test_dividend_per_investee_never_negative():
    r = c("dividend_received_deduction", {"year": 2022, "interest_paid": 50000000, "total_assets_jeoksu": 1825000000000,
                                           "investees": [{"name": "C", "listed": False, "ratio": 0.45, "dividend": 1000000, "book_value_jeoksu": 219000000000}]})
    assert r["결과"]["피출자법인별"][0]["익금불산입액"] == 0 and r["결과"]["익금불산입액"] == 0


def test_entertainment_in_kind_valued_at_market_plus_vat():
    r = c("entertainment_adjustment", {"year": 2022, "sme": True,
                                       "ledger": [{"항목": "거래처 증정 제품", "금액": 9000000, "증빙": "적격", "성격": "현물", "시가": 10000000, "장부가액": 8000000}],
                                       "revenue": {"매출액": 15000000000, "특수관계매출": 3000000000}})
    item = [p for p in r["판단"] if p["항목"] == "거래처 증정 제품"][0]
    assert item["금액"] == 11000000 and r["결과"]["시부인_대상"] == 11000000


def test_entertainment_private_use_is_bonus_not_limit_test():
    r = c("entertainment_adjustment", {"year": 2023, "sme": False,
                                       "ledger": [{"항목": "대표이사 사적 사용", "금액": 1000000, "증빙": "적격", "성격": "사적사용"},
                                                  {"항목": "접대비", "금액": 5000000, "증빙": "적격"}],
                                       "revenue": {"매출액": 1000000000}})
    assert r["결과"]["직부인_대표자상여"] == 1000000 and r["결과"]["시부인_대상"] == 5000000
    assert r["결과"]["손금불산입_합계"] == 1000000
    assert r["결과"]["소득처분별_합계"]["대표자상여"] == 1000000
    assert any(t["소득처분"] == "대표자상여" and t["금액"] == 1000000 for t in r["결과"]["세무조정"])


def test_common_input_new_building_uses_planned_area_ratio():
    r = c("common_input_tax", {"year": 2023, "period": "2기", "filing": "확정",
                               "supplies": {"확정": {"taxable": 45, "exempt": 55}},
                               "ledger": [{"항목": "신축건물 공통매입", "매입세액": 20000000, "사용처": "공통", "면적": {"과세": 53, "면세": 47}, "신축건물": True}]})
    assert r["결과"]["공제매입세액"] == 10600000
    assert any("예정사용면적" in p["결론"] for p in r["판단"])


def test_inheritance_spouse_legal_share_accepts_decimal():
    r = c("inheritance_tax", {"year": 2021, "estate_value": 3800000000, "funeral_cost": 4000000, "enshrinement_cost": 9000000,
                              "spouse": {"actual": 0, "legal_share": 0.6}, "children": 1,
                              "net_financial_assets": 1300000000, "cohabiting_house": {"value": 2500000000}})
    assert r["결과"]["과세표준"] == 1990000000
    bad = c("inheritance_tax", {"year": 2021, "estate_value": 3800000000, "spouse": {"actual": 0, "legal_share": "abc"}})
    assert "error" in bad and "3/5" in json.dumps(bad, ensure_ascii=False)


def test_entertainment_in_kind_with_only_one_value():
    """시가 또는 장부가액 중 하나만 있어도 평가해야 한다(하네스 점검 후속 리뷰)."""
    only_market = c("entertainment_adjustment", {"year": 2022, "sme": True, "revenue": {"매출액": 1000000000},
                                                 "ledger": [{"항목": "현물", "성격": "현물", "시가": 10000000}]})
    assert "error" not in only_market and only_market["결과"]["시부인_대상"] == 11000000
    only_book = c("entertainment_adjustment", {"year": 2022, "sme": True, "revenue": {"매출액": 1000000000},
                                               "ledger": [{"항목": "현물", "성격": "현물", "장부가액": 8000000}]})
    assert "error" not in only_book and only_book["결과"]["시부인_대상"] == 8800000
