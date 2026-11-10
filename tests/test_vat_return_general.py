"""일반과세자 부가가치세 확정신고 집계 도구 vat_return_general — 정답 테스트(수정 금지, Claude 작성).

부품 도구(vat_input_tax_deduction·common_input_tax·vat_bad_debt_credit·vat_card_sales_credit·invoice_penalty_bundle·
late_payment_penalty)의 결과를 받아 별지 제21호서식(일반과세자 부가가치세 신고서) 순서로 합산해 차가감 납부(환급)세액을 낸다.
새 세법 판정은 하지 않는다. 금액은 원 단위, 원 미만 절사(국고금 관리법 제47조).
근거: 부가가치세법 제37조·제38조·제39조·제45조·제46조·제48조·제49조·제60조, 조세특례제한법 제104조의8②(전자신고세액공제 —
납부세액에서 공제하거나 환급세액에 가산, 매출·매입 모두 없는 일반과세자는 제외), 같은 법 시행령 제104조의5③(확정신고·제67조 신고만)·④
(2026.2.27부터 5천원, 2010.2.18~2026.2.26은 1만원).
공개 검증 사례: 2026-11-10 통합 시나리오(가상 법인 (주)라마바 2026년 1기 확정) 손계산.
"""
from _helpers import call as c
from korean_tax_calc_mcp.engine import calc_vat as V

M = 1_000_000

# ── G1 (주)라마바 2026-1기 확정 — 부품 도구 결과를 그대로 넣음 ─────────────────────────────────
G1 = {"year": 2026, "period": "1", "kind": "확정",
      "sales_invoice": 800 * M, "sales_card_cash": 50 * M, "sales_zero_invoice": 100 * M, "deemed_supply": 3 * M,
      "bad_debt_credit": 1 * M,
      "purchase_invoice": 420 * M, "purchase_card_cash": 20 * M,
      "nondeductible": 5_500_000, "common_nondeductible": 100_000,
      "card_sales_credit": 0, "e_filing": True,
      "prepaid_assessed": 20 * M,
      "penalties": [{"kind": "지연수취", "amount": 50_000, "basis": "부가가치세법 제60조⑦"}]}


def test_g1_full_return_matches_hand_calc():
    r = c("vat_return_general", G1)
    assert "error" not in r, r
    g = r["결과"]
    assert g["과세표준"] == 853 * M                      # (1) 800M + (3) 50M + (4) 기타(간주공급) 3M
    assert g["영세율_과세표준"] == 100 * M
    assert g["매출세액"] == 85_300_000
    assert g["대손세액_가감"] == -1 * M                   # (8) 공제분은 음수
    assert g["매출세액_합계"] == 84_300_000
    assert g["매입세액"] == 44 * M                        # (420M + 20M) × 10%
    assert g["공제받지못할_매입세액"] == 5_600_000         # (16) 5,500,000 + 공통 100,000
    assert g["매입세액_차감계"] == 38_400_000
    assert g["납부환급세액"] == 45_900_000
    assert g["경감공제세액"] == 5_000                     # 전자신고 5천원(영 제104조의5④, 2026.2.27~)
    assert g["예정고지세액"] == 20 * M
    assert g["가산세액계"] == 50_000
    assert g["차가감_납부세액"] == 25_945_000
    assert g["납부세액"] == 25_945_000 and g["환급세액"] == 0
    assert "제104조의8" in r["근거"] and "제47조" in r["근거"]
    assert isinstance(r["단계별_계산"], list) and len(r["단계별_계산"]) >= 6
    assert all(isinstance(v, int) for v in g.values())
    # 서식 칸 — 부가가치세법 시행규칙 별지 제21호서식 <개정 2026. 3. 20.> 제1쪽 ① 신고내용 원문 이름(법령정보 서식 PDF 대조)
    f = r["서식"]
    assert f["(1) 세금계산서 발급분"] == {"금액": 800 * M, "세액": 80 * M}
    assert f["(3) 신용카드ㆍ현금영수증 발행분"] == {"금액": 50 * M, "세액": 5 * M}
    assert f["(4) 기타(정규영수증 외 매출분)"] == {"금액": 3 * M, "세액": 300_000}
    assert f["(5) 영세율 세금계산서 발급분"] == {"금액": 100 * M, "세액": 0}
    assert f["(8) 대손세액 가감"] == -1 * M
    assert f["(9) 합계"] == 84_300_000
    assert f["(10) 일반매입"] == {"금액": 420 * M, "세액": 42 * M}
    assert f["(15) 그 밖의 공제매입세액"] == 2 * M
    assert f["(16) 합계"] == 44 * M and f["(17) 공제받지 못할 매입세액"] == 5_600_000 and f["(18) 차감계"] == 38_400_000
    assert f["납부(환급)세액"] == 45_900_000
    assert f["(19) 그 밖의 경감ㆍ공제세액"] == 5_000 and f["(20) 신용카드매출전표등 발행공제 등"] == 0 and f["(21) 합계"] == 5_000
    assert f["(24) 예정고지세액"] == 20 * M and f["(29) 가산세액 계"] == 50_000
    assert f["(30) 차감ㆍ가감하여 납부할 세액(환급받을 세액)"] == 25_945_000


