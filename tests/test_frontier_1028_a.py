"""기타소득 연도별 규칙 회귀 — 값은 해당 연도 시행본 조문으로 손계산 (Claude 2026-10-28).

- 소득세법 제129조①6호가목: 제14조③8호라목(복권)·마목(시행령 제21조: 투표권 환급금·슬롯머신 당첨금)
  소득금액 3억원 초과분 100분의 30 — 2016 시행본부터 같은 문구.
- 제84조: 2호 복권 당첨금 건별 200만원 이하(2022.12.31. 개정, 부칙 제7조 시행 이후 지급분), 그 전은 3호 기타소득금액 5만원 이하.
  1호 투표권 환급금: 권면 합계 10만원 이하 + (가) 개별투표당 10만원 이하 또는 (나) 100배 이하·200만원 이하.
- 제37조①1호 단위투표금액, 2호 슬롯머신 투입금액이 필요경비.
"""
import asyncio, json
from korean_tax_calc_mcp.server import mcp


def c(n, a):
    return json.loads(asyncio.run(mcp.call_tool(n, a)).content[0].text)


def one(year, item):
    return c("other_income_aggregate", {"year": year, "items": [item]})


def test_lottery_over_300m_30pct_all_years():
    # 4억: 3억 × 20% + 1억 × 30% = 6천만 + 3천만 = 9천만 (제129조①6호가목·라목)
    for y in (2016, 2020, 2023, 2026):
        r = one(y, {"kind": "복권당첨금", "amount": 400_000_000})
        assert r["결과"]["분리과세_원천징수세액"] == 90_000_000, y


def test_lottery_threshold_by_payment_year():
    # 2022: 소득금액 1,000,000 > 5만 → 과세 20% = 200,000 (제84조3호)
    r = one(2022, {"kind": "복권당첨금", "amount": 1_000_000})
    assert r["결과"]["분리과세_원천징수세액"] == 200_000
    # 2023~: 당첨금 200만원 이하 과세최저한 (제84조2호)
    r = one(2023, {"kind": "복권당첨금", "amount": 2_000_000, "actual_cost": 1_000})
    assert r["항목별"][0]["과세구분"] == "과세최저한" and r["결과"]["분리과세_원천징수세액"] == 0
    # 200만 초과는 구입비 빼고 20%: (2,001,000 − 1,000) × 20% = 400,000
    r = one(2024, {"kind": "복권당첨금", "amount": 2_001_000, "actual_cost": 1_000})
    assert r["결과"]["분리과세_원천징수세액"] == 400_000


def test_lottery_small_amount_no_name_error():
    r = one(2020, {"kind": "복권당첨금", "amount": 40_000})
    assert r.get("error") is None and r["항목별"][0]["과세구분"] == "과세최저한"


def test_horse_and_slot_over_300m_30pct():
    # 승마: (500,010,000 − 10,000) = 5억 → 3억×20% + 2억×30% = 1.2억
    r = one(2018, {"kind": "승마투표권환급금", "amount": 500_010_000, "unit_bet": 10_000})
    assert r["결과"]["분리과세_원천징수세액"] == 120_000_000
    # 슬롯: 4억 − 투입 1천만 = 3.9억 → 6천만 + 9천만×30% 2,700만 = 8,700만
    r = one(2021, {"kind": "슬롯머신당첨금", "amount": 400_000_000, "stake": 10_000_000})
    assert r["결과"]["분리과세_원천징수세액"] == 87_000_000


def test_slot_stake_is_expense():
    # 5,000,000 − 투입 1,000,000 = 4,000,000 × 20% = 800,000 (제37조①2호)
    r = one(2025, {"kind": "슬롯머신당첨금", "amount": 5_000_000, "stake": 1_000_000})
    assert r["항목별"][0]["소득금액"] == 4_000_000 and r["결과"]["분리과세_원천징수세액"] == 800_000


