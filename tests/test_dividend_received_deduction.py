"""내국법인 수입배당금액 익금불산입 정답 테스트 — 손계산·조문 대조 사례."""
import asyncio, json

import pytest

from korean_tax_calc_mcp.server import mcp

M = 1_000_000
TOOL = "dividend_received_deduction"


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


def by_name(r, name):
    return next(x for x in r["결과"]["피출자법인별"] if x["이름"] == name)


# 법 제18조의2①1호 표(2023.1.1~): 50%↑ 100, 20~50% 80, 20%↓ 30 / 영 제17조의2③ 차감 = A×B/C×D
# 갑 50M×1 − 25M×0.2×1 = 45M, 을 20M×0.8 − 25M×0.1×0.8 = 14M, 병 10M×0.3 − 25M×0.05×0.3 = 2,625,000
def test_current_three_investees_with_interest():
    r = c(TOOL, {
        "year": 2024,
        "investees": [
            {"name": "갑", "listed": False, "dividend": 50 * M,
             "shares": {"issued": 10_000, "held": 6_000, "within_3m": 0}, "book_value_jeoksu": 2_000 * M},
            {"name": "을", "listed": True, "dividend": 20 * M, "ratio": 0.25, "book_value_jeoksu": 1_000 * M},
            {"name": "병", "listed": True, "dividend": 10 * M, "ratio": 0.05, "book_value_jeoksu": 500 * M},
        ],
        "interest_paid": 30 * M, "interest_excluded": 5 * M, "total_assets_jeoksu": 10_000 * M,
    })
    assert r["계산"]["차입금이자"] == 25 * M
    assert by_name(r, "갑")["익금불산입률"] == 1.0
    assert by_name(r, "갑")["차감액"] == 5 * M
    assert by_name(r, "을")["익금불산입률"] == 0.8
    assert by_name(r, "을")["익금불산입액"] == 14 * M
    assert by_name(r, "병")["차감액"] == 375_000
    assert r["계산"]["익금불산입_대상액_합계"] == 69 * M
    assert r["계산"]["차감액_합계"] == 7_375_000
    assert r["결과"]["익금불산입액"] == 61_625_000
    adj = r["결과"]["세무조정"]
    assert len(adj) == 1 and adj[0]["조정"] == "익금불산입" and adj[0]["소득처분"] == "기타"
    assert adj[0]["금액"] == 61_625_000


# 영 제17조의2① 후단 선입선출 양도 → 3개월 이상 1,500주(15%) → 30%, 법 제18조의2②1호 3개월 이내 2,000주분 제외
# 배당 35M/3,500주 = 1만원/주: 제외 20M, 대상 15M × 0.3 = 4,500,000
def test_lots_fifo_and_within_3_months():
    r = c(TOOL, {
        "year": 2025,
        "investees": [{"name": "정", "listed": False, "dividend": 35 * M, "record_date": "2025-12-31",
                       "shares_issued": 10_000,
                       "lots": [{"date": "2024-05-01", "shares": 3_000},
                                {"date": "2025-11-01", "shares": 2_000},
                                {"date": "2025-11-20", "shares": -1_500}]}],
    })
    x = by_name(r, "정")
    assert x["출자비율"] == pytest.approx(0.15)
    assert x["익금불산입률"] == 0.3
    assert x["제외_배당금"] == 20 * M
    assert x["대상_배당금"] == 15 * M
    assert r["결과"]["익금불산입액"] == 4_500_000


# 법 제18조의2②8호·영 제17조의2⑤(2024.1.1 이후 받는 분, 법률 제19930호 부칙 제3조) / ②4호 감면법인은 2023에도 제외
@pytest.mark.parametrize("year,kind,expected", [
    (2024, "감자등의제배당", 0),
    (2023, "감자등의제배당", 10 * M),
    (2023, "감면법인", 0),
])
def test_exclusion_kind_by_receipt_year(year, kind, expected):
    r = c(TOOL, {"year": year,
                 "investees": [{"name": "무", "dividend": 10 * M, "ratio": 0.6, "exclusion": kind}]})
    assert r["결과"]["익금불산입액"] == expected
    if expected == 0:
        assert r["결과"]["세무조정"] == []


# 2022 받은 배당(일반, 법 제18조의2①1호 2020~2022 표): 상장 35%→50%, 비상장 40%→30%, 비상장 100%→100%
def test_2022_general_listed_unlisted_bands():
    r = c(TOOL, {"year": 2022, "investees": [
        {"name": "상장35", "listed": True, "dividend": 10 * M, "ratio": 0.35},
        {"name": "비상장40", "listed": False, "dividend": 10 * M, "ratio": 0.40},
        {"name": "완전", "listed": False, "dividend": 10 * M, "ratio": 1.0},
    ]})
    assert by_name(r, "상장35")["익금불산입률"] == 0.5
    assert by_name(r, "비상장40")["익금불산입률"] == 0.3
    assert by_name(r, "완전")["익금불산입률"] == 1.0
    assert r["결과"]["익금불산입액"] == 18 * M