def test_g1b_with_late_payment_penalty_added():
    args = {**G1, "penalties": G1["penalties"] + [{"kind": "납부지연", "amount": 56_969, "basis": "국세기본법 제47조의4"}]}
    g = c("vat_return_general", args)["결과"]
    assert g["가산세액계"] == 106_969 and g["차가감_납부세액"] == 26_001_969


def test_g1_engine_function_pure():
    """엔진 함수는 서버 없이 같은 값."""
    g = V.vat_return_general({**G1, "e_filing_credit": 5_000})["결과"]
    assert g["차가감_납부세액"] == 25_945_000


# ── G2 환급: 설비투자 과세기간 ─────────────────────────────────────────────────────────────
def test_g2_refund_period_e_filing_added_to_refund():
    r = c("vat_return_general", {"year": 2026, "period": "1", "sales_invoice": 100 * M,
                                 "purchase_invoice_fixed": 500 * M, "e_filing": True})
    g = r["결과"]
    assert g["납부환급세액"] == -40 * M
    assert g["경감공제세액"] == 5_000
    assert g["차가감_납부세액"] == -40_005_000               # 제104조의8②: 환급세액에 가산
    assert g["납부세액"] == 0 and g["환급세액"] == 40_005_000
    assert g["가산세액계"] == 0


# ── G3 예정신고 ──────────────────────────────────────────────────────────────────────────
def test_g3_prelim_return_rejects_prepaid_inputs():
    r = c("vat_return_general", {"year": 2026, "period": "1", "kind": "예정", "sales_invoice": 100 * M,
                                 "prepaid_assessed": 20 * M})
    assert "error" in r and "예정" in r["error"]


def test_g3_prelim_return_no_e_filing_credit():
    """영 제104조의5③: 전자신고세액공제는 확정신고(법 제49조)·제67조 신고만."""
    g = c("vat_return_general", {"year": 2026, "period": "1", "kind": "예정", "sales_invoice": 100 * M, "e_filing": True})["결과"]
    assert g["경감공제세액"] == 0 and g["차가감_납부세액"] == 10 * M


# ── G4 전자신고세액공제 연도표 ───────────────────────────────────────────────────────────────
def test_g4_e_filing_credit_10000_before_20260227():
    g = c("vat_return_general", {"year": 2025, "period": "2", "sales_invoice": 100 * M, "e_filing": True,
                                 "filed_on": "2026-01-25"})["결과"]
    assert g["경감공제세액"] == 10_000 and g["차가감_납부세액"] == 9_990_000


