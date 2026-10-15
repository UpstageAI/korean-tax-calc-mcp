"""의제배당(잉여금 자본전입) 끝에서 끝까지 계산기 정답 테스트 (Claude 작성 2026-10-13) — 수정 금지.
공개 검증 사례(세무사 1차 2024-64, 출처 Q-Net)는 법인세법 제16조①3호·영 제14조①1호가목으로 손계산해 공식 정답과 일치 확인. 실무형 사례는 Claude 손계산.
"""
import asyncio, json
from korean_tax_calc_mcp.server import mcp


def c(n, a):
    return json.loads(asyncio.run(mcp.call_tool(n, a)).content[0].text)


HOLDERS = [{"name": "A(자기주식)", "shares": 20_000, "self_stock": True},
           {"name": "B", "shares": 30_000}, {"name": "C", "shares": 40_000}, {"name": "D", "shares": 10_000}]


def by_name(r):
    return {h["name"]: h for h in r["결과"]["주주별"]}


def test_capital_surplus_self_stock_allotted():  # 공개 검증 사례 2024-64 사례1: 주식발행초과금 2억, 자기주식 몫을 B·C·D에 교부
    r = c("deemed_dividend_bonus_shares", {"year": 2024, "shareholder_type": "법인", "source": "주식발행초과금",
                                           "capitalized_amount": 200_000_000, "par_value": 500,
                                           "shareholders": HOLDERS, "self_stock_allotment": "다른주주에게교부"})
    h = by_name(r)
    assert h["B"]["배정주식수"] == 150_000 and h["C"]["배정주식수"] == 200_000 and h["D"]["배정주식수"] == 50_000
    assert h["B"]["의제배당"] == 15_000_000 and h["C"]["의제배당"] == 20_000_000 and h["D"]["의제배당"] == 5_000_000
    assert h["A(자기주식)"]["의제배당"] == 0


def test_capital_surplus_self_stock_not_allotted():  # 2024-64 사례2: 자기주식 몫 미교부 → 사례1과의 차이 B 300만·C 400만·D 100만(정답 ④)
    r = c("deemed_dividend_bonus_shares", {"year": 2024, "shareholder_type": "법인", "source": "주식발행초과금",
                                           "capitalized_amount": 200_000_000, "par_value": 500,
                                           "shareholders": HOLDERS, "self_stock_allotment": "미교부"})
    h = by_name(r)
    assert h["B"]["배정주식수"] == 120_000 and h["C"]["배정주식수"] == 160_000 and h["D"]["배정주식수"] == 40_000
    assert h["B"]["의제배당"] == 12_000_000 and h["C"]["의제배당"] == 16_000_000 and h["D"]["의제배당"] == 4_000_000
    assert r["결과"]["전입후총주식수"] == 420_000


def test_taxable_source_full_par_value():  # 실무형: 이익잉여금 재원이면 받은 주식 × 액면 전액 의제배당
    r = c("deemed_dividend_bonus_shares", {"year": 2025, "shareholder_type": "개인", "source": "이익잉여금",
                                           "capitalized_amount": 200_000_000, "par_value": 500,
                                           "shareholders": HOLDERS, "self_stock_allotment": "미교부"})
    h = by_name(r)
    assert h["B"]["의제배당"] == 60_000_000 and h["C"]["의제배당"] == 80_000_000 and h["D"]["의제배당"] == 20_000_000
    assert "소득세법" in json.dumps(r, ensure_ascii=False)       # 개인 주주 → 소득세법 근거


def test_no_self_stock_no_shift():  # 실무형: 자기주식이 없으면 과세 제외 재원의 의제배당은 0
    r = c("deemed_dividend_bonus_shares", {"year": 2025, "shareholder_type": "법인", "source": "자본준비금",
                                           "capitalized_amount": 10_000_000, "par_value": 500,
                                           "shareholders": [{"name": "X", "shares": 6_000}, {"name": "Y", "shares": 4_000}],
                                           "self_stock_allotment": "미교부"})
    assert sum(hh["의제배당"] for hh in r["결과"]["주주별"]) == 0


def test_unknown_source_rejected():
    r = c("deemed_dividend_bonus_shares", {"year": 2025, "shareholder_type": "법인", "source": "감자차익",
                                           "capitalized_amount": 1_000_000, "par_value": 500,
                                           "shareholders": [{"name": "X", "shares": 100}], "self_stock_allotment": "미교부"})
    assert "error" in r


# ── CodeSolar 리뷰(PR #8) 회귀 (Claude 추가 10-13) ──
def test_self_stock_gets_nothing_when_not_allotted():  # 미교부: 자기주식 주주 배정·의제배당 0, 발행 합계 = 신주 − 자기주식 몫
    r = c("deemed_dividend_bonus_shares", {"year": 2025, "shareholder_type": "법인", "source": "이익잉여금",
                                           "capitalized_amount": 200_000_000, "par_value": 500,
                                           "shareholders": HOLDERS, "self_stock_allotment": "미교부"})
    h = by_name(r)
    assert h["A(자기주식)"]["배정주식수"] == 0 and h["A(자기주식)"]["의제배당"] == 0
    assert sum(x["배정주식수"] for x in r["결과"]["주주별"]) == 320_000 and r["결과"]["전입후총주식수"] == 420_000


def test_remainder_shares_fully_distributed():  # 교부: 단주까지 다른 주주에게 전부 배정(합계 = 신주)
    r = c("deemed_dividend_bonus_shares", {"year": 2025, "shareholder_type": "개인", "source": "주식발행초과금",
                                           "capitalized_amount": 5_000, "par_value": 500, "self_stock_allotment": "다른주주에게교부",
                                           "shareholders": [{"name": "X", "shares": 5}, {"name": "Y", "shares": 2, "self_stock": True}, {"name": "Z", "shares": 1}]})
    h = by_name(r)
    assert h["X"]["배정주식수"] == 8 and h["Z"]["배정주식수"] == 2 and h["Y"]["배정주식수"] == 0   # 10 × 5/6 = 8.33, 10 × 1/6 = 1.67 → 나머지 1주는 Z
    assert sum(x["배정주식수"] for x in r["결과"]["주주별"]) == 10


def test_summary_puts_deemed_dividend_first():  # 공개 사례 2024-64: 주주별 의제배당 요약 제공, 각 주주 항목의 첫 숫자가 의제배당
    r = c("deemed_dividend_bonus_shares", {"year": 2024, "shareholder_type": "법인", "source": "주식발행초과금",
                                           "capitalized_amount": 200_000_000, "par_value": 500, "shareholders": HOLDERS, "self_stock_allotment": "다른주주에게교부"})
    assert r["결과"]["주주별_의제배당"] == {"A(자기주식)": 0, "B": 15_000_000, "C": 20_000_000, "D": 5_000_000}
    assert list(r["결과"]["주주별"][1].keys())[:2] == ["name", "의제배당"]
