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
    "mix_unverified_review": 0.10,   # 원문 매출유형 칸·계정명이 아닌 분류(모델·규칙)로 정한 매출 행이 매출 구성의 10% 이상이면 포함 후보를 사람 확인으로
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
    bound = None
    if share is None or cov is None or not (r["coverage_min"] - EPS <= cov <= r["coverage_max"] + EPS):
        v = UNK
        # 제품·상품 배분만 불명이고 나머지 갈래가 확보면 상한(1 − 나머지 합)으로도 판정할 수 있다
        if share is None and cov is not None and r["coverage_min"] - EPS <= cov <= r["coverage_max"] + EPS and tested["main_category"] in ("product", "merchandise"):
            others = [k for k in ("service", "sw_license", "platform_fee", "other")]
            vals = [_num(cand.get("mix_" + k), False) for k in others]
            if all(x is not None for x in vals):
                bound = max(0.0, 1 - sum(vals))
                if bound < tested["main_share"] - r["mix_max_diff"] - EPS:
                    v = DIFF
    else:
        v = NEAR if abs(share - tested["main_share"]) <= r["mix_max_diff"] + EPS else DIFF
    mcell = cand.get("mix_" + tested["main_category"])
    mnote = mcell.get("note", "") if isinstance(mcell, dict) and v == UNK else (
        f"제품·상품 배분은 불명이나 상한 {bound:.0%}로도 차이가 큼" if bound is not None else "")
    items["revenue_mix"] = {"verdict": v, "candidate": share, "tested": tested["main_share"], "coverage": cov, "note": mnote,
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
    unv, unv_rows = _unverified_mix(cand)
    if unv is not None and unv >= r["mix_unverified_review"] - EPS:
        indep_note = f"매출 행 분류 확인 필요 — 원문 유형 칸이 없는 행 {unv:.0%}({', '.join(unv_rows[:3])})를 모델·규칙으로 분류"
        if overall == "포함 후보":
            overall = "사람 확인"
        items["revenue_mix"]["review"] = indep_note
    reasons = [f"{ITEMS[k]} {items[k]['verdict']}" + (f" — {items[k]['note']}" if items[k].get("note") else "") for k in CORE if items[k]["verdict"] != NEAR] + indep
    if items["revenue_mix"].get("review"):
        reasons.append(items["revenue_mix"]["review"])
    unk = [ITEMS[k] for k, x in items.items() if x["verdict"] == UNK and k not in CORE]
    if overall == "사람 확인" and all_v.count(UNK) >= r["unknown_review_count"]:
        reasons.append(f"불명 {all_v.count(UNK)}개(" + ", ".join([ITEMS[k] for k in CORE if items[k]["verdict"] == UNK] + unk) + ")")
    return {"company_id": cand.get("company_id"), "company_name": cand.get("company_name"), "items": items,
            "independence": indep or ["문제 없음" if ms is not None else "최대주주 지분 불명"], "overall": overall,
            "reasons": reasons or ["핵심 항목 가까움"], "rules_used": r}


def _unverified_mix(cand):
    """매출 구성 근거 행 중 원문 유형·계정명이 아닌 분류로 정한 행의 비중."""
    mc = cand.get("mix_coverage")
    rows = (mc or {}).get("evidence", {}).get("rows") if isinstance(mc, dict) else None
    if not rows:
        return None, []
    tot = sum(abs(x.get("amount") or 0) for x in rows)
    bad = [x for x in rows if not str(x.get("reason", "")).startswith(("원문", "회계 기준 배분"))]
    if not tot:
        return None, []
    return sum(abs(x.get("amount") or 0) for x in bad) / tot, [str(x.get("label", ""))[:30] for x in bad]


def compare_many(tested, candidates, rules=None):
    rows = [compare_profile(tested, c, rules) for c in candidates]
    counts = {k: sum(1 for x in rows if x["overall"] == k) for k in ("포함 후보", "사람 확인", "제외 후보")}
    used = copy.deepcopy(DEFAULT_RULES); used.update(rules or {})
    return {"rows": rows, "counts": counts, "rules_used": used, "note": "기준값은 기본값(조정 가능) — 법령 숫자 아님. 사람 확인 후보는 근거를 보고 포함·제외(이유 필수)."}


MAIN_CATS = ("product", "merchandise", "service", "sw_license", "platform_fee", "other")
DRAFT_STATE = "초안 — 사람이 사유·근거를 확인한 뒤 확정(확정 전에는 tp_comparable_screen에 넣지 않음)"


def _profiles_from(candidates):
    """kr_comparable_candidates 출력 그대로({'결과': {'후보_프로필': [...]}}·{'후보_프로필': [...]}) 또는 프로필 목록."""
    if isinstance(candidates, dict):
        candidates = candidates.get("결과", candidates).get("후보_프로필")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("candidates는 후보 프로필 목록(또는 kr_comparable_candidates 결과)")
    return candidates


def _check_tested(t):
    if t.get("main_category") not in MAIN_CATS:
        raise ValueError(f"tested.main_category는 {MAIN_CATS} 중 하나")
    if not isinstance(t.get("main_share"), (int, float)) or not 0 <= t["main_share"] <= 1:
        raise ValueError("tested.main_share는 0~1 비율")
    if t.get("inventory_basis", "ratio") not in ("ratio", "raw_material"):
        raise ValueError("tested.inventory_basis는 ratio|raw_material")
    if t.get("inventory_basis", "ratio") == "ratio" and t.get("inv_to_sales") is None:
        raise ValueError("inventory_basis=ratio이면 tested.inv_to_sales(재고/매출)가 필요")
    if t.get("inventory_basis") == "raw_material" and t.get("raw_material_inv") is None:
        raise ValueError("inventory_basis=raw_material이면 tested.raw_material_inv(true|false)가 필요")
    for k in ("ppe_ratio", "rnd_ratio", "advert_ratio", "inv_to_sales"):
        v = t.get(k)
        if v is not None and (not isinstance(v, (int, float)) or v < 0):
            raise ValueError(f"tested.{k}는 0 이상 비율")


def _evidence(cand, item):
    fld = {"revenue_mix": "mix_coverage", "inventory": "inv_to_sales", "ppe": "ppe_ratio", "rnd": "rnd_ratio", "advert": "advert_ratio", "raw_material": "raw_material_inv"}[item]
    c = cand.get(fld) or {}
    e = {"상태": c.get("status"), **(c.get("evidence") or {})}
    if c.get("note"):
        e["메모"] = c["note"]
    return e


def run_tool(tested, candidates, rules=None):
    """kr_comparable_profile_compare 본체 — {'결과', '근거', '주의'}."""
    _check_tested(tested)
    profs = _profiles_from(candidates)
    unknown = [k for k in (rules or {}) if k not in DEFAULT_RULES]
    if unknown:
        raise ValueError(f"rules에 모르는 키: {unknown} — 쓸 수 있는 키: {sorted(DEFAULT_RULES)}")
    m = compare_many(tested, profs, rules)
    table, review, drafts = [], [], []
    for p, x in zip(profs, m["rows"]):
        row = {"company_id": x["company_id"], "company_name": x["company_name"], "종합": x["overall"], "사유": x["reasons"], "독립성": x["independence"],
               **{ITEMS[k]: {"판정": v["verdict"], "후보": v["candidate"], "분석대상": v["tested"]} for k, v in x["items"].items()}}
        table.append(row)
        if x["overall"] == "사람 확인":
            review.append({"company_id": x["company_id"], "company_name": x["company_name"], "사유": x["reasons"],
                           "근거": {ITEMS[k]: _evidence(p, k) for k, v in x["items"].items() if v["verdict"] != NEAR or v.get("review")},
                           "매출_행": ((p.get("mix_coverage") or {}).get("evidence") or {}).get("rows", [])[:20],
                           "선택지": "확인 뒤 포함하면 그대로 두고, 빼려면 manual_decisions에 {decision: reject, reason} 추가"})
        elif x["overall"] == "제외 후보":
            drafts.append({"company_id": x["company_id"], "decision": "reject",
                           "reason": "프로필 비교(기능·자산·위험): " + "; ".join(x["reasons"]),
                           "evidence": "; ".join(f"{ITEMS[k]} {v['verdict']}(후보 {v['candidate']}, 분석대상 {v['tested']}) 근거 {p.get('rcept_no') or ''}"
                                                for k, v in x["items"].items() if k in CORE),
                           "reviewer": "", "상태": DRAFT_STATE})
    res = {"후보_수": len(profs), "종합": m["counts"], "비교표": table, "사람_확인_목록": review,
           "manual_decisions_초안": drafts, "포함_후보_id": [x["company_id"] for x in m["rows"] if x["overall"] == "포함 후보"],
           "사용_기준": m["rules_used"], "분석대상": tested}
    basis = ["국조법 시행령 제14조(정상가격 산출방법 선택 기준 — 비교가능성)·국조칙 비교가능성 분석요소(기능·자산·위험)",
             "국조법 시행령 제2조②(특수관계 — 의결권 있는 주식 50% 이상, 법정 하한)"]
    notes = [m["note"], "대분류(제조·유통·서비스·무형자산)는 설명용 — 판정은 항목별 숫자 비교로만 함.",
             "manual_decisions_초안은 사람이 사유·근거를 확인하고 reviewer를 채운 뒤 tp_comparable_screen에 넣는다.",
             "포함 후보도 거래 단계·시장·계약 조건 등 숫자로 안 잡히는 비교가능성은 사람이 확인한다."]
    return {"결과": res, "근거": basis, "주의": notes}
