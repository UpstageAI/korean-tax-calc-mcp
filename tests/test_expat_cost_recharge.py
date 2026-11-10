"""해외 파견 인건비 청구 expat_cost_recharge — 정답 테스트(수정 금지, Claude 작성 2026-11-10).
근거: 법인세법 제15조·제19조, 시행령 제106조제1항제1호 라목, 국조법 제7조, 소득세법 제12조제3호거목·시행령 제16조제1항제1호(월 100만원, 건설·선박 500만원).
해석: 서면-2017-법인-3468, 심사법인99-0511, 조심-2015-부-1111. 공개 검증 사례: 2026-11-10 5개년 시나리오 파견 1명(연 급여 6천만).
"""
from _helpers import call as c

M = 1_000_000
A = {"이름": "A", "급여": 60 * M, "사회보험": 6 * M, "체재비": 12 * M, "귀속": "현지법인", "마크업": 0.05, "청구액": 0, "국외근로_개월": 12}


def test_e1_unrecharged_subsidiary_work_is_nondeductible():
    r = c("expat_cost_recharge", {"year": 2026, "items": [A]})
    assert "error" not in r, r
    it = r["결과"]["항목별"][0]
    assert it["원가"] == 78 * M and it["현지법인_귀속원가"] == 78 * M and it["정상청구액"] == 81_900_000
    assert it["청구액"] == 0 and it["미청구"] == 81_900_000
    assert it["본사_손금불산입"] == 78 * M and it["본사_손금"] == 0 and it["정상가격_조정_익금산입"] == 0
    assert "기타소득" in it["소득처분"] and "제106조" in it["소득처분"]
    assert it["근로자_비과세"] == 12 * M
    assert r["결과"]["합계"]["본사_손금불산입"] == 78 * M
    assert "제106조" in r["근거"] and "제7조" in r["근거"] and "제16조" in r["근거"]


def test_e2_common_split():
    it = c("expat_cost_recharge", {"year": 2026, "items": [{**A, "귀속": "공통", "공통비율": 0.5}]})["결과"]["항목별"][0]
    assert it["현지법인_귀속원가"] == 39 * M and it["정상청구액"] == 40_950_000
    assert it["본사_손금불산입"] == 39 * M and it["본사_손금"] == 39 * M


def test_e3_full_recharge_deductible_and_fee_income():
    it = c("expat_cost_recharge", {"year": 2026, "items": [{**A, "청구액": 85 * M}]})["결과"]["항목별"][0]
    assert it["미청구"] == 0 and it["본사_손금불산입"] == 0 and it["본사_손금"] == 78 * M
    assert it["정상가격_조정_익금산입"] == 0 and it["청구액_익금"] == 85 * M


def test_e4_under_recharge_arms_length_adjustment():
    r = c("expat_cost_recharge", {"year": 2026, "items": [{**A, "청구액": 50 * M}]})
    it = r["결과"]["항목별"][0]
    assert it["본사_손금불산입"] == 0 and it["정상가격_조정_익금산입"] == 31_900_000 and it["본사_손금"] == 78 * M
    assert any("정상가격" in str(j) for j in r["판단"])


def test_e5_head_office_work_fully_deductible():
    it = c("expat_cost_recharge", {"year": 2026, "items": [{**A, "귀속": "본사", "국외근로_개월": 0}]})["결과"]["항목별"][0]
    assert it["현지법인_귀속원가"] == 0 and it["본사_손금"] == 78 * M and it["본사_손금불산입"] == 0 and it["근로자_비과세"] == 0


def test_e6_nonresident_no_exemption_and_construction_rate():
    r = c("expat_cost_recharge", {"year": 2026, "items": [{**A, "거주자": False}]})
    assert r["결과"]["항목별"][0]["근로자_비과세"] == 0 and any("비거주자" in str(j) for j in r["판단"])
    it = c("expat_cost_recharge", {"year": 2026, "items": [{**A, "국외근로_유형": "건설·선박", "국외근로_개월": 6}]})["결과"]["항목별"][0]
    assert it["근로자_비과세"] == 30 * M


def test_totals_over_items():
    g = c("expat_cost_recharge", {"year": 2026, "items": [A, {**A, "이름": "B", "청구액": 85 * M}]})["결과"]["합계"]
    assert g["원가"] == 156 * M and g["본사_손금불산입"] == 78 * M and g["청구액"] == 85 * M and g["근로자_비과세"] == 24 * M


def test_errors():
    r = c("expat_cost_recharge", {"year": 2026, "items": [{**A, "귀속": "지점"}]})
    assert "error" in r and "허용값" in r
    assert "error" in c("expat_cost_recharge", {"year": 2026, "items": [{**A, "귀속": "공통"}]})
    assert "error" in c("expat_cost_recharge", {"year": 2026, "items": [{**A, "급여": -1}]})
    assert "error" in c("expat_cost_recharge", {"year": 2026, "items": [{**A, "마크업": -0.1}]})


def test_find_tool_surfaces_tool():
    r = c("find_tool", {"query": "해외 파견 직원 인건비 현지법인 청구", "n": 3})
    assert "expat_cost_recharge" in [x["도구"] for x in r["결과"]["후보"]], r
