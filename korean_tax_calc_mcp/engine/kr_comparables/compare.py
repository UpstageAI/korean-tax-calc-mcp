"""분석대상 프로필 × 후보 프로필 → 항목별 가까움/다름/불명 + 종합. 순수 함수. Claude 작성(2026-11-16).

기준값은 모두 '기본값(조정 가능)' — 국조법령에 숫자가 없는 실무 판단용 출발점이다. 결과에 사용 기준을 그대로 싣는다.

항목
1. revenue_mix(핵심): 분석대상 주된 갈래(main_category)의 후보 비중과 분석대상 비중 차이 ≤ mix_max_diff → 가까움.
   후보 커버리지가 coverage_min~coverage_max 밖이거나 매출 구성 불명이면 불명.
2. inventory(핵심): 분석대상 inventory_basis가
   - "ratio": 재고/매출이 분석대상의 ratio_low~ratio_high배 → 가까움(재고 계정 없음=0은 다름)
   - "raw_material": 원재료·재공품 재고 유무가 같으면 가까움
3. ppe(핵심): 유형자산/자산이 ratio_low~ratio_high배이거나 차이 ≤ ppe_abs_tol → 가까움
4. rnd, 5. advert(보조): 같은 방식(차이 허용 rnd_abs_tol·advert_abs_tol). '불명-없음'(계정 없음)은 0으로 비교.
6. raw_material(보조): inventory_basis가 "ratio"이고 분석대상 raw_material_inv가 주어지면 유무 비교.
독립성: 최대주주 ≥ independence_legal_pct(법정 하한, 국조법 시행령 제2조②) → 제외 후보.
        특수관계 매출 ≥ related_sales_review → 포함 후보를 사람 확인으로.
종합: 핵심 다름 ≥ 1 → 제외 후보 / 핵심 불명 ≥ 1 또는 전체 불명 ≥ unknown_review_count → 사람 확인 / 나머지 포함 후보.
경계값은 포함(≤, 0.5배·2배 포함).
"""
import copy

from .schema import STATUS_OK, STATUS_NONE

DEFAULT_RULES = {
    "mix_max_diff": 0.20,
    "ratio_low": 0.5, "ratio_high": 2.0,
    "ppe_abs_tol": 0.05, "rnd_abs_tol": 0.01, "advert_abs_tol": 0.01,
    "coverage_min": 0.8, "coverage_max": 1.2,
    "independence_legal_pct": 50.0, "related_sales_review": 0.25,
    "unknown_review_count": 3,
}
ITEMS = {"revenue_mix": "매출 구성", "inventory": "재고", "ppe": "유형자산", "rnd": "연구개발", "advert": "광고판촉", "raw_material": "원재료 재고"}
CORE = ("revenue_mix", "inventory", "ppe")
NEAR, DIFF, UNK = "가까움", "다름", "불명"
EPS = 1e-12


def _num(cell, zero_if_none_status=True):
    """프로필 값 → 비교용 숫자. 불명-없음은 0, 불명-못찾음은 None."""
    if not isinstance(cell, dict):
        return cell
    if cell.get("status") == STATUS_OK:
        return cell.get("value")
    if cell.get("status") == STATUS_NONE and zero_if_none_status:
        return 0.0 if not isinstance(cell.get("value"), bool) else cell.get("value")
    return None


def _flag(cell):
    """원재료 재고 유무 → True/False/None. 불명-없음은 '없음'(False)."""
    if not isinstance(cell, dict):
        return cell
    if cell.get("status") == STATUS_OK:
        return bool(cell.get("value"))
    if cell.get("status") == STATUS_NONE:
        return False
    return None


def _ratio_near(c, t, low, high, abs_tol):
    if c is None or t is None:
        return UNK
    if t == 0:
        return NEAR if abs(c) <= abs_tol + EPS else DIFF
    lo, hi = sorted((low * t, high * t))
    if lo - EPS <= c <= hi + EPS or abs(c - t) <= abs_tol + EPS:
        return NEAR
    return DIFF


