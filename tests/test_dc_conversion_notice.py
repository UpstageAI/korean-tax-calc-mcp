"""확정기여형 전환 회사 고지 정답 테스트 (Claude 2026-11-06).

전환 전 근무분 퇴직급여충당금(법인세법 시행규칙 제31조②)이 남은 회사는 도구가 일부만 처리하므로 판단에 '확인 필요'로 알린다.
처리하지 않는 것: 그 금액 계산(직전 사업연도말 누적액 × 확정기여형 설정자 추계액 비율), 확정기여형만 있는 회사의 입력,
그 몫의 지급·이전, 그 몫 관련 부인누계 구분.
"""
from test_form_templates import c

BASE = {"year": 2025, "allowance": {"opening": 100_000_000, "provision": 10_000_000, "closing": 110_000_000},
        "prior_disallowed": 0, "estimate": {"lump_sum": 300_000_000}, "salary": {"total": 500_000_000}}


def _notice(r):
    return [x for x in r["판단"] if x.get("항목") == "확정기여형 전환 회사"]


def test_notice_when_dc_members_exist():
    r = c("retirement_allowance_adjustment", dict(BASE, salary={"total": 500_000_000, "dc_members": 100_000_000}))
    n = _notice(r)
    assert len(n) == 1 and n[0]["결론"].startswith("확인 필요")
    s = n[0]["결론"]
    for word in ("제31조②", "확정기여형만", "지급", "이전", "부인누계", "세무 전문가"):
        assert word in s, word
    assert "시행규칙 제31조②" in n[0]["근거"]


def test_notice_when_transferred_allowance_given():
    a = dict(BASE, pension={"asset_closing": 50_000_000, "prior_deducted": 0, "dc_transferred_allowance": 20_000_000})
    assert len(_notice(c("retirement_allowance_adjustment", a))) == 1


def test_no_notice_without_dc():
    assert _notice(c("retirement_allowance_adjustment", BASE)) == []


def test_description_mentions_limit():
    import asyncio
    from korean_tax_calc_mcp.server import mcp
    tools = {t.name: t for t in asyncio.run(mcp.list_tools())}
    assert "제31조제2항" in tools["retirement_allowance_adjustment"].description