# 상장 정확히 30%: 2019(30% 초과만 50%) → 30% / 2020(30% 이상 50%, 법률 제16833호 부칙 제3조) → 50%
@pytest.mark.parametrize("year,rate,amount", [(2019, 0.3, 3 * M), (2020, 0.5, 5 * M)])
def test_boundary_30pct_changes_2020(year, rate, amount):
    r = c(TOOL, {"year": year, "investees": [{"name": "경계", "listed": True, "dividend": 10 * M, "ratio": 0.30}]})
    assert by_name(r, "경계")["익금불산입률"] == rate
    assert r["결과"]["익금불산입액"] == amount


# 2018 지주회사(구 법 제18조의2): 비상장 90%(80% 초과)→100%, 상장 35%(40% 이하)→80%
# 구 영 제17조의2⑤·⑦: 10M × (200×1 + 100×0.8)/1,000 = 2.8M → 28M − 2.8M = 25.2M
def test_2018_holding_company():
    r = c(TOOL, {"year": 2018, "company_type": "지주회사", "investees": [
        {"name": "자1", "listed": False, "dividend": 20 * M, "ratio": 0.9, "book_value_jeoksu": 200 * M},
        {"name": "자2", "listed": True, "dividend": 10 * M, "ratio": 0.35, "book_value_jeoksu": 100 * M},
    ], "interest_paid": 10 * M, "total_assets_jeoksu": 1_000 * M})
    assert by_name(r, "자1")["익금불산입률"] == 1.0
    assert by_name(r, "자2")["익금불산입률"] == 0.8
    assert r["계산"]["차감액_합계"] == 2_800_000
    assert r["결과"]["익금불산입액"] == 25_200_000


# 2021 지주회사(법 제18조의3 2020~2022 표): 비상장 60%→90%, 상장 25%(자회사 요건 20% 충족)→80%
# 비상장 30%는 자회사 요건(40%) 미달 → 일반 법 제18조의2 비상장 50% 미만 30%
def test_2021_holding_company_with_non_subsidiary():
    r = c(TOOL, {"year": 2021, "company_type": "지주회사", "investees": [
        {"name": "자A", "listed": False, "dividend": 10 * M, "ratio": 0.6},
        {"name": "자B", "listed": True, "dividend": 10 * M, "ratio": 0.25},
        {"name": "비자", "listed": False, "dividend": 10 * M, "ratio": 0.3},
    ]})
    assert by_name(r, "자A")["익금불산입률"] == 0.9
    assert by_name(r, "자B")["익금불산입률"] == 0.8
    assert by_name(r, "비자")["익금불산입률"] == 0.3
    assert r["결과"]["익금불산입액"] == 20 * M


# 법률 제19193호 부칙 제16조②(2025.3.14 개정, 2026.12.31까지 받는 분): 지주회사 종전 제18조의3 비율 선택
# 상장 35%: 현행 80% → 8M / 종전 30~40% 90% → 9M
@pytest.mark.parametrize("election,amount", [(False, 8 * M), (True, 9 * M)])
def test_holding_legacy_election_2025(election, amount):
    r = c(TOOL, {"year": 2025, "company_type": "지주회사", "holding_legacy_election": election,
                 "investees": [{"name": "자C", "listed": True, "dividend": 10 * M, "ratio": 0.35}]})
    assert r["결과"]["익금불산입액"] == amount


# 법 제18조의2① 후단: 대상 300,000 − 차감 10M×0.5×0.3 = 1,500,000 → 음수 → 0
def test_negative_total_is_zero():
    r = c(TOOL, {"year": 2025, "investees": [
        {"name": "소액", "listed": True, "dividend": 1 * M, "ratio": 0.10, "book_value_jeoksu": 5_000 * M}],
        "interest_paid": 10 * M, "total_assets_jeoksu": 10_000 * M})
    assert by_name(r, "소액")["차감액"] == 1_500_000
    assert r["결과"]["익금불산입액"] == 0
    assert r["결과"]["세무조정"] == []


# 출자비율 정보 없음 / 차감 이자 있는데 자산총액 적수 없음 → 계산하지 않음
@pytest.mark.parametrize("args", [
    {"year": 2024, "investees": [{"name": "누락", "dividend": 10 * M}]},
    {"year": 2024, "investees": [{"name": "적수", "dividend": 10 * M, "ratio": 0.6, "book_value_jeoksu": 100 * M}],
     "interest_paid": 5 * M},
])
def test_missing_inputs_rejected(args):
    s = c_or_exc(TOOL, args)
    assert "error" in s or s.startswith("EXC")
    assert '"결과"' not in s
