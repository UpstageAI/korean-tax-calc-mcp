"""확정기여형 전환 — 설정 전 계상 퇴직급여충당금 정답 테스트 (Claude 2026-11-06, 2026-11-15 개정).

대조한 원문: 법인세법 시행규칙 제31조②(2026.7.1. 시행본), 별지 제32호서식(2026.7.1. 시행본) 작성방법 2·3·4·8.
⑤ 설정 전 계상 충당금 = 직전 사업연도말 누적액 × (해당 사업연도 확정기여형 설정자의 직전 사업연도말 추계액 ÷ 전원 추계액).
⑦ 기초충당금 부인누계액에서 설정 전 충당금 관련 부인액은 제외. 설정 전 근무기간분 부담금 지출은 ⑤에서 먼저 지출(법인세과-1032, 2009.9.21.·법인세과-4271, 2008.12.30.).
"""
from test_form_templates import c

BASE = {"year": 2025, "allowance": {"opening": 100_000_000, "provision": 10_000_000, "closing": 110_000_000},
        "prior_disallowed": 0, "estimate": {"lump_sum": 300_000_000}, "salary": {"total": 500_000_000}}


def _items(r, prefix):
    return [x for x in r["판단"] if x.get("항목", "").startswith(prefix)]


def test_dc_members_only_asks_for_input():
    r = c("retirement_allowance_adjustment", dict(BASE, salary={"total": 500_000_000, "dc_members": 100_000_000}))
    n = _items(r, "확정기여형 설정자")
    assert len(n) == 1 and "dc_conversion" in n[0]["결론"] and "제31조②" in n[0]["근거"]


def test_ratio_computation_without_db_pension():
    # 누적액 100,000,000 × 설정자 추계액 60,000,000 ÷ 전원 추계액 240,000,000 = 25,000,000 (확정급여형 퇴직연금 없이도 입력)
    a = dict(BASE, allowance=dict(BASE["allowance"], dc_conversion={"prior_estimate_total": 240_000_000, "prior_estimate_dc": 60_000_000}))
    r = c("retirement_allowance_adjustment", a)
    n = _items(r, "확정기여형 전환 — 설정 전 기계상")
    assert len(n) == 1 and "25,000,000원" in n[0]["결론"] and "작성방법" in n[0]["근거"]
    # 퇴직금전환금 90,000,000이 있으면 누적한도 = 90,000,000 − (100,000,000 − 25,000,000) = 15,000,000 ≥ 설정 10,000,000 → 한도초과 없음.
    # 설정 전 충당금을 빼지 않으면 90,000,000 − 100,000,000 < 0 → 10,000,000 전액 한도초과
    with_dc = c("retirement_allowance_adjustment", dict(a, conversion_fund=90_000_000))
    without = c("retirement_allowance_adjustment", dict(BASE, conversion_fund=90_000_000))
    assert with_dc["결과"]["손금불산입_합계"] == 0 and without["결과"]["손금불산입_합계"] == 10_000_000
    # 직접 입력(amount)·기존 pension.dc_transferred_allowance 입력과 같은 결과
    b = dict(BASE, conversion_fund=90_000_000, allowance=dict(BASE["allowance"], dc_conversion={"amount": 25_000_000}))
    assert c("retirement_allowance_adjustment", b)["결과"] == with_dc["결과"]


def test_related_disallowed_is_excluded_from_opening_disallowed():
    # 전체 부인누계 30,000,000 가운데 설정 전 충당금 관련 10,000,000 → ⑦ = 20,000,000 (작성방법 3)
    a = dict(BASE, prior_disallowed=30_000_000,
             allowance=dict(BASE["allowance"], dc_conversion={"amount": 25_000_000, "related_disallowed": 10_000_000}))
    b = dict(BASE, prior_disallowed=20_000_000, allowance=dict(BASE["allowance"], dc_conversion={"amount": 25_000_000}))
    ra, rb = c("retirement_allowance_adjustment", a), c("retirement_allowance_adjustment", b)
    assert ra["결과"] == rb["결과"] and ra["계산"] == rb["계산"]
    assert "20,000,000원" in _items(ra, "확정기여형 전환 — 설정 전 기계상")[0]["결론"]
    bad = dict(BASE, prior_disallowed=5_000_000, allowance=dict(BASE["allowance"], dc_conversion={"amount": 25_000_000, "related_disallowed": 10_000_000}))
    assert "error" in c("retirement_allowance_adjustment", bad)


def test_payout_is_taken_from_pre_setup_allowance_first():
    # 법인세과-1032(2009.9.21.): 설정 전 근무기간분 부담금 지출액은 누적액에서 차감된 충당금(⑤)에서 먼저 지출한 것으로 봄
    al = {"opening": 100_000_000, "provision": 10_000_000, "paid_cash": 30_000_000, "closing": 80_000_000}
    a = dict(BASE, allowance=dict(al, dc_conversion={"amount": 25_000_000, "paid": 30_000_000}))
    r = c("retirement_allowance_adjustment", a)
    n = _items(r, "확정기여형 전환 — 설정 전 근무기간분 부담금 지출")
    assert len(n) == 1 and "25,000,000원은" in n[0]["결론"] and "초과 5,000,000원" in n[0]["결론"] and "법인세과-1032" in n[0]["근거"]
    # ⑤에서 25,000,000을 먼저 쓰고 5,000,000만 그 밖의 충당금 지급 → 설정 전 충당금 없이 5,000,000을 지급한 회사(기초 75,000,000)와 같은 세무조정
    b = dict(BASE, allowance={"opening": 75_000_000, "provision": 10_000_000, "paid_cash": 5_000_000, "closing": 80_000_000})
    assert r["결과"] == c("retirement_allowance_adjustment", b)["결과"]
    # 지출을 따로 넣지 않으면 입력 안내만
    n0 = _items(c("retirement_allowance_adjustment", dict(BASE, allowance=dict(BASE["allowance"], dc_conversion={"amount": 25_000_000}))), "확정기여형 전환 — 설정 전 근무기간분 부담금 지출")
    assert "dc_conversion.paid" in n0[0]["결론"]
    assert "error" in c("retirement_allowance_adjustment", dict(BASE, allowance=dict(al, dc_conversion={"amount": 25_000_000, "paid": 31_000_000})))


def test_both_inputs_rejected_and_no_notice_without_dc():
    a = dict(BASE, pension={"asset_closing": 50_000_000, "prior_deducted": 0, "dc_transferred_allowance": 20_000_000},
             allowance=dict(BASE["allowance"], dc_conversion={"amount": 20_000_000}))
    assert "error" in c("retirement_allowance_adjustment", a)
    assert _items(c("retirement_allowance_adjustment", BASE), "확정기여형") == []


def test_description_mentions_rule():
    import asyncio
    from korean_tax_calc_mcp.server import mcp
    tools = {t.name: t for t in asyncio.run(mcp.list_tools())}
    d = tools["retirement_allowance_adjustment"].description
    assert "제31조제2항" in d and "dc_conversion" in d
