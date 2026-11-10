"""외감·외부세무조정·국제거래 자료 제출 의무 판정 corporate_filing_obligations — 정답 테스트(수정 금지, Claude 작성 2026-11-10).
근거: 외감법 제4조·시행령 제5조, 법인세법 제60조제9항·시행령 제97조의2 제1항(2026.10.1 시행본 원문 확인), 국조법 제16조·시행령 제34조·제36조, 제58조.
공개 검증 사례: 2026-11-10 5개년 시나리오(가상 (주)글로우랩 2022·2024·2026).
"""
from _helpers import call as c

M = 1_000_000
Y24 = {"year": 2024, "corp_type": "주식회사", "revenue": 12_000 * M, "revenue_prev": 4_000 * M, "assets": 6_000 * M, "liabilities": 3_000 * M,
       "employees": 35, "established_on": "2021-03-01", "foreign_subsidiary": True, "foreign_direct_investment": True,
       "related_goods": 1_200 * M, "party_max_goods": 1_200 * M}


def test_f1_2024_subsidiary_triggers_external_adjustment_not_audit():
    r = c("corporate_filing_obligations", Y24)
    assert "error" not in r, r
    g = r["결과"]
    assert g["외부감사"]["대상"] is False
    assert g["외부세무조정"]["대상"] is True and any("7호" in s for s in g["외부세무조정"]["사유"])
    assert g["국제거래명세서"] is True and g["요약손익계산서"] is True and g["정상가격산출방법신고서"] is False
    assert g["국제거래정보통합보고서"] is False
    assert g["해외직접투자명세"] == {"대상": True, "기한": "2025-06-30"}
    assert "제97조의2" in r["근거"] and "제36조" in r["근거"]


def test_f2_2022_new_company_rule_4():
    g = c("corporate_filing_obligations", {"year": 2022, "revenue": 1_200 * M, "revenue_prev": 300 * M, "assets": 500 * M, "liabilities": 200 * M,
                                            "employees": 4, "established_on": "2021-03-01"})["결과"]
    assert g["외부감사"]["대상"] is False
    assert g["외부세무조정"]["대상"] is True and any("4호" in s for s in g["외부세무조정"]["사유"])
    assert g["국제거래명세서"] is False and g["해외직접투자명세"]["대상"] is False


def test_f3_2026_audit_and_arms_length_report():
    g = c("corporate_filing_obligations", {**Y24, "year": 2026, "revenue": 80_000 * M, "revenue_prev": 35_000 * M, "assets": 30_000 * M,
                                            "liabilities": 15_000 * M, "employees": 120, "related_goods": 14_000 * M, "party_max_goods": 10_000 * M})["결과"]
    assert g["외부감사"]["대상"] is True and len(g["외부감사"]["충족조건"]) >= 3
    assert g["외부세무조정"]["대상"] is True and any("1호" in s for s in g["외부세무조정"]["사유"])
    assert g["정상가격산출방법신고서"] is True and g["국제거래정보통합보고서"] is False      # 매출 800억 < 1,000억


def test_f3b_integrated_report_needs_both_thresholds():
    g = c("corporate_filing_obligations", {**Y24, "revenue": 150_000 * M, "revenue_prev": 90_000 * M, "related_goods": 60_000 * M,
                                            "party_max_goods": 60_000 * M, "assets": 50_000 * M, "liabilities": 20_000 * M, "employees": 200})["결과"]
    assert g["국제거래정보통합보고서"] is True
    g2 = c("corporate_filing_obligations", {**Y24, "revenue": 150_000 * M, "related_goods": 40_000 * M, "party_max_goods": 40_000 * M})["결과"]
    assert g2["국제거래정보통합보고서"] is False


def test_f4_limited_company_three_of_five():
    g = c("corporate_filing_obligations", {"year": 2026, "corp_type": "유한회사", "revenue": 9_000 * M, "revenue_prev": 8_000 * M, "assets": 13_000 * M,
                                            "liabilities": 8_000 * M, "employees": 60, "members": 60})["결과"]
    assert g["외부감사"]["대상"] is True
    g2 = c("corporate_filing_obligations", {"year": 2026, "corp_type": "유한회사", "revenue": 9_000 * M, "revenue_prev": 8_000 * M, "assets": 13_000 * M,
                                             "liabilities": 8_000 * M, "employees": 60, "members": 10})["결과"]
    assert g2["외부감사"]["대상"] is False


def test_f5_assets_500bn_alone():
    g = c("corporate_filing_obligations", {"year": 2026, "revenue": 1_000 * M, "revenue_prev": 1_000 * M, "assets": 60_000 * M, "liabilities": 100 * M, "employees": 3})["결과"]
    assert g["외부감사"]["대상"] is True and g["외부세무조정"]["대상"] is True       # 외감이면 1호


def test_party_level_exemption_for_arms_length_report():
    g = c("corporate_filing_obligations", {**Y24, "related_goods": 6_000 * M, "party_max_goods": 900 * M})["결과"]     # 전체 60억 > 50억이지만 상대별 9억 ≤ 10억
    assert g["정상가격산출방법신고서"] is False and g["국제거래명세서"] is True


def test_errors():
    r = c("corporate_filing_obligations", {**Y24, "corp_type": "합자회사"})
    assert "error" in r and "허용값" in r
    assert "error" in c("corporate_filing_obligations", {**Y24, "revenue": -1})


def test_find_tool_surfaces_tool():
    r = c("find_tool", {"query": "외부세무조정 대상 외감 대상 판정", "n": 3})
    assert "corporate_filing_obligations" in [x["도구"] for x in r["결과"]["후보"]], r
