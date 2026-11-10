"""vat_simplified_taxpayer 도구 테스트 — SPEC c4b 가상 수치. 작성 Mia(윤승미)"""

from korean_tax_calc_mcp.server import vat_simplified_taxpayer


def _result(r):
    """도구 응답은 {"결과": {...}, "근거": ...} 구조 — 결과 부분만 추출"""
    return r["결과"]


def test_simplified_with_penalty():
    """가상 수치: supply 60,000,000, mileage 0, value_added_rate 0.2, invoice 10,000,000,
    card 20,000,000, no_invoice 1,000,000, year 2026
    → 납부세액 1,200,000, 공제 50,000+260,000=310,000, 가산세 5,000, 차가감 895,000"""
    r = vat_simplified_taxpayer(
        supply_incl_vat=60_000_000,
        value_added_rate=0.2,
        invoice_purchase_incl_vat=10_000_000,
        mileage_supply_incl_vat=0,
        card_cash_receipt_supply_incl_vat=20_000_000,
        no_invoice_purchase_incl_vat=1_000_000,
        year=2026,
    )
    res = _result(r)
    assert res["과세표준"] == 60_000_000
    assert res["납부세액"] == 1_200_000
    assert res["매입세금계산서등_공제"] == 50_000
    assert res["카드발행세액공제"] == 260_000
    assert res["공제_합계"] == 310_000
    assert res["가산세"] == 5_000
    assert res["차가감_납부세액"] == 895_000


def test_simplified_credits_exceed_tax_due():
    """공제가 납부세액을 넘는 경우: 가산세만 남는지 확인
    supply 10,000,000, value_added_rate 0.15 → 납부세액 150,000
    invoice 10,000,000 → 매입공제 50,000
    card 30,000,000 → 카드공제 min(390,000, 10,000,000) = 390,000
    총공제 = min(50,000+390,000, 150,000) = 150,000
    가산세 = 5,000 (no_invoice 1,000,000 × 0.5%)
    차가감 = max(0, 150,000-150,000) + 5,000 = 5,000"""
    r = vat_simplified_taxpayer(
        supply_incl_vat=10_000_000,
        value_added_rate=0.15,
        invoice_purchase_incl_vat=10_000_000,
        card_cash_receipt_supply_incl_vat=30_000_000,
        no_invoice_purchase_incl_vat=1_000_000,
        year=2026,
    )
    res = _result(r)
    assert res["납부세액"] == 150_000
    assert res["공제_합계"] == 150_000  # 납부세액 한도로 제한
    assert res["가산세"] == 5_000
    assert res["차가감_납부세액"] == 5_000  # 공제 후 0 + 가산세


def test_simplified_exempt_threshold_text():
    """면제 판정 문구: '해당 과세기간 공급대가' 표기 확인 (제69조는 과세기간 기준)"""
    r = vat_simplified_taxpayer(
        supply_incl_vat=30_000_000,
        value_added_rate=0.15,
        year=2026,
    )
    res = _result(r)
    steps = res["단계별_계산"]
    exempt_step = [s for s in steps if "납부의무 면제" in s["항목"]][0]
    assert "해당 과세기간 공급대가" in exempt_step["항목"]
    assert "직전 연도" not in exempt_step["항목"]
    assert res["납부의무_면제"] is True  # 30,000,000 < 48,000,000


def test_simplified_prepaid_tax_deducted():
    """제67조②: 예정부과·예정신고 납부·수시부과 세액은 확정신고 때 공제.
    가상 수치: 위 케이스(차가감 895,000) + prepaid_tax 300,000 → 차가감 595,000, 환급 0"""
    r = vat_simplified_taxpayer(
        supply_incl_vat=60_000_000, value_added_rate=0.2, invoice_purchase_incl_vat=10_000_000,
        card_cash_receipt_supply_incl_vat=20_000_000, no_invoice_purchase_incl_vat=1_000_000,
        prepaid_tax=300_000, year=2026,
    )
    res = _result(r)
    assert res["예정부과세액_공제"] == 300_000
    assert res["차가감_납부세액"] == 595_000
    assert res["환급세액"] == 0
    assert "제67조" in r["근거"]


def test_simplified_prepaid_tax_exceeds_gives_refund():
    """예정부과세액이 납부할 세액보다 크면 차가감은 음수, 환급세액 = 초과분. 895,000 − 1,000,000 = −105,000"""
    r = vat_simplified_taxpayer(
        supply_incl_vat=60_000_000, value_added_rate=0.2, invoice_purchase_incl_vat=10_000_000,
        card_cash_receipt_supply_incl_vat=20_000_000, no_invoice_purchase_incl_vat=1_000_000,
        prepaid_tax=1_000_000, year=2026,
    )
    res = _result(r)
    assert res["차가감_납부세액"] == -105_000
    assert res["환급세액"] == 105_000


def test_simplified_exempt_with_prepaid_refunds():
    """제69조④: 납부의무 면제 사업자가 자진 납부한 금액은 환급. 공급대가 30,000,000(면제) + prepaid 200,000 → 환급 200,000"""
    r = vat_simplified_taxpayer(supply_incl_vat=30_000_000, value_added_rate=0.2, prepaid_tax=200_000, year=2026)
    res = _result(r)
    assert res["납부의무_면제"] is True
    assert res["차가감_납부세액"] == -200_000
    assert res["환급세액"] == 200_000


def test_simplified_prepaid_default_zero_unchanged():
    r = vat_simplified_taxpayer(supply_incl_vat=60_000_000, value_added_rate=0.2, year=2026)
    res = _result(r)
    assert res["예정부과세액_공제"] == 0
    assert res["환급세액"] == 0
    assert res["차가감_납부세액"] == 1_200_000
