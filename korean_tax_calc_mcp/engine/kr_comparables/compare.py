"""분석대상 프로필 × 후보 프로필 → 항목별 숫자 차이 + (기준을 받으면) 가까움/다름/불명 + 종합. 순수 함수. Claude 작성(2026-11-16, 0.61.0 11-17).

계산 MCP는 숫자 비교까지만 한다. 관행·우리 규칙 기준값은 두지 않는다 — rules로 받은 값만 쓰고(값·출처는 조문 MCP transfer_pricing_guide),
rules가 없으면 법정 기준(최대주주 50% 이상 → 제외 후보, 특수관계 거래 의존 50% 이상 → 사람 확인)만 적용한다.
결과(후보별 숫자·차이·근거 문장·접수번호)는 그대로 조문 MCP 판단 도구에 넘길 수 있다.

rules 키(단위) — 없는 키의 기준은 끔
  mix_max_diff(비율 차이, 예 0.2) · coverage_min·coverage_max(배) — 매출 구성: 주된 갈래 비중 차이, 커버리지 범위 밖이면 불명
  ratio_low·ratio_high(배) · ppe_abs_tol·rnd_abs_tol(비율 차이) — 재고/매출·유형자산/자산·연구개발/매출
  advert_mult·sga_mult(배, 1/x~x — advert_mult가 없으면 광고는 ratio_low~ratio_high) · advert_abs_tol·sga_abs_tol(비율 차이) — 광고판촉/매출·판관비/매출
  independence_legal_pct(%, 50 이하만 — 더 엄격하게만), control_dependence(비율, 0.5 이하만) — 법정 기준, 안 주면 50%
  related_review(비율) — 사용자 검토선(기본값 없음 — 법령·판례상 숫자 기준 없음). 특수관계 매출 또는 매입 비중 이상이면 사람 확인
  related_purchase_review(비율) — 특수관계 매입 비중(÷ 매출원가)을 따로 줄 때. 안 주면 매입에도 related_review를 씀
  loss_review_years(연도 수) · unknown_review_count(개) · mix_unverified_review(비율)
종합(기준을 준 항목만)
  제외 후보: [M1] 매출 구성 다름 / [K3] 재고·유형자산 둘 다 다름 / [K4] 원재료 재고 유무가 다르고 재고 또는 유형자산도 다름 / [I1] 최대주주 50% 이상(법정 준용)
  사람 확인: [M0] 매출 구성 불명 / [U1] 불명 다수 / [K1]·[K2]·[K5] 하나만 다름 / [A1] 광고판촉 / [A2] 판관비율 / [P1] 품목 키워드 겹침 없음 /
            [I2] 특수관계 매출·매입 비중 / [C2] 특수관계 거래 의존 50% 이상(법정 준용) / [I3] 비상장 지분 50% 이상(제외 아님) / [L2] 지속 손실 / [R1] 매출 행 분류 확인
  표시만: [W3] 연구개발 다름, [L1] 손실 연도, [P0] 품목 대조 자료 없음, [C1] 실질 지배 신호 문장(참고)
경계값은 포함(≤).
"""
import copy
import re

from .schema import STATUS_OK, STATUS_NONE

# 법정 기준만 상수로 둔다(시행령 제2조② — 의결권 50%, 실질 지배의 거래 의존 50%). 나머지 기준은 rules로만.
LEGAL_RULES = {"independence_legal_pct": 50.0, "control_dependence": 0.50}
RULE_KEYS = ("mix_max_diff", "coverage_min", "coverage_max", "ratio_low", "ratio_high", "ppe_abs_tol", "rnd_abs_tol",
             "advert_mult", "advert_abs_tol", "sga_mult", "sga_abs_tol", "related_review", "related_purchase_review", "loss_review_years",
             "unknown_review_count", "mix_unverified_review")
ALL_KEYS = tuple(LEGAL_RULES) + RULE_KEYS
# 실질 지배 — 공시 숫자로 못 재는 항목은 질문으로 붙임(시행령 제2조②)
CONTROL_QUESTIONS = ["상대 법인 임원이 이 회사 대표임원이거나 임원의 절반 이상인가(최근 3년 이내 겸직 포함)?",
                     "사업활동 자금(자기자본+타인자본)의 절반 이상을 특정 법인에서 차입하거나 보증받는가?",
                     "특정 지식재산권 사용대가가 전체 영업비용의 절반 이상인가?",
                     "공정거래법상 같은 기업집단 소속(계열회사)인가?"]
