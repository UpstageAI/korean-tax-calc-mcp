"""재고자산 평가 세무조정 정답 테스트 — 손계산·조문 대조 사례."""
import asyncio, json

import pytest

from korean_tax_calc_mcp.server import mcp

M = 1_000_000
TOOL = "inventory_valuation_adjustment"


def c(tool, a):
    r = asyncio.run(mcp.call_tool(tool, a))
    return json.loads((r.content[0] if hasattr(r, "content") else r[0][0]).text)


def c_or_exc(tool, a):
    """오류가 dict로 오든 예외로 오든 문자열로 돌려준다."""
    try:
        return json.dumps(c(tool, a), ensure_ascii=False)
    except Exception as e:  # 도구 호출 단계 검증 오류
        return "EXC " + str(e)


def is_err(r):
    return isinstance(r, dict) and "error" in r


PRODUCT = {"category": "제품·상품", "reported_method": "총평균법", "used_method": "총평균법",
           "book_value": 48 * M, "valuations": {"총평균법": 50 * M, "선입선출법": 55 * M}}


# 영 제74조①(신고 방법) 50M − 48M = 익금산입 2M / ④1호 무신고 선입선출법 33M − 30M = 익금산입 3M
def test_reported_and_unreported_two_categories():
    r = c(TOOL, {"year": 2025, "items": [
        PRODUCT,
        {"category": "원재료", "reported_method": "무신고", "used_method": "총평균법",
         "book_value": 30 * M, "valuations": {"총평균법": 30 * M, "선입선출법": 33 * M}},
    ]})
    rows = {x["재고구분"]: x for x in r["결과"]["구분별"]}
    assert rows["제품·상품"]["세법상_방법"] == "총평균법"
    assert rows["제품·상품"]["조정액"] == 2 * M
    assert rows["원재료"]["판정"] == "무신고"
    assert rows["원재료"]["세법상_방법"] == "선입선출법"
    assert rows["원재료"]["세법상_평가액"] == 33 * M
    assert r["결과"]["익금산입_합계"] == 5 * M
    assert r["결과"]["손금산입_합계"] == 0
    assert all(a["조정"] == "익금산입" and a["소득처분"] == "유보" for a in r["결과"]["세무조정"])


# 영 제74조④2호 단서: 임의변경 → max(선입선출 45M, 신고 총평균 46M) = 46M − 회사 43M = 익금산입 3M
def test_arbitrary_change_uses_larger_of_fifo_and_reported():
    r = c(TOOL, {"year": 2025, "items": [
        {"category": "제품·상품", "reported_method": "총평균법", "used_method": "이동평균법", "book_value": 43 * M,
         "valuations": {"총평균법": 46 * M, "이동평균법": 43 * M, "선입선출법": 45 * M}}]})
    row = r["결과"]["구분별"][0]
    assert "임의변경" in row["판정"]
    assert row["세법상_평가액"] == 46 * M
    assert row["세법상_방법"] == "총평균법"
    assert r["결과"]["익금산입_합계"] == 3 * M


# 영 제74조③2호: FY 12-31 종료 → 변경신고 기한 09-30. 기한 내면 새 방법(조정 0),
# 하루 늦으면 ④3호·⑤ 임의변경 → max(선입선출 45M, 종전 총평균 46M) − 45M = 익금산입 1M
@pytest.mark.parametrize("filed_on,adj", [("2025-09-30", 0), ("2025-10-01", 1 * M)])
def test_change_report_deadline(filed_on, adj):
    r = c(TOOL, {"year": 2025, "items": [
        {"category": "제품·상품", "reported_method": "총평균법", "used_method": "선입선출법", "book_value": 45 * M,
         "change_report": {"method": "선입선출법", "filed_on": filed_on},
         "valuations": {"총평균법": 46 * M, "선입선출법": 45 * M}}]})
    assert r["계산"]["변경신고_기한"] == "2025-09-30"
    assert r["결과"]["구분별"][0]["조정액"] == adj
    assert r["결과"]["익금산입_합계"] == adj


