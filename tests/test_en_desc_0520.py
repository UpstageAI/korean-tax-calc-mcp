"""0.52.0 도구 설명 영문 한 줄 — 영어 질의로 도구를 찾을 수 있게.

- 모든 도구 설명 첫 줄은 ASCII 영문으로 시작하고 괄호 안 국문 용어를 함께 쓴다(docs/glossary_ko_en.md).
- find_tool은 영어 질의(외국 기업·주재원 포함)에도 목표 도구를 상위 3위 안에 돌려준다.
- 거주자 판정(tax residency)은 계산 도구가 없으므로 korean-tax-mcp residency_check로 보낸다.
  대조: 소득세법 제1조의2(정의 — 거주자), 시행령 제2조(주소와 거소의 판정)·제3조(해외현지법인 임직원 등의 거주자 판정),
  법제처 영문법령(소득세법 2024.5.17. 시행본, 시행령 2026.2.27. 시행본) 조 제목으로 확인.
- 회귀: financial_income_aggregate 출자공동사업자배당 + 외국법인배당 + 상장배당 + 고배당기업배당(분리 선택)
  — 소득세법 제14조제3항제6호, 제17조, 제56조, 조특법 제104조의27(2026.1.1. 이후 받는 배당).
"""
import re
from importlib.metadata import PackageNotFoundError, version

import pytest

from korean_tax_calc_mcp import server as S

TOOLS = {t.name: t for t in S.mcp._tool_manager.list_tools()}


def _first_line(name: str) -> str:
    return next(ln.strip() for ln in (TOOLS[name].description or "").splitlines() if ln.strip())


@pytest.mark.parametrize("name", sorted(TOOLS))
def test_first_line_english_with_korean_term(name):
    line = _first_line(name)
    assert line[:1].isascii() and line[:1].isalpha(), (name, line)
    head = line.split("(", 1)[0]
    assert head.isascii() and len(head.split()) >= 2, (name, line)
    assert re.search(r"\([^()]*[가-힣][^()]*\)", line), (name, line)


def test_every_registered_tool_has_english_line_and_korean_body():
    for name, t in TOOLS.items():
        lines = [ln.strip() for ln in (t.description or "").splitlines() if ln.strip()]
        assert len(lines) >= 2 and re.search(r"[가-힣]", lines[1]), name  # 국문 설명은 그대로 둘째 줄부터
        assert "언제" in t.description, name


def test_find_tool_doc_does_not_hardcode_count():
    assert "70개" not in TOOLS["find_tool"].description
    assert "도구가 많으니" in TOOLS["find_tool"].description


def _top(query, n=3):
    r = S.find_tool(query=query)
    return [c["도구"] for c in r["결과"]["후보"][:n]]


@pytest.mark.parametrize("query,target", [
    ("entertainment expense limit", "entertainment_limit"),
    ("late payment penalty", "late_payment_penalty"),
    ("corporate income tax", "corporate_tax"),
    ("royalty withholding nonresident", "nonresident_withholding"),
    ("nonresident withholding royalty", "nonresident_withholding"),
    ("wage income tax", "wage_income_tax"),
    # 외국 기업·주재원
    ("foreign tax credit", "foreign_tax_credit"),
    ("thin capitalization", "thin_capitalization"),
    ("transfer pricing arm's length range", "arm_length_range"),
    ("foreign subsidiary dividend", "foreign_subsidiary_dividend"),
    ("expat cost recharge", "expat_cost_recharge"),
    ("business promotion expenses", "entertainment_limit"),
])
def test_find_tool_english_query_top3(query, target):
    assert target in _top(query), (query, _top(query, 5))


def test_find_tool_tax_residency_points_to_law_mcp():
    r = S.find_tool(query="tax residency")["결과"]
    assert r["후보"] == []
    assert "residency_check" in r["korean-tax-mcp 도구"]
    assert {"law_name": "소득세법", "article": "제1조의2"}.items() <= r["근거 조회"][0].items()


def test_find_tool_korean_queries_unchanged():
    assert "entertainment_limit" in _top("접대비 한도")
    assert "nonresident_withholding" in _top("비거주자 원천징수")
    assert S.find_tool(query="종부세")["결과"]["후보"] == []


def test_find_tool_candidate_shows_korean_description():
    c = S.find_tool(query="entertainment expense limit")["결과"]["후보"][0]
    assert c["설명"].startswith("Entertainment") and re.search(r"[가-힣]", c["국문 설명"])


def test_server_info_version_from_package_metadata():
    try:
        expected = version("korean-tax-calc-mcp")
    except PackageNotFoundError:
        pytest.skip("패키지 미설치")
    assert S.mcp._lowlevel_server.version == expected != ""


def test_financial_income_partner_dividend_with_high_dividend_separate():
    """PR #159 리뷰 확인 사례 — 출자공동사업자배당은 판정합계에서 빼고 항상 합산."""
    r = S.financial_income_aggregate(year=2026, items=[
        {"kind": "출자공동사업자배당", "amount": 5_000_000},
        {"kind": "외국법인배당", "amount": 8_000_000},
        {"kind": "상장법인현금배당", "amount": 10_000_000, "paid_date": "2026-06-30"},
        {"kind": "고배당기업배당", "amount": 5_000_000, "separate_election": True},
    ])["결과"]
    # 판정합계 = 8,000,000 + 10,000,000 = 18,000,000 ≤ 20,000,000 → 분리과세, 합산액 = 출자공동사업자배당 5,000,000
    assert r["합산액"] == 5_000_000 and r["분리과세"] is True and r["Gross-up"] == 0
    # 특례배당을 기준금액 판정에 넣으면(영 제116조의2 순서: 이자 0 → 비대상 8,000,000 → 특례 5,000,000 → 대상 10,000,000)
    # 2천만원을 넘는 상장배당 3,000,000 × 10% = Gross-up 300,000
    # 합산액 = 8,000,000 + 10,000,000 + 300,000 + 출자공동 5,000,000 = 23,300,000 (특례배당은 분리 산출세액)
    alt = r["기준금액_포함시"]
    assert alt["Gross-up"] == 300_000 and alt["합산액"] == 23_300_000 and alt["분리과세"] is False