FUNCTION_QUESTIONS = {"own_marketing": ("자체 마케팅(시장개척·브랜드 홍보)을 하는가", "advert_ratio"),
                      "bears_inventory_risk": ("재고위험을 부담하는가", "inv_to_sales")}
RULE_ALIASES = {"related_sales_review": "related_review"}   # 0.60.x 이름
NOT_LEGAL = "법정 특수관계 판정 아님 — 실질 지배·거래의 독립성 판단은 조문 MCP에서 확인"
LAW_MCP = "판단 기준·판례는 조문 MCP(korean-tax-mcp) transfer_pricing_guide·transfer_pricing_cases에서 확인"
NO_PRACTICE = "관행 기준 미적용 — 조문 MCP transfer_pricing_guide(비교대상 선정 기준)의 값을 rules로 넣으세요. 지금은 법정 기준(최대주주 50% 이상, 특수관계 거래 의존 50% 이상)만 적용"
RULE_SOURCE = {
    "independence_legal_pct": ("법정 준용", "국조법 시행령 제2조제2항(의결권 주식 50% 이상)을 비교대상 독립성에 준용"),
    "control_dependence": ("법정 준용", "국조법 시행령 제2조제2항 실질 지배(사업활동의 50% 이상 거래 의존)를 숫자 신호로 — 사람 확인"),
    "related_review": ("입력", "특수관계 매출 또는 매입 비중 사용자 검토선 — 사람 확인. 법령·판례상 비교대상의 특수관계 거래 비중 숫자 기준 없음(기본값 없음). " + NOT_LEGAL),
    "related_purchase_review": ("관행", "특수관계 매입 비중(÷ 매출원가) — 주면 매입 쪽은 이 값으로, 안 주면 related_review를 매입에도 씀. " + NOT_LEGAL),
    "loss_review_years": ("관행", "손실 연도 수 — 자동 제외하지 않고 사람 확인"),
    "mix_max_diff": ("우리 규칙", "매출 구성 주된 갈래 비중 차이"),
    "coverage_min": ("우리 규칙", "매출 구성 커버리지 하한"), "coverage_max": ("우리 규칙", "매출 구성 커버리지 상한"),
    "ratio_low": ("우리 규칙", "재고·유형자산·연구개발 비율 배수 하한"), "ratio_high": ("우리 규칙", "재고·유형자산·연구개발 비율 배수 상한"),
    "ppe_abs_tol": ("우리 규칙", "유형자산 비중 차이 허용"), "rnd_abs_tol": ("우리 규칙", "연구개발 비율 차이 허용 — 표시만"),
    "advert_mult": ("우리 규칙", "광고판촉/매출 배수"), "advert_abs_tol": ("우리 규칙", "광고판촉/매출 차이 허용"),
    "sga_mult": ("우리 규칙", "판관비/매출 배수"), "sga_abs_tol": ("우리 규칙", "판관비/매출 차이 허용"),
    "unknown_review_count": ("우리 규칙", "불명 항목 수 → 사람 확인"),
    "mix_unverified_review": ("우리 규칙", "원문 유형 칸 없이 분류한 매출 행 비중 → 사람 확인"),
}
OTHER_CRITERIA = {
    "범위·중위값 조정(tp_comparable_screen·arm_length_range)": ("법정", "국조법 시행령 제15조제5항·제6항"),
    "품목 키워드 겹침(tested.product_keywords)": ("입력", "겹침 없으면 원문 문장을 붙여 사람 확인 — 숫자로 제외하지 않음"),
}


def merged_rules(rules):
    r = dict(LEGAL_RULES)
    r.update({k: None for k in RULE_KEYS})
    r.update({RULE_ALIASES.get(k, k): v for k, v in (rules or {}).items()})
    return r


def labeled_rules(r, given=None):
    given = {RULE_ALIASES.get(k, k) for k in (given or {})}
    out = {}
    for k, v in r.items():
        a, b = RULE_SOURCE.get(k, ("우리 규칙", ""))
        out[k] = {"값": v if v is not None else "꺼짐", "구분": a, "근거": b,
                  "입력": "사용자 입력" if k in given else ("법정 — 항상 적용" if k in LEGAL_RULES else "입력 없음 — 꺼짐(값·출처는 조문 MCP transfer_pricing_guide)")}
    out.update({k: {"값": "—", "구분": a, "근거": b} for k, (a, b) in OTHER_CRITERIA.items()})
    out["판단_근거_확인"] = {"값": "—", "구분": "안내", "근거": LAW_MCP}
    return out


