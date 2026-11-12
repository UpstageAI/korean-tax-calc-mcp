"""0.32.0 vat_tax_base_adjustments 정답 테스트(2026-11-12, Claude 손계산).
조문: 부가가치세법 제29조③6호·⑤·⑥(2016·2017·2026 시행본), 시행령 제61조(2016·2017.4.1.·2019·2026)·제70조①1호, 대통령령 제27838호 부칙 제1조."""
import asyncio
from korean_tax_calc_mcp import server as S


def f(**k):
    return getattr(S.vat_tax_base_adjustments, "fn", S.vat_tax_base_adjustments)(**k)


def test_returns_allowances_incentives():
    # 매출 10억 − 환입 5,000만 − 에누리 1,000만 − 매출할인 300만 = 9.37억. 장려금 2,000만·대손금 700만은 공제 안 함
    r = f(period="2025-2", sales=1_000_000_000, adjustments=[
        {"종류": "환입", "금액": 50_000_000, "발생일": "2025-09-10"}, {"종류": "매출에누리", "금액": 10_000_000},
        {"종류": "매출할인", "금액": 3_000_000}, {"종류": "판매장려금", "금액": 20_000_000}, {"종류": "대손금", "금액": 7_000_000}])
    res = r["결과"]
    assert res["과세표준"] == 937_000_000 and res["차감_합계"] == 63_000_000 and res["매출세액"] == 93_700_000
    rows = {x["종류"]: x for x in r["계산"]["조정_항목별"]}
    assert rows["판매장려금"]["과세표준_차감"] == 0 and "제29조⑥" in rows["판매장려금"]["근거"]
    assert rows["환입"]["근거"] == "부가가치세법 제29조⑤2호, 시행령 제70조①1호"
    assert "제70조①1호" in r["근거"]


def test_return_outside_period_not_deducted():
    r = f(period="2025-2", sales=100_000_000, adjustments=[{"종류": "환입", "금액": 5_000_000, "발생일": "2026-01-05"}])
    assert r["결과"]["과세표준"] == 100_000_000
    assert "과세기간 2025-2 밖" in r["계산"]["조정_항목별"][0]["사유"]


def test_interest_and_subsidy_excluded():
    r = f(period="2025-1", sales=100_000_000, adjustments=[{"종류": "연체이자", "금액": 1_000_000}, {"종류": "보조금", "금액": 4_000_000},
                                                            {"종류": "도달전파손", "금액": 2_000_000}])
    assert r["결과"]["과세표준"] == 93_000_000


def test_own_mileage_excluded_vat_included():
    # 판매가 110,000(부가세 포함) 중 자기적립 포인트 22,000 결제 → 공급가액 = 88,000 × 100/110 = 80,000
    r = f(period="2025-2", mileage_sales=[{"이름": "자사몰", "공급일": "2025-08-01", "현금등": 88_000, "자기적립마일리지": 22_000}], vat_included=True)
    assert r["결과"]["과세표준"] == 80_000 and r["결과"]["매출세액"] == 8_000
    assert "제61조②9호·10호" in r["근거"]


def test_third_party_mileage_with_compensation():
    # 현금 77,000 + 제휴 포인트 33,000(제휴사 보전 22,000) → (77,000 + 22,000) × 100/110 = 90,000
    r = f(period="2025-2", mileage_sales=[{"공급일": "2025-08-02", "현금등": 77_000, "그외마일리지": 33_000, "보전금액": 22_000}], vat_included=True)
    assert r["결과"]["과세표준"] == 90_000
    # 부가세 제외 금액으로 넣으면 그대로
    r = f(period="2025-2", mileage_sales=[{"공급일": "2025-08-02", "현금등": 70_000, "그외마일리지": 30_000, "보전금액": 20_000}])
    assert r["결과"]["과세표준"] == 90_000


