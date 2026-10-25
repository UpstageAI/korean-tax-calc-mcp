"""부가세 판정 도구 2개(매입세액 공제 판정·간주공급 판정)의 정답 테스트. 작성 Claude 2026-10-24.
값은 문항을 손으로 푼 결과(docs/SPEC_gold_gaps4.md)."""
import asyncio, json
from korean_tax_calc_mcp.server import mcp


def c(tool, a):
    r = asyncio.run(mcp.call_tool(tool, a))
    return json.loads((r.content[0] if hasattr(r, "content") else r[0][0]).text)


def err(r):
    return "입력 확인 필요" in json.dumps(r, ensure_ascii=False)


# 1. vat_input_tax_deduction
def test_input_tax_misstated_amount_land_and_simplified_supplier():
    r = c("vat_input_tax_deduction", {"period": "2023-2", "filing": "예정", "items": [
        {"항목": "원재료", "증빙": "세금계산서", "공급가액": 110000000, "실제공급가액": 100000000, "성격": "일반"},
        {"항목": "접대용 물품", "증빙": "세금계산서", "공급가액": 10000000, "성격": "접대"},
        {"항목": "작업복", "증빙": "세금계산서", "공급가액": 20000000, "성격": "일반"},
        {"항목": "철거 목적 건물", "증빙": "세금계산서", "공급가액": 500000000, "성격": "토지관련"},
        {"항목": "건물 철거비", "증빙": "세금계산서", "공급가액": 30000000, "성격": "토지관련"},
        {"항목": "직원 선물", "증빙": "신용카드", "공급대가": 2200000, "성격": "일반", "공급자": "간이과세자_영수증"}]})
    assert r["결과"]["공제매입세액"] == 12000000
    by = {p["항목"]: p for p in r["계산"]["항목별"]}
    assert by["원재료"]["공제세액"] == 10000000 and by["직원 선물"]["공제세액"] == 0
    assert by["철거 목적 건물"]["불공제사유"]


def test_input_tax_late_invoice_within_return_deadline_and_card_vat():
    r = c("vat_input_tax_deduction", {"period": "2024-1", "filing": "확정", "items": [
        {"항목": "업무용승용차", "증빙": "세금계산서", "공급가액": 30000000, "성격": "비영업용승용차"},
        {"항목": "포장 용기", "증빙": "세금계산서", "공급가액": 700000, "성격": "일반", "공급시기": "2024-01-07", "발급일": "2024-06-05"},
        {"항목": "작업복", "증빙": "신용카드", "공급대가": 330000, "성격": "일반"},
        {"항목": "판촉 물품(거래처 제공)", "증빙": "세금계산서", "공급가액": 500000, "성격": "접대"},
        {"항목": "공장 임차료", "증빙": "세금계산서", "공급가액": 4000000, "성격": "일반"}]})
    assert r["결과"]["공제매입세액"] == 500000


def test_input_tax_land_installment_fuel_gift_and_cash_receipt():
    r = c("vat_input_tax_deduction", {"period": "2025-2", "filing": "확정", "items": [
        {"항목": "토지 형질변경", "증빙": "세금계산서", "공급가액": 10000000, "성격": "토지관련"},
        {"항목": "기계 장기할부", "증빙": "세금계산서", "공급가액": 20000000, "성격": "일반"},
        {"항목": "트럭 유류", "증빙": "신용카드", "공급대가": 660000, "성격": "일반"},
        {"항목": "승용차 유류", "증빙": "신용카드", "공급대가": 220000, "성격": "비영업용승용차"},
        {"항목": "거래처 증정품", "증빙": "신용카드", "공급대가": 1650000, "성격": "접대"},
        {"항목": "종업원 선물", "증빙": "현금영수증", "공급대가": 3300000, "성격": "일반"}]})
    assert r["결과"]["공제매입세액"] == 2360000


def test_input_tax_late_invoice_after_deadline():
    base = {"항목": "부품", "증빙": "세금계산서", "공급가액": 1000000, "성격": "일반", "공급시기": "2024-01-07"}
    r = c("vat_input_tax_deduction", {"period": "2024-1", "filing": "확정", "items": [{**base, "발급일": "2024-09-01"}]})
    assert r["결과"]["공제매입세액"] == 100000 and any("가산세" in p["결론"] for p in r["판단"])
    r = c("vat_input_tax_deduction", {"period": "2024-1", "filing": "확정", "items": [{**base, "발급일": "2025-09-01"}]})
    assert r["결과"]["공제매입세액"] == 0


def test_input_tax_rejects_unknown_nature_and_missing_amount():
    assert err(c("vat_input_tax_deduction", {"period": "2024-1", "filing": "확정", "items": [{"항목": "가", "증빙": "세금계산서", "공급가액": 1, "성격": "모름"}]}))
    assert err(c("vat_input_tax_deduction", {"period": "2024-1", "filing": "확정", "items": [{"항목": "가", "증빙": "세금계산서", "성격": "일반"}]}))


# 2. vat_deemed_supply_items
def test_deemed_supply_car_dealer():
    r = c("vat_deemed_supply_items", {"period": "2025-2", "items": [
        {"항목": "승용차X 판매", "거래": "판매", "매입세액공제": True, "금액": 25000000},
        {"항목": "승용차X 업무 전용", "거래": "비영업용승용차전용", "매입세액공제": True, "시가": 25000000},
        {"항목": "승용차Y 판매", "거래": "판매", "매입세액공제": False, "금액": 20000000},
        {"항목": "승용차Y 거래처 증여", "거래": "사업상증여", "매입세액공제": False, "시가": 20000000}]})
    assert r["결과"]["과세표준"] == 70000000
    by = {p["항목"]: p for p in r["계산"]["항목별"]}
    assert by["승용차Y 거래처 증여"]["과세표준"] == 0 and by["승용차Y 거래처 증여"]["제외사유"]


def test_deemed_supply_personal_gift_threshold():
    r = c("vat_deemed_supply_items", {"period": "2025-2", "items": [
        {"항목": "명절 선물 갑", "거래": "개인적공급", "매입세액공제": True, "시가": 100000, "1인당_연간금액": 100000},
        {"항목": "명절 선물 을", "거래": "개인적공급", "매입세액공제": True, "시가": 150000, "1인당_연간금액": 150000}]})
    assert r["결과"]["과세표준"] == 50000


def test_deemed_supply_depreciable_asset_on_closure():
    r = c("vat_deemed_supply_items", {"period": "2024-2", "items": [
        {"항목": "기계", "거래": "폐업시잔존", "매입세액공제": True, "감가상각": {"구분": "기타", "취득가액": 10000000, "취득일": "2023-03-10", "공급일": "2024-08-31"}}]})
    assert r["결과"]["과세표준"] == 2500000


def test_deemed_supply_sample_and_unknown_type():
    r = c("vat_deemed_supply_items", {"period": "2025-2", "items": [
        {"항목": "견본품", "거래": "사업상증여", "매입세액공제": True, "시가": 300000, "견본_광고선전물": True}]})
    assert r["결과"]["과세표준"] == 0
    assert err(c("vat_deemed_supply_items", {"period": "2025-2", "items": [{"항목": "가", "거래": "모름", "매입세액공제": True, "시가": 1}]}))
