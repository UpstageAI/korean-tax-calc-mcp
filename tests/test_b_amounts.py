"""금액 결함 회귀 테스트(실사용 점검) — 공급시기 세금계산서 매칭, 개인적공급 10만원 한도, 증여 합산 공제,
지방소득세 포함 조약, 원천징수 등 납부지연가산세."""

from korean_tax_calc_mcp.server import find_tool
from tests._helpers import call as c

M = 1_000_000


def times(r):
    return [(it["공급시기"], it["금액"]) for row in r["거래별"] for it in row["공급시기별"]]


# ── 부가가치세 공급시기: 공급시기 당일·이후 발급 세금계산서는 선발급이 아님(법 제15·17조, 영 제28조③3호) ──
TRUCK = {"이름": "푸드트럭", "종류": "중간지급조건부", "인도일": "2025-11-30", "대가": [
    {"약정일": "2025-05-01", "금액": 3 * M, "구분": "계약금"},
    {"약정일": "2025-08-01", "금액": 4 * M, "구분": "중도금"},
    {"약정일": "2025-11-30", "금액": 3 * M, "구분": "잔금"}]}


def test_supply_timing_late_invoice_not_prepaid():
    tx = dict(TRUCK, 세금계산서=[{"발급일": "2025-05-01", "금액": 3 * M, "수령일": "2025-05-01"},
                                {"발급일": "2025-10-20", "금액": 4 * M, "수령일": "2025-08-01"},
                                {"발급일": "2025-11-30", "금액": 3 * M, "수령일": "2025-11-30"}])
    r = c("vat_supply_timing", {"period": "2025-2기", "transactions": [tx]})
    assert times(r) == [("2025-05-01", 3 * M), ("2025-08-01", 4 * M), ("2025-11-30", 3 * M)]
    assert r["결과"]["거래_합계"] == 10 * M
    assert r["결과"]["조회기간_과세표준"] == 7 * M


def test_supply_timing_real_prepayment_still_moves():
    # 잔금(11.30.)을 10.20.에 받고 그 대가에 대해 발급 → 발급일이 공급시기(제17조①)
    tx = dict(TRUCK, 세금계산서=[{"발급일": "2025-05-01", "금액": 3 * M, "수령일": "2025-05-01"},
                                {"발급일": "2025-08-01", "금액": 4 * M, "수령일": "2025-08-01"},
                                {"발급일": "2025-10-20", "금액": 3 * M, "수령일": "2025-10-20"}])
    r = c("vat_supply_timing", {"transactions": [tx]})
    assert times(r) == [("2025-05-01", 3 * M), ("2025-08-01", 4 * M), ("2025-10-20", 3 * M)]
    assert r["결과"]["거래_합계"] == 10 * M


# ── 간주공급: 개인적공급 10만원은 사용인 경조사·명절·생일 등(영 제19조의2 3호)에만, 목별·1인당·연간 ──
def test_personal_use_asset_no_100k():
    r = c("vat_deemed_supply_items", {"period": "2025-2", "items": [
        {"항목": "공기청정기", "거래": "개인적공급", "매입세액공제": True,
         "감가상각": {"구분": "기타", "취득가액": 2_000_000, "취득일": "2025-02-10", "공급일": "2025-09-01"}}]})
    assert r["결과"]["과세표준"] == 1_500_000


def test_employee_gifts_per_head_per_category():
    r = c("vat_deemed_supply_items", {"period": "2025-2", "items": [
        {"항목": "추석 선물(6명)", "거래": "개인적공급", "매입세액공제": True, "시가": 900_000,
         "사용인_구분": "설날·추석", "인원": 6, "1인당_연간금액": 180_000},
        {"항목": "생일선물(6명)", "거래": "개인적공급", "매입세액공제": True, "시가": 300_000,
         "사용인_구분": "창립기념일·생일", "인원": 6, "1인당_연간금액": 50_000}]})
    by = {p["항목"]: p["과세표준"] for p in r["계산"]["항목별"]}
    assert by == {"추석 선물(6명)": 480_000, "생일선물(6명)": 0}
    assert r["결과"]["과세표준"] == 480_000


def test_employee_gift_one_person_uses_annual_amount():
    r = c("vat_deemed_supply_items", {"period": "2025-2", "items": [
        {"항목": "추석 선물", "거래": "개인적공급", "매입세액공제": True, "시가": 150_000,
         "사용인_구분": "추석", "1인당_연간금액": 180_000}]})
    assert r["결과"]["과세표준"] == 80_000


def test_employee_gift_group_total_without_headcount_is_rejected():
    r = c("vat_deemed_supply_items", {"period": "2025-2", "items": [
        {"항목": "추석 선물(6명)", "거래": "개인적공급", "매입세액공제": True, "시가": 900_000, "1인당_연간금액": 180_000}]})
    assert "error" in r


