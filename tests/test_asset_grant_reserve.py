"""국고보조금·공사부담금·보험차익 일시상각충당금·압축기장충당금 세무조정 정답 테스트 — 손계산·조문 대조 사례."""
import asyncio, json

import pytest

from korean_tax_calc_mcp.server import mcp

M = 1_000_000
TOOL = "asset_grant_reserve"


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


def adj(r, 조정):
    return sum(x["금액"] for x in r["세무조정"] if x["조정"] == 조정)


MACHINE = {"asset": "기계", "cost": 200 * M, "used": 100 * M, "depreciable": True,
           "depreciation_this_year": 40 * M}


# 법 제36조①, 영 제64조②③1호·④1호, 영 제98조②(신고조정)
# 설정 1억(손금산입 △유보), 상계 4,000만×1억/2억=2,000만(익금산입 유보), 기말 8,000만
@pytest.mark.parametrize("year", [2016, 2025])
def test_grant_depreciable_by_return(year):
    r = c(TOOL, {"year": year, "kind": "국고보조금", "received": 100 * M, "assets": [MACHINE]})
    assert r["결과"]["충당금_설정액"] == 100 * M
    assert r["결과"]["상계액"] == 20 * M
    assert r["결과"]["기말_충당금_잔액"] == 80 * M
    assert adj(r, "손금산입") == 100 * M
    assert adj(r, "익금산입") == 20 * M
    assert r["결과"]["소득금액_순영향"] == -80 * M
    assert r["계산"]["자산별"][0]["구분"] == "일시상각충당금"


# 법 제37조①, 영 제65조③→제64조③2호: 토지는 압축기장충당금, 결산 계상 6,000만 중 한도 5,000만 초과 1,000만 손금불산입 유보
def test_construction_contribution_land_over_limit():
    r = c(TOOL, {"year": 2025, "kind": "공사부담금", "received": 50 * M,
                 "assets": [{"asset": "토지", "cost": 80 * M, "used": 50 * M, "depreciable": False,
                             "depreciation_this_year": 0, "book_provision": 60 * M}]})
    a = r["계산"]["자산별"][0]
    assert a["구분"] == "압축기장충당금"
    assert r["결과"]["충당금_설정액"] == 50 * M
    assert adj(r, "손금불산입") == 10 * M
    assert r["결과"]["상계액"] == 0
    assert r["결과"]["기말_충당금_잔액"] == 50 * M
    assert r["결과"]["소득금액_순영향"] == 10 * M


# 법 제36조②: 미사용 3,000만 중 사용계획 2,000만 손금산입 △유보, 1,000만은 익금 그대로
# −7,000만 + 1,400만(상계 1,400만×7,000만/7,000만) − 2,000만 = −7,600만
def test_grant_planned_use():
    r = c(TOOL, {"year": 2024, "kind": "국고보조금", "received": 100 * M, "planned_use": 20 * M,
                 "assets": [{"asset": "설비", "cost": 70 * M, "used": 70 * M, "depreciable": True,
                             "depreciation_this_year": 14 * M}]})
    assert r["결과"]["사용계획_손금산입"] == 20 * M
    assert r["결과"]["상계액"] == 14 * M
    assert r["결과"]["사용기한_연"] == 1
    assert r["결과"]["소득금액_순영향"] == -76 * M


# 영 제64조④1호 단서·⑤: 이후 연도 상계 2,000만(4,000만×1억/2억) 뒤 처분 — 전부 처분 잔액 6,000만, 절반 처분 3,000만 익금산입
@pytest.mark.parametrize("ratio,disp,end", [(1.0, 60 * M, 0), (0.5, 30 * M, 30 * M)])
def test_later_year_offset_and_disposal(ratio, disp, end):
    r = c(TOOL, {"year": 2025, "kind": "국고보조금", "received": 0, "receipt_year": False,
                 "assets": [{"asset": "기계", "cost": 200 * M, "depreciable": True,
                             "depreciation_this_year": 40 * M, "reserve_initial": 100 * M,
                             "reserve_opening": 80 * M, "disposed": True, "disposed_ratio": ratio}]})
    assert r["결과"]["상계액"] == 20 * M
    assert r["결과"]["처분_익금산입"] == disp
    assert r["결과"]["기말_충당금_잔액"] == end
    assert adj(r, "익금산입") == 20 * M + disp
    assert r["결과"]["충당금_설정액"] == 0


# 법 제38조①②, 영 제66조②: 보험차익 = 3억 − 1.2억 = 1.8억, 대체자산 가액에서 장부가액분을 먼저 쓴 것으로 봄
# 대체 2.5억 → 한도 min(1.8억, 1.3억)=1.3억, 상계 2,500만×1.3억/2.5억=1,300만 / 대체 4억 → 한도 1.8억, 상계 2,500만×1.8억/4억=1,125만
@pytest.mark.parametrize("cost,limit,offset", [(250 * M, 130 * M, 13 * M), (400 * M, 180 * M, 11_250_000)])
def test_insurance_gain(cost, limit, offset):
    r = c(TOOL, {"year": 2025, "kind": "보험차익", "received": 300 * M, "lost_book_value": 120 * M,
                 "assets": [{"asset": "건물", "cost": cost, "depreciable": True, "depreciation_this_year": 25 * M}]})
    assert r["결과"]["보험차익"] == 180 * M
    assert r["결과"]["손금산입_한도"] == limit
    assert r["결과"]["상계액"] == offset
    assert r["결과"]["사용기한_연"] == 2


# 영 제98조②: 결산 계상 6,000만(환입 1,200만) — 신고조정 안 하면 조정 없음, 하면 4,000만 손금산입·환입 차액 800만 익금산입
@pytest.mark.parametrize("claim,expected_net,expected_reserve", [(False, 0, 60 * M), (True, -32 * M, 100 * M)])
def test_book_provision_and_return_claim(claim, expected_net, expected_reserve):
    r = c(TOOL, {"year": 2025, "kind": "국고보조금", "received": 100 * M, "claim_by_return": claim,
                 "assets": [{**MACHINE, "book_provision": 60 * M, "book_reversal": 12 * M}]})
    assert r["결과"]["충당금_설정액"] == expected_reserve
    assert r["결과"]["소득금액_순영향"] == expected_net
    if not claim:
        assert r["세무조정"] == []
    else:
        assert adj(r, "손금산입") == 40 * M
        assert adj(r, "익금산입") == 8 * M


# 사용액 합계가 수령액을 넘으면 계산하지 않음, 보험차익은 멸실자산 장부가액 필수
def test_input_errors():
    r = c(TOOL, {"year": 2025, "kind": "국고보조금", "received": 50 * M, "assets": [MACHINE]})
    assert is_err(r)
    r2 = c(TOOL, {"year": 2025, "kind": "보험차익", "received": 300 * M,
                  "assets": [{"asset": "건물", "cost": 250 * M, "depreciable": True, "depreciation_this_year": 0}]})
    assert is_err(r2)
    s = c_or_exc(TOOL, {"year": 2025, "kind": "국고보조금", "received": 100 * M, "assets": [MACHINE], "grant_rate": 1})
    assert "grant_rate" in s