def test_horse_threshold_needs_ticket_total():
    base = {"kind": "승마투표권환급금", "amount": 1_500_000, "unit_bet": 20_000}   # 75배, 200만 이하 → 나목 후보
    assert "입력 확인 필요" in json.dumps(one(2025, base), ensure_ascii=False)
    r = one(2025, {**base, "ticket_total": 100_000})
    assert r["항목별"][0]["과세구분"] == "과세최저한"
    # 권면 합계 10만원 초과 → 과세: (1,500,000 − 20,000) × 20% = 296,000
    r = one(2025, {**base, "ticket_total": 150_000})
    assert r["결과"]["분리과세_원천징수세액"] == 296_000
    # 100배 초과(가·나목 모두 아님) → ticket_total 없이도 과세: (1,500,000 − 10,000) × 20% = 298,000
    r = one(2025, {"kind": "승마투표권환급금", "amount": 1_500_000, "unit_bet": 10_000})
    assert r["결과"]["분리과세_원천징수세액"] == 298_000
    # 가목: 개별투표당 10만원 이하
    r = one(2025, {"kind": "승마투표권환급금", "amount": 90_000, "unit_bet": 100, "ticket_total": 50_000})
    assert r["항목별"][0]["과세구분"] == "과세최저한"


def test_citations_point_to_right_articles():
    r = one(2025, {"kind": "슬롯머신당첨금", "amount": 3_000_000})
    b = json.dumps(r["항목별"][0]["근거"], ensure_ascii=False)
    assert "14호" in b and "제37조" in b
    r = one(2025, {"kind": "복권당첨금", "amount": 3_000_000})
    b = json.dumps(r["항목별"][0]["근거"], ensure_ascii=False)
    assert '"2호"' in b and "8호라목" in b and "6호가목" in b


# 직무발명보상금_퇴직후: 시행령 제18조② 신설 2017.2.3. 연 300만원 → 2019.2.12. 500만원 → 2024.2.29. 700만원.
# 2016 시행본에는 제21조①22호의2가 없음(제12조5호라목이 한도 없이 비과세).
def test_retired_invention_bonus_limit_2017_2018():
    for y in (2017, 2018):
        r = one(y, {"kind": "직무발명보상금_퇴직후", "amount": 4_000_000, "employment_exempt_used": 1_000_000})
        h = r["항목별"][0]
        # 한도 300만 − 재직 중 100만 = 200만 비과세, 소득 200만, 원천징수 40만
        assert h["비과세"] == 2_000_000 and h["소득금액"] == 2_000_000 and h["원천징수세액"] == 400_000, y
    r = one(2016, {"kind": "직무발명보상금_퇴직후", "amount": 4_000_000, "employment_exempt_used": 0})
    assert "입력 확인 필요" in json.dumps(r, ensure_ascii=False)


# 제14조③8호가목: 2019 시행본까지 "제1호부터 제20호까지, 제22호 및 제26호 … 원천징수된 소득",
# 2020.1.1. 시행본부터 22호의2 추가·"제127조제1항제6호나목에 해당하여 원천징수되지 아니하는 경우를 포함".
def test_optional_separation_invention_bonus_from_2020():
    item = {"kind": "직무발명보상금_퇴직후", "amount": 5_000_000, "employment_exempt_used": 0}
    r19 = one(2019, {**item, "amount": 7_000_000})   # 한도 500만 → 소득 200만
    assert r19["결과"]["선택적_분리과세_가능"] is False
    assert r19["결과"]["선택적_분리과세_적용시_종합합산_기타소득금액"] == 2_000_000
    r20 = one(2020, {**item, "amount": 7_000_000})
    assert r20["결과"]["선택적_분리과세_가능"] is True
    assert r20["결과"]["선택적_분리과세_적용시_종합합산_기타소득금액"] == 0


def test_optional_separation_deposit_penalty_from_2020():
    items = [{"kind": "위약금·배상금", "amount": 2_500_000, "deposit_substituted": 2_000_000},
             {"kind": "일시적인적용역", "amount": 1_000_000}]
    # 2019: 계약금 대체 200만은 원천징수 안 된 소득 → 선택 불가, 나머지(위약금 50만 + 용역 40만 = 90만)만 선택 가능
    r = c("other_income_aggregate", {"year": 2019, "items": items})
    assert r["결과"]["선택적_분리과세_가능"] is True
    assert r["결과"]["선택적_분리과세_적용시_종합합산_기타소득금액"] == 2_000_000
    # 2020: 계약금 대체분도 포함 → 합계 290만 ≤ 300만, 전부 분리과세 선택 가능
    r = c("other_income_aggregate", {"year": 2020, "items": items})
    assert r["결과"]["선택적_분리과세_가능"] is True
    assert r["결과"]["선택적_분리과세_적용시_종합합산_기타소득금액"] == 0
