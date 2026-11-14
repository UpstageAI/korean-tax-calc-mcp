"""외국자회사 수입배당금 foreign_subsidiary_dividend — 정답 테스트(수정 금지, Claude 작성 2026-11-10).
근거: 법인세법 제18조의4(2023.1.1~, 95% 익금불산입)·시행령 제18조제1항(6개월 보유), 제57조제4항·제5항·제7항, 시행령 제94조제8항(간접외국납부세액),
제21조제1호, 부칙 법률 19193호 제4조·제19조.
2026-11-14: 2026.1.1.~12.31. 수령분은 조세특례제한법 제23조의2(법률 제21549호, 2026.4.21. 신설)로 100% — D1(2026-06-30) 기대값을 100%로 고침, 95% 끝수 검사는 2025 수령분으로. 공개 검증 사례: 2026-11-10 5개년 시나리오(가상 (주)글로우랩 일본법인 배당 2억, 원천세 5%).
"""
from _helpers import call as c

M = 1_000_000
D1 = {"received_on": "2026-06-30", "ownership_ratio": 1.0, "held_months": 27, "dividend": 200 * M, "foreign_withholding": 10 * M,
      "subsidiary_tax": 30 * M, "subsidiary_income": 230 * M}


def test_d1_exclusion_regime_2026():
    r = c("foreign_subsidiary_dividend", D1)
    assert "error" not in r, r
    g = r["결과"]
    assert g["제도"] == "익금불산입" and g["익금불산입액"] == 200 * M and g["익금산입액"] == 0     # 조특법 제23조의2제1항 100%
    assert g["직접외국납부세액"] == 0 and g["간접외국납부세액"] == 0 and g["공제대상_외국법인세액"] == 0 and g["Gross_up_익금산입"] == 0
    assert g["외국세_손금불산입"] == 10 * M
    assert "제18조의4" in r["근거"] and "제57조제7항" in r["근거"] and "제21조" in r["근거"]
    assert "명세서" in r["서식"]
    assert any("제57조제7항" in str(j) for j in r["판단"])


def test_d2_received_in_2022_uses_old_credit_regime():
    r = c("foreign_subsidiary_dividend", {**D1, "received_on": "2022-12-20"})
    g = r["결과"]
    assert g["제도"] == "외국납부세액공제" and g["익금불산입액"] == 0 and g["익금산입액"] == 200 * M
    assert g["직접외국납부세액"] == 10 * M and g["간접외국납부세액"] == 30 * M           # 30M × 200M ÷ (230M − 30M)
    assert g["공제대상_외국법인세액"] == 40 * M and g["Gross_up_익금산입"] == 30 * M and g["외국세_손금불산입"] == 0
    assert any("종전" in str(j) or "부칙" in str(j) for j in r["판단"])


def test_d2b_2022_indirect_needs_25pct():
    g = c("foreign_subsidiary_dividend", {**D1, "received_on": "2022-12-20", "ownership_ratio": 0.2})["결과"]
    assert g["제도"] == "외국납부세액공제" and g["간접외국납부세액"] == 0 and g["공제대상_외국법인세액"] == 10 * M


def test_d3_held_under_6_months_falls_to_credit():
    r = c("foreign_subsidiary_dividend", {**D1, "held_months": 4})
    assert r["결과"]["제도"] == "외국납부세액공제" and r["결과"]["공제대상_외국법인세액"] == 40 * M
    assert any("6개월" in str(j) for j in r["판단"])


def test_d4_under_10pct_no_indirect():
    g = c("foreign_subsidiary_dividend", {**D1, "ownership_ratio": 0.08})["결과"]
    assert g["제도"] == "외국납부세액공제" and g["간접외국납부세액"] == 0 and g["공제대상_외국법인세액"] == 10 * M


def test_d5_cfc_low_tax_included_in_income():
    r = c("foreign_subsidiary_dividend", {**D1, "cfc_low_tax": True})
    assert r["결과"]["익금불산입액"] == 0 and r["결과"]["익금산입액"] == 200 * M and r["결과"]["공제대상_외국법인세액"] == 40 * M
    assert any("특정외국법인" in str(j) for j in r["판단"])


def test_d6_hybrid_included_in_income():
    r = c("foreign_subsidiary_dividend", {**D1, "hybrid": True})
    assert r["결과"]["익금불산입액"] == 0 and any("혼성" in str(j) for j in r["판단"])


def test_d7_resource_development_5pct():
    g = c("foreign_subsidiary_dividend", {**D1, "ownership_ratio": 0.05, "resource_development": True})["결과"]
    assert g["제도"] == "익금불산입" and g["익금불산입액"] == 200 * M      # 2026 수령분 조특법 제23조의2 100%


def test_truncation():
    g = c("foreign_subsidiary_dividend", {**D1, "received_on": "2025-06-30", "dividend": 1_234_567, "foreign_withholding": 0})["결과"]
    assert g["익금불산입액"] == 1_172_838 and g["익금산입액"] == 61_729      # 1,234,567 × 0.95 = 1,172,838.65


def test_errors():
    assert "error" in c("foreign_subsidiary_dividend", {**D1, "ownership_ratio": 1.5})
    assert "error" in c("foreign_subsidiary_dividend", {**D1, "dividend": 0})
    assert "error" in c("foreign_subsidiary_dividend", {**D1, "foreign_withholding": -1})
    assert "error" in c("foreign_subsidiary_dividend", {**D1, "received_on": "2026/06/30"})
    assert "error" in c("foreign_subsidiary_dividend", {**D1, "held_months": 4, "subsidiary_income": 20 * M})   # 소득 ≤ 법인세


def test_find_tool_surfaces_tool():
    r = c("find_tool", {"query": "외국자회사 배당 익금불산입 95% 외국납부세액", "n": 3})
    assert "foreign_subsidiary_dividend" in [x["도구"] for x in r["결과"]["후보"]], r
