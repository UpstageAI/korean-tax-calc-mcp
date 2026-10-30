"""처음 쓰는 사람 점검(생활어 질문 10개)에서 나온 입력·안내 문제 회귀 테스트. 작성 Claude 2026-10-30."""
import asyncio, json
from korean_tax_calc_mcp.server import mcp


def c(tool, a):
    r = asyncio.run(mcp.call_tool(tool, a))
    return json.loads((r.content[0] if hasattr(r, "content") else r[0][0]).text)


def top(q):
    return [x["도구"] for x in c("find_tool", {"query": q})["결과"]["후보"]]


def test_find_tool_everyday_words():
    assert top("연봉 5천만원 직장인 세금 얼마 내요?")[0] == "wage_income_tax"
    assert top("프리랜서로 3.3% 떼고 3천만원 받았는데 종합소득세 얼마?")[0] == "estimated_business_income"
    assert top("배당 3천만원 받으면 종합과세 되나요?")[0] == "financial_income_aggregate"
    assert top("부모님한테 2억 받으면 증여세 얼마?")[0] == "gift_tax"
    r = c("find_tool", {"query": "연봉 5천만원 세금"})["결과"]
    assert "law_article" in r["근거 조회"] and "github.com/UpstageAI/korean-tax-mcp" in r["근거 서버"]["레포"]


def test_find_tool_stock_routes_to_new_tools():
    assert top("삼성전자 주식 팔았는데 양도세")[0] == "stock_capital_gains_tax"
    assert top("나 대주주야?")[0] == "stock_major_shareholder"


def test_find_tool_longer_alias_wins():
    assert top("수입배당금 익금불산입")[0] == "dividend_received_deduction"
    assert top("의제배당 무상주")[0] == "deemed_dividend_bonus_shares"
    assert top("경매 배당표 국세")[0] == "tax_priority_distribution"


def test_find_tool_names_missing_calculations():
    for q, what in (("월세 100만원 내는데 세액공제 얼마 돼요?", "월세액 세액공제"), ("연금저축 400만원 넣으면 세액공제?", "연금계좌 세액공제"),
                    ("종부세 얼마", "종합부동산세")):
        r = c("find_tool", {"query": q})["결과"]
        assert r["후보"] == [] and what in r["없는 계산"]
        assert r["근거 조회"][0]["도구"] == "law_article" and r["근거 조회"][0]["article"].startswith("제")
        assert "uvx korean-tax-mcp" in r["근거 서버"]["설치"]
    # 양도 계산 질문에 섞인 취득세는 걸러내지 않음
    assert "없는 계산" not in c("find_tool", {"query": "양도할 때 취득세 필요경비 되나"})["결과"]
    assert top("양도할 때 취득세 필요경비 되나")[0] == "capital_gains_income"


def test_gift_tax_relation_everyday_words():
    r = c("gift_tax", {"gift_date": "2026-10-30", "gift_value": 200000000, "relation": "부모"})
    assert r["결과"]["증여재산공제"] == 50000000 and "직계존속" in r["입력 해석"]
    r = c("gift_tax", {"gift_date": "2026-10-30", "gift_value": 50000000, "relation": "장인"})
    assert r["결과"]["증여재산공제"] == 10000000 and "기타친족" in r["입력 해석"]
    r = c("gift_tax", {"gift_date": "2026-10-30", "gift_value": 50000000, "relation": "직계존속"})
    assert "입력 해석" not in r
    e = c("gift_tax", {"gift_date": "2026-10-30", "gift_value": 1, "relation": "옆집"})
    assert e["error"].startswith("입력 확인 필요") and "기타친족" in e["허용값"]


def test_financial_income_kind_everyday_words():
    r = c("financial_income_aggregate", {"year": 2025, "items": [{"kind": "배당", "amount": 30000000}, {"kind": "이자", "amount": 1000000}]})
    assert "error" not in r and r["결과"]["Gross-up"] == 1100000 and r["결과"]["합산액"] == 32100000
    assert any("상장법인현금배당" in x for x in r["입력 해석"]) and any("예금이자" in x for x in r["입력 해석"])