def test_third_party_mileage_without_compensation_market_value():
    m = {"공급일": "2025-08-03", "현금등": 77_000, "그외마일리지": 33_000, "보전금액": 0}
    # 보전 없음 + 자기생산·취득재화 → 시가(10호 가목)
    r = f(period="2025-2", mileage_sales=[{**m, "자기생산취득재화": True, "시가": 110_000}], vat_included=True)
    assert r["결과"]["과세표준"] == 100_000 and "10호 가목" in r["계산"]["마일리지등_거래"][0]["사유"]
    # 시가를 안 주면 계산하지 않음
    assert "error" in f(period="2025-2", mileage_sales=[{**m, "자기생산취득재화": True}], vat_included=True)
    # 자기생산·취득재화가 아니면 받은 금액
    r = f(period="2025-2", mileage_sales=[m], vat_included=True)
    assert r["결과"]["과세표준"] == 70_000
    # 특수관계인 저가 보전 → 시가(10호 나목)
    r = f(period="2025-2", mileage_sales=[{**m, "보전금액": 5_000, "특수관계_저가보전": True, "시가": 110_000}], vat_included=True)
    assert r["결과"]["과세표준"] == 100_000 and "10호 나목" in r["계산"]["마일리지등_거래"][0]["사유"]


def test_combined_period():
    r = f(period="2025-2", sales=1_000_000_000,
          adjustments=[{"종류": "환입", "금액": 50_000_000, "발생일": "2025-09-10"}, {"종류": "판매장려금", "금액": 20_000_000}, {"종류": "매출에누리", "금액": 10_000_000}],
          mileage_sales=[{"공급일": "2025-08-01", "현금등": 88_000_000, "자기적립마일리지": 22_000_000},
                         {"공급일": "2025-08-02", "현금등": 77_000_000, "그외마일리지": 33_000_000, "보전금액": 22_000_000}], vat_included=True)
    assert r["결과"] == {"과세표준": 1_110_000_000, "조정전_매출": 1_000_000_000, "차감_합계": 60_000_000,
                        "마일리지등_거래_공급가액": 170_000_000, "매출세액": 111_000_000}


def test_mileage_rule_dates():
    ok = f(period="2017-1", mileage_sales=[{"공급일": "2017-04-01", "현금등": 88_000, "자기적립마일리지": 22_000}], vat_included=True)
    assert ok["결과"]["과세표준"] == 80_000 and "제61조①9호·10호" in ok["근거"]      # 2018.2.13. 전에는 제1항
    old = f(period="2017-1", mileage_sales=[{"공급일": "2017-03-31", "현금등": 88_000, "자기적립마일리지": 22_000}], vat_included=True)
    assert "error" in old and "2017.3.31." in old["문제"][0]
    out = f(period="2025-2", mileage_sales=[{"공급일": "2025-06-30", "현금등": 88_000}])
    assert "error" in out and "밖" in out["문제"][0]


def test_input_errors():
    assert "error" in f(period="2027-1", sales=1)
    assert "error" in f(period="2025-3", sales=1)
    r = f(period="2025-1", sales=1, adjustments=[{"종류": "반품비", "금액": 1}])
    assert "error" in r and "허용값" in r["문제"][0]
    assert "error" in f(period="2025-1", sales=1, adjustments=[{"종류": "환입", "금액": -1}])


def test_negative_base_noted():
    r = f(period="2025-1", sales=10_000_000, adjustments=[{"종류": "환입", "금액": 30_000_000}])
    assert r["결과"]["과세표준"] == -20_000_000 and r["결과"]["매출세액"] == 0
    assert any(p["항목"] == "과세표준" for p in r["판단"])


def test_find_tool_routes_keywords():
    g = getattr(S.find_tool, "fn", S.find_tool)
    for q in ("포인트 결제 부가세 과세표준", "반품 수정세금계산서 과세표준", "판매장려금 과세표준 공제"):
        r = g(q)
        assert "vat_tax_base_adjustments" in str(r), (q, r)