def test_g4_e_filing_credit_default_filed_on_is_statutory_due():
    """filed_on 생략 → 확정신고 기한(1기 7.25, 2기 다음 해 1.25) 기준. 2025-2기 → 2026-01-25 → 1만원, 2026-1기 → 2026-07-25 → 5천원."""
    assert c("vat_return_general", {"year": 2025, "period": "2", "sales_invoice": 100 * M, "e_filing": True})["결과"]["경감공제세액"] == 10_000
    assert c("vat_return_general", {"year": 2026, "period": "1", "sales_invoice": 100 * M, "e_filing": True})["결과"]["경감공제세액"] == 5_000


def test_g4_e_filing_credit_not_for_zero_sales_and_purchases():
    """제104조의8② 단서: 매출가액과 매입가액이 없는 일반과세자는 공제 없음."""
    r = c("vat_return_general", {"year": 2026, "period": "1", "e_filing": True})
    assert r["결과"]["경감공제세액"] == 0 and r["결과"]["차가감_납부세액"] == 0
    assert any("제104조의8" in s for s in r["주의"])


# ── G5 원장형 입력 ───────────────────────────────────────────────────────────────────────
LEDGER_G1 = {"공급": [{"항목": "세금계산서 발급분", "금액": 800 * M}, {"항목": "신용카드·현금영수증 발행분", "금액": 50 * M},
                    {"항목": "영세율 세금계산서 발급분", "금액": 100 * M}, {"항목": "간주공급", "금액": 3 * M}],
             "매입": [{"항목": "세금계산서 수취분 일반매입", "금액": 420 * M}, {"항목": "신용카드·현금영수증 수취분", "금액": 20 * M}],
             "세액": [{"항목": "대손세액", "금액": 1 * M}, {"항목": "공제받지 못할 매입세액", "금액": 5_500_000},
                    {"항목": "공통매입세액 면세사업분", "금액": 100_000}]}


def test_g5_ledger_equals_g1():
    r = c("vat_return_general", {"year": 2026, "period": "1", "e_filing": True, "prepaid_assessed": 20 * M,
                                 "penalties": G1["penalties"], "ledger": LEDGER_G1})
    assert "error" not in r, r
    assert r["결과"] == c("vat_return_general", G1)["결과"]
    assert r["원장대조"]["판정"] == "일치"


def test_g5_ledger_unknown_item_refused():
    bad = {**LEDGER_G1, "공급": LEDGER_G1["공급"] + [{"항목": "수수료 수입", "금액": 1 * M}]}
    r = c("vat_return_general", {"year": 2026, "period": "1", "ledger": bad})
    assert "error" in r and "수수료 수입" in "".join(r.get("문제", [])) + r["error"]
    assert "허용값" in r


def test_g5_ledger_and_scalar_duplicate_refused():
    r = c("vat_return_general", {"year": 2026, "period": "1", "sales_invoice": 1 * M, "ledger": LEDGER_G1})
    assert "error" in r and "sales_invoice" in r["error"]


# ── 입력 오류 ───────────────────────────────────────────────────────────────────────────
def test_negative_amount_refused_except_bad_debt_recovery():
    assert "error" in c("vat_return_general", {"year": 2026, "period": "1", "sales_invoice": -1})
    g = c("vat_return_general", {"year": 2026, "period": "1", "sales_invoice": 100 * M, "bad_debt_credit": -300_000})["결과"]
    assert g["대손세액_가감"] == 300_000 and g["매출세액_합계"] == 10_300_000   # 회수분은 가산


def test_penalty_items_need_kind_and_amount():
    r = c("vat_return_general", {"year": 2026, "period": "1", "sales_invoice": 100 * M, "penalties": [{"amount": 10}]})
    assert "error" in r


def test_find_tool_surfaces_new_tool():
    r = c("find_tool", {"query": "부가가치세 신고서 집계 차가감 납부세액", "n": 3})
    names = [x["도구"] for x in r["결과"]["후보"]]
    assert "vat_return_general" in names, names