def test_wage_income_tax_without_tax_base():
    r = c("wage_income_tax", {"gross_pay": 50000000, "year": 2025})
    res = r["결과"]
    assert res["근로소득공제"] == 12250000 and res["과세표준"] == 36250000 and res["산출세액"] == 4177500
    assert res["근로소득세액공제"] == 660000 and res["표준세액공제"] == 130000 and res["결정세액(참고)"] == 3387500 and res["지방소득세(참고)"] == 338750
    assert "150만" in r["판단"][0]
    # 과세표준을 주면 그대로
    r2 = c("wage_income_tax", {"gross_pay": 50000000, "year": 2025, "tax_base": 30000000})
    assert r2["결과"]["과세표준"] == 30000000 and r2["판단"][0] == "과세표준은 입력값 그대로"
    assert r2["결과"]["표준세액공제"] == 0 and r2["결과"]["결정세액(참고)"] == r2["결과"]["산출세액"] - r2["결과"]["근로소득세액공제"]


def test_find_tool_local_tax_in_capital_gains_question_not_blocked():
    r = c("find_tool", {"query": "자동차세 낸 것도 양도세 필요경비?"})["결과"]
    assert "없는 계산" not in r and r["후보"][0]["도구"] == "capital_gains_income"


def test_simplified_vat_card_fee_not_treated_as_card_sales():
    e = c("simplified_vat_return", {"year": 2025, "business_type": "소매업", "ledger": {"공급": [{"항목": "카드수수료", "금액": 100000}], "매입": []}})
    assert "error" in e


def test_simplified_vat_card_sales_word():
    r = c("simplified_vat_return", {"year": 2025, "business_type": "소매업", "ledger": {"공급": [{"항목": "카드매출", "금액": 60000000}], "매입": []}})
    assert "error" not in r and r["계산"]["신용카드매출전표등발급세액공제"] == 780000


def test_business_car_plate_rule_only_for_80m_and_up():
    # 6천만원 차량·번호판 미부착·운행기록 80%: 번호판 요건 대상 아님 → 손금산입 12,000,000 / 손금불산입 0.6+2.4+1.6 → 순 −7,400,000
    r = c("business_car_expense", {"year": 2026, "upkeep": 3_000_000, "depreciation": 12_000_000, "booked_depreciation": 0, "log_kept": True, "business_ratio": 0.8, "months": 12, "plate_ok": False, "acquisition_cost": 60_000_000})
    res = r["결과"]
    assert res["업무사용비율"] == 0.8 and res["유지비 손금불산입(상여)"] == 600_000 and res["감가상각 한도초과(유보)"] == 1_600_000 and "번호판 요건" in res
    r = c("business_car_expense", {"year": 2026, "upkeep": 3_000_000, "depreciation": 12_000_000, "booked_depreciation": 0, "log_kept": True, "business_ratio": 0.8, "months": 12, "plate_ok": False, "acquisition_cost": 90_000_000})
    assert r["결과"]["업무사용비율"] == 0


def test_entertainment_limit_exposes_market():
    # 2024 사업연도: 전통시장 추가한도 10% → 7,840,000, 한도초과 17,760,000
    r = c("entertainment_limit", {"year": 2024, "sme": True, "general_revenue": 16_000_000_000, "related_revenue": 2_000_000_000, "expensed": 110_000_000, "culture": 6_000_000, "market": 9_000_000})
    res = r["결과"]
    assert res["일반한도"] == 78_400_000 and res["문화한도"] == 6_000_000 and res["전통시장한도"] == 7_840_000 and res["한도초과(기타사외유출)"] == 17_760_000
    # 2025 사업연도 신고분(2026.1.1. 이후 신고)은 법률 제21223호 부칙 제31조로 20% → 9,000,000, 한도초과 16,600,000
    res = c("entertainment_limit", {"year": 2025, "sme": True, "general_revenue": 16_000_000_000, "related_revenue": 2_000_000_000, "expensed": 110_000_000, "culture": 6_000_000, "market": 9_000_000})["결과"]
    assert res["전통시장한도"] == 9_000_000 and res["한도초과(기타사외유출)"] == 16_600_000