# 영 제74조①2호 저가법: min(총평균 40M, 시가 37M) = 37M − 회사 38M = 손금산입 1M(△유보)
def test_lower_of_cost_or_market_reported():
    r = c(TOOL, {"year": 2025, "items": [
        {"category": "제품·상품", "reported_method": "총평균법", "reported_lcm": True,
         "used_method": "총평균법", "used_lcm": True, "book_value": 38 * M,
         "valuations": {"총평균법": 40 * M, "시가": 37 * M, "선입선출법": 41 * M}}]})
    row = r["결과"]["구분별"][0]
    assert row["세법상_평가액"] == 37 * M
    assert row["조정액"] == -1 * M
    adj = r["결과"]["세무조정"]
    assert len(adj) == 1 and adj[0]["조정"] == "손금산입" and adj[0]["소득처분"] == "△유보"
    assert adj[0]["금액"] == 1 * M


# 영 제74조④ 괄호: 매매목적 부동산 무신고 → 개별법 120M − 회사 100M = 익금산입 20M
def test_real_estate_unreported_uses_specific_identification():
    r = c(TOOL, {"year": 2023, "items": [
        {"category": "매매목적부동산", "reported_method": "무신고", "used_method": "총평균법", "book_value": 100 * M,
         "valuations": {"개별법": 120 * M, "선입선출법": 110 * M, "총평균법": 100 * M}}]})
    row = r["결과"]["구분별"][0]
    assert row["세법상_방법"] == "개별법"
    assert r["결과"]["익금산입_합계"] == 20 * M


# 전기 재고자산평가감 유보 1.5M 추인(손금산입 △유보) + 당기 평가감 2M(익금산입 유보), 순 0.5M
def test_prior_year_reversal():
    r = c(TOOL, {"year": 2024, "items": [{**PRODUCT, "prior_adjustment": 1_500_000}]})
    kinds = {(a["조정"], a["소득처분"]): a["금액"] for a in r["결과"]["세무조정"]}
    assert kinds[("손금산입", "△유보")] == 1_500_000
    assert kinds[("익금산입", "유보")] == 2 * M
    assert r["결과"]["순조정액"] == 500_000


# 영 제74조⑥: 무신고 법인의 신고 기한 = 종료일 이전 3월(09-30). ⑤ 기한 후면 그 사업연도는 선입선출 55M → 익금산입 5M
# 영 제74조③1호·법 제60조①: 설립 사업연도는 신고기한(2026-03-31)까지 신고하면 기한 내
@pytest.mark.parametrize("filed_on,new_corp,adj", [
    ("2025-09-15", False, 0),
    ("2025-10-15", False, 5 * M),
    ("2026-03-31", True, 0),
])
def test_unreported_then_report(filed_on, new_corp, adj):
    r = c(TOOL, {"year": 2025, "new_corp": new_corp, "items": [
        {"category": "제품·상품", "reported_method": "무신고", "used_method": "총평균법", "book_value": 50 * M,
         "change_report": {"method": "총평균법", "filed_on": filed_on},
         "valuations": {"총평균법": 50 * M, "선입선출법": 55 * M}}]})
    assert r["결과"]["익금산입_합계"] == adj


# 사업연도 2025-04-01~2026-03-31 → 변경신고 기한 2025-12-31, 그날 신고는 기한 내(조정 0)
def test_non_calendar_fiscal_year_deadline():
    r = c(TOOL, {"year": 2025, "fy_start": "2025-04-01", "fy_end": "2026-03-31", "items": [
        {"category": "저장품", "reported_method": "총평균법", "used_method": "선입선출법", "book_value": 45 * M,
         "change_report": {"method": "선입선출법", "filed_on": "2025-12-31"},
         "valuations": {"총평균법": 46 * M, "선입선출법": 45 * M}}]})
    assert r["계산"]["변경신고_기한"] == "2025-12-31"
    assert r["결과"]["익금산입_합계"] == 0


# 판정에 필요한 평가액 없음(무신고인데 선입선출법 값 없음 / 저가법인데 시가 없음) → 계산하지 않음
@pytest.mark.parametrize("item", [
    {"category": "원재료", "reported_method": "무신고", "used_method": "총평균법", "book_value": 30 * M,
     "valuations": {"총평균법": 30 * M}},
    {"category": "제품·상품", "reported_method": "총평균법", "reported_lcm": True, "used_method": "총평균법",
     "used_lcm": True, "book_value": 38 * M, "valuations": {"총평균법": 40 * M}},
])
def test_missing_valuation_rejected(item):
    s = c_or_exc(TOOL, {"year": 2025, "items": [item]})
    assert "error" in s or s.startswith("EXC")
    assert '"결과"' not in s
