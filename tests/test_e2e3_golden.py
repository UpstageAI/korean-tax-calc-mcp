"""기타소득 끝에서 끝까지 계산기 정답 테스트 (Claude 작성 2026-10-13) — 수정 금지.
공개 검증 사례(세무사 1차 2025-52, 출처 Q-Net)는 소득세법 제21조·제12조·제14조③·제127조·제129조, 영 제18조②·제87조 2025 시행본으로
손계산해 공식 정답(ㄱ 18,700,000 / ㄴ 1,340,000)과 일치 확인. 실무형 사례는 Claude 손계산.
"""
import asyncio, json
from korean_tax_calc_mcp.server import mcp


def c(n, a):
    return json.loads(asyncio.run(mcp.call_tool(n, a)).content[0].text)


ITEMS_2025_52 = [
    {"kind": "산업재산권대여", "amount": 4_000_000},
    {"kind": "뇌물", "amount": 30_000_000, "forfeited": 20_000_000},
    {"kind": "위약금·배상금", "amount": 2_500_000, "deposit_substituted": 2_000_000},
    {"kind": "주택입주지체상금", "amount": 8_000_000},
    {"kind": "연금외수령", "amount": 3_000_000},
    {"kind": "직무발명보상금_퇴직후", "amount": 4_000_000, "employment_exempt_used": 6_000_000},
]


def by_kind(r):
    return {i["kind"]: i for i in r["항목별"]}


def test_public_case_2025_52():
    r = c("other_income_aggregate", {"year": 2025, "items": ITEMS_2025_52})
    assert r["결과"]["종합소득_합산_기타소득금액"] == 18_700_000
    assert r["결과"]["기납부_원천징수세액"] == 1_340_000
    k = by_kind(r)
    assert k["산업재산권대여"]["소득금액"] == 1_600_000 and k["산업재산권대여"]["원천징수세액"] == 320_000
    assert k["뇌물"]["소득금액"] == 10_000_000 and k["뇌물"]["원천징수세액"] == 0
    assert k["위약금·배상금"]["소득금액"] == 2_500_000 and k["위약금·배상금"]["원천징수세액"] == 100_000
    assert k["주택입주지체상금"]["소득금액"] == 1_600_000 and k["주택입주지체상금"]["원천징수세액"] == 320_000
    assert k["연금외수령"]["과세구분"] == "분리과세" and k["연금외수령"]["원천징수세액"] == 450_000
    assert k["직무발명보상금_퇴직후"]["비과세"] == 1_000_000 and k["직무발명보상금_퇴직후"]["소득금액"] == 3_000_000
    assert k["직무발명보상금_퇴직후"]["원천징수세액"] == 600_000


def test_separate_taxation_excluded_from_both_totals():  # 연금외수령은 합산액·기납부세액 모두에서 빠지고 분리과세란에만 잡힘
    r = c("other_income_aggregate", {"year": 2025, "items": [{"kind": "연금외수령", "amount": 3_000_000},
                                                             {"kind": "산업재산권대여", "amount": 10_000_000}]})
    assert r["결과"]["종합소득_합산_기타소득금액"] == 4_000_000
    assert r["결과"]["기납부_원천징수세액"] == 800_000
    assert r["결과"]["분리과세_기타소득금액"] == 3_000_000 and r["결과"]["분리과세_원천징수세액"] == 450_000


def test_invention_bonus_exempt_limit_without_employment_use():  # 재직 중 비과세 사용 0 → 700만 한도 전부 적용
    r = c("other_income_aggregate", {"year": 2025, "items": [{"kind": "직무발명보상금_퇴직후", "amount": 4_000_000, "employment_exempt_used": 0}]})
    k = by_kind(r)["직무발명보상금_퇴직후"]
    assert k["비과세"] == 4_000_000 and k["소득금액"] == 0 and k["원천징수세액"] == 0
    r = c("other_income_aggregate", {"year": 2023, "items": [{"kind": "직무발명보상금_퇴직후", "amount": 8_000_000, "employment_exempt_used": 0}]})
    assert by_kind(r)["직무발명보상금_퇴직후"]["비과세"] == 5_000_000           # 2023 한도 500만 원(영 제18조② 2019 개정본)


def test_expense_rate_follows_year():  # 영 제87조 1호의2: 2018 이전 70%, 2019 이후 60%
    r18 = c("other_income_aggregate", {"year": 2018, "items": [{"kind": "일시적인적용역", "amount": 4_000_000}]})
    r19 = c("other_income_aggregate", {"year": 2019, "items": [{"kind": "일시적인적용역", "amount": 4_000_000}]})
    assert by_kind(r18)["일시적인적용역"]["소득금액"] == 1_200_000
    assert by_kind(r19)["일시적인적용역"]["소득금액"] == 1_600_000


def test_optional_separate_choice_flag():  # 기타소득금액 300만 이하·원천징수 → 선택 분리과세 가능(제14조③8호가목), 뇌물 포함 시 불가
    r = c("other_income_aggregate", {"year": 2025, "items": [{"kind": "일시적인적용역", "amount": 5_000_000}]})
    assert r["결과"]["선택적_분리과세_가능"] is True                       # 소득금액 2,000,000
    r = c("other_income_aggregate", {"year": 2025, "items": [{"kind": "뇌물", "amount": 2_000_000, "forfeited": 0}]})
    assert r["결과"]["선택적_분리과세_가능"] is False


def test_actual_expense_exceeding_rate():  # 실제 경비가 정률을 넘으면 실제 경비(영 제87조 단서)
    r = c("other_income_aggregate", {"year": 2025, "items": [{"kind": "산업재산권대여", "amount": 4_000_000, "actual_expense": 3_000_000}]})
    assert by_kind(r)["산업재산권대여"]["소득금액"] == 1_000_000


def test_missing_required_fact_rejected():  # 직무발명보상금_퇴직후는 같은 해 근로 비과세액 없이는 계산하지 않음
    r = c("other_income_aggregate", {"year": 2025, "items": [{"kind": "직무발명보상금_퇴직후", "amount": 4_000_000}]})
    assert "error" in r
    r = c("other_income_aggregate", {"year": 2025, "items": [{"kind": "복권당첨금", "amount": 4_000_000}]})
    assert "error" in r and "허용값" in r


def test_inconsistent_facts_rejected():  # CodeSolar 리뷰(PR #9) 회귀 (Claude 추가 10-13): 몰수액·계약금 대체액이 총액을 넘으면 계산하지 않음
    r = c("other_income_aggregate", {"year": 2025, "items": [{"kind": "뇌물", "amount": 1_000_000, "forfeited": 2_000_000}]})
    assert "error" in r
    r = c("other_income_aggregate", {"year": 2025, "items": [{"kind": "위약금·배상금", "amount": 1_000_000, "deposit_substituted": 2_000_000}]})
    assert "error" in r