def test_employee_gift_category_split_by_period():
    items = [{"항목": "설날", "거래": "개인적공급", "매입세액공제": True, "시가": 60_000, "사용인_구분": "설날"},
             {"항목": "생일", "거래": "개인적공급", "매입세액공제": True, "시가": 60_000, "사용인_구분": "생일"}]
    # 2024.11.12. 개정(영 부칙 제2조: 시행일이 속하는 과세기간부터) 전 — 설날·추석·창립기념일·생일이 한 목
    assert c("vat_deemed_supply_items", {"period": "2024-1", "items": items})["결과"]["과세표준"] == 20_000
    # 개정 후 — 나목(설날·추석)·다목(창립기념일·생일) 따로
    assert c("vat_deemed_supply_items", {"period": "2025-1", "items": items})["결과"]["과세표준"] == 0


# ── 증여세: 합산하는 같은 증여자 사전증여에서 받은 공제는 다시 빼지 않음(상증법 제47조②·제53조) ──
GIFT = {"gift_date": "2025-11-20", "gift_value": 900 * M, "relation": "직계존속", "assumed_debt": 300 * M,
        "prior_gifts_same_donor": 100 * M, "prior_gift_tax_paid": 5 * M, "filed": True}


def test_gift_aggregated_prior_deduction_not_taken_twice():
    r = c("gift_tax", dict(GIFT, prior_deduction_same_donor=50 * M))
    res = r["결과"]
    assert (res["과세가액"], res["증여재산공제"], res["과세표준"], res["산출세액"], res["납부할세액"]) == \
        (700 * M, 50 * M, 650 * M, 135 * M, 126_100_000)


def test_gift_ambiguous_prior_deduction_rejected():
    r = c("gift_tax", dict(GIFT, prior_deduction_used=50 * M))
    assert "error" in r


def test_gift_split_never_taxed_more_than_at_once():
    once = c("gift_tax", {"gift_date": "2025-11-20", "gift_value": 1000 * M, "relation": "직계존속", "assumed_debt": 300 * M})
    split = c("gift_tax", dict(GIFT, prior_deduction_same_donor=50 * M))
    assert split["결과"]["산출세액"] <= once["결과"]["산출세액"]


def test_gift_no_prior_not_aggregated():
    r = c("gift_tax", {"gift_date": "2025-11-20", "gift_value": 50 * M, "relation": "직계존속"})
    assert r["판단"]["합산여부"] is False


# ── 비거주자 원천징수: 대상조세에 지방소득세(주민세)가 든 조약은 제한세율이 합계 상한(법인세법 제98조의7①2호) ──
def test_treaty_rate_includes_local_tax_japan():
    r = c("nonresident_withholding", {"income_kind": "사용료", "amount": 55 * M, "recipient_type": "법인",
                                      "residence_country": "일본", "treaty_rate": 0.1})
    res = r["결과"]
    assert (res["원천징수세액"], res["지방소득세"], res["합계"]) == (5 * M, 500_000, 5_500_000)
    assert "소득세법" not in r["근거"]


def test_treaty_rate_excludes_local_tax_us_and_override():
    r = c("nonresident_withholding", {"income_kind": "사용료", "amount": 55 * M, "recipient_type": "법인",
                                      "residence_country": "미국", "treaty_rate": 0.1})
    assert (r["결과"]["원천징수세액"], r["결과"]["지방소득세"]) == (5_500_000, 550_000)
    r = c("nonresident_withholding", {"income_kind": "사용료", "amount": 55 * M, "recipient_type": "법인",
                                      "residence_country": "일본", "treaty_rate": 0.1, "treaty_includes_local_tax": False})
    assert (r["결과"]["원천징수세액"], r["결과"]["지방소득세"]) == (5_500_000, 550_000)


# ── 원천징수 등 납부지연가산세(국세기본법 제47조의5①): 3% + 일수분, 고지 전 10% 한도 ──
def test_withholding_late_payment_tool():
    names = [x["도구"] for x in find_tool("원천징수 납부지연가산세")["결과"]["후보"]]
    assert names[0] == "withholding_late_payment_penalty"
    r = c("withholding_late_payment_penalty", {"unpaid_tax": 5 * M, "due": "2025-07-10", "until": "2026-06-30"})
    assert r["결과"]["가산세"] == 500_000
    r = c("withholding_late_payment_penalty", {"unpaid_tax": 5 * M, "due": "2025-07-10", "until": "2025-08-09"})
    assert r["결과"]["가산세"] == 150_000 + 33_000   # 3% + 5,000,000 × 30일 × 22/100,000
