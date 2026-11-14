"""비거주자·외국법인 양도소득 원천징수, 비거주자 상속세·증여세 — 원문에서 손으로 계산한 정답.

대조한 시행본(법제처 DRF, 2026-11-14 조회):
- 소득세법 2016.9.1.(법률 제13796호)·2018.9.21.(제15522호)·2019.1.1.(제16104호)·2026.7.1.(제21221호) 시행본 제156조제1항
  (2018년까지 제4호 부동산등·제5호 유가증권, 2019년부터 제5호·제7호 — 지급금액 10%, 취득가액·양도비용 확인 시 양도차익 20%와 중 적은 금액)
- 법인세법 2016.1.25.·2018.11.1.·2019.1.1.(제16096호)·2026.7.1. 시행본 제98조제1항(같은 구조), 제97조제1항
- 소득세법 시행령 제179조제11항제1호 단서·법인세법 시행령 제132조제8항제2호 단서(2016·2026 시행본) — 증권시장 양도·계속 25% 미만
- 상속세 및 증여세법 2016.9.1.~2026.1.2. 연말 시행본 제3조·제4조의2·제13조·제14조·제18조~제23조의2·제53조·제53조의2·제67조·제68조·제69조
"""
from korean_tax_calc_mcp import server as S
from korean_tax_calc_mcp.engine import calc_inhgift as IG

W = S.nonresident_capital_gains_withholding
H = S.nonresident_inheritance_gift


# ── 양도소득 원천징수 ─────────────────────────────────────────────
def test_real_estate_gain_side_2025():
    # 10억 × 10% = 1억, (10억 − 7억 − 1천만) × 20% = 5,800만 → 5,800만, 지방 580만
    r = W("개인", "부동산등", 2025, 1_000_000_000, acquisition_cost=700_000_000, transfer_expenses=10_000_000)
    assert r["결과"]["원천징수세액"] == 58_000_000
    assert r["결과"]["지방소득세"] == 5_800_000
    assert r["결과"]["적용"] == "양도차익 × 20%"
    assert "소득세법 제156조제1항제5호" in r["근거"]


def test_min_boundary_pair():
    # 양도차익 5억이면 20% = 1억 = 10% — 같음. 5억 − 1원이면 20% 쪽 99,999,999.8 → 원 미만 버림 99,999,999
    eq = W("개인", "부동산등", 2024, 1_000_000_000, acquisition_cost=500_000_000)
    assert eq["결과"]["원천징수세액"] == 100_000_000
    lt = W("개인", "부동산등", 2024, 1_000_000_000, acquisition_cost=500_000_001)
    assert lt["결과"]["원천징수세액"] == 99_999_999
    assert lt["결과"]["적용"] == "양도차익 × 20%"
    assert lt["결과"]["지방소득세"] == 9_999_999
    gt = W("개인", "부동산등", 2024, 1_000_000_000, acquisition_cost=499_999_999)
    assert gt["결과"]["원천징수세액"] == 100_000_000
    assert gt["결과"]["적용"] == "지급금액 × 10%"


def test_no_cost_confirmed_ten_percent():
    r = W("법인", "주식", 2026, 333_333_337)
    assert r["결과"]["원천징수세액"] == 33_333_333      # 33,333,333.7 → 버림
    assert r["결과"]["지방소득세"] == 3_333_333
    assert "법인세법 제98조제1항제7호" in r["근거"]


def test_loss_gives_zero():
    r = W("개인", "주식", 2023, 100_000_000, acquisition_cost=150_000_000)
    assert r["결과"]["원천징수세액"] == 0


def test_ho_numbering_2018_vs_2019():
    assert "소득세법 제156조제1항제4호" in W("개인", "부동산등", 2018, 10_000_000)["근거"]
    assert "소득세법 제156조제1항제5호" in W("개인", "부동산등", 2019, 10_000_000)["근거"]
    assert "소득세법 제156조제1항제5호" in W("개인", "주식", 2018, 10_000_000)["근거"]
    assert "소득세법 제156조제1항제7호" in W("개인", "주식", 2019, 10_000_000)["근거"]
    assert "법인세법 제98조제1항제4호" in W("법인", "부동산등", 2016, 10_000_000)["근거"]
    assert "법인세법 제98조제1항제5호" in W("법인", "부동산등", 2019, 10_000_000)["근거"]
    # 세율은 같음
    assert W("개인", "부동산등", 2018, 10_000_000)["결과"]["원천징수세액"] == W("개인", "부동산등", 2019, 10_000_000)["결과"]["원천징수세액"] == 1_000_000


def test_listed_small_holder_boundary():
    below = W("개인", "주식", 2025, 500_000_000, listed_via_exchange=True, max_ownership_ratio=0.2499)
    assert below["결과"]["원천징수세액"] == 0
    at = W("개인", "주식", 2025, 500_000_000, listed_via_exchange=True, max_ownership_ratio=0.25)
    assert at["결과"]["원천징수세액"] == 50_000_000


def test_listed_small_holder_foreign_corp_pe():
    no_pe = W("법인", "주식", 2025, 500_000_000, listed_via_exchange=True, max_ownership_ratio=0.1)
    assert no_pe["결과"]["원천징수세액"] == 0
    pe = W("법인", "주식", 2025, 500_000_000, listed_via_exchange=True, max_ownership_ratio=0.1, has_domestic_pe=True)
    assert pe["결과"]["원천징수세액"] == 50_000_000
    assert any(x["항목"] == "상장주식 소액주주" for x in pe["판단"])


