"""간이과세자 부가가치세 신고 끝에서 끝까지 계산기 정답 테스트 (Claude 작성 2026-10-13) — 수정 금지.
공개 검증 사례는 부가가치세법 제46조①·제63조·제68조의2②·제69조, 영 제61조②·제111조②로
손계산해 공개 정답과 일치 확인(495,000 / 366,000 / 310,000). 실무형 사례는 Claude 손계산.
"""
import asyncio, json
from korean_tax_calc_mcp.server import mcp
from tests._legacy_to_ledger import to_ledger   # 0.9.0: 옛 입력은 테스트에서 원장형으로 변환해 호출


def c(n, a):
    return json.loads(asyncio.run(mcp.call_tool(n, to_ledger(n, a))).content[0].text)


def test_public_case_public_case_80():
    r = c("simplified_vat_return", {"year": 2023, "business_type": "음식점업",
                                    "supplies": {"total": 70_000_000, "card_receipt_issued": 30_000_000},
                                    "purchases": {"tax_invoice_received": 33_000_000, "exempt_farm_products": 4_360_000},
                                    "prior_year_supplies": 60_000_000, "prepaid_assessed": 0})
    k = r["계산"]
    assert k["과세표준"] == 70_000_000 and k["납부세액"] == 1_050_000
    assert k["세금계산서등수취세액공제"] == 165_000 and k["신용카드매출전표등발급세액공제"] == 390_000
    assert k["의제매입세액공제"] == 0                                   # 2021-07-01부터 간이과세자 적용 없음
    assert r["결과"]["차가감납부세액"] == 495_000 and r["결과"]["납부의무면제"] is False


def test_public_case_public_case_76():  # 자기적립마일리지 제외, 세금계산서 미수취 가산세 0.5%
    r = c("simplified_vat_return", {"year": 2025, "business_type": "음식점업",
                                    "supplies": {"total": 99_500_000, "card_receipt_issued": 80_000_000, "self_mileage": 1_000_000},
                                    "purchases": {"tax_invoice_received": 16_500_000, "invoice_received": 29_000_000,
                                                  "no_tax_invoice_from_issuer": 2_200_000},
                                    "prior_year_supplies": 75_000_000, "prepaid_assessed": 0})
    k = r["계산"]
    assert k["과세표준"] == 98_500_000 and k["납부세액"] == 1_477_500
    assert k["세금계산서등수취세액공제"] == 82_500 and k["신용카드매출전표등발급세액공제"] == 1_040_000
    assert k["세금계산서미수취가산세"] == 11_000
    assert r["결과"]["차가감납부세액"] == 366_000


def test_public_case_public_case_78():  # 대손은 간이과세자 납부세액에 영향 없음
    r = c("simplified_vat_return", {"year": 2026, "business_type": "음식점업",
                                    "supplies": {"total": 75_000_000, "card_receipt_issued": 50_000_000},
                                    "purchases": {"tax_invoice_received": 33_000_000, "exempt_farm_products": 4_360_000},
                                    "bad_debt_confirmed": 2_200_000, "prior_year_supplies": 70_000_000, "prepaid_assessed": 0})
    assert r["결과"]["차가감납부세액"] == 310_000
    assert "대손" in json.dumps(r["판단"], ensure_ascii=False)       # 적용 없음을 판단에 명시


def test_exemption_under_threshold():  # 공급대가 4,800만 원 미만 → 납부의무 면제, 공제도 없음
    r = c("simplified_vat_return", {"year": 2025, "business_type": "소매업",
                                    "supplies": {"total": 40_000_000, "card_receipt_issued": 10_000_000},
                                    "purchases": {"tax_invoice_received": 11_000_000}, "prior_year_supplies": 30_000_000, "prepaid_assessed": 0})
    assert r["결과"]["납부의무면제"] is True and r["결과"]["차가감납부세액"] == 0
    r20 = c("simplified_vat_return", {"year": 2020, "business_type": "소매업", "supplies": {"total": 40_000_000}, "purchases": {}, "prior_year_supplies": 30_000_000, "prepaid_assessed": 0})
    assert "error" in r20 or r20["결과"]["납부의무면제"] is False    # 2020은 기준 3천만 원·부가가치율 표가 달라 계산하지 않거나 면제 아님


def test_credits_cannot_exceed_tax():  # 공제 합계 > 납부세액 → 0 (제63조⑥), 환급 없음
    r = c("simplified_vat_return", {"year": 2025, "business_type": "소매업",
                                    "supplies": {"total": 60_000_000, "card_receipt_issued": 60_000_000},
                                    "purchases": {"tax_invoice_received": 55_000_000}, "prior_year_supplies": 50_000_000, "prepaid_assessed": 0})
    assert r["계산"]["납부세액"] == 900_000 and r["결과"]["차가감납부세액"] == 0


def test_penalty_waived_in_receipt_period():  # 직전연도 공급대가 4,800만 원 미만 → 영수증 발급 기간 → 미수취 가산세 없음
    r = c("simplified_vat_return", {"year": 2025, "business_type": "음식점업",
                                    "supplies": {"total": 60_000_000}, "purchases": {"no_tax_invoice_from_issuer": 2_200_000},
                                    "prior_year_supplies": 40_000_000, "prepaid_assessed": 0})
    assert r["계산"]["세금계산서미수취가산세"] == 0


def test_prepaid_deducted_and_unknown_type_rejected():
    r = c("simplified_vat_return", {"year": 2025, "business_type": "숙박업", "supplies": {"total": 80_000_000}, "purchases": {},
                                    "prior_year_supplies": 70_000_000, "prepaid_assessed": 500_000})
    assert r["계산"]["납부세액"] == 2_000_000 and r["결과"]["차가감납부세액"] == 1_500_000
    r = c("simplified_vat_return", {"year": 2025, "business_type": "카페", "supplies": {"total": 80_000_000}, "purchases": {}, "prior_year_supplies": 0, "prepaid_assessed": 0})
    assert "error" in r and "허용값" in r


def test_card_credit_rate_2021_2022():  # CodeSolar(PR #11) 지적 후 Claude 확인(10-13): 2021-07~2022도 1.3%·1천만 원(제46조①3호 2021·2022 시행본)
    r = c("simplified_vat_return", {"year": 2022, "business_type": "음식점업", "supplies": {"total": 60_000_000, "card_receipt_issued": 10_000_000},
                                    "purchases": {}, "prior_year_supplies": 50_000_000, "prepaid_assessed": 0})
    assert r["계산"]["신용카드매출전표등발급세액공제"] == 130_000 and r["계산"]["납부세액"] == 900_000


def test_penalty_survives_exemption():  # CodeSolar(PR #11 2차) 후 Claude 확인: 납부의무 면제(제69조①)여도 미수취 가산세(제68조의2②)는 별도 — 제69조②는 미등록 가산세만 배제
    r = c("simplified_vat_return", {"year": 2025, "business_type": "소매업", "supplies": {"total": 40_000_000},
                                    "purchases": {"no_tax_invoice_from_issuer": 2_200_000}, "prior_year_supplies": 50_000_000, "prepaid_assessed": 0})
    assert r["결과"]["납부의무면제"] is True and r["계산"]["납부세액"] == 0
    assert r["계산"]["세금계산서미수취가산세"] == 11_000 and r["결과"]["차가감납부세액"] == 11_000