ITEMS = {"revenue_mix": "매출 구성", "inventory": "재고", "ppe": "유형자산", "rnd": "연구개발", "advert": "광고판촉", "sga": "판관비율", "raw_material": "원재료 재고"}
CORE = ("revenue_mix",)
NEAR, DIFF, UNK, NOCRIT = "가까움", "다름", "불명", "기준 없음"
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


def _norm_kw(x):
    return re.sub(r"\s", "", str(x)).lower()


def product_match(keywords, cand):
    """분석대상 품목 키워드 ↔ 후보 사업 설명·매출 행 이름. 반환 {키워드, 겹침, 원문} 또는 None(키워드 없음)."""
    kws = [k for k in (keywords or []) if str(k).strip()]
    if not kws:
        return None
    bd = cand.get("business_desc")
    desc = bd.get("value") if isinstance(bd, dict) and bd.get("status") == STATUS_OK else ""
    rows = ((cand.get("mix_coverage") or {}).get("evidence") or {}).get("rows") or [] if isinstance(cand.get("mix_coverage"), dict) else []
    labels = [str(x.get("label", "")) for x in rows]
    hay = _norm_kw(desc + " " + " ".join(labels))
    if not hay.strip():
        return {"키워드": kws, "겹침": None, "원문": []}
    hits = [k for k in kws if _norm_kw(k) in hay]
    sents = [x.strip() for x in re.split(r"(?<=[다음함])\.\s*", desc) if len(x.strip()) >= 10][:2]
    return {"키워드": kws, "겹침": hits, "원문": [x[:200] for x in sents] + ([f"매출 행: {', '.join(labels[:8])}"] if labels else [])}


def _has(r, *ks):
    return all(r.get(k) is not None for k in ks)