def test_exclusions():
    assert W("개인", "부동산등", 2025, 1_000_000_000, payer_is_individual=True)["결과"]["원천징수세액"] == 0
    assert W("법인", "부동산등", 2025, 1_000_000_000, attributable_to_pe=True)["결과"]["원천징수세액"] == 0
    t = W("개인", "주식", 2025, 1_000_000_000, treaty_exempt=True, residence_country="US")
    assert t["결과"]["원천징수세액"] == 0
    assert "소득세법 제156조의2" in t["판단"][0]["근거"]


def test_normal_price():
    # 정상가격 2억이 지급금액 — 2억 × 10% = 2천만, (2억 − 1.5억) × 20% = 1천만 → 1천만
    r = W("법인", "주식", 2025, 100_000_000, acquisition_cost=150_000_000, normal_price=200_000_000)
    assert r["결과"]["원천징수세액"] == 10_000_000


def test_input_errors():
    assert "error" in W("개인", "부동산등", 2025, 1, transfer_expenses=1)
    assert "error" in W("개인", "부동산등", 2025, 100, normal_price=200)
    assert "error" in W("개인", "주식", 2025, 100, payer_is_individual=True)
    assert "error" in W("개인", "주식", 2025, 100, listed_via_exchange=True)
    assert "error" in W("개인", "주식", 2025, 100, normal_price=50)


# ── 비거주자 상속세 ───────────────────────────────────────────────
def test_inheritance_nonresident_basic_only():
    # 국내 재산 10억 − 담보채무 1억 = 과세가액 9억, 기초공제 2억 → 과세표준 7억
    # 산출 1억×10% + 4억×20% + 2억×30% = 1.5억, 신고세액공제 3% 450만 → 1억4,550만
    r = H("상속", "2025-03-10", 1_000_000_000, debts=100_000_000)
    assert r["결과"]["과세가액"] == 900_000_000
    assert r["결과"]["상속공제_합계"] == 200_000_000
    assert r["결과"]["산출세액"] == 150_000_000
    assert r["결과"]["납부할세액"] == 145_500_000
    assert r["계산"]["장례비용"] == 0 and r["계산"]["일괄공제_적용"] is False
    assert r["결과"]["신고기한"] == "2025-12-31"          # 3월 말일부터 9개월
    assert H("상속", "2025-03-10", 1_000_000_000, debts=100_000_000, foreign_address=False)["결과"]["신고기한"] == "2025-09-30"


def test_inheritance_resident_unchanged():
    # 같은 재산을 거주자로 보면 일괄공제 5억·장례비용 최소 500만 — 기존 결과 그대로
    res = IG.inheritance_tax(year=2025, estate_value=1_000_000_000, debts=100_000_000)
    assert res["계산"]["장례비용"] == 5_000_000
    assert res["결과"]["상속공제_합계"] == 500_000_000
    assert res == IG.inheritance_tax(year=2025, estate_value=1_000_000_000, debts=100_000_000, resident=True)


def test_inheritance_2016_rate():
    # 2016: 신고세액공제 10%(제69조①, 2016.9.1. 시행본). 5억 − 2억 = 3억 → 1천만 + 4천만 = 5천만, 공제 500만
    r = H("상속", "2016-06-01", 500_000_000)
    assert r["결과"]["산출세액"] == 50_000_000
    assert r["결과"]["신고세액공제"] == 5_000_000


def test_inheritance_rejects_resident_only_inputs():
    r = IG.inheritance_tax(year=2025, estate_value=1, funeral_cost=10_000_000, resident=False)
    assert "error" in r
    r = IG.inheritance_tax(year=2025, estate_value=1, children=2, resident=False)
    assert "error" in r
    assert "error" in H("상속", "2025-01-01", 1, assumed_debt=1)


# ── 비거주자 증여세 ───────────────────────────────────────────────
def test_gift_no_deduction_2025():
    # 직계존속 1억 — 증여재산공제 없음: 과세표준 1억 → 1천만, 신고세액공제 3% 30만 → 970만
    r = H("증여", "2025-03-10", 100_000_000, relation="직계존속")
    assert r["결과"]["증여재산공제"] == 0
    assert r["결과"]["산출세액"] == 10_000_000
    assert r["결과"]["납부할세액"] == 9_700_000
    assert r["결과"]["신고기한"] == "2025-06-30"
    assert "제6항제3호" in r["판단"]["연대납부"]["근거"]
    # 거주자는 5천만 공제 → 과세표준 5천만, 산출 500만
    res = IG.gift_tax(gift_date="2025-03-10", gift_value=100_000_000, relation="직계존속")
    assert res["결과"]["증여재산공제"] == 50_000_000 and res["결과"]["산출세액"] == 5_000_000


def test_gift_joint_liability_paragraph_2018_vs_2019():
    r18 = H("증여", "2018-05-20", 100_000_000, filed=False)
    r19 = H("증여", "2019-05-20", 100_000_000, filed=False)
    assert "제5항제3호" in r18["판단"]["연대납부"]["근거"]
    assert "제6항제3호" in r19["판단"]["연대납부"]["근거"]
    assert r18["결과"]["납부할세액"] == r19["결과"]["납부할세액"] == 10_000_000


def test_gift_2016_scope_note():
    r = H("증여", "2016-07-01", 100_000_000)
    assert "국외 예금" in r["판단"]["과세대상"]["결론"]
    assert r["결과"]["신고세액공제"] == 1_000_000       # 2016 10%


def test_gift_marriage_birth_rejected():
    r = IG.gift_tax(gift_date="2025-03-10", gift_value=100_000_000, relation="직계존속", marriage_birth=True, recipient_resident=False)
    assert "error" in r