def compare_profile(tested, cand, rules=None):
    """tested: {main_category, main_share, inventory_basis('ratio'|'raw_material'), inv_to_sales, raw_material_inv,
                ppe_ratio, rnd_ratio, advert_ratio}
    cand: 표준 프로필(schema.PROFILE_FIELDS, 값은 value() 형식)."""
    r = copy.deepcopy(DEFAULT_RULES)
    r.update(rules or {})
    items = {}
    # 1 매출 구성
    cov = _num(cand.get("mix_coverage"), False)
    share = _num(cand.get("mix_" + tested["main_category"]), False)
    if share is None or cov is None or not (r["coverage_min"] - EPS <= cov <= r["coverage_max"] + EPS):
        v = UNK
    else:
        v = NEAR if abs(share - tested["main_share"]) <= r["mix_max_diff"] + EPS else DIFF
    items["revenue_mix"] = {"verdict": v, "candidate": share, "tested": tested["main_share"], "coverage": cov,
                            "rule": f"{tested['main_category']} 비중 차이 ≤ {r['mix_max_diff']:.0%}p, 커버리지 {r['coverage_min']}~{r['coverage_max']}"}
    # 2 재고
    if tested.get("inventory_basis", "ratio") == "raw_material":
        c = _flag(cand.get("raw_material_inv")); t = bool(tested.get("raw_material_inv"))
        items["inventory"] = {"verdict": UNK if c is None else (NEAR if c == t else DIFF), "candidate": c, "tested": t, "rule": "원재료·재공품 재고 유무 같음"}
    else:
        c = _num(cand.get("inv_to_sales")); t = tested.get("inv_to_sales")
        items["inventory"] = {"verdict": _ratio_near(c, t, r["ratio_low"], r["ratio_high"], 0.0), "candidate": c, "tested": t,
                              "rule": f"재고/매출 {r['ratio_low']}~{r['ratio_high']}배"}
    # 3 유형자산, 4·5 연구개발·광고
    for key, fld, tol in (("ppe", "ppe_ratio", "ppe_abs_tol"), ("rnd", "rnd_ratio", "rnd_abs_tol"), ("advert", "advert_ratio", "advert_abs_tol")):
        c = _num(cand.get(fld)); t = tested.get(fld)
        items[key] = {"verdict": _ratio_near(c, t, r["ratio_low"], r["ratio_high"], r[tol]) if t is not None else UNK,
                      "candidate": c, "tested": t, "rule": f"{r['ratio_low']}~{r['ratio_high']}배 또는 차이 ≤ {r[tol]:.0%}p"}
    # 6 원재료(보조)
    if tested.get("inventory_basis", "ratio") == "ratio" and tested.get("raw_material_inv") is not None:
        c = _flag(cand.get("raw_material_inv")); t = bool(tested["raw_material_inv"])
        items["raw_material"] = {"verdict": UNK if c is None else (NEAR if c == t else DIFF), "candidate": c, "tested": t, "rule": "원재료·재공품 재고 유무 같음"}
    # 독립성
    ms = _num(cand.get("max_shareholder_pct"), False); rs = _num(cand.get("related_sales_ratio"), False)
    indep = []
    legal = ms is not None and ms >= r["independence_legal_pct"] - EPS
    if legal:
        indep.append(f"최대주주 {ms}% ≥ {r['independence_legal_pct']:g}%(법정 하한)")
    review_rel = rs is not None and rs >= r["related_sales_review"] - EPS
    if review_rel:
        indep.append(f"특수관계 매출 {rs:.0%} ≥ {r['related_sales_review']:.0%}")
    # 종합
    core_v = [items[k]["verdict"] for k in CORE]
    all_v = [x["verdict"] for x in items.values()]
    if DIFF in core_v or legal:
        overall = "제외 후보"
    elif UNK in core_v or all_v.count(UNK) >= r["unknown_review_count"]:
        overall = "사람 확인"
    else:
        overall = "포함 후보"
    if overall == "포함 후보" and review_rel:
        overall = "사람 확인"
    reasons = [f"{ITEMS[k]} {items[k]['verdict']}" for k in CORE if items[k]["verdict"] != NEAR] + indep
    return {"company_id": cand.get("company_id"), "company_name": cand.get("company_name"), "items": items,
            "independence": indep or ["문제 없음" if ms is not None else "최대주주 지분 불명"], "overall": overall,
            "reasons": reasons or ["핵심 항목 가까움"], "rules_used": r}


def compare_many(tested, candidates, rules=None):
    rows = [compare_profile(tested, c, rules) for c in candidates]
    counts = {k: sum(1 for x in rows if x["overall"] == k) for k in ("포함 후보", "사람 확인", "제외 후보")}
    used = copy.deepcopy(DEFAULT_RULES); used.update(rules or {})
    return {"rows": rows, "counts": counts, "rules_used": used, "note": "기준값은 기본값(조정 가능) — 법령 숫자 아님. 사람 확인 후보는 근거를 보고 포함·제외(이유 필수)."}