def compare_profile(tested, cand, rules=None):
    """tested: {main_category, main_share, inventory_basis('ratio'|'raw_material'), inv_to_sales, raw_material_inv,
                ppe_ratio, rnd_ratio, advert_ratio, sga_ratio(선택), product_keywords(선택), own_marketing·bears_inventory_risk(선택)}
    cand: 표준 프로필(schema.PROFILE_FIELDS, 값은 value() 형식). rules: RULE_KEYS 중 준 것만 기준으로 씀."""
    r = merged_rules(rules)
    items = {}
    # 1 매출 구성 — 숫자(후보 비중·차이·커버리지)는 늘 냄
    cov = _num(cand.get("mix_coverage"), False)
    share = _num(cand.get("mix_" + tested["main_category"]), False)
    cov_ok = cov is not None and (r["coverage_min"] is None or cov >= r["coverage_min"] - EPS) and (r["coverage_max"] is None or cov <= r["coverage_max"] + EPS)
    bound = None
    if share is None or not cov_ok:
        v = UNK
        if share is None and cov_ok and _has(r, "mix_max_diff") and tested["main_category"] in ("product", "merchandise"):
            vals = [_num(cand.get("mix_" + k), False) for k in ("service", "sw_license", "platform_fee", "other")]
            if all(x is not None for x in vals):
                bound = max(0.0, 1 - sum(vals))
                if bound < tested["main_share"] - r["mix_max_diff"] - EPS:
                    v = DIFF
    elif _has(r, "mix_max_diff"):
        v = NEAR if abs(share - tested["main_share"]) <= r["mix_max_diff"] + EPS else DIFF
    else:
        v = NOCRIT
    mcell = cand.get("mix_" + tested["main_category"])
    mnote = mcell.get("note", "") if isinstance(mcell, dict) and v == UNK else (
        f"제품·상품 배분은 불명이나 상한 {bound:.0%}로도 차이가 큼" if bound is not None else "")
    items["revenue_mix"] = {"verdict": v, "candidate": share, "tested": tested["main_share"], "coverage": cov, "note": mnote,
                            "차이": None if share is None else round(share - tested["main_share"], 6),
                            "rule": f"비중 차이 ≤ {r['mix_max_diff']}" if _has(r, "mix_max_diff") else "기준 없음"}
    # 2 재고
    raw_basis = tested.get("inventory_basis", "ratio") == "raw_material"
    asset_rule = _has(r, "ratio_low", "ratio_high")
    if raw_basis:
        c = _flag(cand.get("raw_material_inv")); t = bool(tested.get("raw_material_inv"))
        items["inventory"] = {"verdict": UNK if c is None else (NEAR if c == t else DIFF), "candidate": c, "tested": t, "rule": "원재료·재공품 재고 유무 같음"}
    else:
        c = _num(cand.get("inv_to_sales")); t = tested.get("inv_to_sales")
        items["inventory"] = {"verdict": _ratio_near(c, t, r["ratio_low"], r["ratio_high"], 0.0) if asset_rule else (UNK if c is None else NOCRIT),
                              "candidate": c, "tested": t, "배수": _mult(c, t), "rule": f"재고/매출 {r['ratio_low']}~{r['ratio_high']}배" if asset_rule else "기준 없음"}
    # 3 유형자산, 4 연구개발, 5 광고, 6 판관비
    for key, fld, need, lohi, tol in (("ppe", "ppe_ratio", ("ratio_low", "ratio_high"), lambda: (r["ratio_low"], r["ratio_high"]), "ppe_abs_tol"),
                                      ("rnd", "rnd_ratio", ("ratio_low", "ratio_high"), lambda: (r["ratio_low"], r["ratio_high"]), "rnd_abs_tol"),
                                      ("advert", "advert_ratio", ("advert_mult",) if r.get("advert_mult") is not None else ("ratio_low", "ratio_high"),
                                       lambda: (1 / r["advert_mult"], r["advert_mult"]) if r.get("advert_mult") is not None else (r["ratio_low"], r["ratio_high"]), "advert_abs_tol"),
                                      ("sga", "sga_ratio", ("sga_mult",), lambda: (1 / r["sga_mult"], r["sga_mult"]), "sga_abs_tol")):
        t = tested.get(fld)
        if key == "sga" and t is None:
            continue                                   # 분석대상 판관비율을 주지 않으면 비교하지 않음
        c = _num(cand.get(fld))
        if _has(r, *need):
            lo, hi = lohi()
            verdict = _ratio_near(c, t, lo, hi, r[tol] or 0.0) if t is not None else UNK
            rule = f"{lo:g}~{hi:g}배 또는 차이 ≤ {r[tol] or 0:g}"
        else:
            verdict, rule = (UNK if c is None or t is None else NOCRIT), "기준 없음"
        items[key] = {"verdict": verdict, "candidate": c, "tested": t, "배수": _mult(c, t), "차이": None if c is None or t is None else round(c - t, 6), "rule": rule}
    # 7 원재료(사실 비교 — 유무)
    if not raw_basis and tested.get("raw_material_inv") is not None:
        c = _flag(cand.get("raw_material_inv")); t = bool(tested["raw_material_inv"])
        items["raw_material"] = {"verdict": UNK if c is None else (NEAR if c == t else DIFF), "candidate": c, "tested": t, "rule": "원재료·재공품 재고 유무 같음"}
    V = {k: x["verdict"] for k, x in items.items()}
    excl, review, flags = [], [], []
    if V["revenue_mix"] == DIFF:
        excl.append("[M1] 매출 구성 다름" + (f" — {items['revenue_mix']['note']}" if items["revenue_mix"].get("note") else ""))
    elif V["revenue_mix"] == UNK and _has(r, "mix_max_diff"):
        review.append("[M0] 매출 구성 불명" + (f" — {items['revenue_mix']['note']}" if items["revenue_mix"].get("note") else ""))
    if asset_rule:                                     # 재고·유형자산·원재료 조합은 자산 비율 기준을 받았을 때만
        raw_diff = (raw_basis and V["inventory"] == DIFF) or V.get("raw_material") == DIFF
        inv_diff = V["inventory"] == DIFF and not raw_basis
        if inv_diff and V["ppe"] == DIFF:
            excl.append("[K3] 재고·유형자산 둘 다 다름")
        elif raw_diff and (inv_diff or V["ppe"] == DIFF):
            excl.append("[K4] 원재료·재공품 재고 유무까지 다름(" + ("재고" if inv_diff else "유형자산") + " 차이와 겹침)")
        else:
            for k, code, lab in (("inventory", "K1", "재고"), ("ppe", "K2", "유형자산"), ("raw_material", "K5", "원재료 재고 유무")):
                if V.get(k) == DIFF:
                    review.append(f"[{code}] {lab}만 다름 — 조정 가능한 차이인지 사람 확인(운전자본 조정은 tp_comparable_screen wca)")
    if V.get("advert") == DIFF:
        review.append(f"[A1] 광고판촉/매출 다름(후보 {items['advert']['candidate']:.1%}, 분석대상 {items['advert']['tested']:.1%})")
    if V.get("sga") == DIFF:
        review.append(f"[A2] 판관비/매출 다름(후보 {items['sga']['candidate']:.1%}, 분석대상 {items['sga']['tested']:.1%})")
    if V.get("rnd") == DIFF:
        flags.append("[W3] 연구개발 다름 — 표시만")
    pm = product_match(tested.get("product_keywords"), cand)
    if pm is not None:
        if pm["겹침"] is None:
            flags.append("[P0] 품목 대조 자료 없음(사업 설명·매출 행 없음)")
        elif not pm["겹침"]:
            review.append(f"[P1] 품목 키워드({', '.join(map(str, pm['키워드'][:5]))}) 겹침 없음 — 원문 확인")
    # 독립성·실질 지배(법정 준용) + 관행(rules)
    ms = _num(cand.get("max_shareholder_pct"), False)
    legal = ms is not None and ms >= r["independence_legal_pct"] - EPS
    indep = []
    if legal:
        indep.append(f"[I1] 최대주주 {ms}% ≥ {r['independence_legal_pct']:g}%(법정 준용, 국조법 시행령 제2조제2항)")
        excl.append(indep[-1])
    rs_, rp_ = _num(cand.get("related_sales_ratio"), False), _num(cand.get("related_purchase_ratio"), False)
    for x, lab in ((rs_, "매출"), (rp_, "매입")):
        rk = "related_purchase_review" if lab == "매입" and _has(r, "related_purchase_review") else "related_review"
        if x is not None and _has(r, rk) and x >= r[rk] - EPS:
            indep.append(f"[I2] 특수관계 {lab} {x:.0%} ≥ {r[rk]:.0%}(입력한 검토선) — 사람 확인, 법정 특수관계 판정 아님")
            review.append(indep[-1])
        if x is not None and x >= r["control_dependence"] - EPS:
            review.append(f"[C2] 특수관계 {lab} 의존 {x:.0%} ≥ {r['control_dependence']:.0%} — 실질 지배 신호(법정 준용, 국조법 시행령 제2조제2항), 사람 확인")
    op = _num(cand.get("owner_pct"), False)
    if op is not None and op >= r["independence_legal_pct"] - EPS and not legal:
        f = lambda x: "불명" if x is None else f"{x:.0%}"
        indep.append(f"[I3] 최대주주·지배기업 지분 {op:g}%(감사보고서 주석) — 지분만으로 제외하지 않음, 특수관계 매출 {f(rs_)}·매입 {f(rp_)}로 거래의 독립성 확인(판단은 조문 MCP)")
        review.append(indep[-1])
    cs = cand.get("control_signals")
    sig = cs.get("value") if isinstance(cs, dict) and cs.get("status") == STATUS_OK else None
    if sig:
        kinds = sorted({x.get("kind", "") for x in sig})
        flags.append(f"[C1] 실질 지배 신호 문장({', '.join(kinds)}) — 참고(표시만), 법정 특수관계 판정 아님")
    lc = cand.get("loss_years")
    loss = _num(lc, False)
    if loss is not None and _has(r, "loss_review_years") and loss >= r["loss_review_years"]:
        review.append(f"[L2] 지속 손실({lc.get('note') or f'{loss}개 연도'}) — 사람 확인(손실만으로 제외하지 않음)")
    elif loss:
        flags.append(f"[L1] 영업손실 {lc.get('note') or f'{loss}개 연도'} — 표시만")
    unv, unv_rows = _unverified_mix(cand)
    if unv is not None and _has(r, "mix_unverified_review") and unv >= r["mix_unverified_review"] - EPS:
        items["revenue_mix"]["review"] = f"[R1] 매출 행 분류 확인 필요 — 원문 유형 칸이 없는 행 {unv:.0%}({', '.join(unv_rows[:3])})를 모델·규칙으로 분류"
        review.append(items["revenue_mix"]["review"])
    all_v = list(V.values())
    if _has(r, "unknown_review_count") and all_v.count(UNK) >= r["unknown_review_count"]:
        review.append(f"[U1] 불명 {all_v.count(UNK)}개(" + ", ".join(ITEMS[k] for k, x in V.items() if x == UNK) + ")")
    fq = []
    for k, (q, fld) in FUNCTION_QUESTIONS.items():
        if isinstance(tested.get(k), bool):
            it = "advert" if fld == "advert_ratio" else "inventory"
            fq.append({"질문": q, "분석대상": "예" if tested[k] else "아니오", "후보_단서": f"{ITEMS[it]} {items[it]['candidate']}", "근거": "기능·위험 차이 — " + LAW_MCP})
    overall = "제외 후보" if excl else ("사람 확인" if review else "포함 후보")
    return {"company_id": cand.get("company_id"), "company_name": cand.get("company_name"), "items": items,
            "related_shares": {"매출": rs_, "매입": rp_},
            "independence": indep or ["문제 없음" if ms is not None else "최대주주 지분 불명"], "overall": overall,
            "reasons": excl + review or ["제외·사람 확인 사유 없음(준 기준 안에서)"], "warnings": flags, "product_match": pm, "function_questions": fq,
            "rules_used": r}


