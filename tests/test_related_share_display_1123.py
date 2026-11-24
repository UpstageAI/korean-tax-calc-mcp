"""특수관계 매출·매입 비중 — 자동 제외 없음, 늘 숫자로 표시(0.72.0). 가상 회사. Claude 작성(2026-11-23).

법령·판례상 비교대상의 특수관계 거래 비중 숫자 기준이 없어 조문 MCP(0.30.0~)는 상한(related_max·related_purchase_max)과
검토선(related_sales_review·related_purchase_review)을 넘기지 않는다. 이 도구는 받은 값만 쓴다 — 상한을 주면 예전처럼 탈락(옛 조문 MCP와도 맞물림).
"""
from korean_tax_calc_mcp.engine import calc_tp_screen as T
from korean_tax_calc_mcp.engine.kr_comparables import compare as P
from korean_tax_calc_mcp.engine.kr_comparables.schema import empty_profile, value

YEARS = [2022, 2023, 2024]


def _rows(cid, name, om=0.05, **extra):
    return [{"company_id": cid, "company_name": name, "country": "KR", "industry_code": "46539", "currency": "KRW", "year": y,
             "revenue": 1000, "cogs": 800, "operating_profit": 1000 * om, "total_assets": 800, "max_shareholder_pct": 10, **extra} for y in YEARS]


def _run(rows, screens=None):
    tp = {"name": "분석대상", "is_resident": True, "years": {y: {"revenue": 100, "operating_profit": 3} for y in YEARS}}
    return T.comparable_screen(rows=rows, tested_party=tp, analysis_years=YEARS, tested_year=2024, screens=screens,
                               multi_year_reason={"code": 1, "text": "경기 변동"}, search_log={"db": "가상"})


ROWS = (_rows("A", "가", 0.04) + _rows("B", "나", 0.05)
        + _rows("H", "다", 0.06, related_party_revenue=600)               # 매출 60%
        + _rows("Q", "라", 0.07, related_party_purchase=480)              # 매입 480/800 = 60%
        + _rows("N", "마", 0.08))                                          # 자료 없음
# 조문 MCP 0.30.0 '넘길 값'의 screens(특수관계 상한 없음)
NEW_LAW_SCREENS = {"independence_pct": 25, "independence_bvd_reject": ["C", "D", "U"], "loss_years": 2, "crisis_exception": False,
                   "rnd_max": 0.03, "adv_max": 0.05, "segment_min": 0.75, "size_min": None, "size_max": None, "outlier_k": 1.5}


def _mx(r):
    return {m["company_id"]: m for m in r["탈락_매트릭스"]}


def test_no_exclusion_by_related_share_without_cap():
    for screens in (None, NEW_LAW_SCREENS):
        r = _run(ROWS, screens)
        m = _mx(r)
        assert r["결과"]["최종_수"] == 5 and all(m[c]["최종"] == "선정" for c in "ABHQN")
        assert m["H"]["S9"].startswith("건너뜀") and m["Q"]["S9b"].startswith("건너뜀")
    assert T.DEFAULT_SCREENS["related_max"] is None and T.DEFAULT_SCREENS["related_purchase_max"] is None


def test_shares_always_shown_as_numbers():
    r = _run(ROWS, NEW_LAW_SCREENS)
    m = _mx(r)
    assert m["H"]["특수관계_매출%"] == 60.0 and m["H"]["특수관계_매입%"] is None
    assert m["Q"]["특수관계_매입%"] == 60.0 and m["Q"]["특수관계_매출%"] is None
    assert m["N"]["특수관계_매출%"] is None and m["N"]["특수관계_매입%"] is None
    fin = {x["company_id"]: x for x in r["최종_비교대상"]}
    assert fin["H"]["특수관계_매출%"] == 60.0 and fin["Q"]["특수관계_매입%"] == 60.0


def test_explicit_cap_still_excludes_backward_compatible():
    """옛 조문 MCP(0.29.0 이하)가 related_max·related_purchase_max를 넘기면 그 값으로 탈락 — 오류 없이."""
    r = _run(ROWS, {**NEW_LAW_SCREENS, "related_max": 0.25, "related_purchase_max": 0.25})
    m = _mx(r)
    assert m["H"]["S9"].startswith("탈락") and m["Q"]["S9b"].startswith("탈락") and r["결과"]["최종_수"] == 3
    assert m["H"]["특수관계_매출%"] == 60.0                  # 탈락해도 숫자는 표시
    crit = {c["기준"]: c for c in r["보고서_부록"]["탐색_조건"]["적용_기준"]}
    assert crit["S9 특수관계 매출 상한"]["입력"] == "사용자 입력" and "숫자 기준 없음" in crit["S9 특수관계 매출 상한"]["성격"]
    crit = {c["기준"]: c for c in _run(ROWS, NEW_LAW_SCREENS)["보고서_부록"]["탐색_조건"]["적용_기준"]}
    assert crit["S9 특수관계 매출 상한"]["값"] == "꺼짐"


def _prof(cid, rs=None, rp=None):
    p = empty_profile(company_id=cid, company_name=cid)
    p.update({"main_category": value("merchandise"), "main_share": value(0.9), "inv_to_sales": value(0.15), "ppe_ratio": value(0.05),
              "raw_material_inv": value(False)})
    if rs is not None:
        p["related_sales_ratio"] = value(rs)
    if rp is not None:
        p["related_purchase_ratio"] = value(rp)
    return p


TESTED = {"main_category": "merchandise", "main_share": 0.9, "inventory_basis": "ratio", "inv_to_sales": 0.15, "ppe_ratio": 0.05}
NEW_LAW_RULES = {"mix_max_diff": 0.2, "ratio_low": 0.5, "ratio_high": 2.0, "ppe_abs_tol": 0.05, "rnd_abs_tol": 0.01, "advert_abs_tol": 0.01,
                 "coverage_min": 0.8, "coverage_max": 1.2, "independence_legal_pct": 50.0, "control_dependence": 0.5,
                 "unknown_review_count": 3, "mix_unverified_review": 0.1}


def test_profile_table_shows_shares_and_flags_at_50():
    out = P.run_tool(TESTED, [_prof("저", 0.1, 0.2), _prof("매출", 0.5), _prof("매입", 0.05, 0.6), _prof("없음")], NEW_LAW_RULES)
    t = {r["company_id"]: r for r in out["결과"]["비교표"]}
    assert t["저"]["특수관계_거래_비중"]["매출"] == 0.1 and t["저"]["특수관계_거래_비중"]["매입"] == 0.2
    assert not any(x.startswith(("[C2]", "[I2]")) for x in t["저"]["사유"])          # 50% 아래 — 숫자만
    assert t["없음"]["특수관계_거래_비중"]["매출"] is None
    for c in ("매출", "매입"):
        assert t[c]["종합"] == "사람 확인" and any(x.startswith("[C2]") for x in t[c]["사유"])
    assert not any(r["종합"] == "제외 후보" for r in t.values())


def test_old_handoff_keys_still_accepted():
    """옛 조문 MCP 이름(related_sales_review·related_purchase_review)도 받음 — 배포 순서와 상관없이 오류 없음."""
    out = P.run_tool(TESTED, [_prof("가", 0.3)], {**NEW_LAW_RULES, "related_sales_review": 0.25, "related_purchase_review": 0.25})
    row = out["결과"]["비교표"][0]
    assert row["종합"] == "사람 확인" and any("[I2]" in x and "입력한 검토선" in x for x in row["사유"])