def _mult(c, t):
    return None if c is None or not t else round(c / t, 4)


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
    return {"rows": rows, "counts": counts, "rules_used": merged_rules(rules),
            "note": "rules로 받은 기준만 적용(값·출처는 조문 MCP transfer_pricing_guide) — 없으면 법정 기준만. 사람 확인 후보는 근거를 보고 포함·제외(이유 필수)."}


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
    pk = t.get("product_keywords")
    if pk is not None and (not isinstance(pk, list) or not all(isinstance(x, str) for x in pk)):
        raise ValueError("tested.product_keywords는 문자열 목록(예: ['의료기기', '진단'])")
    for k in ("own_marketing", "bears_inventory_risk"):
        if t.get(k) is not None and not isinstance(t[k], bool):
            raise ValueError(f"tested.{k}는 true|false")
    for k in ("ppe_ratio", "rnd_ratio", "advert_ratio", "inv_to_sales", "sga_ratio"):
        v = t.get(k)
        if v is not None and (not isinstance(v, (int, float)) or v < 0):
            raise ValueError(f"tested.{k}는 0 이상 비율")


def _evidence(cand, item):
    fld = {"revenue_mix": "mix_coverage", "inventory": "inv_to_sales", "ppe": "ppe_ratio", "rnd": "rnd_ratio", "advert": "advert_ratio", "sga": "sga_ratio",
           "raw_material": "raw_material_inv"}[item]
    c = cand.get(fld) or {}
    e = {"상태": c.get("status"), **(c.get("evidence") or {})}
    if c.get("note"):
        e["메모"] = c["note"]
    return e


def run_tool(tested, candidates, rules=None):
    """kr_comparable_profile_compare 본체 — {'결과', '근거', '주의'}."""
    _check_tested(tested)
    profs = _profiles_from(candidates)
    unknown = [k for k in (rules or {}) if RULE_ALIASES.get(k, k) not in ALL_KEYS]
    if unknown:
        raise ValueError(f"rules에 모르는 키: {unknown} — 쓸 수 있는 키: {list(RULE_KEYS)} (법정 {list(LEGAL_RULES)}은 더 느슨하게 바꿀 수 없음)")
    for k, lim in LEGAL_RULES.items():
        v = (rules or {}).get(k)
        if v is not None and not isinstance(v, bool) and isinstance(v, (int, float)) and v > lim:
            raise ValueError(f"rules.{k}={v} — 법정 기준 {lim:g}보다 느슨하게 둘 수 없음(국조법 시행령 제2조제2항)")
    for k, v in (rules or {}).items():
        if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0):
            raise ValueError(f"rules.{k}는 0 이상 숫자(끄려면 빼거나 null)")
    m = compare_many(tested, profs, rules)
    table, review, drafts = [], [], []
    for p, x in zip(profs, m["rows"]):
        row = {"company_id": x["company_id"], "company_name": x["company_name"], "종합": x["overall"], "사유": x["reasons"], "표시": x["warnings"], "독립성": x["independence"],
               "특수관계_거래_비중": {"매출": x["related_shares"]["매출"], "매입": x["related_shares"]["매입"],   # 기준과 상관없이 늘 숫자(없으면 None)
                                "근거": "감사보고서·사업보고서 특수관계자 주석(매출 ÷ 매출, 매입 ÷ 매출원가) — 50% 이상이면 [C2]"},
               **{ITEMS[k]: {"판정": v["verdict"], "후보": v["candidate"], "분석대상": v["tested"], **{kk: v[kk] for kk in ("차이", "배수") if kk in v}} for k, v in x["items"].items()}}
        table.append(row)
        if x["overall"] == "사람 확인":
            cs = p.get("control_signals") or {}
            review.append({"company_id": x["company_id"], "company_name": x["company_name"], "사유": x["reasons"], "표시": x["warnings"],
                           "실질_지배_근거(참고)": (cs.get("value") or []) if cs.get("status") == "확보" else [],
                           "품목_대조": x["product_match"], "기능_질문": x["function_questions"],
                           "실질_지배_질문": CONTROL_QUESTIONS if any(c.startswith(("[C1]", "[C2]", "[I2]", "[I3]")) for c in x["reasons"] + x["warnings"]) else [],
                           "근거": {ITEMS[k]: _evidence(p, k) for k, v in x["items"].items() if v["verdict"] not in (NEAR, NOCRIT) or v.get("review")},
                           "매출_행": ((p.get("mix_coverage") or {}).get("evidence") or {}).get("rows", [])[:20],
                           "선택지": "확인 뒤 포함하면 그대로 두고, 빼려면 manual_decisions에 {decision: reject, reason} 추가"})
        elif x["overall"] == "제외 후보":
            drafts.append({"company_id": x["company_id"], "decision": "reject",
                           "reason": "프로필 비교(기능·자산·위험): " + "; ".join(x["reasons"]),
                           "evidence": "; ".join(f"{ITEMS[k]} {v['verdict']}(후보 {v['candidate']}, 분석대상 {v['tested']}) 근거 {p.get('rcept_no') or ''}"
                                                for k, v in x["items"].items() if k in ("revenue_mix", "inventory", "ppe", "raw_material")),
                           "reviewer": "", "상태": DRAFT_STATE})
    res = {**({"안내": NO_PRACTICE} if not any(v is not None for v in (rules or {}).values()) else {}), "특수관계_안내": NOT_LEGAL, "후보_수": len(profs), "종합": m["counts"], "비교표": table, "사람_확인_목록": review,
           "manual_decisions_초안": drafts, "포함_후보_id": [x["company_id"] for x in m["rows"] if x["overall"] == "포함 후보"],
           "사용_기준": labeled_rules(m["rules_used"], rules), "분석대상": tested}
    basis = ["국조법 시행령 제14조(정상가격 산출방법 선택 기준 — 비교가능성)·국조칙 비교가능성 분석요소(기능·자산·위험)",
             "국조법 시행령 제2조제2항(특수관계 — 의결권 있는 주식 50% 이상, 실질 지배)를 비교대상 독립성에 준용"]
    notes = ([NO_PRACTICE] if not any(v is not None for v in (rules or {}).values()) else []) + [m["note"], "대분류(제조·유통·서비스·무형자산)는 설명용 — 판정은 항목별 숫자 비교로만 함.",
             "manual_decisions_초안은 사람이 사유·근거를 확인하고 reviewer를 채운 뒤 tp_comparable_screen에 넣는다.",
             "포함 후보도 거래 단계·시장·계약 조건 등 숫자로 안 잡히는 비교가능성은 사람이 확인한다.",
             "사유 코드 — 제외 후보: M1 매출 구성 다름·K3 재고·유형자산 둘 다 다름·K4 원재료 재고 유무까지 다름·I1 법정 지분 / 사람 확인: M0 매출 구성 불명·K1 재고만·K2 유형자산만·K5 원재료 재고 유무만 다름·"
             "A1 광고판촉·A2 판관비율 다름·P1 품목 키워드 겹침 없음·I2 특수관계 매출·매입·C2 거래 의존 50%·I3 비상장 지분 50% 이상·L2 지속 손실·R1 매출 행 분류·U1 불명 다수 / 표시: C1 실질 지배 신호 문장(참고)·W3 연구개발·L1 1년 손실·P0 품목 자료 없음.",
             NOT_LEGAL,
             "운전자본 조정은 재고·채권·채무 수준 차이만 조정 — 품목·거래단계·기능 차이는 해소하지 못함.",
             "같은 사유 코드가 붙은 회사를 일부는 넣고 일부는 빼면 기준이 일관되지 않음 — 보고서에서 점검.",
             LAW_MCP + ". 이 결과(비교표·사람_확인_목록)를 그대로 넘기면 됨."]
    return {"결과": res, "근거": basis, "주의": notes}
